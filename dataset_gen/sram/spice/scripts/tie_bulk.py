#!/usr/bin/env python3
"""
tie_bulk.py — Connect MOS bulk terminals to supply rails.

The ICV + icv_nettran extraction flow emits floating internal nets as the
bulk (4th) terminal of every transistor.  This script rewrites those nodes:
  nmos1  bulk → VSS
  pmos1  bulk → VDD

Ported from NN_sram_datagen/KNU_20nm/03-pl/new_test.py (replace_mos_type).

Usage:
    python3 tie_bulk.py <input.sp> <output.sp>
"""

import sys

BULK_MAP = {
    'nmos1': 'VSS',
    'pmos1': 'VDD',
}


def tie_bulk(lines):
    result = []
    for line in lines:
        if line.startswith('M'):
            parts = line.split()
            model = parts[5] if len(parts) > 5 else ''
            if model in BULK_MAP:
                parts[4] = BULK_MAP[model]
                line = ' '.join(parts) + '\n'
        result.append(line)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: tie_bulk.py <input.sp> <output.sp>', file=sys.stderr)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, 'r') as f:
        lines = f.readlines()

    tied = tie_bulk(lines)

    with open(out_path, 'w') as f:
        f.writelines(tied)

    n_nmos = sum(1 for l in tied if l.startswith('M') and 'nmos1' in l)
    n_pmos = sum(1 for l in tied if l.startswith('M') and 'pmos1' in l)
    print('tie_bulk: {} nmos1 → VSS, {} pmos1 → VDD  ({} → {})'.format(
        n_nmos, n_pmos, in_path, out_path), file=sys.stderr)
