#!/usr/bin/env python3
"""Helpers to run KLayout (via docker) and parse lyrdb reports."""

import os
import subprocess
import xml.etree.ElementTree as ET

IMAGE = os.environ.get('KLAYOUT_IMAGE', 'factory.symbioticeda.com/asic-all:dev')
KLAYOUT_BIN = os.environ.get('KLAYOUT_BIN')  # native klayout if available


def klayout_cmd(args, cwd):
    if KLAYOUT_BIN:
        return [KLAYOUT_BIN] + args
    uid = os.getuid()
    home = os.path.expanduser('~')
    vols = ['-v', '%s:%s' % (home, home), '-v', '/etc/passwd:/etc/passwd:ro']
    if os.path.isdir('/tmp/claude-1000'):
        vols += ['-v', '/tmp/claude-1000:/tmp/claude-1000']
    return ['docker', 'run', '--rm', '-u', str(uid)] + vols + ['-w', cwd, IMAGE, 'klayout'] + args


def run_klayout(script, rd=None, cwd=None, timeout=7200):
    cwd = os.path.abspath(cwd or os.getcwd())
    args = ['-b', '-r', os.path.abspath(script)]
    for k, v in (rd or {}).items():
        args += ['-rd', '%s=%s' % (k, v)]
    p = subprocess.run(klayout_cmd(args, cwd), capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def _parse_values(txt, dbu):
    """parse lyrdb value strings into geometry tuples (in dbu)."""
    txt = txt.strip()
    def pts(s):
        out = []
        for pp in s.split(';'):
            pp = pp.strip()
            if not pp:
                continue
            x, y = pp.split(',')
            out.append((round(float(x) / dbu), round(float(y) / dbu)))
        return out
    if txt.startswith('polygon:'):
        body = txt[len('polygon:'):].strip().strip('()')
        # holes are separated by '/'
        hull = body.split('/')[0]
        return ('p', pts(hull))
    if txt.startswith('box:'):
        body = txt[len('box:'):].strip().strip('()')
        p = pts(body)
        (x1, y1), (x2, y2) = p
        return ('p', [(x1, y1), (x1, y2), (x2, y2), (x2, y1)])
    if txt.startswith('edge-pair:'):
        body = txt[len('edge-pair:'):].strip()
        # (x,y;x,y)|(x,y;x,y) or (..)/(..)
        sep = '|' if '|' in body else '/'
        a, b = body.split(sep)
        pa = pts(a.strip().strip('()'))
        pb = pts(b.strip().strip('()'))
        return ('ep', [(pa[0][0], pa[0][1], pa[1][0], pa[1][1]), (pb[0][0], pb[0][1], pb[1][0], pb[1][1])])
    if txt.startswith('edge:'):
        body = txt[len('edge:'):].strip().strip('()')
        p = pts(body)
        return ('e', [(p[0][0], p[0][1], p[1][0], p[1][1])])
    if txt.startswith('text:') or txt.startswith('label:'):
        return None
    return None


def parse_lyrdb(path, dbu=0.001):
    tree = ET.parse(path)
    root = tree.getroot()
    res = {}
    cats = []
    for c in root.iter('category'):
        n = c.find('name')
        if n is not None:
            cats.append(n.text)
    items = root.find('items')
    if items is None:
        return res
    for it in items.findall('item'):
        cat = it.find('category').text.strip("'")
        vals = it.find('values')
        geos = []
        if vals is not None:
            for v in vals.findall('value'):
                g = _parse_values(v.text or '', dbu)
                if g:
                    geos.append(g)
        res.setdefault(cat, []).extend(geos)
    for c in cats:
        res.setdefault(c.strip("'"), [])
    return res
