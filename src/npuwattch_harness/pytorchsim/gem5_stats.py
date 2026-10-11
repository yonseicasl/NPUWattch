"""Parse the dump sections of a gem5 ``stats.txt`` file.

A gem5 stats file has one or more ``Begin/End Simulation Statistics``
sections. For PyTorchSim, gem5 runs the **sample program** of the kernel,
not the kernel. The sample program executes each compute node of the tile
graph one time, in file order, and dumps the statistics after each node
(``tile_graph.py``). Thus each section holds the counts of **one execution
of one compute node**, and the last section is the tail of the program.
``system.cpu.numCycles`` of a section is the cycle count that PyTorchSim
gives to that node.

The counts are not kernel totals. ``activity.py`` scales each section by the
number of executions of its node (from the tile graph), or by the COMP
counts of the TOGSim log when the tile graph is not available.

This reader is generic: it gives name → value for each section. A different
gem5 harness can also use it. The selection of the PyTorchSim stats is in
``activity.py``.
"""

from __future__ import annotations

import re
from typing import Dict, List

__all__ = [
    "parse_sections",
    "section_committed_inst",
    "sum_stat",
    "sum_committed_inst",
]

_BEGIN = "Begin Simulation Statistics"
_END = "End Simulation Statistics"
# "<name>  <value>  [cols...]  # comment": the pattern takes the first numeric token.
_STAT = re.compile(r"^(\S+)\s+(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b")
_INST = re.compile(r"committedInstType::(\w+)")


def parse_sections(text: str) -> List[Dict[str, float]]:
    """Divide the text into one ``{stat_name: value}`` dict for each section.

    A file with no ``Begin`` marker is one implicit section. Some gem5
    configurations write a stats block without markers.
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
        code = line.split("#", 1)[0]  # remove the comment at the end of the line
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
    """Sum one stat across all sections. The result is 0.0 if the stat is absent."""
    return float(sum(sec.get(name, 0.0) for sec in sections))


def sum_committed_inst(sections: List[Dict[str, float]]) -> Dict[str, int]:
    """Sum each ``committedInstType::<class>`` stat across the sections.

    Return ``{class_name: total_count}``, for example
    ``{"CustomMatMulwVpush": 71}``. The key is the instruction class name
    without the ``commitStatsN`` prefix.
    """
    totals: Dict[str, int] = {}
    for sec in sections:
        for name, value in sec.items():
            m = _INST.search(name)
            if m:
                cls = m.group(1)
                totals[cls] = totals.get(cls, 0) + int(value)
    return totals


def section_committed_inst(section: Dict[str, float]) -> Dict[str, int]:
    """Return ``{class_name: count}`` of one section (one compute node)."""
    return sum_committed_inst([section])
