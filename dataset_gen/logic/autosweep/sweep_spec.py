"""The sweep specification: every architectural configuration in the dataset.

One place enumerates the (rtl_name, arch_params) pairs the frequency probe
and the main sweep consume. Values are log-spaced (the model space is log10),
densified for interpolation, with extrapolation tails bounded only by
physical limits:
  - signal pin budget (a config whose I/O would force a lower placement
    utilization distorts the area data; caps below keep buses <= ~2k pins),
  - PnR runtime (multipliers above 64 bit grow O(w^2) and are excluded).
"""
from __future__ import annotations

# Modules whose generated RTL has i_clk/i_rst_n; the NoC blocks are
# combinational and synthesize against a virtual clock.
CLOCKED_MODULES = {
    "intadd", "intmul", "intmac",
    "fpadd", "fpmul", "fpmac", "mxfpmac",
    "regfile", "fifo",
}

# (exp_bits, mantissa_bits): the 7 industry formats plus synthetic points
# that densify/extend both axes for interpolation and extrapolation.
FP_FORMATS = [
    (4, 3),    # fp8 e4m3
    (5, 2),    # fp8 e5m2
    (5, 10),   # fp16
    (8, 7),    # bf16
    (8, 10),   # tf32
    (8, 23),   # fp32
    (11, 52),  # fp64
    (3, 2), (4, 6), (6, 5), (6, 12), (7, 15), (9, 31), (10, 40), (12, 64),
]

# The six OCP MX standard concrete formats (spec block size k=32, E8M0 scale,
# FP32 accumulation are the generator defaults).
MX_STANDARD_FORMATS = [
    "mxfp8_e5m2", "mxfp8_e4m3",
    "mxfp6_e3m2", "mxfp6_e2m3",
    "mxfp4_e2m1", "mxint8",
]
_MX_ELEM_BITS = {
    "mxfp8_e5m2": 8, "mxfp8_e4m3": 8,
    "mxfp6_e3m2": 6, "mxfp6_e2m3": 6,
    "mxfp4_e2m1": 4, "mxint8": 8, "bf16": 16,
}
# Keep each MX operand bus at or below 1024 bits (~2.1k signal pins total).
_MX_MAX_OPERAND_BITS = 1024


def _mx_ok(fmt: str, block_elems: int, num_blocks: int) -> bool:
    return block_elems * num_blocks * _MX_ELEM_BITS[fmt] <= _MX_MAX_OPERAND_BITS


def _intadd():
    for w in (4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128):
        for out in (w, w + 8):
            for pipe in (2, 3, 5):
                yield f"a_width={w};b_width={w};out_width={out};pipeline_stages={pipe}"


def _intmul():
    for w in (4, 6, 8, 12, 16, 24, 32, 48, 64):
        for pipe in (2, 3, 5):
            yield f"a_width={w};b_width={w};out_width={2 * w};pipeline_stages={pipe}"
    for a, b in ((8, 4), (16, 4), (16, 8), (32, 16)):
        for pipe in (2, 5):
            yield f"a_width={a};b_width={b};out_width={a + b};pipeline_stages={pipe}"


def _intmac():
    for w in (4, 6, 8, 12, 16, 24, 32, 48, 64):
        accs = sorted({min(2 * w + 8, 128), min(2 * w + 16, 128)}) if w in (8, 16, 32, 64) else [min(2 * w + 8, 128)]
        for acc in accs:
            for pipe in (2, 3, 5):
                yield f"a_width={w};b_width={w};out_width={acc};acc_width={acc};pipeline_stages={pipe}"
    for a, b in ((8, 4), (16, 4), (16, 8), (32, 16)):
        acc = a + b + 16
        for pipe in (2, 5):
            yield f"a_width={a};b_width={b};out_width={acc};acc_width={acc};pipeline_stages={pipe}"


def _fp(pipes):
    for exp, mant in FP_FORMATS:
        for pipe in pipes:
            yield f"exp_bits={exp};mantissa_bits={mant};pipeline_stages={pipe}"


def _mxfpmac():
    for fmt in MX_STANDARD_FORMATS:
        for nb in (1, 2, 4):
            if _mx_ok(fmt, 32, nb):
                yield f"block_elems=32;num_blocks={nb};input_format={fmt}"
    for fmt in MX_STANDARD_FORMATS:
        for k in (8, 16, 64):
            if _mx_ok(fmt, k, 2):
                yield f"block_elems={k};num_blocks=2;input_format={fmt}"
    if _mx_ok("mxfp4_e2m1", 32, 8):
        yield "block_elems=32;num_blocks=8;input_format=mxfp4_e2m1"
    for nb in (1, 2):
        if _mx_ok("bf16", 32, nb):
            yield f"block_elems=32;num_blocks={nb};input_format=bf16"


def _regfile():
    for w in (8, 16, 32, 64):
        for d in (16, 32, 64, 128, 256):
            yield f"width={w};depth={d};num_read_ports=1;num_write_ports=1"
    for r, wr in ((2, 1), (2, 2), (4, 2), (4, 4)):
        for w, d in ((32, 64), (32, 128), (64, 64)):
            yield f"width={w};depth={d};num_read_ports={r};num_write_ports={wr}"
    yield "width=32;depth=512;num_read_ports=1;num_write_ports=1"
    yield "width=128;depth=64;num_read_ports=1;num_write_ports=1"


def _fifo():
    for w in (16, 32, 64, 128, 256):
        for d in (4, 8, 16, 32, 64, 128):
            yield f"width={w};depth={d}"
    yield "width=512;depth=8"
    yield "width=512;depth=16"


def _simplemux():
    for dw in (16, 32, 64, 128, 256):
        for n in (2, 4, 8, 16):
            if n * dw <= 2048:
                yield f"data_width={dw};num_inputs={n}"


def _crossbar():
    for dw in (32, 64, 128):
        for ni, no in ((2, 2), (4, 4), (8, 8), (16, 16), (8, 4), (16, 8), (4, 8)):
            if (ni + no) * dw <= 2560:
                yield f"data_width={dw};num_inputs={ni};num_outputs={no}"


def _fattree():
    for radix, levels in ((2, 2), (2, 3), (2, 4), (2, 5), (4, 2), (4, 3)):
        nodes = radix ** levels
        for dw in (32, 64, 128):
            if nodes * dw <= 2048:
                yield f"data_width={dw};radix={radix};num_levels={levels};oversubscription=1.0"
    for radix, levels, dw in ((4, 2, 32), (4, 2, 64), (2, 4, 32)):
        yield f"data_width={dw};radix={radix};num_levels={levels};oversubscription=0.5"


def _foldedclos():
    for tpl, leaves, spines in ((2, 2, 2), (4, 4, 2), (4, 4, 4), (8, 4, 4), (4, 8, 4), (8, 8, 4)):
        nodes = tpl * leaves
        for dw in (32, 64):
            if nodes * dw <= 2048:
                yield (
                    f"data_width={dw};terminals_per_leaf={tpl};num_leaves={leaves};"
                    f"num_spines={spines};oversubscription=1.0"
                )
    for tpl, leaves, spines, dw, osub in (
        (4, 4, 4, 32, 0.5),
        (8, 4, 4, 32, 0.5),
        (4, 4, 4, 32, 0.25),
        (4, 8, 4, 32, 0.5),
    ):
        yield (
            f"data_width={dw};terminals_per_leaf={tpl};num_leaves={leaves};"
            f"num_spines={spines};oversubscription={osub}"
        )


_GENERATORS = {
    "intadd": _intadd,
    "intmul": _intmul,
    "intmac": _intmac,
    "fpadd": lambda: _fp((2, 3, 5)),
    "fpmul": lambda: _fp((2, 3, 5)),
    "fpmac": lambda: _fp((2, 5)),
    "mxfpmac": _mxfpmac,
    "regfile": _regfile,
    "fifo": _fifo,
    "simplemux": _simplemux,
    "crossbar": _crossbar,
    "fattree": _fattree,
    "foldedclos": _foldedclos,
}

SWEEP_NODES = ("20", "16", "10", "7", "5")


def sweep_configs() -> list[tuple[str, str]]:
    """Every (rtl_name, arch_params) pair of the sweep, in a stable order."""
    configs: list[tuple[str, str]] = []
    for rtl_name, gen in _GENERATORS.items():
        for arch in gen():
            configs.append((rtl_name, arch))
    return configs


if __name__ == "__main__":
    per_module: dict[str, int] = {}
    for rtl_name, _ in sweep_configs():
        per_module[rtl_name] = per_module.get(rtl_name, 0) + 1
    for name, count in per_module.items():
        print(f"{name:12} {count}")
    print(f"{'total':12} {sum(per_module.values())}")
