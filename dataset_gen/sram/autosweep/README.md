# SRAM autosweep runner

Drives the whole per-configuration flow (GDS generation → extraction →
HSPICE array TB → decoder characterization →
`dataset_gen/sram/datasets/sram_array.csv` + `sram_decoder.csv`) from a
job list.

```
autosweep/
├── jobs.csv          # THE job list — one row per dataset point (edit freely)
├── gen_jobs.py       # grid generator: cartesian product of axes → jobs.csv
├── run_batch.sh      # runs the list; builds missing collateral per job
├── site.env.example  # copy to site.env (git-ignored): PYTHON_GDSTK=...
└── logs/             # one log per job per autosweep invocation
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
cp site.env.example site.env          # once; point PYTHON_GDSTK at gdstk py3
./run_batch.sh                        # run autosweep/jobs.csv
./run_batch.sh myjobs.csv --dry-run   # show per-job actions, run nothing
./run_batch.sh --stop-on-fail         # abort on first failure
./run_batch.sh --no-dec               # array flow only, skip the decoder
./gen_jobs.py --nodes 20 16 10 7 5 --rows 16 32 64 128 --cols 4 8 16 32 \
              --toggles 1.0 > jobs.csv      # regenerate the standard grid
```

Per job, `run_batch.sh` builds only what is missing under
`../TECH_<N>nm/<config>/` — column GDS (`gen_col.py`), array GDS + area
sidecar (`gen_array.py`, `01_gds/`), extraction (`gds2spice.sh`,
`02_pex/`) — then simulates (`run_array.sh` → `03_sim/`, 6-op sequence; see
"Array testbench" in `../array/README.md` for the stimulus and measurement
locations), and finally runs the matching **decoder** characterization
(`../decoder/run_decoder.sh --reuse-gds` → `dec_<R>x<C>/`; needs
dc_shell/icc2_shell licenses). The decoder point is
(node, rows, cols, vdd, temp, pex) — toggle-rate variants share it, so it
runs once per point per invocation, and `--reuse-gds` skips the DC/ICC2/PEX
stages when the collateral already exists from an earlier batch (only the
HSPICE sim repeats). A decoder failure fails that job like any other step.

Jobs run sequentially (single HSPICE license); a failing job logs and the
batch continues. Afterwards `collect_array.py` rebuilds
`../datasets/sram_array.csv` idempotently and `collect_decoder.py` rebuilds
`sram_decoder.csv` + joins `decoder_area_um2`/`macro_area_um2` into the
array sheet — re-running a job just refreshes its row (latest run per
config key wins), so job lists may overlap freely.
