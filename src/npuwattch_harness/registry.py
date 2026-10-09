"""Harness registry. It finds each harness and runs the selected harness.

A harness is a package ``harness.<simulator>`` that declares a
module-level dict ``HARNESS_SPEC``. The estimators declare ``ESTIMATOR_SPEC``
in the same way. The ingest function of a harness reads the simulator output
and returns an ``EmittedArch``.

A harness gives only its log readers and its definitions. The core
(``npuwattch.arch_synth``) emits the description and the activity rows.

Each input is a named path that the user gives explicitly. There is no single
run directory. For example, PyTorchSim writes its TOGSim logs and its
gem5/codegen outputs for each kernel to different locations. Thus the CLI has
one flag for each input, and each ``required`` input must be present. The
wrapper ``run.sh`` is for the case where the two directories have the same
root.

The CLI parser does not contain the flags of a harness. It makes them from
the ``HARNESS_SPEC`` declarations (:func:`cli_flags`). Thus a new harness
adds its flags to the CLI without a change to the parser.

``HARNESS_SPEC`` schema::

    HARNESS_SPEC = {
        "name": "pytorchsim",
        "description": "...",
        "inputs": {                      # name -> declaration, one CLI flag each
            "<name>": {
                "flag": "--togsim-dir",  # the CLI flag
                "required": True,
                "kind": "dir",           # "dir" (default) | "file" | "path"
                                         # ("path" = file or directory)
                "hint": "...",           # text for --help and error messages
                # Optional keys:
                "requires": "<name>",    # this input needs that input
                "provides_activity": True,   # with this input, the run is
                                         # not VECTORLESS
                "names_design": "parent",    # the report gets its design
                                         # name from this path: "parent"
                                         # (directory name) or "stem"
            },
        },
        "options": {                     # optional: name -> declaration of a
            "<name>": {                  # CLI option that is not a path
                "flag": "--stats-mode",
                "choices": ["windows", "aggregate"],   # optional
                "requires": "<input name>",            # optional
                "hint": "...",
            },                           # the ingest gets it as opts[<name>]
        },
        "usage_hint": "...",             # optional: text for the error
                                         # message when the user gives -i
        "ingest": callable,              # ({name: Path}, tech, **opts) -> EmittedArch
        "synthesizes_activity": True,    # optional: the harness can make
                                         # synthetic activity. Such a run is
                                         # VECTORLESS, and the CLI option
                                         # --vectorless-activity applies
    }
"""

from __future__ import annotations

from npuwattch.diagnostics import NPUWattchError
import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Union

__all__ = [
    "HarnessError",
    "HarnessInfo",
    "available_harnesses",
    "cli_flags",
    "get_harness",
    "run_harness",
]


class HarnessError(NPUWattchError, ValueError):
    """A harness is unknown, its declaration is incorrect, or an input is incorrect."""


@dataclass(frozen=True)
class HarnessInfo:
    name: str
    description: str
    inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ingest: Optional[Callable[..., Any]] = None
    #: True if the harness can make synthetic (vectorless) activity. The CLI
    #: option --vectorless-activity applies only to such a harness.
    synthesizes_activity: bool = False
    #: CLI options that are not paths. The ingest gets them as keyword options.
    options: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: Text for the error message when the user gives ``-i`` in harness mode.
    usage_hint: str = ""


def available_harnesses() -> Dict[str, HarnessInfo]:
    """Find each package ``harness.<sub>`` that declares a ``HARNESS_SPEC``.

    The function ignores a package that does not import or that has no
    ``HARNESS_SPEC``.
    """
    import npuwattch_harness as pkg

    found: Dict[str, HarnessInfo] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if not mod_info.ispkg:
            continue
        try:
            mod = importlib.import_module(f"npuwattch_harness.{mod_info.name}")
        except Exception:
            continue
        spec = getattr(mod, "HARNESS_SPEC", None)
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not name:
            raise HarnessError.nw(5001, package=mod_info.name)
        inputs = spec.get("inputs")
        if not isinstance(inputs, dict) or not inputs:
            raise HarnessError.nw(5002, harness=name)
        ingest = spec.get("ingest")
        if not callable(ingest):
            raise HarnessError.nw(5003, harness=name)
        found[name] = HarnessInfo(
            name=name,
            description=spec.get("description", ""),
            inputs={k: dict(v) for k, v in inputs.items()},
            ingest=ingest,
            synthesizes_activity=bool(spec.get("synthesizes_activity", False)),
            options={k: dict(v)
                     for k, v in (spec.get("options") or {}).items()},
            usage_hint=str(spec.get("usage_hint", "")),
        )
    return found


def cli_flags() -> Dict[str, Dict[str, Any]]:
    """Return the CLI flags that the harnesses declare.

    The result is ``flag -> entry``. Two harnesses can declare the same flag
    (for example, ``--energy-table``). Each entry contains:

    * ``name``: the input name or the option name.
    * ``is_option``: ``True`` for an entry of ``options``.
    * ``dest``: the attribute name in the parsed arguments.
    * ``choices``: the permitted values, or ``None``.
    * ``help``: the help text, made from the hints of the harnesses.
    * ``by_harness``: harness name -> the declaration of that harness.
    """
    flags: Dict[str, Dict[str, Any]] = {}
    for hname, info in available_harnesses().items():
        for is_option, table in ((False, info.inputs), (True, info.options)):
            for name, decl in table.items():
                flag = decl.get("flag")
                if not flag:
                    continue
                entry = flags.setdefault(flag, {
                    "name": name, "is_option": is_option,
                    "dest": flag.lstrip("-").replace("-", "_"),
                    "choices": decl.get("choices"), "by_harness": {}})
                if (entry["name"], entry["is_option"]) != (name, is_option):
                    raise HarnessError.nw(
                        5004, flag=flag, first=entry["name"], second=name,
                        harness=hname)
                entry["by_harness"][hname] = decl
    for entry in flags.values():
        parts = []
        for hname, decl in entry["by_harness"].items():
            if entry["is_option"] or decl.get("required", True):
                label = f"{hname} harness"
            else:
                label = f"{hname} harness (optional)"
            parts.append(f"{label}: {decl.get('hint', '')}".rstrip(": "))
        entry["help"] = " | ".join(parts)
    return flags


def get_harness(name: str) -> HarnessInfo:
    harnesses = available_harnesses()
    if name not in harnesses:
        avail = ", ".join(sorted(harnesses)) or "(none)"
        raise HarnessError.nw(5005, harness=name, available=avail)
    return harnesses[name]


def _validate_inputs(
    info: HarnessInfo, inputs: Mapping[str, Union[str, Path, None]]
) -> Dict[str, Path]:
    """Check the named inputs against the declaration of the harness."""
    unknown = sorted(set(inputs) - set(info.inputs))
    if unknown:
        raise HarnessError.nw(
            5006, harness=info.name, unknown=", ".join(unknown),
            declared=", ".join(sorted(info.inputs)))
    resolved: Dict[str, Path] = {}
    for iname, decl in info.inputs.items():
        value = inputs.get(iname)
        if value is None:
            if decl.get("required", True):
                flag = decl.get("flag", iname)
                hint = decl.get("hint", "")
                if hint:
                    raise HarnessError.nw(5007, harness=info.name,
                                          input_name=iname, flag=flag,
                                          hint=hint)
                raise HarnessError.nw(5008, harness=info.name,
                                      input_name=iname, flag=flag)
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
            raise HarnessError.nw(5009, harness=info.name, input_name=iname,
                                  expected=expected, path=path)
        resolved[iname] = path
    return resolved


def run_harness(
    name: str, inputs: Mapping[str, Union[str, Path, None]], tech: Any, **opts: Any
) -> Any:
    """Select the harness ``name``, check its named inputs, and run its ingest.

    Return the ``EmittedArch`` that the ingest gives.
    """
    info = get_harness(name)
    resolved = _validate_inputs(info, inputs)
    return info.ingest(resolved, tech, **opts)
