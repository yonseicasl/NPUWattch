"""Regfile Estimator Module.

This module provides MLP-based estimation for:
- Energy/Power consumption (based on regfile_power.py)
- Area (based on regfile_area.py)
- Timing (new addition following the same pattern)

Each estimator uses a 6-layer MLP architecture trained on characterized data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

###############################################################################
# ESTIMATOR_SPEC - Defines the interface for the EstimatorHost
###############################################################################

ESTIMATOR_SPEC = {
    "primitive": "regfile",
    "version": "1.0",
    "description": "Register file energy, area, and timing estimator using MLP models",
    "entrypoints": {
        "energy": "get_energy",
        "area": "get_area",
        "timing": "get_timing",
        "train_energy": "train_energy_model",
        "train_area": "train_area_model",
        "train_timing": "train_timing_model",
    },
    "parameters": {
        "required": [
            {"name": "node", "type": "int", "arch_keys": ["node", "technology", "tech_node"]},
            {"name": "depth", "type": "int", "arch_keys": ["depth", "entries", "num_entries"]},
            {"name": "bw", "type": "int", "arch_keys": ["bw", "width", "bitwidth", "datawidth"]},
        ],
        "optional": [
            {"name": "n_banks", "type": "int", "arch_keys": ["n_banks", "banks"], "default": 1},
            {"name": "n_ports", "type": "int", "arch_keys": ["n_ports", "ports", "num_ports", "nports"], "default": 1},
        ],
    },
    "models": {
        "energy": "regfile_energy_model.pth",
        "area": "regfile_area_model.pth",
        "timing": "regfile_timing_model.pth",
    },
}

# Get the directory where this module is located (for model paths)
_MODULE_DIR = Path(__file__).parent
EPS = 1e-9


###############################################################################
# 1) Dataset Classes
###############################################################################

class PowerDataset(Dataset):
    """
    Reads CSV file and generates:
      X = [node, log2(depth), log8(bw)]
      Y = log10(power_total)
    """
    def __init__(self, csv_file: str):
        super().__init__()
        df = pd.read_csv(csv_file)
        self.node = df['node'].values.astype(np.float32)
        self.depth = df['depth'].values.astype(np.float32)
        self.bw = df['bw'].values.astype(np.float32)
        self.power = df['power_total'].values.astype(np.float32)

    def __len__(self):
        return len(self.node)

    def __getitem__(self, idx):
        n = self.node[idx]
        d = np.log2(self.depth[idx] + EPS)
        b = np.log2(self.bw[idx] + EPS) / 3  # log8
        X = np.array([n, d, b], dtype=np.float32)
        Y = np.array([np.log10(self.power[idx] + EPS)], dtype=np.float32)
        return X, Y


class AreaDataset(Dataset):
    """
    Reads CSV file and generates:
      X = [node, log2(depth), log2(bw)]
      Y = log10(area)
    """
    def __init__(self, csv_file: str):
        super().__init__()
        df = pd.read_csv(csv_file)
        self.node = df['node'].values.astype(np.float32)
        self.depth = df['depth'].values.astype(np.float32)
        self.bw = df['bw'].values.astype(np.float32)
        self.area = df['area'].values.astype(np.float32)

    def __len__(self):
        return len(self.node)

    def __getitem__(self, idx):
        n = self.node[idx]
        d = np.log2(self.depth[idx] + EPS)
        b = np.log2(self.bw[idx] + EPS)
        X = np.array([n, d, b], dtype=np.float32)
        Y = np.array([np.log10(self.area[idx] + EPS)], dtype=np.float32)
        return X, Y


class TimingDataset(Dataset):
    """
    Reads CSV file and generates:
      X = [node, log2(depth), log2(bw)]
      Y = log10(timing)
    """
    def __init__(self, csv_file: str):
        super().__init__()
        df = pd.read_csv(csv_file)
        self.node = df['node'].values.astype(np.float32)
        self.depth = df['depth'].values.astype(np.float32)
        self.bw = df['bw'].values.astype(np.float32)
        self.timing = df['timing'].values.astype(np.float32)

    def __len__(self):
        return len(self.node)

    def __getitem__(self, idx):
        n = self.node[idx]
        d = np.log2(self.depth[idx] + EPS)
        b = np.log2(self.bw[idx] + EPS)
        X = np.array([n, d, b], dtype=np.float32)
        Y = np.array([np.log10(self.timing[idx] + EPS)], dtype=np.float32)
        return X, Y


###############################################################################
# 2) MLP Model Classes
###############################################################################

class PowerModel(nn.Module):
    """
    Predicts log10(power_total) from 3 inputs using a 6-layer MLP + ReLU.
    """
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(3, 240)
        self.fc2 = nn.Linear(240, 180)
        self.fc3 = nn.Linear(180, 120)
        self.fc4 = nn.Linear(120, 80)
        self.fc5 = nn.Linear(80, 40)
        self.fc_out = nn.Linear(40, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))
        x = F.relu(self.fc5(x))
        return self.fc_out(x)


class AreaModel(nn.Module):
    """
    Predicts log10(area) from 3 inputs using a 6-layer MLP + ReLU.
    """
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(3, 240)
        self.fc2 = nn.Linear(240, 180)
        self.fc3 = nn.Linear(180, 120)
        self.fc4 = nn.Linear(120, 80)
        self.fc5 = nn.Linear(80, 40)
        self.fc_out = nn.Linear(40, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))
        x = F.relu(self.fc5(x))
        return self.fc_out(x)


class TimingModel(nn.Module):
    """
    Predicts log10(timing) from 3 inputs using a 6-layer MLP + ReLU.
    """
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(3, 240)
        self.fc2 = nn.Linear(240, 180)
        self.fc3 = nn.Linear(180, 120)
        self.fc4 = nn.Linear(120, 80)
        self.fc5 = nn.Linear(80, 40)
        self.fc_out = nn.Linear(40, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))
        x = F.relu(self.fc5(x))
        return self.fc_out(x)


###############################################################################
# 3) Training Routine
###############################################################################

def _train_model_generic(
    dataset: Dataset,
    model: nn.Module,
    epochs: int = 100,
    batch_size: int = 32,
    lr: float = 1e-3,
    validation_split: float = 0.2,
    verbose: bool = True,
) -> nn.Module:
    """
    Generic training routine for MLP models using MSE loss + Adam optimizer.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    # Train/val split
    train_size = int((1 - validation_split) * len(dataset))
    val_size = len(dataset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for X, Y in train_loader:
            X, Y = X.to(device), Y.to(device)
            optimizer.zero_grad()
            pred = model(X)
            loss = criterion(pred, Y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * X.size(0)
        avg_train = train_loss / len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X, Y in val_loader:
                X, Y = X.to(device), Y.to(device)
                val_loss += criterion(model(X), Y).item() * X.size(0)
        avg_val = val_loss / len(val_loader.dataset)

        if verbose and (epoch % 50 == 0 or epoch == 1):
            print(f"[INFO] Epoch [{epoch}/{epochs}] - Train MSE: {avg_train:.6f}, Val MSE: {avg_val:.6f}")

    model.eval()
    return model


###############################################################################
# 4) Save and Load Routines
###############################################################################

def _get_model_path(model_type: str) -> Path:
    """Get the default path for a model file."""
    model_files = ESTIMATOR_SPEC["models"]
    filename = model_files.get(model_type, f"regfile_{model_type}_model.pth")
    return _MODULE_DIR / filename


def save_model(model: nn.Module, path: Union[str, Path]) -> None:
    """Save model parameters to disk."""
    torch.save(model.state_dict(), str(path))
    print(f"[INFO] Model saved to {path}")


def load_model(model_class, path: Union[str, Path]) -> Optional[nn.Module]:
    """Load model from disk."""
    path = Path(path)
    if not path.exists():
        return None
    model = model_class()
    model.load_state_dict(torch.load(str(path), map_location=torch.device('cpu')))
    model.eval()
    return model


def load_energy_model(path: Optional[Union[str, Path]] = None) -> Optional[PowerModel]:
    """Load the energy/power model from disk."""
    if path is None:
        path = _get_model_path("energy")
    return load_model(PowerModel, path)


def load_area_model(path: Optional[Union[str, Path]] = None) -> Optional[AreaModel]:
    """Load the area model from disk."""
    if path is None:
        path = _get_model_path("area")
    return load_model(AreaModel, path)


def load_timing_model(path: Optional[Union[str, Path]] = None) -> Optional[TimingModel]:
    """Load the timing model from disk."""
    if path is None:
        path = _get_model_path("timing")
    return load_model(TimingModel, path)


###############################################################################
# 5) Predict Routines
###############################################################################

def predict_power(model: PowerModel, params: Dict[str, Any]) -> float:
    """
    Single-sample prediction for power/energy.
    Uses log8 for bw (log2/3).
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    n = float(params['node'])
    d = np.log2(float(params['depth']) + EPS)
    b = np.log2(float(params['bw']) + EPS) / 3  # log8

    arr = np.array([n, d, b], dtype=np.float32)
    x = torch.from_numpy(arr).unsqueeze(0).to(device)

    with torch.no_grad():
        out_log10 = model(x)
        power = torch.pow(10.0, out_log10)

    return power.cpu().item()


def predict_area(model: AreaModel, params: Dict[str, Any]) -> float:
    """
    Single-sample prediction for area.
    Uses log2 for bw.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    n = float(params['node'])
    d = np.log2(float(params['depth']) + EPS)
    b = np.log2(float(params['bw']) + EPS)

    arr = np.array([n, d, b], dtype=np.float32)
    x = torch.from_numpy(arr).unsqueeze(0).to(device)

    with torch.no_grad():
        out_log10 = model(x)
        area = torch.pow(10.0, out_log10)

    return area.cpu().item()


def predict_timing(model: TimingModel, params: Dict[str, Any]) -> float:
    """
    Single-sample prediction for timing.
    Uses log2 for bw.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    n = float(params['node'])
    d = np.log2(float(params['depth']) + EPS)
    b = np.log2(float(params['bw']) + EPS)

    arr = np.array([n, d, b], dtype=np.float32)
    x = torch.from_numpy(arr).unsqueeze(0).to(device)

    with torch.no_grad():
        out_log10 = model(x)
        timing = torch.pow(10.0, out_log10)

    return timing.cpu().item()


###############################################################################
# 6) Training Entry Points (for EstimatorHost)
###############################################################################

def train_energy_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 8,
    lr: float = 1e-3,
) -> PowerModel:
    """Train the energy/power model on a CSV dataset."""
    print(f"[INFO] Training energy model from {csv_file}")
    dataset = PowerDataset(csv_file)
    model = PowerModel()
    trained = _train_model_generic(dataset, model, epochs, batch_size, lr)

    if output_path is None:
        output_path = _get_model_path("energy")
    save_model(trained, output_path)

    return trained


def train_area_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 10,
    lr: float = 1e-3,
) -> AreaModel:
    """Train the area model on a CSV dataset."""
    print(f"[INFO] Training area model from {csv_file}")
    dataset = AreaDataset(csv_file)
    model = AreaModel()
    trained = _train_model_generic(dataset, model, epochs, batch_size, lr)

    if output_path is None:
        output_path = _get_model_path("area")
    save_model(trained, output_path)

    return trained


def train_timing_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 10,
    lr: float = 1e-3,
) -> TimingModel:
    """Train the timing model on a CSV dataset."""
    print(f"[INFO] Training timing model from {csv_file}")
    dataset = TimingDataset(csv_file)
    model = TimingModel()
    trained = _train_model_generic(dataset, model, epochs, batch_size, lr)

    if output_path is None:
        output_path = _get_model_path("timing")
    save_model(trained, output_path)

    return trained


###############################################################################
# 7) Public API - Entry Points for EstimatorHost
###############################################################################

def _normalize_params(features: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parameter names to internal format."""
    # Map alternative key names
    node = features.get('node', features.get('technology', features.get('tech_node', 7)))
    
    # Parse technology node from string like "45nm"
    if isinstance(node, str):
        import re
        match = re.search(r'(\d+)', node)
        if match:
            node = int(match.group(1))
        else:
            node = 7
    
    depth = features.get('depth', features.get('entries', features.get('num_entries', 64)))
    bw = features.get('bw', features.get('width', features.get('bitwidth', features.get('datawidth', 32))))
    
    return {
        'node': node,
        'depth': depth,
        'bw': bw,
    }


def get_energy(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
) -> Optional[float]:
    """
    Get energy estimation for given features.

    Args:
        features: Dictionary with 'node', 'depth', 'bw' (or alternatives)
        model_path: Optional path to model weights

    Returns:
        Estimated energy value or None if model not found
    """
    if features is None:
        features = {"node": 7, "depth": 64, "bw": 32}

    params = _normalize_params(features)
    model = load_energy_model(model_path)
    
    if model is None:
        return None

    return predict_power(model, params)


def get_area(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
) -> Optional[float]:
    """
    Get area estimation for given features.

    Args:
        features: Dictionary with 'node', 'depth', 'bw' (or alternatives)
        model_path: Optional path to model weights

    Returns:
        Estimated area value or None if model not found
    """
    if features is None:
        features = {"node": 7, "depth": 64, "bw": 32}

    params = _normalize_params(features)
    model = load_area_model(model_path)
    
    if model is None:
        return None

    return predict_area(model, params)


def get_timing(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
) -> Optional[float]:
    """
    Get timing estimation for given features.

    Args:
        features: Dictionary with 'node', 'depth', 'bw' (or alternatives)
        model_path: Optional path to model weights

    Returns:
        Estimated timing value or None if model not found
    """
    if features is None:
        features = {"node": 7, "depth": 64, "bw": 32}

    params = _normalize_params(features)
    model = load_timing_model(model_path)
    
    if model is None:
        return None

    return predict_timing(model, params)


def check_models_available() -> Dict[str, bool]:
    """Check which models are available."""
    return {
        "energy": _get_model_path("energy").exists(),
        "area": _get_model_path("area").exists(),
        "timing": _get_model_path("timing").exists(),
    }


###############################################################################
# 8) Utility Functions
###############################################################################

def find_matching_rows(csv_file: str, params: Dict[str, Any], columns: list = None):
    """
    Finds rows in csv_file matching all key/value pairs in params dict.
    """
    df = pd.read_csv(csv_file)
    mask = None
    for k, v in params.items():
        if k in df.columns:
            if mask is None:
                mask = df[k] == v
            else:
                mask &= df[k] == v
    if mask is None:
        return pd.DataFrame()
    if columns:
        return df.loc[mask, columns]
    return df.loc[mask]


###############################################################################
# 9) Example Usage / Self-Test
###############################################################################

if __name__ == "__main__":
    print("[INFO] Regfile Estimator Module")
    print("=" * 60)

    # Check available models
    available = check_models_available()
    print(f"[INFO] Available models: {available}")

    # Test prediction with sample parameters
    sample = {'node': 7, 'depth': 64, 'bw': 32}

    energy = get_energy(sample)
    if energy is not None:
        print(f"[INFO] Energy prediction for {sample}: {energy}")
    else:
        print("[WARNING] Energy model not found")

    area = get_area(sample)
    if area is not None:
        print(f"[INFO] Area prediction for {sample}: {area}")
    else:
        print("[WARNING] Area model not found")

    timing = get_timing(sample)
    if timing is not None:
        print(f"[INFO] Timing prediction for {sample}: {timing}")
    else:
        print("[WARNING] Timing model not found")
