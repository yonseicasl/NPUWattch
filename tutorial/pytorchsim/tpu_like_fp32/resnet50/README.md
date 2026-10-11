# Workload — resnet50: seven ResNet-50 layers, batch 1

The seven ResNet-50 layers of the Timeloop examples
(`../../../timeloop/gemmini_like/resnet50/`), run through PyTorchSim as
`F.conv2d` and one `torch.matmul` with batch 1, plus a ReLU and a batch
norm. All kernels are float32.

```bash
./run
```

## Kernels

PyTorchSim compiles a convolution into two or three kernels: one or two
vector kernels that lay out and pad the input (`_p0`, `_p1`), and the GEMM.
A 1×1 convolution with no padding has no padding kernel, so it gives two
kernels. The window names come from `kernels.yaml`.

| Layer | Shape | GEMM window | Cycles | Energy at 7nm | Useful MACs | Array occupancy | pJ per useful MAC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| conv1 | C=3, M=64, 7×7, 112×112, stride 2 | `01_conv1_p2` | 315 300 | 15.5 mJ | 118 M | 1.2% | 132 |
| res2 1×1 | C=64, M=64, 56×56 | `02_res2_1x1_p1` | 5 913 | 187 µJ | 12.8 M | 25% | 14.6 |
| res2 3×3 | C=64, M=64, 3×3, 56×56 | `03_res2_3x3_p2` | 18 920 | 1.24 mJ | 116 M | 25% | 10.7 |
| res3 3×3 | C=128, M=128, 3×3, 28×28 | `04_res3_3x3_p2` | 9 612 | 690 µJ | 116 M | 100% | 6.0 |
| res4 1×1 expand | C=256, M=1024, 14×14 | `05_res4_1x1_exp_p1` | 9 021 | 352 µJ | 51 M | 100% | 6.9 |
| res5 3×3 | C=512, M=512, 3×3, 7×7 | `06_res5_3x3_p2` | 43 981 | 1.18 mJ | 116 M | 88% | 10.2 |
| fc | C=2048, M=1000 | `07_fc` | 26 246 | 344 µJ | 2 M | 98% | 168 |

"Array occupancy" is the useful MACs divided by the active PE cycles of the
layer, as `INFO (NW-6222)` reports it. The twelve vector kernels (`_p0`,
`_p1`, `08_relu`, `09_bn`) add 1.31 mJ, 6.3% of the total. The whole run is
**20.9 mJ** over 531 107 cycles, 533 M useful MACs, 39 pJ per useful MAC.

## Read the conv1 window first

conv1 is 75% of the energy. Its GEMM is active for 315 300 cycles, and both
arrays report 97% active cycles, but the layer has only 118 M useful MACs.
Two 128×128 arrays can do 118 M MACs in 3 600 cycles. The array is busy for
87 times longer, because conv1 has three input channels: the reduction
dimension of its GEMM is 3×7×7 = 147, the compiler's tile uses 8 of the 128
rows of each weight tile (`linalg.matmul` of 112×8 @ 8×64 in the kernel
MLIR), and the simulator runs 5 831 small GEMM tiles.

NPUWattch charges the 118 M useful MACs in the compute mode of the PE and
the other 9.96 G active PE cycles in the idle mode: the PE is clocked and
holds its data, but no new weight or input moves through it. The idle mode
costs about 1.3 pJ per PE cycle at 7nm, against 5.05 pJ for a MAC. So the
window costs 132 pJ per useful MAC, against 6.0 pJ in `04_res3_3x3_p2`, where
the tiles are full. The report's `MAC ops` (533 M) and `pJ/MAC` (39) count
the useful MACs.

The clocked PE cycles are the cost of running a batch-1 CNN on a large
weight-stationary array. The Timeloop runs of the same layers map each layer
onto a 16×16 or 8×8 array with a mapper that keeps the PEs full, so they do
not see this effect.

## The same layers on the Timeloop designs

| | TPU-like (this folder) | Gemmini-like | NVDLA-like |
| --- | --- | --- | --- |
| Operands | fp32 | int8 | int8 |
| Array | 2 × 128×128 | 16×16 | 8×8 |
| Energy, 7 layers | 20.9 mJ | 1.32 mJ | 1.22 mJ |
| Energy, without conv1 | 5.3 mJ | 1.04 mJ | 1.01 mJ |
| Useful MACs | 533 M | 531 M | 531 M |
| Area | 88.8 mm² | 0.42 mm² | 0.09 mm² |

The TPU-like design multiplies in fp32 (5.05 pJ per MAC in the PE, against
0.7 pJ for the int8 MAC of the two Timeloop designs) and has 128 times more
PEs than the Gemmini-like design. For batch-1 inference of a CNN, the smaller
int8 designs use far less energy. To see the TPU-like design at its best,
look at the matmul and the LLM prefill workloads.

## Files

```
config.yml                  the PyTorchSim run configuration (1 core, BookSim fly NoC)
togsim_results/             19 TOGSim logs, one per kernel, in run order
outputs/<hash>/             meta.txt, m5out/stats.txt, c<hash>_tog.py, c<hash>.mlir of each kernel
booksim2_config/            the NoC file the run used
kernels.yaml                kernel name -> hash -> log file
how_the_data_was_made/      the PyTorch script and the run manifest
run                         the command; the hardware model comes from ../
out/                        report.html + report.json (included; ./run overwrites them)
```

Two windows share one hash (`02_res2_1x1_p0` and `03_res2_3x3_p0`): the
same layout kernel for the same 1×64×56×56 input. `kernels.yaml` names them
by log file, so they stay apart in the report.

## Messages you'll see

- `WARNING (NW-6201)` ×12: one for each vector-only kernel (no
  `linalg.matmul`).
- `INFO (NW-6222)` ×7: the useful MACs and the array occupancy of each GEMM
  kernel. The conv1 line reads `118013952 useful MACs of 10074734592 active
  PE cycles (1.2%)`.
- `INFO (NW-6217)` ×19: the gem5 counts of each kernel are scaled by its tile
  graph.
- `INFO (NW-6001): 12 non-MAC kernel(s) use the f32 datapath of MAC kernel
  agpfubfynsc.` The vector kernels borrow the data type of the first GEMM
  kernel.
- `NW-8212` ×3, `NW-6607`, `NW-8111`, as in the parent folder.

## How the sample data was made

Same image and config as the parent folder, run on 2026-10-10. The script in
`how_the_data_was_made/` compiles each layer as its own function with
random float32 inputs and weights of the shapes in the table. Every
convolution lowered directly; no im2col fallback was needed. All outputs
match the CPU reference. See `docs/PYTORCHSIM_DOCKER.md` for the procedure.
