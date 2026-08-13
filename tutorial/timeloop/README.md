# Example 1 — Timeloop / Accelergy

An Eyeriss-like accelerator running all eight layers of AlexNet.

```bash
./run
```

## Files

```
arch.yaml                 the architecture description (Accelergy v0.4)
stats/01_conv1.stats.txt  Timeloop's activity counts for layer 1
stats/02_conv2.stats.txt  ... one file per layer, 8 in total
stats/08_fc8.stats.txt
run                       the script
out/                      report.html + report.json — shipped, and ./run overwrites them
```

## What NPUWattch reads

**`arch.yaml`** — the same file you would give Timeloop, unmodified. It
declares six components:

| Component | Accelergy class | NPUWattch primitive |
| --- | --- | --- |
| `DRAM` | `DRAM` | `hbm` (analytic constants) |
| `shared_glb` | `smartbuffer_SRAM` | `sram` |
| `ifmap_spad`, `weights_spad`, `psum_spad` | `smartbuffer_RF` | `regfile` |
| `mac` | `intmac` | `intmac` |

The `!Container` nodes (`PE_column` with `meshX: 14`, `PE` with `meshY: 12`)
set the instance counts: 14 × 12 = 168 copies of each scratchpad and MAC.

**`stats/*.stats.txt`** — what Timeloop's mapper reported for the mapping it
found. NPUWattch reads the per-level `STATS` blocks:

```
=== weights_spad ===
    STATS
    -----
    Cycles               : 638880
    Weights:
        Scalar reads (per-instance)              : 638880
        Scalar fills (per-instance)              : 11616
        Utilized instances (max)                 : 110
```

Reads and fills become read and write events; the count is multiplied by
*utilized instances* and divided by the block size, so a component that sits
idle in a given layer is charged leakage only. `Computes` on the `mac` level
becomes MAC operations, charged in the weight-stationary mode this mapping uses.

**Level names bind to component names.** `=== weights_spad ===` charges the
component named `weights_spad`. If your names differ, pass a `--stats-map`
YAML with `levels:` renames and `ignore:` for levels you mean to drop.

## One window per layer

`--stats stats/` is a directory, so NPUWattch makes one report window per file,
sorted by filename — hence the `01_`…`08_` prefixes. The window label is the
filename, which is why the console table reads `01_conv1`, `02_conv2`, and so
on. `--stats-mode aggregate` sums them into a single window instead.

## Messages you will see, and why

- `Accelergy class routed to the 'hbm' primitive` — `arch.yaml` declares
  LPDDR4, but `hbm` is currently NPUWattch's only DRAM-device model. The DRAM
  row is priced with analytic HBM2 constants, not a trained model, and is marked
  `const` in the summary.
- `no operand width declared — assuming 8 bits` — Accelergy's `intmac` class
  has `multiplier_width`/`adder_width`, which are not the same thing as an
  operand width. NPUWattch says what it assumed instead of guessing silently.
- `the description declares technology 65nm but the run is evaluated at 7nm`
  — the `technology:` attribute in an Accelergy file is a label; NPUWattch
  models the node you pass with `--node`.

## How the sample data was made

The architecture is the `eyeriss_like` design from
[timeloop-accelergy-exercises](https://github.com/Accelergy-Project/timeloop-accelergy-exercises)
(`workspace/example_designs/example_designs/eyeriss_like/arch.yaml`), copied
verbatim.

The stats files come from running `timeloop-mapper` once per AlexNet layer
against that architecture, using the layer shapes bundled with the same
exercises (`layer_shapes/alexnet/0.yaml` … `7.yaml`):

| File | Layer | Shape |
| --- | --- | --- |
| `01_conv1` | conv1 | C=3, M=64, P=Q=55, R=S=11, stride 4 |
| `02_conv2` | conv2 | C=64, M=192, P=Q=27, R=S=5 |
| `03_conv3` | conv3 | C=192, M=384, P=Q=13, R=S=3 |
| `04_conv4` | conv4 | C=384, M=256, P=Q=13, R=S=3 |
| `05_conv5` | conv5 | C=256, M=256, P=Q=13, R=S=3 |
| `06_fc6` | fc6 | C=9216, M=4096 |
| `07_fc7` | fc7 | C=4096, M=4096 |
| `08_fc8` | fc8 | C=4096, M=1000 |

Each mapper run takes about 25 seconds; the eight together produced the 8
stats files unchanged in `stats/`. Nothing in this folder was hand-edited.
