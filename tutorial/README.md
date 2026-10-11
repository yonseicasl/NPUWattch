# NPUWattch Tutorial

This folder has ready-to-run examples for two simulators. The examples use
activity counts from real simulator runs. You don't need any EDA tools, PDKs,
or GPUs. All you need is NPUWattch.

```
tutorial/
├── npuwattch_basic/   Start here — what NPUWattch is, how it is built, what it reads
├── hands_on/          Jupyter notebooks that run the examples below, step by step
├── timeloop/      Example 1 — Timeloop / Accelergy input
│   ├── eyeriss_like/alexnet/      AlexNet, 8 layers (the basic example)
│   ├── gemmini_like/{resnet50,llama3_8b}/
│   └── nvdla_like/{resnet50,llama3_8b}/
└── pytorchsim/    Example 2 — PyTorchSim input
    ├── tpu_like_fp32/             the hardware model (three definition files)
    │   ├── matmul_1024/           one 1024³ matmul (the basic example)
    │   ├── matmul_train/, matmul_2048_{1,2}core/, softmax/, resnet50/
    │   └── llama3_8b/, gemma2_9b/, deepseek_v2_lite/   one decoder block each, prefill + decode
    └── tpu_like_bf16/             the same model, PEs fixed to bf16 MACs
        └── matmul_1024/           the matmul again, priced with bf16 PEs
```

`npuwattch_basic/` is a four-part introduction (motivation, method, the
structure of a run and the files each harness reads, and how to bring your
own data). `hands_on/` has the same exercises as Jupyter notebooks, with
their output already in place.

To run an example:

```bash
cd tutorial/timeloop/eyeriss_like/alexnet && ./run
cd tutorial/pytorchsim/tpu_like_fp32/matmul_1024 && ./run
```

Each script writes `out/report.html` (open it in a browser) and
`out/report.json`. Every example folder already includes the reports from a
7nm run, so you can look at the output before you run anything.

---

## 1. What NPUWattch does

NPUWattch estimates the **energy, area, and timing** of an accelerator design
when it runs a given workload.

It takes two inputs:

| Input | What it is | Where it comes from |
| --- | --- | --- |
| **Architecture description** | The hardware in the design: how many MACs, the size of each buffer, and the NoC layout | An Accelergy/Timeloop `arch.yaml`, a PyTorchSim `config.yml`, or NPUWattch's own YAML |
| **Activity counts** | How many times each part was used, and for how many cycles | Timeloop's `*.stats.txt`, a PyTorchSim run directory, or NPUWattch's own CSV |

NPUWattch maps each component in your description to one of its **calibrated
primitives** (`fpmac`, `intmac`, `sram`, `regfile`, `crossbar`, `fifo`, …).
For each primitive, a trained model predicts the per-access energy, leakage,
area, and critical-path delay at your technology node. NPUWattch then
multiplies these values by the activity counts.

Each example folder also has three **definition files**. NPUWattch looks for
them by name, or you can choose other files with `--compound-components`,
`--projection`, and `--user-components`:

| File | What it is |
| --- | --- |
| `compound_components.yaml` | Hardware structures built from several primitives. For example, a systolic array is a set of MACs plus weight registers, and one Accelergy class can map to several primitives. |
| `projection.yaml` | Which simulator counter drives which part of a compound, and in which activity mode |
| `user_components.yaml` | Area and per-action energy for your own custom blocks. You supply the numbers. |

These files are part of your input, and a run stops with an error if they
are missing. This way, every number in the report comes from a trained model
or from data you provided.

The models are small MLPs trained on **post-layout data**. For logic, the RTL
goes through synthesis, place and route, parasitic extraction, and power
sign-off. For SRAM, the data comes from SPICE simulations of extracted
layouts. So the estimates are based on real layouts, not on scaled lookup
tables.

The activity input is optional. Without it, you still get the area and a
first-order **vectorless** energy estimate that assumes 25% switching
activity. The report labels this estimate clearly, so you won't confuse it
with a result based on activity counts.

---

## 2. Install

NPUWattch requires Python 3.10 or newer.

```bash
cd NPUWattch
pip install -e .
npuwattch --version
```

This adds the `npuwattch` command to your PATH. The `./run` scripts check for
it and let you know if it's missing.

---

## 3. The examples

|  | `timeloop/eyeriss_like/alexnet/` | `pytorchsim/tpu_like_fp32/matmul_1024/` |
| --- | --- | --- |
| Design | Eyeriss-like, 14×12 int8 PE array | TPUv3-like, 2× 128×128 fp32 systolic arrays |
| Workload | AlexNet, all 8 layers | one 1024×1024×1024 `torch.matmul` |
| Architecture source | `arch.yaml` (Accelergy v0.4) | `config.yml` + the simulator's own log header |
| Activity source | 8 × `*.stats.txt` (one per layer) | TOGSim log + gem5 `stats.txt` |
| Report shows | 8 energy windows, one per layer | 1 window (the kernel) |
| Runtime | a few seconds | a few seconds |

All examples run at **7nm**. To try other nodes, see §7.

For a file-by-file walkthrough of each example, including how the sample data
was produced, see `timeloop/eyeriss_like/README.md` and
`pytorchsim/README.md`. `timeloop/README.md` covers two more
Timeloop designs, Gemmini-like and NVDLA-like, each with ResNet-50 and
Llama-3-8B. `pytorchsim/README.md` covers the other PyTorchSim workloads on
the TPU-like NPU: a training step, a 2-core run, kernels without a MAC,
ResNet-50, and three LLM decoder blocks.

---

## 4. Example 1 — Timeloop

```bash
cd tutorial/timeloop/eyeriss_like/alexnet
./run
```

The script runs:

```bash
npuwattch --harness timeloop \
          --arch-yaml ../arch.yaml \
          --stats     stats/ \
          --node 7nm --clock-mhz 1000 \
          --tree --report out/
```

- `--arch-yaml` is the same architecture file you give Timeloop. NPUWattch
  doesn't need any other description.
- `--stats` points to a **directory**, so each `*.stats.txt` file in it becomes
  one report window, in filename order. If you pass a single file, you get one
  window. To combine all layers into one window, add `--stats-mode aggregate`.
- `--clock-mhz 1000` matches Timeloop's default 1 ns cycle, so NPUWattch's
  times line up with Timeloop's cycle counts.

Here is the per-layer table from the console:

```
┏━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ # ┃ window   ┃  cycles ┃  dyn (pJ) ┃ leak (pJ) ┃ total (pJ) ┃ avg power (mW) ┃
┡━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ 0 │ 01_conv1 │  638880 │ 9.419e+07 │ 1.873e+06 │  9.606e+07 │          150.4 │
│ 1 │ 02_conv2 │ 2332800 │ 8.403e+08 │  6.84e+06 │  8.472e+08 │          363.2 │
│ 2 │ 03_conv3 │  718848 │  1.85e+08 │ 2.108e+06 │  1.871e+08 │          260.3 │
│ 3 │ 04_conv4 │ 1437696 │ 2.056e+08 │ 4.215e+06 │  2.098e+08 │          145.9 │
│ 4 │ 05_conv5 │  638976 │ 1.374e+08 │ 1.873e+06 │  1.393e+08 │            218 │
│ 5 │ 06_fc6   │ 2359872 │ 2.461e+09 │ 6.919e+06 │  2.467e+09 │           1046 │
│ 6 │ 07_fc7   │ 1048832 │ 1.094e+09 │ 3.075e+06 │  1.097e+09 │           1046 │
│ 7 │ 08_fc8   │  256256 │ 2.672e+08 │ 7.513e+05 │   2.68e+08 │           1046 │
└───┴──────────┴─────────┴───────────┴───────────┴────────────┴────────────────┘
```

Total: **5.31 mJ**, 0.56 W average power, 0.459 mm² area, and 7.4 pJ per MAC.

The average power of a window is its energy divided by its cycles. The fully
connected layers are limited by the DRAM bandwidth in `arch.yaml` (16 B per
cycle), so all three show about 1 W.

The per-component table below it shows *where* the energy goes. The component
names are shown relative to the hierarchy prefix they all share, which is
printed above the table:

```
INFO (NW-1037): Per-window component energy (dynamic, pJ):
       component names relative to 'system_top_level'
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ component                         ┃  01_conv1 ┃  02_conv2 ┃    06_fc6 ┃    08_fc8 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ DRAM                              │ 2.956e+07 │  6.33e+08 │ 2.417e+09 │ 2.625e+08 │
│ eyeriss.shared_glb                │ 8.933e+05 │ 2.188e+06 │ 2.478e+04 │      1550 │
│ eyeriss.PE_column.PE.weights_spad │ 6.652e+06 │ 2.232e+07 │ 1.339e+07 │ 1.453e+06 │
│ eyeriss.PE_column.PE.mac          │ 4.609e+07 │ 1.469e+08 │ 2.475e+07 │ 2.686e+06 │
└───────────────────────────────────┴───────────┴───────────┴───────────┴───────────┘
```

(Only four of the eight columns and four of the six rows are shown here.) In
the conv layers, the MAC is the largest on-chip consumer. In the fully
connected layers, DRAM traffic takes over. The fc6 layer alone spends
2.42e+09 pJ in DRAM, because each weight is used only once. This kind of
breakdown is exactly what NPUWattch is designed to show.

Tables are sized to the data and split to fit your console window, so nothing
gets cut off or misaligned. To force a specific width, set `COLUMNS`.

## 5. Example 2 — PyTorchSim

```bash
cd tutorial/pytorchsim/tpu_like_fp32/matmul_1024
./run
```

The script runs:

```bash
npuwattch --harness pytorchsim \
          --togsim-dir  togsim_results/ \
          --gem5-dir    outputs/ \
          --config-yml  config.yml \
          --booksim-dir booksim2_config/ \
          --compound-components ../compound_components.yaml \
          --projection          ../projection.yaml \
          --user-components     ../user_components.yaml \
          --node 7nm --tree --report out/
```

PyTorchSim stores its results in several folders, so each one has its own
flag. The three definition files are the hardware model; they live in the
design folder `tpu_like_fp32/` and every workload folder points at them. If
a run root holds everything, the repository's `run.sh` finds the folders for
you:

```bash
../../../../run.sh . --node 7nm --report out/  # same thing, one argument
```

This example has **no** architecture file. NPUWattch rebuilds the hardware
from the simulator's own configuration and `compound_components.yaml`. Here is
what `--tree` prints (shortened):

```
chip
├── core0
│   ├── array0
│   │   ├── pe [×16384]  (class: fpmac, exponent_bits=8, mantissa_bits=23, pipeline_stages=4)
│   │   └── w_reg [×16384]  (class: register_file, data_width=32, mem_depth_per_bank=1)
│   ├── array1                        (identical to array0)
│   ├── vmem  (class: sram, mem_banks=32, mem_depth_per_bank=32768, data_width=128 = 16 MB)
│   ├── vpu_spad [×128], vrf [×128], vfu [×128], sfu_pipe [×128]
│   ├── dma_q  (class: fifo)
│   └── dma_addr  (class: intadd)
├── noc
│   ├── icnt_xbar  (class: crossbar, net_inputs=32, net_outputs=32, data_width=256)
│   └── icnt_buf [×32]  (class: sram)
└── dram
    └── dram_chan [×16]  (class: hbm)
```

Result: **5.96 mJ** over 52 022 cycles, 108 W average power, 88.75 mm²,
2.78 pJ/FLOP, and 38.8 TFLOP/s. The two systolic arrays account for 91% of the
energy and DRAM for 8%, which is what you'd expect from a matmul.

The long INFO block in this run (`NW-6008` and `NW-2209`) is worth a look.
It lists the parts that are *not* included in the totals (the scalar core and its caches, the VCIX
serializer, and DRAM standby power), so you always know what the numbers
cover.

### The bf16 variant

```bash
cd tutorial/pytorchsim/tpu_like_bf16/matmul_1024
./run
```

<!-- Internal note: PyTorchSim cannot simulate bf16 kernels, so this example
reuses the float32 run and fixes the PE type in the hardware model. DRAM and
NoC energy keep the float32 byte counts, so they are high for a bf16 kernel. -->
A real TPU multiplies in bf16. This design reads the simulator files of
`tpu_like_fp32/matmul_1024` and changes only `compound_components.yaml`: the `pe` element
uses a fixed bf16 `fpmac` instead of the `{mac_primitive}` / `{mac_config}`
templates. The PE energy drops from 5.05 to 1.56 pJ per MAC, and the total is
**2.21 mJ, 1.03 pJ/FLOP**. DRAM and NoC traffic use the byte counts from the
float32 run. See `pytorchsim/tpu_like_bf16/README.md` for details.

### More workloads

The other folders under `pytorchsim/tpu_like_fp32/` run other workloads on
the same NPU. Each is a PyTorchSim run root with its own `run` script, and each
`kernels.yaml` names the kernels, so the report shows names instead of
hashes:

```bash
cd tutorial/pytorchsim/tpu_like_fp32/resnet50 && ./run
cd tutorial/pytorchsim/tpu_like_fp32/llama3_8b/prefill && ./run
```

`pytorchsim/README.md` lists them with their results.

---

## 6. Reading the output

**Console output**, from top to bottom:

1. `--tree`: the hardware as NPUWattch read it from your input. Check this
   first. If a component is missing or has the wrong size, all the numbers
   after it will be off.
2. `WARNING` / `INFO` lines: every assumption NPUWattch made for you, such
   as default values, ignored attributes, and activity counters that are left
   out on purpose. See "Messages" below.
3. **Per-window energy**: one row per layer (Timeloop) or per kernel
   (PyTorchSim).
4. **Per-window component energy**: where the energy went in each window.
5. **Energy summary**: totals per component for the whole run, with area and
   leakage. The `model` column shows `cal` for a calibrated MLP prediction,
   `const` for a table constant (DRAM devices, die-to-die links), and `user`
   for a block priced from your `user_components.yaml`.
6. The run totals, and the list of available primitives.
7. The message summary.

**`out/report.html`** shows the same information as a self-contained page (no
internet connection or extra files needed). It includes charts for the energy
and area breakdowns and the DRAM breakdown, a cycle-level energy plot across
windows, the component table, the instance tree, and a provenance section that
lists every input file, warning, and note.

**`out/report.json`** has the same numbers in plain JSON, for use in scripts.

### Messages

Each message has a level and a code. The format is `LEVEL (NW-nnnn): text`:

```
WARNING (NW-8111): core0.vrf: width=256 is outside the characterized range 8-128 of regfile.
```

The level tells you what to do:

| Level | Meaning |
| --- | --- |
| `INFO` | A fact about the run. No action is necessary. |
| `WARNING` | The run continues, but the result can be approximate. Read the message. |
| `ERROR` | A problem in the input. The run stops. Correct the input. |
| `CRITICAL` | A problem in NPUWattch. The run stops. Please report it. |

The code does not change from release to release. Use it to get more
information:

```bash
npuwattch --explain NW-8111         # the full explanation of one message
npuwattch --list-messages NW-6      # all messages that start with NW-6 (PyTorchSim harness)
./run --suppress NW-8212            # do not print this INFO or WARNING message
```

You cannot suppress an `ERROR` or a `CRITICAL` message. The run ends with a
message summary. It gives the number of messages at each level, and one row
for each WARNING code:

```
INFO (NW-1902): Message summary: 0 CRITICAL, 0 ERROR, 5 WARNING, 18 INFO.
    NW-6607   WARNING  x1
    NW-8111   WARNING  x1
    NW-8212   WARNING  x3
```

Suppressed messages are counted in the summary, but the report does not show
them. In `report.html`, the message table shows the code, the level, the text,
and the count. Click a message to see its explanation. `MESSAGES.md` in the
repository root lists all messages.

---

## 7. Things to try next

```bash
# A different technology node. 5/7/10/16/20nm are characterized; anything
# between them is interpolated; 2.5-30nm is extrapolated with a warning.
./run --node 5nm
./run --node 3nm            # extrapolated — NPUWattch says so

# A different operating point.
./run --node 7nm --corner SS --temperature 85 --voltage-offset -0.05

# No activity at all: area + a vectorless energy estimate.
cd timeloop/eyeriss_like && npuwattch --harness timeloop --arch-yaml arch.yaml --node 7nm

# One number for the whole network instead of eight windows.
cd timeloop/eyeriss_like/alexnet && ./run --stats-mode aggregate
```

## 8. Using your own data

- **If you use Timeloop or Accelergy**: point `--arch-yaml` to your
  architecture file and `--stats` to your `timeloop-model.stats.txt` (or to a
  directory of per-layer files). If a stats level name doesn't match a
  component name, pass a `--stats-map` YAML file. Use `levels:` in it to rename
  levels and `ignore:` to skip them. Copy the three definition files from
  `timeloop/eyeriss_like/` into the folder with your `arch.yaml`.
- **If you use PyTorchSim**: copy your run root (the folder with
  `togsim_results/` and `outputs/`), copy the three definition files from
  `pytorchsim/tpu_like_fp32/` into it, and run `run.sh <root>`.
- **If your design has a custom block**: add it to `user_components.yaml`
  (name, area, and energy per action), or describe an Accelergy class as a set
  of primitives in `compound_components.yaml`.
- **If you use another simulator**: write an NPUWattch native description YAML
  and an activity CSV, then run `npuwattch -d description.yaml -l activity.csv`.
  The easiest way to learn the two formats is to let a harness write them for
  you and then edit the result:

  ```bash
  cd timeloop/eyeriss_like/alexnet
  npuwattch --harness timeloop --arch-yaml ../arch.yaml --stats stats/ \
            --node 7nm --clock-mhz 1000 -o native/
  # native/description.yaml — every component, class, count and attribute
  # native/activity.csv     — window,cycle_start,cycle_end,component,event,mode,count
  npuwattch -d native/description.yaml -l native/activity.csv
  ```

To see all the options, run `npuwattch --help`.
