from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import torch
import torch.nn as nn


ESTIMATOR_SPEC = {
    "primitive": "adder",
    "entrypoints": {
        "energy": "get_energy",
        "train": "train",
        "switching": "estimate_switching_energy",
    },
    "parameters": {
        "required": [
            {"name": "bitwidth", "type": "int", "arch_keys": ["bitwidth", "bits", "width"]},
        ],
        "optional": [
            {"name": "activity", "type": "float", "arch_keys": ["activity"], "default": 0.5},
        ],
    },
}


# ---- MLP estimator metadata (example knobs you can version-control) ----
MLP_DEPTH: int = 3
INPUT_DIM: int = 2
HIDDEN_DIM: int = 32
OUTPUT_DIM: int = 1


@dataclass(frozen=True)
class AdderEstimatorConfig:
    mlp_depth: int = MLP_DEPTH
    input_dim: int = INPUT_DIM
    hidden_dim: int = HIDDEN_DIM
    output_dim: int = OUTPUT_DIM


def build_mlp(cfg: AdderEstimatorConfig) -> nn.Module:
    layers: list[nn.Module] = []
    in_dim = cfg.input_dim
    for _ in range(cfg.mlp_depth):
        layers.append(nn.Linear(in_dim, cfg.hidden_dim))
        layers.append(nn.ReLU())
        in_dim = cfg.hidden_dim
    layers.append(nn.Linear(in_dim, cfg.output_dim))
    return nn.Sequential(*layers)


def load_model(
    weights_path: Optional[str] = None,
    device: Optional[str] = None,
    cfg: Optional[AdderEstimatorConfig] = None,
) -> nn.Module:
    """Load the estimator model. If weights_path is None, returns an untrained model skeleton."""
    cfg = cfg or AdderEstimatorConfig()
    dev = torch.device(device or "cpu")

    model = build_mlp(cfg).to(dev)
    model.eval()

    if weights_path:
        state = torch.load(weights_path, map_location=dev)
        model.load_state_dict(state)

    return model


def _features_to_tensor(features: Dict[str, Any], device: torch.device) -> torch.Tensor:
    """
    Convert features to a fixed-size tensor.
    Skeleton mapping: [bitwidth, activity].
    """
    bitwidth = float(features.get("bitwidth", features.get("bits", 8)))
    activity = float(features.get("activity", 0.5))
    x = torch.tensor([bitwidth, activity], dtype=torch.float32, device=device).view(1, -1)
    return x


@torch.no_grad()
def infer(model: nn.Module, features: Dict[str, Any]) -> float:
    device = next(model.parameters()).device
    x = _features_to_tensor(features, device)
    y = model(x).view(-1)
    return float(y.item())


def get_energy(
    features: Optional[Dict[str, Any]] = None,
    *,
    weights_path: Optional[str] = None,
    device: Optional[str] = None,
) -> float:
    """Required callable: returns an energy estimate for an adder."""
    features = features or {"bitwidth": 8, "activity": 0.5}
    model = load_model(weights_path=weights_path, device=device)
    return infer(model, features)


def train(
    model: nn.Module,
    dataset: Sequence[Tuple[Dict[str, Any], float]],
    *,
    epochs: int = 5,
    lr: float = 1e-3,
    device: Optional[str] = None,
) -> nn.Module:
    """Training skeleton: dataset items of (features_dict, target_energy)."""
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = model.to(dev)
    model.train()

    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    for _ in range(epochs):
        for feat, target in dataset:
            x = _features_to_tensor(feat, dev)
            y_true = torch.tensor([float(target)], device=dev, dtype=torch.float32)

            y_pred = model(x).view(-1)
            loss = loss_fn(y_pred, y_true)

            opt.zero_grad()
            loss.backward()
            opt.step()

    model.eval()
    return model


def estimate_switching_energy(bitwidth: int, activity: float) -> float:
    """Unique helper (placeholder) – callable via EstimatorHost.execute("adder", ...)."""
    return float(bitwidth) * float(activity) * 1e-3
