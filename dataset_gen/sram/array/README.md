# SRAM array compiler and SPICE flows (node-aware)

This flow covers all five nodes with one set of scripts. It runs alongside
`../decoder/` (the row-decoder PnR flow), and the shared extraction and
device-model tools live in `../spice/`. It replaces the per-node copies in
`array_spice/20_wd_spice` and `array_spice/20_col_spice`, which stay in place
as a reference.
<!-- Original wording: "kept untouched as reference until this flow is fully adopted". -->

All library collateral (tech files, model cards, primitive GDS) lives in the
shared `dataset_gen/tech_libs/` tree. The flow finds each file through
`tech_libs/catalog.json` (`../spice/scripts/tech_paths.py`), and nothing is
copied under `sram/`. Generated files are grouped by node first, with one
directory per configuration and numbered stage directories in the order they
are created. This is the same layout as `dataset_gen/logic/TECH_<N>nm/`.

```
sram/
├── array/                      # THIS flow: wd / column / array compilers + sims
│   ├── run_wd.sh               #   write-driver TB sim (HSPICE; --pex = SPEF via ba_file)
│   ├── run_col.sh              #   column TB sim (6-op write/read + energy measures)
│   ├── run_array.sh            #   array TB sim (word-wide ops + toggle-rate knob)
│   ├── lib/tb_wd_template.sp   #   TB template (@CELLNAME@ @VDD@ @TEMP@ @BL_CAP@ @NODE@)
│   ├── scripts/gen_wd.py       #   strength-ladder generator (vertical tiling; gdstk)
│   ├── scripts/gen_col.py      #   node-aware column compiler (primitives + wd ladder)
│   ├── scripts/gen_array.py    #   array compiler (columns tiled horizontally at bitcell pitch)
│   ├── scripts/gen_col_tb.py   #   column TB generator (row-count aware; called by run_col.sh)
│   ├── scripts/gen_array_tb.py #   array TB generator (toggle-rate aware; called by run_array.sh)
│   ├── scripts/col_measures.py #   .mt0 parser → measures.csv + pass/fail (columns)
│   ├── scripts/array_measures.py #  .mt0 parser + per-column checks (arrays)
│   └── scripts/collect_array.py  #  run dirs → datasets/sram_array.csv (log sheet)
├── spice/                      # shared extraction + device/model tools
│   ├── gds2spice.sh            #   GDS → .sp + .spef   (ICV → icv_nettran → StarXtract;
│   │                           #   used by array AND decoder flows)
│   └── scripts/                #   tech_paths.py (catalog resolver), tie_bulk.py,
│                               #   char_nodes.py / build_5nm.py (model cards)
├── decoder/                    # row-decoder PnR flow — see decoder/README.md
├── autosweep/                  # job-list batch runner — see autosweep/README.md
│   ├── jobs.csv                #   one row per dataset point (node,rows,cols,wd,
│   │                           #   toggle_rate,vdd_V,temp_C,pex; blanks = defaults)
│   ├── gen_jobs.py             #   grid generator (cartesian product of axes)
│   └── run_batch.sh            #   builds missing collateral per job, runs, collects
├── datasets/                   # sram_array.csv + sram_decoder.csv (kept by clean_all)
├── clean_all.sh                # rm -rf TECH_*nm + autosweep logs (all regenerable)
└── TECH_<N>nm/                 # generated work, one dir per configuration:
    ├── wd_X<S>/                #   ladder    01_gds/ → 02_pex/ → 03_sim/<run>/
    ├── column_X<S>_<R>/        #   column    01_gds/ → 02_pex/ → 03_sim/<run>/
    ├── array_X<S>_<R>x<C>/     #   array     01_gds/ (+ .json area sidecar)
    │                           #             → 02_pex/ → 03_sim/<run>/
    └── dec_<R>x<C>/            #   decoder   01_syn/ → 02_pnr/ → 03_gds/
                                #             → 04_pex/ → 05_sim/<run>/

tech_libs/techlib_<N>nm/        # shared library (catalog.json entry per node)
├── i3d_*.nxtgrd  i3d_*.mw.tf   #   StarRC grd + layout tf (grdfile/techfile;
│                               #   20nm also carries the custom hx2mw.tf)
├── gds/                        #   std-cell layouts        (catalog "gdsdir")
└── sram/                       #   SRAM library home       (catalog "sramdir")
    ├── node.env                #     VDD/TEMP/BL_CAP + collateral filenames
    ├── gds/                    #     hand-delivered primitives: sram_cell, pc,
    │                           #     sense_amp, buffer, unit wd_X<u>
    ├── models/                 #     nmos1.inc, pmos1.inc (HSPICE model cards)
    └── lvs.rs  strc_map_file.map  extract_template.strc
```

Each file has exactly one location, and there are no fallbacks. The tech
files named in `node.env` (`NXTGRD`, `LAYOUT_TF`) are looked up only in the
techlib root. The SRAM-specific ICV and StarRC setup files (`LVS_RS`,
`STARRC_MAP`, `STRC_TEMPLATE`) are looked up only in the `sram/` pack.

## Usage

```bash
# 1) GDS → SPICE + SPEF (shared tool in ../spice/; work dir auto-removed on
#    success, --keep to retain)
../spice/gds2spice.sh --node 20 wd_X4  # bare name → config store, then the
                                       # SRAM library (techlib_20nm/sram/gds/)
../spice/gds2spice.sh --node 16 /path/to/any.gds [cellname]   # explicit path works too

# 2) Strength ladder: stack the node's unit WD vertically (needs gdstk —
#    conda activate npuwattch). Targets are multiples of the unit strength.
python3 scripts/gen_wd.py --node 20 --list      # show unit cell + tiling pitch
python3 scripts/gen_wd.py --node 10 X4 X8       # → TECH_10nm/wd_X{4,8}/01_gds/

# 3) Array column: pc + N bitcell rows + sense amp + wd ladder + buffer
python3 scripts/gen_col.py --node 20 --rows 32 --wd 16   # → TECH_20nm/column_X16_32/01_gds/
python3 scripts/gen_col.py --node 5 --rows 4             # --wd defaults to the node's unit
python3 scripts/gen_col.py --node 16 --check             # re-derive frozen geometry vs library GDS
../spice/gds2spice.sh --node 20 column_X16_32            # → TECH_20nm/column_X16_32/02_pex/

# 3b) Array: tile a generated column horizontally (see "Arrays" below)
python3 scripts/gen_array.py --node 20 --rows 128 --wd 16 --cols 32
../spice/gds2spice.sh --node 20 array_X16_128x32         # → TECH_20nm/array_X16_128x32/02_pex/

# 4) Write-driver behavior sim
./run_wd.sh --node 20 wd_X4            # pre-layout (HSPICE)
./run_wd.sh --node 20 wd_X4 --pex      # post-layout (HSPICE + SPEF ba_file)

# 5) Column write/read/energy sim (see "Column testbench" below)
./run_col.sh --node 20 column_X4_2 --pex     # 6-op sequence + per-op energy
./run_col.sh --node 5  column_X64_512 --pex  # any extracted column_X<S>_<R>

# 5b) Array write/read/energy sim (see "Array testbench" below)
./run_array.sh --node 20 array_X4_16x4 --pex               # toggle rate 1.0
./run_array.sh --node 20 array_X4_16x4 --pex --toggle 0.25 # 25% of cols flip
./run_array.sh --node 20 array_X4_16x4 --pex --vdd 0.85 --temp 85  # PVT point
python3 scripts/collect_array.py    # rebuild sram/datasets/sram_array.csv

# 5c) Batches: whole dataset sweeps from a job list (see ../autosweep/README.md)
(cd ../autosweep && ./run_batch.sh jobs.csv)

# 6) Housekeeping — wipe ALL generated work (TECH_*nm + autosweep logs);
#    library collateral in tech_libs/ and datasets/ sheets are never touched
../clean_all.sh
```

`--node` accepts `20 | 16 | 10 | 7 | 5`. The `nm` suffix and zero-padding are
optional. A run stops with a clear error message if a required tech file is
empty (0 bytes).
<!-- Original wording: "Runs abort with a clear message if a required tech file is still a 0-byte stub." -->

## Per-node tech packs

All five node packs are complete. They live at `tech_libs/techlib_<N>nm/sram/`
(the `sramdir` entry in catalog.json). The nxtgrd and tf files come from the
shared techlib root. The table below still lists the files under their older
`tech/` paths. It shows where each file came from and what changes each node
needed.
<!-- History: packs populated 2026-07-12 ("nothing is stubbed anymore").
     Relocated 2026-07-13 to tech_libs/techlib_<N>nm/sram/ (catalog.json
     sramdir); the duplicated nxtgrd/tf copies were dropped in favor of the
     shared techlib files. The tech/ paths below are the packs' historical
     location. -->

| File | Source | Node-specific notes |
|---|---|---|
| `tech/lvs.rs` | 20nm SRAM flow (works at every node; the 16nm copy was byte-identical) | Same file at every node. |
| `tech/i3d_*.nxtgrd` | `dataset_gen/tech_libs/techlib_<N>nm/` (shared by logic and SRAM) <!-- moved up from logic/ 2026-07-13 --> | 5nm: the pack's `i3d_finfet5nm.nxtgrd` was generated from `~/5_to_20nm/5nm/i3d_finfet5nm.itf` (2025-03-13, M-style) with `grdgenxo`. <!-- 5nm: every pre-existing copy on this machine is gzip-truncated, so the grd was regenerated from the ITF. --> |
| `tech/strc_map_file.map` | 20nm ICV-to-grd map, adapted per node | The right-column layer names follow each node's grd. 16/7 use `metal0..12` (as is); 10/5 use `M0..M12`; 5 also uses `PO` and `VIA0..VIA11`. The non-20nm grds have no `FIN` or `via12` layer, so `nsd/psd` map to `NDIFF/PDIFF` and the `via12` line is removed (checked: no warnings). |
| `tech/extract_template.strc` | 20nm template with the nxtgrd name replaced | Must use the nxtgrd and map file names from `node.env`. |
| `tech/i3d_*.mw.tf` | `dataset_gen/tech_libs` | Not used by the automated 3-step flow. Kept for interactive Custom Compiler work. |
| `models/nmos1.inc`, `models/pmos1.inc` | `~/2026_0617/SPICE_MODEL/<N>nm/FE/Spice_Model/`. The packs keep only the in-use `nmos1.inc`/`pmos1.inc`; the original files stay at the source paths. <!-- raw/backup card copies were removed from the packs 2026-07-13 on user request --> | 16/10/7: PTM-MG level-72 cards with `.model nfet/pfet` renamed to `nmos1/pmos1`. 5nm: BSIM-CMG cards rescaled from the PTM-MG 7nm cards (see the 5nm model notes below). The 5nm `node.env` uses TEMP=25, the same as the other nodes. <!-- Original 5nm entry: "5nm: BSIM-CMG — cards already named nmos1/pmos1, loaded with the Verilog-A under models/va/ via MODEL_HDL=va/bsimcmg.va in node.env (run_wd.sh emits the .hdl line). 5nm card is characterized at 0V7/27C (node.env keeps TEMP=25 for cross-node consistency — change if 27 was intended). Superseded 2026-07-13: 5nm cards recalibrated (PTM-MG-7nm rescale; student cards kept as *.inc.student)." --> |

`VDD` per node is 0.90 V (20nm), 0.85 V (16nm), 0.80 V (10nm), 0.75 V (7nm),
and 0.70 V (5nm). If you change any file names later, update
`tech_libs/techlib_<N>nm/sram/node.env` to match.

**Shared tech_libs**: logic and SRAM share one per-node collateral tree at
`dataset_gen/tech_libs` (see its README). Std-cell GDS lives there too
(`techlib_<N>nm/gds/`). It was imported from `~/5_to_20nm/<N>nm/gds` for
20/16/10/7 and from `~/5_to_20nm/5nm/i3d_5nm_finfet_gds` for 5nm. The decoder
flow (PnR and post-layout SPICE) uses this library. Use the Synopsys tech
files in tech_libs, not the ones in `~/5_to_20nm`. Note that the 5nm GDS cells
use a different naming style (`AND2X1` instead of `AND2_X1`).
<!-- History: consolidated 2026-07-13, when dataset_gen/logic/tech_libs moved
     to dataset_gen/tech_libs. The Synopsys tech files in ~/5_to_20nm are
     outdated; the tech_libs copies are authoritative. -->

## Validation

20nm is the reference node, and all sims were tested there first.
<!-- Validation date: 2026-07-12. -->

- `gds2spice.sh --node 20` gives a netlist that is byte-identical to the
  known-good `array_spice/20_wd_spice/out/wd_X4.sp`. The work dir is removed
  automatically.
- ICV reports `NOT CLEAN` because of one `text_net:text_open_merge` on VDD.
  The verified 20nm cell and the 16nm scaled cell show the same message. It
  comes from the cell itself (the rails join at the column level), so it is
  expected and has nothing to do with scaling or with this flow.
- `run_wd.sh --node 20 wd_X4`: BL falls in 239 ps and rises in 302 ps into
  20 fF, and q(VDD) = −31.0 fC over the write window.
- `run_wd.sh --node 20 wd_X4 --pex`: 46 nets, 192 R, and 118 coupled C are
  back-annotated. q_write is −34.6 fC and t_bl_rise is 330 ps, so the effect
  of the parasitics is clear.
  <!-- Reproduced after the @HDL_LINE@/@XDUT_PORTS@ template changes. -->

Unit cells use canonical names: the GDS file name matches the top cell name.
The rename did not change any geometry.
<!-- Naming applied 2026-07-12. -->

| Node | GDS in `array_compiler/compiler_XX/gen_wd/` | Top cell | Old name |
|---|---|---|---|
| 20nm | `out/wd_X4.gds` | `wd_X4` | (unchanged) |
| 16nm | `wd_X4.gds` | `wd_X4` | file `wd_x4.gds`, cell `wd_X4_v2` |
| 10nm | `wd_X2.gds` | `wd_X2` | cell `WriteDriver_10nm_12fin` |
| 7nm  | `wd_X4.gds` | `wd_X4` | cell `WRITE_DRIVER_X2` |
| 5nm  | `wd_X2.gds` | `wd_X2` | cell `wd_x2` |

Smoke extractions with the node packs (full gds2spice, no warnings, run again
after the renames). All netlists match the 20nm 8T topology:
- 16nm `wd_X4`: .sp and .spef produced. <!-- This was the first-ever 16nm .spef. -->
- 10nm `wd_X2` and 7nm `wd_X4`: .sp and .spef produced.
- 5nm `wd_X2`: .sp and .spef produced with the grd generated from the 2025
  ITF (grdgenxo, ~45 min; the output is named `finfet5nm.nxtgrd` after the
  ITF's TECHNOLOGY line). This grd is installed as
  `tech_libs/techlib_05nm/i3d_5nm.nxtgrd`, so logic and SRAM both use it from
  the techlib root. Do not re-import it from `~/tech_libs`.
  <!-- The pre-existing "corrupt" copies were exactly 35 bytes shorter than
       the regenerated file: a truncated copy had propagated everywhere.
       Fixed 2026-07-13: the regenerated file replaced
       tech_libs/techlib_05nm/i3d_5nm.nxtgrd. The ~/tech_libs copy is still
       truncated, so do not re-import from there. -->
- Every cell in the family (20/16/5 checked) reports the same single
  `text_net:text_open_merge` on a power text. This comes from the cell design
  (the rails join at the column level) and is expected at every node.

## Strength ladders

<!-- Built and validated 2026-07-12. -->

`scripts/gen_wd.py --node N X8 X16 ...` stacks the node's unit WD vertically
and follows the verified 20nm ladder pattern exactly. The top cell holds N
plain references to the unit at a fixed pitch, plus a copy of the unit's pin
labels at each position. ICV uses these labels to merge the signal nets of
the stacked units, which is why each unit reports a `text_open_merge`
message. This is expected. The pitch is measured from the unit GDS as
ymin(top M0 rail) − ymin(bottom M0 rail), so adjacent VDD rails overlap when
the cells abut.

Regression check: the generated 20nm `wd_X8`/`wd_X16` are identical after
flattening (geometry and labels) to the hand-made references in
`compiler_20/gen_wd/out/`.

Pin names follow the 20nm cell (`BL BL_bar data write VDD VSS`). The 10nm
`BLB` label was renamed to `BL_bar` in both GDS copies (geometry unchanged,
unit re-extracted).

| Node | pitch (µm) | ladder in `gds/` | t_bl_fall X-unit→×2→×4 (ps) | q_write (fC) |
|---|---|---|---|---|
| 20nm | 2.560 | X4 X8 X16 | 241 → 124 → 65 | 34.6 → 40.5 → 51.5 |
| 16nm | 2.560 | X4 X8 X16 | 168 → 87 → 46  | 31.9 → 37.2 → 47.0 |
| 10nm | 1.167 | X2 X4 X8  | 105 → 54 → 29  | 28.1 → 31.5 → 37.7 |
| 7nm  | 1.728 | X4 X8 X16 | 95 → 49 → 27   | 26.5 → 30.5 → 37.6 |
| 5nm  | 0.452 | X2 X4 X8  | 51 → 26 → 13   | 27.9 → 30.5 → 36.6 |

All 15 post-layout (--pex) sims confirm correct function. While write=1,
**BL = buffer(data)** and **BL_bar = invert(data)**, with driven highs at
VDD−V_tn. The WD drives the bitlines through NMOS write pass transistors; in
a column, the precharge pulls the bitlines all the way to VDD. Doubling the
stack roughly halves the BL transition times at every node. q_write grows
less than linearly because the 20 fF bitline load dominates.

**5nm model note**: the 5nm cards use the native
`.model nmos1|pmos1 nmos|pmos level = 72` + `version = 105.03` form. This is
the same native BSIM-CMG 105.03 implementation that the 16/10/7nm PTM-MG cards
use, and it binds directly to the extracted 4-terminal M elements. `MODEL_HDL`
in the 05nm `node.env` is empty, so no `.hdl` line is written. The original
Verilog-A form cards are in `~/5_to_20nm/5nm/i3d_5nm_finfet_modelcards/`.
<!-- Original note: HSPICE cannot bind the extracted 4-terminal M elements to
     the 5-terminal bsimcmg Verilog-A module, so the 5nm cards were converted
     to the native level-72 form. The VA-form cards and the models/va/
     includes were removed in the 2026-07-13 cleanup. -->

**5nm model cards**: the 5nm cards are **PTM-MG 7nm HP cards rescaled by
geometry**, the same method PTM uses between its own nodes. The changes are:
- HFIN from 34 to 50 nm and TFIN from 7 to 5 nm (IRDS/N5-class fin).
- EOT from 6.2 to 5.8 Å·10, FPITCH from 22 to 18 nm, LINT from 2 to 1 Å·10.
- CGSO/CGDO from 11 to 10e-10, following the family trend.
- RHOC from 4e-13 to 2e-13 and HEPI from 8 to 10 nm (contact-resistivity
  scaling; without it the L=12 nm device is limited by series resistance).

PHIG and VSAT were then tuned so that:
- IOFF follows the measured family trend (N 7.1/4.9/4.2/3.2/**2.6** nA/µm,
  P 5.5/3.6/2.8/1.9/**1.6** across 20/16/10/7/5 nm),
- per-device ION stays monotone (N 171 µA > 164 at 7nm, P 123 > 121;
  P/N = 0.72),
- SS is 65.1 mV/dec (family 63.0–64.5).

Final knobs: N PHIG=4.4399 VSAT=6.61e4, P PHIG=4.7324 VSAT=9.54e4.
Everything else (temperature, junction, and gate-leakage physics) comes from
the 7nm card. The earlier 5nm cards are kept at
`~/2026_0617/SPICE_MODEL/5nm/Spice_Model/i3d_5nm_0V7_27C.*`.

Two scripts support the model cards. `scripts/char_nodes.py` prints a
5-node single-device IOFF/ION/SS/VT table; run it after **any** card change.
`scripts/build_5nm.py` rebuilds and retunes the 5nm cards from the 7nm
sources into `<cwd>/draft/`. Like the other nodes, 5nm uses predictive
models, and its cards are consistent with the rest of the PTM-MG family.
<!-- 5nm model recalibration (2026-07-13), original background: the delivered
     5nm cards descended from the BSIM-CMG *sample benchmark* modelcard ("not
     based on any real technology" per its own header) with ad-hoc edits: VSAT
     cut 4x below the 7nm card and the drive current restored via stacked
     duplicate IDS0MULT = 5.433 lines, a raw current multiplier that inflated
     OFF-current by the same 5.433x (single-device IOFF 70 nA/um vs 3.2 at
     7nm; 2x2 array leak 457 nW vs 7-8 nW at every other node), plus
     duplicated U0 lines, N/P-inconsistent fin pitch (33 vs 48 nm), and PMOS
     drive stronger than NMOS. The student cards were removed from the pack
     in the 2026-07-13 cleanup (originals remain at
     ~/2026_0617/SPICE_MODEL/5nm/Spice_Model/i3d_5nm_0V7_27C.*). 5nm absolute
     accuracy is still predictive-model-grade, but it is now consistent with
     the PTM-MG family instead of 60x off in leakage. -->

Topology check (input to the choice between scaling and tiling): the
extracted netlists of the 16nm scaled cell and the 10/7/5nm native cells all
match the 20nm 8T write-driver topology exactly (5N/3P, same connectivity up
to drain/source symmetry). Only the drawn dimensions differ:
l = 24/22/20/18/12 nm and per-device w = 0.61/0.61/0.27/0.41/0.09–0.11 µm at
20/16/10/7/5 nm. Port order and names differ per node (10nm: `data write BL BLB
VSS VDD`), but run_wd.sh reads the port order from the extracted .SUBCKT, so
this is handled automatically.

## Column primitives

<!-- Standardized 2026-07-12. -->

The four column primitives use the 20nm `gen_col` naming: the file name
matches the top cell name, and the pins use the 20nm names (geometry
unchanged).

| Canonical | pins | Old name (16nm / 10nm / 7nm / 5nm) |
|---|---|---|
| `sram_cell` | BL BL_bar WL Q Q_bar VDD VSS | SRAM_CELL / Sramcell_10nm_fin_new333 / SRAM_CELL / SRAM_cell |
| `pc` | BL BL_bar pre_en VDD | PRECHARGE / Precharging_10nm / PRECHARGE / pre_5nm |
| `sense_amp` | BL BL_bar sen_en sen_en_bar VDD VSS | SENSE_AMP2 / SenseAmplifer_10nm / SENSE_AMP2 / SA_5nm |
| `buffer` | BL OUT VDD VSS | buffer / Buffer_10nm / buffer_7nm / buf |

Label renames: `BLB`, `BL_BAR`, and `!BL` became `BL_bar`; `sense_en(_bar)`
became `sen_en(_bar)`; `IN` became `BL`; and `out` became `OUT`. The 20nm
originals were copied into the 20nm SRAM library store unchanged. All 19
possible extractions were smoke-run and compared against the 20nm netlists.

**All 20 primitives (4 cells × 5 nodes) extract cleanly and match the 20nm
topology** (6T cell, 2T pc, 6T latch SA, 4T buffer).
<!-- "as of the final re-deliveries on 2026-07-12 evening". Issues found and
     fixed by re-delivery along the way: 16nm (crashing sram_cell,
     floating-gate pc/buffer devices, mislabeled/open sense_amp, buffer.gds
     that was a precharge copy), 7nm (sense_amp open: NMOS terminal on an
     internal net instead of BL_bar), 5nm (buffer with an extra weak PMOS
     between OUT and VSS). -->

## Columns (gen_col.py)

<!-- Built and validated 2026-07-12. -->

`scripts/gen_col.py --node N --rows R --wd S` builds one array column from
the standardized primitives and a gen_wd strength ladder, and writes
`TECH_<N>nm/column_X<S>_<R>/01_gds/column_X<S>_<R>.gds`:

```
pc                      0.01 um above the top row (BL/BL_bar reach it via M3;
sram_cell x R           its VDD merges by label)   mirror-tiled rows sharing
sense_amp               alternating VDD/VSS rails  oriented VDD-rail-down
wd_X<S>                 ladder top VDD rail shared with the SA
buffer                  oriented VDD-rail-up, under the ladder
```

Cells are stacked vertically by **rail abutment**: adjacent cells overlap
their full-width M0 edge rails, net on net. This scheme was taken from the
verified 20nm reference and checked against it. Bitlines are M3 straps over
the existing VIA2 stubs of every cell. Wordlines are full-width M0 straps over
each row's WL shape, with `wl[i]` pins. Sub-cell port labels are copied again
onto the top cell, except for Q/Q_bar: text with the same name would short
the storage nodes of all rows together.

The measured geometry for each node is fixed in `NODE_SPECS` inside the
script (bboxes, rail bands with nets, BL track x, WL band, flips, unit
strength). `--check` re-derives every number from the GDS store and reports
any drift. Run it after any primitive re-delivery. All store cells follow the
20nm drawing convention. The column pitch equals the bitcell width at every
node (20nm: 0.66 um, confirmed by the layout owner).
<!-- Convention fixed in-GDS 2026-07-12, per the layout owner: the 7nm sense
     amp and 5nm buffer were delivered VDD-rail-on-bottom and have been
     flipped vertically, and the 16nm write driver (scaled from 20nm) sat
     1 nm off the shared BL grid and was shifted x -0.001 (ladders
     regenerated, copy in array_compiler/compiler_16/gen_wd/ synced). All
     three fixes are pure mirror/translate transforms; the regenerated
     columns are flatten-identical to the extraction-verified ones. -->

Validation:
<!-- Validation date: 2026-07-12. -->
- 20nm `column_X4_2` regenerates **identical after flattening** to the
  reference (`array_compiler/compiler_20/gen_col/out/`): 722 polygons,
  57 labels.
- 20nm `column_X16_32`: all 4691 polygons are identical, and the labels match
  in text, layer, and position. The only differences are display-only
  magnification inside the ladder and the planned renames from
  `sense_en(_bar)` to `sen_en(_bar)` and from `out` to `OUT` (canonical
  primitive pin names).
- `--check` is clean at all 5 nodes (17 checks each).
- 4-row columns at unit strength were generated at all 5 nodes and extracted
  (`gds2spice.sh`, .sp + .spef). Every node gives 44 devices and the same
  ports, and the **topology matches 20nm**. The only ICV messages are two
  `text_open_merge` on VDD/VSS. These are the expected label merges (the
  rails join only through the array power grid), the same as in the
  reference flow.

## Column testbench (run_col.sh + gen_col_tb.py)

<!-- Built 2026-07-12. -->

`run_col.sh --node N column_X<S>_<R> [--pex]` simulates an extracted column.
`scripts/gen_col_tb.py` generates the testbench for each row count. It is
based on the verified 20nm 50 ns TB (`array_spice/20_col_spice`) and keeps
its **slow 10 ns/op cadence**. The wide windows let BL swings and sensing
settle fully at every column size, so we chose this over a faster clock. The
sequence has 6 ops instead of the original 4, so one run gives the write
energy both with and without a bit flip:

```
 0- 3 ns  idle                     13-23  RD0   read 0 (expect OUT=0)
 3-13 ns  WR0   write 0 (init)     33-43  RD1   read 1 (expect OUT=VDD)
23-33 ns  WR1f  write 1 = BIT FLIP 53-63  RD1b  read 1 after same-write
43-53 ns  WR1s  write 1 = SAME     90-99       leakage window (settled tail)
```

Write op at T: pre_en releases at T, write at T+1, wl at T+2..T+5, and the
precharge restores at T+7. Each op's energy window is the full [T, T+10], so
the bitline recharge is charged to the op that discharged it. Read op at T:
wl at T+1..T+6, sense at T+4..T+7, and OUT is sampled at T+5.5. `data` flips
inside the flip-write window, so the switching of the WD input inverter
counts as flip energy.

Energy test points: the column's single VDD port feeds every sink (WD, SA,
buffer, precharge source, cell pull-ups). Per-op energy is
`INTEG -v(VDD)*i(VVDD)` over the op window, and leakage is the `AVG` of the
same quantity at 90–99 ns. The long idle time before the leakage window is
needed. At 512 rows, the supply current keeps decaying for ~25 ns after the
last precharge restore while the internal nodes settle (BL itself is back at
VDD within ~2 ns). A window at 65 ns would read 20nm 512-row leakage 3.5× too
high (1692 vs 484 nW settled).

Functional checks sample OUT during each sense window, plus the BL / BL_bar
hold levels during the write pulses. `col_measures.py` converts the .mt0 to
`measures.csv` and stops with an error on any incorrect read-back or missing
measure. Only `wl[0]` is driven. `wl[1..R-1]` are tied to ground directly in
the DUT port list, so there are no per-row sources even at 512 rows. The
unused rows still load the bitlines, which is exactly the row-count effect
the sweep measures.

Results (post-layout, nominal VDD, 25C):
<!-- Results date: 2026-07-12. -->
- 2-row columns pass at 20/16/10/7nm with the node's unit WD.
- **5nm: the smallest usable write driver is X4**, and the sweeps map 5nm
  sizes this way.
  <!-- 5nm: the X2 unit WD is below write margin even against a single cell.
       Writing 0 leaves BL at 0.19 V (contention with the cell pull-up; the
       failed write burns 0.45 pJ vs 3 fJ normal) and the cell keeps its old
       value. -->
- Row-scaling sweep (rows 64/128/256/512 with WD X8/X16/X32/X64): all 20
  configs pass post-layout at all 5 nodes. The per-run `measures.csv` files
  are under `TECH_<N>nm/column_*/03_sim/`. Read/write energy and leakage
  scale about linearly with rows, and flip-write is higher than same-write
  everywhere. BL fall stays under 0.9 ns even at 512 rows. The WD mapping
  keeps drive and load roughly balanced, so the small rise at 512 rows comes
  from bitline-strap RC.
- 20nm 512-row: flip-write 0.171 pJ, read 0.10-0.12 pJ, leakage 0.48 uW.
  These values drop steadily down to 7nm (0.071 pJ / 0.06 pJ / 0.32 uW).
  <!-- 5nm is leakage-dominated (HP-only model card): 25.5 uW at 512 rows, so
       its op "energies" are mostly leakage integrated over the 10 ns window.
       The dataset collector must report/subtract the leak baseline
       (E_dyn ~ E_op - P_leak*10 ns) or 5nm dynamic energy will be
       meaningless. (These 5nm numbers appear to predate the 2026-07-13 5nm
       card recalibration.) -->
- 7nm 2-row leakage reads about −0.3 nW. Values below 1 nW are under the
  integration noise floor, so treat |leak| < 1 nW as zero and ignore the
  sign.

## Arrays (gen_array.py)

<!-- Built and validated 2026-07-12. -->

`scripts/gen_array.py --node N --rows R --wd S --cols C` tiles the generated
`column_X<S>_<R>.gds` horizontally C times at the node's column pitch (the
bitcell width; 20nm 0.66 um, confirmed by the layout owner) and writes
`array_X<S>_<R>x<C>.gds`. Every cell in the column stack is exactly one pitch
wide, so the columns abut edge to edge with no gap or overlap.

- Net model: the **shared** nets are wl[0..R−1], pre_en, sen_en, sen_en_bar,
  write, VDD, and VSS. Each column carries labels with the same names, and
  ICV merges them by text. The WL M0 straps of adjacent columns also touch
  and merge into one polygon, so the wl nets need no text merge at all. The
  **per-column** nets data, OUT, BL, and BL_bar are renamed `data[c]`,
  `OUT[c]`, `BL[c]`, and `BL_bar[c]`. Only top-cell labels reach flat
  extraction, so the column's top labels are copied again at absolute
  positions on the array top cell.
- Validation: 2×2 smoke arrays at all 5 nodes extract with exactly the
  expected port set and device count (2 × column devices). ICV is clean
  except for the usual `text_open_merge` on the shared nets. A net-count
  check (array nets = 2·(column nets − 8 shared) + 8) passes at every node,
  so the abutment creates no shorts between columns.
  <!-- Validated 2026-07-12. -->
- Large case: 20nm `array_X16_128x32` (the largest planned grid point in the
  dataset, 25 984 devices, 21.12 × 114.68 um = 2422 um²) generates and
  extracts in under a minute, so extraction time does not limit the phase-4
  sweep.
- The script prints the footprint (w, h, area in um²) from the top bbox when
  it generates the array. This is the source of `total_area_um2` in the
  dataset.

## Array testbench (run_array.sh + gen_array_tb.py)

<!-- Built 2026-07-13. -->

`run_array.sh --node N array_X<S>_<R>x<C> [--pex] [--toggle <0..1>]`
simulates an extracted array with a word-wide testbench generated by
`scripts/gen_array_tb.py`, which reads the rows and columns from the netlist
port list. Arrays normally use the default write-driver strength from
`gen_array.py`. This is the smallest strength with a clean write margin for
the row count, based on the phase-2 column sweeps: ceil(rows/8), rounded up
to the node unit, with X4 as the minimum at 5nm. So 64 rows use X8, 128 use
X16, 256 use X32, and 512 use X64. `--wd` can override it.
<!-- Original: "floor X4 at 5nm where X2 is below write margin". -->

**Stimulus summary** (10 ns/op cadence with the same intra-op edges as the
column TB). All C columns work together as one word. Only wl[0] is driven,
and wl[1..R−1] are grounded, so the idle rows still load the bitlines:

```
 0- 3 ns  idle   precharge ON, all BL/BL_bar at VDD
 3-13 ns  WR1i   write 1, all cols (init — prior state unknown; aux)
13-23 ns  RD11   read all-1 word  → rd_1to1_energy  (BL side stays at VDD)
23-33 ns  WRs    rewrite 1, all cols, ZERO flips → wr_same_energy
33-43 ns  WRt    n_t = round(toggle·C) cols flip 1→0, rest rewrite 1
                 → wr_toggle_energy at the requested toggle rate
43-53 ns  WR0f   write 0, all cols (flips the remaining C−n_t; aux)
53-63 ns  RD10   read all-0 word  → rd_1to0_energy  (BL discharges to 0)
90-99 ns         leakage window (settled tail)
```

Write op at T: pre_en releases at T, write at T+1, wl at T+2..T+5, and the
precharge restores at T+7. Each op's energy window is the full [T, T+10], so
the bitline recharge is charged to the op that discharged it. Read op at T:
wl at T+1..T+6, sense at T+4..T+7, and OUT is sampled at T+5.5. The toggling
columns are data[0..n_t−1]. Their data input falls at T+0.5 inside the
toggle-write window, so the WD input-inverter switching counts as toggle
energy. In the columns that hold their value, data falls inside the
fill-write window instead.

**Measurement locations**:

| measure | where / how |
|---|---|
| per-op energy (6×) | `INTEG −v(VDD)·i(VVDD)` over the op's [T, T+10] ns. The array's single VDD port feeds every sink (all columns' WDs, SAs, buffers, precharge PMOS, cell pull-ups). |
| `p_leak_W` | `AVG −v(VDD)·i(VVDD)` at 90–99 ns (all controls idle, settled) |
| `out_rd1_c<c>` | `v(OUT[c])` at 18.5 ns, every column; expect > 0.85·VDD |
| `out_rd0_c<c>` | `v(OUT[c])` at 58.5 ns, every column; expect < 0.15·VDD |
| `blb_wrs_c0` | `v(BL_bar[0])` at 27.9 ns; the WD holds BL_bar low in the same-write |
| `bl_wrt_c0` | `v(BL[0])` at 37.9 ns; a toggling column pulls BL low |
| `blb_wrt_c<C−1>` | `v(BL_bar[C−1])` at 37.9 ns; a holding column keeps writing 1 |
| `t_rd_wl_out` | RD10 op: from the `wl[0]` 50% rise to the `OUT[C−1]` 50% fall. This is the **read access time**. |
| `t_rd_bl_dev` | RD10 op: from the `wl[0]` 50% rise until `v(BL_bar[C−1])−v(BL[C−1])` reaches 0.1·VDD |
| `t_rd_sense` | RD10 op: from the `sen_en` 50% rise to the `OUT[C−1]` 50% fall (can be negative) |
| `t_wr_bl` | flip op: from the `write` 50% rise until `v(BL[C−1])` falls to 0.1·VDD |
| `t_wr_cell` | flip op: from the `wl[0]` 50% rise to the 50% fall of the cell's internal Q (the write event) |
| `t_wr_total` | `t_wr_bl + t_wr_cell`. This is the **write time** (conservative, since the phases are treated as sequential). |

**Read/write delay method.** All delays are measured at the far column C−1.
It is the last column to see the wordline through the post-layout WL RC, so
it is the worst case.

*Read* delay is measured in the RD(1→0) op. The cell stores 0, so the
buffered output moves away from its precharged 1, and `t_rd_wl_out` (wl to
OUT) is the access time. Two parts are recorded with it. `t_rd_bl_dev` is the
bitline development time (bitline cap × cell read current). It does not
depend on the sense schedule, and it is the part that scales with rows. The
other part is `t_rd_sense`. The TB fires `sen_en` at a fixed wl+3 ns. In
small arrays, the cell alone can pull the bitline past the output-buffer
threshold before that. In that case `t_rd_sense` is **negative**: the sense
amp only helped, and `t_rd_wl_out` does not depend on the sense schedule. If
`t_rd_sense` is positive, the fixed 3 ns sense schedule limits `t_rd_wl_out`,
and `t_rd_bl_dev` is the better measure of array speed.

*Write* delay is measured on a real 1-to-0 flip of the cell at (row 0,
col C−1). This happens in WRt when the whole word toggles (n_t = C), and
otherwise in WR0f (which flips columns n_t..C−1). `t_wr_bl` is the time the
write driver takes to drive the bitline, which is what WD sizing controls.
The TB fires the WD 1 ns before WL, so this part is easy to separate.
`t_wr_cell` runs from the wl rise to the point where the cell's internal Q
crosses 50%. This is the actual store event, after which WL could close. We
do not use the bitline re-settle after the cell's back-injection bump as the
criterion: with a strong WD the bump is only a few millivolts, and a
threshold on it is numerically fragile. Q's netlist name (`N32`-style,
different in every extraction) is found automatically by `gen_array_tb.py`.
It is the non-bitline channel terminal of the access transistor gated by
`wl[0]` on `BL[C−1]`, and it is probed hierarchically as `v(Xdut.<node>)`
(checked to work after SPEF back-annotation).

`array_measures.py` checks all of the above and stops with an error on any
incorrect read-back or missing measure (delays must be in (0, 10 ns);
`t_rd_sense` can be negative). Each run directory gets `meta.json` (config,
PVT, toggle rate, run id) and `area.json` (copied from the `gen_array.py`
sidecar `gds/<array>.json`). `collect_array.py` scans
`TECH_*nm/array_*/03_sim/*/` and rebuilds
**`dataset_gen/sram/datasets/sram_array.csv`**. The step is idempotent, and
the latest run for each config key wins. The sheet columns are:
- config/PVT keys, `toggle_rate`, `n_toggle_cols`;
- the four dataset targets `wr_same_energy_pJ`, `wr_toggle_energy_pJ`,
  `rd_1to1_energy_pJ`, `rd_1to0_energy_pJ`;
- the auxiliary energies `wr1_init_energy_pJ` / `wr0_fill_energy_pJ`;
- `leak_power_mW`;
- the delays `rd_delay_ns` / `rd_bl_dev_ns` / `rd_sense_ns` / `wr_delay_ns` /
  `wr_bl_ns` / `wr_cell_ns` (ns);
- the layout geometry `width_um` / `height_um` / `total_area_um2` (from the
  GDS bounding box via the `gen_array.py` sidecar);
- `flow_run_id`.

Energies are raw integrals over each op window, so each one includes the
leakage that flows during its 10 ns window. Leakage is recorded as-is at
every node, including 5nm. The flow does not subtract a baseline anywhere. If
you want pure dynamic energy, subtract `leak_power · 10 ns` downstream.
Sub-nW |leak| readings in tiny arrays are integration noise (7nm 2×2 reads
−5 nW), so keep that floor in mind when you use the data. The 5nm 2×2
leakage is 6.6 nW, in line with the other nodes.
<!-- Before the 2026-07-13 5nm card recalibration, the 5nm 2x2 leak was
     457 nW, about 4.6 fJ of every 10 ns op window. -->

Validation (post-layout, nominal VDD, 25C):
<!-- Validation date: 2026-07-13. -->
- 2×2 arrays pass at all 5 nodes (every per-column OUT sample is correct, and
  the BL hold checks pass). A 1-to-0 read costs about 2× a 1-to-1 read, and a
  toggle-write about 4–5× a same-write. Both agree with the column results.
- The toggle knob is linear. At 20nm 2×2, `wr_toggle` at rate 0.5 is
  0.01394 pJ, versus 0.01395 predicted from the rate-0 (equal to `wr_same`)
  and rate-1 endpoints. At 20nm 16×4, rate 0.25 gives 0.03268 vs 0.03276
  predicted. Ops other than WRt/WR0f are bit-identical across rates, as
  expected.
- A 16-row × 4-col grid point ran end to end, from `gen_col.py` to the sheet,
  in about 2 min (the default WD picked X4 for 16 rows).
- Delay measures (all 10 configs): read access time drops or stays flat
  across nodes at 2×2 (post-layout: 20nm 82.9 ps, 16nm 57.9, 10nm 32.1,
  7nm 28.8, 5nm 29.5 ps). The 5nm value uses the recalibrated card, and it
  sits slightly above 7nm because its lower VDD offsets the smaller layout.
  Parasitics matter: the 20nm 2×2 pre-layout read is 35.8 ps. A −0.05 V
  change slows 20nm by about 3–4 %. Going from 2×2 to 16×4 at 20nm roughly
  doubles both delays (rd from 82.9 to 142.1 ps, wr from 160.8 to 273.2 ps).
  The growth comes from the bitline cap: `wr_bl` goes from 124 to 247 ps,
  while the cell flip stays at ~27–37 ps. `t_rd_sense` is negative in every
  config so far. These small arrays discharge the bitline past the buffer
  threshold before the fixed wl+3 ns sense fires, so the recorded access
  times do not depend on the sense schedule.
  <!-- Delay measures added 2026-07-13; all 10 configs were re-run. The 5nm
       value was described as "a flag-level blip, not an error". -->

## Notes and decisions

- **20nm `hx2mw.tf` version**: the pack uses the `20_col_spice/tech` copy
  (2026-07-01). Nothing in the automated flow reads this file, so it only
  matters for interactive Custom Compiler work.
  <!-- The repo had two diverged copies; this pack uses the newer one
       (20_col_spice/tech, 2026-07-01, layer numbers shifted vs the 06-30
       20_wd_spice copy) on the "tech file for 20nm is final" instruction.
       Swap the file if the other version was meant. -->
- The TB template adds `.measure` lines (average and integrated VDD current
  during the write window, BL fall and rise delays) to the original verified
  20nm TB. The transient stimulus itself is the same.
- `lvs.rs` works the same way at every node. Extracted devices are always
  `nmos1`/`pmos1` with drawn `l`/`w`, so node differences come only from the
  drawn gate length, the model cards, and the nxtgrd parasitics.
- Older flat run directories (`array_spice/16`, `array_spice/20`, root logs)
  are left as they are.
  <!-- Archive or delete them separately once this flow is adopted. -->
