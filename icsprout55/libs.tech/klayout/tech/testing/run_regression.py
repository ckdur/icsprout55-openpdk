#!/usr/bin/env python3
"""ICS55 KLayout DRC regression on the PDK standard cells and IO library.

Runs tech/ics55.drc on each testcase and compares the markers per rule and
per cell against golden/<testcase>.json.

Usage:
  python3 run_regression.py [--tests T1,T2] [--run-dir DIR] [--update]

  --tests    Comma separated subset of testcases (default: all)
  --run-dir  Where wrapper GDS, reports and logs go (default: testing/run)
  --update   Overwrite the golden files with the current results

Exit code is 1 if any testcase differs from its golden file.
Needs `klayout` in PATH and the `klayout` python module.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from summary import summarize
from wrap_lib import wrap

TESTING_DIR = Path(__file__).resolve().parent
TECH_DIR = TESTING_DIR.parent
DRC_DECK = TECH_DIR / 'ics55.drc'
LIBS_REF = TESTING_DIR.parents[3] / 'libs.ref'
GOLDEN_DIR = TESTING_DIR / 'golden'

STDCELL = 'ics55_LLSC_H7C{v}/gds/ics55_LLSC_H7C{v}{suffix}.gds'

# name -> (gds relative to libs.ref, filler cell to abut with or None, wrap in "ALL" top)
TESTCASES = {
    'stdcell_H7CR': (STDCELL.format(v='R', suffix=''), 'FILLER4H7R', True),
    'stdcell_H7CH': (STDCELL.format(v='H', suffix=''), 'FILLER4H7H', True),
    'stdcell_H7CL': (STDCELL.format(v='L', suffix=''), 'FILLER4H7L', True),
    'stdcell_H7CR_M2': (STDCELL.format(v='R', suffix='_M2'), 'FILLER4H7R', True),
    'io': ('ICsprout_55LLULP1233_IO_251013/gds/ICSIOA_N55_3P3_1P6M1TM.gds', None, False),
}


def run_testcase(name, run_dir):
    gds_rel, filler, wrapped = TESTCASES[name]
    gds = LIBS_REF / gds_rel
    cmd = ['klayout', '-b', '-r', str(DRC_DECK)]
    if wrapped:
        wrapper = run_dir / f'{name}.gds'
        wrap(str(gds), str(wrapper), filler)
        cmd += ['-rd', f'input={wrapper}', '-rd', 'topcell=ALL']
    else:
        cmd += ['-rd', f'input={gds}']
    report = run_dir / f'{name}.lyrdb'
    log = run_dir / f'{name}.log'
    cmd += ['-rd', f'report={report}', '-rd', f'log={log}']
    print(f'[{name}] running DRC')
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return {rule: {'count': sum(cells.values()), 'cells': dict(sorted(cells.items()))}
            for rule, cells in sorted(summarize(str(report)).items())}


def compare(name, result, golden):
    """Print the differences and return True if result matches golden."""
    ok = True
    for rule in sorted(set(result) | set(golden)):
        got = result.get(rule, {'count': 0, 'cells': {}})
        exp = golden.get(rule, {'count': 0, 'cells': {}})
        if got == exp:
            continue
        ok = False
        print(f'[{name}] {rule}: {exp["count"]} -> {got["count"]} markers')
        for cell in sorted(set(got['cells']) | set(exp['cells'])):
            g, e = got['cells'].get(cell, 0), exp['cells'].get(cell, 0)
            if g != e:
                print(f'    {cell}: {e} -> {g}')
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tests', default=','.join(TESTCASES))
    parser.add_argument('--run-dir', default=str(TESTING_DIR / 'run'))
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in args.tests.split(','):
        if name not in TESTCASES:
            sys.exit(f'Unknown testcase {name}. Available: {", ".join(TESTCASES)}')
        result = run_testcase(name, run_dir)
        golden_file = GOLDEN_DIR / f'{name}.json'
        total = sum(r['count'] for r in result.values())
        if args.update:
            golden_file.write_text(json.dumps(result, indent=1) + '\n')
            print(f'[{name}] {total} markers, golden updated')
        elif not golden_file.exists():
            print(f'[{name}] no golden file, run with --update')
            failed.append(name)
        elif compare(name, result, json.loads(golden_file.read_text())):
            print(f'[{name}] PASS ({total} markers, matches golden)')
        else:
            print(f'[{name}] FAIL (differs from golden)')
            failed.append(name)

    if failed:
        print(f'Failed: {", ".join(failed)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
