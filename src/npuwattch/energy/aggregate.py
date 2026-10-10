"""Calculate energy, area, and power from the activity of each window (manual §6).

This module uses the §6 equations:

    T_exec  = total_cycles · T_clk
    E_dyn   = Σ_c Σ_event  N(c,event) · E_event(c)     # activity counts, NOT ×count
    E_leak  = ( Σ_c count(c) · P_leak(c) ) · T_exec     # area and leakage use count
    E_total = E_dyn + E_leak ;  P_avg = E_total / T_exec

The count convention, with an example: an action that drives each of N
instances for C cycles has an activity count of N·C. The dynamic energy is that
count times the unit energy, and it is not multiplied by N again. Area and
leakage use the instance count of the component.

``aggregate_native`` is the entry point. Its inputs are a description
(manual §3.1) and its activity rows (manual §3.3). All input paths (a harness
or the ``-d``/``-l`` files) use it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from npuwattch.diagnostics import NPUWattchError, about, warning
from ..naming import validate_attributes
from ..user_components import user_components_of
from .unit_cost import NoModelError, TechContext, UnitCostProvider

__all__ = [
    "AggregateError",
    "ComponentEnergy",
    "WindowEnergy",
    "RunEnergy",
    "aggregate_native",
    "aggregate_run",
]


class AggregateError(NPUWattchError, ValueError):
    """The energy of a description cannot be calculated."""


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
    #: The dynamic energy for each stim_mode. The sum is dyn_energy_pJ.
    #: A breakdown for each command reads this field (for example, the DRAM
    #: activate, read, write, and refresh energies). The key of a row that
    #: has no mode is "unspecified".
    dyn_by_mode: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class WindowEnergy:
    #: The name of the window (for example, a kernel hash or a layer name).
    label: str
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


def _features(config: Any, tech: TechContext, stim_mode: Optional[str] = None,
              clock_mhz: Optional[float] = None) -> Dict[str, Any]:
    feats: Dict[str, Any] = dict(tech.features())
    # Add the clock of the window to the features. An estimator that depends
    # on the frequency then uses the clock of the run (the logic MLPs use
    # log10_clock_ns). A clock from TechContext or --clock-mhz has priority.
    if clock_mhz and not feats.get("clock_mhz"):
        feats["clock_mhz"] = float(clock_mhz)
    if isinstance(config, Mapping):
        feats.update(config)
    if stim_mode is not None:
        feats["stim_mode"] = stim_mode
    return feats


def _book_idle_per_cycle(
    components: Mapping[str, tuple],
    dyn: Dict[str, float],
    dyn_modes: Dict[str, Dict[str, float]],
    events_by_mode: Dict[str, Dict[str, float]],
    *,
    provider: UnitCostProvider,
    tech: TechContext,
    clock_MHz: float,
    exec_cycles: int,
    warnings: List[str],
) -> None:
    """Charge the clocked-idle energy of a memory one time for each cycle.

    A provider can have the optional method ``idle_terms(primitive, features)
    -> (e_idle_per_cycle, idle_displaced_per_access)``. The unit cost of one
    access of such a provider includes idle energy: the energy of all the
    other clocked decoder groups in a cycle that has one access. This idle
    part is ``e_idle - displaced``.

    If each event includes this idle part, the idle energy is too large for
    a cycle that has two or more accesses (parallel banks). It is too small
    for a cycle that has no access. Thus, if the cycle count of the window is
    known, this function moves the idle part out of the events:

        E_events = Σ N_mode · (E_mode - (e_idle - displaced))
        E_idle   = max(0, instances · e_idle · cycles - N_total · displaced)

    A component that has ``idle`` rows in its activity is not changed. If the
    window has no cycle count, each access event keeps its idle part, and the
    window gets a warning.
    """
    idle_fn = getattr(provider, "idle_terms", None)
    if idle_fn is None:
        return
    pending: List[str] = []
    for name, (primitive, config, instances) in components.items():
        modes = dyn_modes.get(name)
        if not modes or "idle" in modes:
            continue
        terms = idle_fn(primitive, _features(config, tech, clock_mhz=clock_MHz))
        if not terms:
            continue
        e_idle_cycle, displaced = float(terms[0]), float(terms[1])
        if exec_cycles <= 0:
            pending.append(name)
            continue
        per_event_idle = e_idle_cycle - displaced
        n_total = 0.0
        for mode_key, n in events_by_mode.get(name, {}).items():
            modes[mode_key] = max(0.0, modes[mode_key] - n * per_event_idle)
            n_total += n
        budget = float(instances) * e_idle_cycle * float(exec_cycles)
        idle = budget - n_total * displaced
        if idle < 0.0:
            warnings.append(warning(3101, component=name, events=n_total,
                                    instances=instances, cycles=exec_cycles))
            idle = 0.0
        modes["idle"] = modes.get("idle", 0.0) + idle
        dyn[name] = sum(modes.values())
    if pending:
        warnings.append(warning(3102, components=", ".join(pending)))


def _aggregate_one_window(
    components: Mapping[str, tuple],          # name -> (primitive, config, instances)
    activity_items: List[tuple],              # (name, primitive, config, mode, count)
    *,
    clock_MHz: float,
    exec_cycles: int,
    provider: UnitCostProvider,
    tech: TechContext,
    label: str,
    warnings: Optional[List[str]] = None,
) -> WindowEnergy:
    """Calculate the §6 results of one window.

    The dynamic energy is the sum of event_count · energy_per_cycle. The area
    and the leakage use the instance count of each component. The leakage
    energy is leak_power · t_exec.
    """
    warnings = list(warnings or [])
    t_exec_s = exec_cycles * (1.0e-6 / clock_MHz)   # MHz -> period in seconds

    dyn: Dict[str, float] = {name: 0.0 for name in components}
    dyn_modes: Dict[str, Dict[str, float]] = {}
    events_by_mode: Dict[str, Dict[str, float]] = {}
    for name, primitive, config, mode, count in activity_items:
        if name not in components:
            continue                               # the component is not in the description
        e_pc = provider.energy_per_cycle(
            primitive, _features(config, tech, mode, clock_mhz=clock_MHz))
        e = count * e_pc
        dyn[name] += e
        per_mode = dyn_modes.setdefault(name, {})
        mode_key = str(mode) if mode is not None else "unspecified"
        per_mode[mode_key] = per_mode.get(mode_key, 0.0) + e
        n_by_mode = events_by_mode.setdefault(name, {})
        n_by_mode[mode_key] = n_by_mode.get(mode_key, 0.0) + count

    _book_idle_per_cycle(components, dyn, dyn_modes, events_by_mode,
                         provider=provider, tech=tech, clock_MHz=clock_MHz,
                         exec_cycles=exec_cycles, warnings=warnings)

    comp_energy: Dict[str, ComponentEnergy] = {}
    crit_paths: List[float] = []
    for name, (primitive, config, instances) in components.items():
        feats = _features(config, tech, clock_mhz=clock_MHz)
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
            dyn_by_mode=dyn_modes.get(name, {}),
        )

    e_dyn = sum(c.dyn_energy_pJ for c in comp_energy.values())
    e_leak = sum(c.leak_energy_pJ for c in comp_energy.values())
    e_total = e_dyn + e_leak
    p_avg = (e_total * 1.0e-9 / t_exec_s) if t_exec_s > 0 else 0.0   # pJ/s -> mW
    f_max = (1000.0 / max(crit_paths)) if crit_paths and max(crit_paths) > 0 else None

    return WindowEnergy(
        label=label,
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


def aggregate_run(window_energies: List[WindowEnergy], *, calibrated: bool) -> RunEnergy:
    """Add the window results to get the totals of the run (§6)."""
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


# ``_primitive_of`` gives the primitive name for the ``class`` of a component.
# Most names are the same. An exception is the class ``register_file`` of
# §3.1, which is the primitive ``regfile``.
from ..naming import primitive_of as _primitive_of  # noqa: E402


def aggregate_native(
    description: Mapping[str, Any],           # §3.1 {"npuwattch": {...}}
    activity_rows: List[Mapping[str, Any]],  # §3.3 rows (window, component, mode, count)
    provider: UnitCostProvider,
    tech: TechContext,
    *,
    default_clock_mhz: Optional[float] = None,
    warnings: Optional[List[str]] = None,
    window_labels: Optional[Sequence[str]] = None,
    clock_check: bool = True,
) -> RunEnergy:
    """Calculate the energy of a run from a description and its activity rows.

    This function is the only energy entry point. A harness calls it with
    the data of ``EmittedArch``. The ``-l activity.csv`` path calls it with
    the rows of the file.

    The components come from the ``components`` list of the description
    (manual §3.1). ``count`` includes all the instances of the component.
    ``class`` gives the primitive. The ``mode`` column of a row selects the
    dynamic energy of one event.

    The windows are consecutive in time. Thus the cycle count of a window
    comes from ``cycle_start`` and ``cycle_end`` of its rows.

    ``clock_check`` False removes the clock-range checks from the envelope
    warnings. The energy does not change.

    ``window_labels`` is optional. It gives the name of each window, and its
    index is the window number. A harness supplies
    ``EmittedArch.window_labels``. An activity CSV has no names, thus the
    name of window ``i`` is ``window{i}``.

    If no provider has a model for the class of a component, the function
    raises ``NoModelError`` (a ``ValueError``). A component of the user
    component library (the ``user_components`` block of the description) has
    no attributes to check.
    """
    nw = description.get("npuwattch", {})
    clock = (nw.get("clock") or {}).get("frequency_MHz") or default_clock_mhz
    if not clock:
        raise AggregateError.nw(3103)

    # Each attribute has one NPUWattch name. A legacy alias of an attribute
    # name causes an error here. Without the error, the estimator uses a
    # default value and gives no message.
    user_names = set(user_components_of(description))
    components = {}
    for c in nw.get("components", []):
        attrs = dict(c.get("attributes") or {})
        if str(c.get("class", "")) in user_names:
            primitive = str(c["class"])         # a user component keeps its name
        else:
            primitive = _primitive_of(c.get("class", ""))
            notes = validate_attributes(primitive, attrs,
                                        component=str(c.get("name", "?")))
            if warnings is not None:
                warnings.extend(notes)
        components[c["name"]] = (primitive, attrs, int(c.get("count", 1)))
        # Make sure that a provider has a model for the class. The error
        # message gives the component name.
        try:
            provider.area(primitive, _features(attrs, tech,
                                               clock_mhz=float(clock)))
        except NoModelError as e:
            raise NoModelError.nw(3104, component=c["name"],
                                  primitive=primitive) from e

    # A query can be outside the range that the estimators characterized.
    # Examples are a pipeline depth that the RTL does not have, and a clock
    # that no implementation met. The provider gives a value for such a query,
    # and a warning that tells why the value is not a measured design point.
    envelope_fn = getattr(provider, "envelope_warnings", None)
    if envelope_fn is not None and warnings is not None:
        for name, (primitive, attrs, _) in components.items():
            feats = _features(attrs, tech, clock_mhz=float(clock))
            feats["clock_check"] = clock_check
            for w in envelope_fn(primitive, feats):
                warnings.append(about(name, w))

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
                label=label,
            )
        )
    return aggregate_run(window_energies, calibrated=bool(getattr(provider, "calibrated", False)))
