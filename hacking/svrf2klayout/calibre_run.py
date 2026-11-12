#!/usr/bin/env python3
"""Helpers to run Calibre DRC and parse its ASCII results database."""

import os
import re
import subprocess
import tempfile


def parse_ascii_db(path):
    """Parse a Calibre ASCII DRC results database.

    Returns (precision, {rule: [result, ...]}) where each result is
    ('p', [(x,y),...]) for polygons or ('e', (x1,y1,x2,y2)) for edges
    (edge pairs appear as two consecutive edges with the same ordinal).
    Coordinates are in database units (integers).
    """
    res = {}
    with open(path, encoding='latin-1') as f:
        lines = f.read().split('\n')
    if not lines or not lines[0].strip():
        return 1000, res
    hdr = lines[0].split()
    prec = int(hdr[1]) if len(hdr) > 1 else 1000
    i = 1
    n = len(lines)
    while i < n:
        name = lines[i].strip()
        if not name:
            i += 1
            continue
        i += 1
        if i >= n:
            break
        cnts = lines[i].split()
        i += 1
        cur = int(cnts[0])
        nlines = int(cnts[2]) if len(cnts) > 2 else 0
        i += nlines  # skip rule text lines
        items = []
        for _ in range(cur):
            # skip optional property lines
            while i < n and not re.match(r'^[pe] \d+ \d+', lines[i]):
                i += 1
            if i >= n:
                break
            kind, _ord, cnt = lines[i].split()[:3]
            cnt = int(cnt)
            i += 1
            # cell/transform lines may follow ("CN ...")
            while i < n and lines[i].startswith('CN'):
                i += 1
            if kind == 'p':
                pts = []
                for k in range(cnt):
                    x, y = lines[i + k].split()[:2]
                    pts.append((int(x), int(y)))
                i += cnt
                items.append(('p', pts))
            else:
                eds = []
                for k in range(cnt):
                    v = [int(t) for t in lines[i + k].split()[:4]]
                    eds.append(tuple(v))
                i += cnt
                items.append(('e', eds))
        res[name] = items
    return prec, res


HEADER = '''LAYOUT PATH "{gds}"
LAYOUT PRIMARY "{top}"
LAYOUT SYSTEM GDSII
DRC RESULTS DATABASE "{db}" ASCII
DRC SUMMARY REPORT "{sum}"
DRC MAXIMUM RESULTS ALL
DRC MAXIMUM VERTEX ALL
PRECISION 1000
RESOLUTION 1
'''


def run_calibre(rules_text, gds, top, workdir=None, hier=False, timeout=3600, header=True):
    """Run calibre on the given rule text (body without LAYOUT directives) and
    return parsed results."""
    if workdir is None:
        workdir = tempfile.mkdtemp(prefix='cal_')
    workdir = os.path.abspath(workdir)
    os.makedirs(workdir, exist_ok=True)
    db = os.path.join(workdir, 'out.db')
    sm = os.path.join(workdir, 'out.sum')
    rf = os.path.join(workdir, 'rules.svrf')
    with open(rf, 'w') as f:
        if header:
            f.write(HEADER.format(gds=os.path.abspath(gds), top=top, db=db, sum=sm))
        f.write(rules_text)
    if os.path.exists(db):
        os.remove(db)
    cmd = 'source /usr/local/bin/616cad >/dev/null 2>&1; cd %s && calibre -drc %s %s' % (
        workdir, '-hier' if hier else '', rf)
    p = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True, timeout=timeout)
    log = p.stdout + p.stderr
    with open(os.path.join(workdir, 'calibre.log'), 'w') as f:
        f.write(log)
    if not os.path.exists(db):
        raise RuntimeError('calibre failed:\n' + '\n'.join(
            l for l in log.split('\n') if 'ERROR' in l or 'Error' in l)[:4000])
    return parse_ascii_db(db)
