# SRAM autosweep runner

This runner drives the full flow for each configuration from a job list:
GDS generation, extraction, the HSPICE array TB, and decoder
characterization. The results go to
`dataset_gen/sram/datasets/sram_array.csv` and `sram_decoder.csv`. It works
like the logic autosweep driver: all nodes run in parallel, resume is based
on the dataset sheets, and disk use stays bounded.

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
| `node` | yes | — | `20 \| 16 \| 10 \| 7 \| 5`. Selects the tech pack, model cards, nominal VDD (0.90/0.85/0.80/0.75/0.70 V), and default temperature from `tech_libs/techlib_<N>nm/sram/node.env` (catalog `sramdir`). |
| `rows` | yes | — | bitcells per column (wordlines) |
| `cols` | yes | — | number of columns, which is the word width (bits) |
| `wd` | no | performance map | Write-driver strength X`wd`. If blank, the flow uses the smallest strength with a clean write margin in the phase-2 column sweeps: ceil(rows/8) rounded up to the node unit, with a minimum of X4 at 5nm (X2 is below the 5nm write margin). |
| `toggle_rate` | no | `1.0` | Fraction of columns that flip in the toggle-write op (0..1). Toggle-write energy scales linearly between the same-write (rate 0) and full-flip (rate 1) end points. |
| `vdd_V` | no | node nominal | Absolute supply override. The sheet's `voltage_offset_V` is computed relative to the node nominal. |
| `temp_C` | no | `node.env` TEMP (25) | simulation temperature |
| `pex` | no | `1` | `1` for post-layout (SPEF back-annotation), `0` for pre-layout |

Transistor flavor and process corner are recorded as fixed `hp`/`TT` in the
sheet. We are preparing to support them as job inputs in the future.
<!-- Original note: Not yet sweepable (recorded as fixed `hp`/`TT` in the
sheet): transistor flavor and process corner — each node's tech pack
carries a single model card today (5nm is HP-only). They become job inputs
once SS/FF/LP cards land in `tech_libs/techlib_<N>nm/sram/models/`. -->

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

The driver runs on the system python3 (3.6 works, and it uses only the
standard library). Only the GDS generators need the gdstk python from
`site.env`.

### Parallelism

Jobs are grouped by node, and all nodes run in parallel (one worker per
node). Within a node, `-jobs-per-node N` sims run at the same time (default
1). The total number of HSPICE runs at once is nodes × N, so choose N based
on your license seats. Keep in mind that decoder points also use
dc_shell/icc2_shell seats while their files are being built. The
collateral builds for each config and the whole decoder script are
serialized with per-cell locks. This way, two PVT points of one
configuration never write to the same GDS/PEX/DC/ICC2 files at once.

### Resume and skip rules

- An array job is skipped if its configuration key (node, transistor,
  corner, voltage_offset, temperature, rows, cols, wd, effective
  toggle_rate, pex) already has a row in `datasets/sram_array.csv`.
- A decoder point (node, rows, cols, voltage_offset, temperature, pex) is
  skipped if it is already in `sram_decoder.csv`. Decoder points are
  planned separately from their array jobs. So a decoder point skipped by
  an earlier `--no-dec` batch still runs, even when the array row exists.
- A job interrupted by a crash leaves no sheet row, so it runs again from
  the start. Duplicate keys within one job list run once. This means that
  re-running the same command after a crash picks up where it stopped.
- To measure a config again, delete its sheet row (or remove the run dir
  and then run `collect_*`). The latest run for each key wins.

### Adding a node later (incremental sweep)

`-nodes 3` (or `-nodes 20,16`) limits the job list to those nodes. It stops
right away if a requested node has no `sramdir` in
`tech_libs/catalog.json`, so a typo can't waste a batch. Because resume is
based on the sheets, you can also just add the new node's rows to
`jobs.csv` and run again without `-nodes`. All finished nodes are skipped,
but the filter avoids even planning them. A new node also needs its SRAM
tech pack (node.env, model cards, nxtgrd, std-cell GDS store) and a
`NODE_SPECS` entry in `array/scripts/gen_col.py`. When only one node is
running, raise `-jobs-per-node`, since the license limit is nodes × N.

### Storage bounding

- **Sim run dirs** (`03_sim`/`05_sim`): Right after each sim, the run dir
  is pruned down to `meta.json`, `area.json`, `wl_load.json`,
  `measures.csv`, `sim.log`, the `.mt0`, the testbench, and a **gzipped
  tr0**. The netlist copy, `.lis`/`.ic0`/`.st0`/`.pa0`, and symlinks are
  deleted. Both collect scripts read only the kept files, so pruned dirs
  are still valid sources when you rebuild a sheet.
- **tr0 size at the source**: The TB generators emit `.option probe`, so
  the tr0 holds only the `.probe` port list instead of every internal node
  of the flat extracted netlist. This keeps the tr0 small (the 512-row
  decoder tr0 is about 385 MB without it). The full 0–100 ns of the probed
  ports is recorded, with no time windowing.
  <!-- Original wording: the TB generators now emit `.option probe` ...
  this alone is what shrank the 512-row decoder tr0 from ~385 MB. -->
- **Decoder DC/ICC2/GDS/PEX stage dirs**: After the last batch job of a
  decoder config finishes without errors, `01_syn`..`04_pex` are pruned
  down to reports and json sidecars (`.rpt`, `dims/rails.json`,
  `icc2_reports/`, ICV `.RESULTS`). As a result, `--reuse-gds` no longer
  applies to that config, and a later batch on it runs DC/ICC2/PEX again. A
  failed config is left as is for debugging.
- **Array `01_gds`/`02_pex` files are kept** (a few MB per config). Every
  PVT point of the config reuses them, and the decoder flow reads the array
  SPEF for its wordline load. Deleting them would mean a licensed
  re-extraction for each PVT point, for very little saved space.

### After the batch

`collect_array.py --skip-bad` rebuilds `../datasets/sram_array.csv`, and
`collect_decoder.py` rebuilds `sram_decoder.csv` and joins
`decoder_area_um2`/`macro_area_um2` into the array sheet. The latest run
for each config key wins. If a run fails its functional or range checks,
its `measures.csv` gets a `verdict,FAIL: ...` row (written by
`array_measures.py`/`dec_measures.py`; all measured values are kept for
debugging), and the run is left out of both sheets. So a failed re-run can
never replace an earlier good run. The FAIL/WARN value bounds are listed in
`sanity_bounds.md` and are enforced in the measures scripts. After collect,
`qa_sheets.py` prints sheet-level warnings from trend and monotonicity
checks; it never drops rows. Failures are added to `sweep_failures.tsv`
(tag, step, error) and don't stop the batch unless you pass
`--stop-on-fail`. Per-job logs are in `logs/`.
