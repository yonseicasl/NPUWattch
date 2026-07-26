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
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..naming import validate_attributes
from .unit_cost import TechContext, UnitCostProvider

__all__ = [
    "ComponentEnergy",
    "WindowEnergy",
    "RunEnergy",
    "aggregate_window",
    "aggregate_native",
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


def _aggregate_one_window(
    components: Mapping[str, tuple],          # name -> (primitive, config, instances)
    activity_items: List[tuple],              # (name, primitive, config, mode, count)
    *,
    clock_MHz: float,
    exec_cycles: int,
    provider: UnitCostProvider,
    tech: TechContext,
    kernel_hash: str,
    warnings: Optional[List[str]] = None,
) -> WindowEnergy:
    """The §6 arithmetic for one window — shared by the BoundAction adapter
    (``aggregate_window``) and the native adapter (``aggregate_native``).

    Dynamic energy sums event_count · per-cycle energy (events only); area and
    leakage use the per-component instance count; leak energy = leak_power · t_exec.
    """
    warnings = list(warnings or [])
    t_exec_s = exec_cycles * (1.0e-6 / clock_MHz)   # MHz -> period in seconds

    dyn: Dict[str, float] = {name: 0.0 for name in components}
    for name, primitive, config, mode, count in activity_items:
        if name not in components:
            continue                               # activity for an unlisted component
        e_pc = provider.energy_per_cycle(primitive, _features(config, tech, mode))
        dyn[name] += count * e_pc

    comp_energy: Dict[str, ComponentEnergy] = {}
    crit_paths: List[float] = []
    for name, (primitive, config, instances) in components.items():
        feats = _features(config, tech)
        area = instances * provider.area(primitive, feats)
        leak_mW = instances * provider.leak_power(primitive, feats)
        crit = provider.crit_path(primitive, feats)
        crit_paths.append(crit)
        leak_energy_pJ = leak_mW * t_exec_s * 1.0e9   # mW·s -> pJ
        comp_energy[name] = ComponentEnergy(
            element=name,
            primitive=primitive,
            instances=instances,
            dyn_energy_pJ=dyn.get(name, 0.0),
            area_um2=area,
            leak_power_mW=leak_mW,
            leak_energy_pJ=leak_energy_pJ,
            crit_path_ns=crit,
        )

    e_dyn = sum(c.dyn_energy_pJ for c in comp_energy.values())
    e_leak = sum(c.leak_energy_pJ for c in comp_energy.values())
    e_total = e_dyn + e_leak
    p_avg = (e_total * 1.0e-9 / t_exec_s) if t_exec_s > 0 else 0.0   # pJ/s -> mW
    f_max = (1000.0 / max(crit_paths)) if crit_paths and max(crit_paths) > 0 else None

    return WindowEnergy(
        kernel_hash=kernel_hash,
        components=comp_energy,
        dyn_energy_pJ=e_dyn,
        leak_energy_pJ=e_leak,
        total_energy_pJ=e_total,
        exec_time_s=t_exec_s,
        avg_power_mW=p_avg,
        f_max_MHz=f_max,
        exec_cycles=exec_cycles,
        clock_MHz=clock_MHz,
        calibrated=bool(getattr(provider, "calibrated", False)),
        warnings=warnings,
    )


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
    """Energy/area/power for one kernel window from the harness BoundAction path (§6).

    Thin adapter over ``_aggregate_one_window``: ``resolved`` is
    ``resolve_compound(...)`` output; ``bound_actions`` is ``bind_window(...)``.
    ``num_arrays`` scales area/leak (physical array count), never dynamic energy.
    """
    warnings: List[str] = []
    clock = _resolve_clock(window, tech, clock_mhz)
    cycles = _exec_cycles(window)
    if cycles is None:
        warnings.append("no exec cycles; leakage energy set to 0")
        cycles = 0

    components = {
        name: (rel.primitive, rel.config, int(rel.count) * max(1, num_arrays))
        for name, rel in resolved.items()
    }
    activity_items = [
        (rae.element, rae.primitive, rae.config, rae.stim_mode, ba.cycle_count)
        for ba in bound_actions
        for rae in ba.elements
    ]
    return _aggregate_one_window(
        components, activity_items,
        clock_MHz=clock, exec_cycles=cycles, provider=provider, tech=tech,
        kernel_hash=getattr(window, "kernel_hash", "?"), warnings=warnings,
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


# Native description ``class`` → the provider/estimator ``primitive`` key. Most are
# identity; the systolic weight register is named ``register_file`` in §3.1.
from ..naming import primitive_of as _primitive_of  # noqa: E402  (class → primitive)


def aggregate_native(
    description: Mapping[str, Any],           # §3.1 {"npuwattch": {...}}
    activity_rows: List[Mapping[str, Any]],  # §3.3 rows (window,component,mode,count)
    provider: UnitCostProvider,
    tech: TechContext,
    *,
    default_clock_mhz: Optional[float] = None,
    warnings: Optional[List[str]] = None,
    window_labels: Optional[Sequence[str]] = None,
) -> RunEnergy:
    """The **core §6 entry**: energy from a native description + native activity.

    Both input paths converge here — the PyTorchSim harness (``EmittedArch``, in
    memory) and the direct ``-l activity.csv`` path (parsed rows). Components come
    from the §3.1 ``components`` (``count`` already includes multi-array/core
    instances; ``class`` → provider primitive); dynamic energy is keyed by the
    ``mode`` column. Kernels run back-to-back, so each window's exec cycles come
    from its rows' ``cycle_start/end``.

    ``window_labels`` (optional, indexed by window number) names each window's
    kernel in the per-window results — the harness passes
    ``EmittedArch.window_labels``; a bare ``-l`` CSV has no names, so windows
    fall back to ``window{i}``.
    """
    nw = description.get("npuwattch", {})
    clock = (nw.get("clock") or {}).get("frequency_MHz") or default_clock_mhz
    if not clock:
        raise ValueError("native description has no clock.frequency_MHz (and no default_clock_mhz)")

    # Attribute names are a contract, not a suggestion: a hand-written or
    # harness-emitted description that uses a legacy spelling raises here rather
    # than silently defaulting inside an estimator.
    components = {}
    for c in nw.get("components", []):
        primitive = _primitive_of(c.get("class", ""))
        attrs = dict(c.get("attributes") or {})
        notes = validate_attributes(primitive, attrs, component=str(c.get("name", "?")))
        if warnings is not None:
            warnings.extend(notes)
        components[c["name"]] = (primitive, attrs, int(c.get("count", 1)))

    by_window: Dict[int, List[Mapping[str, Any]]] = {}
    for r in activity_rows:
        if str(r.get("component")) == "__meta__":
            continue
        by_window.setdefault(int(r["window"]), []).append(r)

    window_energies: List[WindowEnergy] = []
    for w in sorted(by_window):
        rows = by_window[w]
        cs = min(int(r["cycle_start"]) for r in rows)
        ce = max(int(r["cycle_end"]) for r in rows)
        cycles = (ce - cs + 1) if ce >= cs else 0
        activity_items = []
        for r in rows:
            name = r["component"]
            if name not in components:
                continue
            primitive, config, _ = components[name]
            activity_items.append((name, primitive, config, r.get("mode"), float(r["count"])))
        label = (window_labels[w]
                 if window_labels is not None and w < len(window_labels)
                 else f"window{w}")
        window_energies.append(
            _aggregate_one_window(
                components, activity_items,
                clock_MHz=float(clock), exec_cycles=cycles, provider=provider, tech=tech,
                kernel_hash=label,
            )
        )
    return aggregate_run(window_energies, calibrated=bool(getattr(provider, "calibrated", False)))


def analyze_run(
    togsim_dir: Path,
    gem5_dir: Path,
    provider: UnitCostProvider,
    tech: TechContext,
    *,
    compound_name: str = "systolic_mac",
    bundle: Any = None,
    default_clock_mhz: Optional[float] = None,
) -> RunEnergy:
    """End-to-end: read a PyTorchSim run (TOGSim logs dir + gem5 outputs dir) →
    native (via the emitter) → §6.

    The one-call demo of the full pipeline (activity → native arch/activity →
    energy), routed through the same ``aggregate_native`` core the CLI uses.
    """
    from ..arch_synth import synthesize_run

    em = synthesize_run(
        togsim_dir, gem5_dir, tech, compound_name=compound_name, bundle=bundle,
        default_clock_mhz=default_clock_mhz,
    )
    return aggregate_native(em.description, em.activity_rows, provider, tech,
                            default_clock_mhz=default_clock_mhz,
                            window_labels=em.window_labels)
