"""Custom component energy/area scaler.

The values of a user component are for its reference technology
(``UserComponent.reference``). The scaler changes them to the technology of
the run: node, transistor type, corner, voltage, temperature, and clock.

THE SCALER IS NOT IMPLEMENTED. :func:`scale` returns the reference values
without a change, and :func:`scaling_warning` tells the user about it.

The planned model is the user-defined sub-engine of the logic estimator
(Kim et al., HPCA 2026, Section IV-A). It is a neural network that has the
same inputs as the models of the predefined primitives. A user component has
no RTL, thus its sequential cell ratios (SCR, SAR) come from a preset of its
``design_class`` (``register`` or ``compute``).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

__all__ = ["scale", "scaling_warning"]


def scale(component: Any, target: Mapping[str, Any]) -> Any:
    """Return ``component`` with its values at the technology ``target``.

    ``component`` is a ``npuwattch.user_components.UserComponent``. ``target``
    is the feature mapping of a provider query (``node``, ``transistor``,
    ``corner``, ``voltage_offset_V``, ``temperature_C``, ``clock_mhz``).

    Not implemented: the function returns ``component`` without a change.
    """
    return component


def scaling_warning(component: Any, target: Mapping[str, Any]) -> Optional[str]:
    """Return a warning if the values are not for the node of the run."""
    reference = str(component.reference.get("node", "")).strip().lower()
    node = str(target.get("node", "")).strip().lower()
    if not node or reference == node:
        return None
    return (f"user component {component.name!r}: the values are for "
            f"{component.reference.get('node')} and the run is at "
            f"{target.get('node')}; the custom component scaler is not "
            f"implemented, so the values are used WITHOUT scaling")
