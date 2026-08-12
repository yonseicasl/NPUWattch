# SRAM estimator

Standalone plugin. Everything SRAM lives in this directory; nothing outside it
imports these files as Python modules.

```
sram.py           entry module (stdlib-only) — model, solver, entrypoints
sram_mlp.py       torch side — MLP inference (loaded lazily by sram.py)
train_sram.py     trains the 4 MLPs, writes the checkpoints + eval_report.json
<metric>__v1.*    checkpoint quartets (.pt + scalers/loss/meta sidecars)
```

## How it talks to EstimatorHost

The host never imports this package — the contract is file-shaped:

1. **Discovery**: `EstimatorHost.scan_estimators()` looks for
   `estimators/<name>/<name>.py` and reads the module-level `ESTIMATOR_SPEC`
   dict via `ast.literal_eval` (no execution). That dict is how this plugin
   announces itself: primitive name (`"sram"`), entrypoints, parameters
   (with `arch_keys` aliases), model files.
2. **Calls**: the host executes `sram.py` with `runpy.run_path` and invokes an
   entrypoint function with a plain **features dict**, e.g.
   `host.estimate_energy("sram", {"node": 7, "depth": 512, "bw": 128})`.
   Entrypoints: `energy` / `area` / `timing` / `leakage` (scalar), `report` /
   `unit_costs` (dict), `unit_cost_provider` (a `UnitCostProvider` object for
   the §6 energy-aggregation path). On any invalid input they print
   `[ERROR] sram: …` and return `None` — they never raise at the host.
3. **Routing**: the harness that reads the description decides. For
   Accelergy/Timeloop inputs that is
   `harness/timeloop/vocabulary.reclassify_regfile_as_sram`, which sends any
   regfile-classed component with `mem_banks·mem_depth_per_bank·data_width >
   32768` bits here (the rule moved out of the retired
   `npuwattch_class_mapper` on 2026-08-12).

Key feature-dict conventions: `depth` = **words per bank**; `bw` = word width
in bits; `toggle_rate` = fraction of data bits flipping per write access
(default 0.5); `source` = `auto | table | mlp` (auto prefers the trained MLPs
when the quartets are present and torch imports, else the measured table).

## The solver (features → physical SRAM)

The datasets contain single-array tiles (no column mux, no wordline
stitching), each with its own row decoder. The solver maps a CACTI-style
query onto a grid of those measured tiles:

1. `normalize_config` validates/canonicalizes the features (node, PVT range,
   aliases, port clamp).
2. Candidate tile shapes = the node's **measured grid only** (rows 8–512 ×
   cols 4–64, ≤ 8192 cells) — shapes are never interpolated.
3. For each candidate `(r, c)`: `n_vert = ceil(depth / r)` vertical groups
   (one selected per access, the rest idle), `n_horz` horizontal tiles (all
   fire together); a non-power-of-2 width gets a smaller ragged edge tile
   (e.g. width 20 → 16 + 4).
4. Each candidate is fully costed (per-tile costs from the table or the
   MLPs; whole-instance composition over banks × groups × ports, with
   non-firing decoders charged `dec_idle` per cycle) and the best one wins
   the `optimize` objective (`energy` default, `area`, `delay`) —
   deterministic lexicographic tie-break.
5. Delays follow the measured composition `t_read = dec_wlen_wl + rd_delay`,
   `t_write = max(dec_wlen_wl, wr_bl) + wr_cell`.

`get_report` echoes the chosen structure (tile shape, groups, utilization),
cost breakdown, PVT scaling diagnostics, provenance (dataset rows used) and
all warnings.
