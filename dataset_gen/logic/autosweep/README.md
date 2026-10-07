# Logic autosweep runner

This runner drives the full logic flow for each design point from a job
manifest: RTL generation, DC synthesis, ICC2 place and route, StarRC
extraction, gate-level simulation, and PrimeTime power. It works the same
way as the SRAM autosweep (`dataset_gen/sram/autosweep/`).

```
autosweep/
├── jobs              # THE job manifest — one TSV row per design point
├── run_batch.py      # the one-way workflow CLI: probe → gen-jobs → rtl → sweep
├── autocommon.py     # manifest/catalog parsing, run-id naming, scoreboard
├── autortl.py        # stage: rtl       (rtl_gen/ generators → .sv + TB)
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
├── sweep_failures.tsv# sweep failures (run_id, stage, error); sweep continues past
│                     # them; `rerun-failed` consumes and retires this file
└── scoreboard.jsonl  # append-only event log (one JSON object per line)
```

## Job inputs (columns of `jobs`, tab-separated)

Lines that start with `#` are skipped. `rtl_name` and `arch_params` are
always required. The EDA stages also need the tech-corner and clock
columns.

| column | required | meaning |
|---|---|---|
| `rtl_name` | yes | Generator name in `rtl_gen/` (`intmac`, `fifo`, `crossbar`, ...; see `../SUMMARY.md`) |
| `arch_params` | yes | `key=value` pairs joined with `;` (e.g. `a_width=32;b_width=32;pipeline_stages=3`) |
| `node` | yes (EDA stages) | Technology node number (`20`, `16`, `10`, `7`, `5`, ...). Selects `TECH_<NN>nm/` and the catalog entry. |
| `process` | syn+ | Corner process (`TT`/`SS`/`FF`). Must exist in `tech_libs/catalog.json`. |
| `voltage` | syn+ | Corner voltage (e.g. `0.9`). Must match the catalog. |
| `temp` | syn+ | Corner temperature in °C. Must match the catalog. |
| `clock_period_ns` | one of the two | Clock constraint. If both clock columns are set, this one is used. |
| `clock_freq_mhz` | one of the two | Alternative clock setting (period is 1000/f) |
| `clock_port` | no (default `i_clk`) | Clock port name for `create_clock`. If the design has no such port (combinational NoC blocks), synthesis uses a virtual clock with zero I/O delays. |
| `reset_port` | no | If set, a `set_false_path -from` is added on this port. |
| `reset_active` | no | Reset polarity, used by the generated TB. |

Each row gets a fixed run id,
`<rtl>_<arch tokens>_<NN>nm_<process>_<voltage>_<temp>C_<freq>MHz`
(e.g. `intmac_32_32_64_64_3_20nm_TT_0V9_25C_200MHz`), which names the run
directory of every stage.

## Usage

The workflow runs in one direction. Each command uses the output of the
command before it:

```bash
python3 run_batch.py probe -jobs-per-node 2   # overnight: T_min per config×node
python3 run_batch.py gen-jobs                 # seconds: writes the jobs manifest
python3 run_batch.py rtl                      # seconds: renders every RTL variant + TB
python3 run_batch.py sweep -jobs-per-node 2   # days: the storage-bounded sweep
python3 run_batch.py rerun-failed             # patch clocks for recorded failures, retire the log
python3 run_batch.py scoreboard               # stage × status summary (JSON)
```

You need Python 3.9 or later (plus `jinja2` for the rtl stage) and the
Synopsys tool wrappers in `TECH_<NN>nm/run_scripts/` on a licensed host.
To debug one design point by hand, run the stage scripts directly
(`TECH_<NN>nm/run_scripts/<stage>.sh <run_id>`).

## Stages

The sweep runs each job through the stages below as a pipeline. There is
no separate batch mode for a single stage. `rtl` is the only stage with its
own command, because you may need to regenerate testbenches between sweep
runs.

Every EDA stage works the same way. For each job, it:

- looks up the tech corner (db/ndm/tf/TLUPlus/map/nxtgrd) in
  `tech_libs/catalog.json`,
- fills in the matching master script from `../master_tcl/` with the job's
  values,
- recreates the run directory `TECH_<NN>nm/<stage>/<run_id>/` (a re-run
  deletes the old one), and
- runs `TECH_<NN>nm/run_scripts/<stage>.sh <run_id>` and copies the tool
  output to a log in the run directory.

Jobs for **different nodes run in parallel**, with one worker per node.
Within a node, jobs run one at a time by default, or N at a time with
`-jobs-per-node N`. Running jobs at the same time is safe, because each job
owns its run directory and its RTL variant directory. Pick N based on your
EDA license pool (the total number of tool runs at once is nodes × N) and
on host cores (each ICC2 run uses up to 16).

1. **rtl** (`autortl.py`): Removes duplicate `(rtl_name, arch_params)`
   entries from the manifest and calls the `gen_<rtl_name>` generator from
   `../rtl_gen/`. It writes `rtl_gen/rtl/<variant>/<name>/<name>.sv` and the
   self-checking `<name>_tb.sv`, where `<variant>` is `<name>_<arch tokens>`
   (e.g. `intmac_32_32_64_64_3`). Each arch variant gets its own directory,
   so one manifest can hold several configurations of the same module. No
   EDA tools are needed.
   <!-- Original rationale: One directory per arch variant — a shared
   per-module directory would let manifests with several configurations of
   one module silently synthesize only the last-generated RTL. -->
2. **syn** (`autosynth.py`, `01_syn.tcl`): Adds `create_clock` (with 0.2 ns
   uncertainty and a reset false path) to the master script, plus one
   `set_dont_use` for each cell in the node's catalog `dontuse` list.
   <!-- Original note: (5nm excludes `MUX_X1`/`MUX_X2` to stay uniform with
   the 44-cell 20–7nm libraries). This is outdated: all five nodes now have
   the same 51-cell set and the `dontuse` list is empty. -->

   Clock handling depends on the design's ports, not on the module type. If
   the job's clock port does not exist on the design (the combinational NoC
   blocks), synthesis uses a **virtual clock with zero input/output
   delays**. Every input-to-output path must then fit in one cycle, so the
   job's frequency still has a clear meaning. The virtual clock is passed on
   to ICC2 and PT through the SDC.

   Clocked designs get `set_input_delay (T/2 − uncertainty)` on the data
   inputs and `set_output_delay 0`. The testbenches drive DUT inputs on the
   falling clock edge, so paths from input ports to flops get only half a
   cycle in gate-level sim. The uncertainty is subtracted because the sim
   budget is exact. Keeping it would only raise T_min for every clocked
   module. With these input constraints, STA checks the same port-to-flop
   paths that the gate-level sim uses.
   <!-- Original note: Leaving the inputs unconstrained lets slow nodes
   corrupt captures while STA looks clean (2026-07-17 PDK pilot: regfile
   20/16 nm failed their sim self-checks this way; STA startpoints were all
   internal flops). -->

   Kept files: `<rtl>_syn.v`, `<rtl>.sdc`, and `synthesis.log`. The QoR and
   area reports in the log give `comb/seq_cells` and `comb/seq_area`, which
   are used for SCR/SAR.
3. **pnr** (`autopnr.py`, `02_pnr.tcl`): ICC2 place and route of the
   synthesized netlist. CTS and the clock-tree reports run only when the
   design has registers. A purely combinational block (virtual clock only)
   has no clock sinks, and `synthesize_clock_trees` would stop with error
   CTS-036. So the flow skips CTS for these blocks and writes placeholder
   clock reports. Kept file: `<rtl>_icc2.v`. The layout files and the
   post-layout area report stay in the run directory.
4. **pex** (`autopex.py`, `03_pex.strc`): StarRC extraction on the PnR
   result. Kept file: `<rtl>.spef`.
5. **logic-sim** (`autosim.py`): Runs SDF-annotated gate-level simulation
   of the PnR netlist with the generated TB. It builds a `04_sim.f` file
   list. When you call `04_sim.sh`, point `STD_CELL_MODELS_F`/
   `STD_CELL_MODELS` at the cell models. The TB first runs its
   self-checking functional phase. Only if that passes does it run a seeded
   random-stimulus **power phase** (full-rate operands, 2000 vectors and
   seed 42 by default; see `../rtl_gen/SUMMARY.md`). autosim passes
   `+nw_clock_period_ps=<job clock>`, so the activity toggles at the
   frequency the power row reports. You can add more plusargs
   (`+nw_power_cycles`, `+nw_power_seed`) to
   `04_sim.sh <run_id> [plusargs...]`.

   Outputs: `sim.saif` (the toggle window covers exactly the power phase;
   this is the activity input for vectored power) and `sim.vcd` (a debug
   trace of the functional phase only; dumping stops when the power phase
   starts).

   Simulation settings: VCS runs with `+vcs+initreg+random`, so every
   sequential cell starts with a defined random value at time 0. If the
   functional check finds mismatches that have defined (non-X) values, it
   reports `PASS marginal_errors=N`, which is logged as a scoreboard
   warning, and the job continues. Unknown (X) outputs stop the job.
   <!-- Original sim policy note (2026-07/08): VCS runs with
   `+vcs+initreg+random` because power-up X otherwise sticks through the
   synthesized sync-reset datapath (X-pessimism) even though the netlist
   resets correctly from any definite state. The functional check tolerates
   definite-value mismatches: they are near-miss-timing artifacts of the
   sampled instant, and the power phase's random-stimulus toggle statistics
   do not depend on them. Unknown (X) outputs still abort, because they mean
   the sim itself is broken and the SAIF would be garbage. -->
6. **pwr** (`autopwr.py`, `05_pwr.tcl`): Runs PrimeTime PX on the PnR
   netlist with the PEX SPEF back-annotated. The sweep runs it once
   **unvectored** (vectorless activity, the project-wide 10 % convention)
   and once **vectored** for each stimulus mode. A vectored run reads that
   mode's `sim_<mode>.saif` from logic-sim, whose duration covers exactly
   the TB power phase. Kept file: `power.rpt`.

7. **collect** (`autocollect.py`): Parses the report files written by the
   stages above and adds one row per design point to
   `../datasets/logic_<rtl_name>.csv`. There is one CSV per component class,
   in the same way as `dataset_gen/sram/datasets/`. Rows are keyed by
   `flow_run_id`. Collecting a run id again replaces its row. No EDA tools
   are needed.

## Reports the collector reads

Each EDA stage writes its reports to fixed file names. This way the
collector parses report files instead of reading the mixed tool log.

| stage | file | supplies |
|---|---|---|
| syn | `synthesis.log` (`Report : qor` section) | total/comb/seq cell count and area, SCR/SAR, WNS/TNS |
| pnr | `qor.rpt` | post-route total/comb/seq cell count and area; timing over all path groups: WNS (worst group), TNS/violators (summed), `pnr_min_period_ns` plus `pnr_crit_group`/`pnr_crit_path_ns` (the group that sets it) |
| pnr | `utilization.rpt` | core area, utilization ratio |
| pnr | `clock_qor.rpt`, `clock_timing.rpt` | clock-tree insertion delay, skew, repeater count (we are preparing to add these to the CSV) <!-- not yet in the CSV --> |
| pex | `*.star_sum` | StarRC version |
| pwr | `power_summary.rpt` | internal/switching/leakage/total power and the split per power group |
| pwr | `power_hier.rpt` | power unit header (report values are scaled to mW), per-instance tree |
| pwr | `global_timing.rpt`, `constraint.rpt` | signoff WNS/TNS, all violators (we are preparing to add these to the CSV) <!-- not yet in the CSV --> |
| pwr | `switching_activity.rpt` | activity annotation coverage, which confirms that a vectored run used the SAIF (we are preparing to add this to the CSV) <!-- not yet in the CSV --> |

ICC2 has no `report_area` (unlike DC and PT), so post-route cell areas come
from `report_qor`, and the physical area comes from `report_utilization`.

ICC2's `report_qor` prints one block per path group. It lists the automatic
port-cone groups (`**in2reg_default**`, `**reg2out_default**`,
`**in2out_default**`) before the clock group. The collector (schema 3)
reads every group. `pnr_min_period_ns` is the maximum over all groups of
T − k·slack, where k is 2 for a clocked design's in2reg/in2out cones and 1
for the others. This value is the target for the logic timing models.
`recollect_timing.py [--write]` recomputes these columns for rows that were
already collected, using `../sweep_reports/*.reports.tar.gz`, without
running any tool again. It backs up each CSV as `*.bak_schema2_<stamp>`.
<!-- Original history: Collector schema ≤ 2 took the first block, so a
clocked design's `pnr_crit_path_ns` was the in2reg cone, mostly the SDC's
T/2 input delay. Schema 3 (2026-09-30) reads every group. -->

Every row records the tool versions that produced it (`dc_version`,
`icc2_version`, `starrc_version`, `pt_version`), plus
`power_activity_mode`, `stim_mode`, and `collector_schema`. Synopsys report
labels stay the same across releases. If one ever moves, the parser raises
an error instead of writing a blank cell, and the version columns show
which rows a format change would affect.

### Activity modes (`stim_mode`)

Vectored power is measured once for each **stimulus class** of the module
(`sweep_spec.POWER_MODES`; e.g. regfile: `random`/`read`/`write`/`idle`,
MACs: `random`/`hold_b`/`sparse50`/`idle`). During the SAIF-windowed power
phase, the TB picks its stimulus based on the `+nw_power_mode` plusarg. One
gate-level sim runs per mode (with a shared VCS compile) and writes
`sim_<mode>.saif`. One vectored PrimeTime run then reads each file. Rows
are keyed by `(flow_run_id, power_activity_mode, stim_mode)`, and
unvectored rows have `stim_mode=none`. The sweep runs every mode
automatically. See `activity_modes.md` for the full mode table and the
details. **Add new modes before a sweep.** Run directories are deleted
after collection, so a mode added later means re-running the whole EDA
chain for the affected jobs.

### How mode stimuli are generated, and when and how they are measured

The testbench produces the stimuli **during gate-level simulation**.
PrimeTime then computes power from the toggle statistics that the
simulation recorded. Nothing is measured per operation (the SRAM flow, by
contrast, uses per-operation `.measure` windows). Each mode gives the
**time-averaged power of one steady-state activity class**.

1. **Stimulus generation (in the TB, during sim).** Every generated TB runs
   two phases: a self-checking functional phase (the same for every mode),
   then the power phase. When the power phase starts, the TB seeds
   `$urandom` (42 by default, so runs are fully reproducible) and reads
   `+nw_power_mode`. On each falling clock edge (for combinational modules,
   each pacing period), `nw_drive_random()` drives one input vector. The
   mode only decides **which port groups get new random values and which
   are held**. For example, regfile `read` holds `w_en=0` and randomizes
   only the read addresses. `hold_b` latches one seeded constant onto the
   weight operand on the first cycle and randomizes the rest. `idle` holds
   every input while the clock keeps running. An unknown mode string calls
   `$fatal()`, so the TB can never quietly fall back to random stimulus.
2. **Toggle capture (also during sim).** The SAIF window covers exactly the
   power phase: `$toggle_start()` at the start and `$toggle_stop()` at the
   end. In between, VCS counts toggles and state times for **every net of
   the SDF-annotated post-PnR netlist**. One simulation runs per mode (the
   VCS compile is shared, and later modes re-run `./simv` directly), and
   its result is saved as `sim_<mode>.saif`. The functional phase runs the
   same way in every mode and is left out of the window.
3. **Power computation (after sim, in PrimeTime PX averaged mode).** For
   each mode, one PT run reads the netlist, the SPEF parasitics, the SDC,
   and that mode's SAIF. It converts the toggle counts over the window into
   per-net switching rates, and `update_power` reports internal, switching,
   and leakage power averaged over the phase. The collector converts the
   values to mW and computes `dyn_energy_pJ = dyn_power_mW × clock_period_ns`,
   which is the energy per cycle for that activity class. It writes one
   dataset row per `(flow_run_id, power_activity_mode, stim_mode)`.

Cost: the physical implementation (syn/pnr/pex) is built once per job. Each
added stimulus class costs only one more simv run and one more PT run.

Areas are in library units (um2). Power is converted to mW from whatever
unit the PrimeTime report uses. `dyn_energy_pJ` is
`dyn_power_mW * clock_period_ns`.

## Dataset sweep (probe, gen-jobs, rtl, sweep)

The full dataset run takes four commands. You can safely stop and re-run
each one, so they work well on a shared server (for example, inside tmux):

```bash
python3 run_batch.py probe -jobs-per-node 2    # overnight: T_min per config×node
python3 run_batch.py gen-jobs                  # seconds: writes the jobs manifest
python3 run_batch.py rtl                       # seconds: renders every RTL variant + TB
python3 run_batch.py sweep -jobs-per-node 2    # days: the storage-bounded sweep
```

1. **probe** synthesizes every `sweep_spec.py` configuration once per node
   at a 0.5 ns clock that no design can meet. The resulting critical path is
   close to the minimum period, T_min. Results are added to
   `probe_results.tsv`. On a re-run, ok rows are skipped and error rows are
   tried again. Each probe run directory is deleted right after parsing.
2. **gen-jobs** derives two clocks for each (config, node): tight
   (1.2×T_min) and relaxed (2×T_min), both rounded up to a 0.25 ns grid. It
   then writes the manifest and backs up the previous one to `jobs.prev`.
   These margins are only a starting point. Probe timing comes from
   synthesis alone, and the sweep adjusts any clock that PnR cannot meet
   (see below).
3. **sweep** runs each job through syn, pnr, pex, sim (one gate-level run
   per stimulus mode), unvectored pwr, and CSV, and then through vectored
   pwr and CSV for each mode. After that, it archives the report text files
   to `../sweep_reports/<run_id>.reports.tar.gz` and deletes the run
   directories. At any moment, the disk holds only the jobs in progress
   (nodes × `-jobs-per-node`), not the whole sweep (~350 GB unpruned).

   **Clock self-correction**: After PnR, a setup violation larger than the
   sim margin (any path group below −1.5× the 0.2 ns clock uncertainty)
   does not fail the job. Instead, the sweep derives a slower clock from the
   measured slack. Slack on in2reg, in2out, and reg2out paths counts double,
   because their SDC budget is T/2. The sweep rounds the clock up to the
   0.25 ns grid while avoiding the config's other clock, **saves the new
   clock in the manifest**, and re-runs syn and PnR at that clock. It does
   this up to two times. Only a job that still misses timing after that is
   recorded as a `pnr-timing` failure. The dataset row records the clock
   that actually ran.

   **Crash resume**: A job is skipped when its dataset CSV already has the
   unvectored row and one vectored row for each stimulus mode of its
   module. So re-running the same command picks up where it stopped. A
   failing job is recorded in `sweep_failures.tsv`, and the sweep moves on.
   Its report files are still archived, along with the netlist, SDF, and
   annotation log for debugging.

After a sweep pass, `run_batch.py rerun-failed` reads `sweep_failures.tsv`.
For each recorded `pnr-timing` failure, it updates the manifest clock based
on the slack stored in the failure message. It uses the same math as the
in-flight correction, so the next pass starts at the corrected clock. It
then renames the log to `sweep_failures.prev.tsv`. Failures from other
stages need no changes, because jobs without complete dataset rows run
again automatically.

### Adding a node later (incremental sweep)

All three stages take `-nodes` (comma-separated, e.g. `-nodes 3` or
`-nodes 20,16`), so you can bring up a newly characterized node without
re-running the finished ones. `-jobs-per-node` still applies within the
node:

```bash
python3 run_batch.py probe -nodes 3 -jobs-per-node 4   # probe the new node only
python3 run_batch.py gen-jobs -nodes 3                 # manifest = that node's rows only
python3 run_batch.py sweep -nodes 3 -jobs-per-node 4   # sweep those rows
```

- The node must already be in the technology catalog. If it isn't, probe
  and gen-jobs stop right away with "no TT/25C corners in the catalog".
- `gen-jobs -nodes ...` writes a manifest that holds **only** those nodes
  (the previous manifest is backed up to `jobs.prev` as usual). To add the
  node for good, also add it to `SWEEP_NODES` in `sweep_spec.py` so that
  future unfiltered runs include it.
- With a single node, that node gets the whole license and core budget, so
  `-jobs-per-node` can be higher than in the full run (the total number of
  tool runs at once is nodes × jobs-per-node).
- Finished nodes are safe even without the filter. Probe skips ok rows of
  `probe_results.tsv`, and sweep skips jobs whose CSV already has both
  activity-mode rows. `-nodes` just avoids scanning them at all and keeps
  the manifest limited to the selected nodes.

To look at a collected row again, start from its report archive. To
reproduce it fully, run the stage scripts directly
(`TECH_<NN>nm/run_scripts/<stage>.sh <run_id>`).

### Adding a module later (incremental sweep)

A new primitive needs code in three places. After that, you use the normal
workflow commands. You don't need to edit the job list by hand or re-run
finished modules.

1. **Generator and templates** (`rtl_gen/`): a `gen_<name>()` entry point
   and the `<name>.sv.j2` / `<name>_tb.sv.j2` templates. The TB must follow
   the shared power-stimulus contract (`_power_stim.sv.j2`): the functional
   self-check runs first, and then `nw_drive_random()` drives the power
   phase.
2. **Sweep spec** (`sweep_spec.py`): the module's configuration list in
   `sweep_configs()`, membership in `CLOCKED_MODULES` if it has
   `i_clk`/`i_rst_n`, and, if its ports support distinct operations, its
   stimulus classes in `POWER_MODES`. Add the modes **before** the sweep.
   Run directories are deleted after collection, so a mode added later
   means re-running the whole EDA chain for the affected jobs. Add the mode
   handling to the TB template in the same change. A TB that does not
   handle a mode calls `$fatal()` for any non-random mode, so it never
   quietly measures random activity instead.
3. **Run as usual**: `probe`, `gen-jobs`, `rtl`, `sweep`. The resume keys
   make the addition incremental with no extra work. Probe skips every
   (config, node) that is already `ok` in `probe_results.tsv`, so only the
   new module's configurations run. Sweep skips jobs whose dataset rows are
   complete, so only the new module's manifest rows run. The regenerated
   manifest covers both old and new modules, and the old rows are simply
   skipped.

The collector needs no changes. Architectural parameters become columns
automatically (`parse_arch_params`), and each module gets its own
`datasets/logic_<name>.csv`, so new parameter sets never affect existing
files.

## Scoreboard

Every stage adds structured events (timestamp, stage, status
`start|running|skip|done|error|terminated`, run id, details) to
`scoreboard.jsonl`. `run_batch.py scoreboard` prints status counts for each
stage. The raw JSONL is the record of which run directories are current. A
failing job logs an `error` event, and the sweep continues with the other
jobs.
