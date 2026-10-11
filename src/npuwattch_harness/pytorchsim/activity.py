"""Read the outputs of a PyTorchSim run into windows and bind their activity.

One compiled kernel is one window. PyTorchSim writes its results to two
different locations:

* The TOGSim logs go to a ``togsim_results/`` directory.
* The gem5 and codegen files of each kernel go to ``outputs/<hash>/``. In a
  delivery bundle, the directory is ``gem5_outputs/<hash>/``.

Thus ``read_run`` gets the two directories as two inputs. The command line in
each log (``--trace_so .../outputs/<hash>/trace.so``) gives the hash of the
kernel. ``read_run`` uses this hash to find the directory of the kernel:

    architecture  ← MacConfig from <gem5_dir>/<hash>/meta.txt + MLIR (mac_config.py)
    activity      ← systolic/vector cycles + COMP ops                (togsim_log.py)
    activity      ← CustomMatMul* instruction counts                 (gem5_stats.py)

A raw run tree can also contain ``outputs/<hash>/togsim_result/``. Those logs
are autotune candidates, not final results. Only the logs in the root
``togsim_results/`` are the results of the run. For this reason, the TOGSim
directory is a separate input.

``read_run`` returns a list of ``KernelWindow``. Each window has a ``stats``
dict. Its keys are the ``count_from.stat`` names of the projection
(``systolic_active_cycles``, ``CustomMatMulwVpush``, ...).

``bind_window`` applies the projection to one window and one compound. For
each action, it gives the cycle count of each element in a stim_mode. The
energy calculation multiplies these counts by the energy of one cycle. The
primitive estimator gives that energy, and this module does not calculate it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from npuwattch.diagnostics import info, warning

from ..compounds.loader import (
    Compound,
    CompoundBundleError,
    PrimitiveModes,
    Projection,
    ResolvedActionElement,
    resolve_action,
)
from .booksim import derive_noc
from .definitions import VOCABULARY
from .dram import dram_stats
from .gem5_stats import parse_sections, section_committed_inst, sum_committed_inst, sum_stat
from .tile_graph import find_tile_graph, read_tile_graph
from .useful_macs import useful_macs
from .mac_config import (
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config_from_dir,
    infer_mac_config_from_meta,
    parse_meta,
)
from .togsim_log import TogsimActivity, TogsimLogError, parse_togsim_log

__all__ = ["KernelWindow", "BoundAction", "read_run", "bind_window"]

#: gem5 instruction classes that the readers collect. The vocabulary table
#: of this harness lists them.
_MATMUL_INSTS = VOCABULARY.stats["matmul_instructions"]
_SFU_INSTS = VOCABULARY.stats["sfu_instructions"]

# The default datatype of the SFU tables: fp32 (8 exponent bits, 23 mantissa
# bits). The SFU is a floating-point unit. It uses this default if the kernel
# has no operand datatype or has an integer datatype.
_SFU_FALLBACK_EXP_MANT = (8, 23)

# The vector type of an SFU operation in the kernel MLIR, for example
# ``math.exp %t : vector<16xf32>``. The width is the number of elements that
# one SFU instruction processes in one lane (the RVV register group).
_SFU_MLIR_OP = re.compile(
    r"math\.(?:exp2?|erf|tanh|sin|cos)\b[^\n:]*:\s*vector<(\d+)x")


@dataclass(frozen=True)
class KernelWindow:
    """The architecture and the activity of one kernel.

    A window is one time interval of the activity (§3.3). This definition is
    the same for all harnesses. In this harness, one compiled kernel is one
    window. Thus the messages to the user say "kernel", and the identifiers
    in the code and in the schema say "window".

    In other harnesses, a window is not a kernel. Examples are a periodic
    gem5 dump, a Timeloop layer, and the interval of a vectorless run.
    """

    index: int
    kernel_hash: str
    log_name: str
    mac_config: Optional[MacConfig]
    stats: Dict[str, float]
    lanes: int
    config: Dict[str, object]              # the run configuration of this log
    exec_cycles: Optional[int]
    warnings: List[str] = field(default_factory=list)
    #: The counters of each core from the log (``per_core`` of togsim_log):
    #: the systolic and vector active cycles, the active cycles of each array,
    #: and the MOVIN and MOVOUT counts. ``instances.py`` uses these counters
    #: to divide the chip totals between the instances.
    per_core: Dict[int, Dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundAction:
    """One action of a compound with the activity of one window.

    ``cycle_count = stat_value × scale`` is the number of cycles that each
    element operates in its ``stim_mode``. The energy is ``cycle_count ×
    per_cycle_energy(primitive, config, stim_mode)``. The primitive estimator
    gives the last factor.
    """

    action: str
    stat: str
    stat_value: float
    scale: int
    cycle_count: float
    elements: List[ResolvedActionElement]
    #: The ``count_from.unit`` of the action. With "words", ``cycle_count`` is
    #: a count of memory words. With "bytes" or "vectors", the emitter converts
    #: ``cycle_count`` to memory words. The emitter has the word width of the
    #: resolved macro.
    unit: str = "words"


def _num(x: float) -> float:
    return int(x) if float(x).is_integer() else x


def _mac_config_for(kernel_dir: Path, act: TogsimActivity,
                    pipeline_stages: int,
                    warnings: List[str]) -> Optional[MacConfig]:
    """Infer the MAC configuration of one kernel from its codegen files.

    The kernel MLIR is the primary source. If there is no MLIR, the function
    uses ``meta.txt``, but only if the log shows systolic or GEMM activity.
    Without ``linalg.matmul``, ``meta.txt`` cannot show that the kernel is a
    matmul. Return ``None`` if the kernel has no MAC configuration.
    """
    khash = act.kernel_hash
    mac_config: Optional[MacConfig] = None
    has_mlir = any(kernel_dir.glob("*.mlir"))
    meta_path = kernel_dir / "meta.txt"
    gemm_active = act.systolic_active_cycles > 0 or act.comp_gemm_ops > 0
    if has_mlir:
        try:
            mac_config = infer_mac_config_from_dir(
                kernel_dir, act.lanes, pipeline_stages=pipeline_stages,
                kernel=khash,
            )
            warnings.extend(mac_config.warnings)
        except NotAMatmulKernel:
            warnings.append(warning(6201, kernel=khash))
        except MacInferenceError as e:
            warnings.append(warning(6202, kernel=khash, error=e))
    elif not gemm_active:
        warnings.append(warning(6203, kernel=khash))
    elif meta_path.is_file():
        try:
            mac_config = infer_mac_config_from_meta(
                meta_path.read_text(encoding="utf-8"), act.lanes,
                pipeline_stages=pipeline_stages, kernel=khash,
            )
            warnings.extend(mac_config.warnings)
        except MacInferenceError as e:
            warnings.append(warning(6204, kernel=khash, error=e))
    else:
        warnings.append(warning(6205, kernel=khash))
    return mac_config


def _gem5_instruction_stats(kernel_dir: Path, khash: str,
                            warnings: List[str], act: TogsimActivity) -> Dict[str, float]:
    """Return the kernel totals of the gem5 instruction counts, and ``numCycles``.

    gem5 runs the sample program of the kernel: one execution of each compute
    node of the tile graph, with one statistics dump after each node
    (``tile_graph.py``, ``gem5_stats.py``). The counts of a dump are the
    counts of one execution of its node. This function scales them to the
    kernel:

    * With the tile graph (``*_tog.py`` in the kernel directory): the counts
      of node ``k`` times the executions of node ``k``. This is exact.
    * Without it: the average of the GEMM-type sections times the COMP GEMM
      count of the log, and the average of the vector-type sections times the
      COMP vector count. This is approximate (``NW-6218``).

    ``numCycles`` stays the sum over the sections: it is the cycle count of
    the sample program and is informational.
    """
    stats: Dict[str, float] = {}
    stats_path = kernel_dir / "m5out" / "stats.txt"
    if not stats_path.is_file():
        warnings.append(warning(6206, kernel=khash))
        return stats
    sections = parse_sections(stats_path.read_text(encoding="utf-8", errors="ignore"))
    stats["numCycles"] = sum_stat(sections, "system.cpu.numCycles")
    per_section = [section_committed_inst(sec) for sec in sections]
    names = list(_MATMUL_INSTS) + list(_SFU_INSTS)
    totals: Dict[str, float] = {n: 0.0 for n in names}

    graph = None
    tog_path = find_tile_graph(kernel_dir)
    if tog_path is not None:
        try:
            graph = read_tile_graph(tog_path)
        except (OSError, ValueError, SyntaxError, KeyError) as e:
            warnings.append(warning(6223, kernel=khash, error=e))
    if graph is not None and len(per_section) - 1 != len(graph.nodes):
        warnings.append(warning(6220, kernel=khash, sections=len(per_section),
                                nodes=len(graph.nodes)))
        graph = None

    if graph is not None:
        for node, counts in zip(graph.nodes, per_section):
            for n in names:
                totals[n] += counts.get(n, 0) * node.executions
        if (graph.gemm_executions != act.comp_gemm_ops
                or graph.vector_executions != act.comp_vector_ops):
            warnings.append(warning(6219, kernel=khash,
                                    graph_gemm=graph.gemm_executions,
                                    graph_vector=graph.vector_executions,
                                    log_gemm=act.comp_gemm_ops,
                                    log_vector=act.comp_vector_ops))
        warnings.append(info(6217, kernel=khash, nodes=len(graph.nodes),
                             executions=sum(n.executions for n in graph.nodes)))
    else:
        body = per_section[:-1] if len(per_section) > 1 else per_section
        gemm_secs = [c for c in body if any(c.get(n) for n in _MATMUL_INSTS)]
        vec_secs = [c for c in body if c not in gemm_secs]
        for n in _MATMUL_INSTS:
            if gemm_secs:
                totals[n] = (sum(c.get(n, 0) for c in gemm_secs) / len(gemm_secs)
                             * act.comp_gemm_ops)
        for n in _SFU_INSTS:
            if vec_secs and any(c.get(n) for c in vec_secs):
                totals[n] = (sum(c.get(n, 0) for c in vec_secs) / len(vec_secs)
                             * act.comp_vector_ops)
            elif gemm_secs and any(c.get(n) for c in gemm_secs):   # fused kernel
                totals[n] = (sum(c.get(n, 0) for c in gemm_secs) / len(gemm_secs)
                             * act.comp_gemm_ops)
        if any(totals.values()):
            warnings.append(warning(6218, kernel=khash))
    for n in names:
        stats[n] = float(totals[n])
    return stats


def _useful_mac_stats(kernel_dir: Path, khash: str, act: TogsimActivity,
                      mac_config: Optional[MacConfig],
                      warnings: List[str]) -> Dict[str, float]:
    """Return ``useful_macs`` and ``array_idle_slots`` of a MAC kernel.

    ``array_idle_slots`` is the number of active PE cycles in which the PE
    holds no real weight: ``systolic_active_cycles x lanes^2 - useful_macs``.
    A kernel without a MAC configuration gives no stats. A kernel with an
    unknown operator gets all active PE cycles as useful MACs (``NW-6221``).
    """
    if mac_config is None:
        return {}
    slots = act.systolic_active_cycles * act.lanes * act.lanes
    macs: Optional[int] = None
    meta_path = kernel_dir / "meta.txt"
    if meta_path.is_file():
        macs = useful_macs(act.operation, parse_meta(meta_path.read_text(encoding="utf-8",
                                                                             errors="ignore")))
    if macs is None:
        warnings.append(warning(6221, kernel=khash, operation=act.operation))
        return {"useful_macs": float(slots), "array_idle_slots": 0.0}
    if macs > slots:
        warnings.append(warning(6224, kernel=khash, useful=macs, slots=slots))
        macs = slots
    util = round(100.0 * macs / slots, 1) if slots else 0.0
    warnings.append(info(6222, kernel=khash, useful=macs, slots=slots, utilization=util))
    return {"useful_macs": float(macs), "array_idle_slots": float(slots - macs)}


def _sfu_vector_elems(kernel_dir: Path, khash: str, stats: Mapping[str, float],
                      lanes: int, warnings: List[str]) -> Optional[int]:
    """Return the elements that one SFU instruction processes in one lane.

    The kernel MLIR gives the vector type of each math operation
    (``vector<16xf32>``). One committed ``CustomV*`` instruction processes
    that many elements in each of the ``lanes`` lanes. The function reads the
    largest width. It returns ``None`` if the kernel has no SFU instructions,
    or if no MLIR gives the width; then the projection uses one vector
    register (``vector_elems``), and the run gives a warning.
    """
    if not any(stats.get(name) for name in _SFU_INSTS):
        return None
    widths: List[int] = []
    for path in sorted(kernel_dir.glob("*.mlir")):
        if "_llvm" in path.name or "_sample" in path.name:
            continue
        try:
            widths.extend(int(w) for w in _SFU_MLIR_OP.findall(
                path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    if not widths:
        warnings.append(warning(6226, kernel=khash))
        return None
    width = max(widths)
    warnings.append(info(6225, kernel=khash, elems=width, lanes=lanes,
                         total=width * lanes))
    return width


def _sfu_format(mac_config: Optional[MacConfig], stats: Mapping[str, float],
                khash: str, warnings: List[str]) -> Tuple[int, int]:
    """Return the exponent and mantissa widths of the SFU tables.

    The SFU is a floating-point unit. It uses the operand datatype of the
    kernel. For an integer kernel, or a kernel without a MAC configuration,
    it uses fp32. That case gives a warning only if the kernel has SFU
    operations.
    """
    sfu_exp, sfu_mant = _SFU_FALLBACK_EXP_MANT
    od = mac_config.operand_dtype if mac_config is not None else None
    if (od is not None and od.kind == "float"
            and isinstance(od.exp_bits, int) and isinstance(od.mantissa_bits, int)):
        sfu_exp, sfu_mant = od.exp_bits, od.mantissa_bits
    elif any(stats.get(name) for name in _SFU_INSTS):
        if od is not None:
            warnings.append(warning(6207, kernel=khash))      # integer dtype
        else:
            warnings.append(warning(6208, kernel=khash))      # no dtype
    return sfu_exp, sfu_mant


def read_run(togsim_dir: Path, gem5_dir: Path, *,
             base_config: Optional[Dict[str, object]] = None,
             pipeline_stages: int = 2,
             booksim_dir: Optional[Path] = None,
             expected_dram_table: Optional[str] = None) -> List[KernelWindow]:
    """Read a PyTorchSim run and return one window for each kernel.

    * ``togsim_dir``: the final TOGSim logs. In a raw run tree, this is the
      root ``togsim_results/``. Do not use ``outputs/<hash>/togsim_result/``,
      which contains autotune candidates.
    * ``gem5_dir``: the directories of the kernels. In a raw run tree, this
      is ``outputs/``. In a delivery bundle, it is ``gem5_outputs/``.

    Each log is one kernel that the run executed. The hash in the command
    line of the log identifies ``<gem5_dir>/<hash>/``. A directory in
    ``gem5_dir`` without a log is an autotune candidate that did not run, and
    the function ignores it. The lane count comes from the run configuration
    in each log.

    Optional inputs:

    * ``booksim_dir``: the ``booksim2_config/`` directory of the run. An
      ``anynet`` NoC topology needs its ``.net`` file from this directory. A
      ``fly`` topology needs only the BookSim configuration that the log
      contains (booksim.py).
    * ``expected_dram_table``: the name of the energy table that NPUWattch
      uses. This is the ``name`` in the ``--energy-table`` file. ``None``
      means the default table (HBM2). A log that declares a different
      table in ``[Config/Energy]`` gives a warning.
    """
    log_dir = Path(togsim_dir)
    out_dir = Path(gem5_dir)
    if not log_dir.is_dir():
        raise MacInferenceError.nw(6209, path=log_dir)
    if not out_dir.is_dir():
        raise MacInferenceError.nw(6210, path=out_dir)
    if not sorted(log_dir.glob("*.log")):
        raise MacInferenceError.nw(6211, path=log_dir)

    windows: List[KernelWindow] = []
    skipped: List[str] = []
    seen_noc_warnings: set = set()
    vlen_warned = False      # report each NoC message one time
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
        warnings.extend(act.warnings)
        kernel_dir = out_dir / khash

        mac_config: Optional[MacConfig] = None
        if kernel_dir.is_dir():
            mac_config = _mac_config_for(kernel_dir, act, pipeline_stages,
                                         warnings)
        else:
            warnings.append(warning(6212, kernel=khash, directory=out_dir.name))

        # Activity from the TOGSim log. The DRAM, NoC, and gem5 stats follow.
        stats: Dict[str, float] = {
            "systolic_active_cycles": act.systolic_active_cycles,
            "vector_active_cycles": act.vector_active_cycles,
            "comp_gemm_ops": act.comp_gemm_ops,
            "comp_vector_ops": act.comp_vector_ops,
        }
        if act.total_exec_cycles is not None:
            stats["total_exec_cycles"] = act.total_exec_cycles
        stats.update(dram_stats(act, expected_dram_table, warnings))

        # NoC (BookSim2). The topology symbols go into the run configuration,
        # thus the compounds can use them in expressions. The symbols are
        # icnt_ports, icnt_routers, icnt_channels, and the integer booksim_*
        # keys. The flit stats drive the noc actions of the projection. If
        # NPUWattch cannot model the NoC of a run, the run gives a warning
        # and does not stop.
        noc = derive_noc(act, booksim_dir=booksim_dir)
        win_config = dict(act.config)
        win_config.update(noc.symbols)
        # The queue width of the dma compound is `dram_req_size_byte*8`. Make
        # sure that the symbol always has a value. The default is 32 B, the
        # HBM2 request size.
        if not isinstance(win_config.get("dram_req_size_byte"), int):
            win_config["dram_req_size_byte"] = 32
        stats.update(noc.stats)
        for msg in noc.warnings:
            if msg not in seen_noc_warnings:
                seen_noc_warnings.add(msg)
                warnings.append(msg)

        stats.update(_gem5_instruction_stats(kernel_dir, khash, warnings, act))
        stats.update(_useful_mac_stats(kernel_dir, khash, act, mac_config, warnings))
        (win_config["sfu_exponent_bits"],
         win_config["sfu_mantissa_bits"]) = _sfu_format(
            mac_config, stats, khash, warnings)
        if not isinstance(win_config.get("vpu_vector_length_bits"), int):
            if not vlen_warned:
                vlen_warned = True
                warnings.append(warning(6227))
        sfu_elems = _sfu_vector_elems(kernel_dir, khash, stats, act.lanes,
                                      warnings)
        if sfu_elems is not None:
            win_config["sfu_vector_elems"] = sfu_elems

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
        raise MacInferenceError.nw(6213, path=log_dir, skipped="; ".join(skipped))
    if skipped:
        windows[0].warnings.insert(
            0, warning(6214, count=len(skipped), skipped="; ".join(skipped)))
    return windows


def bind_window(
    window: KernelWindow,
    projection: Projection,
    compound: Compound,
    primitive_modes: PrimitiveModes,
    *,
    skipped: Optional[List[str]] = None,
) -> List[BoundAction]:
    """Apply the projection to one window and one compound.

    Return one ``BoundAction`` for each action of the compound whose
    ``count_from.stat`` is in the stats of the window. The function ignores
    an action whose stat is not in the window. The coverage check of the
    caller reports activity that no action uses. The window must have a MAC
    configuration.

    ``skipped`` is an optional list for actions that the function cannot
    resolve. For example, an element can use a symbol that the run
    configuration does not have. In that case, the emitter did not emit the
    element.

    * With ``skipped``, the function adds a message to the list and ignores
      the action.
    * Without ``skipped``, the function raises the error. Use this to find
      errors in the definitions.
    """
    if window.mac_config is None:
        raise MacInferenceError.nw(6215, kernel=window.kernel_hash)
    # Each integer key of the run configuration is also a symbol. The
    # compounds and the projection of this harness can use it in expressions.
    extra_symbols = {
        k: v for k, v in (window.config or {}).items()
        if isinstance(v, int) and not isinstance(v, bool)
    }
    actions = projection.compounds.get(compound.name, {})
    bound: List[BoundAction] = []
    for action_name, mapping in actions.items():
        stat = mapping.count_from.stat
        if stat not in window.stats:
            continue  # this run does not have the stat: the action gets no energy
        try:
            ares = resolve_action(projection, compound, action_name,
                                  window.mac_config, primitive_modes,
                                  extra_symbols=extra_symbols)
        except CompoundBundleError as e:
            if skipped is None:
                raise
            skipped.append(warning(6216, compound=compound.name,
                                   action=action_name, error=e))
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
