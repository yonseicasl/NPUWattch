"""NPUWattch class/feature mapping.

This module owns:
- Mapping from component class/subclass strings to estimator module names
- Feature extraction rules from component attributes to estimator feature dicts

Keeping these mappings in a dedicated module makes them easy to update without
touching the console or estimator host logic.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence, Tuple
import re

# -----------------------------------------------------------------------------
# Component class/subclass -> estimator module mapping
# -----------------------------------------------------------------------------

CLASS_TO_ESTIMATOR: Dict[str, str] = {
    # Register files and storage
    "regfile": "regfile",
    "register_file": "regfile",
    "rf": "regfile",
    "smartbuffer_rf": "regfile",
    "smartbuffer_sram": "regfile",
    "sram": "regfile",
    "dram": "regfile",

    # Crossbar
    "crossbar": "crossbar",
    "xbar": "crossbar",
    
    # Compute units
    "intmac": "regfile",
    "mac": "regfile",
    "compute": "regfile",
}

# -----------------------------------------------------------------------------
# Feature mapping rules
# -----------------------------------------------------------------------------

# Each entry: feature_name -> (candidate_attribute_keys, default_value, transform_fn)
# - candidate_attribute_keys: checked in order; first existing key wins
# - transform_fn: applied to the found value (or default)
FeatureRule = Tuple[Sequence[str], Any, Callable[[Any], Any]]

def _parse_technology_node(value: Any, default: int = 7) -> int:
    """Parse technology node from int or strings like '45nm', '7 nm'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default
    if isinstance(value, str):
        m = re.search(r"(\d+)", value)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return default
    return default

FEATURE_MAPPER: Dict[str, FeatureRule] = {
    "node": (("technology", "node"), 7, _parse_technology_node),
    "depth": (("depth", "entries", "memory_depth"), 64, int),
    "bw": (("width", "bw", "datawidth", "bitwidth"), 32, int),
    "n_banks": (("n_banks",), 1, int),
    "n_ports": (("n_ports", "num_ports", "nports"), 1, int),
}

def extract_features_from_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """Extract estimator features from a component's attributes dict."""
    features: Dict[str, Any] = {}
    for feat, (keys, default, transform) in FEATURE_MAPPER.items():
        val: Any = default
        for k in keys:
            if k in attributes:
                val = attributes.get(k)
                break
        try:
            # Special-case: keep None as default for numeric transforms
            if val is None:
                val = default
            val = transform(val) if transform else val
        except Exception:
            val = default
        features[feat] = val
    return features

def map_class_to_estimator(comp_class: str, subclass: Optional[str] = None) -> Optional[str]:
    """Resolve estimator module name from class/subclass strings."""
    if comp_class:
        key = comp_class.lower()
        if key in CLASS_TO_ESTIMATOR:
            return CLASS_TO_ESTIMATOR[key]
    if subclass:
        key = subclass.lower()
        if key in CLASS_TO_ESTIMATOR:
            return CLASS_TO_ESTIMATOR[key]
    return None
