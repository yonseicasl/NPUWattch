# Workload — matmul_2048_2core: one 2048³ matmul on two cores

The matmul of `../matmul_2048_1core/` on PyTorchSim's 2-core TPUv3-like
config: two cores with two 128×128 arrays each, 32 HBM2 channels, and a
32×32 BookSim `fly` NoC.

```bash
./run
```

## Result

| | `../matmul_2048_1core/` | 2 cores (this folder) |
| --- | --- | --- |
| Cycles | 313 749 | 169 707 |
| Energy at 7nm | 47.9 mJ | 47.6 mJ |
| Area | 53.2 mm² | 106.4 mm² |
| Average power | 143 W | 264 W |

Each core does half of the GEMM tiles. The log shows the same COMP count on
`Core [0]` and `Core [1]`, and each array is active for 131 072 cycles, half
of the 1-core value. NPUWattch divides the chip totals between the cores
with the per-core counters of the log, and prints one WARNING for each
division that is not exact.

## What is new in the tree

`--tree` shows two cores, each with two arrays, a VMEM, and 128 VPU lanes,
a 64-port NoC crossbar, and 32 HBM channels. The crossbar is larger than
the characterized range of the crossbar model (2 to 32 ports), so NPUWattch
extrapolates and says so (`NW-8111`).

## Files

```
config.yml                  the PyTorchSim run configuration (2 cores, 32 HBM channels, fly_c32_m32)
togsim_results/             one TOGSim log
outputs/<hash>/             meta.txt, m5out/stats.txt, c<hash>.mlir
booksim2_config/            the NoC file the run used
kernels.yaml                kernel name -> hash -> log file
how_the_data_was_made/      the PyTorch script and the run manifest
run                         the command; the hardware model comes from ../
out/                        report.html + report.json (included; ./run overwrites them)
```

## Messages you'll see

The five WARNING lines of the parent folder, and these for the second core:

- `NW-6602`, `NW-6603`: the DRAM fill and drain are divided between the
  cores by their MOVIN and MOVOUT instruction counts.
- `NW-6604` ×2: the input-push and result-pop counts are divided by the
  systolic active cycles of each core.
- `NW-8111` ×3 more: `core1.vrf` width 256, and the 64-port crossbar inputs
  and outputs.

## How the sample data was made

Same image as the parent folder, run on 2026-10-10 with the image's
`systolic_ws_128x128_c2_booksim_tpuv3.yml`. The script is the one of
`../matmul_2048_1core/`. The result matches the CPU reference. See
`docs/PYTORCHSIM_DOCKER.md` for the procedure.
