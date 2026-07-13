# spice — shared extraction + device/model tools

Node-agnostic tools consumed by BOTH sibling flows, `../array/` (wd/column/
array compilers + SPICE TBs) and `../decoder/` (row-decoder PnR flow).
Flow-specific scripts live with their flow; this directory only holds what
they share.

```
spice/
├── gds2spice.sh          # GDS → .sp + .spef  (ICV → icv_nettran → StarXtract)
│                         #   --node N <gds|cellname> [cellname] [--keep]
│                         #   [--outdir <dir>]  (default TECH_<N>nm/<cell>/02_pex)
└── scripts/
    ├── tech_paths.py     # tech_libs/catalog.json → collateral paths; emits
    │                     #   TECH_LIB_DIR/DB/NDM/TF/TLUP/MAP/GRD/GDS/SRAM/VDD/TEMP
    │                     #   (the single source of truth for library locations)
    ├── tie_bulk.py       # extracted-netlist fixup: nmos1 bulk→VSS, pmos1 bulk→VDD
    ├── char_nodes.py     # 5-node single-device IOFF/ION/SS/VT table — run after
    │                     #   ANY model-card change (cards live in
    │                     #   tech_libs/techlib_<N>nm/sram/models/)
    ├── build_5nm.py      # rebuild + retune the 5nm cards from the 7nm sources
    └── char/             # characterization decks/results from char_nodes.py
```

`gds2spice.sh` resolves a bare cell name against `TECH_<N>nm/<name>/01_gds/`
first, then the node's SRAM library (`tech_libs/techlib_<N>nm/sram/gds/`).
Collateral file lookup has one authoritative location per file (no
fallbacks): `NXTGRD`/`LAYOUT_TF` from the techlib root ONLY, `LVS_RS`/
`STARRC_MAP`/`STRC_TEMPLATE` from the sram/ pack ONLY (filenames declared in
`techlib_<N>nm/sram/node.env`).

See `../array/README.md` for the extraction validation history, per-node
tech-pack notes, and the 5nm model-card recalibration record;
`../decoder/README.md` for the decoder flow's use of gds2spice
(`--outdir <cfg>/04_pex`).
