# RUN_MANIFEST — deepseek_v2_lite_prefill

DeepSeek-V2-Lite, one MoE decoder block (not the dense first layer), prefill (T=512).
BRIEF section C2. All kernels are float32.

## Environment

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` |
| PyTorchSim | `/workspace/PyTorchSim` in the image (git `33ee1c8`), torch 2.8.0 |
| config | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied to `config.yml`, plus `core_spad_size_kb: 16384`) |
| modes | timing mode 1, functional mode 1, autotune on (config defaults), `icnt_type: booksim2` |
| launcher | `_data/probe/run_in_container.sh deepseek_v2_lite_prefill_raw <config> run_deepseek_v2_lite_prefill.py` (rootless podman, `--security-opt label=disable`) |
| script | `run_deepseek_v2_lite_prefill.py` (in this folder) |
| process wall time | 282m23.547s |
| raw dump | `../_data/deepseek_v2_lite_prefill_raw/` (collected with `_data/probe/collect.py`) |

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
| 0 | 1_q_proj | `g4wbm3aqxno` | `000_1_q_proj__20261010_084636_25b43709.log` | 139312 | 912.1 |
| 1 | 2_kv_a_proj | `4juhudcu6xg` | `001_2_kv_a_proj__20261010_084900_a7d54ec4.log` | 54389 | 113.6 |
| 2 | 3_kv_b_proj | `ozskmqoc53u` | `002_3_kv_b_proj__20261010_085718_cc7020e7.log` | 61383 | 508.4 |
| 3 | 4_attn_qk | `mexm4j36gm3` | `003_4_attn_qk__20261010_085939_dca30417.log` | 100308 | 150.1 |
| 4 | 5_attn_av | `gn5sehm27w7` | `004_5_attn_av__20261010_090130_733de3af.log` | 76224 | 100.3 |
| 5 | 6_o_proj | `uamihvutfaj` | `005_6_o_proj__20261010_090714_f7c0698c.log` | 101607 | 352.5 |
| 6 | 7_router | `knksp34kkyf` | `006_7_router__20261010_090808_06e71e88.log` | 16117 | 22.8 |
| 7 | 8_experts_up_gate | `lb3gjkmiu5u` | `007_8_experts_up_gate__20261010_104810_48c2b583.log` | 4625367 | 8697.8 |
| 8 | 9_experts_down | `tm4zpclg4np` | `008_9_experts_down__20261010_121252_def8470d.log` | 3164956 | 3325.9 |
| 9 | 10_shared_up_gate | `3joqlgrg3jp` | `009_10_shared_up_gate__20261010_125723_3436d7a8.log` | 226925 | 1821.1 |
| 10 | 11_shared_down | `s5jhtwwawn7` | `010_11_shared_down__20261010_130524_3cf83b53.log` | 246805 | 479.0 |
| 11 | 12_softmax_p0 | `lkqg5ic62vw` | `011_12_softmax_p0__20261010_131116_ff996b30.log` | 51849 | 335.9 |
| 12 | 12_softmax_p1 | `ipbxgx4w6yq` | `012_12_softmax_p1__20261010_131133_78297e65.log` | 52064 | 335.9 |
| 13 | 12_softmax_p2 | `of3ho7cemfo` | `013_12_softmax_p2__20261010_131205_27c553e9.log` | 105741 | 335.9 |
| 14 | 13_rmsnorm_p0 | `chblzwae5qv` | `014_13_rmsnorm_p0__20261010_131343_ef183179.log` | 15040 | 85.8 |
| 15 | 13_rmsnorm_p1 | `itbaxabxxkb` | `015_13_rmsnorm_p1__20261010_131353_3d8ceb2d.log` | 37521 | 85.8 |
| 16 | 14_silu_mul | `i5oxd5f7hhn` | `016_14_silu_mul__20261010_131425_048e40b7.log` | 42656 | 26.3 |

Sum of kernel cycles: 9118264.

## Shapes (prefill, T=512)

| kernel | op | shape |
| --- | --- | --- |
| 1_q_proj | matmul | 512×2048 @ 2048×3072 |
| 2_kv_a_proj | matmul | 512×2048 @ 2048×576 |
| 3_kv_b_proj | matmul | 512×512 @ 512×4096 |
| 4_attn_qk | bmm | 16 × (512×192 @ 192×512) |
| 5_attn_av | bmm | 16 × (512×512 @ 512×128) |
| 6_o_proj | matmul | 512×2048 @ 2048×2048 |
| 7_router | matmul | 512×2048 @ 2048×64 |
| 8_experts_up_gate | bmm | 64 × (48×2048 @ 2048×2816) |
| 9_experts_down | bmm | 64 × (48×1408 @ 1408×2048) |
| 10_shared_up_gate | matmul | 512×2048 @ 2048×5632 |
| 11_shared_down | matmul | 512×2816 @ 2816×2048 |
| 12_softmax | softmax dim=-1 | 16×512×512 (3 kernels: `_p0` amax, `_p1` exp/sum, `_p2` div) |
| 13_rmsnorm | x·rsqrt(mean(x²)+1e-6)·w | 512×2048 (2 kernels: `_p0`, `_p1`) |
| 14_silu_mul | silu(g)·u | 512×1408 |

## Assumptions

- **Uniform routing.** Routing is data dependent. For this energy run every
  one of the 64 routed experts gets the same load: 512 tokens × top-6 / 64
  experts = 48 tokens per expert. The routed-expert GEMMs are therefore one
  bmm of batch 64 with M=48 each (`8_experts_up_gate`, `9_experts_down`).
  The routing decision itself (top-k, token gather/scatter, weighted
  combine) is NOT simulated; only the router GEMM (`7_router`) is.
- MLA is run without weight absorption (q head dim 192 = 128 nope + 64 rope,
  v head dim 128, no q LoRA in Lite). RoPE, residual adds and the causal
  mask are not simulated (`4_attn_qk` is the full 512×512 score matrix).

## Deviations

- `14_silu_mul`: the BRIEF row reads "512×1408 (one expert's 48 tokens:
  48×1408)". This root runs the 512×1408 shape (the main shape in the
  table; same rule as the decode root, T×1408). The silu·mul work of the
  whole routed MoE is 64 × 48×1408 = 6× this window, and of the shared
  experts 512×2816 = 2× this window; neither is a separate window here.
- The script has a fallback for the expert bmm kernels (retry with a smaller
  batch of the same per-expert shape if batch 64 fails). It was not needed:
  both expert kernels ran at the full batch 64 (`[expert-batch] ...
  batch=64 scale_factor=1` in `stdout.log`). No scale factor applies.
- The image's frontend `LOCK_TIMEOUT = 600` s (compile lock wait,
  `PyTorchSimFrontend/extension_codecache.py`) was NOT changed; no kernel
  hit the lock timeout.
- Autotune candidate TOGSim runs that exceed the first candidate's wall time
  + 15 s are terminated by the frontend (`Simulator subprocess exceeded
  timeout` in `stdout.log`). This is normal autotune behaviour; the final
  run of the chosen tiling completed for every kernel.
- Observation (not a deviation): `11_shared_down` (2.9 GMAC) took more
  cycles (246805) than `10_shared_up_gate` (5.9 GMAC, 226925). The tiling
  was picked by autotune; recorded as measured.
- The two routed-expert kernels dominate: 7.79 M of 9.13 M cycles. With
  M=48 per expert the 128×128 arrays are poorly filled and the 1.48 GB
  (up/gate) + 0.74 GB (down) of expert weights stream from HBM once.

## NPUWattch check

The three definition yamls (`compound_components.yaml`, `projection.yaml`,
`user_components.yaml`) were copied from
`NPUWattch/tutorial/pytorchsim/tpu_like_fp32/`. Command (from
`/home/KNUEEhdd1/ys_knu/kmk/NPUWattch`, npuwattch env on PATH):
`./run.sh <this root> --node 7nm --report <this root>/out/`. Exit code 0;
console in `out/console.txt`, report in `out/report.{html,json}`.
Result: 17 windows (window names from kernels.yaml, NW-6014), total
3.502e+11 pJ (dyn 3.477e+11 + leak 2.573e+09), exec 9.70 ms, 0 ERROR,
14 WARNING (NW-6201 x6, NW-6208 x3, NW-8212 x3, NW-6607 x1, NW-8111 x1).
The two routed-expert windows are 68 % of the block energy.

