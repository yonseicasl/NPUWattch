"""Timeloop/Accelergy vocabulary → NPUWattch's canonical vocabulary.

Per ``npuwattch.naming``, translating a simulator's own spelling into ours is
**the harness author's job, done once, at ingest** — downstream only canonical
names exist. This module is that translation for Timeloop/Accelergy v0.4
architecture descriptions:

* ``class:``/``subclass:`` strings → a NPUWattch primitive (:data:`CLASS_TO_PRIMITIVE`);
* the component's ``attributes:`` block → canonical ``§3.1`` attributes
  (:func:`attributes_for`).

Two deliberate properties:

**Unmapped classes are not errors.** An Accelergy description may declare
anything; a class we do not recognize becomes ``user_defined`` and is
placeholder-priced, with a warning naming it. Guessing a primitive would be
worse than saying "I don't model this".

**Every inference is announced.** Accelergy carries less information than our
primitives need — an ``intmac`` has no declared accumulator width, an ``fpmac``
no declared exponent/mantissa split. Where we fill a gap from a documented
convention we emit a note, so a user reading the run output can see exactly
which numbers were declared and which were inferred.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from ...naming import CANONICAL, CONTEXT_NAMES, LEGACY_ALIASES, PRIMITIVE_PARAMS

__all__ = [
    "CLASS_TO_PRIMITIVE",
    "UNMAPPED_PRIMITIVE",
    "primitive_for",
    "attributes_for",
    "reclassify_regfile_as_sram",
    "REGFILE_TO_SRAM_THRESHOLD_BITS",
]

#: Class for a component whose Accelergy class we do not model. No estimator
#: claims it, so the provider chain prices it with the placeholder.
UNMAPPED_PRIMITIVE = "user_defined"

#: An Accelergy ``regfile`` above this many bits is a memory macro, not a
#: flop-based register file — the SRAM estimator models it far better. Carried
#: over from the retired ``npuwattch_class_mapper`` (32 Kib).
REGFILE_TO_SRAM_THRESHOLD_BITS = 32768


# ---------------------------------------------------------------------------
# class vocabulary
# ---------------------------------------------------------------------------

#: Accelergy/Timeloop ``class`` (lowercased) → NPUWattch primitive.
#:
#: Network classes (``XY_NoC``, ``legacy_network``, …) are deliberately absent:
#: a mesh router is not one of our characterized fabrics, and inventing a radix
#: for it would fabricate energy. Declare the fabric explicitly (``crossbar`` /
#: ``fattree`` / ``foldedclos``) to have it modeled.
CLASS_TO_PRIMITIVE: Dict[str, str] = {
    # -- storage ------------------------------------------------------------
    "sram": "sram",
    "smartbuffer_sram": "sram",
    "smartbuffer": "sram",
    "scratchpad": "sram",
    "storage": "sram",
    "buffer": "sram",
    "regfile": "regfile",
    "register_file": "regfile",
    "rf": "regfile",
    "smartbuffer_rf": "regfile",
    "fifo": "fifo",
    # The `hbm` primitive is our only DRAM-device model (analytic per-command
    # constants). Any off-chip main memory routes here; `attributes_for` warns
    # that HBM2 constants are being charged.
    "dram": "hbm",
    "main_memory": "hbm",
    "hbm": "hbm",
    # -- compute ------------------------------------------------------------
    "intmac": "intmac",
    "mac": "intmac",
    "intmultiplier_accumulator": "intmac",
    "fpmac": "fpmac",
    "intadd": "intadd",
    "adder": "intadd",
    "int_adder": "intadd",
    "integer_adder": "intadd",
    "intmul": "intmul",
    "multiplier": "intmul",
    "int_multiplier": "intmul",
    "intmultiplier": "intmul",
    "fpadd": "fpadd",
    "fp_adder": "fpadd",
    "float_adder": "fpadd",
    "fpmul": "fpmul",
    "fp_multiplier": "fpmul",
    "float_multiplier": "fpmul",
    "mxfpmac": "mxfpmac",
    "fpsfu": "fpsfu",
    # -- interconnect -------------------------------------------------------
    "crossbar": "crossbar",
    "xbar": "crossbar",
    "mux": "simplemux",
    "multiplexer": "simplemux",
    "simplemux": "simplemux",
    "fattree": "fattree",
    "foldedclos": "foldedclos",
    "wire": "d2dlink",
    "d2dlink": "d2dlink",
}

#: int primitive → its fp sibling, for a class whose attributes declare a
#: floating-point datatype (Accelergy's generic ``mac``/``adder``/``multiplier``
#: name a structure, not a number format).
_INT_TO_FP = {"intmac": "fpmac", "intadd": "fpadd", "intmul": "fpmul"}

_FP_FORMAT_WORDS = ("fp", "float", "floating", "bfloat", "bf16", "half", "double")


def primitive_for(
    comp_class: Optional[str],
    subclass: Optional[str] = None,
    attributes: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Resolve an Accelergy class/subclass to a NPUWattch primitive.

    Returns ``None`` when nothing matches — the caller decides what an unmapped
    component becomes (see :data:`UNMAPPED_PRIMITIVE`). ``class`` wins over
    ``subclass``: the subclass is a refinement of the class, so if both are
    known the more specific declaration is still the same family.
    """
    prim: Optional[str] = None
    for candidate in (comp_class, subclass):
        if not candidate:
            continue
        prim = CLASS_TO_PRIMITIVE.get(str(candidate).strip().lower())
        if prim is not None:
            break
    if prim is None:
        return None
    # A generic structural class (mac/adder/multiplier) with a declared
    # floating-point datatype is an fp unit, not an int one.
    if prim in _INT_TO_FP and _declares_float(attributes or {}):
        return _INT_TO_FP[prim]
    return prim


def _declares_float(attributes: Mapping[str, Any]) -> bool:
    for key in ("number_format", "datatype", "data_type", "format", "precision"):
        value = attributes.get(key)
        if isinstance(value, str) and any(w in value.lower()
                                          for w in _FP_FORMAT_WORDS):
            return True
    return False


def reclassify_regfile_as_sram(attributes: Mapping[str, Any]) -> bool:
    """Is this ``regfile`` big enough that the SRAM estimator should own it?"""
    try:
        bits = (int(attributes.get("mem_depth_per_bank", 0))
                * int(attributes.get("data_width", 0))
                * int(attributes.get("mem_banks", 1) or 1))
    except (TypeError, ValueError):
        return False
    return bits > REGFILE_TO_SRAM_THRESHOLD_BITS


# ---------------------------------------------------------------------------
# attribute vocabulary
# ---------------------------------------------------------------------------

# Candidate source keys per concept, most explicit first. Names are matched
# after `-`→`_` normalization and lowercasing (canonical spellings are kept
# verbatim, since a few of them carry a unit suffix in caps).
#
# `datawidth` is absent from the storage list on purpose: in Accelergy it is the
# *element* datatype width, and the memory word is `datawidth x block-size`
# (see `_block_width`). For a compute unit the same key IS the operand width.
_WORD_KEYS = ("data_width", "word_bits", "memory_width", "width")
_OPERAND_KEYS = ("data_width", "datawidth", "width", "word_bits")
_DEPTH_KEYS = ("mem_depth_per_bank", "memory_depth", "depth", "entries",
               "num_entries", "n_entries")
_CAPACITY_BIT_KEYS = ("capacity_bit", "capacity_bits")
_CAPACITY_BYTE_KEYS = ("sizekb", "size_kb", "capacity_kb")
_BANK_KEYS = ("mem_banks", "n_banks", "num_banks", "banks")
_RW_PORT_KEYS = ("mem_rw_ports", "n_rdwr_ports", "num_rdwr_ports", "n_ports",
                 "num_ports", "ports")
_R_PORT_KEYS = ("mem_r_ports", "n_rd_ports", "num_read_ports", "read_ports")
_W_PORT_KEYS = ("mem_w_ports", "n_wr_ports", "num_write_ports", "write_ports")
_BLOCK_SIZE_KEYS = ("block_size", "blocksize")
_INPUT_KEYS = ("net_inputs", "num_inputs", "n_inputs", "inputs", "ingresses")
_OUTPUT_KEYS = ("net_outputs", "num_outputs", "n_outputs", "outputs", "egresses")
# NOT `latency`: on an Accelergy storage component that is access latency, and
# on a compute component it is unrelated to the registered depth our models take.
_PIPELINE_KEYS = ("pipeline_stages", "n_stages", "stages")

#: Accelergy keys that carry no physical NPUWattch attribute — dropped without
#: a per-key note (spatial fanout is already folded into the instance count;
#: the rest are mapping/placement hints Timeloop uses, not hardware).
_SILENTLY_DROPPED = frozenset({
    "meshx", "meshy", "cluster_size", "clustersize", "instances",
    "read_bandwidth", "write_bandwidth", "bandwidth", "shared_bandwidth",
    "network_read", "network_write", "network_fill", "network_drain",
    "allow_overbooking", "has_power_gating", "utilized_capacity",
    # The clock is a description-level property (`_clock_mhz` reads it from the
    # top-level attributes), but Accelergy inheritance copies it onto every
    # component — reporting it as "ignored" once per component is just noise.
    "clockrate", "clock_rate", "frequency_mhz", "clock_mhz",
    "global_cycle_seconds", "cycle_seconds",
})

#: IEEE-754-ish (exponent, mantissa) by total width, for an fp unit declared
#: only by its datapath width.
_FP_SPLIT_BY_WIDTH: Dict[int, Tuple[int, int]] = {
    8: (4, 3),      # OCP fp8 E4M3
    16: (5, 10),    # IEEE half
    32: (8, 23),    # IEEE single
    64: (11, 52),   # IEEE double
}

#: Accumulator width for a MAC declared only by its operand width. int8×int8
#: into int32 is the NPU convention (4x); Accelergy declares no accumulator.
_ACC_WIDTH_MULTIPLIER = 4


def _norm_key(key: Any) -> str:
    """``block-size`` → ``block_size``; canonical names pass through verbatim
    (``net_energy_per_bit_pJ`` must not be lowercased into a stranger)."""
    text = str(key).strip()
    if text in CANONICAL:
        return text
    return text.replace("-", "_").lower()


def _first(attrs: Mapping[str, Any], keys: Tuple[str, ...]) -> Optional[Any]:
    for k in keys:
        if k in attrs and attrs[k] is not None:
            return attrs[k]
    return None


def _as_int(value: Any) -> Optional[int]:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def attributes_for(
    primitive: str,
    raw: Mapping[str, Any],
    *,
    component: str,
    warnings: List[str],
    notes: List[str],
) -> Dict[str, Any]:
    """Translate one component's Accelergy ``attributes`` into canonical form.

    ``warnings`` collects things that may make the answer wrong (an unmodeled
    device family, a required attribute we had to guess at); ``notes`` collects
    documented conventions applied (an inferred accumulator width). Keys that
    carry no NPUWattch meaning are dropped and listed once per component.
    """
    attrs = {_norm_key(k): v for k, v in (raw or {}).items()}
    attrs.pop("technology", None)          # PVT lives in the description header
    out: Dict[str, Any] = {}
    consumed: set = {"technology"}

    def take(keys: Tuple[str, ...]) -> Optional[Any]:
        for k in keys:
            if k in attrs and attrs[k] is not None:
                consumed.add(k)
                return attrs[k]
        return None

    if primitive in ("sram", "regfile", "fifo"):
        _storage_attributes(primitive, attrs, take, out, component=component,
                            warnings=warnings, notes=notes, consumed=consumed)
    elif primitive == "hbm":
        width = _as_int(take(_WORD_KEYS)) or _block_width(attrs, take)
        if width is None:
            warnings.append(
                f"{component} (hbm): no word width declared — charging a 32 B "
                f"burst (256 bits) per access")
            width = 256
        out["data_width"] = width
        warnings.append(
            f"{component}: Accelergy class routed to the 'hbm' primitive — "
            f"NPUWattch's only DRAM-device model, priced with analytic HBM2 "
            f"constants. Override them per component if the part differs.")
    elif primitive in ("intadd", "intmul", "intmac"):
        _int_attributes(primitive, attrs, take, out, component=component,
                        warnings=warnings, notes=notes)
    elif primitive in ("fpadd", "fpmul", "fpmac", "fpsfu"):
        _fp_attributes(primitive, attrs, take, out, component=component,
                       warnings=warnings, notes=notes)
    elif primitive in ("crossbar", "simplemux"):
        _fabric_attributes(primitive, attrs, take, out, component=component,
                           warnings=warnings)
    elif primitive == "d2dlink":
        width = _as_int(take(_OPERAND_KEYS))
        if width is None:
            warnings.append(
                f"{component} (d2dlink): no width declared — assuming 64 bits")
            width = 64
        out["data_width"] = width
    else:
        # user_defined / fattree / foldedclos / mxfpmac: pass through whatever
        # is already canonical (or a known alias) and let §3.1 validation speak.
        for key, value in attrs.items():
            canon = key if key in CANONICAL else LEGACY_ALIASES.get(key)
            if canon:
                out[canon] = value
                consumed.add(key)

    # Anything already spelled canonically that belongs to this primitive and
    # the branch above did not claim: the `hbm` per-part constants the warning
    # above invites you to override, an sram `mem_template`, a d2dlink
    # `net_energy_per_bit_pJ`. Context keys stay out — the description's
    # technology block governs PVT, not a per-component attribute.
    spec = PRIMITIVE_PARAMS.get(primitive)
    if spec is not None:
        for key in spec.all():
            if key in CONTEXT_NAMES or key in consumed or key in out:
                continue
            if attrs.get(key) is not None:
                out[key] = attrs[key]
                consumed.add(key)

    # Only the arithmetic primitives take a registered depth; on a memory or a
    # link the same word would be access latency, which our models do not read.
    if primitive in ("intadd", "intmul", "intmac", "fpadd", "fpmul", "fpmac",
                     "fpsfu", "mxfpmac"):
        stages = _as_int(take(_PIPELINE_KEYS))
        if stages is not None:
            out["pipeline_stages"] = stages

    ignored = sorted(k for k in attrs
                     if k not in consumed and k not in _SILENTLY_DROPPED)
    if ignored:
        notes.append(
            f"{component} ({primitive}): ignored Accelergy attribute(s) "
            f"{', '.join(ignored)} — no NPUWattch attribute corresponds")
    return out


def _block_width(attrs: Mapping[str, Any], take) -> Optional[int]:
    """Accelergy's ``word-bits = datawidth x block-size`` convention."""
    datawidth = _as_int(_first(attrs, ("datawidth",)))
    if datawidth is None:
        return None
    take(("datawidth",))
    block = _as_int(take(_BLOCK_SIZE_KEYS)) or 1
    return datawidth * block


def _storage_attributes(primitive, attrs, take, out, *, component,
                        warnings, notes, consumed) -> None:
    width = _as_int(take(_WORD_KEYS))
    if width is None:
        width = _block_width(attrs, take)
    if width is None:
        warnings.append(
            f"{component} ({primitive}): no word width declared — assuming "
            f"32 bits")
        width = 32
    out["data_width"] = width

    depth = _as_int(take(_DEPTH_KEYS))
    if depth is None:
        capacity_bits = _as_int(take(_CAPACITY_BIT_KEYS))
        if capacity_bits is None:
            kb = _as_int(take(_CAPACITY_BYTE_KEYS))
            capacity_bits = kb * 1024 * 8 if kb else None
        if capacity_bits is not None:
            depth = max(1, capacity_bits // width)
            notes.append(
                f"{component} ({primitive}): depth {depth} derived from the "
                f"declared capacity / {width} b word")
    if depth is None:
        warnings.append(
            f"{component} ({primitive}): neither depth nor capacity declared "
            f"— assuming 64 entries")
        depth = 64
    out["mem_depth_per_bank"] = depth

    banks = _as_int(take(_BANK_KEYS))
    if banks is not None:
        out["mem_banks"] = banks
    if primitive == "fifo":
        return

    r_ports = _as_int(take(_R_PORT_KEYS))
    w_ports = _as_int(take(_W_PORT_KEYS))
    rw_ports = _as_int(take(_RW_PORT_KEYS))
    if r_ports is None and w_ports is None and rw_ports is None:
        rw_ports = 1
        notes.append(
            f"{component} ({primitive}): no port count declared — assuming a "
            f"single shared read-or-write port")
    if r_ports is not None:
        out["mem_r_ports"] = r_ports
    if w_ports is not None:
        out["mem_w_ports"] = w_ports
    if rw_ports is not None:
        out["mem_rw_ports"] = rw_ports


def _int_attributes(primitive, attrs, take, out, *, component,
                    warnings, notes) -> None:
    a = _as_int(take(("data_width_a", "a_width")))
    b = _as_int(take(("data_width_b", "b_width")))
    width = _as_int(take(_OPERAND_KEYS))
    a = a or width
    if a is None:
        warnings.append(
            f"{component} ({primitive}): no operand width declared — assuming "
            f"8 bits")
        a = 8
    b = b or a
    out["number_format"] = "int"
    out["data_width_a"] = a
    out["data_width_b"] = b

    declared_out = _as_int(take(("data_width_out", "out_width")))
    if primitive == "intmac":
        acc = _as_int(take(("data_width_acc", "acc_width")))
        if acc is None:
            acc = _ACC_WIDTH_MULTIPLIER * max(a, b)
            notes.append(
                f"{component} (intmac): accumulator width {acc} b inferred as "
                f"{_ACC_WIDTH_MULTIPLIER}x the operand width — Accelergy "
                f"declares none (int8 x int8 -> int32 convention)")
        out["data_width_acc"] = acc
        out["data_width_out"] = declared_out or acc
    elif primitive == "intmul":
        out["data_width_out"] = declared_out or (a + b)
    else:                                    # intadd
        out["data_width_out"] = declared_out or max(a, b)


def _fp_attributes(primitive, attrs, take, out, *, component,
                   warnings, notes) -> None:
    exp = _as_int(take(("exponent_bits", "exp_bits")))
    mant = _as_int(take(("mantissa_bits", "man_bits")))
    width = _as_int(take(_OPERAND_KEYS))
    if exp is None or mant is None:
        split = _FP_SPLIT_BY_WIDTH.get(width or 32)
        if split is None:
            warnings.append(
                f"{component} ({primitive}): {width} b is not an IEEE width — "
                f"assuming single precision (8, 23); declare exponent_bits / "
                f"mantissa_bits to model the real format")
            split = _FP_SPLIT_BY_WIDTH[32]
        elif width is None:
            warnings.append(
                f"{component} ({primitive}): no width or exponent/mantissa "
                f"split declared — assuming fp32")
        else:
            notes.append(
                f"{component} ({primitive}): exponent/mantissa {split} "
                f"inferred from the declared {width} b width (IEEE 754); "
                f"bf16 and fp16 share a width — declare the split to "
                f"distinguish them")
        exp, mant = split
    out["number_format"] = "fp"
    out["exponent_bits"] = exp
    out["mantissa_bits"] = mant
    if width is not None:
        out["data_width"] = width
    if primitive == "fpsfu":
        for key in ("sfu_segments", "sfu_op_exp", "sfu_op_trig", "sfu_op_hyp",
                    "sfu_op_erf", "sfu_op_relu"):
            value = _as_int(take((key,)))
            if value is not None:
                out[key] = value
        if "sfu_segments" not in out:
            out["sfu_segments"] = 16
            notes.append(
                f"{component} (fpsfu): sfu_segments not declared — assuming "
                f"a 16-segment PWL table")
        for key, default in (("sfu_op_exp", 1), ("sfu_op_trig", 1),
                             ("sfu_op_hyp", 1), ("sfu_op_erf", 1)):
            out.setdefault(key, default)


def _fabric_attributes(primitive, attrs, take, out, *, component,
                       warnings) -> None:
    width = _as_int(take(_OPERAND_KEYS))
    if width is None:
        warnings.append(
            f"{component} ({primitive}): no flit/data width declared — "
            f"assuming 64 bits")
        width = 64
    out["data_width"] = width
    ni = _as_int(take(_INPUT_KEYS))
    no = _as_int(take(_OUTPUT_KEYS))
    if ni is None and no is None:
        warnings.append(
            f"{component} ({primitive}): no port count declared — assuming a "
            f"2-port element")
        ni = no = 2
    out["net_inputs"] = ni if ni is not None else no
    if primitive == "crossbar":
        out["net_outputs"] = no if no is not None else ni
