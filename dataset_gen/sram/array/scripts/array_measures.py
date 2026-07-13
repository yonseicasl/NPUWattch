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

    with open(a.out, "w") as f:
        w = csv.writer(f)
        w.writerow(["measure", "value_si"])
        for k, v in sorted(m.items()):
            if k not in ("temper", "alter#"):
                w.writerow([k, "" if v is None else repr(v)])
    print("\narray_measures: wrote %s" % a.out)

    if problems:
        print("array_measures: FAIL — " + "; ".join(problems[:12])
              + (" (+%d more)" % (len(problems) - 12)
                 if len(problems) > 12 else ""))
        sys.exit(1)
    print("array_measures: PASS")


if __name__ == "__main__":
    main()
