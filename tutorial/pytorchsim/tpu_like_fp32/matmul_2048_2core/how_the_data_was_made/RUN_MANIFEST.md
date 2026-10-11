# RUN_MANIFEST — matmul_2048_2core

- Date: 2026-10-10
- Image: `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
  digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5`
  (PyTorchSim HEAD `33ee1c8`, torch 2.8.0)
- Run config: `/workspace/PyTorchSim/configs/systolic_ws_128x128_c2_booksim_tpuv3.yml` (copied verbatim to `config.yml`, plus the appended line
  `core_spad_size_kb: 16384`)
- Script: `run_matmul_2048_2core.py` (in this folder). Launched with
  `_data/probe/run_in_container.sh matmul_2048_2core_raw /workspace/PyTorchSim/configs/systolic_ws_128x128_c2_booksim_tpuv3.yml run_matmul_2048_2core.py`
  (podman, `--security-opt label=disable`; one compiled call per kernel, no
  `TOGSimulator` context; one TOGSim log per kernel).
- Raw dump: `_data/matmul_2048_2core_raw/` (collected with `_data/probe/collect.py`).
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
| 01_mm2048 | `myoxyuozhim` | `000_01_mm2048__20261010_084204_97b1ec07.log` | 169707 | c0: 2562 (2560/2); c1: 2562 (2560/2) | 179.3 | 1499.1 |

## Notes and deviations

- Config: the image's shipped 2-core BookSim TPUv3 config (no hand-made config):
  `num_cores: 2`, `dram_channels: 32`, `booksim_config_path:
  ../configs/booksim2_configs/fly_c32_m32.icnt`, `icnt_injection_ports_per_core: 16`.
- 169,707 cycles (ISPASS tutorial: ~160k; 1-core root: 313,749 -> 1.85x speed-up).
- **Both cores have COMP work**: Core [0] and Core [1] each
  `COMP inst_count: 2562 (GEMM: 2560, Vector: 2)`; each core's two arrays have
  131,072 active cycles (77.2 % utilization) = half of the 1-core run's 262,144.
- DMA per core: 98,304 active cycles, 278 GB/s, 1,572,864 responses each.
- DRAM: `channels 0..31 combined | 557.57 GB/s aggregate, 57.93 % utilization
  (avg. per channel) | 2,621,440 reads, 524,288 writes`; per channel
  ~81,920 reads / 16,384 writes, 17.42 GB/s each. Total reads/writes are
  identical to the 1-core run (16 ch, 301.59 GB/s, 62.66 %).
- BookSim2 (end of log): packet latency avg 1994.62 (min 7, max 4759),
  network latency avg 1806.45, injected/accepted packet rate avg 0.579
  (1-core run: 2251.69 / 1978.8 / 0.627). Packet length 1 flit.
- Same kernel hash as the 1-core run (`myoxyuozhim`): same code/tiling.
- Kernel call wall time 1499.1 s (process 25 min 5 s); final TOGSim run 179.3 s.
- No deviation from BRIEF A3.
