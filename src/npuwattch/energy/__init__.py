"""Activity → energy aggregation (manual §6).

``unit_cost`` defines the calling convention of the estimators
(``UnitCostProvider``). ``provider_factory`` makes the provider chain of a run.
``aggregate`` calculates the energy, area, and power of each component and of
the run from a description (manual §3.1) and its activity rows (manual §3.3).
"""

from __future__ import annotations

from .activity_io import read_activity_csv
from .aggregate import (
    ComponentEnergy,
    RunEnergy,
    WindowEnergy,
    aggregate_native,
    aggregate_run,
)
from .node_scaling import (
    NodeResolution,
    NodeScalingProvider,
    apply_node_scaling,
    parse_node_nm,
    resolve_node,
)
from .provider_factory import ProviderChain, build_provider
from .unit_cost import (
    D2D_ENERGY_PER_BIT_PJ,
    D2DLinkCostProvider,
    NoModelError,
    NoModelProvider,
    TechContext,
    UnitCostProvider,
)
from .vectorless import DEFAULT_VECTORLESS_ACTIVITY, vectorless_activity_rows

__all__ = [
    "D2D_ENERGY_PER_BIT_PJ",
    "D2DLinkCostProvider",
    "DEFAULT_VECTORLESS_ACTIVITY",
    "vectorless_activity_rows",
    "NodeResolution",
    "NodeScalingProvider",
    "apply_node_scaling",
    "parse_node_nm",
    "resolve_node",
    "ProviderChain",
    "build_provider",
    "ComponentEnergy",
    "RunEnergy",
    "WindowEnergy",
    "aggregate_native",
    "aggregate_run",
    "read_activity_csv",
    "NoModelError",
    "NoModelProvider",
    "TechContext",
    "UnitCostProvider",
]
