# Logic autosweep runner

Drives the whole per-design-point logic flow (RTL generation → DC
synthesis → ICC2 PnR → StarRC PEX → gate-level simulation → PrimeTime
power) from a job manifest, mirroring the SRAM autosweep
(`dataset_gen/sram/autosweep/`).

```
autosweep/
├── jobs              # THE job manifest — one TSV row per design point
├── run_batch.py      # runs the manifest, stage by stage (see Usage)
├── autocommon.py     # manifest/catalog parsing, run-id naming, scoreboard
├── autortl.py        # stage: rtl-gen   (rtl_gen/ generators → .sv + TB)
├── autosynth.py      # stage: syn       (Design Compiler)
├── autopnr.py        # stage: pnr       (IC Compiler II)
├── autopex.py        # stage: pex       (StarRC)
├── autosim.py        # stage: logic-sim (gate-level sim of the PnR netlist)
├── autopwr.py        # stage: pwr       (PrimeTime PX power)
├── autocollect.py    # stage: collect   (reports → ../datasets/logic_<rtl>.csv)
├── sweep_spec.py     # THE sweep specification: every arch config (pin-capped)
├── autoprobe.py      # stage: probe (T_min per config×node) + gen-jobs (manifest)
├── autosweeprun.py   # stage: sweep (storage-bounded per-job pipeline, resumable)
├── probe_results.tsv # probe output; ok rows are skipped on probe re-runs
├── sweep_failures.tsv# sweep failures (run_id, stage, error); sweep continues past them
└── scoreboard.jsonl  # append-only event log (one JSON object per line)
```

## Job inputs (columns of `jobs`, tab-separated)

Lines starting with `#` are skipped. `rtl_name` and `arch_params` are
always required; the EDA stages additionally need the tech-corner and
clock columns.

| column | required | meaning |
|---|---|---|
| `rtl_name` | yes | generator name in `rtl_gen/` (`intmac`, `fifo`, `crossbar`, ... — see `../SUMMARY.md`) |
| `arch_params` | yes | `key=value` pairs joined with `;` (e.g. `a_width=32;b_width=32;pipeline_stages=3`) |
| `node` | yes (EDA stages) | technology node number (`20`, `16`, `10`, `7`, `5`, ...) — selects `TECH_<NN>nm/` and the catalog entry |
| `process` | syn+ | corner process (`TT`/`SS`/`FF`) — must exist in `tech_libs/catalog.json` |
| `voltage` | syn+ | corner voltage (e.g. `0.9`) — catalog match |
| `temp` | syn+ | corner temperature in °C — catalog match |
| `clock_period_ns` | one of the two | clock constraint; takes precedence when both are set |
| `clock_freq_mhz` | one of the two | alternative clock spec (period = 1000/f) |
| `clock_port` | no (default `i_clk`) | clock port name for `create_clock`; if the design has no such port (combinational NoC blocks), synthesis uses a virtual clock with zero I/O delays instead |
| `reset_port` | no | when set, a `set_false_path -from` is added on it |
| `reset_active` | no | reset polarity, consumed by the generated TB |

Each row gets a deterministic run id
`<rtl>_<arch tokens>_<NN>nm_<process>_<voltage>_<temp>C_<freq>MHz`
(e.g. `intmac_32_32_64_64_3_20nm_TT_0V9_25C_200MHz`) that names every
stage's run directory.

## Usage

```bash
python3.11 run_batch.py                 # all stages, whole manifest
python3.11 run_batch.py syn             # one stage: rtl|syn|pnr|pex|sim|pwr|collect
python3.11 run_batch.py -verbose pnr    # stream tool output while logging
python3.11 run_batch.py -vectored pwr   # power from gate-sim activity
python3.11 run_batch.py -jobs-per-node 2 syn  # 2 concurrent jobs per node worker
python3.11 run_batch.py collect         # parse reports into ../datasets/
python3.11 run_batch.py scoreboard      # stage × status summary (JSON)
```

Requires Python ≥ 3.9 (plus `jinja2` for the rtl-gen stage) and the
Synopsys tool wrappers in `TECH_<NN>nm/run_scripts/` on a licensed host.

## Stages

Every EDA stage works the same way: for each job it (1) resolves the tech
corner (db/ndm/tf/TLUPlus/map/nxtgrd) from `tech_libs/catalog.json`,
(2) instantiates the matching master script from `../master_tcl/` with
job-specific values injected, (3) recreates the run directory
`TECH_<NN>nm/<stage>/<run_id>/` (a re-run wipes the old one), and
(4) executes `TECH_<NN>nm/run_scripts/<stage>.sh <run_id>`, teeing the
tool output to a log in the run directory. Jobs for **different nodes run
in parallel** (one worker per node); within a node, jobs run sequentially
by default, or `-jobs-per-node N` at a time. Concurrency is safe (each job
owns its run directory and RTL variant directory); size N by the EDA
license pool — total concurrent tools = nodes × N — and by host cores
(each ICC2 run claims up to 16).

1. **rtl-gen** (`autortl.py`) — deduplicates the manifest by
   `(rtl_name, arch_params)` and calls the `gen_<rtl_name>` generator from
   `../rtl_gen/`, emitting `rtl_gen/rtl/<variant>/<name>/<name>.sv` + the
   self-checking `<name>_tb.sv`, where `<variant>` is `<name>_<arch tokens>`
   (e.g. `intmac_32_32_64_64_3`). One directory per arch variant — a shared
   per-module directory would let manifests with several configurations of
   one module silently synthesize only the last-generated RTL. No EDA tools
   needed.
2. **syn** (`autosynth.py`, `01_syn.tcl`) — injects `create_clock`
   (+ 0.2 ns uncertainty, reset false path) into the master script, plus one
   `set_dont_use` per cell in the node's catalog `dontuse` list (5nm excludes
   `MUX_X1`/`MUX_X2` to stay uniform with the 44-cell 20–7nm libraries).
   Clock handling is data-driven, not per-module: when the job's clock port
   does not exist on the design (the combinational NoC blocks), the injected
   snippet falls back to a **virtual clock with zero input/output delays**,
   so every in→out path must fit in one cycle and the job's frequency axis
   keeps its meaning. The virtual clock flows to ICC2/PT through the SDC.
   Clocked designs get `set_input_delay (T/2 − uncertainty)` on the data
   inputs and `set_output_delay 0`: the testbenches drive DUT inputs at the
   falling edge, so port→flop cones only get half a cycle in gate-level sim.
   The uncertainty is subtracted because that sim budget is exact — keeping
   it would just floor T_min for every clocked module. Leaving the inputs
   unconstrained lets slow nodes corrupt captures while STA looks clean
   (2026-07-17 PDK pilot: regfile 20/16 nm failed their sim self-checks
   this way; STA startpoints were all internal flops).
   Keepers: `<rtl>_syn.v`, `<rtl>.sdc`, `synthesis.log` (the QoR/area
   reports feed `comb/seq_cells`, `comb/seq_area` → SCR/SAR).
3. **pnr** (`autopnr.py`, `02_pnr.tcl`) — ICC2 place & route of the
   synthesized netlist. CTS and the clock-tree reports are gated on
   register presence: a purely combinational block (virtual clock only)
   has no clock sinks and `synthesize_clock_trees` would error (CTS-036),
   so it is skipped and placeholder clock reports are written. Keeper:
   `<rtl>_icc2.v` (+ layout artifacts and the post-layout area report in
   the run dir).
4. **pex** (`autopex.py`, `03_pex.strc`) — StarRC extraction on the PnR
   result. Keeper: `<rtl>.spef`.
5. **logic-sim** (`autosim.py`) — SDF-annotated gate-level simulation of the
   PnR netlist against the generated TB; builds a `04_sim.f` filelist (point
   `STD_CELL_MODELS_F`/`STD_CELL_MODELS` at the cell models when invoking
   `04_sim.sh`). The TB runs its self-checking functional phase, then (only
   on PASS) a seeded random-stimulus **power phase** (full-rate operands,
   2000 vectors / seed 42 by default — see `../rtl_gen/SUMMARY.md`). autosim
   passes `+nw_clock_period_ps=<job clock>` so the activity toggles at the
   frequency the power row claims; extra plusargs (`+nw_power_cycles`,
   `+nw_power_seed`) can be appended to `04_sim.sh <run_id> [plusargs...]`.
   Outputs: `sim.saif` (toggle window = exactly the power phase; the
   vectored-power activity input) and `sim.vcd` (functional-phase debug
   trace only — dumping stops when the power phase starts). The job clock
   must be timing-clean for the netlist: an SDF gate sim of a WNS < 0 design
   corrupts its own functional checks and the run aborts before writing
   activity — fix the design point, don't relax the sim clock, or the
   activity no longer matches the row's frequency.
6. **pwr** (`autopwr.py`, `05_pwr.tcl`) — PrimeTime PX on the PnR netlist
   with the PEX SPEF back-annotated. Default is **unvectored** (vectorless
   activity, the project-wide 10 % convention); `-vectored` instead reads
   the logic-sim `sim.saif` (preferred — its duration covers exactly the
   TB power phase; `sim.vcd` is only a fallback). Keeper: `power.rpt`.

7. **collect** (`autocollect.py`) — parses the report files the stages above
   write and appends one row per design point to
   `../datasets/logic_<rtl_name>.csv` (one CSV per component class, mirroring
   `dataset_gen/sram/datasets/`). Rows are keyed by `flow_run_id`; re-collecting
   a run id replaces its row. No EDA tools needed.

## Reports the collector reads

Each EDA stage redirects its reports to fixed file names so the collector parses
report files rather than scraping the interleaved tool log.

| stage | file | supplies |
|---|---|---|
| syn | `synthesis.log` (`Report : qor` section) | total/comb/seq cell count + area, SCR/SAR, WNS/TNS |
| pnr | `qor.rpt` | post-route total/comb/seq cell count + area, WNS/TNS |
| pnr | `utilization.rpt` | core area, utilization ratio |
| pnr | `clock_qor.rpt`, `clock_timing.rpt` | clock-tree insertion delay, skew, repeater count (not yet in the CSV) |
| pex | `*.star_sum` | StarRC version |
| pwr | `power_summary.rpt` | internal/switching/leakage/total power + per-power-group split |
| pwr | `power_hier.rpt` | power unit header (report values are scaled to mW), per-instance tree |
| pwr | `global_timing.rpt`, `constraint.rpt` | signoff WNS/TNS, all violators (not yet in the CSV) |
| pwr | `switching_activity.rpt` | activity annotation coverage — sanity check that a vectored run actually consumed the SAIF (not yet in the CSV) |

ICC2 has no `report_area` (unlike DC and PT), so post-route cell areas come from
`report_qor` and the physical area from `report_utilization`.

Every row records the tool version that produced it (`dc_version`,
`icc2_version`, `starrc_version`, `pt_version`) plus `power_activity_mode`,
`stim_mode` and `collector_schema`. Synopsys report labels are stable across
releases, but if one ever moves, the parser raises rather than writing a blank
cell — and the version columns identify which rows a format change would affect.

### Activity modes (`stim_mode`)

Vectored power is measured once per **stimulus class** of the module
(`sweep_spec.POWER_MODES`; e.g. regfile: `random`/`read`/`write`/`idle`,
MACs: `random`/`hold_b`/`sparse50`/`idle`). The TB dispatches on the
`+nw_power_mode` plusarg during the SAIF-windowed power phase; one gate-level
sim runs per mode (shared VCS compile) producing `sim_<mode>.saif`, and one
vectored PrimeTime run consumes each. Rows are keyed by
`(flow_run_id, power_activity_mode, stim_mode)`; unvectored rows carry
`stim_mode=none`. The sweep stage runs every mode automatically; stage-wise,
`run_batch.py pwr -vectored -stim-mode <m>` runs one class. Full mode table
and mechanics: `activity_modes.md`. **Add new modes before a sweep** — run
dirs are pruned after collection, so a mode added later re-runs the whole EDA
chain for the affected jobs.

### How mode stimuli are generated, and when/how they are measured

Stimuli are produced by the testbench **during the gate-level simulation**;
power is computed afterwards by PrimeTime from the toggle statistics that
simulation recorded. Nothing is measured per-operation (contrast the SRAM
flow's per-op `.measure` windows) — each mode yields the **time-averaged
power of one steady-state activity class**.

1. **Stimulus generation (in the TB, at sim time).** Every generated TB runs
   two phases: a self-checking functional phase (mode-independent), then the
   power phase. At power-phase entry the TB seeds `$urandom` (default 42 —
   fully reproducible) and reads `+nw_power_mode`. Each clock negedge
   (combinational modules: each pacing period) `nw_drive_random()` drives one
   input vector; the mode only decides **which port groups get fresh random
   values and which are pinned** — e.g. regfile `read` holds `w_en=0` and
   randomizes only read addresses; `hold_b` latches one seeded constant onto
   the weight operand on the first cycle and randomizes the rest; `idle`
   pins every input while the clock keeps running. An unknown mode string
   `$fatal()`s — it can never silently fall back to random.
2. **Toggle capture (still at sim time).** The SAIF window brackets exactly
   the power phase: `$toggle_start()` at entry, `$toggle_stop()` at exit.
   In between, VCS counts toggles and state-times of **every net of the
   SDF-annotated post-PnR netlist**. One simulation runs per mode (the VCS
   compile is shared; later modes re-run `./simv` directly) and its capture
   is stashed as `sim_<mode>.saif`. The functional phase re-runs identically
   in every mode and is excluded from the window.
3. **Power computation (after sim, in PrimeTime PX, averaged mode).** Per
   mode, one PT run reads netlist + SPEF parasitics + SDC + that mode's
   SAIF, converts the toggle counts over the window duration into per-net
   switching rates, and `update_power` produces internal/switching/leakage
   power averaged over the phase. The collector converts to mW and derives
   `dyn_energy_pJ = dyn_power_mW × clock_period_ns` — the per-cycle energy
   of that activity class — writing one dataset row per
   `(flow_run_id, power_activity_mode, stim_mode)`.

Cost model: the physical implementation (syn/pnr/pex) is built once per job;
each stimulus class adds only one simv re-run plus one PT run.

Areas are library units (um2); power is converted to mW from whatever unit the
PrimeTime report declares. `dyn_energy_pJ` is `dyn_power_mW * clock_period_ns`.

## Dataset sweep (probe → gen-jobs → sweep)

The full dataset run is three commands, each safe to interrupt and re-run
(designed for a shared server, e.g. inside tmux):

```bash
python3 run_batch.py probe -jobs-per-node 2    # overnight: T_min per config×node
python3 run_batch.py gen-jobs                  # seconds: writes the jobs manifest
python3 run_batch.py sweep -jobs-per-node 2    # days: the storage-bounded sweep
```

1. **probe** synthesizes every `sweep_spec.py` configuration once per node at
   an unreachable 0.5 ns clock; the achieved critical path approximates the
   minimum period T_min. Results append to `probe_results.tsv` (ok rows are
   skipped on re-run, error rows retried); each probe run directory is
   deleted right after parsing.
2. **gen-jobs** derives two clocks per (config, node) — tight = 1.2×T_min,
   relaxed = 2×T_min, ceil'd to a 0.25 ns grid — and writes the manifest
   (backing up the previous one to `jobs.prev`). The 1.2× margin absorbs the
   observed syn→PnR timing degradation so vectored rows stay timing-clean.
3. **sweep** pipelines each job through
   syn→pnr→pex→sim (one gate-level run per stimulus mode)→pwr(unvectored)→CSV
   →[pwr(vectored, mode)→CSV per mode], then archives the report texts to
   `../sweep_reports/<run_id>.reports.tar.gz` and deletes the run
   directories. Disk at any moment holds only the jobs in flight
   (nodes × `-jobs-per-node`), not the whole sweep (~350 GB unpruned).
   **Crash resume**: a job is skipped when its dataset CSV already has the
   unvectored row plus one vectored row per stimulus mode of its module, so
   re-running the same command continues where it stopped. A failing job is
   recorded in `sweep_failures.tsv` (its report texts still archived) and
   the sweep moves on.

### Adding a node later (incremental sweep)

All three stages take `-nodes` (comma-separated, e.g. `-nodes 3` or
`-nodes 20,16`), so a newly characterized node can be brought up without
re-running the finished ones. Module-level parallelism (`-jobs-per-node`)
still applies within the node:

```bash
python3 run_batch.py probe -nodes 3 -jobs-per-node 4   # probe the new node only
python3 run_batch.py gen-jobs -nodes 3                 # manifest = that node's rows only
python3 run_batch.py sweep -nodes 3 -jobs-per-node 4   # sweep those rows
```

- The node must already be in the technology catalog; probe/gen-jobs fail
  fast with "no TT/25C corners in the catalog" otherwise.
- `gen-jobs -nodes ...` writes a manifest holding ONLY those nodes (the
  previous manifest is backed up to `jobs.prev` as usual). For a permanent
  addition, also append the node to `SWEEP_NODES` in `sweep_spec.py` so
  future unfiltered runs cover it.
- With a single node the license/core budget is undivided, so
  `-jobs-per-node` can go higher than in the full run (total concurrent
  tools = nodes × jobs-per-node).
- Finished nodes are protected even without the filter: probe skips ok
  rows of `probe_results.tsv` and sweep skips jobs whose CSV already has
  both activity-mode rows — `-nodes` just avoids scanning them at all and
  keeps the manifest scoped.

To re-examine a collected row, start from its report archive; to reproduce
it fully, re-run that single design point with the per-stage commands above.

### Adding a module later (incremental sweep)

A new primitive needs code in three places, then the ordinary three commands
— no manual job-list surgery and no re-run of finished modules:

1. **Generator + templates** (`rtl_gen/`): a `gen_<name>()` entry point and
   the `<name>.sv.j2` / `<name>_tb.sv.j2` templates. The TB must follow the
   shared power-stimulus contract (`_power_stim.sv.j2`): functional
   self-check first, then `nw_drive_random()` driving the power phase.
2. **Sweep spec** (`sweep_spec.py`): the module's configuration list in
   `sweep_configs()`, membership in `CLOCKED_MODULES` if it has
   `i_clk`/`i_rst_n`, and — if its ports have distinguishable operations —
   its stimulus classes in `POWER_MODES` (**before** the sweep: run dirs are
   pruned after collection, so a mode added afterwards re-runs the whole EDA
   chain for the affected jobs). Modes must be dispatched in the TB template
   in the same change; an un-dispatched TB `$fatal()`s on any non-random
   mode rather than silently measuring random activity.
3. **Run as usual**: `probe` → `gen-jobs` → `sweep`. Resume keys make the
   addition incremental for free: probe skips every (config, node) already
   `ok` in `probe_results.tsv` — only the new module's configurations run —
   and sweep skips jobs whose dataset rows are complete, so only the new
   module's manifest rows execute. The regenerated manifest covers old and
   new modules alike; the old rows simply skip.

The collector needs no changes: architectural parameters become columns
automatically (`parse_arch_params`), and each module gets its own
`datasets/logic_<name>.csv`, so new key sets never disturb existing files.

## Scoreboard

Every stage appends structured events (timestamp, stage, status
`start|running|skip|done|error|terminated`, run id, details) to
`scoreboard.jsonl`. `run_batch.py scoreboard` prints per-stage status
counts; the raw JSONL is the audit trail for which run directories are
current. A failing job logs an `error` event and the sweep continues with
the remaining jobs.
