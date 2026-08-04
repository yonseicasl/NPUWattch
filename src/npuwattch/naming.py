"""Canonical input-name vocabulary — the single source of truth for the names
estimators accept in a component's ``attributes`` block.

Why this exists
---------------
Every harness (PyTorchSim, Timeloop/Accelergy, …) reads a simulator's own
vocabulary, which is *not* ours: Timeloop says ``word-bits``, gem5 says
``bitwidth``, our RTL generator says ``a_width``. Historically each estimator
accepted a *list* of aliases (``arch_keys``), which meant a typo silently fell
through to a default and two harnesses could disagree forever without anyone
noticing.

The contract is now inverted, and it is one-directional:

* **The estimator's accepted name is the standard.** Exactly one name per
  concept. No aliases.
* **A harness may warn about its own source log**, but the names it *emits* must
  already be canonical. Translating the simulator's vocabulary into ours is the
  harness author's job, done once, at ingest.
* **A non-canonical attribute name is an error**, not a silent default. If it is
  a known legacy alias, the error says what to rename it to.

Scope: this governs *architecture attributes* — the description's
``components[].attributes``, i.e. what the hardware physically is. It does not
govern estimator-local policy knobs (``toggle_rate``, ``read_zero_fraction``,
``optimize``, ``source``, tile hints, …), which are not emitted by harnesses and
are declared per estimator as optional parameters.

Naming rules
------------
=====================  ======================================================
Rule                   Content
=====================  ======================================================
No aliases             One canonical name per concept; mismatch → error
Domain prefix          ``mem_`` storage, ``net_`` interconnect, ``mx_``
                       microscaling. Universal parameters take no prefix
Counts                 Plural noun (``mem_banks``, ``net_inputs``) — never
                       ``num_``/``n_`` prefixes
Units                  Suffix only when ambiguous (``_bits``, ``_V``, ``_C``,
                       ``_ns``). ``data_width`` is self-evidently bits
=====================  ======================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = [
    "NamingError",
    "Param",
    "CANONICAL",
    "LEGACY_ALIASES",
    "PRIMITIVE_PARAMS",
    "canonical_names",
    "resolve_alias",
    "validate_attributes",
]


class NamingError(ValueError):
    """A component attribute violates the canonical vocabulary."""


@dataclass(frozen=True)
class Param:
    """One canonical attribute name."""

    name: str
    kind: str            # "int" | "float" | "str"
    doc: str
    unit: str = ""       # informational; units are encoded in the name itself


def _p(name: str, kind: str, doc: str, unit: str = "") -> Tuple[str, Param]:
    return name, Param(name, kind, doc, unit)


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

CANONICAL: Dict[str, Param] = dict([
    # -- universal ----------------------------------------------------------
    _p("node", "str", "Technology node string, e.g. '7nm'"),
    _p("data_width", "int", "Primary datapath width", "bits"),
    _p("pipeline_stages", "int",
       "Registered pipeline depth (range is primitive-specific: most 2-5, "
       "fpsfu 4-10)"),
    _p("number_format", "str", "Numeric family: int | fp | mx"),

    # -- integer arithmetic (asymmetric operands) ---------------------------
    _p("data_width_a", "int", "Operand A width", "bits"),
    _p("data_width_b", "int", "Operand B width", "bits"),
    _p("data_width_out", "int", "Visible result width", "bits"),
    _p("data_width_acc", "int", "Internal accumulator width (MACs)", "bits"),

    # -- floating point -----------------------------------------------------
    _p("exponent_bits", "int", "Exponent field width", "bits"),
    _p("mantissa_bits", "int",
       "Mantissa width, excluding the implicit leading bit", "bits"),

    # -- storage ------------------------------------------------------------
    _p("mem_depth_per_bank", "int", "Entries (words) per bank"),
    _p("mem_banks", "int", "Number of banks"),
    _p("mem_r_ports", "int", "Dedicated read ports"),
    _p("mem_w_ports", "int", "Dedicated write ports"),
    _p("mem_rw_ports", "int", "Shared read-or-write ports (1RW macros)"),
    _p("mem_template", "str",
       "SRAM macro template for capacity-only specs: sram_64k | sram_256k "
       "(fixes data_width/depth; see src/estimators/sram)"),
    # Analytic DRAM-device constants (the `hbm` primitive — an off-chip device,
    # no characterization flow; defaults in energy.unit_cost cite the source).
    _p("mem_act_energy_pJ", "float",
       "DRAM row-activation energy per ACT (precharge + activate)", "pJ"),
    _p("mem_access_energy_per_bit_pJ", "float",
       "DRAM access energy per bit (column access + on-die data movement + "
       "I/O), charged per read/write command x data_width", "pJ/bit"),
    _p("mem_ref_energy_pJ", "float",
       "DRAM refresh energy per maintenance (REFab) command", "pJ"),

    # -- interconnect -------------------------------------------------------
    _p("net_inputs", "int", "Source port count"),
    _p("net_outputs", "int", "Sink port count"),
    _p("net_radix", "int", "Downward ports per switch"),
    _p("net_levels", "int", "Tree levels"),
    _p("net_oversubscription", "float", "Up/down link capacity ratio, (0, 1]"),
    _p("net_terminals_per_leaf", "int", "Node downlinks per leaf switch"),
    _p("net_leaves", "int", "Leaf switch count"),
    _p("net_spines", "int", "Spine switch count"),
    _p("net_switch_radix", "int", "Total port budget of a leaf switch"),
    _p("net_energy_per_bit_pJ", "float",
       "Traversal energy per bit for analytic link models (d2dlink)", "pJ/bit"),

    # -- special function unit (fpsfu) --------------------------------------
    # Op-group selection flags are 0/1 ints (numeric on purpose: they are MLP
    # input features). Groups pair ops that share structure: exp{exp,exp2},
    # trig{sin,cos} (shared range reduction), hyp{tanh,sigmoid}, erf; relu is a
    # near-free comparator+mux extra.
    _p("sfu_op_exp", "int", "Op group enable: exp + exp2 (0/1)"),
    _p("sfu_op_trig", "int", "Op group enable: sin + cos (0/1)"),
    _p("sfu_op_hyp", "int", "Op group enable: tanh + sigmoid (0/1)"),
    _p("sfu_op_erf", "int", "Op group enable: erf (0/1)"),
    _p("sfu_op_relu", "int", "Op group enable: relu / leaky-relu (0/1)"),
    _p("sfu_segments", "int", "Piecewise-linear segments per op table"),

    # -- microscaling floating point ---------------------------------------
    _p("mx_block_elems", "int", "Elements sharing one scale"),
    _p("mx_blocks", "int", "Blocks processed per operation"),
    _p("mx_input_format", "str",
       "mxfp8_e5m2 | mxfp8_e4m3 | mxfp6_e3m2 | mxfp6_e2m3 | mxfp4_e2m1 | "
       "mxint8 | bf16 | custom"),
    _p("mx_scale_exponent_bits", "int", "Shared-scale exponent width", "bits"),
    _p("mx_scale_bias", "int", "Shared-scale exponent bias"),
    _p("mx_acc_format", "str", "fp32 | fp64 | custom"),
    _p("mx_decode_width", "int", "Decoded internal datapath width", "bits"),
    _p("mx_decode_frac_bits", "int", "Fractional bits after decode", "bits"),
])

#: PVT/context keys. Not authored per component — the core merges these in from
#: the description's ``technology:``/``clock:`` blocks (or a harness's CLI
#: flags), so they are accepted in a features dict but never emitted as
#: component attributes.
CONTEXT_NAMES: Tuple[str, ...] = (
    "node", "transistor", "corner", "voltage_offset_V", "temperature_C",
    "clock_mhz", "stim_mode",
)

# ---------------------------------------------------------------------------
# Legacy aliases — accepted nowhere, but recognized so the error can say what to
# rename. Every one of these was a live `arch_keys` entry before the freeze.
# ---------------------------------------------------------------------------

LEGACY_ALIASES: Dict[str, str] = {
    # node
    "technology": "node",
    "tech_node": "node",
    # width
    "bw": "data_width",
    "bits": "data_width",
    "width": "data_width",
    "bitwidth": "data_width",
    "width_bits": "data_width",
    "datawidth": "data_width",
    "word_bits": "data_width",
    # operand widths (RTL-generator spelling)
    "a_width": "data_width_a",
    "b_width": "data_width_b",
    "out_width": "data_width_out",
    "acc_width": "data_width_acc",
    # float
    "exp_bits": "exponent_bits",
    "format": "number_format",
    # storage
    "depth": "mem_depth_per_bank",
    "entries": "mem_depth_per_bank",
    "num_entries": "mem_depth_per_bank",
    "memory_depth": "mem_depth_per_bank",
    "words": "mem_depth_per_bank",
    "n_banks": "mem_banks",
    "banks": "mem_banks",
    "num_read_ports": "mem_r_ports",
    "num_write_ports": "mem_w_ports",
    # port totals have no single canonical successor — steer to the RW form,
    # which is what a bare "n_ports=1" historically meant (a 1RW macro).
    "n_ports": "mem_rw_ports",
    "ports": "mem_rw_ports",
    "num_ports": "mem_rw_ports",
    "nports": "mem_rw_ports",
    # interconnect
    "num_inputs": "net_inputs",
    "num_outputs": "net_outputs",
    "radix": "net_radix",
    "num_levels": "net_levels",
    "oversubscription": "net_oversubscription",
    "terminals_per_leaf": "net_terminals_per_leaf",
    "num_leaves": "net_leaves",
    "num_spines": "net_spines",
    "switch_radix": "net_switch_radix",
    # microscaling
    "block_elems": "mx_block_elems",
    "num_blocks": "mx_blocks",
    "input_format": "mx_input_format",
    "scale_exp_bits": "mx_scale_exponent_bits",
    "scale_bias": "mx_scale_bias",
    "acc_format": "mx_acc_format",
    "decode_width": "mx_decode_width",
    "decode_frac_bits": "mx_decode_frac_bits",
}


# ---------------------------------------------------------------------------
# Per-primitive parameter sets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParamSet:
    required: Tuple[str, ...]
    optional: Tuple[str, ...] = ()

    def all(self) -> Tuple[str, ...]:
        return self.required + self.optional


_INT_BINOP = ParamSet(
    required=("node", "data_width_a", "data_width_b", "data_width_out"),
    optional=("pipeline_stages", "number_format"),
)
_FP_BINOP = ParamSet(
    required=("node", "exponent_bits", "mantissa_bits"),
    optional=("pipeline_stages", "number_format", "data_width"),
)
_MEM = ParamSet(
    required=("node", "data_width", "mem_depth_per_bank"),
    optional=("mem_banks", "mem_r_ports", "mem_w_ports", "mem_rw_ports",
              "mem_template"),
)

PRIMITIVE_PARAMS: Dict[str, ParamSet] = {
    # integer arithmetic
    "intadd": _INT_BINOP,
    "adder": _INT_BINOP,            # legacy estimator module name for intadd
    "intmul": _INT_BINOP,
    "intmac": ParamSet(
        required=_INT_BINOP.required + ("data_width_acc",),
        optional=_INT_BINOP.optional,
    ),
    # floating point
    "fpadd": _FP_BINOP,
    "fpmul": _FP_BINOP,
    "fpmac": _FP_BINOP,
    # special function unit — PWL evaluator for transcendentals (fp only; an
    # int8 variant would be a direct-indexed LUT, i.e. a different primitive,
    # deliberately NOT built — see docs/DESIGN_SFU_DMA.md)
    "fpsfu": ParamSet(
        required=("node", "exponent_bits", "mantissa_bits", "sfu_op_exp",
                  "sfu_op_trig", "sfu_op_hyp", "sfu_op_erf", "sfu_segments"),
        optional=("pipeline_stages", "number_format", "sfu_op_relu"),
    ),
    "mxfpmac": ParamSet(
        required=("node", "mx_block_elems", "mx_blocks", "mx_input_format",
                  "mx_scale_exponent_bits", "mx_acc_format"),
        optional=("number_format", "pipeline_stages", "mx_scale_bias",
                  "mx_decode_width", "mx_decode_frac_bits"),
    ),
    # storage
    "regfile": _MEM,
    "sram": _MEM,
    "fifo": ParamSet(required=("node", "data_width", "mem_depth_per_bank"),
                     optional=("mem_banks",)),
    # interconnect
    "simplemux": ParamSet(required=("node", "data_width", "net_inputs")),
    "crossbar": ParamSet(
        required=("node", "data_width", "net_inputs", "net_outputs")),
    "fattree": ParamSet(
        required=("node", "data_width", "net_radix", "net_levels"),
        optional=("net_oversubscription",),
    ),
    "foldedclos": ParamSet(
        required=("node", "data_width", "net_terminals_per_leaf", "net_leaves",
                  "net_spines", "net_switch_radix"),
        optional=("net_oversubscription",),
    ),
    # Die-to-die (chiplet) link: no RTL characterization flow exists, so the
    # estimator side is an analytic constant — energy = data_width ×
    # net_energy_per_bit_pJ per flit crossing. The default constant is a
    # literature value (see energy.unit_cost.D2D_ENERGY_PER_BIT_PJ); override it
    # per component in the description when the package/PHY is known.
    "d2dlink": ParamSet(required=("node", "data_width"),
                        optional=("net_energy_per_bit_pJ",)),
    # DRAM device (HBM channel): an off-chip part with no characterization
    # flow, priced by analytic per-command constants (energy.unit_cost — the
    # defaults cite O'Connor & Chatterjee et al., MICRO 2017, Table 3).
    # data_width = bits moved per read/write command (request size × 8).
    "hbm": ParamSet(required=("node", "data_width"),
                    optional=("mem_act_energy_pJ",
                              "mem_access_energy_per_bit_pJ",
                              "mem_ref_energy_pJ")),
}

#: Description ``class:`` strings → primitive. The class vocabulary is a thin
#: presentation layer; the primitive is what estimators register under.
CLASS_TO_PRIMITIVE: Dict[str, str] = {
    "register_file": "regfile",
    "xbar": "crossbar",
    "mux": "simplemux",
}


def primitive_of(component_class: str) -> str:
    """Resolve a description ``class:`` string to its primitive name."""
    key = str(component_class).lower()
    return CLASS_TO_PRIMITIVE.get(key, key)


def canonical_names() -> Tuple[str, ...]:
    """Every legal component-attribute name, sorted."""
    return tuple(sorted(CANONICAL))


def resolve_alias(name: str) -> Optional[str]:
    """The canonical successor of a known legacy alias, else ``None``."""
    return LEGACY_ALIASES.get(name)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_attributes(
    primitive: str,
    attributes: Mapping[str, Any],
    *,
    component: str = "<component>",
    policy_keys: Iterable[str] = (),
) -> List[str]:
    """Check one component's attributes against the canonical vocabulary.

    Returns a list of **warnings**. Raises :class:`NamingError` on anything that
    makes the estimator's answer wrong rather than merely coarse:

    * a legacy alias (``bw``, ``depth``, ``a_width``, …) → error naming the
      replacement, because silently defaulting is exactly the bug this freeze
      removes;
    * a required parameter missing for a known primitive.

    Unknown names that are not known aliases are a **warning**: a user component
    class may legitimately carry attributes this build has never heard of, and
    the estimator that consumes them decides whether they matter.
    """
    warnings: List[str] = []
    prim = primitive_of(primitive)
    spec = PRIMITIVE_PARAMS.get(prim)
    allowed = set(policy_keys) | set(CONTEXT_NAMES)

    for key in attributes:
        if key in CANONICAL or key in allowed:
            continue
        target = LEGACY_ALIASES.get(key)
        if target is not None:
            raise NamingError(
                f"{component} ({prim}): attribute '{key}' is a legacy alias; "
                f"rename it to '{target}'. Estimators accept exactly one name "
                f"per concept — see npuwattch.naming.CANONICAL."
            )
        warnings.append(
            f"{component} ({prim}): unknown attribute '{key}' — not in the "
            f"canonical vocabulary; no estimator will read it"
        )

    if spec is None:
        return warnings

    # Context keys (node, PVT, clock) live in the description's `technology:`
    # block, not per component — the core merges them in before the estimator
    # is queried, so their absence here is not a component-authoring error.
    missing = [k for k in spec.required
               if k not in CONTEXT_NAMES and attributes.get(k) is None]
    if missing:
        raise NamingError(
            f"{component} ({prim}): missing required attribute(s) "
            f"{', '.join(missing)}. Required: {', '.join(spec.required)}"
        )

    extra = [k for k in attributes
             if k in CANONICAL and k not in spec.all() and k not in allowed]
    for key in sorted(extra):
        warnings.append(
            f"{component} ({prim}): '{key}' is canonical but not a "
            f"{prim} parameter — it will be ignored"
        )
    return warnings
