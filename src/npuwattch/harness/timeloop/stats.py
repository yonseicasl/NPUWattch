"""Timeloop stats reader — ``timeloop-{model,mapper}.stats.txt`` → §3.3 activity.

This is the activity half of the Timeloop harness (workstream A). The
architecture half (:mod:`.ingest`) turns the Accelergy YAML into a native §3.1
description; this module turns the stats file Timeloop writes for a mapping
into the native activity rows that drive the same §6 core every other input
drives. With ``--stats`` a Timeloop run is a **vectored** estimate; without it
the harness still synthesizes the labeled VECTORLESS default.

**Count conventions** (each one is a place for a silent N× bug — see the
harness skill's `references/formats.md`):

* Timeloop's per-dataspace ``Scalar reads/fills/updates (per-instance)`` are
  multiplied by that dataspace's ``Utilized instances (max)`` — the same
  multiplier Timeloop's own ``Energy (total)`` uses. Idle instances stay in the
  description (leakage/area) and get no events. ``(total)`` lines are used
  directly when a stats variant prints them.
* A *scalar* access moves one word of ``Word bits``; the physical array access
  our SRAM/regfile/HBM models price moves ``Word bits × Block size`` (the
  description's ``data_width``, from the same Accelergy convention). Scalar
  counts are therefore divided by the level's declared ``Block size`` —
  exactly the amortization behind Timeloop's own per-scalar vs per-vector
  access energies.
* Event → stim_mode: ``reads`` → ``read``, ``fills + updates`` → ``write``
  (a fill is a write into the level); ``Computes (total)`` → one ``op`` per
  MAC in the **hold_b** weight-stationary mode — the mapping
  ``definitions/projections/timeloop.yaml`` declares, shared with PyTorchSim.
  A primitive without the wanted mode falls back (fifo → ``stream``,
  otherwise ``random``) with a note.

**Level → component binding.** Stats level names are the architecture's leaf
names; the ingested description uses full dotted names. A level binds to the
unique component whose dotted name ends with it. Renames and deliberate drops
go through the optional map YAML (``levels:``/``ignore:``); an unmatched or
ambiguous level is a WARNING naming the fix, never a crash, and every ignored
level is listed so nobody silently loses DRAM energy.

Multi-layer runs (a directory of per-layer stats files, sorted by name):
``mode="windows"`` (default) emits one §3.3 window per layer with cumulative
cycle offsets — the report plots per-layer energy over time; ``mode="aggregate"``
sums counts into one window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ...naming import primitive_of

__all__ = [
    "LevelStats",
    "TimeloopStats",
    "activity_from_stats",
    "load_stats_map",
    "parse_stats_file",
    "read_stats_input",
]

#: File pattern a stats directory is scanned for (sorted by name = layer order).
STATS_GLOB = "*.stats.txt"

# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

#: A level header: ``=== mac ===``. Also matched by the Operational Intensity
#: section's headers, so collection stops at the first post-level section.
_LEVEL_RE = re.compile(r"^===\s+(.+?)\s+===\s*$")
#: Sections after the per-level blocks (any of them ends level collection —
#: exact set varies by Timeloop version).
_END_SECTIONS = ("Networks", "Operational Intensity Stats", "Summary Stats")

_INSTANCES_RE = re.compile(r"^\s*Instances\s*:\s*(\d+)")
_BLOCK_RE = re.compile(r"^\s*Block size\s*:\s*(\d+)")
_WORD_RE = re.compile(r"^\s*Word bits\s*:\s*(\d+)")
_CYCLES_RE = re.compile(r"^\s*Cycles\s*:\s*(\d+)")
_UTILIZED_RE = re.compile(r"^\s*Utilized instances(?:\s*\(max\))?\s*:\s*(\d+)")
_COMPUTES_RE = re.compile(
    r"^\s*(?:Actual\s+)?Computes\s*\((total|per-instance)\)\s*:\s*(\d+)")
_SCALAR_RE = re.compile(       # 'Scalar reads' today, 'Actual scalar reads'
    r"^\s*(?:Actual\s+)?Scalar\s+(reads|fills|updates)\s*"     # in older
    r"\((per-instance|total)\)\s*:\s*(\d+)", re.IGNORECASE)    # Timeloops
_SUMMARY_CYCLES_RE = re.compile(r"^\s*Cycles\s*:\s*(\d+)\s*$")


@dataclass
class LevelStats:
    """One ``=== name ===`` level block, with instance-scaled scalar totals."""

    name: str
    instances: Optional[int] = None      # declared (SPECS), for cross-checks
    block_size: int = 1
    word_bits: Optional[int] = None
    cycles: Optional[int] = None
    computes: Optional[int] = None       # arithmetic level: total compute count
    reads: int = 0                       # scalar totals, summed over dataspaces
    fills: int = 0
    updates: int = 0
    #: multiplier for the NEXT per-instance lines (the current dataspace's
    #: ``Utilized instances (max)``; falls back to the declared instances).
    _utilized: Optional[int] = field(default=None, repr=False)

    @property
    def is_compute(self) -> bool:
        return self.computes is not None

    @property
    def has_activity(self) -> bool:
        return self.is_compute or (self.reads + self.fills + self.updates) > 0


@dataclass(frozen=True)
class TimeloopStats:
    """One parsed stats file — one candidate §3.3 window."""

    path: Path
    cycles: int
    levels: Tuple[LevelStats, ...]

    @property
    def label(self) -> str:
        """Window label: the file name without ``.stats.txt``."""
        name = self.path.name
        for suffix in (".stats.txt", ".txt"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name


def parse_stats_file(path: Path) -> TimeloopStats:
    """Parse one ``timeloop-*.stats.txt`` into per-level scalar totals.

    Anchors on the level-name lines, not the ``===`` framing (the framing
    varies across Timeloop versions). Run length comes from the Summary Stats
    ``Cycles`` line; when a stats variant lacks it, the max per-level cycle
    count is used (per-level cycles are utilization detail, not the run
    length — but their max bounds it from below honestly).
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
        raise ValueError(
            f"{path}: no '=== <level> ===' blocks found — is this a "
            f"timeloop-model/mapper .stats.txt?")
    cycles = summary_cycles
    if cycles is None:
        cycles = max((lv.cycles or 0) for lv in levels)
    if cycles <= 0:
        raise ValueError(f"{path}: no positive cycle count found")
    return TimeloopStats(path=Path(path), cycles=cycles, levels=tuple(levels))


def read_stats_input(path: Path) -> List[TimeloopStats]:
    """``--stats`` value → parsed stats, one entry per file.

    A file parses alone; a directory is scanned for ``*.stats.txt`` sorted by
    name (= layer order, per the NeuroSpector-style per-layer workflow).
    """
    p = Path(path)
    if p.is_file():
        return [parse_stats_file(p)]
    files = sorted(p.glob(STATS_GLOB))
    if not files:
        raise ValueError(
            f"{p}: no '{STATS_GLOB}' files found — pass a "
            f"timeloop-model/mapper stats file or a directory of per-layer "
            f"stats files")
    return [parse_stats_file(f) for f in files]


# --------------------------------------------------------------------------
# level → component binding
# --------------------------------------------------------------------------

def load_stats_map(path: Path) -> Tuple[Dict[str, str], set]:
    """Read the optional map YAML: ``levels: {level: component}`` renames plus
    ``ignore: [level, ...]`` deliberate drops."""
    import yaml

    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: expected a mapping with 'levels:'/'ignore:'")
    levels = data.get("levels") or {}
    ignore = data.get("ignore") or []
    if not isinstance(levels, Mapping) or not isinstance(ignore, (list, tuple)):
        raise ValueError(
            f"{path}: 'levels' must be a mapping and 'ignore' a list")
    unknown = sorted(set(data) - {"levels", "ignore"})
    if unknown:
        raise ValueError(
            f"{path}: unknown key(s) {', '.join(unknown)} — the stats map "
            f"takes 'levels:' and 'ignore:'")
    return ({str(k): str(v) for k, v in levels.items()},
            {str(v) for v in ignore})


def _match_component(level: str, names: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    """Bind a stats level name to a description component name.

    Exact dotted-name match first, then unique leaf-suffix match
    (``...PE.mac`` ends with ``.mac``); case-insensitive retry for each.
    Returns ``(match, candidates)`` — no match and >1 candidates are the
    caller's warnings.
    """
    if level in names:
        return level, [level]
    for fold in (False, True):
        lv = level.lower() if fold else level
        cands = [n for n in names
                 if (n.lower() if fold else n) == lv
                 or (n.lower() if fold else n).endswith("." + lv)]
        if cands:
            return (cands[0], cands) if len(cands) == 1 else (None, cands)
    return None, []


def _mode_for(primitive: str, wanted: str,
              modes_by_prim: Mapping[str, List[str]]) -> str:
    """The stim_mode to charge, degrading to what the primitive was
    characterized with (fifo streams; everything has ``random``)."""
    modes = modes_by_prim.get(primitive, ["random"])
    if wanted in modes:
        return wanted
    if wanted in ("read", "write") and "stream" in modes:
        return "stream"                    # fifo: push/pop ≈ the stream mode
    if wanted == "hold_b" and "hold_scale" in modes:
        return "hold_scale"                # mxfpmac's weight-stationary mode
    return "random"


def activity_from_stats(
    stats_path: Path,
    description: Mapping[str, Any],
    *,
    mode: str = "windows",
    map_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], int, List[str], List[str], List[str]]:
    """Timeloop stats + ingested description → native §3.3 rows.

    Returns ``(rows, total_cycles, window_labels, warnings, notes)``.
    ``mode="windows"`` emits one window per stats file (cumulative cycle
    offsets); ``mode="aggregate"`` sums everything into one window.
    """
    if mode not in ("windows", "aggregate"):
        raise ValueError(f"stats mode must be 'windows' or 'aggregate', got {mode!r}")

    stats_list = read_stats_input(stats_path)
    level_map, ignore = load_stats_map(map_path) if map_path else ({}, set())

    comps = (description.get("npuwattch") or {}).get("components", [])
    names = [str(c["name"]) for c in comps]
    by_name = {str(c["name"]): c for c in comps}
    mapped_targets = set(level_map.values())
    missing_targets = sorted(t for t in mapped_targets if t not in by_name)
    if missing_targets:
        raise ValueError(
            f"stats map names component(s) not in the description: "
            f"{', '.join(missing_targets)} — description components are "
            f"{', '.join(sorted(names))}")

    try:
        from ..compounds import load_primitive_modes
        modes_by_prim = load_primitive_modes().modes
    except Exception:                       # advisory, as in the vectorless path
        modes_by_prim = {}

    warnings: List[str] = []
    notes: List[str] = []
    unmatched: List[str] = []
    ignored_with_activity: List[str] = []
    mode_fallbacks: Dict[str, str] = {}     # component → charged mode (≠ wanted)
    covered: set = set()

    # windows[i] = {(component, event, mode): count}; parallel cycles list.
    windows: List[Dict[Tuple[str, str, str], float]] = []
    cycles_per_window: List[int] = []
    labels: List[str] = []

    for st in stats_list:
        counts: Dict[Tuple[str, str, str], float] = {}
        for lv in st.levels:
            if not lv.has_activity:
                continue                     # spatial/dummy levels carry nothing
            if lv.name in ignore:
                ignored_with_activity.append(lv.name)
                continue
            target = level_map.get(lv.name)
            if target is None:
                target, cands = _match_component(lv.name, names)
                if target is None:
                    if len(cands) > 1:
                        warnings.append(
                            f"stats level '{lv.name}' is ambiguous in the "
                            f"description ({', '.join(sorted(cands))}) — "
                            f"pick one via --stats-map 'levels:'")
                    else:
                        unmatched.append(lv.name)
                    continue
            comp = by_name[target]
            primitive = primitive_of(str(comp.get("class", "")))
            declared = int(comp.get("count", 1))
            if lv.instances is not None and lv.instances != declared:
                warnings.append(
                    f"stats level '{lv.name}' declares {lv.instances} "
                    f"instance(s) but the description has {declared} for "
                    f"'{target}' — are the stats from this architecture?")
            covered.add(target)

            def _add(event: str, wanted_mode: str, count: float) -> None:
                if count <= 0:
                    return
                charged = _mode_for(primitive, wanted_mode, modes_by_prim)
                if charged != wanted_mode:
                    mode_fallbacks[target] = charged
                key = (target, event, charged)
                counts[key] = counts.get(key, 0.0) + count

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

    # -- provenance -------------------------------------------------------
    n_layers = len(stats_list)
    notes.append(
        f"Timeloop stats: {n_layers} file(s), {total_cycles} cycles, "
        f"{len(covered)}/{len(names)} description component(s) charged "
        f"({mode} mode); compute charged in the weight-stationary mode the "
        f"timeloop projection declares (Computes -> hold_b)")
    if unmatched:
        warnings.append(
            f"stats level(s) with no matching description component: "
            f"{', '.join(sorted(set(unmatched)))} — their activity is NOT "
            f"charged; rename via --stats-map 'levels:' or drop deliberately "
            f"via 'ignore:'")
    if ignored_with_activity:
        notes.append(
            f"stats level(s) dropped by the map's 'ignore:': "
            f"{', '.join(sorted(set(ignored_with_activity)))} — their energy "
            f"is deliberately NOT in this run")
    uncovered = sorted(set(names) - covered)
    if uncovered:
        warnings.append(
            f"{len(uncovered)} description component(s) get no Timeloop "
            f"activity (charged leakage/area only — Timeloop does not model "
            f"them): {', '.join(uncovered)}")
    for target, charged in sorted(mode_fallbacks.items()):
        notes.append(
            f"{target}: charged in the '{charged}' stim mode — the wanted "
            f"mode is not characterized for this primitive")
    return rows, total_cycles, labels, warnings, notes
