# Design — tpu_like_fp32: a TPUv3-like NPU with fp32 PEs

This folder is the hardware model. The three definition files describe the
machine for NPUWattch; every workload folder below is one PyTorchSim run on
it. The simulator's own configuration (`config.yml` and the log header of
each run) gives the shape of the machine: one core with two 128×128 systolic
arrays, 128 VPU lanes, a 16 MB VMEM, 16 HBM2 channels, and a BookSim `fly`
NoC at 940 MHz.

```
tpu_like_fp32/
├── compound_components.yaml   the hardware model: compounds made of NPUWattch primitives
├── projection.yaml            PyTorchSim actions -> activity of the compound elements
├── user_components.yaml       cost of custom blocks (one example entry)
├── matmul_1024/               one 1024³ matmul (the basic example; start here)
├── matmul_train/              forward + backward of the 1024³ matmul (3 kernels)
├── matmul_2048_1core/         one 2048³ matmul on 1 core
├── matmul_2048_2core/         the same matmul on 2 cores (PyTorchSim's 2-core config)
├── softmax/                   softmax and exp2: kernels with no MAC
├── resnet50/                  the 7 ResNet-50 layers of the Timeloop example, plus ReLU and batch norm
├── llama3_8b/{prefill,decode}/         one Llama-3-8B decoder block
├── gemma2_9b/{prefill,decode}/         one Gemma-2-9B decoder block
└── deepseek_v2_lite/{prefill,decode}/  one DeepSeek-V2-Lite MoE decoder block
```

```bash
cd matmul_1024 && ./run
cd resnet50 && ./run
cd llama3_8b/prefill && ./run
```

Each workload folder is a complete PyTorchSim run root: `config.yml`,
`togsim_results/`, `outputs/<hash>/`, `booksim2_config/`, `kernels.yaml`
(kernel name → hash → log), `run`, `out/` (the report), and
`how_the_data_was_made/` (the PyTorch script and the run manifest). Its `run`
script passes the three definition files of this folder with
`--compound-components ../compound_components.yaml` and the two other flags,
so one hardware model serves every workload.

`matmul_1024/README.md` explains each input file and each console message in
detail. `../README.md` compares the workloads. `../tpu_like_bf16/` is the
same design with the PE fixed to a bf16 MAC.

## The three files

| File | What it is |
| --- | --- |
| `compound_components.yaml` | The compounds: `systolic_mac` (PE + weight register, `lanes×lanes` instances), `vpu` (register file + FPU per lane), `spads` (VMEM and the lane scratchpads, by capacity), `dma`, `fpsfu`, `noc`, `dram`. Element configs use the keys of the run configuration as symbols |
| `projection.yaml` | Which counter drives which element in which mode. The systolic array is charged per useful MAC (`useful_macs`), and the active PE cycles without a real weight in the idle mode (`array_idle_slots`). The gem5 instruction counts (pushes, pops, SFU operations) drive the registers, scratchpads, and SFU |
| `user_components.yaml` | One example entry that no workload uses. It shows the format for a block with your own numbers |

The compounds have no simulator-specific content. The projection is the
only file that names PyTorchSim counters.
