"""LOGIC primitive estimator — the trained v2 MLP quartets as a UnitCostProvider.

Serves the gate-passing logic primitives (eval_report.json ``gates``,
2026-08-09) from the ``<component>_<metric>__v2.*`` checkpoints in this
directory: per-cycle dynamic energy [pJ] at a stim_mode, leakage power [mW],
PnR area [um2] and critical path [ns], each a ``logic_mlp`` MLP over
log-transformed design params + node/mode one-hots.

The NoC fabric blocks — ``crossbar`` (10.2% energy MAPE), ``fattree`` (11.1%)
and ``foldedclos`` (13.7%) — are served despite missing the 10% promotion
gate (user decision 2026-08-12). The gate ranks models against each other;
the question at runtime is *model or placeholder*, and the placeholder is not
close: on post-layout truth for a 7 nm 128 b 8x8 crossbar (3.049 pJ/cycle) it
returns 0.006 pJ/cycle — **476x low** — where this model lands within 0.8%.
Two standing caveats until the 2026-08-09 expanded sweep is trained in:

- their grids are config-starved (15-19 configs each vs fifo 32 / regfile 46),
  so the quoted MAPEs rest on 1-2 held-out configs and are themselves noisy;
- large fabrics extrapolate: the emitter's production crossbar (BookSim 32 B
  flit = 256 b, 32 ports) sits ~2x past the trained 128 b / 16-port envelope.
  Extrapolation is monotone and ~N^2 in port count, i.e. physically ordered,
  but unvalidated.

``net_switch_radix`` is accepted for foldedclos and ignored: the RTL derives
it from terminals + active uplinks, so the sweep never varied it.

Feature translation (canonical vocabulary → dataset columns) lives here, on
the estimator side of the naming freeze: a description speaks
``exponent_bits`` / ``data_width_a`` / ``mem_depth_per_bank`` /
``net_inputs`` (npuwattch.naming), the dataset speaks the RTL sweep's
``exp_bits`` / ``a_width`` / ``depth`` / ``num_inputs``.

Model inputs the description does not carry:

- ``clock`` — every design was implemented against its clock constraint, so
  all four metrics take ``log10_clock_ns``. The §6 aggregator injects the
  run's clock as the ``clock_mhz`` feature (an explicit ``--clock-mhz`` /
  TechContext clock wins); a query without one uses 1 ns (1 GHz), the sweep's
  center.
- PVT — the v2 dataset is TT / 25 °C / nominal-V only; corner/voltage/
  temperature features are accepted but ignored (a PVT-swept dataset bumps
  VERSION and re-adds the axes).
- ``node`` must be one of the characterized nodes (5/7/10/16/20 nm) — anything
  else raises rather than extrapolating a one-hot the models cannot express.

This module is loaded by ``EstimatorHost`` via runpy, so it imports its
sibling ``logic_mlp.py`` (and torch, transitively) lazily by file path —
a torch-less environment fails at ``make_unit_cost_provider`` time, which the
provider factory records as a note and skips, never killing the run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

MODULE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# ESTIMATOR_SPEC — pure literal (EstimatorHost ast.literal_eval's it).
# --------------------------------------------------------------------------

ESTIMATOR_SPEC = {
    "primitive": "logic",
    # Served primitives — every v2 quartet. The gate-failing fabric blocks
    # (crossbar/fattree/foldedclos, 10-14% energy) are served anyway: the
    # placeholder they replace is ~500x off, so a config-starved model is
    # still the accurate choice (user decision 2026-08-12; retrain drops the
    # caveat when the expanded NoC sweep lands).
    "primitives": ["fpadd", "fpmul", "fpmac", "intadd", "intmul", "intmac",
                   "fpsfu", "mxfpmac", "fifo", "regfile", "simplemux",
                   "crossbar", "fattree", "foldedclos"],
    "version": "2.2",
    "description": (
        "Calibrated logic-primitive estimator: post-layout-trained v2 MLP "
        "quartets (energy/leakage/timing/area) for every characterized logic "
        "primitive — arithmetic, SFU, MX, fifo/regfile and the NoC blocks; "
        "stim_mode is a model input for the power metrics. The fabric models "
        "(crossbar 10.2%, fattree 11.1%, foldedclos 13.7% energy MAPE) are "
        "config-starved pending the expanded NoC sweep and extrapolate past "
        "their trained envelopes on large fabrics."
    ),
    "entrypoints": {
        "unit_cost_provider": "make_unit_cost_provider",
    },
}

#: clock period used when a query carries no clock_mhz feature [ns].
DEFAULT_CLOCK_NS = 1.0

#: pipeline_stages default per component when the description omits it — the
#: characterized range minimum (naming.py doc: int 2-5, fpadd/fpmul 2-9,
#: fpmac 4-18, fpsfu 4-10; mxfpmac's pre-07-21 template is combinational).
_PIPELINE_DEFAULTS = {
    "fpadd": 2, "fpmul": 2, "fpmac": 4,
    "intadd": 2, "intmul": 2, "intmac": 2,
    "fpsfu": 10, "mxfpmac": 1,
}

_MLP_MOD_CACHE: Dict[str, Any] = {"mod": None, "err": None}


def _mlp():
    """Import sibling logic_mlp.py by path (runpy-safe), memoized."""
    if _MLP_MOD_CACHE["mod"] is None and _MLP_MOD_CACHE["err"] is None:
        try:
            spec = importlib.util.spec_from_file_location(
                "_npuwattch_logic_mlp", MODULE_DIR / "logic_mlp.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            _MLP_MOD_CACHE.update(mod=mod, err=None)
        except Exception as e:
            sys.modules.pop("_npuwattch_logic_mlp", None)
            _MLP_MOD_CACHE.update(mod=None, err=f"{type(e).__name__}: {e}")
    if _MLP_MOD_CACHE["mod"] is None:
        raise RuntimeError(
            f"logic MLP layer unavailable ({_MLP_MOD_CACHE['err']}) — "
            f"torch and the v2 checkpoints are required")
    return _MLP_MOD_CACHE["mod"]


def _need(features: Mapping[str, Any], key: str, component: str) -> float:
    v = features.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ValueError(
            f"logic/{component}: required attribute {key!r} is missing or "
            f"non-numeric (got {v!r})")
    return float(v)


def _opt(features: Mapping[str, Any], key: str,
         default: Optional[float]) -> Optional[float]:
    v = features.get(key)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return default


#: oversubscription values the fabric sweep characterized. The RTL requires
#: (0, 1]; the models saw only these three, and the feature is log2 of the
#: value, so an unseen ratio interpolates between them.
_OVERSUB_CHARACTERIZED = (0.25, 0.5, 1.0)


def _oversubscription(f: Mapping[str, Any], component: str) -> float:
    """Up/down capacity ratio, defaulting to the sweep's fully-provisioned 1.0."""
    v = _opt(f, "net_oversubscription", 1.0)
    if not 0.0 < v <= 1.0:
        raise ValueError(
            f"logic/{component}: net_oversubscription must be in (0, 1] "
            f"(got {v!r})")
    return v


def _params_for(component: str, f: Mapping[str, Any]) -> Dict[str, Any]:
    """Canonical component attributes → the component's dataset params."""
    if component in ("fpadd", "fpmul", "fpmac"):
        return {
            "exp_bits": _need(f, "exponent_bits", component),
            "mantissa_bits": _need(f, "mantissa_bits", component),
            "pipeline_stages": _opt(f, "pipeline_stages",
                                    _PIPELINE_DEFAULTS[component]),
        }
    if component in ("intadd", "intmul", "intmac"):
        a = _opt(f, "data_width_a", None) or _need(f, "data_width", component)
        b = _opt(f, "data_width_b", None) or a
        out = _opt(f, "data_width_out", None) or max(a, b)
        params = {
            "a_width": a, "b_width": b, "out_width": out,
            "pipeline_stages": _opt(f, "pipeline_stages",
                                    _PIPELINE_DEFAULTS[component]),
        }
        if component == "intmac":
            params["acc_width"] = _need(f, "data_width_acc", component)
        return params
    if component == "fpsfu":
        return {
            "exp_bits": _need(f, "exponent_bits", component),
            "mantissa_bits": _need(f, "mantissa_bits", component),
            "sfu_segments": _need(f, "sfu_segments", component),
            "pipeline_stages": _opt(f, "pipeline_stages",
                                    _PIPELINE_DEFAULTS[component]),
            # op-group tables present in the design (compound default: all
            # four transcendental groups on, relu off)
            "sfu_op_exp": _opt(f, "sfu_op_exp", 1),
            "sfu_op_trig": _opt(f, "sfu_op_trig", 1),
            "sfu_op_hyp": _opt(f, "sfu_op_hyp", 1),
            "sfu_op_erf": _opt(f, "sfu_op_erf", 1),
            "sfu_op_relu": _opt(f, "sfu_op_relu", 0),
        }
    if component == "mxfpmac":
        return {
            "block_elems": _need(f, "mx_block_elems", component),
            "num_blocks": _need(f, "mx_blocks", component),
            "pipeline_stages": _opt(f, "pipeline_stages",
                                    _PIPELINE_DEFAULTS[component]),
            "input_format": str(f.get("mx_input_format")),
        }
    if component == "fifo":
        return {
            "width": _need(f, "data_width", component),
            "depth": _need(f, "mem_depth_per_bank", component),
        }
    if component == "regfile":
        # A shared-RW port has no separate RTL parameter; a 1RW file is
        # approximated as 1R1W (same array, one port pair).
        rw = _opt(f, "mem_rw_ports", 0) or 0
        return {
            "width": _need(f, "data_width", component),
            "depth": _need(f, "mem_depth_per_bank", component),
            "num_read_ports": _opt(f, "mem_r_ports", 0) or rw or 1,
            "num_write_ports": _opt(f, "mem_w_ports", 0) or rw or 1,
        }
    if component == "simplemux":
        return {
            "data_width": _need(f, "data_width", component),
            "num_inputs": _need(f, "net_inputs", component),
        }
    if component == "crossbar":
        # The NoC compound emits a k x k router as net_inputs == net_outputs;
        # a query giving only one side is read as square rather than rejected.
        ni = _opt(f, "net_inputs", None)
        no = _opt(f, "net_outputs", None)
        if ni is None and no is None:
            _need(f, "net_inputs", component)          # raises with the name
        return {
            "data_width": _need(f, "data_width", component),
            "num_inputs": ni if ni is not None else no,
            "num_outputs": no if no is not None else ni,
        }
    if component == "fattree":
        return {
            "data_width": _need(f, "data_width", component),
            "radix": _need(f, "net_radix", component),
            "num_levels": _need(f, "net_levels", component),
            "oversubscription": _oversubscription(f, component),
        }
    if component == "foldedclos":
        # net_switch_radix is a required description attribute but NOT a
        # model input: the RTL derives it (terminals + active uplinks), so
        # the sweep never varied it independently.
        return {
            "data_width": _need(f, "data_width", component),
            "terminals_per_leaf": _need(f, "net_terminals_per_leaf", component),
            "num_leaves": _need(f, "net_leaves", component),
            "num_spines": _need(f, "net_spines", component),
            "oversubscription": _oversubscription(f, component),
        }
    raise ValueError(f"logic: unmapped component {component!r}")


class _LogicUnitCostProvider:
    """Routes the served logic primitives to the v2 MLPs; the rest delegate.

    "The rest" is now only non-logic (sram, d2dlink, hbm) and user blocks —
    every characterized logic primitive is served.

    Implements the ``UnitCostProvider`` protocol structurally (calibrated flag
    + four methods) without importing npuwattch, so this file stays
    runpy-safe. Predictions are memoized per resolved query.
    """

    SERVED = tuple(ESTIMATOR_SPEC["primitives"])

    def __init__(self, defaults: Optional[Mapping[str, Any]] = None,
                 model_dir: Optional[str] = None, fallback: Any = None):
        self._defaults = dict(defaults or {})
        self._model_dir = Path(model_dir) if model_dir else MODULE_DIR
        self._fallback = fallback
        self._models: Dict[Tuple[str, str], Any] = {}
        self._memo: Dict[tuple, float] = {}
        self.calibrated = (True if fallback is None
                           else bool(getattr(fallback, "calibrated", False)))

    # -- model access ------------------------------------------------------

    def _model(self, component: str, metric: str):
        key = (component, metric)
        m = self._models.get(key)
        if m is None:
            mlp = _mlp()
            m = mlp.load_one(self._model_dir, component, metric)
            expect = mlp.feature_names(component, metric)
            got = list(m.meta.get("features", []))
            if got and got != expect:
                raise RuntimeError(
                    f"logic/{component}.{metric}: checkpoint feature order "
                    f"{got} != code {expect} — version drift, retrain or "
                    f"pin logic_mlp.VERSION")
            self._models[key] = m
        return m

    def _predict(self, component: str, metric: str,
                 features: Mapping[str, Any], mode: Optional[str]) -> float:
        mlp = _mlp()
        merged = {**self._defaults, **dict(features)}
        node = str(merged.get("node", ""))
        nm = mlp.node_nm(node)
        if nm not in mlp.NODE_LIST:
            raise ValueError(
                f"logic/{component}: node {node!r} is outside the "
                f"characterized set {sorted(mlp.NODE_LIST)} (nm) — no "
                f"extrapolation across the node one-hot")
        clock_mhz = merged.get("clock_mhz")
        clock_ns = (1000.0 / float(clock_mhz)
                    if isinstance(clock_mhz, (int, float)) and clock_mhz
                    else DEFAULT_CLOCK_NS)
        params = _params_for(component, merged)
        if mode is not None and mode not in mlp.STIM_MODES[component]:
            raise ValueError(
                f"logic/{component}: stim_mode {mode!r} was never "
                f"characterized (known: {mlp.STIM_MODES[component]})")
        key = (component, metric, nm, round(clock_ns, 6),
               tuple(sorted(params.items())), mode)
        hit = self._memo.get(key)
        if hit is None:
            vec = mlp.feature_vector(component, metric, nm, clock_ns,
                                     params, mode)
            hit = self._model(component, metric).predict_linear([vec])[0]
            self._memo[key] = hit
        return hit

    def _leak_mode(self, component: str) -> str:
        """Leakage is a static rating: prefer the quiescent rows."""
        mlp = _mlp()
        for m in ("idle", "none", "random"):
            if m in mlp.STIM_MODES[component]:
                return m
        return mlp.STIM_MODES[component][0]

    def _delegate(self, method: str, primitive: str,
                  features: Mapping[str, Any]) -> float:
        if self._fallback is None:
            raise ValueError(
                f"logic provider got primitive '{primitive}' and has no fallback")
        return getattr(self._fallback, method)(primitive, features)

    # -- UnitCostProvider protocol ----------------------------------------

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.SERVED:
            return self._delegate("energy_per_cycle", primitive, features)
        mode = str(features.get("stim_mode") or "random")
        return self._predict(primitive, "energy", features, mode)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.SERVED:
            return self._delegate("leak_power", primitive, features)
        return self._predict(primitive, "leakage", features,
                             self._leak_mode(primitive))

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.SERVED:
            return self._delegate("area", primitive, features)
        return self._predict(primitive, "area", features, None)

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive not in self.SERVED:
            return self._delegate("crit_path", primitive, features)
        return self._predict(primitive, "timing", features, None)


def make_unit_cost_provider(defaults: Optional[Mapping[str, Any]] = None,
                            model_dir: Optional[str] = None,
                            fallback: Any = None) -> _LogicUnitCostProvider:
    """Build a UnitCostProvider for the served logic primitives.

    ``defaults`` merge UNDER each call's features; ``fallback`` handles every
    primitive this estimator does not serve (sram, d2dlink, hbm, user blocks).
    Raises when torch or the v2 checkpoints are unavailable — the provider
    factory records that as a note and keeps the chain.
    """
    provider = _LogicUnitCostProvider(defaults=defaults, model_dir=model_dir,
                                      fallback=fallback)
    # Fail fast (and factory-visibly) if the checkpoints cannot serve: load
    # one quartet now instead of exploding mid-aggregation.
    provider._model("fpmac", "energy")
    return provider
