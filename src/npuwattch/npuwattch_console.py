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
    host = EstimatorHost()
    host.scan_estimators()

    try:
        # Flatten each description file first
        flattened_files = []
        for desc_file in args.description_files:
            desc_path = Path(desc_file)
            # Generate default flattened filename
            flattened_path = desc_path.parent / f"{desc_path.stem}_flattened{desc_path.suffix}"
            
            # Call flattener to create flattened YAML
            print(f"[INFO] Flattening {desc_path} for estimator mode...")
            flatten_accelergy_v04_yaml(
                input_yaml=str(desc_path),
                output_yaml=str(flattened_path),
                print_tree=(args.verbose >= 0),
            )
            flattened_files.append(flattened_path)
        
        # Load the flattened files instead of original description files
        _descriptions = load_description_files(flattened_files)
        _activity = load_activity_logs(args.activity_logs)

        # Example: if verbose, demonstrate estimator usage
        if args.verbose >= 1:
            # Example "arch params" could be derived from architecture_description.yaml primitives
            adder_arch_params = {"bitwidth": 8, "activity": 0.5}
            crossbar_arch_params = {"inputs": 128, "outputs": 128, "activity": 0.5}

            if host.has_module("adder"):
                e = host.estimate_energy_from_arch("adder", adder_arch_params)
                print(f"[EstimatorHost] adder energy => {e}")
                # Unique helper callable (by name)
                sw = host.execute("adder", "estimate_switching_energy", 8, 0.5)
                print(f"[EstimatorHost] adder.estimate_switching_energy(8,0.5) => {sw}")
            else:
                print("[EstimatorHost] 'adder' not found.")

            if host.has_module("crossbar"):
                e = host.estimate_energy_from_arch("crossbar", crossbar_arch_params)
                print(f"[EstimatorHost] crossbar energy => {e}")
                ce = host.execute("crossbar", "estimate_conductance_energy", 128, 128, 0.5)
                print(f"[EstimatorHost] crossbar.estimate_conductance_energy(128,128,0.5) => {ce}")
            else:
                print("[EstimatorHost] 'crossbar' not found.")

        return 0

    finally:
        # Always rescan and report modules after execution
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
