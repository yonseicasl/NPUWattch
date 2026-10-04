"""Access the PyTorchSim harness's shipped definition bundle.

The bundle (the systolic MAC compound + the PyTorchSim action projection) lives
next to this module under ``definitions/`` and is the DEFAULT NPUWattch loads for
PyTorchSim — and also the worked sample users copy when authoring their own. The
generic compound interpreter (load/validate/resolve) lives in
``npuwattch.harness.compounds``; only the *definition files* are here.
"""

from __future__ import annotations

from pathlib import Path

from ..compounds import Bundle, load_bundle

__all__ = ["DEFINITIONS_DIR", "load_definitions"]

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


def load_definitions() -> Bundle:
    """Load (and validate) the shipped PyTorchSim definition bundle."""
    return load_bundle(DEFINITIONS_DIR)
