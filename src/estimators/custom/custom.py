"""Custom Component Estimator Module.

This module provides MLP-based estimation for custom components:
- Energy/Power consumption using scaling factor model (from lscaler_custom_power.py)
- Area (placeholder - TODO)
- Timing (placeholder - TODO)

The energy model predicts a scaling factor to convert energy from a reference
technology node to a target node.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

###############################################################################
# ESTIMATOR_SPEC - Defines the interface for the EstimatorHost
###############################################################################

ESTIMATOR_SPEC = {
    "primitive": "custom",
    "version": "1.0",
    "description": "Custom component estimator using MLP scaling factor models",
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
            {"name": "from_node", "type": "float"},
            {"name": "to_node", "type": "float"},
            {"name": "area_from", "type": "float"},
            {"name": "energy_from", "type": "float"},
        ],
        "optional": [
            {"name": "scr", "type": "float", "default": 0.1},
            {"name": "sar", "type": "float", "default": 0.3},
        ],
    },
    "models": {
        "energy": "energy_sf_model.pth",
        "area": "area_model.pth",
        "timing": "timing_model.pth",
    },
}

_MODULE_DIR = Path(__file__).parent
EPS = 1e-9


###############################################################################
# 1) Dataset Classes
###############################################################################

class EnergySFDataset(Dataset):
    """
    Reads CSV and generates:
      X = [from_node, scr, sar, log(area_from), log(energy_from), to_node]
      Y = [sf_energy]
    """
    def __init__(self, csv_file: str, hist_info=None):
        super().__init__()
        if not HAS_PANDAS:
            raise ImportError("pandas is required for training")
        df = pd.read_csv(csv_file)

        self.node_from = df['from_node'].values.astype(np.float32)
        self.seq_cnt_ratio = df['scr_from'].values.astype(np.float32)
        self.seq_area_ratio = df['sar_from'].values.astype(np.float32)
        self.area_from = df['area_from'].values.astype(np.float32)
        self.energy_from = df['energy_from'].values.astype(np.float32)
        self.node_to = df['to_node'].values.astype(np.float32)
        self.sf_energy = df['sf_energy'].values.astype(np.float32)

        self.hist_info = hist_info

    def __len__(self):
        return len(self.node_from)

    def _lookup_weight(self, scr, sar):
        if self.hist_info is None:
            return 1.0
        edges_c, w_c, edges_a, w_a = self.hist_info
        bin_c = np.searchsorted(edges_c[:-1], scr, side='right') - 1
        bin_a = np.searchsorted(edges_a[:-1], sar, side='right') - 1
        bin_c = np.clip(bin_c, 0, len(w_c) - 1)
        bin_a = np.clip(bin_a, 0, len(w_a) - 1)
        return float(np.sqrt(w_c[bin_c] * w_a[bin_a]))

    def __getitem__(self, idx):
        nodeF = self.node_from[idx]
        scr = self.seq_cnt_ratio[idx]
        sar = self.seq_area_ratio[idx]
        areaF = self.area_from[idx]
        eF = self.energy_from[idx]
        sfE = self.sf_energy[idx]
        nodeT = self.node_to[idx]

        log_areaF = np.log(areaF + EPS)
        log_eF = np.log(eF + EPS)

        X = np.array([nodeF, scr, sar, log_areaF, log_eF, nodeT], dtype=np.float32)
        Y = np.array([sfE], dtype=np.float32)
        w = self._lookup_weight(scr, sar)

        return X, Y, w


###############################################################################
# 2) MLP Model Classes
###############################################################################

class MLPEnergySF(nn.Module):
    """
    Predicts sf_energy from X = [from_node, scr, sar, log(area_from), log(energy_from), to_node]
    """
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(6, 320)
        self.fc2 = nn.Linear(320, 240)
        self.fc3 = nn.Linear(240, 180)
        self.fc4 = nn.Linear(180, 140)
        self.fc5 = nn.Linear(140, 100)
        self.fc6 = nn.Linear(100, 60)
        self.fc7 = nn.Linear(60, 40)
        self.fc8 = nn.Linear(40, 20)
        self.fc_out = nn.Linear(20, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))
        x = F.relu(self.fc5(x))
        x = F.relu(self.fc6(x))
        x = F.relu(self.fc7(x))
        x = F.relu(self.fc8(x))
        x = self.fc_out(x)
        return x


class MLPArea(nn.Module):
    """Placeholder area model - TODO: implement proper architecture."""
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(6, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc_out = nn.Linear(64, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc_out(x)


class MLPTiming(nn.Module):
    """Placeholder timing model - TODO: implement proper architecture."""
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(6, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc_out = nn.Linear(64, 1)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc_out(x)


###############################################################################
# 3) Training Routines
###############################################################################

class WeightedL1(nn.Module):
    """L1 loss scaled by per-sample weight."""
    def forward(self, pred, target, w):
        loss = torch.abs(pred - target)
        return loss.mean()


def scan_two_histograms(csv_file: str, bins: int = 30):
    """Return histogram info for weighted training."""
    if not HAS_PANDAS:
        return None
    df = pd.read_csv(csv_file)

    scr = df['scr_from'].values.astype(np.float64)
    sar = df['sar_from'].values.astype(np.float64)

    def _one_hist(x):
        counts, edges = np.histogram(x, bins=bins, density=False)
        pmf = counts.astype(np.float32) / counts.sum()
        w = (1.0 / (pmf + 1e-6))
        w /= w.mean()
        w = w * 1e+2
        return edges.astype(np.float32), w.astype(np.float32)

    edges_c, w_c = _one_hist(scr)
    edges_a, w_a = _one_hist(sar)
    return edges_c, w_c, edges_a, w_a


def _train_energy_sf_model(
    dataset: EnergySFDataset,
    model: MLPEnergySF,
    epochs: int = 500,
    batch_size: int = 50,
    lr: float = 1e-4,
    verbose: bool = True,
) -> MLPEnergySF:
    """Train the energy scaling factor model."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    train_size = int(0.8 * len(dataset))
    test_size = len(dataset) - train_size
    train_ds, test_ds = torch.utils.data.random_split(dataset, [train_size, test_size])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = WeightedL1()

    for epoch in range(1, epochs + 1):
        model.train()
        total_train_loss = 0.0
        for X, Y, W in train_loader:
            X_train, Y_train, W_train = X.to(device), Y.to(device), W.to(device)
            optimizer.zero_grad()
            pred = model(X_train)
            loss = criterion(pred, Y_train, W_train)
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item() * X.size(0)

        avg_train = total_train_loss / len(train_loader.dataset)

        if verbose and (epoch % 50 == 0 or epoch == 1):
            model.eval()
            total_test_loss = 0.0
            with torch.no_grad():
                for X, Y, W in test_loader:
                    X_test, Y_test, W_test = X.to(device), Y.to(device), W.to(device)
                    total_test_loss += criterion(model(X_test), Y_test, W_test).item() * X.size(0)
            avg_test = total_test_loss / len(test_loader.dataset)
            print(f"[INFO] Epoch [{epoch}/{epochs}] - Train L1: {avg_train:.6f}, Test L1: {avg_test:.6f}")

    model.eval()
    return model


###############################################################################
# 4) Save and Load Routines
###############################################################################

def _get_model_path(model_type: str) -> Path:
    """Get the default path for a model file."""
    model_files = ESTIMATOR_SPEC["models"]
    filename = model_files.get(model_type, f"custom_{model_type}_model.pth")
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
    model.load_state_dict(torch.load(str(path), map_location=torch.device('cpu'), weights_only=True))
    model.eval()
    return model


def load_energy_model(path: Optional[Union[str, Path]] = None) -> Optional[MLPEnergySF]:
    """Load the energy scaling factor model."""
    if path is None:
        path = _get_model_path("energy")
    return load_model(MLPEnergySF, path)


def load_area_model(path: Optional[Union[str, Path]] = None) -> Optional[MLPArea]:
    """Load the area model (placeholder)."""
    if path is None:
        path = _get_model_path("area")
    return load_model(MLPArea, path)


def load_timing_model(path: Optional[Union[str, Path]] = None) -> Optional[MLPTiming]:
    """Load the timing model (placeholder)."""
    if path is None:
        path = _get_model_path("timing")
    return load_model(MLPTiming, path)


###############################################################################
# 5) Predict Routines
###############################################################################

def predict_energy_sf(
    model: MLPEnergySF,
    from_node: float,
    scr: float,
    sar: float,
    area_from: float,
    energy_from: float,
    to_node: float,
) -> float:
    """
    Predict scaled energy using the energy scaling factor model.

    Returns:
        energy_to: Estimated energy at the target node.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    X = np.array([
        from_node,
        scr,
        sar,
        np.log(area_from + EPS),
        np.log(energy_from + EPS),
        to_node
    ], dtype=np.float32)

    with torch.no_grad():
        inp = torch.from_numpy(X).unsqueeze(0).to(device)
        energy_sf = model(inp)[0, 0].item()

    energy_to_est = energy_from * energy_sf
    return energy_to_est


###############################################################################
# 6) Training Entry Points
###############################################################################

def train_energy_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 50,
    lr: float = 1e-4,
) -> MLPEnergySF:
    """Train the energy scaling factor model on a CSV dataset."""
    print(f"[INFO] Training energy model from {csv_file}")
    hist_info = scan_two_histograms(csv_file, bins=30)
    dataset = EnergySFDataset(csv_file, hist_info)
    model = MLPEnergySF()
    trained = _train_energy_sf_model(dataset, model, epochs, batch_size, lr)

    if output_path is None:
        output_path = _get_model_path("energy")
    save_model(trained, output_path)

    return trained


def train_area_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 50,
    lr: float = 1e-3,
) -> MLPArea:
    """Placeholder: Train the area model on a CSV dataset."""
    print(f"[WARNING] Area model training not yet implemented")
    # TODO: Implement area model training
    return MLPArea()


def train_timing_model(
    csv_file: str,
    output_path: Optional[str] = None,
    epochs: int = 500,
    batch_size: int = 50,
    lr: float = 1e-3,
) -> MLPTiming:
    """Placeholder: Train the timing model on a CSV dataset."""
    print(f"[WARNING] Timing model training not yet implemented")
    # TODO: Implement timing model training
    return MLPTiming()


###############################################################################
# 7) Public API - Entry Points for EstimatorHost
###############################################################################

def _normalize_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize feature names to internal format."""
    return {
        'from_node': float(features.get('from_node', 45)),
        'to_node': float(features.get('to_node', features.get('node', 7))),
        'scr': float(features.get('scr', features.get('seq_cnt_ratio', 0.1))),
        'sar': float(features.get('sar', features.get('seq_area_ratio', 0.3))),
        'area_from': float(features.get('area_from', 1000.0)),
        'energy_from': float(features.get('energy_from', 1e-12)),
    }


def get_energy(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
    **kwargs: Any,
) -> Optional[float]:
    """
    Get energy estimation for given features.

    Args:
        features: Dictionary with custom component parameters
        model_path: Optional path to model weights

    Returns:
        Estimated energy value or None if model not found
    """
    if features is None:
        return None

    # Check if energy value is directly provided in features
    if 'energy' in features and features.get('from_node') is None:
        return float(features['energy'])

    params = _normalize_features(features)
    model = load_energy_model(model_path)

    if model is None:
        # Fall back to direct energy value if model not available
        if 'energy' in features:
            return float(features['energy'])
        return None

    return predict_energy_sf(
        model,
        params['from_node'],
        params['scr'],
        params['sar'],
        params['area_from'],
        params['energy_from'],
        params['to_node'],
    )


def get_area(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
    **kwargs: Any,
) -> Optional[float]:
    """
    Get area estimation for given features.

    Args:
        features: Dictionary with custom component parameters
        model_path: Optional path to model weights

    Returns:
        Estimated area value or None if not available

    Note:
        Area model is not yet implemented. Returns direct value from features if available.
    """
    if features is None:
        return None

    # Return direct area value if provided
    if 'area' in features:
        return float(features['area'])

    # TODO: Implement area model prediction
    # model = load_area_model(model_path)
    # if model is not None:
    #     return predict_area(model, params)

    return None


def get_timing(
    features: Optional[Dict[str, Any]] = None,
    *,
    model_path: Optional[str] = None,
    **kwargs: Any,
) -> Optional[float]:
    """
    Get timing estimation for given features.

    Args:
        features: Dictionary with custom component parameters
        model_path: Optional path to model weights

    Returns:
        Estimated timing value or None if not available

    Note:
        Timing model is not yet implemented. Returns direct value from features if available.
    """
    if features is None:
        return None

    # Return direct timing value if provided
    if 'timing' in features:
        return float(features['timing'])

    # TODO: Implement timing model prediction
    # model = load_timing_model(model_path)
    # if model is not None:
    #     return predict_timing(model, params)

    return None


def check_models_available() -> Dict[str, bool]:
    """Check which models are available."""
    return {
        "energy": _get_model_path("energy").exists(),
        "area": _get_model_path("area").exists(),
        "timing": _get_model_path("timing").exists(),
    }


###############################################################################
# 8) Example Usage / Self-Test
###############################################################################

if __name__ == "__main__":
    print("[INFO] Custom Component Estimator Module")
    print("=" * 60)

    available = check_models_available()
    print(f"[INFO] Available models: {available}")

    sample = {
        'from_node': 45,
        'to_node': 7,
        'scr': 0.17,
        'sar': 0.36,
        'area_from': 1189408.36,
        'energy_from': 7.56e-10,
    }

    energy = get_energy(sample)
    if energy is not None:
        print(f"[INFO] Energy prediction for sample: {energy:.4e}")
    else:
        print("[WARNING] Energy model not found or prediction failed")

    area = get_area(sample)
    if area is not None:
        print(f"[INFO] Area prediction for sample: {area:.4e}")
    else:
        print("[INFO] Area model not yet implemented")

    timing = get_timing(sample)
    if timing is not None:
        print(f"[INFO] Timing prediction for sample: {timing:.4e}")
    else:
        print("[INFO] Timing model not yet implemented")
