# NW Logic Summary

## Goal

This subtree supports logic dataset construction for NPUWattch.

The intended flow is:

`generator input -> RTL emission -> implementation flow -> characterized PAT sample`

## Current RTL Generator Status

The `rtl_gen/` flow now targets arithmetic units and NoC fabrics:

| Unit | Generated RTL | Generated TB | Sweep parameters |
| --- | --- | --- | --- |
| `intadd` | `rtl_gen/rtl/intadd/intadd.sv` | `rtl_gen/rtl/intadd/intadd_tb.sv` | `a_width`, `b_width`, `out_width`, `pipeline_stages` |
| `intmul` | `rtl_gen/rtl/intmul/intmul.sv` | `rtl_gen/rtl/intmul/intmul_tb.sv` | `a_width`, `b_width`, `out_width`, `pipeline_stages` |
| `intmac` | `rtl_gen/rtl/intmac/intmac.sv` | `rtl_gen/rtl/intmac/intmac_tb.sv` | `a_width`, `b_width`, `out_width`, `acc_width`, `pipeline_stages` |
| `regfile` | `rtl_gen/rtl/regfile/regfile.sv` | `rtl_gen/rtl/regfile/regfile_tb.sv` | `width`, `depth`, `num_read_ports`, `num_write_ports` |
| `fifo` | `rtl_gen/rtl/fifo/fifo.sv` | `rtl_gen/rtl/fifo/fifo_tb.sv` | `width`, `depth` |
| `fpadd` | `rtl_gen/rtl/fpadd/fpadd.sv` | `rtl_gen/rtl/fpadd/fpadd_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `fpmul` | `rtl_gen/rtl/fpmul/fpmul.sv` | `rtl_gen/rtl/fpmul/fpmul_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `fpmac` | `rtl_gen/rtl/fpmac/fpmac.sv` | `rtl_gen/rtl/fpmac/fpmac_tb.sv` | `exp_bits`, `mantissa_bits`, `pipeline_stages` |
| `mxfpmac` | `rtl_gen/rtl/mxfpmac/mxfpmac.sv` | `rtl_gen/rtl/mxfpmac/mxfpmac_tb.sv` | `block_elems`, `num_blocks`, `input_format`, `scale_exp_bits`, `acc_format` |
| `simplemux` | `rtl_gen/rtl/simplemux/simplemux.sv` | `rtl_gen/rtl/simplemux/simplemux_tb.sv` | `data_width`, `num_inputs` |
| `crossbar` | `rtl_gen/rtl/crossbar/crossbar.sv` | `rtl_gen/rtl/crossbar/crossbar_tb.sv` | `data_width`, `num_inputs`, `num_outputs` |
| `fattree` | `rtl_gen/rtl/fattree/fattree.sv` | `rtl_gen/rtl/fattree/fattree_tb.sv` | `data_width`, `radix`, `num_levels`, `oversubscription` |
| `foldedclos` | `rtl_gen/rtl/foldedclos/foldedclos.sv` | `rtl_gen/rtl/foldedclos/foldedclos_tb.sv` | `data_width`, `terminals_per_leaf`, `num_leaves`, `num_spines`, `switch_radix`, `oversubscription` |

## Parameter Notes

- Arithmetic widths use `a_width`, `b_width`, `out_width`, and `acc_width`; RTL emits the corresponding uppercase parameters.
- Storage units use `width`, `depth`, and regfile port-count parameters.
- Floating-point widths use `exp_bits` and `mantissa_bits`.
- MX dot-product units use `block_elems`, `num_blocks`, `input_format`, shared-scale fields, and accumulator format fields.
- NoC fabrics use `data_width` for link payload width and topology-specific counts for ports, leaves, spines, radix, and levels.
- NoC `oversubscription` is a normalized uplink/downlink ratio in `(0, 1]`.
- `pipeline_stages` applies to arithmetic units and is valid from 2 to 5.
- Detailed parameter descriptions live in `rtl_gen/SUMMARY.md`.

## Testbench Intent

- Use real, finite, meaningful values.
- Use meaningful signed integer values for integer units.
- Use random storage traffic, including repeated-address overwrites for regfiles.
- Use finite MX/BF16 values for `mxfpmac`.
- Use random idle-to-saturated scenarios for NoC units.
- Print case-by-case input/output comparisons in the simulator console.
- Compare DUT results against Python-generated golden vectors.
- Stay compatible with Verilator-oriented flows.

## Constraints

- Integer widths are configurable per input and output.
- Integer MAC accumulator width is configurable.
- Regfile width, depth, and read/write port counts are configurable.
- FIFO width and depth are configurable.
- Floating-point widths are configurable through exponent and mantissa fields.
- `mxfpmac` supports finite MXFP, MXINT8, BF16, and custom finite formats.
- NoC modules expose only node-facing ports.
- Pipeline depth is configurable from 2 to 5.
- Generated RTL is meant for characterization, not final production IP.
