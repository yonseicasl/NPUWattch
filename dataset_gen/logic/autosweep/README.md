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
| `clock_port` | no (default `i_clk`) | clock port name for `create_clock` |
| `reset_port` | no | when set, a `set_false_path -from` is added on it |
| `reset_active` | no | reset polarity, consumed by the generated TB |

Each row gets a deterministic run id
`<rtl>_<arch tokens>_<NN>nm_<process>_<voltage>_<temp>C_<freq>MHz`
(e.g. `intmac_32_32_64_64_3_20nm_TT_0V9_25C_200MHz`) that names every
stage's run directory.

## Usage

```bash
python3.11 run_batch.py                 # all stages, whole manifest
python3.11 run_batch.py syn             # one stage: rtl|syn|pnr|pex|sim|pwr
python3.11 run_batch.py -verbose pnr    # stream tool output while logging
python3.11 run_batch.py -vectored pwr   # power from gate-sim activity
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
in parallel** (one worker per node); jobs within a node run sequentially.

1. **rtl-gen** (`autortl.py`) — deduplicates the manifest by
   `(rtl_name, arch_params)` and calls the `gen_<rtl_name>` generator from
   `../rtl_gen/`, emitting `rtl_gen/rtl/<name>/<name>.sv` + self-checking
   `<name>_tb.sv`. No EDA tools needed.
2. **syn** (`autosynth.py`, `01_syn.tcl`) — injects `create_clock`
   (+ 0.2 ns uncertainty, reset false path) into the master script.
   Keepers: `<rtl>_syn.v`, `<rtl>.sdc`, `synthesis.log` (the QoR/area
   reports feed `comb/seq_cells`, `comb/seq_area` → SCR/SAR).
3. **pnr** (`autopnr.py`, `02_pnr.tcl`) — ICC2 place & route of the
   synthesized netlist. Keeper: `<rtl>_icc2.v` (+ layout artifacts and the
   post-layout area report in the run dir).
4. **pex** (`autopex.py`, `03_pex.strc`) — StarRC extraction on the PnR
   result. Keeper: `<rtl>.spef`.
5. **logic-sim** (`autosim.py`) — gate-level simulation of the PnR netlist
   against the generated TB; builds a `04_sim.f` filelist (point
   `STD_CELL_MODELS_F`/`STD_CELL_MODELS` at the cell models when invoking
   `04_sim.sh`). Produces `sim.vcd` (or `sim.saif`) — the activity input
   for vectored power. Optional for the default dataset flow.
6. **pwr** (`autopwr.py`, `05_pwr.tcl`) — PrimeTime PX on the PnR netlist
   with the PEX SPEF back-annotated. Default is **unvectored** (vectorless
   activity, the project-wide 10 % convention); `-vectored` instead points
   it at the logic-sim `sim.saif`/`sim.vcd`. Keeper: `power.rpt`.

Data collection into `datasets/logic.csv` is not wired into `run_batch.py`
yet (the `data-collection` stage id is reserved in `autocommon.py`); the
report extractors consume the run directories above.

## Scoreboard

Every stage appends structured events (timestamp, stage, status
`start|running|skip|done|error|terminated`, run id, details) to
`scoreboard.jsonl`. `run_batch.py scoreboard` prints per-stage status
counts; the raw JSONL is the audit trail for which run directories are
current. A failing job logs an `error` event and the sweep continues with
the remaining jobs.
