"""Torch code of the logic primitive MLPs: the feature vocabulary, the net,
and the checkpoint files.

The structure is the same as ``src/npuwattch_estimators/sram/sram_mlp.py``:

- a ``.pt`` file that contains only the state_dict
- JSON sidecar files that contain all the transforms (manual §3.5)
- absolute log10 targets
- a ReLU MLP
- seed 42, for reproducible results

The differences from SRAM come from the data of the logic sweep:

- There is one model for each **(component, metric)** pair. There are 14
  components: 7 arithmetic blocks, mxfpmac, and the NoC and memory blocks
  (crossbar, fifo, regfile, fattree, simplemux, foldedclos). There are 4
  metrics: energy, leakage, timing, area. The files of a model have the name
  ``<component>_<metric>__<VERSION>.*``. A categorical parameter (the
  ``input_format`` of mxfpmac) is a one-hot input from CATEGORICAL_COLUMNS.
- ``stim_mode`` is a one-hot INPUT of the power metrics (energy, leakage). The
  projection asks for the unit cost of each mode (COMPOUND_SCHEMA §6). The
  mode ``none`` is the row without vectors. Remove it for a component only if
  the A/B test in the eval report shows a clear increase of the error.
- The axes of the adaptive loss are **SCR and SAR** (manual §5.3). The SRAM
  models use the target axis because SPICE rows have no SCR or SAR.
- ``log10_clock_ns`` is an input of EACH metric. Each design was implemented
  for its clock constraint, thus the area, the timing, and the power change
  with it.
- There are no PVT features. The logic dataset has only TT, 25 °C, and the
  nominal voltage, and a constant column breaks the scalers. A dataset with a
  PVT sweep needs a new VERSION and these axes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import torch
from torch import nn

from npuwattch_estimators.errors import EstimatorQueryError, LogicQueryError

VERSION = "v2"   # The v2 dataset: re-characterized cell libraries and the
                 # re-pipelined fpadd/fpmul/fpmac RTL.

COMPONENTS = ("fpadd", "fpmul", "fpmac", "intadd", "intmul", "intmac", "fpsfu",
              "mxfpmac", "crossbar", "fifo", "regfile", "fattree",
              "simplemux", "foldedclos")
METRICS = ("energy", "leakage", "timing", "area")

#: The dataset CSV column of each metric. The column has linear units. The
#: target of the model is the absolute log10 of the value.
TARGET_COLUMNS = {
    "energy": "dyn_energy_pJ",          # dynamic energy of one cycle at the mode
    "leakage": "leak_power_mW",
    # The minimum period that the post-route netlist meets (collector
    # schema 3). It includes the SDC budget of each path group and the clock
    # uncertainty. Do NOT use pnr_crit_path_ns: in schema <= 2 it is the delay
    # of the in2reg path group of ICC2, which the input delay controls.
    "timing": "pnr_min_period_ns",
    "area": "pnr_total_area_um2",
}
TARGET_UNITS = {"energy": "pJ", "leakage": "mW", "timing": "ns", "area": "um2"}

#: The metrics that have one row for each stim_mode (a one-hot input). Timing
#: and area are properties of the implementation. They have one row for each
#: design and no mode axis.
MODE_METRICS = ("energy", "leakage")

NODE_LIST = (5, 7, 10, 16, 20)

#: The numeric design parameters of each component (dataset columns). The
#: model input is log2 of the value, because these are size parameters. Do not
#: change the order: it is the feature order.
PARAM_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "fpadd": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "fpmul": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "fpmac": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "intadd": ("a_width", "b_width", "out_width", "pipeline_stages"),
    "intmul": ("a_width", "b_width", "out_width", "pipeline_stages"),
    "intmac": ("a_width", "b_width", "out_width", "acc_width", "pipeline_stages"),
    "fpsfu": ("exp_bits", "mantissa_bits", "sfu_segments", "pipeline_stages"),
    # An empty pipeline_stages cell is 1. Such an mxfpmac row is a
    # combinational design. train_logic supplies the default.
    "mxfpmac": ("block_elems", "num_blocks", "pipeline_stages"),
    "crossbar": ("data_width", "num_inputs", "num_outputs"),
    "fifo": ("width", "depth"),
    "regfile": ("width", "depth", "num_read_ports", "num_write_ports"),
    "fattree": ("data_width", "radix", "num_levels", "oversubscription"),
    "simplemux": ("data_width", "num_inputs"),
    "foldedclos": ("data_width", "terminals_per_leaf", "num_leaves",
                   "num_spines", "oversubscription"),
}

#: The binary design flags. They are 0/1 inputs without scaling.
FLAG_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "fpsfu": ("sfu_op_exp", "sfu_op_trig", "sfu_op_hyp", "sfu_op_erf",
              "sfu_op_relu"),
}

#: The categorical design parameters. They are one-hot inputs without scaling.
#: Do not change the (column, value order) pairs: the order IS the feature
#: order.
CATEGORICAL_COLUMNS: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "mxfpmac": (("input_format", ("mxfp4_e2m1", "mxfp6_e2m3", "mxfp6_e3m2",
                                  "mxfp8_e4m3", "mxfp8_e5m2", "mxint8",
                                  "bf16")),),
}

#: The one-hot order of the stim_mode of each component. Do not change it. It
#: is the same as POWER_MODES, with 'none' added. 'none' is the row without
#: vectors (see the module docstring).
STIM_MODES: Dict[str, Tuple[str, ...]] = {
    "fpadd": ("none", "random"),
    "fpmul": ("none", "random"),
    "intadd": ("none", "random"),
    "intmul": ("none", "random"),
    "fpmac": ("none", "random", "hold_b", "sparse50", "idle"),
    "intmac": ("none", "random", "hold_b", "sparse50", "idle"),
    "fpsfu": ("none", "random", "exp", "trig", "hyp", "erf", "idle"),
    "mxfpmac": ("none", "random", "hold_scale", "sparse50", "idle"),
    # crossbar, simplemux, and foldedclos do NOT have the mode 'none'. For
    # these small combinational blocks, 'none' makes the energy model less
    # accurate.
    "crossbar": ("random", "fixed_route", "valid25"),
    "fifo": ("none", "random", "stream", "idle"),
    "regfile": ("none", "random", "read", "write", "idle"),
    "fattree": ("none", "random", "fixed_route"),
    "simplemux": ("random", "valid25"),
    "foldedclos": ("random", "fixed_route"),
}

DEFAULT_ARCH: Dict[str, List[int]] = {
    "energy": [128, 128, 128],
    "leakage": [128, 128, 128],
    "timing": [64, 64],                 # one row for each design (no mode axis)
    "area": [64, 64],
}


def node_nm(node: str) -> int:
    m = re.search(r"(\d+)", node)
    if not m:
        raise EstimatorQueryError.nw(8002, node=node)
    return int(m.group(1))


def modes_for(component: str, metric: str) -> Tuple[str, ...]:
    return STIM_MODES[component] if metric in MODE_METRICS else ()


def base_feature_names(component: str, metric: str) -> List[str]:
    names = ["log10_node_nm", "log10_clock_ns"]
    names += [f"log2_{c}" for c in PARAM_COLUMNS[component]]
    names += list(FLAG_COLUMNS.get(component, ()))
    names += [f"{col}_is_{v}"
              for col, values in CATEGORICAL_COLUMNS.get(component, ())
              for v in values]
    names += [f"node_is_{n}nm" for n in NODE_LIST]
    return names


def _n_continuous(component: str) -> int:
    return 2 + len(PARAM_COLUMNS[component])


def base_features(component: str, nm: int, clock_ns: float,
                  params: Mapping[str, Any]) -> List[float]:
    f = [math.log10(nm), math.log10(clock_ns)]
    # The minimum is 2^-8, NOT 1. The oversubscription of fattree and
    # foldedclos is a fraction (0.25, 0.5, 1.0). The values must stay different
    # after the log transform.
    f += [math.log2(max(float(params[c]), 2.0 ** -8))
          for c in PARAM_COLUMNS[component]]
    f += [1.0 if float(params.get(c, 0)) else 0.0
          for c in FLAG_COLUMNS.get(component, ())]
    for col, values in CATEGORICAL_COLUMNS.get(component, ()):
        v = str(params[col])
        if v not in values:
            raise LogicQueryError.nw(8150, component=component, column=col,
                                     value=v, known=values)
        f += [1.0 if v == known else 0.0 for known in values]
    f += [1.0 if nm == n else 0.0 for n in NODE_LIST]
    return f


def feature_vector(component: str, metric: str, nm: int, clock_ns: float,
                   params: Mapping[str, float], mode: Optional[str]) -> List[float]:
    modes = modes_for(component, metric)
    onehot = [0.0] * len(modes)
    if modes:
        onehot[modes.index(mode)] = 1.0
    return base_features(component, nm, clock_ns, params) + onehot


def feature_names(component: str, metric: str) -> List[str]:
    return (base_feature_names(component, metric)
            + [f"mode_{m}" for m in modes_for(component, metric)])


def n_inputs(component: str, metric: str) -> int:
    return len(feature_names(component, metric))


def scale_mask(component: str, metric: str) -> List[bool]:
    """Return True for each continuous input, which the scaler standardizes.

    Flags and one-hot inputs stay as they are.
    """
    n_cont = _n_continuous(component)
    total = n_inputs(component, metric)
    return [True] * n_cont + [False] * (total - n_cont)


class LogicMlp(nn.Module):
    def __init__(self, n_in: int, hidden: Sequence[int]):
        super().__init__()
        layers: List[nn.Module] = []
        last = n_in
        for h in hidden:
            layers += [nn.Linear(last, h), nn.ReLU()]
            last = h
        layers.append(nn.Linear(last, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def dataset_csv(dataset_dir: Path, component: str) -> Path:
    return Path(dataset_dir) / f"logic_{component}.csv"


def dataset_hash(dataset_dir: Path, components: Sequence[str] = COMPONENTS) -> str:
    """Return the sha256 of the CSV files of the trained components.

    The hash uses the raw bytes, in the sorted order of the components.
    """
    h = hashlib.sha256()
    for c in sorted(components):
        h.update(dataset_csv(dataset_dir, c).read_bytes())
    return h.hexdigest()


# -- characterized envelope ---------------------------------------------------
#
# The MLPs give an answer for each input. This includes an input that has no
# design point: a pipeline depth below the minimum of the RTL, or a clock
# faster than each implementation. The envelope records the range of the
# dataset. The provider uses it to change a depth that the RTL does not have,
# and to report an extrapolated parameter or clock. train_logic.py writes the
# envelope from the training CSVs, into the directory of the checkpoints.
# Thus the envelope always agrees with the trained data.

def envelope_path(model_dir: Path) -> Path:
    return Path(model_dir) / f"envelope__{VERSION}.json"


def _param_value(row: Mapping[str, Any], col: str) -> float:
    # An empty numeric parameter is 1, the same as in train_logic._mk.
    v = row.get(col, "")
    return float(v) if v not in ("", None) else 1.0


def config_key(component: str, params: Mapping[str, Any]) -> str:
    """Return the string that identifies one design configuration.

    The string contains the parameters, the flags, and the categorical
    values. It is the key of ``config_min_clock_ns``.
    """
    parts = [f"{c}={float(params[c]):g}" for c in PARAM_COLUMNS[component]]
    parts += [f"{c}={1 if float(params.get(c, 0) or 0) else 0}"
              for c in FLAG_COLUMNS.get(component, ())]
    parts += [f"{col}={params[col]}"
              for col, _ in CATEGORICAL_COLUMNS.get(component, ())]
    return ";".join(parts)


def build_envelope(dataset_dir: Path,
                   components: Sequence[str] = COMPONENTS) -> Dict[str, Any]:
    """Make the characterized envelope of each component.

    The envelope contains:

    - the range of each numeric parameter
    - the pipeline depths that the dataset has
    - the clock range of each node
    - the fastest clock of each configuration, for each node
    """
    import csv
    out: Dict[str, Any] = {"version": VERSION,
                           "dataset_sha256": dataset_hash(dataset_dir, components),
                           "components": {}}
    for component in components:
        with open(dataset_csv(dataset_dir, component), newline="") as fp:
            rows = list(csv.DictReader(fp))
        ranges: Dict[str, List[float]] = {}
        stages: set = set()
        clocks: Dict[str, List[float]] = {}
        fastest: Dict[str, Dict[str, float]] = {}
        for row in rows:
            params: Dict[str, Any] = {c: _param_value(row, c)
                                      for c in PARAM_COLUMNS[component]}
            params.update({c: _param_value(row, c)
                           for c in FLAG_COLUMNS.get(component, ())})
            params.update({col: row[col]
                           for col, _ in CATEGORICAL_COLUMNS.get(component, ())})
            for c in PARAM_COLUMNS[component]:
                lo_hi = ranges.setdefault(c, [params[c], params[c]])
                lo_hi[0] = min(lo_hi[0], params[c])
                lo_hi[1] = max(lo_hi[1], params[c])
            if "pipeline_stages" in params:
                stages.add(int(params["pipeline_stages"]))
            nm = str(node_nm(row["node"]))
            t = float(row["clock_period_ns"])
            c_lo_hi = clocks.setdefault(nm, [t, t])
            c_lo_hi[0] = min(c_lo_hi[0], t)
            c_lo_hi[1] = max(c_lo_hi[1], t)
            per_node = fastest.setdefault(nm, {})
            key = config_key(component, params)
            per_node[key] = min(per_node.get(key, t), t)
        out["components"][component] = {
            "params": ranges,
            "pipeline_stages": sorted(stages),
            "clock_ns": clocks,
            "config_min_clock_ns": fastest,
        }
    return out


def write_envelope(dataset_dir: Path, out_dir: Path,
                   components: Sequence[str] = COMPONENTS) -> Path:
    path = envelope_path(out_dir)
    path.write_text(json.dumps(build_envelope(dataset_dir, components),
                               indent=1, sort_keys=True))
    return path


def load_envelope(model_dir: Path) -> Optional[Dict[str, Any]]:
    path = envelope_path(model_dir)
    return json.loads(path.read_text()) if path.is_file() else None


def quartet_paths(model_dir: Path, component: str, metric: str) -> Dict[str, Path]:
    stem = f"{component}_{metric}__{VERSION}"
    return {
        "pt": model_dir / f"{stem}.pt",
        "scalers": model_dir / f"{stem}.scalers.json",
        "loss": model_dir / f"{stem}.loss.json",
        "meta": model_dir / f"{stem}.meta.json",
    }


def available(model_dir: Path, component: str) -> bool:
    return all(p.is_file()
               for m in METRICS
               for p in quartet_paths(Path(model_dir), component, m).values())


def save_quartet(model_dir: Path, component: str, metric: str, net: LogicMlp,
                 scalers: Mapping[str, Any], loss_spec: Mapping[str, Any],
                 meta: Mapping[str, Any]) -> None:
    paths = quartet_paths(Path(model_dir), component, metric)
    torch.save(net.state_dict(), paths["pt"])      # only the state_dict (§3.5)
    paths["scalers"].write_text(json.dumps(dict(scalers), indent=1))
    paths["loss"].write_text(json.dumps(dict(loss_spec), indent=1))
    paths["meta"].write_text(json.dumps(dict(meta), indent=1))


@dataclass
class LoadedModel:
    component: str
    metric: str
    net: LogicMlp
    x_mean: torch.Tensor
    x_std: torch.Tensor
    x_scale_mask: torch.Tensor
    y_mean: float
    y_std: float
    meta: Dict[str, Any]

    def predict_linear(self, rows: Sequence[Sequence[float]]) -> List[float]:
        """Return the linear values (10**log10) of the feature rows."""
        with torch.no_grad():
            x = torch.tensor(rows, dtype=torch.float32)
            xs = torch.where(self.x_scale_mask,
                             (x - self.x_mean) / self.x_std, x)
            y_log = self.net(xs) * self.y_std + self.y_mean
            return [10.0 ** v for v in y_log.tolist()]


def load_one(model_dir: Path, component: str, metric: str) -> LoadedModel:
    paths = quartet_paths(Path(model_dir), component, metric)
    meta = json.loads(paths["meta"].read_text())
    scalers = json.loads(paths["scalers"].read_text())
    net = LogicMlp(int(meta["n_in"]), list(meta["arch"]))
    state = torch.load(paths["pt"], map_location="cpu", weights_only=True)
    net.load_state_dict(state)
    net.eval()
    return LoadedModel(
        component=component,
        metric=metric,
        net=net,
        x_mean=torch.tensor(scalers["x_mean"], dtype=torch.float32),
        x_std=torch.tensor(scalers["x_std"], dtype=torch.float32),
        x_scale_mask=torch.tensor(scalers["x_scale_mask"], dtype=torch.bool),
        y_mean=float(scalers["y_mean"]),
        y_std=float(scalers["y_std"]),
        meta=meta,
    )
