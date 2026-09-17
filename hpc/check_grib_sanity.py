#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sanity check of CHAPTER GRIB2 files against partly-empty sources and schema drift.

Three independent failure modes are covered:

1. A wrfout that is partly zero-filled (truncated transfer, stub) still opens as
   NetCDF and converts "fine": 2024-12-29T18 came out with lsm, surface z, slor,
   skt, tcc and tp all zero. Static fields can never be all-zero over the domain,
   so they are the tell.
2. A field that raises inside the converter is reported and the run aborts, but a
   file produced by an older schema would pass unnoticed -- so the full set of
   (shortName -> number of messages) is compared against the registry.
3. tp must carry the 00Z marker (generatingProcessIdentifier 128, see
   accum_ref.py) and must be exactly zero in the 00Z file.

Usage (eccodes env as in hpc/convert_step.sh):
    python hpc/check_grib_sanity.py <grib> [<grib> ...]
    python hpc/check_grib_sanity.py --since-minutes 600 --month 2025-04
Exit code 1 if any file is BAD.
"""

import argparse
import collections
import glob
import os
import sys
import time

from eccodes import codes_get, codes_grib_new_from_file, codes_release

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrf_era5_comparison import WRF_TO_ECMWF_PARAMID  # noqa: E402

# How many messages each shortName must contribute ('z' appears both on the
# pressure levels and at the surface, hence the accumulation).
EXPECTED = collections.Counter()
for _info in WRF_TO_ECMWF_PARAMID.values():
    EXPECTED[_info['shortName']] += len(_info['levels'])

# Fields that are invariant in time and can never be all-zero over the domain.
# (Not snowc, tsn, fal or ci: those are legitimately empty out of season or at
# night. cvh/tvh/lai_hv cover ~20% of the land, which is never zero everywhere.)
STATIC = {'lsm', 'z', 'sdor', 'slor', 'skt', 'slt',
          'tvl', 'cvl', 'lai_lv', 'tvh', 'cvh', 'lai_hv', 'al'}
TP_MARK = 128


def check(path):
    problems = []
    found = collections.Counter()
    zero_static = set()
    tp_gp = tp_max = None
    with open(path, 'rb') as fh:
        while True:
            gid = codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                name = codes_get(gid, 'shortName')
                found[name] += 1
                if name in STATIC and codes_get(gid, 'maximum') == 0 and codes_get(gid, 'minimum') == 0:
                    zero_static.add(name)
                if codes_get(gid, 'paramId') == 228:
                    tp_gp, tp_max = codes_get(gid, 'generatingProcessIdentifier'), codes_get(gid, 'maximum')
            finally:
                codes_release(gid)

    for name in sorted(zero_static):
        problems.append(f"{name} all zero")
    for name in sorted(set(EXPECTED) | set(found)):
        want, got = EXPECTED[name], found[name]
        if want != got:
            problems.append(f"{name}: {got} messages, expected {want}")
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
    ap.add_argument('--grib-dir', default='/leonardo_work/AIFPT_AILAMIT/CHAPTER/grib_v2')
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
