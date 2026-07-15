"""Storage-bounded sweep driver: one full flow chain per job, then prune.

Unlike the stage-wise run_batch stages (all jobs' syn, then all jobs' pnr,
...), this driver pipelines each job through

    syn -> pnr -> pex -> sim -> pwr(unvectored) -> CSV row
                              -> pwr(vectored)   -> CSV row
    -> archive report texts -> delete the run directories

so the heavy EDA artifacts on disk at any moment belong only to the jobs
currently executing (nodes x jobs_per_node of them), not to the whole sweep.

Crash resume: a job whose dataset CSV already holds both activity-mode rows
for its run id is skipped, so re-running the same command continues where
the previous invocation stopped. Failures are recorded in
sweep_failures.tsv and do not stop the sweep.
"""
from __future__ import annotations

import csv
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
from autosynth import run_synthesis_job

SWEEP_REPORTS_DIR = NW_LOGIC_DIR / "sweep_reports"
SWEEP_FAILURES = NW_LOGIC_DIR / "autosweep" / "sweep_failures.tsv"

# Report/log texts preserved per stage before the run directories are deleted;
# enough to re-collect or debug a row without re-running the tools.
_KEEP = {
    "01_syn": ("synthesis.log",),
    "02_pnr": ("qor.rpt", "utilization.rpt", "clock_qor.rpt", "clock_timing.rpt", "timing.rpt"),
    "03_pex": ("*.star_sum",),
    "04_sim": ("sim.log",),
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


def _collected_modes(job: dict[str, str]) -> set[str]:
    dataset = dataset_path_for(job["rtl_name"].strip())
    if not dataset.exists():
        return set()
    run_id = run_id_for_job(job)
    modes: set[str] = set()
    with _CSV_LOCK, dataset.open(newline="", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            if row.get("flow_run_id") == run_id:
                modes.add(str(row.get("power_activity_mode", "")))
    return modes


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
    if {"unvectored", "vectored"} <= _collected_modes(job):
        return "skipped"

    staging = SWEEP_REPORTS_DIR / f".staging_{run_id}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    stage = "syn"
    try:
        run_synthesis_job(job, job_index)
        stage = "pnr"
        run_pnr_job(job, job_index)
        stage = "pex"
        run_pex_job(job, job_index)
        stage = "sim"
        run_simulation_job(job, job_index)
        stage = "pwr-unvectored"
        run_power_job(job, job_index, vectored=False)
        stage = "collect-unvectored"
        _collect_row(job)
        _stage_keepers(job, staging, "unvectored")
        stage = "pwr-vectored"
        run_power_job(job, job_index, vectored=True)
        stage = "collect-vectored"
        _collect_row(job)
        _stage_keepers(job, staging, "vectored")
    except Exception as exc:  # noqa: BLE001 - a sweep must survive bad jobs
        _record_failure(job, stage, exc)
        _stage_keepers(job, staging, "failed")
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
