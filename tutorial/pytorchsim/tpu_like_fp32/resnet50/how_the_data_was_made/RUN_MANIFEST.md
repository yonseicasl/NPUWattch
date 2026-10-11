# RUN_MANIFEST — resnet50

- Date: 2026-10-10
- Image: `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
  digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5`
  (PyTorchSim HEAD `33ee1c8`, torch 2.8.0)
- Run config: `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied verbatim to `config.yml`, plus the appended line
  `core_spad_size_kb: 16384`)
- Script: `run_resnet50.py` (in this folder). Launched with
  `_data/probe/run_in_container.sh resnet50_raw /workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml run_resnet50.py`
  (podman, `--security-opt label=disable`; one compiled call per kernel, no
  `TOGSimulator` context; one TOGSim log per kernel).
- Raw dump: `_data/resnet50_raw/` (collected with `_data/probe/collect.py`).
- Console: `stdout.log`. Kernel list: `kernels.yaml`. NPUWattch output: `out/`
  (`console.txt`, `report.html`, `report.json`), run with the three
  `tpu_like_fp32` definition yamls copied to this folder:
  `./run.sh <root> --node 7nm --report <root>/out/`.

## Kernels (run order)

COMP = TOGSim `COMP inst_count (GEMM/Vector)` per core. "sim s" = TOGSim
`Wall-clock time for simulation`. "wall s" = wall-clock time of the Python
compiled call (compile + autotune + Spike + TOGSim); when one call produced
several logs, all its logs show the same call time.

| kernel | hash | log | total cycles | COMP | sim s | wall s |
| --- | --- | --- | --- | --- | --- | --- |
| 01_conv1_p0 | `jslakzcgh5c` | `000_01_conv1_p0__20261010_075805_59005799.log` | 4458 | c0: 25 (0/25) | 0.7 | 267.7 |
| 01_conv1_p1 | `j4ha5h5wxsa` | `001_01_conv1_p1__20261010_075805_c6726a0a.log` | 405 | c0: 2 (0/2) | 0.1 | 267.7 |
| 01_conv1_p2 | `agpfubfynsc` | `002_01_conv1_p2__20261010_075910_2fe59677.log` | 315300 | c0: 5838 (5831/7) | 17.4 | 267.7 |
| 02_res2_1x1_p0 | `qgsuptisjyn` | `003_02_res2_1x1_p0__20261010_075949_677b1e23.log` | 5429 | c0: 1 (0/1) | 1.3 | 25.7 |
| 02_res2_1x1_p1 | `drpdulzasqc` | `004_02_res2_1x1_p1__20261010_075951_0fe8e08e.log` | 5913 | c0: 60 (58/2) | 1.4 | 25.7 |
| 03_res2_3x3_p0 | `qgsuptisjyn` | `005_03_res2_3x3_p0__20261010_080026_d59bf093.log` | 5429 | c0: 1 (0/1) | 1.1 | 43.6 |
| 03_res2_3x3_p1 | `tip3uxh2xog` | `006_03_res2_3x3_p1__20261010_080028_6db77cda.log` | 1125 | c0: 4 (0/4) | 0.3 | 43.6 |
| 03_res2_3x3_p2 | `eali2dh4ioy` | `007_03_res2_3x3_p2__20261010_080033_a8cc3c17.log` | 18920 | c0: 524 (522/2) | 3.2 | 43.6 |
| 04_res3_3x3_p0 | `accn7jhjq43` | `008_04_res3_3x3_p0__20261010_080107_e64607d1.log` | 2696 | c0: 1 (0/1) | 0.5 | 35.6 |
| 04_res3_3x3_p1 | `6yhdu4enmge` | `009_04_res3_3x3_p1__20261010_080108_18ba2577.log` | 4279 | c0: 2 (0/2) | 0.8 | 35.6 |
| 04_res3_3x3_p2 | `jaro7yoxxv3` | `010_04_res3_3x3_p2__20261010_080110_bf4c8ed8.log` | 9612 | c0: 262 (261/1) | 1.7 | 35.6 |
| 05_res4_1x1_exp_p0 | `rfuufin5hcc` | `011_05_res4_1x1_exp_p0__20261010_080138_c81bf880.log` | 1444 | c0: 1 (0/1) | 0.2 | 29.7 |
| 05_res4_1x1_exp_p1 | `f5lw5kiwosc` | `012_05_res4_1x1_exp_p1__20261010_080140_7304659b.log` | 9021 | c0: 241 (240/1) | 1.4 | 29.7 |
| 06_res5_3x3_p0 | `f7djzzzst7j` | `013_06_res5_3x3_p0__20261010_080418_c38c2390.log` | 790 | c0: 2 (0/2) | 0.1 | 210.8 |
| 06_res5_3x3_p1 | `k2obfzhchot` | `014_06_res5_3x3_p1__20261010_080425_4c0dd764.log` | 62688 | c0: 16 (0/16) | 25.6 | 210.8 |
| 06_res5_3x3_p2 | `jetdqkoe6sb` | `015_06_res5_3x3_p2__20261010_080455_d4b8feb3.log` | 43981 | c0: 1153 (1152/1) | 17.9 | 210.8 |
| 07_fc | `iiysxgrms23` | `016_07_fc__20261010_080603_5b334655.log` | 26246 | c0: 257 (256/1) | 10.5 | 60.4 |
| 08_relu | `c6uuothmuyo` | `017_08_relu__20261010_080620_7f8de715.log` | 7378 | c0: 25 (0/25) | 0.9 | 7.8 |
| 09_bn | `vkzgpcqnon3` | `018_09_bn__20261010_080643_9ea3af96.log` | 5993 | c0: 2 (0/2) | 1.4 | 23.8 |

## Notes and deviations

- All 7 layers lower directly (no im2col fallback). All outputs allclose.
- **Deviation from the "3 logs per conv2d" expectation:** the 3x3 and 7x7 convs
  give 3 logs (`_p0`, `_p1` vector-only layout/pad, `_p2` GEMM), but the
  **1x1 convs (02_res2_1x1, 05_res4_1x1_exp) give only 2 logs** (`_p0`
  vector-only, `_p1` GEMM): there is no padding kernel when pad = 0.
  Total 19 windows: 7 GEMM windows + 12 vector-only windows.
- `02_res2_1x1_p0` and `03_res2_3x3_p0` have the same hash `qgsuptisjyn`
  (same 1x64x56x56 input layout kernel); they are two windows.
- `06_res5_3x3_p1` (vector-only layout kernel, 16 vector ops) takes 62,688
  cycles, more than its GEMM `_p2` (43,981).
- `01_conv1_p2` (GEMM, 118 MMAC) takes 315,300 cycles with both arrays ~97 %
  "active" (307,432 active cycles). Effective MAC utilization =
  118e6 / (307,432 x 2 x 128^2) = 1.2 % (C_in = 3, so K is tiny for the
  weight-stationary array). NPUWattch charges compute per active cycle x
  lanes^2, so this window is 5.31e10 pJ = 89 % of the root (about 450 pJ/MAC,
  vs about 20 pJ/MAC for 03_res2_3x3_p2). This is what the simulator reports;
  it is recorded, not changed.
- `07_fc` (1x2048x1000) is weight-load bound: 26,246 cycles, 64 array active cycles.
- `09_bn` lowers to one vector kernel (`mul_2_mul_1_add_1_sub`).
- Process wall time 11 min 51 s (01_conv1 call 268 s, 06_res5_3x3 call 211 s).
