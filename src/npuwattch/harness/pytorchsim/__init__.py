"""PyTorchSim harness — architecture inference + activity projection.

``mac_config`` infers a systolic MAC's NPUWattch primitive config from a
compiled kernel's codegen artifacts (meta.txt + MLIR). ``gem5_stats`` and
``togsim_log`` parse the two activity sources; ``activity`` joins them per
kernel into ``KernelWindow``s and binds a tool projection to produce per-element
cycle counts. See ``docs/COMPOUND_SCHEMA.md`` and ``docs/INTEGRATION_PLAN.md`` §4.
"""

from __future__ import annotations

from .activity import BoundAction, KernelWindow, bind_window, read_run
from .definitions import DEFINITIONS_DIR, load_definitions
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
from .mac_config import (
    DType,
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config,
    infer_mac_config_from_dir,
    parse_meta,
    parse_mlir,
)
from .togsim_log import (
    TogsimActivity,
    TogsimLogError,
    parse_config,
    parse_togsim_log,
)

__all__ = [
    # mac_config
    "DType",
    "MacConfig",
    "MacInferenceError",
    "NotAMatmulKernel",
    "infer_mac_config",
    "infer_mac_config_from_dir",
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
    "parse_togsim_log",
    # activity
    "BoundAction",
    "KernelWindow",
    "bind_window",
    "read_run",
    # definitions bundle
    "DEFINITIONS_DIR",
    "load_definitions",
]
