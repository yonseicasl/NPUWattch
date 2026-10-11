# Workload — matmul_1024: one 1024³ matmul (the basic example)

One 1024×1024×1024 float32 `torch.matmul` on the TPUv3-like NPU of `../`.
Start here: this README explains each input file and each console message.

```bash
./run
```

## Files

```
config.yml                              the PyTorchSim run configuration
togsim_results/*.log                    the TOGSim simulation log (the run's results)
togsim_results/*.trace                  the kernel trace TOGSim replayed
outputs/fqywo6ndalo/meta.txt            operand dtypes and shapes
outputs/fqywo6ndalo/m5out/stats.txt     gem5 statistics of the sample program (one dump per tile operation)
outputs/fqywo6ndalo/c<hash>_tog.py      the tile graph: the loop nest of the kernel
outputs/fqywo6ndalo/c<hash>.mlir        the compiled kernel
booksim2_config/fly_c16_m16.icnt        the NoC topology used
kernels.yaml                            kernel name -> hash -> log file (names the report window)
run                                     the script; the hardware model comes from ../
out/                                    report.html + report.json (included; ./run overwrites them)
../compound_components.yaml             the hardware model: compounds made of NPUWattch primitives
../projection.yaml                      PyTorchSim actions -> activity of the compound elements
../user_components.yaml                 cost of custom blocks (one example entry)
```

`fqywo6ndalo` is PyTorchSim's hash for the compiled kernel. Each kernel gets
one report window. A run with several kernels has one `outputs/<hash>/`
directory per kernel. By default the window is labeled with the hash;
`kernels.yaml` gives it the name `matmul_1024` instead. The other workload
folders of `../` have the same layout.

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
| **`meta.txt` + `.mlir`** | The MAC data types. `linalg.matmul` takes `f32` inputs and produces an `f32` output, so the PEs are modeled as fp32 MACs (8-bit exponent, 23-bit mantissa) |
| **`config.yml`** | Fills in values that the log header doesn't include, and cross-checks the rest |
| **`booksim2_config/`** | The NoC network file. It's only needed for `anynet` topologies. This run uses `fly`, which the log describes completely |

The rebuilt machine is what `--tree` prints: 2 × 16 384 fp32 MACs with their
weight registers, a 16 MB VMEM, 128 VPU lanes (each with a scratchpad,
register file, FPU, and SFU), a DMA queue and address adder, a 32×32 NoC
crossbar with its buffers, and 16 HBM channels.

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
  Here that's `../user_components.yaml`
  (`--user-components my_lib.yaml` picks a different file). The file has one
  example entry that this design doesn't use, so the run prints this reminder.
  It doesn't affect the result.

`../compound_components.yaml` and `../projection.yaml` are inputs too.
Together, they define the hardware model of this TPU-like design (systolic
array, vector unit, scratchpads, SFU, DMA, DRAM, and NoC) and the rules that
turn each simulator counter into activity. `run` passes them with
`--compound-components`, `--projection`, and `--user-components`; without
the flags, NPUWattch looks for the three files by name in the run folder.
The design is defined entirely by these files, so the run stops with an
error if they are missing.

## The shortcut

`../../../../run.sh` finds `togsim_results/`, `outputs/`, `config.yml`,
`booksim2_config/`, and an `energy_tables/` folder under one root folder and
builds the command for you. It expects the three definition files in the
root, so copy them in first:

```bash
cp ../compound_components.yaml ../projection.yaml ../user_components.yaml .
../../../../run.sh -n .              # print the command it would run
../../../../run.sh    . --node 7nm --report out/
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

We made two changes for the tutorial, both described above: we added the
`core_spad_size_kb` line to `config.yml`, and we removed the large
`*_llvm.mlir` intermediate files (NPUWattch reads only the kernel file
`c<hash>.mlir` and the tile graph `c<hash>_tog.py`). Everything else is the
simulator's original output.
