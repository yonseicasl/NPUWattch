"""Bit-exact software model of the fpsfu primitive (PWL transcendental unit).

This file is the SINGLE SOURCE of the fpsfu's numeric behavior: it generates
the piecewise-linear coefficient tables embedded in the RTL *and* evaluates the
exact fixed-point algorithm the RTL implements, so the generated testbench's
expected outputs are bit-exact by construction (same convention as the other
generated primitives; see docs/DESIGN_SFU_DMA.md §2).

Numeric contract (documented here and in the RTL header):

* Input decode: fp(E,M) → sign + unsigned fixed-point magnitude X in
  Q(XI.XF), XI=5 integer bits, XF=M+3 fraction bits, TRUNCATED toward zero.
  Subnormals flush to zero; NaN/Inf saturate to the maximum magnitude (the
  unit is a total function — no NaN propagation, stated in the RTL header).
* Every op maps its argument onto a table domain u ∈ [0,1) with one shared
  constant multiply t = (X·K) >> XF, then evaluates y by linear interpolation
  between S+1 quantized nodes of the op's function: seg = u >> DF,
  d = u & (2^DF−1), y = A[seg] + (B[seg]·d >> DF), where A[i] = node i and
  B[i] = node[i+1] − node[i] ≥ 0 (every table is monotone increasing, so the
  interpolation datapath is unsigned end to end). All shifts TRUNCATE.
* Outputs pack with TRUNCATED mantissas (no RNE — the PWL approximation error
  dominates rounding; deviation from the RNE arithmetic primitives is
  deliberate and documented). Exponent overflow saturates to the largest
  finite value; exponent underflow flushes to zero.

Op groups (elaboration-time enables, paired by shared structure):
  exp  : exp (t = x·log2e), exp2 (t = x) — 2^u table, y ∈ [1,2), result 2^n·y
  trig : sin, cos — quarter-wave sin(π/2·u) table, quadrant fold, cos = +1 quadrant
  hyp  : tanh, sigmoid — σ(16u−8) table; tanh(x) = 2σ(2x)−1, magnitude domain
  erf  : erf — erf(4u) table, magnitude domain, odd symmetry
  relu : relu — sign mux only (no table)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

XI = 5          # integer bits of the internal fixed-point magnitude
GUARD = 3       # fraction bits beyond the mantissa (XF = M + GUARD)

# Op codes (3 bits, format-independent; RTL mirrors these localparams).
OPS = {
    "exp": 0, "exp2": 1, "sin": 2, "cos": 3,
    "tanh": 4, "sigmoid": 5, "erf": 6, "relu": 7,
}
GROUP_OF = {
    "exp": "exp", "exp2": "exp", "sin": "trig", "cos": "trig",
    "tanh": "hyp", "sigmoid": "hyp", "erf": "erf", "relu": "relu",
}
GROUP_OPS = {
    "exp": ("exp", "exp2"), "trig": ("sin", "cos"),
    "hyp": ("tanh", "sigmoid"), "erf": ("erf",), "relu": ("relu",),
}


@dataclass(frozen=True)
class SfuSpec:
    exp_bits: int
    mantissa_bits: int
    segments: int
    op_exp: bool = False
    op_trig: bool = False
    op_hyp: bool = False
    op_erf: bool = False
    op_relu: bool = False

    def __post_init__(self) -> None:
        if self.exp_bits < 3:
            raise ValueError("exp_bits must be >= 3")
        if self.mantissa_bits < 2:
            raise ValueError("mantissa_bits must be >= 2")
        if self.segments < 16 or self.segments & (self.segments - 1):
            raise ValueError("segments must be a power of two >= 16")
        if self.seg_bits >= self.xf:
            raise ValueError(
                f"segments={self.segments} needs mantissa_bits > "
                f"{self.seg_bits - GUARD} (interpolation fraction would vanish)"
            )
        if not (self.op_exp or self.op_trig or self.op_hyp
                or self.op_erf or self.op_relu):
            raise ValueError("at least one op group must be enabled")

    # --- derived widths (shared with the RTL template) ---------------------
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
    def xf(self) -> int:                    # internal fraction bits
        return self.mantissa_bits + GUARD

    @property
    def xw(self) -> int:                    # X magnitude width, Q(XI.XF)
        return XI + self.xf

    @property
    def xmax(self) -> int:
        return (1 << self.xw) - 1

    @property
    def one(self) -> int:                   # 1.0 in the u domain
        return 1 << self.xf

    @property
    def one_q(self) -> int:                 # 1.0 in the y domain, Q1.(M+3)
        return 1 << (self.mantissa_bits + GUARD)

    @property
    def seg_bits(self) -> int:
        return self.segments.bit_length() - 1

    @property
    def df(self) -> int:                    # interpolation fraction bits
        return self.xf - self.seg_bits

    @property
    def kw(self) -> int:                    # premultiply constant width
        return self.xf + 2

    @property
    def aw(self) -> int:                    # table node width (2^u needs 2.0)
        return self.mantissa_bits + GUARD + 2

    @property
    def enabled_groups(self) -> tuple[str, ...]:
        out = []
        for g, flag in (("exp", self.op_exp), ("trig", self.op_trig),
                        ("hyp", self.op_hyp), ("erf", self.op_erf),
                        ("relu", self.op_relu)):
            if flag:
                out.append(g)
        return tuple(out)

    @property
    def enabled_ops(self) -> tuple[str, ...]:
        return tuple(op for g in self.enabled_groups for op in GROUP_OPS[g])

    # --- premultiply constants (K in Q2.XF, truncated products) ------------
    @property
    def k_exp(self) -> int:                 # log2(e)
        return round(math.log2(math.e) * self.one)

    @property
    def k_exp2(self) -> int:                # exact 1.0
        return self.one

    @property
    def k_trig(self) -> int:                # 2/π: quarter periods
        return round((2.0 / math.pi) * self.one)

    @property
    def k_hyp(self) -> int:                 # 1/16: window x∈[−8,8) → u∈[0,1)
        return self.one >> 4

    @property
    def k_erf(self) -> int:                 # 1/4: window |x|∈[0,4) → u∈[0,1)
        return self.one >> 2


# ---------------------------------------------------------------------------
# tables — S+1 nodes per group function, quantized to Q1.(M+GUARD)
# ---------------------------------------------------------------------------

def _nodes(spec: SfuSpec, f) -> list[int]:
    vals = []
    for i in range(spec.segments + 1):
        v = f(i / spec.segments)
        q = round(v * spec.one_q)
        vals.append(q)
    for lo, hi in zip(vals, vals[1:]):
        if hi < lo:
            raise AssertionError("table nodes must be monotone increasing")
    return vals


@lru_cache(maxsize=None)
def tables(spec: SfuSpec) -> dict[str, tuple[list[int], list[int]]]:
    """Per enabled group: (A nodes[0..S-1], B diffs[0..S-1]) plus the end node
    under key ``<group>_end`` (the u→1 closure value)."""
    funcs = {
        "exp": lambda u: 2.0 ** u,                      # y ∈ [1,2]
        "trig": lambda u: math.sin(math.pi / 2 * u),    # y ∈ [0,1]
        "hyp": lambda u: 1.0 / (1.0 + math.exp(-(16.0 * u - 8.0))),
        "erf": lambda u: math.erf(4.0 * u),             # y ∈ [0,~1]
    }
    out: dict[str, tuple[list[int], list[int]]] = {}
    for group in spec.enabled_groups:
        if group == "relu":
            continue
        nodes = _nodes(spec, funcs[group])
        a = nodes[:-1]
        b = [hi - lo for lo, hi in zip(nodes, nodes[1:])]
        out[group] = (a, b)
        out[group + "_end"] = nodes[-1]                 # type: ignore[assignment]
    return out


# ---------------------------------------------------------------------------
# bit-exact evaluation (the RTL algorithm, in integers)
# ---------------------------------------------------------------------------

def _decode(spec: SfuSpec, bits: int) -> tuple[int, int]:
    """fp bits → (sign, X magnitude Q(XI.XF)); FTZ subnormals, NaN/Inf → max."""
    sign = (bits >> (spec.width - 1)) & 1
    e = (bits >> spec.mantissa_bits) & spec.exp_max
    frac = bits & ((1 << spec.mantissa_bits) - 1)
    if e == spec.exp_max:                               # NaN / Inf: saturate
        return sign, spec.xmax
    if e == 0:                                          # zero / subnormal: FTZ
        return sign, 0
    sig = (1 << spec.mantissa_bits) | frac              # 1.f, Q1.M
    shift = e - spec.bias + GUARD                       # to Q(XI.XF)
    x = sig << shift if shift >= 0 else sig >> (-shift)
    return sign, min(x, spec.xmax)


def _interp(spec: SfuSpec, group: str, u: int) -> int:
    """Linear interpolation on the group table at u ∈ [0, ONE]."""
    tab = tables(spec)
    if u >= spec.one:                                   # closed right end
        return tab[group + "_end"]                      # type: ignore[return-value]
    a, b = tab[group]
    seg = u >> spec.df
    d = u & ((1 << spec.df) - 1)
    return a[seg] + ((b[seg] * d) >> spec.df)


def _pack(spec: SfuSpec, sign: int, y: int) -> int:
    """y in Q1.(M+GUARD), value ∈ [0, 2) → fp bits (truncate, FTZ, saturate)."""
    if y <= 0:
        return sign << (spec.width - 1)
    p = y.bit_length() - 1                              # msb position
    e_field = spec.bias + p - (spec.mantissa_bits + GUARD)
    if e_field <= 0:                                    # underflow: FTZ
        return sign << (spec.width - 1)
    if e_field >= spec.exp_max:                         # overflow: max finite
        return ((sign << (spec.width - 1))
                | ((spec.exp_max - 1) << spec.mantissa_bits)
                | ((1 << spec.mantissa_bits) - 1))
    norm = y << ((spec.mantissa_bits + GUARD) - p)
    mant = (norm & (spec.one_q - 1)) >> GUARD           # truncate
    return (sign << (spec.width - 1)) | (e_field << spec.mantissa_bits) | mant


def evaluate(spec: SfuSpec, op: str, bits: int) -> int:
    """Bit-exact fpsfu output for one input. ``op`` must be enabled."""
    if op not in spec.enabled_ops:
        raise ValueError(f"op {op!r} not enabled in this spec")
    sign, x = _decode(spec, bits)

    if op == "relu":                                    # sign mux only
        return 0 if sign else bits

    if op in ("exp", "exp2"):
        k = spec.k_exp if op == "exp" else spec.k_exp2
        t = (x * k) >> spec.xf
        tt = -t if sign else t
        n = tt >> spec.xf                               # floor (python >> floors)
        u = tt - (n << spec.xf)
        y = _interp(spec, "exp", u)                     # y ∈ [1,2) in Q1.(M+3)
        p = y.bit_length() - 1                          # M+3 (or M+4 at 2.0 edge)
        e_field = spec.bias + n + (p - (spec.mantissa_bits + GUARD))
        if e_field >= spec.exp_max:
            return ((spec.exp_max - 1) << spec.mantissa_bits) | (
                (1 << spec.mantissa_bits) - 1)          # +max finite
        if e_field <= 0:
            return 0                                    # FTZ
        norm = y << ((spec.mantissa_bits + GUARD) - p)
        mant = (norm & (spec.one_q - 1)) >> GUARD
        return (e_field << spec.mantissa_bits) | mant   # always positive

    if op in ("sin", "cos"):
        t = (x * spec.k_trig) >> spec.xf                # quarter periods
        qn = t >> spec.xf
        u = t & (spec.one - 1)
        q = (qn + (1 if op == "cos" else 0)) & 3
        flip = q & 1
        neg = (q >> 1) & 1
        v = spec.one - u if flip else u
        y = _interp(spec, "trig", v)
        out_sign = neg ^ (sign if op == "sin" else 0)
        return _pack(spec, out_sign, y)

    if op in ("tanh", "sigmoid"):
        xin = min(x << 1, spec.xmax) if op == "tanh" else x
        t = (xin * spec.k_hyp) >> spec.xf
        half = spec.one >> 1
        u = min(half + t, spec.one - 1)                 # clamp = saturate tails
        y = _interp(spec, "hyp", u)                     # σ(|arg|) ≥ 0.5
        if op == "tanh":
            return _pack(spec, sign, (y << 1) - spec.one_q)
        if sign:                                        # σ(−x) = 1 − σ(x)
            return _pack(spec, 0, spec.one_q - y)
        return _pack(spec, 0, y)

    # erf
    t = (x * spec.k_erf) >> spec.xf
    u = min(t, spec.one - 1)
    y = _interp(spec, "erf", u)
    return _pack(spec, sign, y)


# ---------------------------------------------------------------------------
# reference check (informational — PWL accuracy vs libm)
# ---------------------------------------------------------------------------

_REF = {
    "exp": math.exp, "exp2": lambda x: 2.0 ** x, "sin": math.sin,
    "cos": math.cos, "tanh": math.tanh,
    "sigmoid": lambda x: 1.0 / (1.0 + math.exp(-x)), "erf": math.erf,
    "relu": lambda x: max(x, 0.0),
}

# Windows inside which the PWL evaluation is meaningful (beyond them the op
# saturates by design). exp windows keep the *result* within reference range.
_CHECK_WINDOW = {
    "exp": (-8.0, 8.0), "exp2": (-8.0, 8.0), "sin": (-6.0, 6.0),
    "cos": (-6.0, 6.0), "tanh": (-6.0, 6.0), "sigmoid": (-7.0, 7.0),
    "erf": (-3.5, 3.5), "relu": (-8.0, 8.0),
}


def _to_float(spec: SfuSpec, bits: int) -> float:
    sign = -1.0 if (bits >> (spec.width - 1)) & 1 else 1.0
    e = (bits >> spec.mantissa_bits) & spec.exp_max
    frac = bits & ((1 << spec.mantissa_bits) - 1)
    if e == spec.exp_max:
        return sign * (math.inf if frac == 0 else math.nan)
    if e == 0:
        return sign * frac * 2.0 ** (1 - spec.bias - spec.mantissa_bits)
    return sign * (1 + frac * 2.0 ** -spec.mantissa_bits) * 2.0 ** (e - spec.bias)


def _from_float(spec: SfuSpec, v: float) -> int:
    """Nearest-even encode (test-input generation only, not part of the HW)."""
    if math.isnan(v) or math.isinf(v):
        raise ValueError("finite inputs only")
    sign = 1 if math.copysign(1.0, v) < 0 else 0
    m = abs(v)
    if m == 0.0:
        return sign << (spec.width - 1)
    e_unb = math.floor(math.log2(m))
    if m / 2.0 ** e_unb >= 2.0:
        e_unb += 1
    e_field = e_unb + spec.bias
    if e_field <= 0:
        return sign << (spec.width - 1)                 # FTZ inputs
    if e_field >= spec.exp_max:
        e_field, mant = spec.exp_max - 1, (1 << spec.mantissa_bits) - 1
        return (sign << (spec.width - 1)) | (e_field << spec.mantissa_bits) | mant
    mant = round((m / 2.0 ** e_unb - 1.0) * (1 << spec.mantissa_bits))
    if mant == 1 << spec.mantissa_bits:
        e_field += 1
        mant = 0
        if e_field >= spec.exp_max:
            e_field, mant = spec.exp_max - 1, (1 << spec.mantissa_bits) - 1
    return (sign << (spec.width - 1)) | (e_field << spec.mantissa_bits) | mant


def max_errors(spec: SfuSpec, points: int = 2000) -> dict[str, float]:
    """Max |model−libm| relative error (vs max(|ref|, 2^-4)) per enabled op,
    sampled uniformly over each op's check window. Informational."""
    out: dict[str, float] = {}
    for op in spec.enabled_ops:
        lo, hi = _CHECK_WINDOW[op]
        worst = 0.0
        for i in range(points):
            xv = lo + (hi - lo) * i / (points - 1)
            bits = _from_float(spec, xv)
            got = _to_float(spec, evaluate(spec, op, bits))
            ref = _REF[op](_to_float(spec, bits))
            err = abs(got - ref) / max(abs(ref), 2.0 ** -4)
            worst = max(worst, err)
        out[op] = worst
    return out


# ---------------------------------------------------------------------------
# emitters for the jinja templates
# ---------------------------------------------------------------------------

def emit_tables(spec: SfuSpec) -> dict[str, object]:
    """SV literal strings for each enabled group's A/B tables + end nodes."""
    ctx: dict[str, object] = {}
    tab = tables(spec)
    for group in ("exp", "trig", "hyp", "erf"):
        if group not in tab:
            continue
        a, b = tab[group]
        ctx[f"{group}_a"] = [f"{spec.aw}'d{v}" for v in a]
        ctx[f"{group}_b"] = [f"{spec.aw}'d{v}" for v in b]
        ctx[f"{group}_end"] = f"{spec.aw}'d{tab[group + '_end']}"
    return ctx


def _rand_bits(spec: SfuSpec, state: int) -> tuple[int, int]:
    """Deterministic LCG so vectors are reproducible without importing random."""
    state = (state * 6364136223846793005 + 1442695040888963407) & (2**64 - 1)
    return state >> (64 - spec.width) if spec.width <= 64 else state, state


def emit_fpsfu_vectors(spec: SfuSpec) -> list[dict[str, object]]:
    """Directed + deterministic-random cases per enabled op, model-expected."""
    directed = ["0.0", "-0.0", "1.0", "-1.0", "0.5", "-0.5", "2.75", "-3.25",
                "0.0625", "100.0", "-100.0"]
    special = [
        (spec.exp_max << spec.mantissa_bits, "+inf"),
        ((1 << (spec.width - 1)) | (spec.exp_max << spec.mantissa_bits), "-inf"),
        ((spec.exp_max << spec.mantissa_bits) | 1, "nan"),
        (1, "min-subnormal (FTZ)"),
    ]
    rows: list[dict[str, object]] = []
    idx = 0
    state = 42
    digits = (spec.width + 3) // 4
    for op in spec.enabled_ops:
        cases: list[tuple[int, str]] = []
        for text in directed:
            cases.append((_from_float(spec, float(text)), text))
        cases.extend(special)
        for _ in range(6):
            bits, state = _rand_bits(spec, state)
            bits &= (1 << spec.width) - 1
            cases.append((bits, "random"))
        for bits, desc in cases:
            rows.append({
                "index": idx,
                "op": op,
                "op_code": OPS[op],
                "desc": f"{op}({desc})",
                "in_hex": f"{bits:0{digits}x}",
                "expected_hex": f"{evaluate(spec, op, bits):0{digits}x}",
            })
            idx += 1
    return rows


if __name__ == "__main__":
    for e, m in ((5, 10), (8, 7), (8, 23)):
        spec = SfuSpec(exp_bits=e, mantissa_bits=m, segments=64,
                       op_exp=True, op_trig=True, op_hyp=True, op_erf=True,
                       op_relu=True)
        errs = max_errors(spec)
        line = ", ".join(f"{op}={v:.2e}" for op, v in errs.items())
        print(f"e{e}m{m} S=64 max rel err: {line}")
