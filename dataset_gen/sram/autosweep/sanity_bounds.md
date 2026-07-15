# SRAM flow sanity bounds — ENFORCED 2026-07-15

Status: sections A and B are implemented in `dec_measures.py` /
`array_measures.py` (FAIL bounds append to `problems` and set the
measures.csv `verdict` to FAIL — all measured values are still kept, and
`collect_*` skips the run; WARN bounds only print). Section C is
implemented in `qa_sheets.py`, which `run_batch.py` runs after every
collect (warnings only, rows stay in the sheets). The leakage ceilings
D2/A2 are relaxed 30x when the mt0 `temper` exceeds 50 C (hot leakage is
~10-30x nominal); they need `--rows`/`--cols`, which
`run_array.sh`/`run_decoder.sh` now pass. Constants below are calibrated
against the 2026-07-13/14 runs (healthy vs known-broken 5nm bring-up
builds); retune here and in the scripts together.

Motivation (verified 2026-07-15): the existing functional checks catch
dead wordlines and out-of-range delays, but two classes of broken runs
pass them —
- a resistive short from a merged net that does not break decode
  function: 5nm dec_8x4 run `20260714_015203` has leakage 132.8 uW
  (~8300x the healthy 0.016 uW) and 4.6x flip energy, yet PASSes;
- a single-window energy anomaly: 5nm dec_16x4 run `20260714_114949` has
  e_act_same = 0.6187 pJ (38x normal) with every checked value normal.
And the released array sheet carries one physically impossible value:
7nm 2x2 `leak_power_mW = -4.982e-06` (integrator noise at pW scale) —
nothing checks leakage sign today.

Notation: R = rows, C = cols. "FAIL" = run-level verdict;
"WARN" = collect/QA-level flag only (row still enters the sheet, listed
in the QA report).

## A. Per-run bounds — dec_measures.py (decoder TB)

| # | bound | level | rationale / calibration |
|---|---|---|---|
| D1 | `p_leak_w > 0` | FAIL | negative leakage is integrator noise; re-run or investigate |
| D2 | `p_leak_w < 10 nW x R` | FAIL | healthy: 1-2 nW/row (0.016 uW @8 rows ... 0.58 uW @512 rows); shorted builds: 42-226 uW — 2-4 orders above the bound |
| D3 | `e_act_same_j < e_act_flip_j` | FAIL | flip adds addr-register + decode-tree toggling on top of the same-address path; healthy flip/same = 1.5-2.1x; the 114949 anomaly (same=0.6187 > flip=0.0221) violates this |
| D4 | `abs(e_act_same_j - e_act_same2_j) <= 0.25 x max(...)` | FAIL | two nominally identical ops; healthy mismatch <= 8%; the same-window anomaly gives ~40x mismatch |
| D5 | `abs(e_act_flip_j - e_act_back_j) <= 0.25 x max(...)` | FAIL | mirror-image address flips; healthy mismatch <= 14% (512x4: 0.475 vs 0.407) |
| D6 | `e_idle_clk_j < e_act_same_j` | FAIL | idle op has no wlen/WL activity; healthy idle/same = 0.3-0.5; shorted builds show idle >> same (1.33 vs 0.018 pJ) |
| D7 | `e_idle_clk_j > p_leak_w x 10 ns` | WARN | the idle window contains at least its own leakage; violation means the leakage window and op windows disagree |
| D8 | `abs(t_clk_wl - 2 ns - t_wlen_wl) < 0.3 ns` | WARN | clk->WL = 2 ns wlen gate + driver path when decode fits in 2 ns; larger gap flags a decode path slower than the gate (legit at very large R, hence WARN) — healthy data matches to <0.1 ns |

## B. Per-run bounds — array_measures.py (array TB)

| # | bound | level | rationale / calibration |
|---|---|---|---|
| A1 | `p_leak_w > 0` | FAIL | catches the existing 7nm -4.98e-06 mW row class; near-zero leakage at small arrays may need a longer AVG window or tighter tolerances rather than acceptance |
| A2 | `p_leak_w < 10 nW x (R x C / 4 + 1)` | FAIL | healthy 2x2 arrays: 6.5-7.6 nW total; scales with bitcell count + fixed periphery; a merged-net short sits orders above |
| A3 | `e_wr_toggle_j >= 0.9 x e_wr_same_j` (when n_toggle > 0) | FAIL | toggle write = same write + real flips; equality only as toggle_rate -> 0 |
| A4 | `e_rd_1to0_j >= e_rd_1to1_j` | FAIL | reading 0 discharges the full BL (precharge 1->0), reading 1 only BL_bar; healthy ratio 1.6-2.1x |
| A5 | all six op energies `> 0` | FAIL | currently only printed, not checked (decoder already checks this) |
| A6 | `t_wr_cell > 0` and `t_wr_bl > 0` individually | FAIL | already implied by the 0 < t < 10 ns range check — keep explicit if the range check is ever widened |
| A7 | `t_rd_sense > -4 ns` | WARN | sen_en fires 3 ns after wl; more negative than the wl->sen gap means the trigger matched the wrong edge |
| A8 | if `t_rd_sense > 0`: flag `rd_delay_ns` as schedule-limited | WARN | t_rd_wl_out is then bounded by the fixed sen_en at wl+3 ns, not by the array — the dataset consumer must know the delay is a TB-schedule artifact |

## C. Cross-run / sheet-level QA (collect or datasets/qa/, all WARN)

| # | check | rationale |
|---|---|---|
| Q1 | toggle-rate linearity: for a fixed config, `wr_toggle_energy_pJ` monotonic in `n_toggle_cols` and within the [wr_same, full-flip] envelope | the documented energy model is linear interpolation between those endpoints |
| Q2 | node monotonicity at fixed config: energies and delays non-increasing from 20nm -> 5nm (or flagged) | current sheet obeys this; a violation usually means a stale build or util change, not physics |
| Q3 | temperature: `leak_power_mW(85C) > leak_power_mW(25C)` for the same config | physical; 10nm data shows 12x |
| Q4 | same-config run-to-run spread <= 20% across PnR builds (decoder) | two builds of 5nm dec_16x4 differ ~17% (util retune); larger spread flags a mixed/broken build population |
| Q5 | `dec_util` achieved within 2x of `util_target` | routing-failure builds typically show collapsed utilization |

## Known accepted quirks (do NOT bound)

- Decoder addr inputs flip 1 ns before the clk edge (setup), so the
  addr input-buffer energy lands in the PRECEDING same-address window:
  dec_act_energy is overstated / dec_flip_energy understated by
  ~0.007 pJ (16x4) to ~0.010 pJ (512x4). Systematic, small, and a
  consequence of the registered-decoder stimulus — documented here
  instead of bounded.
- Array op energies include their 10 ns window's leakage by design;
  downstream subtracts P_leak x 10 ns for pure dynamic energy.
- Array leakage is measured in the all-zeros stored state only;
  state-dependent leakage spread is not captured.
