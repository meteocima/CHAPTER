#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cdsapi"]
# ///
"""Retrieve the ERA5 comparison set for the audit sample.

    ~/.local/bin/uv run --no-project tools/audit/fetch_era5.py [--dry-run] [--only sl|pl]

WHY IT IS NOT IN THE SHARED VENV. `cdsapi` is needed on a login node, by hand,
for one retrieval; nothing in the pipeline imports it. The shared `.venv` is
read by every compute node on every convert job, so a dependency that only a
human ever runs does not belong there. The PEP 723 block above declares it
instead, and `uv run --no-project` builds a throwaway environment from it --
the dependency is pinned in the file that uses it and reaches nothing else.

WHY ALL TWENTY-FOUR HOURS OF THE SINGLE LEVELS. ERA5's accumulated fields are
accumulated over the preceding hour; ours are accumulated since 00Z of the same
day. Comparing a 12Z value therefore means summing ERA5's hours 01..12, so the
whole day has to be on disk even though only two or four hours of it are sample
timesteps. The instantaneous fields ride along for free and give the diurnal
context at no extra request. The pressure levels are instantaneous throughout,
so only the sample hours are retrieved.

WHY 0.25 DEGREES AND THIS BOX. 0.25 deg is ERA5's own archived resolution: ask
for it explicitly and the server ships the archived field, ask for anything else
and it interpolates. The box is the CHAPTER domain rounded outward by a cell, so
that every WRF point has ERA5 neighbours on all sides and no comparison has to
extrapolate at the edge.

The sample dates are read from `docs/audit/sample.md`, which is the one place
the sample is written down; this script has no copy of the list to drift from.

Re-entrant: a target file that already exists and is a plausible size is left
alone, so the script can be re-run after a queue timeout or a stopped session.
"""

import argparse
import concurrent.futures
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import era5_crosswalk as X  # noqa: E402

SAMPLE_MD = PROJECT / 'docs' / 'audit' / 'sample.md'
WORK = Path(os.environ.get('WORK_DIR', '/leonardo_work/AIFPT_AILAMIT/CHAPTER'))
OUT = WORK / 'era5_audit'

# North, West, South, East. The CHAPTER domain is lat 23.47..60.00,
# lon -19.97..42.26; rounded outward to whole ERA5 cells.
AREA = [60.25, -20.25, 23.25, 42.50]
GRID = [0.25, 0.25]
PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

MIN_BYTES = 100_000          # anything smaller is a truncated or error payload
MAX_PARALLEL = 3             # CDS queues per user; three keeps us a polite client


def sample_timesteps():
    """(date, [hours]) for every date of the audit sample, from sample.md."""
    if not SAMPLE_MD.exists():
        sys.exit(f'{SAMPLE_MD} is missing: the sample list lives there, not here.')
    rows = {}
    pattern = re.compile(r'^\|\s*(\d{4}-\d{2}-\d{2})T(\d{2})\s*\|')
    for line in SAMPLE_MD.read_text().splitlines():
        m = pattern.match(line)
        if m:
            rows.setdefault(m.group(1), set()).add(m.group(2))
    if not rows:
        sys.exit(f'no timestep rows found in {SAMPLE_MD}')
    return [(d, sorted(rows[d])) for d in sorted(rows)]


def request_sl(date):
    year, month, day = date.split('-')
    variables = sorted(set(X.SL_CROSSWALK.values()) | set(X.SL_CONTROLS))
    return {
        'product_type': ['reanalysis'],
        'variable': variables,
        'year': [year], 'month': [month], 'day': [day],
        'time': [f'{h:02d}:00' for h in range(24)],
        'area': AREA, 'grid': GRID,
        'data_format': 'grib', 'download_format': 'unarchived',
    }


def request_pl(date, hours):
    year, month, day = date.split('-')
    return {
        'product_type': ['reanalysis'],
        'variable': sorted(set(X.PL_CROSSWALK.values())),
        'pressure_level': [str(p) for p in PRESSURE_LEVELS],
        'year': [year], 'month': [month], 'day': [day],
        'time': [f'{h}:00' for h in hours],
        'area': AREA, 'grid': GRID,
        'data_format': 'grib', 'download_format': 'unarchived',
    }


def target(kind, date):
    return OUT / kind / f'era5_{kind}_{date.replace("-", "")}.grib'


def already_there(path):
    return path.exists() and path.stat().st_size >= MIN_BYTES


def fetch_one(client, collection, request, path):
    tmp = path.with_suffix(f'.grib.{os.getpid()}.part')
    started = time.time()
    client.retrieve(collection, request, str(tmp))
    size = tmp.stat().st_size
    if size < MIN_BYTES:
        tmp.unlink()
        raise RuntimeError(f'{path.name}: server returned {size} bytes')
    tmp.rename(path)
    return path, size, time.time() - started


LOCK = OUT / '.fetch_era5.lock'


def take_lock():
    """Refuse to start beside another chain.

    Two instances would submit the same 32 requests and race on the same
    outputs -- the collision the fill2024 campaign taught this repo to design
    against. The lock is advisory and stale-tolerant: a lock whose pid is gone
    is taken over rather than being a reason to stop.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().split()[0])
        except (ValueError, IndexError):
            pid = None
        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                print(f'taking over a stale lock from pid {pid}')
            except PermissionError:
                sys.exit(f'{LOCK} is held by pid {pid} (another user); stopping.')
            else:
                sys.exit(f'another fetch is running as pid {pid} '
                         f'({LOCK}); stopping rather than racing it.')
    LOCK.write_text(f'{os.getpid()} {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}\n')


def drop_lock():
    try:
        if LOCK.exists() and LOCK.read_text().split()[0] == str(os.getpid()):
            LOCK.unlink()
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='print the requests and the plan, contact nothing')
    ap.add_argument('--only', choices=['sl', 'pl'], help='one product only')
    args = ap.parse_args()

    steps = sample_timesteps()
    print(f'audit sample: {len(steps)} dates, '
          f'{sum(len(h) for _, h in steps)} timesteps, from {SAMPLE_MD.name}')
    print(f'single level: {len(X.SL_CROSSWALK)} of our variables + '
          f'{len(X.SL_CONTROLS)} controls, all 24 hours of each date')
    print(f'pressure level: {len(X.PL_CROSSWALK)} variables x '
          f'{len(PRESSURE_LEVELS)} levels, sample hours only')
    print(f'not carried by ERA5: {len(X.NOT_IN_ERA5)} of our 90 '
          f'({", ".join(sorted(X.NOT_IN_ERA5))})')
    print(f'output: {OUT}')

    jobs = []
    for date, hours in steps:
        for kind, collection, request in (
            ('sl', X.COLLECTIONS['sl'], request_sl(date)),
            ('pl', X.COLLECTIONS['pl'], request_pl(date, hours)),
        ):
            if args.only and kind != args.only:
                continue
            path = target(kind, date)
            if already_there(path):
                print(f'  SKIP {path.name} ({path.stat().st_size / 1e6:.1f} MB)')
                continue
            jobs.append((collection, request, path))

    print(f'{len(jobs)} request(s) to make')
    if args.dry_run:
        for collection, request, path in jobs[:2]:
            print(f'--- {path.name} <- {collection}')
            for key, value in request.items():
                shown = value if not isinstance(value, list) or len(value) <= 6 \
                    else f'[{len(value)} items] {value[:3]} ...'
                print(f'      {key}: {shown}')
        print('(dry run: nothing contacted)')
        return 0
    if not jobs:
        print('nothing to do')
        return 0

    take_lock()
    for kind in ('sl', 'pl'):
        (OUT / kind).mkdir(parents=True, exist_ok=True)

    import cdsapi
    failures = []
    with concurrent.futures.ThreadPoolExecutor(MAX_PARALLEL) as pool:
        futures = {}
        for collection, request, path in jobs:
            client = cdsapi.Client(quiet=True, wait_until_complete=True)
            futures[pool.submit(fetch_one, client, collection, request, path)] = path
        done = 0
        for future in concurrent.futures.as_completed(futures):
            path = futures[future]
            done += 1
            try:
                _, size, elapsed = future.result()
                print(f'[{done}/{len(jobs)}] OK   {path.name} '
                      f'{size / 1e6:.1f} MB in {elapsed / 60:.1f} min', flush=True)
            except Exception as exc:  # noqa: BLE001 - the report is the point
                failures.append((path.name, exc))
                print(f'[{done}/{len(jobs)}] FAIL {path.name}: {exc}', flush=True)

    drop_lock()
    if failures:
        print(f'\n{len(failures)} request(s) failed; the script is re-entrant, '
              f're-run it to pick them up:')
        for name, exc in failures:
            print(f'  {name}: {exc}')
        return 1
    print('\nall requests satisfied')
    return 0


if __name__ == '__main__':
    sys.exit(main())
