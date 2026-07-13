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
- `corners[]` — one entry per characterized PVT corner with `process`, `voltage`,
  `temperature`, `directory`, and the per-tool file names (`dbfile`, `ndmfile`,
  `techfile`, `tlufile`, `mapfile`, `grdfile`).

## Notes

- The Synopsys tech files here are the maintained versions (the copies in the
  original per-node source archives are outdated — do not re-import from there).
- 5nm GDS cell naming differs from the other nodes: `AND2X1.gds` (no underscore
  before the drive suffix) vs `AND2_X1.gds` at 20/16/10/7nm. Check cell-name
  consistency against the node's `.db`/`.ndm` before any GDS merge at 5nm.
- SPICE transistor model cards live in each node's `sram/models/` (moved here
  2026-07-13 when the SRAM per-node packs were consolidated into tech_libs;
  nothing library-like remains under `dataset_gen/sram/`).
