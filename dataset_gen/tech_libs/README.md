# tech_libs — shared per-node technology collateral

One directory per node, shared by the **logic** (`dataset_gen/logic`) and **SRAM**
(`dataset_gen/sram`) flows so both consume the same libraries at a node. Adding a
future node (3/2nm already stubbed) = drop a `techlib_NNnm/` directory and append a
catalog entry; no flow code changes.

```
tech_libs/
├── catalog.json          # committed — the only committable file here
└── techlib_NNnm/         # git-ignored (PDK-derived; never commit contents)
    ├── *.db  *.ndm       # Design Compiler / IC Compiler II libraries
    ├── *.mw.tf           # layout tech file
    ├── *.tluplus *.nxtgrd + map file   # PEX (StarRC)
    ├── gds/              # standard-cell GDSII (one file per cell)
    └── sram/             # SRAM library pack (catalog "sramdir"; 20/16/10/7/5nm)
        ├── node.env      #   VDD/TEMP/BL_CAP + tech file names (sourced by sram flows)
        ├── gds/          #   hand-delivered primitives: sram_cell, pc, sense_amp,
        │                 #   buffer, unit wd_X<u> (SOURCE cells — not regenerable)
        ├── models/       #   nmos1.inc / pmos1.inc HSPICE model cards
        └── lvs.rs  strc_map_file.map  extract_template.strc   # ICV/StarRC setup
```

Tech files (nxtgrd, layout tf — incl. the custom 20nm `hx2mw.tf`) live in the
techlib root only; the `sram/` pack holds only SRAM-specific collateral. The
`techlib_05nm/i3d_5nm.nxtgrd` is the healthy grd regenerated 2026-07-12 from
the 2025 ITF (the previous copy — and the one still in `~/tech_libs` — was
gzip-truncated by 35 bytes).

## catalog.json

A concatenated stream of JSON objects (not a JSON array), one per node; parsed by
`logic/autosweep/autocommon.py:read_catalog()`. Unknown keys are ignored, so fields
can be added without breaking older readers. Current schema per node:

- `node` — node string without the `nm` suffix (`"20"` … `"2"`).
- `gdsdir` — subdirectory holding std-cell GDS, relative to the corner's
  `directory` (present for 20/16/10/7/5nm; add when GDS lands for a node).
- `sramdir` — subdirectory holding the node's SRAM library pack (primitives,
  model cards, ICV/StarRC setup, node.env), relative to the corner's
  `directory` (present for 20/16/10/7/5nm). Resolved by
  `sram/spice/scripts/tech_paths.py` for all SRAM flows.
- `verilogdir` — subdirectory holding the PrimeLib-emitted Verilog simulation
  models (`verilog.v` + `verilog_udp.v`) for gate-level sim (20/16/10/7/5nm).
- `dontuse` — optional list of lib cells synthesis must not map to; injected
  as `set_dont_use` into `01_syn.tcl` by `logic/autosweep/autosynth.py`. Used
  at 5nm to exclude `MUX_X1`/`MUX_X2` so the mapped cell set stays uniform
  with the 44-cell 20–7nm libraries (those nodes have no MUX layouts).
- `corners[]` — one entry per characterized PVT corner with `process`, `voltage`,
  `temperature`, `directory`, and the per-tool file names (`dbfile`, `ndmfile`,
  `techfile`, `tlufile`, `mapfile`, `grdfile`).

## Notes

- The Synopsys tech files here are the maintained versions (the copies in the
  original per-node source archives are outdated — do not re-import from there).
- 2026-07-13 refresh: every 20–5nm node now carries 5 TT voltage corners
  (nominal ±0.10 V; see `corners[]`), recharacterized with the current model
  cards (2026_0617/2026_0713 flow). The 5nm `.ndm` was rebuilt with complete
  metal0/metal1 frame obstructions. The previous tree is archived in
  `../tech_libs_old.tar.gz`.
- GDS↔db cell-name consistency is enforced as of 2026-07-13: every `.db` cell
  has a matching GDS structure at its node (the 5nm AND-family GDS was renamed
  `AND2X1`→`AND2_X1` etc. to end the old naming quirk; `BUF_X32`, `INV_X32`,
  `MUX_X1`, `MUX_X2` exist only at 5nm and were dropped from the 20/16/10/7nm
  libraries, which have no such layouts). GDS-only extras (`MUX2_*`, `DFFR_X1`,
  `DLH_X1`, `DL_*`, `NAND4_X1`, `NOR4_X1`, 5nm `SDFF_*`/`INV_X*_2`) have no
  netlists/characterization data and are not in any `.db`.
- SPICE transistor model cards live in each node's `sram/models/` (moved here
  2026-07-13 when the SRAM per-node packs were consolidated into tech_libs;
  nothing library-like remains under `dataset_gen/sram/`).
- Liberty `area` attributes are truthful per node as of 2026-07-14: every
  cell in every `.db` carries its real placement footprint (um^2) taken from
  that node's NDM frame boundary (e.g. INV_X1: 0.2112 at 20nm down to 0.0168
  at 5nm), replacing the template-inherited 5nm values that were identical
  across nodes. Timing/power tables are untouched; only `area` changed, so
  DC/PT area reports now scale with the node.
- NDM cell sets pruned to match the `.db` cell sets as of 2026-07-14: the
  20/16/10/7nm NDMs each carried 4 frame-only phantom cells (`BUF_X32`,
  `INV_X32`, `MUX_X1`, `MUX_X2`) with no timing data or GDS at those
  nodes, which ICC2 could otherwise select during optimization. They were
  removed via the icc2_lm edit-flow workspace; every NDM now contains exactly
  the cells of its node's db (42 at 20/16/10/7nm, 46 at 5nm), frame
  coverage re-audited PASS, frame+timing views intact.
