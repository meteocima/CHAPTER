#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sanity check of CHAPTER GRIBs against partly-empty sources.

A wrfout that is partly zero-filled (truncated transfer, stub) still opens as
NetCDF and converts "fine": 2024-12-29T18 came out with lsm, surface z, slor,
skt, tcc and tp all zero. Static fields can never be all-zero over the domain,
so they are the tell. Also reports the tp marker (generatingProcessIdentifier
128 = referred to 00Z of the same day, see accum_ref.py) and that 00Z tp is zero.

Usage (eccodes env as in hpc/convert_step.sh):
    python hpc/check_grib_sanity.py <grib> [<grib> ...]
    python hpc/check_grib_sanity.py --since-minutes 600 --month 2025-04
Exit code 1 if any file is BAD.
"""

import argparse
import glob
import os
import sys
import time

from eccodes import codes_get, codes_grib_new_from_file, codes_release

# (shortName, typeOfLevel indicator, level) that must not be all zero
STATIC = {('lsm', 1, 0), ('z', 1, 0), ('sdor', 1, 0), ('slor', 1, 0), ('skt', 1, 0)}
TP_MARK = 128


def check(path):
    problems, seen = [], set()
    tp_gp = tp_max = None
    with open(path, 'rb') as fh:
        while True:
            gid = codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                key = (codes_get(gid, 'shortName'), codes_get(gid, 'indicatorOfTypeOfLevel', int),
                       codes_get(gid, 'level'))
                if key in STATIC:
                    seen.add(key)
                    if codes_get(gid, 'maximum') == 0 and codes_get(gid, 'minimum') == 0:
                        problems.append(f"{key[0]} all zero")
                if codes_get(gid, 'paramId') == 228:
                    tp_gp, tp_max = codes_get(gid, 'generatingProcessIdentifier'), codes_get(gid, 'maximum')
            finally:
                codes_release(gid)
    for key in sorted(STATIC - seen):
        problems.append(f"{key[0]} missing")
    if tp_gp is None:
        problems.append('tp missing')
    elif tp_gp != TP_MARK:
        problems.append(f"tp not referred to 00Z (genproc {tp_gp})")
    elif path.endswith('00.grib') and tp_max != 0:
        problems.append(f"00Z tp not zero (max {tp_max})")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*')
    ap.add_argument('--grib-dir', default='/leonardo_work/AIFPT_AILAMIT/CHAPTER/grib')
    ap.add_argument('--month', action='append', default=[], help='YYYY-MM (repeatable)')
    ap.add_argument('--since-minutes', type=float, default=None,
                    help='with --month: only files modified in the last N minutes')
    args = ap.parse_args()
    files = list(args.files)
    for m in args.month:
        for p in sorted(glob.glob(os.path.join(args.grib_dir, m[:4], m[5:7], '*.grib'))):
            if args.since_minutes is None or time.time() - os.path.getmtime(p) < args.since_minutes * 60:
                files.append(p)
    bad = 0
    for p in files:
        problems = check(p)
        print(f"{'BAD ' if problems else 'OK  '} {p}" + (f"  <- {'; '.join(problems)}" if problems else ''),
              flush=True)
        bad += bool(problems)
    print(f"\nchecked={len(files)} bad={bad}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
