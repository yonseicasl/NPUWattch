"""Bit-exact model of the NVDLA nv_small SDP int8 datapath (BS -> BN -> CVT).

Each function follows one module of third_party/nvdla_sdp/vmod. The model was
compared with an Icarus Verilog simulation of those files: 80 random
configurations x 256 elements, no difference.

The characterization uses one fixed configuration, ``SDP_CONFIG``: the
epilogue of an int8 convolution.
  BS  ALU sum with a per-channel bias (operand stream, left shift 4).
      MUL and ReLU bypassed.
  BN  MUL with a per-channel Q14 scale (operand stream, right shift 14),
      then ALU sum with a per-channel offset (operand stream), then ReLU.
  CVT requantization to int8: scale 0x2d41, right shift 25, saturation.
"""
from __future__ import annotations

import random

from .int_model import to_hex, wrap_signed

#: The configuration that the testbench writes before it sets op_en.
SDP_CONFIG: dict = {
    "bs": {
        "bypass": 0, "alu_bypass": 0, "alu_algo": 2, "alu_src": 1, "alu_shift": 4,
        "alu_operand": 0, "mul_bypass": 1, "mul_src": 1, "mul_prelu": 0,
        "mul_shift": 0, "mul_operand": 0, "relu_bypass": 1,
    },
    "bn": {
        "bypass": 0, "alu_bypass": 0, "alu_algo": 2, "alu_src": 1, "alu_shift": 0,
        "alu_operand": 0, "mul_bypass": 0, "mul_src": 1, "mul_prelu": 0,
        "mul_shift": 14, "mul_operand": 0, "relu_bypass": 0,
    },
    "cvt_offset": 0,
    "cvt_scale": 0x2D41,
    "cvt_shift": 25,
}

#: One operand beat of the BS/BN streams carries the operands of 8 elements.
ELEMENTS_PER_BEAT = 8


def _sat(value: int, bits: int) -> int:
    low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return low if value < low else high if value > high else value


def shift_left_sat(value: int, shift: int, out_bits: int = 32) -> int:
    """NV_NVDLA_HLS_shiftleftsu: signed left shift, saturated to out_bits."""
    return _sat(value << shift, out_bits)


def shift_right_round_sat(value: int, shift: int, in_bits: int = 49,
                          out_bits: int = 32) -> int:
    """NV_NVDLA_HLS_shiftrightsu and shiftrightsatsu.

    Signed right shift. The result rounds up by one when the first discarded
    bit is set and (the value is positive or another discarded bit is set).
    Then the result saturates to out_bits. A shift of in_bits or more gives 0.
    """
    if shift >= in_bits:
        return 0
    mask = (1 << in_bits) - 1
    raw = value & mask
    sign = (raw >> (in_bits - 1)) & 1
    wide = ((((mask if sign else 0) << in_bits) | raw) << in_bits) >> shift
    data_shift = (wide >> in_bits) & mask
    guide = (wide >> (in_bits - 1)) & 1
    sticky = wide & ((1 << (in_bits - 1)) - 1)
    point5 = guide & ((1 - sign) | (1 if sticky else 0))
    high = (data_shift >> (out_bits - 1)) & ((1 << (in_bits - out_bits)) - 1)
    high_ones = (1 << (in_bits - out_bits)) - 1
    low_ones = (data_shift & ((1 << (out_bits - 1)) - 1)) == (1 << (out_bits - 1)) - 1
    need_sat = (sign and high != high_ones) or (not sign and high != 0) or \
        (not sign and low_ones and point5)
    if need_sat:
        return -(1 << (out_bits - 1)) if sign else (1 << (out_bits - 1)) - 1
    return wrap_signed(data_shift + point5, out_bits)


def x_stage(value: int, cfg: dict, alu_op: int, mul_op: int) -> int:
    """NV_NVDLA_SDP_HLS_x1_int / x2_int: ALU, MUL (PReLU), truncation, ReLU.

    alu_op and mul_op are the stream operands. A stage with src=0 uses the
    register operand of cfg instead.
    """
    if cfg["alu_bypass"]:
        alu = value
    else:
        operand = alu_op if cfg["alu_src"] else cfg["alu_operand"]
        operand = shift_left_sat(wrap_signed(operand, 16), cfg["alu_shift"])
        algo = cfg["alu_algo"]
        alu = max(value, operand) if algo == 0 else \
            min(value, operand) if algo == 1 else value + operand
        alu = wrap_signed(alu, 33)
    if cfg["mul_bypass"]:
        product, keep = alu, False
    else:
        operand = mul_op if cfg["mul_src"] else cfg["mul_operand"]
        keep = bool(cfg["mul_prelu"]) and alu >= 0
        product = alu if keep else wrap_signed(alu * wrap_signed(operand, 16), 49)
    if keep:
        out = wrap_signed(product, 32)
    else:
        out = shift_right_round_sat(product, cfg["mul_shift"], 49, 32)
    if not cfg["relu_bypass"]:
        out = max(out, 0)
    return out


def cvt_int8(value: int, offset: int, scale: int, shift: int) -> int:
    """NV_NVDLA_SDP_HLS_C_int with int8 output precision."""
    diff = wrap_signed(value - wrap_signed(offset, 32), 33)
    product = wrap_signed(diff * wrap_signed(scale, 16), 49)
    return _sat(shift_right_round_sat(product, shift, 49, 17), 8)


def sdp_element(value: int, ops: dict, cfg: dict = SDP_CONFIG) -> int:
    """The int8 result of one int32 accumulator value.

    ops holds the stream operands of the element: bs_alu, bs_mul, bn_alu,
    bn_mul (16-bit values).
    """
    out = value
    if not cfg["bs"]["bypass"]:
        out = x_stage(out, cfg["bs"], ops["bs_alu"], ops["bs_mul"])
    if not cfg["bn"]["bypass"]:
        out = x_stage(out, cfg["bn"], ops["bn_alu"], ops["bn_mul"])
    return cvt_int8(out, cfg["cvt_offset"], cfg["cvt_scale"], cfg["cvt_shift"])


def emit_nvdla_sdp_vectors(num_elements: int = 256, seed: int = 7) -> list[dict]:
    """Directed and random elements for the functional phase of the TB.

    The count is a multiple of 8, because one operand beat and one output
    word each hold 8 elements. The first elements are corner cases: zero,
    the int32 limits, values at the int8 rounding and saturation edges, and
    operands at the int16 limits.
    """
    if num_elements % ELEMENTS_PER_BEAT:
        raise ValueError("num_elements must be a multiple of 8")
    rng = random.Random(seed)
    corners = [0, 1, -1, (1 << 31) - 1, -(1 << 31), 2896, -2896, 1448, -1448,
               371000, -371000, 1 << 20, -(1 << 20), 123456, -654321, 77]
    op_corners = [0, 0x7FFF, 0x8000, 0x4000, 0xFFFF, 0x0001, 0x2000, 0x6000]
    vectors = []
    for index in range(num_elements):
        if index < len(corners):
            value = corners[index]
            ops = {k: op_corners[(index + n) % len(op_corners)]
                   for n, k in enumerate(("bs_alu", "bs_mul", "bn_alu", "bn_mul"))}
        else:
            bits = rng.choice((12, 18, 20, 24, 32))
            value = wrap_signed(rng.getrandbits(bits), bits)
            ops = {"bs_alu": rng.getrandbits(12) - 2048,
                   "bs_mul": rng.getrandbits(16),
                   "bn_alu": rng.getrandbits(13) - 4096,
                   "bn_mul": rng.randint(8192, 24575)}
        result = sdp_element(value, {k: v & 0xFFFF for k, v in ops.items()})
        vectors.append({
            "index": index,
            "data_hex": to_hex(value, 32),
            "bs_alu_hex": to_hex(ops["bs_alu"], 16),
            "bs_mul_hex": to_hex(ops["bs_mul"], 16),
            "bn_alu_hex": to_hex(ops["bn_alu"], 16),
            "bn_mul_hex": to_hex(ops["bn_mul"], 16),
            "expected_hex": to_hex(result, 8),
        })
    return vectors
