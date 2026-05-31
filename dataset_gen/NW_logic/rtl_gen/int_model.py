from __future__ import annotations


def _mask(width: int) -> int:
    return (1 << width) - 1


def wrap_signed(value: int, width: int) -> int:
    bits = value & _mask(width)
    sign = 1 << (width - 1)
    return bits - (1 << width) if bits & sign else bits


def to_bits(value: int, width: int) -> int:
    return value & _mask(width)


def to_hex(value: int, width: int) -> str:
    digits = (width + 3) // 4
    return f"{to_bits(value, width):0{digits}x}"


def _fit(value: int, width: int) -> int:
    return wrap_signed(value, width)


def emit_intadd_vectors(a_width: int, b_width: int, out_width: int) -> list[dict[str, str | int]]:
    seeds = [
        (0, 0),
        (1, 1),
        (-1, 1),
        (7, -3),
        (-8, -5),
        (13, 21),
        (-17, 9),
        (31, -1),
        (-32, 15),
        (5, -12),
        (18, 18),
        (-21, -7),
    ]
    rows: list[dict[str, str | int]] = []
    for idx, (a_raw, b_raw) in enumerate(seeds):
        a_val = _fit(a_raw, a_width)
        b_val = _fit(b_raw, b_width)
        y_val = wrap_signed(a_val + b_val, out_width)
        rows.append(
            {
                "index": idx,
                "desc": f"{a_val} + {b_val}",
                "a_hex": to_hex(a_val, a_width),
                "b_hex": to_hex(b_val, b_width),
                "expected_hex": to_hex(y_val, out_width),
            }
        )
    return rows


def emit_intmul_vectors(a_width: int, b_width: int, out_width: int) -> list[dict[str, str | int]]:
    seeds = [
        (0, 0),
        (1, 1),
        (-1, 1),
        (3, -2),
        (-4, -5),
        (7, 9),
        (-11, 6),
        (15, -7),
        (-16, 5),
        (12, 12),
        (-9, -3),
        (2, -13),
    ]
    rows: list[dict[str, str | int]] = []
    for idx, (a_raw, b_raw) in enumerate(seeds):
        a_val = _fit(a_raw, a_width)
        b_val = _fit(b_raw, b_width)
        y_val = wrap_signed(a_val * b_val, out_width)
        rows.append(
            {
                "index": idx,
                "desc": f"{a_val} * {b_val}",
                "a_hex": to_hex(a_val, a_width),
                "b_hex": to_hex(b_val, b_width),
                "expected_hex": to_hex(y_val, out_width),
            }
        )
    return rows


def emit_intmac_vectors(a_width: int, b_width: int, acc_width: int, out_width: int) -> list[dict[str, str | int]]:
    seeds = [
        (1, 1),
        (2, 3),
        (-4, 5),
        (7, -2),
        (-3, -3),
        (0, 9),
        (5, 5),
        (-8, 4),
        (6, -7),
        (3, 12),
        (-2, 11),
        (9, -1),
    ]
    rows: list[dict[str, str | int]] = []
    acc = 0
    for idx, (a_raw, b_raw) in enumerate(seeds):
        a_val = _fit(a_raw, a_width)
        b_val = _fit(b_raw, b_width)
        prod = wrap_signed(a_val * b_val, acc_width)
        acc = wrap_signed(acc + prod, acc_width)
        out_val = wrap_signed(acc, out_width)
        rows.append(
            {
                "index": idx,
                "desc": f"acc + ({a_val} * {b_val})",
                "a_hex": to_hex(a_val, a_width),
                "b_hex": to_hex(b_val, b_width),
                "expected_hex": to_hex(out_val, out_width),
            }
        )
    return rows
