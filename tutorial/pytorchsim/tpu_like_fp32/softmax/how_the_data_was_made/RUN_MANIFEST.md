# RUN_MANIFEST — softmax

- Date: 2026-10-10
- Image: `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
  digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5`
  (PyTorchSim HEAD `33ee1c8`, torch 2.8.0)
- Run config: `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied verbatim to `config.yml`, plus the appended line
  `core_spad_size_kb: 16384`)
- Script: `run_softmax.py` (in this folder). Launched with
  `_data/probe/run_in_container.sh softmax_raw /workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml run_softmax.py`
  (podman, `--security-opt label=disable`; one compiled call per kernel, no
  `TOGSimulator` context; one TOGSim log per kernel).
- Raw dump: `_data/softmax_raw/` (collected with `_data/probe/collect.py`).
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
| 01_softmax_p0 | `ki6yhkrcpgm` | `000_01_softmax_p0__20261010_080835_9fcf2a2e.log` | 14102 | c0: 6 (0/6) | 4.7 | 128.0 |
| 01_softmax_p1 | `oqy5oqtice5` | `001_01_softmax_p1__20261010_080841_726153ec.log` | 15224 | c0: 6 (0/6) | 5.0 | 128.0 |
| 01_softmax_p2 | `snq4z7o7dnb` | `002_01_softmax_p2__20261010_080908_31b2887b.log` | 26837 | c0: 2 (0/2) | 8.3 | 128.0 |
| 02_exp2 | `7ocdaitk5yp` | `003_02_exp2__20261010_080939_791c3352.log` | 52301 | c0: 128 (0/128) | 5.6 | 28.4 |

## Notes and deviations

- `torch.softmax(x, dim=-1)` on 1024x1024 lowers to 3 kernels
  (`01_softmax_p0` amax, `_p1` sub/exp/sum, `_p2` div/exp/sub), all `GEMM: 0`.
  gem5 has `CustomVexp` in `_p1` and `_p2`.
- `torch.exp2` on 1024x1024 lowers without source edits (1 kernel, `02_exp2`),
  as `CustomVexp` (no `CustomVexp2`), `GEMM: 0`.
- All outputs allclose with the CPU reference.
- This root has no MAC kernel: NPUWattch prints
  `WARNING (NW-6002): The run has no MAC kernel, so non-MAC kernels use an fp32 datapath.`
  (instead of the INFO NW-6001 borrow line seen in mixed roots).
- Process wall time 2 min 43 s. No deviation from BRIEF A4.
- Observation (NPUWattch, not changed): the SFU dynamic energy of `02_exp2`
  (3.179e4 pJ) is 16x lower than that of `01_softmax_p2` (5.086e5 pJ), although
  both kernels apply exp to 1024x1024 elements. The gem5 sampled-tile
  `CustomVexp` counts are 16 (+16) for exp2 and 256 (+256) for softmax_p2.
