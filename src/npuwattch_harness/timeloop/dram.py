"""DRAM energy of a Timeloop/Accelergy run.

This module contains all DRAM-specific code of the Timeloop harness. The
PyTorchSim harness has a module with the same name and the same role.

* :func:`select_table` loads the table of ``--energy-table``.
* :func:`constants_for` selects the energy constants of one DRAM component.
* :func:`warn_if_unused` gives a warning if the description has no DRAM
  component for the table of the user.

The ``hbm`` primitive (``energy.unit_cost.HBMCostProvider``) calculates the
energy of each read or write: ``data_width`` x
``mem_access_energy_per_bit_pJ``. The Timeloop stats give no ACT or REF
counts, thus the activation and refresh constants have no effect on the
energy of a Timeloop run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from npuwattch.energy.dram_table import (
    TABLE_DIR,
    EnergyTable,
    load_energy_table,
    table_for_type,
)
from ..registry import HarnessError

__all__ = ["CONSTANT_NAMES", "FALLBACK_TYPE", "constants_for", "select_table",
           "warn_if_unused"]

#: The NPUWattch attributes that give the energy constants of an ``hbm``
#: component.
CONSTANT_NAMES = ("mem_act_energy_pJ", "mem_access_energy_per_bit_pJ",
                  "mem_ref_energy_pJ")

#: The DRAM type of a component that declares no ``type``.
FALLBACK_TYPE = "LPDDR4"


def select_table(path: Optional[Path]) -> Optional[EnergyTable]:
    """Load the table of ``--energy-table``, or return ``None``.

    A table that has only energy for each bit is sufficient for this harness.
    """
    if not path:
        return None
    return load_energy_table(Path(path), require_activation=False)


def constants_for(dram_type: Any, table: Optional[EnergyTable], *,
                  component: str, declared: Mapping[str, Any],
                  warnings: List[str], notes: List[str]) -> Dict[str, float]:
    """Return the energy attributes of one DRAM component.

    The constants always come from a DRAM energy table:

    1. ``table``: the table that the user gives with ``--energy-table``.
    2. The table in ``energy/dram_tables/`` for the Accelergy DRAM ``type``
       (LPDDR4, LPDDR, DDR3, GDDR5, HBM2, HMC).
    3. If the component declares no ``type``: the table of
       :data:`FALLBACK_TYPE`. This gives a warning.

    A constant that the component declares with its NPUWattch name
    (``declared``) has priority over the table of case 2 or 3.

    The function raises :class:`HarnessError` if the necessary table file is
    not available. This includes a ``type`` that has no table.
    """
    if table is not None:
        notes.append(
            f"{component}: {table.transfer_pj_per_bit:g} pJ/bit from "
            f"--energy-table {table.name!r} "
            f"({table.path.name}: {table.transfer_split_str()})")
        return table.attributes()

    own = {key: declared[key] for key in CONSTANT_NAMES
           if declared.get(key) is not None}
    if dram_type:
        type_table = table_for_type(dram_type)
        if type_table is None:
            raise HarnessError(
                f"{component}: DRAM type {dram_type!r} has no energy table in "
                f"{TABLE_DIR.name}/ — declare an Accelergy type (LPDDR4, "
                f"LPDDR, DDR3, GDDR5, HBM2, HMC) or pass --energy-table")
        notes.append(
            f"{component} (DRAM type {type_table.name}): "
            f"{type_table.transfer_pj_per_bit:g} pJ/bit from the shipped table "
            f"{type_table.path.name} (override with --energy-table)")
    else:
        type_table = table_for_type(FALLBACK_TYPE)
        if type_table is None:
            raise HarnessError(
                f"{component}: no DRAM type declared and the fallback table "
                f"{TABLE_DIR.name}/{FALLBACK_TYPE.lower()}.yml is not "
                f"available — declare an Accelergy type or pass "
                f"--energy-table")
        warnings.append(
            f"{component}: no DRAM type declared — priced with the "
            f"{FALLBACK_TYPE} table ({type_table.path.name}, "
            f"{type_table.transfer_pj_per_bit:g} pJ/bit); declare an "
            f"Accelergy type (LPDDR4, LPDDR, DDR3, GDDR5, HBM2, HMC) or pass "
            f"--energy-table")
    return {**type_table.attributes(), **own}


def warn_if_unused(description: Mapping[str, Any],
                   table: Optional[EnergyTable], warnings: List[str]) -> None:
    """Give a warning if the user gave a table but there is no DRAM component."""
    if table is None:
        return
    if not any(c.get("class") == "hbm"
               for c in description["npuwattch"]["components"]):
        warnings.append(
            f"--energy-table {table.path.name} supplied but the "
            f"description has no DRAM component — the table is unused")
