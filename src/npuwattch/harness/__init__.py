"""NPUWattch simulator harnesses.

Each submodule adapts a specific upstream simulator's output (architecture +
activity) into NPUWattch's internal vocabulary:

- ``pytorchsim`` — PyTorchSim (PSAL-POSTECH) weight-stationary systolic NPU.
- ``timeloop``   — Timeloop/Accelergy (planned).
- ``gem5``       — generic gem5 stats (planned).

A harness owns only its *log readers* and its *definition bundle*
(``<sim>/definitions/{compounds,projections}``), authored by whoever introduces
that simulator's format. Interpreting those definitions into a NPUWattch
description + activity is **core**, not harness: the emitter lives at
``npuwattch.arch_synth`` and the interpreter engine at
``npuwattch.harness.compounds`` (shared by all harnesses).

``registry`` discovers the ``HARNESS_SPEC``-declaring harnesses and runs the one
the CLI's ``--harness`` selects.
"""

from .registry import (
    HarnessError,
    HarnessInfo,
    available_harnesses,
    get_harness,
    run_harness,
)

__all__ = [
    "HarnessError",
    "HarnessInfo",
    "available_harnesses",
    "get_harness",
    "run_harness",
]
