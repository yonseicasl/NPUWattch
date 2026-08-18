"""NPUWattch Estimator Host Module.

Discovers the estimator plugins under ``src/estimators`` and calls into them
**without importing them** (``ast`` for the spec, ``runpy`` for execution), so a
plugin's heavy dependencies — torch, in particular — never enter the main
program's import graph.

Responsibilities:
- Scanning available estimators and reading their ``ESTIMATOR_SPEC``
- Executing declared entrypoints (``unit_cost_provider``, ``energy``, …)
- Training models through a plugin's ``train_*`` entrypoint
- Error handling without program termination

It does **not** decide which estimator a given architecture component belongs
to. That routing used to live here (class→plugin table + per-component feature
extraction) and served the retired legacy Accelergy path; it now belongs to the
harness that reads the description (``harness/timeloop/vocabulary.py``), and
pricing goes through ``energy.provider_factory``'s composed provider chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ast
import importlib.util
import runpy


@dataclass(frozen=True)
class EstimatorModuleInfo:
    """One estimator plugin directory (``logic``, ``sram``).

    A plugin may serve several primitives — the ``logic`` module declares a
    ``primitives`` list covering all 14 characterized blocks — so the directory
    name is the plugin's, not a primitive's.
    """
    name: str
    module_dir: Path
    entry_file: Path
    python_sources: List[Path]
    spec: Optional[dict]


def _resolve_estimator_root() -> Path:
    """
    Resolve the estimator root directory.

    Priority:
      1) Dev/repo usage: ./src/estimators relative to current working directory.
      2) Installed usage: locate the installed top-level 'estimators' package directory.
    """
    dev_root = Path.cwd() / "src" / "estimators"
    if dev_root.is_dir():
        return dev_root

    spec = importlib.util.find_spec("estimators")
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])

    raise FileNotFoundError(
        "[ERROR] Could not locate estimator root. Tried ./src/estimators and installed 'estimators' package."
    )


def _extract_estimator_spec(py_file: Path) -> Optional[dict]:
    """
    Extract ESTIMATOR_SPEC dict literal without importing or executing the module.
    Requires ESTIMATOR_SPEC to be a literal dict (supported by ast.literal_eval).
    """
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "ESTIMATOR_SPEC":
                        return ast.literal_eval(node.value)
    except Exception:
        pass
    return None


class EstimatorHost:
    """
    Scans ./src/estimators (or installed equivalent) and enables calling helper functions
    in estimator modules WITHOUT importing them as Python modules.

    Provides safe estimation methods that return None on error instead of terminating.
    """

    def __init__(self, estimator_root: Optional[Path] = None,
                 verbose: int = 0) -> None:
        self.estimator_root = estimator_root or _resolve_estimator_root()
        self._modules: Dict[str, EstimatorModuleInfo] = {}
        self.verbose = verbose

    def scan_estimators(self) -> Dict[str, EstimatorModuleInfo]:
        """
        Scan estimator_root for modules of the form:
          estimators/<name>/<name>.py

        For each module, record all .py sources for reporting and extract ESTIMATOR_SPEC.
        """
        root = self.estimator_root
        modules: Dict[str, EstimatorModuleInfo] = {}

        if not root.exists():
            self._modules = {}
            return self._modules

        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue

            name = child.name
            entry = child / f"{name}.py"
            if not entry.is_file():
                continue

            py_sources = sorted(child.rglob("*.py"))
            spec = _extract_estimator_spec(entry)

            modules[name] = EstimatorModuleInfo(
                name=name,
                module_dir=child,
                entry_file=entry,
                python_sources=py_sources,
                spec=spec,
            )

        self._modules = modules
        return self._modules

    def list_modules(self) -> List[str]:
        """Return list of available estimator module names."""
        return sorted(self._modules.keys())

    def report_to_console(self) -> None:
        """Report all Python sources discovered under ./src/estimators."""
        print(f"[INFO] Estimator root: {self.estimator_root}")

        if not self._modules:
            print("[WARNING] No estimator modules found.")
            return

        print("[INFO] Modules found:")
        print("=" * 100)
        for name in self.list_modules():
            info = self._modules[name]
            rel_entry = info.entry_file.relative_to(self.estimator_root)
            print(f"  - {name} (entry: {rel_entry})")

            # Report required params (if available)
            required = []
            if info.spec:
                required = info.spec.get("parameters", {}).get("required", []) or []
            if required:
                req_names = [p.get("name", "?") for p in required]
                print(f"      required_params: {req_names}")

            if self.verbose >= 2:
                for src in info.python_sources:
                    rel = src.relative_to(self.estimator_root)
                    print(f"      * {rel}")
        print("=" * 100)

    def has_module(self, name: str) -> bool:
        """Check if an estimator module exists."""
        return name in self._modules

    def get_spec(self, module_name: str) -> Optional[dict]:
        """Get the ESTIMATOR_SPEC for a module, or None if not found."""
        info = self._modules.get(module_name)
        if not info or not info.spec:
            return None
        return info.spec

    def _load_namespace(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Load a module's namespace by executing its entry file via runpy (no import)."""
        info = self._modules.get(module_name)
        if not info:
            return None
        try:
            return runpy.run_path(str(info.entry_file))
        except Exception as e:
            print(f"[ERROR] Failed to load module '{module_name}': {e}")
            return None

    def execute(
        self, module_name: str, function_name: str, *args: Any, **kwargs: Any
    ) -> Tuple[Any, Optional[str]]:
        """
        Execute a function contained in a scanned estimator module.

        Returns:
            Tuple of (result, error_message). If successful, error_message is None.
            If failed, result is None and error_message contains the error.
        """
        if module_name not in self._modules:
            error = f"[ERROR] Estimator module '{module_name}' not found. Available: {self.list_modules()}"
            print(error)
            return None, error

        ns = self._load_namespace(module_name)
        if ns is None:
            error = f"[ERROR] Failed to load namespace for module '{module_name}'"
            print(error)
            return None, error

        fn = ns.get(function_name)
        if not callable(fn):
            available = sorted([k for k, v in ns.items() if callable(v) and not k.startswith('_')])
            error = (f"[ERROR] Function '{function_name}' not found/callable in '{module_name}'. "
                     f"Available: {available}")
            print(error)
            return None, error

        try:
            result = fn(*args, **kwargs)
            return result, None
        except Exception as e:
            error = f"[ERROR] Exception in {module_name}.{function_name}: {e}"
            print(error)
            return None, error

    def execute_entrypoint(
        self, module_name: str, entrypoint_key: str, *args: Any, **kwargs: Any
    ) -> Tuple[Any, Optional[str]]:
        """
        Execute an entrypoint declared in ESTIMATOR_SPEC['entrypoints'].

        Returns:
            Tuple of (result, error_message).
        """
        spec = self.get_spec(module_name)
        if not spec:
            error = f"[ERROR] No ESTIMATOR_SPEC found for module '{module_name}'"
            print(error)
            return None, error

        ep = (spec.get("entrypoints", {}) or {}).get(entrypoint_key)
        if not ep:
            error = f"[ERROR] Entrypoint '{entrypoint_key}' not declared for '{module_name}'"
            print(error)
            return None, error

        return self.execute(module_name, ep, *args, **kwargs)

    ###########################################################################
    # Safe Estimation Methods - Return None on error, don't terminate
    ###########################################################################

    def estimate_energy(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Safely estimate energy for given features.

        Args:
            module_name: Name of the estimator module
            features: Feature dictionary for estimation

        Returns:
            Estimated energy value or None if estimation failed
        """
        if not self.has_module(module_name):
            print(f"[ERROR] Estimator '{module_name}' does not exist. Returning None for energy.")
            return None

        result, error = self.execute_entrypoint(module_name, "energy", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_area(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Safely estimate area for given features.

        Args:
            module_name: Name of the estimator module
            features: Feature dictionary for estimation

        Returns:
            Estimated area value or None if estimation failed
        """
        if not self.has_module(module_name):
            print(f"[ERROR] Estimator '{module_name}' does not exist. Returning None for area.")
            return None

        result, error = self.execute_entrypoint(module_name, "area", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_timing(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Safely estimate timing for given features.

        Args:
            module_name: Name of the estimator module
            features: Feature dictionary for estimation

        Returns:
            Estimated timing value or None if estimation failed
        """
        if not self.has_module(module_name):
            print(f"[ERROR] Estimator '{module_name}' does not exist. Returning None for timing.")
            return None

        result, error = self.execute_entrypoint(module_name, "timing", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_all(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Optional[float]]:
        """
        Estimate energy, area, and timing for given features.

        Args:
            module_name: Name of the estimator module
            features: Feature dictionary for estimation

        Returns:
            Dictionary with 'energy', 'area', 'timing' keys (values may be None)
        """
        return {
            "energy": self.estimate_energy(module_name, features, **kwargs),
            "area": self.estimate_area(module_name, features, **kwargs),
            "timing": self.estimate_timing(module_name, features, **kwargs),
        }

    def train_model(
        self,
        module_name: str,
        model_type: str,
        csv_file: str,
        output_path: Optional[str] = None,
        epochs: int = 500,
        batch_size: int = 10,
        lr: float = 1e-3,
    ) -> Tuple[Any, Optional[str]]:
        """
        Train a model for the specified estimator.

        Args:
            module_name: Name of the estimator module
            model_type: Type of model to train ('energy', 'area', 'timing')
            csv_file: Path to training data CSV
            output_path: Optional output path for saved model
            epochs: Number of training epochs
            batch_size: Training batch size
            lr: Learning rate

        Returns:
            Tuple of (trained_model, error_message)
        """
        if not self.has_module(module_name):
            error = f"[ERROR] Estimator '{module_name}' does not exist. Cannot train."
            print(error)
            return None, error

        # Determine the training entrypoint
        spec = self.get_spec(module_name)
        if spec:
            entrypoints = spec.get("entrypoints", {})
            train_entrypoint = f"train_{model_type}"
            if train_entrypoint in entrypoints:
                train_func = entrypoints[train_entrypoint]
            else:
                train_func = f"train_{model_type}_model"
        else:
            train_func = f"train_{model_type}_model"

        return self.execute(
            module_name,
            train_func,
            csv_file,
            output_path,
            epochs,
            batch_size,
            lr,
        )

    ###########################################################################
    # Utility Methods
    ###########################################################################

    def get_available_entrypoints(self, module_name: str) -> List[str]:
        """Get list of available entrypoints for a module."""
        spec = self.get_spec(module_name)
        if not spec:
            return []
        return list((spec.get("entrypoints", {}) or {}).keys())

    def check_model_availability(self, module_name: str) -> Optional[Dict[str, bool]]:
        """
        Check which models are available for an estimator.

        Returns:
            Dictionary mapping model types to availability, or None if check failed
        """
        if not self.has_module(module_name):
            print(f"[ERROR] Estimator '{module_name}' does not exist.")
            return None

        result, error = self.execute(module_name, "check_models_available")
        if error:
            return None
        return result
