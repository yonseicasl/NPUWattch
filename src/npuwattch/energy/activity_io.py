"""Read the native activity table (§3.3 ``activity.csv``, incl. the ``mode`` column).

The counterpart to ``arch_synth.write_arch``: turns a native activity CSV back into
the row dicts + ``total_cycles`` that ``energy.aggregate_native`` consumes. The
harness path skips this (it has ``EmittedArch.activity_rows`` in memory); this reader
serves the direct ``-l activity.csv`` path and any user-supplied activity table.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = ["read_activity_csv"]

# §3.3 numeric columns to coerce (strings for component/event/mode stay as-is).
_INT_COLS = ("window", "cycle_start", "cycle_end")


def _num(value: str) -> float:
    f = float(value)
    return int(f) if f.is_integer() else f


def read_activity_csv(path: Union[str, Path]) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """Parse a native §3.3 activity CSV.

    Returns ``(rows, total_cycles)`` where ``rows`` are the activity rows (the
    ``__meta__`` total_cycles row is pulled out into ``total_cycles``). Numeric
    columns are coerced; ``mode`` is optional (older §3.3 files omit it).
    """
    rows: List[Dict[str, Any]] = []
    total_cycles: Optional[int] = None

    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            component = (raw.get("component") or "").strip()
            if component == "__meta__":
                if (raw.get("event") or "").strip() == "total_cycles" and raw.get("count"):
                    total_cycles = int(_num(raw["count"]))
                continue
            row: Dict[str, Any] = {
                "component": component,
                "event": (raw.get("event") or "").strip(),
                "mode": (raw.get("mode") or "").strip() or None,
            }
            for col in _INT_COLS:
                if raw.get(col) not in (None, ""):
                    row[col] = int(_num(raw[col]))
            if raw.get("count") not in (None, ""):
                row["count"] = _num(raw["count"])
            rows.append(row)

    return rows, total_cycles
