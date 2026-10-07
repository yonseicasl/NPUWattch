# Timeloop example — Eyeriss-like, AlexNet

An Eyeriss-like accelerator running all eight layers of AlexNet. This is the
basic Timeloop example. `../README.md` lists the others.

```bash
cd alexnet && ./run
```

## Files

```
arch.yaml                         the architecture description (Accelergy v0.4)
compound_components.yaml          compound components: an Accelergy class -> several primitives
projection.yaml                   Timeloop events (read/write/compute) -> compound elements
user_components.yaml              cost of custom blocks (one example entry)
alexnet/stats/01_conv1.stats.txt  Timeloop's activity counts for layer 1
alexnet/stats/02_conv2.stats.txt  ... one file per layer, 8 in total
alexnet/stats/08_fc8.stats.txt
alexnet/run                       the script (--arch-yaml ../arch.yaml --stats stats/)
alexnet/out/                      report.html + report.json (included; ./run overwrites them)
```

## What NPUWattch reads

**`arch.yaml`**: the same file you give Timeloop. It declares six components:

| Component | Accelergy class | NPUWattch primitive |
| --- | --- | --- |
| `DRAM` | `DRAM` | `hbm` (analytic constants) |
| `shared_glb` | `smartbuffer_SRAM` | `sram` |
| `ifmap_spad`, `weights_spad`, `psum_spad` | `smartbuffer_RF` | `regfile` |
| `mac` | `intmac` | `intmac` |

The `!Container` nodes (`PE_column` with `meshX: 14`, `PE` with `meshY: 12`)
set the instance counts: 14 × 12 = 168 copies of each scratchpad and MAC.

**`alexnet/stats/*.stats.txt`**: what Timeloop's mapper reported for the
mapping it found. NPUWattch reads the per-level `STATS` blocks:

```
=== weights_spad ===
    STATS
    -----
    Cycles               : 638880
    Weights:
        Scalar reads (per-instance)              : 638880
        Scalar fills (per-instance)              : 11616
        Utilized instances (max)                 : 110
```

Reads and fills become read and write events. Each count is multiplied by the
number of *utilized instances* and divided by the block size, so a component
that sits idle in a layer is charged only for leakage. `Computes` at the `mac`
level becomes MAC operations, charged in the weight-stationary mode that this
mapping uses.

**Level names map to component names.** `=== weights_spad ===` charges the
component named `weights_spad`. If your names are different, pass a
`--stats-map` YAML file. In it, use `levels:` to rename levels and `ignore:`
to skip levels you don't want charged.

## Banked buffers

`shared_glb` is declared the Accelergy way: `depth: 16384, width: 64,
n_banks: 32`. In Accelergy (and in CACTI, which Accelergy uses), `depth ×
width` is the size of the whole buffer (128 KB here), and `n_banks` splits it
into banks. NPUWattch's `mem_depth_per_bank` is the depth of one bank, so the
harness divides the depth by the number of banks. This note shows what it did:

```
shared_glb (sram): depth 16384 is the Accelergy total over 32 banks → mem_depth_per_bank 512 (128 KB total)
```

The `--tree` label also ends with the resulting capacity (`= 128 KB`). If the
YAML gives `mem_depth_per_bank` directly, NPUWattch uses it as is.

Each bank has its own decoders, and one access event reads or writes one row
(`width` bits) of one bank. Timeloop counts bandwidth in `datawidth` elements,
so `read_bandwidth: 16` on this 8-element row means 2 bank accesses per cycle,
and the stats reader charges each one as a read event. Each event includes the
idle decoders of the other tile groups in the same bank. Banks that aren't
being accessed are clock-gated and use only leakage power. Ports
(`n_rw_ports`, `n_rd_ports`, `n_wr_ports`) are per bank, so a 16-bank buffer
with one port per bank is `n_banks: 16, n_rw_ports: 1`.
`tests/fixtures/timeloop/banked_wbuf/` has a small example: a 32 KB weight
buffer, 16 banks × 2 KB × 256 bits, read at 16 words per cycle.

**Logic between the banks.** If each bank feeds its consumer directly, there's
nothing to add. If several banks share fewer output ports, the read-data mux
(or crossbar) is real hardware that Timeloop doesn't see. Declare it in the
YAML the way the RTL has it (`class: mux`, `num_inputs: 16`,
`datawidth: 256`, named `wbuf_rd_mux[0..3]` for four 16:1 muxes), and bind it
to the buffer's read events in the stats map:

```yaml
levels:
  wbuf:
    read: [wbuf, wbuf_rd_mux]   # every word read also traverses one mux
    write: wbuf
```

Each listed component is charged the level's access count for that event. The
logic estimator prices the mux, and it shows up as its own line.
`arch_mux.yaml` and `stats_map_mux.yaml` in the same fixture folder show how
this works.

## One window per layer

`--stats stats/` is a directory, so NPUWattch makes one report window per
file, sorted by filename. That's why the files have the `01_`…`08_` prefixes.
The window label is the filename, so the console table shows `01_conv1`,
`02_conv2`, and so on. `--stats-mode aggregate` combines them into a single
window instead.

## Messages you'll see, and why

The run prints no warnings.

- `no port count declared — assuming a single shared read-or-write port`: a
  buffer without `n_rw_ports`, `n_rd_ports`, or `n_wr_ports` gets one port.
  NPUWattch checks this port count against the bandwidth the mapping needs.
  `psum_spad` reads a partial sum and writes the updated value in the same
  cycle, so one shared port isn't enough. That's why `arch.yaml` declares
  `n_rd_ports: 1` and `n_wr_ports: 1` for `psum_spad` (see "How the sample
  data was made"). If you remove these two lines, the run prints this warning:
  `psum_spad (regfile): bandwidth 2 words/cycle needs 2 accesses/cycle, more
  than 1 bank(s) × 1 port(s) = 1`.
- `user component 'example_68000_cpu_core' (user_components.yaml): parsed, but
  not used`: for custom blocks, such as control logic or a CPU core, you
  provide the area and the energy of each action in a user component library.
  Here that's `user_components.yaml` next to `arch.yaml`
  (`--user-components my_lib.yaml` picks a different file). The file has one
  example entry that this design doesn't use, so the run prints this reminder.
  It doesn't affect the result.
- `compound component 'counter' (compound_components.yaml): parsed, but not
  used`: a compound component maps one Accelergy class to several NPUWattch
  primitives (here, `counter` is an adder plus a register). NPUWattch reads
  `compound_components.yaml` and `projection.yaml` from the folder with
  `arch.yaml` automatically (`--compound-components` and `--projection`
  select other files). `arch.yaml` has no `counter`, so this is also just a
  reminder. To see it in action, add a component with `class: counter` and
  `attributes: {width: 12}`. It will show up as two rows.
- `DRAM (DRAM type LPDDR4): 8 pJ/bit from the shipped table lpddr4.yml`:
  `arch.yaml` declares an LPDDR4 DRAM, so NPUWattch reads the energy constants
  from its LPDDR4 table. DRAM is priced with table constants instead of a
  trained model, and it's marked `const` in the summary. A DRAM with no `type`
  uses the LPDDR4 table and prints a warning. Use `--energy-table` to supply
  your own table.
- No message for `mac`: Accelergy's `intmac` class declares
  `multiplier_width: 8` and `adder_width: 16`. NPUWattch uses these as the
  operand width and the accumulator width of its `intmac` primitive. If you
  remove them, the run prints the warning `no operand width declared — assuming
  8 bits`.
- `the description declares technology 65nm but the run is evaluated at 7nm`:
  the `technology:` attribute in an Accelergy file is only a label. NPUWattch
  models the node you pass with `--node`.

## How the sample data was made

The architecture is the `eyeriss_like` design from
[timeloop-accelergy-exercises](https://github.com/Accelergy-Project/timeloop-accelergy-exercises)
(`workspace/example_designs/example_designs/eyeriss_like/arch.yaml`), with one
change: we added two lines to the `psum_spad` attributes, `n_rd_ports: 1` and
`n_wr_ports: 1`. Timeloop doesn't use these attributes, so `timeloop-mapper`
gives the same stats with the changed file and with the original.

The stats files come from running `timeloop-mapper` once per AlexNet layer on
that architecture, with the layer shapes that come with the same exercises
(`layer_shapes/alexnet/0.yaml` … `7.yaml`):

| File | Layer | Shape |
| --- | --- | --- |
| `01_conv1` | conv1 | C=3, M=64, P=Q=55, R=S=11, stride 4 |
| `02_conv2` | conv2 | C=64, M=192, P=Q=27, R=S=5 |
| `03_conv3` | conv3 | C=192, M=384, P=Q=13, R=S=3 |
| `04_conv4` | conv4 | C=384, M=256, P=Q=13, R=S=3 |
| `05_conv5` | conv5 | C=256, M=256, P=Q=13, R=S=3 |
| `06_fc6` | fc6 | C=9216, M=4096 |
| `07_fc7` | fc7 | C=4096, M=4096 |
| `08_fc8` | fc8 | C=4096, M=1000 |

Each mapper run takes about 25 seconds. The eight runs produced the 8 stats
files in `alexnet/stats/`, which are unedited.
