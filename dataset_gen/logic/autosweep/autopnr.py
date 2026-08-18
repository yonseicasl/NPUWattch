from __future__ import annotations

import shutil
from pathlib import Path

from autocommon import (
    MASTER_TCL_DIR,
    NW_LOGIC_DIR,
    STAGE_PNR,
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


def prepare_pnr_script(job: dict[str, str], run_dir: Path) -> Path:
    rtl_name = job["rtl_name"].strip()
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    syn_dir = tech_dir / "01_syn" / run_id
    corner = find_tech_corner(job)

    master_script = MASTER_TCL_DIR / "02_pnr.tcl"
    if not master_script.exists():
        raise FileNotFoundError(f"missing PnR template: {master_script}")

    syn_netlist = syn_dir / f"{rtl_name}_syn.v"
    syn_sdc = syn_dir / f"{rtl_name}.sdc"
    if not syn_netlist.exists():
        raise FileNotFoundError(f"missing synthesis netlist: {syn_netlist}")
    if not syn_sdc.exists():
        raise FileNotFoundError(f"missing synthesis SDC: {syn_sdc}")

    recreate_run_dir(run_dir)
    script_path = run_dir / "02_pnr.tcl"
    shutil.copyfile(master_script, script_path)
    shutil.copyfile(syn_netlist, run_dir / syn_netlist.name)
    shutil.copyfile(syn_sdc, run_dir / syn_sdc.name)

    text = script_path.read_text(encoding="utf-8")
    replacements = {
        "MyDesign": rtl_name,
        "./../MyNDMFile": str(corner.ndm_file),
        "./../MyTechFile": str(corner.tech_file),
        "./../MyTLUFile": str(corner.tlu_file),
        "./../MyMapFile": str(corner.map_file),
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"PnR template missing expected text: {old}")
        text = text.replace(old, new)

    script_path.write_text(text, encoding="utf-8")
    return script_path


def run_pnr_job(job: dict[str, str], job_index: int, *, verbose: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "02_pnr" / run_id
    corner = find_tech_corner(job)

    log_event(
        stage=STAGE_PNR,
        status=STATUS_RUNNING,
        message="preparing PnR run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "ndm_file": str(corner.ndm_file),
            "tech_file": str(corner.tech_file),
            "tlu_file": str(corner.tlu_file),
            "map_file": str(corner.map_file),
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    script_path = prepare_pnr_script(job, run_dir)
    pnr_runner = tech_dir / "run_scripts" / "02_pnr.sh"
    if not pnr_runner.exists():
        raise FileNotFoundError(f"missing PnR runner: {pnr_runner}")

    log_event(
        stage=STAGE_PNR,
        status=STATUS_RUNNING,
        message="launching 02_pnr.sh",
        job=job,
        run_id=run_id,
        details={"command": f"{pnr_runner} {run_id}", "run_dir": str(run_dir), "script": str(script_path)},
    )

    runner_log_path = run_dir / "02_pnr.sh.log"
    returncode = run_logged_command(
        [str(pnr_runner), run_id],
        cwd=pnr_runner.parent,
        log_path=runner_log_path,
        verbose=verbose,
        prefix=run_id,
    )

    rtl_name = job["rtl_name"].strip()
    log_path = run_dir / "pnr.log"
    netlist_path = run_dir / f"{rtl_name}_icc2.v"
    sdf_path = run_dir / f"{rtl_name}.sdf"
    gds_path = run_dir / f"{rtl_name}.gds"
    def_path = run_dir / f"{rtl_name}.def"
    if returncode != 0:
        log_event(
            stage=STAGE_PNR,
            status=STATUS_ERROR,
            message=f"02_pnr.sh failed with exit code {returncode}",
            job=job,
            run_id=run_id,
            details={
                "log": str(log_path),
                "runner_log": str(runner_log_path),
                "run_dir": str(run_dir),
            },
        )
        raise RuntimeError(f"PnR failed for {run_id}; see {log_path}")

    log_event(
        stage=STAGE_PNR,
        status=STATUS_DONE,
        message="PnR complete",
        job=job,
        run_id=run_id,
        details={
            "log": str(log_path),
            "netlist": str(netlist_path),
            "sdf": str(sdf_path),
            "gds": str(gds_path),
            "def": str(def_path),
        },
    )
