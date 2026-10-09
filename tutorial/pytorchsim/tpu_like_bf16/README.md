# Example 2b — PyTorchSim, TPU-like bf16

This example uses the same PyTorchSim run as `../tpu_like_fp32/` (one
1024×1024×1024 float32 `torch.matmul` on a TPUv3-like NPU), but it models the
systolic PEs as bf16 MACs, as in a real TPU. Only `compound_components.yaml`
is different from `../tpu_like_fp32/`. All the simulator files are the same.

```bash
./run
```

## Files

```
config.yml                              the PyTorchSim run configuration
togsim_results/*.log                    the TOGSim simulation log (the run's results)
togsim_results/*.trace                  the kernel trace TOGSim replayed
outputs/fqywo6ndalo/meta.txt            operand dtypes and shapes
outputs/fqywo6ndalo/m5out/stats.txt     gem5 statistics
outputs/fqywo6ndalo/c<hash>.mlir        the compiled kernel
booksim2_config/fly_c16_m16.icnt        the NoC topology used
compound_components.yaml                the hardware model: compounds made of NPUWattch primitives (PE set to bf16)
projection.yaml                         PyTorchSim actions -> activity of the compound elements
user_components.yaml                    cost of custom blocks (one example entry)
run                                     the script
out/                                    report.html + report.json (included; ./run overwrites them)
```

`fqywo6ndalo` is PyTorchSim's hash for the compiled kernel. Each kernel gets
one report window. A run with several kernels has one `outputs/<hash>/`
directory per kernel.

## What NPUWattch reads

There's no architecture file here. PyTorchSim sets up its hardware
configuration at runtime, so NPUWattch rebuilds the hardware from the
simulator's own configuration.

| Input | What NPUWattch gets from it |
| --- | --- |
| **TOGSim log header** | The shape of the machine: cores, systolic arrays per core, VPU lanes and vector width, clock, DRAM channels, and NoC type |
| **TOGSim log tail** | The activity: active and idle cycles per systolic array, vector-unit cycles, DMA cycles, DRAM reads and writes, and total execution cycles |
| **`m5out/stats.txt`** | `CustomMatMul*` and `CustomV*` instruction counts (weight pushes, input pushes, pops, and SFU ops) |
| **`meta.txt` + `.mlir`** | The kernel data types. `linalg.matmul` takes `f32` inputs and produces an `f32` output. The systolic PE in this design doesn't use them (see below), but the vector unit does, so it stays fp32 |
| **`config.yml`** | Fills in values that the log header doesn't include, and cross-checks the rest |
| **`booksim2_config/`** | The NoC network file. It's only needed for `anynet` topologies. This run uses `fly`, which the log describes completely |

The rebuilt machine is what `--tree` prints: 2 × 16 384 bf16 MACs with their
16-bit weight registers, a 16 MB VMEM, 128 VPU lanes (each with a scratchpad,
register file, FPU, and SFU), a DMA queue and address adder, a 32×32 NoC
crossbar with its buffers, and 16 HBM channels.

## How the PE is set to bf16

<!-- Internal note: PyTorchSim cannot simulate bf16 or fp16 kernels. Its gem5
does not decode the bf16 instructions, and the frontend does not accept fp16.
So the simulator run is float32, and the bf16 datapath comes from the hardware
model, not from the run. -->
The simulator run is float32, so the bf16 datapath comes from the hardware
model. In `compound_components.yaml`, the `pe` element of `systolic_mac` uses a
fixed primitive and config instead of the `{mac_primitive}` and `{mac_config}`
templates in `../tpu_like_fp32/`:

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
- **DRAM, VMEM, and NoC traffic.** These counts come from the float32 run, so
  they reflect float32 data sizes. At 7nm, DRAM accounts for 21% of the total
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

| | `../tpu_like_fp32/` | this example |
| --- | --- | --- |
| energy per MAC of one PE | 5.05 pJ | 1.56 pJ |
| total energy | 6.13 mJ | 2.29 mJ |
| pJ/FLOP (DRAM included) | 2.86 | 1.07 |

For comparison, the TPUv4i (7nm, 4 × 128×128 bf16 MXUs) has a TDP of 175 W and
a peak of 138 bf16 TFLOP/s (Jouppi et al., ISCA 2021), which works out to
1.27 pJ/FLOP. The TDP is an upper limit on chip power, and it covers the whole
chip, including the scalar core, the 128 MiB CMEM, the inter-chip links, and
the HBM PHY.

## About `core_spad_size_kb`

We added the last line of `config.yml`:

```yaml
core_spad_size_kb: 16384
```

PyTorchSim doesn't use this key, but NPUWattch needs it to size the VMEM SRAM.
Without it, NPUWattch skips the VMEM component and prints warning NW-6006.
TPUv2, v3, and v4 all have 16 MB of VMEM, so the value is 16384 KB. The rest
of `config.yml` is exactly what the simulator ran with.

## Messages you'll see, and why

Each message line has the format `LEVEL (NW-nnnn): text`. To read more
about a message, run `npuwattch --explain NW-nnnn`.

The run prints five warnings. Each one tells you what NPUWattch assumed or
extrapolated. None of them stops the run.

- `WARNING (NW-8212): vmem: The SRAM of 134217728 bits uses the macro
  templates 512x sram_256k in banks of at most 16 macros (utilization
  100.0%).` The same warning occurs for vpu_spad and icnt_buf. The config
  gives only a capacity, not a macro layout. So NPUWattch builds each memory
  from characterized macros and reports the utilization it got.
- `WARNING (NW-6607): CustomMatMulwVpush: NPUWattch divides the kernel total
  between the arrays by their active cycles.` gem5 counts
  `CustomMatMulwVpush` once for the whole kernel, not per array. With two
  arrays, NPUWattch splits the count based on how busy each array was.
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
- `INFO (NW-2116): User component 'example_68000_cpu_core'
  (user_components.yaml) is in the library, but the run does not use it.`
  For custom blocks, such as control logic or a CPU core, you
  provide the area and the energy of each action in a user component library.
  Here that's `user_components.yaml` in this folder
  (`--user-components my_lib.yaml` picks a different file). The file has one
  example entry that this design doesn't use, so the run prints this reminder.
  It doesn't affect the result.

`compound_components.yaml` and `projection.yaml` are inputs too. Together,
they define the hardware model of this TPU-like design (systolic array, vector
unit, scratchpads, SFU, DMA, DRAM, and NoC) and the rules that turn each
simulator counter into activity. NPUWattch reads all three files from this
folder by name, and `--compound-components`, `--projection`, and
`--user-components` let you pick other files. The design is defined entirely
by these files, so the run stops with an error if they are missing.

## The shortcut

`../../../run.sh` finds `togsim_results/`, `outputs/`, `config.yml`,
`booksim2_config/`, and an `energy_tables/` folder under one root folder and
builds the command for you:

```bash
../../../run.sh -n .              # print the command it would run
../../../run.sh    . --node 7nm --report out/
```

`./run` writes out the same command in full, so you can see all the flags.

## How the sample data was made

This is a real run. We made it on 2026-07-21 with the public PyTorchSim Docker
image `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` and its bundled
`systolic_ws_128x128_c1_booksim_tpuv3.yml` config: 1 core, 2 systolic arrays
of 128×128, 128 VPU lanes, 940 MHz, 16 HBM2 channels, and a BookSim `fly` NoC.
The workload is a single `torch.matmul` of two 1024×1024 float32 tensors under
`torch.compile`, which is 1 073 741 824 MACs. The NPUWattch report shows
1 073 881 472, because it also counts one vector operation.

This folder uses the same files as `../tpu_like_fp32/`. We made two changes
for the tutorial, both described above: we added the `core_spad_size_kb` line
to `config.yml`, and we removed the large `*_llvm.mlir` intermediate files
(NPUWattch reads only the kernel file `c<hash>.mlir`). Everything else is the
simulator's original output.
