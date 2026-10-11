# Workload — llama3_8b: one decoder block, prefill and decode

One decoder block of Llama-3-8B on the TPU-like NPU, float32. The layers are
the ones of the Timeloop example (`../../../timeloop/gemmini_like/llama3_8b/`),
plus the three non-GEMM kernels that Timeloop cannot see: softmax, RMSNorm,
and the SiLU gate. Two run roots:

```bash
cd prefill && ./run      # T = 512 tokens
cd decode  && ./run      # T = 1 token, 512-entry KV cache
```

Model dimensions: hidden 4096, 32 query heads and 8 key-value heads of 128,
FFN 14336 with SiLU. The attention GEMMs run per head with `torch.bmm`.
Rotary embedding, the causal mask, and the residual adds are not simulated.

## Kernels

Prefill (T = 512):

| Window | Shape | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- | --- |
| `1_q_proj` | 512×4096 @ 4096×4096 | 345 779 | 49.0 mJ | 5.7 |
| `2_kv_proj` | 512×4096 @ 4096×2048 | 173 832 | 24.4 mJ | 5.7 |
| `3_attn_qk` | 32 × (512×128 @ 128×512) | 152 117 | 7.56 mJ | 7.0 |
| `4_attn_av` | 32 × (512×512 @ 512×128) | 151 557 | 7.50 mJ | 7.0 |
| `5_o_proj` | 512×4096 @ 4096×4096 | 326 832 | 49.0 mJ | 5.7 |
| `6_ffn_up_gate` | 512×4096 @ 4096×28672 | 3 267 126 | 360 mJ | 6.0 |
| `7_ffn_down` | 512×14336 @ 14336×4096 | 1 716 468 | 174 mJ | 5.8 |
| `8_softmax_p0..p2` | 32×512×512 | 420 777 | 9.07 mJ | — |
| `9_rmsnorm_p0..p1` | 512×4096 | 108 919 | 1.42 mJ | — |
| `10_silu_mul` | 512×14336 | 428 866 | 8.99 mJ | — |

Total: **691 mJ** over 7.09 M cycles, 114 G useful MACs, 6.1 pJ per useful
MAC. The two systolic arrays take 83% of the energy and DRAM 12%. The six
non-GEMM windows are 2.8%. This is the TPU-like design at its best: large
GEMMs with 512 rows keep the weight-stationary arrays full, and the energy
per MAC is close to the 1024³ matmul of the design folder (5.7 pJ).

Decode (T = 1):

| Window | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- |
| `1_q_proj` | 203 356 | 2.81 mJ | 167 |
| `2_kv_proj` | 102 319 | 1.41 mJ | 168 |
| `3_attn_qk` (KV 512) | 29 304 | 354 µJ | 169 |
| `4_attn_av` (KV 512) | 30 034 | 358 µJ | 171 |
| `5_o_proj` | 203 356 | 2.81 mJ | 167 |
| `6_ffn_up_gate` | 1 420 007 | 21.3 mJ | 181 |
| `7_ffn_down` | 1 771 963 | 15.1 mJ | 257 |
| non-GEMM kernels (6 windows) | 7 079 | 88 µJ | — |

Total: **44.2 mJ** over 3.77 M cycles, 222 M useful MACs, 199 pJ per useful
MAC. DRAM is 88% of the energy (activation 31%, data transfer 64%, refresh 5%).
Every GEMM is a matrix-vector product, so each weight is read from DRAM
once and used once, and the arrays sit idle: `7_ffn_down` streams 235 MB of
float32 weights for 59 M MACs.

`6_ffn_up_gate` takes fewer cycles than `7_ffn_down` although it has twice
the MACs. The two kernels got different tile choices from the autotuner;
the manifest records the cycles as measured.

## Prefill against decode

| | Prefill, 512 tokens | Decode, 1 token |
| --- | --- | --- |
| Energy of the block | 691 mJ | 44.2 mJ |
| Energy per token | 1.35 mJ | 44.2 mJ |
| DRAM share | 12% | 88% |
| Systolic arrays | 83% | 3% |
| pJ per useful MAC | 6.1 | 199 |

One decoded token costs about 33 times more than one prefill token on this
design. The Timeloop runs of the same block show the same change (DRAM 44%
in prefill, 97% in decode on the Gemmini-like design), with a far smaller
array and int8 operands.

## Files

```
prefill/, decode/           one run root each: config.yml, togsim_results/, outputs/,
                            booksim2_config/, kernels.yaml, run, out/, how_the_data_was_made/
```

The hardware model is in `../` (the design folder). The `run` scripts pass
it with `--compound-components ../../compound_components.yaml` and the two
other definition flags. To price the same runs with bf16 PEs:

```bash
cd prefill && ./run --compound-components ../../../tpu_like_bf16/compound_components.yaml --report out_bf16/
```

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
function with random float32 tensors of the given shapes. The prefill script
raises the compiler's lock wait at run time (`LOCK_TIMEOUT = 14400`), which
changes nothing in the simulation; without it the large FFN kernels fail with
a file-lock timeout during autotune. The decode `6_ffn_up_gate` kernel
failed this way in the first run and was rerun the next day with the same
setting (`run_llama3_8b_decode_ffn.py`). Prefill took 4 h 34 min of wall
time, of which `6_ffn_up_gate` took 3 h; decode took 85 min plus 56 min for
the rerun. All outputs match the CPU
reference. See `docs/PYTORCHSIM_DOCKER.md` for the procedure.
