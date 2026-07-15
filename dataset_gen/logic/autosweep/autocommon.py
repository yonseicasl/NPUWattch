from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


AUTOSWEEP_DIR = Path(__file__).resolve().parent
NW_LOGIC_DIR = AUTOSWEEP_DIR.parent
PROJECT_ROOT = NW_LOGIC_DIR.parents[1]
JOB_LIST = AUTOSWEEP_DIR / "jobs"
SCOREBOARD = AUTOSWEEP_DIR / "scoreboard.jsonl"
MASTER_TCL_DIR = NW_LOGIC_DIR / "master_tcl"
# shared by the logic and SRAM flows; per-node collateral lives in
# tech_libs/techlib_NNnm/ (db/ndm/tf/tluplus/nxtgrd/map + gds/), see catalog.json
TECH_LIBS_DIR = NW_LOGIC_DIR.parent / "tech_libs"
CATALOG_FILE = TECH_LIBS_DIR / "catalog.json"

STAGE_RTL_GEN = "rtl-gen"
STAGE_SYN = "syn"
STAGE_PNR = "pnr"
STAGE_PEX = "pex"
STAGE_LOGIC_SIM = "logic-sim"
STAGE_POWER_SIM = "power-sim"
STAGE_DATA_COLLECTION = "data-collection"

STATUS_START = "start"
STATUS_RUNNING = "running"
STATUS_SKIP = "skip"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_TERMINATED = "terminated"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(NW_LOGIC_DIR))


@dataclass(frozen=True)
class TechCorner:
    node: str
    process: str
    voltage: str
    temp: str
    directory: Path
    db_file: Path
    tlu_file: Path
    ndm_file: Path
    tech_file: Path
    map_file: Path
    grd_file: Path
    # Verilog simulation models for the std cells (gate-level sim). PrimeLib emits
    # them from the same characterization as the .lib/.db; None for nodes whose
    # catalog entry has no "verilogdir" yet.
    verilog_dir: Path | None
    # Library cells synthesis must not map to (catalog "dontuse", node-level).
    # Used to keep the usable cell set uniform across nodes: 5nm characterizes
    # MUX_X1/MUX_X2 which the 20-7nm libraries have no layouts for.
    dont_use: tuple[str, ...] = ()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_name_token(value: Any) -> str:
    token = str(value).strip()
    token = token.replace(".", "p")
    token = token.replace("-", "m")
    cleaned = []
    for char in token:
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "_".join(part for part in "".join(cleaned).split("_") if part)


def parse_scalar(value: str) -> Any:
    value = value.strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        return int(value, 0)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_arch_param_items(raw: str) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    raw = raw.strip()
    if not raw:
        return items

    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"arch_params item lacks '=': {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"arch_params item has an empty key: {item!r}")
        items.append((key, parse_scalar(value)))
    return items


def parse_arch_params(raw: str) -> dict[str, Any]:
    return dict(parse_arch_param_items(raw))


def normalize_node(node: str) -> str:
    node = node.strip().lower()
    return node.removesuffix("nm")


def clock_period_ns(job: dict[str, str]) -> float:
    raw_period = job.get("clock_period_ns", "").strip()
    if raw_period:
        return float(raw_period)

    raw_freq = job.get("clock_freq_mhz", "").strip()
    if raw_freq:
        freq_mhz = float(raw_freq)
        if freq_mhz <= 0.0:
            raise ValueError("clock_freq_mhz must be positive")
        return 1000.0 / freq_mhz

    raise ValueError("synthesis jobs require clock_period_ns or clock_freq_mhz")


def voltage_token(voltage: str) -> str:
    voltage = voltage.strip()
    lowered = voltage.lower()
    if "v" in lowered and "." not in voltage:
        return sanitize_name_token(voltage)
    if lowered.endswith("v"):
        voltage = voltage[:-1]
    if "." in voltage:
        return sanitize_name_token(voltage.replace(".", "V"))
    return f"{sanitize_name_token(voltage)}V"


def frequency_token(job: dict[str, str]) -> str:
    raw_freq = job.get("clock_freq_mhz", "").strip()
    if raw_freq:
        freq = float(raw_freq)
    else:
        freq = 1000.0 / clock_period_ns(job)

    if freq.is_integer():
        return f"{int(freq)}MHz"
    return f"{sanitize_name_token(freq)}MHz"


def run_id_for_job(job: dict[str, str], fallback_index: int | None = None) -> str:
    del fallback_index
    rtl_name = sanitize_name_token(job.get("rtl_name", "unknown").strip() or "unknown")
    arch_tokens = [
        sanitize_name_token(value) for _, value in parse_arch_param_items(job.get("arch_params", ""))
    ]
    tech_tokens = [
        f"{sanitize_name_token(normalize_node(job.get('node', 'node')))}nm",
        sanitize_name_token(job.get("process", "process").strip() or "process"),
        voltage_token(job.get("voltage", "voltage")),
        f"{sanitize_name_token(job.get('temp', 'temp').strip() or 'temp')}C",
    ]
    return "_".join([rtl_name, *arch_tokens, *tech_tokens, frequency_token(job)])


def recreate_run_dir(run_dir: Path) -> bool:
    nw_logic = NW_LOGIC_DIR.resolve()
    parent = run_dir.parent.resolve()
    if nw_logic not in (parent, *parent.parents):
        raise ValueError(f"refusing to recreate directory outside NW_logic: {run_dir}")

    removed_existing = False
    if run_dir.exists() or run_dir.is_symlink():
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise ValueError(f"refusing to remove non-directory run path: {run_dir}")
        shutil.rmtree(run_dir)
        removed_existing = True

    run_dir.mkdir(parents=True, exist_ok=False)
    return removed_existing


def log_event(
    *,
    stage: str,
    status: str,
    message: str,
    job: dict[str, str] | None = None,
    node: str | None = None,
    run_id: str | None = None,
    details: dict[str, Any] | None = None,
    scoreboard: Path = SCOREBOARD,
) -> None:
    event = {
        "timestamp": utc_timestamp(),
        "stage": stage,
        "status": status,
        "message": message,
    }
    if job is not None:
        event["rtl_name"] = job.get("rtl_name", "").strip()
        event["arch_params"] = job.get("arch_params", "").strip()
        event["node"] = job.get("node", "").strip()
        event["run_id"] = run_id or run_id_for_job(job)
    elif node is not None:
        event["node"] = node
    if run_id is not None:
        event["run_id"] = run_id
    if details:
        event["details"] = details

    scoreboard.parent.mkdir(parents=True, exist_ok=True)
    with scoreboard.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(event, sort_keys=True) + "\n")


def load_scoreboard(scoreboard: Path = SCOREBOARD) -> list[dict[str, Any]]:
    if not scoreboard.exists():
        return []
    events: list[dict[str, Any]] = []
    with scoreboard.open(encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid scoreboard JSON on line {line_number}: {exc}") from exc
    return events


def summarize_scoreboard(scoreboard: Path = SCOREBOARD) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for event in load_scoreboard(scoreboard):
        stage = str(event.get("stage", "unknown"))
        status = str(event.get("status", "unknown"))
        summary.setdefault(stage, {})
        summary[stage][status] = summary[stage].get(status, 0) + 1
    return summary


def read_jobs(path: Path = JOB_LIST) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing TSV manifest: {path}")

    with path.open(newline="", encoding="utf-8") as fp:
        rows = [line for line in fp if line.strip() and not line.lstrip().startswith("#")]

    if not rows:
        raise ValueError(f"TSV manifest is empty: {path}")

    reader = csv.DictReader(rows, delimiter="\t")
    if reader.fieldnames is None:
        raise ValueError(f"TSV manifest has no header: {path}")

    required = {"rtl_name", "arch_params"}
    missing = required.difference(reader.fieldnames)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        raise ValueError(f"TSV manifest is missing required column(s): {missing_cols}")

    # A row may leave trailing optional columns off entirely; DictReader maps
    # those to None, which downstream .strip() consumers must not see.
    jobs = [
        {key: (value if value is not None else "") for key, value in row.items() if key is not None}
        for row in reader
    ]
    if not jobs:
        raise ValueError(f"TSV manifest has no jobs: {path}")
    return jobs


def rtl_variant_key(job: dict[str, str]) -> tuple[str, str]:
    rtl_name = job["rtl_name"].strip()
    arch_params = job.get("arch_params", "").strip()
    return rtl_name, arch_params


def rtl_variant_dir_name(job: dict[str, str]) -> str:
    """Per-arch-config RTL output directory name (rtl_gen/rtl/<this>/<rtl>/).

    One directory per (rtl_name, arch_params) variant. A shared per-module
    directory would let the last generated config silently overwrite the
    others, so every job of that module would synthesize the same RTL.
    """
    rtl_name = sanitize_name_token(job.get("rtl_name", "").strip())
    arch_tokens = [
        sanitize_name_token(value) for _, value in parse_arch_param_items(job.get("arch_params", ""))
    ]
    return "_".join([rtl_name, *arch_tokens])


def run_jobs_for_node(
    jobs: list[dict[str, str]],
    job_runner: Callable[[dict[str, str], int], None],
    *,
    jobs_per_node: int = 1,
) -> None:
    """Run job_runner(job, index) over a node's jobs, jobs_per_node at a time.

    Concurrency is safe because every stage works in its own run directory and
    RTL lives in per-variant directories; the practical bound is EDA license
    seats (total concurrent tools = nodes x jobs_per_node). On the first
    failure, not-yet-started jobs are cancelled to match the sequential
    fail-fast behavior; already-running jobs finish.
    """
    if jobs_per_node <= 1:
        for index, job in enumerate(jobs, start=1):
            job_runner(job, index)
        return

    with ThreadPoolExecutor(max_workers=jobs_per_node) as pool:
        futures = {
            pool.submit(job_runner, job, index): index
            for index, job in enumerate(jobs, start=1)
        }
        try:
            for future in as_completed(futures):
                future.result()
        except Exception:
            for future in futures:
                future.cancel()
            raise


def group_jobs_by_node(jobs: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for job in jobs:
        node = job.get("node", "").strip()
        if not node:
            raise ValueError("jobs row is missing required node value")
        grouped.setdefault(node, []).append(job)
    return grouped


def decode_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    index = 0
    objects: list[dict[str, Any]] = []
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        obj, index = decoder.raw_decode(text, index)
        if not isinstance(obj, dict):
            raise ValueError("catalog.json must contain JSON objects")
        objects.append(obj)
    return objects


def read_catalog(path: Path = CATALOG_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing technology catalog: {path}")
    return decode_json_objects(path.read_text(encoding="utf-8"))


def find_tech_corner(job: dict[str, str]) -> TechCorner:
    node = normalize_node(job.get("node", ""))
    process = job.get("process", "").strip()
    voltage = job.get("voltage", "").strip()
    temp = job.get("temp", "").strip()
    if not all([node, process, voltage, temp]):
        raise ValueError("synthesis jobs require node, process, voltage, and temp columns")

    for entry in read_catalog():
        if normalize_node(str(entry.get("node", ""))) != node:
            continue
        for corner in entry.get("corners", []):
            if (
                str(corner.get("process", "")).strip() == process
                and str(corner.get("voltage", "")).strip() == voltage
                and str(corner.get("temperature", "")).strip() == temp
            ):
                directory = TECH_LIBS_DIR / str(corner["directory"])
                # "verilogdir" lives on the node entry (like "gdsdir"), not the corner:
                # the Verilog models are logic + UDPs, so they are corner-independent.
                verilog_dir_name = entry.get("verilogdir")
                dont_use = tuple(str(c) for c in entry.get("dontuse", []))
                return TechCorner(
                    node=node,
                    process=process,
                    voltage=voltage,
                    temp=temp,
                    directory=directory,
                    db_file=directory / str(corner["dbfile"]),
                    tlu_file=directory / str(corner["tlufile"]),
                    ndm_file=directory / str(corner["ndmfile"]),
                    tech_file=directory / str(corner["techfile"]),
                    map_file=directory / str(corner["mapfile"]),
                    grd_file=directory / str(corner["grdfile"]),
                    verilog_dir=directory / str(verilog_dir_name) if verilog_dir_name else None,
                    dont_use=dont_use,
                )

    raise ValueError(f"no catalog corner for node={node}, process={process}, voltage={voltage}, temp={temp}")


def inject_between_markers(text: str, start_marker: str, end_marker: str, injected: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"could not find marker block {start_marker} ... {end_marker}")

    start_line_end = text.find("\n", start)
    if start_line_end == -1:
        raise ValueError(f"start marker has no terminating newline: {start_marker}")

    return text[: start_line_end + 1] + injected.rstrip() + "\n" + text[end:]


def run_logged_command(command: list[str], *, cwd: Path, log_path: Path, verbose: bool, prefix: str) -> int:
    if not verbose:
        with log_path.open("w", encoding="utf-8") as log_fp:
            proc = subprocess.run(
                command,
                cwd=cwd,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        return proc.returncode

    with log_path.open("w", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fp.write(line)
            log_fp.flush()
            sys.stdout.write(f"[{prefix}] {line}")
            sys.stdout.flush()
        return proc.wait()
