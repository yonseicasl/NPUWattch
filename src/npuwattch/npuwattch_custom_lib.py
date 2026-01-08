"""NPUWattch Custom Component Library.

This module handles lookup of custom components from a CSV library file.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CUSTOM_LIB_PATH = "src/estimators/custom/custom_lib.csv"


def lookup_custom_component(
    comp_class: str,
    subclass: Optional[str] = None,
    csv_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Look up a custom component from the CSV library.

    Matching logic:
    - comp_class must exactly match the "name" column
    - subclass match is optional but prioritized
    - If multiple matches exist, warns and selects the first found

    Args:
        comp_class: Component class to match (must match exactly)
        subclass: Component subclass to match (optional, for prioritization)
        csv_path: Path to CSV file (default: src/estimators/custom/custom_lib.csv)

    Returns:
        Dict of features from the matched row, or None if no match found.
    """
    csv_path = csv_path or DEFAULT_CUSTOM_LIB_PATH

    path = Path(csv_path)
    if not path.is_file():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception:
        return None

    if not rows:
        return None

    # Find rows where name matches comp_class exactly
    class_matches: List[Dict[str, str]] = [
        row for row in rows if row.get("name") == comp_class
    ]

    if not class_matches:
        return None

    # Check for rows where both comp_class and subclass match
    if subclass:
        both_matches = [
            row for row in class_matches if row.get("subclass") == subclass
        ]
        if both_matches:
            if len(both_matches) > 1:
                print(
                    f"[WARNING] Multiple custom components match class '{comp_class}' "
                    f"and subclass '{subclass}'. Selecting first found."
                )
            return _row_to_features(both_matches[0])

    # Fall back to class-only matches
    if len(class_matches) > 1:
        print(
            f"[WARNING] Multiple custom components match class '{comp_class}'. "
            f"Selecting first found."
        )

    return _row_to_features(class_matches[0])


def _row_to_features(row: Dict[str, str]) -> Dict[str, Any]:
    """Convert a CSV row to a features dictionary."""
    features: Dict[str, Any] = {}
    for key, value in row.items():
        if key in ("name", "subclass"):
            continue
        # Try to convert to appropriate type
        try:
            if "." in value:
                features[key] = float(value)
            else:
                features[key] = int(value)
        except (ValueError, TypeError):
            features[key] = value
    return features
