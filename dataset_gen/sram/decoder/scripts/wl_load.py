#!/usr/bin/env python3
"""
wl_load.py -- wordline RC load for the decoder flow, from array PEX.

The array TB drives wl[0] with an ideal PWL source, so the wordline CV^2
energy is unbooked there; the decoder characterization owns it by loading
every decoder WL output with the wordline's extracted RC (pi model).

Source of truth: TECH_<N>nm/array_X<S>_<R>x<C>/02_pex/*.spef -- the wl[0]
*D_NET total cap (fF, *C_UNIT 1.0 FF) and the sum of its *RES section
(ohm).  WL cap/res are set by the horizontal strap across C columns and are
independent of the row count, so any extraction with matching cols works;
with no cols match the values are scaled linearly in cols from the closest
available extraction (cap/col and res/col are constant at a node).

Also reports the array die height from the array_X*/01_gds/*.json sidecar
(rows must match; the decoder floorplan is pitch-matched to it).

Usage: wl_load.py --tech-dir TECH_20nm --rows R --cols C   -> JSON on stdout
"""
import argparse
import glob
import json
import os
import re
import sys


def die(msg):
    sys.exit("wl_load: error: %s" % msg)


def parse_wl0(spef):
    """(total_cap_fF, total_res_ohm) of net wl[0]."""
    cap = None
    res = 0.0
    in_net = False
    section = ""
    with open(spef) as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "*D_NET":
                in_net = (t[1] == "wl[0]")
                if in_net:
                    cap = float(t[2])
                section = ""
            elif in_net and t[0] == "*END":
                break
            elif in_net and t[0] in ("*CONN", "*CAP", "*RES", "*INDUC"):
                section = t[0]
            elif in_net and section == "*RES" and len(t) >= 4:
                res += float(t[3])
    if cap is None:
        die("no *D_NET wl[0] in %s" % spef)
    return cap, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tech-dir", required=True,
                    help="per-node work tree, e.g. sram/TECH_20nm")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    a = ap.parse_args()

    pat = re.compile(r"array_X\d+_(\d+)x(\d+)\.spef$")
    cands = []
    for p in glob.glob(os.path.join(a.tech_dir, "array_X*", "02_pex",
                                    "array_X*.spef")):
        m = pat.search(p)
        if m:
            cands.append((int(m.group(1)), int(m.group(2)), p))
    if not cands:
        die("no array_X*/02_pex/*.spef extractions under %s -- run the "
            "array flow (gen_array.py + gds2spice.sh) first" % a.tech_dir)

    # prefer exact cols (WL RC is row-count independent), closest rows;
    # otherwise closest cols and scale linearly in cols
    exact = [c for c in cands if c[1] == a.cols]
    pool = exact if exact else cands
    rows_s, cols_s, spef = min(
        pool, key=lambda c: (abs(c[1] - a.cols), abs(c[0] - a.rows)))
    cap, res = parse_wl0(spef)
    scale = a.cols / float(cols_s)
    out = {
        "wl_cap_fF": round(cap * scale, 5),
        "wl_res_ohm": round(res * scale, 3),
        "src_spef": os.path.basename(spef),
        "src_cols": cols_s,
        "col_scale": round(scale, 5),
    }

    # array height for the pitch-matched decoder floorplan
    sidecars = glob.glob(os.path.join(
        a.tech_dir, "array_X*", "01_gds",
        "array_X*_%dx%d.json" % (a.rows, a.cols)))
    if sidecars:
        with open(sidecars[0]) as f:
            sc = json.load(f)
        out["array_height_um"] = sc["height_um"]
        out["array_width_um"] = sc["width_um"]
        out["src_sidecar"] = os.path.basename(sidecars[0])
    else:
        # derive rows -> height linearly from any two same-node sidecars
        # (height = rows * row_pitch + fixed periphery)
        pts = {}
        for p in glob.glob(os.path.join(a.tech_dir, "array_X*", "01_gds",
                                        "array_X*.json")):
            with open(p) as f:
                sc = json.load(f)
            pts[sc["rows"]] = sc["height_um"]
        if len(pts) < 2:
            die("no array sidecar for %dx%d and <2 others to interpolate "
                "height -- run gen_array.py for this config first"
                % (a.rows, a.cols))
        (r1, h1), (r2, h2) = sorted(pts.items())[:2]
        pitch = (h2 - h1) / float(r2 - r1)
        out["array_height_um"] = round(h1 + (a.rows - r1) * pitch, 4)
        out["src_sidecar"] = "interpolated(rows %d:%g, %d:%g)" % (
            r1, h1, r2, h2)

    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
