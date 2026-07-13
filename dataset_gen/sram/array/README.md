# SRAM array compiler + SPICE flows (node-aware)

One flow, five nodes. Runs in parallel with `../decoder/` (row-decoder PnR
flow); the shared extraction and device/model tools live in `../spice/`.
Supersedes the per-node copies in `array_spice/20_wd_spice` and
`array_spice/20_col_spice` (kept untouched as reference until this flow is
fully adopted).

All library collateral (tech files, model cards, primitive GDS) lives in the
shared `dataset_gen/tech_libs/` tree and is resolved through
`tech_libs/catalog.json` (`../spice/scripts/tech_paths.py`); nothing is
copied under `sram/`. Generated artifacts land node-first, one directory per
configuration, with numbered stage dirs in creation order — the same shape
as `dataset_gen/logic/TECH_<N>nm/`.

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

Each file has exactly one authoritative location (no fallbacks): the tech
files named by `node.env` (`NXTGRD`, `LAYOUT_TF`) resolve in the techlib
root ONLY; the SRAM-specific ICV/StarRC setup (`LVS_RS`, `STARRC_MAP`,
`STRC_TEMPLATE`) resolves in the `sram/` pack ONLY.

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

`--node` accepts `20 | 16 | 10 | 7 | 5` (a `nm` suffix and zero-padding are
optional). Runs abort with a clear message if a required tech file is still a
0-byte stub.

## Per-node tech packs (populated 2026-07-12)

All five packs are populated — nothing is stubbed anymore. **Relocated
2026-07-13**: the packs now live at `tech_libs/techlib_<N>nm/sram/`
(catalog.json `sramdir`); the duplicated nxtgrd/tf copies were dropped in
favor of the shared techlib files (the `tech/` paths below are the packs'
historical location). Sources and per-node adjustments:

| File | Source | Node-specific notes |
|---|---|---|
| `tech/lvs.rs` | 20nm SRAM flow (node-agnostic; 16nm copy was byte-identical) | same file at every node |
| `tech/i3d_*.nxtgrd` | `dataset_gen/tech_libs/techlib_<N>nm/` (moved up from `logic/` 2026-07-13; shared by logic+SRAM) | **5nm: every pre-existing copy on this machine is gzip-truncated** — the pack's `i3d_finfet5nm.nxtgrd` was regenerated from `~/5_to_20nm/5nm/i3d_finfet5nm.itf` (2025-03-13, M-style) with `grdgenxo` |
| `tech/strc_map_file.map` | 20nm ICV→grd map, adapted per node | right-column layer names per node's grd: 16/7 use `metal0..12` (verbatim); 10/5 use `M0..M12`; 5 additionally `PO`, `VIA0..VIA11`. All non-20nm grds lack `FIN` and `via12` → `nsd/psd` remapped to `NDIFF/PDIFF`, `via12` line dropped (verified warning-free) |
| `tech/extract_template.strc` | 20nm template, nxtgrd name substituted | must reference nxtgrd/map by the names in `node.env` |
| `tech/i3d_*.mw.tf` | `dataset_gen/tech_libs` | not consumed by the automated 3-step flow; kept for interactive Custom Compiler work |
| `models/nmos1.inc`, `models/pmos1.inc` | `~/2026_0617/SPICE_MODEL/<N>nm/FE/Spice_Model/` (raw/backup card copies removed from the packs 2026-07-13 on user request — only the in-use `nmos1.inc`/`pmos1.inc` remain; originals still live at the source paths) | 16/10/7: PTM-MG level-72 cards with `.model nfet/pfet` renamed `nmos1/pmos1`. **5nm: BSIM-CMG** — cards already named `nmos1/pmos1`, loaded with the Verilog-A under `models/va/` via `MODEL_HDL=va/bsimcmg.va` in node.env (run_wd.sh emits the `.hdl` line). 5nm card is characterized at 0V7/27C (node.env keeps TEMP=25 for cross-node consistency — change if 27 was intended). **Superseded 2026-07-13: 5nm cards recalibrated** (PTM-MG-7nm rescale; student cards kept as `*.inc.student`) — see the 5nm model notes below |

`VDD` per node: 20→0.90, 16→0.85, 10→0.80, 7→0.75, 5→0.70 V. If you swap in
different file names later, update `tech_libs/techlib_<N>nm/sram/node.env`
accordingly.

**Shared tech_libs (consolidated 2026-07-13)**: `dataset_gen/logic/tech_libs`
moved to `dataset_gen/tech_libs` so logic and SRAM share one per-node collateral
tree (see its README). Std-cell GDS now lives there too
(`techlib_<N>nm/gds/`, imported from `~/5_to_20nm/<N>nm/gds` for 20/16/10/7 and
`~/5_to_20nm/5nm/i3d_5nm_finfet_gds` for 5nm) — this is the library the upcoming
decoder work (PnR + post-layout SPICE) should consume. The Synopsys tech files in
`~/5_to_20nm` are outdated; the tech_libs copies are authoritative. Note the 5nm
GDS cell naming differs (`AND2X1` vs `AND2_X1` elsewhere).

## Validation (2026-07-12)

20nm (reference, per user instruction all sims tested here):
- `gds2spice.sh --node 20` → netlist byte-identical to the known-good
  `array_spice/20_wd_spice/out/wd_X4.sp`; work dir auto-removed.
- The `NOT CLEAN` ICV result is one `text_net:text_open_merge` on VDD — present
  in the verified 20nm cell itself (same violation the 16nm scaled cell shows),
  i.e. inherited from the cell, not introduced by scaling or by this flow.
- `run_wd.sh --node 20 wd_X4`: BL fall 239 ps / rise 302 ps into 20 fF,
  q(VDD) = −31.0 fC over the write window.
- `run_wd.sh --node 20 wd_X4 --pex`: 46 nets / 192 R / 118 coupled C
  back-annotated; q_write −34.6 fC, t_bl_rise 330 ps — parasitic effect
  visible. Reproduced after the @HDL_LINE@/@XDUT_PORTS@ template changes.

Canonical unit-cell naming (applied 2026-07-12; GDS file name = top cell
name, geometry untouched by the rename):

| Node | GDS in `array_compiler/compiler_XX/gen_wd/` | Top cell | was |
|---|---|---|---|
| 20nm | `out/wd_X4.gds` | `wd_X4` | (unchanged) |
| 16nm | `wd_X4.gds` | `wd_X4` | file `wd_x4.gds`, cell `wd_X4_v2` |
| 10nm | `wd_X2.gds` | `wd_X2` | cell `WriteDriver_10nm_12fin` |
| 7nm  | `wd_X4.gds` | `wd_X4` | cell `WRITE_DRIVER_X2` |
| 5nm  | `wd_X2.gds` | `wd_X2` | cell `wd_x2` |

Smoke extractions with the populated packs (full gds2spice, warning-free,
re-run after the renames; all netlists match the 20nm 8T topology):
- 16nm `wd_X4`: .sp + **first-ever 16nm .spef** produced.
- 10nm `wd_X2`, 7nm `wd_X4`: .sp + .spef produced.
- 5nm `wd_X2`: .sp + .spef produced with the grd regenerated from the 2025
  ITF (grdgenxo, ~45 min; output is named `finfet5nm.nxtgrd` after the ITF's
  TECHNOLOGY line). The pre-existing "corrupt" copies were exactly 35 bytes
  shorter than the regenerated file — a truncated copy propagated
  everywhere. **Fixed 2026-07-13**: the regenerated file replaced
  `tech_libs/techlib_05nm/i3d_5nm.nxtgrd`, so logic and SRAM both use the
  healthy grd from the techlib root (the `~/tech_libs` copy is still
  truncated — do not re-import from there).
- Every cell in the family (20/16/5 checked) reports the same single
  `text_net:text_open_merge` on a power text — a property of the cell design
  (rails join at column level), not a per-node defect.

## Strength ladders (built + validated 2026-07-12)

`scripts/gen_wd.py --node N X8 X16 ...` stacks the node's unit WD vertically,
reproducing the verified 20nm ladder pattern exactly: top cell = N plain
references to the unit at a fixed pitch + the unit's pin labels copied per
position (label texting is what merges the stacked units' signal nets in ICV —
the per-unit `text_open_merge` violations are that mechanism, not defects).
Pitch is measured from the unit GDS: ymin(top M0 rail) − ymin(bottom M0 rail),
so adjacent VDD rails overlap on abutment.

Regression: generated 20nm `wd_X8`/`wd_X16` are flatten-identical (geometry +
labels) to the human-made `compiler_20/gen_wd/out/` references.

Pin names were standardized on the 20nm cell (`BL BL_bar data write VDD VSS`);
the only deviation was the 10nm `BLB` label, renamed `BL_bar` in both GDS
copies (geometry untouched, unit re-extracted).

| Node | pitch (µm) | ladder in `gds/` | t_bl_fall X-unit→×2→×4 (ps) | q_write (fC) |
|---|---|---|---|---|
| 20nm | 2.560 | X4 X8 X16 | 241 → 124 → 65 | 34.6 → 40.5 → 51.5 |
| 16nm | 2.560 | X4 X8 X16 | 168 → 87 → 46  | 31.9 → 37.2 → 47.0 |
| 10nm | 1.167 | X2 X4 X8  | 105 → 54 → 29  | 28.1 → 31.5 → 37.7 |
| 7nm  | 1.728 | X4 X8 X16 | 95 → 49 → 27   | 26.5 → 30.5 → 37.6 |
| 5nm  | 0.452 | X2 X4 X8  | 51 → 26 → 13   | 27.9 → 30.5 → 36.6 |

All 15 post-layout (--pex) sims confirm the function: **BL = buffer(data),
BL_bar = invert(data)** while write=1, with driven highs at VDD−V_tn (the WD
drives the bitlines through NMOS write pass transistors; full-VDD high is the
precharge's job in a column). Doubling the stack ≈ halves the BL transition
times at every node; q_write grows sub-linearly because the 20 fF bitline
load dominates.

**5nm model note**: HSPICE cannot bind the extracted 4-terminal M elements to
the 5-terminal `bsimcmg` Verilog-A module, so the 5nm cards were converted to
the native `.model nmos1|pmos1 nmos|pmos level = 72` + `version = 105.03`
form — the same BSIM-CMG 105.03 native implementation the 16/10/7nm PTM-MG
cards use. `MODEL_HDL` in the 05nm `node.env` is now empty (no `.hdl`
line); the VA-form cards and the `models/va/` includes were removed in the
2026-07-13 cleanup (originals in `~/5_to_20nm/5nm/i3d_5nm_finfet_modelcards/`).

**5nm model recalibration (2026-07-13)**: the delivered 5nm cards descended
from the BSIM-CMG *sample benchmark* modelcard ("not based on any real
technology" per its own header) with ad-hoc edits: VSAT cut 4× below the 7nm
card and the drive current restored via stacked duplicate `IDS0MULT = 5.433`
lines — a raw current multiplier that inflated OFF-current by the same
5.433× (single-device IOFF 70 nA/µm vs 3.2 at 7nm; 2×2 array leak 457 nW vs
7–8 nW at every other node), plus duplicated `U0` lines, N/P-inconsistent
fin pitch (33 vs 48 nm), and PMOS drive *stronger* than NMOS. The cards were
rebuilt as **geometry-rescaled PTM-MG 7nm HP cards** (the same method PTM
uses between its own nodes): HFIN 34→50 nm, TFIN 7→5 nm (IRDS/N5-class fin),
EOT 6.2→5.8 Å·10, FPITCH 22→18 nm, LINT 2→1 Å·10, CGSO/CGDO 11→10e-10
following the family cadence, RHOC 4e-13→2e-13 + HEPI 8→10 nm (contact-
resistivity scaling — without it the L=12 nm device is series-R-limited),
then PHIG and VSAT tuned so IOFF continues the measured family trend
(N 7.1/4.9/4.2/3.2/**2.6** nA/µm, P 5.5/3.6/2.8/1.9/**1.6** across
20/16/10/7/5 nm) with per-device ION monotone (N 171 µA > 164 at 7nm,
P 123 > 121; P/N = 0.72) and SS 65.1 mV/dec (family 63.0–64.5). Final knobs:
N PHIG=4.4399 VSAT=6.61e4, P PHIG=4.7324 VSAT=9.54e4; everything else
(temperature, junction, gate-leakage physics) inherits the 7nm card.
The student cards were removed from the pack in the 2026-07-13 cleanup
(originals remain at `~/2026_0617/SPICE_MODEL/5nm/Spice_Model/
i3d_5nm_0V7_27C.*`); the characterization/tuning harness is
`scripts/char_nodes.py` (5-node single-device IOFF/ION/SS/VT table, run it
after ANY card change) and `scripts/build_5nm.py` (rebuilds + retunes the
5nm cards from the 7nm sources into `<cwd>/draft/`). 5nm absolute accuracy is
still predictive-model-grade — but it is now *consistent* with the PTM-MG
family instead of 60× off in leakage.

Topology result (feeds the scaling-vs-tiling decision): the extracted
netlists of the 16nm scaled cell AND the 10/7/5nm native cells all match the
20nm 8T write-driver topology exactly (5N/3P, same connectivity up to
drain/source symmetry). Only drawn dimensions differ:
l = 24/22/20/18/12 nm and per-device w = 0.61/0.61/0.27/0.41/0.09–0.11 µm at
20/16/10/7/5 nm. Port order/naming differs per node (10nm: `data write BL BLB
VSS VDD`) — run_wd.sh parses the port order from the extracted .SUBCKT, so
this is transparent.

## Column primitives (standardized 2026-07-12)

The four column primitives were standardized on the 20nm `gen_col` naming —
file name = top cell name, pins renamed to the 20nm set (geometry untouched):

| Canonical | pins | was (16nm / 10nm / 7nm / 5nm) |
|---|---|---|
| `sram_cell` | BL BL_bar WL Q Q_bar VDD VSS | SRAM_CELL / Sramcell_10nm_fin_new333 / SRAM_CELL / SRAM_cell |
| `pc` | BL BL_bar pre_en VDD | PRECHARGE / Precharging_10nm / PRECHARGE / pre_5nm |
| `sense_amp` | BL BL_bar sen_en sen_en_bar VDD VSS | SENSE_AMP2 / SenseAmplifer_10nm / SENSE_AMP2 / SA_5nm |
| `buffer` | BL OUT VDD VSS | buffer / Buffer_10nm / buffer_7nm / buf |

Label renames applied: `BLB`,`BL_BAR`,`!BL` → `BL_bar`; `sense_en(_bar)` →
`sen_en(_bar)`; `IN` → `BL`; `out` → `OUT`. The 20nm originals were copied
into the 20nm SRAM library store unchanged. All 19 possible extractions were smoke-run;
topology compared against the 20nm netlists:

**All 20 primitives (4 cells × 5 nodes) extract cleanly and MATCH the 20nm
topology** (6T cell, 2T pc, 6T latch SA, 4T buffer) as of the final
re-deliveries on 2026-07-12 evening. Issues found and fixed by re-delivery
along the way: 16nm (crashing sram_cell, floating-gate pc/buffer devices,
mislabeled/open sense_amp, buffer.gds that was a precharge copy), 7nm
(sense_amp open: NMOS terminal on an internal net instead of BL_bar), 5nm
(buffer with an extra weak PMOS between OUT and VSS).

## Columns (gen_col.py, built + validated 2026-07-12)

`scripts/gen_col.py --node N --rows R --wd S` assembles one array column from
the standardized primitives + a gen_wd strength ladder and writes
`TECH_<N>nm/column_X<S>_<R>/01_gds/column_X<S>_<R>.gds`:

```
pc                      0.01 um above the top row (BL/BL_bar reach it via M3;
sram_cell x R           its VDD merges by label)   mirror-tiled rows sharing
sense_amp               alternating VDD/VSS rails  oriented VDD-rail-down
wd_X<S>                 ladder top VDD rail shared with the SA
buffer                  oriented VDD-rail-up, under the ladder
```

Vertical placement is pure **rail abutment** (adjacent cells overlap their
full-width M0 edge rails net-on-net) — decoded from and validated against the
verified 20nm reference. Bitlines are M3 straps over every cell's existing
VIA2 stubs; wordlines are full-width M0 straps over each row's WL shape with
`wl[i]` pins; sub-cell port labels are re-stamped on the top cell
(Q/Q_bar deliberately not — same-name text would short the rows' storage
nodes together).

Per-node measured geometry is frozen in `NODE_SPECS` inside the script
(bboxes, rail bands with nets, BL track x, WL band, flips, unit strength);
`--check` re-derives every number from the GDS store and reports drift — run
it after any primitive re-delivery. The store cells now all follow the 20nm
drawing convention (fixed in-GDS 2026-07-12, per the layout owner): the 7nm
sense amp and 5nm buffer were delivered VDD-rail-on-bottom and have been
flipped vertically, and the 16nm write driver (scaled from 20nm) sat 1 nm
off the shared BL grid and was shifted x −0.001 (ladders regenerated, copy
in `array_compiler/compiler_16/gen_wd/` synced). All three fixes are pure
mirror/translate transforms — the regenerated columns flatten-identical to
the extraction-verified ones. Column pitch = bitcell width at every node
(20nm 0.66 um user-confirmed).

Validation (2026-07-12):
- 20nm `column_X4_2` regenerated **flatten-identical** to the reference
  (`array_compiler/compiler_20/gen_col/out/`): 722 polygons, 57 labels.
- 20nm `column_X16_32`: all 4691 polygons identical; labels identical in
  (text, layer, position) — only display-only magnification differs inside
  the ladder, plus the intentional renames `sense_en(_bar)`→`sen_en(_bar)`,
  `out`→`OUT` (canonical primitive pin names).
- `--check` clean at all 5 nodes (17 checks each).
- 4-row unit-strength columns generated at all 5 nodes, extracted
  (`gds2spice.sh`, .sp + .spef): every node yields 44 devices, identical
  ports, **topology MATCH vs 20nm**. Only ICV violations everywhere: 2×
  `text_open_merge` on VDD/VSS — the expected label-merge mechanism (rails
  join only via the array power grid), same as the reference flow.

## Column testbench (run_col.sh + gen_col_tb.py, built 2026-07-12)

`run_col.sh --node N column_X<S>_<R> [--pex]` simulates an extracted column
with a testbench generated per row count by `scripts/gen_col_tb.py`. It ports
the verified 20nm 50 ns TB (`array_spice/20_col_spice`), keeping the original
**slow 10 ns/op cadence** (wide windows — BL swings and sensing settle fully
at every column size; deliberate decision over a compressed clock), and
extends the sequence from 4 to 6 ops so one run yields flip- vs no-flip
write energy:

```
 0- 3 ns  idle                     13-23  RD0   read 0 (expect OUT=0)
 3-13 ns  WR0   write 0 (init)     33-43  RD1   read 1 (expect OUT=VDD)
23-33 ns  WR1f  write 1 = BIT FLIP 53-63  RD1b  read 1 after same-write
43-53 ns  WR1s  write 1 = SAME     90-99       leakage window (settled tail)
```

Write op @T: pre_en release @T, write @T+1, wl @T+2..T+5, precharge restore
@T+7 — each op's energy window is the full [T, T+10] so the bitline recharge
is attributed to the op that discharged it. Read op @T: wl @T+1..T+6, sense
@T+4..T+7, OUT sampled @T+5.5. `data` flips inside the flip-write window so
the WD input inverter's switching counts as flip energy.

Energy test points: the column's single VDD port feeds every sink (WD, SA,
buffer, precharge source, cell pull-ups), so per-op energy =
`INTEG -v(VDD)*i(VVDD)` over the op window; leakage = `AVG` of the same at
90–99 ns. The long idle before the leak window is required: at 512 rows the
supply current keeps decaying for ~25 ns after the last precharge restore
(internal-node equilibration — BL itself is back at VDD within ~2 ns), and a
65 ns window overstated 20nm 512-row leakage 3.5× (1692 vs 484 nW settled). Functional measures sample OUT during each sense window plus BL /
BL_bar hold levels during the write pulses; `col_measures.py` converts the
.mt0 to `measures.csv` and fails loudly on any wrong read-back or missing
measure. Only `wl[0]` is driven; `wl[1..R-1]` are tied to ground directly in
the DUT port list (no per-row sources at 512 rows) — the un-accessed rows
still load the bitlines, which is exactly the row-count effect being swept.

Findings (2026-07-12, post-layout at nominal VDD/25C):
- 2-row columns PASS at 20/16/10/7nm with the node's unit WD.
- **5nm: the X2 unit WD is below write margin** even against a single cell —
  writing 0 leaves BL at 0.19 V (contention with the cell pull-up; the failed
  write burns 0.45 pJ vs 3 fJ normal) and the cell keeps its old value.
  **Minimum usable 5nm driver is X4**; sweeps map 5nm accordingly.
- Row-scaling sweep (rows 64/128/256/512 with WD X8/X16/X32/X64): all 20
  configs PASS post-layout at all 5 nodes; per-run `measures.csv` under
  `TECH_<N>nm/column_*/03_sim/`. Read/write energy and leakage scale ~linearly
  with rows; flip-write > same-write everywhere; BL fall stays < 0.9 ns even
  at 512 rows (the WD mapping keeps drive/load roughly constant — the 512-row
  uptick is bitline-strap RC, not drive starvation).
- 20nm 512-row flip-write 0.171 pJ / read 0.10-0.12 pJ / leak 0.48 uW,
  decreasing monotonically to 7nm (0.071 pJ / 0.06 pJ / 0.32 uW). **5nm is
  leakage-dominated** (HP-only model card): 25.5 uW at 512 rows, so its op
  "energies" are mostly leakage integrated over the 10 ns window — the
  dataset collector must report/subtract the leak baseline
  (E_dyn ≈ E_op − P_leak·10 ns) or 5nm dynamic energy will be meaningless.
- 7nm 2-row leakage reads ≈ −0.3 nW: sub-nW values are below the integration
  noise floor — treat |leak| < 1 nW as "≈0", don't ingest the sign.

## Arrays (gen_array.py, built + validated 2026-07-12)

`scripts/gen_array.py --node N --rows R --wd S --cols C` tiles the generated
`column_X<S>_<R>.gds` horizontally C times at the node's column pitch
(= bitcell width; 20nm 0.66 um confirmed by the layout owner) into
`array_X<S>_<R>x<C>.gds`. Every cell in the column stack is exactly one
pitch wide, so columns abut edge-to-edge with no gap/overlap.

- Net model: **shared** wl[0..R−1] / pre_en / sen_en / sen_en_bar / write /
  VDD / VSS (same-name labels per column; ICV text-merge parallels them —
  the WL M0 straps of adjacent columns additionally abut physically and
  merge into one polygon, so wl nets need no text merge at all);
  **per-column** data/OUT/BL/BL_bar renamed `data[c]`/`OUT[c]`/`BL[c]`/
  `BL_bar[c]`. Only top-cell labels reach flat extraction, so the column's
  top labels are re-stamped at absolute positions on the array top.
- Validated 2026-07-12: 2×2 smoke arrays at all 5 nodes extract with the
  exact expected port set and device count (2 × column devices), ICV clean
  except the usual `text_open_merge` on the shared nets; net-count check
  (array nets = 2·(column nets − 8 shared) + 8) passes at every node — no
  cross-column shorts from the abutment.
- Stress case: 20nm `array_X16_128x32` (largest planned dataset grid point,
  25 984 devices, 21.12 × 114.68 um = 2422 um²) generates and extracts in
  under a minute — extraction cost is not a bottleneck for the phase-4 sweep.
- Footprint (w, h, area in um²) is printed at generation time from the top
  bbox — this is the `total_area_um2` source for the dataset.

## Array testbench (run_array.sh + gen_array_tb.py, built 2026-07-13)

`run_array.sh --node N array_X<S>_<R>x<C> [--pex] [--toggle <0..1>]`
simulates an extracted array with a word-wide testbench generated by
`scripts/gen_array_tb.py` (rows/cols read from the netlist port list).
The array is normally generated with `gen_array.py`'s default write-driver
strength — the smallest strength with clean write margin for the row count
from the phase-2 column sweeps (ceil(rows/8) rounded up to the node unit;
floor X4 at 5nm where X2 is below write margin; 64→X8, 128→X16, 256→X32,
512→X64) — but `--wd` overrides it freely.

**Stimulus summary** (10 ns/op cadence, same intra-op edges as the column
TB; all C columns operate together as one word; only wl[0] is driven,
wl[1..R−1] grounded — idle rows still load the bitlines):

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

Write op @T: pre_en release @T, write @T+1, wl @T+2..T+5, precharge
restore @T+7 — each op's energy window is the full [T, T+10] so bitline
recharge is attributed to the op that discharged it. Read op @T: wl
@T+1..T+6, sense @T+4..T+7, OUT sampled @T+5.5. Toggling columns are
data[0..n_t−1]; their data input falls at T+0.5 inside the toggle-write
window (WD input-inverter switching counts as toggle energy); the holding
columns' data falls inside the fill-write window instead.

**Measurement locations**:

| measure | where / how |
|---|---|
| per-op energy (6×) | `INTEG −v(VDD)·i(VVDD)` over the op's [T, T+10] ns — the array's single VDD port feeds every sink (all columns' WDs, SAs, buffers, precharge PMOS, cell pull-ups) |
| `p_leak_W` | `AVG −v(VDD)·i(VVDD)` at 90–99 ns (all controls idle, settled) |
| `out_rd1_c<c>` | `v(OUT[c])` at 18.5 ns, every column — expect > 0.85·VDD |
| `out_rd0_c<c>` | `v(OUT[c])` at 58.5 ns, every column — expect < 0.15·VDD |
| `blb_wrs_c0` | `v(BL_bar[0])` at 27.9 ns — WD holds BL_bar low in the same-write |
| `bl_wrt_c0` | `v(BL[0])` at 37.9 ns — a toggling column pulls BL low |
| `blb_wrt_c<C−1>` | `v(BL_bar[C−1])` at 37.9 ns — a holding column keeps writing 1 |
| `t_rd_wl_out` | RD10 op: `wl[0]` 50% rise → `OUT[C−1]` 50% fall — **read access time** |
| `t_rd_bl_dev` | RD10 op: `wl[0]` 50% rise → `v(BL_bar[C−1])−v(BL[C−1])` reaching 0.1·VDD |
| `t_rd_sense` | RD10 op: `sen_en` 50% rise → `OUT[C−1]` 50% fall (may be negative) |
| `t_wr_bl` | flip op: `write` 50% rise → `v(BL[C−1])` falling to 0.1·VDD |
| `t_wr_cell` | flip op: `wl[0]` 50% rise → cell-internal Q 50% fall — the write event |
| `t_wr_total` | `t_wr_bl + t_wr_cell` — **write time** (conservative, phases sequential) |

**Read/write delay — method.** All delays are taken at the far column C−1,
which sees the wordline last through the post-layout WL RC (worst case).

*Read* is measured in the RD(1→0) op: the cell stores 0, so the buffered
output leaves its precharged 1 — `t_rd_wl_out` (wl → OUT) is the access
time. Two components are recorded with it: `t_rd_bl_dev`, the
schedule-independent bitline-development time (bitline cap × cell read
current — the part that scales with rows), and `t_rd_sense`. The TB fires
`sen_en` at a fixed wl+3 ns; when the cell alone discharges the bitline past
the output-buffer threshold sooner (small arrays), `t_rd_sense` comes out
**negative** — the sense amp only assisted and `t_rd_wl_out` is
schedule-free. If `t_rd_sense` is positive, the fixed 3 ns sense schedule
is bounding `t_rd_wl_out` and `t_rd_bl_dev` is the honest array-speed
number.

*Write* is measured on a genuine 1→0 flip of the cell at (row 0, col C−1):
in WRt when the whole word toggles (n_t = C), otherwise in WR0f (which
flips columns n_t..C−1). `t_wr_bl` is the write-driver bitline drive time
(the quantity WD sizing controls; the TB fires the WD 1 ns before WL, so
it is cleanly separable). `t_wr_cell` is wl-rise → the cell's internal Q
crossing 50% — the true store event, after which WL could close. The
bitline re-settle after the cell's back-injection bump is deliberately
NOT used as the criterion: with a strong WD the bump is millivolts and
thresholding it is numerically fragile. Q's netlist name (`N32`-style,
different every extraction) is auto-located by `gen_array_tb.py` as the
non-bitline channel terminal of the access transistor gated by `wl[0]` on
`BL[C−1]`, and probed hierarchically as `v(Xdut.<node>)` (verified to
survive SPEF back-annotation).

`array_measures.py` checks all of the above and fails loudly on any wrong
read-back or missing measure (delays must be in (0, 10 ns); `t_rd_sense`
may be negative). Each run dir gets `meta.json` (config, PVT,
toggle rate, run id) + `area.json` (copied from the `gen_array.py` sidecar
`gds/<array>.json`); `collect_array.py` scans `TECH_*nm/array_*/03_sim/*/` and
rebuilds **`dataset_gen/sram/datasets/sram_array.csv`** (idempotent;
latest run per config key wins). Sheet columns: config/PVT keys, `toggle_rate`, `n_toggle_cols`,
then `wr_same_energy_pJ`, `wr_toggle_energy_pJ`, `rd_1to1_energy_pJ`,
`rd_1to0_energy_pJ` (the four dataset targets), aux `wr1_init_energy_pJ` /
`wr0_fill_energy_pJ`, `leak_power_mW`, the delays `rd_delay_ns` /
`rd_bl_dev_ns` / `rd_sense_ns` / `wr_delay_ns` / `wr_bl_ns` / `wr_cell_ns`
(ns), and the layout geometry `width_um` / `height_um` / `total_area_um2`
(from the GDS bounding box via the `gen_array.py` sidecar), plus
`flow_run_id`.

Energies are raw op-window integrals — each includes the leakage flowing
during its 10 ns window, and leakage is recorded as-is at every node
**including 5nm** (no baseline subtraction anywhere in the flow; subtract
`leak_power · 10 ns` downstream if pure dynamic energy is wanted). Sub-nW
|leak| readings at tiny arrays are integration noise (7nm 2×2 reads −5 nW);
ingest with that floor in mind. (Before the 2026-07-13 5nm card
recalibration the 5nm 2×2 leak was 457 nW — ~4.6 fJ of every 10 ns op
window; it is now 6.6 nW, in line with the other nodes.)

Validation (2026-07-13, post-layout at nominal VDD/25C):
- 2×2 arrays PASS at all 5 nodes (all per-column OUT samples correct, BL
  hold checks ok). Read 1→0 costs ~2× read 1→1; toggle-write ~4–5× same-
  write — consistent with the column results.
- Toggle knob is linear: 20nm 2×2 `wr_toggle` at rate 0.5 = 0.01394 pJ vs
  0.01395 predicted from the rate-0 (= `wr_same`) and rate-1 endpoints;
  20nm 16×4 at rate 0.25 = 0.03268 vs 0.03276 predicted. Ops other than
  WRt/WR0f are bit-identical across rates, as they must be.
- 16-row × 4-col grid point ran end-to-end from `gen_col.py` through the
  sheet in ~2 min (default WD picked X4 for 16 rows).
- Delay measures (added 2026-07-13, all 10 configs re-run): read access
  scales monotonically-or-flat across nodes at 2×2 (20nm 82.9 ps → 16nm
  57.9 → 10nm 32.1 → 7nm 28.8 → 5nm 29.5 ps, post-layout; the 5nm value is
  with the recalibrated card — its lower VDD offsets the smaller layout,
  a flag-level blip, not an error); parasitics matter
  (20nm 2×2 pre-layout reads 35.8 ps); −0.05 V slows 20nm by ~3–4 %; going
  2×2 → 16×4 at 20nm roughly doubles both delays (rd 82.9 → 142.1 ps,
  wr 160.8 → 273.2 ps — the growth is bitline cap: `wr_bl` 124 → 247 ps
  while the cell flip stays ~27–37 ps). `t_rd_sense` is negative at every
  config so far — these small arrays discharge the bitline past the buffer
  threshold before the fixed wl+3 ns sense fires, so the recorded access
  times are schedule-free.

## Notes / decisions

- **20nm `hx2mw.tf` version**: the repo had two diverged copies; this pack uses
  the newer one (`20_col_spice/tech`, 2026-07-01, layer numbers shifted vs the
  06-30 `20_wd_spice` copy) on the "tech file for 20nm is final" instruction.
  Since nothing in the automated flow reads it, this only matters for
  interactive CC work — swap the file if the other version was meant.
- The TB template adds `.measure` lines (avg/integrated VDD current during the
  write window, BL fall/rise delays) on top of the original verified 20nm TB.
  The transient stimulus itself is unchanged.
- `lvs.rs` is node-agnostic in practice; extracted devices are always
  `nmos1`/`pmos1` with drawn `l`/`w`, so the node character enters only via
  the drawn gate length, the model cards, and the nxtgrd parasitics.
- Legacy flat run dirs (`array_spice/16`, `array_spice/20`, root logs) are left
  untouched; archive or delete them separately once this flow is adopted.
