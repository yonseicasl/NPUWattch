#!/usr/bin/env python3
"""Node-aware SRAM array compiler (NPUWattch dataset flow).

Tiles a generated column (gen_col.py output, already extraction-verified)
horizontally C times at the node's column pitch = bitcell width, producing
TECH_<N>nm/array_X<S>_<R>x<C>/01_gds/array_X<S>_<R>x<C>.gds (+ .json area
sidecar).  The columns abut edge-to-edge:
every cell in the column stack is exactly one pitch wide, so column c sits
at x = c * col_pitch with no gap and no overlap.

Net model (matches the user-approved array port plan):
  shared across columns : wl[0..R-1], pre_en, sen_en, sen_en_bar, write,
                          VDD, VSS  -> labels copied per column with the
                          SAME name; ICV text-merge parallels them (the
                          established mechanism from the WD ladders)
  per column            : data, OUT, BL, BL_bar -> renamed data[c], OUT[c],
                          BL[c], BL_bar[c] so extraction keeps them separate

Only labels on the TOP cell reach a flat GDS->SPICE extraction, so the
column's top-cell labels are re-stamped at absolute positions on the array
top; the column cell itself becomes label-carrying geometry only.

Usage:
    gen_array.py --node 20 --rows 32 --wd 16 --cols 8
    (requires the column_X<wd>_<rows> GDS — run gen_col.py first)
"""
import argparse
import json
import os
import sys

import gdstk

from gen_col import NODE_SPECS, find_gds, norm_node, out_gds, r4

PER_COLUMN = {"data", "OUT", "BL", "BL_bar"}
COLS_MIN, COLS_MAX = 1, 64


def default_wd(spec, rows):
    """Performance-backed default driver strength for a row count.

    From the phase-2 column sweeps the smallest strength with clean write
    margin scales as ~rows/8 (64->X8, 128->X16, 256->X32, 512->X64); below
    that the node unit driver passed at every node, except 5nm where X2 is
    below write margin and X4 is the validated minimum.  Rounded up to a
    multiple of the node's unit strength.
    """
    floor = 4 if spec.node == "05nm" else spec.wd_unit
    s = max(floor, -(-rows // 8))          # ceil(rows/8)
    u = spec.wd_unit
    return -(-s // u) * u                  # round up to unit multiple


def main():
    ap = argparse.ArgumentParser(description="node-aware SRAM array compiler")
    ap.add_argument("--node", required=True, help="20|16|10|7|5")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--wd", type=int, default=0,
                    help="driver strength S (column_X<S>_<rows>; default: "
                         "smallest strength with clean write margin for "
                         "this row count, from the phase-2 column sweeps)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    key = norm_node(args.node)
    spec = NODE_SPECS[key]
    if not (COLS_MIN <= args.cols <= COLS_MAX):
        sys.exit(f"cols must be in {COLS_MIN}..{COLS_MAX} (got {args.cols})")
    s = args.wd or default_wd(spec, args.rows)

    col_name = f"column_X{s}_{args.rows}"
    col_path = find_gds(spec, col_name)
    if col_path is None:
        sys.exit(f"{col_name}.gds not found — generate it first: "
                 f"gen_col.py --node {key} --rows {args.rows} --wd {s}")

    src_lib = gdstk.read_gds(col_path)
    cells = {c.name: c for c in src_lib.cells}
    if col_name not in cells:
        sys.exit(f"{col_path}: no cell '{col_name}' (has: {sorted(cells)})")
    col = cells[col_name]

    top_name = f"array_X{s}_{args.rows}x{args.cols}"
    lib = gdstk.Library(name=top_name, unit=src_lib.unit,
                        precision=src_lib.precision)
    for c in src_lib.cells:
        lib.add(c)
    top = lib.new_cell(top_name)

    pitch = spec.col_pitch
    for c in range(args.cols):
        dx = r4(c * pitch)
        top.add(gdstk.Reference(col, (dx, 0.0)))
        for l in col.labels:
            base = l.text
            if base in PER_COLUMN:
                text = f"{base}[{c}]"
            else:
                text = base
            top.add(gdstk.Label(text, (r4(l.origin[0] + dx), r4(l.origin[1])),
                                layer=l.layer, texttype=l.texttype,
                                magnification=l.magnification))

    out = args.out or out_gds(spec, top_name)
    if os.path.exists(out) and not args.force:
        sys.exit(f"{out} exists (use --force)")
    lib.write_gds(out)

    (bx0, by0), (bx1, by1) = top.bounding_box()
    w, h = r4(bx1 - bx0), r4(by1 - by0)
    # sidecar consumed by collect_array.py (area source; no gdstk needed there)
    with open(os.path.splitext(out)[0] + ".json", "w") as f:
        json.dump({"cell": top_name, "node": spec.node, "rows": args.rows,
                   "cols": args.cols, "wd": s, "col_pitch_um": pitch,
                   "width_um": w, "height_um": h,
                   "total_area_um2": r4(w * h)}, f, indent=1)
    print(f"wrote {out}")
    print(f"  node={spec.node} rows={args.rows} cols={args.cols} wd=X{s} "
          f"(column pitch {pitch} um)")
    print(f"  bbox=({r4(bx0)},{r4(by0)})..({r4(bx1)},{r4(by1)})")
    print(f"  footprint: w={w} h={h}  area={r4(w * h)} um2")


if __name__ == "__main__":
    main()
