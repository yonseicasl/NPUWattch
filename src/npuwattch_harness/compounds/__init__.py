"""Compounds and projections: the loaders, the checks, and the resolution."""

from __future__ import annotations

from .loader import (
    DATA_DIR,
    MAC_PRIMITIVES,
    ActionMapping,
    ActionResolution,
    Bundle,
    Compound,
    CompoundBundleError,
    CompoundElement,
    CountFrom,
    PrimitiveModes,
    Projection,
    ResolvedActionElement,
    ResolvedElement,
    load_compounds,
    load_compounds_dir,
    load_primitive_modes,
    load_projection,
    resolve_action,
    resolve_compound,
    validate_projection,
)

__all__ = [
    "DATA_DIR",
    "MAC_PRIMITIVES",
    "ActionMapping",
    "ActionResolution",
    "Bundle",
    "Compound",
    "CompoundBundleError",
    "CompoundElement",
    "CountFrom",
    "PrimitiveModes",
    "Projection",
    "ResolvedActionElement",
    "ResolvedElement",
    "load_compounds",
    "load_compounds_dir",
    "load_primitive_modes",
    "load_projection",
    "resolve_action",
    "resolve_compound",
    "validate_projection",
]
