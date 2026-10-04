"""Make the unit-cost provider of a run (manual §6) from the estimators.

An estimator plugin declares a ``unit_cost_provider`` entrypoint in its
``ESTIMATOR_SPEC`` (see ``src/npuwattch_estimators/sram``). The factory asks
each such estimator for a provider and makes a chain. Each provider answers
for its own primitives and sends the other queries to the next provider:

1. The calibrated estimators (``logic``, ``sram``).
2. The user-defined component estimator (``custom``), for the components of
   the user component library.
3. The constant providers (``hbm``, ``d2dlink``). Their values come from
   table files.
4. ``NoModelProvider``, which raises an error. NPUWattch gives no value for a
   block that it has no model for.

``ProviderChain`` records which primitives each group answers. The CLI and the
report use this to label each result: calibrated, user, or constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from .unit_cost import D2DLinkCostProvider, HBMCostProvider, NoModelProvider

__all__ = ["ProviderChain", "build_provider"]


@dataclass(frozen=True)
class ProviderChain:
    """The provider of a run, and the primitives that each group answers."""

    provider: Any
    calibrated_primitives: Tuple[str, ...] = ()
    #: Primitives that a constant provider answers from a table file (hbm,
    #: d2dlink). They are not calibrated models and have their own label.
    constant_primitives: Tuple[str, ...] = ()
    #: Components of the user component library. Their values come from the
    #: user, through the user-defined component estimator.
    user_primitives: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    #: The characterized technology nodes that all calibrated estimators of
    #: the chain have. This is the intersection of the ``nodes`` lists of
    #: their ESTIMATOR_SPEC. ``node_scaling`` uses these nodes as anchors.
    #: The tuple is empty if no calibrated estimator declares its nodes.
    characterized_nodes: Tuple[str, ...] = ()

    def is_calibrated(self, primitive: str) -> bool:
        return primitive in self.calibrated_primitives


def build_provider(
    fallback: Any = None,
    *,
    host: Any = None,
    defaults: Optional[Mapping[str, Any]] = None,
    verbose: int = 0,
    user_components: Optional[Mapping[str, Any]] = None,
) -> ProviderChain:
    """Make the provider chain.

    ``fallback`` is the last link. The default is ``NoModelProvider()``, which
    raises an error for a primitive that no estimator answers.

    ``user_components`` is the user component library of the run
    (name -> ``UserComponent``). An estimator that declares
    ``accepts_user_components`` gets it.

    An estimator that cannot make a provider is not in the chain. ``notes``
    records the reason. One incorrect plugin must not stop the run.
    """
    if host is None:
        from ..npuwattch_estimator_host import EstimatorHost

        host = EstimatorHost(verbose=verbose)
        host.scan_estimators()

    provider = fallback if fallback is not None else NoModelProvider()
    # The constant providers are immediately before the last link. Thus an
    # estimator has priority for its own primitives.
    constant: List[str] = []
    for constant_provider in (D2DLinkCostProvider, HBMCostProvider):
        provider = constant_provider(fallback=provider)
        constant.extend(constant_provider.primitives)
    user_components = dict(user_components or {})
    # The estimators that use the library are next, in the sorted order below.
    calibrated: List[str] = []
    notes: List[str] = []
    node_sets: List[Tuple[str, ...]] = []

    for name in sorted(host.list_modules()):
        spec = host.get_spec(name) or {}
        entrypoints = spec.get("entrypoints") or {}
        if "unit_cost_provider" not in entrypoints:
            continue
        uses_library = bool(spec.get("accepts_user_components"))
        if uses_library and not user_components:
            continue
        extra = {"user_components": user_components} if uses_library else {}
        try:
            built, error = host.execute_entrypoint(
                name, "unit_cost_provider", defaults=defaults,
                fallback=provider, **extra
            )
        except Exception as e:                      # a plugin must not stop the run
            built, error = None, str(e)
        if error or built is None:
            notes.append(f"estimator {name!r}: unit_cost_provider unavailable ({error})")
            continue
        provider = built
        if uses_library:
            continue                    # its primitives are the library names
        # One estimator can answer for two or more primitives (the logic
        # estimator has four MLPs for each primitive). A `primitives` list
        # has priority over the single `primitive`.
        prims = spec.get("primitives")
        if prims:
            calibrated.extend(str(p) for p in prims)
        else:
            calibrated.append(str(spec.get("primitive", name)))
        if spec.get("nodes"):
            node_sets.append(tuple(str(n) for n in spec["nodes"]))

    # An anchor node of node_scaling must be a node that ALL calibrated
    # estimators have. Thus use the intersection of the declared node sets.
    characterized: Tuple[str, ...] = ()
    if node_sets:
        common = set(node_sets[0]).intersection(*node_sets[1:])
        from .node_scaling import parse_node_nm

        characterized = tuple(sorted(common, key=parse_node_nm))

    return ProviderChain(
        provider=provider,
        calibrated_primitives=tuple(calibrated),
        constant_primitives=tuple(constant),
        user_primitives=tuple(user_components),
        notes=tuple(notes),
        characterized_nodes=characterized,
    )
