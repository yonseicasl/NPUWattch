# RUN_MANIFEST — matmul_train

- Date: 2026-10-10
- Image: `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
  digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5`
  (PyTorchSim HEAD `33ee1c8`, torch 2.8.0)
- Run config: `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (copied verbatim to `config.yml`, plus the appended line
  `core_spad_size_kb: 16384`)
- Script: `run_matmul_train.py` (in this folder). Launched with
  `_data/probe/run_in_container.sh matmul_train_raw /workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml run_matmul_train.py`
  (podman, `--security-opt label=disable`; one compiled call per kernel, no
  `TOGSimulator` context; one TOGSim log per kernel).
- Raw dump: `_data/matmul_train_raw/` (collected with `_data/probe/collect.py`).
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
| fwd | `fqywo6ndalo` | `000_fwd__20261010_081119_c30c29e0.log` | 52058 | c0: 577 (576/1) | 16.3 | 95.2 |
| grad_b | `x5ej34kmf2v` | `001_grad_b__20261010_081350_256e4b4c.log` | 52848 | c0: 577 (576/1) | 17.4 | 185.7 |
| grad_a | `2qor5t5rutd` | `002_grad_a__20261010_081425_22b9a7c6.log` | 52061 | c0: 577 (576/1) | 16.2 | 185.7 |

## Notes and deviations

- Autograd on npu works. Forward is one compiled call (`fwd`); `c.sum().backward()`
  runs the compiled backward graph, which gives 2 GEMM logs (Inductor `mm_1`,
  `mm_2`). No fused backward kernel.
- Which backward GEMM is which: the backward wrapper
  (`_data/matmul_train_raw/outputs/.torchinductor/k7/ck7lfai...py`) runs
  `mm_1(permute, tangents_1) -> buf0` and `mm_2(tangents_1, permute_1) -> buf1`
  and returns `(buf1, buf0)` = (grad of a, grad of b). So
  `mm_1` = `a^T @ g` = **grad_b** (`x5ej34kmf2v`, meta.txt: permute, tangents_1)
  and `mm_2` = `g @ b^T` = **grad_a** (`2qor5t5rutd`, meta.txt: tangents_1, permute_1).
  Run order is therefore fwd, grad_b, grad_a. The script first named the logs
  `bwd_mm_1`/`bwd_mm_2`; they were renamed to `grad_b`/`grad_a` in the raw dump
  (log, trace and kernels.yaml) before collection.
- All three results allclose with the CPU reference (fwd, grad_a, grad_b).
- The fwd hash `fqywo6ndalo` is the same as the 07-21 reference 1024^3 run.
- The two backward kernels share one wall time (one backward call): 185.7 s.
- Process wall time 4 min 48 s. No deviation from BRIEF A2.
