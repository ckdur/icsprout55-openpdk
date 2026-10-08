#!/usr/bin/env python3
"""ICS55 KLayout DRC and LVS regression on the PDK standard cells and IO library.

DRC testcases run tech/ics55.drc and compare the markers per rule and per
cell against golden/<testcase>.json.
LVS testcases run tech/ics55.lvs and compare the match status per cell.

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

from lvs_summary import circuit_status
from lvs_wrap import main as lvs_wrap
from lvs_wrap import subckt_pins
from summary import summarize
from wrap_lib import wrap

import klayout.db as db

TESTING_DIR = Path(__file__).resolve().parent
TECH_DIR = TESTING_DIR.parent
DRC_DECK = TECH_DIR / 'ics55.drc'
LVS_DECK = TECH_DIR / 'ics55.lvs'
LIBS_REF = TESTING_DIR.parents[3] / 'libs.ref'
GOLDEN_DIR = TESTING_DIR / 'golden'

STDCELL_GDS = 'ics55_LLSC_H7C{v}/gds/ics55_LLSC_H7C{v}{suffix}.gds'
STDCELL_CDL = 'ics55_LLSC_H7C{v}/cdl/ics55_LLSC_H7C{v}.cdl'
IO_GDS = 'ICsprout_55LLULP1233_IO_251013/gds/ICSIOA_N55_3P3_1P6M1TM.gds'
IO_CDL = 'ICsprout_55LLULP1233_IO_251013/cdl/ICSIOA_N55_3P3.cdl'

# IO supply rails are split inside a standalone IO cell and connect through the ring
IO_IMPLICIT_NETS = 'VDDIO VSSIO VDD VSS'

# DRC: name -> (gds, filler cell to abut with or None, wrap in "ALL" top)
# LVS: name -> (gds, cdl, mode) with mode 'library' (all cells under "ALL") or 'per_cell'
TESTCASES = {
    'drc_stdcell_H7CR': ('drc', STDCELL_GDS.format(v='R', suffix=''), 'FILLER4H7R', True),
    'drc_stdcell_H7CH': ('drc', STDCELL_GDS.format(v='H', suffix=''), 'FILLER4H7H', True),
    'drc_stdcell_H7CL': ('drc', STDCELL_GDS.format(v='L', suffix=''), 'FILLER4H7L', True),
    'drc_stdcell_H7CR_M2': ('drc', STDCELL_GDS.format(v='R', suffix='_M2'), 'FILLER4H7R', True),
    'drc_io': ('drc', IO_GDS, None, False),
    'lvs_stdcell_H7CR': ('lvs', STDCELL_GDS.format(v='R', suffix=''), STDCELL_CDL.format(v='R'), 'library'),
    'lvs_stdcell_H7CH': ('lvs', STDCELL_GDS.format(v='H', suffix=''), STDCELL_CDL.format(v='H'), 'library'),
    'lvs_stdcell_H7CL': ('lvs', STDCELL_GDS.format(v='L', suffix=''), STDCELL_CDL.format(v='L'), 'library'),
    # The _M2 layouts (MET2 pins, matching the _ecos LEF) are the ones used by the LibreLane flow
    'lvs_stdcell_H7CR_M2': ('lvs', STDCELL_GDS.format(v='R', suffix='_M2'), STDCELL_CDL.format(v='R'), 'library'),
    'lvs_stdcell_H7CH_M2': ('lvs', STDCELL_GDS.format(v='H', suffix='_M2'), STDCELL_CDL.format(v='H'), 'library'),
    'lvs_stdcell_H7CL_M2': ('lvs', STDCELL_GDS.format(v='L', suffix='_M2'), STDCELL_CDL.format(v='L'), 'library'),
    'lvs_io': ('lvs', IO_GDS, IO_CDL, 'per_cell'),
}


def run_klayout(cmd):
    subprocess.run(['klayout', '-b'] + cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


#---------------- DRC ----------------

def run_drc(name, run_dir):
    _, gds_rel, filler, wrapped = TESTCASES[name]
    gds = LIBS_REF / gds_rel
    cmd = ['-r', str(DRC_DECK)]
    if wrapped:
        wrapper = run_dir / f'{name}.gds'
        wrap(str(gds), str(wrapper), filler)
        cmd += ['-rd', f'input={wrapper}', '-rd', 'topcell=ALL']
    else:
        cmd += ['-rd', f'input={gds}']
    report = run_dir / f'{name}.lyrdb'
    cmd += ['-rd', f'report={report}', '-rd', f'log={run_dir / f"{name}.log"}']
    print(f'[{name}] running DRC')
    run_klayout(cmd)
    return {rule: {'count': sum(cells.values()), 'cells': dict(sorted(cells.items()))}
            for rule, cells in sorted(summarize(str(report)).items())}


def compare_drc(name, result, golden):
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


def drc_total(result):
    return f'{sum(r["count"] for r in result.values())} markers'


#---------------- LVS ----------------

def run_lvs(name, run_dir):
    """Return {cell: status} for every cell compared."""
    _, gds_rel, cdl_rel, mode = TESTCASES[name]
    gds, cdl = LIBS_REF / gds_rel, LIBS_REF / cdl_rel
    print(f'[{name}] running LVS')
    if mode == 'library':
        wrapper_gds, wrapper_cdl = run_dir / f'{name}.gds', run_dir / f'{name}.cdl'
        lvs_wrap(str(gds), str(cdl), str(wrapper_gds), str(wrapper_cdl))
        report = run_dir / f'{name}.lvsdb'
        run_klayout(['-r', str(LVS_DECK), '-rd', f'input={wrapper_gds}', '-rd', 'topcell=ALL',
                     '-rd', f'schematic={wrapper_cdl}', '-rd', f'report={report}',
                     '-rd', f'log={run_dir / f"{name}.log"}', '-rd', 'tapless=true'])
        return {c: st for c, st in circuit_status(str(report)).items() if c != 'ALL'}

    # One LVS run per cell that has a schematic
    layout = db.Layout()
    layout.read(str(gds))
    sch = subckt_pins(str(cdl))
    cells = sorted(c.name for c in layout.each_cell() if c.name.upper() in sch)
    cell_dir = run_dir / name
    cell_dir.mkdir(exist_ok=True)
    result = {}
    for cell in cells:
        report = cell_dir / f'{cell}.lvsdb'
        run_klayout(['-r', str(LVS_DECK), '-rd', f'input={gds}', '-rd', f'topcell={cell}',
                     '-rd', f'schematic={cdl}', '-rd', f'report={report}',
                     '-rd', f'target_netlist={cell_dir / f"{cell}.cir"}',
                     '-rd', f'log={cell_dir / f"{cell}.log"}', '-rd', f'implicit_nets={IO_IMPLICIT_NETS}'])
        status = circuit_status(str(report)).get(cell)
        if status is None:
            # Cells without devices (IO corner / spacers) are simplified away on
            # both sides; the overall verdict is in the log
            log = (cell_dir / f'{cell}.log').read_text()
            status = 'match' if 'Netlists match' in log else 'none'
        result[cell] = status
    return result


def lvs_golden(status):
    """Golden format: number of matching cells and the status of the others."""
    return {'match': sum(st == 'match' for st in status.values()),
            'not_matching': {c: st for c, st in sorted(status.items()) if st != 'match'}}


def compare_lvs(name, result, golden):
    ok = result == golden
    if result['match'] != golden['match']:
        print(f'[{name}] matching cells: {golden["match"]} -> {result["match"]}')
    got, exp = result['not_matching'], golden['not_matching']
    for cell in sorted(set(got) | set(exp)):
        if got.get(cell) != exp.get(cell):
            print(f'    {cell}: {exp.get(cell, "match")} -> {got.get(cell, "match")}')
    return ok


def lvs_total(result):
    return f'{result["match"]} cells match, {len(result["not_matching"])} do not'


#---------------- main ----------------

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
        if TESTCASES[name][0] == 'drc':
            result = run_drc(name, run_dir)
            compare, total = compare_drc, drc_total
        else:
            result = lvs_golden(run_lvs(name, run_dir))
            compare, total = compare_lvs, lvs_total
        golden_file = GOLDEN_DIR / f'{name}.json'
        if args.update:
            golden_file.write_text(json.dumps(result, indent=1) + '\n')
            print(f'[{name}] {total(result)}, golden updated')
        elif not golden_file.exists():
            print(f'[{name}] no golden file, run with --update')
            failed.append(name)
        elif compare(name, result, json.loads(golden_file.read_text())):
            print(f'[{name}] PASS ({total(result)}, matches golden)')
        else:
            print(f'[{name}] FAIL (differs from golden)')
            failed.append(name)

    if failed:
        print(f'Failed: {", ".join(failed)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
