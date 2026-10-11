# Workload — softmax: kernels with no MAC

`torch.softmax(x, dim=-1)` and `torch.exp2(x)` on a 1024×1024 float32
tensor. No kernel in this run uses the systolic array. The energy goes to
the vector unit, its register file, the SFU, and DRAM.

```bash
./run
```

## Kernels

PyTorchSim compiles the softmax into three kernels. `exp2` is one kernel.

| Window | What it computes | Cycles | Energy at 7nm |
| --- | --- | --- | --- |
| `01_softmax_p0` | row maximum | 14 102 | 246 µJ |
| `01_softmax_p1` | exp(x − max) and the row sum | 15 224 | 293 µJ |
| `01_softmax_p2` | exp(x − max) / sum | 26 837 | 525 µJ |
| `02_exp2` | 2ˣ | 52 301 | 1.00 mJ |

Total: **2.07 mJ**. Every window is `non_mac`. The vector register file
takes 45% of the energy, DRAM 47%, and the vector FPU 3%. The SFU pipes
are a small part: the exponent is one operation per element, while the
register file is read for every operand of every vector instruction.

`exp2` has no `CustomVexp2` instruction in this PyTorchSim build. The
compiler lowers it to `CustomVexp` with a scaled argument, which is why its
gem5 statistics show `CustomVexp` only.

## What this run shows

- A kernel without `linalg.matmul` has no operand data type for the PE, so
  NPUWattch marks it `non_mac` (`NW-6201`).
- In a run with GEMM kernels, the non-MAC kernels borrow the data type of
  the GEMM kernels (`INFO NW-6001`, see `../resnet50/`). This run has none,
  so NPUWattch uses fp32 for the SFU tables and says so (`NW-6002`,
  `NW-6208`). The simulator ran float32, so this is the right choice here.
- The report's **GEMM / non-GEMM split** shows 100% non-GEMM.

## Files

```
config.yml                  the PyTorchSim run configuration (1 core, BookSim fly NoC)
togsim_results/             four TOGSim logs, one per kernel, in run order
outputs/<hash>/             meta.txt, m5out/stats.txt, c<hash>.mlir of each kernel
booksim2_config/            the NoC file the run used
kernels.yaml                kernel name -> hash -> log file
how_the_data_was_made/      the PyTorch script and the run manifest
run                         the command; the hardware model comes from ../
out/                        report.html + report.json (included; ./run overwrites them)
```

## Messages you'll see

- `WARNING (NW-6002): The run has no MAC kernel, so non-MAC kernels use an
  fp32 datapath.`
- `WARNING (NW-6201): <hash>: the kernel has no linalg.matmul, so it has no
  MAC configuration.` One for each of the four kernels.
- `WARNING (NW-6208): <hash>: the kernel has SFU operations and an unknown
  operand dtype, so NPUWattch charges the SFU at fp32.` For the three
  kernels that use the exponent.
- `NW-8212` ×3 and `NW-8111`, as in the parent folder. The register-file
  extrapolation (`NW-8111`, width 256 outside the characterized 8 to 128)
  matters more here than in a matmul, because the register file is the
  largest on-chip consumer of this run.

## How the sample data was made

Same image and config as the parent folder, run on 2026-10-10. The script in
`how_the_data_was_made/` compiles `torch.softmax` and `torch.exp2` as two
separate functions. Both results match the CPU reference. See
`docs/PYTORCHSIM_DOCKER.md` for the procedure.
