# Part 3 — How NPUWattch is built, and what it reads

This part explains how NPUWattch is put together, at the level you need
to use it with your own simulator runs. It stays out of the source code.
The structure below and the file formats are what you work with, and they
are stable across releases.

The part ends with two short exercises on the `tutorial/timeloop` and
`tutorial/pytorchsim` examples.

## 1. One run, end to end

Every NPUWattch run follows the same path, whatever the input is:

```
                                    ┌──────────────────┐          NPUWATTCH ARTIFACTS
 your simulator's files *1   ─────► │     HARNESS      │ ──► description.yaml  (what the hardware is)
                                    │    pytorchsim    │ ──► activity.csv      (what it did)
 three definition files      ─────► │     timeloop     │ ──► warnings, notes, instance tree
 (compound_components.yaml,         └──────────────────┘
  projection.yaml,                           │
  user_components.yaml)                      ▼
                                    ┌──────────────────┐     ┌──────────────────────────┐
                                    │  NPUWATTCH CORE  │     │        ESTIMATORS        │
                                    │  per component:  │     │  logic models            │
                                    │  energy/access,  │ ◄── │  SRAM model              │
                                    │  leakage, area,  │     │  DRAM / link constants   │
                                    │  critical path   │     │  user components scaler  │
                                    └──────────────────┘     └──────────────────────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │   AGGREGATION    │  count × energy, leakage × time
                                    └──────────────────┘
                                             │
                                             ▼
                                        USER REPORT
                          console table · report.html · report.json

 *1 Currently supports Accelergy v0.4 arch.yaml + Timeloop stats, or a PyTorchSim run folder
```

The key idea is the middle layer. A **harness** turns a simulator's own
files into two plain NPUWattch files: a **description** and an **activity
table**. Everything after that point is the same for every simulator. If
you run with `-o DIR`, NPUWattch writes those two files to disk, and you
can run them again with `npuwattch -d description.yaml -l activity.csv`
without the harness. That is also the path for a simulator that has no
harness yet: write the two files yourself (Part 4).

## 2. The native model: a description and an activity table

### 2.1 `description.yaml`: what the hardware is

A description is a flat list of components. Each component has a name, a
class, a count, and the attributes of that class. Technology and clock are
set once at the top, not per component.

```yaml
npuwattch:
  version: 1.0
  technology: {node: 7nm, transistor: hp, corner: TT, voltage_offset_V: 0.0, temperature_C: 25}
  clock: {frequency_MHz: 1000}
  components:
    - name: pe_array.mac
      class: intmac
      count: 256
      attributes: {data_width_a: 8, data_width_b: 8, data_width_out: 32, data_width_acc: 32, pipeline_stages: 2}
    - name: glb
      class: sram
      count: 1
      attributes: {data_width: 64, mem_depth_per_bank: 512, mem_banks: 32, mem_rw_ports: 1}
```

- **`name`** is free text. Dots group components into a tree, which is what
  `--tree` prints and what the report uses for its breakdowns.
- **`class`** is the name of a primitive (the table below), a user component
  from your library, or a short alias (`register_file`, `xbar`, `mux`).
- **`count`** is the number of identical instances. It sets area and
  leakage. It does not multiply the activity, because the activity counts
  are already totals over all instances.
- **`attributes`** use one fixed vocabulary of names. The main ones are
  `data_width`, `mem_depth_per_bank`, `mem_banks`, `mem_r_ports`,
  `mem_w_ports`, `mem_rw_ports`, `net_inputs`, `net_outputs`,
  `exponent_bits`, `mantissa_bits`, and `pipeline_stages`. A harness
  translates a simulator's own spellings into these names.

The primitives that have trained models:

| Family | Primitives | Main attributes |
| --- | --- | --- |
| Integer arithmetic | `intadd`, `intmul`, `intmac` | `data_width_a`, `data_width_b`, `data_width_out`, `data_width_acc` (MAC), `pipeline_stages` |
| Floating-point arithmetic | `fpadd`, `fpmul`, `fpmac` | `exponent_bits`, `mantissa_bits`, `pipeline_stages` |
| Special functions | `fpsfu` | format bits, which functions (exp, trig, hyp, erf, relu), segments, `pipeline_stages` |
| Microscaling | `mxfpmac` | block size, number of blocks, input format |
| Small storage | `regfile`, `fifo` | `data_width`, `mem_depth_per_bank`, port counts |
| Fabric | `simplemux`, `crossbar`, `fattree`, `foldedclos` | `data_width`, `net_inputs`, `net_outputs`, radix, levels |
| SRAM | `sram` | `data_width`, `mem_depth_per_bank`, `mem_banks`, port counts |

Two more classes get their cost from tables rather than models: `hbm` (DRAM, per
bit and per row activation) and `d2dlink` (a die-to-die link, per bit).

### 2.2 `activity.csv`: what the hardware did

The activity table has one row per (window, component, mode):

```
window,cycle_start,cycle_end,component,event,mode,count
conv1,0,638879,pe_array.mac,op,hold_b,163577856
conv1,0,638879,glb,read,read,2211840
conv1,0,638879,glb,write,write,184320
conv2,638880,1215359,pe_array.mac,op,hold_b,...
,,,__meta__,total_cycles,,1215360
```

The last row is not a component. It records the total cycle count of the
run and stays at the end of the file.

- **`window`** is a slice of the run: one layer for Timeloop, one kernel for
  PyTorchSim. The report shows energy per window and the sum.
- **`component`** is a name from the description.
- **`event`** is a label for the reader: `op`, `read`, `write`,
  `transfer`, or `idle`. It has no effect on the energy.
- **`mode`** sets the energy. It names the **stimulus mode** the primitive
  was characterized in: `hold_b` for a weight-stationary MAC, `random` for
  random operands, `read` or `write` for a memory, `idle` for a clocked
  but inactive block, and so on. Each primitive has its own list of
  characterized modes, and NPUWattch checks every row against that list,
  so a typo in a mode name is caught before anything is computed.
- **`count`** is the number of events in that window, summed over all
  instances of the component.

A component with no row in a window is charged leakage for that window
and no dynamic energy. If a run has no activity at all, NPUWattch gives a
**vectorless** estimate instead: one cycle at 25% of random switching,
labeled VECTORLESS in every output.

### 2.3 How a number is made

For each component in each window:

- dynamic energy = Σ over rows of `count × energy per event(class, attributes, node, mode)`
- leakage energy = `count × leakage power × window time`, with window time = cycles ÷ clock
- area = `count × area per instance`

The per-event energy, leakage power, area, and critical-path delay come
from the **providers**. A request for a component goes down a short chain.
The SRAM model answers `sram`, the logic models answer the 14 logic
primitives, your user library answers your own class names, and the tables
answer `hbm` and `d2dlink`. If no provider has a model for a component, the
run stops and names that component, so every number in a report comes
from a model or from data you supplied.

The `model` column in the console summary tells you which provider answered:
`cal` for a trained model, `const` for a table, `user` for your library.

### 2.4 Technology node and operating point

The trained models are characterized at 5, 7, 10, 16, and 20 nm. The node
you ask for is handled like this:

| You ask for | What happens |
| --- | --- |
| A characterized node | The model answers directly |
| A node between two characterized nodes | Log-log interpolation between the two neighbors, with an INFO line |
| A node outside the range, up to half a step beyond it | Extrapolation from the nearest pair, with a WARNING |
| Anything further out | Clamped to the envelope, with a WARNING on the console and in the report |

Corner, voltage offset, and temperature are part of the technology block.
<!-- Internal note: the released logic v2 models are TT/nominal/25 C only;
SRAM scales voltage and temperature analytically and accepts hp/TT only. Not
stated in the visible text per the external-exposure policy. -->

## 3. Harnesses

A harness is a small adapter between one simulator and the native model. It
declares which input files it needs (the CLI flags for a harness are
generated from that declaration), reads them, and returns the description,
the activity rows, the instance tree, and two kinds of messages:

- **WARNING**: the result may be off. NPUWattch assumed a value,
  extrapolated beyond the characterized range, or found inputs that
  disagree with each other.
- **INFO**: a convention or exclusion you should know about, such as a
  counter that is left out on purpose. Nothing is wrong.

Read the warnings before you read the numbers.

### 3.1 The three definition files

Both harnesses read three YAML files from the folder of your run. They
are part of your input, and NPUWattch asks for them if one is missing.

**`compound_components.yaml`** describes hardware that your simulator sees
as one unit but that NPUWattch models as several primitives. A systolic array is
a set of MACs plus weight registers. A vector lane is an ALU plus a register
file plus a scratchpad.

```yaml
systolic_mac:
  elements:
    pe:
      primitive: fpmac
      config: {exponent_bits: 8, mantissa_bits: 7, pipeline_stages: 4}
      count: "lanes*lanes"
    w_reg:
      primitive: regfile
      config: {data_width: 16, mem_depth_per_bank: 1, mem_r_ports: 1, mem_w_ports: 1}
      count: "lanes*lanes"
```

Config values can be numbers or small expressions over symbols the harness
provides (for PyTorchSim, `lanes`, `bitwidth`, and every integer key of the
run configuration; for Timeloop, the integer attributes of the component).
For PyTorchSim, the quoted templates `"{mac_primitive}"` and `"{mac_config}"`
let the PE follow the data type of each compiled kernel instead of being
fixed.

**`projection.yaml`** ties a counter from the simulator to the elements of a
compound, and says which stimulus mode each element is in during that
action:

```yaml
tool: pytorchsim
compounds:
  systolic_mac:
    CustomMatMul:
      count_from: {stat: systolic_active_cycles, scale: "lanes*lanes"}
      elements: {pe: hold_b, w_reg: idle}
```

This entry reads as: for every active cycle of the systolic array, charge
lanes² MAC operations in weight-stationary mode, and charge the weight
registers one idle cycle each. Elements an action does not name are charged
idle, or nothing if the compound declares `default_mode: gated`. Every
(primitive, mode) pair is validated against the list of characterized modes.
A counter with activity that no action uses gives a coverage warning, unless
you list it under `waivers` with a reason.

**`user_components.yaml`** holds blocks that have no trained model: a control
processor, a post-processing unit, a DMA engine from your own RTL. You give
the area, the leakage, and the energy of each action, at a reference node.
Part 4 shows the full entry.

### 3.2 The Timeloop harness

```bash
npuwattch --harness timeloop --arch-yaml arch.yaml --stats stats/ \
          --node 7nm --clock-mhz 1000 --tree --report out/
```

| File | What NPUWattch reads from it |
| --- | --- |
| `arch.yaml` (Accelergy **v0.4**) | Every `!Component`: its `class`, its `attributes`, and its instance count from the `spatial` mesh of the containers above it. Attributes are inherited from the containers. `technology` is recorded and checked against `--node`. |
| `*.stats.txt` (`timeloop-mapper` or `timeloop-model`) | Each `=== level ===` block: scalar reads, fills, updates, and computes, the utilized instances, the block size, and the cycle count. |
| `stats_map.yaml` (optional) | Renames, fan-outs, and ignores for stats levels whose names do not match a component. |

**The v0.4 format only.** NPUWattch reads the Accelergy **v0.4** architecture
format: a `nodes:` list with the YAML tags `!Container`, `!Component`,
`!Parallel`, and `!Hierarchical`, and instance counts given by
`spatial: {meshX, meshY}` on the containers. This is the format the current
Timeloop and Accelergy releases use, and the one in every tutorial design.
If you still have a file in the older v0.3 layout (`subtree`, `local`,
`instances`), convert it to v0.4 first. The Timeloop documentation
describes the mapping.

```yaml
architecture:
  version: 0.4
  nodes:
    - !Container
      name: PE_column
      spatial: {meshX: 14}
    - !Container
      name: PE
      spatial: {meshY: 12}
    - !Component
      name: mac
      class: intmac
      attributes: {datawidth: 8}
```

**Architecture.** The Accelergy class picks the primitive through a
vocabulary: `smartbuffer_SRAM` to `sram`, `smartbuffer_RF` to `regfile`,
`mac` to `intmac` (or `fpmac` when the data type says so), `DRAM` to `hbm`,
`xbar` to `crossbar`. Attribute names are translated the same way: `width`
to `data_width`, `depth` to `mem_depth_per_bank`, `n_banks` to `mem_banks`,
`n_rd_ports` to `mem_r_ports`. Two conventions differ between the tools and
are handled for you, with a note each time: Accelergy's `depth` is the total
over all banks, so it is divided by the bank count; and a buffer that
declares no ports gets one shared read-or-write port, which NPUWattch then
checks against the bandwidth the mapping needs.

```yaml
- !Component
  name: shared_glb
  class: smartbuffer_SRAM
  attributes: {depth: 16384, width: 64, n_banks: 32, datawidth: 8}
```

**Activity.** Per-instance counts are multiplied by the utilized instances
and divided by the block size, so one event is one word of one bank. Reads
become `read` events, fills and updates become `write` events, and
`Computes` at the MAC level become `op` events in the weight-stationary
mode. The level name is matched to a component name, exact first, then by
the last part of a dotted name.

**Windows.** If `--stats` is a directory, each `*.stats.txt` file becomes one
window, in file-name order. Prefix the files `01_`, `02_`, and so on.
`--stats-mode aggregate` sums them into one window instead.

**Stats map.** When a level name is not a component name, or when one access
should charge more than one component, describe it here:

```yaml
levels:
  wbuf:
    read: [wbuf, wbuf_rd_mux]      # every read also goes through one mux
    write: wbuf
  DRAM:
    write: [DRAM, {sdp: {count: 8, action: process}}]   # 8 user-component actions per DRAM write
ignore: [mapper_scratch]
```

**DRAM.** The Accelergy `type` (LPDDR4, DDR3, HBM2, and others) selects a
per-bit cost table. `--energy-table` replaces it with your own.

### 3.3 The PyTorchSim harness

```bash
npuwattch --harness pytorchsim --togsim-dir togsim_results/ --gem5-dir outputs/ \
          --config-yml config.yml --node 7nm --tree --report out/
```

or, from a run root that has these folders, `./run.sh <run_root> [flags]`.
The script finds `togsim_results/`, `outputs/` (or `gem5_outputs/`),
`config.yml`, `booksim2_config/`, and an `energy_tables/*.yml` file, and
adds the right flags.

PyTorchSim has no architecture file. The simulator builds its machine at run
time from a configuration, so NPUWattch rebuilds it from the run's own
output. One TOGSim log is one kernel, and one kernel is one window.

| File | What NPUWattch reads from it |
| --- | --- |
| `togsim_results/*.log`, header | The shape of the machine: cores, systolic arrays per core, VPU lanes and vector width, scratchpad sizes, clock, DRAM channels and request size, NoC type and its BookSim configuration. |
| `togsim_results/*.log`, tail | The activity: active cycles per systolic array, vector-unit active cycles, DMA cycles, DRAM reads and writes in bytes, DRAM command counts (reads, writes, activations, refreshes), and the total execution cycles. |
| `outputs/<hash>/m5out/stats.txt` (gem5) | The counts of the custom instructions: weight pushes, input pushes, result pops, and the special-function vector instructions (exp, erf, tanh, sin, cos). |
| `outputs/<hash>/meta.txt` and the kernel `.mlir` | The operand and accumulator data types of the kernel. They decide whether the PE is an `intmac` or an `fpmac` and with which widths. |
| `config.yml` (optional) | Fills in keys the log header does not have, and cross-checks the rest. One key, `core_spad_size_kb`, is read only by NPUWattch: it sizes the VMEM. |
| `booksim2_config/` (optional) | The network file. Needed only for `anynet` topologies; a `fly` network is fully described in the log. |
| an energy table `.yml` (optional) | The DRAM cost table the run used. Without it, the default HBM2 constants are charged. |

**Architecture.** The compound definitions do the work here. The harness
provides the symbols (`lanes`, `bitwidth`, the integer configuration keys,
and the NoC port and router counts) and the MAC configuration of each
kernel; the compounds in `compound_components.yaml` turn them into PEs,
weight registers, vector lanes, scratchpads, DMA, NoC crossbar, and DRAM
channels. NPUWattch emits one component per physical instance
(`core0.array1.pe`, `core0.vmem`, `noc.xbar`, `dram.chan`), so the tree in
`--tree` matches the machine.

**Activity.** The projection maps each counter to compound elements. The
systolic arrays are charged from their active cycles, the vector unit from
its active cycles, the VMEM from the DRAM traffic that moved through it, the
weight and input registers from the gem5 push and pop counts, the NoC from
the flits implied by the DRAM requests, and the DRAM from its byte and
command counts. Counters that gem5 reports once for the whole kernel are
split between the arrays in proportion to their active cycles, with a
warning that says so.

**What is left out.** The scalar core and its caches, the VCIX
serializer, and DRAM standby power are not included in the totals. The
INFO block of every run lists them, so you always know what the number
covers.

## 4. Reading the result

In the console, from top to bottom:

1. **`--tree`**: the hardware as NPUWattch understood it. Check this
   first. If a component is missing or has the wrong size here, every
   number after it will be off.
2. **WARNING and INFO lines**: every assumption, extrapolation, and
   exclusion.
3. **Per-window energy** and **per-window component energy**: one row per
   layer or kernel.
4. **Energy summary**: totals per component with area and leakage, and the
   `model` column (`cal`, `const`, `user`).
5. **Run totals**: energy, time, average power, area, and energy per
   operation.

`report.html` shows the same data as a single self-contained page with
breakdown charts, the cycle-level energy across windows, the component
table, the instance tree, and a provenance section that lists every input
file and message. `report.json` has the same numbers for scripts.

## 5. Try it

Both exercises use data that ships with the tutorial. There is nothing
to download, and no EDA tool is involved.

**Exercise A — Timeloop, Eyeriss-like, AlexNet.**

```bash
cd tutorial/timeloop/eyeriss_like/alexnet
./run
```

Look for these three things: the `--tree` block with six components and
`[×168]` on the per-PE scratchpads and MAC; the note that `shared_glb`'s
depth was divided across 32 banks; and the eight windows `01_conv1` to
`08_fc8` in the per-window table. Then run it again with
`--stats-mode aggregate` and compare the single-window total to the sum.

Now go to `tutorial/timeloop/nvdla_like`, open `stats_map.yaml`, and run
`cd resnet50 && ./run`. The SDP, a post-processing block Timeloop never
sees, appears in the summary with `user` in the `model` column. It is
charged eight `process` actions per DRAM write through the stats map.

**Exercise B — PyTorchSim, TPU-like, one matmul.**

```bash
cd tutorial/pytorchsim/tpu_like_fp32
./run
```

Look for the rebuilt machine in `--tree` (two arrays of 16 384 fp32 MACs,
128 VPU lanes, a 16 MB VMEM, a 32×32 NoC crossbar, 16 HBM channels), the
warning that splits the kernel-total gem5 counts between the two arrays,
and the INFO list of excluded blocks. Then run `../tpu_like_bf16/run`. The
only file that differs is `compound_components.yaml`, where the PE is fixed
to a bf16 `fpmac`. Compare the two `pe` rows in the summaries.

Finally, add `-o native/` to either run and open `native/description.yaml`
and `native/activity.csv`. These are the two files from §2. Run them
directly:

```bash
npuwattch -d native/description.yaml -l native/activity.csv
```

The totals match the harness run. This is the starting point for Part 4.
