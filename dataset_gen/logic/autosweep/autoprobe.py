"""Frequency probe and sweep-manifest generation.

The probe synthesizes every sweep configuration once per node at an
unreachable clock (0.5 ns): Design Compiler pushes to its floor and the
achieved critical-path length approximates the minimum achievable period
T_min. From T_min the manifest generator derives the two sweep clocks per
(config, node):

    tight   = ceil(1.2 x T_min / grid) x grid   (MET with PnR margin)
    relaxed = ceil(2.0 x T_min / grid) x grid

Probe results accumulate in probe_results.tsv; ok rows are skipped on
re-run (crash resume), error rows are retried. Each probe run directory is
deleted right after its numbers are parsed, so the probe needs only a few
hundred MB of scratch at any moment.
"""
from __future__ import annotations

import math
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocommon import (
    AUTOSWEEP_DIR,
    JOB_LIST,
    NW_LOGIC_DIR,
    normalize_node,
    parse_arch_params,
    read_catalog,
    rtl_variant_dir_name,
    run_id_for_job,
)
from autosynth import run_synthesis_job
from rtl_gen import generator
from sweep_spec import CLOCKED_MODULES, SWEEP_NODES, sweep_configs

PROBE_CLOCK_NS = 0.5
PROBE_RESULTS = AUTOSWEEP_DIR / "probe_results.tsv"
PROBE_COLUMNS = ("rtl_name", "arch_params", "node", "status", "crit_path_ns", "slack_ns", "message")

TIGHT_MARGIN = 1.2
RELAX_MARGIN = 2.0
CLOCK_GRID_NS = 0.25

_TSV_LOCK = threading.Lock()

_CRIT_RE = re.compile(r"Critical Path Length:\s+([0-9.]+)")
_SLACK_RE = re.compile(r"Critical Path Slack:\s+(-?[0-9.]+)")


def _resolve_nodes(nodes: tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize the requested node list (default: all sweep nodes), dedupe,
    and fail fast on any node the catalog cannot serve — otherwise a typo'd
    node would surface as hundreds of per-config error rows overnight."""
    resolved = tuple(dict.fromkeys(normalize_node(node) for node in (nodes or SWEEP_NODES)))
    for node in resolved:
        nominal_corner(node)
    return resolved


def nominal_corner(node: str) -> dict[str, str]:
    """The node's median-voltage TT/25C corner (5 characterized voltages)."""
    for entry in read_catalog():
        if normalize_node(str(entry.get("node", ""))) != normalize_node(node):
            continue
        corners = [
            corner
            for corner in entry.get("corners", [])
            if str(corner.get("process", "")).strip() == "TT"
            and str(corner.get("temperature", "")).strip() == "25"
        ]
        if not corners:
            break
        corners.sort(key=lambda corner: float(corner["voltage"]))
        chosen = corners[len(corners) // 2]
        return {"voltage": str(chosen["voltage"]).strip(), "temp": str(chosen["temperature"]).strip()}
    raise ValueError(f"no TT/25C corners in the catalog for node {node}")


def sweep_job(rtl_name: str, arch_params: str, node: str, period_ns: float) -> dict[str, str]:
    corner = nominal_corner(node)
    clocked = rtl_name in CLOCKED_MODULES
    return {
        "rtl_name": rtl_name,
        "arch_params": arch_params,
        "node": node,
        "process": "TT",
        "voltage": corner["voltage"],
        "temp": corner["temp"],
        "clock_period_ns": f"{period_ns:g}",
        "clock_freq_mhz": "",
        "clock_port": "i_clk",
        "reset_port": "i_rst_n" if clocked else "",
        "reset_active": "low" if clocked else "",
    }


def _append_result(row: dict[str, str]) -> None:
    with _TSV_LOCK:
        new_file = not PROBE_RESULTS.exists()
        with PROBE_RESULTS.open("a", encoding="utf-8") as fp:
            if new_file:
                fp.write("\t".join(PROBE_COLUMNS) + "\n")
            fp.write("\t".join(str(row.get(col, "")) for col in PROBE_COLUMNS) + "\n")


def load_probe_results() -> dict[tuple[str, str, str], float]:
    """(rtl_name, arch_params, node) -> crit_path_ns for every ok row."""
    results: dict[tuple[str, str, str], float] = {}
    if not PROBE_RESULTS.exists():
        return results
    with PROBE_RESULTS.open(encoding="utf-8") as fp:
        header = fp.readline().rstrip("\n").split("\t")
        for line in fp:
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            if row.get("status") != "ok":
                continue
            key = (row["rtl_name"], row["arch_params"], normalize_node(row["node"]))
            results[key] = float(row["crit_path_ns"])
    return results


def _generate_rtl_variants(configs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Generate every RTL variant; returns {config: error message} for failures."""
    gens = {
        name.removeprefix("gen_"): getattr(generator, name)
        for name in dir(generator)
        if name.startswith("gen_") and callable(getattr(generator, name))
    }
    errors: dict[tuple[str, str], str] = {}
    for index, (rtl_name, arch) in enumerate(configs, start=1):
        job = {"rtl_name": rtl_name, "arch_params": arch}
        variant_root = generator.RTL_DIR / rtl_variant_dir_name(job)
        try:
            gens[rtl_name](**parse_arch_params(arch), output_root=variant_root)
        except Exception as exc:  # noqa: BLE001 - record and continue
            errors[(rtl_name, arch)] = f"{type(exc).__name__}: {exc}"
            print(f"[rtl {index}/{len(configs)}] ERROR {rtl_name} {arch}: {exc}")
    return errors


def _probe_one(rtl_name: str, arch: str, node: str) -> None:
    job = sweep_job(rtl_name, arch, node, PROBE_CLOCK_NS)
    run_id = run_id_for_job(job)
    run_dir = NW_LOGIC_DIR / f"TECH_{int(normalize_node(node)):02d}nm" / "01_syn" / run_id
    base = {"rtl_name": rtl_name, "arch_params": arch, "node": node}
    try:
        run_synthesis_job(job, 0)
        text = (run_dir / "synthesis.log").read_text(encoding="utf-8")
        crit_match = _CRIT_RE.search(text)
        slack_match = _SLACK_RE.search(text)
        if not crit_match:
            raise RuntimeError("no 'Critical Path Length' in synthesis.log")
        _append_result(
            base
            | {
                "status": "ok",
                "crit_path_ns": crit_match.group(1),
                "slack_ns": slack_match.group(1) if slack_match else "",
            }
        )
    except Exception as exc:  # noqa: BLE001 - a probe must survive bad configs
        _append_result(base | {"status": "error", "message": str(exc)[:300].replace("\t", " ").replace("\n", " ")})
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _probe_node(node: str, configs: list[tuple[str, str]], *, jobs_per_node: int) -> None:
    total = len(configs)
    if jobs_per_node <= 1:
        for index, (rtl_name, arch) in enumerate(configs, start=1):
            _probe_one(rtl_name, arch, node)
            print(f"[probe {node}nm] {index}/{total} {rtl_name}")
        return
    with ThreadPoolExecutor(max_workers=jobs_per_node) as pool:
        futures = {pool.submit(_probe_one, rtl_name, arch, node): rtl_name for rtl_name, arch in configs}
        for index, future in enumerate(as_completed(futures), start=1):
            future.result()  # _probe_one never raises
            print(f"[probe {node}nm] {index}/{total} {futures[future]}")


def run_probe(*, jobs_per_node: int = 1, nodes: tuple[str, ...] | None = None) -> None:
    nodes = _resolve_nodes(nodes)
    configs = sweep_configs()
    done = load_probe_results()
    pending_by_node = {
        node: [
            (rtl_name, arch)
            for rtl_name, arch in configs
            if (rtl_name, arch, normalize_node(node)) not in done
        ]
        for node in nodes
    }
    pending_total = sum(len(cfgs) for cfgs in pending_by_node.values())
    print(
        f"probe: {len(configs)} configs x {len(nodes)} nodes, "
        f"{len(done)} already ok, {pending_total} to run"
    )
    if pending_total == 0:
        return

    pending_configs = sorted({cfg for cfgs in pending_by_node.values() for cfg in cfgs})
    print(f"probe: generating RTL for {len(pending_configs)} variants")
    gen_errors = _generate_rtl_variants(pending_configs)
    for (rtl_name, arch), message in gen_errors.items():
        for node in nodes:
            if (rtl_name, arch) in pending_by_node[node]:
                _append_result(
                    {
                        "rtl_name": rtl_name,
                        "arch_params": arch,
                        "node": node,
                        "status": "error",
                        "message": f"rtl-gen: {message}",
                    }
                )

    with ThreadPoolExecutor(max_workers=max(1, len(nodes))) as pool:
        futures = [
            pool.submit(
                _probe_node,
                node,
                [cfg for cfg in cfgs if cfg not in gen_errors],
                jobs_per_node=jobs_per_node,
            )
            for node, cfgs in pending_by_node.items()
            if cfgs
        ]
        for future in as_completed(futures):
            future.result()

    results = load_probe_results()
    print(f"probe complete: {len(results)} ok results in {PROBE_RESULTS}")


def _grid_ceil(period_ns: float) -> float:
    return math.ceil(period_ns / CLOCK_GRID_NS - 1e-9) * CLOCK_GRID_NS


def generate_sweep_manifest(
    out_path: Path = JOB_LIST, *, nodes: tuple[str, ...] | None = None
) -> None:
    """Write the sweep manifest (two clocks per config x node) from probe data."""
    nodes = _resolve_nodes(nodes)
    results = load_probe_results()
    configs = sweep_configs()

    header = (
        "rtl_name\tarch_params\tnode\tprocess\tvoltage\ttemp\t"
        "clock_period_ns\tclock_freq_mhz\tclock_port\treset_port\treset_active"
    )
    lines = [
        "# Generated by run_batch.py gen-jobs from probe_results.tsv.",
        f"# Nodes: {', '.join(nodes)}.",
        f"# Two clocks per (config, node): tight = {TIGHT_MARGIN} x T_min, "
        f"relaxed = {RELAX_MARGIN} x T_min, ceil to {CLOCK_GRID_NS} ns grid.",
        header,
    ]
    missing: list[tuple[str, str, str]] = []
    rows = 0
    for rtl_name, arch in configs:
        for node in nodes:
            crit = results.get((rtl_name, arch, normalize_node(node)))
            if crit is None:
                missing.append((rtl_name, arch, node))
                continue
            tight = _grid_ceil(TIGHT_MARGIN * crit)
            relaxed = _grid_ceil(RELAX_MARGIN * crit)
            if relaxed <= tight:
                relaxed = tight + CLOCK_GRID_NS
            for period in (tight, relaxed):
                job = sweep_job(rtl_name, arch, node, period)
                job["clock_freq_mhz"] = f"{1000.0 / period:.6g}"
                lines.append("\t".join(job[col] for col in header.split("\t")))
                rows += 1

    if out_path.exists():
        backup = out_path.with_suffix(".prev")
        shutil.copyfile(out_path, backup)
        print(f"gen-jobs: previous manifest backed up to {backup}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"gen-jobs: wrote {rows} jobs to {out_path}")
    if missing:
        print(
            f"gen-jobs: WARNING {len(missing)} (config, node) pairs have no ok probe "
            "result and were left out - re-run 'run_batch.py probe' to retry them"
        )
