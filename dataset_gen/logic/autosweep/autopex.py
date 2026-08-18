from __future__ import annotations

import shutil
from pathlib import Path

from autocommon import (
    MASTER_TCL_DIR,
    NW_LOGIC_DIR,
    STAGE_PEX,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    find_tech_corner,
    log_event,
    normalize_node,
    recreate_run_dir,
    run_id_for_job,
    run_logged_command,
)


def prepare_pex_script(job: dict[str, str], run_dir: Path) -> Path:
    rtl_name = job["rtl_name"].strip()
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    pnr_dir = tech_dir / "02_pnr" / run_id
    corner = find_tech_corner(job)

    master_script = MASTER_TCL_DIR / "03_pex.strc"
    if not master_script.exists():
        raise FileNotFoundError(f"missing PEX template: {master_script}")

    ndm_database = pnr_dir / rtl_name
    if not ndm_database.exists():
        raise FileNotFoundError(f"missing ICC2 NDM database: {ndm_database}")

    recreate_run_dir(run_dir)
    script_path = run_dir / "03_pex.strc"
    shutil.copyfile(master_script, script_path)

    text = script_path.read_text(encoding="utf-8")
    replacements = {
        "./../../02_pnr/ICC2_MyDesign/MyDesign": str(ndm_database),
        "MyDesign/route_opt": f"{rtl_name}/route_opt",
        "./../MyGRDFile": str(corner.grd_file),
        "./../MyMapFile": str(corner.map_file),
        "STRC_TEMPERATURE": job.get("temp", "").strip() or corner.temp,
        "MyDesign.spef": f"{rtl_name}.spef",
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"PEX template missing expected text: {old}")
        text = text.replace(old, new)

    script_path.write_text(text, encoding="utf-8")
    return script_path


def run_pex_job(job: dict[str, str], job_index: int, *, verbose: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "03_pex" / run_id
    corner = find_tech_corner(job)

    log_event(
        stage=STAGE_PEX,
        status=STATUS_RUNNING,
        message="preparing PEX run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "grd_file": str(corner.grd_file),
            "map_file": str(corner.map_file),
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    script_path = prepare_pex_script(job, run_dir)
    pex_runner = tech_dir / "run_scripts" / "03_pex.sh"
    if not pex_runner.exists():
        raise FileNotFoundError(f"missing PEX runner: {pex_runner}")

    log_event(
        stage=STAGE_PEX,
        status=STATUS_RUNNING,
        message="launching 03_pex.sh",
        job=job,
        run_id=run_id,
        details={"command": f"{pex_runner} {run_id}", "run_dir": str(run_dir), "script": str(script_path)},
    )

    runner_log_path = run_dir / "03_pex.sh.log"
    returncode = run_logged_command(
        [str(pex_runner), run_id],
        cwd=pex_runner.parent,
        log_path=runner_log_path,
        verbose=verbose,
        prefix=run_id,
    )

    spef_path = run_dir / f"{job['rtl_name'].strip()}.spef"
    log_path = run_dir / "pex.log"
    if returncode != 0:
        log_event(
            stage=STAGE_PEX,
            status=STATUS_ERROR,
            message=f"03_pex.sh failed with exit code {returncode}",
            job=job,
            run_id=run_id,
            details={
                "log": str(log_path),
                "runner_log": str(runner_log_path),
                "run_dir": str(run_dir),
            },
        )
        raise RuntimeError(f"PEX failed for {run_id}; see {log_path}")

    log_event(
        stage=STAGE_PEX,
        status=STATUS_DONE,
        message="PEX complete",
        job=job,
        run_id=run_id,
        details={
            "log": str(log_path),
            "spef": str(spef_path),
        },
    )
