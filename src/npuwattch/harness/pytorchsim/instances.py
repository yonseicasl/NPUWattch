"""Per-instance activity split — never lump instances into one component.

PyTorchSim's TOGSim log reports systolic activity per (core, systolic array)
and several counters per core, but the projection binds chip-aggregate stats.
Collapsing every PE grid into a single ``systolic.pe`` component would average
that detail away, so the emitter names one component per physical instance
(``core0.array1.pe``, ``core1.vmem``, …) and this module splits each window's
bound actions across those instances (user decision 2026-07-21: report at the
finest grain the log supports).

Split rules — exact where the log carries a per-instance counter, proportional
attribution (noted in the emitted warnings) where it carries only kernel
totals:

* ``per: array`` elements (systolic ``pe`` / ``w_reg``) — split by each
  array's share of active cycles. For actions driven by
  ``systolic_active_cycles`` the share is computed from that very counter, so
  the split is exact; gem5 kernel totals (``CustomMatMulwVpush`` weight loads)
  are attributed proportionally.
* ``per: core`` elements — DRAM→VMEM fill bytes by the per-core MOVIN
  instruction share, VMEM→DRAM drain bytes by the MOVOUT share,
  ``vector_active_cycles`` by its own per-core counter (exact),
  ``dram_requests`` (DMA engine events) by the per-core DMA response counter
  (exact), SFU op counts (``CustomV*``) by the vector active-cycle share;
  everything else (``vpu_spad`` vector traffic) by the per-core systolic share.
* ``per: chip`` elements (the NoC) are not split — the log only carries
  aggregate flit counts, so per-router attribution would be invented detail.

A window whose split counters are all zero falls back to a uniform split with
a note; an instance whose share is zero simply gets no activity row (its
leakage is still charged from the description, like any idle component).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .activity import BoundAction

__all__ = ["expand_bounds"]

#: per-core share source per driving stat; anything unlisted uses "systolic".
#: The note (None = exact, no attribution assumption) is surfaced once per run.
_SFU_NOTE = "SFU ops attributed per core by vector active-cycle share"
_CORE_RULES: Dict[str, Tuple[str, str]] = {
    "dram_read_bytes": ("movin",
                        "DRAM→VMEM fill attributed per core by MOVIN instruction share"),
    "dram_write_bytes": ("movout",
                         "VMEM→DRAM drain attributed per core by MOVOUT instruction share"),
    "vector_active_cycles": ("vector", None),
    # DMA engine events: exact — the log's final DMA line per core carries that
    # core's cumulative response (= request) count.
    "dram_requests": ("dma", None),
    # SFU op counts are gem5 kernel totals; the SFU lives on the VPU side, so
    # attribute by each core's vector active-cycle share (proportional, noted).
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


def _num(x: float) -> float:
    return int(x) if float(x).is_integer() else x


class _WindowShares:
    """Lazy share vectors for one window, computed from its per-core block."""

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
    """Split a window's bound actions across physical instances.

    Each (action, element) pair becomes one BoundAction per instance whose
    share is nonzero, with the element renamed to its instance-qualified
    component name (``core{c}.array{a}.{element}`` / ``core{c}.{element}``).
    ``per: chip`` elements pass through unchanged. Returns the expanded list
    plus attribution/fallback notes (the caller dedupes across windows).
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
                # a note only when attribution actually distributes something
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
                    continue        # idle instance: leakage-only, no event row
                out.append(replace(ba, cycle_count=_num(cyc),
                                   elements=[replace(rae, element=qname)]))
    return out, notes + shares.notes
