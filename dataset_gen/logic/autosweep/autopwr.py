from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocommon import (
    JOB_LIST,
    MASTER_TCL_DIR,
    NW_LOGIC_DIR,
    STAGE_POWER_SIM,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_START,
    STATUS_TERMINATED,
    clock_period_ns,
    find_tech_corner,
    group_jobs_by_node,
    log_event,
    normalize_node,
    read_jobs,
    recreate_run_dir,
    run_id_for_job,
    run_jobs_for_node,
    run_logged_command,
)


def _set_tcl_var(text: str, name: str, value: str | float) -> str:
    if isinstance(value, str):
        new_line = f'set {name:<15} "{value}"'
    else:
        new_line = f"set {name:<15} {value:g}"

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(f"set {name}"):
            lines[index] = new_line
            return "\n".join(lines) + "\n"
    raise ValueError(f"PrimeTime template missing variable: {name}")


def _vectored_activity_file(tech_dir: Path, run_id: str) -> Path:
    sim_dir = tech_dir / "04_sim" / run_id
    for candidate in (sim_dir / "sim.saif", sim_dir / "sim.vcd"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"missing vectored activity file: expected {sim_dir}/sim.saif or {sim_dir}/sim.vcd")


def prepare_power_script(job: dict[str, str], run_dir: Path, *, vectored: bool = False) -> Path:
    rtl_name = job["rtl_name"].strip()
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    pnr_dir = tech_dir / "02_pnr" / run_id
    pex_dir = tech_dir / "03_pex" / run_id
    corner = find_tech_corner(job)

    master_script = MASTER_TCL_DIR / "05_pwr.tcl"
    if not master_script.exists():
        raise FileNotFoundError(f"missing PrimeTime power template: {master_script}")

    netlist_path = pnr_dir / f"{rtl_name}_icc2.v"
    sdc_path = pnr_dir / f"{rtl_name}.sdc"
    spef_path = pex_dir / f"{rtl_name}.spef"
    if not netlist_path.exists():
        raise FileNotFoundError(f"missing post-PnR netlist: {netlist_path}")
    if not sdc_path.exists():
        raise FileNotFoundError(f"missing timing constraints: {sdc_path}")
    if not spef_path.exists():
        raise FileNotFoundError(f"missing PEX SPEF: {spef_path}")

    activity_file = _vectored_activity_file(tech_dir, run_id) if vectored else None

    recreate_run_dir(run_dir)
    script_path = run_dir / "05_pwr.tcl"
    shutil.copyfile(master_script, script_path)

    text = script_path.read_text(encoding="utf-8")
    text = _set_tcl_var(text, "top_design", rtl_name)
    text = _set_tcl_var(text, "target_library", str(corner.db_file))
    text = _set_tcl_var(text, "netlist_file", str(netlist_path))
    text = _set_tcl_var(text, "sdc_file", str(sdc_path))
    text = _set_tcl_var(text, "spef_file", str(spef_path))
    text = _set_tcl_var(text, "activity_mode", "vectored" if vectored else "unvectored")
    text = _set_tcl_var(text, "activity_file", str(activity_file) if activity_file else "")
    text = _set_tcl_var(text, "clock_period_ns", clock_period_ns(job))

    clock_port = job.get("clock_port", "").strip() or "i_clk"
    text = text.replace("__CLOCK_PORTS__", clock_port)

    script_path.write_text(text, encoding="utf-8")
    return script_path


def run_power_job(job: dict[str, str], job_index: int, *, verbose: bool = False, vectored: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "05_pwr" / run_id
    corner = find_tech_corner(job)

    log_event(
        stage=STAGE_POWER_SIM,
        status=STATUS_RUNNING,
        message="preparing PrimeTime power run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "db_file": str(corner.db_file),
            "mode": "vectored" if vectored else "unvectored",
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    script_path = prepare_power_script(job, run_dir, vectored=vectored)
    pwr_runner = tech_dir / "run_scripts" / "05_pwr.sh"
    if not pwr_runner.exists():
        raise FileNotFoundError(f"missing PrimeTime power runner: {pwr_runner}")

    log_event(
        stage=STAGE_POWER_SIM,
        status=STATUS_RUNNING,
        message="launching 05_pwr.sh",
        job=job,
        run_id=run_id,
        details={"command": f"{pwr_runner} {run_id}", "run_dir": str(run_dir), "script": str(script_path)},
    )

    runner_log_path = run_dir / "05_pwr.sh.log"
    returncode = run_logged_command(
        [str(pwr_runner), run_id],
        cwd=pwr_runner.parent,
        log_path=runner_log_path,
        verbose=verbose,
        prefix=run_id,
    )

    pt_log = run_dir / "pwr.log"
    report_path = run_dir / "power.rpt"
    if returncode != 0:
        log_event(
            stage=STAGE_POWER_SIM,
            status=STATUS_ERROR,
            message=f"05_pwr.sh failed with exit code {returncode}",
            job=job,
            run_id=run_id,
            details={
                "pt_log": str(pt_log),
                "runner_log": str(runner_log_path),
                "run_dir": str(run_dir),
            },
        )
        raise RuntimeError(f"PrimeTime power failed for {run_id}; see {pt_log}")

    log_event(
        stage=STAGE_POWER_SIM,
        status=STATUS_DONE,
        message="PrimeTime power complete",
        job=job,
        run_id=run_id,
        details={
            "pt_log": str(pt_log),
            "report": str(report_path),
        },
    )


def run_power_for_node(
    node: str,
    jobs: list[dict[str, str]],
    *,
    verbose: bool = False,
    vectored: bool = False,
    jobs_per_node: int = 1,
) -> None:
    log_event(stage=STAGE_POWER_SIM, status=STATUS_START, message="node power worker started", node=node)
    run_jobs_for_node(
        jobs,
        lambda job, index: run_power_job(job, index, verbose=verbose, vectored=vectored),
        jobs_per_node=jobs_per_node,
    )
    log_event(stage=STAGE_POWER_SIM, status=STATUS_DONE, message="node power worker complete", node=node)


def run_power_from_manifest(
    path: Path = JOB_LIST,
    *,
    verbose: bool = False,
    vectored: bool = False,
    jobs_per_node: int = 1,
) -> None:
    jobs = read_jobs(path)
    grouped = group_jobs_by_node(jobs)
    log_event(
        stage=STAGE_POWER_SIM,
        status=STATUS_START,
        message="PrimeTime power stage started",
        details={
            "nodes": sorted(grouped),
            "mode": "vectored" if vectored else "unvectored",
            "jobs_per_node": jobs_per_node,
        },
    )

    with ThreadPoolExecutor(max_workers=max(1, len(grouped))) as executor:
        futures = {
            executor.submit(
                run_power_for_node,
                node,
                node_jobs,
                verbose=verbose,
                vectored=vectored,
                jobs_per_node=jobs_per_node,
            ): node
            for node, node_jobs in grouped.items()
        }
        for future in as_completed(futures):
            node = futures[future]
            try:
                future.result()
            except Exception as exc:
                log_event(
                    stage=STAGE_POWER_SIM,
                    status=STATUS_TERMINATED,
                    message=f"node power worker terminated: {exc}",
                    node=node,
                    details={"error_type": type(exc).__name__},
                )
                raise

    log_event(stage=STAGE_POWER_SIM, status=STATUS_DONE, message="PrimeTime power stage complete")
