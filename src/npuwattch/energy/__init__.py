"""Activity → energy aggregation (manual §6).

``unit_cost`` defines the estimator calling convention (``UnitCostProvider``) plus
a placeholder ``StubUnitCostProvider``; ``aggregate`` turns per-window activity
(the harness's ``bind_window`` output) into per-component and total
energy/area/power. The trained MLP models drop in as a calibrated
``UnitCostProvider`` without touching the aggregator (user item #4).
"""

from __future__ import annotations

from .aggregate import (
    ComponentEnergy,
    RunEnergy,
    WindowEnergy,
    aggregate_run,
    aggregate_window,
    analyze_run,
)
from .unit_cost import StubUnitCostProvider, TechContext, UnitCostProvider

__all__ = [
    "ComponentEnergy",
    "RunEnergy",
    "WindowEnergy",
    "aggregate_run",
    "aggregate_window",
    "analyze_run",
    "StubUnitCostProvider",
    "TechContext",
    "UnitCostProvider",
]
