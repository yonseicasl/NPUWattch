"""Reader for the ``config.yml`` of a run. This is the file that TOGSim gets
with ``--config``.

TOGSim prints this file in the header of each log. The header shows the
configuration that the run used, thus the header always has priority.
``config.yml`` is an optional input with two functions:

* It supplies the keys that a damaged or incomplete header does not have.
* It lets the harness compare the two sources. If a key has different values
  in the file and in the header, the files can be from different runs. The
  harness gives a warning for each such key and does not stop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

import yaml

from npuwattch.diagnostics import NPUWattchError, warning

__all__ = ["RunConfigError", "load_config_yml", "config_conflicts"]


class RunConfigError(NPUWattchError, ValueError):
    """The run configuration (``config.yml`` or the log header) is not correct
    or not complete."""


def load_config_yml(path: Path) -> Dict[str, Any]:
    """Read a TOGSim ``config.yml`` and return its keys and values as a dict."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RunConfigError.nw(6701, path=path, type=type(data).__name__)
    return data


def config_conflicts(base: Mapping[str, Any], merged: Mapping[str, Any]) -> List[str]:
    """Return one message for each key that has different values in
    ``config.yml`` (``base``) and in ``merged``.

    ``merged`` is ``{**base, **header}``. Thus a different value shows that
    the header also has the key and that the header value replaced the file
    value. In that case, the files can be from different runs.
    """
    return [
        warning(6702, key=k, file_value=base[k], log_value=merged[k])
        for k in sorted(base)
        if k in merged and merged[k] != base[k]
    ]
