#!/usr/bin/env python3
"""
dec_measures.py -- parse the HSPICE .mt0 of a decoder TB run, pretty-print
energies/delays, evaluate functional checks, and write measures.csv.
Reuses parse_mt0 from the array flow (PYTHONPATH=spice/scripts).

Exits 1 on any failed check or missing measure -- a silent zero in the
dataset is worse than a crashed run.

Usage: dec_measures.py <file.mt0> --vdd <V> -o measures.csv
"""
import argparse
import csv
import sys

from col_measures import parse_mt0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mt0")
    ap.add_argument("--vdd", type=float, required=True)
    ap.add_argument("--rows", type=int, default=0,
                    help="wordline count; enables the row-scaled leakage "
                         "ceiling (bound D2 in sanity_bounds.md)")
    ap.add_argument("-o", "--out", default="measures.csv")
    a = ap.parse_args()
    m = parse_mt0(a.mt0)
    V = a.vdd
    problems = []

    energies = [("e_act_first_j", "activate addr 0 (aux, first)"),
                ("e_act_same_j", "activate, same address"),
                ("e_act_flip_j", "activate, all addr bits flip"),
                ("e_act_same2_j", "activate, same address (2)"),
                ("e_act_back_j", "activate, all bits flip back"),
                ("e_idle_clk_j", "idle cycle (en=0, clk on)")]
    print("%-32s%12s" % ("op", "energy"))
    for key, label in energies:
        v = m.get(key)
        if v is None:
            problems.append("measure %s missing/failed" % key)
            print("%-32s%12s" % (label, "FAILED"))
        else:
            if v <= 0:
                problems.append("%s=%.4g J not positive" % (key, v))
            print("%-32s%10.4f pJ" % (label, v * 1e12))
    leak = m.get("p_leak_w")
    if leak is None:
        problems.append("p_leak_w missing/failed")
    else:
        print("%-32s%10.4f nW" % ("leakage", leak * 1e9))

    delays = [("t_clk_wl", "clk -> WL far (incl 2ns wlen gate)", 2e-9, 10e-9),
              ("t_wlen_wl", "wlen -> WL far (driver + WL RC)", 0.0, 8e-9),
              ("t_wl_rise", "WL 10-90% rise (far end)", 0.0, 8e-9)]
    print("\n%-36s%12s" % ("delay", "value"))
    for key, label, lo, hi in delays:
        v = m.get(key)
        if v is None:
            problems.append("measure %s missing/failed" % key)
            print("%-36s%12s" % (label, "FAILED"))
            continue
        ok = lo < v < hi
        if not ok:
            problems.append("%s=%.4g s out of range" % (key, v))
        print("%-36s%10.4f ns%s" % (label, v * 1e9,
                                    "" if ok else " ** RANGE **"))

    hi_t, lo_t = 0.85 * V, 0.15 * V
    checks = [("wl0_act", ">", hi_t), ("wl0_off", "<", lo_t),
              ("wllast_act", ">", hi_t), ("wllast_off", "<", lo_t),
              ("wl_idle", "<", lo_t)]
    print("\n%-14s%12s" % ("check", "value"))
    n_bad = 0
    for key, op, lim in checks:
        v = m.get(key)
        ok = v is not None and (v < lim if op == "<" else v > lim)
        if not ok:
            problems.append("%s=%s not %s %.3f" % (key, v, op, lim))
            n_bad += 1
        print("%-14s%12s   (expect %s %.3f V) %s"
              % (key, "FAILED" if v is None else "%.4f V" % v, op, lim,
                 "ok" if ok else "** FAIL **"))

    # ── value-level sanity bounds (autosweep/sanity_bounds.md §A) ───────
    # FAIL bounds append to problems (-> verdict FAIL); WARN bounds only
    # print.  Calibrated on the 2026-07-13/14 healthy vs broken builds.
    warns = []
    temper = m.get("temper")
    hot = temper is not None and temper > 50  # leakage grows ~10-30x hot
    if leak is not None:
        if leak <= 0:
            problems.append("D1: p_leak_w=%.4g W not positive" % leak)
        elif a.rows:
            cap = 10e-9 * a.rows * (30 if hot else 1)
            if leak >= cap:
                problems.append("D2: p_leak_w=%.4g W >= %.3g W ceiling "
                                "(resistive short?)" % (leak, cap))
    e_keys = ("e_act_same_j", "e_act_same2_j", "e_act_flip_j",
              "e_act_back_j", "e_idle_clk_j")
    ev = [m.get(k) for k in e_keys]
    if all(v is not None and v > 0 for v in ev):
        e_s, e_s2, e_f, e_b, e_i = ev
        if e_s >= e_f:
            problems.append("D3: e_act_same=%.4g >= e_act_flip=%.4g"
                            % (e_s, e_f))
        if abs(e_s - e_s2) > 0.25 * max(e_s, e_s2):
            problems.append("D4: e_act_same=%.4g vs same2=%.4g mismatch "
                            "> 25%%" % (e_s, e_s2))
        if abs(e_f - e_b) > 0.25 * max(e_f, e_b):
            problems.append("D5: e_act_flip=%.4g vs back=%.4g mismatch "
                            "> 25%%" % (e_f, e_b))
        if e_i >= e_s:
            problems.append("D6: e_idle_clk=%.4g >= e_act_same=%.4g"
                            % (e_i, e_s))
        if leak is not None and leak > 0 and e_i <= leak * 10e-9:
            warns.append("D7: e_idle_clk=%.4g J below its own leakage "
                         "share %.4g J" % (e_i, leak * 10e-9))
    t_c, t_w = m.get("t_clk_wl"), m.get("t_wlen_wl")
    if t_c is not None and t_w is not None \
            and abs(t_c - 2e-9 - t_w) >= 0.3e-9:
        warns.append("D8: t_clk_wl-2ns-t_wlen_wl=%.4g s (slow decode "
                     "path?)" % (t_c - 2e-9 - t_w))
    for w in warns:
        print("dec_measures: WARN %s" % w)

    # all measured values are kept even on FAIL; the verdict row lets
    # collect_decoder.py drop the run from the sheet without losing data
    with open(a.out, "w") as f:
        w = csv.writer(f)
        w.writerow(["measure", "value_si"])
        for k, v in sorted(m.items()):
            if k not in ("temper", "alter#"):
                w.writerow([k, "" if v is None else repr(v)])
        w.writerow(["verdict", "PASS" if not problems
                    else ("FAIL: " + "; ".join(problems))[:300]])
    print("\ndec_measures: wrote %s" % a.out)

    if problems:
        print("dec_measures: FAIL -- " + "; ".join(problems[:12])
              + (" (+%d more)" % (len(problems) - 12)
                 if len(problems) > 12 else ""))
        sys.exit(1)
    print("dec_measures: PASS")


if __name__ == "__main__":
    main()
