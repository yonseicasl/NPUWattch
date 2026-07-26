# Power-phase activity modes (stimulus classes)

Since 2026-07-17 every vectored power row carries a **stimulus class** in the
dataset's `stim_mode` column. A mode selects what the testbench drives during
the SAIF-windowed power phase; the physical implementation (syn/pnr/pex) is
shared, so each extra mode costs one gate-level sim re-run (shared VCS
compile) plus one vectored PrimeTime run.

Rows:
- `power_activity_mode=unvectored`, `stim_mode=none` — vectorless 10%-style
  estimate, stimulus-independent.
- `power_activity_mode=vectored`, `stim_mode=<mode>` — averaged power over
  the power phase driven with that stimulus class.

The mode axis spans activity levels the runtime model interpolates over:
`idle` (0% input activity, clock running) ↔ realistic dataflow classes
(`hold_b`, `stream`, `fixed_route`, `sparse50`, ...) ↔ `random` (100%
uniform-random inputs, the legacy stimulus and upper anchor).

## Mode table (single source: `sweep_spec.POWER_MODES`)

| module | modes | stimulus |
|---|---|---|
| regfile | random, read, write, idle | read: `w_en=0`, read addrs random; write: `w_en` all-1, write addr/data random, read addrs held; idle: all inputs held |
| fifo | random, stream, idle | stream: `push=pop=1` steady flow-through; idle: no push/pop |
| intmac | random, hold_b, sparse50, idle | hold_b: weight-stationary (b latched once, seeded); sparse50: a zeroed w.p. 0.5 |
| fpmac | random, hold_b, sparse50, idle | as intmac, addend c random in every non-idle mode |
| mxfpmac | random, hold_scale, sparse50, idle | hold_scale: per-block scales latched once (constant inside a real MX tile); sparse50: per-element zeroing of a |
| fpsfu | random, exp, trig, hyp, erf, idle | per-op-group stimulus: op restricted to that group (exp/exp2, sin/cos, tanh/sigmoid, erf), operand random — only that group's table + the shared PWL datapath toggle; random draws ops across every ENABLED group. **Group modes apply only to variants that enable the group** — `power_modes(rtl_name, arch_params)` filters by the job's `sfu_op_*` flags (the TB $fatal()s otherwise) |
| simplemux | random, valid25 | valid25: each source valid w.p. 0.25; invalid sources hold data |
| crossbar | random, fixed_route, valid25 | fixed_route: `dest = src % NUM_OUTPUTS` constant, data random |
| fattree | random, fixed_route | fixed_route: rotation `dest = (src+1) % NUM_NODES` |
| foldedclos | random, fixed_route | as fattree |
| intadd, intmul, fpadd, fpmul | random | pure dataflow arithmetic — random *is* the operation; data-statistics modes (sparse/correlated) are future work |

Deferred candidates (add to `POWER_MODES` + the module's TB template
together): regfile `write_same`, fifo `burst`, MAC `sparse90`/`hold_c`,
fpadd `aligned`, NoC `hotspot`/`local`/`bisection`, arithmetic `sparse50`.

## Mechanics

- TB: `+nw_power_mode=<mode>` plusarg (default `random`), parsed in the
  shared `_power_stim.sv.j2` macros; each mode-aware module dispatches inside
  its `nw_drive_random()` task and **$fatal()s on an unknown mode** so a typo
  can never silently measure random activity. Hold-style modes latch their
  seeded constant on the first power-phase cycle (`nw_mode_init`).
- autosim: per job, the first mode runs through `04_sim.sh` (VCS compile +
  sim + output checks); remaining modes re-run the compiled `./simv` directly
  with the same checks replicated in python. After each run,
  `sim.saif`/`sim.log` are stashed as `sim_<mode>.saif`/`sim_<mode>.log`.
  The functional (self-checking) phase re-runs identically in every mode.
- autopwr: `run_power_job(..., vectored=True, stim_mode=m)` reads
  `sim_<m>.saif` and stamps `set stim_mode "<m>"` into the prepared
  `05_pwr.tcl` (provenance; "none" for unvectored).
- autocollect: parses `stim_mode` back from `05_pwr.tcl`; dataset rows are
  upserted on `(flow_run_id, power_activity_mode, stim_mode)`.
- sweep (autosweeprun): the per-job chain runs sim once (all modes) then one
  `pwr → collect → archive` pass per mode; a job is skipped only when the
  dataset already has `("unvectored","none")` plus `("vectored", m)` for
  every mode of its module. **Add new modes to POWER_MODES before a sweep**:
  run dirs are pruned after collection, so a mode added afterwards re-runs
  the whole EDA chain for the affected jobs.
- Stage-wise use: `run_batch.py sim` produces every mode's SAIF;
  `run_batch.py pwr -vectored -stim-mode read` runs one class (collect right
  after, before the next class overwrites the 05_pwr run dir).

## QA identity

For regfile-class modules, `P(read) + P(write) − P(idle) ≈ P(random)` up to
the write-rate difference (random drives ~50% write-enable rate, write mode
100%). Large violations indicate a stimulus bug — check before training.
