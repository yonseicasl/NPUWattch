"""The HTML and JSON PPA report (manual §8).

``build_context``
    Makes one context dict of plain data from a §6 ``RunEnergy``, the
    description, and the provenance of the run.
``render_html``
    Renders the Jinja2 template with the context.
``write_report``
    Writes ``report.html`` and ``report.json`` (§3.6) from the same context.
    Thus the HTML and the JSON always agree.

This module calculates all the numbers: the shares, the unit costs, and the
f_max check. The template only formats them. The charts are inline SVG strings
from ``report.svg``. They are in the ``svg`` key of the context.
``report.json`` does not contain the ``svg`` key, because §3.6 lists data and
not markup.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from npuwattch.diagnostics import (
    INFO,
    WARNING,
    NPUWattchError,
    group as group_messages,
    is_suppressed,
)
from .svg import (
    donut,
    dyn_leak_bar,
    fmt_si,
    hbar_list,
    share_bar,
    windows_chart,
)

__all__ = ["ReportError", "build_context", "render_html", "write_report"]


class ReportError(NPUWattchError, ValueError):
    """The report cannot be made from the results of the run."""

_TOP_N = 8                     # the donut and the bar list show this many items


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _fmt_or_na(value: float, pattern: str = "{:.3g}") -> str:
    return pattern.format(value) if value else "n/a"


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _top_n(items: Sequence[Tuple[str, float]], n: int = _TOP_N):
    """Return the n largest (label, value) pairs. The sum of the remaining
    pairs follows as one ("other", sum) pair."""
    ranked = sorted((i for i in items if i[1] > 0),
                    key=lambda kv: kv[1], reverse=True)
    head, tail = ranked[:n], ranked[n:]
    if tail:
        head.append(("other", sum(v for _, v in tail)))
    return head


def _model_of(primitive: str, chain: Any) -> str:
    """Return the source of the values of a primitive:

    - ``cal``: a trained estimator.
    - ``const``: a constant from a table file.
    - ``user``: the user component library.
    - ``uncal``: a provider that is not in the lists of the provider chain.
    """
    if primitive in tuple(getattr(chain, "user_primitives", ()) or ()):
        return "user"
    if primitive in tuple(getattr(chain, "calibrated_primitives", ()) or ()):
        return "cal"
    if primitive in tuple(getattr(chain, "constant_primitives", ()) or ()):
        return "const"
    return "uncal"


def _model_tag(models: Iterable[str]) -> str:
    """Return the calibration tag of the summary. The CLI uses the same
    rules."""
    kinds = set(models)
    if kinds == {"cal"}:
        return "calibrated"
    if kinds <= {"uncal"}:
        return "UNCALIBRATED"
    return "PARTIAL calibration"


def _unit_energy_str(provider: Any, primitive: str, feats: Dict[str, Any],
                     charged_modes: Iterable[str] = ()) -> str:
    """Return the energy per cycle of one instance, as text.

    The function uses the stim_modes that the run charged to the component.
    There is no fixed list of modes: a FIFO streams, a memory reads and
    writes, an hbm activates. The function ignores ``idle`` and ``none``,
    because they give no unit information. If the provider has no value for
    the charged modes, the function uses ``random``. The text shows a maximum
    of two values in alphabetical order. Thus a memory shows read / write.
    """
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
# Context
# ---------------------------------------------------------------------------

def _dtype_label(cls: str, attrs: Mapping[str, Any]) -> Optional[str]:
    """Return the dtype name of a MAC component, for example fp32, bf16,
    fp16, int8, or an MX format."""
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
    """Return (dtype, fp32_equivalent) for the efficiency figure.

    Convention: the function calculates the cost of the fp MAC datapath again
    at fp32 (e8m23). The node, the clock, and the pipeline stay the same. The
    function does this for each charged stim_mode with the same provider. The
    energy of all other components (SRAM, NoC, DRAM) does not change. Thus
    you can compare runs of different fp precisions with fp32 references.

    The int and mx datapaths are different primitives, not a different
    precision. For them the function gives the dtype but no fp32 equivalent.
    If a step fails (no provider, unknown mode), the function gives no fp32
    equivalent. A report view must not stop the run.
    """
    macs = [c for c in components if c["cls"] in ("fpmac", "intmac", "mxfpmac")
            and c["dyn_energy_pJ"] > 0]
    if not macs or flops <= 0:
        return None, None
    top = max(macs, key=lambda c: c["dyn_energy_pJ"])
    dtype = _dtype_label(top["cls"], attrs_by_name.get(top["name"], {}))
    if any(c["cls"] != "fpmac" for c in macs):
        return dtype, None                      # int/mx: no fp32 equivalent
    if provider is None:
        return dtype, None
    try:
        delta = 0.0
        for c in macs:
            attrs = attrs_by_name.get(c["name"], {})
            if (attrs.get("exponent_bits"), attrs.get("mantissa_bits")) == (8, 23):
                continue                        # the component is fp32
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
                    continue                    # no model for the mode: ratio = 1
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
    notes: Sequence[str] = (),                  # documented conventions and exclusions
    activity_rows: Sequence[Mapping[str, Any]] = (),
    inputs: Sequence[Tuple[str, Optional[Path]]] = (),
    vectorless: Optional[float] = None,         # activity fraction of a vectorless run
    window_provenance: Sequence[Mapping[str, Any]] = (),  # one harness record per kernel
    node_resolution: Any = None,                # energy.NodeResolution (or None)
    timing: bool = True,                        # show f_max and the critical paths
) -> Dict[str, Any]:
    """Make the one dict of plain data that is the source of ``report.html``
    and ``report.json``.

    ``timing`` False removes f_max, the clock check, and the critical path of
    each component from the report (CLI: no ``--fmax``)."""
    from .tree import to_dict as tree_to_dict

    nw = description.get("npuwattch", {})
    clock = float((nw.get("clock") or {}).get("frequency_MHz") or 0.0)
    attrs_by_name = {c["name"]: (c.get("attributes") or {})
                     for c in nw.get("components", [])}
    provider = getattr(chain, "provider", None)

    if not run.windows:
        raise ReportError.nw(4001)
    comp0 = run.windows[0].components
    total_pJ = run.total_energy_pJ or 1.0

    # -- Totals for each component (one entry for each component name) -------
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
            # Calculate the unit costs at the clock of the run, as §6 does.
            # A clock in the TechContext has priority. tech.features() gives
            # clock_mhz: None if no clock is set. Replace that value.
            feats["clock_mhz"] = clock
        components.append({
            "name": name,
            "cls": c0.primitive,
            # The dynamic energy of the run for each stim_mode. The sum is
            # dyn_energy_pJ. Only the JSON (§3.6) shows this split for each
            # component. The HTML does not.
            "dyn_by_mode": by_mode,
            "model": (model := _model_of(c0.primitive, chain)),
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
            # The unit costs are for one instance (§8.6). The raw *_mW and
            # *_um2 fields are the totals of the component (× count) for §3.6.
            "leak_power_mW": c0.leak_power_mW,
            "unit_leak_power_mW": c0.leak_power_mW / max(1, c0.instances),
            "leak_power_str": _fmt_or_na(c0.leak_power_mW / max(1, c0.instances)),
            "area_um2": c0.area_um2,
            "unit_area_um2": c0.area_um2 / max(1, c0.instances),
            "area_str": _fmt_or_na(c0.area_um2 / max(1, c0.instances)),
            "crit_path_ns": c0.crit_path_ns if timing else None,
            "crit_path_str": _fmt_or_na(c0.crit_path_ns) if timing else None,
            "activity_events": activity_by_comp.get(name, 0.0),
            "activity_str": _fmt_or_na(activity_by_comp.get(name, 0.0)),
            "vectorless": vectorless is not None,
            "user_defined": model == "user",
        })

    # -- Windows and the component × window matrix ---------------------------
    kinds = {p["window"]: p["kind"] for p in window_provenance}
    windows = [{
        "index": i,
        "label": w.label,
        "kind": kinds.get(i),                   # mac|fused|non_mac (harness runs only)
        "cycles": w.exec_cycles,
        "dyn_pJ": w.dyn_energy_pJ, "dyn_str": fmt_si(w.dyn_energy_pJ, "pJ"),
        "leak_pJ": w.leak_energy_pJ, "leak_str": fmt_si(w.leak_energy_pJ, "pJ"),
        "total_pJ": w.total_energy_pJ, "total_str": fmt_si(w.total_energy_pJ, "pJ"),
        "avg_power_mW": w.avg_power_mW, "power_str": fmt_si(w.avg_power_mW, "mW"),
    } for i, w in enumerate(run.windows)]

    # The GEMM and non-GEMM split. It applies only if non-MAC kernels exist.
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

    # -- DRAM command breakdown (§8) -----------------------------------------
    # The split of the hbm components for each mode: row activation, read
    # transfer, write transfer, and the refresh term of NPUWattch. A
    # vectorless run charges hbm at `random`. Such a run has no command
    # modes, thus it has no breakdown.
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
                # The constants that the run charged for each command. They
                # are from the DRAM energy table of the run: the default
                # table or --energy-table. The attributes of the description
                # are the only source in the two cases.
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

    # -- Totals, timing, and banners -----------------------------------------
    total_cycles = sum(w.exec_cycles for w in run.windows)
    area_um2 = sum(c["area_um2"] for c in components)

    # The compute-efficiency figure: the energy of the run per FLOP, where
    # 1 MAC = 2 FLOP. The operation count is the charged events of the MAC
    # datapath components, without the idle events. The systolic PEs give
    # most of the count. The fpmac operations of the vector datapath are
    # also in the count. The numerator includes the DRAM, NoC, and SRAM
    # energy. Thus this is a CHIP-LEVEL figure, which you can compare with
    # TFLOPS/TDP values of a chip. It is not a figure for the MAC only.
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
            # The precision of the datapath and the fp32 equivalent. The
            # equivalent is None for int/mx datapaths, or if the provider
            # cannot calculate it.
            "dtype": dtype,
            "fp32_equivalent": fp32_eq,
        }
    power_density = ((run.avg_power_mW * 1e-3) / (area_um2 / 1e6)
                     if area_um2 > 0 else None)
    f_max = run.f_max_MHz if timing else None
    if not timing:
        check_text, check_color, banner = "not shown (no --fmax)", "muted", None
    elif not f_max:
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
    if "user" in models:
        users = sorted({c["cls"] for c in components if c["model"] == "user"})
        banners.append({"level": "warn",
                        "text": "User component library values for: "
                                + ", ".join(users)
                                + " — these are the user's numbers at their "
                                  "reference technology, not model "
                                  "predictions."})
    if "uncal" in models:
        uncal = sorted({c["cls"] for c in components if c["model"] == "uncal"})
        banners.append({"level": "warn",
                        "text": "Uncalibrated unit costs for: "
                                + ", ".join(uncal) + "."})

    # -- Charts --------------------------------------------------------------
    # The NPU and DRAM split. The DRAM device uses most of the energy of a
    # full run, which makes the other components too small to read in the
    # donut. Thus the hbm components have a separate bar with two segments.
    # The energy donut and the bar list EXCLUDE them and show only the
    # on-chip (NPU) components.
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

    # -- Provenance ----------------------------------------------------------
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
            # The continuous node axis (§6.2): how the run got the values of
            # the requested node from the characterized nodes. An "exact" run
            # has no such fields, because its node is a characterized node.
            **({} if node_resolution is None or node_resolution.kind == "exact"
               else {"node_scaling": node_resolution.kind,
                     "node_evaluated_nm": node_resolution.eval_nm,
                     "node_anchors": [node_resolution.lo,
                                      node_resolution.hi]}),
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
            # The power divided by the MODELED area only. The denominator
            # does not include the IO, the PHY, the controllers, the scalar
            # core, or the empty area, because NPUWattch has no model for
            # them. Thus this value is higher than a TDP density of a full die.
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
            "enabled": timing,
            "f_max_MHz": f_max,
            "f_max_str": f"{f_max:.0f} MHz" if f_max else "n/a",
            "check_text": check_text, "check_color": check_color,
        },
        "windows": windows,
        "kernel_split": kernel_split,
        "dram_breakdown": dram_breakdown,
        "npu_dram_split": npu_dram_split,
        "efficiency": efficiency,
        # The term that the report shows. "window" is the term of the core
        # for one time interval, for all harnesses. A PyTorchSim run has
        # window_provenance and one kernel is one window there. Thus the
        # report of such a run uses "kernel".
        "window_term": "kernel" if window_provenance else "window",
        "matrix": matrix,
        "components": components,
        "tree": tree_to_dict(hierarchy) if hierarchy is not None else None,
        "svg": svg,
        "provenance": {
            "models": [],
            "model_note": ("Calibrated clusters: sram and the "
                           "logic MLP primitives; d2dlink and hbm use cited "
                           "table constants; a user component uses the "
                           "values of the user component library."),
            "inputs": input_entries,
            # The text of each message ("(NW-6101): ..."), and the same
            # messages grouped with their code, level and count. A message
            # that --suppress hides is in neither.
            "warnings": [str(w) for w in warnings
                         if not is_suppressed(getattr(w, "code", None))],
            "notes": [str(n) for n in notes
                      if not is_suppressed(getattr(n, "code", None))],
            "diagnostics": {
                "warnings": group_messages(warnings, WARNING),
                "notes": group_messages(notes, INFO),
            },
            # The provenance of each kernel of a harness run: the kind, the
            # source of the dtype, and the primary activity counters. The
            # JSON always has these records, at each console verbosity.
            "windows": [dict(p) for p in window_provenance],
        },
    }


# ---------------------------------------------------------------------------
# Render and write
# ---------------------------------------------------------------------------

def render_html(context: Mapping[str, Any]) -> str:
    """Render the report template with the context.

    Jinja2 escapes all values automatically. The SVG fields are ``Markup``
    and are not escaped, because ``report.svg`` makes them.
    """
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
    """Write ``<basename>.html`` and ``<basename>.json`` from the same context.

    The JSON (§3.6) contains all keys of the context but the ``svg`` key.
    Return the two paths.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{basename}.html"
    json_path = out_dir / f"{basename}.json"
    html_path.write_text(render_html(context), encoding="utf-8")
    payload = {k: v for k, v in context.items() if k != "svg"}
    json_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return html_path, json_path
