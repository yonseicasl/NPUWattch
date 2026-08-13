# Example 2 — PyTorchSim

One 1024×1024×1024 float32 `torch.matmul` on a TPUv3-like NPU.

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
run                                     the script
out/                                    report.html + report.json — shipped, and ./run overwrites them
```

`fqywo6ndalo` is PyTorchSim's hash for the compiled kernel. One kernel = one
report window; a multi-kernel run has one `outputs/<hash>/` directory each.

## What NPUWattch reads

There is no architecture file here. NPUWattch rebuilds the hardware from the
simulator's own configuration, because PyTorchSim decides its configuration at
runtime.

| Input | What comes out of it |
| --- | --- |
| **TOGSim log header** | cores, systolic arrays per core, VPU lanes and vector width, clock, DRAM channels, NoC type — the shape of the machine |
| **TOGSim log tail** | active and idle cycles per systolic array, vector-unit cycles, DMA cycles, DRAM reads/writes, total execution cycles — the activity |
| **`m5out/stats.txt`** | `CustomMatMul*` and `CustomV*` instruction counts (weight pushes, input pushes, pops, SFU ops) |
| **`meta.txt` + `.mlir`** | the MAC's datatypes. `linalg.matmul` says `f32` in and `f32` out, so the PEs are modeled as fp32 MACs (exponent 8, mantissa 23) |
| **`config.yml`** | fills gaps the log header does not cover, and cross-checks the rest |
| **`booksim2_config/`** | the NoC network file. Only needed for `anynet` topologies; `fly` is fully described in the log, and this run uses `fly` |

The reconstructed machine is what `--tree` prints: 2 × 16 384 fp32 MACs with
their weight registers, a 16 MB VMEM, 128 VPU lanes each with a scratchpad,
register file, FPU and SFU, a DMA queue and address adder, a 32×32 NoC crossbar
with its buffers, and 16 HBM channels.

## About `core_spad_size_kb`

The last line of `config.yml` is an addition:

```yaml
core_spad_size_kb: 16384
```

PyTorchSim does not read this key — it does not model VMEM capacity. NPUWattch
does, to size the SRAM macro. Without it the VMEM component is skipped and a
warning says so. TPUv2/v3/v4 all have 16 MB, hence 16384 KB. Everything else in
`config.yml` is the file the simulator actually ran with.

## Messages you will see, and why

- `Configured clock (940 MHz) is within 20% of the estimated f_max (992 MHz)`
  — NPUWattch predicts a critical path, not only energy. This design has 5%
  timing margin at 940 MHz, which is tight.
- `capacity-only SRAM spec ... auto-applied macro template(s)` — the config
  gives a capacity, not a macro layout, so NPUWattch tiles it out of
  characterized macros and reports the utilization it achieved.
- `kernel-total events attributed per array in proportion to each array's
  active cycles` — gem5 counts `CustomMatMulwVpush` once for the kernel, not
  per array. With two arrays, the count is split by how busy each one was.
- The long `[INFO]` block — everything deliberately *not* charged: the scalar
  RISC-V core and its caches (excluded on the PyTorchSim authors' guidance, as
  negligible next to the datapath), the VCIX serializer, barrier instructions,
  DRAM standby power, and activity counters that would double-count work
  already charged elsewhere. Scope is stated, not hidden.

## The shortcut

`../../run.sh` finds `togsim_results/`, `outputs/`, `config.yml`,
`booksim2_config/`, and an `energy_tables/` folder under one root and builds the
command for you:

```bash
../../run.sh -n .              # print the command it would run
../../run.sh    . --node 7nm --report out/
```

`./run` spells the same command out so the flags are visible.

## How the sample data was made

A real run, produced with the published PyTorchSim Docker image
`ghcr.io/psal-postech/torchsim-tutorial:ispass2026` on 2026-07-21, using the
bundled `systolic_ws_128x128_c1_booksim_tpuv3.yml` config: 1 core, 2 systolic
arrays of 128×128, 128 VPU lanes, 940 MHz, 16 HBM2 channels, BookSim `fly` NoC.
The workload is a single `torch.matmul` of two 1024×1024 float32 tensors under
`torch.compile`, which is 1 073 741 824 MACs — and NPUWattch's report says
1 073 881 472, the difference being one vector operation the model also charges.

Two things were changed for the tutorial, both noted above: the
`core_spad_size_kb` line was added to `config.yml`, and the large `*_llvm.mlir`
intermediates were dropped (NPUWattch reads only the kernel `c<hash>.mlir`).
Everything else is the simulator's own output.
