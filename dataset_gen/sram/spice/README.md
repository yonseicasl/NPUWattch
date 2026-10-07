# spice: shared extraction, device, and model tools

These node-independent tools are used by **both** sibling flows: `../array/`
(wd/column/array compilers and SPICE TBs) and `../decoder/` (row-decoder PnR
flow). Scripts that only one flow uses live with that flow. This directory
holds only what the two flows share.

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

`gds2spice.sh` looks up a bare cell name in `TECH_<N>nm/<name>/01_gds/`
first, and then in the node's SRAM library (`tech_libs/techlib_<N>nm/sram/gds/`).
Each collateral file has exactly one location, with no fallbacks.
`NXTGRD`/`LAYOUT_TF` come only from the techlib root, and `LVS_RS`/
`STARRC_MAP`/`STRC_TEMPLATE` come only from the sram/ pack (the file names
are set in `techlib_<N>nm/sram/node.env`).

See `../array/README.md` for the extraction validation history, per-node
tech-pack notes, and the 5nm model-card recalibration record. See
`../decoder/README.md` for how the decoder flow uses gds2spice
(`--outdir <cfg>/04_pex`).
