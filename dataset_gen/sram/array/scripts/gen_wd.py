#!/usr/bin/env python3
"""
gen_wd.py — write-driver strength-ladder generator (node-aware).

Stacks the node's unit write driver vertically to build stronger drivers,
reproducing the verified 20nm ladder pattern exactly:

  * top cell = N plain references to the unit cell (no rotation/mirroring)
    at a fixed pitch, so the shared VDD rails (M0, layer 84) of adjacent
    units overlap on abutment;
  * pitch = ymin(top rail) - ymin(bottom rail), measured from the unit GDS
    (20nm: 2.68 um cell height - 0.12 um rail = 2.56 um pitch);
  * the unit's pin labels (BL, BL_bar, data, write, VDD, VSS) are copied
    into the top cell at each unit position, which is what merges the
    signal nets of the stacked units during ICV extraction (text_net).

Usage:
  gen_wd.py --node <20|16|10|7|5> X8 X16 ...     # target strength labels
  gen_wd.py --node <N> --list                    # show unit/pitch and exit

Targets must be multiples of the node's unit strength (from the unit cell
name, e.g. wd_X4 -> 4). Output: TECH_<N>nm/wd_X<S>/01_gds/wd_X<S>.gds
(file name = top cell name). Requires gdstk (conda activate npuwattch).

The unit cell is the node's SRAM library wd_X*.gds
(tech_libs/techlib_<N>nm/sram/gds/, via catalog.json sramdir) — exactly
one lives there; its labels must already be the standard set.
"""
import argparse
import glob
import os
import re
import sys

try:
    import gdstk
except ImportError:
    sys.exit("gdstk not found — run under the npuwattch env "
             "(conda activate npuwattch) and retry.")

from gen_col import NODE_SPECS, lib_gds, norm_node, out_gds

RAIL_LAYER = (84, 0)          # M0
STD_PINS = {"BL", "BL_bar", "data", "write", "VDD", "VSS"}


def die(msg):
    sys.exit(f"Error: {msg}")


def find_unit(gds_dir):
    """The node's unit cell = the lowest-strength wd_X*.gds in the store."""
    cands = []
    for path in glob.glob(os.path.join(gds_dir, "wd_X*.gds")):
        m = re.fullmatch(r"wd_X(\d+)", os.path.basename(path)[:-4])
        if m:
            cands.append((int(m.group(1)), path))
    if not cands:
        die(f"no wd_X*.gds unit cell in {gds_dir}")
    return min(cands)          # (strength, path)


def rail_pitch(cell):
    """Tiling pitch: ymin(top VDD rail) - ymin(bottom VDD rail) on M0."""
    (x0, y0), (x1, y1) = cell.bounding_box()
    rails = []
    for p in cell.polygons:
        if (p.layer, p.datatype) != RAIL_LAYER:
            continue
        (px0, py0), (px1, py1) = p.bounding_box()
        full_width = (px1 - px0) >= 0.9 * (x1 - x0)
        at_edge = abs(py0 - y0) < 0.05 or abs(py1 - y1) < 0.05
        if full_width and at_edge:
            rails.append((py0, py1))
    if len(rails) != 2:
        die(f"expected 2 full-width M0 rails at cell edges, found {len(rails)}")
    rails.sort()
    (b0, b1), (t0, t1) = rails
    if abs((b1 - b0) - (t1 - t0)) > 1e-6:
        die(f"top/bottom rail heights differ: {b1-b0:.4f} vs {t1-t0:.4f}")
    return t0 - b0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--node", required=True, help="20|16|10|7|5 (nm optional)")
    ap.add_argument("targets", nargs="*",
                    help="strength labels, e.g. X8 X16 (or bare numbers)")
    ap.add_argument("--list", action="store_true",
                    help="print unit cell / pitch info and exit")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing wd_X<S>.gds")
    args = ap.parse_args()

    spec = NODE_SPECS[norm_node(args.node)]
    node = spec.node
    gds_dir = lib_gds(spec)

    unit_strength, unit_path = find_unit(gds_dir)
    lib = gdstk.read_gds(unit_path)
    tops = lib.top_level()
    if len(tops) != 1:
        die(f"{unit_path}: expected a single top cell, got "
            f"{[c.name for c in tops]}")
    unit = tops[0]
    if unit.name != f"wd_X{unit_strength}":
        die(f"{unit_path}: top cell '{unit.name}' does not match file name")

    pin_names = {l.text for l in unit.labels}
    if pin_names != STD_PINS:
        die(f"unit pins {sorted(pin_names)} != standard {sorted(STD_PINS)} — "
            "standardize the unit's labels first")

    pitch = rail_pitch(unit)
    (x0, y0), (x1, y1) = unit.bounding_box()
    print(f"node {node}: unit {unit.name} ({unit_path})")
    print(f"  cell H={y1 - y0:.4f} um, tiling pitch={pitch:.4f} um "
          f"(rail overlap {(y1 - y0) - pitch:.4f} um)")
    if args.list:
        return
    if not args.targets:
        die("no targets given (e.g. X8 X16)")

    for tgt in args.targets:
        m = re.fullmatch(r"[xX]?(\d+)", tgt)
        if not m:
            die(f"bad strength label: {tgt}")
        strength = int(m.group(1))
        count, rem = divmod(strength, unit_strength)
        if rem or count < 2:
            die(f"X{strength} is not a >=2 multiple of the unit X{unit_strength}")

        top_name = f"wd_X{strength}"
        out_path = out_gds(spec, top_name)
        if os.path.exists(out_path) and not args.force:
            die(f"{out_path} exists (use --force to overwrite)")

        out = gdstk.Library(unit=lib.unit, precision=lib.precision)
        # fresh copy of the unit so each output GDS is self-contained;
        # labels live ONLY in the top cell (matches the verified 20nm
        # ladder GDS — the subcell there carries no labels)
        unit_copy = unit.copy(unit.name)
        unit_copy.remove(*unit_copy.labels)
        top = gdstk.Cell(top_name)
        for k in range(count):
            top.add(gdstk.Reference(unit_copy, (0.0, k * pitch)))
            for l in unit.labels:
                top.add(gdstk.Label(l.text,
                                    (l.origin[0], l.origin[1] + k * pitch),
                                    layer=l.layer, texttype=l.texttype))
        out.add(unit_copy, top)
        out.write_gds(out_path)
        print(f"  wrote {out_path}: {count} x {unit.name} @ pitch {pitch:.4f}, "
              f"H={y1 - y0 + (count - 1) * pitch:.4f} um")


if __name__ == "__main__":
    main()
