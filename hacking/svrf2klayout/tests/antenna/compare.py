#!/usr/bin/env python3
"""Compare the KLayout antenna deck (kl.lyrdb) with Calibre (calibre_result.json from
run_calibre.py) on the antenna test vehicle, rule by rule and case by case.
Usage: compare.py [kl.lyrdb]"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
lyrdb = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'kl.lyrdb')
cases = json.load(open(os.path.join(HERE, 'cases.json')))
cal = json.load(open(os.path.join(HERE, 'calibre_result.json')))


def case_of(x):
    return min(cases, key=lambda c: abs(c['x'] - x))['name']


kl = {}
root = ET.parse(lyrdb).getroot()
for it in root.iter('item'):
    rule = it.find('category').text.strip("'\"")
    for v in it.iter('value'):
        nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', v.text or '')]
        if nums:
            xs = nums[0::2]
            kl.setdefault(rule, []).append(case_of(int(round(min(xs) * 1000))))
ok = True
for rule in sorted(set(cal) | set(kl)):
    a = sorted(cal.get(rule, []))
    b = sorted(kl.get(rule, []))
    same = a == b
    ok &= same
    print('%-16s %-4s calibre: %s | klayout: %s' % (rule, 'ok' if same else 'DIFF', ' '.join(a), ' '.join(b)))
print('all rules agree' if ok else 'differences')
sys.exit(0 if ok else 1)
