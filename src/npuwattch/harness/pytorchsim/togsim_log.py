"""Parse a TOGSim run log (``togsim_results/*.log``).

The TOGSim log is the primary activity input: its header echoes the full hardware
config, and its body reports **on-chip** per-core activity (systolic / vector
active cycles, COMP GEMM op counts, DMA engine active/idle cycles + response
counts). Off-chip echoes are read too: the final
DRAM request totals (VMEM + NoC traffic derive from them), the BookSim
``[config]`` block the simulator prints at init (the NoC topology — for ``fly``
networks it makes the log fully self-contained; ``anynet`` additionally needs the
``.net`` file, whose *path* is all the log carries), the one-line
``[Config/DRAM] … N channels, M bytes per request`` init echo (fills
``dram_req_size_byte``/``dram_channels`` when the config block lacks them —
removes the 32 B request-size assumption), and the ``[Config/Energy]`` energy
cost table echo (2026-08-05 author build — the declared DRAM energy table's
name/path, checked against the dram compound's built-in HBM2 constants).

Log format (the 2026-07-20 author build; the earlier ``TOGSim Config: {JSON}``
header format is **retired** — logs from older builds are not accepted):

- Line 1 is the simulator **command line**; the kernel hash is the ``<hash>`` in
  ``--trace_so .../outputs/<hash>/trace.so``. This is the join key to the kernel's
  gem5 output dir (``<gem5_dir>/<hash>/``) — the log body carries no hash, and the
  log *filename*'s hex suffix is NOT the kernel hash.
- The config block is echoed as bare ``key: value`` lines following a
  ``PyTorchSim config:`` marker, terminated by the next timestamped line.
- The per-core activity block is reprinted every ``core_stats_print_period_cycles``
  as a per-period increment, then a final cumulative block is emitted at the end.
  Taking the *last* value reported for each ``(core, systolic-array)`` yields the
  cumulative total; likewise for the vector unit per core. Stat lines are
  colon-separated: ``... utilization(%): 9.79, active_cycles: 64, ...``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = ["TogsimActivity", "TogsimLogError", "parse_config",
           "parse_dram_ctrl_stats", "parse_icnt_config", "parse_togsim_log"]


class TogsimLogError(ValueError):
    """The TOGSim log is malformed or missing an expected field."""


#: Kernel hash from the command line (author builds: --trace_so/--cycle_table).
_TRACE_SO = re.compile(r"--trace_so\s+\S*?[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]trace\.so")
_CYCLE_TABLE = re.compile(r"--cycle_table\s+\S*?[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]")
#: Tutorial/models_list builds pass `--models_list <run>.trace` instead — no hash
#: on the command line. The scheduler body lines still name the kernel dir
#: (`tog_path: .../outputs/<hash>/tile_graph.onnx`), so a log whose body
#: mentions exactly ONE kernel dir is unambiguous.
_OUTPUTS_DIR = re.compile(r"[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]")

_CONFIG_MARKER = "PyTorchSim config:"
_CONFIG_LINE = re.compile(r"^([A-Za-z_]\w*):\s*(.*)$")

# BookSim2's own config echo: a bare "[config]" line, then "key = value" lines
# (blank lines separate sections), ended by the next timestamped "[...]" line.
_ICNT_MARKER = "[config]"
_ICNT_LINE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")

_SYS = re.compile(
    r"Core \[(\d+)\] : Systolic array \[(\d+)\]\s+[Uu]tilization\(%\)\s*:\s*[\d.]+,"
    r"\s*active[ _]cycles?\s*:\s*(\d+)"
)
# Vector line spelling varies (periodic vs final): "active_cycles:" / "active cycle:".
_VEC = re.compile(
    r"Core \[(\d+)\] : Vector unit\s+[Uu]tilization\(%\)\s*:\s*[\d.]+,"
    r"\s*active[ _]cycles?\s*:\s*(\d+)"
)
_COMP = re.compile(
    r"Core \[(\d+)\] : COMP\s+inst_count\s*:\s*(\d+)\s+\(GEMM:\s*(\d+),\s*Vector:\s*(\d+)\)"
)
_MOV = re.compile(r"Core \[(\d+)\] : (MOVIN|MOVOUT)\s+inst_count\s*:\s*(\d+)")
# Core [0] : DMA active_cycles: 8905, DMA idle_cycles: 1095, DRAM BW: 278.000 GB/s (92430 responses)
# Periodic lines are per-period increments (active+idle = the print period); the
# final line is cumulative — same convention as the systolic/vector blocks, and
# verified on the tutorial run (periodic actives sum exactly to the final line;
# final responses 393216 = 12 MB / 32 B = the run's total DRAM requests).
_DMA = re.compile(
    r"Core \[(\d+)\] : DMA active[ _]cycles?\s*:\s*(\d+),\s*"
    r"DMA idle[ _]cycles?\s*:\s*(\d+).*?\((\d+) responses\)"
)
_TOTAL_EXEC = re.compile(r"Total execution cycles:\s+(\d+)")

# Core [0] : NUMA local memory: 393216 requests, remote memory: 0 requests
# Final-block line (one per core): the EXACT local/remote DRAM-request split —
# replaces the NoC's uniform-traffic assumption for chiplet (anynet) runs.
_NUMA = re.compile(
    r"Core \[(\d+)\] : NUMA local memory:\s*(\d+) requests?,\s*"
    r"remote memory:\s*(\d+) requests?"
)

# BookSim's own end-of-run stats echo (bare lines, no [timestamp] prefix):
#   Injected packet length average = 1
# The NoC flit model assumes 1 flit/packet; the LAST reported average is the
# runtime check (and scale factor) for that assumption.
_PKT_LEN = re.compile(r"^Injected packet length average\s*=\s*([\d.eE+-]+)\s*$",
                      re.MULTILINE)

# [DRAM] channel 5 | ... | 48 reads, 16 writes        (per-channel, cumulative)
# [DRAM] channels 0..15 combined | ... | 772 reads, 256 writes
_DRAM_CH = re.compile(r"\[DRAM\] channel (\d+) \|.*\|\s*(\d+) reads?,\s*(\d+) writes?")
_DRAM_ALL = re.compile(r"\[DRAM\] channels [\d.]+ combined \|.*\|\s*(\d+) reads?,\s*(\d+) writes?")

# The DRAM front-end's one-line init echo — the request size the run ACTUALLY
# used (no author build puts a dram_req_size_byte key in the config header):
#   [Config/DRAM] Total bandwidth 481.28 GB/s, 940 MHz, 16 channels, 32 bytes per request
_DRAM_CFG_ECHO = re.compile(
    r"\[Config/DRAM\][^\n]*?\b(\d+)\s+channels,\s*(\d+)\s+bytes per request")

# The declared DRAM energy table (2026-08-05 author build, config key
# `energy_cost_table_path`); the wording varies between "energy table" and
# "energy cost table" within that same build:
#   [Config/Energy] Loaded energy cost table "HBM2" from /path/hbm2.yml
_ENERGY_TABLE_ECHO = re.compile(
    r'\[Config/Energy\] Loaded energy (?:cost )?table "([^"]+)" from (\S+)')

# Ramulator2's end-of-run controller statistics: a "=== DRAM statistics ==="
# marker, then one "--- channel N ---" YAML-ish block per channel. The
# controller counters are what the analytic DRAM energy model charges from:
# ACT(+PRE) commands = row_misses + row_conflicts (open-row policy: a miss or a
# conflict each activates a row), RD/WR = num_read/write_reqs, refresh =
# num_maintenance_reqs. The anchored patterns deliberately do NOT match the
# derived per-kind lines (`read_row_hits: …`) or per-core lines
# (`read_row_hits_core_0: …`) — only the bare controller totals.
_DRAM_STATS_MARKER = "=== DRAM statistics ==="
_DRAM_STATS_CH = re.compile(r"^---\s*channel\s+(\d+)\s*---")
_DRAM_CTRL_KEYS = ("num_read_reqs", "num_write_reqs", "num_maintenance_reqs",
                   "row_hits", "row_misses", "row_conflicts")
_DRAM_CTRL_LINE = re.compile(
    r"^\s*(" + "|".join(_DRAM_CTRL_KEYS) + r"):\s*(\d+)\s*$"
)


def _coerce(raw: str) -> object:
    """Coerce a config value string: int → float → quoted/plain string."""
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def parse_config(text: str) -> Dict[str, object]:
    """Extract the ``PyTorchSim config:`` key/value block.

    Config lines are printed bare (no ``[timestamp]`` prefix) immediately after the
    marker; the block ends at the first timestamped line.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _CONFIG_MARKER in line:
            start = i
            break
    if start is None:
        raise TogsimLogError(
            f"no {_CONFIG_MARKER!r} header found (older 'TOGSim Config: {{JSON}}' "
            f"logs are no longer supported — re-run with a current PyTorchSim build)"
        )
    config: Dict[str, object] = {}
    for line in lines[start + 1:]:
        if line.startswith("["):          # next timestamped log line = end of block
            break
        m = _CONFIG_LINE.match(line.strip())
        if m:
            config[m.group(1)] = _coerce(m.group(2))
    if not config:
        raise TogsimLogError(f"{_CONFIG_MARKER!r} block is empty")
    return config


def parse_icnt_config(text: str) -> Optional[Dict[str, object]]:
    """The BookSim2 ``[config]`` block the simulator echoes at init, or ``None``.

    Absent for non-BookSim interconnects (``icnt_type != booksim2``) and for
    logs from builds that do not echo it — the caller treats ``None`` as "NoC
    not modelable from this log".
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _ICNT_MARKER:
            start = i
            break
    if start is None:
        return None
    icnt: Dict[str, object] = {}
    for line in lines[start + 1:]:
        s = line.strip()
        if not s:
            continue                       # blank section separators
        if s.startswith("["):              # next timestamped line = end of block
            break
        m = _ICNT_LINE.match(s)
        if m:
            icnt[m.group(1)] = _coerce(m.group(2))
    return icnt or None


def parse_dram_ctrl_stats(text: str) -> Optional[Dict[str, int]]:
    """Ramulator2's per-channel controller counters, summed over channels.

    Reads the log's final ``=== DRAM statistics ===`` block (the LAST marker
    when several appear). Returns ``None`` when the log has no such block
    (older TOGSim builds) or when no channel reports a request counter —
    callers then fall back to the ``[DRAM]`` request totals, losing the
    row-activation / refresh split. Channels repeated in the block keep their
    last occurrence (same last-wins convention as the periodic stat lines).
    """
    idx = text.rfind(_DRAM_STATS_MARKER)
    if idx < 0:
        return None
    per_channel: Dict[int, Dict[str, int]] = {}
    current: Optional[Dict[str, int]] = None
    for line in text[idx + len(_DRAM_STATS_MARKER):].splitlines():
        m = _DRAM_STATS_CH.match(line.strip())
        if m:
            current = per_channel.setdefault(int(m.group(1)), {})
            current.clear()                 # repeated channel: last block wins
            continue
        if current is None:
            continue
        m = _DRAM_CTRL_LINE.match(line)
        if m:
            current[m.group(1)] = int(m.group(2))
    channels = {c: v for c, v in per_channel.items()
                if "num_read_reqs" in v or "num_write_reqs" in v}
    if not channels:
        return None
    totals = {k: sum(v.get(k, 0) for v in channels.values())
              for k in _DRAM_CTRL_KEYS}
    totals["channels"] = len(channels)
    return totals


def parse_kernel_hash(text: str) -> str:
    """The kernel hash joining this log to its ``outputs/<hash>/`` dir.

    Sources, in precedence order:

    1. the command line's ``--trace_so .../outputs/<hash>/trace.so``
       (fallback ``--cycle_table``) — author builds, one kernel per log;
    2. a **unique** ``outputs/<hash>/`` mention in the log body — the
       ISPASS-tutorial ``--models_list`` build has no hash on the command line,
       but its scheduler lines name each kernel's ``tile_graph.onnx`` path. A
       models_list log that ran SEVERAL kernels mentions several dirs; its
       combined activity cannot be attributed per kernel, so that is an error
       (run one kernel per invocation when collecting for NPUWattch).
    """
    m = _TRACE_SO.search(text) or _CYCLE_TABLE.search(text)
    if m:
        return m.group(1)
    hashes = sorted(set(_OUTPUTS_DIR.findall(text)))
    if len(hashes) == 1:
        return hashes[0]
    if len(hashes) > 1:
        raise TogsimLogError(
            f"models_list log mentions {len(hashes)} kernel dirs "
            f"({', '.join(hashes[:4])}{', …' if len(hashes) > 4 else ''}) — "
            f"its combined activity cannot be split per kernel; re-run with "
            f"one kernel per simulator invocation"
        )
    raise TogsimLogError(
        "no kernel hash: expected '--trace_so .../outputs/<hash>/trace.so' on "
        "the command line, or (models_list builds) an outputs/<hash>/ path in "
        "the log body"
    )


@dataclass(frozen=True)
class TogsimActivity:
    kernel_hash: str
    config: Dict[str, object]
    lanes: int
    num_cores: int
    arrays_per_core: Optional[int]
    core_freq_mhz: Optional[float]
    systolic_active_cycles: int              # summed over cores × arrays (cumulative)
    vector_active_cycles: int                # summed over cores (cumulative)
    comp_gemm_ops: int                       # summed over cores
    comp_vector_ops: int
    total_exec_cycles: Optional[int]
    dram_reads: Optional[int] = None         # whole-chip DRAM requests (final)
    dram_writes: Optional[int] = None
    icnt_config: Optional[Dict[str, object]] = None   # BookSim [config] echo
    #: NUMA request split, summed over cores (None when the log has no NUMA
    #: line — pre-NUMA builds). local + remote should equal the DRAM total.
    numa_local: Optional[int] = None
    numa_remote: Optional[int] = None
    #: BookSim's last "Injected packet length average" (None when absent).
    booksim_avg_packet_length: Optional[float] = None
    #: Ramulator2 controller totals from the "=== DRAM statistics ===" block
    #: (summed over channels: num_read/write_reqs, num_maintenance_reqs,
    #: row_hits/misses/conflicts, + 'channels'). None for logs without the
    #: block — the analytic DRAM model then degrades (no ACT/refresh split).
    dram_ctrl: Optional[Dict[str, int]] = None
    #: The run's declared DRAM energy table ([Config/Energy] echo) — the name
    #: is the table's own `name:` key. The dram compound's built-in constants
    #: are the HBM2 table; read_run warns when a run declares a different one.
    #: None for logs without the echo (pre-2026-08 builds).
    energy_table_name: Optional[str] = None
    energy_table_path: Optional[str] = None
    #: Parse-level consistency notes (config key vs [Config/DRAM] echo
    #: disagreements) — read_run copies them into the window warnings.
    warnings: List[str] = field(default_factory=list)
    per_core: Dict[int, Dict[str, object]] = field(default_factory=dict)


def _as_int(config: Dict[str, object], key: str) -> Optional[int]:
    v = config.get(key)
    return int(v) if isinstance(v, (int, float)) else None


def parse_togsim_log(text: str,
                     base_config: Optional[Dict[str, object]] = None) -> TogsimActivity:
    """Parse one TOGSim log. ``base_config`` (from ``config.yml``) fills keys a
    damaged header is missing — the header always wins on overlap."""
    config = {**(base_config or {}), **parse_config(text)}
    lanes = _as_int(config, "vpu_num_lanes")
    if lanes is None:
        raise TogsimLogError("config has no integer 'vpu_num_lanes'")
    num_cores = _as_int(config, "num_cores") or 1
    kernel_hash = parse_kernel_hash(text)

    # [Config/DRAM] init echo: fills dram_channels / dram_req_size_byte when
    # the config (header + config.yml) lacks them — the echo states what the
    # simulator actually used. An explicit config key still wins on overlap
    # (same precedence as header-over-yml); a disagreement is warned.
    log_warnings: List[str] = []
    m = _DRAM_CFG_ECHO.search(text)
    if m:
        for key, echoed in (("dram_channels", int(m.group(1))),
                            ("dram_req_size_byte", int(m.group(2)))):
            cur = config.get(key)
            if not isinstance(cur, int):
                config[key] = echoed
            elif cur != echoed:
                log_warnings.append(
                    f"config {key}={cur} disagrees with the [Config/DRAM] "
                    f"echo ({echoed}); keeping the config value"
                )
    m = _ENERGY_TABLE_ECHO.search(text)
    energy_table_name = m.group(1) if m else None
    energy_table_path = m.group(2) if m else None

    # last value per (core, array) / per core = cumulative total.
    sys_last: Dict[tuple, int] = {}
    for m in _SYS.finditer(text):
        sys_last[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    vec_last: Dict[int, int] = {}
    for m in _VEC.finditer(text):
        vec_last[int(m.group(1))] = int(m.group(2))

    comp: Dict[int, tuple] = {}
    for m in _COMP.finditer(text):
        comp[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    mov: Dict[int, Dict[str, int]] = {}
    for m in _MOV.finditer(text):
        mov.setdefault(int(m.group(1)), {})[m.group(2)] = int(m.group(3))

    # DMA engine block: last line per core = cumulative (active, idle, responses).
    dma_last: Dict[int, tuple] = {}
    for m in _DMA.finditer(text):
        dma_last[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))

    # NUMA local/remote request split: last line per core = cumulative.
    numa_last: Dict[int, tuple] = {}
    for m in _NUMA.finditer(text):
        numa_last[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))

    pkt = _PKT_LEN.findall(text)
    try:
        avg_pkt_len = float(pkt[-1]) if pkt else None
    except ValueError:
        avg_pkt_len = None

    te = _TOTAL_EXEC.search(text)
    total_exec = int(te.group(1)) if te else None

    # DRAM request totals: the "channels N..M combined" line when present, else
    # the sum of each channel's last (cumulative) report.
    dram_reads = dram_writes = None
    combined = _DRAM_ALL.findall(text)
    if combined:
        dram_reads, dram_writes = (int(x) for x in combined[-1])
    else:
        ch_last: Dict[int, tuple] = {}
        for m in _DRAM_CH.finditer(text):
            ch_last[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
        if ch_last:
            dram_reads = sum(r for r, _ in ch_last.values())
            dram_writes = sum(w for _, w in ch_last.values())

    per_core: Dict[int, Dict[str, object]] = {}
    core_ids = (set(c for c, _ in sys_last) | set(vec_last) | set(comp)
                | set(mov) | set(dma_last) | set(numa_last))
    for c in sorted(core_ids):
        arrays = {a: v for (cc, a), v in sys_last.items() if cc == c}
        g = comp.get(c, (0, 0, 0))
        d = dma_last.get(c, (0, 0, 0))
        n = numa_last.get(c, (0, 0))
        per_core[c] = {
            "systolic_active_cycles": sum(arrays.values()),
            "arrays": arrays,
            "vector_active_cycles": vec_last.get(c, 0),
            "comp_inst": g[0],
            "comp_gemm_ops": g[1],
            "comp_vector_ops": g[2],
            "movin": mov.get(c, {}).get("MOVIN", 0),
            "movout": mov.get(c, {}).get("MOVOUT", 0),
            "dma_active_cycles": d[0],
            "dma_idle_cycles": d[1],
            "dma_responses": d[2],
            "numa_local": n[0],
            "numa_remote": n[1],
        }

    return TogsimActivity(
        kernel_hash=kernel_hash,
        config=config,
        lanes=lanes,
        num_cores=num_cores,
        arrays_per_core=_as_int(config, "num_systolic_array_per_core"),
        core_freq_mhz=(float(config["core_freq_mhz"])
                       if isinstance(config.get("core_freq_mhz"), (int, float)) else None),
        systolic_active_cycles=sum(sys_last.values()),
        vector_active_cycles=sum(vec_last.values()),
        comp_gemm_ops=sum(g[1] for g in comp.values()),
        comp_vector_ops=sum(g[2] for g in comp.values()),
        total_exec_cycles=total_exec,
        dram_reads=dram_reads,
        dram_writes=dram_writes,
        icnt_config=parse_icnt_config(text),
        numa_local=(sum(l for l, _ in numa_last.values()) if numa_last else None),
        numa_remote=(sum(r for _, r in numa_last.values()) if numa_last else None),
        booksim_avg_packet_length=avg_pkt_len,
        dram_ctrl=parse_dram_ctrl_stats(text),
        energy_table_name=energy_table_name,
        energy_table_path=energy_table_path,
        warnings=log_warnings,
        per_core=per_core,
    )
