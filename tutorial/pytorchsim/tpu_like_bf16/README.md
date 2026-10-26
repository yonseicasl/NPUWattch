# Design — tpu_like_bf16: the same TPUv3-like NPU set up like the TPU, with bf16 PEs

This folder is the second hardware model of the PyTorchSim examples. The
machine is the one of `../tpu_like_fp32` (one core with two 128×128 systolic
arrays, 128 VPU lanes with 16 MB of scratchpad memory, 16 HBM2 channels, and
a BookSim `fly` NoC at 940 MHz) with the PE written to the TPU's own spec: a
bf16 multiply with an fp32 accumulate. PyTorchSim runs fp32 by default; for
the 7 nm TPU comparison the workload below was run in bf16 (bf16 tensors,
bf16 kernel), so the cycles and the DRAM traffic are bf16 as well.

```
tpu_like_bf16/
├── compound_components.yaml   the hardware model; only systolic_mac differs from ../tpu_like_fp32
├── projection.yaml            PyTorchSim actions -> activity; only the systolic_mac actions differ
├── user_components.yaml       cost of custom blocks (the same example entry)
└── matmul_1024/               one 1024³ bf16 matmul (the only workload)
```

```bash
cd matmul_1024 && ./run
```

## The PE

A TPU MXU multiplies in bf16 and accumulates in fp32. The PE is a compound
of three NPUWattch primitives written to that spec, with a fixed configuration (the
fp32 design selects its PE primitive from the kernel's data type instead):

| Element | Primitive | Configuration | Charged for |
| --- | --- | --- | --- |
| `pe` | `fpmul` | 8-bit exponent, 7-bit mantissa, 2 pipeline stages | one bf16 product per useful MAC (`random`: `fpmul` has no held-operand mode) |
| `acc` | `fpadd` | 8-bit exponent, 23-bit mantissa, 2 pipeline stages | one fp32 add per useful MAC (`random`) |
| `acc_reg` | `regfile` | 32 bits × 1 word | one write per useful MAC |
| `w_reg` | `regfile` | the operand width (16 bits for bf16) × 1 word | one write per weight load; idle (leakage only) in the other cycles |

`default_mode: gated` in the compound: an action charges only the elements it
names, and the others are clock-gated. The active PE cycles that hold no
real weight (`array_idle_slots`) charge `w_reg` in the idle mode and nothing
else.

The multiplier is the element named `pe`. The report counts one MAC per
non-idle event of an `fpmac`, `intmac`, or `mxfpmac` component, and also per
event of an `fpmul` or `intmul` component named `pe` or `mac`. So the pJ/FLOP
figure and the MAC utilization of this design count the multiplier events
once. The adder and the register are not counted again.

## Result: the 1024³ matmul at 7 nm, next to the fp32 design

| | `tpu_like_fp32` | `tpu_like_bf16` |
| --- | --- | --- |
| PyTorchSim run | fp32 tensors, 52 022 cycles | bf16 tensors, 45 195 cycles |
| DRAM requests (32 B each) | 262 144 reads, 131 072 writes | 131 072 reads, 65 536 writes |
| Total energy | 5.98 mJ | 3.02 mJ |
| pJ / FLOP (DRAM included) | 2.78 | 1.41 |
| PE energy per useful MAC | 5.05 pJ (one `fpmac`) | 2.56 pJ (0.89 multiply + 1.61 add + 0.06 register) |
| Two arrays / DRAM | 91% / 8% | 91% / 8% |
| MAC utilization | 63% | 72% |
| Average power | 108 W | 63 W |
| Modeled area | 53.2 mm² | 44.9 mm² |

## Next to a published TPU

TPUv4i is a 7 nm chip with four 128×128 MXUs at 1050 MHz. Its TDP of 175 W
over its peak of 138 TFLOP/s is 1.27 pJ/FLOP (Jouppi et al., "Ten Lessons
From Three Generations Shaped Google's TPUv4i", ISCA 2021, Table 1; the chip
TDP does not include the memory system). This design, on the 1024³ matmul
at 7 nm, is at 1.30 pJ/FLOP on chip and 1.41 with DRAM. The on-chip figure
is the closer pair, since it covers about the same blocks. The model lands
within 10% of the published figure.

## Notes on the run

- PyTorchSim ran the kernel in timing mode (`pytorchsim_functional_mode: 0`);
  the image's functional model computes in float only. The cycle counts, the
  DRAM traffic, and the instruction counts are the simulator's.
- `fpmul` is characterized in the `random` mode, so the multiplier (16% of
  the energy) is priced for random operands; the fp32 `fpmac` uses `hold_b`.
- The toolchain of the public PyTorchSim image needed three small patches
  outside the simulator to compile a bf16 kernel. `matmul_1024/how_the_data_was_made/`
  has the patches and the run manifest.
