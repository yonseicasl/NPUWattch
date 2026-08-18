#!/usr/bin/env python3
"""
qa_sheets.py — sheet-level QA for the SRAM datasets (sanity_bounds.md
section C).  Everything here is a WARN: rows stay in the sheets, the
warnings are for the human before a training run.  Exit code is always 0
unless the sheets are unreadable.

  Q1  toggle-rate linearity: wr_toggle_energy monotonic in n_toggle_cols
      and >= 0.9 x wr_same_energy at every rate
  Q2  node monotonicity at a fixed config: energies/delays should not
      grow (>10%) as the node shrinks 20nm -> 5nm
  Q3  leakage grows with temperature for the same config
  Q4  decoder run-to-run spread <= 20% across PASS runs of one config
      (scans run dirs — the sheet keeps only the latest run)
  Q5  decoder achieved utilization within 2x of the floorplan target
      (reads the run dirs' area.json sidecars)

Usage: qa_sheets.py [--sram-dir <path>]
"""
import argparse
import csv
import glob
import json
import os
import sys

# this file lives in autosweep/; the sram tree (TECH_*nm, datasets/) is up one
SRAM_DEFAULT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NODE_ORDER = ["20nm", "16nm", "10nm", "7nm", "5nm"]  # newest last


def read_csv(path):
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def fnum(row, key):
    try:
        return float(row[key])
    except (KeyError, ValueError, TypeError):
        return None


def q1_toggle_linearity(rows, warn):
    groups = {}
    for r in rows:
        key = (r["node"], r["rows"], r["cols"], r["wd"],
               r["voltage_offset_V"], r["temperature_C"], r["pex"])
        groups.setdefault(key, []).append(r)
    for key, grp in groups.items():
        grp = sorted(grp, key=lambda r: fnum(r, "toggle_rate") or 0)
        prev = None
        for r in grp:
            wt, ws = fnum(r, "wr_toggle_energy_pJ"), fnum(r, "wr_same_energy_pJ")
            nt = fnum(r, "n_toggle_cols")
            if None in (wt, ws, nt):
                continue
            if nt > 0 and wt < 0.9 * ws:
                warn("Q1 %s: wr_toggle=%.4g < 0.9*wr_same=%.4g at "
                     "n_toggle=%g" % (key, wt, ws, nt))
            if prev is not None and nt > prev[0] and wt < prev[1] * 0.98:
                warn("Q1 %s: wr_toggle not monotonic in n_toggle "
                     "(%g cols: %.4g pJ vs %g cols: %.4g pJ)"
                     % (key, prev[0], prev[1], nt, wt))
            prev = (nt, wt)


def q2_node_monotonic(rows, warn):
    metrics = ("rd_1to0_energy_pJ", "wr_toggle_energy_pJ",
               "rd_delay_ns", "wr_delay_ns")
    groups = {}
    for r in rows:
        key = (r["rows"], r["cols"], r["toggle_rate"],
               r["voltage_offset_V"], r["temperature_C"], r["pex"])
        groups.setdefault(key, {})[r["node"]] = r
    for key, by_node in groups.items():
        chain = [n for n in NODE_ORDER if n in by_node]
        for metric in metrics:
            for older, newer in zip(chain, chain[1:]):
                vo, vn = fnum(by_node[older], metric), fnum(by_node[newer], metric)
                if None in (vo, vn):
                    continue
                if vn > 1.10 * vo:
                    warn("Q2 config %s: %s grows %s -> %s "
                         "(%.4g -> %.4g)" % (key, metric, older, newer,
                                             vo, vn))


def q3_leak_vs_temp(rows, warn, leak_key="leak_power_mW"):
    groups = {}
    for r in rows:
        key = tuple(r.get(k, "") for k in
                    ("node", "rows", "cols", "wd", "toggle_rate",
                     "voltage_offset_V", "pex"))
        groups.setdefault(key, []).append(r)
    for key, grp in groups.items():
        grp = sorted(grp, key=lambda r: fnum(r, "temperature_C") or 0)
        for cold, hotr in zip(grp, grp[1:]):
            tc, th = fnum(cold, "temperature_C"), fnum(hotr, "temperature_C")
            lc, lh = fnum(cold, leak_key), fnum(hotr, leak_key)
            if None in (tc, th, lc, lh) or th <= tc:
                continue
            if lh <= lc:
                warn("Q3 %s: %s not increasing with temperature "
                     "(%.0fC: %.4g, %.0fC: %.4g)"
                     % (key, leak_key, tc, lc, th, lh))


def dec_run_dirs(sram_dir):
    for run in sorted(glob.glob(os.path.join(
            sram_dir, "TECH_*nm", "dec_*", "05_sim", "*"))):
        meas_p = os.path.join(run, "measures.csv")
        meta_p = os.path.join(run, "meta.json")
        if not (os.path.isfile(meas_p) and os.path.isfile(meta_p)):
            continue
        m = {}
        with open(meas_p) as f:
            for row in csv.DictReader(f):
                m[row["measure"]] = row["value_si"]
        yield run, json.load(open(meta_p)), m


def q4_dec_spread(sram_dir, warn):
    pops = {}
    for run, meta, m in dec_run_dirs(sram_dir):
        if str(m.get("verdict", "PASS")).startswith("FAIL"):
            continue
        try:
            flip = float(m["e_act_flip_j"])
        except (KeyError, ValueError):
            continue
        key = (meta["node"], meta["rows"], meta["cols"],
               meta.get("voltage_offset_V", 0), meta["temperature_C"],
               meta.get("pex", 1))
        pops.setdefault(key, []).append(flip)
    for key, vals in pops.items():
        if len(vals) < 2:
            continue
        spread = (max(vals) - min(vals)) / max(vals)
        if spread > 0.20:
            warn("Q4 decoder %s: e_act_flip spread %.0f%% across %d PASS "
                 "runs (mixed PnR builds?)" % (key, spread * 100, len(vals)))


def q5_dec_util(sram_dir, warn):
    for area_p in sorted(glob.glob(os.path.join(
            sram_dir, "TECH_*nm", "dec_*", "03_gds", "dec_*.json"))):
        try:
            area = json.load(open(area_p))
            target = float(area["util_target"])
            achieved = float(area["util_achieved"])
        except (ValueError, KeyError, TypeError):
            continue
        if achieved < target / 2.0:
            warn("Q5 %s: util achieved %.3f < half of target %.3f "
                 "(routing trouble?)" % (area_p, achieved, target))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sram-dir", default=SRAM_DEFAULT)
    a = ap.parse_args()
    ds = os.path.join(a.sram_dir, "datasets")
    n_warn = [0]

    def warn(msg):
        n_warn[0] += 1
        print("qa_sheets: WARN %s" % msg)

    arr = read_csv(os.path.join(ds, "sram_array.csv"))
    dec = read_csv(os.path.join(ds, "sram_decoder.csv"))
    if not arr and not dec:
        sys.exit("qa_sheets: no sheets under %s" % ds)
    q1_toggle_linearity(arr, warn)
    q2_node_monotonic(arr, warn)
    q3_leak_vs_temp(arr, warn)
    q3_leak_vs_temp(dec, warn, leak_key="dec_leak_power_mW")
    q4_dec_spread(a.sram_dir, warn)
    q5_dec_util(a.sram_dir, warn)
    print("qa_sheets: %d array + %d decoder sheet rows checked, %d warning(s)"
          % (len(arr), len(dec), n_warn[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
