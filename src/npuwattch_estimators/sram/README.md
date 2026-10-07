# SRAM estimator

A standalone plugin. All the SRAM code is in this directory, and nothing
outside it imports these files as Python modules.

```
sram.py           entry module (stdlib-only) — model, solver, entrypoints
sram_mlp.py       torch side — MLP inference (loaded lazily by sram.py)
train_sram.py     trains the 4 MLPs, writes the checkpoints + eval_report.json
<metric>__v1.*    checkpoint quartets (.pt + scalers/loss/meta sidecars)
```

## How it talks to EstimatorHost

The host never imports this package. They communicate through files and a
fixed set of functions:

1. **Discovery**: `EstimatorHost.scan_estimators()` looks for
   `npuwattch_estimators/<name>/<name>.py` and reads the module-level
   `ESTIMATOR_SPEC` dict with `ast.literal_eval`, without running the module.
   This dict tells the host what the plugin offers: the primitive name
   (`"sram"`), the entrypoints, the parameters (with `arch_keys` aliases), and
   the model files.
2. **Calls**: the host runs `sram.py` with `runpy.run_path` and calls an
   entrypoint function with a plain **features dict**, for example
   `host.estimate_energy("sram", {"node": 7, "depth": 512, "bw": 128})`.
   `energy` / `area` / `timing` / `leakage` return a number, `report` /
   `unit_costs` return a dict, and `unit_cost_provider` returns a
   `UnitCostProvider` object for the §6 energy-aggregation path. On invalid
   input, they print `[ERROR] sram: …` and return `None`. They never raise an
   exception to the host.
3. **Routing**: the harness that reads the description decides which
   components come here. For Accelergy/Timeloop inputs, that's
   `npuwattch_harness/timeloop/vocabulary.reclassify_regfile_as_sram`. It
   sends any regfile-class component with `mem_banks·mem_depth_per_bank·data_width >
   32768` bits here.
   <!-- The rule moved out of the retired `npuwattch_class_mapper` on
   2026-08-12. -->

Key feature-dict conventions:

- `mem_depth_per_bank` is the number of **words per bank**. A harness divides
  a total depth by the bank count before it gets here.
- `bw` is the word width in bits.
- `toggle_rate` is the fraction of data bits that flip on each write access
  (default 0.5).
- `source` is `auto | table | mlp`. `auto` uses the trained MLPs when the
  checkpoint quartets are present and torch can be imported. Otherwise it uses
  the measured table.

## Vocabulary

From smallest to largest:

- **tile**: a measured bitcell array plus its row decoder (a CACTI sub-array).
- **tile group**: `n_horz` tiles that fire together. Each bank has `n_vert`
  groups, and one group is selected per access.
- **macro**: a template instance (`sram_64k`/`sram_256k`).
- **bank** (`mem_banks`): has its own decoders, can be addressed on its own,
  and can be accessed at the same time as other banks.
- **instance** (`count`).

Ports are the physical ports of each bank (at most 2), not the number of
concurrent accesses. The full table is in DEVELOPMENT_MANUAL §3.8.

## The solver: from features to a physical SRAM

The datasets contain single-array tiles, each with its own row decoder (no
column mux and no wordline stitching). The solver maps a CACTI-style query onto
a grid of these measured tiles:

1. `normalize_config` checks the features and puts them in standard form
   (node, PVT range, aliases, and port limit).
2. The candidate tile shapes come from the node's **measured grid only** (rows
   8–512 × cols 4–64, ≤ 8192 cells). Shapes are never interpolated.
3. For each candidate `(r, c)`, there are `n_vert = ceil(depth / r)` vertical
   groups (one is selected per access, and the rest stay idle) and `n_horz`
   horizontal tiles (all fire together). A width that isn't a power of 2 gets
   a smaller edge tile (for example, width 20 becomes 16 + 4).
4. Each candidate is fully costed. Per-tile costs come from the table or the
   MLPs, and the whole instance is built up over banks × groups × ports. Only
   the accessed bank is clocked: one access pays for its own group plus
   `dec_idle` of the other groups in that bank. Other banks, and cycles
   without an access, use only leakage power. The candidate with the **fewest
   tiles per bank** wins, and the `optimize` objective (`energy` by default,
   `area`, or `delay`) breaks ties, with a fixed lexicographic order as the
   final tie-break. The datasets don't include the cost of joining tiles (no
   glue logic between vertical groups, and one decoder per horizontal tile),
   so the objective alone would favor many small tiles.
5. Delays follow the measured composition `t_read = dec_wlen_wl + rd_delay`,
   `t_write = max(dec_wlen_wl, wr_bl) + wr_cell`.

`get_report` returns the chosen structure (tile shape, groups, and
utilization), the cost breakdown, PVT scaling diagnostics, provenance (the
dataset rows used), and all warnings.
