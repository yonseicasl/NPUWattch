#!/usr/bin/env python3
"""
array_measures.py — parse the HSPICE .mt0 of an array TB run, pretty-print
the four dataset energies (+aux), evaluate per-column pass/fail, and write
measures.csv.  Used by run_array.sh; collect_array.py reuses the CSV.

Exits 1 when any functional check fails or a measure is missing/failed —
a silent zero in the dataset is worse than a crashed run.

Usage: array_measures.py <file.mt0> --vdd <V> -o measures.csv
"""
import argparse
import csv
import re
import sys

from col_measures import parse_mt0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mt0")
    ap.add_argument("--vdd", type=float, required=True)
    ap.add_argument("--rows", type=int, default=0,
                    help="bitcells per column; with --cols enables the "
                         "cell-scaled leakage ceiling (bound A2)")
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("-o", "--out", default="measures.csv")
    a = ap.parse_args()
    m = parse_mt0(a.mt0)
    V = a.vdd
    problems = []

    energies = [("e_wr1_init_j", "write 1 init (aux)"),
                ("e_rd_1to1_j", "READ precharge 1->1"),
                ("e_wr_same_j", "WRITE same value"),
                ("e_wr_toggle_j", "WRITE toggle"),
                ("e_wr0_fill_j", "write 0 fill (aux)"),
                ("e_rd_1to0_j", "READ precharge 1->0")]
    print("%-22s%12s" % ("op", "energy"))
    for key, label in energies:
        v = m.get(key)
        if v is None:
            problems.append("measure %s missing/failed" % key)
            print("%-22s%12s" % (label, "FAILED"))
        else:
            print("%-22s%10.4f pJ" % (label, v * 1e12))
    leak = m.get("p_leak_w")
    if leak is None:
        problems.append("p_leak_w missing/failed")
    else:
        print("%-22s%10.4f nW" % ("leakage", leak * 1e9))

    # delays: all measured at the far column; t_rd_sense may legitimately be
    # negative (cell discharged the bitline before the sense amp fired)
    delays = [("t_rd_wl_out", "READ delay wl->OUT", False),
              ("t_rd_bl_dev", "  rd: wl->0.1*VDD BL diff", False),
              ("t_rd_sense", "  rd: sen_en->OUT", True),
              ("t_wr_total", "WRITE delay (bl+cell)", False),
              ("t_wr_bl", "  wr: write->BL at 0.1*VDD", False),
              ("t_wr_cell", "  wr: wl->cell Q flip", False)]
    print("\n%-28s%12s" % ("delay", "value"))
    for key, label, neg_ok in delays:
        v = m.get(key)
        if v is None:
            problems.append("measure %s missing/failed" % key)
            print("%-28s%12s" % (label, "FAILED"))
            continue
        ok = (abs(v) < 10e-9) if neg_ok else (0 < v < 10e-9)
        if not ok:
            problems.append("%s=%.4g s out of range" % (key, v))
        print("%-28s%10.4f ns%s" % (label, v * 1e9,
                                    "" if ok else " ** RANGE **"))

    # per-column functional checks (OUT non-inverting; keys out_rd{1,0}_c<c>)
    cols = 1 + max((int(g.group(1)) for g in
                    (re.fullmatch(r"out_rd1_c(\d+)", k) for k in m) if g),
                   default=-1)
    if cols == 0:
        sys.exit("array_measures: no out_rd1_c* measures in %s" % a.mt0)
    lo, hi = 0.15 * V, 0.85 * V
    n_bad = 0
    for c in range(cols):
        for key, op, lim in (("out_rd1_c%d" % c, ">", hi),
                             ("out_rd0_c%d" % c, "<", lo)):
            v = m.get(key)
            ok = v is not None and (v < lim if op == "<" else v > lim)
            if not ok:
                problems.append("%s=%s not %s %.3f" % (key, v, op, lim))
                n_bad += 1
    print("\nOUT samples: %d columns x 2 reads — %s"
          % (cols, "all ok" if not n_bad else "%d FAILED" % n_bad))

    for key in ("blb_wrs_c0", "bl_wrt_c0"):
        v = m.get(key)
        if key in m:
            ok = v is not None and v < lo
            if not ok:
                problems.append("%s=%s not < %.3f" % (key, v, lo))
            print("%-16s%12s   (expect < %.3f V) %s"
                  % (key, "FAILED" if v is None else "%.4f V" % v, lo,
                     "ok" if ok else "** FAIL **"))
    for k in sorted(m):
        if re.fullmatch(r"blb_wrt_c\d+", k):
            v = m[k]
            ok = v is not None and v < lo
            if not ok:
                problems.append("%s=%s not < %.3f" % (k, v, lo))
            print("%-16s%12s   (expect < %.3f V) %s"
                  % (k, "FAILED" if v is None else "%.4f V" % v, lo,
                     "ok" if ok else "** FAIL **"))

    # ── value-level sanity bounds (autosweep/sanity_bounds.md §B) ───────
    # FAIL bounds append to problems (-> verdict FAIL); WARN bounds only
    # print.  Calibrated on the 2026-07-13/14 sheets.
    warns = []
    temper = m.get("temper")
    hot = temper is not None and temper > 50  # leakage grows ~10-30x hot
    if leak is not None:
        if leak <= 0:
            problems.append("A1: p_leak_w=%.4g W not positive" % leak)
        elif a.rows and a.cols:
            cap = 10e-9 * (a.rows * a.cols / 4.0 + 1) * (30 if hot else 1)
            if leak >= cap:
                problems.append("A2: p_leak_w=%.4g W >= %.3g W ceiling "
                                "(resistive short?)" % (leak, cap))
    for key, _label in energies:
        v = m.get(key)
        if v is not None and v <= 0:
            problems.append("A5: %s=%.4g J not positive" % (key, v))
    e_ws, e_wt = m.get("e_wr_same_j"), m.get("e_wr_toggle_j")
    if None not in (e_ws, e_wt) and e_ws > 0 and "bl_wrt_c0" in m \
            and e_wt < 0.9 * e_ws:  # bl_wrt_c0 exists only when n_toggle>0
        problems.append("A3: e_wr_toggle=%.4g < 0.9*e_wr_same=%.4g with "
                        "toggling columns" % (e_wt, e_ws))
    e_r1, e_r0 = m.get("e_rd_1to1_j"), m.get("e_rd_1to0_j")
    if None not in (e_r1, e_r0) and e_r1 > 0 and e_r0 < e_r1:
        problems.append("A4: e_rd_1to0=%.4g < e_rd_1to1=%.4g (full BL "
                        "discharge must cost more)" % (e_r0, e_r1))
    t_sense = m.get("t_rd_sense")
    if t_sense is not None:
        if t_sense <= -4e-9:
            warns.append("A7: t_rd_sense=%.4g s more negative than the "
                         "wl->sen_en gap (wrong edge?)" % t_sense)
        elif t_sense > 0:
            warns.append("A8: t_rd_sense=%.4g s > 0 — rd_delay is "
                         "sense-schedule-limited, not array-limited"
                         % t_sense)
    for w in warns:
        print("array_measures: WARN %s" % w)

    # all measured values are kept even on FAIL; the verdict row lets
    # collect_array.py drop the run from the sheet without losing data
    with open(a.out, "w") as f:
        w = csv.writer(f)
        w.writerow(["measure", "value_si"])
        for k, v in sorted(m.items()):
            if k not in ("temper", "alter#"):
                w.writerow([k, "" if v is None else repr(v)])
        w.writerow(["verdict", "PASS" if not problems
                    else ("FAIL: " + "; ".join(problems))[:300]])
    print("\narray_measures: wrote %s" % a.out)

    if problems:
        print("array_measures: FAIL — " + "; ".join(problems[:12])
              + (" (+%d more)" % (len(problems) - 12)
                 if len(problems) > 12 else ""))
        sys.exit(1)
    print("array_measures: PASS")


if __name__ == "__main__":
    main()
