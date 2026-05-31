from __future__ import annotations

from dataclasses import dataclass
from math import floor, log2


@dataclass(frozen=True)
class MxfpFormat:
    name: str
    elem_width: int
    exp_bits: int
    mant_bits: int
    bias: int
    is_int: bool = False
    use_scale: bool = True


FORMAT_MAP = {
    "mxfp8_e5m2": MxfpFormat("mxfp8_e5m2", 8, 5, 2, 15),
    "mxfp8_e4m3": MxfpFormat("mxfp8_e4m3", 8, 4, 3, 7),
    "mxfp6_e3m2": MxfpFormat("mxfp6_e3m2", 6, 3, 2, 3),
    "mxfp6_e2m3": MxfpFormat("mxfp6_e2m3", 6, 2, 3, 1),
    "mxfp4_e2m1": MxfpFormat("mxfp4_e2m1", 4, 2, 1, 1),
    "mxint8": MxfpFormat("mxint8", 8, 0, 0, 0, is_int=True),
    "bf16": MxfpFormat("bf16", 16, 8, 7, 127, use_scale=False),
}


def get_mxfp_format(
    input_format: str,
    *,
    elem_width: int | None = None,
    elem_exp_bits: int | None = None,
    elem_mant_bits: int | None = None,
    elem_bias: int | None = None,
    is_int: bool = False,
    use_scale: bool = True,
) -> MxfpFormat:
    if input_format != "custom":
        if input_format not in FORMAT_MAP:
            raise ValueError(f"unsupported input_format: {input_format}")
        return FORMAT_MAP[input_format]
    if elem_width is None or elem_exp_bits is None or elem_mant_bits is None:
        raise ValueError("custom format requires elem_width, elem_exp_bits, and elem_mant_bits")
    if elem_width < 2:
        raise ValueError("elem_width must be >= 2")
    if is_int:
        return MxfpFormat("custom", elem_width, 0, 0, 0, is_int=True, use_scale=use_scale)
    bias = elem_bias if elem_bias is not None else (1 << (elem_exp_bits - 1)) - 1
    if elem_exp_bits < 1 or elem_mant_bits < 1:
        raise ValueError("custom FP exp/mant bits must be >= 1")
    return MxfpFormat("custom", elem_width, elem_exp_bits, elem_mant_bits, bias, use_scale=use_scale)


def acc_width_from_format(acc_format: str, acc_width: int | None = None) -> int:
    if acc_format == "fp32":
        return 32
    if acc_format == "fp64":
        return 64
    if acc_format == "custom":
        if acc_width is None or acc_width < 8:
            raise ValueError("custom accumulator requires acc_width >= 8")
        return acc_width
    raise ValueError(f"unsupported acc_format: {acc_format}")


def _mask(width: int) -> int:
    return (1 << width) - 1


def _wrap_signed(value: int, width: int) -> int:
    value &= _mask(width)
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def _to_hex(value: int, width: int) -> str:
    digits = (width + 3) // 4
    return f"{value & _mask(width):0{digits}x}"


def _decode_elem(code: int, fmt: MxfpFormat, scale: int, scale_bias: int, frac_bits: int) -> int:
    if fmt.is_int:
        val = _wrap_signed(code, fmt.elem_width)
        shift = frac_bits + (scale - scale_bias if fmt.use_scale else 0)
        return val << shift if shift >= 0 else val >> (-shift)

    sign = (code >> (fmt.elem_width - 1)) & 1
    exp = (code >> fmt.mant_bits) & _mask(fmt.exp_bits)
    mant = code & _mask(fmt.mant_bits)
    if exp == 0 and mant == 0:
        return 0
    if exp == 0:
        mag = mant
        shift = 1 - fmt.bias - fmt.mant_bits + frac_bits
    else:
        mag = (1 << fmt.mant_bits) | mant
        shift = exp - fmt.bias - fmt.mant_bits + frac_bits
    if fmt.use_scale:
        shift += scale - scale_bias
    val = mag << shift if shift >= 0 else mag >> (-shift)
    return -val if sign else val


def _encode_int(value: int, fmt: MxfpFormat) -> int:
    return value & _mask(fmt.elem_width)


def _encode_fp(value: int, fmt: MxfpFormat) -> int:
    if value == 0:
        return 0
    sign = 1 if value < 0 else 0
    mag = abs(value)
    exp_unbiased = floor(log2(mag))
    exp = exp_unbiased + fmt.bias
    if exp <= 0:
        mant = max(1, min(_mask(fmt.mant_bits), mag))
        exp = 0
    else:
        scaled = int(round((mag / (2**exp_unbiased) - 1.0) * (1 << fmt.mant_bits)))
        if scaled >= (1 << fmt.mant_bits):
            scaled = 0
            exp += 1
        exp = min(exp, _mask(fmt.exp_bits))
        mant = scaled & _mask(fmt.mant_bits)
    return (sign << (fmt.elem_width - 1)) | (exp << fmt.mant_bits) | mant


def _encode_value(value: int, fmt: MxfpFormat) -> int:
    if fmt.is_int:
        return _encode_int(value, fmt)
    return _encode_fp(value, fmt)


def _pack(values: list[int], width: int) -> str:
    packed = 0
    for idx, value in enumerate(values):
        packed |= (value & _mask(width)) << (idx * width)
    return _to_hex(packed, len(values) * width)


def emit_mxfpmac_vectors(
    fmt: MxfpFormat,
    *,
    block_elems: int,
    num_blocks: int,
    scale_exp_bits: int,
    scale_bias: int,
    acc_width: int,
    decode_frac_bits: int,
) -> list[dict[str, str | int]]:
    patterns = [
        ("idle zeros", lambda b, e: 0, lambda b, e: 0, lambda b: 0),
        ("positive ramp", lambda b, e: (e % 3) + 1, lambda b, e: (e % 2) + 1, lambda b: 0),
        ("signed mix", lambda b, e: ((e % 5) - 2), lambda b, e: (2 - (e % 5)), lambda b: 0),
        ("scaled blocks", lambda b, e: (b % 3) + 1, lambda b, e: (e % 3) - 1, lambda b: (b % 3) - 1),
        ("sparse", lambda b, e: 2 if (e + b) % 7 == 0 else 0, lambda b, e: -1 if e % 5 == 0 else 1, lambda b: 0),
        ("busy", lambda b, e: ((b + e) % 5) - 2, lambda b, e: ((2 * b + e) % 5) - 2, lambda b: 0),
    ]

    vectors: list[dict[str, str | int]] = []
    for index, (desc, aval, bval, shift_fn) in enumerate(patterns):
        a_codes: list[int] = []
        b_codes: list[int] = []
        a_scales: list[int] = []
        b_scales: list[int] = []
        expected = 0
        for block in range(num_blocks):
            shift = shift_fn(block)
            scale = max(0, min(_mask(scale_exp_bits), scale_bias + shift))
            a_scales.append(scale if fmt.use_scale else 0)
            b_scales.append(scale_bias if fmt.use_scale else 0)
            for elem in range(block_elems):
                a_code = _encode_value(aval(block, elem), fmt)
                b_code = _encode_value(bval(block, elem), fmt)
                a_codes.append(a_code)
                b_codes.append(b_code)
                a_dec = _decode_elem(a_code, fmt, a_scales[-1], scale_bias, decode_frac_bits)
                b_dec = _decode_elem(b_code, fmt, b_scales[-1], scale_bias, decode_frac_bits)
                expected += (a_dec * b_dec) >> decode_frac_bits
        expected = _wrap_signed(expected, acc_width)
        vectors.append(
            {
                "index": index,
                "desc": desc,
                "a_hex": _pack(a_codes, fmt.elem_width),
                "b_hex": _pack(b_codes, fmt.elem_width),
                "scale_a_hex": _pack(a_scales, scale_exp_bits),
                "scale_b_hex": _pack(b_scales, scale_exp_bits),
                "expected_hex": _to_hex(expected, acc_width),
            }
        )
    return vectors
