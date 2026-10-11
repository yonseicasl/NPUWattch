# Workload — deepseek_v2_lite: one MoE decoder block, prefill and decode

One decoder block of DeepSeek-V2-Lite (16B parameters, 2.4B active per
token) on the TPU-like NPU, float32. Two run roots:

```bash
cd prefill && ./run      # T = 512 tokens
cd decode  && ./run      # T = 1 token, 512-entry KV cache
```

The block has two parts that the dense Llama and Gemma blocks don't have:

- **Multi-head latent attention (MLA).** The keys and values are compressed
  to a 512-wide latent vector (`kv_a_proj`), then expanded per head
  (`kv_b_proj`). The query heads are 192 wide (128 content + 64 rotary).
- **Mixture of experts (MoE).** 64 routed experts of width 1408, of which
  each token uses 6, plus 2 shared experts that every token uses. The
  router is a GEMM to 64 scores.

Model dimensions: hidden 2048, 16 heads, value heads 128 wide.

## The routing assumption

Which experts a token uses depends on the data. The run assumes a uniform
load: in prefill, every expert receives 512 × 6 / 64 = 48 tokens; in decode,
the one token goes to 6 experts. The expert GEMMs run as one batched matmul
(`torch.bmm`) over the 64 (or 6) experts. The router GEMM is simulated. The
top-k selection, the token gather and scatter, and the weighted sum of the
expert outputs are not. Rotary embedding, the causal mask, and the residual
adds are not simulated either. `how_the_data_was_made/RUN_MANIFEST.md` has
the list.

## Kernels

Prefill (T = 512):

| Window | Shape | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- | --- |
| `1_q_proj` | 512×2048 @ 2048×3072 | 139 312 | 17.9 mJ | 5.5 |
| `2_kv_a_proj` | 512×2048 @ 2048×576 | 54 389 | 3.65 mJ | 6.0 |
| `3_kv_b_proj` | 512×512 @ 512×4096 | 61 383 | 6.27 mJ | 5.8 |
| `4_attn_qk` | 16 × (512×192 @ 192×512) | 100 308 | 5.29 mJ | 6.6 |
| `5_attn_av` | 16 × (512×512 @ 512×128) | 76 224 | 3.63 mJ | 6.8 |
| `6_o_proj` | 512×2048 @ 2048×2048 | 101 607 | 12 mJ | 5.6 |
| `7_router` | 512×2048 @ 2048×64 | 16 117 | 517 µJ | 7.7 |
| `8_experts_up_gate` | 64 × (48×2048 @ 2048×2816) | 4 625 367 | 151 mJ | 8.5 |
| `9_experts_down` | 64 × (48×1408 @ 1408×2048) | 3 164 956 | 81.9 mJ | 9.2 |
| `10_shared_up_gate` | 512×2048 @ 2048×5632 | 226 925 | 33 mJ | 5.6 |
| `11_shared_down` | 512×2816 @ 2816×2048 | 246 805 | 17.9 mJ | 6.1 |
| `12_softmax_p0..p2` | 16×512×512 | 209 654 | 2.92 mJ | — |
| `13_rmsnorm_p0..p1` | 512×2048 | 52 561 | 536 µJ | — |
| `14_silu_mul` | 512×1408 | 42 656 | 357 µJ | — |

Total: **337.2 mJ** over 9.12 M cycles, 43.9 G useful MACs, 7.7 pJ per useful
MAC. DRAM is 31% of the energy. The non-GEMM kernels are 1.1%.

Decode (T = 1):

| Window | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- |
| `1_q_proj` | 76 946 | 1.02 mJ | 161 |
| `2_kv_a_proj` | 16 736 | 207 µJ | 176 |
| `3_kv_b_proj` | 26 466 | 360 µJ | 172 |
| `4_attn_qk` (KV 512) | 27 305 | 342 µJ | 217 |
| `5_attn_av` (KV 512) | 15 057 | 160 µJ | 153 |
| `6_o_proj` | 51 924 | 678 µJ | 162 |
| `7_router` | 2 371 | 21.2 µJ | 162 |
| `8_experts_up_gate` (6 experts) | 420 210 | 5.67 mJ | 164 |
| `9_experts_down` (6 experts) | 211 418 | 2.86 mJ | 165 |
| `10_shared_up_gate` | 140 446 | 1.88 mJ | 163 |
| `11_shared_down` | 101 989 | 1.08 mJ | 187 |
| non-GEMM kernels (6 windows) | 4 414 | 12.1 µJ | — |

Total: **14.3 mJ** over 1.10 M cycles, 86.3 M useful MACs, 166 pJ per useful
MAC. DRAM is 90% of the energy.

## What to look at

- **Prefill: the experts.** The two expert kernels are 69% of the block's
  energy and 85% of its cycles. Each expert GEMM has only 48 rows, so the
  weight-stationary array loads a 128×128 weight tile and streams 48 inputs
  through it before the next load. The energy per useful MAC is 8.5 to 9.2 pJ,
  against 5.5 to 5.6 pJ in the dense projections with 512 rows. The array is full in
  both cases; the difference is the weight loads and the DRAM traffic per
  MAC. This is the cost of
  MoE on a large systolic array: fewer MACs per token than a dense FFN, but
  each MAC is more expensive.
- **Decode: DRAM.** Every GEMM is a matrix-vector product. The weights are
  read once from DRAM and used once, so DRAM takes 90% of the energy and
  the arrays 4%. One decoded token costs 14.3 mJ, and 512 prefill tokens
  cost 337.2 mJ, or 0.66 mJ per token.
- **The router** is a small GEMM (N = 64) with a higher cost per MAC: the
  weight tile has 64 real columns of 128, so half of the active PE cycles are
  empty (`NW-6222` reports 50%). The empty PEs are clock-gated and cost
  leakage only; the higher cost per MAC (7.7 pJ) is the data movement, which
  is shared by half as many MACs.

## Files

```
prefill/, decode/           one run root each: config.yml, togsim_results/, outputs/,
                            booksim2_config/, kernels.yaml, run, out/, how_the_data_was_made/
```

The hardware model is in `../` (the design folder). The `run` scripts pass
it with `--compound-components ../../compound_components.yaml` and the two
other definition flags.

## Messages you'll see

- `WARNING (NW-6201)` ×6: the softmax, RMSNorm, and SiLU kernels have no
  `linalg.matmul`.
- `WARNING (NW-6208)` ×3: the SFU is charged at fp32 in the kernels that use
  the exponent (softmax, SiLU). The GEMM kernels are fp32 too, so this is
  the right data type.
- `INFO (NW-6001)`: the six non-MAC kernels use the f32 datapath of the first
  GEMM kernel.
- `NW-8212` ×3, `NW-6607`, `NW-8111`, as in the design folder.

## How the sample data was made

Same image and config as the design folder, run on 2026-10-10. The script in
`how_the_data_was_made/` compiles each kernel of the table as its own
function with random float32 tensors of the given shapes. Prefill took 4 h
42 min of wall time (the 64-expert batched matmul alone took 2.4 h); decode
took 37 min. All outputs match the CPU reference. See
`docs/PYTORCHSIM_DOCKER.md` for the procedure.
