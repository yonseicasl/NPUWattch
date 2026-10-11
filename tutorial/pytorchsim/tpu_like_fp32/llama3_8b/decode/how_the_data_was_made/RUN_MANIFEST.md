# Run manifest: llama3_8b_decode

Workload: BRIEF section B2, Llama-3-8B, one decoder block, decode pass
(T = 1 token, KV length 512). fp32. hidden 4096, 32 q heads, 8 kv heads,
head_dim 128, FFN 14336.

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` (id `d7881046072c`) |
| PyTorchSim | git `33ee1c8` in the image, torch 2.8.0, Python 3.11 |
| config | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (shipped, unchanged; copy in `config.yml` + `core_spad_size_kb: 16384`) |
| modes | timing 1, functional 1, autotune on (as shipped), `icnt_type: booksim2` |
| script | `run_llama3_8b_decode.py` (this folder) |
| launcher | `_data/probe/run_in_container.sh llama3_8b_decode_raw <config> run_llama3_8b_decode.py` |
| raw dump | `../_data/llama3_8b_decode_raw/` |
| date | 2026-10-10, container 08:00-09:25 UTC, process wall 85 min |

One `torch.compile(dynamic=False)` call per kernel, no `TOGSimulator(...)`
context, so every log names exactly one `outputs/<hash>/`. Logs carry a
run-order prefix (`NNN_<kernel>__<orig>.log`). All outputs matched the CPU
reference (`allclose=True`).

## Per-kernel table

| # | kernel | op / shape | hash | log | total exec cycles | wall (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 1_q_proj | matmul 1x4096 @ 4096x4096 | qf2u6pwfefi | 000_1_q_proj__20261010_080133_591ef552.log | 203356 | 523.5 |
| 1 | 2_kv_proj | matmul 1x4096 @ 4096x2048 | zoc2mqr5ybk | 001_2_kv_proj__20261010_080650_e5528433.log | 102319 | 259.3 |
| 2 | 3_attn_qk | bmm 32 x (1x128 @ 128x512) | oa52pdopd2q | 002_3_attn_qk__20261010_080811_2d1658fa.log | 29304 | 29.1 |
| 3 | 4_attn_av | bmm 32 x (1x512 @ 512x128) | qe4zxjwzzag | 003_4_attn_av__20261010_080837_125c4eff.log | 30034 | 26.7 |
| 4 | 5_o_proj | matmul 1x4096 @ 4096x4096 | qf2u6pwfefi | 004_5_o_proj__20261010_080950_0c679931.log | 203356 | 186.4 |
| - | 6_ffn_up_gate | matmul 1x4096 @ 4096x28672 | **FAILED** (no log) | - | - | ~1850 (until failure) |
| 5 | 7_ffn_down | matmul 1x14336 @ 14336x4096 | 3zn5oxuk6p7 | 005_7_ffn_down__20261010_091130_1d47dac3.log | 1771963 | 2196.6 |
| 6 | 8_softmax_p0 | softmax 32x1x512 (amax) | wdpiae4vm5p | 006_8_softmax_p0__20261010_091921_b7caa3cb.log | 1005 | 15.5 (3 parts) |
| 7 | 8_softmax_p1 | softmax (sub/exp/sum) | 3zi7ioqwvol | 007_8_softmax_p1__20261010_091922_74f2f936.log | 1440 | ″ |
| 8 | 8_softmax_p2 | softmax (div/exp/sub) | jjmhjeb5mau | 008_8_softmax_p2__20261010_091922_5805b44a.log | 647 | ″ |
| 9 | 9_rmsnorm_p0 | rmsnorm 1x4096 (mean of x^2) | 2kx5gfubcac | 009_9_rmsnorm_p0__20261010_091944_824d8886.log | 2334 | 23.1 (2 parts) |
| 10 | 9_rmsnorm_p1 | rmsnorm (rsqrt, mul) | xgss3yhbtnx | 010_9_rmsnorm_p1__20261010_091945_53247ea7.log | 465 | ″ |
| 11 | 10_silu_mul | silu(g)*u 1x14336 | qq7izvmhwhp | 011_10_silu_mul__20261010_091948_e9bc15ac.log | 1188 | 3.0 |

`1_q_proj` and `5_o_proj` have the same shape, so they share the hash
`qf2u6pwfefi` (second call reused the compiled kernel; TOGSim ran again).

## Deviations

1. **`6_ffn_up_gate` is missing.** Its autotune failed with
   `InductorError: Timeout: The file lock '/data/llama3_8b_decode_raw/outputs/sosdyy6oyxz/.compile.lock' could not be acquired.`
   Cause: the frontend constant `LOCK_TIMEOUT = 600` s
   (`PyTorchSimFrontend/extension_codecache.py`, line 17, in the image). The
   parallel autotune candidates got a timeout of baseline wall + 15 s = 911.8 s;
   a candidate that waits for the `.compile.lock` of the same hash gives up after
   600 s, and `filelock.Timeout` is not caught by the autotune loop. The
   script recorded the error and continued. A rerun of this one kernel with a
   larger `LOCK_TIMEOUT` (runtime only) was not run: the session did not
   permit it. So this root has 12 windows, not 13; the FFN
   up/gate projection energy is not in the total.
2. `kernels.yaml` has a row `{name: 6_ffn_up_gate, hash: FAILED, log: -}`
   for traceability. NPUWattch read the file without complaint (NW-6014).
3. Decode kernels were not "minutes": the GEMV projections take 3-37 min each
   because autotune runs full TOGSim simulations of each tile candidate on a
   shared, loaded host (load average ~30-38).
4. The prefill run (`llama3_8b_prefill`) was started at 08:57 UTC, while
   this decode process was still in `7_ffn_down` (one decode + one prefill
   process at the same time).

## NPUWattch

`out/console.txt`, `out/report.{html,json}`; run with
`./run.sh <this root> --node 7nm --report <this root>/out/` and the three
tutorial yamls from `NPUWattch/tutorial/pytorchsim/tpu_like_fp32/`.
Total 2.294e+10 pJ (dyn 2.228e+10 + leak 6.623e+08), 2.497 ms;
dram_chan 2.025e+10 pJ dynamic = 88 % of total. 0 ERROR, 14 WARNING.

## Rerun of 6_ffn_up_gate (2026-10-11)

This rerun fills in deviation 1. The root now has 13 windows.

| item | value |
| --- | --- |
| date | 2026-10-10 15:14-16:11 UTC (2026-10-11 00:14-01:11 KST), process wall 56 min 23 s |
| script | `run_llama3_8b_decode_ffn.py` (this folder): the same `run_kernel` logic and shapes as `run_llama3_8b_decode.py`, kernel 6 only |
| runtime change | `PyTorchSimFrontend.extension_codecache.LOCK_TIMEOUT = 14400` (was 600 s), set by the script at run time, as in `run_llama3_8b_prefill.py`. The image is not edited. The simulation is not changed. |
| launcher | `_data/probe/run_in_container.sh llama3_8b_decode_ffn_raw <config> run_llama3_8b_decode_ffn.py` |
| config | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml`, the same as the first run (identical copy) |
| raw dump | `../_data/llama3_8b_decode_ffn_raw/` |
| kernel | 6_ffn_up_gate, matmul 1x4096 @ 4096x28672 (fp32, T = 1) |
| hash | `l3g7wgugjfc` (the failed run's lock was on candidate `sosdyy6oyxz`) |
| log | `004a_6_ffn_up_gate__20261010_155809_d0129f13.log` (+ `.trace`) |
| total exec cycles | 1420007 |
| wall | 3377.1 s (autotune, then the final TOGSim run) |
| check | `allclose=True` |

The prefix `004a` sorts after `004_5_o_proj` and before `005_7_ffn_down`, so
the window order is the run order of the original script. The other logs keep
their names. `kernels.yaml`: the `FAILED` row is replaced by the real row at
the same position. `outputs/l3g7wgugjfc/` has `meta.txt`, `m5out/stats.txt`
and the `c*.mlir` file only.

Note: 6_ffn_up_gate (N = 28672) has fewer cycles than 7_ffn_down
(K = 14336, N = 4096, 1771963 cycles). Both are autotuned GEMVs with
different tile choices; the numbers are recorded as they are.

### NPUWattch after the rerun (supersedes the totals above)

13 windows. 0 ERROR, 14 WARNING (the same codes as before: NW-6201 x6,
NW-6208 x3, NW-6607, NW-8111, NW-8212 x3).
6_ffn_up_gate window: 2.126e+10 pJ (dyn 2.085e+10 + leak 4.006e+08).
Total 4.419e+10 pJ (dyn 4.313e+10 + leak 1.063e+09), 4.008 ms,
avg power 1.103e+04 mW. dram_chan 3.895e+10 pJ dynamic = 88 % of total
(activation 30.8 %, transfer 64.4 %, refresh 4.9 %).
GEMM 4.411e+10 pJ (7 windows), non-GEMM 8.807e+07 pJ (6 windows, 0.2 %).
