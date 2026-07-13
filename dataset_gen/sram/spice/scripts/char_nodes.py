#!/usr/bin/env python3
# Characterize N/P single devices at every node with production instance
# lines (python3.6-compatible).  Prints IOFF/ION/SS/VT/DIBL + card params.
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TECHLIBS_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "tech_libs"))

#          node dir, vdd,  l(um), w(um) from extracted netlists
NODES = [("20nm", 0.90, 0.024, 0.17),
         ("16nm", 0.85, 0.022, 0.189),
         ("10nm", 0.80, 0.020, 0.12),
         ("07nm", 0.75, 0.018, 0.034),
         ("05nm", 0.70, 0.012, 0.034)]

PARAM_KEYS = ["phig", "vsat", "u0", "cdsc", "cdscd", "cit", "eta0", "dsub",
              "rdsw", "ids0mult", "dvtshift", "delvtrand", "hfin", "tfin",
              "fpitch", "eot", "lint", "cgso", "cgdo", "cfs", "cfd",
              "kt1", "ute", "utl", "at", "tnom"]


def parse_card(path):
    vals = {}
    for line in open(path):
        s = line.strip()
        if s.startswith("*"):
            continue
        for m in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+0-9.eE]+)", s):
            vals[m.group(1).lower()] = float(m.group(2))  # last wins (HSPICE)
    return vals


def deck(node, pol, vdd, l_um, w_um, card):
    if pol == "n":
        body = ("Ma da g 0 0 nmos1 l=%gu w=%gu wfin=%g nfin=1 nf=1 m=1\n"
                "vda da 0 %g\nvg g 0 0\n"
                ".dc vg 0 %g 0.001\n"
                ".meas dc ioff find i(vda) at=0\n"
                ".meas dc i1 find i(vda) at=0.1\n"
                ".meas dc ion find i(vda) at=%g\n"
                ".meas dc vtcc when i(vda)=-1e-6 cross=1\n"
                ".alter\nvda da 0 0.05\n"
                % (l_um, w_um, w_um, vdd, vdd, vdd))
    else:
        body = ("Ma da g vdd vdd pmos1 l=%gu w=%gu wfin=%g nfin=1 nf=1 m=1\n"
                "vs vdd 0 %g\nvda da 0 0\nvg g 0 0\n"
                ".dc vg 0 %g 0.001\n"
                ".meas dc ioff find i(vda) at=%g\n"
                ".meas dc i1 find i(vda) at=%g\n"
                ".meas dc ion find i(vda) at=0\n"
                ".meas dc vtcc when i(vda)=1e-6 cross=1\n"
                ".alter\nvda da 0 %g\n"
                % (l_um, w_um, w_um, vdd, vdd, vdd, vdd - 0.1, vdd - 0.05))
    return ("* char %s %smos\n.option ingold=2 post=0\n.temp 25\n"
            ".include '%s'\n%s.end\n" % (node, pol, card, body))


def parse_ms0(path):
    names, floats = [], []
    for line in open(path):
        if line.startswith("$DATA") or line.startswith(".TITLE"):
            continue
        for tok in line.split():
            try:
                floats.append(float(tok))
            except ValueError:
                if not floats:
                    names.append(tok)
                else:
                    floats.append(float("nan"))  # 'failed'
    rows = []
    n = len(names)
    for i in range(0, len(floats) // n * n, n):
        rows.append(dict(zip(names, floats[i:i + n])))
    return rows


def main():
    wd = os.path.join(HERE, "char")
    if not os.path.isdir(wd):
        os.makedirs(wd)
    results = []
    for node, vdd, l_um, w_um in NODES:
        for pol in "np":
            card = os.path.join(TECHLIBS_DIR, "techlib_%s" % node, "sram", "models", "%smos1.inc" % pol)
            name = "%s_%s" % (node, pol)
            sp = os.path.join(wd, name + ".sp")
            open(sp, "w").write(deck(node, pol, vdd, l_um, w_um, card))
            subprocess.call("hspice -i %s.sp -o %s > /dev/null 2>&1" % (name, name),
                            shell=True, cwd=wd)
            rows = parse_ms0(os.path.join(wd, name + ".ms0"))
            cp = parse_card(card)
            weff = 2 * cp.get("hfin", 0) + cp.get("tfin", 0)  # m
            sat, lin = rows[0], rows[1] if len(rows) > 1 else {}
            ioff = abs(sat.get("ioff", float("nan")))
            i1 = abs(sat.get("i1", float("nan")))
            ion = abs(sat.get("ion", float("nan")))
            import math
            ss = 0.1 / (math.log10(i1 / ioff)) * 1000 if i1 > 0 and ioff > 0 else float("nan")
            vt_sat = sat.get("vtcc", float("nan"))
            vt_lin = lin.get("vtcc", float("nan"))
            if pol == "p":
                vt_sat = vdd - vt_sat
                vt_lin = vdd - vt_lin
            dibl = (vt_lin - vt_sat) / (vdd - 0.05) * 1000  # mV/V
            results.append((node, pol, vdd, weff * 1e9, ioff, ion, ss,
                            vt_sat, dibl, cp))
    hdr = ("node pol vdd  Weff_nm  IOFF_nA  IOFF_nA/um  ION_uA  ION_uA/um"
           "  SS_mV/dec  VTsat_V  DIBL_mV/V")
    print(hdr)
    for node, pol, vdd, weff, ioff, ion, ss, vt, dibl, cp in results:
        print("%-5s %s  %.2f  %6.1f  %8.3f  %9.1f  %7.1f  %8.0f  %8.1f"
              "  %7.3f  %8.1f"
              % (node, pol, vdd, weff, ioff * 1e9, ioff * 1e9 / (weff * 1e-3),
                 ion * 1e6, ion * 1e6 / (weff * 1e-3), ss, vt, dibl))
    print()
    print("card parameters (last-occurrence wins):")
    print("%-10s" % "param" +
          "".join("%12s" % ("%s_%s" % (n[0], p)) for n in NODES for p in "np"))
    cps = [r[9] for r in results]
    for k in PARAM_KEYS:
        row = "%-10s" % k
        for cp in cps:
            v = cp.get(k)
            row += "%12s" % ("-" if v is None else "%.4g" % v)
        print(row)


if __name__ == "__main__":
    main()
