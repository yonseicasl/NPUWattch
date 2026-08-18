"""Harness registry — discover ``HARNESS_SPEC``-declaring simulator harnesses and
run the selected one's ingest (its simulator output → a native ``EmittedArch``).

A harness owns only its log readers + definition bundle; interpreting them into a
NPUWattch description + activity is core (``npuwattch.arch_synth``). Each harness
self-announces via a module-level ``HARNESS_SPEC`` dict (same plugin idea as the
estimators' ``ESTIMATOR_SPEC``).

Inputs are **named directories, passed explicitly** — there is no single
"run directory" umbrella. PyTorchSim itself writes its two result sets to
separate locations (TOGSim logs vs per-kernel gem5/codegen outputs), so the CLI
takes one flag per input and every ``required`` input must be present; the
``run.sh`` wrapper exists for the convenience case where both happen to live
under one root.

``HARNESS_SPEC`` schema::

    HARNESS_SPEC = {
        "name": "pytorchsim",
        "description": "...",
        "inputs": {                      # name → declaration, one CLI flag each
            "<name>": {
                "flag": "--togsim-dir",  # the CLI spelling (documentation)
                "required": True,
                "kind": "dir",           # "dir" (default) | "file" | "path"
                                         # ("path" = file OR directory)
                "hint": "...",           # shown in --help / error messages
            },
        },
        "ingest": callable,              # ({name: Path}, tech, **opts) -> EmittedArch
        "synthesizes_activity": True,    # optional: no activity reader yet —
                                         # the run is VECTORLESS and the CLI's
                                         # --vectorless-activity override applies
    }
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Union

__all__ = [
    "HarnessError",
    "HarnessInfo",
    "available_harnesses",
    "get_harness",
    "run_harness",
]


class HarnessError(ValueError):
    """A harness is unknown, misdeclared, or its inputs are missing/invalid."""


@dataclass(frozen=True)
class HarnessInfo:
    name: str
    description: str
    inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ingest: Optional[Callable[..., Any]] = None
    #: True when the harness has no activity reader and synthesizes vectorless
    #: activity instead — gates the CLI's --vectorless-activity override.
    synthesizes_activity: bool = False


def _to_info(spec: Dict[str, Any]) -> HarnessInfo:
    name = spec.get("name")
    if not name:
        raise HarnessError("HARNESS_SPEC missing 'name'")
    inputs = spec.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise HarnessError(f"harness {name!r}: 'inputs' must be a non-empty dict")
    ingest = spec.get("ingest")
    if not callable(ingest):
        raise HarnessError(f"harness {name!r}: 'ingest' must be callable")
    return HarnessInfo(
        name=name,
        description=spec.get("description", ""),
        inputs={k: dict(v) for k, v in inputs.items()},
        ingest=ingest,
        synthesizes_activity=bool(spec.get("synthesizes_activity", False)),
    )


def available_harnesses() -> Dict[str, HarnessInfo]:
    """Discover every ``npuwattch.harness.<sub>`` package that declares a
    ``HARNESS_SPEC``. Import failures / non-harness subpackages are skipped.
    """
    import npuwattch.harness as pkg

    found: Dict[str, HarnessInfo] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if not mod_info.ispkg:
            continue
        try:
            mod = importlib.import_module(f"npuwattch.harness.{mod_info.name}")
        except Exception:
            continue
        spec = getattr(mod, "HARNESS_SPEC", None)
        if isinstance(spec, dict):
            info = _to_info(spec)
            found[info.name] = info
    return found


def get_harness(name: str) -> HarnessInfo:
    harnesses = available_harnesses()
    if name not in harnesses:
        avail = ", ".join(sorted(harnesses)) or "(none)"
        raise HarnessError(f"unknown harness {name!r}; available: {avail}")
    return harnesses[name]


def _validate_inputs(
    info: HarnessInfo, inputs: Mapping[str, Union[str, Path, None]]
) -> Dict[str, Path]:
    """Check the provided named directories against the harness declaration."""
    unknown = sorted(set(inputs) - set(info.inputs))
    if unknown:
        raise HarnessError(
            f"harness {info.name!r}: unknown input(s) {', '.join(unknown)}; "
            f"declared: {', '.join(sorted(info.inputs))}"
        )
    resolved: Dict[str, Path] = {}
    for iname, decl in info.inputs.items():
        value = inputs.get(iname)
        if value is None:
            if decl.get("required", True):
                flag = decl.get("flag", iname)
                hint = decl.get("hint", "")
                raise HarnessError(
                    f"harness {info.name!r}: missing required input {iname!r} "
                    f"({flag}){' — ' + hint if hint else ''}"
                )
            continue
        path = Path(value)
        kind = decl.get("kind", "dir")
        if kind == "file":
            ok, expected = path.is_file(), "file"
        elif kind == "path":
            ok, expected = path.exists(), "file or directory"
        else:
            ok, expected = path.is_dir(), "directory"
        if not ok:
            raise HarnessError(
                f"harness {info.name!r}: input {iname!r} is not a "
                f"{expected}: {path}"
            )
        resolved[iname] = path
    return resolved


def run_harness(
    name: str, inputs: Mapping[str, Union[str, Path, None]], tech: Any, **opts: Any
) -> Any:
    """Select harness ``name``, validate its named directory inputs, and run its
    ingest → ``EmittedArch``."""
    info = get_harness(name)
    resolved = _validate_inputs(info, inputs)
    return info.ingest(resolved, tech, **opts)
