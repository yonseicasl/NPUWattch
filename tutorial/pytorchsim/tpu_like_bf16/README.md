# Design — tpu_like_bf16: the same NPU with bf16 PEs

This design uses the simulator run of `../tpu_like_fp32/matmul_1024/` (one
1024×1024×1024 float32 `torch.matmul` on a TPUv3-like NPU), but it models the
systolic PEs as bf16 MACs, as in a real TPU. Only `compound_components.yaml`
differs from `../tpu_like_fp32/`. The simulator files are not copied: the
`run` script reads them from the fp32 folder.

```bash
cd matmul_1024 && ./run
```

## Files

```
compound_components.yaml                the hardware model, with the PE fixed to a bf16 fpmac
projection.yaml                         the same file as ../tpu_like_fp32/
user_components.yaml                    the same file as ../tpu_like_fp32/
matmul_1024/run                         the script: data from ../../tpu_like_fp32/matmul_1024/, model from ../
matmul_1024/out/                        report.html + report.json (included; ./run overwrites them)
```

To price any other workload of `../tpu_like_fp32/` with bf16 PEs, give its
`run` script this folder's compound file:

```bash
cd ../tpu_like_fp32/llama3_8b/prefill
./run --compound-components ../../../tpu_like_bf16/compound_components.yaml --report out_bf16/
```

## What NPUWattch reads

There's no architecture file here. PyTorchSim sets up its hardware
configuration at runtime, so NPUWattch rebuilds the hardware from the
simulator's own configuration.

| Input | What NPUWattch gets from it |
| --- | --- |
| **TOGSim log header** | The shape of the machine: cores, systolic arrays per core, VPU lanes and vector width, clock, DRAM channels, and NoC type |
| **TOGSim log tail** | The activity: active and idle cycles per systolic array, vector-unit cycles, DMA cycles, DRAM reads and writes, and total execution cycles |
| **`m5out/stats.txt`** | `CustomMatMul*` and `CustomV*` instruction counts (weight pushes, input pushes, pops, and SFU ops). gem5 runs each tile operation one time, so NPUWattch multiplies each count by the executions of its tile operation |
| **`c<hash>_tog.py`** | The tile graph: how many times each tile operation runs. Without it, NPUWattch scales the gem5 counts by the COMP counts of the log and prints `NW-6218` |
| **`meta.txt` + `.mlir`** | The kernel data types. `linalg.matmul` takes `f32` inputs and produces an `f32` output. The systolic PE in this design doesn't use them (see below), but the vector unit does, so it stays fp32 |
| **`config.yml`** | Fills in values that the log header doesn't include, and cross-checks the rest |
| **`booksim2_config/`** | The NoC network file. It's only needed for `anynet` topologies. This run uses `fly`, which the log describes completely |

The rebuilt machine is what `--tree` prints: 2 × 16 384 bf16 MACs with their
16-bit weight registers, 128 VPU lanes (each with a 128 KB scratchpad,
together the 16 MB scratchpad memory of the core, a register file, an FPU,
and an SFU), a DMA queue and address adder, a 32×32 NoC
crossbar with its buffers, and 16 HBM channels.

## How the PE is set to bf16

<!-- Internal note: PyTorchSim cannot simulate bf16 or fp16 kernels. Its gem5
does not decode the bf16 instructions, and the frontend does not accept fp16.
So the simulator run is float32, and the bf16 datapath comes from the hardware
model, not from the run. -->
The simulator run is float32, so the bf16 datapath comes from the hardware
model. In `compound_components.yaml`, the `pe` element of `systolic_mac` uses a
fixed primitive and config instead of the `{mac_primitive}` and `{mac_config}`
templates in `../tpu_like_fp32/compound_components.yaml`:

```yaml
    pe:
      primitive: fpmac
      config:
        exponent_bits: 8              # bf16 = e8m7
        mantissa_bits: 7
        pipeline_stages: 4
      count: "lanes*lanes"
    w_reg:
      ...
        data_width: 16                # one bf16 weight
```

A fixed element doesn't follow the kernel's data type. You can use the same
approach whenever you want the hardware datapath to differ from the simulated
kernel. The report shows the PE data type ("bf16 datapath") and its
fp32-equivalent pJ/FLOP.

What carries over from the float32 run:

- **Cycles and MAC counts.** The systolic array does one MAC per PE per cycle
  for any data type, so the 1 073 741 824 MACs and the active cycles apply to
  bf16 as well.
- **DRAM, scratchpad, and NoC traffic.** These counts come from the float32 run, so
  they reflect float32 data sizes. At 7nm, DRAM accounts for 22% of the total
  energy of this run.
  <!-- Internal note: a bf16 kernel moves half of these bytes. NPUWattch
  charges the counts from the log without scaling them, so the memory and NoC
  energy is high for bf16. -->

A TPU MXU multiplies in bf16 and accumulates in fp32. In this example, the
`fpmac` primitive uses bf16 for both. We are preparing to support
mixed-precision MACs in the future.
<!-- Internal note: the fpmac primitive uses one format for the multiplier and
the accumulator, so the PE energy of this example is a lower bound for an MXU
PE. -->

Results at 7nm:

| | `../tpu_like_fp32/matmul_1024/` | this design |
| --- | --- | --- |
| energy per MAC of one PE | 5.05 pJ | 1.56 pJ |
| total energy | 5.98 mJ | 2.22 mJ |
| pJ/FLOP (DRAM included) | 2.78 | 1.04 |

For comparison, the TPUv4i (7nm, 4 × 128×128 bf16 MXUs) has a TDP of 175 W and
a peak of 138 bf16 TFLOP/s (Jouppi et al., ISCA 2021), which works out to
1.27 pJ/FLOP. The TDP is an upper limit on chip power, and it covers the whole
chip, including the scalar core, the 128 MiB CMEM, the inter-chip links, and
the HBM PHY.

## Messages you'll see, and why

Each message line has the format `LEVEL (NW-nnnn): text`. To read more
about a message, run `npuwattch --explain NW-nnnn`.

The run prints four warnings. Each one tells you what NPUWattch assumed or
extrapolated. None of them stops the run.

- `WARNING (NW-8212): vpu_spad: The SRAM of 1048576 bits uses the macro
  templates 4x sram_256k in banks of at most 16 macros (utilization
  100.0%).` The same warning occurs for icnt_buf. The config
  gives only a capacity, not a macro layout. So NPUWattch builds each memory
  from characterized macros and reports the utilization it got.
- `WARNING (NW-6607): CustomMatMulwVpush: NPUWattch divides the kernel total
  between the arrays by their active cycles.` The weight-push count is a
  kernel total. With two arrays, NPUWattch splits it based on how busy each
  array was.
- `WARNING (NW-8111): core0.vrf: width=256 is outside the characterized range
  8-128 of regfile.` The vector register file is 256 bits wide
  (`vpu_vector_length_bits`). The regfile model is trained on widths from 8 to
  128 bits, so NPUWattch extrapolates to 256 bits.

The INFO messages:

- `INFO (NW-6008): Out of scope: ...` and `INFO (NW-2209): Activity stat
  ... is not charged, because projection 'pytorchsim' waives it: ...`: the
  list of items that are *not* included in the totals. These are the scalar
  RISC-V core and its caches (left out on the advice of the PyTorchSim
  authors, since their energy is very small next to the datapath), the VCIX
  serializer, barrier instructions, DRAM standby power, and activity counters
  that would count work already charged somewhere else. The text after
  `Out of scope:` comes from `projection.yaml`.
- `INFO (NW-6222): fqywo6ndalo: 1073741824 useful MACs of 1073741824 active
  PE cycles (100.0%) ...`: NPUWattch counts the MACs of the operator from
  its shapes (1024³) and compares them with the PE cycles the arrays were
  active. Here every active PE did a useful MAC. In a kernel that leaves PEs
  empty (a batch-1 convolution, a matrix-vector product), the empty PE
  cycles are charged in the idle mode instead. `INFO (NW-6217)` says that the
  gem5 counts were scaled by the tile graph (3 tile operations, 577
  executions).
- `INFO (NW-2116): User component 'example_68000_cpu_core'
  (user_components.yaml) is in the library, but the run does not use it.`
  For custom blocks, such as control logic or a CPU core, you
  provide the area and the energy of each action in a user component library.
  Here that's `user_components.yaml` in this folder
  (`--user-components my_lib.yaml` picks a different file). The file has one
  example entry that this design doesn't use, so the run prints this reminder.
  It doesn't affect the result.

`compound_components.yaml` and `projection.yaml` are inputs too. Together,
they define the hardware model (systolic array, vector unit, scratchpads,
SFU, DMA, DRAM, and NoC) and the rules that turn each simulator counter into
activity. `matmul_1024/run` passes this folder's files with
`--compound-components`, `--projection`, and `--user-components`, and the
simulator files of the fp32 run with `--togsim-dir`, `--gem5-dir`,
`--config-yml`, `--booksim-dir`, and `--kernel-names`.

## How the sample data was made

This is a real run. We made it on 2026-07-21 with the public PyTorchSim Docker
image `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` and its bundled
`systolic_ws_128x128_c1_booksim_tpuv3.yml` config: 1 core, 2 systolic arrays
of 128×128, 128 VPU lanes, 940 MHz, 16 HBM2 channels, and a BookSim `fly` NoC.
The workload is a single `torch.matmul` of two 1024×1024 float32 tensors under
`torch.compile`, which is 1 073 741 824 MACs. The NPUWattch report shows
1 073 881 472, because it also counts one vector operation.

The simulator files are those of `../tpu_like_fp32/matmul_1024/`; see its
README for the two changes we made for the tutorial.
