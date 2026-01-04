from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import torch
import torch.nn as nn


ESTIMATOR_SPEC = {
    "primitive": "crossbar",
    "entrypoints": {
        "energy": "get_energy",
        "train": "train",
        "conductance": "estimate_conductance_energy",
    },
    "parameters": {
        "required": [
            {"name": "inputs", "type": "int", "arch_keys": ["inputs", "in", "in_dim", "rows"]},
            {"name": "outputs", "type": "int", "arch_keys": ["outputs", "out", "out_dim", "cols"]},
        ],
        "optional": [
            {"name": "bitwidth", "type": "int", "arch_keys": ["bitwidth", "bits"], "default": 8},
            {"name": "activity", "type": "float", "arch_keys": ["activity"], "default": 0.5},
        ],
    },
}


MLP_DEPTH: int = 4
INPUT_DIM: int = 3
HIDDEN_DIM: int = 64
OUTPUT_DIM: int = 1


@dataclass(frozen=True)
class CrossbarEstimatorConfig:
    mlp_depth: int = MLP_DEPTH
    input_dim: int = INPUT_DIM
    hidden_dim: int = HIDDEN_DIM
    output_dim: int = OUTPUT_DIM


def build_mlp(cfg: CrossbarEstimatorConfig) -> nn.Module:
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
    cfg: Optional[CrossbarEstimatorConfig] = None,
) -> nn.Module:
    cfg = cfg or CrossbarEstimatorConfig()
    dev = torch.device(device or "cpu")

    model = build_mlp(cfg).to(dev)
    model.eval()

    if weights_path:
        state = torch.load(weights_path, map_location=dev)
        model.load_state_dict(state)

    return model


def _features_to_tensor(features: Dict[str, Any], device: torch.device) -> torch.Tensor:
    """Skeleton mapping: [inputs, outputs, activity]"""
    inputs = float(features.get("inputs", features.get("rows", 128)))
    outputs = float(features.get("outputs", features.get("cols", 128)))
    activity = float(features.get("activity", 0.5))
    x = torch.tensor([inputs, outputs, activity], dtype=torch.float32, device=device).view(1, -1)
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
    features = features or {"inputs": 128, "outputs": 128, "activity": 0.5}
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


def estimate_conductance_energy(inputs: int, outputs: int, activity: float) -> float:
    """Unique helper (placeholder) – callable via EstimatorHost.execute("crossbar", ...)."""
    return float(inputs * outputs) * float(activity) * 1e-6
