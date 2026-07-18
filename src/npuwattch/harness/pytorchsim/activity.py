"""Assemble PyTorchSim run outputs into NPUWattch-consumable activity windows.

One compiled kernel = one **window**. ``read_run`` walks a run directory
(``togsim_results/*.log`` + ``outputs/<hash>/``), and for each executed kernel
joins three things by the log's ``outputs/<hash>`` pointer:

    architecture  ← MacConfig from outputs/<hash>/meta.txt + MLIR   (mac_config.py)
    activity      ← systolic/vector cycles + COMP ops               (togsim_log.py)
    activity      ← CustomMatMul* instruction counts                (gem5_stats.py)

The result is a list of ``KernelWindow`` carrying a ``stats`` dict whose keys are
exactly the projection ``count_from.stat`` names (``systolic_active_cycles``,
``CustomMatMulwVpush``, …). ``bind_window`` then turns a window + a tool
projection + a compound into per-action, per-element **cycle counts in a
stim_mode** — the direct input to energy (the final × per-cycle-energy step needs
the primitive estimator and is out of scope here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..compounds.loader import (
    Compound,
    PrimitiveModes,
    Projection,
    ResolvedActionElement,
    resolve_action,
)
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
from .mac_config import (
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config_from_dir,
)
from .togsim_log import TogsimLogError, parse_togsim_log

__all__ = ["KernelWindow", "BoundAction", "read_run", "bind_window"]

# gem5 committedInstType classes the systolic projection may reference.
_MATMUL_INSTS = (
    "CustomMatMul",
    "CustomMatMulwVpush",
    "CustomMatMuliVpush",
    "CustomMatMulvpop",
)


@dataclass(frozen=True)
class KernelWindow:
    """One kernel's architecture + activity, ready for a projection."""

    index: int
    kernel_hash: str
    log_name: str
    mac_config: Optional[MacConfig]
    stats: Dict[str, float]
    lanes: int
    config: Dict[str, object]              # TOGSim config header (this run)
    exec_cycles: Optional[int]
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BoundAction:
    """A native action bound to a window: total element-cycles per stim_mode.

    ``cycle_count = stat_value × scale`` is how many cycles each element spends in
    its assigned ``stim_mode``. Energy = ``cycle_count × per_cycle_energy(primitive,
    config, stim_mode)`` — the last factor comes from the primitive estimator.
    """

    action: str
    stat: str
    stat_value: float
    scale: int
    cycle_count: float
    elements: List[ResolvedActionElement]


def _num(x: float) -> float:
    return int(x) if float(x).is_integer() else x


def read_run(run_dir: Path, *, pipeline_stages: int = 2) -> List[KernelWindow]:
    """Read a PyTorchSim run directory into per-kernel activity windows.

    ``run_dir`` contains ``togsim_results/`` and ``outputs/``. Each TOGSim log is
    one executed kernel; ``outputs/<hash>`` dirs without a log are unexecuted
    autotune candidates and are skipped. lanes come from each log's config header.
    """
    run_dir = Path(run_dir)
    log_dir = run_dir / "togsim_results"
    out_dir = run_dir / "outputs"
    if not log_dir.is_dir():
        raise MacInferenceError(f"no togsim_results/ under {run_dir}")

    windows: List[KernelWindow] = []
    for idx, log_path in enumerate(sorted(log_dir.glob("*.log"))):
        warnings: List[str] = []
        try:
            act = parse_togsim_log(log_path.read_text(encoding="utf-8", errors="ignore"))
        except TogsimLogError as e:
            warnings.append(f"unparseable TOGSim log {log_path.name}: {e}")
            continue
        if len(act.kernel_hashes) != 1:
            warnings.append(
                f"{log_path.name}: expected 1 kernel hash, got {act.kernel_hashes}; skipped"
            )
            continue
        khash = act.kernel_hashes[0]
        kernel_dir = out_dir / khash

        # architecture: MacConfig from the codegen artifacts.
        mac_config: Optional[MacConfig] = None
        if kernel_dir.is_dir():
            try:
                mac_config = infer_mac_config_from_dir(
                    kernel_dir, act.lanes, pipeline_stages=pipeline_stages
                )
                warnings.extend(mac_config.warnings)
            except NotAMatmulKernel:
                warnings.append(f"{khash}: kernel has no linalg.matmul; no MAC config")
            except MacInferenceError as e:
                warnings.append(f"{khash}: MAC config inference failed: {e}")
        else:
            warnings.append(f"{khash}: outputs/{khash}/ not found; MAC config unavailable")

        # activity: gem5 CustomMatMul* + numCycles.
        stats: Dict[str, float] = {
            "systolic_active_cycles": act.systolic_active_cycles,
            "vector_active_cycles": act.vector_active_cycles,
            "comp_gemm_ops": act.comp_gemm_ops,
            "comp_vector_ops": act.comp_vector_ops,
        }
        if act.total_exec_cycles is not None:
            stats["total_exec_cycles"] = act.total_exec_cycles
        stats_path = kernel_dir / "m5out" / "stats.txt"
        if stats_path.is_file():
            sections = parse_sections(stats_path.read_text(encoding="utf-8", errors="ignore"))
            inst = sum_committed_inst(sections)
            for name in _MATMUL_INSTS:
                stats[name] = float(inst.get(name, 0))
            stats["numCycles"] = sum_stat(sections, "system.cpu.numCycles")
        else:
            warnings.append(f"{khash}: no m5out/stats.txt; gem5 instruction counts unavailable")

        windows.append(
            KernelWindow(
                index=idx,
                kernel_hash=khash,
                log_name=log_path.name,
                mac_config=mac_config,
                stats={k: _num(v) for k, v in stats.items()},
                lanes=act.lanes,
                config=act.config,
                exec_cycles=act.total_exec_cycles,
                warnings=warnings,
            )
        )
    return windows


def bind_window(
    window: KernelWindow,
    projection: Projection,
    compound: Compound,
    primitive_modes: PrimitiveModes,
) -> List[BoundAction]:
    """Bind a window's activity to a projection+compound → per-action cycle counts.

    Only actions whose ``count_from.stat`` is present in the window are emitted;
    a missing stat is skipped (recorded in the window's warnings by the caller's
    convention). Requires the window to have a resolved ``mac_config``.
    """
    if window.mac_config is None:
        raise MacInferenceError(
            f"window {window.kernel_hash} has no MAC config; cannot bind projection"
        )
    actions = projection.compounds.get(compound.name, {})
    bound: List[BoundAction] = []
    for action_name, mapping in actions.items():
        stat = mapping.count_from.stat
        if stat not in window.stats:
            continue  # unmapped for this run — dropped, never silently charged
        ares = resolve_action(projection, compound, action_name, window.mac_config, primitive_modes)
        stat_value = window.stats[stat]
        bound.append(
            BoundAction(
                action=action_name,
                stat=stat,
                stat_value=stat_value,
                scale=ares.scale,
                cycle_count=_num(stat_value * ares.scale),
                elements=ares.elements,
            )
        )
    return bound
