# Workload — matmul_train: forward and backward of one 1024³ matmul

The 1024×1024×1024 float32 matmul of the parent folder, trained: `c = a @ b`
followed by `c.sum().backward()`. PyTorchSim compiles the backward pass into
two GEMMs, so the run has three kernels.

```bash
./run
```

## Kernels

| Window | What it computes | Shape | Cycles | Energy at 7nm |
| --- | --- | --- | --- | --- |
| `fwd` | `c = a @ b` | 1024×1024×1024 | 52 058 | 5.98 mJ |
| `grad_b` | `aᵀ @ g` | 1024×1024×1024 | 52 848 | 6.03 mJ |
| `grad_a` | `g @ bᵀ` | 1024×1024×1024 | 52 061 | 6.03 mJ |

Total: **18.0 mJ**, 2.80 pJ/FLOP. The backward pass costs twice the forward
pass, because each gradient is a GEMM of the same size. The three windows
differ by less than 1%. The transposed operands change the DRAM access
pattern a little, not the MAC count.

The window names come from `kernels.yaml`. The hash of `fwd` is the same as
in the parent folder, because it is the same kernel.

## Files

```
config.yml                  the PyTorchSim run configuration (1 core, BookSim fly NoC)
togsim_results/             three TOGSim logs, one per kernel, in run order
outputs/<hash>/             meta.txt, m5out/stats.txt, c<hash>.mlir of each kernel
booksim2_config/            the NoC file the run used
kernels.yaml                kernel name -> hash -> log file
how_the_data_was_made/      the PyTorch script and the run manifest
run                         the command; the hardware model comes from ../
out/                        report.html + report.json (included; ./run overwrites them)
```

## Messages you'll see

The same five WARNING lines as the parent folder (`NW-8212` ×3, `NW-6607`,
`NW-8111`), plus `INFO (NW-6014): The window names come from kernels.yaml.`

## How the sample data was made

Same image and config as the parent folder
(`ghcr.io/psal-postech/torchsim-tutorial:ispass2026`,
`systolic_ws_128x128_c1_booksim_tpuv3.yml`), run on 2026-10-10. The script
in `how_the_data_was_made/` sets `requires_grad` on both operands, compiles
the forward function, and calls `backward()` on the sum. PyTorch autograd
runs the backward graph through the same compiler, which gives the two
backward GEMMs (`mm_1`, `mm_2` in the Inductor wrapper). All three results
match the CPU reference. See `docs/PYTORCHSIM_DOCKER.md` for the procedure.
