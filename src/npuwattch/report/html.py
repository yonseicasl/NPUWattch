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
    share_bar,
    windows_chart,
)

__all__ = ["build_context", "render_html", "write_report"]

_TOP_N = 8                     # donut / bar-list grouping (skill guidance)


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


def _unit_energy_str(provider: Any, primitive: str, feats: Dict[str, Any],
                     charged_modes: Iterable[str] = ()) -> str:
    """Per-instance E/cycle, priced at the stim modes this run actually
    charged the component with — mode-agnostic by design (a FIFO streams, a
    memory reads/writes, an hbm activates; no fixed mode list). ``idle``/
    ``none`` carry no unit information and are skipped; a component with no
    priceable charged mode falls back to ``random``. At most two values are
    shown, alphabetically (memories keep the familiar read / write pair)."""
    def one(mode: str) -> Optional[float]:
        try:
            return provider.energy_per_cycle(primitive, {**feats, "stim_mode": mode})
        except Exception:
            return None
    modes = sorted(m for m in set(charged_modes) if m not in ("idle", "none"))
    priced = [(m, v) for m in modes if (v := one(m)) is not None]
    if not priced:
        op = one("random")
        return f"{op:.3g}" if op is not None else "n/a"
    return " / ".join(f"{v:.3g}" for _, v in priced[:2])


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def _dtype_label(cls: str, attrs: Mapping[str, Any]) -> Optional[str]:
    """Human dtype of a MAC-family component (fp32/bf16/fp16/int8/mx…)."""
    if cls == "fpmac":
        e, m = attrs.get("exponent_bits"), attrs.get("mantissa_bits")
        if (e, m) == (8, 23):
            return "fp32"
        if (e, m) == (8, 7):
            return "bf16"
        if (e, m) == (5, 10):
            return "fp16"
        return f"fp e{e}m{m}" if e and m else None
    if cls == "intmac":
        w = attrs.get("data_width_a") or attrs.get("data_width")
        return f"int{w}" if w else "int"
    if cls == "mxfpmac":
        return str(attrs.get("mx_input_format") or "mx")
    return None


def _fp32_equivalent(components, attrs_by_name, provider, tech, clock,
                     total_pJ, flops):
    """(dtype, fp32_equivalent) for the efficiency KPI.

    Convention (2026-08-11): re-price the fp MAC datapath at fp32 (e8m23)
    with identical structure (node/clock/pipeline), per charged stim_mode,
    using the same provider — everything non-MAC (SRAM/NoC/DRAM) stays
    unchanged, so runs of different fp precisions compare against fp32
    references apples-to-apples. int/mx datapaths are different primitives,
    not a precision rescale → dtype is labeled but no equivalent is claimed.
    Any failure (no provider, unknown mode) skips the annotation — a report
    view must never fail the run.
    """
    macs = [c for c in components if c["cls"] in ("fpmac", "intmac", "mxfpmac")
            and c["dyn_energy_pJ"] > 0]
    if not macs or flops <= 0:
        return None, None
    top = max(macs, key=lambda c: c["dyn_energy_pJ"])
    dtype = _dtype_label(top["cls"], attrs_by_name.get(top["name"], {}))
    if any(c["cls"] != "fpmac" for c in macs):
        return dtype, None                      # int/mx: no fp32 rescale
    if provider is None:
        return dtype, None
    try:
        delta = 0.0
        for c in macs:
            attrs = attrs_by_name.get(c["name"], {})
            if (attrs.get("exponent_bits"), attrs.get("mantissa_bits")) == (8, 23):
                continue                        # already fp32
            base = {**tech.features(), "clock_mhz": clock, **attrs}
            fp32 = {**base, "exponent_bits": 8, "mantissa_bits": 23,
                    "data_width": 32}
            for mode, e in c["dyn_by_mode"].items():
                try:
                    e_native = provider.energy_per_cycle(
                        "fpmac", {**base, "stim_mode": mode})
                    e_fp32 = provider.energy_per_cycle(
                        "fpmac", {**fp32, "stim_mode": mode})
                except Exception:
                    continue                    # uncharacterized mode: r = 1
                if e_native > 0:
                    delta += e * (e_fp32 / e_native - 1.0)
        pj_per_flop = (total_pJ + delta) / flops
        return dtype, {
            "pJ_per_flop": pj_per_flop,
            "pJ_per_flop_str": f"{pj_per_flop:.3g} pJ/FLOP",
            "factor": pj_per_flop / (total_pJ / flops),
        }
    except Exception:
        return dtype, None


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
    window_provenance: Sequence[Mapping[str, Any]] = (),  # harness per-kernel records
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
        by_mode: Dict[str, float] = {}
        for w in run.windows:
            for m, e in getattr(w.components[name], "dyn_by_mode", {}).items():
                by_mode[m] = by_mode.get(m, 0.0) + e
        feats: Dict[str, Any] = dict(tech.features())
        feats.update(attrs_by_name.get(name, {}))
        if clock and not feats.get("clock_mhz"):
            # price unit costs at the run clock, exactly as §6 charged them
            # (an explicit TechContext clock still wins, mirroring aggregate;
            # tech.features() emits clock_mhz: None when unset — overwrite it)
            feats["clock_mhz"] = clock
        components.append({
            "name": name,
            "cls": c0.primitive,
            # dynamic energy per stim_mode (run total; Σ == dyn_energy_pJ) —
            # the finest split the activity carries, §3.6 only (not rendered
            # per component in the HTML).
            "dyn_by_mode": by_mode,
            "model": _model_of(c0.primitive, chain),
            "count": c0.instances,
            "dyn_energy_pJ": dyn,
            "dyn_str": fmt_si(dyn, "pJ") if dyn else "—",
            "leak_energy_pJ": leak,
            "leak_str": fmt_si(leak, "pJ"),
            "energy_pJ": dyn + leak,
            "energy_str": fmt_si(dyn + leak, "pJ"),
            "energy_pct": round(100.0 * (dyn + leak) / total_pJ, 1),
            "unit_energy_str": (_unit_energy_str(provider, c0.primitive, feats,
                                                 by_mode)
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
    kinds = {p["window"]: p["kind"] for p in window_provenance}
    windows = [{
        "index": i,
        "label": w.kernel_hash,
        "kind": kinds.get(i),                   # mac|fused|non_mac (harness runs)
        "cycles": w.exec_cycles,
        "dyn_pJ": w.dyn_energy_pJ, "dyn_str": fmt_si(w.dyn_energy_pJ, "pJ"),
        "leak_pJ": w.leak_energy_pJ, "leak_str": fmt_si(w.leak_energy_pJ, "pJ"),
        "total_pJ": w.total_energy_pJ, "total_str": fmt_si(w.total_energy_pJ, "pJ"),
        "avg_power_mW": w.avg_power_mW, "power_str": fmt_si(w.avg_power_mW, "mW"),
    } for i, w in enumerate(run.windows)]

    # GEMM vs non-GEMM split (only meaningful when non-MAC kernels exist).
    kernel_split = None
    if any(k == "non_mac" for k in kinds.values()):
        non_tot = sum(w.total_energy_pJ for i, w in enumerate(run.windows)
                      if kinds.get(i) == "non_mac")
        mac_tot = run.total_energy_pJ - non_tot
        kernel_split = {
            "gemm_pJ": mac_tot, "gemm_str": fmt_si(mac_tot, "pJ"),
            "non_gemm_pJ": non_tot, "non_gemm_str": fmt_si(non_tot, "pJ"),
            "non_gemm_pct": round(
                100.0 * non_tot / (run.total_energy_pJ or 1.0), 1),
            "non_gemm_windows": sum(1 for k in kinds.values() if k == "non_mac"),
        }

    # -- DRAM device command breakdown (§8; author handoff 2026-08-10) -------
    # The per-mode split of the hbm components: the authors' verification
    # vocabulary (activation vs transfer) + NPUWattch's refresh term. A
    # vectorless run prices hbm at `random` → no command modes → omitted.
    dram_comps = [c for c in components if c["cls"] == "hbm"]
    dram_breakdown = None
    if dram_comps:
        modes: Dict[str, float] = {}
        for c in dram_comps:
            for m, e in c["dyn_by_mode"].items():
                modes[m] = modes.get(m, 0.0) + e
        labels = [("activate", "Row activation (ACT+PRE)"),
                  ("read", "Transfer — read"),
                  ("write", "Transfer — write"),
                  ("refresh", "Refresh")]
        dram_total = sum(modes.get(k, 0.0) for k, _ in labels)
        if dram_total > 0:
            attrs0 = attrs_by_name.get(dram_comps[0]["name"], {})
            dram_breakdown = {
                "components": [c["name"] for c in dram_comps],
                "rows": [{
                    "mode": k, "label": lbl,
                    "energy_pJ": modes.get(k, 0.0),
                    "energy_str": fmt_si(modes.get(k, 0.0), "pJ"),
                    "pct": round(100.0 * modes.get(k, 0.0) / dram_total, 1),
                } for k, lbl in labels],
                "total_pJ": dram_total,
                "total_str": fmt_si(dram_total, "pJ"),
                "share_of_run_pct": round(100.0 * dram_total / total_pJ, 1),
                # the charged per-command constants (built-in or the run's
                # --energy-table override — the description attrs are the
                # single source either way)
                "constants": {
                    "act_pJ": attrs0.get("mem_act_energy_pJ"),
                    "access_pJ_per_bit": attrs0.get("mem_access_energy_per_bit_pJ"),
                    "ref_pJ": attrs0.get("mem_ref_energy_pJ"),
                    "data_width_bits": attrs0.get("data_width"),
                },
            }

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

    # Compute-efficiency KPI (user request 2026-08-11): run energy per FLOP,
    # with MAC = 2 FLOP. Op count = the charged events of the MAC-family
    # datapath components (systolic PEs dominate; the vector datapath's
    # fpmac-class ops ride along), idle events excluded. Deliberately
    # includes DRAM/NoC/SRAM energy in the numerator — it is a CHIP-LEVEL
    # figure, comparable to per-chip TFLOPS/TDP quotes, not a bare-MAC one.
    _MAC_PRIMS = ("fpmac", "intmac", "mxfpmac")
    mac_ops = 0.0
    for r in activity_rows:
        name = str(r.get("component", ""))
        if name == "__meta__" or name not in comp0:
            continue
        if (comp0[name].primitive in _MAC_PRIMS
                and str(r.get("mode")) != "idle"):
            mac_ops += float(r.get("count", 0))
    efficiency = None
    if mac_ops > 0 and run.exec_time_s > 0:
        flops = 2.0 * mac_ops
        dtype, fp32_eq = _fp32_equivalent(
            components, attrs_by_name, provider, tech, clock,
            run.total_energy_pJ, flops)
        efficiency = {
            "mac_ops": mac_ops,
            "pJ_per_mac": run.total_energy_pJ / mac_ops,
            "pJ_per_flop": run.total_energy_pJ / flops,
            "pJ_per_flop_str":
                f"{run.total_energy_pJ / flops:.3g} pJ/FLOP",
            "tflops": flops / run.exec_time_s / 1e12,
            "tflops_str": f"{flops / run.exec_time_s / 1e12:.3g}",
            # datapath precision + the fp32-normalized figure (None for
            # int/mx datapaths or when the provider cannot re-price)
            "dtype": dtype,
            "fp32_equivalent": fp32_eq,
        }
    power_density = ((run.avg_power_mW * 1e-3) / (area_um2 / 1e6)
                     if area_um2 > 0 else None)
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
    # NPU vs DRAM top-level split (user request 2026-08-11): the DRAM device
    # dominates full-run totals and drowned the per-component donut, so hbm
    # components get a dedicated two-way bar and are EXCLUDED from the
    # energy donut/bar list, which then covers the on-chip (NPU) side only.
    dram_pJ = sum(c["energy_pJ"] for c in components if c["cls"] == "hbm")
    npu_pJ = run.total_energy_pJ - dram_pJ
    npu_dram_split = None
    if dram_pJ > 0:
        npu_dram_split = {
            "npu_pJ": npu_pJ, "npu_str": fmt_si(npu_pJ, "pJ"),
            "npu_pct": round(100.0 * npu_pJ / total_pJ, 1),
            "dram_pJ": dram_pJ, "dram_str": fmt_si(dram_pJ, "pJ"),
            "dram_pct": round(100.0 * dram_pJ / total_pJ, 1),
        }
    energy_items = _top_n([(c["name"], c["energy_pJ"]) for c in components
                           if c["cls"] != "hbm"])
    area_items = _top_n([(c["name"], c["area_um2"]) for c in components])
    svg = {
        "split_bar": dyn_leak_bar(run.dyn_energy_pJ, run.leak_energy_pJ),
        "npu_dram_bar": (share_bar("NPU (on-chip)", npu_pJ, "DRAM", dram_pJ,
                                   aria="NPU vs DRAM energy share")
                         if npu_dram_split else ""),
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
            # power over the MODELED area only — no IO/PHY/controllers/
            # scalar core/whitespace in the denominator (they are out of
            # scope), so this reads high vs whole-die TDP densities.
            "power_density_W_per_mm2": power_density,
            "power_density_str": (f"{power_density:.3g} W/mm²"
                                  if power_density else None),
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
        "kernel_split": kernel_split,
        "dram_breakdown": dram_breakdown,
        "npu_dram_split": npu_dram_split,
        "efficiency": efficiency,
        # window/kernel terminology (user decision 2026-07-31): "window" is
        # the core's harness-neutral time-interval term; PyTorchSim-harness
        # runs (window_provenance present) address end users as "kernel"
        # since there one kernel == one window by construction.
        "window_term": "kernel" if window_provenance else "window",
        "matrix": matrix,
        "components": components,
        "tree": tree_to_dict(hierarchy) if hierarchy is not None else None,
        "svg": svg,
        "provenance": {
            "models": [],
            "model_note": ("Calibrated-model manifest (checkpoint hashes) not "
                           "yet wired. Calibrated clusters: sram + the logic "
                           "v2 MLP quartets (fpadd/fpmul/fpmac/intadd/intmul/"
                           "intmac/fpsfu/mxfpmac/fifo/regfile/simplemux, "
                           "wired 2026-08-11); d2dlink and hbm are cited "
                           "analytic constants; crossbar/fattree/foldedclos "
                           "stay placeholders until the expanded NoC sweep "
                           "retrains them."),
            "inputs": input_entries,
            "warnings": list(warnings),
            "notes": list(notes),
            # Per-kernel provenance parsed from the run (harness mode): kind,
            # dtype origin, headline activity counters. Always present in the
            # JSON regardless of console verbosity.
            "windows": [dict(p) for p in window_provenance],
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
