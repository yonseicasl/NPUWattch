"""Continuous technology-node resolution over the characterized node set.

The MLP estimators are trained at a handful of characterized nodes (today
5/7/10/16/20 nm, node one-hot inputs) and hard-error on anything else. The CLI,
however, must accept the node axis **continuously** (user decision 2026-08-13):
Accelergy/Timeloop descriptions routinely declare 65/45/32 nm, and a node
whitelist turns every such run into a crash.

The rule, verbatim from that decision:

* The supported envelope is the characterized range extended by **50 % on each
  side**: lower bound = min characterized node x 0.5, upper = max x 1.5.
  With the current 5-20 nm datasets that is **2.5-30 nm**.
* Any node inside the envelope is evaluated: between two characterized nodes by
  **log-log interpolation** of the two anchor predictions (energy/area/delay
  scale polynomially with feature size, so straight lines in log-log space are
  the right local model); beyond the characterized edge by log-log
  **extrapolation** from the edge pair's trend (WARNING).
* A node outside the envelope is **clamped** to the nearest envelope bound and
  the run continues — with a WARNING on the CLI *and* in the report, never a
  crash. The numbers then model the clamp bound, not the requested node, and
  every output says so.

The estimators themselves stay node-discrete: this layer only ever queries them
at characterized nodes, so their own validation is untouched (defense in depth
for direct API users).
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass, replace as _dc_replace
from typing import Any, Mapping, Optional, Sequence, Tuple

__all__ = [
    "ENVELOPE_LO_FACTOR",
    "ENVELOPE_HI_FACTOR",
    "NodeResolution",
    "NodeScalingProvider",
    "apply_node_scaling",
    "node_envelope_nm",
    "parse_node_nm",
    "resolve_node",
]

#: Envelope factors around the characterized range (user decision 2026-08-13):
#: accept min x 0.5 ... max x 1.5, clamp-with-warning beyond.
ENVELOPE_LO_FACTOR = 0.5
ENVELOPE_HI_FACTOR = 1.5

#: Relative tolerance for "this IS a characterized node".
_EXACT_RTOL = 1e-6


def parse_node_nm(value: Any) -> float:
    """A node spelling -> nanometers, continuously ("7nm", "8.5nm", 12, "45NM").

    Raises ``ValueError`` for anything that is not a positive length in nm.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        nm = float(value)
    else:
        text = str(value).strip().lower().replace(" ", "")
        if text.endswith("nm"):
            text = text[:-2]
        try:
            nm = float(text)
        except ValueError:
            raise ValueError(
                f"cannot parse technology node {value!r} — expected a length "
                f"in nm such as '7nm' or '12.5nm'") from None
    if not math.isfinite(nm) or nm <= 0:
        raise ValueError(f"technology node must be a positive length, got {value!r}")
    return nm


def node_envelope_nm(characterized_nm: Sequence[float]) -> Tuple[float, float]:
    """The accepted continuous range: characterized min x 0.5 ... max x 1.5."""
    return (min(characterized_nm) * ENVELOPE_LO_FACTOR,
            max(characterized_nm) * ENVELOPE_HI_FACTOR)


@dataclass(frozen=True)
class NodeResolution:
    """How a requested node is evaluated against the characterized set.

    ``kind`` is one of:

    * ``exact`` — the requested node is characterized; single-anchor queries.
    * ``interpolated`` — inside the characterized range; log-log interpolation
      between the bracketing anchors (INFO note).
    * ``extrapolated`` — outside the characterized range but inside the +-50 %
      envelope; log-log extrapolation from the edge pair (WARNING).
    * ``clamped`` — outside the envelope; evaluated at the envelope bound via
      the edge pair (WARNING; the results model the bound, not the request).
    """

    requested: str
    requested_nm: float
    eval_nm: float
    kind: str
    lo: str                       # anchor node strings from the characterized set
    hi: str
    weight: float                 # position of eval_nm on the lo..hi log axis
    warnings: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


def resolve_node(node: Any, characterized: Sequence[str]) -> NodeResolution:
    """Plan the evaluation of ``node`` over ``characterized`` (e.g. ["5nm", ...]).

    Raises ``ValueError`` only for an unparseable node spelling — every parseable
    node resolves (clamped at worst), per the 2026-08-13 decision.
    """
    if not characterized:
        raise ValueError("resolve_node needs a non-empty characterized node set")
    requested_nm = parse_node_nm(node)

    anchors = sorted(((parse_node_nm(s), str(s)) for s in characterized))
    nms = [a[0] for a in anchors]
    lo_env, hi_env = node_envelope_nm(nms)
    lo_char, hi_char = nms[0], nms[-1]

    warnings: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    eval_nm = requested_nm

    for nm, name in anchors:
        if abs(requested_nm - nm) <= _EXACT_RTOL * nm:
            return NodeResolution(
                requested=str(node), requested_nm=requested_nm, eval_nm=nm,
                kind="exact", lo=name, hi=name, weight=0.0)

    if requested_nm < lo_env or requested_nm > hi_env:
        eval_nm = min(max(requested_nm, lo_env), hi_env)
        kind = "clamped"
        warnings = ((
            f"node {requested_nm:g} nm is outside the supported envelope "
            f"{lo_env:g}-{hi_env:g} nm (characterized {lo_char:g}-{hi_char:g} nm "
            f"±50%) — evaluated at {eval_nm:g} nm instead; the results "
            f"model {eval_nm:g} nm, not {requested_nm:g} nm"),)
    elif requested_nm < lo_char or requested_nm > hi_char:
        kind = "extrapolated"
    else:
        kind = "interpolated"

    if eval_nm <= lo_char:
        pair = anchors[0], anchors[1]
    elif eval_nm >= hi_char:
        pair = anchors[-2], anchors[-1]
    else:
        i = bisect_left(nms, eval_nm)
        pair = anchors[i - 1], anchors[i]
    (n1, lo_name), (n2, hi_name) = pair
    weight = (math.log(eval_nm) - math.log(n1)) / (math.log(n2) - math.log(n1))

    if kind == "extrapolated":
        warnings = ((
            f"node {requested_nm:g} nm is outside the characterized range "
            f"{lo_char:g}-{hi_char:g} nm — log-extrapolated from the "
            f"{lo_name}/{hi_name} trend; treat the results as first-order"),)
    elif kind == "interpolated":
        notes = ((
            f"node {requested_nm:g} nm is not a characterized node — "
            f"log-interpolated between {lo_name} and {hi_name}"),)

    return NodeResolution(
        requested=str(node), requested_nm=requested_nm, eval_nm=eval_nm,
        kind=kind, lo=lo_name, hi=hi_name, weight=weight,
        warnings=warnings, notes=notes)


class NodeScalingProvider:
    """Unit-cost provider adapter executing a :class:`NodeResolution`.

    Every metric query is answered from the inner provider evaluated at the
    resolution's characterized anchor node(s); two-anchor answers are combined
    log-linearly in log(node) (``weight`` may lie outside [0, 1] for
    extrapolation). Providers that ignore the node (hbm/d2dlink/placeholder)
    return identical anchor answers, which short-circuit unchanged.
    """

    def __init__(self, inner: Any, resolution: NodeResolution):
        self._inner = inner
        self._res = resolution
        self.calibrated = bool(getattr(inner, "calibrated", False))

    def _blend(self, method: str, primitive: str,
               features: Mapping[str, Any]) -> float:
        res = self._res
        call = getattr(self._inner, method)
        if res.kind == "exact":
            return call(primitive, {**features, "node": res.lo})
        y1 = call(primitive, {**features, "node": res.lo})
        y2 = call(primitive, {**features, "node": res.hi})
        if y1 == y2:
            return y1
        if y1 > 0 and y2 > 0:
            return math.exp((1.0 - res.weight) * math.log(y1)
                            + res.weight * math.log(y2))
        # Mixed-sign/zero anchors cannot be combined in log space; fall back to
        # linear and floor at 0 (an extrapolation weight could cross zero).
        return max(0.0, (1.0 - res.weight) * y1 + res.weight * y2)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("energy_per_cycle", primitive, features)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("leak_power", primitive, features)

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("area", primitive, features)

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("crit_path", primitive, features)


def apply_node_scaling(chain: Any, tech: Any) -> Tuple[Any, Optional[NodeResolution]]:
    """Wrap a ``ProviderChain`` so its provider serves the tech's node continuously.

    Returns the (possibly re-wrapped) chain plus the resolution. When the chain
    declares no characterized nodes (stub-only environments) the chain is
    returned untouched with ``None`` — legacy discrete behavior.

    An unparseable node raises ``ValueError`` — the console turns that into a
    clean CLI error.
    """
    characterized = tuple(getattr(chain, "characterized_nodes", ()) or ())
    if not characterized:
        return chain, None
    resolution = resolve_node(tech.node, characterized)
    wrapped = NodeScalingProvider(chain.provider, resolution)
    return _dc_replace(chain, provider=wrapped), resolution
