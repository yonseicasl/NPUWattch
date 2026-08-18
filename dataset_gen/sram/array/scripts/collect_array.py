#!/usr/bin/env python3
"""
collect_array.py — build the SRAM array results log sheet from run dirs.

Scans TECH_*nm/array_*/03_sim/*/ for meta.json + measures.csv (+ area.json
from gen_array.py), keeps the LATEST run per configuration key, and
(re)writes the sheet — deterministic and idempotent, safe to re-run after
any batch.

One row per (node, transistor, corner, voltage_offset_V, temperature_C,
rows, cols, wd, toggle_rate, pex).  Energies are the four dataset targets
plus the two aux ops, all raw op-window integrals: each includes the
leakage flowing during its 10 ns window, and leak_power_mW is recorded
separately for every node INCLUDING 5nm — no baseline subtraction is done
here; downstream consumers subtract P_leak*10ns themselves if they want
pure dynamic energy.

A run with a missing/failed measure is a hard error (silent zeros are
worse than a crashed collect); use --skip-bad to warn and drop instead.

Usage:
  collect_array.py [--sram-dir ../..]
                   [-o <sram>/datasets/sram_array.csv] [--skip-bad]
"""
import argparse
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

ENERGY_COLS = [  # measures.csv key (J) -> sheet column (pJ)
    ("e_wr_same_j", "wr_same_energy_pJ"),
    ("e_wr_toggle_j", "wr_toggle_energy_pJ"),
    ("e_rd_1to1_j", "rd_1to1_energy_pJ"),
    ("e_rd_1to0_j", "rd_1to0_energy_pJ"),
    ("e_wr1_init_j", "wr1_init_energy_pJ"),
    ("e_wr0_fill_j", "wr0_fill_energy_pJ"),
]
DELAY_COLS = [  # measures.csv key (s) -> sheet column (ns); far column,
    ("t_rd_wl_out", "rd_delay_ns"),      # worst-case wordline RC
    ("t_rd_bl_dev", "rd_bl_dev_ns"),
    ("t_rd_sense", "rd_sense_ns"),       # <0: cell beat the sense amp
    ("t_wr_total", "wr_delay_ns"),
    ("t_wr_bl", "wr_bl_ns"),
    ("t_wr_cell", "wr_cell_ns"),
]
FIELDS = ["node", "transistor", "corner", "voltage_offset_V", "vdd_V",
          "temperature_C", "rows", "cols", "wd", "toggle_rate",
          "n_toggle_cols", "pex",
          "wr_same_energy_pJ", "wr_toggle_energy_pJ",
          "rd_1to1_energy_pJ", "rd_1to0_energy_pJ",
          "wr1_init_energy_pJ", "wr0_fill_energy_pJ",
          "leak_power_mW",
          "rd_delay_ns", "rd_bl_dev_ns", "rd_sense_ns",
          "wr_delay_ns", "wr_bl_ns", "wr_cell_ns",
          "width_um", "height_um", "total_area_um2", "flow_run_id"]


def load_measures(path):
    out = {}
    with open(path) as f:
        for rec in csv.DictReader(f):
            v = rec["value_si"]
            try:
                out[rec["measure"]] = float(v) if v else None
            except ValueError:
                out[rec["measure"]] = v  # non-numeric row, e.g. verdict
    return out


def collect_run(run_dir, problems):
    meta_p = os.path.join(run_dir, "meta.json")
    meas_p = os.path.join(run_dir, "measures.csv")
    area_p = os.path.join(run_dir, "area.json")
    if not (os.path.isfile(meta_p) and os.path.isfile(meas_p)):
        return None  # not a completed array run (old col run, crashed, ...)
    meta = json.load(open(meta_p))
    meas = load_measures(meas_p)

    # runs whose functional/range checks failed carry a FAIL verdict from
    # array_measures.py (values are kept for debugging, never collected)
    verdict = meas.get("verdict")
    if isinstance(verdict, str) and verdict.startswith("FAIL"):
        print("collect_array: skip (verdict %s): %s"
              % (verdict.split(";")[0][:60], run_dir), file=sys.stderr)
        return None

    row = {
        "node": meta["node"], "transistor": meta.get("transistor", "hp"),
        "corner": meta.get("corner", "TT"),
        "voltage_offset_V": meta.get("voltage_offset_V", 0.0),
        "vdd_V": meta["vdd_V"], "temperature_C": meta["temperature_C"],
        "rows": meta["rows"], "cols": meta["cols"], "wd": meta["wd"],
        "toggle_rate": round(float(meta["toggle_rate"]), 6),
        "n_toggle_cols": meta["n_toggle"], "pex": meta.get("pex", 1),
        "flow_run_id": meta["flow_run_id"],
    }
    for key, col in ENERGY_COLS:
        v = meas.get(key)
        if v is None:
            problems.append("%s: %s missing/failed" % (run_dir, key))
            return None
        row[col] = round(v * 1e12, 6)
    leak = meas.get("p_leak_w")
    if leak is None:
        problems.append("%s: p_leak_w missing/failed" % run_dir)
        return None
    # record raw at every node (incl. 5nm); 6 sig figs kills float-repr noise
    row["leak_power_mW"] = float("%.6g" % (leak * 1e3))

    for key, col in DELAY_COLS:
        v = meas.get(key)
        if v is None:
            problems.append("%s: %s missing/failed (rerun the job — the run "
                            "predates the delay measures)" % (run_dir, key))
            return None
        row[col] = round(v * 1e9, 6)

    if os.path.isfile(area_p):
        area = json.load(open(area_p))
        row["width_um"] = area["width_um"]
        row["height_um"] = area["height_um"]
        row["total_area_um2"] = area["total_area_um2"]
    else:
        problems.append("%s: no area.json (regenerate array with current "
                        "gen_array.py)" % run_dir)
        return None
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sram-dir",
                    default=os.path.join(HERE, "..", ".."))
    ap.add_argument("-o", "--out",
                    default=os.path.join(HERE, "..", "..", "datasets",
                                         "sram_array.csv"))
    ap.add_argument("--skip-bad", action="store_true",
                    help="warn and drop incomplete runs instead of failing")
    a = ap.parse_args()

    problems = []
    best = {}  # config key -> row (latest flow_run_id wins)
    run_dirs = sorted(glob.glob(os.path.join(a.sram_dir, "TECH_*nm",
                                             "array_*", "03_sim", "*")))
    n_runs = 0
    for rd in run_dirs:
        row = collect_run(rd, problems)
        if row is None:
            continue
        n_runs += 1
        key = tuple(row[k] for k in
                    ("node", "transistor", "corner", "voltage_offset_V",
                     "temperature_C", "rows", "cols", "wd", "toggle_rate",
                     "pex"))
        if key not in best or row["flow_run_id"] > best[key]["flow_run_id"]:
            best[key] = row

    if problems:
        for p in problems:
            print("collect_array: %s: %s"
                  % ("WARN" if a.skip_bad else "ERROR", p), file=sys.stderr)
        if not a.skip_bad:
            sys.exit(1)

    rows = sorted(best.values(),
                  key=lambda r: (int(r["node"].rstrip("nm")), r["rows"],
                                 r["cols"], r["wd"], r["toggle_rate"],
                                 r["pex"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("collect_array: %d run(s) -> %d unique config(s) -> %s"
          % (n_runs, len(rows), a.out))


if __name__ == "__main__":
    main()
