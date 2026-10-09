"""User-defined component estimator.

This estimator gives the cost of the components of the user component library
(``npuwattch.user_components``): the area, the leakage power, and the energy
of each action. The values come from the user. The scaler (``scaler.py``)
changes them to the technology of the run.

The estimator has no data of its own. Without a library, it sends each query
to the next provider.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, List, Mapping, Optional

from npuwattch_estimators.errors import EstimatorQueryError, CustomQueryError

# ESTIMATOR_SPEC must be a pure literal. The EstimatorHost reads it and does
# not import this module.
ESTIMATOR_SPEC = {
    "primitive": "custom",
    "version": "1.0",
    "description": (
        "User-defined component estimator: design cost data from the user "
        "component library. The custom component scaler is not implemented; "
        "values are used at their reference technology."
    ),
    "entrypoints": {
        "unit_cost_provider": "make_unit_cost_provider",
    },
    # This estimator gets the user component library from the provider
    # factory. Its primitives are the names in the library.
    "accepts_user_components": True,
    "parameters": {},
}

MODULE_DIR = Path(__file__).resolve().parent
_SCALER = None


def _scaler():
    """Import the sibling module scaler.py by its path. Keep the result."""
    global _SCALER
    if _SCALER is None:
        spec = importlib.util.spec_from_file_location(
            "_npuwattch_custom_scaler", MODULE_DIR / "scaler.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SCALER = module
    return _SCALER


class _UserComponentProvider:
    """A provider for the components of the user component library.

    A query for a different primitive goes to ``fallback``.
    """

    def __init__(self, components: Mapping[str, Any], fallback: Any) -> None:
        self.components = dict(components)
        self.fallback = fallback

    @property
    def calibrated(self) -> bool:
        # User data is not a calibrated model. The label of a user component
        # comes from ProviderChain.user_primitives.
        return bool(getattr(self.fallback, "calibrated", False))

    def _scaled(self, primitive: str, features: Mapping[str, Any]) -> Any:
        return _scaler().scale(self.components[primitive], features)

    def _delegate(self, method: str, primitive: str,
                  features: Mapping[str, Any]) -> float:
        if self.fallback is None:
            raise EstimatorQueryError.nw(8001, provider="user component",
                                         primitive=primitive)
        return getattr(self.fallback, method)(primitive, features)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.components:
            return self._delegate("energy_per_cycle", primitive, features)
        component = self._scaled(primitive, features)
        action = features.get("stim_mode")
        if action not in component.actions:
            raise CustomQueryError.nw(
                8301, component=primitive, action=action,
                actions=", ".join(sorted(component.actions)))
        return component.actions[action]

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.components:
            return self._delegate("leak_power", primitive, features)
        return self._scaled(primitive, features).leak_power_mW

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.components:
            return self._delegate("area", primitive, features)
        return self._scaled(primitive, features).area_um2

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.components:
            return self._delegate("crit_path", primitive, features)
        return 0.0                  # the library has no timing data

    def idle_terms(self, primitive: str, features: Mapping[str, Any]):
        if primitive in self.components or self.fallback is None:
            return None
        fb = getattr(self.fallback, "idle_terms", None)
        return fb(primitive, features) if fb is not None else None

    def envelope_warnings(self, primitive: str,
                          features: Mapping[str, Any]) -> List[str]:
        if primitive in self.components:
            warning = _scaler().scaling_warning(self.components[primitive],
                                                features)
            return [warning] if warning else []
        fb = getattr(self.fallback, "envelope_warnings", None)
        return list(fb(primitive, features)) if fb is not None else []


def make_unit_cost_provider(defaults: Optional[Mapping[str, Any]] = None,
                            fallback: Any = None,
                            user_components: Optional[Mapping[str, Any]] = None
                            ) -> _UserComponentProvider:
    """Make the provider for the components of ``user_components``.

    ``user_components`` is name -> ``UserComponent``. ``defaults`` is not
    used. It is in the signature because all estimators have it.
    """
    return _UserComponentProvider(user_components or {}, fallback)
