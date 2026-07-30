"""Torch-side vocabulary + net + quartet IO for the LOGIC primitive MLPs.

Deliberately the same shape as ``src/estimators/sram/sram_mlp.py`` (user
decision 2026-07-28: same MLP structure and code as SRAM, for consistency):
state_dict-only ``.pt`` with all transforms frozen in the JSON sidecars
(manual §3.5), absolute log10 targets, ReLU MLP, seed-42 reproducibility.

Differences from SRAM, driven by what the logic sweep measures:

- one model per **(component, metric)**: 7 components (fpadd/fpmul/fpmac/
  intadd/intmul/intmac/fpsfu; mxfpmac joins when its sweep completes) ×
  4 metrics (energy/leakage/timing/area) — quartets are named
  ``<component>_<metric>__v1.*``;
- ``stim_mode`` is a one-hot INPUT for the power metrics (energy/leakage):
  the projection layer requests per-mode unit costs (COMPOUND_SCHEMA §6).
  ``none`` (the unvectored row) is included as a mode per the 2026-07-28
  decision — drop it only if the A/B in the eval report shows clear damage;
- the adaptive loss axes are **SCR/SAR** (manual §5.3 as written; the SRAM
  models adapted it to the target axis because SPICE rows have no SCR/SAR);
- ``log10_clock_ns`` is an input for EVERY metric: each design was implemented
  against its clock constraint, so area/timing/power all move with it;
- no PVT features: the current logic dataset is TT / 25 °C / nominal-V only
  (user decision 2026-07-28 — constant columns would break the scalers).
  PVT-swept datasets bump VERSION and re-add the axes.
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

VERSION = "v1"

COMPONENTS = ("fpadd", "fpmul", "fpmac", "intadd", "intmul", "intmac", "fpsfu")
METRICS = ("energy", "leakage", "timing", "area")

#: dataset CSV column -> metric target (absolute log10 of these, linear units)
TARGET_COLUMNS = {
    "energy": "dyn_energy_pJ",          # per-cycle dynamic energy at the mode
    "leakage": "leak_power_mW",
    "timing": "pnr_crit_path_ns",
    "area": "pnr_total_area_um2",
}
TARGET_UNITS = {"energy": "pJ", "leakage": "mW", "timing": "ns", "area": "um2"}

#: metrics whose rows are per stim_mode (one-hot input); timing/area are
#: implementation properties — one row per design, no mode axis.
MODE_METRICS = ("energy", "leakage")

NODE_LIST = (5, 7, 10, 16, 20)

#: integer design params per component (dataset columns; log2-transformed
#: inputs, per the size-like→log convention). Order is frozen — it is the
#: feature order.
PARAM_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "fpadd": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "fpmul": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "fpmac": ("exp_bits", "mantissa_bits", "pipeline_stages"),
    "intadd": ("a_width", "b_width", "out_width", "pipeline_stages"),
    "intmul": ("a_width", "b_width", "out_width", "pipeline_stages"),
    "intmac": ("a_width", "b_width", "out_width", "acc_width", "pipeline_stages"),
    "fpsfu": ("exp_bits", "mantissa_bits", "sfu_segments", "pipeline_stages"),
}

#: binary design flags (0/1 inputs, unscaled)
FLAG_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "fpsfu": ("sfu_op_exp", "sfu_op_trig", "sfu_op_hyp", "sfu_op_erf",
              "sfu_op_relu"),
}

#: frozen stim_mode one-hot order per component (mirrors POWER_MODES + 'none',
#: the unvectored row — see module docstring).
STIM_MODES: Dict[str, Tuple[str, ...]] = {
    "fpadd": ("none", "random"),
    "fpmul": ("none", "random"),
    "intadd": ("none", "random"),
    "intmul": ("none", "random"),
    "fpmac": ("none", "random", "hold_b", "sparse50", "idle"),
    "intmac": ("none", "random", "hold_b", "sparse50", "idle"),
    "fpsfu": ("none", "random", "exp", "trig", "hyp", "erf", "idle"),
}

DEFAULT_ARCH: Dict[str, List[int]] = {
    "energy": [128, 128, 128],
    "leakage": [128, 128, 128],
    "timing": [64, 64],                 # per-design rows only (no mode axis)
    "area": [64, 64],
}


def node_nm(node: str) -> int:
    m = re.search(r"(\d+)", node)
    if not m:
        raise ValueError(f"cannot parse node '{node}'")
    return int(m.group(1))


def modes_for(component: str, metric: str) -> Tuple[str, ...]:
    return STIM_MODES[component] if metric in MODE_METRICS else ()


def base_feature_names(component: str, metric: str) -> List[str]:
    names = ["log10_node_nm", "log10_clock_ns"]
    names += [f"log2_{c}" for c in PARAM_COLUMNS[component]]
    names += list(FLAG_COLUMNS.get(component, ()))
    names += [f"node_is_{n}nm" for n in NODE_LIST]
    return names


def _n_continuous(component: str) -> int:
    return 2 + len(PARAM_COLUMNS[component])


def base_features(component: str, nm: int, clock_ns: float,
                  params: Mapping[str, float]) -> List[float]:
    f = [math.log10(nm), math.log10(clock_ns)]
    f += [math.log2(max(float(params[c]), 1.0)) for c in PARAM_COLUMNS[component]]
    f += [1.0 if float(params.get(c, 0)) else 0.0
          for c in FLAG_COLUMNS.get(component, ())]
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
    """True = standardize (continuous); flags/one-hots left as-is."""
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
    """sha256 over the trained components' CSVs (sorted, raw bytes)."""
    h = hashlib.sha256()
    for c in sorted(components):
        h.update(dataset_csv(dataset_dir, c).read_bytes())
    return h.hexdigest()


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
    torch.save(net.state_dict(), paths["pt"])      # state_dict ONLY (§3.5)
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
        """Feature rows -> linear-domain values (10**log10)."""
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
