"""Parse a TOGSim run log (``togsim_results/*.log``).

The TOGSim log is the primary activity input: its header echoes the full hardware
config as JSON, and its body reports **on-chip** per-core activity. NPUWattch uses
the on-chip rows only (systolic / vector active cycles, COMP GEMM op counts, the
``outputs/<hash>`` pointer); the DRAM/NoC rows are TOGSim's off-chip domain and are
ignored.

Two structural facts (verified against the local-run samples):

- The per-core activity block is reprinted every ``core_stats_print_period_cycles``
  as a **per-period increment**, then a **final cumulative block** is emitted at the
  end. Taking the *last* value reported for each ``(core, systolic-array)`` yields the
  cumulative total (= sum of the increments); likewise for the vector unit per core.
- Each log corresponds to **one compiled kernel**, named by the
  ``.../outputs/<hash>/tile_graph.onnx`` path in the ``Register graph path`` line —
  that hash is the join key to the kernel's ``meta.txt`` / MLIR / ``m5out``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = ["TogsimActivity", "TogsimLogError", "parse_config", "parse_togsim_log"]


class TogsimLogError(ValueError):
    """The TOGSim log is malformed or missing an expected field."""


_HASH = re.compile(r"outputs/([A-Za-z0-9]+)/tile_graph\.onnx")
_SYS = re.compile(
    r"Core \[(\d+)\] : Systolic array \[(\d+)\]\s+utilization\(%\)\s+[\d.]+,\s+"
    r"active_cycles\s+(\d+)"
)
# Vector line has two spellings: periodic "Utilization ... active_cycles N",
# final "utilization ... active cycle N". Capture the count either way.
_VEC = re.compile(
    r"Core \[(\d+)\] : Vector unit\s+[Uu]tilization\(%\)\s+[\d.]+,\s+"
    r"active[ _]cycles?\s+(\d+)"
)
_COMP = re.compile(
    r"Core \[(\d+)\] : COMP\s+inst_count\s+(\d+)\s+\(GEMM:\s+(\d+),\s+Vector:\s+(\d+)\)"
)
_MOV = re.compile(r"Core \[(\d+)\] : (MOVIN|MOVOUT)\s+inst_count\s+(\d+)")
_TOTAL_EXEC = re.compile(r"Total execution cycles:\s+(\d+)")


def parse_config(text: str) -> Dict[str, object]:
    """Extract the ``TOGSim Config: { ... }`` JSON header block."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "TOGSim Config: {" in line:
            start = i
            break
    if start is None:
        raise TogsimLogError("no 'TOGSim Config: {' header found")
    buf = ["{"]
    for line in lines[start + 1:]:
        buf.append(line)
        if line.strip() == "}":
            break
    else:
        raise TogsimLogError("TOGSim Config block not terminated by '}'")
    try:
        return json.loads("\n".join(buf))
    except json.JSONDecodeError as e:
        raise TogsimLogError(f"TOGSim Config is not valid JSON: {e}") from e


@dataclass(frozen=True)
class TogsimActivity:
    kernel_hashes: List[str]
    config: Dict[str, object]
    lanes: int
    num_cores: int
    arrays_per_core: Optional[int]
    core_freq_mhz: Optional[float]
    systolic_active_cycles: int              # summed over cores × arrays (cumulative)
    vector_active_cycles: int                # summed over cores (cumulative)
    comp_gemm_ops: int                       # summed over cores
    comp_vector_ops: int
    total_exec_cycles: Optional[int]
    per_core: Dict[int, Dict[str, object]] = field(default_factory=dict)

    @property
    def primary_hash(self) -> str:
        if len(self.kernel_hashes) != 1:
            raise TogsimLogError(
                f"expected exactly one kernel hash, found {self.kernel_hashes}"
            )
        return self.kernel_hashes[0]


def _as_int(config: Dict[str, object], key: str) -> Optional[int]:
    v = config.get(key)
    return int(v) if isinstance(v, (int, float)) else None


def parse_togsim_log(text: str) -> TogsimActivity:
    config = parse_config(text)
    lanes = _as_int(config, "vpu_num_lanes")
    if lanes is None:
        raise TogsimLogError("config has no integer 'vpu_num_lanes'")
    num_cores = _as_int(config, "num_cores") or 1

    hashes: List[str] = []
    for h in _HASH.findall(text):
        if h not in hashes:
            hashes.append(h)

    # last value per (core, array) / per core = cumulative total.
    sys_last: Dict[tuple, int] = {}
    for m in _SYS.finditer(text):
        sys_last[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    vec_last: Dict[int, int] = {}
    for m in _VEC.finditer(text):
        vec_last[int(m.group(1))] = int(m.group(2))

    comp: Dict[int, tuple] = {}
    for m in _COMP.finditer(text):
        comp[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    mov: Dict[int, Dict[str, int]] = {}
    for m in _MOV.finditer(text):
        mov.setdefault(int(m.group(1)), {})[m.group(2)] = int(m.group(3))

    te = _TOTAL_EXEC.search(text)
    total_exec = int(te.group(1)) if te else None

    per_core: Dict[int, Dict[str, object]] = {}
    core_ids = set(c for c, _ in sys_last) | set(vec_last) | set(comp) | set(mov)
    for c in sorted(core_ids):
        arrays = {a: v for (cc, a), v in sys_last.items() if cc == c}
        g = comp.get(c, (0, 0, 0))
        per_core[c] = {
            "systolic_active_cycles": sum(arrays.values()),
            "arrays": arrays,
            "vector_active_cycles": vec_last.get(c, 0),
            "comp_inst": g[0],
            "comp_gemm_ops": g[1],
            "comp_vector_ops": g[2],
            "movin": mov.get(c, {}).get("MOVIN", 0),
            "movout": mov.get(c, {}).get("MOVOUT", 0),
        }

    return TogsimActivity(
        kernel_hashes=hashes,
        config=config,
        lanes=lanes,
        num_cores=num_cores,
        arrays_per_core=_as_int(config, "num_systolic_array_per_core"),
        core_freq_mhz=(float(config["core_freq_mhz"])
                       if isinstance(config.get("core_freq_mhz"), (int, float)) else None),
        systolic_active_cycles=sum(sys_last.values()),
        vector_active_cycles=sum(vec_last.values()),
        comp_gemm_ops=sum(g[1] for g in comp.values()),
        comp_vector_ops=sum(g[2] for g in comp.values()),
        total_exec_cycles=total_exec,
        per_core=per_core,
    )
