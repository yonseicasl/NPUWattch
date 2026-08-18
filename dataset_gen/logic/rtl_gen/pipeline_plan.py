"""Register-bank placement for the generated arithmetic pipelines.

A deeper pipeline is only worth its flops if the *logic* is split. Appending
output delay banks raises latency and sequential area while leaving the
critical path untouched, and the sweep measured exactly that: until
2026-08-05 ``fpadd``/``fpmul``/``fpmac`` built ``PIPELINE_STAGES - 2`` output
shift-register banks, and ``pnr_crit_path_ns`` was flat across
``pipeline_stages`` at every node (5nm fpadd: 0.570 ns at ps 2, 3 and 5 alike;
``mxfpmac``, which distributes its banks, went 0.96 -> 0.59 ns from ps 2 to 4).
A timing MLP trained on that data learns "pipeline depth does not affect
crit_path", which then drags the harness f_max check for any deeply pipelined
FP unit.

This module turns a datapath described as an ordered list of combinational
segments, each carrying a relative delay weight, into a concrete set of
register cuts that balances the stages.

Contract (shared with fpsfu's hand-written cut ladder):

* a design with ``stages`` pipeline stages has ``stages`` register banks --
  one input capture, ``stages - 2`` internal cuts, one output register -- so
  its latency is ``stages`` cycles exactly;
* the ``stages - 1`` combinational blocks between those banks are contiguous
  groups of segments, hence ``stages <= len(weights) + 1``;
* placement minimises the heaviest group (that group sets the achievable
  clock period), and ties are broken towards the smallest spread, so a given
  (weights, stages) pair always yields the same plan.

The weights are a first-order structural delay proxy, not a characterisation
result: gate depth of the adders/shifters/encoders each segment synthesises
to. They only have to rank the segments correctly -- the exact clock period
still comes from the sweep. Refine them against measured ``pnr_crit_path_ns``
once the re-run lands rather than guessing further here.
"""

from __future__ import annotations

from itertools import combinations
from typing import Sequence


def clog2(value: int) -> int:
    """``ceil(log2(value))`` for positive ints, i.e. levels in a balanced tree."""
    if value < 1:
        raise ValueError("clog2 needs a positive value")
    return (value - 1).bit_length()


def max_stages(num_segments: int) -> int:
    """Deepest pipeline a datapath of ``num_segments`` segments supports.

    One comb block per segment plus the input capture and output banks; the
    generators clamp ``pipeline_stages`` to this.
    """
    if num_segments < 1:
        raise ValueError("need at least one segment")
    return num_segments + 1


def plan_cuts(weights: Sequence[int], stages: int) -> tuple[bool, ...]:
    """Where to put register cuts between ``weights``' segments.

    Returns one flag per internal boundary (``len(weights) - 1`` of them):
    ``cuts[k]`` is True when a register bank sits between segment ``k`` and
    segment ``k + 1``. Exactly ``stages - 2`` flags are True.
    """
    num_segments = len(weights)
    if num_segments < 1:
        raise ValueError("need at least one segment")
    if any(w <= 0 for w in weights):
        raise ValueError("segment weights must be positive")
    if stages < 2:
        raise ValueError("pipeline needs at least an input and an output bank")
    if stages > max_stages(num_segments):
        raise ValueError(
            f"{num_segments} segments support at most "
            f"{max_stages(num_segments)} stages, got {stages}"
        )

    num_groups = stages - 1
    boundaries = range(1, num_segments)
    best_choice: tuple[int, ...] | None = None
    best_score: tuple[int, int] | None = None
    # num_segments stays in the single digits, so enumerating every contiguous
    # partition is both exact and cheaper than reasoning about a DP recurrence.
    for choice in combinations(boundaries, num_groups - 1):
        groups = _group_weights(weights, choice)
        score = (max(groups), sum(g * g for g in groups))
        if best_score is None or score < best_score:
            best_score = score
            best_choice = choice
    assert best_choice is not None
    cut_at = set(best_choice)
    return tuple(k in cut_at for k in boundaries)


def stage_weights(weights: Sequence[int], cuts: Sequence[bool]) -> list[int]:
    """Per-stage combinational weight for a plan, heaviest one sets the clock."""
    if len(cuts) != len(weights) - 1:
        raise ValueError("one cut flag per internal boundary")
    choice = tuple(k + 1 for k, cut in enumerate(cuts) if cut)
    return _group_weights(weights, choice)


def _group_weights(weights: Sequence[int], choice: Sequence[int]) -> list[int]:
    groups: list[int] = []
    start = 0
    for stop in list(choice) + [len(weights)]:
        groups.append(sum(weights[start:stop]))
        start = stop
    return groups


def describe_plan(names: Sequence[str], weights: Sequence[int],
                  cuts: Sequence[bool]) -> str:
    """One-line-per-stage plan summary, emitted into the generated RTL header."""
    lines = []
    stage = 1
    current: list[str] = []
    for idx, name in enumerate(names):
        current.append(f"{name}({weights[idx]})")
        cut_here = idx < len(cuts) and cuts[idx]
        if cut_here or idx == len(names) - 1:
            total = sum(weights[i] for i in range(idx - len(current) + 1, idx + 1))
            lines.append(f"stage {stage}: " + " + ".join(current) + f" = {total}")
            stage += 1
            current = []
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-module segment tables. The names match the SEG<n> comments in the
# templates; keep the two in step when either changes.
# ---------------------------------------------------------------------------

FPADD_SEGMENTS = (
    "unpack",      # field split, class flags, effective exponents
    "compare",     # magnitude compare, exponent difference, large/small swap
    "align",       # barrel right shift of the small significand + sticky OR
    "addsub",      # significand add/sub
    "lzc",         # leading-zero count over the add result
    "expresolve",  # shift amount, subnormal test, pre-rounding exponent
    "normalize",   # barrel left shift + guard/round/sticky extraction
    "round",       # rounding increment, class mux, pack
)

FPMUL_SEGMENTS = (
    "unpack",      # field split, class flags, hidden bits, exponent sum
    "ppgen",       # significand partial products (hi/lo split operand)
    "ppadd",       # partial-product combine into the full product
    "lzc",         # leading-zero count over the product
    "normalize",   # normalizing shift + adjusted exponent
    "subshift",    # gradual-underflow right shift + lost-bit sticky
    "roundgrs",    # guard/round/sticky and the rounding increments
    "pack",        # class mux, saturation, pack
)


def fpadd_weights(exp_bits: int, mantissa_bits: int) -> tuple[int, ...]:
    """Relative delay of each :data:`FPADD_SEGMENTS` block."""
    width = exp_bits + mantissa_bits + 1
    shift_in = mantissa_bits + 4          # aligned significand width
    sum_width = mantissa_bits + 5         # add/sub result width
    return (
        3,                                # unpack: field slicing + reductions
        2 + clog2(width),                 # compare: |a| vs |b| over the fields
        2 * clog2(shift_in),              # align: shift levels + sticky tree
        2 + clog2(sum_width),             # addsub: carry-propagate adder
        2 * clog2(shift_in),              # lzc: priority encode
        2 + clog2(sum_width),             # expresolve: small subtract + mux
        2 + clog2(sum_width),             # normalize: shift levels + GRS mux
        3 + clog2(width),                 # round: increment + class mux
    )


def fpmac_stage_bounds(exp_bits: int, mantissa_bits: int) -> tuple[int, int]:
    """Legal ``pipeline_stages`` range for fpmac, whose latency is mul + add."""
    mul_max = max_stages(len(fpmul_weights(exp_bits, mantissa_bits)))
    add_max = max_stages(len(fpadd_weights(exp_bits, mantissa_bits)))
    return (4, mul_max + add_max)


def split_mac_stages(exp_bits: int, mantissa_bits: int,
                     stages: int) -> tuple[int, int]:
    """Split an fpmac latency budget into (fpmul stages, fpadd stages).

    The two units sit back to back, so the chain's clock is set by whichever
    of them ends up with the heavier stage; pick the split that minimises that
    maximum. Ties go to the smaller total, then to the deeper multiplier --
    the significand multiply is the wider tree, so giving it the spare stage
    ages better as the format grows.
    """
    mul_w = fpmul_weights(exp_bits, mantissa_bits)
    add_w = fpadd_weights(exp_bits, mantissa_bits)
    low, high = fpmac_stage_bounds(exp_bits, mantissa_bits)
    if stages < low or stages > high:
        raise ValueError(f"fpmac pipeline_stages must be in [{low}, {high}], got {stages}")

    best: tuple[tuple[int, int, int], tuple[int, int]] | None = None
    for mul_stages in range(2, max_stages(len(mul_w)) + 1):
        add_stages = stages - mul_stages
        if add_stages < 2 or add_stages > max_stages(len(add_w)):
            continue
        mul_peak = max(stage_weights(mul_w, plan_cuts(mul_w, mul_stages)))
        add_peak = max(stage_weights(add_w, plan_cuts(add_w, add_stages)))
        score = (max(mul_peak, add_peak), mul_peak + add_peak, -mul_stages)
        if best is None or score < best[0]:
            best = (score, (mul_stages, add_stages))
    assert best is not None
    return best[1]


def fpmul_weights(exp_bits: int, mantissa_bits: int) -> tuple[int, ...]:
    """Relative delay of each :data:`FPMUL_SEGMENTS` block.

    ``ppgen``/``ppadd`` model the significand multiplier after the exact hi/lo
    operand split the template applies: each half-width multiply is a tree over
    roughly half the multiplier bits, and the combine is one adder.
    """
    width = exp_bits + mantissa_bits + 1
    sig = mantissa_bits + 1               # significand width incl. hidden bit
    prod = 2 * mantissa_bits + 2          # full product width
    half = max(1, sig // 2)
    return (
        3,                                # unpack: field slicing + reductions
        2 + 2 * clog2(half),              # ppgen: two half-operand multiplies
        2 + clog2(prod),                  # ppadd: shifted-sum adder
        2 * clog2(prod),                  # lzc: priority encode
        2 + clog2(prod),                  # normalize: shift levels
        2 + clog2(prod),                  # subshift: shift levels + sticky
        3 + clog2(width),                 # roundgrs: sticky tree + increments
        3,                                # pack: class mux
    )
