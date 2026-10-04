"""Data-collection stage: parse the EDA reports of each run into datasets/*.csv.

Consumes the report files written by the master scripts (not the interleaved tool
logs):

    01_syn/<run_id>/synthesis.log      report_qor section (DC)
    02_pnr/<run_id>/qor.rpt            report_qor          (ICC2)
    02_pnr/<run_id>/utilization.rpt    report_utilization  (ICC2)
    05_pwr/<run_id>/power_summary.rpt  report_power        (PrimeTime)
    05_pwr/<run_id>/power_hier.rpt     report_power -verbose, for the unit header

One CSV per component class, mirroring dataset_gen/sram/datasets/: a row per design
point, keyed by flow_run_id. Re-collecting a run_id overwrites its row in place.

Report labels are stable across Synopsys releases, but every row also records the
exact tool version that produced it (dc_version / icc2_version / starrc_version /
pt_version), so a future format change can be traced to the rows it affected. If a
label ever moves, the parser raises instead of silently writing a blank cell.

Areas are in library units (um2). Power is converted to mW from whatever unit the
PrimeTime report declares in its unit header.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from autocommon import (
    NW_LOGIC_DIR,
    STAGE_DATA_COLLECTION,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_START,
    clock_period_ns,
    log_event,
    normalize_node,
    parse_arch_params,
    read_jobs,
    run_id_for_job,
    utc_timestamp,
)


DATASETS_DIR = NW_LOGIC_DIR / "datasets"

# Schema version for the emitted CSVs. Bump when columns are added or renamed so a
# mixed-vintage dataset can be told apart.
# 2: rows carry stim_mode (power-phase stimulus class; "none" for unvectored)
# 3: syn/pnr timing columns span every report_qor path group (WNS = worst
#    group) and PnR adds pnr_min_period_ns (period the netlist meets, per-group
#    SDC budgets) + pnr_crit_group; schema-2 rows took the FIRST group, which in
#    ICC2 is the input-delay-bound **in2reg_default**. recollect_timing.py
#    upgrades archived rows in place.
COLLECTOR_SCHEMA_VERSION = "3"

_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# PrimeTime power groups, in the order report_power prints them.
POWER_GROUPS = (
    "clock_network",
    "register",
    "combinational",
    "sequential",
    "memory",
    "io_pad",
    "black_box",
)

_UNIT_SCALE_TO_WATT = {
    "": 1.0,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


class ReportParseError(RuntimeError):
    """A report was missing, or a label the collector depends on was not found."""


def _read_report(path: Path) -> str:
    if not path.exists():
        raise ReportParseError(f"missing report: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _section(text: str, header: str, *, source: Path) -> str:
    """Slice one Synopsys report out of a log holding several of them."""
    start = text.find(header)
    if start == -1:
        raise ReportParseError(f"{source}: no '{header}' section")
    nxt = text.find("\nReport : ", start + len(header))
    return text[start:] if nxt == -1 else text[start:nxt]


def _field(text: str, label: str, *, source: Path) -> float:
    """Value of a 'Label:  <number>' line. Case-sensitive: DC's report_qor prints
    'Combinational Area' while its report_area prints 'Combinational area'."""
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*({_NUMBER})\s*$", text, re.MULTILINE)
    if match is None:
        raise ReportParseError(f"{source}: label not found: {label!r}")
    return float(match.group(1))


def _version(text: str, *, source: Path) -> str:
    match = re.search(r"^Version:\s*(\S+)\s*$", text, re.MULTILINE)
    if match is None:
        raise ReportParseError(f"{source}: no 'Version:' line")
    return match.group(1)


_QOR_GROUP_RE = re.compile(r"^\s*Timing Path Group\s+'([^']+)'\s*$", re.MULTILINE)

_QOR_GROUP_FIELDS = {
    "length": "Critical Path Length",
    "slack": "Critical Path Slack",
    "tns": "Total Negative Slack",
    "violating": "No. of Violating Paths",
}

# ICC2's auto port-cone groups whose STA budget is T/2 on a CLOCKED design:
# autosynth's SDC sets set_input_delay = T/2 - uncertainty, so their slack is
# T/2 - L and recovering it takes 2x the slack in period. Register-launched
# groups (the clock group, reg2out with output delay 0) and a combinational
# block's in2out (virtual clock, zero I/O delays) see T - uncertainty: 1x.
_HALF_BUDGET_GROUPS = ("**in2reg_default**", "**in2out_default**")
_REGISTER_GROUPS = ("**in2reg_default**", "**reg2out_default**")


def _qor_timing(qor: str, *, source: Path) -> dict[str, Any]:
    """Timing summary over ALL report_qor path groups.

    A clocked design reports one block per path group, and ICC2 lists its auto
    port-cone groups (``**in2reg_default**`` ...) BEFORE the clock group, so
    the first 'Critical Path Length' in the report is a port cone whose length
    is mostly the T/2 input delay (collector schema <= 2 read exactly that).

    - ``min_period_ns``: the period this netlist meets, from each group's
      slack and SDC budget: max over groups of T - k*slack, k = 2 for port
      cones of a clocked design, else 1 (includes the clock uncertainty, like
      the manifest clocks). Only when every group prints its clock period
      (ICC2 does, DC does not) — otherwise None.
    - ``crit_group`` / ``crit_path_ns``: the group that sets min_period_ns and
      its path length; without periods, the clock group(s) (reg2reg), else the
      longest group.
    - ``wns_ns`` worst slack over groups; ``tns_ns`` and ``violating_paths``
      summed.
    """
    starts = [(m.start(), m.group(1)) for m in _QOR_GROUP_RE.finditer(qor)]
    if not starts:
        raise ReportParseError(f"{source}: no 'Timing Path Group' block")
    groups: list[dict[str, Any]] = []
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(qor)
        block = qor[pos:end]
        group: dict[str, Any] = {
            "name": name,
            **{key: _field(block, label, source=source)
               for key, label in _QOR_GROUP_FIELDS.items()},
        }
        period = re.search(rf"^\s*Critical Path Clk Period\s*:\s*({_NUMBER})\s*$",
                           block, re.MULTILINE)
        group["period"] = float(period.group(1)) if period else None
        groups.append(group)

    clocked = any(g["name"] in _REGISTER_GROUPS for g in groups)
    min_period = None
    if all(g["period"] is not None for g in groups):
        def need(g: dict[str, Any]) -> float:
            k = 2.0 if clocked and g["name"] in _HALF_BUDGET_GROUPS else 1.0
            return g["period"] - k * g["slack"]
        binding = max(groups, key=need)
        min_period = round(need(binding), 6)
    else:
        clock_groups = [g for g in groups if not g["name"].startswith("**")]
        binding = max(clock_groups or groups, key=lambda g: g["length"])
    return {
        "crit_path_ns": binding["length"],
        "crit_group": binding["name"].strip("*"),
        "min_period_ns": min_period,
        "wns_ns": min(g["slack"] for g in groups),
        "tns_ns": sum(g["tns"] for g in groups),
        "violating_paths": int(sum(g["violating"] for g in groups)),
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0.0:
        return None
    return numerator / denominator


def parse_syn_reports(run_dir: Path) -> dict[str, Any]:
    """Cell counts and areas from the DC report_qor section of synthesis.log."""
    source = run_dir / "synthesis.log"
    qor = _section(_read_report(source), "Report : qor", source=source)

    total_cells = _field(qor, "Leaf Cell Count", source=source)
    comb_cells = _field(qor, "Combinational Cell Count", source=source)
    seq_cells = _field(qor, "Sequential Cell Count", source=source)
    total_area = _field(qor, "Cell Area", source=source)
    comb_area = _field(qor, "Combinational Area", source=source)
    seq_area = _field(qor, "Noncombinational Area", source=source)

    return {
        "dc_version": _version(qor, source=source),
        "syn_total_cells": int(total_cells),
        "syn_comb_cells": int(comb_cells),
        "syn_seq_cells": int(seq_cells),
        "syn_total_area_um2": total_area,
        "syn_comb_area_um2": comb_area,
        "syn_seq_area_um2": seq_area,
        # SCR/SAR: the sequential-cell count and area ratios NPUWattch trains on.
        "syn_scr": _ratio(seq_cells, total_cells),
        "syn_sar": _ratio(seq_area, total_area),
        **{f"syn_{key}": value
           for key, value in _qor_timing(qor, source=source).items()
           # DC's report_qor prints no per-group clock period and lumps the
           # port cones into the clock group: no min period, one group.
           if key not in ("min_period_ns", "crit_group")},
    }


def parse_pnr_reports(run_dir: Path) -> dict[str, Any]:
    """Post-route cell counts/areas (qor.rpt) and physical area (utilization.rpt).

    ICC2 has no report_area, so cell areas come from report_qor and the core area
    from report_utilization.
    """
    qor_source = run_dir / "qor.rpt"
    qor = _read_report(qor_source)

    total_cells = _field(qor, "Leaf Cell Count", source=qor_source)
    comb_cells = _field(qor, "Combinational Cell Count", source=qor_source)
    seq_cells = _field(qor, "Sequential Cell Count", source=qor_source)
    total_area = _field(qor, "Cell Area (netlist)", source=qor_source)
    comb_area = _field(qor, "Combinational Area", source=qor_source)
    seq_area = _field(qor, "Noncombinational Area", source=qor_source)

    util_source = run_dir / "utilization.rpt"
    util = _read_report(util_source)

    return {
        "icc2_version": _version(qor, source=qor_source),
        "pnr_total_cells": int(total_cells),
        "pnr_comb_cells": int(comb_cells),
        "pnr_seq_cells": int(seq_cells),
        "pnr_total_area_um2": total_area,
        "pnr_comb_area_um2": comb_area,
        "pnr_seq_area_um2": seq_area,
        "pnr_core_area_um2": _field(util, "Total Area", source=util_source),
        "pnr_utilization": _field(util, "Utilization Ratio", source=util_source),
        # Post-CTS ratios: clock-tree and optimization buffers land in the
        # combinational bucket, so these differ from the synthesis-time SCR/SAR.
        "pnr_scr": _ratio(seq_cells, total_cells),
        "pnr_sar": _ratio(seq_area, total_area),
        **{f"pnr_{key}": value
           for key, value in _qor_timing(qor, source=qor_source).items()},
    }


def _power_unit_to_mw(text: str, label: str, *, source: Path) -> float:
    """Factor converting the report's power numbers to mW.

    The unit header only appears in the -verbose report, e.g.
        Dynamic Power Units = 1 W
        Leakage Power Units = 1pW
    """
    match = re.search(
        rf"^\s*{re.escape(label)}\s*=\s*({_NUMBER})\s*([kmunpf]?)W\s*$",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise ReportParseError(f"{source}: no '{label}' unit line")
    magnitude = float(match.group(1))
    scale = _UNIT_SCALE_TO_WATT[match.group(2)]
    return magnitude * scale * 1e3  # W -> mW


def _power_group_row(text: str, group: str, *, source: Path) -> tuple[float, float, float, float]:
    """The internal/switching/leakage/total cells of one report_power group row."""
    match = re.search(
        rf"^{re.escape(group)}\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\(",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise ReportParseError(f"{source}: no power-group row for {group!r}")
    return tuple(float(match.group(i)) for i in range(1, 5))  # type: ignore[return-value]


def _power_total(text: str, label: str, *, source: Path) -> float:
    match = re.search(rf"^\s*{re.escape(label)}\s*=\s*({_NUMBER})", text, re.MULTILINE)
    if match is None:
        raise ReportParseError(f"{source}: no total power line for {label!r}")
    return float(match.group(1))


def parse_pwr_reports(run_dir: Path, *, period_ns: float) -> dict[str, Any]:
    """Totals and per-group power from PrimeTime, converted to mW."""
    hier_source = run_dir / "power_hier.rpt"
    hier = _read_report(hier_source)
    dyn_to_mw = _power_unit_to_mw(hier, "Dynamic Power Units", source=hier_source)
    leak_to_mw = _power_unit_to_mw(hier, "Leakage Power Units", source=hier_source)

    source = run_dir / "power_summary.rpt"
    summary = _read_report(source)

    internal_mw = _power_total(summary, "Cell Internal Power", source=source) * dyn_to_mw
    switching_mw = _power_total(summary, "Net Switching Power", source=source) * dyn_to_mw
    leak_mw = _power_total(summary, "Cell Leakage Power", source=source) * leak_to_mw
    total_mw = _power_total(summary, "Total Power", source=source) * dyn_to_mw
    dyn_mw = internal_mw + switching_mw

    record: dict[str, Any] = {
        "pt_version": _version(summary, source=source),
        "internal_power_mW": internal_mw,
        "switching_power_mW": switching_mw,
        "leak_power_mW": leak_mw,
        "total_power_mW": total_mw,
        "dyn_power_mW": dyn_mw,
        # Energy of one clock cycle: mW * ns == pJ.
        "dyn_energy_pJ": dyn_mw * period_ns,
    }

    for group in POWER_GROUPS:
        internal, switching, leakage, total = _power_group_row(summary, group, source=source)
        record[f"{group}_internal_power_mW"] = internal * dyn_to_mw
        record[f"{group}_switching_power_mW"] = switching * dyn_to_mw
        record[f"{group}_leak_power_mW"] = leakage * leak_to_mw
        record[f"{group}_total_power_mW"] = total * dyn_to_mw

    return record


def parse_pex_report(run_dir: Path) -> dict[str, Any]:
    """StarRC version only ? the SPEF feeds PrimeTime, it carries no PAT numbers."""
    source = run_dir / f"{run_dir.name.split('_')[0]}.star_sum"
    matches = list(source.parent.glob("*.star_sum")) if not source.exists() else [source]
    if not matches:
        raise ReportParseError(f"missing StarRC summary in {run_dir}")
    text = _read_report(matches[0])
    match = re.search(r"^Version:\s*(\S+)\s*$", text, re.MULTILINE)
    return {"starrc_version": match.group(1) if match else ""}


def _activity_mode(pwr_run_dir: Path) -> str:
    """Vectorless or simulation-driven ? decisive provenance for the power numbers."""
    script = pwr_run_dir / "05_pwr.tcl"
    if not script.exists():
        return ""
    match = re.search(r'^set\s+activity_mode\s+"([^"]*)"', script.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def _stim_mode(pwr_run_dir: Path) -> str:
    """Power-phase stimulus class of the vectored SAIF ("none" when unvectored).

    Parsed from the same prepared script as _activity_mode; scripts that
    predate the stim_mode variable read back as "random" for vectored runs
    (the legacy stimulus) and "none" otherwise.
    """
    script = pwr_run_dir / "05_pwr.tcl"
    if not script.exists():
        return ""
    text = script.read_text(encoding="utf-8")
    match = re.search(r'^set\s+stim_mode\s+"([^"]*)"', text, re.MULTILINE)
    if match:
        return match.group(1)
    return "random" if _activity_mode(pwr_run_dir) == "vectored" else "none"


def collect_job(job: dict[str, str]) -> dict[str, Any]:
    run_id = run_id_for_job(job)
    node = normalize_node(job.get("node", ""))
    tech_dir = NW_LOGIC_DIR / f"TECH_{int(node):02d}nm"
    period_ns = clock_period_ns(job)

    record: dict[str, Any] = {
        # --- design point identity -------------------------------------------------
        "flow_run_id": run_id,
        "rtl_name": job["rtl_name"].strip(),
        "arch_params": job.get("arch_params", "").strip(),
        # --- technology / operating corner ------------------------------------------
        "node": f"{int(node)}nm",
        "corner": job.get("process", "").strip(),
        "vdd_V": float(job["voltage"]) if job.get("voltage", "").strip() else None,
        "temperature_C": float(job["temp"]) if job.get("temp", "").strip() else None,
        "clock_period_ns": period_ns,
        "clock_freq_mhz": 1000.0 / period_ns,
    }

    # Architectural configuration as its own columns (a_width, pipeline_stages, ...).
    # One CSV per component class, so the key set is uniform within a file.
    record.update(parse_arch_params(job.get("arch_params", "")))

    record.update(parse_syn_reports(tech_dir / "01_syn" / run_id))
    record.update(parse_pnr_reports(tech_dir / "02_pnr" / run_id))
    record.update(parse_pex_report(tech_dir / "03_pex" / run_id))
    pwr_dir = tech_dir / "05_pwr" / run_id
    record.update(parse_pwr_reports(pwr_dir, period_ns=period_ns))

    record["power_activity_mode"] = _activity_mode(pwr_dir)
    record["stim_mode"] = _stim_mode(pwr_dir)
    record["collector_schema"] = COLLECTOR_SCHEMA_VERSION
    record["collected_at"] = utc_timestamp()
    return record


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    """Rows are keyed by run id, activity mode AND stimulus class: the same design
    point yields a different power measurement unvectored (vectorless estimate) than
    vectored, and a different vectored measurement per stimulus class (random /
    read / write / hold_b / ...) -- all worth keeping.  Legacy rows without a
    stim_mode column key as ("", ...) and are replaced by their re-collected
    successors only when activity mode and run id also match."""
    return (
        str(row.get("flow_run_id", "")),
        str(row.get("power_activity_mode", "")),
        str(row.get("stim_mode", "")),
    )


def _upsert_csv(path: Path, record: dict[str, Any]) -> None:
    """Append the record, replacing any existing row with the same key.

    Columns are unioned so a component whose sweep gains an arch parameter does not
    invalidate the rows already collected.
    """
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    key = _row_key(record)
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            fieldnames = list(reader.fieldnames or [])
            rows = [row for row in reader if _row_key(row) != key]

    for key in record:
        if key not in fieldnames:
            fieldnames.append(key)
    rows.append({key: record.get(key, "") for key in fieldnames})

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


def dataset_path_for(rtl_name: str) -> Path:
    return DATASETS_DIR / f"logic_{rtl_name}.csv"


def collect_from_manifest() -> None:
    jobs = read_jobs()
    log_event(stage=STAGE_DATA_COLLECTION, status=STATUS_START, message="data collection started")

    collected = 0
    failed = 0
    for index, job in enumerate(jobs, start=1):
        run_id = run_id_for_job(job)
        log_event(
            stage=STAGE_DATA_COLLECTION,
            status=STATUS_RUNNING,
            message="parsing run reports",
            job=job,
            run_id=run_id,
        )
        try:
            record = collect_job(job)
        except (ReportParseError, ValueError, KeyError) as exc:
            failed += 1
            log_event(
                stage=STAGE_DATA_COLLECTION,
                status=STATUS_ERROR,
                message=f"could not collect {run_id}: {exc}",
                job=job,
                run_id=run_id,
            )
            print(f"[{index}] ERROR {run_id}: {exc}")
            continue

        dataset = dataset_path_for(record["rtl_name"])
        _upsert_csv(dataset, record)
        collected += 1
        log_event(
            stage=STAGE_DATA_COLLECTION,
            status=STATUS_DONE,
            message="row written",
            job=job,
            run_id=run_id,
            details={"dataset": str(dataset)},
        )
        print(f"[{index}] collected {run_id} -> {dataset}")

    log_event(
        stage=STAGE_DATA_COLLECTION,
        status=STATUS_ERROR if failed else STATUS_DONE,
        message=f"data collection complete: {collected} collected, {failed} failed",
        details={"collected": collected, "failed": failed},
    )
    print(f"data collection complete: {collected} collected, {failed} failed")


if __name__ == "__main__":
    collect_from_manifest()
