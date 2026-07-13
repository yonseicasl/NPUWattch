#!/usr/bin/env python3
"""
tech_paths.py -- resolve a node's library collateral from the shared
dataset_gen/tech_libs/catalog.json (stream of JSON objects, unknown keys
ignored).  Prints shell-eval'able KEY=path lines; the single source of
truth for where tech_libs collateral lives (used by spice/, decoder/ and
autosweep/ -- nothing is copied under sram/).

Per-node catalog attributes consumed here:
  corners[0] dbfile/ndmfile/techfile/tlufile/mapfile/grdfile  (EDA corner)
  gdsdir   -- std-cell layout GDS store (one file per cell), for the
              decoder stream-out merge
  sramdir  -- SRAM library home: primitive GDS (gds/), model cards
              (models/), LVS runset, StarRC map/template, node.env

Usage: tech_paths.py --node 20 [--catalog <path>]
Emits: TECH_LIB_DIR= TECH_DB= TECH_NDM= TECH_TF= TECH_TLUP= TECH_MAP=
       TECH_GRD= TECH_GDS= TECH_SRAM= TECH_VDD= TECH_TEMP=
(TECH_GDS/TECH_SRAM are emitted empty when the catalog entry has no
gdsdir/sramdir or the directory is missing -- callers must check.)
"""
import argparse
import json
import os
import sys


def decode_json_objects(text):
    dec = json.JSONDecoder()
    i, out = 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        obj, j = dec.raw_decode(text, i)
        out.append(obj)
        i = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", required=True)
    ap.add_argument("--catalog", default=None)
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    catalog = a.catalog or os.path.normpath(
        os.path.join(here, "..", "..", "..", "tech_libs", "catalog.json"))
    node = str(int(a.node.rstrip("nm")))

    with open(catalog) as f:
        entries = decode_json_objects(f.read())
    for e in entries:
        if e.get("node") != node:
            continue
        c = e["corners"][0]        # TT nominal-V 25C (one corner per node)
        base = os.path.join(os.path.dirname(catalog), c["directory"])
        print("TECH_LIB_DIR=%s" % base)
        for key, fname in (("TECH_DB", "dbfile"), ("TECH_NDM", "ndmfile"),
                           ("TECH_TF", "techfile"), ("TECH_TLUP", "tlufile"),
                           ("TECH_MAP", "mapfile"), ("TECH_GRD", "grdfile")):
            p = os.path.join(base, c[fname])
            ok = (os.path.isdir(p) and os.listdir(p)) if key == "TECH_NDM" \
                else (os.path.isfile(p) and os.path.getsize(p) > 0)
            if not ok:
                sys.exit("tech_paths: missing/empty %s (%s)" % (p, key))
            print("%s=%s" % (key, p))
        for key, attr in (("TECH_GDS", "gdsdir"), ("TECH_SRAM", "sramdir")):
            d = os.path.join(base, e[attr]) if e.get(attr) else ""
            print("%s=%s" % (key, d if d and os.path.isdir(d) else ""))
        print("TECH_VDD=%s" % c["voltage"])
        print("TECH_TEMP=%s" % c["temperature"])
        return
    sys.exit("tech_paths: node %s not in %s" % (node, catalog))


if __name__ == "__main__":
    main()
