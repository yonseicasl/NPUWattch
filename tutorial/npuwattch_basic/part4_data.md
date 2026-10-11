# Part 4 — Bringing your own data

Part 2 explained where NPUWattch's numbers come from. This part is the
practical one. It covers the ways to put your own data into a run, from
the easiest to the most involved, and it ends with one exercise.

## 1. Five ways in

These are listed in order of effort. Most users only need the first one.

### 1.1 A user component: supply the cost of one block yourself

This is the path for anything NPUWattch has no model for: a control
processor, a post-processing unit, a compression engine, an interface
block. You supply the area, the leakage, and the energy of each action, at
the node you measured or estimated them for. NPUWattch uses them as given
and reports them in the `model` column as `user`.

```yaml
user_components:
  nvdla_sdp:
    reference: {node: 7nm, corner: TT, voltage_V: 0.75, temperature_C: 25.0, clock_MHz: 800.0}
    design_class: compute          # register | compute
    area_um2: 1942.0               # per instance
    leak_power_mW: 0.01159
    actions:
      idle:    {energy_pJ: 9.09}
      process: {energy_pJ: 15.65}
```

- **The entry name is the class name.** A component in a native description
  with `class: nvdla_sdp`, or a Timeloop component whose class is
  `nvdla_sdp`, uses this entry. In a Timeloop architecture you can also
  keep the Accelergy class and add the attribute `user_component: nvdla_sdp`
  to the component. That is how the NVDLA-like tutorial design attaches
  its SDP.
- **An action name is an activity mode.** A row in the activity table
  with `mode: process` charges 15.65 pJ per count. NPUWattch checks every
  action name against the entry, so a typo is caught before anything is
  computed.
- **Where do the numbers come from?** From whatever source you trust:
  your own RTL run through synthesis and place and route, a vendor
  datasheet, or a published measurement. The NVDLA SDP entry above was
  made by running the SDP RTL through the same flow as our primitives.
- **The reference node.** State the node the numbers belong to. If the run
  node is different, NPUWattch warns. We are preparing to support scaling
  user components across nodes in a future release.
  <!-- Internal note: the user-component node scaler is a stub today
  (scale() returns the reference values unchanged); the paper's SCR/SAR
  preset sub-engine is planned. Keep this out of the visible text. -->

**Giving it activity.** The simulator has no counter for a block it
doesn't model, so you tell NPUWattch how to count its actions:

- With Timeloop, a stats map fans an existing level out to it. The NVDLA
  example charges eight `process` actions per DRAM write, because the SDP
  processes every output element on its way out:

  ```yaml
  levels:
    DRAM:
      read: DRAM
      write: [DRAM, {sdp: {count: 8, action: process}}]
  ```

- With a native activity table, add rows with the component name, the
  action as the `mode`, and the count.

The exercise at the end of this part does the second one.

### 1.2 Your own DRAM table

The DRAM cost comes from a small table: energy per row activation, energy
per transferred bit, and an optional refresh term. The tutorial ships
tables for LPDDR4, DDR3, GDDR5, HBM2, and HMC with their citations. If you
have your own numbers (from a datasheet or from a DRAM simulator), write
the same table and pass it with `--energy-table`:

```yaml
name: HBM2
offchip_dram:
  row_activation_pj: 909.0
  transfer_pj_per_bit: {dram: 1.51, io: 1.17, phy: 0.80}
  refresh_pj_per_refab: 58176.0
```

The flag works for both harnesses. In a native description, the same
values can be written directly as attributes of an `hbm` component, and the
per-bit cost of a `d2dlink` component is its `net_energy_per_bit_pJ`
attribute.

### 1.3 A compound: describe a block as a set of primitives

If your block is really made of things NPUWattch already models, you
don't have to cost it by hand. Write it as a compound in
`compound_components.yaml`, and the trained models cost every element. An accumulator with scaling is
an `intmul` plus an `intadd` plus a `regfile`. A vector lane is an `fpadd`,
a `regfile`, and a small `sram`. Part 3, §3.1 has the schema. The energy
of each element is then charged from the projection, so the `model`
column still says `cal`.

### 1.4 A simulator without a harness: the native files

Any tool that can report access counts per block can drive NPUWattch. Write
the two files from Part 3, §2: a description with one component per block,
and an activity table with one row per (window, block, mode). The quickest
way to learn the formats is to run one of the tutorial examples with
`-o native/` and edit what it wrote. The activity rows can be produced by a
few lines of script from your simulator's statistics output.

### 1.5 Retraining, and adding a primitive

The training scripts ship with the package, and they accept a dataset
directory in the same CSV layout as ours. If you have post-layout rows for
one of the existing primitives at one of the characterized nodes, you can
retrain that primitive's models on your rows. Adding a **new** primitive is
a larger job: it needs an RTL generator, the sweep on licensed EDA tools,
and the registration of its parameters and stimulus modes in the estimator.
If you need a primitive that isn't in the list, open an issue. Once it is
in the released set, everyone benefits from it.

## 2. Try it: add a block to a native run

Start from the files that Part 3, Exercise B wrote with `-o native/`.

1. Open `native/description.yaml`. Add a `user_components:` block with the
   `nvdla_sdp` entry from §1.1, and add one component to the list:

   ```yaml
   - {name: post.sdp, class: nvdla_sdp, count: 128}
   ```

2. Open `native/activity.csv`. Add one row to the kernel's window that
   charges a `process` action per output element. For the 1024³ matmul,
   that is 1 048 576 elements:

   ```
   <window>,<cycle_start>,<cycle_end>,post.sdp,op,process,1048576
   ```

   Copy the window name and cycle range from the existing rows, and keep
   the `__meta__` row as the last line of the file.

3. Run it:

   ```bash
   npuwattch -d native/description.yaml -l native/activity.csv
   ```

In the summary, `post.sdp` appears with `user` in the `model` column, its
area is 128 times the entry's area, and its energy is the count times
15.65 pJ plus leakage for the window. Everything else is unchanged. Now
remove the activity row and run again: the block keeps its area and
leakage and loses its dynamic energy, which is what an unused block should
do.
