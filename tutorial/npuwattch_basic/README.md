# NPUWattch basics

A short introduction to NPUWattch in three parts. Read it before the
`timeloop/` and `pytorchsim/` examples, or alongside them: the exercises in
Part 2 and Part 3 use those examples as their data.

| Part | What it covers | Time |
| --- | --- | --- |
| [Part 1 — Why NPUWattch, and how it works](part1_motivation.md) | The limits of scaling factors and lookup tables; technology libraries, post-layout datasets, and per-component models | 10 min read |
| [Part 2 — How NPUWattch is built, and what it reads](part2_structure.md) | The run from input to report; the native description and activity table; the estimators; the Timeloop and PyTorchSim harnesses and every file they read; two exercises | 25 min |
| [Part 3 — Where the numbers come from, and how to add your own](part3_data.md) | How the logic and SRAM datasets are made; user components, DRAM tables, compounds, native files, retraining; one exercise | 15 min |

The parts describe NPUWattch at the level of its files and its flow, not its
source code. The file formats and the command lines are stable across
releases. Where the text names a flag or a file, `npuwattch --help` and the
example folders are the reference.

## Before you start

```bash
cd NPUWattch
pip install -e .
npuwattch --version
```

The exercises need nothing else: no simulator, no EDA tool, no GPU. Every
input they use is in `tutorial/timeloop/` and `tutorial/pytorchsim/`.
