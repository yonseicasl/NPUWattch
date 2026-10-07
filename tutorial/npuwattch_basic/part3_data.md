# Part 3 — Where the numbers come from, and how to add your own

The first half of this part is a short description of how the training data
behind NPUWattch is made. You don't run any of it. It is here so you know
what a "calibrated" number means. The second half is the practical part:
the ways to put your own data into a run, from the easiest to the most
involved.

## 1. How the datasets are made

### 1.1 Logic

Each logic primitive (`intmac`, `fpadd`, `regfile`, `crossbar`, and the
rest) is a parameterized RTL generator with a self-checking testbench. A
**sweep** is a grid over the generator's parameters, the technology nodes,
and the clock. One point of the grid is one **job**, for example an
`intmac` with 8-bit operands, a 32-bit accumulator, and 2 pipeline stages,
at 7 nm, at a 1 ns clock.

Every job goes through the full back-end flow with commercial EDA tools:

1. **Synthesis.** The cell report gives the combinational and sequential
   cell counts and areas, from which SCR and SAR are computed (Part 1).
2. **Place and route**, then **parasitic extraction** of the routed design.
3. **Gate-level simulation** on the extracted netlist. After a functional
   self-check, the testbench drives the design with one stimulus pattern per
   **stimulus mode** and records the switching activity of every net.
   Modes include random operands, a weight-stationary MAC that holds one
   operand (`hold_b`), sparse operands, a clocked idle block, and the read
   and write patterns of a storage element.
4. **Power sign-off** on the extracted netlist, once per stimulus mode with
   its recorded activity.

The result for one job is one row per stimulus mode: the design parameters,
node, clock, SCR and SAR, the post-layout area, the minimum clock period,
the leakage power, and the dynamic energy per cycle in that mode. These
rows, one CSV per primitive, are the logic dataset. The stimulus modes in
the dataset are exactly the `mode` values you can use in an activity table
(Part 2, §2.2).

Choosing the clock is part of the sweep. A probe synthesis first finds the
fastest clock each configuration can reach at each node, and the sweep then
runs each point at a tight and a relaxed clock, so the dataset covers the
timing-driven region as well as the relaxed one.

### 1.2 SRAM

SRAM is measured, not synthesized. Our memory compiler generates the layout
of a bit-cell array with its write drivers, column circuits, and sense
amplifiers for a grid of row and column counts at each node. Each instance
goes through layout-versus-schematic checking, parasitic extraction, and
transient SPICE simulation with measurement windows around each operation.
The dataset rows carry the read and write energies for the different data
patterns, the leakage, the access timings, and the area. The decoders are
digital logic and go through the logic flow above.

Banks and total capacity are not swept. At run time, the SRAM estimator
tiles the measured array shapes into the bank count, depth, and width you
asked for, and charges the decoders of each bank with it.

### 1.3 Training

One small multilayer perceptron is trained per (primitive, metric): energy,
leakage, timing, and area for each of the 14 logic primitives, plus the
four SRAM models. The inputs are the log of the design parameters, the
clock, a one-hot node, and, for energy and leakage, the stimulus mode. The
targets are log values. The loss is the histogram-weighted L1 from Part 1.
Training runs on a CPU in minutes. Each trained model is shipped with its
scalers and with the **envelope** of the data it was trained on: the range
of each parameter and of the clock. When a run asks for a value outside the
envelope, the warning you see on the console comes from that file.

Each release reports, per model, the validation error against held-out
designs. The acceptance target is 5% mean absolute percentage error for a
typical model and 10% at most.

## 2. Bringing your own data

There are five ways in, in order of effort. Most users need only the first.

### 2.1 A user component: price one block yourself

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
- **An action name is an activity mode.** A row in the activity table with
  `mode: process` charges 15.65 pJ per count. An action the entry does not
  define is an error, not a default.
- **Where do the numbers come from?** From whatever you trust: your own RTL
  through synthesis and place and route, a vendor datasheet, or a published
  measurement. The NVDLA SDP entry above was made by running the SDP RTL
  through the same flow as our primitives.
- **The reference node.** State the node the numbers belong to. If the run
  node is different, NPUWattch warns. We are preparing to support scaling
  user components across nodes in a future release.
  <!-- Internal note: the user-component node scaler is a stub today
  (scale() returns the reference values unchanged); the paper's SCR/SAR
  preset sub-engine is planned. Keep this out of the visible text. -->

**Giving it activity.** The simulator doesn't know the block exists, so
you tell NPUWattch how to count its actions:

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

### 2.2 Your own DRAM table

The DRAM is priced from a small table: energy per row activation, energy
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

### 2.3 A compound: describe a block as a set of primitives

If your block is really made of things NPUWattch already models, don't
price it by hand. Write it as a compound in `compound_components.yaml`
and the trained models price every element. An accumulator with scaling is
an `intmul` plus an `intadd` plus a `regfile`. A vector lane is an `fpadd`,
a `regfile`, and a small `sram`. Part 2, §3.1 has the schema. The energy
of each element is then charged from the projection, so the `model`
column still says `cal`.

### 2.4 A simulator without a harness: the native files

Any tool that can report access counts per block can drive NPUWattch. Write
the two files from Part 2, §2: a description with one component per block,
and an activity table with one row per (window, block, mode). The quickest
way to learn the formats is to run one of the tutorial examples with
`-o native/` and edit what it wrote. The activity rows can be produced by a
few lines of script from your simulator's statistics output.

### 2.5 Retraining, and adding a primitive

The training scripts ship with the package, and they accept a dataset
directory in the same CSV layout as ours. If you have post-layout rows for
one of the existing primitives at one of the characterized nodes, you can
retrain that primitive's models on your rows. Adding a **new** primitive is
a larger job: it needs an RTL generator, the sweep on licensed EDA tools,
and the registration of its parameters and stimulus modes in the estimator.
If you need a primitive that isn't in the list, open an issue. It is more
useful to everyone if it lands in the released set.

<!-- Internal note: a custom estimator plugin is also possible (a package
under npuwattch_estimators/ with an ESTIMATOR_SPEC literal and a
unit-cost provider that answers its own primitives and delegates the rest).
Not documented in the visible text; it is an internal convention, not a
supported interface, in v1.0. -->

## 3. Try it: add a block to a native run

Start from the files that Part 2, Exercise B wrote with `-o native/`.

1. Open `native/description.yaml`. Add a `user_components:` block with the
   `nvdla_sdp` entry from §2.1, and add one component to the list:

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
