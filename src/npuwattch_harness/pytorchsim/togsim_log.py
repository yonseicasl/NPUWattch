"""Parse a TOGSim run log (``togsim_results/*.log``).

The TOGSim log is the primary activity input. Its header shows the full run
configuration. Its body gives the **on-chip** activity of each core:

* the active cycles of the systolic arrays and of the vector unit,
* the COMP GEMM operation counts,
* the active cycles, idle cycles, and response counts of the DMA engine.

The parser also reads these off-chip lines:

* The final DRAM request totals. The VMEM traffic and the NoC traffic come
  from them.
* The BookSim ``[config]`` block, which gives the NoC topology. For a ``fly``
  network the log is sufficient. For an ``anynet`` network the log gives only
  the *path* of the ``.net`` file, thus the file is also necessary.
* The ``[Config/DRAM] … N channels, M bytes per request`` line. It supplies
  ``dram_req_size_byte`` and ``dram_channels`` if the config block does not
  have them. Thus no assumption about the request size is necessary.
* The ``[Config/Energy]`` line. It gives the name and the path of the DRAM
  energy table of the run. ``dram.dram_stats`` compares the name with the
  table that NPUWattch charges.

Log format (the parser does not accept the ``TOGSim Config: {JSON}`` header
format):

- Line 1 is the simulator **command line**. The kernel hash is the ``<hash>`` in
  ``--trace_so .../outputs/<hash>/trace.so``. The hash connects the log to the
  gem5 output directory of the kernel (``<gem5_dir>/<hash>/``). The log body
  has no hash. The hex suffix of the log *filename* is NOT the kernel hash.
- The config block is a ``PyTorchSim config:`` marker, then ``key: value``
  lines without a timestamp. The next line with a timestamp ends the block.
- The log prints the activity block of each core one time for each
  ``core_stats_print_period_cycles``. Each such block is the increment of one
  period. A final cumulative block is at the end. Thus the *last* value for
  each ``(core, systolic-array)`` is the cumulative total. The same rule
  applies to the vector unit of each core. The stat lines use colons:
  ``... utilization(%): 9.79, active_cycles: 64, ...``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from npuwattch.diagnostics import NPUWattchError, warning

__all__ = ["TogsimActivity", "TogsimLogError", "parse_config",
           "parse_dram_ctrl_stats", "parse_icnt_config", "parse_togsim_log"]


class TogsimLogError(NPUWattchError, ValueError):
    """The TOGSim log has an incorrect format or does not have a necessary field."""


#: Kernel hash from the command line (--trace_so or --cycle_table).
_TRACE_SO = re.compile(r"--trace_so\s+\S*?[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]trace\.so")
_CYCLE_TABLE = re.compile(r"--cycle_table\s+\S*?[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]")
#: Some builds use `--models_list <run>.trace`. Then the command line has no
#: hash. The scheduler lines in the log body give the kernel directory:
#: `tog_path: .../outputs/<hash>/tile_graph.onnx`.
#: The hash is known if the log body names exactly ONE kernel directory.
_OUTPUTS_DIR = re.compile(r"[/\\]outputs[/\\]([A-Za-z0-9]+)[/\\]")

_CONFIG_MARKER = "PyTorchSim config:"
_CONFIG_LINE = re.compile(r"^([A-Za-z_]\w*):\s*(.*)$")

# The config block that BookSim2 prints: a "[config]" line, then "key = value"
# lines. Blank lines divide the sections. The next "[...]" line with a
# timestamp ends the block.
_ICNT_MARKER = "[config]"
_ICNT_LINE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")

_SYS = re.compile(
    r"Core \[(\d+)\] : Systolic array \[(\d+)\]\s+[Uu]tilization\(%\)\s*:\s*[\d.]+,"
    r"\s*active[ _]cycles?\s*:\s*(\d+)"
)
# The periodic line and the final line use different spellings:
# "active_cycles:" and "active cycle:".
_VEC = re.compile(
    r"Core \[(\d+)\] : Vector unit\s+[Uu]tilization\(%\)\s*:\s*[\d.]+,"
    r"\s*active[ _]cycles?\s*:\s*(\d+)"
)
_COMP = re.compile(
    r"Core \[(\d+)\] : COMP\s+inst_count\s*:\s*(\d+)\s+\(GEMM:\s*(\d+),\s*Vector:\s*(\d+)\)"
)
_MOV = re.compile(r"Core \[(\d+)\] : (MOVIN|MOVOUT)\s+inst_count\s*:\s*(\d+)")
# Core [0] : DMA active_cycles: 8905, DMA idle_cycles: 1095, DRAM BW: 278.000 GB/s (92430 responses)
# A periodic line gives the increment of one period (active + idle = the print
# period). The final line is cumulative. The systolic and vector blocks use
# the same rule. The final response count is equal to the total DRAM requests
# of the run.
_DMA = re.compile(
    r"Core \[(\d+)\] : DMA active[ _]cycles?\s*:\s*(\d+),\s*"
    r"DMA idle[ _]cycles?\s*:\s*(\d+).*?\((\d+) responses\)"
)
_TOTAL_EXEC = re.compile(r"Total execution cycles:\s+(\d+)")

# Core [0] : NUMA local memory: 393216 requests, remote memory: 0 requests
# The final block has one such line for each core. The line gives the EXACT
# split of the DRAM requests into local and remote. For a chiplet (anynet)
# run, this split replaces the uniform-traffic assumption of the NoC.
_NUMA = re.compile(
    r"Core \[(\d+)\] : NUMA local memory:\s*(\d+) requests?,\s*"
    r"remote memory:\s*(\d+) requests?"
)

# The BookSim statistics at the end of the run (lines without a [timestamp]
# prefix):
#   Injected packet length average = 1
# The NoC flit model assumes 1 flit/packet. The LAST reported average is the
# check of this assumption and the scale factor for the flit totals.
_PKT_LEN = re.compile(r"^Injected packet length average\s*=\s*([\d.eE+-]+)\s*$",
                      re.MULTILINE)

# [DRAM] channel 5 | ... | 48 reads, 16 writes        (per-channel, cumulative)
# [DRAM] channels 0..15 combined | ... | 772 reads, 256 writes
_DRAM_CH = re.compile(r"\[DRAM\] channel (\d+) \|.*\|\s*(\d+) reads?,\s*(\d+) writes?")
_DRAM_ALL = re.compile(r"\[DRAM\] channels [\d.]+ combined \|.*\|\s*(\d+) reads?,\s*(\d+) writes?")

# The one-line DRAM configuration that the front end prints at the start. It
# gives the request size that the run used. The config header usually has no
# dram_req_size_byte key.
#   [Config/DRAM] Total bandwidth 481.28 GB/s, 940 MHz, 16 channels, 32 bytes per request
_DRAM_CFG_ECHO = re.compile(
    r"\[Config/DRAM\][^\n]*?\b(\d+)\s+channels,\s*(\d+)\s+bytes per request")

# The DRAM energy table of the run (config key `energy_cost_table_path`).
# The log text can be "energy table" or "energy cost table":
#   [Config/Energy] Loaded energy cost table "HBM2" from /path/hbm2.yml
_ENERGY_TABLE_ECHO = re.compile(
    r'\[Config/Energy\] Loaded energy (?:cost )?table "([^"]+)" from (\S+)')

# The Ramulator2 controller statistics at the end of the run. A
# "=== DRAM statistics ===" marker comes first. Then each channel has one
# "--- channel N ---" block of "key: value" lines. The analytic DRAM energy
# model uses these controller counters:
#   ACT(+PRE) commands = row_misses + row_conflicts
#   RD / WR            = num_read_reqs / num_write_reqs
#   refresh            = num_maintenance_reqs
# With the open-row policy, each miss and each conflict activates one row.
# The patterns match only the controller totals. They do NOT match the lines
# for each kind (`read_row_hits: …`) or for each core
# (`read_row_hits_core_0: …`).
_DRAM_STATS_MARKER = "=== DRAM statistics ==="
_DRAM_STATS_CH = re.compile(r"^---\s*channel\s+(\d+)\s*---")
_DRAM_CTRL_KEYS = ("num_read_reqs", "num_write_reqs", "num_maintenance_reqs",
                   "row_hits", "row_misses", "row_conflicts")
_DRAM_CTRL_LINE = re.compile(
    r"^\s*(" + "|".join(_DRAM_CTRL_KEYS) + r"):\s*(\d+)\s*$"
)


def _coerce(raw: str) -> object:
    """Convert a config value string: quoted string, then int, then float, then plain string."""
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
    """Get the key/value block after the ``PyTorchSim config:`` marker.

    The config lines come immediately after the marker and have no
    ``[timestamp]`` prefix. The block ends at the first line with a timestamp.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _CONFIG_MARKER in line:
            start = i
            break
    if start is None:
        raise TogsimLogError.nw(6301)
    config: Dict[str, object] = {}
    for line in lines[start + 1:]:
        if line.startswith("["):          # a line with a timestamp ends the block
            break
        m = _CONFIG_LINE.match(line.strip())
        if m:
            config[m.group(1)] = _coerce(m.group(2))
    if not config:
        raise TogsimLogError.nw(6302)
    return config


def parse_icnt_config(text: str) -> Optional[Dict[str, object]]:
    """Return the BookSim2 ``[config]`` block of the log, or ``None``.

    The block is absent if the interconnect is not BookSim
    (``icnt_type != booksim2``) or if the build does not print it. If the
    result is ``None``, the caller cannot model the NoC from this log.
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
            continue                       # blank lines divide the sections
        if s.startswith("["):              # a line with a timestamp ends the block
            break
        m = _ICNT_LINE.match(s)
        if m:
            icnt[m.group(1)] = _coerce(m.group(2))
    return icnt or None


def parse_dram_ctrl_stats(text: str) -> Optional[Dict[str, int]]:
    """Return the Ramulator2 controller counters, summed over the channels.

    The function reads the LAST ``=== DRAM statistics ===`` block of the log.
    It returns ``None`` if the log has no such block or if no channel gives a
    request counter. The caller then uses the ``[DRAM]`` request totals, which
    do not give the split into row activations and refreshes. If a channel
    occurs more than one time in the block, the last occurrence has priority.
    The periodic stat lines use the same rule.
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
            current.clear()                 # repeated channel: the last block has priority
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
    """Return the kernel hash that connects this log to its ``outputs/<hash>/`` directory.

    Sources, in the order of priority:

    1. The command line: ``--trace_so .../outputs/<hash>/trace.so``, or
       ``--cycle_table`` as the fallback. Such a log has one kernel.
    2. One **unique** ``outputs/<hash>/`` path in the log body. A
       ``--models_list`` build has no hash on the command line, but its
       scheduler lines give the ``tile_graph.onnx`` path of each kernel.

    A ``--models_list`` log with more than one kernel names more than one
    directory. The function cannot divide the combined activity between the
    kernels, thus it raises an error. Run one kernel for each simulator
    invocation.
    """
    m = _TRACE_SO.search(text) or _CYCLE_TABLE.search(text)
    if m:
        return m.group(1)
    hashes = sorted(set(_OUTPUTS_DIR.findall(text)))
    if len(hashes) == 1:
        return hashes[0]
    if len(hashes) > 1:
        shown = ", ".join(hashes[:4]) + (", …" if len(hashes) > 4 else "")
        raise TogsimLogError.nw(6303, count=len(hashes), hashes=shown)
    raise TogsimLogError.nw(6304)


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
    dram_reads: Optional[int] = None         # final DRAM requests of the full chip
    dram_writes: Optional[int] = None
    icnt_config: Optional[Dict[str, object]] = None   # BookSim [config] block
    #: NUMA request split, summed over the cores. None if the log has no NUMA
    #: line. The sum of local and remote must agree with the DRAM total.
    numa_local: Optional[int] = None
    numa_remote: Optional[int] = None
    #: The last "Injected packet length average" of BookSim. None if absent.
    booksim_avg_packet_length: Optional[float] = None
    #: Ramulator2 controller totals from the "=== DRAM statistics ===" block,
    #: summed over the channels. The keys are num_read_reqs, num_write_reqs,
    #: num_maintenance_reqs, row_hits, row_misses, row_conflicts, and
    #: 'channels'. None if the log has no such block. The analytic DRAM model
    #: then has no ACT/refresh split.
    dram_ctrl: Optional[Dict[str, int]] = None
    #: The DRAM energy table of the run, from the [Config/Energy] line. The
    #: name is the `name:` key of the table. `dram.dram_stats` gives a
    #: warning if NPUWattch charges a different table. None if the log has no
    #: such line.
    energy_table_name: Optional[str] = None
    energy_table_path: Optional[str] = None
    #: Warnings from the parser: a config key that disagrees with the
    #: [Config/DRAM] line. read_run copies them into the window warnings.
    warnings: List[str] = field(default_factory=list)
    per_core: Dict[int, Dict[str, object]] = field(default_factory=dict)


def _as_int(config: Dict[str, object], key: str) -> Optional[int]:
    v = config.get(key)
    return int(v) if isinstance(v, (int, float)) else None


def parse_togsim_log(text: str,
                     base_config: Optional[Dict[str, object]] = None) -> TogsimActivity:
    """Parse one TOGSim log.

    ``base_config`` (from ``config.yml``) supplies the keys that a damaged
    header does not have. If a key is in the two sources, the header has
    priority.
    """
    config = {**(base_config or {}), **parse_config(text)}
    lanes = _as_int(config, "vpu_num_lanes")
    if lanes is None:
        raise TogsimLogError.nw(6305)
    num_cores = _as_int(config, "num_cores") or 1
    kernel_hash = parse_kernel_hash(text)

    # The [Config/DRAM] line supplies dram_channels and dram_req_size_byte if
    # the run configuration (header and config.yml) does not have them. The
    # line gives the values that the simulator used. An explicit config key
    # has priority. A disagreement gives a warning.
    log_warnings: List[str] = []
    m = _DRAM_CFG_ECHO.search(text)
    if m:
        for key, echoed in (("dram_channels", int(m.group(1))),
                            ("dram_req_size_byte", int(m.group(2)))):
            cur = config.get(key)
            if not isinstance(cur, int):
                config[key] = echoed
            elif cur != echoed:
                log_warnings.append(warning(6306, kernel=kernel_hash, key=key,
                                            value=cur, echoed=echoed))
    m = _ENERGY_TABLE_ECHO.search(text)
    energy_table_name = m.group(1) if m else None
    energy_table_path = m.group(2) if m else None

    # The last value for each (core, array) and for each core is the cumulative total.
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

    # DMA engine block: the last line of each core is cumulative (active, idle, responses).
    dma_last: Dict[int, tuple] = {}
    for m in _DMA.finditer(text):
        dma_last[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))

    # NUMA local/remote request split: the last line of each core is cumulative.
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

    # DRAM request totals: use the "channels N..M combined" line if it is
    # present. If not, add the last (cumulative) report of each channel.
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
