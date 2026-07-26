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
    "fpadd", "fpmul", "fpmac", "mxfpmac", "fpsfu",
    "regfile", "fifo",
}

# Power-phase stimulus classes per module (+nw_power_mode; see
# activity_modes.md).  Each mode is one extra gate-level sim + one vectored
# PrimeTime run per job — syn/pnr/pex are shared.  "random" must stay first:
# it is the legacy full-random stimulus every module supports.  Modules not
# listed have no distinguishable operations (their operation IS random data)
# and run only "random".
POWER_MODES = {
    "regfile": ("random", "read", "write", "idle"),
    "fifo": ("random", "stream", "idle"),
    "intmac": ("random", "hold_b", "sparse50", "idle"),
    "fpmac": ("random", "hold_b", "sparse50", "idle"),
    "mxfpmac": ("random", "hold_scale", "sparse50", "idle"),
    # per-op-group stimulus: only that group's table + the shared PWL datapath
    # toggle. Modes for groups a variant disables are rejected by the TB.
    "fpsfu": ("random", "exp", "trig", "hyp", "erf", "idle"),
    "simplemux": ("random", "valid25"),
    "crossbar": ("random", "fixed_route", "valid25"),
    "fattree": ("random", "fixed_route"),
    "foldedclos": ("random", "fixed_route"),
}


def power_modes(rtl_name: str, arch_params: str = "") -> tuple[str, ...]:
    """Stimulus classes to measure for a module (always at least 'random').

    fpsfu's per-group modes apply only when the variant enables that op group
    (``arch_params`` carries the ``sfu_op_*`` flags) — the generated TB
    $fatal()s on a mode whose group is disabled, so the driver must not ask
    for it. Callers that have the job MUST pass its arch_params through.
    """
    modes = POWER_MODES.get(rtl_name, ("random",))
    if rtl_name != "fpsfu" or not arch_params:
        return modes
    flags: dict[str, str] = {}
    for item in arch_params.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            flags[key.strip()] = value.strip()
    keep = {"random", "idle"}
    for mode, flag in (("exp", "sfu_op_exp"), ("trig", "sfu_op_trig"),
                       ("hyp", "sfu_op_hyp"), ("erf", "sfu_op_erf")):
        if flags.get(flag, "0").lower() not in ("0", "", "false"):
            keep.add(mode)
    return tuple(m for m in modes if m in keep)

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


def _mxfpmac_bases():
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


# Pipelined variants added 2026-07-21: the base (no pipeline_stages token)
# configs keep their original arch_params strings so already-collected rows
# and run_ids stay valid; they are the legacy pipeline_stages=1 structure
# (fully combinational dot product + output register), whose achievable clock
# is bounded by the in2reg half-period budget. The explicit-stage variants
# add an input capture stage + tree-internal banks and reach the clock range
# the unpipelined design cannot.
MXFPMAC_PIPELINE_STAGES = (2, 4)


def _mxfpmac():
    for base in _mxfpmac_bases():
        yield base
    for base in _mxfpmac_bases():
        for ps in MXFPMAC_PIPELINE_STAGES:
            yield f"{base};pipeline_stages={ps}"


def _regfile():
    for w in (8, 16, 32, 64):
        for d in (1, 4, 8, 16, 32, 64, 128, 256):
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


# fpsfu op-group combos: each group alone (isolates its table/logic cost),
# all-on (+relu, ~free), and exp+hyp (the common NN activation pair).
_FPSFU_COMBOS = (
    {"sfu_op_exp": 1},
    {"sfu_op_trig": 1},
    {"sfu_op_hyp": 1},
    {"sfu_op_erf": 1},
    {"sfu_op_exp": 1, "sfu_op_trig": 1, "sfu_op_hyp": 1, "sfu_op_erf": 1,
     "sfu_op_relu": 1},
    {"sfu_op_exp": 1, "sfu_op_hyp": 1},
)
_FPSFU_FLAGS = ("sfu_op_exp", "sfu_op_trig", "sfu_op_hyp", "sfu_op_erf",
                "sfu_op_relu")


def _fpsfu():
    # ps range is [4, 10] (user decision 2026-07-24; real stage distribution
    # over 9 segments — see fpsfu.sv.j2). Endpoints + a middle point so the
    # timing MLP interpolates across the 2.5x span.
    for exp, mant in ((5, 10), (8, 7), (8, 23)):    # fp16, bf16, fp32
        for combo in _FPSFU_COMBOS:
            flags = ";".join(f"{f}={combo.get(f, 0)}" for f in _FPSFU_FLAGS)
            for segments in (64, 128):
                for pipe in (4, 7, 10):
                    yield (
                        f"exp_bits={exp};mantissa_bits={mant};"
                        f"sfu_segments={segments};{flags};"
                        f"pipeline_stages={pipe}"
                    )


_GENERATORS = {
    "intadd": _intadd,
    "intmul": _intmul,
    "intmac": _intmac,
    "fpadd": lambda: _fp((2, 3, 5)),
    "fpmul": lambda: _fp((2, 3, 5)),
    "fpmac": lambda: _fp((2, 5)),
    "fpsfu": _fpsfu,
    "mxfpmac": _mxfpmac,
    "regfile": _regfile,
    "fifo": _fifo,
    "simplemux": _simplemux,
    "crossbar": _crossbar,
    "fattree": _fattree,
    "foldedclos": _foldedclos,
}

SWEEP_NODES = ("20", "16", "10", "7", "5")

#: Modules whose generated RTL has NOT yet passed the user-run VCS smoke —
#: excluded from sweep_configs() by default so a production probe→gen-jobs→
#: sweep restart cannot silently pick up an unvalidated module. After the
#: fpsfu smoke passes (docs/DESIGN_SFU_DMA.md §2.5), remove it here and run
#: it as an incremental module add — never fold it into an in-flight sweep.
# Modules specced here but excluded from sweep_configs() until their RTL
# generation lands. fpsfu graduated 2026-07-23 (sfu_model.py + templates +
# gen_fpsfu complete and validated).
DEFERRED_MODULES: frozenset[str] = frozenset()


def sweep_configs(include_deferred: bool = False) -> list[tuple[str, str]]:
    """Every (rtl_name, arch_params) pair of the sweep, in a stable order."""
    configs: list[tuple[str, str]] = []
    for rtl_name, gen in _GENERATORS.items():
        if rtl_name in DEFERRED_MODULES and not include_deferred:
            continue
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
