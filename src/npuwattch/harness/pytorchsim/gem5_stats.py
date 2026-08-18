"""Parse gem5 ``stats.txt`` dump sections.

A gem5 stats file is one or more ``Begin/End Simulation Statistics`` sections,
each a periodic ``m5.stats.dump()`` snapshot. For PyTorchSim the sections are
**per-dump, not cumulative** (``system.cpu.numCycles`` is non-monotonic across
sections), so per-kernel totals are the **sum across a file's sections**.

This reader is deliberately generic (name → value per section) so the roadmap
generic-gem5 harness can reuse it; the PyTorchSim-specific stat selection lives
in ``activity.py``.
"""

from __future__ import annotations

import re
from typing import Dict, List

__all__ = [
    "parse_sections",
    "sum_stat",
    "sum_committed_inst",
]

_BEGIN = "Begin Simulation Statistics"
_END = "End Simulation Statistics"
# "<name>  <value>  [cols...]  # comment" — take the first numeric token.
_STAT = re.compile(r"^(\S+)\s+(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b")
_INST = re.compile(r"committedInstType::(\w+)")


def parse_sections(text: str) -> List[Dict[str, float]]:
    """Split into per-section ``{stat_name: value}`` dicts.

    A file with no ``Begin`` marker is treated as a single implicit section
    (some gem5 configs emit a bare stats block).
    """
    sections: List[Dict[str, float]] = []
    current: Dict[str, float] = {}
    seen_begin = False
    have_current = False

    for line in text.splitlines():
        if _BEGIN in line:
            if have_current:
                sections.append(current)
            current = {}
            have_current = True
            seen_begin = True
            continue
        if _END in line:
            if have_current:
                sections.append(current)
            current = {}
            have_current = False
            continue
        code = line.split("#", 1)[0]  # drop trailing comment
        m = _STAT.match(code)
        if m:
            try:
                current[m.group(1)] = float(m.group(2))
            except ValueError:
                continue
            have_current = True

    if have_current and (current or not seen_begin):
        sections.append(current)
    return sections


def sum_stat(sections: List[Dict[str, float]], name: str) -> float:
    """Sum one stat across all sections (0.0 if never present)."""
    return float(sum(sec.get(name, 0.0) for sec in sections))


def sum_committed_inst(sections: List[Dict[str, float]]) -> Dict[str, int]:
    """Sum every ``committedInstType::<class>`` across sections.

    Returns ``{class_name: total_count}`` (e.g. ``{"CustomMatMulwVpush": 71}``),
    keyed by the bare instruction-class name regardless of the ``commitStatsN``
    prefix.
    """
    totals: Dict[str, int] = {}
    for sec in sections:
        for name, value in sec.items():
            m = _INST.search(name)
            if m:
                cls = m.group(1)
                totals[cls] = totals.get(cls, 0) + int(value)
    return totals
