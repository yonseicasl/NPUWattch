# Part 1 — Why NPUWattch: three pitfalls in accelerator modeling

This part covers the motivation. It follows the first half of our HPCA
2026 talk: why we need pre-silicon models of neural accelerators, how
design costs are usually scaled across technology nodes today, and the
three pitfalls in that practice that NPUWattch was built to avoid. Part 2
explains the method.

## 1. Introduction: modeling neural accelerators

Neural accelerators have become one of the main topics in architecture
research. Before any proposal can be compared with another, it has to
answer the same question: what does the design cost in power, area, and
timing (PAT)? A full tape-out flow gives an exact answer, but it is far
too expensive for early design space exploration, where hundreds of
variants are compared and most of them are thrown away.

So designers rely on PAT models such as CACTI, Aladdin, and Accelergy.
These tools trade accuracy for speed by design. A few equations and
lookup tables give a number in milliseconds. That trade made sense when
designs were small and the reference node was close to the target node.
Today, with FinFET and gate-all-around transistors below 10 nm, and with
accelerators that are mostly large arrays and large buffers, rule-based
models no longer have enough detail, and the pre-silicon analysis built
on them becomes inaccurate.

## 2. Background: the common practice for scaling design costs

Advanced nodes are hard to get to in academia. Access to a FinFET or
GAAFET process design kit is limited, so an academic design is usually
built at an older planar node, such as 45 nm, where an open cell library
and PDK exist. To compare the design with a commercial baseline, its
measured cost is then multiplied by a **technology scaling factor** for
the target node, say 10 nm.

The common practice has four steps:

1. Measure the design cost at the old node.
2. Multiply it by a published CMOS scaling factor.
3. Treat the result as the cost at the new node.
4. Compare it with the actual cost at the new node.

Step 4 is where it goes wrong: the two numbers don't match. The scaling
factor came from a planar CMOS circuit, but the new node is a FinFET or
GAAFET process with different transistor geometry, wire resistance, and
parasitics. Scaling a planar design cost to such a node does not work.
The three pitfalls below show why, with measurements.

## 3. Pitfall A: technology scaling factors, one size never fits all

A single scaling factor derived from a small reference circuit does not
give accurate estimates for complex designs at a new node.

To test this, we built a set of benchmark circuits, from small adders
and FIFOs to open-source accelerator blocks, at 45 and 32 nm, and again
at 20, 16, 10, 7, and 5 nm with our own libraries. Dividing the measured
energy at each new node by the measured energy at the old node gives the
**actual** scaling factor of each design. When these factors are plotted
as one box per node pair, they spread widely from design to design, and
the single published factor sits below almost all of them.

The picture has two parts. Scaling from one planar node to another (45
to 32 nm) is not too bad: the spread is narrow and the published factor
is close. Scaling from planar to FinFET is where it breaks down: the
spread widens and the gap to the published factor becomes large. Wire
load, clock-tree size, and the mix of cells don't scale the same way for
a register file as for a multiplier, and no single number can capture
that.

**Takeaway.** A single scaling factor cannot represent design variation,
nor technology scaling to newly emerging process nodes.

## 4. Pitfall B: nonlinearity in design scaling

Traditional analytical and rule-based models fail to capture the
nonlinearity in design scaling. Even identical designs don't scale the
same way at different nodes.

SRAM shows this most clearly. Take an SRAM array and grow its capacity
from a few hundred bytes to a few kilobytes. At 45 nm, the access energy
grows along one curve. At 7 nm, the same series of arrays follows a
different, steeper curve. A rule-based model such as CACTI, calibrated
around the old node, follows the 45 nm curve reasonably well, but it
drifts away from the measured 7 nm curve as the array grows. The gap
between the model and the post-layout result is much larger at the
advanced node.

Logic has the same problem in a different form. A floating-point
multiplier's energy and area don't grow linearly with its bit width, and
two formats with the same width but a different split between exponent
and mantissa have different costs. A table built from one FP32 design
can't express either effect.

**Takeaway.** Traditional rule-based models cannot capture the nonlinearity
in design scaling and in technology scaling.

## 5. Pitfall C: inconsistency in heterogeneous modeling

On a monolithic die, logic and SRAM sit on the same wafer and are built
from the same transistor. A model of that die needs a common calibration
point for both, and in practice that point is the transistor model. Most
frameworks don't have one. They estimate logic with one model and SRAM
with another, each calibrated under different assumptions, and the
combination introduces bias.

We compared the design cost of the open-source accelerator Flex-DPE at
45 nm, as estimated by Accelergy with its Aladdin logic tables and its
CACTI SRAM plug-in, against the post-layout result. The totals look
reasonable, but the breakdowns don't match. The SRAM share is badly
underestimated in both energy and area, and that error distorts the
whole picture. A designer reading the estimate would optimize the wrong
component.

**Takeaway.** Neural accelerators must be modeled with a coherent design
methodology for both logic and SRAM.

## 6. What a better model needs

The three pitfalls lead to three requirements. The model has to learn how
each design scales instead of applying one factor to all of them. It has
to capture nonlinear scaling in both the design parameters and the
technology node. And it has to estimate logic and SRAM from the same
calibration point. Part 2 describes how NPUWattch meets these
requirements.

## Reference

S. Kim, M. Kim, C. Park, H. Park, S. Kim, T. Song, and W. J. Song,
"NPUWattch: ML-based Power, Area, and Timing Modeling for Neural
Accelerators," *IEEE International Symposium on High-Performance Computer
Architecture (HPCA)*, Jan. 2026.
