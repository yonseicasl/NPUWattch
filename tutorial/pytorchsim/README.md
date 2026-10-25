# PyTorchSim examples

PyTorchSim runs on a TPUv3-like NPU: one core with two 128×128 systolic
arrays, 128 VPU lanes with 16 MB of scratchpad memory, 16 HBM2 channels, and a BookSim `fly`
NoC, at 940 MHz. NPUWattch reads each run as is. Every folder has a `./run`
script and a README.

```
pytorchsim/
└── tpu_like_fp32/           the hardware model (three definition files) and its workloads
    ├── matmul_1024/         one 1024³ matmul (the basic example)
    ├── matmul_train/        forward + backward of the matmul (3 kernels)
    ├── matmul_2048_1core/   one 2048³ matmul on 1 core
    ├── matmul_2048_2core/   the same matmul on 2 cores
    ├── softmax/             softmax and exp2: kernels with no MAC
    ├── resnet50/            the 7 ResNet-50 layers of the Timeloop example, plus ReLU and batch norm
    ├── llama3_8b/           one Llama-3-8B decoder block: prefill/ and decode/
    ├── gemma2_9b/           one Gemma-2-9B decoder block: prefill/ and decode/
    └── deepseek_v2_lite/    one DeepSeek-V2-Lite MoE decoder block: prefill/ and decode/
```

```bash
cd tpu_like_fp32/matmul_1024 && ./run           # the basic example
cd tpu_like_fp32/resnet50 && ./run
cd tpu_like_fp32/llama3_8b/prefill && ./run
```

Start with `tpu_like_fp32/matmul_1024/README.md`. It explains each file and
each console message in detail. The tutorial runs are float32.

## Folder layout

`tpu_like_fp32/` is the design folder. Its three definition files
(`compound_components.yaml`, `projection.yaml`, `user_components.yaml`) are
the hardware model, and every workload folder below it uses them through
`--compound-components ../compound_components.yaml` and the two other flags.
This is the same layout as `../timeloop/`: a design folder with the hardware
files, and one folder per workload with the simulator data.

| File | Where | What it is |
| --- | --- | --- |
| `compound_components.yaml`, `projection.yaml`, `user_components.yaml` | design folder | The NPUWattch definition files |
| `config.yml` | each run root | The PyTorchSim configuration the run used (the 2-core run has a different one) |
| `togsim_results/*.log`, `*.trace` | each run root | One TOGSim log per kernel, in run order |
| `outputs/<hash>/` | each run root | `meta.txt`, `m5out/stats.txt`, and the kernel `.mlir` |
| `booksim2_config/` | each run root | The NoC file the run used |
| `kernels.yaml` | each workload folder | Kernel name → hash → log file. NPUWattch uses the names as window labels |
| `outputs/<hash>/*_tog.py` | each run root | The tile graph of the kernel. NPUWattch scales the gem5 counts of each tile operation by its executions |
| `how_the_data_was_made/` | each workload folder | The PyTorch script and the run manifest |
| `run` | each run root | The command |
| `out/` | each run root | The report |

## The workloads

| Workload | Kernels | Energy at 7nm | DRAM share | What it shows |
| --- | --- | --- | --- | --- |
| `matmul_1024` | 1 | 5.98 mJ | 8% | The basic example: 2.78 pJ/FLOP, arrays at 91% |
| `matmul_train` | 3 | 18.0 mJ | 9% | The backward pass is two more GEMMs of the same size |
| `matmul_2048_1core` | 1 | 47.9 mJ | 8% | 313 749 cycles on one core |
| `matmul_2048_2core` | 1 | 47.6 mJ | 8% | 169 707 cycles: 1.85× faster for the same energy and twice the area |
| `softmax` | 4 | 1.16 mJ | 83% | No MAC at all: DRAM takes the energy, and the vector datapath leads on chip |
| `resnet50` | 19 | 6.10 mJ | 46% | Batch-1 CNN layers on a large array; conv1 (3 input channels, 1.2% array occupancy) is 27% of the run |
| `llama3_8b/prefill` | 13 | 666.2 mJ | 12% | Large GEMMs keep the arrays full: 5.8 pJ per useful MAC |
| `llama3_8b/decode` | 13 | 42.9 mJ | 91% | Matrix-vector products: DRAM dominates, 192 pJ per useful MAC |
| `gemma2_9b/prefill` | 13 | 672.2 mJ | 20% | Wider heads and GeGLU: same energy as the Llama block for 9% fewer MACs |
| `gemma2_9b/decode` | 13 | 38.5 mJ | 91% | Matrix-vector products: 190 pJ per useful MAC |
| `deepseek_v2_lite/prefill` | 17 | 337.2 mJ | 31% | MoE: the 64 expert GEMMs with 48 rows each are 69% of the energy |
| `deepseek_v2_lite/decode` | 17 | 14.3 mJ | 90% | 6 experts of one token each; DRAM again |

Each README has the per-kernel table, the energy per useful MAC, and the
messages the run prints. NPUWattch counts the useful MACs of each GEMM
kernel from the operator and its tensor shapes, charges them in the compute
mode of the PE, and charges the active PE cycles that hold no real weight in
the idle mode, which costs leakage only (`INFO NW-6222` gives both numbers). The `MAC ops` and
`pJ/MAC` of the report are therefore per useful MAC.

## Three things these runs show

**Prefill and decode are different machines.** On the Llama block, 512
prefill tokens cost 666.2 mJ (1.30 mJ per token) with the arrays at 86%. One
decode token costs 42.9 mJ with DRAM at 91%. The same ratio appears in
the Timeloop runs of the same block on the Gemmini-like and NVDLA-like
designs.

**Reuse decides the energy per MAC.** The dense GEMMs of the LLM blocks
cost 5.5 to 6.8 pJ per useful MAC. The expert GEMMs of DeepSeek, with 48 rows
each, cost 8.5 to 9.2 pJ. The conv1 layer of ResNet-50, with three input
channels, costs 13.7 pJ: only 1.2% of its active PE cycles do useful work.
The empty PEs are clock-gated and cost leakage only, so the extra cost is
the data movement of nearly empty tiles.

**The non-GEMM kernels are small but visible.** Softmax, RMSNorm, and the
activation are 1 to 2% of a prefill block and under 1% of a decode block.
In the softmax run alone, DRAM takes 83% of the energy, and the vector
datapath is the largest on-chip line.
This is work the Timeloop examples do not see.

## How the sample data was made

All runs use the public PyTorchSim Docker image
`ghcr.io/psal-postech/torchsim-tutorial:ispass2026` and its bundled
`systolic_ws_128x128_c1_booksim_tpuv3.yml` config (the 2-core run uses
`systolic_ws_128x128_c2_booksim_tpuv3.yml`). The basic matmul was run on
2026-07-21 and the workloads on 2026-10-10. Each kernel is one
`torch.compile` call, so each kernel has its own TOGSim log. The script and
the run manifest of each workload are in its `how_the_data_was_made/`
folder; `docs/PYTORCHSIM_DOCKER.md` in the repository describes the
procedure. We made one change to the simulator output for the tutorial: we
kept only the kernel `.mlir` file of each `outputs/<hash>/` directory.
