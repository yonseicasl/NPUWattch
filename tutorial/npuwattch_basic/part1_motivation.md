# Part 1 — Why NPUWattch, and how it works

This part is a short read. It explains the problem NPUWattch solves and the
method behind it. The details are in the HPCA 2026 paper, listed at the end.

## 1. The problem

When you evaluate a new accelerator design, you need its power, area, and
timing (PAT) long before the RTL exists. The usual tools (Aladdin, Accelergy
with CACTI, McPAT, and their relatives) answer this question with analytical
equations and lookup tables. These tools were calibrated on a small set of
reference circuits at an older technology node, usually 40 or 45 nm. To give a
number for a newer node, they multiply by a **technology scaling factor**. To
give a number for a larger or differently shaped design, they interpolate the
table.

This approach has served architecture research well, but it has three limits
that get worse as designs grow and nodes shrink:

1. **One scaling factor doesn't fit all designs.** We built the same set of
   benchmark circuits at 45, 32, 20, 16, 10, 7, and 5 nm and measured how much
   energy each one really saved. The measured factors spread widely from
   design to design, and the single published factor sits below almost all of
   them. Wire load, clock-tree size, and cell mix don't scale the same way for
   a register file as for a multiplier.
2. **Design scaling is nonlinear.** A floating-point multiplier's energy and
   area don't grow linearly with its bit width, and two formats with the same
   width (for example, E2M3 and E3M2) have different costs. A table built from
   one FP32 design can't express this.
3. **Mixed models don't add up.** Most frameworks price logic with one model
   and SRAM with another, each calibrated under different conditions. When
   you put them together, the relative shares in the breakdown are wrong even
   when each total looks reasonable. On a published accelerator module with a
   128 KB buffer, this combination underestimated the SRAM energy by more than
   40% and its area by about a third.

An accelerator breakdown that places the energy in the wrong component sends
a design study in the wrong direction. This is the problem NPUWattch targets.

## 2. The method

NPUWattch replaces the equation-and-table layer with **neural network
regressors trained on post-layout measurements**. The method has three steps.
The first two happen once, offline, in our lab. You only use the third.

### Step 1: one set of technology libraries, 65 nm to 2 nm

We developed our own technology libraries for every node NPUWattch supports:
planar CMOS above 20 nm, FinFET from 20 nm to 5 nm, nanosheet at 3 nm, and
forksheet at 2 nm. Each library has transistor models, design rules, a
standard-cell library, and an SRAM compiler. All of them come from the same
transistor model and the same design rules, so a logic block and an SRAM
macro at 7 nm are characterized under the same conditions. That consistency
is what makes a breakdown trustworthy.

### Step 2: datasets from full physical implementation

For each component type, we wrote a parameterized RTL design (bit widths,
depths, port counts, pipeline stages, and so on) and swept the parameters
across all nodes. Every point in the sweep goes through the complete
back-end flow: synthesis, place and route, parasitic extraction, and power
sign-off on the extracted netlist. SRAM instances go through the memory
compiler, LVS, parasitic extraction, and transient SPICE simulation. The
result for every point is a row of measured values: dynamic energy per
operation, leakage, area, and critical-path delay.

Two features are recorded alongside the design parameters: the **sequential
cell count ratio (SCR)** and the **sequential cell area ratio (SAR)**. They
describe the mix of flip-flops and combinational gates in the design. These
two numbers are available right after synthesis, and they explain a large
part of how a design's cost moves across nodes.

### Step 3: one small model per component and metric

Each component type (MAC, multiplier, adder, register file, FIFO, crossbar,
SRAM, and others) gets its own small multilayer perceptron for each metric
(energy, area, timing). The models are small on purpose: training takes
minutes on a desktop CPU, and inference is instant. The design datasets are
long-tailed, so the training uses an **adaptive loss** that reweights rare
design points by their SCR/SAR histogram bins. Without this, the models
would fit the common small designs and drift on the large ones.

At runtime, NPUWattch reads your architecture description, maps each
component to its model, asks the model for the per-operation energy, leakage,
area, and delay at your node and operating point, and multiplies by the
activity your simulator recorded. Part 2 walks through that path.

## 3. What you get, and what you don't

- **Accuracy.** Against the post-layout results of five open-source
  accelerators (FEATHER, Flex-DPE, Gemmini, MAERI, NVDLA), NPUWattch's
  average estimation error is 2.7%, and the component breakdowns keep the
  right ordering.
- **Scope.** NPUWattch models the datapath and memory of an accelerator: MAC
  arrays, vector units, register files, buffers, NoC, and DRAM. Control
  processors, host interfaces, and I/O are outside the trained set. You can
  price them yourself with a user component (Part 3).
- **Nodes.** The released models are characterized at 5, 7, 10, 16, and
  20 nm. Nodes between them are interpolated. Nodes outside that range are
  extrapolated, and NPUWattch tells you when it does so.
- **No EDA tools at your end.** The flow in Step 2 is ours. You never run
  synthesis, SPICE, or a memory compiler to use NPUWattch.

## Reference

S. Kim, M. Kim, C. Park, H. Park, S. Kim, T. Song, and W. J. Song,
"NPUWattch: ML-based Power, Area, and Timing Modeling for Neural
Accelerators," *IEEE International Symposium on High-Performance Computer
Architecture (HPCA)*, Jan. 2026.
