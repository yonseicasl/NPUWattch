# RUN_MANIFEST — deepseek_v2_lite_decode

DeepSeek-V2-Lite, one MoE decoder block (not the dense first layer), decode (T=1, KV length 512).
BRIEF section C2. All kernels are float32.

## Environment

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` |
| PyTorchSim | `/workspace/PyTorchSim` in the image (git `33ee1c8`), torch 2.8.0 |
| config | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied to `config.yml`, plus `core_spad_size_kb: 16384`) |
| modes | timing mode 1, functional mode 1, autotune on (config defaults), `icnt_type: booksim2` |
| launcher | `_data/probe/run_in_container.sh deepseek_v2_lite_decode_raw <config> run_deepseek_v2_lite_decode.py` (rootless podman, `--security-opt label=disable`) |
| script | `run_deepseek_v2_lite_decode.py` (in this folder) |
| process wall time | 37m2.481s |
| raw dump | `../_data/deepseek_v2_lite_decode_raw/` (collected with `_data/probe/collect.py`) |

Each kernel is its own `torch.compile(dynamic=False)` call on fresh tensors
(one TOGSim log per kernel; no `TOGSimulator(...)` context). Log files carry
a 3-digit run-order prefix. Every log was checked: line 1 is the TOGSim
command line, a `PyTorchSim config:` block follows, and the tail has
`Total execution cycles:`. Each log names exactly one `outputs/<hash>/`.
Functional outputs were compared with the CPU result (`allclose`, rtol/atol
1e-2); all passed.

## Kernels (run order)

Wall time is the wall time of the whole `run_kernel` call (compile +
autotune + Spike + final TOGSim). For an op that lowers to several kernels
(softmax 3, RMSNorm 2) all parts show the wall time of the whole op.

| # | kernel | hash | log | total execution cycles | wall (s) |
| --- | --- | --- | --- | --- | --- |
| 0 | 1_q_proj | `mouppepddmz` | `000_1_q_proj__20261010_075735_df96a58c.log` | 76946 | 192.8 |
| 1 | 2_kv_a_proj | `ihd5idr4osw` | `001_2_kv_a_proj__20261010_075847_234726fb.log` | 16736 | 38.9 |
| 2 | 3_kv_b_proj | `rp7pyxcfn7y` | `002_3_kv_b_proj__20261010_075936_4596c726.log` | 26466 | 56.1 |
| 3 | 4_attn_qk | `p7zky3c5322` | `003_4_attn_qk__20261010_080011_4d6c505a.log` | 27305 | 31.4 |
| 4 | 5_attn_av | `joi5sug2p3f` | `004_5_attn_av__20261010_080031_98b7fd11.log` | 15057 | 15.3 |
| 5 | 6_o_proj | `x4gbocnvdq6` | `005_6_o_proj__20261010_080223_a566e319.log` | 51924 | 133.2 |
| 6 | 7_router | `ovmjmkmnzu5` | `006_7_router__20261010_080254_bf9c8c6d.log` | 2371 | 7.0 |
| 7 | 8_experts_up_gate | `yd7br2k3a74` | `007_8_experts_up_gate__20261010_081303_d660c8ab.log` | 420210 | 858.0 |
| 8 | 9_experts_down | `irn7r2gdy7q` | `008_9_experts_down__20261010_082058_3b56898c.log` | 211418 | 316.5 |
| 9 | 10_shared_up_gate | `vrgyqc523fp` | `009_10_shared_up_gate__20261010_082658_42dee1ef.log` | 140446 | 341.8 |
| 10 | 11_shared_down | `sf5tgfpnj7t` | `010_11_shared_down__20261010_083037_259c97e9.log` | 101989 | 182.3 |
| 11 | 12_softmax_p0 | `xef3d6mdsn3` | `011_12_softmax_p0__20261010_083133_e367b7a4.log` | 895 | 19.2 |
| 12 | 12_softmax_p1 | `iwflep7gzuf` | `012_12_softmax_p1__20261010_083133_41f47cef.log` | 1296 | 19.2 |
| 13 | 12_softmax_p2 | `6mtuccoae3f` | `013_12_softmax_p2__20261010_083133_99ab6e54.log` | 389 | 19.2 |
| 14 | 13_rmsnorm_p0 | `eiz6zzjaxru` | `014_13_rmsnorm_p0__20261010_083151_5d4678c1.log` | 1269 | 18.4 |
| 15 | 13_rmsnorm_p1 | `yuurxh453b3` | `015_13_rmsnorm_p1__20261010_083152_28698e65.log` | 294 | 18.4 |
| 16 | 14_silu_mul | `sjhoun2vri5` | `016_14_silu_mul__20261010_083156_70f4d1db.log` | 271 | 4.4 |

Sum of kernel cycles: 1095282.

## Shapes (decode, T=1, KV length 512)

| kernel | op | shape |
| --- | --- | --- |
| 1_q_proj | matmul | 1×2048 @ 2048×3072 |
| 2_kv_a_proj | matmul | 1×2048 @ 2048×576 |
| 3_kv_b_proj | matmul | 1×512 @ 512×4096 |
| 4_attn_qk | bmm | 16 × (1×192 @ 192×512) |
| 5_attn_av | bmm | 16 × (1×512 @ 512×128) |
| 6_o_proj | matmul | 1×2048 @ 2048×2048 |
| 7_router | matmul | 1×2048 @ 2048×64 |
| 8_experts_up_gate | bmm | 6 × (1×2048 @ 2048×2816) |
| 9_experts_down | bmm | 6 × (1×1408 @ 1408×2048) |
| 10_shared_up_gate | matmul | 1×2048 @ 2048×5632 |
| 11_shared_down | matmul | 1×2816 @ 2816×2048 |
| 12_softmax | softmax dim=-1 | 16×1×512 (3 kernels: `_p0` amax, `_p1` exp/sum, `_p2` div) |
| 13_rmsnorm | x·rsqrt(mean(x²)+1e-6)·w | 1×2048 (2 kernels: `_p0`, `_p1`) |
| 14_silu_mul | silu(g)·u | 1×1408 |

## Assumptions

- Routing: top-6 of 64 routed experts, each active expert sees the one
  decode token, so the expert GEMMs are one bmm of batch 6 with M=1. The
  routing decision (top-k, gather/scatter, weighted combine) is NOT
  simulated; only the router GEMM (`7_router`) is.
- MLA is run without weight absorption: `kv_b_proj` expands the new token's
  latent (1×512); attention uses K/V of length 512 with q/k head dim 192
  (128 nope + 64 rope) and v head dim 128. The KV cache expansion for the
  other 511 positions is not simulated.
- Element-wise RoPE, residual adds and the expert weighted sum are not
  simulated.

## Deviations

- None from the BRIEF table. `14_silu_mul` uses the T-row shape (1×1408),
  consistent with the prefill root (512×1408); see the prefill manifest.
- Autotune candidate TOGSim runs for the decode GEMVs (M=1) hit the
  autotune timeout several times (`Simulator subprocess exceeded timeout`);
  this is normal autotune behaviour (the candidate is dropped) and the
  final run of the chosen tiling completed. Decode GEMVs are slow to
  simulate (for example 858 s for `8_experts_up_gate`) because they are
  weight-streaming bound.


## NPUWattch check

The three definition yamls (`compound_components.yaml`, `projection.yaml`,
`user_components.yaml`) were copied from
`NPUWattch/tutorial/pytorchsim/tpu_like_fp32/`. Command (from
`/home/KNUEEhdd1/ys_knu/kmk/NPUWattch`, npuwattch env on PATH):
`./run.sh <this root> --node 7nm --report <this root>/out/`. Exit code 0;
console in `out/console.txt`, report in `out/report.{html,json}`.
Result: 17 windows (window names from kernels.yaml, NW-6014), total
1.484e+10 pJ (dyn 1.453e+10 + leak 3.09e+08), exec 1.165 ms, 0 ERROR,
15 WARNING (NW-6201 x6, NW-6208 x3, NW-8212 x3, NW-6606 x1, NW-6607 x1,
NW-8111 x1). DRAM is 86 % of the energy (decode is weight-streaming bound).
