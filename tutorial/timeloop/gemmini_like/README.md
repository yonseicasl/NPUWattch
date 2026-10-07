# Timeloop example — Gemmini-like

A Gemmini-like accelerator (the default Gemmini configuration) with two
workloads:

```bash
cd resnet50  && ./run        # ResNet-50, 7 layers
cd llama3_8b && ./run        # Llama-3-8B, one decoder block (prefill + decode)
```

`../README.md` lists the layer shapes for both workloads and compares this
design with `nvdla_like`.

## Files

```
arch.yaml                 the architecture description (Accelergy v0.4)
compound_components.yaml  NPUWattch definition files, read from the directory
projection.yaml             of arch.yaml (the same files as in ../eyeriss_like/)
user_components.yaml
resnet50/stats/           7 timeloop-mapper stats files, one per layer
resnet50/run              the command
resnet50/out/             report.html + report.json
llama3_8b/stats/          14 timeloop-mapper stats files (7 decode, 7 prefill)
llama3_8b/run
llama3_8b/out/
```

## The design

`--tree` prints the hardware that NPUWattch builds from `arch.yaml`:

```
system_top_level
├── DRAM                         (class: DRAM)              → hbm primitive, LPDDR4 table
└── gemmini
    ├── scratchpad               (class: smartbuffer_SRAM = 256 KB, 4 banks)  → sram
    ├── accumulator              (class: smartbuffer_SRAM = 64 KB, 2 banks)   → sram
    └── PE_column (meshY=16)
        └── PE (meshX=16)
            ├── weight_reg [×256]  (class: regfile = 2 B)   → regfile
            ├── input_reg  [×256]  (class: regfile = 1 B)   → regfile
            ├── psum_reg   [×256]  (class: regfile = 4 B)   → regfile
            └── mac        [×256]  (class: intmac)          → intmac
```

- The scratchpad holds inputs and weights, and the accumulator holds the
  int32 outputs. The `!Parallel` node places them side by side, so Timeloop
  can send each data space to its own buffer.
- Each PE has three registers, as in the Gemmini RTL. The weight register has
  two entries because Gemmini double-buffers the stationary weight
  (`propagate`). The partial sum moves down the column through `psum_reg`.
- `mac` declares `multiplier_width: 8` and `adder_width: 32`. NPUWattch uses
  them as the operand and accumulator widths.

## Results (7nm, 1 GHz)

| | ResNet-50 | Llama-3-8B block |
| --- | --- | --- |
| Total energy | 1323 µJ | 310 mJ (prefill 295 mJ, decode 15 mJ) |
| DRAM share | 39% | prefill 44%, decode 97% |
| Average power | 316 mW | 673 mW |
| On-chip energy per MAC | 1.53 pJ | 1.45 pJ |
| Area | 0.423 mm² | 0.423 mm² |

On chip, `mac` uses about half of the energy, and `psum_reg` uses 35–38%.
Every cycle, each PE reads and writes a 32-bit partial sum. The NVDLA-like
design doesn't have this register (its adder tree reduces the partial sums),
and that's the main reason its datapath uses less energy per MAC.

Like the NVDLA-like design, `arch.yaml` prevents partial-sum spills (see "No
partial-sum spill" in `../nvdla_like/README.md`). The reduction loops are the
innermost DRAM loops, and the scratchpad level has no output loops. The 64 KB
accumulator holds 16K int32 partial sums, so a long reduction re-reads its
inputs and weights far less often than on the NVDLA-like design (1 KB CACC).

## Messages you'll see

The run prints no warnings. The INFO messages are the same kinds as in
`../eyeriss_like/README.md`:

- `depth 16384 is the Accelergy total over 4 banks → mem_depth_per_bank 4096`:
  in Accelergy, `depth` is the size of the whole buffer, so NPUWattch divides
  it by `n_banks`.
- `no port count declared — assuming a single shared read-or-write port`:
  `arch.yaml` has no port attributes, so NPUWattch uses one port.
- `ignored Accelergy attribute(s) datawidth`: `datawidth` is a Timeloop
  attribute. NPUWattch uses `width` for the row size.
- `parsed, but not used`: the example entries in `user_components.yaml` and
  `compound_components.yaml`.
