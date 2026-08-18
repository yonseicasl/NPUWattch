#!/usr/bin/env python3
"""
label_rails.py -- add VDD/VSS text labels on the decoder's M0 power rails.

Power rails have no logical ports, so ICC2's stream-out carries no text for
them; ICV then cannot name the power nets.  The legacy flow guessed the net
from y % 1.6 (20nm row height) -- here the exact rail tracks come straight
from ICC2 (rails.json written by icc2.tcl), so this works at every node.

Labels are GDT text records on layer 88 (M0 text, post-remap numbering),
matching the legacy convention:  t{88 mc m0.1 xy(x y) 'VDD'}
Same-name labels text-merge in ICV; the rails join only through the cell
rows, so the known/accepted text_open_merge violation may appear -- same
as the SRAM column/array flow.

Usage: label_rails.py <in.gdt> <rails.json> <top_cell> <out.gdt>
"""
import json
import re
import sys


def main():
    gdt_in, rails_js, top, gdt_out = sys.argv[1:5]
    with open(rails_js) as f:
        rails = json.load(f)
    x = rails["die_w_um"] / 2.0
    labels = []
    for net, key in (("VDD", "vdd_ys"), ("VSS", "vss_ys")):
        for y in rails[key]:
            labels.append("t{88 mc m0.1 xy(%.4f %.4f) '%s'}\n" % (x, y, net))
    if not labels:
        sys.exit("label_rails: rails.json has no rail tracks")

    lines = open(gdt_in).readlines()
    # insert right after the top cell's definition header: cell{... '<top>'
    pat = re.compile(r"^cell\{.*'%s'" % re.escape(top))
    idx = next((i for i, l in enumerate(lines) if pat.match(l)), None)
    if idx is None:
        sys.exit("label_rails: no cell{... '%s' in %s" % (top, gdt_in))
    with open(gdt_out, "w") as f:
        f.writelines(lines[:idx + 1])
        f.writelines(labels)
        f.writelines(lines[idx + 1:])
    print("label_rails: %s -> %s (+%d rail labels: %d VDD, %d VSS)"
          % (gdt_in, gdt_out, len(labels), len(rails["vdd_ys"]),
             len(rails["vss_ys"])))


if __name__ == "__main__":
    main()
