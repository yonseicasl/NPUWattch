# SRAM autosweep runner

Drives the whole per-configuration flow (GDS generation → extraction →
HSPICE array TB → decoder characterization →
`dataset_gen/sram/datasets/sram_array.csv` + `sram_decoder.csv`) from a
job list, with the same operating model as the logic autosweep driver:
all nodes in parallel, sheet-based resume, and storage-bounded runs.

```
autosweep/
├── jobs.csv            # THE job list — one row per dataset point (edit freely)
├── gen_jobs.py         # grid generator: cartesian product of axes → jobs.csv
├── run_batch.py        # the driver (replaced run_batch.sh, 2026-07-15)
├── qa_sheets.py        # sheet-level QA warnings (run after every collect)
├── sanity_bounds.md    # the FAIL/WARN value-bound list (enforced)
├── site.env.example    # copy to site.env (git-ignored): PYTHON_GDSTK=...
├── sweep_failures.tsv  # one line per failed job (created on first failure)
└── logs/               # one log per job per autosweep invocation
```

## Job inputs (columns of jobs.csv)

| column | required | default when blank | meaning |
|---|---|---|---|
| `node` | yes | — | `20 \| 16 \| 10 \| 7 \| 5`; picks tech pack, model cards, nominal VDD (0.90/0.85/0.80/0.75/0.70 V) and default temperature from `tech_libs/techlib_<N>nm/sram/node.env` (catalog `sramdir`) |
| `rows` | yes | — | bitcells per column (wordlines) |
| `cols` | yes | — | columns = word width (bits) |
| `wd` | no | performance map | write-driver strength X`wd`; blank = smallest strength with clean write margin from the phase-2 column sweeps: ceil(rows/8) rounded up to the node unit, floor X4 at 5nm (X2 is below 5nm write margin) |
| `toggle_rate` | no | `1.0` | fraction of columns flipping in the toggle-write op (0..1); the toggle-write energy scales linearly between the same-write (rate 0) and full-flip (rate 1) endpoints |
| `vdd_V` | no | node nominal | absolute supply override; the sheet's `voltage_offset_V` is computed against the node nominal |
| `temp_C` | no | `node.env` TEMP (25) | simulation temperature |
| `pex` | no | `1` | `1` = post-layout (SPEF back-annotation), `0` = pre-layout |

Not yet sweepable (recorded as fixed `hp`/`TT` in the sheet): transistor
flavor and process corner — each node's tech pack carries a single model
card today (5nm is HP-only). They become job inputs once SS/FF/LP cards
land in `tech_libs/techlib_<N>nm/sram/models/`.

## Usage

```bash
cp site.env.example site.env        # once; point PYTHON_GDSTK at a gdstk py3
./run_batch.py --dry-run            # per-node plan + skip counts, run nothing
./run_batch.py                      # run autosweep/jobs.csv, all nodes parallel
./run_batch.py myjobs.csv -jobs-per-node 2   # 2 concurrent sims per node
./run_batch.py -nodes 3             # only node 3 rows of the list (see below)
./run_batch.py --no-dec             # array flow only, skip decoder points
./run_batch.py --stop-on-fail      # abort the whole batch on first failure
./gen_jobs.py --nodes 20 16 10 7 5 --rows 16 32 64 128 --cols 4 8 16 32 \
              --toggles 1.0 > jobs.csv      # regenerate the standard grid
```

The driver runs on the system python3 (3.6-ok, stdlib only); only the GDS
generators need the gdstk python from `site.env`.

### Parallelism

Jobs are grouped by node and every node runs in parallel (one worker per
node); within a node, `-jobs-per-node N` sims run concurrently (default
1). Total concurrent HSPICE = nodes × N — size N to the license seats,
remembering that decoder points also take dc_shell/icc2_shell seats while
their collateral is being built. Per-config collateral builds and the
whole decoder script are serialized with per-cell locks, so two PVT
points of one configuration never race on shared GDS/PEX/DC/ICC2 files.

### Resume / skip rules

- An array job whose configuration key (node, transistor, corner,
  voltage_offset, temperature, rows, cols, wd, effective toggle_rate,
  pex) already has a row in `datasets/sram_array.csv` is skipped.
- A decoder point (node, rows, cols, voltage_offset, temperature, pex)
  already in `sram_decoder.csv` is skipped — decoder points are planned
  independently of their array jobs, so a decoder missed by an earlier
  `--no-dec` batch runs even when the array row exists.
- Crash-interrupted jobs left no sheet row and re-run whole; duplicate
  keys inside one job list run once. Re-running the same command after a
  crash therefore continues where it stopped.
- To deliberately re-measure a config, delete its sheet row (or run
  `collect_*` after removing the run dir) — latest run per key wins.

### Adding a node later (incremental sweep)

`-nodes 3` (or `-nodes 20,16`) filters the job list to those nodes and
fails fast if a requested node has no `sramdir` in
`tech_libs/catalog.json`, so a typo cannot burn a batch. Because resume
is sheet-based, simply appending the new node's rows to `jobs.csv` and
re-running without `-nodes` also works — finished nodes all skip — but
the filter avoids even planning them. A new node additionally needs its
SRAM tech pack (node.env, model cards, nxtgrd, std-cell GDS store) and a
`NODE_SPECS` entry in `array/scripts/gen_col.py`; with a single node
running, raise `-jobs-per-node` since the license bound is nodes × N.

### Storage bounding

- **Sim run dirs** (`03_sim`/`05_sim`): right after each sim the run dir
  is pruned to `meta.json`, `area.json`, `wl_load.json`, `measures.csv`,
  `sim.log`, the `.mt0`, the testbench, and a **gzipped tr0**; the
  netlist copy, `.lis`/`.ic0`/`.st0`/`.pa0` and symlinks are deleted.
  Both collect scripts read only the kept files, so pruned dirs remain
  valid sources for idempotent sheet rebuilds.
- **tr0 size at the source**: the TB generators now emit `.option probe`,
  so the tr0 holds only the `.probe` port list instead of every internal
  node of the flat extracted netlist — this alone is what shrank the
  512-row decoder tr0 from ~385 MB. The full 0–100 ns of the probed
  ports is recorded (no time windowing).
- **Decoder DC/ICC2/GDS/PEX stage dirs**: after the last batch job of a
  decoder config finishes cleanly, `01_syn`..`04_pex` are pruned to
  reports and json sidecars (`.rpt`, `dims/rails.json`, `icc2_reports/`,
  ICV `.RESULTS`). This intentionally breaks `--reuse-gds` for that
  config — a future batch on it re-runs DC/ICC2/PEX. A failed config is
  left unpruned for debugging.
- **Array `01_gds`/`02_pex` collateral is kept** (a few MB per config):
  every PVT point of the config reuses it, and the decoder flow reads
  the array SPEF for its wordline load — deleting it would force a
  licensed re-extraction per PVT point for no meaningful saving.

### After the batch

`collect_array.py --skip-bad` rebuilds `../datasets/sram_array.csv` and
`collect_decoder.py` rebuilds `sram_decoder.csv` + joins
`decoder_area_um2`/`macro_area_um2` into the array sheet (latest run per
config key wins). Runs whose functional/range checks failed carry a
`verdict,FAIL: ...` row in their `measures.csv` (written by
`array_measures.py`/`dec_measures.py`; all measured values are kept for
debugging) and are excluded from both sheets — a failed re-run can never
shadow an earlier good run. The FAIL/WARN value bounds are listed in
`sanity_bounds.md` (enforced in the measures scripts); after collect,
`qa_sheets.py` prints sheet-level warnings (trend/monotonicity
checks — rows are never dropped). Failures are appended to `sweep_failures.tsv` (tag,
step, error) and never stop the batch unless `--stop-on-fail`; per-job
logs are in `logs/`.
