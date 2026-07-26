"""Timeloop harness — planned (workstream A).

Parked here so far: the definition bundle (``definitions/projections/
timeloop.yaml`` maps Timeloop's coarse ``Computes`` onto the same ``hold_b``
compute state PyTorchSim uses — the stim_mode is a hardware property, and that
shared axis is the Timeloop↔PyTorchSim join) and the **instance-hierarchy tree
builder** (``tree.py`` — builders are harness-owned; the Accelergy description
path this harness will absorb declares its hierarchy in the YAML, and the
CLI's ``--tree`` renders it through the shared ``report.tree`` renderers). The
compound the projection targets (``systolic_mac``) is shipped with the
PyTorchSim harness for now and will be added here (or promoted to a shared
location) when the Timeloop harness lands.

**Design commitment (user decision 2026-07-21): the declared hierarchy is the
energy-accounting skeleton, not just a view.** When this harness's ingest
lands, every component the description declares keeps its own identity — its
own energy/area/leakage row — exactly as the flatten+estimate path does today.
Collapsing declared components into a few compound-level buckets ("just PE")
would defeat fine-grained measurement and is not allowed. The *tree display*
on the other hand is optional by contract: if it cannot be built, print a
WARNING and continue — accounting is never affected.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["DEFINITIONS_DIR"]

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
