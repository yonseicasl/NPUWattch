# Part 2 — How NPUWattch works: the method

This part follows the second half of our HPCA 2026 talk. It explains how
the technology libraries, the datasets, and the models behind NPUWattch
are made, and what accuracy you can expect. You don't run any of this
yourself. It is here so you know what a "calibrated" number means when
you see one in a report.

## 1. The framework at a glance

NPUWattch is a drop-in replacement for the rule-based layer of a
conventional PAT tool. It takes three inputs: an **architectural
configuration** that lists the blocks in the design and their sizes, an
optional **custom component library** for blocks you cost yourself, and
an optional **cycle-level activity log** from a simulator. Inside, a set
of **neural estimators**, one per component type (multiplier, adder,
register file, SRAM, and so on), predicts the power, area, and timing of
each block. The per-component results are added up into an
accelerator-level PAT report. Part 3 walks through this path file by
file.

The accuracy of the estimates comes from the data the estimators were
trained on: carefully curated post-layout measurements, produced by a
three-stage development pipeline.

## 2. The development pipeline

The pipeline has three stages. The first two are done once, in our lab.
The third produces the models that ship with the tool.

1. **Technology library development.** One consistent design workflow for
   both logic and SRAM, giving technology libraries from 65 nm down to
   2 nm.
2. **Dataset construction.** Component selection, feature selection, and
   simulation data collection: a sweep of design parameters across the
   nodes, with the post-layout cost of every point.
3. **Neural network model training.** Network organization, an adaptive
   loss function, and feature engineering, trained on that dataset.

### Stage 1: one set of technology libraries, 65 nm to 2 nm

We developed our own technology libraries for every node NPUWattch
supports: planar CMOS above 20 nm, FinFET from 20 nm to 5 nm, nanosheet
at 3 nm, and forksheet at 2 nm. Each library includes transistor models,
design rules, a standard-cell library, and an SRAM compiler. Within a
node, everything comes from the same transistor model and the same design
rules, so a logic block and an SRAM macro at 7 nm are characterized under
the same conditions. That consistency is what makes a breakdown
trustworthy.

### Stage 2: datasets from full physical implementation

**Logic.** Each logic primitive (`intmac`, `fpadd`, `regfile`, `crossbar`,
and the rest) is a parameterized RTL generator with a self-checking
testbench. A sweep is a grid over the generator's parameters, the
technology nodes, and the clock. One point on the grid is one job: for
example, an `intmac` with 8-bit operands, a 32-bit accumulator, and 2
pipeline stages, at 7 nm, with a 1 ns clock. Every job goes through the
complete back-end flow with commercial EDA tools:

1. **Synthesis.** The cell report gives the combinational and sequential
   cell counts and areas.
2. **Place and route**, then **parasitic extraction** of the routed design.
3. **Gate-level simulation** on the extracted netlist. After a functional
   self-check, the testbench drives the design with one input pattern per
   **stimulus mode** and records how often every net switches. The modes
   include random operands, a weight-stationary MAC that holds one operand
   (`hold_b`), sparse operands, a clocked idle block, and the read and
   write patterns of a storage element.
4. **Power analysis** on the extracted netlist, once per stimulus mode.

The result for one job is one row per stimulus mode: the design
parameters, node, clock, post-layout area, minimum clock period, leakage
power, and dynamic energy per cycle in that mode. The stimulus modes in
the dataset are the same modes you can name in an activity table later
(Part 3). Choosing the clock is part of the sweep. A first synthesis pass
finds the fastest clock each configuration can reach at each node, and
the sweep then runs each point at a tight clock and at a relaxed clock.

**SRAM.** SRAM is simulated at the circuit level, not synthesized. The
memory compiler generates the layout of a bit-cell array with its write
drivers, column circuits, and sense amplifiers for a grid of row and
column counts at each node. Each instance goes through
layout-versus-schematic checking, parasitic extraction, and transient
SPICE simulation, with a measurement window around each operation. The
rows record the read and write energies for the different data patterns,
the leakage, the access timings, and the area. The decoders are digital
logic and go through the logic flow. At run time, the SRAM estimator
tiles these measured array shapes into the bank count, depth, and width
you ask for.

**Two extra features.** Every logic row also records the **sequential cell
count ratio (SCR)** and the **sequential cell area ratio (SAR)**: the
share of flip-flops among all cells, by count and by area. Both are
available right after synthesis, and they explain a large part of how a
design's cost changes across nodes.

The reason is that the two kinds of cells don't shrink the same way. A
simple gate such as a NAND is a few transistors and short wires, and it
gets almost the full benefit of a smaller node. A flip-flop is a larger
cell with more transistors, and its energy and area shrink by a smaller
factor from one node to the next. A flip-flop also needs a clock network
to drive it, and that network, with its buffers and long wires, scales
worse than the cells it feeds and takes a growing share of the power at
small nodes. So two designs with the same gate count but a different
share of flip-flops scale differently, and a model that only knows the
gate count will miss that. SCR and SAR give the model that share. They
are also the axes along which the training data is rebalanced in
Stage 3.

### Stage 3: one small model per component and metric

Each component type gets its own small multilayer perceptron for each
metric: energy, leakage, timing, and area for each of the 14 logic
primitives, plus four SRAM models. The inputs are the design parameters
(on a log scale), the clock, the node, and, for energy and leakage, the
stimulus mode. The outputs are on a log scale as well. The models are
small on purpose: training takes minutes on a desktop CPU, and a
prediction takes well under a millisecond.

The design datasets are long-tailed, with many small designs and few
large ones, so the training uses an **adaptive loss** that gives more
weight to rare design points based on their SCR and SAR. Without it, the
models would fit the common small designs well and drift on the large
ones.

Each trained model ships with the range of parameters and clocks it was
trained on. When a run asks for a value outside that range, NPUWattch
prints a warning that says so. Each release also reports the validation
error of every model on held-out designs. The target is a mean absolute
percentage error of 5% for a typical model and no more than 10% for any
model.

At run time, NPUWattch reads your architecture description, maps each
component to its model, asks the model for the energy per operation, the
leakage, the area, and the delay at your node, and multiplies by the
activity your simulator recorded. Part 3 walks through that path.

## 3. What the evaluation shows, and what you get

The comparison is done at 45 nm, because that is where the baseline,
Accelergy with the Aladdin tables and the CACTI plug-in, is calibrated.
The ground truth is the post-layout result of five open-source RTL
accelerators (FEATHER, Flex-DPE, Gemmini, MAERI, and NVDLA) built with
the Nangate 45 nm library and OpenRAM. To make sure we were testing
generalization and not memorization, the 45 nm data was left out of
NPUWattch's training for this comparison.

- **Breakdowns.** On the accelerator-level energy breakdown, NPUWattch
  cuts the mean absolute percentage error by 2.5 times compared with
  Accelergy, and it keeps the component ranking right. That includes
  Gemmini, with its large buffer, where Accelergy points at the wrong
  bottleneck.
- **Components.** On individual components, the estimated area is within
  2.7% of the post-layout value on average.
- **Workloads.** On MobileNetV3, ResNet-50, BERT, and Llama-3 across three
  accelerators, the workload-level energy error is 6.3% for NPUWattch and
  68.1% for Accelergy.
- **Scope.** NPUWattch models the datapath and memory of an accelerator:
  MAC arrays, vector units, register files, buffers, NoC, and DRAM. For
  blocks outside that set, such as a control processor or a host
  interface, you can supply your own numbers as a user component
  (Part 4).
- **Nodes.** The released models cover 5, 7, 10, 16, and 20 nm. Nodes in
  between are interpolated. For nodes outside that range, NPUWattch
  extrapolates and tells you that it did. We are preparing to support
  3 nm and 2 nm in a future release.
- **No EDA tools on your side.** The flow in Stage 2 is ours. You never
  run synthesis, SPICE, or a memory compiler to use NPUWattch.

## Reference

S. Kim, M. Kim, C. Park, H. Park, S. Kim, T. Song, and W. J. Song,
"NPUWattch: ML-based Power, Area, and Timing Modeling for Neural
Accelerators," *IEEE International Symposium on High-Performance Computer
Architecture (HPCA)*, Jan. 2026.
