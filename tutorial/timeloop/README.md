# Timeloop / Accelergy examples

Three accelerator designs, each with real `timeloop-mapper` output. Each
example is a folder with a `./run` script.

```
timeloop/
├── eyeriss_like/            Eyeriss-like (14×12 PE array)
│   └── alexnet/             AlexNet, 8 layers (the basic example)
├── gemmini_like/            Gemmini-like (16×16 systolic array)
│   ├── resnet50/            ResNet-50, 7 representative layers
│   └── llama3_8b/           Llama-3-8B, one decoder block (prefill + decode)
└── nvdla_like/              NVDLA-like (8×8 MAC cells + SDP post-processing)
    ├── resnet50/
    └── llama3_8b/
```

```bash
cd eyeriss_like/alexnet  && ./run
cd gemmini_like/resnet50 && ./run
cd nvdla_like/llama3_8b  && ./run
```

Each run writes `out/report.html` and `out/report.json` to its own folder. All
five folders already include the reports from a 7nm, 1 GHz run.

## Folder layout

A design folder has the files that describe the hardware. A workload folder
has the files for one run on that hardware.

| File | Where | What it is |
| --- | --- | --- |
| `arch.yaml` | design folder | The Accelergy v0.4 architecture, the same file Timeloop reads |
| `compound_components.yaml`, `projection.yaml`, `user_components.yaml` | design folder | The NPUWattch definition files. NPUWattch reads them from the folder that has `arch.yaml` |
| `stats_map.yaml` | design folder (`nvdla_like` only) | Maps stats levels to components (`--stats-map`). Here it gives the SDP its activity |
| `stats/*.stats.txt` | workload folder | One `timeloop-mapper` stats file per layer |
| `run` | workload folder | The command (`--arch-yaml ../arch.yaml --stats stats/`) |
| `out/` | workload folder | The report |

Start with `eyeriss_like/README.md`. It explains each file and each console
message in detail.

## The two tutorial designs

Both designs follow the specifications in Table IV of the NPUWattch HPCA'26
paper: int8 operands, int32 accumulation, LPDDR4 DRAM, and
`technology: "7nm"`.

| | `gemmini_like` | `nvdla_like` |
| --- | --- | --- |
| Compute | 16 × 16 weight-stationary systolic array (256 MACs) | 8 MAC cells × 8 multipliers, adder-tree reduction (64 MACs) |
| On-chip buffer | 256 KB scratchpad (4 banks) + 64 KB accumulator (2 banks) | 64 KB CBUF (16 banks) + 1 KB CACC |
| Per-PE registers | Weight (double-buffered), input, and partial sum | Weight and input. Partial sums go through the adder tree |
| Post-processing | — | SDP: bias, batch norm, ReLU, and int8 requantization (a user component; see `nvdla_like/README.md`) |
| Area at 7nm | 0.423 mm² | 0.088 mm² |

## The two workloads

The window label for each layer is its stats file name. NPUWattch sorts the
files by name, so the Llama report lists the seven `decode_*` windows first,
followed by the seven `prefill_*` windows.

**ResNet-50**: seven layers, one from each part of the network.

| Window | Layer | Shape |
| --- | --- | --- |
| `01_conv1` | conv1 | C=3, M=64, R=S=7, P=Q=112, stride 2 |
| `02_res2_1x1` | res2 1×1 reduce | C=64, M=64, P=Q=56 |
| `03_res2_3x3` | res2 3×3 | C=64, M=64, R=S=3, P=Q=56 |
| `04_res3_3x3` | res3 3×3 | C=128, M=128, R=S=3, P=Q=28 |
| `05_res4_1x1_exp` | res4 1×1 expand | C=256, M=1024, P=Q=14 |
| `06_res5_3x3` | res5 3×3 | C=512, M=512, R=S=3, P=Q=7 |
| `07_fc` | fc | C=2048, M=1000 |

**Llama-3-8B**: one decoder block, W8A8. Prefill processes 512 tokens
(P=512). Decode generates one token (P=1) with a 512-entry KV cache. The
attention layers use one group per query head (G=32).

| Window | Layer | Shape (prefill; decode has P=1) |
| --- | --- | --- |
| `*_1_q_proj` | Q projection | C=4096, M=4096, P=512 |
| `*_2_kv_proj` | K and V projections together | C=4096, M=2048, P=512 |
| `*_3_attn_qk` | Q·Kᵀ per head | C=128, M=512, P=512, G=32 |
| `*_4_attn_av` | scores·V per head | C=512, M=128, P=512, G=32 |
| `*_5_o_proj` | output projection | C=4096, M=4096, P=512 |
| `*_6_ffn_up_gate` | FFN up and gate together | C=4096, M=28672, P=512 |
| `*_7_ffn_down` | FFN down | C=14336, M=4096, P=512 |

## Results (7nm, 1 GHz, LPDDR4 8 pJ/bit)

| | Gemmini-like | NVDLA-like |
| --- | --- | --- |
| ResNet-50, total | 1323 µJ | **1219 µJ** |
| ResNet-50, DRAM share | 39% | 58% |
| On-chip energy per MAC | 1.53 pJ | 0.96 pJ |
| Llama-3-8B block, total | **310 mJ** | 1021 mJ |
| Llama-3-8B, DRAM share in prefill | 44% | 90% |
| Llama-3-8B, DRAM share in decode | 97% | 98% |

The better design depends on the workload. For ResNet-50, the NVDLA-like
design uses less energy because its datapath is cheaper. It has no per-PE
partial-sum register, which accounts for 35% of the Gemmini-like design's
on-chip energy. For Llama-3-8B, the Gemmini-like design uses 3.3 times less
energy. Neither design can write partial sums to memory, so the accumulator
size determines how often the inputs and weights of a long reduction have to
be read again. The Gemmini-like accumulator holds 64 KB, while the NVDLA-like
CACC holds only 1 KB. Decode is a matrix-vector product on both designs, so
DRAM accounts for almost all of the decode energy.

The NVDLA-like numbers include its SDP (2.0% of the ResNet-50 energy and less
than 0.1% of the Llama-3-8B energy). The Gemmini-like design doesn't include a
post-processing unit.

## How the sample data was made

We wrote the two `arch.yaml` files in this folder for this tutorial. They are
not part of the upstream
[timeloop-accelergy-exercises](https://github.com/Accelergy-Project/timeloop-accelergy-exercises).
The stats files come from `timeloop-mapper` (NVlabs/timeloop master, commit
`3237082`), with one mapper run per layer and design. We used a victory
condition of 2000, a timeout of 50000, and 8 threads. The default exercise
setting (victory condition 100) stops too early on the 256-PE array. The stats
files are unedited.

Both `arch.yaml` files prevent partial-sum spills, so the accumulator holds
each output until its reduction is done. (`nvdla_like/README.md` explains the
two constraints that do this.) In all 42 runs, each output is written to DRAM
once, and no output is read back.

The SDP level in `nvdla_like/arch.yaml` holds no data and has no loops, so it
doesn't change the mapping. The NVDLA-like layers give the same cycles and the
same Timeloop energy with or without it.
