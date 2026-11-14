#!/usr/bin/env python3
"""Per cell result of a fixed library: DRC markers (from check_cells.py run dir,
context rules dropped) and LVS status, joined with fix_report.json.

Usage: python3 classify.py <fix_report.json> <check_cells run dir> [out.json]
"""
import collections
import json
import re
import sys
from pathlib import Path

TESTING = Path(__file__).resolve().parents[2] / 'icsprout55/libs.tech/klayout/tech/testing'
sys.path.insert(0, str(TESTING))
from summary import summarize          # noqa: E402
from lvs_summary import circuit_status  # noqa: E402

# found on every library cell without taps / outside a placed design
CONTEXT = re.compile(r'^(LU_S_2_.*|NW1_R_1|.*_D_\d+(_min|_max)?)$')


def main(report, run, out=None):
    rep = json.loads(Path(report).read_text())
    run = Path(run)
    drc = summarize(str(run / 'drc.lyrdb'), str(run / 'drc_wrap.gds'))
    per = collections.defaultdict(collections.Counter)
    for rule, cells in drc.items():
        if CONTEXT.match(rule):
            continue
        for c, n in cells.items():
            for name in c.split('|'):
                per[name][rule] += n
    lvs = circuit_status(str(run / 'lvs.lvsdb')) if (run / 'lvs.lvsdb').exists() else {}
    res = {}
    for name, r in rep.items():
        res[name] = {'fix': r['status'], 'grow': r['grow'], 'drc': dict(per.get(name, {})),
                     'lvs': lvs.get(name, 'n/a'), 'msg': r['msg']}
    cnt = collections.Counter()
    for name, r in res.items():
        clean = not r['drc'] and r['lvs'] in ('match', 'n/a')
        cnt[(r['fix'], 'clean' if clean else ('lvs ' + r['lvs'] if r['lvs'] not in ('match', 'n/a') else 'drc'))] += 1
    for k, v in sorted(cnt.items()):
        print(f'{v:5d}  fix {k[0]:6s} {k[1]}')
    rules = collections.Counter()
    for name, r in res.items():
        if r['fix'] == 'ok':
            for rule, n in r['drc'].items():
                rules[rule] += 1
    print('rules in legalized cells (cells):', ', '.join(f'{k}:{v}' for k, v in rules.most_common()))
    if out:
        Path(out).write_text(json.dumps(res, indent=1, sort_keys=True))
    return res


if __name__ == '__main__':
    main(*sys.argv[1:])
