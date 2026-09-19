#!/usr/bin/env python3
"""What actually came back from CDS, message by message.

    source tools/eccodes_env.sh
    uv run python tools/audit/era5_inventory.py <file.grib> [...]
    uv run python tools/audit/era5_inventory.py --convention <file.grib>

The crosswalk says what we asked for; this says what arrived. It exists because
the audit's whole method is that a claim needs a measurement, and "ERA5 carries
this parameter" is a claim about the bytes on disk, not about the request we
sent.

`--convention` answers the one question a comparison can silently get wrong:
our accumulated variables are referred to 00Z of the same day, ERA5's are
accumulated over some other interval, and the interval is read off the GRIB
keys rather than remembered.
"""

import argparse
import collections
import sys

import eccodes

KEYS = ('shortName', 'paramId', 'typeOfLevel', 'level', 'stepType',
        'stepRange', 'startStep', 'endStep', 'dataDate', 'dataTime',
        'validityDate', 'validityTime', 'Ni', 'Nj', 'gridType')


def messages(path):
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                return
            try:
                yield {k: _get(gid, k) for k in KEYS}
            finally:
                eccodes.codes_release(gid)


def _get(gid, key):
    try:
        return eccodes.codes_get(gid, key)
    except Exception:
        return None


def summarise(path):
    by_param = collections.OrderedDict()
    total = 0
    grids = set()
    for m in messages(path):
        total += 1
        grids.add((m['gridType'], m['Ni'], m['Nj']))
        rec = by_param.setdefault(
            m['shortName'],
            {'paramId': m['paramId'], 'levelType': m['typeOfLevel'],
             'levels': set(), 'stepType': set(), 'stepRange': set(),
             'times': set(), 'n': 0})
        rec['levels'].add(m['level'])
        rec['stepType'].add(m['stepType'])
        rec['stepRange'].add(m['stepRange'])
        rec['times'].add((m['validityDate'], m['validityTime']))
        rec['n'] += 1
    return total, grids, by_param


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--convention', action='store_true',
                    help='only the accumulated parameters, with their step ranges')
    args = ap.parse_args()

    for path in args.files:
        total, grids, by_param = summarise(path)
        print(f'=== {path}')
        print(f'    {total} messages, {len(by_param)} parameters, '
              f'grid {sorted(grids)}')
        for short, rec in by_param.items():
            accum = rec['stepType'] - {'instant'}
            if args.convention and not accum:
                continue
            levels = sorted(rec['levels'])
            steps = sorted(rec['stepRange'], key=lambda s: (len(s), s))
            print(f'    {short:<8} {rec["paramId"]:<8} {rec["levelType"]:<16} '
                  f'n={rec["n"]:<5} levels={levels if len(levels) <= 3 else f"{len(levels)} of {levels[0]}..{levels[-1]}"} '
                  f'stepType={sorted(rec["stepType"])} '
                  f'stepRange={steps if len(steps) <= 4 else f"{len(steps)}: {steps[0]}..{steps[-1]}"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
