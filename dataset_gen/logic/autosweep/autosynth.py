from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from autocommon import (
    JOB_LIST,
    MASTER_TCL_DIR,
    NW_LOGIC_DIR,
    STAGE_SYN,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_START,
    STATUS_TERMINATED,
    clock_period_ns,
    find_tech_corner,
    group_jobs_by_node,
    inject_between_markers,
    log_event,
    normalize_node,
    read_jobs,
    recreate_run_dir,
    rtl_variant_dir_name,
    run_id_for_job,
    run_jobs_for_node,
    run_logged_command,
)
from rtl_gen import generator


def dc_append_script(job: dict[str, str], dont_use: tuple[str, ...] = ()) -> str:
    period = clock_period_ns(job)
    half_period = period / 2.0
    clock_port = job.get("clock_port", "").strip() or "i_clk"
    reset_port = job.get("reset_port", "").strip()

    lines = []
    # Node-level cell exclusions from tech_libs/catalog.json ("dontuse"). Keeps
    # the mapped cell set uniform across nodes; a typo'd cell name makes
    # get_lib_cells return nothing and DC error out, which is the right failure.
    for cell in dont_use:
        lines.append(f"set_dont_use [get_lib_cells */{cell}]")
    # One uniform snippet for every module: a design that has the clock port
    # gets a real clock; a purely combinational one (the NoC blocks) gets a
    # virtual clock with zero I/O delays, so every in->out path must fit in
    # one cycle and the job's frequency axis keeps its meaning.
    lines += [
        f"set clockPorts [get_ports -quiet {{{clock_port}}}]",
        "if {[sizeof_collection $clockPorts] > 0} {",
        f"    create_clock -name clk $clockPorts -period {period:g} -waveform {{0 {half_period:g}}}",
        "} else {",
        "    # Combinational block: virtual clock constrains the in->out paths.",
        f"    create_clock -name clk -period {period:g} -waveform {{0 {half_period:g}}}",
        "    set_input_delay 0 -clock clk [all_inputs]",
        "    set_output_delay 0 -clock clk [all_outputs]",
        "}",
        "set_clock_uncertainty 0.2 [get_clocks clk]",
    ]
    if reset_port:
        lines.extend(
            [
                f"set resetPorts [get_ports {{{reset_port}}}]",
                "set_false_path -from $resetPorts",
            ]
        )
    return "\n".join(lines)


def prepare_synthesis_script(job: dict[str, str], run_dir: Path) -> Path:
    rtl_name = job["rtl_name"].strip()
    corner = find_tech_corner(job)
    master_script = MASTER_TCL_DIR / "01_syn.tcl"
    if not master_script.exists():
        raise FileNotFoundError(f"missing synthesis template: {master_script}")

    rtl_dir = generator.RTL_DIR / rtl_variant_dir_name(job) / rtl_name
    if not rtl_dir.exists():
        raise FileNotFoundError(f"missing generated RTL directory: {rtl_dir}")

    recreate_run_dir(run_dir)
    script_path = run_dir / "01_syn.tcl"
    shutil.copyfile(master_script, script_path)

    text = script_path.read_text(encoding="utf-8")
    replacements = {
        "set topModule  MyDesign": f"set topModule  {rtl_name}",
        "set printModule ./MyDesign": f"set printModule ./{rtl_name}",
        "set verilogDir  ./../../../rtl/MyDesign": f"set verilogDir  {rtl_dir}",
        "set target_library ./../MyDBFile": f"set target_library {corner.db_file}",
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"synthesis template missing expected text: {old}")
        text = text.replace(old, new)

    old_read_block = (
        "read_file -autoread -format verilog   $verilogDir -top $topModule\n"
        "read_file -autoread -format sverilog  $verilogDir -top $topModule"
    )
    new_read_block = "read_file -format sverilog ${verilogDir}/${topModule}.sv"
    if old_read_block not in text:
        raise ValueError("synthesis template missing expected read_file block")
    text = text.replace(old_read_block, new_read_block)
    text = text.replace("elaborate $topModule\n\n", "")

    text = inject_between_markers(
        text,
        "#START_OF_DC_APPENDED_SCRIPT",
        "#END_OF_DC_APPENDED_SCRIPT",
        dc_append_script(job, corner.dont_use),
    )
    script_path.write_text(text, encoding="utf-8")
    return script_path


def run_synthesis_job(job: dict[str, str], job_index: int, *, verbose: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "01_syn" / run_id
    corner = find_tech_corner(job)

    log_event(
        stage=STAGE_SYN,
        status=STATUS_RUNNING,
        message="preparing synthesis run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "db_file": str(corner.db_file),
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    script_path = prepare_synthesis_script(job, run_dir)
    syn_runner = tech_dir / "run_scripts" / "01_syn.sh"
    if not syn_runner.exists():
        raise FileNotFoundError(f"missing synthesis runner: {syn_runner}")

    log_event(
        stage=STAGE_SYN,
        status=STATUS_RUNNING,
        message="launching 01_syn.sh",
        job=job,
        run_id=run_id,
        details={"command": f"{syn_runner} {run_id}", "run_dir": str(run_dir), "script": str(script_path)},
    )

    runner_log_path = run_dir / "01_syn.sh.log"
    returncode = run_logged_command(
        [str(syn_runner), run_id],
        cwd=syn_runner.parent,
        log_path=runner_log_path,
        verbose=verbose,
        prefix=run_id,
    )

    netlist_path = run_dir / f"{job['rtl_name'].strip()}_syn.v"
    sdc_path = run_dir / f"{job['rtl_name'].strip()}.sdc"
    log_path = run_dir / "synthesis.log"
    if returncode != 0:
        log_event(
            stage=STAGE_SYN,
            status=STATUS_ERROR,
            message=f"01_syn.sh failed with exit code {returncode}",
            job=job,
            run_id=run_id,
            details={
                "log": str(log_path),
                "runner_log": str(runner_log_path),
                "run_dir": str(run_dir),
            },
        )
        raise RuntimeError(f"synthesis failed for {run_id}; see {log_path}")

    log_event(
        stage=STAGE_SYN,
        status=STATUS_DONE,
        message="synthesis complete",
        job=job,
        run_id=run_id,
        details={
            "log": str(log_path),
            "netlist": str(netlist_path),
            "sdc": str(sdc_path),
        },
    )


def run_synthesis_for_node(
    node: str, jobs: list[dict[str, str]], *, verbose: bool = False, jobs_per_node: int = 1
) -> None:
    log_event(stage=STAGE_SYN, status=STATUS_START, message="node synthesis worker started", node=node)
    run_jobs_for_node(
        jobs,
        lambda job, index: run_synthesis_job(job, index, verbose=verbose),
        jobs_per_node=jobs_per_node,
    )
    log_event(stage=STAGE_SYN, status=STATUS_DONE, message="node synthesis worker complete", node=node)


def run_synthesis_from_manifest(
    path: Path = JOB_LIST, *, verbose: bool = False, jobs_per_node: int = 1
) -> None:
    jobs = read_jobs(path)
    grouped = group_jobs_by_node(jobs)
    log_event(
        stage=STAGE_SYN,
        status=STATUS_START,
        message="synthesis stage started",
        details={"nodes": sorted(grouped), "jobs_per_node": jobs_per_node},
    )

    with ThreadPoolExecutor(max_workers=max(1, len(grouped))) as executor:
        futures = {
            executor.submit(
                run_synthesis_for_node, node, node_jobs, verbose=verbose, jobs_per_node=jobs_per_node
            ): node
            for node, node_jobs in grouped.items()
        }
        for future in as_completed(futures):
            node = futures[future]
            try:
                future.result()
            except Exception as exc:
                log_event(
                    stage=STAGE_SYN,
                    status=STATUS_TERMINATED,
                    message=f"node synthesis worker terminated: {exc}",
                    node=node,
                    details={"error_type": type(exc).__name__},
                )
                raise

    log_event(stage=STAGE_SYN, status=STATUS_DONE, message="synthesis stage complete")
