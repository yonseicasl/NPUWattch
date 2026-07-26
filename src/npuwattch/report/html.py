"""HTML/JSON PPA report generation (manual §8, workstream R1).

``build_context`` turns a §6 ``RunEnergy`` (+ the native description and run
provenance) into one plain-data context dict; ``render_html`` pushes it through
the Jinja2 template; ``write_report`` writes ``report.html`` and, from the very
same context, ``report.json`` (§3.6) — HTML and JSON can never disagree.

Everything numeric is computed here (shares, unit costs, f_max check); the
template only formats. Charts are inline SVG strings from ``report.svg``,
stored under the context's ``svg`` key, which is the one key stripped from
``report.json`` (§3.6 lists data, not markup).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .svg import (
    donut,
    dyn_leak_bar,
    fmt_si,
    hbar_list,
    windows_chart,
)

__all__ = ["build_context", "render_html", "write_report"]

_TOP_N = 8                     # donut / bar-list grouping (skill guidance)
_MEM_PRIMS = ("sram", "regfile", "fifo")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _fmt_or_na(value: float, pattern: str = "{:.3g}") -> str:
    return pattern.format(value) if value else "n/a"


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _top_n(items: Sequence[Tuple[str, float]], n: int = _TOP_N):
    """Largest-n (label, value) pairs plus an aggregated ("other", rest)."""
    ranked = sorted((i for i in items if i[1] > 0),
                    key=lambda kv: kv[1], reverse=True)
    head, tail = ranked[:n], ranked[n:]
    if tail:
        head.append(("other", sum(v for _, v in tail)))
    return head


def _model_of(primitive: str, chain: Any) -> str:
    if primitive in tuple(getattr(chain, "calibrated_primitives", ()) or ()):
        return "cal"
    if primitive in tuple(getattr(chain, "constant_primitives", ()) or ()):
        return "const"
    return "stub"


def _model_tag(models: Iterable[str]) -> str:
    """The summary calibration tag, same semantics as the CLI's."""
    kinds = set(models)
    if kinds == {"cal"}:
        return "calibrated"
    if kinds <= {"stub"}:
        return "FIRST-ORDER (uncalibrated placeholder)"
    return "PARTIAL calibration"


def _unit_energy_str(provider: Any, primitive: str, feats: Dict[str, Any]) -> str:
    """E/op for logic and links, E/rd·wr for memories — per single instance."""
    def one(mode: str) -> Optional[float]:
        try:
            return provider.energy_per_cycle(primitive, {**feats, "stim_mode": mode})
        except Exception:
            return None
    if primitive in _MEM_PRIMS:
        rd, wr = one("read"), one("write")
        if rd is None and wr is None:
            return "n/a"
        return (f"{rd:.3g} / {wr:.3g}"
                if rd is not None and wr is not None
                else f"{(rd if rd is not None else wr):.3g}")
    op = one("random")
    return f"{op:.3g}" if op is not None else "n/a"


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def build_context(
    run: Any,                                   # energy.RunEnergy
    description: Mapping[str, Any],             # native §3.1 dict
    *,
    tech: Any,                                  # energy.TechContext
    design_name: str,
    activity_source: str,
    chain: Any = None,                          # provider_factory.ProviderChain
    hierarchy: Any = None,                      # report.tree.ArchTreeNode
    warnings: Sequence[str] = (),
    notes: Sequence[str] = (),                  # declared exclusions (INFO tier)
    activity_rows: Sequence[Mapping[str, Any]] = (),
    inputs: Sequence[Tuple[str, Optional[Path]]] = (),
    vectorless: Optional[float] = None,         # activity fraction when defaulted
) -> Dict[str, Any]:
    """One plain-data dict driving both ``report.html`` and ``report.json``."""
    from .tree import to_dict as tree_to_dict

    nw = description.get("npuwattch", {})
    clock = float((nw.get("clock") or {}).get("frequency_MHz") or 0.0)
    attrs_by_name = {c["name"]: (c.get("attributes") or {})
                     for c in nw.get("components", [])}
    provider = getattr(chain, "provider", None)

    if not run.windows:
        raise ValueError("report: RunEnergy has no windows to report")
    comp0 = run.windows[0].components
    total_pJ = run.total_energy_pJ or 1.0

    # -- per-component accumulation (identity per physical instance) ---------
    activity_by_comp: Dict[str, float] = {}
    for r in activity_rows:
        name = str(r.get("component", ""))
        if name and name != "__meta__":
            activity_by_comp[name] = activity_by_comp.get(name, 0.0) + float(r.get("count", 0))

    components: List[Dict[str, Any]] = []
    for name, c0 in comp0.items():
        dyn = sum(w.components[name].dyn_energy_pJ for w in run.windows)
        leak = sum(w.components[name].leak_energy_pJ for w in run.windows)
        feats: Dict[str, Any] = dict(tech.features())
        feats.update(attrs_by_name.get(name, {}))
        components.append({
            "name": name,
            "cls": c0.primitive,
            "model": _model_of(c0.primitive, chain),
            "count": c0.instances,
            "dyn_energy_pJ": dyn,
            "dyn_str": fmt_si(dyn, "pJ") if dyn else "—",
            "leak_energy_pJ": leak,
            "leak_str": fmt_si(leak, "pJ"),
            "energy_pJ": dyn + leak,
            "energy_str": fmt_si(dyn + leak, "pJ"),
            "energy_pct": round(100.0 * (dyn + leak) / total_pJ, 1),
            "unit_energy_str": (_unit_energy_str(provider, c0.primitive, feats)
                                if provider is not None else "n/a"),
            # unit costs are per single instance (§8.6); the *_mW/_um2 raw
            # fields keep the whole-component totals (× count) for §3.6.
            "leak_power_mW": c0.leak_power_mW,
            "unit_leak_power_mW": c0.leak_power_mW / max(1, c0.instances),
            "leak_power_str": _fmt_or_na(c0.leak_power_mW / max(1, c0.instances)),
            "area_um2": c0.area_um2,
            "unit_area_um2": c0.area_um2 / max(1, c0.instances),
            "area_str": _fmt_or_na(c0.area_um2 / max(1, c0.instances)),
            "crit_path_ns": c0.crit_path_ns,
            "crit_path_str": _fmt_or_na(c0.crit_path_ns),
            "activity_events": activity_by_comp.get(name, 0.0),
            "activity_str": _fmt_or_na(activity_by_comp.get(name, 0.0)),
            "vectorless": vectorless is not None,
            "user_defined": False,
        })

    # -- windows + component × window matrix ---------------------------------
    windows = [{
        "index": i,
        "label": w.kernel_hash,
        "cycles": w.exec_cycles,
        "dyn_pJ": w.dyn_energy_pJ, "dyn_str": fmt_si(w.dyn_energy_pJ, "pJ"),
        "leak_pJ": w.leak_energy_pJ, "leak_str": fmt_si(w.leak_energy_pJ, "pJ"),
        "total_pJ": w.total_energy_pJ, "total_str": fmt_si(w.total_energy_pJ, "pJ"),
        "avg_power_mW": w.avg_power_mW, "power_str": fmt_si(w.avg_power_mW, "mW"),
    } for i, w in enumerate(run.windows)]

    active = [c["name"] for c in components
              if any(w.components[c["name"]].dyn_energy_pJ for w in run.windows)]
    matrix = {"rows": [{
        "name": name,
        "cells": [fmt_si(w.components[name].dyn_energy_pJ, "pJ")
                  if w.components[name].dyn_energy_pJ else "—"
                  for w in run.windows],
    } for name in active]}

    # -- totals / timing / banners ------------------------------------------
    total_cycles = sum(w.exec_cycles for w in run.windows)
    area_um2 = sum(c["area_um2"] for c in components)
    f_max = run.f_max_MHz
    if not f_max:
        check_text, check_color, banner = "no timing model", "muted", None
    elif clock > f_max:
        check_text, check_color = f"FAIL — clock {clock:.0f} MHz > f_max", "err-ink"
        banner = {"level": "err",
                  "text": f"Configured clock ({clock:.0f} MHz) exceeds the "
                          f"estimated f_max ({f_max:.0f} MHz) — timing is not "
                          f"met; energy numbers assume the configured clock."}
    elif clock > 0.8 * f_max:
        check_text, check_color = f"tight — {100 * clock / f_max:.0f}% of f_max", "warn-ink"
        banner = {"level": "warn",
                  "text": f"Configured clock ({clock:.0f} MHz) is within 20% of "
                          f"the estimated f_max ({f_max:.0f} MHz)."}
    else:
        check_text, check_color, banner = "OK", "ok", None

    banners: List[Dict[str, str]] = []
    if vectorless is not None:
        banners.append({"level": "warn",
                        "text": f"No activity log was given — every component "
                                f"uses the VECTORLESS default "
                                f"({vectorless:.0%} of random activity)."})
    if banner:
        banners.append(banner)
    models = [c["model"] for c in components]
    if "stub" in models:
        stubs = sorted({c["cls"] for c in components if c["model"] == "stub"})
        banners.append({"level": "warn",
                        "text": "Placeholder (uncalibrated) unit costs for: "
                                + ", ".join(stubs)
                                + " — absolute numbers are first-order until "
                                  "the trained models land."})

    # -- charts --------------------------------------------------------------
    energy_items = _top_n([(c["name"], c["energy_pJ"]) for c in components])
    area_items = _top_n([(c["name"], c["area_um2"]) for c in components])
    svg = {
        "split_bar": dyn_leak_bar(run.dyn_energy_pJ, run.leak_energy_pJ),
        "energy_donut": donut(energy_items, unit="pJ"),
        "energy_bars": hbar_list(energy_items, unit="pJ"),
        "area_donut": donut(area_items, unit="µm²"),
        "area_bars": hbar_list(area_items, unit="µm²"),
        "windows": windows_chart(windows) if len(windows) > 1 or vectorless is None else "",
    }

    # -- provenance ----------------------------------------------------------
    input_entries = [{"name": str(label), "sha": _sha256(p) if p else None}
                     for label, p in inputs]
    from npuwattch._version import __version__

    return {
        "schema": "npuwattch-report/1",
        "design_name": design_name,
        "timestamp": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": __version__,
        "git_commit": "n/a",
        "tech": {
            "node": tech.node, "transistor": tech.transistor,
            "corner": tech.corner,
            "voltage_offset_V": tech.voltage_offset_V,
            "temperature_C": tech.temperature_C,
        },
        "clock": {"frequency_MHz": clock},
        "activity_source": activity_source,
        "model_tag": _model_tag(models),
        "banners": banners,
        "totals": {
            "energy_pJ": run.total_energy_pJ, "energy_str": fmt_si(run.total_energy_pJ, "pJ"),
            "dyn_pJ": run.dyn_energy_pJ, "dyn_str": fmt_si(run.dyn_energy_pJ, "pJ"),
            "leak_pJ": run.leak_energy_pJ, "leak_str": fmt_si(run.leak_energy_pJ, "pJ"),
            "dyn_pct": round(100.0 * run.dyn_energy_pJ / total_pJ, 1),
            "leak_pct": round(100.0 * run.leak_energy_pJ / total_pJ, 1),
            "avg_power_mW": run.avg_power_mW,
            "avg_power_str": fmt_si(run.avg_power_mW, "mW"),
            "area_um2": area_um2, "area_mm2": round(area_um2 / 1e6, 3),
            "cycles": total_cycles,
            "exec_time_s": run.exec_time_s,
            "exec_time_str": (f"{run.exec_time_s * 1e6:.3g} µs"
                              if run.exec_time_s < 1e-3
                              else f"{run.exec_time_s * 1e3:.3g} ms"),
        },
        "timing": {
            "f_max_MHz": f_max,
            "f_max_str": f"{f_max:.0f} MHz" if f_max else "n/a",
            "check_text": check_text, "check_color": check_color,
        },
        "windows": windows,
        "matrix": matrix,
        "components": components,
        "tree": tree_to_dict(hierarchy) if hierarchy is not None else None,
        "svg": svg,
        "provenance": {
            "models": [],
            "model_note": ("Calibrated-model manifest not yet wired: the sram "
                           "cluster runs trained MLPs (module-local "
                           "checkpoints), d2dlink is an analytic constant, and "
                           "the remaining clusters are placeholders until "
                           "workstream D lands."),
            "inputs": input_entries,
            "warnings": list(warnings),
            "notes": list(notes),
        },
    }


# ---------------------------------------------------------------------------
# rendering + writing
# ---------------------------------------------------------------------------

def render_html(context: Mapping[str, Any]) -> str:
    """Render the report template with the context (autoescaped; the SVG
    fields are injected via ``Markup`` since we generate them ourselves)."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from markupsafe import Markup

    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
        autoescape=select_autoescape(("html", "j2")),
        trim_blocks=True, lstrip_blocks=True,
    )
    ctx = dict(context)
    ctx["svg"] = {k: Markup(v) for k, v in context.get("svg", {}).items()}
    return env.get_template("report.html.j2").render(**ctx)


def write_report(context: Mapping[str, Any], out_dir: Path,
                 *, basename: str = "report") -> Tuple[Path, Path]:
    """Write ``<basename>.html`` and ``<basename>.json`` (same context, §3.6:
    the JSON drops only the ``svg`` markup key). Returns the two paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{basename}.html"
    json_path = out_dir / f"{basename}.json"
    html_path.write_text(render_html(context), encoding="utf-8")
    payload = {k: v for k, v in context.items() if k != "svg"}
    json_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return html_path, json_path
