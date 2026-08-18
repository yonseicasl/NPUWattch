# NPUWattch Tutorial

This folder contains two complete, ready-to-run examples. Each one is a real
simulator run with real activity counts. You do not need any EDA tool, PDK, or
GPU — just NPUWattch.

```
tutorial/
├── timeloop/      Example 1 — Timeloop / Accelergy input (AlexNet, 8 layers)
└── pytorchsim/    Example 2 — PyTorchSim input (one 1024³ matmul)
```

Run either one with:

```bash
cd tutorial/timeloop && ./run
cd tutorial/pytorchsim && ./run
```

Each script writes `out/report.html` (open it in a browser) and
`out/report.json` next to it. Both folders already contain the reports from a
7nm run, so you can look at the output before running anything.

---

## 1. What NPUWattch does

NPUWattch answers one question: **how much energy, area, and timing does this
accelerator design need to run this workload?**

It needs two things:

| Input | What it is | Where it comes from |
| --- | --- | --- |
| **Architecture description** | What hardware exists: how many MACs, how big each buffer is, what the NoC looks like | An Accelergy/Timeloop `arch.yaml`, a PyTorchSim `config.yml`, or NPUWattch's own YAML |
| **Activity counts** | How many times each part was used, and for how many cycles | Timeloop's `*.stats.txt`, a PyTorchSim run directory, or NPUWattch's own CSV |

NPUWattch maps every component in your description onto one of its **calibrated
primitives** (`fpmac`, `intmac`, `sram`, `regfile`, `crossbar`, `fifo`, …), asks
the trained model for that primitive's per-access energy, leakage, area, and
critical path at your technology node, then multiplies by the activity counts.

The models are small MLPs trained on **post-layout measurements** — RTL through
synthesis, place-and-route, parasitic extraction, and power sign-off for logic;
SPICE on extracted layout for SRAM. That is why the answer is a prediction of
silicon, not a scaled lookup table.

The activity half is optional. Without it you still get area, timing, and a
first-order **vectorless** energy estimate (25% switching assumed). The report
labels that clearly, so you never mistake it for a measured number.

---

## 2. Install

NPUWattch needs Python 3.10 or newer.

```bash
cd NPUWattch
pip install -e .
npuwattch --version
```

That puts the `npuwattch` command on your PATH. The two `./run` scripts check
for it and tell you if it is missing.

---

## 3. The two examples

|  | `timeloop/` | `pytorchsim/` |
| --- | --- | --- |
| Design | Eyeriss-like, 14×12 int8 PE array | TPUv3-like, 2× 128×128 fp32 systolic arrays |
| Workload | AlexNet, all 8 layers | one 1024×1024×1024 `torch.matmul` |
| Architecture from | `arch.yaml` (Accelergy v0.4) | `config.yml` + the simulator's own log header |
| Activity from | 8 × `*.stats.txt` (one per layer) | TOGSim log + gem5 `stats.txt` |
| Report shows | 8 energy windows, one per layer | 1 window (the kernel) |
| Runtime | a few seconds | a few seconds |

Both are run at **7nm** (`--node 7nm`). Try other nodes — see §7.

Read `timeloop/README.md` and `pytorchsim/README.md` for a file-by-file
explanation of each example, including how the sample data was produced.

---

## 4. Example 1 — Timeloop

```bash
cd tutorial/timeloop
./run
```

The script runs:

```bash
npuwattch --harness timeloop \
          --arch-yaml arch.yaml \
          --stats     stats/ \
          --node 7nm --clock-mhz 1000 \
          --tree --report out/
```

- `--arch-yaml` is the architecture you gave Timeloop, unmodified.
- `--stats` is a **directory**, so each `*.stats.txt` inside becomes one report
  window, in filename order. Pass a single file instead and you get one window.
  Add `--stats-mode aggregate` to sum all layers into one instead.
- `--clock-mhz 1000` matches Timeloop's default 1 ns cycle, so NPUWattch's
  seconds agree with Timeloop's cycles.

Result — the per-layer table, straight from the console:

```
┏━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ # ┃ window   ┃  cycles ┃  dyn (pJ) ┃ leak (pJ) ┃ total (pJ) ┃ avg power (mW) ┃
┡━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ 0 │ 01_conv1 │  638880 │ 6.925e+08 │ 1.557e+07 │   7.08e+08 │           1108 │
│ 1 │ 02_conv2 │ 2332800 │ 2.439e+09 │ 5.686e+07 │  2.496e+09 │           1070 │
│ 2 │ 03_conv3 │  718848 │ 1.158e+09 │ 1.752e+07 │  1.175e+09 │           1635 │
│ 3 │ 04_conv4 │ 1437696 │ 1.546e+09 │ 3.504e+07 │  1.581e+09 │           1099 │
│ 4 │ 05_conv5 │  638976 │ 1.031e+09 │ 1.557e+07 │  1.046e+09 │           1637 │
│ 5 │ 06_fc6   │  393216 │ 1.606e+09 │ 9.584e+06 │  1.616e+09 │           4109 │
│ 6 │ 07_fc7   │  262144 │ 7.125e+08 │ 6.389e+06 │  7.189e+08 │           2742 │
│ 7 │ 08_fc8   │   40960 │ 1.739e+08 │ 9.983e+05 │  1.749e+08 │           4270 │
└───┴──────────┴─────────┴───────────┴───────────┴────────────┴────────────────┘
```

Total: **9.52 mJ**, 1.47 W average, 5.40 mm² area, 13.3 pJ per MAC.

The per-component table underneath shows *why*. Component names there are
printed relative to the hierarchy prefix they all share, which is noted above
the table:

```
[INFO] Per-window component energy (dynamic, pJ)
       component names relative to 'system_top_level'
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ component                         ┃  01_conv1 ┃  02_conv2 ┃    06_fc6 ┃    08_fc8 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ DRAM                              │ 1.286e+07 │ 2.754e+08 │ 1.052e+09 │ 1.142e+08 │
│ eyeriss.shared_glb                │ 4.367e+07 │ 9.942e+07 │ 2.424e+06 │ 6.967e+04 │
│ eyeriss.PE_column.PE.weights_spad │ 4.042e+08 │ 1.312e+09 │ 4.273e+08 │ 4.637e+07 │
│ eyeriss.PE_column.PE.mac          │ 4.977e+07 │ 1.586e+08 │ 2.673e+07 │ 2.901e+06 │
└───────────────────────────────────┴───────────┴───────────┴───────────┴───────────┘
```

(Four of the eight columns and four of the six rows shown here.) In the conv
layers the weight scratchpads dominate; in the fully-connected layers DRAM
traffic takes over — fc6 alone reads 1.05e+09 pJ from DRAM, because its weights
are used once and thrown away. That split is the kind of thing NPUWattch exists
to make visible.

Tables are sized from the data and chunked to fit your console, so nothing is
ever truncated or knocked out of alignment. Set `COLUMNS` to force a width.

## 5. Example 2 — PyTorchSim

```bash
cd tutorial/pytorchsim
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

PyTorchSim splits its results across folders, so each one gets a flag. The
repository's `run.sh` finds them for you when they share a root:

```bash
../../run.sh . --node 7nm --report out/     # same thing, one argument
```

Here NPUWattch does **not** read an architecture file. It reconstructs the
hardware from the simulator's own configuration — that is what `--tree` prints
(abridged here):

```
chip
├── core0
│   ├── array0
│   │   ├── pe [×16384]  (class: fpmac, exponent_bits=8, mantissa_bits=23, pipeline_stages=4)
│   │   └── w_reg [×16384]  (class: register_file, data_width=32, mem_depth_per_bank=1)
│   ├── array1                        (identical to array0)
│   ├── vmem  (class: sram, mem_banks=32, mem_depth_per_bank=32768, data_width=128)
│   ├── vpu_spad [×128], vrf [×128], vfu [×128], sfu_pipe [×128]
│   ├── dma_q  (class: fifo)
│   └── dma_addr  (class: intadd)
├── noc
│   ├── icnt_xbar  (class: crossbar, net_inputs=32, net_outputs=32, data_width=256)
│   └── icnt_buf [×32]  (class: sram)
└── dram
    └── dram_chan [×16]  (class: hbm)
```

Result: **6.13 mJ** over 52 022 cycles, 111 W average, 88.7 mm², 2.85 pJ/FLOP,
38.8 TFLOP/s. The two systolic arrays account for 91% of the dynamic energy and
DRAM for 8%, which is what you want from a matmul.

Two messages in this run are worth understanding:

- `Configured clock (940 MHz) is within 20% of the estimated f_max (992 MHz)`
  — the timing model says this design barely closes at 940 MHz. NPUWattch
  predicts a critical path, not just energy.
- The long `[INFO]` block listing what is *not* charged (the scalar core, its
  caches, the VCIX serializer, DRAM standby power). NPUWattch states its scope
  explicitly instead of silently leaving things out.

---

## 6. Reading the output

**Console**, top to bottom:

1. `--tree` — the hardware NPUWattch thinks you described. Check this first. If
   a component is missing or has the wrong size, everything downstream is wrong.
2. `[WARNING]` / `[INFO]` — every assumption made on your behalf: defaults
   filled in, attributes ignored, activity counters deliberately not charged.
3. **Per-window energy** — one row per layer (Timeloop) or kernel (PyTorchSim).
4. **Per-window component energy** — where the energy went, per window.
5. **Energy summary** — the whole run per component, with area and leakage.
   `model` says `cal` for a calibrated MLP prediction and `const` for an
   analytic constant (today only DRAM devices).
6. Totals, and which primitives were available.

**`out/report.html`** is the same information, self-contained (no internet, no
external files) with charts: energy and area breakdowns, the DRAM split, a
cycle-level energy plot across windows, the component table, the instance tree,
and a provenance section listing every input file, warning, and note.

**`out/report.json`** is the same data for scripts — same numbers, no styling.

---

## 7. Things to try next

```bash
# A different technology node. 5/7/10/16/20nm are characterized; anything
# between them is interpolated; 2.5-30nm is extrapolated with a warning.
./run --node 5nm
./run --node 3nm            # extrapolated — NPUWattch says so

# A different operating point.
./run --node 7nm --corner SS --temperature 85 --voltage-offset -0.05

# No activity at all: area + timing + a vectorless energy estimate.
cd timeloop && npuwattch --harness timeloop --arch-yaml arch.yaml --node 7nm

# One number for the whole network instead of eight windows.
cd timeloop && ./run --stats-mode aggregate
```

## 8. Using your own data

- **You use Timeloop or Accelergy** → point `--arch-yaml` at your architecture
  and `--stats` at your `timeloop-model.stats.txt` (or a directory of per-layer
  files). If a stats level name does not match a component name, pass a
  `--stats-map` YAML with `levels:` renames and `ignore:` drops.
- **You use PyTorchSim** → copy your run root (the folder holding
  `togsim_results/` and `outputs/`) and run `run.sh <root>`.
- **You use something else** → write NPUWattch's native description YAML and an
  activity CSV, then `npuwattch -d description.yaml -l activity.csv`. The
  quickest way to learn those two formats is to have a harness write them for
  you and edit the result:

  ```bash
  cd timeloop
  npuwattch --harness timeloop --arch-yaml arch.yaml --stats stats/ \
            --node 7nm --clock-mhz 1000 -o native/
  # native/description.yaml — every component, class, count and attribute
  # native/activity.csv     — window,cycle_start,cycle_end,component,event,mode,count
  npuwattch -d native/description.yaml -l native/activity.csv
  ```

Every flag: `npuwattch --help`.
