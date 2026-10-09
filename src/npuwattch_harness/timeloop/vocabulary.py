"""Timeloop/Accelergy vocabulary -> NPUWattch vocabulary.

The name translation is a table: ``definitions/vocabulary.yaml``. The shared
engine ``npuwattch_harness.vocabulary`` loads and applies the table. To support
a new Accelergy spelling, change the table.

This module contains the derivation rules. A derivation rule calculates a
NPUWattch attribute that Accelergy does not declare directly. There is one rule
for each attribute family:

=========  ==============================================================
Family     Derivations
=========  ==============================================================
storage    word width, depth for each bank, port count
dram       word width; the energy constants come from ``dram.py``
int        operand widths, output width, accumulator width
fp         exponent and mantissa widths, SFU defaults
fabric     data width, port counts
link       data width
=========  ==============================================================

Two properties are intentional:

* An unknown class is not an error. :func:`primitive_for` returns ``None``.
  The ingest then uses the user component library entry of the same name. If
  there is no entry, the component is not in the description and the run
  gives a warning. NPUWattch gives no value for a block without a model.
* Each derived value gives a message. A warning tells the user that the result
  can be incorrect. A note tells the user that a documented convention was
  applied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from npuwattch.diagnostics import info, warning
from npuwattch.naming import CONTEXT_NAMES, PRIMITIVE_PARAMS
from .dram import CONSTANT_NAMES, constants_for
from ..vocabulary import (
    AttributeReader,
    Vocabulary,
    load_vocabulary,
    positive_int,
)

__all__ = [
    "CLASS_TO_PRIMITIVE",
    "VOCABULARY",
    "primitive_for",
    "attributes_for",
    "reclassify_regfile_as_sram",
    "REGFILE_TO_SRAM_THRESHOLD_BITS",
]

#: The vocabulary table of this harness.
VOCABULARY: Vocabulary = load_vocabulary(
    Path(__file__).resolve().parent / "definitions" / "vocabulary.yaml")

#: Accelergy ``class`` (lowercase) -> NPUWattch primitive.
CLASS_TO_PRIMITIVE: Mapping[str, str] = VOCABULARY.classes

#: A ``regfile`` that is larger than this number of bits is a memory macro.
#: The SRAM estimator models it (32 Kib).
REGFILE_TO_SRAM_THRESHOLD_BITS = 32768

#: Exponent and mantissa widths for each total width. The rule for the ``fp``
#: family uses this table when the component declares only a total width.
_FP_SPLIT_BY_WIDTH: Dict[int, Tuple[int, int]] = {
    8: (4, 3),      # OCP fp8 E4M3
    16: (5, 10),    # IEEE half
    32: (8, 23),    # IEEE single
    64: (11, 52),   # IEEE double
}

#: Accumulator width = this value x operand width. Accelergy does not declare
#: an accumulator width. The NPU convention is int8 x int8 -> int32.
_ACC_WIDTH_MULTIPLIER = 4

#: Only arithmetic units have a pipeline depth. For a memory or a link, the
#: same Accelergy word is an access latency.
_ARITHMETIC_FAMILIES = ("int", "fp", "mx")


def primitive_for(
    comp_class: Optional[str],
    subclass: Optional[str] = None,
    attributes: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Return the NPUWattch primitive for an Accelergy class, or ``None``.

    The caller decides what to do with an unknown class (``None``).
    ``comp_class`` has priority over ``subclass``.
    """
    return VOCABULARY.primitive_for(comp_class, subclass, attributes)


def reclassify_regfile_as_sram(attributes: Mapping[str, Any]) -> bool:
    """Return ``True`` if the SRAM estimator must model this ``regfile``."""
    try:
        bits = (int(attributes.get("mem_depth_per_bank", 0))
                * int(attributes.get("data_width", 0))
                * int(attributes.get("mem_banks", 1) or 1))
    except (TypeError, ValueError):
        return False
    return bits > REGFILE_TO_SRAM_THRESHOLD_BITS


def attributes_for(
    primitive: str,
    raw: Mapping[str, Any],
    *,
    component: str,
    warnings: List[str],
    notes: List[str],
    energy_table: Optional[Any] = None,
) -> Dict[str, Any]:
    """Translate the Accelergy ``attributes`` of one component.

    ``energy_table`` is the ``EnergyTable`` of ``--energy-table``, or ``None``.
    Only a DRAM component uses it.

    The function adds messages to two lists:

    * ``warnings``: the result can be incorrect (for example, a necessary
      attribute was not declared and a default value was used).
    * ``notes``: a documented convention was applied, or attributes were
      ignored.
    """
    reader = VOCABULARY.read(primitive, raw)
    # The technology is in the header of the description, not in a component.
    reader.values.pop("technology", None)
    out: Dict[str, Any] = {}

    family = VOCABULARY.family(primitive)
    rule = _RULES.get(family)
    if family == "dram":
        _dram_rule(primitive, reader, out, component, warnings, notes,
                   energy_table=energy_table)
    elif rule is not None:
        rule(primitive, reader, out, component, warnings, notes)
    else:
        out.update(reader.take_named())

    # Keep each attribute of this primitive that already has its NPUWattch
    # name and that the rule did not take. Examples: an sram `mem_template`,
    # a d2dlink `net_energy_per_bit_pJ`. Context names stay out, because the
    # technology block of the description controls them.
    spec = PRIMITIVE_PARAMS.get(primitive)
    if spec is not None:
        for key in spec.all():
            if key in CONTEXT_NAMES or key in reader.consumed or key in out:
                continue
            if reader.values.get(key) is not None:
                out[key] = reader.values[key]
                reader.consumed.add(key)

    if family in _ARITHMETIC_FAMILIES:
        stages = reader.take_int("pipeline_stages")
        if stages is not None:
            out["pipeline_stages"] = stages

    ignored = reader.ignored()
    if ignored:
        notes.append(info(7301, component=component, primitive=primitive,
                          attributes=", ".join(ignored)))
    return out


# ---------------------------------------------------------------------------
# Derivation rules, one for each family
# ---------------------------------------------------------------------------

def _block_width(reader: AttributeReader) -> Optional[int]:
    """Return the Accelergy word width, ``datawidth x block_size``."""
    if reader.peek_int("element_width") is None:
        return None
    return reader.take_int("element_width") * (reader.take_int("block_size") or 1)


def _storage_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
                  component: str, warnings: List[str], notes: List[str]) -> None:
    width = reader.take_int("data_width")
    if width is None:
        width = _block_width(reader)
    if width is None:
        warnings.append(warning(7302, component=component, primitive=primitive))
        width = 32
    out["data_width"] = width

    # Read the banks first. The Accelergy `depth` and capacity are totals for
    # all banks (the CACTI convention). Only `mem_depth_per_bank` is a value
    # for one bank.
    banks = reader.take_int("mem_banks")

    depth_key, depth_raw = reader.take_with_key("mem_depth_per_bank")
    depth = positive_int(depth_raw)
    if depth is None:
        capacity_bits = reader.take_int("capacity_bits")
        if capacity_bits is None:
            kb = reader.take_int("capacity_kb")
            capacity_bits = kb * 1024 * 8 if kb else None
        if capacity_bits is not None:
            depth = max(1, capacity_bits // width)
            notes.append(info(7303, component=component, primitive=primitive,
                              depth=depth, width=width))
    if depth is None:
        warnings.append(warning(7304, component=component, primitive=primitive))
        depth = 64
    if banks and banks > 1 and depth_key != "mem_depth_per_bank":
        per_bank = -(-depth // banks)            # ceiling division
        if depth % banks:
            warnings.append(warning(7305, component=component,
                                    primitive=primitive, depth=depth,
                                    banks=banks, per_bank=per_bank))
        total_bits = banks * per_bank * width
        if total_bits % (8 * 1024 * 1024) == 0:
            capacity = f"{total_bits // (8 * 1024 * 1024)} MB"
        elif total_bits % (8 * 1024) == 0:
            capacity = f"{total_bits // (8 * 1024)} KB"
        else:
            capacity = f"{total_bits} bit"
        notes.append(info(7306, component=component, primitive=primitive,
                          depth=depth, banks=banks, per_bank=per_bank,
                          capacity=capacity))
        depth = per_bank
    out["mem_depth_per_bank"] = depth
    if banks is not None:
        out["mem_banks"] = banks
    if primitive == "fifo":
        return

    r_ports = reader.take_int("mem_r_ports")
    w_ports = reader.take_int("mem_w_ports")
    rw_ports = reader.take_int("mem_rw_ports")
    if r_ports is None and w_ports is None and rw_ports is None:
        rw_ports = 1
        notes.append(info(7307, component=component, primitive=primitive))
    if r_ports is not None:
        out["mem_r_ports"] = r_ports
    if w_ports is not None:
        out["mem_w_ports"] = w_ports
    if rw_ports is not None:
        out["mem_rw_ports"] = rw_ports

    # The Timeloop bandwidth is a mapping constraint, not hardware. But for a
    # banked memory it gives the number of bank accesses in one cycle.
    # The unit of the bandwidth is one `datawidth` element. One bank access
    # moves a block of `width / datawidth` elements.
    # Thus: accesses in one cycle = ceil(bandwidth / block).
    bandwidths = reader.take_all_ints("bandwidth")
    if bandwidths:
        bandwidth = max(bandwidths)
        element = reader.peek_int("element_width")
        block = width // element if element and width % element == 0 else 1
        accesses = -(-bandwidth // block)
        per = (f"{bandwidth} words/cycle ({block} words per access)"
               if block > 1 else f"{bandwidth} words/cycle")
        n_banks = banks or 1
        ports = (r_ports or 0) + (w_ports or 0) + (rw_ports or 0) or 1
        if accesses > 1 and n_banks > 1:
            notes.append(info(7308, component=component, primitive=primitive,
                              bandwidth=per,
                              accesses=min(accesses, n_banks * ports)))
        if accesses > n_banks * ports:
            warnings.append(warning(
                7309, component=component, primitive=primitive, bandwidth=per,
                accesses=accesses, banks=n_banks, ports=ports,
                slots=n_banks * ports, needed_banks=-(-accesses // ports)))


def _dram_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
               component: str, warnings: List[str], notes: List[str],
               energy_table: Optional[Any] = None) -> None:
    width = reader.take_int("data_width") or _block_width(reader)
    if width is None:
        warnings.append(warning(7310, component=component))
        width = 256
    out["data_width"] = width

    # The module `dram` selects the energy constants. It raises an error if
    # the necessary DRAM energy table is not available.
    out.update(constants_for(
        reader.take("dram_type"), energy_table, component=component,
        declared=reader.values, warnings=warnings, notes=notes))
    reader.consumed.update(CONSTANT_NAMES)


def _int_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
              component: str, warnings: List[str], notes: List[str]) -> None:
    a = reader.take_int("data_width_a")
    b = reader.take_int("data_width_b")
    width = reader.take_int("operand_width")
    a = a or width
    if a is None:
        warnings.append(warning(7311, component=component, primitive=primitive))
        a = 8
    b = b or a
    out["number_format"] = "int"
    out["data_width_a"] = a
    out["data_width_b"] = b

    declared_out = reader.take_int("data_width_out")
    if primitive == "intmac":
        acc = reader.take_int("data_width_acc")
        if acc is None:
            acc = _ACC_WIDTH_MULTIPLIER * max(a, b)
            notes.append(info(7312, component=component, width=acc,
                              multiplier=_ACC_WIDTH_MULTIPLIER))
        out["data_width_acc"] = acc
        out["data_width_out"] = declared_out or acc
    elif primitive == "intmul":
        out["data_width_out"] = declared_out or (a + b)
    else:                                    # intadd
        out["data_width_out"] = declared_out or max(a, b)


def _fp_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
             component: str, warnings: List[str], notes: List[str]) -> None:
    exp = reader.take_int("exponent_bits")
    mant = reader.take_int("mantissa_bits")
    width = reader.take_int("data_width")
    if exp is None or mant is None:
        split = _FP_SPLIT_BY_WIDTH.get(width or 32)
        if split is None:
            warnings.append(warning(7313, component=component,
                                    primitive=primitive, width=width))
            split = _FP_SPLIT_BY_WIDTH[32]
        elif width is None:
            warnings.append(warning(7314, component=component,
                                    primitive=primitive))
        else:
            notes.append(info(7315, component=component, primitive=primitive,
                              split=split, width=width))
        exp, mant = split
    out["number_format"] = "fp"
    out["exponent_bits"] = exp
    out["mantissa_bits"] = mant
    if width is not None:
        out["data_width"] = width
    if primitive == "fpsfu":
        for key in ("sfu_segments", "sfu_op_exp", "sfu_op_trig", "sfu_op_hyp",
                    "sfu_op_erf", "sfu_op_relu"):
            value = reader.take_int(key)
            if value is not None:
                out[key] = value
        if "sfu_segments" not in out:
            out["sfu_segments"] = 16
            notes.append(info(7316, component=component))
        for key in ("sfu_op_exp", "sfu_op_trig", "sfu_op_hyp", "sfu_op_erf"):
            out.setdefault(key, 1)


def _fabric_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
                 component: str, warnings: List[str], notes: List[str]) -> None:
    width = reader.take_int("data_width")
    if width is None:
        warnings.append(warning(7317, component=component, primitive=primitive))
        width = 64
    out["data_width"] = width
    inputs = reader.take_int("net_inputs")
    outputs = reader.take_int("net_outputs")
    if inputs is None and outputs is None:
        warnings.append(warning(7318, component=component, primitive=primitive))
        inputs = outputs = 2
    out["net_inputs"] = inputs if inputs is not None else outputs
    if primitive == "crossbar":
        out["net_outputs"] = outputs if outputs is not None else inputs


def _link_rule(primitive: str, reader: AttributeReader, out: Dict[str, Any],
               component: str, warnings: List[str], notes: List[str]) -> None:
    width = reader.take_int("data_width")
    if width is None:
        warnings.append(warning(7319, component=component))
        width = 64
    out["data_width"] = width


_Rule = Callable[[str, AttributeReader, Dict[str, Any], str, List[str],
                  List[str]], None]

#: Family -> derivation rule. A family without a rule keeps only the
#: attributes that already have a NPUWattch name.
_RULES: Dict[str, _Rule] = {
    "storage": _storage_rule,
    "dram": _dram_rule,
    "int": _int_rule,
    "fp": _fp_rule,
    "fabric": _fabric_rule,
    "link": _link_rule,
}
