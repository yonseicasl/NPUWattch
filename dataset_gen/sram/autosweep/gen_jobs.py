#!/usr/bin/env python3
"""
gen_jobs.py — emit a jobs.csv grid for run_batch.sh (stdlib only, py3.6-ok).

Cartesian product of the given axes, one CSV row per point:

  ./gen_jobs.py                                  # default phase-4 grid:
                                                 # 5 nodes x rows{16,32,64,128}
                                                 # x cols{4,8,16,32}, nominal
  ./gen_jobs.py --nodes 20 --rows 64 128 --cols 32 --toggles 0.25 0.5 1.0
  ./gen_jobs.py --voffsets -0.05 0 0.05 --temps -40 25 85 > jobs.csv

vdd_V is written as nominal+offset (nominals: 20nm 0.90, 16nm 0.85,
10nm 0.80, 7nm 0.75, 5nm 0.70); offset 0 leaves the field blank so
run_array.sh uses node.env.  temps: the literal 'nom' leaves the field
blank.  wd is left blank (performance default) unless --wd is given.
"""
import argparse
import sys

NOMINAL = {"20": 0.90, "16": 0.85, "10": 0.80, "7": 0.75, "5": 0.70}
HEADER = "node,rows,cols,wd,toggle_rate,vdd_V,temp_C,pex"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", nargs="+", default=["20", "16", "10", "7", "5"])
    ap.add_argument("--rows", nargs="+", type=int, default=[16, 32, 64, 128])
    ap.add_argument("--cols", nargs="+", type=int, default=[4, 8, 16, 32])
    ap.add_argument("--toggles", nargs="+", type=float, default=[1.0])
    ap.add_argument("--voffsets", nargs="+", type=float, default=[0.0])
    ap.add_argument("--temps", nargs="+", default=["nom"])
    ap.add_argument("--wd", type=int, default=0,
                    help="fixed driver strength (default: blank = auto map)")
    ap.add_argument("--pex", type=int, default=1, choices=(0, 1))
    a = ap.parse_args()

    bad = [n for n in a.nodes if n.rstrip("nm") not in NOMINAL]
    if bad:
        sys.exit("gen_jobs: unknown node(s): %s" % bad)

    print(HEADER)
    n = 0
    for node in a.nodes:
        key = node.rstrip("nm")
        for rows in a.rows:
            for cols in a.cols:
                for tr in a.toggles:
                    for vo in a.voffsets:
                        vdd = "" if vo == 0 else "%.4g" % (NOMINAL[key] + vo)
                        for t in a.temps:
                            temp = "" if str(t) == "nom" else str(t)
                            print("%s,%d,%d,%s,%g,%s,%s,%d"
                                  % (key, rows, cols,
                                     a.wd or "", tr, vdd, temp, a.pex))
                            n += 1
    print("gen_jobs: %d job(s)" % n, file=sys.stderr)


if __name__ == "__main__":
    main()
