"""DRAM energy tables. All harnesses use this module.

A DRAM energy table gives the energy constants of one DRAM type. NPUWattch
always gets the constants of an ``hbm`` component from a table:

* ``dram_tables/*.yml``: one table for each DRAM type. ``hbm2.yml`` is the
  default table (:func:`default_table`).
* ``--energy-table``: a table that the user gives for one run.

Each harness selects the table in its ``dram.py`` module.
:meth:`EnergyTable.attributes` gives the component attributes for a table.

The file format is the ``energy_cost_table_path`` format of PyTorchSim. The
PyTorchSim log shows the name of its table in this line:
``[Config/Energy] Loaded energy (cost) table "NAME" from PATH``.

Table format::

    name: HBM2                       # necessary. Compared with the log line.
    offchip_dram:
      row_activation_pj: 909.0       # one ACT (+PRE) command. Necessary for
                                     #   PyTorchSim, which counts ACT commands.
                                     #   Optional for Timeloop, which has no
                                     #   ACT events.
      transfer_pj_per_bit:           # necessary. The terms are added.
        dram: 1.51                   #   The labels are free text. The report
        io: 1.17                     #   shows them.
        phy: 0.80
      refresh_pj_per_refab: 58176.0  # optional. A NPUWattch extension of the
                                     #   PyTorchSim format.

If a table has no refresh term, the refresh energy comes from the default
table, and the harness writes a note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml

__all__ = ["EnergyTable", "EnergyTableError", "TABLE_DIR", "default_table",
           "load_energy_table", "table_for_type"]

#: The directory of the DRAM energy tables, one for each DRAM type (package
#: data).
TABLE_DIR = Path(__file__).resolve().parent / "dram_tables"


class EnergyTableError(ValueError):
    """The energy table file has an incorrect format or no necessary key."""


@dataclass(frozen=True)
class EnergyTable:
    name: str
    path: Path
    #: Energy of one ACT (+PRE) command. None if the table has only the
    #: transfer terms.
    act_pj: Optional[float]
    #: The transfer terms: label -> pJ for each bit, in the order of the file.
    transfer_terms: Dict[str, float] = field(default_factory=dict)
    #: Energy of one REFab command. None if the table has no refresh term.
    #: The refresh energy then comes from the default table.
    ref_pj: Optional[float] = None

    @property
    def transfer_pj_per_bit(self) -> float:
        # Round the sum to 10 significant digits. This removes the binary
        # float error of the sum: 1.51+1.17+0.80 gives 3.48, not
        # 3.4799999999999995. The description YAML and the report show this
        # value without a change.
        return float(f"{sum(self.transfer_terms.values()):.10g}")

    def attributes(self) -> Dict[str, float]:
        """The ``hbm`` component attributes that this table defines.

        A table without an activation or a refresh term does not give that
        attribute.
        """
        attrs: Dict[str, float] = {}
        if self.act_pj is not None:
            attrs["mem_act_energy_pJ"] = self.act_pj
        attrs["mem_access_energy_per_bit_pJ"] = self.transfer_pj_per_bit
        if self.ref_pj is not None:
            attrs["mem_ref_energy_pJ"] = self.ref_pj
        return attrs

    def transfer_split_str(self) -> str:
        """Return the transfer terms as text, for the notes of a run.

        Example: ``dram 1.51 + io 1.17 + phy 0.8``.
        """
        return " + ".join(f"{k} {v:g}" for k, v in self.transfer_terms.items())


def _positive_number(value: object, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise EnergyTableError(f"{where} must be a positive number, got {value!r}")
    return float(value)


def load_energy_table(path: Path, *, require_activation: bool = True) -> EnergyTable:
    """Read one table file.

    With ``require_activation=False``, the function accepts a table that has
    no ``row_activation_pj``. Such a table is sufficient for a harness that
    has no ACT events.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise EnergyTableError(f"energy table not found: {path}") from e
    except yaml.YAMLError as e:
        raise EnergyTableError(f"energy table {path}: not valid YAML — {e}") from e
    if not isinstance(data, dict):
        raise EnergyTableError(f"energy table {path}: top level must be a mapping")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise EnergyTableError(
            f"energy table {path}: missing 'name' (the table name the log's "
            f"[Config/Energy] echo declares, e.g. HBM2)"
        )
    dram = data.get("offchip_dram")
    if not isinstance(dram, dict):
        raise EnergyTableError(f"energy table {path}: missing 'offchip_dram' mapping")

    act_raw = dram.get("row_activation_pj")
    act = (None if act_raw is None and not require_activation else
           _positive_number(act_raw,
                            f"energy table {path}: offchip_dram.row_activation_pj"))
    terms_raw = dram.get("transfer_pj_per_bit")
    if not isinstance(terms_raw, dict) or not terms_raw:
        raise EnergyTableError(
            f"energy table {path}: offchip_dram.transfer_pj_per_bit must be a "
            f"non-empty mapping of per-bit terms"
        )
    terms = {str(k): _positive_number(
                 v, f"energy table {path}: transfer_pj_per_bit.{k}")
             for k, v in terms_raw.items()}

    ref = dram.get("refresh_pj_per_refab")
    ref_pj = (None if ref is None else _positive_number(
        ref, f"energy table {path}: offchip_dram.refresh_pj_per_refab"))

    return EnergyTable(name=name, path=path, act_pj=act,
                       transfer_terms=terms, ref_pj=ref_pj)


@lru_cache(maxsize=None)
def default_table() -> EnergyTable:
    """Return the default table, ``dram_tables/hbm2.yml``.

    This table is the one source of the default ``hbm`` constants. It has all
    three terms: activation, transfer, and refresh. If the file is not
    available, the function raises :class:`EnergyTableError`.
    """
    return load_energy_table(TABLE_DIR / "hbm2.yml")


def table_for_type(dram_type: object) -> Optional[EnergyTable]:
    """Return the table in ``dram_tables/`` whose ``name`` is ``dram_type``.

    The comparison ignores the letter case. An example is the Accelergy type
    ``LPDDR4``. Return None if there is no such table.
    """
    if not isinstance(dram_type, str) or not dram_type.strip():
        return None
    path = TABLE_DIR / f"{dram_type.strip().lower()}.yml"
    if not path.is_file():
        return None
    table = load_energy_table(path, require_activation=False)
    return table if table.name.lower() == dram_type.strip().lower() else None

