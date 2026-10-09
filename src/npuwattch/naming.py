"""NPUWattch names: the attribute names that the estimators accept.

This module is the only definition of the names in the ``attributes`` block of
a component.

Why this module is necessary
----------------------------
Each simulator uses its own names. For example, Timeloop writes ``word-bits``,
gem5 writes ``bitwidth``, and the RTL generator writes ``a_width``. If an
estimator accepts many names for one concept, a spelling error gives a default
value and no message. Then two harnesses can give different results and no
one sees the cause.

Thus the rules are:

* The name that the estimator accepts is the standard. Each concept has
  exactly one name. There are no aliases.
* A harness must emit only NPUWattch names. The author of the harness
  translates the simulator names with a vocabulary table,
  ``<harness>/definitions/vocabulary.yaml``. The engine
  ``npuwattch_harness.vocabulary`` applies the table during ingest.
* An attribute name that is a known old alias is an error. The error message
  gives the correct name. The estimator does not use a default value.

Scope: these rules apply to the architecture attributes, which are the
``components[].attributes`` of the description. These attributes describe the
hardware. The rules do not apply to the policy parameters of one estimator
(``toggle_rate``, ``read_zero_fraction``, ``optimize``, ``source``, tile
hints). A harness does not emit such parameters. Each estimator declares them
as optional parameters.

Naming rules
------------
=====================  ======================================================
Rule                   Content
=====================  ======================================================
No aliases             One name for each concept. A different name is an
                       error
Domain prefix          ``mem_`` storage, ``net_`` interconnect, ``mx_``
                       microscaling. Universal parameters have no prefix
Counts                 Plural noun (``mem_banks``, ``net_inputs``). Do not
                       use the prefixes ``num_`` or ``n_``
Units                  A suffix only if the unit is not clear (``_bits``,
                       ``_V``, ``_C``, ``_ns``). ``data_width`` is in bits
=====================  ======================================================
"""

from __future__ import annotations

from npuwattch.diagnostics import NPUWattchError, warning
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = [
    "NamingError",
    "Param",
    "CANONICAL",
    "LEGACY_ALIASES",
    "PRIMITIVE_PARAMS",
    "validate_attributes",
]


class NamingError(NPUWattchError, ValueError):
    """A component attribute does not obey the naming rules."""


@dataclass(frozen=True)
class Param:
    """One NPUWattch attribute name."""

    name: str
    kind: str            # "int" | "float" | "str"
    doc: str
    unit: str = ""       # Only for information. The name gives the unit.


def _p(name: str, kind: str, doc: str, unit: str = "") -> Tuple[str, Param]:
    return name, Param(name, kind, doc, unit)


# ---------------------------------------------------------------------------
# The NPUWattch names
# ---------------------------------------------------------------------------

CANONICAL: Dict[str, Param] = dict([
    # -- universal ----------------------------------------------------------
    _p("node", "str", "Technology node string, e.g. '7nm'"),
    _p("data_width", "int", "Primary datapath width", "bits"),
    _p("pipeline_stages", "int",
       "Registered pipeline depth = latency in cycles (range is "
       "primitive-specific: int units 2-5, fpadd/fpmul 2-9, fpmac 4-18, "
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
    _p("mem_banks", "int",
       "Independently addressable banks (each with its own decoders; may be "
       "accessed concurrently — the CACTI 5+ bank)"),
    _p("mem_r_ports", "int", "Dedicated read ports, physical, per bank"),
    _p("mem_w_ports", "int", "Dedicated write ports, physical, per bank"),
    _p("mem_rw_ports", "int",
       "Shared read-or-write ports, physical, per bank (1RW macros); not the "
       "number of concurrent accesses — use banks for that"),
    _p("mem_template", "str",
       "SRAM macro template for capacity-only specs: sram_64k | sram_256k "
       "(fixes data_width/depth; see src/npuwattch_estimators/sram)"),
    # Analytic constants of a DRAM device (the `hbm` primitive). The device is
    # off-chip and has no characterization flow. The defaults and their
    # source are in energy.unit_cost.
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
    # Each flag selects one op group. A flag is the integer 0 or 1, because
    # the flags are input features of the MLP.
    # A group contains the ops that use the same structure:
    #   exp:  exp, exp2
    #   trig: sin, cos (the same range reduction)
    #   hyp:  tanh, sigmoid
    #   erf:  erf
    # relu adds only a comparator and a mux, thus its cost is almost zero.
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

#: Context keys (PVT and clock). A component does not declare them. The core
#: adds them from the ``technology:`` and ``clock:`` blocks of the description,
#: or from the CLI flags of a harness. Thus a features dict can contain them,
#: but a harness does not emit them as component attributes.
CONTEXT_NAMES: Tuple[str, ...] = (
    "node", "transistor", "corner", "voltage_offset_V", "temperature_C",
    "clock_mhz", "stim_mode",
)

# ---------------------------------------------------------------------------
# Legacy aliases. No estimator accepts them. The table lets the error message
# give the correct NPUWattch name.
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
    # A port total has no single NPUWattch name. The table gives the RW name,
    # because "n_ports=1" usually describes a 1RW macro.
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
# Parameter sets, one for each primitive
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
    "adder": _INT_BINOP,            # the legacy name of intadd
    "intmul": _INT_BINOP,
    "intmac": ParamSet(
        required=_INT_BINOP.required + ("data_width_acc",),
        optional=_INT_BINOP.optional,
    ),
    # floating point
    "fpadd": _FP_BINOP,
    "fpmul": _FP_BINOP,
    "fpmac": _FP_BINOP,
    # Special function unit: a piecewise-linear (PWL) evaluator for
    # transcendental functions. It is for floating point only. An int8 unit
    # is a LUT with a direct index, which is a different primitive. NPUWattch
    # has no model for that primitive (see docs/DESIGN_SFU_DMA.md).
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
    # Die-to-die (chiplet) link. It has no RTL characterization flow, thus the
    # model is an analytic constant:
    #   energy of one flit crossing = data_width x net_energy_per_bit_pJ
    # The default constant is a literature value (see
    # energy.unit_cost.D2D_ENERGY_PER_BIT_PJ). If you know the package or the
    # PHY, set the constant for the component in the description.
    "d2dlink": ParamSet(required=("node", "data_width"),
                        optional=("net_energy_per_bit_pJ",)),
    # DRAM device (HBM channel). It is an off-chip part and has no
    # characterization flow. Analytic constants give the energy of each
    # command (energy.unit_cost). The source of the defaults is O'Connor &
    # Chatterjee et al., MICRO 2017, Table 3.
    # data_width = bits that one read or write command moves
    #            = request size in bytes x 8.
    "hbm": ParamSet(required=("node", "data_width"),
                    optional=("mem_act_energy_pJ",
                              "mem_access_energy_per_bit_pJ",
                              "mem_ref_energy_pJ")),
}

#: Class of a description -> primitive. A class is only a name in the
#: description. An estimator registers for the primitive.
CLASS_TO_PRIMITIVE: Dict[str, str] = {
    "register_file": "regfile",
    "xbar": "crossbar",
    "mux": "simplemux",
}


def primitive_of(component_class: str) -> str:
    """Return the primitive for a class of a description."""
    key = str(component_class).lower()
    return CLASS_TO_PRIMITIVE.get(key, key)


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
    """Check the attributes of one component against the NPUWattch names.

    Return a list of warnings. Raise :class:`NamingError` if an attribute
    makes the result of the estimator incorrect:

    * A legacy alias (``bw``, ``depth``, ``a_width``, ...). The error message
      gives the correct name. Without the error, the estimator uses a default
      value and gives no message.
    * A known primitive that does not have a necessary parameter.

    An unknown name that is not a legacy alias gives a warning, not an error.
    A user-defined class can have attributes that this module does not know.
    The estimator that reads them decides if they are important.
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
            raise NamingError.nw(2001, component=component, primitive=prim,
                                 key=key, target=target)
        warnings.append(warning(2002, component=component, primitive=prim,
                                key=key))

    if spec is None:
        return warnings

    # The context keys (node, PVT, clock) are in the `technology:` block of
    # the description, not in a component. The core adds them before it
    # queries the estimator. Thus a component without them is not an error.
    missing = [k for k in spec.required
               if k not in CONTEXT_NAMES and attributes.get(k) is None]
    if missing:
        raise NamingError.nw(2003, component=component, primitive=prim,
                             missing=", ".join(missing),
                             required=", ".join(spec.required))

    extra = [k for k in attributes
             if k in CANONICAL and k not in spec.all() and k not in allowed]
    for key in sorted(extra):
        warnings.append(warning(2004, component=component, primitive=prim,
                                key=key))
    return warnings
