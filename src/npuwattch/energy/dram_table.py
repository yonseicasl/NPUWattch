"""Load a PyTorchSim run's DRAM energy-cost table (``energy_cost_table_path``).

The simulator config names a YAML of DRAM energy constants (author handoff
2026-08-10, sample ``hbm2.yml``); the log echoes the loaded table as
``[Config/Energy] Loaded energy (cost) table "NAME" from PATH``. When the user
supplies that file (``--energy-table``, auto-added by ``run.sh`` from
``<root>/energy_tables/``), the emitter overrides the dram compound's built-in
constants with the table's values, so NPUWattch charges exactly what the run
declared. Without it, the built-in cited constants apply (O'Connor MICRO 2017
— identical to the authors' HBM2 table today, pinned by
``tests/harness/test_dram_authors_verification.py``).

Table contract (the authors let us fix the structure)::

    name: HBM2                       # required — matched against the log echo
    offchip_dram:
      row_activation_pj: 909.0       # required — one ACT(+PRE) command
      transfer_pj_per_bit:           # required — per-bit terms, summed;
        dram: 1.51                   #   labels are free-form (dram/io/phy in
        io: 1.17                     #   the author sample) and kept for the
        phy: 0.80                    #   report's transfer-split provenance
      refresh_pj_per_refab: 58176.0  # optional — our proposed extension; the
                                     #   author sample has none, so the
                                     #   built-in derived constant stays

Refresh: the authors' energy formula has no refresh term. When the table omits
it, the dram compound keeps charging the built-in derived REFab constant — the
caller notes that, it is never silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

__all__ = ["EnergyTable", "EnergyTableError", "load_energy_table"]


class EnergyTableError(ValueError):
    """The energy table file is missing a required key or malformed."""


@dataclass(frozen=True)
class EnergyTable:
    name: str
    path: Path
    act_pj: float
    #: per-bit transfer terms, label → pJ/bit (order preserved from the file).
    transfer_terms: Dict[str, float] = field(default_factory=dict)
    #: per-REFab refresh energy; None when the table has no refresh term
    #: (the author format) — the built-in derived constant then stays.
    ref_pj: Optional[float] = None

    @property
    def transfer_pj_per_bit(self) -> float:
        # 10 significant digits: keeps any real precision, drops binary float
        # summation noise (1.51+1.17+0.80 → 3.48, not 3.4799999999999995 —
        # this value lands in the description YAML and the report verbatim).
        return float(f"{sum(self.transfer_terms.values()):.10g}")

    def transfer_split_str(self) -> str:
        """``dram 1.51 + io 1.17 + phy 0.8`` — for provenance notes."""
        return " + ".join(f"{k} {v:g}" for k, v in self.transfer_terms.items())


def _positive_number(value: object, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise EnergyTableError(f"{where} must be a positive number, got {value!r}")
    return float(value)


def load_energy_table(path: Path) -> EnergyTable:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
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

    act = _positive_number(dram.get("row_activation_pj"),
                           f"energy table {path}: offchip_dram.row_activation_pj")
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
