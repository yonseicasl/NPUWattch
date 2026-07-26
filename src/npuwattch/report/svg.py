"""Inline-SVG chart generation for the HTML PPA report (manual §8).

Pure functions returning SVG strings — no I/O, no state — so tests can assert
on structure (element counts, summed percentages) rather than pixels. All
numbers are computed by the caller (`report/html.py`); these functions only
draw what they are handed.

Component→color assignment is stable across every chart in a report:
``color_for`` hashes the component name into a fixed palette, so the same
component is the same color in the energy donut, the area donut, and the bar
lists (skill guidance).
"""

from __future__ import annotations

import hashlib
import math
from typing import List, Mapping, Sequence, Tuple

__all__ = [
    "PALETTE", "color_for", "fmt_si",
    "dyn_leak_bar", "donut", "hbar_list", "windows_chart",
]

#: 12 chart colors, ordered for adjacent contrast on the report's light ground.
PALETTE = (
    "#C27200", "#118476", "#6E59B5", "#A5518E", "#2E6FA3", "#7A8B2F",
    "#B5484D", "#3A9A8F", "#8A6ED1", "#C1793A", "#4E7AC0", "#948C22",
)
_LEAK = "#8A97A0"
_INK = "#1c1c1c"
_MUTED = "#6b6b6b"
_GRID = "#e3e1dc"


def color_for(name: str) -> str:
    """Stable component color: hash of the name → palette index."""
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return PALETTE[h % len(PALETTE)]


def fmt_si(value: float, unit: str) -> str:
    """3-significant-figure value with an SI-scaled unit (pJ→nJ→µJ, mW→W)."""
    scales = {"pJ": (("µJ", 1e6), ("nJ", 1e3), ("pJ", 1.0)),
              "mW": (("W", 1e3), ("mW", 1.0))}
    for u, s in scales.get(unit, ((unit, 1.0),)):
        if abs(value) >= s or s == 1.0:
            return f"{value / s:.3g} {u}"
    return f"{value:.3g} {unit}"


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# dynamic-vs-leakage split bar
# ---------------------------------------------------------------------------

def dyn_leak_bar(dyn_pJ: float, leak_pJ: float, *, width: int = 560) -> str:
    """Two-segment stacked bar: dynamic vs leakage share of total energy."""
    total = dyn_pJ + leak_pJ
    frac = (dyn_pJ / total) if total > 0 else 0.0
    h, w_dyn = 20, frac * width
    return (
        f'<svg viewBox="0 0 {width} {h + 18}" role="img" '
        f'aria-label="dynamic vs leakage energy split">'
        f'<rect class="seg-dyn" x="0" y="0" width="{w_dyn:.1f}" height="{h}" '
        f'fill="#3b6ea5"><title>dynamic {fmt_si(dyn_pJ, "pJ")} '
        f'({100 * frac:.1f}%)</title></rect>'
        f'<rect class="seg-leak" x="{w_dyn:.1f}" y="0" '
        f'width="{width - w_dyn:.1f}" height="{h}" fill="{_LEAK}">'
        f'<title>leakage {fmt_si(leak_pJ, "pJ")} '
        f'({100 * (1 - frac):.1f}%)</title></rect>'
        f'<text x="0" y="{h + 13}" font-size="11" fill="{_MUTED}">'
        f'dynamic {100 * frac:.1f}%</text>'
        f'<text x="{width}" y="{h + 13}" font-size="11" fill="{_MUTED}" '
        f'text-anchor="end">leakage {100 * (1 - frac):.1f}%</text></svg>'
    )


# ---------------------------------------------------------------------------
# donut (per-component share)
# ---------------------------------------------------------------------------

def donut(items: Sequence[Tuple[str, float]], *, unit: str = "pJ",
          size: int = 200) -> str:
    """Donut of (label, value) shares. The caller passes already-grouped items
    (top-N + "other"); values must be non-negative. Center shows the total."""
    total = sum(v for _, v in items)
    cx = cy = size / 2
    r, ring = size * 0.40, size * 0.16
    parts: List[str] = []
    angle = -90.0                                     # start at 12 o'clock
    for label, value in items:
        if total <= 0 or value <= 0:
            continue
        sweep = 360.0 * value / total
        a0, a1 = math.radians(angle), math.radians(angle + min(sweep, 359.99))
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        large = 1 if sweep > 180 else 0
        color = _LEAK if label == "other" else color_for(label)
        parts.append(
            f'<path class="slice" d="M {x0:.2f} {y0:.2f} '
            f'A {r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="{ring:.1f}">'
            f'<title>{_esc(label)}: {fmt_si(value, unit)} '
            f'({100 * value / total:.1f}%)</title></path>')
        angle += sweep
    center = fmt_si(total, unit) if total > 0 else "n/a"
    return (
        f'<svg viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="per-component breakdown donut" '
        f'style="max-width:{size}px">'
        + "".join(parts) +
        f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="14" '
        f'font-weight="600" fill="{_INK}">{center}</text></svg>'
    )


# ---------------------------------------------------------------------------
# horizontal bar list (per-component share)
# ---------------------------------------------------------------------------

def hbar_list(items: Sequence[Tuple[str, float]], *, unit: str = "pJ",
              width: int = 560) -> str:
    """One row per (label, value): swatch, name, bar ∝ value, value + share."""
    total = sum(v for _, v in items) or 1.0
    vmax = max((v for _, v in items), default=1.0) or 1.0
    row_h, bar_x, bar_w = 22, 190, width - 190 - 120
    rows: List[str] = []
    for i, (label, value) in enumerate(items):
        y = i * row_h
        color = _LEAK if label == "other" else color_for(label)
        w = max(1.5, bar_w * value / vmax) if value > 0 else 0
        rows.append(
            f'<g class="bar-row">'
            f'<rect x="0" y="{y + 5}" width="10" height="10" fill="{color}"/>'
            f'<text x="16" y="{y + 14}" font-size="11" fill="{_INK}">'
            f'{_esc(label[:26])}</text>'
            f'<rect x="{bar_x}" y="{y + 4}" width="{w:.1f}" height="12" '
            f'fill="{color}" opacity="0.85"/>'
            f'<text x="{width}" y="{y + 14}" font-size="11" fill="{_MUTED}" '
            f'text-anchor="end">{fmt_si(value, unit)} · '
            f'{100 * value / total:.1f}%</text></g>')
    h = len(items) * row_h
    return (f'<svg viewBox="0 0 {width} {h}" role="img" '
            f'aria-label="per-component bar list">' + "".join(rows) + "</svg>")


# ---------------------------------------------------------------------------
# cycle-level chart (§8.5): windowed energy bars + average-power line
# ---------------------------------------------------------------------------

def windows_chart(windows: Sequence[Mapping], *, width: int = 960,
                  height: int = 280) -> str:
    """E(w) bars over a true cycle axis (bar width ∝ window cycles; dynamic
    stacked under leakage) with the per-window average-power line overlaid on
    a right-hand axis. ``windows`` rows need: label, cycles, dyn_pJ, leak_pJ,
    total_pJ, avg_power_mW."""
    if not windows:
        return ""
    L, R, T, B = 72, 76, 14, 44
    plot_w, plot_h = width - L - R, height - T - B
    total_cycles = sum(w["cycles"] for w in windows) or 1
    e_max = max(w["total_pJ"] for w in windows) * 1.1 or 1.0
    p_max = max(w["avg_power_mW"] for w in windows) * 1.25 or 1.0
    y_e = lambda v: T + plot_h * (1 - v / e_max)
    y_p = lambda v: T + plot_h * (1 - v / p_max)

    parts: List[str] = []
    for i in range(5):                                # energy grid + ticks
        v = e_max * i / 4
        parts.append(
            f'<line x1="{L}" x2="{width - R}" y1="{y_e(v):.1f}" '
            f'y2="{y_e(v):.1f}" stroke="{_GRID}"/>'
            f'<text x="{L - 8}" y="{y_e(v) + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="{_MUTED}">{fmt_si(v, "pJ")}</text>')
        pv = p_max * i / 4                            # power ticks (right)
        parts.append(
            f'<text x="{width - R + 8}" y="{y_p(pv) + 4:.1f}" font-size="10" '
            f'fill="#2E6FA3">{fmt_si(pv, "mW")}</text>')

    x = float(L)
    line_pts: List[str] = []
    gap = 3.0
    for w in windows:
        seg_w = max(2.0, plot_w * w["cycles"] / total_cycles - gap)
        yd, yt = y_e(w["dyn_pJ"]), y_e(w["total_pJ"])
        parts.append(                                  # dynamic
            f'<rect class="w-dyn" x="{x:.1f}" y="{yd:.1f}" width="{seg_w:.1f}" '
            f'height="{T + plot_h - yd:.1f}" fill="#3b6ea5">'
            f'<title>{_esc(w["label"])}: dynamic '
            f'{fmt_si(w["dyn_pJ"], "pJ")}</title></rect>')
        parts.append(                                  # leakage on top
            f'<rect class="w-leak" x="{x:.1f}" y="{yt:.1f}" width="{seg_w:.1f}" '
            f'height="{yd - yt:.1f}" fill="{_LEAK}" opacity="0.6">'
            f'<title>{_esc(w["label"])}: leakage '
            f'{fmt_si(w["leak_pJ"], "pJ")}</title></rect>')
        parts.append(
            f'<text x="{x + seg_w / 2:.1f}" y="{T + plot_h + 15}" '
            f'text-anchor="middle" font-size="10" fill="{_MUTED}">'
            f'{_esc(str(w["label"])[:8])}</text>'
            f'<text x="{x + seg_w / 2:.1f}" y="{T + plot_h + 28}" '
            f'text-anchor="middle" font-size="9" fill="{_MUTED}" opacity="0.8">'
            f'{w["cycles"]} cyc</text>')
        line_pts.append(f'{x + seg_w / 2:.1f},{y_p(w["avg_power_mW"]):.1f}')
        x += seg_w + gap

    parts.append(                                      # avg-power overlay
        f'<polyline class="p-line" points="{" ".join(line_pts)}" fill="none" '
        f'stroke="#2E6FA3" stroke-width="2"/>')
    for pt in line_pts:
        px, py = pt.split(",")
        parts.append(f'<circle cx="{px}" cy="{py}" r="3" fill="#2E6FA3"/>')
    parts.append(
        f'<line x1="{L}" x2="{width - R}" y1="{T + plot_h}" y2="{T + plot_h}" '
        f'stroke="{_MUTED}"/>'
        f'<text x="{L}" y="{height - 2}" font-size="10" fill="{_MUTED}">'
        f'bars: window energy (dyn + leak) · line: average power · '
        f'bar width ∝ cycles</text>')
    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="energy and power per kernel window over cycles">'
            + "".join(parts) + "</svg>")
