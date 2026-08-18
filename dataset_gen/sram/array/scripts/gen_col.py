#!/usr/bin/env python3
"""Node-aware SRAM column compiler (NPUWattch dataset flow).

Builds a single array column from the standardized primitives in the
node's SRAM library (tech_libs/techlib_<N>nm/sram/gds/: sram_cell, pc,
sense_amp, buffer, unit driver — resolved via catalog.json sramdir) plus
a write-driver strength ladder from gen_wd.py:

    pc                          <- 0.01 um above the top row
    sram_cell x N rows          <- mirror-tiled, sharing VDD/VSS rails
    sense_amp                   <- oriented so its VDD rail faces down
    wd_X<S>                     <- ladder; top VDD rail shared with the SA
    buffer                      <- oriented so its VDD rail faces up

Vertical placement is pure rail abutment: adjacent cells overlap their
full-width M0 edge rails net-on-net (VDD-VDD / VSS-VSS), exactly as in the
verified 20nm reference column.  Bitlines are M3 straps dropped over every
cell's existing VIA2 stubs on the two bitline tracks.  Wordlines are
full-width M0 straps over each row's internal WL shape.

Per-node measured geometry is FROZEN in NODE_SPECS below (bboxes, rail
bands, track x, flips).  The assembly rule is shared code.  Run with
--check to re-derive every frozen number from the GDS store and report
drift (e.g. after a primitive is re-delivered).

Only labels in the TOP cell reach a flat GDS->SPICE extraction, so the
column re-stamps each placed cell's port labels at their absolute
positions (VDD/VSS everywhere; data/write on the driver; pre_en, sen_en,
sen_en_bar, OUT on their cells).  Q/Q_bar are intentionally NOT promoted:
same-name text merges nets in ICV, which would short all rows' storage
nodes together.

Generated GDS lands in the per-config work tree:
sram/TECH_<N>nm/<cellname>/01_gds/<cellname>.gds.

Usage:
    gen_col.py --node 20 --rows 32 --wd 16
    gen_col.py --node 5 --rows 4            # wd defaults to the unit strength
    gen_col.py --node 16 --check
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass

import gdstk

HERE = os.path.dirname(os.path.abspath(__file__))
SRAM_DIR = os.path.normpath(os.path.join(HERE, "..", ".."))
CATALOG = os.path.normpath(os.path.join(SRAM_DIR, "..", "tech_libs",
                                        "catalog.json"))

L_M0 = (84, 0)
L_M3 = (15, 0)
L_VIA2 = (14, 0)
L_M0PIN = 88
L_M3PIN = 33

PIN_MAG_POWER = 0.1
PIN_MAG_SIGNAL = 0.02
PC_CLEARANCE = 0.01     # gap between top row edge and pc bottom edge (um)
BL_VIA_TOL = 0.02       # x tolerance matching VIA2 stubs to a bitline track
BL_M3_MARGIN = 0.002    # M3 strap overhang past the outermost VIA2 stub

ROWS_MIN, ROWS_MAX = 1, 512

# Labels re-stamped on the top cell, per placed-cell role.
PROMOTE = {
    "sram_cell": {"VDD", "VSS"},
    "pc": {"VDD", "pre_en"},
    "sense_amp": {"VDD", "VSS", "sen_en", "sen_en_bar"},
    "buffer": {"VDD", "VSS", "OUT"},
    "wd": {"VDD", "VSS", "data", "write"},
}


@dataclass(frozen=True)
class CellGeom:
    bbox: tuple          # (x0, y0, x1, y1)
    rails: tuple         # ((y0, y1, net), ...) full-width M0 rails, bottom-up
    x_off: float = 0.0   # placement x offset aligning this cell's BL stubs

    def rail(self, net, top=None):
        """The cell's rail carrying `net`; top=True/False picks by position
        when both edge rails carry the same net (write driver)."""
        hits = [r for r in self.rails if r[2] == net]
        if top is True:
            return max(hits)
        if top is False:
            return min(hits)
        assert len(hits) == 1, f"ambiguous {net} rail: {hits}"
        return hits[0]


@dataclass(frozen=True)
class NodeSpec:
    node: str            # canonical node dir token ("20nm", "05nm", ...)
    wd_unit: int         # unit driver strength (file wd_X<unit>.gds)
    y_row0: float        # y origin of the first (unflipped) bitcell row
    bl_x: float          # BL track x at column datum (= bitcell stub x + x_off)
    blbar_x: float
    strap_w: float       # M3 bitline strap width (node M3 width)
    wl_band: tuple       # (y0, y1) of the bitcell's internal WL M0 shape
    col_pitch: float     # horizontal column pitch = bitcell width
                         # (20nm 0.66 um confirmed by the layout owner)
    cells: dict          # name -> CellGeom
    sa_flip: bool        # sense amp drawn VDD-on-top -> flip so VDD faces down
    buf_flip: bool       # buffer drawn VDD-on-bottom -> flip so VDD faces up


# Frozen per-node geometry, measured from the primitive GDS store (2026-07-12).
# Verify against the live GDS store with --check.
NODE_SPECS = {
    "20": NodeSpec(
        node="20nm", wd_unit=4, y_row0=2.089,
        bl_x=0.198, blbar_x=0.462, strap_w=0.066,
        wl_band=(0.331, 0.371), col_pitch=0.66,
        cells={
            "sram_cell": CellGeom((-0.006, 0.091, 0.654, 1.011),
                                  ((0.091, 0.211, "VSS"), (0.891, 1.011, "VDD")),
                                  x_off=-0.060),
            "pc": CellGeom((0.027, 0.222, 0.687, 0.532),
                           ((0.412, 0.532, "VDD"),), x_off=-0.093),
            "sense_amp": CellGeom((0.017, 0.014, 0.677, 1.094),
                                  ((0.014, 0.134, "VSS"), (0.974, 1.094, "VDD")),
                                  x_off=-0.083),
            "buffer": CellGeom((0.017, 0.006, 0.677, 0.766),
                               ((0.006, 0.126, "VSS"), (0.646, 0.766, "VDD")),
                               x_off=-0.083),
            "wd": CellGeom((0.0, 0.0, 0.66, 2.68), (), x_off=-0.066),
        },
        sa_flip=True, buf_flip=False),
    "16": NodeSpec(
        node="16nm", wd_unit=4, y_row0=2.0,
        bl_x=0.193, blbar_x=0.409, strap_w=0.054,
        wl_band=(0.128, 0.16), col_pitch=0.494,
        cells={
            "sram_cell": CellGeom((0.0, 0.0, 0.494, 0.736),
                                  ((0.0, 0.096, "VSS"), (0.64, 0.736, "VDD"))),
            "pc": CellGeom((0.0, 0.0, 0.494, 0.515), ((0.419, 0.515, "VDD"),)),
            "sense_amp": CellGeom((0.0, 0.0, 0.494, 0.864),
                                  ((0.0, 0.096, "VSS"), (0.768, 0.864, "VDD"))),
            "buffer": CellGeom((0.0, 0.0, 0.494, 0.608),
                               ((0.0, 0.096, "VSS"), (0.512, 0.608, "VDD"))),
            # scaled-from-20nm driver, shifted -1 nm onto the BL grid 2026-07-12
            "wd": CellGeom((-0.001, 0.0, 0.493, 2.656), ()),
        },
        sa_flip=True, buf_flip=False),
    "10": NodeSpec(
        node="10nm", wd_unit=2, y_row0=2.0,
        bl_x=0.142, blbar_x=0.302, strap_w=0.04,
        wl_band=(0.144, 0.168), col_pitch=0.364,
        cells={
            "sram_cell": CellGeom((0.0, 0.0, 0.364, 0.552),
                                  ((0.0, 0.072, "VSS"), (0.48, 0.552, "VDD"))),
            "pc": CellGeom((0.0, 0.0, 0.364, 0.186), ((0.114, 0.186, "VDD"),)),
            "sense_amp": CellGeom((0.0, 0.0, 0.364, 0.648),
                                  ((0.0, 0.072, "VSS"), (0.576, 0.648, "VDD"))),
            "buffer": CellGeom((0.0, 0.0, 0.364, 0.408),
                               ((0.0, 0.072, "VSS"), (0.336, 0.408, "VDD"))),
            "wd": CellGeom((0.0, 0.001, 0.364, 1.24), ()),
        },
        sa_flip=True, buf_flip=False),
    "7": NodeSpec(
        node="07nm", wd_unit=4, y_row0=2.0,
        bl_x=0.115, blbar_x=0.243, strap_w=0.03,
        wl_band=(0.072, 0.09), col_pitch=0.294,
        cells={
            "sram_cell": CellGeom((0.0, 0.0, 0.294, 0.414),
                                  ((0.0, 0.054, "VSS"), (0.36, 0.414, "VDD"))),
            "pc": CellGeom((0.0, -0.09, 0.294, 0.144), ((0.09, 0.144, "VDD"),)),
            # flipped vertically 2026-07-12 to the store convention (VDD on top)
            "sense_amp": CellGeom((0.0, 0.0, 0.294, 0.486),
                                  ((0.0, 0.054, "VSS"), (0.432, 0.486, "VDD"))),
            "buffer": CellGeom((0.0, 0.0, 0.294, 0.342),
                               ((0.0, 0.054, "VSS"), (0.288, 0.342, "VDD"))),
            "wd": CellGeom((0.0, -0.864, 0.294, 0.918), ()),
        },
        sa_flip=True, buf_flip=False),
    "5": NodeSpec(
        node="05nm", wd_unit=2, y_row0=2.0,
        bl_x=0.086, blbar_x=0.186, strap_w=0.02,
        wl_band=(0.056, 0.07), col_pitch=0.222,
        cells={
            "sram_cell": CellGeom((0.0, 0.0, 0.222, 0.322),
                                  ((0.0, 0.042, "VSS"), (0.28, 0.322, "VDD"))),
            "pc": CellGeom((0.0, 0.0, 0.222, 0.106), ((0.064, 0.106, "VDD"),)),
            "sense_amp": CellGeom((0.0, 0.0, 0.222, 0.378),
                                  ((0.0, 0.042, "VSS"), (0.336, 0.378, "VDD"))),
            # flipped vertically 2026-07-12 to the store convention (VDD on top)
            "buffer": CellGeom((0.0, 0.0, 0.222, 0.392),
                               ((0.0, 0.042, "VSS"), (0.35, 0.392, "VDD"))),
            "wd": CellGeom((0.0, 0.0, 0.222, 0.494), ()),
        },
        sa_flip=True, buf_flip=False),
}


def norm_node(s):
    key = str(s).lower().replace("nm", "").lstrip("0") or "0"
    if key not in NODE_SPECS:
        sys.exit(f"unknown node '{s}' (known: {', '.join(NODE_SPECS)})")
    return key


def r4(v):
    return round(v, 4)


def _catalog_entry(spec):
    """The node's tech_libs/catalog.json object (stream of JSON objects)."""
    dec = json.JSONDecoder()
    text = open(CATALOG).read()
    node = str(int(spec.node.rstrip("nm")))
    i = 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        obj, i = dec.raw_decode(text, i)
        if obj.get("node") == node:
            return obj
    sys.exit(f"node {node} not in {CATALOG}")


def lib_gds(spec):
    """SRAM primitive store: tech_libs/techlib_<N>nm/sram/gds/."""
    e = _catalog_entry(spec)
    if not e.get("sramdir"):
        sys.exit(f"node {spec.node}: no sramdir in {CATALOG}")
    d = os.path.join(os.path.dirname(CATALOG), e["corners"][0]["directory"],
                     e["sramdir"], "gds")
    if not os.path.isdir(d):
        sys.exit(f"no SRAM primitive store: {d}")
    return d


def cfg_dir(spec, cell):
    """Per-config work tree: sram/TECH_<N>nm/<cell>/."""
    return os.path.join(SRAM_DIR, f"TECH_{spec.node}", cell)


def find_gds(spec, cell):
    """Locate a cell GDS: generated config store first, then the library."""
    for p in (os.path.join(cfg_dir(spec, cell), "01_gds", f"{cell}.gds"),
              os.path.join(lib_gds(spec), f"{cell}.gds")):
        if os.path.isfile(p):
            return p
    return None


def out_gds(spec, cell):
    """Output path for a generated cell (creates <cfg>/01_gds/)."""
    d = os.path.join(cfg_dir(spec, cell), "01_gds")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{cell}.gds")


def read_top(path, name):
    cells = {c.name: c for c in gdstk.read_gds(path).cells}
    if name not in cells:
        sys.exit(f"{path}: no cell '{name}' (has: {sorted(cells)})")
    return cells


def full_rails(cell, labels=None):
    """Full-width M0 rails of a cell, tagged with the VDD/VSS label on them."""
    (x0, y0), (x1, y1) = cell.bounding_box()
    w = x1 - x0
    labels = labels if labels is not None else cell.labels
    out = []
    for p in cell.get_polygons(depth=None, layer=L_M0[0], datatype=L_M0[1]):
        (px0, py0), (px1, py1) = p.bounding_box()
        if (px1 - px0) < 0.9 * w:
            continue
        net = "?"
        for l in labels:
            if l.text in ("VDD", "VSS") and py0 - 0.01 <= l.origin[1] <= py1 + 0.01:
                net = l.text
        out.append((r4(py0), r4(py1), net))
    return tuple(sorted(set(out)))


def load_flat(lib, path, name):
    src = read_top(path, name)[name]
    dst = lib.new_cell(name)
    dst.add(*[p.copy() for p in src.polygons])
    dst.add(*[l.copy() for l in src.labels])
    for pth in src.paths:
        dst.add(pth.copy())
    return dst


def load_wd(lib, path, name):
    """Bring the driver ladder into lib preserving its unit-cell hierarchy."""
    src_lib = gdstk.read_gds(path)
    names = {c.name for c in src_lib.cells}
    if name not in names:
        sys.exit(f"{path}: no cell '{name}' (has: {sorted(names)})")
    for c in src_lib.cells:
        lib.add(c)
    return {c.name: c for c in src_lib.cells}[name]


def check_cell(name, cell, geom):
    """Guard against a re-delivered GDS drifting from the frozen spec."""
    (x0, y0), (x1, y1) = cell.bounding_box()
    bbox = (r4(x0), r4(y0), r4(x1), r4(y1))
    if bbox != geom.bbox:
        sys.exit(f"{name}: GDS bbox {bbox} != frozen spec {geom.bbox} — "
                 f"re-derive NODE_SPECS (--check) after re-delivery")
    if geom.rails:
        rails = full_rails(cell)
        if rails != tuple(sorted(geom.rails)):
            sys.exit(f"{name}: GDS rails {rails} != frozen spec {geom.rails}")


def add_pin(cell, text, layer, x, y):
    mag = PIN_MAG_POWER if text in ("VDD", "VSS") else PIN_MAG_SIGNAL
    cell.add(gdstk.Label(text, (r4(x), r4(y)), layer=layer, magnification=mag))


def net_via2_extent(placed, xc, tol=BL_VIA_TOL):
    """Lowest/highest VIA2-stub y on a bitline x-track across all placed
    cells (flattened, so every stacked driver copy is included)."""
    lo = hi = None
    for cell, ox, oy, flip, _role in placed:
        for p in cell.get_polygons(depth=None, layer=L_VIA2[0], datatype=L_VIA2[1]):
            (px0, py0), (px1, py1) = p.bounding_box()
            if abs((px0 + px1) / 2 + ox - xc) > tol:
                continue
            y0, y1 = (oy - py1, oy - py0) if flip else (oy + py0, oy + py1)
            lo = y0 if lo is None else min(lo, y0)
            hi = y1 if hi is None else max(hi, y1)
    return lo, hi


def build_column(spec, rows, s, col=0):
    if not (ROWS_MIN <= rows <= ROWS_MAX):
        raise ValueError(f"rows must be in {ROWS_MIN}..{ROWS_MAX} (got {rows})")
    if s % spec.wd_unit:
        raise ValueError(f"wd strength must be a multiple of X{spec.wd_unit} "
                         f"at {spec.node} (got X{s})")
    store = lib_gds(spec)
    wd_name = f"wd_X{s}"
    wd_path = find_gds(spec, wd_name)
    if wd_path is None:
        sys.exit(f"{wd_name}.gds not found — generate it first: "
                 f"gen_wd.py --node {spec.node.rstrip('nm').lstrip('0')} X{s}")

    lib = gdstk.Library(name=f"column_X{s}_{rows}")
    cells = {n: load_flat(lib, os.path.join(store, f"{n}.gds"), n)
             for n in ("buffer", "sense_amp", "sram_cell", "pc")}
    for n in ("buffer", "sense_amp", "sram_cell", "pc"):
        check_cell(n, cells[n], spec.cells[n])
    c_wd = load_wd(lib, wd_path, wd_name)
    if s == spec.wd_unit:
        check_cell(wd_name, c_wd, spec.cells["wd"])

    # driver rails measured from the ladder (top rail rises with strength)
    wd_rails = full_rails(c_wd)
    wd_vdd_rails = [rl for rl in wd_rails if rl[2] == "VDD"]
    assert len(wd_vdd_rails) >= 2, f"wd ladder rails: {wd_rails}"
    wd_bot, wd_top = min(wd_vdd_rails), max(wd_vdd_rails)

    top = lib.new_cell(f"column_X{s}_{rows}")
    cx = col * spec.col_pitch
    placed = []

    def place(name, cell, oy, flip=False):
        ox = cx + spec.cells[name if name in spec.cells else "wd"].x_off
        top.add(gdstk.Reference(cell, (ox, r4(oy)), x_reflection=flip))
        placed.append((cell, ox, r4(oy), flip, name))

    # ---- bitcell rows: mirror-tiled, sharing alternating VSS/VDD rails ----
    sram = spec.cells["sram_cell"]
    vss = sram.rail("VSS")
    vdd = sram.rail("VDD")
    period = r4(2 * (vdd[0] - vss[0]))
    y0n = spec.y_row0
    y0f = r4(y0n + vdd[0] + sram.bbox[3])   # flipped origin sharing row0's VDD rail
    rows_yf = [(r4(y0n + period * k), False) for k in range((rows + 1) // 2)]
    rows_yf += [(r4(y0f + period * k), True) for k in range(rows // 2)]
    rows_yf.sort(key=lambda t: t[0])

    # ---- sense amp below row 0: VSS rail up (to row0), VDD rail down ------
    sa = spec.cells["sense_amp"]
    row0_vss = r4(y0n + vss[0])             # abs y0 of row0's bottom VSS rail
    sa_vss, sa_vdd = sa.rail("VSS"), sa.rail("VDD")
    sa_y = r4(row0_vss + sa_vss[1]) if spec.sa_flip else r4(row0_vss - sa_vss[0])
    sa_vdd_abs = r4(sa_y - sa_vdd[1]) if spec.sa_flip else r4(sa_y + sa_vdd[0])

    # ---- driver below the SA: ladder's top VDD rail under the SA's --------
    wd_y = r4(sa_vdd_abs - wd_top[0])

    # ---- buffer below the driver: VDD rail up, under the ladder's bottom --
    buf = spec.cells["buffer"]
    buf_vdd = buf.rail("VDD")
    wd_bot_abs = r4(wd_y + wd_bot[0])
    buf_y = r4(wd_bot_abs + buf_vdd[1]) if spec.buf_flip else r4(wd_bot_abs - buf_vdd[0])

    place("buffer", cells["buffer"], buf_y, flip=spec.buf_flip)
    place("wd", c_wd, wd_y)
    place("sense_amp", cells["sense_amp"], sa_y, flip=spec.sa_flip)

    sram_x = cx + sram.x_off
    for i, (y, flip) in enumerate(rows_yf):
        place("sram_cell", cells["sram_cell"], y, flip=flip)
        w0, w1 = spec.wl_band
        wy0, wy1 = (r4(y - w1), r4(y - w0)) if flip else (r4(y + w0), r4(y + w1))
        top.add(gdstk.rectangle((r4(sram_x + sram.bbox[0]), wy0),
                                (r4(sram_x + sram.bbox[2]), wy1), layer=L_M0[0]))
        add_pin(top, f"wl[{i}]", L_M0PIN,
                sram_x + (sram.bbox[0] + sram.bbox[2]) / 2, (wy0 + wy1) / 2)

    # ---- pc floating PC_CLEARANCE above the top row edge ------------------
    top_edge = max((y - sram.bbox[1]) if flip else (y + sram.bbox[3])
                   for y, flip in rows_yf)
    pc_y = r4(top_edge + PC_CLEARANCE - spec.cells["pc"].bbox[1])
    place("pc", cells["pc"], pc_y)

    # ---- bitlines: one M3 strap per track over every VIA2 stub ------------
    def draw_bl(xc, name):
        lo, hi = net_via2_extent(placed, xc)
        if lo is None:
            raise RuntimeError(f"no VIA2 stubs on the {name} track x={xc}")
        y0, y1 = r4(lo - BL_M3_MARGIN), r4(hi + BL_M3_MARGIN)
        top.add(gdstk.rectangle((r4(xc - spec.strap_w / 2), y0),
                                (r4(xc + spec.strap_w / 2), y1), layer=L_M3[0]))
        add_pin(top, name, L_M3PIN, xc, (y0 + y1) / 2)
        return y0, y1

    bl_y = draw_bl(r4(cx + spec.bl_x), "BL")
    blbar_y = draw_bl(r4(cx + spec.blbar_x), "BL_bar")

    # ---- promote sub-cell port labels onto the top cell -------------------
    seen = set()
    for cell, ox, oy, flip, role in placed:
        keep = PROMOTE[role]
        for l in cell.labels:
            if l.text not in keep:
                continue
            lx = r4(ox + l.origin[0])
            ly = r4(oy - l.origin[1] if flip else oy + l.origin[1])
            if (l.text, lx, ly) in seen:
                continue
            seen.add((l.text, lx, ly))
            add_pin(top, l.text, l.layer, lx, ly)

    return lib, top, dict(wd_y=wd_y, buf_y=buf_y, sa_y=sa_y, pc_y=pc_y,
                          bl_y=bl_y, blbar_y=blbar_y)


# ---------------------------------------------------------------------------
# --check: re-derive the frozen numbers from the GDS store and diff
# ---------------------------------------------------------------------------
def check_node(key):
    spec = NODE_SPECS[key]
    store = lib_gds(spec)
    unit = f"wd_X{spec.wd_unit}"
    drift = 0

    def cmp(what, derived, frozen):
        nonlocal drift
        ok = derived == frozen
        drift += 0 if ok else 1
        mark = "OK   " if ok else "DRIFT"
        print(f"  {mark} {what:28s} derived={derived}"
              + ("" if ok else f"  frozen={frozen}"))

    print(f"== {spec.node} ==")
    loaded = {}
    for name in ("sram_cell", "pc", "sense_amp", "buffer", unit):
        cell = read_top(os.path.join(store, f"{name}.gds"), name)[name]
        loaded[name] = cell
        key2 = "wd" if name == unit else name
        geom = spec.cells[key2]
        (x0, y0), (x1, y1) = cell.bounding_box()
        cmp(f"{key2}.bbox", (r4(x0), r4(y0), r4(x1), r4(y1)), geom.bbox)
        if geom.rails:
            cmp(f"{key2}.rails", full_rails(cell), tuple(sorted(geom.rails)))

    # VIA2 stub alignment on both tracks, per cell
    for name, cell in loaded.items():
        key2 = "wd" if name == unit else name
        stubs = set()
        for p in cell.get_polygons(depth=None, layer=L_VIA2[0], datatype=L_VIA2[1]):
            (px0, py0), (px1, py1) = p.bounding_box()
            stubs.add(r4((px0 + px1) / 2 + spec.cells[key2].x_off))
        want = [spec.bl_x] + ([] if name == "buffer" else [spec.blbar_x])
        missing = [x for x in want
                   if not any(abs(x - sx) <= 0.001 for sx in stubs)]
        cmp(f"{key2}.bl_stubs", "aligned" if not missing else f"missing {missing}",
            "aligned")

    # WL band = the bitcell M0 shape under the WL label
    cell = loaded["sram_cell"]
    wl = [l for l in cell.labels if l.text == "WL"]
    band = None
    if wl:
        lx, ly = wl[0].origin
        for p in cell.get_polygons(depth=None, layer=L_M0[0], datatype=L_M0[1]):
            (px0, py0), (px1, py1) = p.bounding_box()
            if px0 <= lx <= px1 and py0 <= ly <= py1:
                band = (r4(py0), r4(py1))
    cmp("wl_band", band, spec.wl_band)

    # orientation policy from rail nets
    sa_rails = sorted(spec.cells["sense_amp"].rails)
    cmp("sa_flip", full_rails(loaded["sense_amp"])[-1][2] == "VDD", spec.sa_flip)
    buf_rails = full_rails(loaded["buffer"])
    cmp("buf_flip", buf_rails[-1][2] != "VDD", spec.buf_flip)

    print(f"  {'clean' if not drift else f'{drift} DRIFT(S)'}")
    return drift


def main():
    ap = argparse.ArgumentParser(description="node-aware SRAM column compiler")
    ap.add_argument("--node", required=True, help="20|16|10|7|5")
    ap.add_argument("--rows", type=int, default=32)
    ap.add_argument("--wd", type=int, default=0,
                    help="driver strength S (wd_X<S>; default: node unit)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="re-derive frozen NODE_SPECS values from GDS and diff")
    args = ap.parse_args()

    key = norm_node(args.node)
    spec = NODE_SPECS[key]
    if args.check:
        sys.exit(1 if check_node(key) else 0)

    s = args.wd or spec.wd_unit
    lib, top, info = build_column(spec, args.rows, s)
    out = args.out or out_gds(spec, top.name)
    if os.path.exists(out) and not args.force:
        sys.exit(f"{out} exists (use --force)")
    lib.write_gds(out)
    (bx0, by0), (bx1, by1) = top.bounding_box()
    print(f"wrote {out}")
    print(f"  node={spec.node} rows={args.rows} wd=X{s}")
    print(f"  bbox=({r4(bx0)},{r4(by0)})..({r4(bx1)},{r4(by1)})  "
          f"w={r4(bx1-bx0)} h={r4(by1-by0)}  area={r4((bx1-bx0)*(by1-by0))} um2")
    print(f"  buf_y={info['buf_y']} wd_y={info['wd_y']} sa_y={info['sa_y']} "
          f"pc_y={info['pc_y']}")
    print(f"  BL m3 y=[{info['bl_y'][0]},{info['bl_y'][1]}]  "
          f"BL_bar y=[{info['blbar_y'][0]},{info['blbar_y'][1]}]")


if __name__ == "__main__":
    main()
