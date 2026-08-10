"""Storage-bounded sweep driver: one full flow chain per job, then prune.

The driver pipelines each job (RTL must already be rendered: run_batch rtl)
through

    syn -> pnr [-> clock rederivation -> syn -> pnr]
        -> pex -> sim (one gate-level run per stimulus mode)
        -> pwr(unvectored)          -> CSV row
        -> pwr(vectored, mode) x N  -> CSV row each   (N = power_modes(module))
    -> archive report texts -> delete the run directories

so the heavy EDA artifacts on disk at any moment belong only to the jobs
currently executing (nodes x jobs_per_node of them), not to the whole sweep.

Clock self-correction: probe periods are synthesis-only estimates, so a
post-PnR setup violation beyond the sim margin does not fail the job -- the
sweep derives a slower clock from the measured slack, persists it into the
manifest, and re-runs syn+PnR (up to two rederivations per job).

Crash resume: a job whose dataset CSV already holds the unvectored row AND
one vectored row per stimulus mode of its module is skipped, so re-running
the same command continues where the previous invocation stopped.  NOTE the
flip side of the storage bounding: because run directories are deleted after
collection, adding a NEW mode to POWER_MODES later re-runs the whole EDA
chain for the affected jobs -- extend the mode list before a sweep, not
after.  Failures are recorded in sweep_failures.tsv and do not stop the
sweep; run_batch rerun-failed patches their clocks and retires the log.
"""
from __future__ import annotations

import csv
import math
import os
import re
import shutil
import tarfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocollect import collect_job, dataset_path_for, _upsert_csv
from autocommon import (
    JOB_LIST,
    NW_LOGIC_DIR,
    group_jobs_by_node,
    log_event,
    normalize_node,
    read_jobs,
    run_id_for_job,
)
from autopex import run_pex_job
from autopnr import run_pnr_job
from autoprobe import CLOCK_GRID_NS
from autopwr import run_power_job
from autosim import run_simulation_job
from autosynth import CLOCK_UNCERTAINTY_NS, run_synthesis_job
from sweep_spec import power_modes

SWEEP_REPORTS_DIR = NW_LOGIC_DIR / "sweep_reports"
SWEEP_FAILURES = NW_LOGIC_DIR / "autosweep" / "sweep_failures.tsv"

# Report/log texts preserved per stage before the run directories are deleted;
# enough to re-collect or debug a row without re-running the tools.
_KEEP = {
    "01_syn": ("synthesis.log",),
    "02_pnr": ("qor.rpt", "utilization.rpt", "clock_qor.rpt", "clock_timing.rpt", "timing.rpt"),
    "03_pex": ("*.star_sum",),
    # sim*.log covers both the per-mode stashed logs (sim_<mode>.log) and a
    # bare sim.log left by a failed mode (stashing happens only on success);
    # vcs_compile.log diagnoses compile-stage failures
    "04_sim": ("sim*.log", "vcs_compile.log"),
    "05_pwr": (
        "power_summary.rpt",
        "power_hier.rpt",
        "timing.rpt",
        "global_timing.rpt",
        "constraint.rpt",
        "annotated_parasitics.rpt",
        "switching_activity.rpt",
        "pwr.log",
    ),
}
_STAGE_DIRS = tuple(_KEEP)

_CSV_LOCK = threading.Lock()
_FAIL_LOCK = threading.Lock()
_MANIFEST_LOCK = threading.Lock()


def _tech_dir(job: dict[str, str]) -> Path:
    return NW_LOGIC_DIR / f"TECH_{int(normalize_node(job['node'])):02d}nm"


_QOR_GROUP_RE = re.compile(r"Timing Path Group\s+'([^']+)'")
_QOR_SLACK_RE = re.compile(r"Critical Path Slack:\s+(-?[0-9.]+)")

# The timing gate trips only when a violation eats into the margin the
# SIMULATION actually has.  STA slack includes the 0.2 ns clock uncertainty,
# which is jitter margin that does not exist in the jitter-free SDF sim, and
# the TBs tolerate definite-value mismatches ("PASS marginal_errors=N")
# because random-stimulus toggle statistics do not depend on numerically
# exact captures (only unknown/X outputs abort).  The gate therefore only
# reacts to clocks so far past fmax that the whole netlist would compute
# garbage: 1.5x the uncertainty past zero.  A tripped gate is not a failure
# -- the sweep rederives a slower clock from the measured slack and moves on
# (probe periods are synthesis-only estimates; PnR routing can exceed their
# margin, 2026-08-07: 119 jobs, mxfpmac in2reg and comb-NoC in2out worst).
PNR_GATE_SLACK_NS = -(CLOCK_UNCERTAINTY_NS * 1.5)

# Attempts per job: the first rederivation uses the measured post-PnR slack,
# so it normally lands in one step; the second absorbs PnR noise on the new
# netlist.  Only an exhausted job is recorded as a pnr-timing failure.
PNR_CLOCK_ATTEMPTS = 3

# Added on top of the recovered slack before snapping up to the clock grid.
REDERIVE_MARGIN_NS = 0.05

# Path groups whose SDC budget is T/2: recovering slack s there needs the
# period to grow by 2*s (reg2reg / 'clk' needs s).
_HALF_BUDGET_TAGS = ("in2reg", "in2out", "reg2out")


def _pnr_violations(job: dict[str, str]) -> list[tuple[str, float]]:
    """(path group, slack) pairs beyond PNR_GATE_SLACK_NS in this job's
    post-PnR qor report; empty when timing is usable (or the report is
    missing -- the gate is advisory, not load-bearing)."""
    qor_path = _tech_dir(job) / "02_pnr" / run_id_for_job(job) / "qor.rpt"
    if not qor_path.exists():
        return []
    violations: list[tuple[str, float]] = []
    group = None
    for line in qor_path.read_text(encoding="utf-8", errors="replace").splitlines():
        group_match = _QOR_GROUP_RE.search(line)
        if group_match:
            group = group_match.group(1)
            continue
        slack_match = _QOR_SLACK_RE.search(line)
        if slack_match and group is not None:
            slack = float(slack_match.group(1))
            if slack < PNR_GATE_SLACK_NS:
                violations.append((group, slack))
            group = None
    return violations


def _violation_text(violations: list[tuple[str, float]]) -> str:
    return "; ".join(f"{group} slack {slack:g}" for group, slack in violations)


def rederived_period_ns(period_ns: float, violations: list[tuple[str, float]]) -> float:
    """Slower clock period that clears the measured violations, snapped up to
    the manifest clock grid (strictly slower than the input)."""
    need = max(
        (2.0 if any(tag in group for tag in _HALF_BUDGET_TAGS) else 1.0) * -slack
        for group, slack in violations
    )
    target = period_ns + need + REDERIVE_MARGIN_NS
    slower = math.ceil(target / CLOCK_GRID_NS - 1e-9) * CLOCK_GRID_NS
    if slower <= period_ns + 1e-9:
        slower = period_ns + CLOCK_GRID_NS
    return round(slower, 6)


def _patch_manifest_clocks(
    path: Path, proposals: dict[tuple[str, str, str, str], float], *, backup: bool
) -> dict[tuple[str, str, str, str], float]:
    """Rewrite manifest rows' clocks and return the final periods.

    proposals maps (rtl_name, arch_params, node, clock_period_ns as written)
    to a proposed period.  A proposal colliding with another clock of the
    same (rtl, arch, node) is bumped by grid steps so the config keeps
    distinct clocks (dataset diversity).  Comments and row order are
    preserved; the write is atomic.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    col: dict[str, int] = {}
    rows: list[tuple[int, list[str]]] = []
    for index, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            continue
        if not col:
            col = {name: j for j, name in enumerate(line.split("\t"))}
            continue
        rows.append((index, line.split("\t")))

    def config_of(fields: list[str]) -> tuple[str, str, str]:
        return fields[col["rtl_name"]], fields[col["arch_params"]], fields[col["node"]]

    periods: dict[tuple[str, str, str], set[float]] = defaultdict(set)
    for _, fields in rows:
        periods[config_of(fields)].add(round(float(fields[col["clock_period_ns"]]), 6))

    finals: dict[tuple[str, str, str, str], float] = {}
    for index, fields in rows:
        key = (*config_of(fields), fields[col["clock_period_ns"]])
        if key not in proposals:
            continue
        config = config_of(fields)
        periods[config].discard(round(float(fields[col["clock_period_ns"]]), 6))
        period = round(proposals[key], 6)
        while period in periods[config]:
            period = round(period + CLOCK_GRID_NS, 6)
        periods[config].add(period)
        fields[col["clock_period_ns"]] = f"{period:g}"
        fields[col["clock_freq_mhz"]] = f"{1000.0 / period:.6g}"
        lines[index] = "\t".join(fields)
        finals[key] = period

    missing = set(proposals) - set(finals)
    if missing:
        raise KeyError(f"manifest rows not found for clock patch: {sorted(missing)}")
    if backup:
        shutil.copyfile(path, path.with_suffix(".prev"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return finals


def _slow_down_job(job: dict[str, str], violations: list[tuple[str, float]]) -> None:
    """Move the job to a clock that clears the measured violations: persist it
    to the manifest (resume and future sweeps start there) and drop the
    too-fast attempt's artifacts before the run_id changes."""
    old_run_id = run_id_for_job(job)
    old_period = job["clock_period_ns"]
    key = (job["rtl_name"], job["arch_params"], job["node"], old_period)
    proposal = rederived_period_ns(float(old_period), violations)
    with _MANIFEST_LOCK:
        final = _patch_manifest_clocks(JOB_LIST, {key: proposal}, backup=False)[key]
    tech_dir = _tech_dir(job)
    for stage_dir in ("01_syn", "02_pnr"):
        shutil.rmtree(tech_dir / stage_dir / old_run_id, ignore_errors=True)
    job["clock_period_ns"] = f"{final:g}"
    job["clock_freq_mhz"] = f"{1000.0 / final:.6g}"
    detail = _violation_text(violations)
    print(
        f"[sweep] {old_run_id}: clock rederived to {job['clock_freq_mhz']} MHz ({detail})",
        flush=True,
    )
    log_event(
        stage="pnr-timing",
        status="running",
        message=f"clock rederived: {old_period} -> {job['clock_period_ns']} ns ({detail})",
        job=job,
    )


def _collected_modes(job: dict[str, str]) -> set[tuple[str, str]]:
    """(power_activity_mode, stim_mode) pairs already in the dataset for this job."""
    dataset = dataset_path_for(job["rtl_name"].strip())
    if not dataset.exists():
        return set()
    run_id = run_id_for_job(job)
    modes: set[tuple[str, str]] = set()
    with _CSV_LOCK, dataset.open(newline="", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            if row.get("flow_run_id") == run_id:
                modes.add(
                    (str(row.get("power_activity_mode", "")), str(row.get("stim_mode", "")))
                )
    return modes


def _required_modes(job: dict[str, str]) -> set[tuple[str, str]]:
    """Every (activity, stimulus) row a complete job must have in the dataset."""
    required = {("unvectored", "none")}
    required.update(
        ("vectored", mode)
        for mode in power_modes(job["rtl_name"].strip(), job.get("arch_params", ""))
    )
    return required


def _collect_row(job: dict[str, str]) -> None:
    record = collect_job(job)
    with _CSV_LOCK:
        _upsert_csv(dataset_path_for(record["rtl_name"]), record)


def _stage_keepers(job: dict[str, str], staging: Path, phase: str) -> None:
    """Copy the keep-listed report texts of every stage dir into the staging area."""
    run_id = run_id_for_job(job)
    tech_dir = _tech_dir(job)
    for stage, patterns in _KEEP.items():
        stage_run = tech_dir / stage / run_id
        if not stage_run.is_dir():
            continue
        dest = staging / f"{stage}{'_' + phase if stage == '05_pwr' else ''}"
        dest.mkdir(parents=True, exist_ok=True)
        for pattern in patterns:
            for source in stage_run.glob(pattern):
                if source.is_file():
                    shutil.copyfile(source, dest / source.name)


def _stash_failure_evidence(job: dict[str, str], staging: Path) -> None:
    """On failure, also archive the PnR netlist and SDF next to the reports.

    A sim failure is undiagnosable once the run dirs are pruned (2026-07-26:
    59 intmac gate sims produced X outputs with clean timing and the netlists
    were already gone).  Only the failure path pays the archive cost.
    """
    run_id = run_id_for_job(job)
    rtl_name = job["rtl_name"].strip()
    pnr_run = _tech_dir(job) / "02_pnr" / run_id
    dest = staging / "02_pnr"
    for name in (f"{rtl_name}_icc2.v", f"{rtl_name}.sdf"):
        source = pnr_run / name
        if source.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest / name)
    # The annotator log is the only record of unannotated arcs, which fall
    # back to the 1.0 ns specify defaults and silently corrupt gate sims.
    sim_source = _tech_dir(job) / "04_sim" / run_id / "sdf_annotate.log"
    if sim_source.is_file():
        sim_dest = staging / "04_sim"
        sim_dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sim_source, sim_dest / sim_source.name)


def _prune_job(job: dict[str, str], staging: Path) -> None:
    run_id = run_id_for_job(job)
    tech_dir = _tech_dir(job)
    SWEEP_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive = SWEEP_REPORTS_DIR / f"{run_id}.reports.tar.gz"
    if any(staging.iterdir()):
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=run_id)
    for stage in _STAGE_DIRS:
        shutil.rmtree(tech_dir / stage / run_id, ignore_errors=True)
    shutil.rmtree(staging, ignore_errors=True)


def _record_failure(job: dict[str, str], stage: str, error: Exception) -> None:
    message = f"{type(error).__name__}: {error}"
    with _FAIL_LOCK:
        new_file = not SWEEP_FAILURES.exists()
        with SWEEP_FAILURES.open("a", encoding="utf-8") as fp:
            if new_file:
                fp.write("run_id\tstage\terror\n")
            fp.write(
                "\t".join(
                    (run_id_for_job(job), stage, message[:300].replace("\t", " ").replace("\n", " "))
                )
                + "\n"
            )


def _new_staging(job: dict[str, str]) -> Path:
    staging = SWEEP_REPORTS_DIR / f".staging_{run_id_for_job(job)}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def run_sweep_job(job: dict[str, str], job_index: int) -> str:
    """Full chain for one job; returns 'done' | 'skipped' | 'failed:<stage>'."""
    if _required_modes(job) <= _collected_modes(job):
        return "skipped"

    staging: Path | None = None
    stage = "syn"
    try:
        for attempt in range(PNR_CLOCK_ATTEMPTS):
            stage = "syn"
            run_synthesis_job(job, job_index)
            stage = "pnr"
            run_pnr_job(job, job_index)
            stage = "pnr-timing"
            violations = _pnr_violations(job)
            if not violations:
                break
            if attempt == PNR_CLOCK_ATTEMPTS - 1:
                raise RuntimeError(
                    f"post-PnR setup timing still violated after "
                    f"{PNR_CLOCK_ATTEMPTS - 1} clock rederivations "
                    f"(threshold {PNR_GATE_SLACK_NS:g}: {_violation_text(violations)})"
                )
            _slow_down_job(job, violations)
        staging = _new_staging(job)
        stage = "pex"
        run_pex_job(job, job_index)
        stage = "sim"
        run_simulation_job(job, job_index)
        stage = "pwr-unvectored"
        run_power_job(job, job_index, vectored=False)
        stage = "collect-unvectored"
        _collect_row(job)
        _stage_keepers(job, staging, "unvectored")
        for mode in power_modes(job["rtl_name"].strip(), job.get("arch_params", "")):
            stage = f"pwr-vectored-{mode}"
            run_power_job(job, job_index, vectored=True, stim_mode=mode)
            stage = f"collect-vectored-{mode}"
            _collect_row(job)
            _stage_keepers(job, staging, f"vectored_{mode}")
    except Exception as exc:  # noqa: BLE001 - a sweep must survive bad jobs
        _record_failure(job, stage, exc)
        if staging is None:
            staging = _new_staging(job)
        _stage_keepers(job, staging, "failed")
        _stash_failure_evidence(job, staging)
        _prune_job(job, staging)
        return f"failed:{stage}"
    _prune_job(job, staging)
    return "done"


def _sweep_node(node: str, jobs: list[dict[str, str]], *, jobs_per_node: int) -> dict[str, int]:
    counts = {"done": 0, "skipped": 0, "failed": 0}
    total = len(jobs)

    def _finish(index: int, run_id: str, outcome: str) -> None:
        counts["failed" if outcome.startswith("failed") else outcome] += 1
        print(f"[sweep {node}nm] {index}/{total} {outcome} {run_id}", flush=True)

    if jobs_per_node <= 1:
        for index, job in enumerate(jobs, start=1):
            _finish(index, run_id_for_job(job), run_sweep_job(job, index))
        return counts

    with ThreadPoolExecutor(max_workers=jobs_per_node) as pool:
        futures = {
            pool.submit(run_sweep_job, job, index): run_id_for_job(job)
            for index, job in enumerate(jobs, start=1)
        }
        for index, future in enumerate(as_completed(futures), start=1):
            _finish(index, futures[future], future.result())
    return counts


def run_sweep(
    path: Path = JOB_LIST, *, jobs_per_node: int = 1, nodes: tuple[str, ...] | None = None
) -> None:
    jobs = read_jobs(path)
    if nodes:
        wanted = {normalize_node(node) for node in nodes}
        kept = [job for job in jobs if normalize_node(job["node"]) in wanted]
        print(
            f"sweep: node filter {sorted(wanted)} kept {len(kept)}/{len(jobs)} manifest jobs"
        )
        jobs = kept
    grouped = group_jobs_by_node(jobs)
    print(
        f"sweep: {len(jobs)} jobs across nodes {sorted(grouped)}; "
        f"{jobs_per_node} concurrent per node; reports -> {SWEEP_REPORTS_DIR}"
    )
    totals = {"done": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=max(1, len(grouped))) as pool:
        futures = [
            pool.submit(_sweep_node, node, node_jobs, jobs_per_node=jobs_per_node)
            for node, node_jobs in grouped.items()
        ]
        for future in as_completed(futures):
            for key, value in future.result().items():
                totals[key] += value
    print(
        f"sweep complete: {totals['done']} done, {totals['skipped']} skipped, "
        f"{totals['failed']} failed (see {SWEEP_FAILURES})"
    )


_FAILURE_SLACK_RE = re.compile(r"([A-Za-z0-9_*]+) slack (-?[0-9.]+)")


def rerun_failed(jobs_path: Path = JOB_LIST, failures_path: Path = SWEEP_FAILURES) -> None:
    """Move recorded pnr-timing failures to achievable clocks, then retire the
    failure log so the next sweep run starts clean.

    The sweep now rederives clocks in-flight; this applies the same math to
    failures recorded before that existed (or by exhausted retries), using the
    slack numbers embedded in the failure messages, so the next run starts
    each job directly at the corrected clock instead of rediscovering the
    violation with a wasted syn+PnR round.  Failures from other stages need
    no patching: jobs without complete dataset rows rerun automatically.
    """
    if not failures_path.exists():
        print(f"rerun-failed: no failure log at {failures_path}; nothing to do")
        return
    failures: dict[str, tuple[str, str]] = {}
    with failures_path.open(newline="", encoding="utf-8") as fp:
        for row in csv.DictReader(fp, delimiter="\t"):
            failures[row["run_id"]] = (row["stage"], row["error"])

    by_run_id = {run_id_for_job(job): job for job in read_jobs(jobs_path)}
    proposals: dict[tuple[str, str, str, str], float] = {}
    run_ids: dict[tuple[str, str, str, str], str] = {}
    passthrough = 0
    unmatched = 0
    for run_id, (stage, message) in sorted(failures.items()):
        job = by_run_id.get(run_id)
        if job is None:
            unmatched += 1
            continue
        violations = (
            [(group.strip("*"), float(slack)) for group, slack in _FAILURE_SLACK_RE.findall(message)]
            if stage == "pnr-timing"
            else []
        )
        if not violations:
            passthrough += 1
            continue
        key = (job["rtl_name"], job["arch_params"], job["node"], job["clock_period_ns"])
        proposals[key] = rederived_period_ns(float(job["clock_period_ns"]), violations)
        run_ids[key] = run_id

    if proposals:
        finals = _patch_manifest_clocks(jobs_path, proposals, backup=True)
        for key in sorted(finals):
            old_mhz = 1000.0 / float(key[3])
            new_mhz = 1000.0 / finals[key]
            print(f"rerun-failed: {run_ids[key]}: {old_mhz:.6g} -> {new_mhz:.6g} MHz")
        print(f"rerun-failed: manifest backed up to {jobs_path.with_suffix('.prev')}")

    retired = failures_path.with_suffix(".prev.tsv")
    shutil.move(failures_path, retired)
    print(
        f"rerun-failed: {len(proposals)} clock(s) patched, {passthrough} failure(s) "
        f"rerun as-is, {unmatched} without a manifest row; log retired to {retired}"
    )
