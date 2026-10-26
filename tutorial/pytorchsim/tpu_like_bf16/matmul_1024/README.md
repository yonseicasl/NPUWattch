# Workload — matmul_1024: one 1024³ bf16 matmul

One 1024×1024×1024 bfloat16 `torch.matmul` on the bf16 design of `../`. It is
the bf16 twin of `../../tpu_like_fp32/matmul_1024`: the same machine
configuration, the same operator, and a native bf16 PyTorchSim run.

```bash
./run                                   # 7 nm, report in out/
```

## Files

```
config.yml                              the PyTorchSim run configuration (functional mode off, see below)
togsim_results/*.log                    the TOGSim simulation log (the run's results)
togsim_results/*.trace                  the kernel trace TOGSim replayed
outputs/5affeun55ak/meta.txt            operand dtypes and shapes: torch.bfloat16
outputs/5affeun55ak/m5out/stats.txt     gem5 statistics of the sample program (one dump per tile operation)
outputs/5affeun55ak/c<hash>_tog.py      the tile graph: the loop nest of the kernel
outputs/5affeun55ak/c<hash>.mlir        the compiled kernel
booksim2_config/fly_c16_m16.icnt        the NoC topology used
kernels.yaml                            kernel name -> hash -> log file (names the report window)
run                                     the script; the hardware model comes from ../
out/                                    report.html + report.json at 7 nm (included; ./run overwrites them)
how_the_data_was_made/                  the PyTorch script, the two toolchain patches, and RUN_MANIFEST.md
../compound_components.yaml             the hardware model: the PE is fpmul + fpadd + a 32-bit register
../projection.yaml                      PyTorchSim actions -> activity of the compound elements
../user_components.yaml                 cost of custom blocks (one example entry)
```

`5affeun55ak` is PyTorchSim's hash for the compiled bf16 kernel. The layout
is the one of the fp32 workload folders; `../../tpu_like_fp32/matmul_1024/README.md`
explains each input file and each console message.

## What differs from the fp32 run

| | `tpu_like_fp32/matmul_1024` | this run |
| --- | --- | --- |
| `meta.txt` | `torch.float32` operands and output | `torch.bfloat16` operands and output |
| Total execution cycles | 52 022 | 45 195 |
| DRAM requests (32 B each) | 262 144 reads, 131 072 writes (8 MB + 4 MB) | 131 072 reads, 65 536 writes (4 MB + 2 MB) |
| Useful MACs (`NW-6222`) | 1 073 741 824 of 1 073 741 824 active PE cycles | the same |
| PE in the tree | `pe`: `fpmac` e8m23 (follows the kernel dtype) | `pe`: `fpmul` e8m7, `acc`: `fpadd` e8m23, `acc_reg`: 32 b (fixed) |
| `w_reg` | 32 bits | 16 bits (the operand width) |

The kernel's data type still reaches the vector unit: `vfu` follows it (an
e8m7 `fpmac`), as in the fp32 design.

## Result at 7 nm

3.02 mJ for the kernel, 1.41 pJ/FLOP with DRAM included, 48.1 µs, 62.8 W,
72% MAC utilization. The two arrays are 91% of the energy: the fp32 adders
29% each, the bf16 multipliers 16% each, the partial-sum registers 1% each.
DRAM is 8% (236 µJ). The PE costs 2.56 pJ per useful MAC against the 5.05 pJ
of the fp32 `fpmac`. `../README.md` has the full comparison and the published
TPU figures.

## Messages you'll see

The same four warnings as the fp32 run (`NW-8212` twice, `NW-6607`,
`NW-8111`) and the same INFO block. `NW-6222` reads
`5affeun55ak: 1073741824 useful MACs of 1073741824 active PE cycles (100.0%)`:
the 1024³ matmul fills the weight tiles completely in bf16 too.

## How the sample data was made

A real run of 2026-10-26 with the public PyTorchSim Docker image
`ghcr.io/psal-postech/torchsim-tutorial:ispass2026` (PyTorchSim v1.1.0) and
its bundled `systolic_ws_128x128_c1_booksim_tpuv3.yml` config with the
functional mode turned off. The workload is one `torch.matmul` of two
1024×1024 bfloat16 tensors under `torch.compile`. The image's compiler
toolchain cannot build a bf16 kernel as shipped, so three small patches were
applied outside the simulator (LLVM target features, a bf16 vector-add
rewrite in the LLVM IR, and a vector LMUL cap). `how_the_data_was_made/RUN_MANIFEST.md`
lists them with the exact commands, what was checked, and what was not. As
for the fp32 run, only the kernel `.mlir` file of `outputs/<hash>/` was kept.
