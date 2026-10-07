# Timeloop example — NVDLA-like

An NVDLA-like convolution core (nv_small class) with its SDP post-processing
unit, and two workloads:

```bash
cd resnet50  && ./run        # ResNet-50, 7 layers
cd llama3_8b && ./run        # Llama-3-8B, one decoder block (prefill + decode)
```

`../README.md` lists the layer shapes for both workloads and compares this
design with `gemmini_like`.

## Files

```
arch.yaml                 the architecture description (Accelergy v0.4)
compound_components.yaml  NPUWattch definition files, read from the directory
projection.yaml             of arch.yaml
user_components.yaml      the cost of the SDP (measured) and one example entry
stats_map.yaml            connects the DRAM writes to the SDP (--stats-map)
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
└── nvdla
    ├── sdp                      (class: dummy_storage)     → user component nvdla_sdp
    ├── cbuf                     (class: smartbuffer_SRAM = 64 KB, 16 banks)  → sram
    ├── cacc                     (class: smartbuffer_SRAM = 1 KB)             → sram
    └── mac_cell (meshY=8)
        └── lane (meshX=8)
            ├── weight_reg [×64]  (class: regfile = 1 B)   → regfile
            ├── input_reg  [×64]  (class: regfile = 1 B)   → regfile
            └── mac        [×64]  (class: intmac)          → intmac
```

- CBUF holds features and weights, and CACC holds the int32 partial sums. The
  `!Parallel` node places them side by side, so Timeloop can send each data
  space to its own buffer.
- Each of the 8 MAC cells computes one output channel. Its 8 lanes multiply 8
  input channels, and an adder tree sums the 8 products. So a lane has no
  partial-sum register. The `!Nothing` node in `arch.yaml` tells Timeloop that
  the outputs are reduced spatially on their way to CACC.
- `mac` declares `multiplier_width: 8` and `adder_width: 32`. NPUWattch uses
  them as the operand and accumulator widths.

## The SDP: a block that Timeloop doesn't model

Every output of the convolution core goes from CACC through the SDP (Single
Data Point processor) to DRAM. The SDP adds the bias, applies batch norm and
ReLU, and converts the int32 accumulator value to int8, one element per cycle.
Timeloop has no model for the SDP, so this example adds it as an NPUWattch
user component with measured costs. Three files bring it into the run:

1. **`arch.yaml`** declares `sdp` as a Timeloop level that does nothing: class
   `dummy_storage` (zero cost in Accelergy), no data (it bypasses all data
   spaces), and no loops (all temporal factors are 1). So Timeloop finds the
   same mappings as it would without it. The attribute
   `user_component: "nvdla_sdp"` tells NPUWattch where to find its cost.
2. **`user_components.yaml`** gives that cost. The `nvdla_sdp` entry is a
   measurement, not an estimate. We ran the NVDLA SDP RTL (nv_small) through
   the NPUWattch logic flow (synthesis, place and route, extraction,
   gate-level simulation, and PrimeTime power) at 20, 16, 10, 7, and 5nm. The
   run uses the 7nm values (`reference`). The values for the other nodes are
   under `characterized`.

   | action | energy at 7nm, 800 MHz | meaning |
   | --- | --- | --- |
   | `process` | 15.65 pJ | one element of the conv epilogue |
   | `idle` | 9.09 pJ | one clock cycle with no input |
   | `random` | 16.91 pJ | one element with random data (upper bound) |

   Area 1942 µm², leakage 0.012 mW.
3. **`stats_map.yaml`** provides the activity. Timeloop counts the DRAM
   writes, and one write event is a block of 8 int8 outputs. The map charges
   each write to DRAM, and also as 8 `process` actions of `sdp`:

   ```yaml
   levels:
     DRAM:
       read: DRAM
       write: [DRAM, {sdp: {count: 8, action: process}}]
   ```

`user_components.yaml` also has the example entry `example_68000_cpu_core`,
which no design uses.

## Results (7nm, 1 GHz)

| | ResNet-50 | Llama-3-8B block |
| --- | --- | --- |
| Total energy | 1219 µJ | 1021 mJ (prefill 1006 mJ, decode 15 mJ) |
| DRAM share | 58% | prefill 90%, decode 98% |
| SDP share | 2.0% | 0.05% |
| Average power | 91 mW | 569 mW |
| On-chip energy per MAC | 0.96 pJ | 0.91 pJ |
| Area | 0.088 mm² | 0.088 mm² |

On chip, `mac` uses about 75% of the energy. Without a per-PE partial-sum
register, the datapath uses about 40% less energy per MAC than the
Gemmini-like design.

The accumulator is the bottleneck. CACC holds 256 int32 partial sums, and
NVDLA can't write partial sums to memory (see "No partial-sum spill" below).
So for each block of 256 outputs, the core reads the inputs and weights for
the whole reduction from DRAM again. In Llama-3-8B prefill, the reductions are
long (up to 14336), and DRAM takes 90% of the energy. The whole block uses 3.3
times the energy of the Gemmini-like design, whose accumulator holds 64 KB.

The SDP costs 15.65 pJ per output. Each output takes hundreds to thousands of
MACs, so the SDP is 2% of the ResNet-50 energy and almost nothing in the
DRAM-bound Llama-3-8B run.

## No partial-sum spill

The NVDLA CACC accumulates the whole reduction for an output before it sends
the output through the SDP to memory. Partial sums never leave the core.
Without constraints, Timeloop's mapper might write partial sums to DRAM and
read them back. `arch.yaml` prevents this with two constraints:

- `DRAM`: `temporal: {permutation: [C, R, S]}`. The reduction loops are the
  innermost DRAM loops.
- `cbuf`: `temporal: {factors: [M=1, P=1, Q=1, N=1, G=1]}`. There are no output
  loops at this level. (timeloopfe places `cbuf` above `cacc`, so an output
  loop here would cycle through the output tiles inside a DRAM reduction
  loop.)

With these constraints, every layer writes each output to DRAM once and never
reads an output back. So the DRAM writes are exactly the outputs that the SDP
processes.

## Messages you'll see

The run prints no warnings. The INFO messages:

- `sdp: attribute user_component 'nvdla_sdp' — the user component library
  entry gives its cost`: the link from item 1 above.
- `stats level 'DRAM' fans out per --stats-map: ... sdp ×8 as 'process'`: the
  mapping from item 3.
- `depth 8192 is the Accelergy total over 16 banks → mem_depth_per_bank 512`:
  in Accelergy, `depth` is the size of the whole buffer, so NPUWattch divides
  it by `n_banks`.
- `bandwidth 16 words/cycle (8 words per access) → up to 2 bank accesses per
  cycle`: a CBUF row has 8 int8 words, so Timeloop's 16 words/cycle means two
  bank accesses. NPUWattch charges each access as one read or write event.
- `no port count declared — assuming a single shared read-or-write port`:
  `arch.yaml` has no port attributes, so NPUWattch uses one port.
- `ignored Accelergy attribute(s) datawidth`: `datawidth` is a Timeloop
  attribute. NPUWattch uses `width` for the row size.
- `parsed, but not used`: the example entries in `user_components.yaml` and
  `compound_components.yaml`.
