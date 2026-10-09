"""User component library: the design cost of blocks that NPUWattch has no
model for.

NPUWattch has models for a fixed set of primitives. A design can contain other
blocks (for example, custom control logic). The user gives the cost of such a
block in a library file: its name, its area, and the energy of each action.

File format::

    user_components:
      example_68000_cpu_core:        # the component name (= its class)
        reference:                   # the technology of the values below
          node: 65nm
        design_class: compute        # optional: register | compute
        area_um2: 215000.0
        leak_power_mW: 0.0           # optional, default 0
        actions:                     # action name -> energy of one action
          idle:    {energy_pJ: 2.1}
          process: {energy_pJ: 48.0}
        characterized:               # optional: values measured at other
          45nm:                      #   nodes, the same keys as above
            clock_MHz: 500.0         #   (clock_MHz and run_id optional)
            area_um2: 98000.0
            leak_power_mW: 0.0
            actions:
              idle:    {energy_pJ: 1.0}
              process: {energy_pJ: 25.0}

How the library is used:

* The library is an input of a run. A harness loads ``user_components.yaml``
  from the directory of the run inputs, or the file of ``--user-components``.
  A component of the design uses a library entry if its class is the entry
  name.
* The harness copies each entry that the design uses into the description
  (``npuwattch.user_components``). Thus a description contains all the data
  that is necessary to calculate its energy.
* The user-defined component estimator (``npuwattch_estimators/custom``)
  gives the cost of these components. ``reference`` and ``design_class`` are
  the inputs of its scaler, which changes the values to the technology of the
  run.

An action name is the ``mode`` of an activity row (manual §3.3).

``characterized`` keeps the values that were measured at other nodes (for
example, a block run through the logic flow at every node). The run does not
use them: it uses the reference values. They are data for the scaler.
"""

from __future__ import annotations

from npuwattch.diagnostics import NPUWattchError, info
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

__all__ = [
    "DESIGN_CLASSES",
    "UserComponent",
    "UserComponentError",
    "load_user_components",
    "parse_user_components",
    "unused_component_notes",
    "user_components_of",
]

_NAME_RE = re.compile(r"[a-z][a-z0-9_]*$")
_NODE_RE = re.compile(r"\d+(\.\d+)?nm$")

#: The design classes that the scaler knows. Each class is a preset of the
#: sequential cell ratios (SCR, SAR) of the component.
DESIGN_CLASSES = ("register", "compute")


class UserComponentError(NPUWattchError, ValueError):
    """A user component library is incorrect."""


@dataclass(frozen=True)
class UserComponent:
    """The design cost of one user component, at its reference technology."""

    name: str
    area_um2: float
    #: action name -> energy of one action, in pJ
    actions: Dict[str, float]
    leak_power_mW: float = 0.0
    #: The technology of the values (``node`` and optional PVT keys).
    reference: Dict[str, Any] = field(default_factory=dict)
    design_class: Optional[str] = None
    #: node -> {clock_MHz?, area_um2, leak_power_mW, actions, run_id?}
    characterized: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return the entry in the file format."""
        out: Dict[str, Any] = {"reference": dict(self.reference)}
        if self.design_class is not None:
            out["design_class"] = self.design_class
        out["area_um2"] = self.area_um2
        out["leak_power_mW"] = self.leak_power_mW
        out["actions"] = {k: {"energy_pJ": v} for k, v in self.actions.items()}
        if self.characterized:
            out["characterized"] = {
                node: {**{k: v for k, v in row.items() if k != "actions"},
                       "actions": {a: {"energy_pJ": e}
                                   for a, e in row["actions"].items()}}
                for node, row in self.characterized.items()}
        return out


def parse_user_components(table: Any, where: str) -> Dict[str, UserComponent]:
    """Check a ``user_components`` mapping and return its components.

    ``where`` is the source of the mapping, for error messages.
    """
    if table is None:
        return {}
    if not isinstance(table, Mapping):
        raise UserComponentError.nw(2101, where=where)

    def number(value: Any, what: str, *, positive: bool) -> float:
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and (value > 0 if positive else value >= 0))
        if not ok:
            if positive:
                raise UserComponentError.nw(2102, where=where, what=what,
                                            value=value)
            raise UserComponentError.nw(2103, where=where, what=what,
                                        value=value)
        return float(value)

    out: Dict[str, UserComponent] = {}
    for name, entry in table.items():
        name = str(name)
        if not _NAME_RE.match(name):
            raise UserComponentError.nw(2104, where=where, name=name)
        if not isinstance(entry, Mapping):
            raise UserComponentError.nw(2105, where=where, name=name)
        unknown = sorted(set(entry) - {"reference", "design_class", "area_um2",
                                       "leak_power_mW", "actions",
                                       "description", "characterized"})
        if unknown:
            raise UserComponentError.nw(2106, where=where, name=name,
                                        keys=", ".join(unknown))
        reference = entry.get("reference") or {}
        if not isinstance(reference, Mapping) or not reference.get("node"):
            raise UserComponentError.nw(2107, where=where, name=name)
        design_class = entry.get("design_class")
        if design_class is not None and design_class not in DESIGN_CLASSES:
            raise UserComponentError.nw(2108, where=where, name=name,
                                        classes=", ".join(DESIGN_CLASSES),
                                        design_class=design_class)
        def parse_actions(actions_raw: Any, what: str) -> Dict[str, float]:
            if not isinstance(actions_raw, Mapping) or not actions_raw:
                raise UserComponentError.nw(2109, where=where, name=what)
            parsed: Dict[str, float] = {}
            for action, spec in actions_raw.items():
                if not isinstance(spec, Mapping) or "energy_pJ" not in spec:
                    raise UserComponentError.nw(2110, where=where, name=what,
                                                action=action)
                parsed[str(action)] = number(
                    spec["energy_pJ"], f"{what}.actions.{action}.energy_pJ",
                    positive=False)
            return parsed

        actions = parse_actions(entry.get("actions"), name)
        characterized: Dict[str, Dict[str, Any]] = {}
        table = entry.get("characterized") or {}
        if not isinstance(table, Mapping):
            raise UserComponentError.nw(2111, where=where, name=name)
        for node, row in table.items():
            node = str(node).strip().lower()
            what = f"{name}.characterized.{node}"
            if not _NODE_RE.match(node) or not isinstance(row, Mapping):
                raise UserComponentError.nw(2112, where=where, name=what)
            unknown_row = sorted(set(row) - {"clock_MHz", "area_um2",
                                             "leak_power_mW", "actions",
                                             "run_id"})
            if unknown_row:
                raise UserComponentError.nw(2106, where=where, name=what,
                                            keys=", ".join(unknown_row))
            parsed_row: Dict[str, Any] = {}
            if "clock_MHz" in row:
                parsed_row["clock_MHz"] = number(row["clock_MHz"],
                                                 f"{what}.clock_MHz",
                                                 positive=True)
            parsed_row["area_um2"] = number(row.get("area_um2"),
                                            f"{what}.area_um2", positive=True)
            parsed_row["leak_power_mW"] = number(row.get("leak_power_mW", 0.0),
                                                 f"{what}.leak_power_mW",
                                                 positive=False)
            parsed_row["actions"] = parse_actions(row.get("actions"), what)
            if "run_id" in row:
                parsed_row["run_id"] = str(row["run_id"])
            characterized[node] = parsed_row
        out[name] = UserComponent(
            name=name,
            area_um2=number(entry.get("area_um2"), f"{name}.area_um2",
                            positive=True),
            actions=actions,
            leak_power_mW=number(entry.get("leak_power_mW", 0.0),
                                 f"{name}.leak_power_mW", positive=False),
            reference={str(k): v for k, v in reference.items()},
            design_class=design_class,
            characterized=characterized,
        )
    return out


def load_user_components(path: Path) -> Dict[str, UserComponent]:
    """Load and check one user component library file."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise UserComponentError.nw(2113, path=path) from e
    except yaml.YAMLError as e:
        raise UserComponentError.nw(2114, path=path, error=e) from e
    if not isinstance(data, Mapping) or "user_components" not in data:
        raise UserComponentError.nw(2115, path=path)
    return parse_user_components(data["user_components"], str(path))


def user_components_of(description: Mapping[str, Any]) -> Dict[str, UserComponent]:
    """Return the user components that a description contains."""
    block = (description.get("npuwattch") or {}).get("user_components")
    return parse_user_components(block, "description")


def unused_component_notes(library: Mapping[str, UserComponent],
                           used: Iterable[str], source: str) -> List[str]:
    """Return one note for each library component that the design does not use."""
    used = set(used)
    return [info(2116, name=name, source=source)
            for name in library if name not in used]
