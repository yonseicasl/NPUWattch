# Workload — matmul_2048_1core: one 2048³ matmul on one core

One 2048×2048×2048 float32 `torch.matmul` on the 1-core TPUv3-like config.
The partner folder `../matmul_2048_2core/` runs the same matmul on two cores.
Compare the two.

```bash
./run
```

## Result

| | 1 core (this folder) | 2 cores (`../matmul_2048_2core/`) |
| --- | --- | --- |
| Cycles | 313 749 | 169 707 |
| Energy at 7nm | 49.1 mJ | 48.8 mJ |
| DRAM share | 8.0% | 7.5% |
| Area | 88.8 mm² | 177.5 mm² |
| Average power | 147 W | 270 W |
| Power density | 1.66 W/mm² | 1.52 W/mm² |
| pJ/FLOP | 2.86 | 2.84 |

The second core cuts the time by 1.85× (the ISPASS PyTorchSim tutorial shows
the same speed-up). The energy stays the same: the work is the same, and the
systolic arrays take 89% of it in both runs. The second core doubles the
area and the power. The power density stays the same, so for a TDP or a
cooling budget the second core costs as much as the first one.

The 2-core run uses a different PyTorchSim config
(`systolic_ws_128x128_c2_booksim_tpuv3.yml`: 2 cores, 32 HBM channels, a
32×32 NoC). NPUWattch reads the machine from the log header, so both runs
use the same hardware model in `../compound_components.yaml`.

## Files

```
config.yml                  the PyTorchSim run configuration (1 core, 16 HBM channels, fly_c16_m16)
togsim_results/             one TOGSim log
outputs/<hash>/             meta.txt, m5out/stats.txt, c<hash>.mlir
booksim2_config/            the NoC file the run used
kernels.yaml                kernel name -> hash -> log file
how_the_data_was_made/      the PyTorch script and the run manifest
run                         the command; the hardware model comes from ../
out/                        report.html + report.json (included; ./run overwrites them)
```

## Messages you'll see

The same five WARNING lines as the parent folder, plus `INFO (NW-6014)` for
the window name.

## How the sample data was made

Same image and config as the parent folder, run on 2026-10-10. The script in
`how_the_data_was_made/` compiles one `torch.matmul` of two 2048×2048 float32
tensors. The result matches the CPU reference. See
`docs/PYTORCHSIM_DOCKER.md` for the procedure.
