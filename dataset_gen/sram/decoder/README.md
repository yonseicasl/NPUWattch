# decoder — SRAM row-decoder characterization flow

Standalone post-layout characterization of the SRAM wordline decoder
(FPGA-BRAM style: address registered at posedge clk when `en`, one-hot
decode, WL pulse gated by `wlen`).  One command per (node, rows, cols):

```
./run_decoder.sh --node 20 --rows 16 --cols 4
```

The autosweep runner (`../autosweep/run_batch.sh`) invokes this
automatically after each array job (once per node/rows/cols/V/T/pex point,
with `--reuse-gds`); run it by hand for one-off configs or reruns.

Pipeline: RTL gen → DC synthesis → ICC2 PnR → GDS text-layer remap +
power-rail labels → std-cell layout merge → ICV GDS2SPICE + StarRC PEX
(shared `spice/gds2spice.sh`) → HSPICE transient → `measures.csv`.
Then `scripts/collect_decoder.py` rebuilds `datasets/sram_decoder.csv` and
joins `decoder_area_um2` / `macro_area_um2` into `datasets/sram_array.csv`.

## Energy accounting (no double counting)

The array TB drives its wordline with an **ideal PWL source**, so wordline
charging energy is unbooked in the array sheet.  Here every decoder WL
output carries a **pi model of the array wordline RC** (`wl_load.py`
parses the wl[0] `*D_NET` cap and `*RES` sum from the array's SPEF; both
scale linearly in cols and are independent of rows).  Decoder energies
therefore own: register + decode logic + WL driver + wordline CV².
The TB clocks at the array's 10 ns/op cadence with wlen high at T+2..T+5 —
the exact WL window of the array TB.

## Floorplan (pitch-matched row decoder)

Height is fixed to the array die height (from the `gds/array_*.json`
sidecar; interpolated across rows if the exact config has no sidecar),
rounded up to a whole std-cell row.  Width is derived at 70 % target
utilization from the **post-sizing** cell area: ICC2 coarse-places once in
a loose box (place_opt resizes for the easy 10 ns timing), re-floorplans at
the target, then runs the real place/CTS/route.  `wl[i]` pins sit on the
east edge at the array row pitch; controls on the west edge.
`dec_area_um2` in the sheet = the die box (layout-honest, integration
overhead included); `macro_area_um2` = array + decoder (shared height ⇒
one clean rectangle).

## Per-node GDS handling

- ICC2 streams port text on drawing-layer numbers; the LVS runsets expect
  text layers.  `scripts/text_layer_map.sed` is the proven remap table from
  the legacy flow, applied at **every node incl. 5 nm** — ICC2's stream-out
  text numbering is identical everywhere (the "no remap at 5 nm" convention
  applies to the custom SRAM GDT flow, not to ICC2 output).
- Top-level routing stays off M1 (`min_routing_layer M2`): the frames carry
  no M1 blockages, so M1 routes can short cell internals.  At 5 nm only,
  vias are additionally forced fully inside pin shapes
  (`route.common.connect_within_pins_by_layer_name`, `DEC_PIN_VIA_STRICT`)
  — a via pad centered on the M2 track clipped an internal DFF wire 8 nm
  below the D pin.  The same option at 20 nm produced merged decode nets in
  extraction, so it is per-node, on only where needed.
- Power rails have no logical ports → no text.  `icc2.tcl` exports the
  exact VDD/VSS M0 rail tracks (`rails.json`); `scripts/label_rails.py`
  adds `t{88 ... 'VDD'}` labels.  The 2× `text_open_merge` ICV violation on
  VDD/VSS is expected (rails join only through the cell rows) — same
  accepted convention as the column/array flow.
- The NDMs carry only frame views, so the streamed GDS references std cells
  without geometry; `scripts/merge_stdcells.py` (gdstk) injects the layouts
  from the catalog `gdsdir` store (`dataset_gen/tech_libs/techlib_<N>nm/gds/`;
  handles the 5 nm no-underscore cell naming).

## Dataset columns (`datasets/sram_decoder.csv`)

`dec_act_energy_pJ` (activation, same address = steady state),
`dec_flip_energy_pJ` (all addr bits toggle — upper bound),
`dec_idle_energy_pJ` (en=0, clk running), `dec_leak_power_mW` (raw, no
subtraction), `dec_clk_wl_ns` (clk→WL far node; includes the 2 ns wlen
gate by construction), `dec_wlen_wl_ns` (driver + WL RC — add to the
array's wl→OUT for the serial read path), `dec_wl_rise_ns` (10–90 % at the
far end — feed back into the array TB PWL slope if it grows), plus the WL
load, die W/H/area, achieved utilization, and `flow_run_id`.

## Layout

```
decoder/
├── run_decoder.sh        # the one entry point (see --help)
├── scripts/              # gen_decoder_rtl / wl_load / dc.tcl / icc2.tcl /
│                         # text_layer_map.sed / label_rails /
│                         # merge_stdcells / gen_dec_tb / dec_measures /
│                         # collect_decoder
└── site.env              # optional overrides: DC_ENV, ICC2_ENV, GDT_DIR,
                          # DEC_LOAD_SCALE, PYTHON_GDSTK
```

All work lands in the per-config tree `sram/TECH_<N>nm/dec_<R>x<C>/`, stage
dirs in creation order: `01_syn` (DC) → `02_pnr` (ICC2) → `03_gds` (remap +
labels + std-cell merge; final `dec_<R>x<C>.gds` + `.json` area sidecar) →
`04_pex` (ICV + StarRC keepers) → `05_sim/<run_id>/` (HSPICE). Library
collateral resolves via `spice/scripts/tech_paths.py` from
`tech_libs/catalog.json` (DB/NDM/tf/TLUPlus/map, `gdsdir` std cells,
`sramdir` SRAM pack).

Prereq per config: an array extraction at the node (for the WL load) and
the array GDS sidecar (for the height) — run the array flow / autosweep runner
first.  Requires dc_shell + icc2_shell licenses (tool env csh scripts,
override via site.env) and the gdstk conda python for the cell merge.
