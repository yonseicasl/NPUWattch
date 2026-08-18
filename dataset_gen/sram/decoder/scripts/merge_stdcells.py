#!/usr/bin/env python3
"""
merge_stdcells.py -- inject std-cell layout GDS into the ICC2 stream-out.

The per-node NDMs carry only frame (abstract) views, so ICC2's write_gds
emits instance placements of cells whose geometry is not in the file (ICV:
layout_drawn_errors:missing_cell).  The full layouts live one-file-per-cell
in dataset_gen/tech_libs/techlib_<N>nm/gds/ -- this script resolves every
unresolved reference from there and rewrites the GDS self-contained.

Needs gdstk (run with $PYTHON_GDSTK / the npuwattch conda env).

Usage: merge_stdcells.py <in.gds> <stdcell_gds_dir> -o <out.gds>
"""
import argparse
import os
import sys

import gdstk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("celldir")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    lib = gdstk.read_gds(a.gds)
    have = {c.name for c in lib.cells}

    def missing_refs():
        names = set()
        for c in lib.cells:
            for r in c.references:
                n = r.cell if isinstance(r.cell, str) else r.cell.name
                if n not in have:
                    names.add(n)
        return names

    added = []
    while True:
        need = missing_refs()
        if not need:
            break
        for name in sorted(need):
            path = os.path.join(a.celldir, name + ".gds")
            if not os.path.isfile(path):
                # 5nm-style naming without the underscore (AND2X1 vs AND2_X1)
                alt = os.path.join(a.celldir, name.replace("_", "") + ".gds")
                if os.path.isfile(alt):
                    path = alt
                else:
                    sys.exit("merge_stdcells: no GDS for referenced cell "
                             "'%s' in %s" % (name, a.celldir))
            sub = gdstk.read_gds(path)
            top = [c for c in sub.cells if c.name == name] or \
                sub.top_level()
            if top[0].name != name:
                # 5nm GDS tops drop the underscore (AND2X1) while the NDM
                # references AND2_X1 -- rename to the referenced name
                print("merge_stdcells: renaming %s -> %s (%s)"
                      % (top[0].name, name, os.path.basename(path)))
                top[0].name = name
            for c in sub.cells:
                if c.name not in have:
                    lib.add(c)
                    have.add(c.name)
            added.append(name)

    lib.write_gds(a.out)
    print("merge_stdcells: %s -> %s (+%d cell defs: %s)"
          % (a.gds, a.out, len(added),
             " ".join(sorted(set(added))[:12])
             + (" ..." if len(set(added)) > 12 else "")))


if __name__ == "__main__":
    main()
