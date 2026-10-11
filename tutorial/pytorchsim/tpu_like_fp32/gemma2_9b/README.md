# Workload — gemma2_9b: one decoder block, prefill and decode

One decoder block of Gemma-2-9B on the TPU-like NPU, float32. The layout is
the same as `../llama3_8b/`: the projections, the per-head attention GEMMs
(`torch.bmm`), the FFN GEMMs, and the three non-GEMM kernels. Two run roots:

```bash
cd prefill && ./run      # T = 512 tokens
cd decode  && ./run      # T = 1 token, 512-entry KV cache
```

Model dimensions: hidden 3584, 16 query heads and 8 key-value heads of 256,
FFN 14336 with GeGLU (`F.gelu(approximate="tanh")`). Against Llama-3-8B, the
hidden size is smaller, the heads are twice as wide, and the activation is a
GELU instead of a SiLU. Rotary embedding, the causal mask, attention logit
soft-capping, and the residual adds are not simulated.

## Kernels

Prefill (T = 512):

| Window | Shape | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- | --- |
| `1_q_proj` | 512×3584 @ 3584×4096 | 411 821 | 42.6 mJ | 5.7 |
| `2_kv_proj` | 512×3584 @ 3584×4096 | 415 722 | 42.6 mJ | 5.7 |
| `3_attn_qk` | 16 × (512×256 @ 256×512) | 100 824 | 6.65 mJ | 6.2 |
| `4_attn_av` | 16 × (512×512 @ 512×256) | 101 085 | 6.66 mJ | 6.2 |
| `5_o_proj` | 512×4096 @ 4096×3584 | 316 815 | 42.7 mJ | 5.7 |
| `6_ffn_up_gate` | 512×3584 @ 3584×28672 | 5 575 632 | 350 mJ | 6.6 |
| `7_ffn_down` | 512×14336 @ 14336×3584 | 2 691 664 | 173 mJ | 6.6 |
| `8_softmax_p0..p2` | 16×512×512 | 208 556 | 2.98 mJ | — |
| `9_rmsnorm_p0..p1` | 512×3584 | 86 747 | 1.11 mJ | — |
| `10_gelu_mul` | 512×14336 | 471 933 | 3.89 mJ | — |

Total: **672.2 mJ** over 10.4 M cycles, 104 G useful MACs, 6.5 pJ per useful
MAC. The two systolic arrays take 78% of the energy and DRAM 20%. The six
non-GEMM windows are 1.2%.

Decode (T = 1):

| Window | Cycles | Energy at 7nm | pJ per useful MAC |
| --- | --- | --- | --- |
| `1_q_proj` | 179 060 | 2.67 mJ | 182 |
| `2_kv_proj` | 179 087 | 2.67 mJ | 182 |
| `3_attn_qk` (KV 512) | 27 509 | 347 µJ | 166 |
| `4_attn_av` (KV 512) | 27 477 | 339 µJ | 162 |
| `5_o_proj` | 178 464 | 2.39 mJ | 163 |
| `6_ffn_up_gate` | 1 242 039 | 18.1 mJ | 176 |
| `7_ffn_down` | 1 049 115 | 12 mJ | 233 |
| non-GEMM kernels (6 windows) | 6 340 | 20.1 µJ | — |

Total: **38.5 mJ** over 2.89 M cycles, 203 M useful MACs, 190 pJ per useful
MAC. DRAM is 91% of the energy.

## Gemma next to Llama

| | Gemma-2-9B prefill | Llama-3-8B prefill | Gemma-2-9B decode | Llama-3-8B decode |
| --- | --- | --- | --- | --- |
| Useful MACs | 104 G | 114 G | 203 M | 223 M |
| Energy | 672.2 mJ | 666.2 mJ | 38.5 mJ | 42.9 mJ |
| pJ per useful MAC | 6.5 | 5.8 | 190 | 192 |
| DRAM share | 20% | 12% | 91% | 91% |

The Gemma block has 9% fewer MACs than the Llama block but costs the same in
prefill. Its FFN GEMMs cost 6.6 pJ per MAC against 5.6 to 5.8 in Llama: the hidden
size 3584 is 28 tiles of 128, and the two FFN kernels take 1.7 times more
cycles than Llama's for 0.9 times the MACs, which the simulator's tiling of
this shape explains. DRAM takes a larger share because the FFN runs longer
and the wider heads move more key-value data. In decode both blocks are
matrix-vector products and cost about 190 pJ per MAC.

## The GELU kernel

`F.gelu(approximate="tanh")` crashes PyTorchSim's functional simulator
(Spike) with functional mode on. Kernel 10 ran with a copy of the config
that has `pytorchsim_functional_mode: 0`. The timing simulation and the
energy do not depend on this flag; only the check of the result against the
CPU is lost. `how_the_data_was_made/RUN_MANIFEST.md` records it. The run
root's `config.yml` is the functional-ON config of the other nine kernels.

## Files

```
prefill/, decode/           one run root each: config.yml, togsim_results/, outputs/,
                            booksim2_config/, kernels.yaml, run, out/, how_the_data_was_made/
```

The hardware model is in `../` (the design folder). The `run` scripts pass
it with `--compound-components ../../compound_components.yaml` and the two
other definition flags. `1_q_proj` and `2_kv_proj` have the same shape and
share one hash; `kernels.yaml` names them by log file.

## Messages you'll see

- `WARNING (NW-6201)` ×6: the softmax, RMSNorm, and GELU kernels have no
  `linalg.matmul`.
- `WARNING (NW-6208)` ×3: the SFU is charged at fp32 in the kernels that use
  the exponent or the tanh (softmax, GELU).
- `INFO (NW-6222)` ×7: the useful MACs and the array occupancy of each GEMM
  kernel; all are 94% or more.
- `INFO (NW-6001)`: the six non-MAC kernels use the f32 datapath of the first
  GEMM kernel.
- `NW-8212` ×3, `NW-6607`, `NW-8111`, as in the design folder.

## How the sample data was made

Same image and config as the design folder, run on 2026-10-10 and 11. The
script in `how_the_data_was_made/` compiles each kernel of the table as its
own function with random float32 tensors of the given shapes, and raises the
compiler's lock wait at run time (`LOCK_TIMEOUT = 14400`), which changes
nothing in the simulation. Prefill took 7 h 43 min of wall time
(`6_ffn_up_gate` 3.5 h, `7_ffn_down` 3.1 h); decode took 99 min. Kernels 1
to 9 match the CPU reference. See `docs/PYTORCHSIM_DOCKER.md` for the
procedure.
