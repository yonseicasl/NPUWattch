"""Re-derive the syn/pnr timing columns of collected rows from archived reports.

Collector schema 2 read the FIRST 'Critical Path Length'/'Slack' block of each
report_qor. ICC2 prints the auto port-cone groups (``**in2reg_default**`` ...)
before the clock group, so for every clocked design ``pnr_crit_path_ns`` held
the input-delay-bound in2reg cone (~T/2 + one gate) instead of the reg2reg path,
and ``pnr_wns_ns``/``pnr_tns_ns``/``pnr_violating_paths`` described that group
only. Schema 3 (autocollect._qor_timing) spans all groups.

The sweep deletes run directories after collection, but the report texts it
needs survive in ``../sweep_reports/<run_id>.reports.tar.gz``
(``01_syn/synthesis.log`` + ``02_pnr/qor.rpt``). This script re-parses them and
rewrites ONLY the timing columns (+ ``collector_schema``) of every row whose
flow_run_id has an archive, adding the schema-3 ``pnr_min_period_ns`` /
``pnr_crit_group`` columns after ``pnr_violating_paths``; power/area/cell
columns are left byte-identical.

Usage:
    python3 recollect_timing.py            # dry run: per-component change summary
    python3 recollect_timing.py --write    # back up each CSV, then rewrite it
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from autocollect import (
    COLLECTOR_SCHEMA_VERSION,
    DATASETS_DIR,
    ReportParseError,
    _qor_timing,
    _section,
)

REPORTS_DIR = DATASETS_DIR.parent / "sweep_reports"

NEW_COLUMNS = ("pnr_min_period_ns", "pnr_crit_group")


def _member_text(tar: tarfile.TarFile, run_id: str, rel: str) -> str | None:
    try:
        fp = tar.extractfile(f"{run_id}/{rel}")
    except KeyError:
        return None
    return None if fp is None else fp.read().decode("utf-8", errors="replace")


def timing_from_archive(run_id: str) -> dict[str, float | int]:
    """The schema-3 syn_*/pnr_* timing fields of one archived run."""
    path = REPORTS_DIR / f"{run_id}.reports.tar.gz"
    out: dict[str, float | int] = {}
    with tarfile.open(path) as tar:
        syn = _member_text(tar, run_id, "01_syn/synthesis.log")
        pnr = _member_text(tar, run_id, "02_pnr/qor.rpt")
    if syn is None or pnr is None:
        raise ReportParseError(f"{path}: synthesis.log or qor.rpt not archived")
    syn_qor = _section(syn, "Report : qor", source=path)
    for prefix, text in (("syn", syn_qor), ("pnr", pnr)):
        for key, value in _qor_timing(text, source=path).items():
            if prefix == "syn" and key in ("min_period_ns", "crit_group"):
                continue                    # as parse_syn_reports
            out[f"{prefix}_{key}"] = value
    return out


def _safe(run_id: str):
    try:
        return run_id, timing_from_archive(run_id), None
    except (OSError, tarfile.TarError, ReportParseError) as exc:
        return run_id, None, str(exc)


def _fmt(value) -> str:
    return "" if value is None else str(value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="rewrite the CSVs (default: dry run)")
    ap.add_argument("--jobs", type=int, default=16)
    args = ap.parse_args()

    csvs = sorted(DATASETS_DIR.glob("logic_*.csv"))
    tables: dict[Path, tuple[list[str], list[dict[str, str]]]] = {}
    run_ids: set[str] = set()
    for path in csvs:
        with path.open(newline="", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            rows = list(reader)
            tables[path] = (list(reader.fieldnames or []), rows)
        run_ids.update(r["flow_run_id"] for r in rows)

    archived = {rid for rid in run_ids
                if (REPORTS_DIR / f"{rid}.reports.tar.gz").exists()}
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(_safe, sorted(archived), chunksize=32))
    timing = {rid: t for rid, t, err in results if t is not None}
    errors = [(rid, err) for rid, t, err in results if t is None]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for path, (fieldnames, rows) in tables.items():
        for col in NEW_COLUMNS:
            if col not in fieldnames:
                at = fieldnames.index("pnr_violating_paths") + 1
                fieldnames.insert(at + NEW_COLUMNS.index(col), col)
        changed = unarchived = 0
        rel_moves: list[float] = []
        for row in rows:
            new = timing.get(row["flow_run_id"])
            if new is None:
                unarchived += 1
                continue
            old_crit = float(row["pnr_crit_path_ns"] or "nan")
            if any(_fmt(new[k]) != row.get(k, "") for k in new):
                changed += 1
            if old_crit > 0 and new["pnr_min_period_ns"] is not None:
                rel_moves.append(new["pnr_min_period_ns"] / old_crit)
            for k, v in new.items():
                row[k] = _fmt(v)
            row["collector_schema"] = COLLECTOR_SCHEMA_VERSION
        rel_moves.sort()
        med = rel_moves[len(rel_moves) // 2] if rel_moves else float("nan")
        print(f"{path.name:24s} rows {len(rows):5d}  timing changed {changed:5d}  "
              f"no archive {unarchived:3d}  median min_period/old crit {med:5.2f}")
        if args.write:
            shutil.copy2(path, path.with_name(f"{path.name}.bak_schema2_{stamp}"))
            with path.open("w", newline="", encoding="utf-8") as fp:
                writer = csv.DictWriter(fp, fieldnames=fieldnames, restval="")
                writer.writeheader()
                writer.writerows(rows)

    for rid, err in errors:
        print(f"[ERROR] {rid}: {err}", file=sys.stderr)
    print(f"{len(timing)} archived runs parsed, {len(errors)} errors"
          + ("" if args.write else " (dry run — pass --write to apply)"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
