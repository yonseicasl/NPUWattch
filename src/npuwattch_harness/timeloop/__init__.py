"""Timeloop/Accelergy harness.

This harness reads the files of the Timeloop/Accelergy toolchain. It translates
the names in these files into NPUWattch names.

Module layout:

``definitions/vocabulary.yaml``
    The vocabulary table: Accelergy ``class`` and ``attributes`` names ->
    NPUWattch names.
Definition files of the design (inputs of the run, ``..run_inputs``)
    ``compound_components.yaml``, ``projection.yaml``, and
    ``user_components.yaml`` in the directory of the architecture file. A
    compound component is an Accelergy class that becomes more than one
    primitive. The projection connects the Timeloop events (read, write,
    compute) to the elements of a compound.
:mod:`.accelergy_flattener`
    Reads the Accelergy v0.4 architecture file. It resolves the hierarchy, the
    spatial fanout, and the attribute inheritance.
:mod:`.vocabulary`
    The derivation rules. A rule calculates a NPUWattch attribute that
    Accelergy does not declare directly.
:mod:`.dram`
    The DRAM energy table of the run and the energy constants of each DRAM
    component.
:mod:`.ingest`
    The entry point. It makes the description (manual §3.1) and the activity,
    and sends them to the energy core (manual §6).
:mod:`.stats`
    Reads the Timeloop stats into activity rows (manual §3.3). The input is
    one ``timeloop-{model,mapper}.stats.txt`` file, or a directory that has
    one stats file for each layer.
:mod:`.tree`
    Makes the hierarchy view for ``--tree``. The shared ``report.tree``
    module prints the view.

Activity
--------
With ``--stats``, the activity comes from the Timeloop stats. Without
``--stats``, the run is a vectorless run and has the label VECTORLESS.

The projection file is the declaration of the ``Computes`` -> ``hold_b``
mapping. :func:`.stats.activity_from_stats` applies this mapping directly. It
does not use the compound interpreter, because an Accelergy file declares
components and does not declare compounds.

Design rule
-----------
The declared hierarchy is the structure of the energy accounts. Each declared
component keeps its own row of energy, area, and leakage. Do not merge the
declared components into a small number of compound totals, because that
removes the detail of the measurement.

The tree view is optional. If the harness cannot make the tree, it gives a
warning and continues. The energy accounts do not change.
"""

from __future__ import annotations

from ..run_inputs import DEFINITION_INPUTS
from .ingest import DEFINITIONS_DIR, description_from_accelergy, ingest

__all__ = ["DEFINITIONS_DIR", "HARNESS_SPEC", "description_from_accelergy",
           "ingest"]

HARNESS_SPEC = {
    "name": "timeloop",
    "description": "Timeloop/Accelergy v0.4 architecture description "
                   "(+ optional timeloop-model/mapper stats).",
    "inputs": {
        "arch": {
            "flag": "--arch-yaml",
            "required": True,
            "kind": "file",
            "names_design": "stem",
            "hint": "the Accelergy/Timeloop architecture YAML (v0.4, "
                    "'architecture:' root) — the only route for such files; "
                    "-d takes native descriptions only.",
        },
        "energy_table": {
            "flag": "--energy-table",
            "required": False,
            "kind": "file",
            "hint": "a DRAM energy table yml (PyTorchSim format; per-bit-only "
                    "tables are accepted) — overrides the table shipped for "
                    "the Accelergy DRAM 'type'",
        },
        "stats": {
            "flag": "--stats",
            "required": False,
            "kind": "path",
            "provides_activity": True,
            "hint": "a timeloop-model/mapper .stats.txt file, or a directory "
                    "of per-layer stats files (sorted by name = layer order). "
                    "Without it the run is the labeled VECTORLESS estimate.",
        },
        "stats_map": {
            "flag": "--stats-map",
            "required": False,
            "kind": "file",
            "requires": "stats",
            "hint": "YAML mapping stats level names to description "
                    "components ('levels:') and dropping levels deliberately "
                    "('ignore:'); exact/leaf-name matches need no entry.",
        },
        **DEFINITION_INPUTS,
    },
    "options": {
        "stats_mode": {
            "flag": "--stats-mode",
            "choices": ["windows", "aggregate"],
            "requires": "stats",
            "hint": "how a DIRECTORY of per-layer stats files is combined — "
                    "'windows' (default) keeps one window per layer "
                    "(per-layer energy over time in the report), 'aggregate' "
                    "sums counts into a single window.",
        },
    },
    # With --stats, the activity comes from the Timeloop stats. Without
    # --stats, the harness makes the VECTORLESS default activity. Thus the
    # --vectorless-activity option of the CLI applies. The parser does not
    # accept --vectorless-activity together with --stats, because `stats`
    # declares `provides_activity`.
    "synthesizes_activity": True,
    "ingest": ingest,
}
