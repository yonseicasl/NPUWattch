"""Timeloop/Accelergy harness.

Owns what a harness owns: reading that toolchain's file format and translating
its vocabulary into ours.

* :mod:`.ingest` — an Accelergy v0.4 architecture YAML → a native §3.1
  description + activity. **This absorbed the console's legacy Accelergy path
  (2026-08-12)**: the same input now runs through the §6 core (v2 logic MLPs +
  the SRAM estimator, window accounting, ``--report``) instead of the old
  per-component plugin calls, which is why ``src/estimators/`` no longer carries
  the prototype-era ``adder``/``crossbar``/``regfile``/``custom`` directories.
* :mod:`.stats` — the activity half (**workstream A, built 2026-08-13**):
  ``timeloop-{model,mapper}.stats.txt`` (one file, or a directory of per-layer
  files) → native §3.3 rows. ``--stats`` makes the run vectored; without it
  the harness still synthesizes the labeled VECTORLESS default.
* :mod:`.vocabulary` — Accelergy ``class``/``attributes`` → NPUWattch primitives
  and canonical attribute names.
* :mod:`.tree` — the declared-hierarchy view for ``--tree`` (builders are
  harness-owned; rendered through the shared ``report.tree`` renderers).
* ``definitions/projections/timeloop.yaml`` — maps Timeloop's coarse ``Computes``
  onto the same ``hold_b`` compute state PyTorchSim uses (the stim_mode is a
  hardware property, and that shared axis is the Timeloop↔PyTorchSim join).

**Workstream A landed 2026-08-13**: the stats reader above wires
mapping-driven activity. The projection file stays as the *declaration* of the
mode mapping (Computes → ``hold_b``); the flat-description route charges it via
:func:`.stats.activity_from_stats` directly rather than through the compound
interpreter — the Accelergy description declares plain components, not a
compound bundle. A run without ``--stats`` remains the labeled VECTORLESS
estimate.

**Design commitment: the declared hierarchy is the energy-accounting
skeleton, not just a view.** Every component the description
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
    "description": "Timeloop/Accelergy v0.4 architecture description "
                   "(+ optional timeloop-model/mapper stats).",
    "inputs": {
        "arch": {
            "flag": "--arch-yaml",
            "required": True,
            "kind": "file",
            "hint": "the Accelergy/Timeloop architecture YAML (v0.4, "
                    "'architecture:' root) — the only route for such files; "
                    "-d takes native descriptions only.",
        },
        "stats": {
            "flag": "--stats",
            "required": False,
            "kind": "path",
            "hint": "a timeloop-model/mapper .stats.txt file, or a directory "
                    "of per-layer stats files (sorted by name = layer order). "
                    "Without it the run is the labeled VECTORLESS estimate.",
        },
        "stats_map": {
            "flag": "--stats-map",
            "required": False,
            "kind": "file",
            "hint": "optional YAML mapping stats level names to description "
                    "components ('levels:') and dropping levels deliberately "
                    "('ignore:'); exact/leaf-name matches need no entry.",
        },
    },
    # --stats wires real activity; without it the harness synthesizes the
    # VECTORLESS default, so the CLI's --vectorless-activity override applies
    # (the parser rejects combining it with --stats).
    "synthesizes_activity": True,
    "ingest": ingest,
}
