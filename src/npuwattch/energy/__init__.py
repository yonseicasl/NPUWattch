"""Activity → energy aggregation (manual §6).

``unit_cost`` defines the estimator calling convention (``UnitCostProvider``) plus
a placeholder ``StubUnitCostProvider``; ``aggregate`` turns per-window activity
(the harness's ``bind_window`` output) into per-component and total
energy/area/power. The trained MLP models drop in as a calibrated
``UnitCostProvider`` without touching the aggregator (user item #4).
"""

from __future__ import annotations

from .activity_io import read_activity_csv
from .aggregate import (
    ComponentEnergy,
    RunEnergy,
    WindowEnergy,
    aggregate_native,
    aggregate_run,
    aggregate_window,
    analyze_run,
)
from .provider_factory import ProviderChain, build_provider
from .unit_cost import (
    D2D_ENERGY_PER_BIT_PJ,
    D2DLinkCostProvider,
    StubUnitCostProvider,
    TechContext,
    UnitCostProvider,
)
from .vectorless import DEFAULT_VECTORLESS_ACTIVITY, vectorless_activity_rows

__all__ = [
    "D2D_ENERGY_PER_BIT_PJ",
    "D2DLinkCostProvider",
    "DEFAULT_VECTORLESS_ACTIVITY",
    "vectorless_activity_rows",
    "ProviderChain",
    "build_provider",
    "ComponentEnergy",
    "RunEnergy",
    "WindowEnergy",
    "aggregate_native",
    "aggregate_run",
    "aggregate_window",
    "analyze_run",
    "read_activity_csv",
    "StubUnitCostProvider",
    "TechContext",
    "UnitCostProvider",
]
