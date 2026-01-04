from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import ast
import importlib.util
import runpy


@dataclass(frozen=True)
class EstimatorModuleInfo:
    """Represents one estimator module directory (e.g., 'adder', 'crossbar')."""
    name: str
    module_dir: Path
    entry_file: Path
    python_sources: List[Path]
    spec: Optional[dict]


def _resolve_estimator_root() -> Path:
    """
    Resolve the estimator root directory.

    Priority:
      1) Dev/repo usage: ./src/estimator relative to current working directory.
      2) Installed usage: locate the installed top-level 'estimator' package directory.
    """
    dev_root = Path.cwd() / "src" / "estimator"
    if dev_root.is_dir():
        return dev_root

    spec = importlib.util.find_spec("estimator")
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])

    raise FileNotFoundError(
        "[ERROR] Could not locate estimator root. Tried ./src/estimator and installed 'estimator' package."
    )


def _extract_estimator_spec(py_file: Path) -> Optional[dict]:
    """
    Extract ESTIMATOR_SPEC dict literal without importing or executing the module.
    Requires ESTIMATOR_SPEC to be a literal dict (supported by ast.literal_eval).
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ESTIMATOR_SPEC":
                    return ast.literal_eval(node.value)
    return None


class EstimatorHost:
    """
    Scans ./src/estimator (or installed equivalent) and enables calling helper functions
    in estimator modules WITHOUT importing them as Python modules.

    Additionally, the host extracts each estimator's parameter requirements from
    ESTIMATOR_SPEC during scanning (AST parse; no import/exec).
    """

    def __init__(self, estimator_root: Optional[Path] = None) -> None:
        self.estimator_root = estimator_root or _resolve_estimator_root()
        self._modules: Dict[str, EstimatorModuleInfo] = {}

    def scan_estimators(self) -> Dict[str, EstimatorModuleInfo]:
        """
        Scan estimator_root for modules of the form:
          estimator/<name>/<name>.py

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
        return sorted(self._modules.keys())

    def report_to_console(self) -> None:
        """Report all Python sources discovered under ./src/estimator (or installed equivalent)."""
        print(f"[INFO] Estimator root: {self.estimator_root}")

        if not self._modules:
            print("[WARNING] No estimator modules found.")
            return

        print("[INFO] Modules found:")
        print("=" * 80)
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

            for src in info.python_sources:
                rel = src.relative_to(self.estimator_root)
                print(f"      * {rel}")
        print("=" * 80)

    def has_module(self, name: str) -> bool:
        return name in self._modules

    def get_spec(self, module_name: str) -> dict:
        info = self._modules.get(module_name)
        if not info or not info.spec:
            raise KeyError(f"[ERROR] No ESTIMATOR_SPEC found for module '{module_name}'.")
        return info.spec

    def build_params_from_arch(self, module_name: str, arch_params: dict) -> dict:
        """
        Given params from architecture_description.yaml, produce the param dict expected
        by the estimator, using arch_keys aliases + defaults described in ESTIMATOR_SPEC.
        """
        info = self._modules.get(module_name)
        if not info or not info.spec:
            raise KeyError(f"[ERROR] Module '{module_name}' not found or missing ESTIMATOR_SPEC.")

        pblock = info.spec.get("parameters", {})
        required = pblock.get("required", []) or []
        optional = pblock.get("optional", []) or []

        out: dict = {}

        def find_value(param_def: dict) -> tuple[bool, Any]:
            for k in param_def.get("arch_keys", []) or []:
                if k in arch_params:
                    return True, arch_params[k]
            return False, None

        missing: list[str] = []
        for p in required:
            ok, val = find_value(p)
            if not ok:
                missing.append(p.get("name", "?"))
            else:
                out[p["name"]] = val

        if missing:
            raise ValueError(
                f"[ERROR] Missing required params for '{module_name}': {missing}. "
                f"[ERROR] Available arch keys: {sorted(arch_params.keys())}"
            )

        for p in optional:
            ok, val = find_value(p)
            if ok:
                out[p["name"]] = val
            elif "default" in p:
                out[p["name"]] = p["default"]

        return out

    def _load_namespace(self, module_name: str) -> Dict[str, Any]:
        """Load a module's namespace by executing its entry file via runpy (no import)."""
        info = self._modules.get(module_name)
        if not info:
            raise KeyError(f"ERROR] Estimator module '{module_name}' not found in scanned list.")
        return runpy.run_path(str(info.entry_file))

    def execute(self, module_name: str, function_name: str, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function contained in a scanned estimator module.

        This loads the file with runpy.run_path and calls the named callable.
        """
        if module_name not in self._modules:
            raise KeyError(
                f"[ERROR] Estimator module '{module_name}' not found. Available: {self.list_modules()}"
            )

        ns = self._load_namespace(module_name)
        fn = ns.get(function_name)

        if not callable(fn):
            available = sorted([k for k, v in ns.items() if callable(v)])
            raise AttributeError(
                f"[ERROR] Function '{function_name}' not found/callable in '{module_name}'. "
                f"[INFO] Callable symbols: {available}"
            )

        return fn(*args, **kwargs)

    def execute_entrypoint(self, module_name: str, entrypoint_key: str, *args: Any, **kwargs: Any) -> Any:
        """
        Execute an entrypoint declared in ESTIMATOR_SPEC['entrypoints'].
        """
        spec = self.get_spec(module_name)
        ep = (spec.get("entrypoints", {}) or {}).get(entrypoint_key)
        if not ep:
            raise KeyError(f"Entrypoint '{entrypoint_key}' not declared for '{module_name}'.")
        return self.execute(module_name, ep, *args, **kwargs)

    def get_energy(self, module_name: str, features: dict, **kwargs: Any) -> Any:
        """Convenience wrapper: calls the energy entrypoint if declared, else get_energy."""
        info = self._modules.get(module_name)
        if not info:
            raise KeyError(f"Estimator module '{module_name}' not found.")
        if info.spec and "entrypoints" in info.spec and "energy" in (info.spec.get("entrypoints") or {}):
            return self.execute_entrypoint(module_name, "energy", features, **kwargs)
        return self.execute(module_name, "get_energy", features, **kwargs)

    def estimate_energy_from_arch(self, module_name: str, arch_params: dict, **kwargs: Any) -> float:
        """
        Build params from architecture parameters and invoke the estimator energy entrypoint.
        """
        features = self.build_params_from_arch(module_name, arch_params)
        return float(self.get_energy(module_name, features, **kwargs))
