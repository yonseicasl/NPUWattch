"""NPUWattch Console Application.

This is the main entry point for the NPUWattch CLI tool.
Supports three modes:
1. Flatten mode: Convert Accelergy v0.4 YAML to flattened format
2. Estimator mode: Run energy/area/timing estimation on architecture
3. Training mode: Train MLP models for estimation
"""

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
from npuwattch.npuwattch_db import build_database, NPUWattchDatabase, ComponentEntry


def _run_flattener(args) -> int:
    """Run YAML flattener mode."""
    flatten_accelergy_v04_yaml(
        input_yaml=str(args.input_yaml),
        output_yaml=str(args.output_yaml),
        print_tree=(args.verbose >= 1),
    )
    return 0


def _run_training(args, host: EstimatorHost) -> int:
    """Run model training mode."""
    print(f"[INFO] Starting training mode")
    print(f"[INFO] Estimator: {args.train_estimator}")
    print(f"[INFO] Model type: {args.train_model_type}")
    print(f"[INFO] Training data: {args.train_csv}")
    print(f"[INFO] Epochs: {args.train_epochs}, Batch size: {args.train_batch_size}, LR: {args.train_lr}")
    print("=" * 80)

    result, error = host.train_model(
        module_name=args.train_estimator,
        model_type=args.train_model_type,
        csv_file=str(args.train_csv),
        output_path=str(args.train_output) if args.train_output else None,
        epochs=args.train_epochs,
        batch_size=args.train_batch_size,
        lr=args.train_lr,
    )

    if error:
        print(f"[ERROR] Training failed: {error}")
        return 1

    print("[INFO] Training completed successfully!")
    return 0

def _run_estimator(args) -> int:
    """Run estimator (normal) mode."""
    print("[INFO] Starting estimator mode")
    print("=" * 100)

    # Initialize estimator host
    host = EstimatorHost(verbose=args.verbose)
    host.scan_estimators()

    try:
        # Process each description file
        flattened_files: List[Path] = []
        databases: List[NPUWattchDatabase] = []

        for desc_file in args.description_files:
            desc_path = Path(desc_file)
            flattened_path = desc_path.parent / f"{desc_path.stem}_flattened{desc_path.suffix}"

            # Flatten the YAML
            print(f"[INFO] Flattening {desc_path}...")
            flatten_accelergy_v04_yaml(
                input_yaml=str(desc_path),
                output_yaml=str(flattened_path),
                print_tree=(args.verbose >= 1),
            )
            flattened_files.append(flattened_path)

            # Build database
            db = build_database(
                yaml_path=flattened_path,
                verbose=args.verbose,
            )
            databases.append(db)

        # Report available estimators
        if args.verbose >= 1:
            host.report_to_console()

        # Run estimation on each database
        host.estimate_databases(databases)

        print("\n[INFO] Estimation completed.")
        return 0

    except Exception as e:
        print(f"[ERROR] Estimation failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for NPUWattch CLI."""
    msg._print_intro()

    argv_list: List[str] = list(sys.argv[1:] if argv is None else argv)

    try:
        args = parse_args(argv_list)
    except SystemExit as e:
        return 0 if (e.code == 0) else 1

    # Initialize estimator host for training mode
    if args.train:
        host = EstimatorHost(verbose=args.verbose)
        host.scan_estimators()
        return _run_training(args, host)

    # Mode dispatch
    if args.flatten:
        return _run_flattener(args)

    return _run_estimator(args)


if __name__ == "__main__":
    raise SystemExit(main())