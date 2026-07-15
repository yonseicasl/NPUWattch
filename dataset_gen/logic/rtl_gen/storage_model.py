from __future__ import annotations

import random


def _mask(width: int) -> int:
    return (1 << width) - 1


def _hex(value: int, width: int) -> str:
    return f"{value & _mask(width):0{(width + 3) // 4}x}"


def _pack(values: list[int], width: int) -> str:
    packed = 0
    for idx, value in enumerate(values):
        packed |= (value & _mask(width)) << (idx * width)
    return _hex(packed, len(values) * width)


def emit_regfile_vectors(width: int, depth: int, num_r: int, num_w: int, cycles: int = 96) -> list[dict[str, int | str]]:
    rng = random.Random(20260601)
    mem = [0] * depth
    # The RTL register file does not reset its storage, so reads of
    # never-written entries return X. Only read written addresses.
    written: list[int] = []
    vectors: list[dict[str, int | str]] = []
    addr_width = max(1, (depth - 1).bit_length())
    for cycle in range(cycles):
        w_en: list[int] = []
        w_addr: list[int] = []
        w_data: list[int] = []

        hot_addr = cycle % min(depth, 7)
        for port in range(num_w):
            en = 1 if cycle < 16 or rng.randrange(4) != 0 else 0
            addr = hot_addr if cycle % 5 == 0 else rng.randrange(depth)
            data = rng.randrange(1 << width)
            w_en.append(en)
            w_addr.append(addr)
            w_data.append(data)

        for port in range(num_w):
            if w_en[port]:
                mem[w_addr[port]] = w_data[port]
                if w_addr[port] not in written:
                    written.append(w_addr[port])

        r_addr = []
        r_expected = []
        for port in range(num_r):
            if cycle % 6 == 0 and hot_addr in written:
                addr = hot_addr
            else:
                addr = rng.choice(written)
            r_addr.append(addr)
            r_expected.append(mem[addr])

        vectors.append(
            {
                "index": cycle,
                "w_en_hex": _pack(w_en, 1),
                "w_addr_hex": _pack(w_addr, addr_width),
                "w_data_hex": _pack(w_data, width),
                "r_addr_hex": _pack(r_addr, addr_width),
                "r_expected_hex": _pack(r_expected, width),
            }
        )
    return vectors


def emit_fifo_vectors(width: int, depth: int, cycles: int = 128) -> list[dict[str, int | str]]:
    rng = random.Random(20260602)
    queue: list[int] = []
    vectors: list[dict[str, int | str]] = []
    for cycle in range(cycles):
        if cycle < 10:
            push_req = 1
            pop_req = 0
        elif cycle < 24:
            push_req = 0
            pop_req = 1
        elif cycle < 60:
            push_req = 1 if rng.randrange(3) != 0 else 0
            pop_req = 1 if rng.randrange(2) == 0 else 0
        elif cycle < 96:
            push_req = 1
            pop_req = 1 if rng.randrange(4) != 0 else 0
        else:
            push_req = 0
            pop_req = 1

        push_data = rng.randrange(1 << width)
        full_before = 1 if len(queue) >= depth else 0
        empty_before = 1 if not queue else 0
        pop_valid = 1 if pop_req and not empty_before else 0
        pop_data = queue[0] if pop_valid else 0
        push_fire = 1 if push_req and not full_before else 0

        if pop_valid:
            queue.pop(0)
        if push_fire:
            queue.append(push_data)

        vectors.append(
            {
                "index": cycle,
                "push": push_req,
                "pop": pop_req,
                "push_data_hex": _hex(push_data, width),
                "expected_valid": pop_valid,
                "expected_data_hex": _hex(pop_data, width),
                "expected_full": 1 if len(queue) >= depth else 0,
                "expected_empty": 1 if not queue else 0,
            }
        )
    return vectors
