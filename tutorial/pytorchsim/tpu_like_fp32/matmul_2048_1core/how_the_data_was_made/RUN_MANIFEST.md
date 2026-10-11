# RUN_MANIFEST — matmul_2048_1core

- Date: 2026-10-10
- Image: `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
  digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5`
  (PyTorchSim HEAD `33ee1c8`, torch 2.8.0)
- Run config: `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied verbatim to `config.yml`, plus the appended line
  `core_spad_size_kb: 16384`)
- Script: `run_matmul_2048_1core.py` (in this folder). Launched with
  `_data/probe/run_in_container.sh matmul_2048_1core_raw /workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml run_matmul_2048_1core.py`
  (podman, `--security-opt label=disable`; one compiled call per kernel, no
  `TOGSimulator` context; one TOGSim log per kernel).
- Raw dump: `_data/matmul_2048_1core_raw/` (collected with `_data/probe/collect.py`).
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
| 01_mm2048 | `myoxyuozhim` | `000_01_mm2048__20261010_081650_4b04b6ac.log` | 313749 | c0: 5124 (5120/4) | 166.9 | 1477.6 |

## Notes and deviations

- 313,749 cycles (ISPASS tutorial: ~300k). Arrays 83.6 % utilized
  (262,144 active cycles each = 2048^3 / (2 x 128^2), i.e. ideal).
- Kernel call wall time 1477.6 s (process 24 min 44 s); final TOGSim run 166.9 s.
- No deviation from BRIEF A3.
