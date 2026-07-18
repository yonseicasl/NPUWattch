"""Timeloop harness — planned (workstream A).

Only the definition bundle is parked here so far: ``definitions/projections/
timeloop.yaml`` maps Timeloop's coarse ``Computes`` onto the same ``hold_b``
compute state PyTorchSim uses (the stim_mode is a hardware property — that shared
axis is the Timeloop↔PyTorchSim join). The compound this projection targets
(``systolic_mac``) is shipped with the PyTorchSim harness for now and will be
added here (or promoted to a shared location) when the Timeloop harness lands.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["DEFINITIONS_DIR"]

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
