#!/usr/bin/env python3
"""The dead-field census: every variable in the wrfout, over the whole sample.

    uv run python tools/audit/dead_fields.py scan --timestep 2024-07-15T12 --out f.json
    uv run python tools/audit/dead_fields.py aggregate --dir <census dir>

`CONTEXT.md` defines a dead field as one that is **identically zero on every
sampled timestep, whatever the physical reason**. Two words in that sentence
decide how this is written.

*Identically* means exactly zero, not small: the test is `max(abs(x)) == 0`, with
no tolerance. A field of 1e-30 is alive and badly scaled, which is a different
finding from a field that was never written to.

*Every sampled timestep* means the census cannot be run on a summer afternoon and
generalised, which is how the list in `CLAUDE.md` was built and why it is a
hypothesis here rather than an input. `ACSNOW` and the snow fields are the
obvious risk: a summer-only sample cannot tell a dead field from a seasonally
zero one, and January, February, November and December are in the sample
precisely so that it can.

So the census reports three states, and keeps the second strictly apart from the
first:

  dead              exactly zero at all 34 timesteps
  seasonally zero   exactly zero at some, non-zero at others -- the months named
  alive             non-zero everywhere

It runs over **all 200 variables**, not over the ones already suspected: a field
nobody looked at because nothing wanted it is exactly what an audit is for.
"""

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent.parent
WORK = Path(os.environ.get('WORK_DIR', '/leonardo_work/AIFPT_AILAMIT/CHAPTER'))
WRFOUT_DIR = WORK / 'wrfout_audit'
SAMPLE_MD = PROJECT / 'docs' / 'audit' / 'sample.md'

# What CLAUDE.md currently claims is dead. Carried here as the hypothesis under
# test, never as an input to the measurement.
CLAIMED_DEAD = [
    'ACHFX', 'ACLHF', 'ACGRDFLX', 'NOAHRES', 'SSTSK', 'SST_INPUT', 'SWNORM',
    'ACSNOW', 'HAILNC', 'RAINC', 'RAINSH', 'PREC_ACC_C', 'LWDNT', 'LWDNTC',
    'ACLWDNT', 'ACLWDNTC',
]


def sample_timesteps():
    out = []
    pattern = re.compile(r'^\|\s*(\d{4}-\d{2}-\d{2})T(\d{2})\s*\|')
    for line in SAMPLE_MD.read_text().splitlines():
        m = pattern.match(line)
        if m:
            out.append(f'{m.group(1)}T{m.group(2)}')
    return sorted(set(out))


def wrfout_path(timestep):
    date, hour = timestep.split('T')
    return WRFOUT_DIR / date / f'wrfout_d02_{date}_{hour}:00:00'


def scan(timestep):
    import netCDF4
    path = wrfout_path(timestep)
    result = {'timestep': timestep, 'file': path.name, 'variables': {}}
    with netCDF4.Dataset(path) as nc:
        for name, var in nc.variables.items():
            if var.dtype.kind in 'SU':          # Times
                continue
            data = np.ma.asarray(var[:])
            values = np.ma.filled(data, np.nan).astype(np.float64, copy=False)
            finite = np.isfinite(values)
            n_finite = int(finite.sum())
            entry = {
                'shape': list(var.shape),
                'units': getattr(var, 'units', ''),
                'description': getattr(var, 'description', '')[:120],
                'n': int(values.size),
                'n_finite': n_finite,
            }
            if n_finite == 0:
                entry.update({'absmax': None, 'all_zero': None,
                              'n_nonzero': 0, 'min': None, 'max': None})
            else:
                good = values[finite]
                absmax = float(np.abs(good).max())
                entry.update({
                    'absmax': absmax,
                    'all_zero': absmax == 0.0,
                    'n_nonzero': int((good != 0.0).sum()),
                    'min': float(good.min()), 'max': float(good.max()),
                    'mean': float(good.mean()),
                })
            result['variables'][name] = entry
            del values, data
    return result


def cmd_scan(args):
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result = scan(args.timestep)
    out.write_text(json.dumps(result))
    n = len(result['variables'])
    dead = sum(1 for v in result['variables'].values() if v.get('all_zero'))
    print(f'{args.timestep}: {n} variables, {dead} exactly zero -> {out}')
    return 0


def cmd_aggregate(args):
    files = sorted(Path(args.dir).glob('census_*.json'))
    expected = len(sample_timesteps())
    print(f'{len(files)} of {expected} timesteps present')
    if len(files) != expected:
        print('INCOMPLETE: the census is not over the whole sample',
              file=sys.stderr)
    scans = [json.loads(f.read_text()) for f in files]
    seen = collections.defaultdict(dict)
    for s in scans:
        for name, entry in s['variables'].items():
            seen[name][s['timestep']] = entry

    dead, seasonal, alive, never_finite = [], [], [], []
    for name in sorted(seen):
        per = seen[name]
        if len(per) != len(scans):
            print(f'  ! {name} is absent from {len(scans) - len(per)} timesteps',
                  file=sys.stderr)
        zero_at = sorted(t for t, e in per.items() if e.get('all_zero') is True)
        live_at = sorted(t for t, e in per.items() if e.get('all_zero') is False)
        if not zero_at and not live_at:
            never_finite.append(name)
        elif not live_at:
            dead.append(name)
        elif not zero_at:
            alive.append(name)
        else:
            seasonal.append((name, zero_at, live_at))

    seasonal_names = [item[0] for item in seasonal]
    print(f'\ndead ({len(dead)}): exactly zero at every sampled timestep')
    for name in dead:
        mark = '' if name in CLAIMED_DEAD else '   <-- NOT in the CLAUDE.md list'
        print(f'  {name}{mark}')
    print(f'\nseasonally zero ({len(seasonal_names)}): zero at some timesteps only')
    for name, zero_at, live_at in seasonal:
        mark = '   <-- CLAUDE.md calls this DEAD' if name in CLAIMED_DEAD else ''
        print(f'  {name}: zero at {len(zero_at)} of {len(scans)}{mark}')
        print(f'      zero:  {", ".join(zero_at)}')
        print(f'      alive: {", ".join(live_at)}')
    print(f'\nalive ({len(alive)})')
    print('  ' + ', '.join(alive))
    if never_finite:
        print(f'\nno finite value anywhere ({len(never_finite)}): '
              + ', '.join(never_finite))

    print('\n--- against the list CLAUDE.md carries ---')
    for name in CLAIMED_DEAD:
        if name not in seen:
            print(f'  {name}: NOT IN THE WRFOUT AT ALL')
        elif name in dead:
            print(f'  {name}: confirmed dead')
        elif name in seasonal_names:
            print(f'  {name}: **WRONG** -- seasonally zero, not dead')
        else:
            print(f'  {name}: **WRONG** -- alive')
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('scan')
    s.add_argument('--timestep', required=True)
    s.add_argument('--out', required=True)
    s.set_defaults(func=cmd_scan)
    a = sub.add_parser('aggregate')
    a.add_argument('--dir', default=str(WORK / 'audit_census'))
    a.set_defaults(func=cmd_aggregate)
    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
