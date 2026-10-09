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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from npuwattch.diagnostics import warning

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
from .gem5_stats import parse_sections, sum_committed_inst, sum_stat
from .mac_config import (
    MacConfig,
    MacInferenceError,
    NotAMatmulKernel,
    infer_mac_config_from_dir,
    infer_mac_config_from_meta,
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
                            warnings: List[str]) -> Dict[str, float]:
    """Return the gem5 instruction counts and ``numCycles`` of one kernel."""
    stats: Dict[str, float] = {}
    stats_path = kernel_dir / "m5out" / "stats.txt"
    if stats_path.is_file():
        sections = parse_sections(stats_path.read_text(encoding="utf-8", errors="ignore"))
        inst = sum_committed_inst(sections)
        for name in _MATMUL_INSTS + _SFU_INSTS:
            stats[name] = float(inst.get(name, 0))
        stats["numCycles"] = sum_stat(sections, "system.cpu.numCycles")
    else:
        warnings.append(warning(6206, kernel=khash))
    return stats


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
    seen_noc_warnings: set = set()      # report each NoC message one time
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

        stats.update(_gem5_instruction_stats(kernel_dir, khash, warnings))
        (win_config["sfu_exponent_bits"],
         win_config["sfu_mantissa_bits"]) = _sfu_format(
            mac_config, stats, khash, warnings)

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
