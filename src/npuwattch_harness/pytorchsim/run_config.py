"""The run's ``config.yml`` — the file passed to TOGSim via ``--config``.

The log *header* (the binary's echo of this file at run time) is the per-run
truth and always wins; ``config.yml`` is an optional side input that

* **fills in** keys a damaged/truncated header is missing, and
* **cross-checks** the pairing: a key present in both with different values
  means the directory mixes files from different runs — surfaced as warnings,
  never an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

import yaml

__all__ = ["load_config_yml", "config_conflicts"]


def load_config_yml(path: Path) -> Dict[str, Any]:
    """Parse a TOGSim ``config.yml`` into a flat key/value dict."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping, got {type(data).__name__}")
    return data


def config_conflicts(base: Mapping[str, Any], merged: Mapping[str, Any]) -> List[str]:
    """Keys where config.yml (``base``) disagrees with the header-merged config.

    ``merged`` is ``{**base, **header}``, so a differing value means the header
    carried the key too and won — evidence of a mixed run directory.
    """
    return [
        f"config.yml disagrees with the log header: {k} = {base[k]!r} vs {merged[k]!r}"
        for k in sorted(base)
        if k in merged and merged[k] != base[k]
    ]
