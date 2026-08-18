from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


@dataclass(frozen=True)
class FloatFormat:
    exp_bits: int
    mantissa_bits: int

    @property
    def width(self) -> int:
        return 1 + self.exp_bits + self.mantissa_bits

    @property
    def bias(self) -> int:
        return (1 << (self.exp_bits - 1)) - 1

    @property
    def exp_max(self) -> int:
        return (1 << self.exp_bits) - 1

    @property
    def mantissa_mask(self) -> int:
        return (1 << self.mantissa_bits) - 1


@dataclass(frozen=True)
class EncodedValue:
    bits: int
    text: str


def _pow2(exp: int) -> Fraction:
    if exp >= 0:
        return Fraction(1 << exp, 1)
    return Fraction(1, 1 << (-exp))


def _round_to_even(value: Fraction) -> int:
    floor = value.numerator // value.denominator
    rem = value - floor
    half = Fraction(1, 2)
    if rem > half:
        return floor + 1
    if rem < half:
        return floor
    return floor if (floor % 2 == 0) else floor + 1


def _fraction_from_text(text: str) -> Fraction:
    return Fraction(text)


def _find_exponent(value: Fraction) -> int:
    exp = value.numerator.bit_length() - value.denominator.bit_length()
    while value < _pow2(exp):
        exp -= 1
    while value >= _pow2(exp + 1):
        exp += 1
    return exp


def _qnan(fmt: FloatFormat) -> int:
    return (fmt.exp_max << fmt.mantissa_bits) | (1 << max(fmt.mantissa_bits - 1, 0))


def pack_fraction(value: Fraction, fmt: FloatFormat) -> int:
    sign = 1 if value < 0 else 0
    magnitude = -value if value < 0 else value

    if magnitude == 0:
        return sign << (fmt.width - 1)

    min_normal_exp = 1 - fmt.bias
    exponent = _find_exponent(magnitude)

    if exponent > fmt.bias:
        return (sign << (fmt.width - 1)) | (fmt.exp_max << fmt.mantissa_bits)

    if exponent >= min_normal_exp:
        scaled = magnitude / _pow2(exponent)
        mantissa_fraction = (scaled - 1) * (1 << fmt.mantissa_bits)
        mantissa = _round_to_even(mantissa_fraction)
        if mantissa == (1 << fmt.mantissa_bits):
            exponent += 1
            mantissa = 0
        if exponent > fmt.bias:
            return (sign << (fmt.width - 1)) | (fmt.exp_max << fmt.mantissa_bits)
        exp_field = exponent + fmt.bias
        return (
            (sign << (fmt.width - 1))
            | (exp_field << fmt.mantissa_bits)
            | mantissa
        )

    scaled = magnitude / _pow2(min_normal_exp - fmt.mantissa_bits)
    mantissa = _round_to_even(scaled)
    if mantissa == 0:
        return sign << (fmt.width - 1)
    if mantissa >= (1 << fmt.mantissa_bits):
        return (
            (sign << (fmt.width - 1))
            | (1 << fmt.mantissa_bits)
        )
    return (sign << (fmt.width - 1)) | mantissa


def decode_bits(bits: int, fmt: FloatFormat) -> tuple[str, Fraction | None, int]:
    sign = -1 if ((bits >> (fmt.width - 1)) & 1) else 1
    exp_field = (bits >> fmt.mantissa_bits) & fmt.exp_max
    mantissa = bits & fmt.mantissa_mask

    if exp_field == fmt.exp_max:
        if mantissa == 0:
            return "inf", None, sign
        return "nan", None, sign

    if exp_field == 0:
        if mantissa == 0:
            return "zero", Fraction(0, 1), sign
        value = Fraction(mantissa, 1 << fmt.mantissa_bits) * _pow2(1 - fmt.bias)
        return "finite", sign * value, sign

    value = (
        Fraction((1 << fmt.mantissa_bits) | mantissa, 1 << fmt.mantissa_bits)
        * _pow2(exp_field - fmt.bias)
    )
    return "finite", sign * value, sign


def add_bits(a_bits: int, b_bits: int, fmt: FloatFormat) -> int:
    a_kind, a_val, a_sign = decode_bits(a_bits, fmt)
    b_kind, b_val, b_sign = decode_bits(b_bits, fmt)

    if "nan" in (a_kind, b_kind):
        return _qnan(fmt)
    if a_kind == "inf" and b_kind == "inf" and a_sign != b_sign:
        return _qnan(fmt)
    if a_kind == "inf":
        return a_bits
    if b_kind == "inf":
        return b_bits
    return pack_fraction((a_val or Fraction(0, 1)) + (b_val or Fraction(0, 1)), fmt)


def mul_bits(a_bits: int, b_bits: int, fmt: FloatFormat) -> int:
    a_kind, a_val, a_sign = decode_bits(a_bits, fmt)
    b_kind, b_val, b_sign = decode_bits(b_bits, fmt)

    if "nan" in (a_kind, b_kind):
        return _qnan(fmt)
    if (a_kind == "inf" and b_kind == "zero") or (b_kind == "inf" and a_kind == "zero"):
        return _qnan(fmt)
    if a_kind == "inf" or b_kind == "inf":
        sign = 1 if a_sign * b_sign < 0 else 0
        return (sign << (fmt.width - 1)) | (fmt.exp_max << fmt.mantissa_bits)
    return pack_fraction((a_val or Fraction(0, 1)) * (b_val or Fraction(0, 1)), fmt)


def mac_bits(a_bits: int, b_bits: int, c_bits: int, fmt: FloatFormat) -> int:
    product = mul_bits(a_bits, b_bits, fmt)
    return add_bits(product, c_bits, fmt)


def to_hex(bits: int, width: int) -> str:
    digits = (width + 3) // 4
    return f"{bits:0{digits}x}"


def text_to_bits(text: str, fmt: FloatFormat) -> EncodedValue:
    value = _fraction_from_text(text)
    return EncodedValue(bits=pack_fraction(value, fmt), text=text)


def emit_add_vectors(fmt: FloatFormat) -> list[dict[str, str | int]]:
    cases = [
        ("1.0", "1.0"),
        ("1.5", "2.25"),
        ("-2.5", "1.25"),
        ("0.5", "0.03125"),
        ("16.0", "-12.5"),
        ("0.75", "-0.5"),
        ("-7.125", "-1.875"),
        ("0.0", "3.5"),
        ("7.125", "0.03125"),
        ("1.875", "-1.75"),
        ("4.5", "4.5"),
        ("-0.125", "-0.5"),
    ]
    return [
        _emit_binary_case(idx, lhs, rhs, fmt, add_bits(lhs_bits.bits, rhs_bits.bits, fmt))
        for idx, (lhs, rhs) in enumerate(cases)
        for lhs_bits, rhs_bits in [(text_to_bits(lhs, fmt), text_to_bits(rhs, fmt))]
    ]


def emit_mul_vectors(fmt: FloatFormat) -> list[dict[str, str | int]]:
    cases = [
        ("1.5", "2.25"),
        ("-2.5", "1.25"),
        ("0.5", "0.03125"),
        ("-0.75", "-4.5"),
        ("3.75", "0.0"),
        ("7.125", "1.875"),
        ("16.0", "-0.5"),
        ("1.125", "1.125"),
        ("0.25", "0.25"),
        ("-3.5", "2.0"),
        ("5.5", "-1.5"),
        ("0.0625", "4.0"),
    ]
    return [
        _emit_binary_case(idx, lhs, rhs, fmt, mul_bits(lhs_bits.bits, rhs_bits.bits, fmt))
        for idx, (lhs, rhs) in enumerate(cases)
        for lhs_bits, rhs_bits in [(text_to_bits(lhs, fmt), text_to_bits(rhs, fmt))]
    ]


def emit_mac_vectors(fmt: FloatFormat) -> list[dict[str, str | int]]:
    cases = [
        ("1.5", "2.0", "0.25"),
        ("-2.5", "1.5", "4.0"),
        ("0.5", "0.03125", "1.0"),
        ("-0.75", "-4.5", "-1.25"),
        ("3.75", "0.0", "2.25"),
        ("7.125", "1.875", "-8.0"),
        ("16.0", "-0.5", "1.0"),
        ("1.125", "1.125", "1.125"),
        ("0.25", "0.25", "0.25"),
        ("-3.5", "2.0", "7.0"),
        ("5.5", "-1.5", "0.5"),
        ("0.0625", "4.0", "-0.25"),
    ]
    rows: list[dict[str, str | int]] = []
    for idx, (lhs, rhs, addend) in enumerate(cases):
        a_bits = text_to_bits(lhs, fmt)
        b_bits = text_to_bits(rhs, fmt)
        c_bits = text_to_bits(addend, fmt)
        expected = mac_bits(a_bits.bits, b_bits.bits, c_bits.bits, fmt)
        rows.append(
            {
                "index": idx,
                "desc": f"{lhs} * {rhs} + {addend}",
                "a_hex": to_hex(a_bits.bits, fmt.width),
                "b_hex": to_hex(b_bits.bits, fmt.width),
                "c_hex": to_hex(c_bits.bits, fmt.width),
                "expected_hex": to_hex(expected, fmt.width),
            }
        )
    return rows


def _emit_binary_case(index: int, lhs: str, rhs: str, fmt: FloatFormat, expected: int) -> dict[str, str | int]:
    a_bits = text_to_bits(lhs, fmt)
    b_bits = text_to_bits(rhs, fmt)
    op = "+" if expected == add_bits(a_bits.bits, b_bits.bits, fmt) else "*"
    return {
        "index": index,
        "desc": f"{lhs} {op} {rhs}",
        "a_hex": to_hex(a_bits.bits, fmt.width),
        "b_hex": to_hex(b_bits.bits, fmt.width),
        "expected_hex": to_hex(expected, fmt.width),
    }


def emit_manifest_lines(paths: Iterable[str]) -> str:
    return "\n".join(f"- `{path}`" for path in paths)
