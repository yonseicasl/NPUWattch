"""DRAM energy of a PyTorchSim run.

This module contains all DRAM-specific code of the PyTorchSim harness. The
Timeloop harness has a module with the same name and the same role.

* :func:`select_table` selects the DRAM energy table of the run.
* :func:`set_constants` writes the constants of that table to each ``hbm``
  component of the description.
* :func:`dram_stats` reads the DRAM command counts from the TOGSim log.

The ``hbm`` primitive (``energy.unit_cost.HBMCostProvider``) calculates the
energy from the constants and the counts:

* each RD or WR command: ``data_width`` x ``mem_access_energy_per_bit_pJ``
* each ACT command: ``mem_act_energy_pJ``
* each REFab command: ``mem_ref_energy_pJ``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from npuwattch.diagnostics import info, warning
from npuwattch.energy.dram_table import (
    EnergyTable,
    EnergyTableError,
    default_table,
    load_energy_table,
)
from ..registry import HarnessError
from .togsim_log import TogsimActivity

__all__ = ["dram_stats", "select_table", "set_constants"]


def select_table(path: Optional[Path]) -> Optional[EnergyTable]:
    """Load the table of ``--energy-table``, or return ``None``.

    ``None`` means that the run uses the default table, ``hbm2.yml``
    (``energy.dram_table.default_table``). :func:`set_constants` raises an
    error if that file is not available. A table for this harness must have
    an activation term, because PyTorchSim counts ACT commands.
    """
    return load_energy_table(Path(path)) if path else None


def set_constants(description: Mapping[str, Any],
                  table: Optional[EnergyTable],
                  notes: List[str], warnings: List[str]) -> None:
    """Write the DRAM energy constants to each ``hbm`` component.

    ``table`` is the result of :func:`select_table`. The default table
    supplies each term that ``table`` does not have. The PyTorchSim table
    format has no refresh term, thus the refresh energy usually comes from
    the default table.

    The constants are component attributes. ``write_arch`` saves them, thus a
    subsequent ``-d``/``-l`` run uses the same constants.
    """
    hbm_comps = [c for c in description.get("npuwattch", {}).get("components", [])
                 if c.get("class") == "hbm"]
    if not hbm_comps:
        if table is not None:
            warnings.append(warning(6501, file=table.path.name))
        return
    try:
        constants = dict(default_table().attributes())
    except EnergyTableError as e:
        raise HarnessError.nw(6502, error=e) from e
    if table is not None:
        constants.update(table.attributes())
    for c in hbm_comps:
        c.setdefault("attributes", {}).update(constants)
    if table is None:
        return
    if table.ref_pj is not None:
        notes.append(info(
            6503, name=table.name, file=table.path.name, act_pj=table.act_pj,
            transfer_pj_per_bit=table.transfer_pj_per_bit,
            transfer_split=table.transfer_split_str(), ref_pj=table.ref_pj))
    else:
        notes.append(info(
            6504, name=table.name, file=table.path.name, act_pj=table.act_pj,
            transfer_pj_per_bit=table.transfer_pj_per_bit,
            transfer_split=table.transfer_split_str()))


def dram_stats(act: TogsimActivity, expected_dram_table: Optional[str],
               warnings: List[str]) -> Dict[str, float]:
    """Return the DRAM stats of one kernel.

    The function gives two groups of stats:

    * Traffic (``dram_read_bytes``, ``dram_write_bytes``, ``dram_requests``):
      the request counts of the log x the request size of the configuration.
    * Device commands (``dram_read_cmds``, ``dram_write_cmds``,
      ``dram_act_cmds``, ``dram_ref_cmds``): from the Ramulator2
      ``=== DRAM statistics ===`` block. A log without this block gives only
      the read and write commands.

    The function also compares the energy table that the run declares with
    the table that NPUWattch charges, and gives a warning if they are
    different.
    """
    khash = act.kernel_hash
    stats: Dict[str, float] = {}
    # DRAM traffic in bytes. This is the estimate of the data that goes into
    # and out of the VMEM. It is the request count of the log x the request
    # size of the run configuration. If the configuration has no request
    # size, the function uses 32 B, the HBM2 default.
    if act.dram_reads is not None:
        req_size = act.config.get("dram_req_size_byte")
        if not isinstance(req_size, int):
            req_size = 32
            warnings.append(warning(6505, kernel=khash, size=req_size))
        stats["dram_read_bytes"] = act.dram_reads * req_size
        stats["dram_write_bytes"] = act.dram_writes * req_size
        # Events of the DMA engine. Each DRAM request moves one entry through
        # the queue and does one address addition (docs/DESIGN_SFU_DMA.md §1).
        stats["dram_requests"] = act.dram_reads + act.dram_writes
        # Compare the total with the DMA blocks of the cores. The last DMA
        # line of a core gives its total response count. This count must be
        # equal to the DRAM requests of that core.
        dma_total = sum(int(pc.get("dma_responses", 0) or 0)
                        for pc in act.per_core.values())
        if dma_total and dma_total != stats["dram_requests"]:
            warnings.append(warning(6506, kernel=khash, dma_total=dma_total,
                                    dram_total=stats["dram_requests"]))

    # Command counts of the DRAM device, for the HBM energy model of the dram
    # compound. The primary source is the "=== DRAM statistics ===" block of
    # Ramulator2. It gives the measured row hits, misses, and conflicts:
    #   ACT (+PRE) commands = row_misses + row_conflicts
    #   refresh commands    = num_maintenance_reqs
    # Thus the function does not assume a hit rate.
    # If the log does not have the block, the function uses the [DRAM]
    # request totals. Then the read and write energy is in the results, but
    # the ACT and refresh energy is not.
    ctrl = act.dram_ctrl
    if ctrl is not None:
        stats["dram_read_cmds"] = ctrl["num_read_reqs"]
        stats["dram_write_cmds"] = ctrl["num_write_reqs"]
        stats["dram_act_cmds"] = ctrl["row_misses"] + ctrl["row_conflicts"]
        stats["dram_ref_cmds"] = ctrl["num_maintenance_reqs"]
        if (act.dram_reads is not None
                and (ctrl["num_read_reqs"], ctrl["num_write_reqs"])
                != (act.dram_reads, act.dram_writes)):
            warnings.append(warning(
                6507, kernel=khash, reads=ctrl["num_read_reqs"],
                writes=ctrl["num_write_reqs"], log_reads=act.dram_reads,
                log_writes=act.dram_writes))
    elif act.dram_reads is not None:
        stats["dram_read_cmds"] = act.dram_reads
        stats["dram_write_cmds"] = act.dram_writes
        warnings.append(warning(6508, kernel=khash))

    # Compare the energy table that the run declares in [Config/Energy] with
    # the table that NPUWattch charges (`select_table`). If the two tables
    # are different, the DRAM energy is for an incorrect memory technology.
    charged = expected_dram_table or default_table().name
    if (act.energy_table_name is not None
            and act.energy_table_name != charged):
        if expected_dram_table is not None:
            warnings.append(warning(
                6509, kernel=khash, declared=act.energy_table_name,
                path=act.energy_table_path, charged=charged))
        else:
            warnings.append(warning(
                6510, kernel=khash, declared=act.energy_table_name,
                path=act.energy_table_path, charged=charged))
    return stats
