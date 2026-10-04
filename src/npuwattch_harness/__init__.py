"""NPUWattch simulator harnesses.

A harness reads the output of one simulator and gives NPUWattch a description
of the architecture and its activity. All harnesses have the same layout::

    npuwattch_harness/<simulator>/
        __init__.py     HARNESS_SPEC: the name, the inputs, the entry point
        ingest.py       ingest(inputs, tech, **opts) -> EmittedArch
        <readers>.py    parsers for the files of the simulator
        definitions/
            vocabulary.yaml   simulator names -> NPUWattch names

The definitions of a design are inputs of the run, not part of a harness.
A harness reads them from the directory of the run inputs, or from the files
that the user gives (``run_inputs``)::

    compound_components.yaml   hardware structures made of primitives
    projection.yaml            simulator actions -> activity of the elements
    user_components.yaml       the cost of blocks that have no model

Available harnesses:

- ``pytorchsim``: PyTorchSim (PSAL-POSTECH), a weight-stationary systolic NPU.
- ``timeloop``: Timeloop/Accelergy v0.4.

Modules that all harnesses use:

- ``registry``: finds each harness and runs the one that ``--harness`` selects.
- ``run_inputs``: finds and loads the definition files of a run.
- ``vocabulary``: loads and applies a vocabulary table.
- ``compounds``: loads, checks, and resolves compounds and projections.
- ``npuwattch.arch_synth``: emits the description and the activity rows.

Terms
-----
primitive
    A hardware block that NPUWattch has a model for (``intmac``, ``sram``, ...).
compound
    A hardware structure that is a group of primitives.
element
    One primitive in a compound.
projection
    A table that connects each simulator action to the activity of the
    elements of a compound.
vocabulary table
    A table that translates simulator names into NPUWattch names.
stim_mode
    An activity mode for which a primitive has a characterized energy.
window
    One time interval of the activity. For PyTorchSim, one kernel is one
    window. For Timeloop, one layer is one window.
warning
    A message that tells the user that a result can be incorrect.
note
    A message that tells the user about a documented convention or exclusion.
"""

from .registry import (
    HarnessError,
    HarnessInfo,
    available_harnesses,
    get_harness,
    run_harness,
)

__all__ = [
    "HarnessError",
    "HarnessInfo",
    "available_harnesses",
    "get_harness",
    "run_harness",
]
