# NPUWattch basics

A short introduction to NPUWattch in four parts. Parts 1 and 2 are the
talk: why NPUWattch exists and how it was built. Parts 3 and 4 are the
hands-on: what a run reads, and how to bring your own data. Read them
before the `timeloop/` and `pytorchsim/` examples, or alongside them: the
exercises in Parts 3 and 4 use those examples as their data.

| Part | What it covers | Time |
| --- | --- | --- |
| [Part 1 — Why NPUWattch: three pitfalls in accelerator modeling](part1_motivation.md) | Why pre-silicon PAT models are needed, how design costs are scaled today, and the three pitfalls of that practice | 8 min read |
| [Part 2 — How NPUWattch works: the method](part2_method.md) | The framework, the three-stage pipeline (technology libraries, post-layout datasets, per-component models), and the evaluation | 12 min read |
| [Part 3 — How NPUWattch is built, and what it reads](part3_structure.md) | The run from input to report; the native description and activity table; the estimators; the Timeloop and PyTorchSim harnesses and every file they read; two exercises | 25 min |
| [Part 4 — Bringing your own data](part4_data.md) | User components, your own DRAM table, compounds, native files for any simulator, retraining; one exercise | 12 min |

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
