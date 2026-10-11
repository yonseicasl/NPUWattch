"""The exception classes of the built-in estimators.

The estimators raise these classes with ``Cls.nw(<number>, ...)``. The
entries are in ``npuwattch_estimators.catalog``.

Each class keeps its built-in base (``ValueError`` or ``RuntimeError``).
The provider chain and the tests catch these bases, thus their behaviour does
not change.

The classes are in this importable module, and not in the estimator files.
``EstimatorHost`` and the tests load the estimator files with runpy or by
file path, thus a class in an estimator file can have more than one class
object. A class in this module has one class object.

This module uses only ``npuwattch.diagnostics``, which uses only the
standard library.
"""

from __future__ import annotations

from npuwattch.diagnostics import CRITICAL, NPUWattchError


class EstimatorQueryError(NPUWattchError, ValueError):
    """An estimator cannot answer a query (all estimators)."""


class EstimatorInternalError(NPUWattchError, ValueError):
    """An internal check of an estimator failed. The estimator code is not correct."""

    level = CRITICAL


class LogicQueryError(EstimatorQueryError):
    """The logic estimator cannot answer a query: an attribute is missing or not characterized."""


class LogicModelError(NPUWattchError, RuntimeError):
    """The logic MLP layer cannot be loaded (torch or the checkpoints are missing)."""


class LogicCheckpointError(NPUWattchError, RuntimeError):
    """A logic checkpoint does not agree with the code that uses it."""

    level = CRITICAL


class SramQueryError(EstimatorQueryError):
    """The SRAM estimator cannot answer a query: a feature is missing, incorrect, or not characterized."""


class SramDatasetError(NPUWattchError, ValueError):
    """The SRAM dataset is not consistent. The estimator cannot use it."""

    level = CRITICAL


class SramCheckpointError(NPUWattchError, ValueError):
    """The SRAM checkpoint quartets do not agree with each other."""

    level = CRITICAL


class CustomQueryError(EstimatorQueryError):
    """The user component estimator cannot answer a query."""
