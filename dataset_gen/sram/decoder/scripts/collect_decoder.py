#!/usr/bin/env python3
"""
collect_decoder.py -- rebuild datasets/sram_decoder.csv from decoder run
dirs (TECH_<N>nm/dec_<R>x<C>/05_sim/*/ with meta.json + area.json +
measures.csv), then (unless --no-join) refresh the decoder columns joined
into datasets/sram_array.csv:

  decoder_area_um2   die box of the pitch-matched decoder (same height)
  macro_area_um2     array total_area_um2 + decoder_area_um2

Join key: (node, rows, cols, voltage_offset_V, temperature_C, pex) -- the
decoder is transistor/corner-degenerate for now (one model card per node).
Runs are deduped to the latest flow_run_id per config key, same policy as
collect_array.py.  Run dirs are the source of truth; both sheets are always
rebuildable.

Usage: collect_decoder.py [--sram-dir <path>] [--no-join]
"""
import argparse
import csv
import glob
import json
import os
import sys

COLS = ["node", "transistor", "corner", "voltage_offset_V", "vdd_V",
        "temperature_C", "rows", "cols", "pex",
        "dec_act_energy_pJ", "dec_flip_energy_pJ", "dec_idle_energy_pJ",
        "dec_leak_power_mW", "dec_clk_wl_ns", "dec_wlen_wl_ns",
        "dec_wl_rise_ns", "wl_cap_fF", "wl_res_ohm",
        "dec_width_um", "dec_height_um", "dec_area_um2", "dec_util",
        "clk_ns", "flow_run_id"]

KEY = ("node", "rows", "cols", "voltage_offset_V", "temperature_C", "pex")


def read_measures(path):
    m = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            v = row["value_si"]
            try:
                m[row["measure"]] = float(v) if v else None
            except ValueError:
                m[row["measure"]] = v  # non-numeric row, e.g. verdict
    return m


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--sram-dir",
                    default=os.path.normpath(os.path.join(here, "..", "..")))
    ap.add_argument("--no-join", action="store_true")
    a = ap.parse_args()
    ds = os.path.join(a.sram_dir, "datasets")

    rows = {}
    skipped = 0
    for run in sorted(glob.glob(os.path.join(
            a.sram_dir, "TECH_*nm", "dec_*", "05_sim", "*"))):
        need = [os.path.join(run, f) for f in
                ("meta.json", "area.json", "measures.csv")]
        if not all(os.path.isfile(p) for p in need):
            print("skip (incomplete): %s" % run)
            skipped += 1
            continue
        meta = json.load(open(need[0]))
        area = json.load(open(need[1]))
        m = read_measures(need[2])
        # runs whose functional/range checks failed carry a FAIL verdict
        # from dec_measures.py (values kept for debugging, never collected)
        verdict = m.get("verdict")
        if isinstance(verdict, str) and verdict.startswith("FAIL"):
            print("skip (verdict %s): %s" % (verdict.split(";")[0][:60], run))
            skipped += 1
            continue
        e = {k: m.get(k) for k in
             ("e_act_same_j", "e_act_same2_j", "e_act_flip_j",
              "e_act_back_j", "e_idle_clk_j", "p_leak_w",
              "t_clk_wl", "t_wlen_wl", "t_wl_rise")}
        if any(v is None for v in e.values()):
            print("skip (failed measures): %s" % run)
            skipped += 1
            continue
        r = {
            "node": meta["node"], "transistor": meta["transistor"],
            "corner": meta["corner"],
            "voltage_offset_V": meta["voltage_offset_V"],
            "vdd_V": meta["vdd_V"], "temperature_C": meta["temperature_C"],
            "rows": meta["rows"], "cols": meta["cols"], "pex": meta["pex"],
            # activation energy: same-address ops (steady-state activate)
            "dec_act_energy_pJ": round(
                (e["e_act_same_j"] + e["e_act_same2_j"]) / 2 * 1e12, 6),
            # full address flip (upper bound on addr-toggle overhead)
            "dec_flip_energy_pJ": round(
                (e["e_act_flip_j"] + e["e_act_back_j"]) / 2 * 1e12, 6),
            "dec_idle_energy_pJ": round(e["e_idle_clk_j"] * 1e12, 6),
            "dec_leak_power_mW": round(e["p_leak_w"] * 1e3, 9),
            "dec_clk_wl_ns": round(e["t_clk_wl"] * 1e9, 6),
            "dec_wlen_wl_ns": round(e["t_wlen_wl"] * 1e9, 6),
            "dec_wl_rise_ns": round(e["t_wl_rise"] * 1e9, 6),
            "wl_cap_fF": meta["wl_cap_fF"], "wl_res_ohm": meta["wl_res_ohm"],
            "dec_width_um": area["width_um"],
            "dec_height_um": area["height_um"],
            "dec_area_um2": area["total_area_um2"],
            "dec_util": area.get("util_achieved", ""),
            "clk_ns": meta["clk_ns"], "flow_run_id": meta["flow_run_id"],
        }
        k = tuple(str(r[x]) for x in KEY)
        # latest run wins (flow_run_id ends with the timestamp)
        if k not in rows or rows[k]["flow_run_id"] < r["flow_run_id"]:
            rows[k] = r

    if not rows:
        sys.exit("collect_decoder: no complete decoder runs found")
    os.makedirs(ds, exist_ok=True)
    out = os.path.join(ds, "sram_decoder.csv")
    order = sorted(rows.values(), key=lambda r: (
        -float(str(r["node"]).rstrip("nm")), r["rows"], r["cols"],
        r["voltage_offset_V"], r["temperature_C"]))
    with open(out, "w") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(order)
    print("collect_decoder: wrote %s (%d rows, %d skipped runs)"
          % (out, len(order), skipped))

    if a.no_join:
        return

    # -- join decoder area into the array sheet ---------------------------
    # area is a layout property -- join on (node, rows, cols) only, so
    # PVT-variant array rows share the nominal run's decoder area
    arr_csv = os.path.join(ds, "sram_array.csv")
    if not os.path.isfile(arr_csv):
        print("collect_decoder: no %s to join into" % arr_csv)
        return
    dec_by_key = {(r["node"], str(r["rows"]), str(r["cols"])): r
                  for r in rows.values()}
    with open(arr_csv) as f:
        rd = csv.DictReader(f)
        arr_rows = list(rd)
        fields = list(rd.fieldnames)
    for c in ("decoder_area_um2", "macro_area_um2"):
        if c not in fields:
            fields.append(c)
    n_hit = 0
    for r in arr_rows:
        d = dec_by_key.get((r["node"], str(r["rows"]), str(r["cols"])))
        if d:
            r["decoder_area_um2"] = d["dec_area_um2"]
            r["macro_area_um2"] = round(
                float(r["total_area_um2"]) + float(d["dec_area_um2"]), 4)
            n_hit += 1
        else:
            r.setdefault("decoder_area_um2", "")
            r.setdefault("macro_area_um2", "")
    with open(arr_csv, "w") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(arr_rows)
    print("collect_decoder: joined decoder area into %s "
          "(%d/%d array rows matched)" % (arr_csv, n_hit, len(arr_rows)))


if __name__ == "__main__":
    main()
