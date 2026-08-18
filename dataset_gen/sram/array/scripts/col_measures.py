#!/usr/bin/env python3
"""
col_measures.py — parse the HSPICE .mt0 of a column TB run, pretty-print
the energy/functional results, evaluate pass/fail, and write measures.csv.

Used by run_col.sh after each simulation; the phase-4 dataset collector
reuses the same parser.  Exits 1 when any functional check fails or a
measure is missing/failed — a silent zero in the dataset is worse than a
crashed run.

Usage: col_measures.py <file.mt0> --vdd <V> -o measures.csv
"""
import argparse
import csv
import sys


def parse_mt0(path):
    """Return {measure_name: float|None}. Handles multi-line name/value
    blocks; the name list ends at 'alter#'."""
    tokens = []
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("$") or s.upper().startswith(".TITLE") \
           or s.startswith("'"):
            continue
        tokens += s.split()
    if "alter#" not in tokens:
        sys.exit(f"col_measures: no 'alter#' column in {path} — not a .mt0?")
    n = tokens.index("alter#") + 1
    names, values = tokens[:n], tokens[n:]
    if len(values) < len(names):
        sys.exit(f"col_measures: truncated .mt0 {path} "
                 f"({len(names)} names, {len(values)} values)")
    out = {}
    for name, val in zip(names, values):
        try:
            out[name.lower()] = float(val)
        except ValueError:
            out[name.lower()] = None  # 'failed' etc.
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mt0")
    ap.add_argument("--vdd", type=float, required=True)
    ap.add_argument("-o", "--out", default="measures.csv")
    a = ap.parse_args()
    m = parse_mt0(a.mt0)
    V = a.vdd

    energies = [("e_wr0_j", "write0 (init)"),
                ("e_rd0_j", "read 0"),
                ("e_wr1_flip_j", "write 1 FLIP"),
                ("e_rd1_j", "read 1"),
                ("e_wr1_same_j", "write 1 SAME"),
                ("e_rd1b_j", "read 1 (b)")]
    problems = []

    print(f"{'op':<16}{'energy':>12}")
    for key, label in energies:
        v = m.get(key)
        if v is None:
            problems.append(f"measure {key} missing/failed")
            print(f"{label:<16}{'FAILED':>12}")
        else:
            print(f"{label:<16}{v * 1e12:>10.4f} pJ")
    leak = m.get("p_leak_w")
    if leak is None:
        problems.append("p_leak_w missing/failed")
    else:
        print(f"{'leakage':<16}{leak * 1e9:>10.4f} nW")

    # functional checks (OUT is the buffered bitline — non-inverting)
    lo, hi = 0.15 * V, 0.85 * V
    checks = [("out_rd0", "<", lo), ("out_rd1", ">", hi),
              ("out_rd1b", ">", hi), ("bl_wr0", "<", lo),
              ("blb_wr1", "<", lo)]
    print()
    for key, op, lim in checks:
        v = m.get(key)
        ok = v is not None and (v < lim if op == "<" else v > lim)
        if not ok:
            problems.append(f"{key}={v} not {op} {lim:.3f}")
        vs = "FAILED" if v is None else f"{v:.4f} V"
        print(f"{key:<16}{vs:>12}   (expect {op} {lim:.3f} V) "
              f"{'ok' if ok else '** FAIL **'}")
    for key in ("bl_dev_rd0", "t_bl_fall_wr0", "t_blb_fall_wr1"):
        v = m.get(key)
        if v is not None:
            unit = " V" if key.startswith("bl") else " s"
            print(f"{key:<16}{v:>12.4g}{unit}")

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["measure", "value_si"])
        for k, v in sorted(m.items()):
            if k not in ("temper", "alter#"):
                w.writerow([k, "" if v is None else repr(v)])
    print(f"\ncol_measures: wrote {a.out}")

    if problems:
        print("col_measures: FAIL — " + "; ".join(problems))
        sys.exit(1)
    print("col_measures: PASS")


if __name__ == "__main__":
    main()
