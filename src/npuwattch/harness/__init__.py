"""NPUWattch simulator harnesses.

Each submodule adapts a specific upstream simulator's output (architecture +
activity) into NPUWattch's internal vocabulary:

- ``pytorchsim`` — PyTorchSim (PSAL-POSTECH) weight-stationary systolic NPU.
- ``timeloop``   — Timeloop/Accelergy (planned).
- ``gem5``       — generic gem5 stats (planned).
"""
