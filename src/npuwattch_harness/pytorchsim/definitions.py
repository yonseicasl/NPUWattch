"""Definitions of the PyTorchSim harness.

The harness has one definition file of its own, ``definitions/vocabulary.yaml``
(PyTorchSim names -> NPUWattch names).

The definitions of the design are inputs of the run
(``npuwattch_harness.run_inputs``): ``compound_components.yaml``,
``projection.yaml``, and ``user_components.yaml`` in the directory that
contains ``togsim_results/``. :func:`load_definitions` loads the first two.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from ..compounds import Bundle
from ..run_inputs import find_definition, load_run_bundle
from ..vocabulary import Vocabulary, load_vocabulary

__all__ = ["DEFINITIONS_DIR", "VOCABULARY", "load_definitions"]

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"

#: The vocabulary table of this harness.
VOCABULARY: Vocabulary = load_vocabulary(DEFINITIONS_DIR / "vocabulary.yaml")


def load_definitions(run_dir: Path,
                     inputs: Optional[Mapping[str, Any]] = None) -> Bundle:
    """Load and check the compounds and the projection of a run.

    ``run_dir`` is the directory of the run inputs. ``inputs`` are the named
    inputs of the harness. A file that the user gives has priority over the
    file with the fixed name in ``run_dir``.
    """
    inputs = inputs or {}
    return load_run_bundle(
        find_definition(inputs, "compound_components", run_dir),
        find_definition(inputs, "projection", run_dir))
