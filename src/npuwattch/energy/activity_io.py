"""Read the activity table (manual §3.3, ``activity.csv``).

``arch_synth.write_arch`` writes an activity CSV. This module reads such a
file and gives the activity rows that ``energy.aggregate_native`` uses, and
``total_cycles``.

A harness run does not use this module, because the harness has
``EmittedArch.activity_rows`` in memory. The ``-l activity.csv`` path uses
it, for the file of a harness or a file that the user makes.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = ["read_activity_csv"]

# The integer columns of §3.3. The component, event, and mode columns are
# strings.
_INT_COLS = ("window", "cycle_start", "cycle_end")


def _num(value: str) -> float:
    f = float(value)
    return int(f) if f.is_integer() else f


def read_activity_csv(path: Union[str, Path]) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """Read an activity CSV (manual §3.3).

    Return ``(rows, total_cycles)``. ``rows`` are the activity rows.
    ``total_cycles`` comes from the ``__meta__`` row of the file, which is
    not in ``rows``. The function changes the numeric columns into numbers.
    The ``mode`` column is optional.
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
