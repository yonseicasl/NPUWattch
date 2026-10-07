# decoder: SRAM row-decoder characterization flow

This is a standalone post-layout characterization flow for the SRAM
wordline decoder. The decoder works like an FPGA BRAM: the address is
registered on the rising clock edge when `en` is high, it is decoded to
one-hot, and `wlen` gates the WL pulse. You run one command for each
(node, rows, cols):

```
./run_decoder.sh --node 20 --rows 16 --cols 4
```

The autosweep runner (`../autosweep/run_batch.py`) calls this flow
automatically after each array job, once per node/rows/cols/V/T/pex point,
with `--reuse-gds`. Run it by hand for one-off configs or reruns.

The pipeline runs these steps in order: RTL generation, DC synthesis, ICC2
PnR, GDS text-layer remap and power-rail labels, std-cell layout merge, ICV
GDS2SPICE and StarRC PEX (shared `spice/gds2spice.sh`), and HSPICE
transient simulation, which writes `measures.csv`. Then
`scripts/collect_decoder.py` rebuilds `datasets/sram_decoder.csv` and joins
`decoder_area_um2` / `macro_area_um2` into `datasets/sram_array.csv`.

## Energy accounting (no double counting)

The array TB drives its wordline with an **ideal PWL source**, so the array
sheet does not include wordline charging energy. Here, every decoder WL
output drives a **pi model of the array wordline RC**. `wl_load.py` reads
the wl[0] `*D_NET` cap and the `*RES` sum from the array's SPEF. Both scale
linearly with cols and do not depend on rows. So the decoder energies cover
the register, the decode logic, the WL driver, and the wordline CV². The TB
clocks at the array's 10 ns/op rate with wlen high at T+2..T+5, which is
exactly the WL window of the array TB.

## Floorplan (pitch-matched row decoder)

The height is fixed to the array die height, taken from the
`gds/array_*.json` sidecar and rounded up to a whole std-cell row. If the
exact config has no sidecar, the height is interpolated across rows. The
width is set for 70 % target utilization based on the cell area **after
sizing**. ICC2 first does a coarse placement in a loose box (place_opt
resizes cells for the easy 10 ns timing), then redoes the floorplan at the
target, and then runs the real place, CTS, and route. The `wl[i]` pins sit
on the east edge at the array row pitch, and the control pins sit on the
west edge. `dec_area_um2` in the sheet is the full die box, so it includes
integration overhead. `macro_area_um2` is the array plus the decoder. Since
both have the same height, the macro is one clean rectangle.

## Per-node GDS handling

- ICC2 writes port text on drawing-layer numbers, but the LVS runsets
  expect text layers. `scripts/text_layer_map.sed` is the remap table from
  the earlier flow, and it is applied at **every node, including 5 nm**.
  ICC2 uses the same text numbering at every node on stream-out. The "no
  remap at 5 nm" convention applies only to the custom SRAM GDT flow.
- Top-level routing starts at M2 (`min_routing_layer M2`), so routes stay
  clear of cell internals on M1. At 5 nm only, vias are also forced fully
  inside pin shapes (`route.common.connect_within_pins_by_layer_name`,
  `DEC_PIN_VIA_STRICT`). This setting is per node and is turned on only
  where it is needed.
  <!-- Original note: Top-level routing stays off M1 (`min_routing_layer
  M2`): the frames carry no M1 blockages, so M1 routes can short cell
  internals. At 5 nm only, vias are additionally forced fully inside pin
  shapes — a via pad centered on the M2 track clipped an internal DFF wire
  8 nm below the D pin. The same option at 20 nm produced merged decode
  nets in extraction, so it is per-node, on only where needed. -->
- Power rails have no logical ports, so they get no text. `icc2.tcl`
  exports the exact VDD/VSS M0 rail tracks (`rails.json`), and
  `scripts/label_rails.py` adds `t{88 ... 'VDD'}` labels. ICV reports the
  `text_open_merge` check twice on VDD/VSS. This is expected, because the
  rails connect only through the cell rows. The column/array flow follows
  the same convention.
- The NDMs contain only frame views, so the streamed GDS refers to std
  cells without geometry. `scripts/merge_stdcells.py` (gdstk) adds the
  layouts from the catalog `gdsdir` store
  (`dataset_gen/tech_libs/techlib_<N>nm/gds/`). It also handles the 5 nm
  cell names that have no underscore.

## Dataset columns (`datasets/sram_decoder.csv`)

- `dec_act_energy_pJ`: activation with the same address (steady state)
- `dec_flip_energy_pJ`: all address bits toggle (upper bound)
- `dec_idle_energy_pJ`: en=0 with the clock running
- `dec_leak_power_mW`: raw leakage, nothing subtracted
- `dec_clk_wl_ns`: clk to the far node of the WL. By design, this includes
  the 2 ns wlen gate.
- `dec_wlen_wl_ns`: driver plus WL RC. Add it to the array's wl-to-OUT delay
  to get the serial read path.
- `dec_wl_rise_ns`: 10–90 % rise time at the far end. If this value grows,
  update the PWL slope in the array TB to match.
- Also: the WL load, die W/H/area, achieved utilization, and `flow_run_id`.

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

All work goes into the per-config tree `sram/TECH_<N>nm/dec_<R>x<C>/`. The
stage directories, in the order they are created, are `01_syn` (DC),
`02_pnr` (ICC2), `03_gds` (remap, labels, and std-cell merge; final
`dec_<R>x<C>.gds` plus a `.json` area sidecar), `04_pex` (kept ICV and
StarRC outputs), and `05_sim/<run_id>/` (HSPICE). Library files are found
through `spice/scripts/tech_paths.py` from `tech_libs/catalog.json`
(DB/NDM/tf/TLUPlus/map, `gdsdir` std cells, `sramdir` SRAM pack).

Before you run a config, you need an array extraction at the node (for the
WL load) and the array GDS sidecar (for the height). So run the array flow
or the autosweep runner first. The flow needs dc_shell and icc2_shell
licenses (tool env csh scripts, which you can override in site.env) and the
gdstk conda python for the cell merge.
