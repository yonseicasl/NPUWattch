"""Default activity for a run that has no activity table (manual §6).

A run with ``-d`` and without ``-l`` has no activity table, thus it has no
event counts for the dynamic energy. This module makes a **first-order
steady-state estimate**: each component operates at
``DEFAULT_VECTORLESS_ACTIVITY`` (25 %) of full random switching.

The value of 25 % has two reasons:

* It agrees with sign-off practice for datapath blocks under load. The 10 %
  default of the tools is low when compared with vectored SAIF results.
* It is equal to the **measured** ``valid25`` stim_mode of the crossbar-family
  primitives. If a primitive has that stim_mode, the vectorless run uses the
  characterized point and does not scale ``random``.

The module makes one window of one cycle. Thus the dynamic values are
**energies for one cycle**, and the §6 average power is the steady-state
power. The leakage and area calculations of §6 do not change. A §3.3 count
is the total for all the instances of a component, thus each count below is
multiplied by the ``count`` of the component. The rows of each component
are:

* The primitive has ``valid25``: the full cycle in ``valid25``.
* The primitive has ``idle``: the fraction ``activity`` of a cycle in
  ``random``, and the remaining fraction in ``idle``. The clocked-idle energy
  is a real cost.
* All other primitives: the fraction ``activity`` of a cycle in ``random``.

A capacity ``.tail`` part (§3.8) gets leakage and area only, the same as in a
harness run. The ``random`` unit cost of a memory instance is for one access,
with the adjacent macros idle and the other banks gated. Dynamic energy for
the tail would count that access again.

All user-facing output must show the label **VECTORLESS** for a result from
this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ..naming import primitive_of
from ..user_components import user_components_of

__all__ = ["DEFAULT_VECTORLESS_ACTIVITY", "vectorless_activity_rows"]

#: The fraction of full random switching for a run that has no activity log.
DEFAULT_VECTORLESS_ACTIVITY = 0.25


def _primitive_modes() -> Mapping[str, List[str]]:
    """Return the stim_modes of each primitive, or {} if they are not available."""
    try:
        from npuwattch_harness.compounds import load_primitive_modes
        return load_primitive_modes().modes
    except Exception:                      # the run continues without the table
        return {}


def vectorless_activity_rows(
    description: Mapping[str, Any],
    *,
    activity: float = DEFAULT_VECTORLESS_ACTIVITY,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Make the activity rows (manual §3.3) for a description that has no activity log.

    Return ``(rows, notes)``. The rows are one window of one cycle, and they
    are an input of ``aggregate_native``. The notes tell the user how the
    module made the rows.
    """
    if not (0.0 < activity <= 1.0):
        raise ValueError(f"vectorless activity must be in (0, 1], got {activity}")
    modes_by_prim = _primitive_modes()
    user = user_components_of(description)
    user_skipped: List[str] = []
    rows: List[Dict[str, Any]] = []
    notes: List[str] = [
        f"VECTORLESS estimate: no activity log — every component charged at "
        f"{activity:.0%} of random switching (crossbar-family uses the "
        f"measured valid25 mode); dynamic values are per-cycle energies and "
        f"avg power is the steady-state figure",
    ]
    tails = 0

    def _row(component: str, mode: str, count: float) -> Dict[str, Any]:
        return {
            "window": 0, "cycle_start": 0, "cycle_end": 0,
            "component": component, "event": "vectorless", "mode": mode,
            "count": count,
        }

    for comp in (description.get("npuwattch") or {}).get("components", []):
        name = str(comp.get("name", "?"))
        instances = int(comp.get("count", 1))
        if name.endswith(".tail"):         # a capacity tail: leakage and area only
            tails += 1
            continue
        if str(comp.get("class", "")) in user:
            # A user component has only the actions that the user gives.
            if "random" in user[str(comp["class"])].actions:
                rows.append(_row(name, "random", activity * instances))
            else:
                user_skipped.append(name)
            continue
        prim = primitive_of(comp.get("class", ""))
        modes = modes_by_prim.get(prim, ["random"])
        if "valid25" in modes:
            rows.append(_row(name, "valid25", 1.0 * instances))
        else:
            rows.append(_row(name, "random", activity * instances))
            if "idle" in modes and activity < 1.0:
                rows.append(_row(name, "idle", (1.0 - activity) * instances))
    if user_skipped:
        notes.append(
            f"user component(s) {', '.join(user_skipped)}: no `random` action "
            f"in the library — charged area and leakage only in this "
            f"VECTORLESS run")
    if tails:
        notes.append(
            f"{tails} capacity '.tail' part(s) charged leakage/area only "
            f"(their access energy is already in the primary part's unit cost)"
        )
    return rows, notes
