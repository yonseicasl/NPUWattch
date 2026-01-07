from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import npuwattch.npuwattch_messages as msg
from npuwattch.npuwattch_parser import (
    parse_args,
    load_description_files,
    load_activity_logs,
)
from npuwattch.npuwattch_estimator_host import EstimatorHost
from npuwattch.yaml_flattener_accelergy_v4 import flatten_accelergy_v04_yaml
from npuwattch.npuwattch_db import build_database, NPUWattchDatabase

def _run_flattener(args) -> int:
    """Run YAML flattener mode."""
    flatten_accelergy_v04_yaml(
        input_yaml=str(args.input_yaml),
        output_yaml=str(args.output_yaml),
        print_tree=(args.verbose >= 0),
    )
    return 0


def _run_estimator(args) -> int:
    """Run estimator (normal) mode."""

    try:
        # Flatten each description file first
        flattened_files: List[Path] = []
        databases: List[NPUWattchDatabase] = []
        
        for desc_file in args.description_files:
            desc_path = Path(desc_file)
            # Generate default flattened filename
            flattened_path = desc_path.parent / f"{desc_path.stem}_flattened{desc_path.suffix}"
            
            # Call flattener to create flattened YAML
            flatten_accelergy_v04_yaml(
                input_yaml=str(desc_path),
                output_yaml=str(flattened_path),
                print_tree=(args.verbose >= 0),
            )
            flattened_files.append(flattened_path)
            
            # Build database from the flattened file
            db = build_database(
                yaml_path=flattened_path,
                verbose=args.verbose,
            )
            databases.append(db)


    finally:
        print("[INFO] YAML processing and database construction completed.")

    host = EstimatorHost()
    host.scan_estimators()
    host.report_to_console()


def main(argv: Optional[List[str]] = None) -> int:
    """Welcome message, arg parsing, and mode dispatch."""
    msg._print_intro()

    argv_list: List[str] = list(sys.argv[1:] if argv is None else argv)

    try:
        args = parse_args(argv_list)
    except SystemExit as e:
        # 0 for --help, non-zero (often 2) for errors.
        return 0 if (e.code == 0) else 1

    # Mode dispatch
    if args.flatten:
        return _run_flattener(args)

    return _run_estimator(args)


if __name__ == "__main__":
    raise SystemExit(main())