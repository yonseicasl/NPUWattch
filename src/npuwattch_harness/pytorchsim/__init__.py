"""PyTorchSim harness: one PyTorchSim run -> one NPUWattch description and its
activity.

The package has these modules:

* ``definitions``: the vocabulary table of this harness, and the loader of
  the definition files of a run (compound components and projection).
* Readers, one for each input of a run:

  * ``togsim_log``: the TOGSim logs (run configuration and cycle counts).
  * ``gem5_stats``: the gem5 instruction counts.
  * ``mac_config``: the MAC configuration of a kernel, from its codegen files
    (``meta.txt`` and MLIR).
  * ``booksim``: the NoC topology and the flit counts.
  * ``run_config``: the ``config.yml`` of the run.

* ``activity``: ``read_run`` reads the run into one window for each kernel.
  ``bind_window`` applies the projection to a window.
* ``dram``: the DRAM energy table of the run, the DRAM constants of the
  ``hbm`` components, and the DRAM command counts.
* ``instances``: divides the activity of a window between the physical
  instances.
* ``hierarchy``: builds the tree view of the instances.
* ``ingest``: the entry point of the harness.

Refer to ``docs/COMPOUND_SCHEMA.md`` and ``docs/INTEGRATION_PLAN.md`` §4.
"""

from __future__ import annotations

from npuwattch.energy.dram_table import EnergyTable, EnergyTableError, load_energy_table
from ..run_inputs import DEFINITION_INPUTS
from .activity import BoundAction, KernelWindow, bind_window, read_run
from .definitions import DEFINITIONS_DIR, VOCABULARY, load_definitions
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
from .hierarchy import build_hierarchy
from .ingest import ingest, synthesize_run
from .instances import expand_bounds
from .mac_config import (
    DType,
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config,
    infer_mac_config_from_dir,
    infer_mac_config_from_meta,
    parse_meta,
    parse_mlir,
)
from .togsim_log import (
    TogsimActivity,
    TogsimLogError,
    parse_config,
    parse_kernel_hash,
    parse_togsim_log,
)


#: The declaration of this harness. ``npuwattch_harness.registry`` reads it from this module.
HARNESS_SPEC = {
    "name": "pytorchsim",
    "description": "PyTorchSim (PSAL-POSTECH) weight-stationary systolic NPU.",
    "inputs": {
        "togsim": {
            "flag": "--togsim-dir",
            "required": True,
            "names_design": "parent",
            "hint": "final TOGSim logs (the run's root togsim_results/; one .log "
                    "per executed kernel — NOT outputs/<hash>/togsim_result/, "
                    "those are autotune candidates)",
        },
        "gem5": {
            "flag": "--gem5-dir",
            "required": True,
            "hint": "per-kernel gem5/codegen dirs (raw run: outputs/; author "
                    "bundle: gem5_outputs/) — <hash>/{meta.txt, m5out/stats.txt"
                    ", kernel .mlir when present}",
        },
        "config": {
            "flag": "--config-yml",
            "required": False,
            "kind": "file",
            "hint": "the run's config.yml (--config file). The log header wins; "
                    "this fills gaps in damaged headers and cross-checks the "
                    "pairing (disagreements are warned)",
        },
        "booksim": {
            "flag": "--booksim-dir",
            "required": False,
            "hint": "the run's booksim2_config/ directory. Needed only for "
                    "anynet NoC topologies (their .net network file); fly NoCs "
                    "are self-contained in the log's BookSim config echo",
        },
        "energy_table": {
            "flag": "--energy-table",
            "required": False,
            "kind": "file",
            "hint": "the run's DRAM energy-cost table yml (the config's "
                    "energy_cost_table_path, e.g. hbm2.yml) — overrides the "
                    "default HBM2 table with the run's own; "
                    "without it the default cited HBM2 constants are charged",
        },
        **DEFINITION_INPUTS,
    },
    "usage_hint": "use run.sh to auto-locate both directories under one root",
    "ingest": ingest,
}

__all__ = [
    # mac_config
    "DType",
    "MacConfig",
    "MacInferenceError",
    "NotAMatmulKernel",
    "infer_mac_config",
    "infer_mac_config_from_dir",
    "infer_mac_config_from_meta",
    "parse_meta",
    "parse_mlir",
    # gem5_stats
    "parse_sections",
    "sum_committed_inst",
    "sum_stat",
    # togsim_log
    "TogsimActivity",
    "TogsimLogError",
    "parse_config",
    "parse_kernel_hash",
    "parse_togsim_log",
    # activity
    "BoundAction",
    "KernelWindow",
    "bind_window",
    "read_run",
    # hierarchy view (--tree) and instances
    "build_hierarchy",
    "expand_bounds",
    # definitions
    "DEFINITIONS_DIR",
    "VOCABULARY",
    "load_definitions",
    # ingest
    "ingest",
    "synthesize_run",
    # DRAM energy table (--energy-table)
    "EnergyTable",
    "EnergyTableError",
    "load_energy_table",
    # harness declaration
    "HARNESS_SPEC",
]
