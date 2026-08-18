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
  as `set_dont_use` into `01_syn.tcl` by `logic/autosweep/autosynth.py`.
  Currently unused: it existed only to mask the retired 5nm `MUX_X1`/`MUX_X2`,
  which were removed from the 5nm db/NDM entirely on 2026-07-17 (all five
  nodes now expose the identical 51-cell set).
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
  `AND2X1`→`AND2_X1` etc. to end the old naming quirk). Since 2026-07-17 the
  only GDS-only extras left are `DLH_X1` (all nodes) and the 5nm
  `SDFF_*`/`INV_X*_2` strays; there are no db/NDM cells without GDS at any
  node.
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
- 2026-07-17 refresh (7 new cells characterized + libraries recompiled):
  `NAND4_X1`, `NOR4_X1`, `MUX2_X1`, `MUX2_X2`, `DFFR_X1`, `DL_X1`, `DL_X2`
  were characterized at all 25 corners (2026_0617/2026_0717_char, same
  PrimeLib flow/settings as 2026_0713) and merged into every corner db —
  now exactly **51 cells at every node**. The retired 5nm `MUX_X1`/`MUX_X2`
  were removed from the 5nm db/NDM (and the catalog `dontuse` entry dropped)
  the same day, after verifying the 5nm `MUX2_X1`/`MUX2_X2` are the same
  physical cells renamed (identical GDS polygons/labels, frames, and netlist
  connectivity) — old gate-level netlists that still instantiate `MUX_X1`
  will black-box in PT and must be resynthesized; the Verilog sim models for
  the old names remain in `verilog/` as a compatibility superset (all nodes
  keep sim models for cells outside their db, historical convention).
  All five NDMs were rebuilt from the previous installed frames
  + the release frames + the merged nominal dbs; db↔NDM cell parity and
  db-area↔NDM-frame agreement verified 1285/1285, frame-vs-GDS coverage
  audit PASS at every node (0 uncovered M0/M1 shapes). Two defects fixed on
  the way: (a) BUF_X32/INV_X32 Liberty areas at 20/16/10/7nm still carried
  the 5nm template values (the 07-14 area patch predated the X32 splice) —
  now the real per-node frame areas; (b) the 2026_0716_cells 5nm LEF had
  fragmented metal1 OBS for MUX2_X1/X2 (42-45% of drawn M1 uncovered →
  router-short exposure) — OBS regenerated from GDS
  (2026_0717_char/lef/primelib_cells_5nm_M1fix.lef). Per-node `verilog/`
  packs gained PrimeLib-generated simulation models for the 7 cells
  (behavior verified: NAND4/NOR4/2:1-MUX truth tables, DFFR posedge FF with
  active-low async clear, DL transparent-high latch); the stale bodiless
  10nm `DFFR_X1` shell from the Jan-2026 run was replaced. The previous
  tree (incl. all `.bak_42cell` and `lvs.rs.bak_i3dhdd1` backups) is
  archived in `../tech_libs_old_2.tar.gz`; catalog.json needed no changes
  and re-validates (read_catalog + files-exist + find_tech_corner).
- Known characterization quirk (pre-existing, affects old and new cells
  equally): with `model -leakage_power_calc best`, `cell_leakage_power` is
  the minimum-leakage state, and stacked-off states settle slowly at low
  VDD, so that attribute is not always monotonic vs VDD (e.g. NAND3/NAND4,
  DFF/DFFR at some nodes). Per-state `leakage_power` groups and the INV_X1
  monotonicity gate are unaffected.
- 2026-07-29/30 full re-characterization: all 25 corner dbs and all five
  NDMs were regenerated from a single 51-cell re-characterization run
  (`2026_0617/2026_0729_rechar/`) after fixing two leakage defects reported
  by the NPUWattch logic workstream (`LEAKAGE_RECHAR_REPORT_20260729.md`):
  the OR2_X4 drawn-layout crowbar defect at 20/16/10/7nm (shared
  NOR/inverter diffusion strip — GDS repaired here and in `5_to_20nm`) and
  stale Jan-2026 BUF_X32/INV_X32 netlists containing floating-gate devices
  (re-extracted from the installed GDS). Leakage tables are now sane
  (BUF_X32 = 2x BUF_X16 everywhere; OR2_X4 states ~1-2 nW); the only
  remaining scanner flags are the known `cell_leakage_power : 0` DFF
  entries (min-state settle artifact, deliberately unchanged). All
  verification gates re-run PASS (db<->NDM parity 51/51, area==frame
  1275/1275, frame-vs-GDS coverage 0 uncovered at every node). The 5nm NDM
  build requires `primelib_cells_5nm_M1fix.lef` (the 2026_0716 release LEF
  has fragmented MUX2 M1 OBS). Response doc:
  `2026_0617/LEAKAGE_RECHAR_RESPONSE_20260730.md`.
- Extraction runsets made self-contained on 2026-07-17: every
  `techlib_*/sram/lvs.rs` referenced two files on the now-unreachable
  `/home/i3dhdd1/...` mount (`#define FINFET_PDK`, line 26), which makes ICV
  abort with PXL fatal #913. Local copies now live in `pattmath_local/`
  (see its README for provenance and equivalence proof), and each runset's
  line 26 points there; the pre-patch runsets are kept as
  `lvs.rs.bak_i3dhdd1`. Validated by re-extracting DL_X1 at 20/16/5nm with
  the patched runsets — netlists byte-identical (outside comment headers)
  to the references produced while the original mount was alive. No other
  step of the characterization flow (PrimeLib, StarRC, 5nm DRC deck)
  depends on files outside `/home/KNUEEhdd1`.
