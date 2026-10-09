"""Timeloop stats reader: ``timeloop-{model,mapper}.stats.txt`` -> activity rows.

Timeloop writes one stats file for each mapping. This module reads the stats
and makes the activity rows (manual §3.3). :mod:`.ingest` makes the
description (manual §3.1) from the Accelergy file. The same energy core
(manual §6) uses the two results.

With ``--stats``, the activity of the run comes from the stats. Without
``--stats``, the run is a vectorless run and has the label VECTORLESS.

Count conventions
-----------------
An error in one of these conventions multiplies the energy by a constant
factor, and no message shows the error.

* **Utilized instances.** For each dataspace, Timeloop prints ``Scalar
  reads/fills/updates (per-instance)``. The reader multiplies each value by
  the ``Utilized instances (max)`` of that dataspace. Timeloop uses the same
  multiplier for its ``Energy (total)``. Idle instances stay in the
  description for leakage and area, and they get no events. If the stats file
  has ``(total)`` lines, the reader uses these values directly.
* **Block size.** One scalar access moves one word of ``Word bits``. One
  physical access of the array moves ``Word bits x Block size`` bits. This is
  the ``data_width`` of the description, and the SRAM, regfile, and HBM models
  give the energy of one physical access. Thus the reader divides the scalar
  counts by the declared ``Block size`` of the level. Timeloop does the same
  division between its per-vector and per-scalar access energies.
* **Event and stim_mode.**

  - ``reads`` -> ``read``
  - ``fills + updates`` -> ``write``. A fill is a write into the level.
  - ``Computes (total)`` -> one ``op`` for each MAC, in the ``hold_b``
    stim_mode (weight-stationary). The PyTorchSim harness uses the same
    stim_mode.
  - For a compound component, the projection of the run gives the elements
    and the stim_mode of each event.

  If a primitive does not have the necessary stim_mode, the reader uses
  ``stream`` for a fifo and ``random`` for all other primitives. The run
  gives a note.

Level -> component
------------------
A level name in the stats is a leaf name of the architecture. A component name
in the description is a full dotted name. The reader connects a level to the
one component whose dotted name ends with the level name.

The optional map file (``--stats-map``) has two keys. ``levels:`` renames a
level or connects it to more than one component. ``ignore:`` removes a level
intentionally. A level that has no match, or more than one match, gives a
warning that tells the user the correction. It does not stop the run. A note
lists each ignored level, thus the user always knows about energy that is not
in the run (for example, DRAM energy).

More than one layer
-------------------
The input can be a directory that has one stats file for each layer. The
reader sorts the files by name.

* ``mode="windows"`` (default): one window for each layer. The cycle offsets
  are cumulative, thus the report shows the energy of each layer against time.
* ``mode="aggregate"``: one window that contains the sum of all counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from npuwattch.diagnostics import NPUWattchError, info, warning
from npuwattch.naming import primitive_of
from npuwattch.user_components import user_components_of

__all__ = [
    "LevelStats",
    "TimeloopStats",
    "TimeloopStatsError",
    "activity_from_stats",
    "load_stats_map",
    "parse_stats_file",
    "read_stats_input",
]

class TimeloopStatsError(NPUWattchError, ValueError):
    """A stats file, a stats directory, or a ``--stats-map`` file is not
    correct."""


#: File pattern for a stats directory. The name order is the layer order.
STATS_GLOB = "*.stats.txt"

# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

#: ``_LIST_SUFFIX_RE``: the range suffix of an Accelergy list component, for
#: example ``[0..3]``. ``_LEVEL_RE``: a level header, for example
#: ``=== mac ===``. The headers of the Operational Intensity section have the
#: same form. Thus the parser stops at the first section after the levels.
_LIST_SUFFIX_RE = re.compile(r"\[[^\]]*\]$")
_LEVEL_RE = re.compile(r"^===\s+(.+?)\s+===\s*$")
#: The sections that come after the level blocks. Each one is the end of the
#: levels. The set of sections is different between Timeloop versions.
_END_SECTIONS = ("Networks", "Operational Intensity Stats", "Summary Stats")

_INSTANCES_RE = re.compile(r"^\s*Instances\s*:\s*(\d+)")
_BLOCK_RE = re.compile(r"^\s*Block size\s*:\s*(\d+)")
_WORD_RE = re.compile(r"^\s*Word bits\s*:\s*(\d+)")
_CYCLES_RE = re.compile(r"^\s*Cycles\s*:\s*(\d+)")
_UTILIZED_RE = re.compile(r"^\s*Utilized instances(?:\s*\(max\))?\s*:\s*(\d+)")
_COMPUTES_RE = re.compile(
    r"^\s*(?:Actual\s+)?Computes\s*\((total|per-instance)\)\s*:\s*(\d+)")
_SCALAR_RE = re.compile(       # Old Timeloop versions add
    r"^\s*(?:Actual\s+)?Scalar\s+(reads|fills|updates)\s*"     # 'Actual'
    r"\((per-instance|total)\)\s*:\s*(\d+)", re.IGNORECASE)    # in front.
_SUMMARY_CYCLES_RE = re.compile(r"^\s*Cycles\s*:\s*(\d+)\s*$")


@dataclass
class LevelStats:
    """One ``=== name ===`` level block.

    The scalar totals include the instance multiplier.
    """

    name: str
    instances: Optional[int] = None      # declared count (SPECS), for a check
    block_size: int = 1
    word_bits: Optional[int] = None
    cycles: Optional[int] = None
    computes: Optional[int] = None       # compute level: total compute count
    reads: int = 0                       # scalar totals, the sum of all dataspaces
    fills: int = 0
    updates: int = 0
    #: The multiplier for the subsequent per-instance lines. It is the
    #: ``Utilized instances (max)`` of the current dataspace. If the dataspace
    #: has no such line, the parser uses the declared instances.
    _utilized: Optional[int] = field(default=None, repr=False)

    @property
    def is_compute(self) -> bool:
        return self.computes is not None

    @property
    def has_activity(self) -> bool:
        return self.is_compute or (self.reads + self.fills + self.updates) > 0


@dataclass(frozen=True)
class TimeloopStats:
    """One parsed stats file. It can become one window (manual §3.3)."""

    path: Path
    cycles: int
    levels: Tuple[LevelStats, ...]

    @property
    def label(self) -> str:
        """The window label: the file name without ``.stats.txt``."""
        name = self.path.name
        for suffix in (".stats.txt", ".txt"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name


def parse_stats_file(path: Path) -> TimeloopStats:
    """Parse one ``timeloop-*.stats.txt`` file into scalar totals for each level.

    The parser finds each level by its name line (``=== name ===``). It does
    not use the other ``===`` frame lines, because they are different between
    Timeloop versions.

    The run length is the ``Cycles`` line of the Summary Stats section. If the
    file has no such line, the run length is the largest cycle count of the
    levels. The cycle count of a level shows utilization, not the run length.
    But the largest one is a lower limit of the run length.
    """
    levels: List[LevelStats] = []
    current: Optional[LevelStats] = None
    in_levels = True
    in_summary = False
    summary_cycles: Optional[int] = None

    with Path(path).open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped in _END_SECTIONS:
                in_levels = False
                current = None
                in_summary = stripped == "Summary Stats"
                continue

            if in_summary and summary_cycles is None:
                m = _SUMMARY_CYCLES_RE.match(line)
                if m:
                    summary_cycles = int(m.group(1))
                continue

            if not in_levels:
                continue

            m = _LEVEL_RE.match(line)
            if m:
                current = LevelStats(name=m.group(1).strip())
                levels.append(current)
                continue
            if current is None:
                continue

            m = _SCALAR_RE.match(line)
            if m:
                kind, form, value = m.group(1), m.group(2), int(m.group(3))
                if form == "per-instance":
                    value *= current._utilized or current.instances or 1
                current.reads += value if kind == "reads" else 0
                current.fills += value if kind == "fills" else 0
                current.updates += value if kind == "updates" else 0
                continue
            m = _COMPUTES_RE.match(line)
            if m:
                form, value = m.group(1), int(m.group(2))
                if form == "per-instance":
                    value *= current._utilized or current.instances or 1
                current.computes = (current.computes or 0) + value
                continue
            m = _UTILIZED_RE.match(line)
            if m:
                current._utilized = int(m.group(1))
                continue
            m = _INSTANCES_RE.match(line)
            if m and current.instances is None:
                current.instances = int(m.group(1))
                continue
            m = _BLOCK_RE.match(line)
            if m:
                current.block_size = max(1, int(m.group(1)))
                continue
            m = _WORD_RE.match(line)
            if m and current.word_bits is None:
                current.word_bits = int(m.group(1))
                continue
            m = _CYCLES_RE.match(line)
            if m and current.cycles is None:
                current.cycles = int(m.group(1))
                continue

    if not levels:
        raise TimeloopStatsError.nw(7201, path=path)
    cycles = summary_cycles
    if cycles is None:
        cycles = max((lv.cycles or 0) for lv in levels)
    if cycles <= 0:
        raise TimeloopStatsError.nw(7202, path=path)
    return TimeloopStats(path=Path(path), cycles=cycles, levels=tuple(levels))


def read_stats_input(path: Path) -> List[TimeloopStats]:
    """Read the ``--stats`` path. Return one parsed entry for each file.

    If the path is a file, the result has one entry. If the path is a
    directory, the function reads all ``*.stats.txt`` files in name order.
    The name order is the layer order.
    """
    p = Path(path)
    if p.is_file():
        return [parse_stats_file(p)]
    files = sorted(p.glob(STATS_GLOB))
    if not files:
        raise TimeloopStatsError.nw(7203, path=p, pattern=STATS_GLOB)
    return [parse_stats_file(f) for f in files]


# --------------------------------------------------------------------------
# level -> component
# --------------------------------------------------------------------------

_EVENTS = ("read", "write", "op")
_ANY = "*"
_MULT = "multiplicity"      # reserved key: {component: events for each access}
_ACT = "action"             # reserved key: {event: {component: stim mode}}
_TARGET_KEYS = {"count", "action"}


def _is_count(n: Any) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and n >= 1


def _is_target_spec(value: Any) -> bool:
    """True for the value of ``{name: N}`` or ``{name: {count:, action:}}``."""
    if _is_count(value):
        return True
    return isinstance(value, Mapping) and bool(value) \
        and set(map(str, value)) <= _TARGET_KEYS


def _targets(level: str, where: str, tgt: Any
             ) -> Tuple[List[str], Dict[str, int], Dict[str, str]]:
    """One target entry -> (names, {name: events per access}, {name: action}).

    A target is one of:

    * ``name``: one event of the component for each access of the level;
    * ``{name: N}``: N events of the component for each access. For example,
      a unit that has 8 lanes gets one block of 8 elements for each access;
    * ``{name: {count: N, action: A}}``: N events (default 1), charged as
      the action A of the component. Without an action, the event name of the
      level (read, write, op) selects the action.
    """
    items = tgt if isinstance(tgt, (list, tuple)) else [tgt]
    names: List[str] = []
    mult: Dict[str, int] = {}
    actions: Dict[str, str] = {}
    for item in items:
        if isinstance(item, str):
            names.append(item)
            continue
        if isinstance(item, Mapping) and len(item) == 1:
            (name, spec), = item.items()
            if isinstance(name, str) and _is_target_spec(spec):
                n = spec if _is_count(spec) else spec.get("count", 1)
                action = None if _is_count(spec) else spec.get("action")
                if _is_count(n) and (action is None
                                     or (isinstance(action, str) and action)):
                    names.append(name)
                    if n > 1:
                        mult[name] = n
                    if action is not None:
                        actions[name] = action
                    continue
        raise TimeloopStatsError.nw(7204, level=level, where=where)
    if not names:
        raise TimeloopStatsError.nw(7205, level=level, where=where)
    return names, mult, actions


def _normalize_binding(level: str, value: Any) -> Dict[str, Any]:
    """One ``levels:`` entry -> ``{event: [component, ...]}``.

    Accepted forms:
      ``component``                         all events go to one component
      ``[c1, c2]``                          all events go to each listed one
      ``{read: [c1, c2], write: c1}``       one list for each event
                                            (``read``, ``write``, ``op``)

    Thus the read events of a level can also give activity to a read-data mux
    or a crossbar. This logic is between the banks of the level and the
    consumer. The user declares it as a component of the description, and
    NPUWattch adds no hardware.

    A target can be ``{name: N}``. Then each access of the level is N events
    of that component. For example, a post-processing unit that has 8 lanes
    gets blocks of 8 elements. The reserved key ``_MULT`` contains these
    multipliers.

    A target can also be ``{name: {count: N, action: A}}``. Then the events
    are charged as the action A of the component (for example, ``process``
    of a user component), not as the event name. The reserved key ``_ACT``
    contains these actions for each event.
    """
    per_event = isinstance(value, Mapping) and not (
        len(value) == 1 and _is_target_spec(next(iter(value.values()))))
    acts: Dict[str, Dict[str, str]] = {}
    if per_event:                            # {read: ..., write: ..., op: ...}
        unknown = [str(ev) for ev in value if str(ev) not in _EVENTS]
        if unknown:
            raise TimeloopStatsError.nw(7206, level=level, event=unknown[0],
                                        events=", ".join(_EVENTS))
        if not value:
            raise TimeloopStatsError.nw(7207, level=level)
        out: Dict[str, Any] = {}
        mult: Dict[str, int] = {}
        for ev, tgt in value.items():
            out[str(ev)], m, a = _targets(level, f", event '{ev}'", tgt)
            mult.update(m)
            if a:
                acts[str(ev)] = a
    elif isinstance(value, (str, list, tuple, Mapping)):   # all events
        names, mult, a = _targets(level, "", value)
        out = {_ANY: names}
        if a:
            acts[_ANY] = a
    else:
        raise TimeloopStatsError.nw(7208, level=level)
    if mult:
        out[_MULT] = mult
    if acts:
        out[_ACT] = acts
    return out


def load_stats_map(path: Path) -> Tuple[Dict[str, Dict[str, List[str]]], set]:
    """Read the optional map file of ``--stats-map``.

    The file has two keys:

    * ``levels: {level: binding}`` connects a level to components.
    * ``ignore: [level, ...]`` removes levels intentionally.

    A binding has one of three forms:

    * a component name: the level gets a new name,
    * a list of names: each listed component gets the events of the level,
    * a mapping with one list for each event.

    Refer to :func:`_normalize_binding`.
    """
    import yaml

    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, Mapping):
        raise TimeloopStatsError.nw(7209, path=path)
    levels = data.get("levels") or {}
    ignore = data.get("ignore") or []
    if not isinstance(levels, Mapping) or not isinstance(ignore, (list, tuple)):
        raise TimeloopStatsError.nw(7210, path=path)
    unknown = sorted(set(data) - {"levels", "ignore"})
    if unknown:
        raise TimeloopStatsError.nw(7211, path=path, keys=", ".join(unknown))
    return ({str(k): _normalize_binding(str(k), v) for k, v in levels.items()},
            {str(v) for v in ignore})


def _match_component(level: str, names: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    """Find the component of the description for a level name.

    The order is:

    1. An exact match of the full dotted name.
    2. A leaf name match that is unique: ``...PE.mac`` ends with ``.mac``.
    3. The same leaf name match, but case-insensitive.

    Return ``(match, candidates)``. ``match`` is ``None`` if there is no
    candidate or more than one candidate. The caller gives the warning.
    """
    if level in names:
        return level, [level]
    # The name of an Accelergy list component includes its range, for
    # example ``wbuf_rd_mux[0..3]``. Stats levels and map targets use the
    # name without the range.
    base = {n: _LIST_SUFFIX_RE.sub("", n) for n in names}
    for fold in (False, True):
        lv = level.lower() if fold else level
        cands = [n for n in names
                 if (base[n].lower() if fold else base[n]) == lv
                 or (base[n].lower() if fold else base[n]).endswith("." + lv)]
        if cands:
            return (cands[0], cands) if len(cands) == 1 else (None, cands)
    return None, []


def _mode_for(primitive: str, wanted: str,
              modes_by_prim: Mapping[str, List[str]]) -> str:
    """Return the stim_mode to use for the primitive.

    If the primitive has no characterized energy for ``wanted``, use the
    nearest available stim_mode. All primitives have ``random``.
    """
    modes = modes_by_prim.get(primitive, ["random"])
    if wanted in modes:
        return wanted
    if wanted in ("read", "write") and "stream" in modes:
        return "stream"                    # fifo: push and pop use ``stream``
    if wanted == "hold_b" and "hold_scale" in modes:
        return "hold_scale"                # weight-stationary mode of mxfpmac
    return "random"


def activity_from_stats(
    stats_path: Path,
    description: Mapping[str, Any],
    *,
    mode: str = "windows",
    map_path: Optional[Path] = None,
    compound_bindings: Optional[Mapping[str, Mapping[str, Sequence[
        Tuple[str, str, int]]]]] = None,
) -> Tuple[List[Dict[str, Any]], int, List[str], List[str], List[str]]:
    """Timeloop stats + description -> activity rows (manual §3.3).

    Return ``(rows, total_cycles, window_labels, warnings, notes)``.

    * ``mode="windows"``: one window for each stats file, with cumulative
      cycle offsets.
    * ``mode="aggregate"``: one window that contains the sum of all counts.

    A ``levels:`` entry of ``--stats-map`` can connect one level to more than
    one component for each event, for example ``{read: [wbuf, wbuf_rd_mux]}``.
    Then the read-data mux between a banked buffer and its consumer gets the
    access count of the buffer (manual §4.2, banked buffers).

    ``compound_bindings`` is for the components that are compound components:
    ``component -> event -> [(element component, stim_mode, scale)]``. A
    level or a map target can name such a component. Its events then go to
    its elements, as the projection of the run declares.
    """
    if mode not in ("windows", "aggregate"):
        raise TimeloopStatsError.nw(7212, mode=mode)

    stats_list = read_stats_input(stats_path)
    level_map, ignore = load_stats_map(map_path) if map_path else ({}, set())

    compound_bindings = compound_bindings or {}
    compound_names = list(compound_bindings)
    comps = (description.get("npuwattch") or {}).get("components", [])
    names = [str(c["name"]) for c in comps]
    by_name = {str(c["name"]): c for c in comps}
    # Map targets use the same match rules as level names: the exact dotted
    # name, or a leaf name that is unique. For example, ``wbuf_rd_mux``
    # matches ``system_top_level.wbuf_rd_mux``.
    missing_targets: List[str] = []
    resolved_map: Dict[str, Dict[str, List[str]]] = {}
    level_mult: Dict[str, Dict[str, int]] = {}   # level -> {component: events for each access}
    level_act: Dict[str, Dict[Tuple[str, str], str]] = {}  # level -> {(event, component): action}
    for level, binding in level_map.items():
        rb: Dict[str, List[str]] = {}
        resolved: Dict[str, str] = {}
        for ev, targets in binding.items():
            if ev in (_MULT, _ACT):
                continue
            rt = []
            for t in targets:
                match, _ = _match_component(t, compound_names)
                if match is None:
                    match, _ = _match_component(t, names)
                if match is None:
                    missing_targets.append(t)
                else:
                    rt.append(match)
                    resolved[t] = match
            rb[ev] = rt
        resolved_map[level] = rb
        level_mult[level] = {resolved[t]: n
                             for t, n in binding.get(_MULT, {}).items()
                             if t in resolved}
        level_act[level] = {(ev, resolved[t]): a
                            for ev, per_t in binding.get(_ACT, {}).items()
                            for t, a in per_t.items() if t in resolved}
    level_map = resolved_map
    if missing_targets:
        raise TimeloopStatsError.nw(
            7213, missing=", ".join(sorted(set(missing_targets))),
            components=", ".join(sorted(names)))

    try:
        from ..compounds import load_primitive_modes
        modes_by_prim = dict(load_primitive_modes().modes)
    except Exception:                       # optional, same as a vectorless run
        modes_by_prim = {}
    # The modes of a user component are the actions that the user gives.
    for user_name, user_component in user_components_of(description).items():
        modes_by_prim[user_name] = list(user_component.actions)

    warnings: List[str] = []
    notes: List[str] = []
    unmatched: List[str] = []
    ignored_with_activity: List[str] = []
    mode_fallbacks: Dict[str, str] = {}     # component -> used stim_mode (not the wanted one)
    fanout: Dict[str, Dict[str, List[str]]] = {}   # level -> targets for each event
    covered: set = set()

    # windows[i] = {(component, event, mode): count}.
    # cycles_per_window[i] is the cycle count of the same window.
    windows: List[Dict[Tuple[str, str, str], float]] = []
    cycles_per_window: List[int] = []
    labels: List[str] = []

    for st in stats_list:
        counts: Dict[Tuple[str, str, str], float] = {}
        for lv in st.levels:
            if not lv.has_activity:
                continue                     # a spatial or dummy level has no activity
            if lv.name in ignore:
                ignored_with_activity.append(lv.name)
                continue
            binding = level_map.get(lv.name)
            if binding is None:
                target, cands = _match_component(lv.name, compound_names)
                if target is None:
                    target, cands = _match_component(lv.name, names)
                if target is None:
                    if len(cands) > 1:
                        warnings.append(warning(
                            7214, level=lv.name,
                            candidates=", ".join(sorted(cands))))
                    else:
                        unmatched.append(lv.name)
                    continue
                binding = {_ANY: [target]}
            all_targets = sorted({t for ts in binding.values() for t in ts})
            mult = level_mult.get(lv.name, {})
            acts = level_act.get(lv.name, {})
            # Compare the instance counts only for the component that is the
            # level itself. That is the renamed target or the target whose
            # name matches the level. The other targets (a mux, a
            # post-processing unit) are different hardware.
            own = ({all_targets[0]} if len(all_targets) == 1 else
                   {t for t in all_targets
                    if _match_component(lv.name, [t])[0] is not None})
            prim_of: Dict[str, str] = {}
            for target in all_targets:
                if target in compound_bindings:
                    # A compound component: its elements get the events.
                    covered.update(
                        element for bound in compound_bindings[target].values()
                        for element, _, _ in bound)
                    continue
                comp = by_name[target]
                prim_of[target] = primitive_of(str(comp.get("class", "")))
                declared = int(comp.get("count", 1))
                if target in own and lv.instances is not None \
                        and lv.instances != declared:
                    warnings.append(warning(
                        7215, level=lv.name, stats_instances=lv.instances,
                        declared=declared, component=target))
                covered.add(target)
            if len(all_targets) > 1 or set(binding) != {_ANY} or mult or acts:
                fanout.setdefault(lv.name, binding)

            def _add(event: str, wanted_mode: str, count: float) -> None:
                if count <= 0:
                    return
                for target in binding.get(event, binding.get(_ANY, [])):
                    action = acts.get((event, target),
                                      acts.get((_ANY, target)))
                    if target in compound_bindings:
                        if action is not None:
                            raise TimeloopStatsError.nw(
                                7216, level=lv.name, action=action,
                                component=target)
                        for element, stim, scale in compound_bindings[
                                target].get(event, ()):
                            key = (element, event, stim)
                            counts[key] = (counts.get(key, 0.0) + count * scale
                                           * mult.get(target, 1))
                        continue
                    primitive = prim_of[target]
                    if action is not None:
                        # The user named the action: use it or stop.
                        known = modes_by_prim.get(primitive, ["random"])
                        if action not in known:
                            raise TimeloopStatsError.nw(
                                7217, level=lv.name, component=target,
                                action=action, actions=", ".join(known))
                        charged = action
                    else:
                        charged = _mode_for(primitive, wanted_mode, modes_by_prim)
                        if charged != wanted_mode:
                            mode_fallbacks[target] = charged
                    key = (target, event, charged)
                    counts[key] = (counts.get(key, 0.0)
                                   + count * mult.get(target, 1))

            if lv.is_compute:
                _add("op", "hold_b", float(lv.computes))
            block = max(1, lv.block_size)
            _add("read", "read", lv.reads / block)
            _add("write", "write", (lv.fills + lv.updates) / block)

        windows.append(counts)
        cycles_per_window.append(st.cycles)
        labels.append(st.label)

    if mode == "aggregate" and len(windows) > 1:
        merged: Dict[Tuple[str, str, str], float] = {}
        for counts in windows:
            for key, value in counts.items():
                merged[key] = merged.get(key, 0.0) + value
        windows = [merged]
        cycles_per_window = [sum(cycles_per_window)]
        labels = [f"aggregate({len(stats_list)} layers)"]

    rows: List[Dict[str, Any]] = []
    offset = 0
    for w, (counts, cycles) in enumerate(zip(windows, cycles_per_window)):
        start, end = offset, offset + cycles - 1
        for (component, event, stim), count in counts.items():
            rows.append({
                "window": w, "cycle_start": start, "cycle_end": end,
                "component": component, "event": event, "mode": stim,
                "count": int(count) if float(count).is_integer() else count,
            })
        offset = end + 1
    total_cycles = offset

    # -- notes and warnings about the source of the activity --------------
    n_layers = len(stats_list)
    notes.append(info(7218, files=n_layers, cycles=total_cycles,
                      charged=len(covered), total=len(names), mode=mode))
    if unmatched:
        warnings.append(warning(7219, levels=", ".join(sorted(set(unmatched)))))
    if ignored_with_activity:
        notes.append(info(
            7220, levels=", ".join(sorted(set(ignored_with_activity)))))
    uncovered = sorted(set(names) - covered)
    if uncovered:
        warnings.append(warning(7221, count=len(uncovered),
                                components=", ".join(uncovered)))
    for level, binding in sorted(fanout.items()):
        mult = level_mult.get(level, {})
        acts = level_act.get(level, {})
        parts = []
        for ev in list(_EVENTS) + [_ANY]:
            if ev in binding:
                parts.append(
                    f"{'all events' if ev == _ANY else ev} → "
                    + ", ".join(
                        t + (f" ×{mult[t]}" if t in mult else "")
                        + (f" as '{acts.get((ev, t), acts.get((_ANY, t)))}'"
                           if (ev, t) in acts or (_ANY, t) in acts else "")
                        for t in binding[ev]))
        notes.append(info(7222, level=level, bindings="; ".join(parts)))
    for target, charged in sorted(mode_fallbacks.items()):
        notes.append(info(7223, component=target, mode=charged))
    warnings = list(dict.fromkeys(warnings))  # remove duplicate warnings
    return rows, total_cycles, labels, warnings, notes
