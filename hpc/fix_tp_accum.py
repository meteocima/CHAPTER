#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Refer tp in already-produced CHAPTER GRIBs to 00Z of the same day.

HISTORICAL TOOL. It applies to the old GRIB1 archive under `grib/` only; the
GRIB2 archive in `grib_v2/` is written with 00Z-referred accumulations from the
start, so nothing there ever needs this fix. Kept for the record and for any
leftover GRIB1 day (see logs/tp_accum_recovery_TODO.md).

GRIBs written before commit 1eaffb8 hold tp = RAINNC accumulated since run init
(18Z of the previous day). Since tp_grib(H) and tp_grib(00Z) share that origin,
    tp(H) = tp_grib(H) - tp_grib(00Z)
is pure GRIB arithmetic -- no wrfout needed.

Per day, in this order:
  1. reference = tp of the 00Z GRIB if not yet corrected, else the accum_ref sidecar;
     neither -> NO_REFERENCE, nothing touched
  2. the sidecar is written from the 00Z GRIB BEFORE any file is modified, so a crash
     never loses the reference (and later hole refills of that day find it too)
  3. hours 01..23, then 00Z LAST (it becomes zero): each file is rewritten to a
     temporary file message by message -- only tp is re-encoded, every other message
     is copied unchanged -- verified, fsync'ed and atomically renamed over the original.

Idempotent: a corrected tp message carries generatingProcessIdentifier=128
(accum_ref.ACCUM_FROM_00Z_GENPROC, also set by the converter); marked files are
skipped. Outcomes are appended to a ledger (FIXED / ALREADY_FIXED / NO_REFERENCE / ERROR).

Usage (eccodes env as in hpc/convert_step.sh):
    python hpc/fix_tp_accum.py --month 2025-06 [--dry-run]
    python hpc/fix_tp_accum.py --date 2025-06-15 [--dry-run]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime

import numpy as np
from eccodes import (codes_count_in_file, codes_get, codes_get_values,
                     codes_grib_new_from_file, codes_release, codes_set,
                     codes_set_values, codes_write)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import accum_ref  # noqa: E402

TP_PARAMID = 228
MARK = accum_ref.ACCUM_FROM_00Z_GENPROC
WORK_DIR = '/leonardo_work/AIFPT_AILAMIT/CHAPTER'
NAME_RE = re.compile(r'-(\d{8})(\d{2})\.grib$')
# 24-bit packing of a field of a few tenths of a metre quantises at ~1e-8 m; a
# difference more negative than this is not quantisation but a wrong reference.
NEG_TOL = 1e-6


def log(ledger, path, status, detail=''):
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    line = f"{ts} | {path} | {status} | {detail}"
    print(line, flush=True)
    if ledger:
        with open(ledger, 'a') as fh:
            fh.write(line + '\n')


def read_tp(path):
    """(values, generatingProcessIdentifier, (Nj, Ni)) of the tp message; raises if absent."""
    with open(path, 'rb') as fh:
        while True:
            gid = codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                if codes_get(gid, 'paramId') == TP_PARAMID:
                    return (codes_get_values(gid), codes_get(gid, 'generatingProcessIdentifier'),
                            (codes_get(gid, 'Nj'), codes_get(gid, 'Ni')))
            finally:
                codes_release(gid)
    raise ValueError(f"no tp (paramId {TP_PARAMID}) message in {path}")


def rewrite(path, ref_m):
    """Rewrite path with tp := tp - ref_m (ref_m=None -> zeros) and the marker.
    Returns (min_before_clip, mean_after)."""
    tmp = path + '.fixtmp'
    try:
        stats = _rewrite_to(path, tmp, ref_m)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return stats


def _rewrite_to(path, tmp, ref_m):
    n_in = n_tp = 0
    stats = None
    with open(path, 'rb') as fin, open(tmp, 'wb') as fout:
        while True:
            gid = codes_grib_new_from_file(fin)
            if gid is None:
                break
            n_in += 1
            try:
                if codes_get(gid, 'paramId') == TP_PARAMID:
                    n_tp += 1
                    if codes_get(gid, 'generatingProcessIdentifier') == MARK:
                        raise RuntimeError('tp already marked (concurrent fix?)')
                    vals = codes_get_values(gid)
                    new = np.zeros_like(vals) if ref_m is None else vals - ref_m
                    vmin = float(new.min())
                    if vmin < -NEG_TOL:
                        raise ValueError(f"tp - 00Z has min {vmin:.3e} m < -{NEG_TOL}: "
                                         f"reference does not match this file")
                    new = np.maximum(new, 0.0)
                    codes_set(gid, 'generatingProcessIdentifier', MARK)
                    codes_set_values(gid, new)
                    stats = (vmin, float(new.mean()))
                codes_write(gid, fout)  # untouched messages are written byte-identical
            finally:
                codes_release(gid)
        fout.flush()
        os.fsync(fout.fileno())
    if n_tp != 1:
        raise ValueError(f"expected 1 tp message, found {n_tp}")
    with open(tmp, 'rb') as fh:
        n_out = codes_count_in_file(fh)
    if n_out != n_in:
        raise ValueError(f"message count {n_out} != {n_in}")
    _, gp, _ = read_tp(tmp)
    if gp != MARK:
        raise ValueError('marker not written')
    shutil.copymode(path, tmp)
    os.replace(tmp, path)
    return stats


def fix_day(day, files, accum_ref_dir, ledger, dry_run):
    """files: {hour: path}. Returns a Counter-like dict of outcomes."""
    out = defaultdict(int)
    date = datetime.strptime(day, '%Y%m%d')
    sidecar = accum_ref.sidecar_path(accum_ref_dir, date)

    # Current state of every file (tp values are only kept for 00Z)
    marks = {}
    ref_m = None
    ref_src = None
    shape = None
    for h, p in sorted(files.items()):
        try:
            vals, gp, shape = read_tp(p)
        except Exception as e:  # noqa: BLE001
            log(ledger, p, 'ERROR', f"unreadable: {e}")
            out['ERROR'] += 1
            return out
        marks[h] = gp == MARK
        if h == 0 and not marks[h]:
            ref_m, ref_src = vals, p

    todo = [h for h in files if not marks[h]]
    for h in files:
        if marks[h]:
            log(ledger, files[h], 'ALREADY_FIXED')
            out['ALREADY_FIXED'] += 1
    if not todo:
        return out

    # Reference: unmarked 00Z GRIB, else the sidecar
    side = None
    if os.path.isfile(sidecar):
        side, _ = accum_ref.load_sidecar(sidecar)
        if 'RAINNC' not in side:
            side = None
    if ref_m is not None and side is not None:
        diff = float(np.abs(ref_m - side['RAINNC'].ravel().astype(np.float64) / 1000.0).max())
        if diff > NEG_TOL:
            for h in todo:
                log(ledger, files[h], 'ERROR', f"00Z GRIB and sidecar {sidecar} differ by {diff:.3e} m")
                out['ERROR'] += 1
            return out
    if ref_m is None and side is not None:
        ref_m = side['RAINNC'].ravel().astype(np.float64) / 1000.0
        ref_src = sidecar
    if ref_m is None:
        for h in todo:
            log(ledger, files[h], 'NO_REFERENCE',
                f"no unmarked 00Z GRIB and no sidecar {sidecar}; re-run the step pipeline on "
                f"{date:%Y-%m-%d}T00, then this fix")
            out['NO_REFERENCE'] += 1
        return out

    if dry_run:
        for h in sorted(todo):
            log(None, files[h], 'WOULD_FIX', f"ref={ref_src}")
            out['WOULD_FIX'] += 1
        return out

    # 2. persist the reference before touching anything
    if not os.path.isfile(sidecar):
        # Values are the WRF array flattened in C order (see the converter): store
        # them 2D, as a wrfout-sourced sidecar, so the converter can use either.
        accum_ref.write_sidecar(sidecar, {'RAINNC': (ref_m * 1000.0).reshape(shape)},
                            {'source': 'grib', 'source_path': ref_src,
                             'valid_time': f"{date:%Y-%m-%d}_00:00:00"})
        log(ledger, sidecar, 'REF_WRITTEN', f"from {ref_src}")

    # 3. hours 01..23 first, 00Z last. Zero 00Z only if the reference was validated
    # by at least one other hour of the day (fixed now or earlier) or there is no
    # other hour: a failing hour among good ones is a broken file (e.g. 2024-12-29T18,
    # a partly all-zero source), not a wrong reference. The sidecar keeps the
    # reference either way.
    failed = False
    validated = any(marks[h] for h in files if h != 0)
    for h in sorted(x for x in todo if x != 0) + ([0] if 0 in todo else []):
        if h == 0 and failed and not validated:
            log(ledger, files[h], 'ERROR', 'not zeroed: no other hour of this day matched the reference')
            out['ERROR'] += 1
            continue
        t0 = time.time()
        try:
            vmin, mean = rewrite(files[h], None if h == 0 else ref_m)
            log(ledger, files[h], 'FIXED',
                f"mean_tp={mean * 1000:.4f}mm min_raw={vmin:.2e}m {time.time() - t0:.1f}s")
            out['FIXED'] += 1
            validated = validated or h != 0
        except Exception as e:  # noqa: BLE001
            failed = True
            log(ledger, files[h], 'ERROR', str(e))
            out['ERROR'] += 1
    return out


def running_converts():
    try:
        res = subprocess.run(['squeue', '-h', '-u', os.environ.get('USER', ''), '-o', '%j'],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return [j for j in res.stdout.split() if j.startswith(('conv_', 'chapter_conv'))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--grib-dir', default=f'{WORK_DIR}/grib')
    ap.add_argument('--accum-ref-dir', default=f'{WORK_DIR}/accum_ref',
                    help='00Z accumulation sidecars. Defaults to the v1 tree ON PURPOSE: '
                         'this script repairs GRIBs under grib/, which were produced against '
                         'it. Everything current uses accum_ref_v2.')
    ap.add_argument('--ledger', default=f'{WORK_DIR}/logs/fix_tp_accum_status.log')
    ap.add_argument('--month', action='append', default=[], help='YYYY-MM (repeatable)')
    ap.add_argument('--date', action='append', default=[], help='YYYY-MM-DD (repeatable)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--ignore-running-converts', action='store_true')
    args = ap.parse_args()
    if not args.month and not args.date:
        ap.error('give --month and/or --date')

    if not args.dry_run and not args.ignore_running_converts:
        jobs = running_converts()
        if jobs:
            sys.exit(f"ERROR: convert jobs are queued/running ({len(jobs)}, e.g. {jobs[0]}); "
                     f"they write GRIBs concurrently. Wait, or pass --ignore-running-converts.")
        if jobs is None:
            print('WARN: squeue unavailable, cannot check for running converts', flush=True)

    months = set(args.month) | {d[:7] for d in args.date}
    wanted_days = {d.replace('-', '') for d in args.date}
    days = defaultdict(dict)
    for m in sorted(months):
        mdir = os.path.join(args.grib_dir, m[:4], m[5:7])
        if not os.path.isdir(mdir):
            print(f"WARN: {mdir} does not exist", flush=True)
            continue
        for name in os.listdir(mdir):
            mt = NAME_RE.search(name)
            if not mt:
                continue
            day, hour = mt.group(1), int(mt.group(2))
            if args.date and m not in args.month and day not in wanted_days:
                continue
            days[day][hour] = os.path.join(mdir, name)

    ledger = None if args.dry_run else args.ledger
    if ledger:
        os.makedirs(os.path.dirname(ledger), exist_ok=True)
    total = defaultdict(int)
    for day in sorted(days):
        res = fix_day(day, days[day], args.accum_ref_dir, ledger, args.dry_run)
        for k, v in res.items():
            total[k] += v
    print(f"\nSUMMARY {sorted(months)} days={len(days)} files={sum(len(f) for f in days.values())} "
          + ' '.join(f"{k}={v}" for k, v in sorted(total.items())), flush=True)
    sys.exit(1 if total.get('ERROR') else 0)


if __name__ == '__main__':
    main()
