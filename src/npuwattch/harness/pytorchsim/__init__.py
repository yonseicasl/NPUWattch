"""PyTorchSim harness — architecture inference + activity projection.

``mac_config`` infers a systolic MAC's NPUWattch primitive config from a
compiled kernel's codegen artifacts (meta.txt + MLIR). ``gem5_stats`` and
``togsim_log`` parse the two activity sources; ``activity`` joins them per
kernel into ``KernelWindow``s and binds a tool projection to produce per-element
cycle counts. See ``docs/COMPOUND_SCHEMA.md`` and ``docs/INTEGRATION_PLAN.md`` §4.
"""

from __future__ import annotations

from pathlib import Path

from .activity import BoundAction, KernelWindow, bind_window, read_run
from .definitions import DEFINITIONS_DIR, load_definitions
from .energy_table import EnergyTable, EnergyTableError, load_energy_table
from .hierarchy import build_hierarchy
from .instances import expand_bounds
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
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


def _ingest(inputs, tech, **opts):
    """Ingest a PyTorchSim run (named inputs) → ``EmittedArch``.

    ``inputs`` is the registry-validated ``{"togsim": Path, "gem5": Path}`` plus
    an optional ``"config"`` (the run's config.yml — header wins, yml fills
    gaps and cross-checks) and an optional ``"booksim"`` (the run's
    ``booksim2_config/`` — anynet NoC topologies need their .net file from it).
    PyTorchSim stores the two result sets in separate locations, so both arrive
    as explicit directories. Genuine ambiguity (e.g. two kernel MLIRs for one
    hash) raises from ``read_run``/``synthesize_run``.
    """
    from ...arch_synth import synthesize_run
    from .energy_table import load_energy_table
    from .run_config import load_config_yml

    config_path = inputs.get("config")
    base_config = load_config_yml(config_path) if config_path else None
    booksim = inputs.get("booksim")
    etable_path = inputs.get("energy_table")
    energy_table = load_energy_table(etable_path) if etable_path else None
    return synthesize_run(Path(inputs["togsim"]), Path(inputs["gem5"]), tech,
                          base_config=base_config,
                          booksim_dir=Path(booksim) if booksim else None,
                          energy_table=energy_table,
                          **opts)


#: Self-announced harness declaration (discovered by ``harness.registry``).
HARNESS_SPEC = {
    "name": "pytorchsim",
    "description": "PyTorchSim (PSAL-POSTECH) weight-stationary systolic NPU.",
    "inputs": {
        "togsim": {
            "flag": "--togsim-dir",
            "required": True,
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
                    "dram compound's built-in constants with the run's own; "
                    "without it the built-in cited HBM2 constants are charged",
        },
    },
    "ingest": _ingest,
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
    # hierarchy view (--tree)
    "build_hierarchy",
    "expand_bounds",
    # definitions bundle
    "DEFINITIONS_DIR",
    "load_definitions",
    # DRAM energy table (--energy-table)
    "EnergyTable",
    "EnergyTableError",
    "load_energy_table",
    # harness registration
    "HARNESS_SPEC",
]
