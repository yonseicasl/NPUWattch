"""The torch part of the SRAM estimator.

``sram.py`` loads this file with ``importlib``, by file path and only if it is
necessary. It is not a package import. Thus ``sram.py`` uses only the standard
library, and ``EstimatorHost`` can execute it with runpy. All SRAM code that
uses torch is in this file, in the self-contained estimator directory
``src/npuwattch_estimators/sram/``:

- The checkpoint quartet format:
  ``<metric>__v1.{pt,scalers.json,loss.json,meta.json}`` (manual §3.5). The
  ``.pt`` file has only the state_dict. The other files of the quartet hold
  all transforms. Inference does not fit them again.
- The MLP definition and the vocabulary of features and one-hots.
  ``train_sram.py`` also uses them.
- ``MlpTilePointSource``: the TilePointSource implementation. It predicts the
  ABSOLUTE log10 costs of one tile at the (ΔV, T) of the query. The units are
  dynamic pJ without leakage, mW, ns, and um2.

The timing model predicts the composed access times ``t_read`` and
``t_write``. ``compose_timing`` has the Appendix-A delay composition that
makes these targets from the four raw paths.
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

from npuwattch.diagnostics import warning
from npuwattch_estimators.errors import EstimatorQueryError, SramCheckpointError

VERSION = "v1"
MODEL_NAMES = ("energy", "leakage", "timing", "area")
ENERGY_OPS = ("rd_1to1", "rd_1to0", "wr_same", "wr_toggle",
              "dec_act", "dec_flip", "dec_idle")
LEAK_COMPS = ("array", "dec")
# The timing targets are composed access times, not raw paths.
# - The raw dec_wlen_wl data has discontinuities from synthesis: the decoder
#   structure and drive strength change with the row count. A smooth model
#   of (log2 rows, log2 cols) cannot fit them.
# - The estimator uses the composed targets (the "access time" of manual
#   §5.1). The smooth array terms make the discontinuities smaller.
TIMING_TARGETS = ("t_read", "t_write")
AREA_COMPS = ("array", "dec")
ONE_HOTS: Dict[str, Tuple[str, ...]] = {
    "energy": ENERGY_OPS,
    "leakage": LEAK_COMPS,
    "timing": TIMING_TARGETS,
    "area": AREA_COMPS,
}
TARGET_UNITS = {"energy": "pJ", "leakage": "mW", "timing": "ns", "area": "um2"}
DEFAULT_ARCH: Dict[str, List[int]] = {
    "energy": [128, 128, 128],
    "leakage": [128, 128, 128],   # the most difficult data: exponential in V and T
    "timing": [128, 128, 128],
    "area": [64, 64],
}


def node_nm(node: str) -> int:
    m = re.search(r"(\d+)", node)
    if not m:
        raise EstimatorQueryError.nw(8002, node=node)
    return int(m.group(1))


NODE_LIST = (5, 7, 10, 16, 20)


def base_feature_names(model: str) -> List[str]:
    names = ["log10_node_nm", "log2_rows", "log2_cols"]
    if model != "area":
        names += ["voltage_offset_V", "temperature_C"]
    if model == "leakage":
        names += ["inv_T_1000K"]                # 1000/(T+273.15), the Arrhenius axis
    # A one-hot for each node, together with the numeric node feature.
    # - It lets the model change the trend at a device transition.
    # - Example: at +0.1V/85C, the leakage of the 20nm node increases ~7.5x,
    #   but that of the FinFET nodes increases ~1.3x.
    # - With only a numeric node feature, the 20nm behavior changes the 16nm
    #   prediction.
    # - The device-family one-hot of manual §5.2 has the same purpose. Here
    #   each dataset node has its own flag.
    names += [f"node_is_{n}nm" for n in NODE_LIST]
    return names


def _n_continuous(model: str) -> int:
    return 3 + (2 if model != "area" else 0) + (1 if model == "leakage" else 0)


def base_features(model: str, nm: int, rows: int, cols: int,
                  dv: float, temp: float) -> List[float]:
    f = [math.log10(nm), math.log2(rows), math.log2(cols)]
    if model != "area":
        f += [dv, temp]
    if model == "leakage":
        f += [1000.0 / (temp + 273.15)]
    f += [1.0 if nm == n else 0.0 for n in NODE_LIST]
    return f


def feature_vector(model: str, nm: int, rows: int, cols: int,
                   dv: float, temp: float, op: str) -> List[float]:
    onehot = [0.0] * len(ONE_HOTS[model])
    onehot[ONE_HOTS[model].index(op)] = 1.0
    return base_features(model, nm, rows, cols, dv, temp) + onehot


def n_inputs(model: str) -> int:
    return len(base_feature_names(model)) + len(ONE_HOTS[model])


def scale_mask(model: str) -> List[bool]:
    """Return the mask of input columns to standardize.

    True is a continuous column. The one-hot columns are False and do not
    change.
    """
    n_cont = _n_continuous(model)
    total = len(base_feature_names(model)) + len(ONE_HOTS[model])
    return [True] * n_cont + [False] * (total - n_cont)


class SramMlp(nn.Module):
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


def dataset_hash(dataset_dir: Path) -> str:
    """Return the sha256 of the raw bytes of the two dataset CSVs (array, then decoder)."""
    h = hashlib.sha256()
    for name in ("sram_array.csv", "sram_decoder.csv"):
        h.update((dataset_dir / name).read_bytes())
    return h.hexdigest()


def quartet_paths(model_dir: Path, model: str) -> Dict[str, Path]:
    stem = f"{model}__{VERSION}"
    return {
        "pt": model_dir / f"{stem}.pt",
        "scalers": model_dir / f"{stem}.scalers.json",
        "loss": model_dir / f"{stem}.loss.json",
        "meta": model_dir / f"{stem}.meta.json",
    }


def available(model_dir: Path) -> bool:
    return all(p.is_file()
               for m in MODEL_NAMES for p in quartet_paths(Path(model_dir), m).values())


def save_quartet(model_dir: Path, model: str, net: SramMlp, scalers: Mapping[str, Any],
                 loss_spec: Mapping[str, Any], meta: Mapping[str, Any]) -> None:
    paths = quartet_paths(Path(model_dir), model)
    torch.save(net.state_dict(), paths["pt"])      # the state_dict ONLY (manual §3.5)
    paths["scalers"].write_text(json.dumps(dict(scalers), indent=1))
    paths["loss"].write_text(json.dumps(dict(loss_spec), indent=1))
    paths["meta"].write_text(json.dumps(dict(meta), indent=1))


@dataclass
class LoadedModel:
    name: str
    net: SramMlp
    x_mean: torch.Tensor
    x_std: torch.Tensor
    x_scale_mask: torch.Tensor
    y_mean: float
    y_std: float
    meta: Dict[str, Any]

    def predict_linear(self, rows: Sequence[Sequence[float]]) -> List[float]:
        """Predict linear values (10**log10) for a list of feature rows."""
        with torch.no_grad():
            x = torch.tensor(rows, dtype=torch.float32)
            xs = torch.where(self.x_scale_mask,
                             (x - self.x_mean) / self.x_std, x)
            y_log = self.net(xs) * self.y_std + self.y_mean
            return [10.0 ** v for v in y_log.tolist()]


@dataclass
class MlpBundle:
    model_dir: Path
    models: Dict[str, LoadedModel]
    dataset_sha256: str                       # from the meta files, which must all agree

    def summary(self) -> Dict[str, Any]:
        return {
            "version": VERSION,
            "model_dir": str(self.model_dir),
            "dataset_sha256": self.dataset_sha256,
            "models": {m: {"arch": lm.meta.get("arch"),
                           "val_mape": lm.meta.get("val_mape"),
                           "test_mape": lm.meta.get("test_mape"),
                           "date": lm.meta.get("date")}
                       for m, lm in self.models.items()},
        }


_BUNDLE_CACHE: Dict[str, MlpBundle] = {}


def _load_one(model_dir: Path, model: str) -> LoadedModel:
    paths = quartet_paths(model_dir, model)
    meta = json.loads(paths["meta"].read_text())
    scalers = json.loads(paths["scalers"].read_text())
    net = SramMlp(int(meta["n_in"]), list(meta["arch"]))
    state = torch.load(paths["pt"], map_location="cpu", weights_only=True)
    net.load_state_dict(state)
    net.eval()
    return LoadedModel(
        name=model,
        net=net,
        x_mean=torch.tensor(scalers["x_mean"], dtype=torch.float32),
        x_std=torch.tensor(scalers["x_std"], dtype=torch.float32),
        x_scale_mask=torch.tensor(scalers["x_scale_mask"], dtype=torch.bool),
        y_mean=float(scalers["y_mean"]),
        y_std=float(scalers["y_std"]),
        meta=meta,
    )


def load_bundle(model_dir: Path,
                dataset_dir: Optional[Path] = None) -> Tuple[MlpBundle, List[str]]:
    """Load and cache the four quartets.

    Give a warning if the dataset hash is different from that of the training.
    """
    model_dir = Path(model_dir).resolve()
    key = str(model_dir)
    bundle = _BUNDLE_CACHE.get(key)
    if bundle is None:
        models = {m: _load_one(model_dir, m) for m in MODEL_NAMES}
        hashes = {lm.meta.get("dataset_sha256") for lm in models.values()}
        if len(hashes) != 1:
            raise SramCheckpointError.nw(8250, path=model_dir)
        bundle = MlpBundle(model_dir=model_dir, models=models,
                           dataset_sha256=hashes.pop())
        _BUNDLE_CACHE[key] = bundle
    warnings: List[str] = []
    if dataset_dir is not None:
        live = dataset_hash(Path(dataset_dir))
        if live != bundle.dataset_sha256:
            warnings.append(warning(8251,
                                    trained_sha=bundle.dataset_sha256[:12],
                                    live_sha=live[:12]))
    return bundle, warnings


def compose_timing(dec_wlen_wl: float, rd_delay: float,
                   wr_bl: float, wr_cell: float) -> Tuple[float, float]:
    """Return (t_read, t_write): the Appendix-A composition of the four raw paths."""
    return dec_wlen_wl + rd_delay, max(dec_wlen_wl, wr_bl) + wr_cell


class MlpTilePointSource:
    """The TilePointSource that uses the trained MLPs (absolute predictions).

    Each query makes one instance with the clamped (ΔV, T). ``tile_costs``
    has the signature of the TilePointSource interface. It accepts the
    PvtScale ``k`` of the table source but does not use it, because the
    absolute predictions include the PVT effect. ``tile_costs_cls`` is the
    TileCosts dataclass of sram.py. The caller supplies it to prevent a
    circular load.
    """

    def __init__(self, bundle: MlpBundle, dv: float, temp: float,
                 tile_costs_cls: Any):
        self._b = bundle
        self._dv = float(dv)
        self._temp = float(temp)
        self._cls = tile_costs_cls
        self._cache: Dict[Tuple[str, int, int], Any] = {}

    def _predict(self, model: str, nm: int, rows: int, cols: int) -> Dict[str, float]:
        ops = ONE_HOTS[model]
        feats = [feature_vector(model, nm, rows, cols, self._dv, self._temp, op)
                 for op in ops]
        vals = self._b.models[model].predict_linear(feats)
        return dict(zip(ops, vals))

    def tile_costs(self, node: str, rows: int, cols: int, k: Any) -> Any:
        key = (node, rows, cols)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        nm = node_nm(node)
        e = self._predict("energy", nm, rows, cols)
        l = self._predict("leakage", nm, rows, cols)
        t = self._predict("timing", nm, rows, cols)
        a = self._predict("area", nm, rows, cols)
        t_read, t_write = t["t_read"], t["t_write"]
        tc = self._cls(
            rows=rows, cols=cols,
            rd_1to1_dyn_pJ=e["rd_1to1"],
            rd_1to0_dyn_pJ=e["rd_1to0"],
            wr_same_dyn_pJ=e["wr_same"],
            wr_toggle_dyn_pJ=e["wr_toggle"],
            dec_act_dyn_pJ=e["dec_act"],
            dec_flip_dyn_pJ=e["dec_flip"],
            dec_idle_dyn_pJ=e["dec_idle"],
            leak_array_mW=l["array"],
            leak_dec_mW=l["dec"],
            t_read_ns=t_read,
            t_write_ns=t_write,
            array_area_um2=a["array"],
            dec_area_um2=a["dec"],
        )
        self._cache[key] = tc
        return tc
