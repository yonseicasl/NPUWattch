# NPUWattch Tutorial

This folder has ready-to-run examples for two simulators. The examples use
activity counts from real simulator runs. You don't need any EDA tools, PDKs,
or GPUs. All you need is NPUWattch.

```
tutorial/
├── timeloop/      Example 1 — Timeloop / Accelergy input
│   ├── eyeriss_like/alexnet/      AlexNet, 8 layers (the basic example)
│   ├── gemmini_like/{resnet50,llama3_8b}/
│   └── nvdla_like/{resnet50,llama3_8b}/
└── pytorchsim/    Example 2 — PyTorchSim input (one 1024³ matmul)
    ├── tpu_like_fp32/             fp32 PEs, as the simulator ran the kernel
    └── tpu_like_bf16/             the same run, PEs fixed to bf16 MACs
```

To run an example:

```bash
cd tutorial/timeloop/eyeriss_like/alexnet && ./run
cd tutorial/pytorchsim/tpu_like_fp32 && ./run
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

|  | `timeloop/eyeriss_like/` | `pytorchsim/tpu_like_fp32/` |
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
Llama-3-8B.

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
│ 0 │ 01_conv1 │  638880 │ 6.627e+08 │ 1.873e+06 │  6.646e+08 │           1040 │
│ 1 │ 02_conv2 │ 2332800 │ 2.688e+09 │  6.84e+06 │  2.695e+09 │           1155 │
│ 2 │ 03_conv3 │  718848 │ 1.134e+09 │ 2.108e+06 │  1.136e+09 │           1581 │
│ 3 │ 04_conv4 │ 1437696 │ 1.472e+09 │ 4.215e+06 │  1.476e+09 │           1027 │
│ 4 │ 05_conv5 │  638976 │ 9.741e+08 │ 1.873e+06 │  9.759e+08 │           1527 │
│ 5 │ 06_fc6   │  393216 │ 2.968e+09 │ 1.153e+06 │  2.969e+09 │           7550 │
│ 6 │ 07_fc7   │  262144 │ 1.318e+09 │ 7.686e+05 │  1.318e+09 │           5029 │
│ 7 │ 08_fc8   │   40960 │ 3.219e+08 │ 1.201e+05 │   3.22e+08 │           7862 │
└───┴──────────┴─────────┴───────────┴───────────┴────────────┴────────────────┘
```

Total: **11.6 mJ**, 1.79 W average power, 0.459 mm² area, and 16.2 pJ per MAC.

The per-component table below it shows *where* the energy goes. The component
names are shown relative to the hierarchy prefix they all share, which is
printed above the table:

```
[INFO] Per-window component energy (dynamic, pJ)
       component names relative to 'system_top_level'
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ component                         ┃  01_conv1 ┃  02_conv2 ┃    06_fc6 ┃    08_fc8 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ DRAM                              │ 2.956e+07 │  6.33e+08 │ 2.417e+09 │ 2.625e+08 │
│ eyeriss.shared_glb                │ 8.933e+05 │ 2.188e+06 │ 4.925e+04 │      1550 │
│ eyeriss.PE_column.PE.weights_spad │ 4.042e+08 │ 1.312e+09 │ 4.273e+08 │ 4.637e+07 │
│ eyeriss.PE_column.PE.mac          │ 4.609e+07 │ 1.469e+08 │ 2.475e+07 │ 2.686e+06 │
└───────────────────────────────────┴───────────┴───────────┴───────────┴───────────┘
```

(Only four of the eight columns and four of the six rows are shown here.) In
the conv layers, the weight scratchpads use the most energy. In the fully
connected layers, DRAM traffic takes over. The fc6 layer alone spends
2.42e+09 pJ in DRAM, because each weight is used only once. This kind of
breakdown is exactly what NPUWattch is designed to show.

Tables are sized to the data and split to fit your console window, so nothing
gets cut off or misaligned. To force a specific width, set `COLUMNS`.

## 5. Example 2 — PyTorchSim

```bash
cd tutorial/pytorchsim/tpu_like_fp32
./run
```

The script runs:

```bash
npuwattch --harness pytorchsim \
          --togsim-dir  togsim_results/ \
          --gem5-dir    outputs/ \
          --config-yml  config.yml \
          --booksim-dir booksim2_config/ \
          --node 7nm --tree --report out/
```

PyTorchSim stores its results in several folders, so each one has its own
flag. If they are all under one root folder, the repository's `run.sh` finds
them for you:

```bash
../../../run.sh . --node 7nm --report out/  # same thing, one argument
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

Result: **6.13 mJ** over 52 022 cycles, 111 W average power, 88.75 mm²,
2.86 pJ/FLOP, and 38.8 TFLOP/s. The two systolic arrays account for 91% of the
dynamic energy and DRAM for 8%, which is what you'd expect from a matmul.

The long `[INFO]` block in this run is worth a look. It lists the parts that
are *not* included in the totals (the scalar core and its caches, the VCIX
serializer, and DRAM standby power), so you always know what the numbers
cover.

### The bf16 variant

```bash
cd tutorial/pytorchsim/tpu_like_bf16
./run
```

<!-- Internal note: PyTorchSim cannot simulate bf16 kernels, so this example
reuses the float32 run and fixes the PE type in the hardware model. DRAM and
NoC energy keep the float32 byte counts, so they are high for a bf16 kernel. -->
A real TPU multiplies in bf16. This example uses the same simulator files as
`tpu_like_fp32` and changes only `compound_components.yaml`: the `pe` element
uses a fixed bf16 `fpmac` instead of the `{mac_primitive}` / `{mac_config}`
templates. The PE energy drops from 5.05 to 1.56 pJ per MAC, and the total is
**2.29 mJ, 1.07 pJ/FLOP**. DRAM and NoC traffic use the byte counts from the
float32 run. See `pytorchsim/tpu_like_bf16/README.md` for details.

---

## 6. Reading the output

**Console output**, from top to bottom:

1. `--tree`: the hardware as NPUWattch read it from your input. Check this
   first. If a component is missing or has the wrong size, all the numbers
   after it will be off.
2. `[WARNING]` / `[INFO]`: every assumption NPUWattch made for you, such as
   default values, ignored attributes, and activity counters that are left out
   on purpose.
3. **Per-window energy**: one row per layer (Timeloop) or per kernel
   (PyTorchSim).
4. **Per-window component energy**: where the energy went in each window.
5. **Energy summary**: totals per component for the whole run, with area and
   leakage. The `model` column shows `cal` for a calibrated MLP prediction,
   `const` for a table constant (DRAM devices, die-to-die links), and `user`
   for a block priced from your `user_components.yaml`.
6. The run totals, and the list of available primitives.

**`out/report.html`** shows the same information as a self-contained page (no
internet connection or extra files needed). It includes charts for the energy
and area breakdowns and the DRAM breakdown, a cycle-level energy plot across
windows, the component table, the instance tree, and a provenance section that
lists every input file, warning, and note.

**`out/report.json`** has the same numbers in plain JSON, for use in scripts.

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
