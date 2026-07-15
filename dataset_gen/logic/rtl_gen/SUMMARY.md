# RTL Generator Summary

## Objective

`rtl_gen/` owns the Python + Jinja2 flow that emits sweepable SystemVerilog RTL into `rtl_gen/rtl/` for characterization.

Flow:

`architectural parameters -> generated RTL/TB -> synthesis/PnR -> post-layout PAT data`

## Current Scope

Implemented generator targets:

| Model | Generator | Outputs | Main parameters |
| --- | --- | --- | --- |
| `intadd` | `gen_intadd` | `intadd.sv`, `intadd_tb.sv` | `a_width`, `b_width`, `out_width`, `pipeline_stages` |
| `intmul` | `gen_intmul` | `intmul.sv`, `intmul_tb.sv` | `a_width`, `b_width`, `out_width`, `pipeline_stages` |
| `intmac` | `gen_intmac` | `intmac.sv`, `intmac_tb.sv` | `a_width`, `b_width`, `out_width`, `acc_width`, `pipeline_stages` |
| `regfile` | `gen_regfile` | `regfile.sv`, `regfile_tb.sv` | `width`, `depth`, `num_read_ports`, `num_write_ports` |
| `fifo` | `gen_fifo` | `fifo.sv`, `fifo_tb.sv` | `width`, `depth` |
| `fpadd` | `gen_fpadd` | `fpadd.sv`, `fpadd_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `fpmul` | `gen_fpmul` | `fpmul.sv`, `fpmul_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `fpmac` | `gen_fpmac` | `fpmac.sv`, `fpmac_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `mxfpmac` | `gen_mxfpmac` | `mxfpmac.sv`, `mxfpmac_tb.sv` | `block_elems`, `num_blocks`, `input_format`, `scale_exp_bits`, `acc_format` |
| `simplemux` | `gen_simplemux` | `simplemux.sv`, `simplemux_tb.sv` | `data_width`, `num_inputs` |
| `crossbar` | `gen_crossbar` | `crossbar.sv`, `crossbar_tb.sv` | `data_width`, `num_inputs`, `num_outputs` |
| `fattree` | `gen_fattree` | `fattree.sv`, `fattree_tb.sv` | `data_width`, `radix`, `num_levels`, `oversubscription` |
| `foldedclos` | `gen_foldedclos` | `foldedclos.sv`, `foldedclos_tb.sv` | `data_width`, `terminals_per_leaf`, `num_leaves`, `num_spines`, `switch_radix`, `oversubscription` |

## Parameter Reference

Parameter names use Python `snake_case`; generated RTL uses conventional uppercase names.

Common arithmetic parameters:
- `a_width`: bit width of input operand A.
- `b_width`: bit width of input operand B.
- `out_width`: bit width of the visible result.
- `acc_width`: internal accumulator width for MAC units.
- `pipeline_stages`: registered pipeline depth. Valid range is 2 to 5.

Storage parameters:
- `width`: data bit width.
- `depth`: number of entries. It does not need to be a power of two.
- `num_read_ports`: dedicated read-port count.
- `num_write_ports`: dedicated write-port count.

Floating-point parameters:
- `exp_bits`: IEEE-like exponent field width.
- `mantissa_bits`: fraction field width, excluding the implicit leading bit.
- `pipeline_stages`: registered pipeline depth. Valid range is 2 to 5.

MX dot-product parameters:
- `block_elems`: elements per MX block. Default is 32.
- `num_blocks`: K-dimension block count. `1` skips the inter-block accumulator.
- `input_format`: `mxfp8_e5m2`, `mxfp8_e4m3`, `mxfp6_e3m2`, `mxfp6_e2m3`, `mxfp4_e2m1`, `mxint8`, `bf16`, or `custom`.
- `scale_exp_bits`: shared scale exponent width. Default is 8 for E8M0-like scales.
- `scale_bias`: shared scale exponent bias. Default is midpoint bias.
- `acc_format`: `fp32`, `fp64`, or `custom`. RTL uses a signed fixed-point surrogate of the selected width.
- `decode_width`: internal decoded element width.
- `decode_frac_bits`: fixed-point fractional bits after decode.

NoC common parameters:
- `data_width`: payload width of each node-facing link.
- `num_inputs`: number of source ports.
- `num_outputs`: number of sink ports.
- `oversubscription`: normalized uplink/downlink capacity ratio in `(0, 1]`. `1.0` is full bandwidth.

Fat-tree parameters:
- `radix`: number of child/down ports per switch.
- `num_levels`: number of tree levels from leaves toward the root.
- `oversubscription`: scales effective up-ports as `ceil(radix * oversubscription)`.

Folded-Clos parameters:
- `terminals_per_leaf`: number of node-facing downlinks per leaf switch.
- `num_leaves`: number of leaf switches.
- `num_spines`: number of spine switches.
- `switch_radix`: total leaf switch port budget. Must cover downlinks plus uplinks.
- `oversubscription`: scales active spine uplinks as `ceil(terminals_per_leaf * oversubscription)`.

RTL ratio encoding:
- `oversubscription` is accepted as a Python float.
- Generated RTL emits `OVERSUBSCRIPTION_NUM` and `OVERSUBSCRIPTION_DEN`.

## Testbench structure

Every generated TB has two phases (shared blocks in
`templates/_power_stim.sv.j2`):

1. **Functional phase** — the self-checking directed vectors (golden values
   from the Python models). On any mismatch the TB prints `FAIL` and
   `$fatal`s; the power phase never runs for a broken design.
2. **Power phase** — full-rate uniform-random stimulus (one vector per
   clock/pacing period, protocol-legal per module: bounded mux selects,
   guarded FIFO push/pop, written-address regfile reads, all-valid NoC
   injection). Marked by `nw_power_phase` and by
   `power phase start/end` log lines.

Under `+define+NW_LOGIC_GATE_SIM` (set by the autosweep gate-sim filelist)
the TB also opens a VCS toggle window over exactly the power phase and writes
`sim.saif` — the activity input for vectored PrimeTime power. The SAIF
duration therefore covers only defined, reproducible random activity, never
the reset or the directed vectors. Note VCS toggle monitoring covers wires,
so an RTL sim of a logic-only module yields a header-only SAIF; gate-level
netlists (all wires) always populate it.

Runtime plusargs (all optional): `+nw_clock_period_ps` (TB clock / pacing
period, default 10000; the autosweep sim stage passes the job's clock),
`+nw_power_cycles` (default 2000, baked in from
`generator.DEFAULT_POWER_CYCLES`), `+nw_power_seed` (default 42).

## Rules

- Use Python and Jinja2-style templates for generation.
- Emit generated files under `dataset_gen/NW_logic/rtl_gen/rtl/<unit>/`.
- Keep RTL synthesizable and structurally representative.
- Support signed integer width sweeps directly.
- Support exponent/mantissa sweeps directly.
- Support node-facing NoC topology sweeps directly.
- Support pipeline depths from 2 to 5.

## Notes

- `pipeline_stages=2` means input and output latches only.
- Testbenches target Verilator-style console checking.
- Test vectors use meaningful finite values, not unconstrained NaN-heavy random data.
- Integer test vectors use signed values with wrap-to-width golden results.
- Golden vectors are produced by the Python floating-point helper in `float_model.py`.
- Golden integer vectors are produced by `int_model.py`.
- Storage vectors are produced by `storage_model.py`.
- MX dot-product vectors are produced by `mxfp_model.py`.
- NoC testbenches sweep idle, sparse, mixed, and saturated traffic.
- `mxfpmac` models finite values and does not implement full IEEE exception semantics.

## Next Useful Extensions

1. Add a CLI or batch sweep driver.
2. Add config-file based generation.
3. Add more integer and memory primitives.
4. Add simulator scripts for Verilator automation.
