"""Division of the activity of a window between the physical instances.

The TOGSim log gives the systolic activity of each systolic array and some
counters of each core. But the projection binds stats that are totals for the
chip. One ``systolic.pe`` component for all PE grids would hide the detail of
the log. Thus the emitter names one component for each physical instance
(``core0.array1.pe``, ``core1.vmem``, ...). This module divides the bound
actions of each window between those instances.

A division is exact if the log has a counter for each instance. If the log has
only a total for the kernel, the division is in proportion to a related
counter, and the module gives a message. The rules are:

* Elements with ``per: array`` (the systolic ``pe`` and ``w_reg``): the share
  of each array is its fraction of the active cycles.

  * An action that ``systolic_active_cycles`` drives uses the same counter.
    This division is exact.
  * A gem5 total for the kernel (the ``CustomMatMulwVpush`` weight loads) is
    in proportion to that share.

* Elements with ``per: core``: the share comes from a counter of each core.

  * ``dram_read_bytes`` (DRAM to VMEM): the MOVIN instruction counts.
  * ``dram_write_bytes`` (VMEM to DRAM): the MOVOUT instruction counts.
  * ``vector_active_cycles``: the same counter of each core (exact).
  * ``dram_requests`` (the events of the DMA engine): the DMA response
    counts (exact).
  * SFU operation counts (``CustomV*``): the vector active cycles.
  * All other stats (for example, the ``vpu_spad`` vector traffic): the
    systolic active cycles.

* Elements with ``per: chip`` (the NoC): no division. The log has only total
  flit counts, thus there is no data for a division between the routers.

If all the counters for a division are zero in a window, the module divides
the activity equally and gives a message. An instance with a share of zero
gets no activity row. The description still gives its leakage, as for each
idle component.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .activity import BoundAction, _num

__all__ = ["expand_bounds"]

#: For each stat that drives an action: the counter that gives the share of
#: each core, and a message. A stat that is not in this table uses "systolic".
#: A message of None means that the division is exact. A run shows each
#: message one time.
_SFU_NOTE = "SFU ops attributed per core by vector active-cycle share"
_CORE_RULES: Dict[str, Tuple[str, str]] = {
    "dram_read_bytes": ("movin",
                        "DRAM→VMEM fill attributed per core by MOVIN instruction share"),
    "dram_write_bytes": ("movout",
                         "VMEM→DRAM drain attributed per core by MOVOUT instruction share"),
    "vector_active_cycles": ("vector", None),
    # Events of the DMA engine. The division is exact. The last DMA line of
    # each core in the log gives the total response count of that core. One
    # response is one request.
    "dram_requests": ("dma", None),
    # The SFU operation counts are gem5 totals for the kernel. The SFU is a
    # part of the VPU. Thus the division is in proportion to the vector
    # active cycles of each core.
    "CustomVexp": ("vector", _SFU_NOTE),
    "CustomVexp2": ("vector", _SFU_NOTE),
    "CustomVerf": ("vector", _SFU_NOTE),
    "CustomVtanh": ("vector", _SFU_NOTE),
    "CustomVsin": ("vector", _SFU_NOTE),
    "CustomVcos": ("vector", _SFU_NOTE),
}
_DEFAULT_CORE_RULE: Tuple[str, str] = (
    "systolic", "attributed per core by systolic active-cycle share")

_CORE_STAT_KEY = {
    "systolic": "systolic_active_cycles",
    "vector": "vector_active_cycles",
    "movin": "movin",
    "movout": "movout",
    "dma": "dma_responses",
}


class _WindowShares:
    """The shares of the instances in one window.

    The class calculates each share from the counters of each core in the
    log, at the first time that the caller asks for it.
    """

    def __init__(self, per_core: Mapping[int, Mapping[str, Any]],
                 num_cores: int, arrays_per_core: int) -> None:
        self._pc = per_core or {}
        self._C = max(1, num_cores)
        self._A = max(1, arrays_per_core)
        self.notes: List[str] = []
        self._cache: Dict[str, Dict] = {}

    def array(self) -> Dict[Tuple[int, int], float]:
        m = self._cache.get("array")
        if m is None:
            vals: Dict[Tuple[int, int], float] = {}
            for c in range(self._C):
                arrays = (self._pc.get(c) or {}).get("arrays") or {}
                for a in range(self._A):
                    vals[(c, a)] = float(arrays.get(a, 0) or 0)
            m = self._cache["array"] = self._normalize(vals, "per-array active cycles")
        return m

    def core(self, kind: str) -> Dict[int, float]:
        key = f"core:{kind}"
        m = self._cache.get(key)
        if m is None:
            stat_key = _CORE_STAT_KEY[kind]
            vals = {c: float((self._pc.get(c) or {}).get(stat_key, 0) or 0)
                    for c in range(self._C)}
            if sum(vals.values()) <= 0 and kind != "systolic":
                self.notes.append(
                    f"no per-core {stat_key} counters; falling back to the "
                    f"systolic active-cycle share")
                m = dict(self.core("systolic"))
            else:
                m = self._normalize(vals, f"per-core {stat_key}")
            self._cache[key] = m
        return m

    def _normalize(self, vals: Dict, what: str) -> Dict:
        total = sum(vals.values())
        if total > 0:
            return {k: v / total for k, v in vals.items()}
        if len(vals) > 1:
            self.notes.append(f"{what}: all zero in this window; split uniformly")
        return {k: 1.0 / len(vals) for k in vals}


def expand_bounds(
    window: Any,
    bounds: Sequence[BoundAction],
    per_by_element: Mapping[str, str],
    *,
    num_cores: int,
    arrays_per_core: int,
) -> Tuple[List[BoundAction], List[str]]:
    """Divide the bound actions of a window between the physical instances.

    Each pair of action and element gives one ``BoundAction`` for each
    instance that has a share larger than zero. The element name becomes the
    component name of the instance (``core{c}.array{a}.{element}`` or
    ``core{c}.{element}``). An element with ``per: chip`` does not change.

    Return the new list and the messages about the division. The caller
    removes the messages that occur again in other windows.
    """
    C, A = max(1, num_cores), max(1, arrays_per_core)
    shares = _WindowShares(getattr(window, "per_core", None) or {}, C, A)
    out: List[BoundAction] = []
    notes: List[str] = []
    for ba in bounds:
        for rae in ba.elements:
            domain = per_by_element.get(rae.element, "chip")
            if domain == "chip":
                out.append(replace(ba, elements=[rae]))
                continue
            if domain == "array":
                smap = shares.array()
                # Give a message only if there is more than one array.
                if ba.stat != "systolic_active_cycles" and C * A > 1:
                    notes.append(
                        f"{ba.stat}: kernel-total events attributed per array "
                        f"in proportion to each array's active cycles")
                pieces = [(f"core{c}.array{a}.{rae.element}", smap[(c, a)])
                          for c in range(C) for a in range(A)]
            else:                                                  # per: core
                kind, note = _CORE_RULES.get(ba.stat, _DEFAULT_CORE_RULE)
                smap = shares.core(kind)
                if note and C > 1:
                    notes.append(f"{ba.stat}: {note}")
                pieces = [(f"core{c}.{rae.element}", smap[c]) for c in range(C)]
            for qname, s in pieces:
                cyc = ba.cycle_count * s
                if not cyc:
                    continue        # idle instance: only leakage, no activity row
                out.append(replace(ba, cycle_count=_num(cyc),
                                   elements=[replace(rae, element=qname)]))
    return out, notes + shares.notes
