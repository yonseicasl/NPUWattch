"""Logic primitive estimator: the trained v2 MLP models as a UnitCostProvider.

This estimator gives the cost of the logic primitives. The models are the
``<component>_<metric>__v2.*`` checkpoints in this directory. Each primitive
has four models:

- the dynamic energy of one cycle [pJ] at a stim_mode
- the leakage power [mW]
- the PnR area [um2]
- the critical path [ns]

Each model is a ``logic_mlp`` MLP. Its inputs are the log-transformed design
parameters and the one-hot codes of the node and of the mode.

The estimator also serves the NoC fabric blocks (``crossbar``, ``fattree``,
``foldedclos``). The fabric models have one limit:

- A large fabric is an extrapolation. The crossbar of the BookSim emitter has
  a 256 b flit (32 B) and 32 ports. This is approximately 2x more than the
  trained envelope of 128 b and 16 ports. The extrapolation is monotone and
  approximately N^2 in the port count. There is no data to validate it.

The estimator accepts ``net_switch_radix`` for foldedclos and ignores it. The
RTL calculates it from the terminals and the active uplinks, thus the sweep
did not change it.

This module changes the NPUWattch names of a description into the dataset
columns. A description uses ``exponent_bits``, ``data_width_a``,
``mem_depth_per_bank``, and ``net_inputs`` (npuwattch.naming). The dataset
uses the names of the RTL sweep: ``exp_bits``, ``a_width``, ``depth``, and
``num_inputs``.

Model inputs that are not in the description:

- ``clock``. Each design was implemented for its clock constraint, thus all
  four metrics use ``log10_clock_ns``. The §6 aggregator supplies the clock of
  the run as the ``clock_mhz`` feature. An explicit ``--clock-mhz`` or the
  clock of the TechContext has priority. A query without a clock uses 1 ns
  (1 GHz), which is the center of the sweep.
- PVT. The v2 dataset has only TT, 25 °C, and the nominal voltage. The
  estimator accepts the corner, voltage, and temperature features and ignores
  them. A dataset with a PVT sweep needs a new VERSION and these axes.
- ``node``. The node must be one of the characterized nodes (5, 7, 10, 16,
  20 nm). A different node raises an error, because the models have a one-hot
  node input. The continuous node axis is above this estimator:
  ``npuwattch.energy.node_scaling`` queries the two adjacent characterized
  nodes and combines the results on a log-log scale (manual §6.2). Thus this
  estimator gets only characterized nodes.

Characterized envelope (``envelope__v2.json``, which train_logic.py writes
from the training CSVs; see ``envelope_warnings``):

- If ``pipeline_stages`` is outside the characterized depths, the estimator
  uses the nearest characterized depth. The RTL has no design with a smaller
  or larger depth, and the MLP has no physical reference there. The depth is
  the registered latency and includes the input and output registers. Thus an
  fpadd or fpmul with ps=2 is the single-cycle reg->logic->reg unit, and the
  minimum depth of fpmac is ps=4.
- The estimator calculates a query that has other parameters outside their
  characterized range, and reports it as an extrapolation.
- The estimator does the same for a clock that is faster than the fastest
  implementation of that configuration, or outside the clock range of the
  node.

``EstimatorHost`` loads this module with runpy. Thus the module imports its
sibling ``logic_mlp.py`` by file path, and only when it is necessary. That
import also imports torch. If torch is not available,
``make_unit_cost_provider`` raises. The provider factory then records a note
and does not use this estimator.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

MODULE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# ESTIMATOR_SPEC must be a pure literal. The EstimatorHost reads it with
# ast.literal_eval.
# --------------------------------------------------------------------------

ESTIMATOR_SPEC = {
    "primitive": "logic",
    # The served primitives: each primitive that has v2 models.
    "primitives": ["fpadd", "fpmul", "fpmac", "intadd", "intmul", "intmac",
                   "fpsfu", "mxfpmac", "fifo", "regfile", "simplemux",
                   "crossbar", "fattree", "foldedclos"],
    # The characterized nodes. They must be the same as logic_mlp.NODE_LIST.
    # energy.node_scaling interpolates the continuous node axis of the CLI
    # between these nodes.
    "nodes": ["5nm", "7nm", "10nm", "16nm", "20nm"],
    "version": "2.2",
    "description": (
        "Calibrated logic-primitive estimator: post-layout-trained v2 MLP "
        "quartets (energy/leakage/timing/area) for every characterized logic "
        "primitive — arithmetic, SFU, MX, fifo/regfile and the NoC blocks; "
        "stim_mode is a model input for the power metrics. The fabric models "
        "extrapolate past their trained envelopes on large fabrics."
    ),
    "entrypoints": {
        "unit_cost_provider": "make_unit_cost_provider",
    },
}

#: The clock period [ns] for a query that has no clock_mhz feature.
DEFAULT_CLOCK_NS = 1.0

#: The default pipeline_stages of each component, if the description does not
#: give it. The characterized ranges are in naming.py: int 2-5, fpadd/fpmul
#: 2-9, fpmac 4-18, fpsfu 4-10. The default mxfpmac is combinational (1 stage).
_PIPELINE_DEFAULTS = {
    "fpadd": 2, "fpmul": 2, "fpmac": 4,
    "intadd": 2, "intmul": 2, "intmac": 2,
    "fpsfu": 10, "mxfpmac": 1,
}

_MLP_MOD_CACHE: Dict[str, Any] = {"mod": None, "err": None}


def _mlp():
    """Import the sibling module logic_mlp.py by its path. Keep the result."""
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


#: The oversubscription values of the fabric sweep. The RTL accepts a value
#: in (0, 1]. The feature is log2 of the value, thus the models interpolate a
#: value that is between these three.
_OVERSUB_CHARACTERIZED = (0.25, 0.5, 1.0)


def _oversubscription(f: Mapping[str, Any], component: str) -> float:
    """Return the ratio of the up capacity to the down capacity.

    The default is 1.0 (no oversubscription), as in the sweep.
    """
    v = _opt(f, "net_oversubscription", 1.0)
    if not 0.0 < v <= 1.0:
        raise ValueError(
            f"logic/{component}: net_oversubscription must be in (0, 1] "
            f"(got {v!r})")
    return v


def _params_for(component: str, f: Mapping[str, Any]) -> Dict[str, Any]:
    """Change the attributes of a component into its dataset parameters."""
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
            # The operation-group tables that the design contains. The
            # default is the four transcendental groups, without relu.
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
        # The RTL has no parameter for a shared read/write port. A 1RW file
        # uses the 1R1W model: the same array with one port pair.
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
        # The NoC compound component gives a k x k router with net_inputs
        # equal to net_outputs. If a query gives only one side, the crossbar
        # is square.
        ni = _opt(f, "net_inputs", None)
        no = _opt(f, "net_outputs", None)
        if ni is None and no is None:
            _need(f, "net_inputs", component)   # raises an error with the name
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
        # net_switch_radix is a necessary attribute of the description, but
        # it is NOT a model input. The RTL calculates it from the terminals
        # and the active uplinks, thus the sweep did not change it.
        return {
            "data_width": _need(f, "data_width", component),
            "terminals_per_leaf": _need(f, "net_terminals_per_leaf", component),
            "num_leaves": _need(f, "net_leaves", component),
            "num_spines": _need(f, "net_spines", component),
            "oversubscription": _oversubscription(f, component),
        }
    raise ValueError(f"logic: unmapped component {component!r}")


class _LogicUnitCostProvider:
    """A provider that gets the cost of the served logic primitives from the
    v2 MLPs.

    A query for a different primitive (sram, d2dlink, hbm, or a user
    component) goes to ``fallback``.

    The class has the structure of the ``UnitCostProvider`` protocol: the
    ``calibrated`` flag and four methods. It does not import npuwattch, thus
    runpy can load this file. The provider keeps each prediction and uses it
    again for an equal query.
    """

    SERVED = tuple(ESTIMATOR_SPEC["primitives"])

    def __init__(self, defaults: Optional[Mapping[str, Any]] = None,
                 model_dir: Optional[str] = None, fallback: Any = None):
        self._defaults = dict(defaults or {})
        self._model_dir = Path(model_dir) if model_dir else MODULE_DIR
        self._fallback = fallback
        self._models: Dict[Tuple[str, str], Any] = {}
        self._memo: Dict[tuple, float] = {}
        self._env: Any = None               # the envelope JSON, loaded at its first use
        self._env_loaded = False
        self.calibrated = (True if fallback is None
                           else bool(getattr(fallback, "calibrated", False)))

    # -- access to the models ----------------------------------------------

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

    def _envelope_for(self, component: str) -> Optional[Mapping[str, Any]]:
        if not self._env_loaded:
            self._env = _mlp().load_envelope(self._model_dir)
            self._env_loaded = True
        if self._env is None:
            return None
        return self._env.get("components", {}).get(component)

    def _resolve(self, component: str, features: Mapping[str, Any]
                 ) -> Tuple[int, float, Dict[str, Any], Optional[int]]:
        """Return the node [nm], the clock [ns], and the dataset parameters.

        The fourth value is the requested depth if the provider changed it to
        a characterized depth. If not, it is None.
        """
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
        requested = None
        env = self._envelope_for(component)
        depths = (env or {}).get("pipeline_stages") or []
        if "pipeline_stages" in params and depths:
            ps = int(params["pipeline_stages"])
            clamped = min(max(ps, min(depths)), max(depths))
            if clamped != ps:
                requested = ps
                params["pipeline_stages"] = clamped
        return nm, clock_ns, params, requested

    def _predict(self, component: str, metric: str,
                 features: Mapping[str, Any], mode: Optional[str]) -> float:
        mlp = _mlp()
        nm, clock_ns, params, _ = self._resolve(component, features)
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
        """Return the mode of the leakage query.

        Leakage is a static value, thus a mode without activity has priority.
        """
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

    # -- the UnitCostProvider protocol -------------------------------------

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

    def idle_terms(self, primitive: str, features: Mapping[str, Any]):
        """Return the idle terms of a primitive (optional protocol method).

        Logic primitives have no idle terms. A query for a different
        primitive goes to the fallback.
        """
        if primitive in self.SERVED or self._fallback is None:
            return None
        fb = getattr(self._fallback, "idle_terms", None)
        return fb(primitive, features) if fb is not None else None

    def envelope_warnings(self, primitive: str,
                          features: Mapping[str, Any]) -> List[str]:
        """Return the reasons why a query is not a characterized design point
        (optional protocol method).

        The reasons are a changed depth, an extrapolated parameter, or an
        extrapolated clock. There is one message for each reason. The list is
        empty if the query is in the envelope.
        """
        if primitive not in self.SERVED:
            fb = getattr(self._fallback, "envelope_warnings", None)
            return list(fb(primitive, features)) if fb is not None else []
        env = self._envelope_for(primitive)
        if env is None:
            return []
        mlp = _mlp()
        nm, clock_ns, params, requested = self._resolve(primitive, features)
        out: List[str] = []
        depths = env.get("pipeline_stages") or []
        if requested is not None:
            out.append(
                f"pipeline_stages={requested} is outside the characterized "
                f"{min(depths)}-{max(depths)} for {primitive} (depth = "
                f"registered latency incl. input/output registers) — "
                f"evaluated at pipeline_stages={params['pipeline_stages']}")
        for col, (lo, hi) in sorted(env.get("params", {}).items()):
            if col == "pipeline_stages" or col not in params:
                continue
            v = float(params[col])
            if not lo <= v <= hi:
                out.append(
                    f"{col}={v:g} is outside the characterized {lo:g}-{hi:g} "
                    f"for {primitive} — extrapolated")
        fastest = (env.get("config_min_clock_ns", {}).get(str(nm), {})
                   .get(mlp.config_key(primitive, params)))
        lo_hi = env.get("clock_ns", {}).get(str(nm))
        mhz = 1000.0 / clock_ns
        # A tolerance of 0.5%: a clock in rounded MHz (307.7 for 3.25 ns) is
        # the characterized point, not an extrapolation.
        tol = 0.005
        if fastest is not None and clock_ns < fastest * (1 - tol):
            out.append(
                f"clock {clock_ns:g} ns ({mhz:.0f} MHz) is faster than the "
                f"fastest characterized implementation of this {primitive} "
                f"configuration at {nm} nm ({fastest:g} ns, "
                f"{1000.0 / fastest:.0f} MHz) — extrapolated along the clock "
                f"axis; a deeper pipeline or slower clock is characterized")
        elif (lo_hi is not None
              and not lo_hi[0] * (1 - tol) <= clock_ns <= lo_hi[1] * (1 + tol)):
            side = "faster" if clock_ns < lo_hi[0] else "slower"
            out.append(
                f"clock {clock_ns:g} ns ({mhz:.0f} MHz) is {side} than any "
                f"characterized {primitive} at {nm} nm ({lo_hi[0]:g}-"
                f"{lo_hi[1]:g} ns) — extrapolated along the clock axis")
        return out


def make_unit_cost_provider(defaults: Optional[Mapping[str, Any]] = None,
                            model_dir: Optional[str] = None,
                            fallback: Any = None) -> _LogicUnitCostProvider:
    """Make a UnitCostProvider for the served logic primitives.

    The features of each query have priority over ``defaults``. ``fallback``
    answers each primitive that this estimator does not serve (sram, d2dlink,
    hbm, user components). The function raises if torch or the v2 checkpoints
    are not available. The provider factory then records a note and does not
    change the provider chain.
    """
    provider = _LogicUnitCostProvider(defaults=defaults, model_dir=model_dir,
                                      fallback=fallback)
    # Load one model now. Thus a checkpoint problem stops the provider
    # factory, and not the energy aggregation.
    provider._model("fpmac", "energy")
    return provider
