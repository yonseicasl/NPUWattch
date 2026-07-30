#!/usr/bin/env python3
"""Build (and optionally apply) the leakage re-extraction list.

Background (2026-07-29, see 2026_0617/LEAKAGE_RECHAR_REPORT_20260729.md):
BUF_X32 (16/20nm) and OR2_X4 (20/16/10/7nm) carry leakage_power tables that
are 3-4 decades too high, so dataset leakage ground truth is corrupted for

  * EVERY design at 16nm and 20nm (BUF_X32 is a CTS cell; the sub-cut rows
    are still mildly contaminated -- a per-row filter cannot save the node), and
  * the 7/10nm designs whose synthesis picked OR2_X4 (detected per row as a
    leak-per-cell outlier vs the node's clean population).

Because run dirs are pruned after collection, leakage cannot be re-measured
in isolation: affected designs must re-run the whole flow. The sweep skips a
job when its dataset rows are complete (autosweeprun._collected_modes), so
deleting a design's rows is exactly what schedules it for re-run.

Usage (AFTER the libraries are fixed -- re-running against the current libs
just reproduces the corruption):

  python3 gen_leakage_rerun.py            # dry run: summary + rerun_leakage.list
  python3 gen_leakage_rerun.py -go        # also wipe the listed rows (with backup)

The sweep MUST be stopped before -go (it appends to the same CSVs).
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[1] / "datasets"
LIST_PATH = Path(__file__).resolve().parent / "rerun_leakage.list"

#: nodes whose leakage is untrustworthy wholesale (BUF_X32 corruption + the
#: 6-30x sub-cut continuum) -- every design re-runs.
FULL_RERUN_NODES = {16, 20}
#: nodes screened per design for OR2_X4 hits (5nm is clean, never listed).
SCREENED_NODES = {7, 10}
#: outlier cut in decades above the node's p10 leak-per-cell anchor. Wider
#: (lower) than train_logic's 1.5 training quarantine on purpose: missing a
#: mildly-hit design here bakes bad ground truth into v2.
DEFAULT_DEX = 1.0
#: 5nm-control residual cut (decades): r = (lpc - node med) - (same-arch 5nm
#: delta). 2026-07-30 stats: clean bulk <= +0.15 (post-fix sd 0.02-0.03),
#: contamination >= +0.28, the gap in between is EMPTY -> 0.25 sits in it.
RESID_CUT = 0.25
#: within-design across-mode leakage ratio cut. State-dependent corruption
#: makes leakage swing with stimulus; clean designs are flat (q95 <= 1.24,
#: contaminated up to 9.4x). Insensitive for 2-mode components by nature.
SPREAD_CUT = 1.5


def node_nm(value: str) -> int:
    m = re.search(r"(\d+)", value or "")
    if not m:
        raise ValueError(f"cannot parse node {value!r}")
    return int(m.group(1))


def p10(values: list[float]) -> float:
    v = sorted(values)
    return v[max(0, int(0.10 * len(v)) - 1)] if len(v) > 1 else v[0]


def leak_per_cell_log10(row: dict[str, str]) -> float | None:
    try:
        leak = float(row["leak_power_mW"])
        cells = float(row["pnr_total_cells"])
    except (KeyError, TypeError, ValueError):
        return None
    if leak <= 0 or cells <= 0:
        return None
    return math.log10(leak / cells)


def scan_component(path: Path, dex: float,
                   before: str | None) -> tuple[dict[str, str], dict[str, int]]:
    """-> ({flow_run_id: reason}, per-node row counts) for one dataset CSV.

    With ``before`` (ISO timestamp), only rows collected before it are
    eligible -- post-fix re-collections are never flagged or wiped. The
    outlier anchor still uses ALL rows (the clean population dominates).
    """
    with path.open(newline="", encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))

    def eligible(row: dict[str, str]) -> bool:
        return before is None or row.get("collected_at", "") < before

    rerun: dict[str, str] = {}
    node_rows: dict[str, int] = {}
    per_node_lpc: dict[int, list[float]] = {}
    # per-design views for the 5nm-control and mode-spread detectors
    designs: dict[str, dict] = {}

    for row in rows:
        nm = node_nm(row["node"])
        node_rows[f"{nm}nm"] = node_rows.get(f"{nm}nm", 0) + 1
        if nm in FULL_RERUN_NODES:
            if eligible(row):
                rerun[row["flow_run_id"]] = f"{nm}nm (node-wide BUF_X32 corruption)"
        if nm in SCREENED_NODES or nm == 5:
            d = designs.setdefault(row["flow_run_id"], {
                "nm": nm, "arch": row["arch_params"],
                "eligible": eligible(row), "leaks": [], "lpc": None})
            try:
                leak = float(row["leak_power_mW"])
                if leak > 0:
                    d["leaks"].append(leak)
            except (KeyError, TypeError, ValueError):
                pass
            if row.get("stim_mode") in ("", "none", None):
                d["lpc"] = leak_per_cell_log10(row)
            if nm in SCREENED_NODES and d["lpc"] is not None:
                per_node_lpc.setdefault(nm, []).append(d["lpc"])

    anchors = {nm: p10(v) for nm, v in per_node_lpc.items() if v}
    node_med = {nm: sorted(v)[len(v) // 2]
                for nm, v in per_node_lpc.items() if v}
    lpc5 = [d["lpc"] for d in designs.values() if d["nm"] == 5 and d["lpc"] is not None]
    med5 = sorted(lpc5)[len(lpc5) // 2] if lpc5 else None
    arch_d5: dict[str, list[float]] = {}
    if med5 is not None:
        for d in designs.values():
            if d["nm"] == 5 and d["lpc"] is not None:
                arch_d5.setdefault(d["arch"], []).append(d["lpc"] - med5)

    for rid, d in designs.items():
        nm = d["nm"]
        if nm not in SCREENED_NODES or not d["eligible"]:
            continue
        lpc = d["lpc"]
        if lpc is not None and nm in anchors and lpc > anchors[nm] + dex:
            rerun.setdefault(rid, f"{nm}nm leak/cell outlier "
                             f"({lpc:.2f} > {anchors[nm]:.2f}+{dex:g}, OR2_X4 suspect)")
            continue
        if lpc is not None and d["arch"] in arch_d5 and nm in node_med:
            d5 = arch_d5[d["arch"]]
            resid = (lpc - node_med[nm]) - sum(d5) / len(d5)
            if resid > RESID_CUT:
                rerun.setdefault(rid, f"{nm}nm 5nm-control residual +{resid:.2f} "
                                 f"(> {RESID_CUT:g}, OR2_X4 suspect)")
                continue
        if len(d["leaks"]) >= 2 and max(d["leaks"]) / min(d["leaks"]) > SPREAD_CUT:
            rerun.setdefault(rid, f"{nm}nm mode-spread "
                             f"{max(d['leaks']) / min(d['leaks']):.2f}x "
                             f"(> {SPREAD_CUT:g}, state-dependent corruption)")
    return rerun, node_rows


def wipe(path: Path, run_ids: set[str], before: str | None) -> int:
    with path.open(newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        fields = reader.fieldnames or []
        keep, dropped = [], 0
        for row in reader:
            if (row.get("flow_run_id") in run_ids
                    and (before is None or row.get("collected_at", "") < before)):
                dropped += 1
            else:
                keep.append(row)
    if not dropped:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    shutil.copy2(path, path.with_suffix(f".csv.bak_leakagewipe_{stamp}"))
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(keep)
    return dropped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-go", action="store_true",
                    help="wipe listed rows from the dataset CSVs (default: dry run)")
    ap.add_argument("-dex", type=float, default=DEFAULT_DEX,
                    help=f"7/10nm outlier cut in decades (default {DEFAULT_DEX})")
    ap.add_argument("-before", default=None, metavar="ISO_UTC",
                    help="only rows collected before this timestamp are "
                         "flagged/wiped (use the lib-fix install time for "
                         "second-pass sweeps; post-fix rows are never touched)")
    args = ap.parse_args()

    datasets = sorted(DATASET_DIR.glob("logic_*.csv"))
    if not datasets:
        sys.exit(f"no datasets under {DATASET_DIR}")

    all_rerun: dict[str, str] = {}
    per_component: dict[str, dict[str, str]] = {}
    for path in datasets:
        comp = path.stem.replace("logic_", "")
        rerun, node_rows = scan_component(path, args.dex, args.before)
        per_component[comp] = rerun
        all_rerun.update(rerun)
        wholesale = sum(1 for r in rerun.values() if "node-wide" in r)
        print(f"[{comp}] designs to re-run: {len(rerun)} "
              f"(16/20nm wholesale: {wholesale}, "
              f"7/10nm OR2_X4 suspects: {len(rerun) - wholesale})  rows/node: {node_rows}")

    LIST_PATH.write_text("".join(
        f"{rid}\t{reason}\n" for rid, reason in sorted(all_rerun.items())))
    print(f"\n{len(all_rerun)} designs total -> {LIST_PATH}")

    if not args.go:
        print("dry run -- pass -go to wipe these rows (stop the sweep first; "
              "only wipe once the fixed libraries are installed)")
        return 0

    for path in datasets:
        comp = path.stem.replace("logic_", "")
        dropped = wipe(path, set(per_component[comp]), args.before)
        print(f"[{comp}] wiped {dropped} rows "
              f"(backup: {path.name}.bak_leakagewipe_*)" if dropped
              else f"[{comp}] nothing to wipe")
    print("done -- next sweep invocation re-runs exactly the wiped designs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
