"""Compose the §6 unit-cost provider from whatever calibrated estimators exist.

An estimator plugin opts into the §6 path by declaring a ``unit_cost_provider``
entrypoint in its ``ESTIMATOR_SPEC`` (see ``src/estimators/sram``). The factory
asks each such estimator for a provider and **chains** them: every provider serves
its own primitive and delegates the rest to the previous link, with
``StubUnitCostProvider`` (placeholder, ``calibrated=False``) at the bottom.

That means calibration arrives incrementally and per primitive — today only
``sram`` is calibrated; the logic primitives (``fpmac``/``intmac``/``regfile``…)
keep returning placeholder costs until workstream D trains their models, at which
point their estimators declare the same entrypoint and drop into this chain with
no change to the aggregator.

``ProviderChain.calibrated_primitives`` records which primitives are real, so the
CLI/report can label results honestly instead of a single all-or-nothing flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from .unit_cost import D2DLinkCostProvider, HBMCostProvider, StubUnitCostProvider

__all__ = ["ProviderChain", "build_provider"]


@dataclass(frozen=True)
class ProviderChain:
    """A composed provider plus which primitives it answers with real models."""

    provider: Any
    calibrated_primitives: Tuple[str, ...] = ()
    #: Primitives answered by an analytic constant (d2dlink) — neither
    #: calibrated nor placeholder; labeled distinctly so reports stay honest.
    constant_primitives: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    def is_calibrated(self, primitive: str) -> bool:
        return primitive in self.calibrated_primitives


def build_provider(
    fallback: Any = None,
    *,
    host: Any = None,
    defaults: Optional[Mapping[str, Any]] = None,
    verbose: int = 0,
) -> ProviderChain:
    """Build the provider chain: calibrated estimators over a placeholder base.

    ``fallback`` defaults to ``StubUnitCostProvider()``. Estimators that fail to
    produce a provider are skipped (recorded in ``notes``) rather than breaking
    the chain — a broken plugin must not take the whole run down.
    """
    if host is None:
        from ..npuwattch_estimator_host import EstimatorHost

        host = EstimatorHost(verbose=verbose)
        host.scan_estimators()

    provider = fallback if fallback is not None else StubUnitCostProvider()
    # The analytic constants (d2dlink, hbm) sit just above the placeholder
    # base, so calibrated estimator links always win for their own primitive.
    provider = D2DLinkCostProvider(fallback=provider)
    provider = HBMCostProvider(fallback=provider)
    calibrated: List[str] = []
    notes: List[str] = []

    for name in sorted(host.list_modules()):
        spec = host.get_spec(name) or {}
        entrypoints = spec.get("entrypoints") or {}
        if "unit_cost_provider" not in entrypoints:
            continue
        try:
            built, error = host.execute_entrypoint(
                name, "unit_cost_provider", defaults=defaults, fallback=provider
            )
        except Exception as e:                      # a plugin must not kill the run
            built, error = None, str(e)
        if error or built is None:
            notes.append(f"estimator {name!r}: unit_cost_provider unavailable ({error})")
            continue
        provider = built
        # One module may serve several primitives (the logic estimator's MLP
        # quartets) — a `primitives` list wins over the single `primitive`.
        prims = spec.get("primitives")
        if prims:
            calibrated.extend(str(p) for p in prims)
        else:
            calibrated.append(str(spec.get("primitive", name)))

    return ProviderChain(
        provider=provider,
        calibrated_primitives=tuple(calibrated),
        constant_primitives=("d2dlink", "hbm"),
        notes=tuple(notes),
    )
