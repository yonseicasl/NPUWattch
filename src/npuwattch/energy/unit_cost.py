"""Unit-cost provider — the calling convention between the estimators and the
energy aggregator.

A ``UnitCostProvider`` answers, for one primitive instance at a queried
technology/PVT/frequency, the four §6 unit costs NPUWattch needs:

    energy_per_cycle(primitive, features)  pJ per active cycle in a given stim_mode
    leak_power(primitive, features)        mW per instance (static)
    area(primitive, features)              µm² per instance
    crit_path(primitive, features)         ns per instance

``features`` is a plain dict (the element's config ∪ the tech context ∪, for
energy, ``stim_mode``) — the same features-dict convention as
``EstimatorHost.estimate_energy(module, features)``. This is the interface the
**trained MLP models drop into** (workstream D, user item #4): a real provider
wraps ``EstimatorHost`` and returns per-(component×metric) MLP predictions. Until
those land, ``StubUnitCostProvider`` returns deterministic *placeholder* numbers so
the whole activity→energy pipeline runs end-to-end; its ``calibrated`` flag is
``False`` so any report can label the result a first-order estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - py<3.8
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

__all__ = ["TechContext", "UnitCostProvider", "StubUnitCostProvider",
           "D2DLinkCostProvider", "D2D_ENERGY_PER_BIT_PJ"]


@dataclass(frozen=True)
class TechContext:
    """Technology / PVT / frequency the estimators are queried at.

    Simulators know nothing of node/PVT — these come from the user (CLI/defaults).
    ``clock_mhz`` may be left ``None`` and filled per-run from the log's
    ``core_freq_mhz``.
    """

    node: str = "7nm"
    transistor: str = "hp"          # hp | lp
    corner: str = "TT"              # TT | SS | FF
    voltage_offset_V: float = 0.0   # −0.15 … +0.15
    temperature_C: float = 25.0
    clock_mhz: float | None = None

    def features(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "transistor": self.transistor,
            "corner": self.corner,
            "voltage_offset_V": self.voltage_offset_V,
            "temperature_C": self.temperature_C,
            "clock_mhz": self.clock_mhz,
        }


@runtime_checkable
class UnitCostProvider(Protocol):
    """Per-instance unit costs for a primitive at a queried tech/PVT/frequency."""

    #: False for placeholder providers → reports must flag "not calibrated".
    calibrated: bool

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def area(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float: ...


# ---------------------------------------------------------------------------
# Placeholder provider (deterministic, NOT calibrated)
# ---------------------------------------------------------------------------

# Relative dynamic activity of each stim_mode (idle ≈ leakage-only).
_STIM_ACTIVITY: Dict[str, float] = {
    "idle": 0.02,
    "read": 0.4,
    "write": 0.5,
    "hold_b": 0.6,
    "hold_scale": 0.6,
    "sparse50": 0.5,
    "stream": 0.7,
    "fixed_route": 0.7,
    "valid25": 0.35,
    "random": 1.0,
    # fpsfu op-group modes: one group's table + the shared PWL datapath active.
    "exp": 0.8,
    "trig": 0.8,
    "hyp": 0.8,
    "erf": 0.8,
}


def _effective_width(features: Mapping[str, Any]) -> int:
    """A rough operand width from the canonical width attributes.

    Only canonical names (``npuwattch.naming``) are read — harnesses translate
    their simulator's vocabulary at ingest, so by the time a features dict
    reaches a provider there is exactly one spelling per concept.
    """
    for k in ("data_width", "data_width_a", "data_width_out", "data_width_acc"):
        v = features.get(k)
        if isinstance(v, int):
            return max(1, v)
    exp = features.get("exponent_bits")
    mant = features.get("mantissa_bits")
    if isinstance(exp, int) and isinstance(mant, int):
        return exp + mant + 1
    return 16


@dataclass(frozen=True)
class StubUnitCostProvider:
    """Deterministic, physically-plausible-but-uncalibrated unit costs.

    Exists only so the pipeline yields numbers before the MLPs are trained. The
    magnitudes are order-of-magnitude toys, monotone in width, not real silicon.
    """

    calibrated: bool = False

    def _base_area_um2(self, primitive: str, features: Mapping[str, Any]) -> float:
        w = _effective_width(features)
        # MACs ~ w² (multiplier dominated); regfile ~ w·depth; else ~ w.
        if primitive in ("intmac", "fpmac", "mxfpmac"):
            base = 0.15 * w * w
        elif primitive == "fpsfu":
            # PWL evaluator: a mantissa multiplier (~w²) + one coefficient
            # table per enabled op group, scaled by the segment count.
            groups = sum(
                1 for k in ("sfu_op_exp", "sfu_op_trig", "sfu_op_hyp",
                            "sfu_op_erf", "sfu_op_relu")
                if int(features.get(k, 0) or 0)
            )
            segs = max(1, int(features.get("sfu_segments", 64)))
            base = 0.12 * w * w + 0.02 * w * segs * max(1, groups)
        elif primitive == "regfile":
            base = 0.05 * w * max(1, int(features.get("mem_depth_per_bank", 1)))
        else:
            base = 0.05 * w
        return base * (1.0 + max(0, int(features.get("pipeline_stages", 0))) * 0.1)

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._base_area_um2(primitive, features)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        # leakage ∝ area; a small mW/µm² density.
        return 2.0e-4 * self._base_area_um2(primitive, features)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        stim = str(features.get("stim_mode", "random"))
        activity = _STIM_ACTIVITY.get(stim, 1.0)
        w = _effective_width(features)
        # dynamic switching energy ~ area·activity, in pJ (toy scale).
        return 1.0e-3 * self._base_area_um2(primitive, features) * activity

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        w = _effective_width(features)
        stages = max(1, int(features.get("pipeline_stages", 1)))
        # log-depth path, shortened by pipelining.
        return (0.08 * math.log2(w + 1) + 0.05) / stages


# ---------------------------------------------------------------------------
# Analytic die-to-die link model (constant pJ/bit — no characterization flow)
# ---------------------------------------------------------------------------

#: Default die-to-die link traversal energy. A **literature constant**, not a
#: measurement: on-package SerDes/parallel PHYs land around 0.5–1 pJ/bit
#: (UCIe-class links; Simba's GRS reports 0.82–1.75 pJ/bit) — we take the
#: conservative round value. Override per component via the canonical
#: ``net_energy_per_bit_pJ`` attribute in the description.
D2D_ENERGY_PER_BIT_PJ = 1.0


@dataclass(frozen=True)
class D2DLinkCostProvider:
    """Chain link answering primitive ``d2dlink`` with the analytic constant.

    Energy per crossing = ``data_width × net_energy_per_bit_pJ``; there is no
    leakage/area/timing model (all 0.0 — the PHY is not ours to model).
    Everything else delegates to ``fallback``. ``calibrated`` is inherited from
    the fallback: a constant is never calibration.
    """

    fallback: Any = None

    @property
    def calibrated(self) -> bool:
        return bool(getattr(self.fallback, "calibrated", False))

    def _delegate(self, method: str, primitive: str,
                  features: Mapping[str, Any]) -> float:
        if self.fallback is None:
            raise ValueError(
                f"d2dlink provider got primitive {primitive!r} and has no fallback"
            )
        return getattr(self.fallback, method)(primitive, features)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "d2dlink":
            return self._delegate("energy_per_cycle", primitive, features)
        bits = int(features.get("data_width") or 0)
        per_bit = features.get("net_energy_per_bit_pJ")
        if not isinstance(per_bit, (int, float)) or per_bit <= 0:
            per_bit = D2D_ENERGY_PER_BIT_PJ
        return bits * float(per_bit)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "d2dlink":
            return self._delegate("leak_power", primitive, features)
        return 0.0

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "d2dlink":
            return self._delegate("area", primitive, features)
        return 0.0

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "d2dlink":
            return self._delegate("crit_path", primitive, features)
        return 0.0
