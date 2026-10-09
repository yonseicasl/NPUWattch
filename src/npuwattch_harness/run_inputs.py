"""Definition files that are inputs of a run. All harnesses use this module.

Three definition files describe the design of a run. They are inputs, not
part of NPUWattch:

``compound_components.yaml``
    The compound components of the design: hardware structures that are
    groups of NPUWattch primitives.
``projection.yaml``
    The connection between the simulator actions and the elements of the
    compounds.
``user_components.yaml``
    The user component library: the cost of blocks that NPUWattch has no
    model for.

A harness finds each file in this order:

1. The file that the user gives with the CLI option (``--compound-components``,
   ``--projection``, ``--user-components``).
2. The file with the fixed name in the directory of the run inputs. For
   PyTorchSim this is the directory that contains ``togsim_results/``. For
   Timeloop this is the directory of the architecture file.

There is no default in NPUWattch. If a file is not found, the run stops with
an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from npuwattch.user_components import (
    UserComponent,
    UserComponentError,
    load_user_components,
    unused_component_notes,
)

from .compounds import (
    Bundle,
    CompoundBundleError,
    load_compounds,
    load_compounds_dir,
    load_primitive_modes,
    load_projection,
)
from .registry import HarnessError

__all__ = [
    "DEFINITION_INPUTS",
    "FIXED_NAMES",
    "attach_user_components",
    "find_definition",
    "load_run_bundle",
    "load_user_library",
]

#: Input name -> the fixed file name in the directory of the run inputs.
FIXED_NAMES: Dict[str, str] = {
    "compound_components": "compound_components.yaml",
    "projection": "projection.yaml",
    "user_components": "user_components.yaml",
}

#: The ``HARNESS_SPEC`` input declarations of the three definition files.
#: A harness adds them to its ``inputs``. They are not ``required`` on the
#: command line, because the fixed name in the run directory is sufficient.
DEFINITION_INPUTS: Dict[str, Dict[str, Any]] = {
    "compound_components": {
        "flag": "--compound-components",
        "required": False,
        "kind": "path",
        "hint": "the compound components of the design (a yaml file, or a "
                "directory of yaml files). Default: compound_components.yaml "
                "in the directory of the run inputs",
    },
    "projection": {
        "flag": "--projection",
        "required": False,
        "kind": "file",
        "hint": "the projection: simulator actions -> elements of the "
                "compound components. Default: projection.yaml in the "
                "directory of the run inputs",
    },
    "user_components": {
        "flag": "--user-components",
        "required": False,
        "kind": "file",
        "hint": "the user component library: the area and the action "
                "energies of blocks that NPUWattch has no model for. "
                "Default: user_components.yaml in the directory of the run "
                "inputs",
    },
}


def find_definition(inputs: Mapping[str, Any], name: str, run_dir: Path) -> Path:
    """Return the path of the definition file ``name`` of a run.

    ``inputs`` are the named inputs of the harness. ``run_dir`` is the
    directory of the run inputs. Raise :class:`HarnessError` if the user gave
    no file and ``run_dir`` has no file with the fixed name.
    """
    given = inputs.get(name)
    if given:
        return Path(given)
    path = Path(run_dir) / FIXED_NAMES[name]
    if path.exists():
        return path
    flag = DEFINITION_INPUTS[name]["flag"]
    raise HarnessError.nw(5101, file_name=FIXED_NAMES[name], run_dir=run_dir,
                          flag=flag)


def load_run_bundle(compounds_path: Path, projection_path: Path) -> Bundle:
    """Load and check the compound components and the projection of a run.

    ``compounds_path`` is one file or a directory of files.
    """
    try:
        compounds_path = Path(compounds_path)
        compounds = (load_compounds_dir(compounds_path)
                     if compounds_path.is_dir()
                     else load_compounds(compounds_path))
        projection = load_projection(Path(projection_path))
        bundle = Bundle(compounds=compounds,
                        projections={projection.tool: projection},
                        primitive_modes=load_primitive_modes())
        bundle.validate()
    except CompoundBundleError as e:
        raise HarnessError.nw(5102, error=e) from e
    return bundle


def load_user_library(path: Path) -> Dict[str, UserComponent]:
    """Load the user component library of a run."""
    try:
        return load_user_components(Path(path))
    except UserComponentError as e:
        raise HarnessError.nw(5103, error=e) from e


def attach_user_components(description: Mapping[str, Any],
                           library: Mapping[str, UserComponent],
                           source: Path, notes: List[str]) -> None:
    """Copy the library components that the design uses into the description.

    A component of the description uses a library component if its class is
    the name of the library component. The function adds one note for each
    library component that the design does not use.
    """
    body = description["npuwattch"]
    used = [name for name in library
            if any(c.get("class") == name for c in body["components"])]
    if used:
        body["user_components"] = {name: library[name].to_dict()
                                   for name in used}
    notes.extend(unused_component_notes(library, used, Path(source).name))
