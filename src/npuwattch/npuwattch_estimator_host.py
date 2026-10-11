"""NPUWattch estimator host.

This module finds the estimator plugins in ``src/npuwattch_estimators`` and
calls them. It does **not import** a plugin. It reads the spec with ``ast``
and runs the code with ``runpy``. Thus the large dependencies of a plugin
(torch, for example) do not enter the import graph of the main program.

Functions of the host:

- Scan the available estimators and read their ``ESTIMATOR_SPEC``.
- Run the declared entrypoints (``unit_cost_provider``, ``energy``, …).
- Train models through the ``train_*`` entrypoint of a plugin.
- Report an error without a stop of the program.

The host does **not** select the estimator of a component. The harness that
reads the description changes each class to a primitive (for example,
``npuwattch_harness/timeloop/vocabulary.py``). The provider chain of
``energy.provider_factory`` gives the costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ast
import importlib.util
import runpy

from npuwattch import diagnostics as diag
from npuwattch.diagnostics import NPUWattchError


class EstimatorRootError(NPUWattchError, FileNotFoundError):
    """The directory of the estimator plugins cannot be found."""


@dataclass(frozen=True)
class EstimatorModuleInfo:
    """One estimator plugin directory (for example, ``logic`` or ``sram``).

    One plugin can serve more than one primitive. The ``logic`` plugin
    declares a ``primitives`` list of all the logic primitives that it serves.
    Thus the directory name is the name of the plugin, not of a primitive.
    """
    name: str
    module_dir: Path
    entry_file: Path
    python_sources: List[Path]
    spec: Optional[dict]


def _resolve_estimator_root() -> Path:
    """
    Find the estimator root directory.

    Priority:
      1) Repository use: ./src/npuwattch_estimators in the current working directory.
      2) Installed use: the directory of the installed 'npuwattch_estimators' package.
    """
    dev_root = Path.cwd() / "src" / "npuwattch_estimators"
    if dev_root.is_dir():
        return dev_root

    spec = importlib.util.find_spec("npuwattch_estimators")
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])

    raise EstimatorRootError.nw(1201)


def _extract_estimator_spec(py_file: Path) -> Optional[dict]:
    """
    Read the ESTIMATOR_SPEC dict of a file. Do not import or run the module.
    ESTIMATOR_SPEC must be a literal dict that ast.literal_eval accepts.
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
    Scans the estimator root and calls functions of the estimator plugins.
    The host does NOT import a plugin as a Python module.

    The estimation methods return None on an error. They do not stop the program.
    """

    def __init__(self, estimator_root: Optional[Path] = None,
                 verbose: int = 0) -> None:
        self.estimator_root = estimator_root or _resolve_estimator_root()
        self._modules: Dict[str, EstimatorModuleInfo] = {}
        self.verbose = verbose

    def scan_estimators(self) -> Dict[str, EstimatorModuleInfo]:
        """
        Scan estimator_root for plugins of the form:
          npuwattch_estimators/<name>/<name>.py

        For each plugin, record all its .py files and read its ESTIMATOR_SPEC.
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
        """Return the sorted names of the estimator plugins."""
        return sorted(self._modules.keys())

    def report_to_console(self) -> None:
        """Print the plugins and the Python files in the estimator root."""
        diag.info(1202, path=self.estimator_root).emit()

        if not self._modules:
            diag.warning(1203).emit()
            return

        diag.info(1204).emit()
        print("=" * 100)  # nw-lint: text
        for name in self.list_modules():
            info = self._modules[name]
            rel_entry = info.entry_file.relative_to(self.estimator_root)
            print(f"  - {name} (entry: {rel_entry})")  # nw-lint: text

            # Print the required parameters, if the spec gives them.
            required = []
            if info.spec:
                required = info.spec.get("parameters", {}).get("required", []) or []
            if required:
                req_names = [p.get("name", "?") for p in required]
                print(f"      required_params: {req_names}")  # nw-lint: text

            if self.verbose >= 2:
                for src in info.python_sources:
                    rel = src.relative_to(self.estimator_root)
                    print(f"      * {rel}")  # nw-lint: text
        print("=" * 100)  # nw-lint: text

    def has_module(self, name: str) -> bool:
        """Return True if the estimator plugin exists."""
        return name in self._modules

    def get_spec(self, module_name: str) -> Optional[dict]:
        """Return the ESTIMATOR_SPEC of a plugin, or None if there is none."""
        info = self._modules.get(module_name)
        if not info or not info.spec:
            return None
        return info.spec

    def _load_namespace(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Run the entry file of a plugin with runpy and return its namespace."""
        info = self._modules.get(module_name)
        if not info:
            return None
        try:
            return runpy.run_path(str(info.entry_file))
        except Exception as e:
            diag.error(1205, module=module_name, error=e).emit()
            return None

    def execute(
        self, module_name: str, function_name: str, *args: Any, **kwargs: Any
    ) -> Tuple[Any, Optional[diag.Diagnostic]]:
        """
        Run a function of a scanned estimator plugin.

        Returns:
            (result, error_message). On success, error_message is None.
            On failure, result is None and error_message is the catalog
            message (a ``str``) that describes the error. The host prints
            the message.
        """
        if module_name not in self._modules:
            error = diag.error(1206, module=module_name,
                               available=self.list_modules())
            error.emit()
            return None, error

        ns = self._load_namespace(module_name)
        if ns is None:
            error = diag.error(1207, module=module_name)
            error.emit()
            return None, error

        fn = ns.get(function_name)
        if not callable(fn):
            available = sorted([k for k, v in ns.items() if callable(v) and not k.startswith('_')])
            error = diag.error(1208, function=function_name,
                               module=module_name, available=available)
            error.emit()
            return None, error

        try:
            result = fn(*args, **kwargs)
            return result, None
        except Exception as e:
            error = diag.error(1209, module=module_name,
                               function=function_name, error=e)
            error.emit()
            return None, error

    def execute_entrypoint(
        self, module_name: str, entrypoint_key: str, *args: Any, **kwargs: Any
    ) -> Tuple[Any, Optional[diag.Diagnostic]]:
        """
        Run an entrypoint that ESTIMATOR_SPEC['entrypoints'] declares.

        Returns:
            (result, error_message).
        """
        spec = self.get_spec(module_name)
        if not spec:
            error = diag.error(1210, module=module_name)
            error.emit()
            return None, error

        ep = (spec.get("entrypoints", {}) or {}).get(entrypoint_key)
        if not ep:
            error = diag.error(1211, entrypoint=entrypoint_key,
                               module=module_name)
            error.emit()
            return None, error

        return self.execute(module_name, ep, *args, **kwargs)

    ###########################################################################
    # Estimation methods: return None on an error, do not stop the program
    ###########################################################################

    def estimate_energy(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Estimate the energy for the given features.

        Args:
            module_name: The name of the estimator plugin
            features: The feature dictionary

        Returns:
            The energy, or None if the estimation failed
        """
        if not self.has_module(module_name):
            diag.error(1212, module=module_name, metric="energy").emit()
            return None

        result, error = self.execute_entrypoint(module_name, "energy", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_area(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Estimate the area for the given features.

        Args:
            module_name: The name of the estimator plugin
            features: The feature dictionary

        Returns:
            The area, or None if the estimation failed
        """
        if not self.has_module(module_name):
            diag.error(1212, module=module_name, metric="area").emit()
            return None

        result, error = self.execute_entrypoint(module_name, "area", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_timing(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Optional[float]:
        """
        Estimate the timing for the given features.

        Args:
            module_name: The name of the estimator plugin
            features: The feature dictionary

        Returns:
            The timing, or None if the estimation failed
        """
        if not self.has_module(module_name):
            diag.error(1212, module=module_name, metric="timing").emit()
            return None

        result, error = self.execute_entrypoint(module_name, "timing", features, **kwargs)
        if error:
            return None
        return float(result) if result is not None else None

    def estimate_all(
        self, module_name: str, features: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Optional[float]]:
        """
        Estimate the energy, the area, and the timing for the given features.

        Args:
            module_name: The name of the estimator plugin
            features: The feature dictionary

        Returns:
            A dictionary with the keys 'energy', 'area', 'timing'. A value can be None.
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
    ) -> Tuple[Any, Optional[diag.Diagnostic]]:
        """
        Train a model of the given estimator.

        Args:
            module_name: The name of the estimator plugin
            model_type: The model type ('energy', 'area', 'timing')
            csv_file: The path of the training data CSV
            output_path: The optional output path of the model
            epochs: The number of training epochs
            batch_size: The training batch size
            lr: The learning rate

        Returns:
            (trained_model, error_message)
        """
        if not self.has_module(module_name):
            error = diag.error(1213, module=module_name)
            error.emit()
            return None, error

        # Find the training entrypoint.
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
    # Utility methods
    ###########################################################################

    def get_available_entrypoints(self, module_name: str) -> List[str]:
        """Return the entrypoint names of a plugin."""
        spec = self.get_spec(module_name)
        if not spec:
            return []
        return list((spec.get("entrypoints", {}) or {}).keys())

    def check_model_availability(self, module_name: str) -> Optional[Dict[str, bool]]:
        """
        Find which models of an estimator are available.

        Returns:
            A dictionary of model type -> availability, or None if the check failed
        """
        if not self.has_module(module_name):
            diag.error(1214, module=module_name).emit()
            return None

        result, error = self.execute(module_name, "check_models_available")
        if error:
            return None
        return result
