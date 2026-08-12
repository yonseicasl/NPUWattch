"""Timeloop/Accelergy harness.

Owns what a harness owns: reading that toolchain's file format and translating
its vocabulary into ours.

* :mod:`.ingest` — an Accelergy v0.4 architecture YAML → a native §3.1
  description + activity. **This absorbed the console's legacy Accelergy path
  (2026-08-12)**: the same input now runs through the §6 core (v2 logic MLPs +
  the SRAM estimator, window accounting, ``--report``) instead of the old
  per-component plugin calls, which is why ``src/estimators/`` no longer carries
  the prototype-era ``adder``/``crossbar``/``regfile``/``custom`` directories.
* :mod:`.vocabulary` — Accelergy ``class``/``attributes`` → NPUWattch primitives
  and canonical attribute names.
* :mod:`.tree` — the declared-hierarchy view for ``--tree`` (builders are
  harness-owned; rendered through the shared ``report.tree`` renderers).
* ``definitions/projections/timeloop.yaml`` — maps Timeloop's coarse ``Computes``
  onto the same ``hold_b`` compute state PyTorchSim uses (the stim_mode is a
  hardware property, and that shared axis is the Timeloop↔PyTorchSim join).

**Still ahead (workstream A): mapping-driven activity.** The projection above is
parked, not wired — no Timeloop stats reader exists yet, so a run ingested here
is a VECTORLESS estimate (25 % of random switching, labeled as such). Wiring the
stats file in changes only :mod:`.ingest`'s activity half; the description half
and everything downstream stay as they are.

**Design commitment (user decision 2026-07-21): the declared hierarchy is the
energy-accounting skeleton, not just a view.** Every component the description
declares keeps its own identity — its own energy/area/leakage row. Collapsing
declared components into a few compound-level buckets ("just PE") would defeat
fine-grained measurement and is not allowed. The *tree display* on the other hand
is optional by contract: if it cannot be built, print a WARNING and continue —
accounting is never affected.
"""

from __future__ import annotations

from pathlib import Path

from .ingest import description_from_accelergy, ingest

__all__ = ["DEFINITIONS_DIR", "HARNESS_SPEC", "description_from_accelergy",
           "ingest"]

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"

HARNESS_SPEC = {
    "name": "timeloop",
    "description": "Timeloop/Accelergy v0.4 architecture description.",
    "inputs": {
        "arch": {
            "flag": "--arch-yaml",
            "required": True,
            "kind": "file",
            "hint": "the Accelergy/Timeloop architecture YAML (v0.4, "
                    "'architecture:' root) — the only route for such files; "
                    "-d takes native descriptions only.",
        },
    },
    # No stats reader yet (workstream A) — activity is synthesized, so the
    # CLI's --vectorless-activity override applies to this harness.
    "synthesizes_activity": True,
    "ingest": ingest,
}
