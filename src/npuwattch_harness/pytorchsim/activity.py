"""Assemble PyTorchSim run outputs into NPUWattch-consumable activity windows.

One compiled kernel = one **window**. PyTorchSim writes its two result sets to
*separate* locations (author guidance, 2026-07-20): TOGSim logs to a
``togsim_results/`` directory and per-kernel gem5/codegen artifacts to
``outputs/<hash>/`` (delivery bundles: ``gem5_outputs/<hash>/``). ``read_run``
therefore takes the **two directories explicitly** and joins them per kernel by
the hash from each log's ``--trace_so .../outputs/<hash>/trace.so`` command line:

    architecture  ← MacConfig from <gem5_dir>/<hash>/meta.txt + MLIR (mac_config.py)
    activity      ← systolic/vector cycles + COMP ops                (togsim_log.py)
    activity      ← CustomMatMul* instruction counts                 (gem5_stats.py)

``outputs/<hash>/togsim_result/`` (when present in a raw tree) holds autotune
*candidate* logs, not final results — only the root ``togsim_results/`` logs are
authoritative, which is exactly why the TOGSim directory is a separate input.

The result is a list of ``KernelWindow`` carrying a ``stats`` dict whose keys are
exactly the projection ``count_from.stat`` names (``systolic_active_cycles``,
``CustomMatMulwVpush``, …). ``bind_window`` then turns a window + a tool
projection + a compound into per-action, per-element **cycle counts in a
stim_mode** — the direct input to energy (the final × per-cycle-energy step needs
the primitive estimator and is out of scope here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..compounds.loader import (
    Compound,
    CompoundBundleError,
    PrimitiveModes,
    Projection,
    ResolvedActionElement,
    resolve_action,
)
from .booksim import derive_noc
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
from .mac_config import (
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config_from_dir,
    infer_mac_config_from_meta,
)
from .togsim_log import TogsimLogError, parse_togsim_log

__all__ = ["KernelWindow", "BoundAction", "read_run", "bind_window"]

# gem5 committedInstType classes the systolic projection may reference.
_MATMUL_INSTS = (
    "CustomMatMul",
    "CustomMatMulwVpush",
    "CustomMatMuliVpush",
    "CustomMatMulvpop",
)

# SFU (per-core transcendental unit, ARCHITECTURE_SPEC §2/§3) op counts — one
# committed instruction = one vector of `lanes` elements through the SFU.
# `CustomVlaneIdx` is deliberately NOT collected: it is lane-index generation
# (not an SFU op) and its energy is negligible.
_SFU_INSTS = (
    "CustomVexp",
    "CustomVexp2",
    "CustomVerf",
    "CustomVtanh",
    "CustomVsin",
    "CustomVcos",
)

# fp32 fallback for the SFU table datatype when the kernel's operand dtype is
# absent or integer (the SFU is a floating-point unit).
_SFU_FALLBACK_EXP_MANT = (8, 23)

# The dram compound's built-in per-command constants ARE the HBM2 table
# (O'Connor & Chatterjee et al., MICRO 2017 — see compounds/dram.yaml). A run
# whose [Config/Energy] echo declares a DIFFERENT table is still charged at
# the built-in constants, so that gets a warning naming the override path.
_BUILTIN_DRAM_TABLE = "HBM2"


@dataclass(frozen=True)
class KernelWindow:
    """One kernel's architecture + activity, ready for a projection.

    The name states the terminology bridge: a "window" is the core's
    harness-neutral time interval of the §3.3 activity
    trace; in THIS harness one compiled kernel fills exactly one window, so
    user-facing output calls these "kernels" while schema/code identifiers
    keep "window" (other harnesses have windows that are not kernels — gem5
    periodic dumps, Timeloop layers, the vectorless synthetic interval).
    """

    index: int
    kernel_hash: str
    log_name: str
    mac_config: Optional[MacConfig]
    stats: Dict[str, float]
    lanes: int
    config: Dict[str, object]              # TOGSim config header (this run)
    exec_cycles: Optional[int]
    warnings: List[str] = field(default_factory=list)
    #: The log's per-core counter block (togsim_log per_core): per-core systolic/
    #: vector active cycles, per-array cycles, MOVIN/MOVOUT counts. This is what
    #: the per-instance split (instances.py) distributes chip-aggregate stats by.
    per_core: Dict[int, Dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundAction:
    """A native action bound to a window: total element-cycles per stim_mode.

    ``cycle_count = stat_value × scale`` is how many cycles each element spends in
    its assigned ``stim_mode``. Energy = ``cycle_count × per_cycle_energy(primitive,
    config, stim_mode)`` — the last factor comes from the primitive estimator.
    """

    action: str
    stat: str
    stat_value: float
    scale: int
    cycle_count: float
    elements: List[ResolvedActionElement]
    #: count_from.unit — "words" leaves cycle_count as-is; "bytes"/"vectors"
    #: are converted to memory words by the emitter (which knows the resolved
    #: macro's word width).
    unit: str = "words"


def _num(x: float) -> float:
    return int(x) if float(x).is_integer() else x


def read_run(togsim_dir: Path, gem5_dir: Path, *,
             base_config: Optional[Dict[str, object]] = None,
             pipeline_stages: int = 2,
             booksim_dir: Optional[Path] = None,
             expected_dram_table: Optional[str] = None) -> List[KernelWindow]:
    """Read a PyTorchSim run (two explicit directories) into per-kernel windows.

    ``togsim_dir`` holds the final TOGSim logs (the raw tree's root
    ``togsim_results/`` — never ``outputs/<hash>/togsim_result/`` autotune
    candidates). ``gem5_dir`` holds the per-kernel dirs (raw: ``outputs/``,
    delivery bundle: ``gem5_outputs/``). Each log is one executed kernel, joined
    to ``<gem5_dir>/<hash>/`` by its command-line hash; ``<gem5_dir>`` entries
    without a log are unexecuted autotune candidates and are skipped. lanes come
    from each log's config header.

    ``booksim_dir`` (optional, the run's ``booksim2_config/``) supplies the
    ``.net`` network file that ``anynet`` NoC topologies need; ``fly`` topologies
    are self-contained in the log's embedded BookSim config echo (booksim.py).

    ``expected_dram_table`` (optional): the name of the energy table whose
    constants WILL be charged — the ``--energy-table`` file's ``name`` when one
    is supplied; ``None`` means the built-in HBM2 constants. A log whose
    ``[Config/Energy]`` echo declares a different table is warned.
    """
    log_dir = Path(togsim_dir)
    out_dir = Path(gem5_dir)
    if not log_dir.is_dir():
        raise MacInferenceError(f"TOGSim log directory not found: {log_dir}")
    if not out_dir.is_dir():
        raise MacInferenceError(f"gem5/codegen output directory not found: {out_dir}")
    if not sorted(log_dir.glob("*.log")):
        raise MacInferenceError(
            f"no *.log in {log_dir} — pass the run's final togsim_results/ "
            f"directory (autotune logs under outputs/<hash>/togsim_result/ are "
            f"candidates, not results)"
        )

    windows: List[KernelWindow] = []
    skipped: List[str] = []
    seen_noc_warnings: set = set()      # identical per-log NoC notes reported once
    for idx, log_path in enumerate(sorted(log_dir.glob("*.log"))):
        warnings: List[str] = []
        try:
            act = parse_togsim_log(
                log_path.read_text(encoding="utf-8", errors="ignore"),
                base_config=base_config,
            )
        except TogsimLogError as e:
            skipped.append(f"{log_path.name}: {e}")
            continue
        khash = act.kernel_hash
        warnings.extend(f"{khash}: {w}" for w in act.warnings)
        kernel_dir = out_dir / khash

        # architecture: MacConfig from the codegen artifacts. MLIR is the
        # primary source; author delivery bundles ship none, so fall back to
        # meta.txt-only inference — gated on the log actually showing systolic/
        # GEMM activity, because without linalg.matmul the meta cannot prove
        # the kernel is a matmul.
        mac_config: Optional[MacConfig] = None
        if kernel_dir.is_dir():
            has_mlir = any(kernel_dir.glob("*.mlir"))
            meta_path = kernel_dir / "meta.txt"
            gemm_active = act.systolic_active_cycles > 0 or act.comp_gemm_ops > 0
            if has_mlir:
                try:
                    mac_config = infer_mac_config_from_dir(
                        kernel_dir, act.lanes, pipeline_stages=pipeline_stages
                    )
                    warnings.extend(mac_config.warnings)
                except NotAMatmulKernel:
                    warnings.append(f"{khash}: kernel has no linalg.matmul; no MAC config")
                except MacInferenceError as e:
                    warnings.append(f"{khash}: MAC config inference failed: {e}")
            elif not gemm_active:
                warnings.append(
                    f"{khash}: no kernel MLIR and no systolic/GEMM activity in the "
                    f"log; treated as a non-MAC kernel"
                )
            elif meta_path.is_file():
                try:
                    mac_config = infer_mac_config_from_meta(
                        meta_path.read_text(encoding="utf-8"), act.lanes,
                        pipeline_stages=pipeline_stages,
                    )
                    warnings.extend(f"{khash}: {w}" for w in mac_config.warnings)
                except MacInferenceError as e:
                    warnings.append(
                        f"{khash}: meta.txt-only MAC config inference failed: {e}"
                    )
            else:
                warnings.append(
                    f"{khash}: no kernel MLIR and no meta.txt; MAC config unavailable"
                )
        else:
            warnings.append(
                f"{khash}: {out_dir.name}/{khash}/ not found; MAC config unavailable"
            )

        # activity: gem5 CustomMatMul* + numCycles.
        stats: Dict[str, float] = {
            "systolic_active_cycles": act.systolic_active_cycles,
            "vector_active_cycles": act.vector_active_cycles,
            "comp_gemm_ops": act.comp_gemm_ops,
            "comp_vector_ops": act.comp_vector_ops,
        }
        if act.total_exec_cycles is not None:
            stats["total_exec_cycles"] = act.total_exec_cycles
        # DRAM traffic in bytes (VMEM fill/drain estimate): request counts from
        # the log x the config's request size (32 B when the config omits it —
        # the HBM2 default of every sample seen so far).
        if act.dram_reads is not None:
            req_size = act.config.get("dram_req_size_byte")
            if not isinstance(req_size, int):
                req_size = 32
                warnings.append(
                    f"{khash}: config has no dram_req_size_byte; assuming "
                    f"{req_size} B per DRAM request for byte traffic"
                )
            stats["dram_read_bytes"] = act.dram_reads * req_size
            stats["dram_write_bytes"] = act.dram_writes * req_size
            # DMA engine events: one queue transit + one address add per DRAM
            # request (docs/DESIGN_SFU_DMA.md §1).
            stats["dram_requests"] = act.dram_reads + act.dram_writes
            # Cross-check against the per-core DMA blocks: the final DMA line's
            # cumulative response count equals that core's DRAM requests.
            dma_total = sum(int(pc.get("dma_responses", 0) or 0)
                            for pc in act.per_core.values())
            if dma_total and dma_total != stats["dram_requests"]:
                warnings.append(
                    f"{khash}: per-core DMA responses total {dma_total} != "
                    f"[DRAM] request total {stats['dram_requests']}; using the "
                    f"[DRAM] total (per-core split still uses the DMA shares)"
                )

        # DRAM device command counts (the analytic HBM energy model — the dram
        # compound). Ramulator2's "=== DRAM statistics ===" controller block is
        # the primary source: it carries the MEASURED row hit/miss/conflict
        # split, so ACT(+PRE) commands = row_misses + row_conflicts and refresh
        # = num_maintenance_reqs — no trace synthesis or hit-rate assumption.
        # Logs without the block (older builds) fall back to the [DRAM] request
        # totals: read/write energy is still charged, ACT/refresh is not.
        ctrl = act.dram_ctrl
        if ctrl is not None:
            stats["dram_read_cmds"] = ctrl["num_read_reqs"]
            stats["dram_write_cmds"] = ctrl["num_write_reqs"]
            stats["dram_act_cmds"] = ctrl["row_misses"] + ctrl["row_conflicts"]
            stats["dram_ref_cmds"] = ctrl["num_maintenance_reqs"]
            if (act.dram_reads is not None
                    and (ctrl["num_read_reqs"], ctrl["num_write_reqs"])
                    != (act.dram_reads, act.dram_writes)):
                warnings.append(
                    f"{khash}: DRAM statistics block reports "
                    f"{ctrl['num_read_reqs']} reads / {ctrl['num_write_reqs']} "
                    f"writes but the [DRAM] interval totals sum to "
                    f"{act.dram_reads} / {act.dram_writes}; device energy uses "
                    f"the statistics block (VMEM/NoC traffic keeps the totals)"
                )
        elif act.dram_reads is not None:
            stats["dram_read_cmds"] = act.dram_reads
            stats["dram_write_cmds"] = act.dram_writes
            warnings.append(
                f"{khash}: log has no '=== DRAM statistics ===' block; DRAM "
                f"read/write energy is charged from the [DRAM] request totals, "
                f"but row-activation and refresh energy are NOT charged"
            )

        # The run's declared energy table ([Config/Energy] echo) vs what the
        # dram compound will actually charge — the supplied --energy-table
        # when given, else the built-in HBM2 constants. A mismatch means the
        # numbers would be silently attributed to the wrong memory technology.
        charged = expected_dram_table or _BUILTIN_DRAM_TABLE
        if (act.energy_table_name is not None
                and act.energy_table_name != charged):
            if expected_dram_table is not None:
                warnings.append(
                    f"{khash}: run declares DRAM energy table "
                    f"{act.energy_table_name!r} ({act.energy_table_path}), but "
                    f"--energy-table supplied {charged!r} — its constants are "
                    f"charged; pass the run's own table file instead"
                )
            else:
                warnings.append(
                    f"{khash}: run declares DRAM energy table "
                    f"{act.energy_table_name!r} ({act.energy_table_path}), but "
                    f"the dram compound charges the built-in "
                    f"{_BUILTIN_DRAM_TABLE} constants — pass the run's table "
                    f"via --energy-table (or override mem_act_energy_pJ / "
                    f"mem_access_energy_per_bit_pJ / mem_ref_energy_pJ in a "
                    f"bundle copy of compounds/dram.yaml)"
                )

        # NoC (BookSim2): topology symbols (icnt_ports/routers/channels + the raw
        # booksim_* config ints) join the run-config expression symbols, and flit
        # stats drive the projection's noc actions. A run whose NoC cannot be
        # modeled degrades to a warning — never an error.
        noc = derive_noc(act, booksim_dir=booksim_dir)
        win_config = dict(act.config)
        win_config.update(noc.symbols)
        # The dma compound's queue width is `dram_req_size_byte*8`; make the
        # symbol always resolvable (32 B is the HBM2 default of every sample).
        if not isinstance(win_config.get("dram_req_size_byte"), int):
            win_config["dram_req_size_byte"] = 32
        stats.update(noc.stats)
        for msg in noc.warnings:
            if msg not in seen_noc_warnings:
                seen_noc_warnings.add(msg)
                warnings.append(msg)

        stats_path = kernel_dir / "m5out" / "stats.txt"
        if stats_path.is_file():
            sections = parse_sections(stats_path.read_text(encoding="utf-8", errors="ignore"))
            inst = sum_committed_inst(sections)
            for name in _MATMUL_INSTS + _SFU_INSTS:
                stats[name] = float(inst.get(name, 0))
            stats["numCycles"] = sum_stat(sections, "system.cpu.numCycles")
        else:
            warnings.append(f"{khash}: no m5out/stats.txt; gem5 instruction counts unavailable")

        # SFU table datatype: the fpsfu compound resolves its exponent_bits /
        # mantissa_bits from these injected symbols. The SFU is an fp unit, so
        # an int kernel (or one with no MAC config) falls back to fp32 tables —
        # only worth a warning when the kernel actually ran SFU ops.
        sfu_exp, sfu_mant = _SFU_FALLBACK_EXP_MANT
        od = mac_config.operand_dtype if mac_config is not None else None
        if (od is not None and od.kind == "float"
                and isinstance(od.exp_bits, int) and isinstance(od.mantissa_bits, int)):
            sfu_exp, sfu_mant = od.exp_bits, od.mantissa_bits
        elif any(stats.get(name) for name in _SFU_INSTS):
            warnings.append(
                f"{khash}: SFU ops present but the kernel's operand dtype is "
                f"{'integer' if od is not None else 'unknown'}; charging the SFU "
                f"at fp32 (e8m23) tables"
            )
        win_config["sfu_exponent_bits"] = sfu_exp
        win_config["sfu_mantissa_bits"] = sfu_mant

        windows.append(
            KernelWindow(
                index=idx,
                kernel_hash=khash,
                log_name=log_path.name,
                mac_config=mac_config,
                stats={k: _num(v) for k, v in stats.items()},
                lanes=act.lanes,
                config=win_config,
                exec_cycles=act.total_exec_cycles,
                warnings=warnings,
                per_core=act.per_core,
            )
        )
    if not windows and skipped:
        raise MacInferenceError(
            "no parseable TOGSim log in "
            f"{log_dir} — " + "; ".join(skipped)
        )
    if skipped:
        windows[0].warnings.insert(
            0, f"{len(skipped)} unparseable log(s) skipped: " + "; ".join(skipped)
        )
    return windows


def bind_window(
    window: KernelWindow,
    projection: Projection,
    compound: Compound,
    primitive_modes: PrimitiveModes,
    *,
    skipped: Optional[List[str]] = None,
) -> List[BoundAction]:
    """Bind a window's activity to a projection+compound → per-action cycle counts.

    Only actions whose ``count_from.stat`` is present in the window are emitted;
    a missing stat is skipped (recorded in the window's warnings by the caller's
    convention). Requires the window to have a resolved ``mac_config``.

    ``skipped`` (optional): when given, an action whose element resolution fails
    (e.g. a capacity expression over a run-config symbol this run lacks — the
    matching element was already "not emitted" by the emitter) is recorded there
    and skipped instead of raising, mirroring the emitter's element-by-element
    leniency. Without it, resolution errors raise (definition-bug gate).
    """
    if window.mac_config is None:
        raise MacInferenceError(
            f"window {window.kernel_hash} has no MAC config; cannot bind projection"
        )
    # Integer run-config keys double as expression symbols — a bundle is
    # harness-owned, so its compounds/projections may use them.
    extra_symbols = {
        k: v for k, v in (window.config or {}).items()
        if isinstance(v, int) and not isinstance(v, bool)
    }
    actions = projection.compounds.get(compound.name, {})
    bound: List[BoundAction] = []
    for action_name, mapping in actions.items():
        stat = mapping.count_from.stat
        if stat not in window.stats:
            continue  # unmapped for this run — dropped, never silently charged
        try:
            ares = resolve_action(projection, compound, action_name,
                                  window.mac_config, primitive_modes,
                                  extra_symbols=extra_symbols)
        except CompoundBundleError as e:
            if skipped is None:
                raise
            skipped.append(f"{compound.name}.{action_name}: not charged — {e}")
            continue
        stat_value = window.stats[stat]
        bound.append(
            BoundAction(
                action=action_name,
                stat=stat,
                stat_value=stat_value,
                scale=ares.scale,
                cycle_count=_num(stat_value * ares.scale),
                elements=ares.elements,
                unit=ares.unit,
            )
        )
    return bound
