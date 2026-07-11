from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocommon import (
    JOB_LIST,
    NW_LOGIC_DIR,
    STAGE_LOGIC_SIM,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_START,
    STATUS_TERMINATED,
    find_tech_corner,
    group_jobs_by_node,
    log_event,
    normalize_node,
    read_jobs,
    recreate_run_dir,
    run_id_for_job,
    run_logged_command,
)
from rtl_gen import generator


SIM_MODEL_EXTENSIONS = {".v", ".sv", ".vg", ".vlog", ".verilog"}


def discover_std_cell_models(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        file_path
        for file_path in directory.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in SIM_MODEL_EXTENSIONS
    )


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("could not find matching ')' for DUT parameter override")


def _gate_level_testbench_text(text: str, rtl_name: str, sdf_name: str) -> str:
    tb_match = re.search(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b", text)
    if not tb_match:
        raise ValueError("could not find testbench module declaration")
    tb_module = tb_match.group(1)

    inst_pattern = re.compile(rf"(?m)^(\s*){re.escape(rtl_name)}\s*#\s*\(")
    inst_match = inst_pattern.search(text)
    if not inst_match:
        raise ValueError(f"could not find parameterized DUT instantiation for {rtl_name}")

    open_index = text.find("(", inst_match.start())
    close_index = _find_matching_paren(text, open_index)
    tail_match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\(", text[close_index + 1 :])
    if not tail_match:
        raise ValueError("could not find DUT instance name after parameter override")

    indent = inst_match.group(1)
    instance_name = tail_match.group(1)
    replace_end = close_index + 1 + tail_match.end()
    text = (
        text[: inst_match.start()]
        + f"{indent}{rtl_name} {instance_name} ("
        + text[replace_end:]
    )

    gate_hook = f"""
`ifdef NW_LOGIC_GATE_SIM
    initial begin
        $sdf_annotate("{sdf_name}", {instance_name},, "sdf_annotate.log", "MAXIMUM");
        $dumpfile("sim.vcd");
        $dumpvars(0, {tb_module});
    end
`endif

"""
    always_match = re.search(r"(?m)^\s*always\b", text)
    if not always_match:
        raise ValueError("could not find insertion point before the testbench clock generator")
    return text[: always_match.start()] + gate_hook + text[always_match.start() :]


def prepare_simulation_run(job: dict[str, str], run_dir: Path) -> Path:
    rtl_name = job["rtl_name"].strip()
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    pnr_dir = tech_dir / "02_pnr" / run_id
    corner = find_tech_corner(job)

    pnr_netlist = pnr_dir / f"{rtl_name}_icc2.v"
    pnr_sdf = pnr_dir / f"{rtl_name}.sdf"
    rtl_tb = generator.RTL_DIR / rtl_name / f"{rtl_name}_tb.sv"
    if not pnr_netlist.exists():
        raise FileNotFoundError(f"missing post-PnR netlist: {pnr_netlist}")
    if not pnr_sdf.exists():
        raise FileNotFoundError(f"missing post-PnR SDF: {pnr_sdf}")
    if not rtl_tb.exists():
        raise FileNotFoundError(f"missing generated RTL testbench: {rtl_tb}")

    recreate_run_dir(run_dir)
    netlist_path = run_dir / pnr_netlist.name
    sdf_path = run_dir / pnr_sdf.name
    tb_path = run_dir / f"{rtl_name}_gate_tb.sv"
    models_path = run_dir / "stdcell_models.f"
    filelist_path = run_dir / "04_sim.f"

    shutil.copyfile(pnr_netlist, netlist_path)
    shutil.copyfile(pnr_sdf, sdf_path)
    tb_path.write_text(
        _gate_level_testbench_text(rtl_tb.read_text(encoding="utf-8"), rtl_name, sdf_path.name),
        encoding="utf-8",
    )

    model_files = discover_std_cell_models(corner.directory)
    with models_path.open("w", encoding="utf-8") as fp:
        fp.write(f"// DB reference for this corner: {corner.db_file}\n")
        if model_files:
            for model_file in model_files:
                fp.write(f"{model_file}\n")
        else:
            fp.write("// No Verilog standard-cell simulation models were found under the tech library directory.\n")
            fp.write("// Add model paths here, or set STD_CELL_MODELS_F / STD_CELL_MODELS when running 04_sim.sh.\n")

    with filelist_path.open("w", encoding="utf-8") as fp:
        fp.write("+define+NW_LOGIC_GATE_SIM\n")
        fp.write("+libext+.v+.sv\n")
        fp.write("-f stdcell_models.f\n")
        fp.write(f"{netlist_path.name}\n")
        fp.write(f"{tb_path.name}\n")

    return filelist_path


def run_simulation_job(job: dict[str, str], job_index: int, *, verbose: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "04_sim" / run_id
    corner = find_tech_corner(job)

    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_RUNNING,
        message="preparing gate-level simulation run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "db_file": str(corner.db_file),
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    filelist_path = prepare_simulation_run(job, run_dir)
    sim_runner = tech_dir / "run_scripts" / "04_sim.sh"
    if not sim_runner.exists():
        raise FileNotFoundError(f"missing simulation runner: {sim_runner}")

    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_RUNNING,
        message="launching 04_sim.sh",
        job=job,
        run_id=run_id,
        details={"command": f"{sim_runner} {run_id}", "run_dir": str(run_dir), "filelist": str(filelist_path)},
    )

    runner_log_path = run_dir / "04_sim.sh.log"
    returncode = run_logged_command(
        [str(sim_runner), run_id],
        cwd=sim_runner.parent,
        log_path=runner_log_path,
        verbose=verbose,
        prefix=run_id,
    )

    sim_log = run_dir / "sim.log"
    vcd_path = run_dir / "sim.vcd"
    if returncode != 0:
        log_event(
            stage=STAGE_LOGIC_SIM,
            status=STATUS_ERROR,
            message=f"04_sim.sh failed with exit code {returncode}",
            job=job,
            run_id=run_id,
            details={
                "sim_log": str(sim_log),
                "runner_log": str(runner_log_path),
                "run_dir": str(run_dir),
            },
        )
        raise RuntimeError(f"gate-level simulation failed for {run_id}; see {sim_log}")

    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_DONE,
        message="gate-level simulation complete",
        job=job,
        run_id=run_id,
        details={
            "sim_log": str(sim_log),
            "vcd": str(vcd_path),
        },
    )


def run_simulation_for_node(node: str, jobs: list[dict[str, str]], *, verbose: bool = False) -> None:
    log_event(stage=STAGE_LOGIC_SIM, status=STATUS_START, message="node simulation worker started", node=node)
    for index, job in enumerate(jobs, start=1):
        run_simulation_job(job, index, verbose=verbose)
    log_event(stage=STAGE_LOGIC_SIM, status=STATUS_DONE, message="node simulation worker complete", node=node)


def run_simulation_from_manifest(path: Path = JOB_LIST, *, verbose: bool = False) -> None:
    jobs = read_jobs(path)
    grouped = group_jobs_by_node(jobs)
    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_START,
        message="gate-level simulation stage started",
        details={"nodes": sorted(grouped)},
    )

    with ThreadPoolExecutor(max_workers=max(1, len(grouped))) as executor:
        futures = {
            executor.submit(run_simulation_for_node, node, node_jobs, verbose=verbose): node
            for node, node_jobs in grouped.items()
        }
        for future in as_completed(futures):
            node = futures[future]
            try:
                future.result()
            except Exception as exc:
                log_event(
                    stage=STAGE_LOGIC_SIM,
                    status=STATUS_TERMINATED,
                    message=f"node simulation worker terminated: {exc}",
                    node=node,
                    details={"error_type": type(exc).__name__},
                )
                raise

    log_event(stage=STAGE_LOGIC_SIM, status=STATUS_DONE, message="gate-level simulation stage complete")
