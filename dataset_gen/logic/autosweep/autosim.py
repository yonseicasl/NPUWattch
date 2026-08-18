from __future__ import annotations

import re
import shutil
from pathlib import Path

from autocommon import (
    NW_LOGIC_DIR,
    STAGE_LOGIC_SIM,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    clock_period_ns,
    find_tech_corner,
    log_event,
    normalize_node,
    recreate_run_dir,
    rtl_variant_dir_name,
    run_id_for_job,
    run_logged_command,
)
from rtl_gen import generator
from sweep_spec import power_modes


SIM_MODEL_EXTENSIONS = {".v", ".sv", ".vg", ".vlog", ".verilog"}


def discover_std_cell_models(directory: Path | None) -> list[Path]:
    """Verilog std-cell models for gate-level sim, from the catalog's verilogdir.

    UDP primitives must be compiled before the cells that instantiate them, so the
    *_udp.v file is listed first rather than in plain sorted order.
    """
    if directory is None or not directory.exists():
        return []
    files = sorted(
        file_path
        for file_path in directory.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in SIM_MODEL_EXTENSIONS
    )
    return sorted(files, key=lambda path: (0 if "udp" in path.stem.lower() else 1, path.name))


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

    # Two generated instantiation styles exist: parameterized
    # (`rtl_name #(...) dut (`) whose override list must be stripped because
    # the gate netlist's module has its parameters baked in, and plain
    # (`rtl_name dut (` -- regfile/fifo/mxfpmac templates, where the
    # generator bakes the parameters into the RTL) which needs no rewrite,
    # only the instance name for the SDF hook.
    inst_pattern = re.compile(rf"(?m)^(\s*){re.escape(rtl_name)}\s*#\s*\(")
    inst_match = inst_pattern.search(text)
    if inst_match:
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
    else:
        plain_match = re.search(
            rf"(?m)^\s*{re.escape(rtl_name)}\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(", text
        )
        if not plain_match:
            raise ValueError(f"could not find DUT instantiation for {rtl_name}")
        instance_name = plain_match.group(1)

    gate_hook = f"""
`ifdef NW_LOGIC_GATE_SIM
    initial begin
        $sdf_annotate("{sdf_name}", {instance_name},, "sdf_annotate.log", "MAXIMUM");
        $dumpfile("sim.vcd");
        $dumpvars(0, {tb_module});
        // The VCD is the functional-phase debug trace; power activity comes
        // from the SAIF whose window the TB opens over the power phase.
        @(posedge nw_power_phase);
        $dumpoff;
    end
`endif

"""
    anchor_match = re.search(r"(?m)^\s*initial\b", text)
    if not anchor_match:
        raise ValueError("could not find an initial block to insert the gate-sim hook before")
    return text[: anchor_match.start()] + gate_hook + text[anchor_match.start() :]


def prepare_simulation_run(job: dict[str, str], run_dir: Path) -> Path:
    rtl_name = job["rtl_name"].strip()
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    pnr_dir = tech_dir / "02_pnr" / run_id
    corner = find_tech_corner(job)

    pnr_netlist = pnr_dir / f"{rtl_name}_icc2.v"
    pnr_sdf = pnr_dir / f"{rtl_name}.sdf"
    rtl_tb = generator.RTL_DIR / rtl_variant_dir_name(job) / rtl_name / f"{rtl_name}_tb.sv"
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

    model_files = discover_std_cell_models(corner.verilog_dir)
    with models_path.open("w", encoding="utf-8") as fp:
        fp.write(f"// DB reference for this corner: {corner.db_file}\n")
        if model_files:
            for model_file in model_files:
                fp.write(f"{model_file}\n")
        else:
            fp.write("// No Verilog standard-cell simulation models for this node.\n")
            fp.write("// Add a \"verilogdir\" to the node's catalog.json entry (PrimeLib 'model -verilog'\n")
            fp.write("// emits them from the same characterization as the .lib), or set\n")
            fp.write("// STD_CELL_MODELS_F / STD_CELL_MODELS when running 04_sim.sh.\n")

    with filelist_path.open("w", encoding="utf-8") as fp:
        fp.write("+define+NW_LOGIC_GATE_SIM\n")
        fp.write("+libext+.v+.sv\n")
        fp.write("-f stdcell_models.f\n")
        fp.write(f"{netlist_path.name}\n")
        fp.write(f"{tb_path.name}\n")

    return filelist_path


def _marginal_error_count(sim_log: Path) -> int:
    """Total tolerated value mismatches reported by the TB's summary line
    ("<tb> PASS marginal_errors=N"); 0 when the log is absent or clean."""
    if not sim_log.exists():
        return 0
    total = 0
    for match in re.finditer(
        r"PASS marginal_errors=(\d+)", sim_log.read_text(encoding="utf-8", errors="replace")
    ):
        total += int(match.group(1))
    return total


def _check_direct_sim_outputs(run_dir: Path) -> str | None:
    """Replicate 04_sim.sh's pass/fail checks for direct ./simv re-runs.

    Returns an error string or None.  The runner script performs these checks
    itself for the first (compiling) invocation; subsequent per-mode runs call
    simv directly and must apply the same gate.
    """
    sim_log = run_dir / "sim.log"
    if not sim_log.exists():
        return "simv produced no sim.log"
    text = sim_log.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?m)^\s*(Error-|Error:|Fatal:)", text) or " FAIL" in text:
        return "sim.log contains failure messages"
    if " PASS" not in text:
        return "sim.log does not contain a PASS marker"
    if not (run_dir / "sim.saif").exists():
        return "missing output sim.saif"
    return None


def _stash_mode_outputs(run_dir: Path, mode: str) -> None:
    """Rename the fixed-name sim outputs to their per-mode names.

    The TB always writes sim.saif/sim.log (04_sim.sh checks those names), so
    each mode's outputs are moved aside before the next mode overwrites them.
    """
    for fixed, stem in (("sim.saif", "sim_%s.saif"), ("sim.log", "sim_%s.log")):
        source = run_dir / fixed
        if source.exists():
            source.replace(run_dir / (stem % mode))


def run_simulation_job(job: dict[str, str], job_index: int, *, verbose: bool = False) -> None:
    run_id = run_id_for_job(job, job_index)
    rtl_name = job["rtl_name"].strip()
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    run_dir = tech_dir / "04_sim" / run_id
    corner = find_tech_corner(job)
    modes = power_modes(rtl_name, job.get("arch_params", ""))

    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_RUNNING,
        message="preparing gate-level simulation run",
        job=job,
        run_id=run_id,
        details={
            "run_dir": str(run_dir),
            "db_file": str(corner.db_file),
            "power_modes": list(modes),
            "reset_existing_run_dir": run_dir.exists(),
        },
    )
    filelist_path = prepare_simulation_run(job, run_dir)
    sim_runner = tech_dir / "run_scripts" / "04_sim.sh"
    if not sim_runner.exists():
        raise FileNotFoundError(f"missing simulation runner: {sim_runner}")

    # Run the TB at the job's clock so the captured activity toggles at the
    # frequency the power row claims (the TB default is 10 ns).
    period_ps = int(round(clock_period_ns(job) * 1000.0))

    # One simulation per stimulus mode, all sharing one VCS compile: the first
    # mode goes through 04_sim.sh (compile + run + output checks), later modes
    # re-run the compiled ./simv directly with a different +nw_power_mode.
    # Each mode's sim.saif/sim.log are stashed as sim_<mode>.saif/.log so the
    # vectored power runs can pick their activity file.
    for mode_index, mode in enumerate(modes):
        simv_args = [
            # Runtime half of +vcs+initreg (compile flag lives in 04_sim.sh):
            # definite random flop values at time 0 instead of X, which would
            # otherwise stick through the synthesized sync-reset logic.
            "+vcs+initreg+random",
            f"+nw_clock_period_ps={period_ps}",
            f"+nw_power_mode={mode}",
        ]
        if mode_index == 0:
            command = [str(sim_runner), run_id, *simv_args]
            cwd = sim_runner.parent
        else:
            command = ["./simv", "-l", "sim.log", *simv_args]
            cwd = run_dir

        log_event(
            stage=STAGE_LOGIC_SIM,
            status=STATUS_RUNNING,
            message=f"launching gate-level sim, mode {mode}",
            job=job,
            run_id=run_id,
            details={
                "command": " ".join(command),
                "run_dir": str(run_dir),
                "filelist": str(filelist_path),
            },
        )

        runner_log_path = run_dir / f"04_sim.sh.{mode}.log"
        returncode = run_logged_command(
            command,
            cwd=cwd,
            log_path=runner_log_path,
            verbose=verbose,
            prefix=f"{run_id}:{mode}",
        )

        sim_log = run_dir / "sim.log"
        error = None
        if returncode != 0:
            error = f"exit code {returncode}"
        elif mode_index > 0:
            error = _check_direct_sim_outputs(run_dir)
        if error:
            log_event(
                stage=STAGE_LOGIC_SIM,
                status=STATUS_ERROR,
                message=f"gate-level sim failed in mode {mode}: {error}",
                job=job,
                run_id=run_id,
                details={
                    "sim_log": str(sim_log),
                    "runner_log": str(runner_log_path),
                    "run_dir": str(run_dir),
                },
            )
            raise RuntimeError(
                f"gate-level simulation failed for {run_id} (mode {mode}); see {sim_log}"
            )
        marginal = _marginal_error_count(sim_log)
        if marginal:
            log_event(
                stage=STAGE_LOGIC_SIM,
                status=STATUS_RUNNING,
                message=(
                    f"WARNING: functional check tolerated {marginal} value "
                    f"mismatch(es) in mode {mode} (near-miss timing; power "
                    "phase unaffected)"
                ),
                job=job,
                run_id=run_id,
                details={"sim_log": str(sim_log), "marginal_errors": marginal},
            )
        _stash_mode_outputs(run_dir, mode)

    log_event(
        stage=STAGE_LOGIC_SIM,
        status=STATUS_DONE,
        message="gate-level simulation complete",
        job=job,
        run_id=run_id,
        details={
            "modes": list(modes),
            "saif_files": [str(run_dir / f"sim_{mode}.saif") for mode in modes],
            "vcd": str(run_dir / "sim.vcd"),
        },
    )
