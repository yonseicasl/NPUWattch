"""Storage-bounded sweep driver: one full flow chain per job, then prune.

Unlike the stage-wise run_batch stages (all jobs' syn, then all jobs' pnr,
...), this driver pipelines each job through

    syn -> pnr -> pex -> sim (one gate-level run per stimulus mode)
        -> pwr(unvectored)          -> CSV row
        -> pwr(vectored, mode) x N  -> CSV row each   (N = power_modes(module))
    -> archive report texts -> delete the run directories

so the heavy EDA artifacts on disk at any moment belong only to the jobs
currently executing (nodes x jobs_per_node of them), not to the whole sweep.

Crash resume: a job whose dataset CSV already holds the unvectored row AND
one vectored row per stimulus mode of its module is skipped, so re-running
the same command continues where the previous invocation stopped.  NOTE the
flip side of the storage bounding: because run directories are deleted after
collection, adding a NEW mode to POWER_MODES later re-runs the whole EDA
chain for the affected jobs -- extend the mode list before a sweep, not
after.  Failures are recorded in sweep_failures.tsv and do not stop the
sweep.
"""
from __future__ import annotations

import csv
import re
import shutil
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocollect import collect_job, dataset_path_for, _upsert_csv
from autocommon import (
    JOB_LIST,
    NW_LOGIC_DIR,
    group_jobs_by_node,
    normalize_node,
    read_jobs,
    run_id_for_job,
)
from autopex import run_pex_job
from autopnr import run_pnr_job
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


def _tech_dir(job: dict[str, str]) -> Path:
    return NW_LOGIC_DIR / f"TECH_{int(normalize_node(job['node'])):02d}nm"


_QOR_GROUP_RE = re.compile(r"Timing Path Group\s+'([^']+)'")
_QOR_SLACK_RE = re.compile(r"Critical Path Slack:\s+(-?[0-9.]+)")

# The gate trips only when a violation eats into the margin the SIMULATION
# actually has.  STA slack includes the 0.2 ns clock uncertainty, which is
# jitter margin that does not exist in the jitter-free SDF sim: a run at STA
# slack s still has s + 0.2 ns of real sim margin.  ICC2 routinely lands a
# few hundredths negative after DC met (2026-07-26: p50 of gate hits was
# -0.03, 97% within the uncertainty; the old sweep had 1,682 such runs pass
# their gate sims, with functional failures only from about -0.23).  Failing
# at half the uncertainty keeps >=0.1 ns of true sim margin while discarding
# only genuinely unachievable clocks.
PNR_GATE_SLACK_NS = -(CLOCK_UNCERTAINTY_NS / 2.0)


def _check_pnr_timing(job: dict[str, str]) -> None:
    """Fail fast on post-PnR setup violations deep enough to corrupt the SDF
    gate sim (2026-07-20: 162/164 sim failures were unmet clocks), instead of
    letting the netlist reach sim where they surface as confusing checker
    FAILs.  Raises RuntimeError listing every path group below
    PNR_GATE_SLACK_NS; silently returns if the qor report is missing (the
    gate is advisory, not load-bearing).
    """
    qor_path = _tech_dir(job) / "02_pnr" / run_id_for_job(job) / "qor.rpt"
    if not qor_path.exists():
        return
    text = qor_path.read_text(encoding="utf-8", errors="replace")
    violated: list[str] = []
    group = None
    for line in text.splitlines():
        group_match = _QOR_GROUP_RE.search(line)
        if group_match:
            group = group_match.group(1)
            continue
        slack_match = _QOR_SLACK_RE.search(line)
        if slack_match and group is not None:
            slack = float(slack_match.group(1))
            if slack < PNR_GATE_SLACK_NS:
                violated.append(f"{group} slack {slack:g}")
            group = None
    if violated:
        raise RuntimeError(
            "post-PnR setup timing violated beyond the sim margin "
            f"(threshold {PNR_GATE_SLACK_NS:g}: " + "; ".join(violated) + ") -- "
            "the job clock is not achievable; gen-jobs should derive a slower one"
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


def run_sweep_job(job: dict[str, str], job_index: int) -> str:
    """Full chain for one job; returns 'done' | 'skipped' | 'failed:<stage>'."""
    run_id = run_id_for_job(job)
    if _required_modes(job) <= _collected_modes(job):
        return "skipped"

    staging = SWEEP_REPORTS_DIR / f".staging_{run_id}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    stage = "syn"
    try:
        run_synthesis_job(job, job_index)
        stage = "pnr"
        run_pnr_job(job, job_index)
        stage = "pnr-timing"
        _check_pnr_timing(job)
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
