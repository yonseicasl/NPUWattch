"""Aggregate per-window activity into energy/area/power, per the manual §6.

Implements exactly the §6 equations, honoring the count convention that is the
source of silent N× bugs:

    T_exec  = total_cycles · T_clk
    E_dyn   = Σ_c Σ_event  N(c,event) · E_event(c)     # activity counts, NOT ×count
    E_leak  = ( Σ_c count(c) · P_leak(c) ) · T_exec     # area/leak DO scale with count
    E_total = E_dyn + E_leak ;  P_avg = E_total / T_exec

For a systolic compound: the projection's ``count_from`` already sums the compute
events over every PE instance (``systolic_active_cycles · lanes²``), so dynamic
energy multiplies unit energy by that event count and by nothing else. Area and
leakage use the element instance count (``lanes²``) times the number of physical
arrays (``cores · arrays_per_core``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .unit_cost import TechContext, UnitCostProvider

__all__ = [
    "ComponentEnergy",
    "WindowEnergy",
    "RunEnergy",
    "aggregate_window",
    "aggregate_run",
    "analyze_run",
]


@dataclass(frozen=True)
class ComponentEnergy:
    element: str
    primitive: str
    instances: int
    dyn_energy_pJ: float
    area_um2: float
    leak_power_mW: float
    leak_energy_pJ: float
    crit_path_ns: float


@dataclass(frozen=True)
class WindowEnergy:
    kernel_hash: str
    components: Dict[str, ComponentEnergy]
    dyn_energy_pJ: float
    leak_energy_pJ: float
    total_energy_pJ: float
    exec_time_s: float
    avg_power_mW: float
    f_max_MHz: Optional[float]
    exec_cycles: int
    clock_MHz: float
    calibrated: bool
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunEnergy:
    windows: List[WindowEnergy]
    dyn_energy_pJ: float
    leak_energy_pJ: float
    total_energy_pJ: float
    exec_time_s: float
    avg_power_mW: float
    f_max_MHz: Optional[float]
    calibrated: bool


def _features(config: Any, tech: TechContext, stim_mode: Optional[str] = None) -> Dict[str, Any]:
    feats: Dict[str, Any] = dict(tech.features())
    if isinstance(config, Mapping):
        feats.update(config)
    if stim_mode is not None:
        feats["stim_mode"] = stim_mode
    return feats


def _resolve_clock(window: Any, tech: TechContext, clock_mhz: Optional[float]) -> float:
    for cand in (clock_mhz, tech.clock_mhz, (window.config or {}).get("core_freq_mhz")):
        if cand:
            return float(cand)
    raise ValueError(
        f"no clock frequency for window {getattr(window, 'kernel_hash', '?')}: "
        "pass clock_mhz, set TechContext.clock_mhz, or ensure the log has core_freq_mhz"
    )


def _exec_cycles(window: Any) -> Optional[int]:
    if getattr(window, "exec_cycles", None):
        return int(window.exec_cycles)
    stats = getattr(window, "stats", {}) or {}
    for k in ("total_exec_cycles", "numCycles"):
        if stats.get(k):
            return int(stats[k])
    return None


def aggregate_window(
    window: Any,
    bound_actions: List[Any],
    resolved: Mapping[str, Any],
    provider: UnitCostProvider,
    tech: TechContext,
    *,
    num_arrays: int = 1,
    clock_mhz: Optional[float] = None,
) -> WindowEnergy:
    """Energy/area/power for one kernel window (§6).

    ``resolved`` is ``resolve_compound(...)`` output (element -> ResolvedElement,
    carrying per-instance ``config`` and ``count``); ``bound_actions`` is
    ``bind_window(...)`` output (per-action ``cycle_count`` + per-element stim_mode).
    ``num_arrays`` scales area/leak (physical array count), never dynamic energy.
    """
    warnings: List[str] = []
    clock = _resolve_clock(window, tech, clock_mhz)
    t_clk_s = 1.0e-6 / clock                       # MHz -> period in seconds
    cycles = _exec_cycles(window)
    if cycles is None:
        warnings.append("no exec cycles; leakage energy set to 0")
        cycles = 0
    t_exec_s = cycles * t_clk_s

    # dynamic energy: sum event_count · per-cycle energy over every action/element.
    dyn: Dict[str, float] = {name: 0.0 for name in resolved}
    for ba in bound_actions:
        for rae in ba.elements:
            feats = _features(rae.config, tech, rae.stim_mode)
            e_pc = provider.energy_per_cycle(rae.primitive, feats)
            dyn[rae.element] = dyn.get(rae.element, 0.0) + ba.cycle_count * e_pc

    components: Dict[str, ComponentEnergy] = {}
    crit_paths: List[float] = []
    for name, rel in resolved.items():
        instances = int(rel.count) * max(1, num_arrays)
        feats = _features(rel.config, tech)
        area = instances * provider.area(rel.primitive, feats)
        leak_mW = instances * provider.leak_power(rel.primitive, feats)
        crit = provider.crit_path(rel.primitive, feats)
        crit_paths.append(crit)
        leak_energy_pJ = leak_mW * t_exec_s * 1.0e9   # mW·s -> pJ
        components[name] = ComponentEnergy(
            element=name,
            primitive=rel.primitive,
            instances=instances,
            dyn_energy_pJ=dyn.get(name, 0.0),
            area_um2=area,
            leak_power_mW=leak_mW,
            leak_energy_pJ=leak_energy_pJ,
            crit_path_ns=crit,
        )

    e_dyn = sum(c.dyn_energy_pJ for c in components.values())
    e_leak = sum(c.leak_energy_pJ for c in components.values())
    e_total = e_dyn + e_leak
    p_avg = (e_total * 1.0e-9 / t_exec_s) if t_exec_s > 0 else 0.0   # pJ/s -> mW
    f_max = (1000.0 / max(crit_paths)) if crit_paths and max(crit_paths) > 0 else None

    return WindowEnergy(
        kernel_hash=getattr(window, "kernel_hash", "?"),
        components=components,
        dyn_energy_pJ=e_dyn,
        leak_energy_pJ=e_leak,
        total_energy_pJ=e_total,
        exec_time_s=t_exec_s,
        avg_power_mW=p_avg,
        f_max_MHz=f_max,
        exec_cycles=cycles,
        clock_MHz=clock,
        calibrated=bool(getattr(provider, "calibrated", False)),
        warnings=warnings,
    )


def aggregate_run(window_energies: List[WindowEnergy], *, calibrated: bool) -> RunEnergy:
    """Sum window results into run totals (§6 windowed aggregation)."""
    e_dyn = sum(w.dyn_energy_pJ for w in window_energies)
    e_leak = sum(w.leak_energy_pJ for w in window_energies)
    e_total = e_dyn + e_leak
    t_exec = sum(w.exec_time_s for w in window_energies)
    p_avg = (e_total * 1.0e-9 / t_exec) if t_exec > 0 else 0.0
    fmaxes = [w.f_max_MHz for w in window_energies if w.f_max_MHz]
    return RunEnergy(
        windows=window_energies,
        dyn_energy_pJ=e_dyn,
        leak_energy_pJ=e_leak,
        total_energy_pJ=e_total,
        exec_time_s=t_exec,
        avg_power_mW=p_avg,
        f_max_MHz=(min(fmaxes) if fmaxes else None),
        calibrated=calibrated,
    )


def analyze_run(
    run_dir: Path,
    provider: UnitCostProvider,
    tech: TechContext,
    *,
    compound_name: str = "systolic_mac",
    bundle: Any = None,
) -> RunEnergy:
    """End-to-end: read a PyTorchSim run dir, project, and aggregate to energy.

    The one-call demo of the full pipeline
    (activity → arch → projection → energy). Windows whose kernel has no MAC
    config (non-matmul) are skipped.
    """
    from ..harness.compounds import resolve_compound
    from ..harness.pytorchsim import bind_window, load_definitions, read_run

    if bundle is None:
        bundle = load_definitions()
    compound = bundle.compound(compound_name)
    projection = bundle.projection("pytorchsim")
    pm = bundle.primitive_modes

    results: List[WindowEnergy] = []
    for w in read_run(run_dir):
        if w.mac_config is None:
            continue
        resolved = resolve_compound(compound, w.mac_config)
        bound = bind_window(w, projection, compound, pm)
        cfg = w.config or {}
        num_arrays = int(cfg.get("num_cores", 1)) * int(cfg.get("num_systolic_array_per_core", 1))
        results.append(
            aggregate_window(w, bound, resolved, provider, tech, num_arrays=num_arrays)
        )
    return aggregate_run(results, calibrated=bool(getattr(provider, "calibrated", False)))
