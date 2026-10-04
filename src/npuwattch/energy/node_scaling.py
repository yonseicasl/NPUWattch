"""Evaluate a technology node that is not a characterized node.

The MLP estimators have models for a small set of characterized nodes
(5, 7, 10, 16, and 20 nm). The node is a one-hot input, and an estimator
raises an error for a different node. But the CLI accepts a continuous node
value, because Accelergy and Timeloop descriptions frequently use 65, 45, or
32 nm.

The rules are:

* The supported envelope is the characterized range with **50 %** added on
  each side. The lower bound is the minimum characterized node x 0.5. The
  upper bound is the maximum characterized node x 1.5. For the 5 nm to 20 nm
  datasets, the envelope is **2.5 nm to 30 nm**.
* A node between two characterized nodes uses **log-log interpolation** of
  the two anchor predictions. Energy, area, and delay are polynomial functions
  of the feature size, thus a straight line in log-log space is a good local
  model.
* A node outside the characterized range and inside the envelope uses log-log
  **extrapolation** from the two nodes at that edge. The run gets a warning.
* A node outside the envelope is **clamped** to the nearest envelope bound,
  and the run continues. The CLI and the report show a warning. The results
  are then for the envelope bound, not for the requested node.

The estimators do not change. This module queries them only at characterized
nodes, thus the node check of each estimator continues to operate for a
direct API call.
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

#: The envelope factors. The envelope is from the minimum characterized node
#: x 0.5 to the maximum characterized node x 1.5. A node outside the envelope
#: is clamped, with a warning.
ENVELOPE_LO_FACTOR = 0.5
ENVELOPE_HI_FACTOR = 1.5

#: The relative tolerance to decide that a node is a characterized node.
_EXACT_RTOL = 1e-6


def parse_node_nm(value: Any) -> float:
    """Return the node in nanometers. Examples: "7nm", "8.5nm", 12, "45NM".

    Raise ``ValueError`` if the value is not a positive length in nm.
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
    """Return the envelope: characterized minimum x 0.5 to maximum x 1.5."""
    return (min(characterized_nm) * ENVELOPE_LO_FACTOR,
            max(characterized_nm) * ENVELOPE_HI_FACTOR)


@dataclass(frozen=True)
class NodeResolution:
    """The method to evaluate a requested node with the characterized nodes.

    ``kind`` is one of:

    * ``exact``: the requested node is a characterized node. Each query uses
      one anchor.
    * ``interpolated``: the node is inside the characterized range. Each query
      uses log-log interpolation between the two adjacent anchors. The run
      gets a note.
    * ``extrapolated``: the node is outside the characterized range and inside
      the +-50 % envelope. Each query uses log-log extrapolation from the two
      anchors at the edge. The run gets a warning.
    * ``clamped``: the node is outside the envelope. Each query uses the
      envelope bound, with the two anchors at the edge. The run gets a
      warning, because the results are for the bound and not for the request.
    """

    requested: str
    requested_nm: float
    eval_nm: float
    kind: str
    lo: str                       # the anchor nodes, from the characterized set
    hi: str
    weight: float                 # the position of eval_nm on the log axis from lo to hi
    warnings: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


def resolve_node(node: Any, characterized: Sequence[str]) -> NodeResolution:
    """Make the :class:`NodeResolution` of ``node`` for the ``characterized`` nodes.

    ``characterized`` is a list of node strings, for example ["5nm", "7nm"].
    Raise ``ValueError`` only if the function cannot parse the node. Each
    node that it can parse gets a resolution. A node outside the envelope is
    clamped.
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
    """A provider that applies a :class:`NodeResolution` to an inner provider.

    For each query, this provider queries the inner provider at the anchor
    nodes of the resolution. If there are two anchors, it combines the two
    answers linearly in log(value) against log(node). For extrapolation,
    ``weight`` can be outside [0, 1].

    Some providers do not use the node (hbm, d2dlink, user components). Their
    two answers are equal, and this provider returns that value.
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
        # Log space is not possible if an anchor value is zero or negative.
        # Use linear interpolation then. The minimum result is 0, because an
        # extrapolation weight can give a negative value.
        return max(0.0, (1.0 - res.weight) * y1 + res.weight * y2)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("energy_per_cycle", primitive, features)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("leak_power", primitive, features)

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("area", primitive, features)

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._blend("crit_path", primitive, features)

    def idle_terms(self, primitive: str, features: Mapping[str, Any]):
        fn = getattr(self._inner, "idle_terms", None)
        if fn is None:
            return None
        res = self._res
        lo = fn(primitive, {**features, "node": res.lo})
        if res.kind == "exact" or lo is None:
            return lo
        hi = fn(primitive, {**features, "node": res.hi})
        if hi is None:
            return lo

        def mix(y1: float, y2: float) -> float:
            if y1 == y2:
                return y1
            if y1 > 0 and y2 > 0:
                return math.exp((1.0 - res.weight) * math.log(y1)
                                + res.weight * math.log(y2))
            return max(0.0, (1.0 - res.weight) * y1 + res.weight * y2)

        return (mix(lo[0], hi[0]), mix(lo[1], hi[1]))

    def envelope_warnings(self, primitive: str, features: Mapping[str, Any]):
        """Return the envelope warnings of the inner provider at the anchor nodes.

        The list has no duplicates. Its order is the order of the anchors.
        """
        fn = getattr(self._inner, "envelope_warnings", None)
        if fn is None:
            return []
        res = self._res
        anchors = [res.lo] if res.kind == "exact" else [res.lo, res.hi]
        out = []
        for node in anchors:
            for w in fn(primitive, {**features, "node": node}):
                if w not in out:
                    out.append(w)
        return out


def apply_node_scaling(chain: Any, tech: Any) -> Tuple[Any, Optional[NodeResolution]]:
    """Put a :class:`NodeScalingProvider` around the provider of a ``ProviderChain``.

    Return the new chain and the resolution of the node of ``tech``. If the
    chain declares no characterized nodes, return the same chain and ``None``.
    The providers then get the node of ``tech`` without a change.

    If the function cannot parse the node, it raises ``ValueError``. The CLI
    shows this as an error message.
    """
    characterized = tuple(getattr(chain, "characterized_nodes", ()) or ())
    if not characterized:
        return chain, None
    resolution = resolve_node(tech.node, characterized)
    wrapped = NodeScalingProvider(chain.provider, resolution)
    return _dc_replace(chain, provider=wrapped), resolution
