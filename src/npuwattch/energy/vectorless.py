"""Vectorless default activity — `-d` without `-l` (manual §6).

With no activity table there is nothing to charge dynamics from, so the
estimator synthesizes a **first-order steady-state assumption**: every
component is exercised at ``DEFAULT_VECTORLESS_ACTIVITY`` (25 %) of full-random
switching. 25 % is deliberate: it matches sign-off practice for datapath-heavy
blocks under load (bare tool defaults of 10 % skew low against vectored SAIF),
and it coincides with the **measured** ``valid25`` stim mode of the
crossbar-family primitives — where that mode exists, the vectorless path uses
the characterized point directly instead of scaling ``random``.

Per component (one synthetic 1-cycle window, so dynamic numbers are
**per-cycle energies** and the §6 average power is the steady-state figure;
leakage/area come from the §6 machinery unchanged):

* primitive has ``valid25``    → every cycle in ``valid25``;
* primitive has ``idle``       → ``activity`` of a cycle in ``random`` +
  the remaining fraction in ``idle`` (clocked-idle energy is real);
* otherwise                    → ``activity`` of a cycle in ``random``.

Capacity-expansion ``.tail`` parts (§3.8) carry leakage/area only — exactly as
in harness runs — because a memory instance's ``random`` unit cost already
models one access with sibling subarrays idle and other banks gated; charging
the tail again would multiply that access.

Any result built this way must be labeled **VECTORLESS** in user-facing output.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ..naming import primitive_of

__all__ = ["DEFAULT_VECTORLESS_ACTIVITY", "vectorless_activity_rows"]

#: Fraction of full-random switching assumed when no activity log is given.
#: User decision 2026-07-21 (was 10 % in the HPCA-prototype convention).
DEFAULT_VECTORLESS_ACTIVITY = 0.25


def _primitive_modes() -> Mapping[str, List[str]]:
    """The shared (primitive → stim modes) contract, or {} if unavailable."""
    try:
        from ..harness.compounds import load_primitive_modes
        return load_primitive_modes().modes
    except Exception:                      # vocabulary is advisory here
        return {}


def vectorless_activity_rows(
    description: Mapping[str, Any],
    *,
    activity: float = DEFAULT_VECTORLESS_ACTIVITY,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Synthesize §3.3 rows for a native description with no activity log.

    Returns ``(rows, notes)`` — one 1-cycle window; feed the rows straight into
    ``aggregate_native``. ``notes`` are user-facing provenance lines.
    """
    if not (0.0 < activity <= 1.0):
        raise ValueError(f"vectorless activity must be in (0, 1], got {activity}")
    modes_by_prim = _primitive_modes()
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
        if name.endswith(".tail"):         # capacity tails: leakage/area only
            tails += 1
            continue
        prim = primitive_of(comp.get("class", ""))
        modes = modes_by_prim.get(prim, ["random"])
        if "valid25" in modes:
            rows.append(_row(name, "valid25", 1.0))
        else:
            rows.append(_row(name, "random", activity))
            if "idle" in modes and activity < 1.0:
                rows.append(_row(name, "idle", 1.0 - activity))
    if tails:
        notes.append(
            f"{tails} capacity '.tail' part(s) charged leakage/area only "
            f"(their access energy is already in the primary part's unit cost)"
        )
    return rows, notes
