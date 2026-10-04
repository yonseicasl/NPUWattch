"""Unit-cost provider: the calling convention between the estimators and the
energy calculation.

A ``UnitCostProvider`` gives the four unit costs of manual §6 for one instance
of a primitive, at the technology, PVT, and frequency of the query:

    energy_per_cycle(primitive, features)  pJ for one active cycle in one stim_mode
    leak_power(primitive, features)        mW for one instance (static)
    area(primitive, features)              µm² for one instance
    crit_path(primitive, features)         ns for one instance

``features`` is a dict. It contains the attributes of the component and the
technology context. For an energy query, it also contains ``stim_mode``.
``EstimatorHost.estimate_energy(module, features)`` uses the same dict
convention. The provider of an estimator returns the predictions of its
trained MLP models through this interface.

The providers make a chain (``provider_factory``). Each provider answers for
its own primitives and sends the other queries to the next provider. The last
link is ``NoModelProvider``, which raises an error: NPUWattch gives no value
for a block that it has no model for. The user gives the cost of such a block
in the user component library (``npuwattch.user_components``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml

from .dram_table import default_table

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - py<3.8
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

__all__ = ["TechContext", "UnitCostProvider", "NoModelError",
           "NoModelProvider",
           "D2DLinkCostProvider", "D2D_ENERGY_PER_BIT_PJ",
           "HBMCostProvider", "HBM_ACT_ENERGY_PJ",
           "HBM_ACCESS_ENERGY_PER_BIT_PJ", "HBM_REF_ENERGY_PJ"]


@dataclass(frozen=True)
class TechContext:
    """The technology, PVT, and frequency of the estimator queries.

    A simulator does not know the node or the PVT. The user gives them on the
    CLI, or the defaults apply. ``clock_mhz`` can be ``None``. The estimators
    then use the clock of the description.
    """

    node: str = "7nm"
    transistor: str = "hp"          # hp | lp
    corner: str = "TT"              # TT | SS | FF
    voltage_offset_V: float = 0.0   # from −0.15 to +0.15
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
    """The unit costs of one instance of a primitive, for the queried features."""

    #: False if a value can come from a model that is not calibrated.
    calibrated: bool

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def area(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float: ...
    # Two methods are optional. The callers find them with getattr.
    #
    # ``idle_terms(primitive, features) ->
    # (e_idle_per_cycle_pJ, idle_displaced_per_access_pJ) | None``:
    # with these terms, the energy calculation charges the clocked-idle energy
    # of a memory one time for each cycle, not in each access event. Refer to
    # aggregate._book_idle_per_cycle.
    #
    # ``envelope_warnings(primitive, features) -> List[str]``: the reasons why
    # a query is not a characterized design point (a clamped depth, or an
    # extrapolated parameter or clock). aggregate_native shows them one time
    # for each component.


# ---------------------------------------------------------------------------
# End of the provider chain
# ---------------------------------------------------------------------------

class NoModelError(ValueError):
    """No provider has a model for a primitive."""


@dataclass(frozen=True)
class NoModelProvider:
    """The last link of the provider chain. It has no model.

    A query that arrives here is for a primitive that no estimator serves.
    Each method raises :class:`NoModelError`. To give the cost of such a
    block, the user adds it to the user component library
    (``npuwattch.user_components``).
    """

    #: This provider gives no value, thus it gives no uncalibrated value.
    calibrated: bool = True

    def _raise(self, primitive: str) -> float:
        raise NoModelError(
            f"no model for class {primitive!r} — NPUWattch has no estimator "
            f"for it; give its area and action energies in the user component "
            f"library (--user-components)")

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._raise(primitive)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._raise(primitive)

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._raise(primitive)

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        return self._raise(primitive)


# ---------------------------------------------------------------------------
# Die-to-die link model: a constant energy for each bit, from a table file
# ---------------------------------------------------------------------------

#: The directory of the link energy tables (package data).
LINK_TABLE_DIR = Path(__file__).resolve().parent / "link_tables"


def _load_d2d_energy_per_bit() -> float:
    """Read the default d2dlink constant from ``link_tables/d2dlink.yml``."""
    path = LINK_TABLE_DIR / "d2dlink.yml"
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))["energy_pj_per_bit"]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
        raise ValueError(f"link energy table {path}: {e}") from e
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(
            f"link energy table {path}: energy_pj_per_bit must be a positive "
            f"number, got {value!r}")
    return float(value)


#: Default energy of the ``d2dlink`` primitive for each bit. It comes from
#: ``link_tables/d2dlink.yml``, which has the value and its source. A
#: component can give its own value with the attribute
#: ``net_energy_per_bit_pJ``.
D2D_ENERGY_PER_BIT_PJ = _load_d2d_energy_per_bit()


@dataclass(frozen=True)
class D2DLinkCostProvider:
    """The provider of the primitive ``d2dlink``. It uses a constant.

    The energy of one flit that crosses the link is
    ``data_width × net_energy_per_bit_pJ``. Leakage, area, and timing are 0.0,
    because NPUWattch has no model of the PHY. The provider sends the queries
    for all other primitives to ``fallback``.

    ``calibrated`` comes from the fallback. A constant is not a calibrated
    model, thus it cannot change this value.
    """

    #: The primitives that this provider answers with a constant.
    primitives = ("d2dlink",)

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

    def idle_terms(self, primitive: str, features: Mapping[str, Any]):
        if primitive == "d2dlink" or self.fallback is None:
            return None
        fb = getattr(self.fallback, "idle_terms", None)
        return fb(primitive, features) if fb is not None else None

    def envelope_warnings(self, primitive: str, features: Mapping[str, Any]):
        if primitive == "d2dlink" or self.fallback is None:
            return []
        fb = getattr(self.fallback, "envelope_warnings", None)
        return list(fb(primitive, features)) if fb is not None else []


# ---------------------------------------------------------------------------
# DRAM device model: a constant energy for each command, from a table file
# ---------------------------------------------------------------------------

#: Default per-command energies of the ``hbm`` primitive. They come from the
#: default DRAM energy table, ``dram_tables/hbm2.yml``. That file has the
#: values and their source. A component can give its own values with the
#: attributes ``mem_act_energy_pJ``, ``mem_access_energy_per_bit_pJ``, and
#: ``mem_ref_energy_pJ``.
HBM_ACT_ENERGY_PJ = default_table().act_pj
HBM_ACCESS_ENERGY_PER_BIT_PJ = default_table().transfer_pj_per_bit
HBM_REF_ENERGY_PJ = default_table().ref_pj


@dataclass(frozen=True)
class HBMCostProvider:
    """The provider of the primitive ``hbm``. It uses constants.

    ``stim_mode`` selects the energy of one event:

    * ``activate`` and ``refresh``: the constant of that command.
    * ``read``, ``write``, and ``random``: ``data_width`` × the access energy
      for each bit. A vectorless run uses ``random``.
    * ``idle``: 0.0.

    Leakage, area, and timing are 0.0. NPUWattch does not model the DRAM die
    or its background and standby power, because vendor IDD values are not
    public. The projection declares this power as out_of_scope.

    The provider sends the queries for all other primitives to ``fallback``.
    ``calibrated`` comes from the fallback. A constant is not a calibrated
    model, thus it cannot change this value.
    """

    #: The primitives that this provider answers with a constant.
    primitives = ("hbm",)

    fallback: Any = None

    @property
    def calibrated(self) -> bool:
        return bool(getattr(self.fallback, "calibrated", False))

    def _delegate(self, method: str, primitive: str,
                  features: Mapping[str, Any]) -> float:
        if self.fallback is None:
            raise ValueError(
                f"hbm provider got primitive {primitive!r} and has no fallback"
            )
        return getattr(self.fallback, method)(primitive, features)

    @staticmethod
    def _const(features: Mapping[str, Any], key: str, default: float) -> float:
        v = features.get(key)
        return float(v) if isinstance(v, (int, float)) and v > 0 else default

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "hbm":
            return self._delegate("energy_per_cycle", primitive, features)
        mode = features.get("stim_mode")
        if mode == "activate":
            return self._const(features, "mem_act_energy_pJ", HBM_ACT_ENERGY_PJ)
        if mode == "refresh":
            return self._const(features, "mem_ref_energy_pJ", HBM_REF_ENERGY_PJ)
        if mode == "idle":
            return 0.0
        bits = int(features.get("data_width") or 0)
        per_bit = self._const(features, "mem_access_energy_per_bit_pJ",
                              HBM_ACCESS_ENERGY_PER_BIT_PJ)
        return bits * per_bit                    # read, write, or random

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "hbm":
            return self._delegate("leak_power", primitive, features)
        return 0.0

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "hbm":
            return self._delegate("area", primitive, features)
        return 0.0

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "hbm":
            return self._delegate("crit_path", primitive, features)
        return 0.0

    def idle_terms(self, primitive: str, features: Mapping[str, Any]):
        if primitive == "hbm" or self.fallback is None:
            return None
        fb = getattr(self.fallback, "idle_terms", None)
        return fb(primitive, features) if fb is not None else None

    def envelope_warnings(self, primitive: str, features: Mapping[str, Any]):
        if primitive == "hbm" or self.fallback is None:
            return []
        fb = getattr(self.fallback, "envelope_warnings", None)
        return list(fb(primitive, features)) if fb is not None else []
