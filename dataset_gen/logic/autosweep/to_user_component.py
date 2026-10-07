"""Turn the dataset rows of a user-component module into a library entry.

A module in sweep_spec.USER_COMPONENT_MODULES (for example, nvdla_sdp_dp) is
characterized by the logic flow like a primitive. This script reads its CSV
(../datasets/logic_<module>.csv) and prints one user_components.yaml entry:

  reference      the values at --reference-node,
  characterized  the values at every node in the CSV.

For each node it uses the job with the highest clock. The values are:

  area_um2       post-route cell area (pnr_total_area_um2),
  leak_power_mW  leakage of the vectored "process" row (else the first mode),
  actions        one action for each vectored stim mode: the dynamic energy
                 of one clock cycle in that mode (dyn_energy_pJ). The module
                 TB drives one element per cycle in its data modes, so this is
                 also the energy of one element.

Usage (npuwattch env):
  python to_user_component.py nvdla_sdp_dp --name nvdla_sdp --reference-node 7nm
"""
from __future__ import annotations

import argparse
import copy
import csv
import sys
from pathlib import Path

import yaml

DATASETS = Path(__file__).resolve().parent.parent / "datasets"


def _sig(value: float, digits: int = 4) -> float:
    return float(f"{value:.{digits}g}")


def entry_for(module: str, name: str, reference_node: str,
              description: str = "") -> dict:
    rows = list(csv.DictReader((DATASETS / f"logic_{module}.csv").open()))
    vectored = [r for r in rows if r["power_activity_mode"] == "vectored"]
    if not vectored:
        raise SystemExit(f"no vectored rows in logic_{module}.csv")
    nodes: dict = {}
    for node in sorted({r["node"] for r in vectored},
                       key=lambda n: -float(n.rstrip("nm"))):
        at_node = [r for r in vectored if r["node"] == node]
        fastest = max(float(r["clock_freq_mhz"]) for r in at_node)
        job = [r for r in at_node if float(r["clock_freq_mhz"]) == fastest]
        modes = {r["stim_mode"]: r for r in job}
        first = modes.get("process", job[0])
        nodes[node] = {
            "clock_MHz": _sig(fastest),
            "area_um2": _sig(float(first["pnr_total_area_um2"])),
            "leak_power_mW": _sig(float(first["leak_power_mW"])),
            "actions": {mode: {"energy_pJ": _sig(float(r["dyn_energy_pJ"]))}
                        for mode, r in sorted(modes.items())},
            "run_id": first["flow_run_id"],
        }
    if reference_node not in nodes:
        raise SystemExit(f"{reference_node} not in {', '.join(nodes)}")
    ref = nodes[reference_node]
    first = [r for r in vectored if r["node"] == reference_node][0]
    out = {}
    if description:
        out["description"] = description
    out["reference"] = {"node": reference_node, "corner": first["corner"],
                        "voltage_V": float(first["vdd_V"]),
                        "temperature_C": float(first["temperature_C"]),
                        "clock_MHz": ref["clock_MHz"]}
    out["design_class"] = "compute"
    out["area_um2"] = ref["area_um2"]
    out["leak_power_mW"] = ref["leak_power_mW"]
    out["actions"] = copy.deepcopy(ref["actions"])
    out["characterized"] = nodes
    return {name: out}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module")
    ap.add_argument("--name", required=True, help="the library entry name")
    ap.add_argument("--reference-node", default="7nm")
    ap.add_argument("--description", default="")
    args = ap.parse_args()
    entry = entry_for(args.module, args.name, args.reference_node,
                      args.description)
    yaml.safe_dump({"user_components": entry}, sys.stdout, sort_keys=False,
                   default_flow_style=None, width=100)


if __name__ == "__main__":
    main()
