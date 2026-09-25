#!/usr/bin/env python3
"""Family 5: the accumulation convention, tested hour by hour over whole days.

Family 4 verified the accumulation MACHINERY -- template 8, the 00Z reference,
exact zero at 00Z, the sidecar subtraction -- on thirteen radiation fields. What
this family owns is the part that machinery cannot settle: whether WRF's own
counters behave the way the convention assumes, and whether `10fg`'s different
time convention is encoded as claimed.

    source tools/eccodes_env.sh
    uv run python tools/audit/f5_water.py --out $WORK/CHAPTER/audit_rows/f5.json

THE SAMPLE IS NOT ENOUGH FOR THIS ONE, AND SAYING SO IS THE POINT. The audit
sample holds 00, 06, 12 and 18Z of one day: it cannot difference consecutive
hours, and the two central claims of this ticket are about consecutive hours --
that `PREC_ACC_NC` equals the hour-to-hour difference of `RAINNC`, and that
`WSPD10MAX` is RESET at every history write. Both days used here are sample
days, and both are on disk at full hourly resolution: 2024-07-15 in
`wrfout_share` (convective) and 2024-02-15 in `wrfout_rebuild` (snow).

  encoding   the GRIB keys of all seven, including whether `10fg` really
             carries reference time H-1 and typeOfStatisticalProcessing 2.
  daycycle   24 consecutive hours of each day: are the six accumulators
             monotone, is RAINC identically zero, does PREC_ACC_NC equal the
             difference of RAINNC, and is WSPD10MAX reset rather than monotone.
  partition  tp against sf + tirf, and what falls between them.
  gust       10fg against the instantaneous 10 m wind of the same file, and
             against the hourly envelope the 24 files allow.
  runoff     where sro, ssro and ro actually live, since leg C puts ssro at
             three parts in a thousand of ERA5's.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402

WORK = Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER')

TOKENS = ['tp', 'sf', 'tirf', 'ro', 'sro', 'ssro', '10fg']

# The two whole days on disk at hourly resolution. Both are sample days.
DAYS = {
    '2024-07-15': WORK / 'wrfout_share' / '2024-07-15',
    '2024-02-15': WORK / 'wrfout_rebuild' / '2024-02-15',
}

ACCUMULATORS = ['RAINNC', 'SNOWNC', 'GRAUPELNC', 'HAILNC', 'SFROFF', 'UDROFF',
                'RAINC', 'ACRUNOFF']

KEYS = ('paramId', 'units', 'name', 'typeOfLevel', 'level', 'stepType',
        'stepRange', 'startStep', 'endStep', 'dataDate', 'dataTime',
        'validityDate', 'validityTime', 'bitmapPresent',
        'productDefinitionTemplateNumber', 'typeOfStatisticalProcessing',
        'generatingProcessIdentifier', 'indicatorOfUnitForTimeRange',
        'lengthOfTimeRange')

SPREAD = ['2024-02-15T12', '2024-07-15T12', '2024-07-15T00', '2024-07-15T18']


def read_family(path, with_keys=False):
    out, keys = {}, {}
    want = set(TOKENS)
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s not in want or s in out:
                    continue
                out[s] = H._message_field(gid)
                if with_keys:
                    k = {}
                    for name in KEYS:
                        try:
                            k[name] = eccodes.codes_get(gid, name)
                        except Exception as exc:          # noqa: BLE001
                            k[name] = f'<{type(exc).__name__}>'
                    keys[s] = k
            finally:
                eccodes.codes_release(gid)
    return (out, keys) if with_keys else out


def _stats(a):
    a = np.asarray(a, dtype=float)
    return {'min': float(np.min(a)), 'max': float(np.max(a)),
            'mean': float(np.mean(a)), 'sum': float(np.sum(a)),
            'n_nonzero': int(np.count_nonzero(a))}


# ---------------------------------------------------------------------------

def m_encoding(steps):
    rows = []
    for ts in steps:
        _, keys = read_family(H.grib_path(ts), with_keys=True)
        rows.append({'timestep': ts, 'keys': keys})
    return rows


def m_daycycle(_steps):
    """24 consecutive hours: monotonicity, the bucket, and the gust reset."""
    from netCDF4 import Dataset
    rows = []
    for day, folder in DAYS.items():
        files = sorted(folder.glob(f'wrfout_d02_{day}_*'))
        prev = None
        per_hour = []
        worst_bucket = {'absmax': 0.0, 'hour': None, 'rel': None}
        drops = {n: {'n': 0, 'worst': 0.0} for n in ACCUMULATORS}
        gust_drops = 0
        gust_rises = 0
        for path in files:
            hour = int(path.name[-8:-6])
            nc = Dataset(path)
            cur = {n: np.asarray(nc.variables[n][0], dtype=np.float64)
                   for n in ACCUMULATORS}
            cur['PREC_ACC_NC'] = np.asarray(nc.variables['PREC_ACC_NC'][0],
                                            dtype=np.float64)
            cur['WSPD10MAX'] = np.asarray(nc.variables['WSPD10MAX'][0],
                                          dtype=np.float64)
            cur['WSPD10'] = np.hypot(
                np.asarray(nc.variables['U10'][0], dtype=np.float64),
                np.asarray(nc.variables['V10'][0], dtype=np.float64))
            nc.close()
            entry = {'hour': hour,
                     'RAINNC_mean': float(cur['RAINNC'].mean()),
                     'RAINC_max': float(cur['RAINC'].max()),
                     'HAILNC_max': float(cur['HAILNC'].max()),
                     'PREC_ACC_NC_sum': float(cur['PREC_ACC_NC'].sum()),
                     'WSPD10MAX_mean': float(cur['WSPD10MAX'].mean()),
                     'WSPD10MAX_ge_instant': int(np.sum(
                         cur['WSPD10MAX'] >= cur['WSPD10'] - 1e-5)),
                     'ACRUNOFF_equals_SFROFF': bool(np.allclose(
                         cur['ACRUNOFF'], cur['SFROFF'], atol=1e-6))}
            if prev is not None:
                # the bucket: PREC_ACC_NC(H) must equal RAINNC(H) - RAINNC(H-1)
                dif = cur['RAINNC'] - prev['RAINNC']
                err = np.abs(cur['PREC_ACC_NC'] - dif)
                entry['bucket_absmax'] = float(err.max())
                entry['bucket_mean_abs'] = float(err.mean())
                entry['bucket_n_gt_1e_4'] = int(np.sum(err > 1e-4))
                if err.max() > worst_bucket['absmax']:
                    worst_bucket = {'absmax': float(err.max()), 'hour': hour,
                                    'rel': float(err.max() /
                                                 max(dif.max(), 1e-12))}
                for n in ACCUMULATORS:
                    d = cur[n] - prev[n]
                    neg = d < -1e-6
                    if neg.any():
                        drops[n]['n'] += int(neg.sum())
                        drops[n]['worst'] = min(drops[n]['worst'],
                                                float(d.min()))
                g = cur['WSPD10MAX'] - prev['WSPD10MAX']
                gust_drops += int(np.sum(g < -1e-3))
                gust_rises += int(np.sum(g > 1e-3))
                entry['gust_n_below_previous'] = int(np.sum(g < -1e-3))
            per_hour.append(entry)
            prev = cur
        rows.append({
            'day': day, 'n_files': len(files), 'hours': per_hour,
            'worst_bucket': worst_bucket,
            'accumulator_drops': drops,
            'gust_points_below_previous_hour': gust_drops,
            'gust_points_above_previous_hour': gust_rises,
        })
    return rows


def m_partition(steps):
    """tp against its two published pieces, and what sits between them."""
    from netCDF4 import Dataset
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        if 'tp' not in got:
            continue
        # tirf is kg/m2 (= mm), tp and sf are metres.
        tp_mm = got['tp'] * 1000.0
        sf_mm = got['sf'] * 1000.0
        residual = tp_mm - sf_mm - got['tirf']
        nc = Dataset(H.wrfout_path(ts))
        raw = {n: np.asarray(nc.variables[n][0], dtype=np.float64)
               for n in ('RAINNC', 'SNOWNC', 'GRAUPELNC')}
        nc.close()
        rows.append({
            'timestep': ts,
            'tp_mm': _stats(tp_mm), 'sf_mm': _stats(sf_mm),
            'tirf': _stats(got['tirf']),
            'residual_tp_minus_sf_minus_tirf': _stats(residual),
            'n_residual_gt_1e_3': int(np.sum(np.abs(residual) > 1e-3)),
            'n_residual_negative': int(np.sum(residual < -1e-3)),
            # the clip in tirf: RAINNC - SNOWNC - GRAUPELNC below zero
            'raw_rain_negative_points': int(np.sum(
                raw['RAINNC'] - raw['SNOWNC'] - raw['GRAUPELNC'] < -1e-6)),
            'raw_rain_worst_negative': float(np.min(
                raw['RAINNC'] - raw['SNOWNC'] - raw['GRAUPELNC'])),
        })
    return rows


def m_gust(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        from netCDF4 import Dataset
        nc = Dataset(H.wrfout_path(ts))
        inst = np.hypot(np.asarray(nc.variables['U10'][0], dtype=np.float64),
                        np.asarray(nc.variables['V10'][0], dtype=np.float64))
        nc.close()
        g = got['10fg']
        rows.append({
            'timestep': ts,
            'gust': _stats(g), 'instantaneous': _stats(inst),
            'n_gust_below_instant': int(np.sum(g < inst - 1e-4)),
            'worst_gust_below_instant': float(np.max(inst - g)),
            'ratio_of_means': float(g.mean() / inst.mean()),
            'mean_excess': float((g - inst).mean()),
        })
    return rows


def m_runoff(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        land = H.read_grib(H.grib_path(ts), 'lsm')['values'] > 0.5
        e = {'timestep': ts}
        for k in ('sro', 'ssro', 'ro'):
            v = got[k]
            e[k] = {'all': _stats(v), 'land': _stats(v[land]),
                    'sea_nonzero': int(np.count_nonzero(v[~land]))}
        e['ro_minus_sum_absmax'] = float(np.max(np.abs(
            got['ro'] - got['sro'] - got['ssro'])))
        e['ssro_share_of_ro'] = float(got['ssro'].sum() /
                                      max(got['ro'].sum(), 1e-30))
        rows.append(e)
    return rows



def m_controls(steps):
    """Leg C against the RIGHT ERA5 counterpart, which is not always the obvious one.

    The harness compares each shortName against the ERA5 field of the same
    name. For this family that is the wrong pairing three times over, and the
    controls to fix it were already retrieved with the audit set:

      CU_PHYSICS = 0, so every millimetre we produce is grid-scale. ERA5's `tp`
      carries convective precipitation we structurally cannot have, so the
      honest counterpart for our `tp` is ERA5's LARGE-SCALE precipitation
      `lsp`, and comparing against `tp` charges us for a process the run does
      not contain. Same for `sf` against `lsf`.

      `tirf` is rain only, and the harness has no ERA5 field for it at all.
      ERA5 carries no rain-only accumulation either -- but `lsp - lsf` IS one,
      exactly: large-scale precipitation minus its frozen part.

      `10fg` is the hourly maximum of the RESOLVED wind; ERA5's `10fg` is a
      gust PARAMETERISATION and `i10fg` its instantaneous form. Neither is the
      same quantity; reporting both brackets the difference instead of hiding
      it behind one ratio.
    """
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        ctx = H.Context(ts)
        if not ctx.era5_ok:
            rows.append({'timestep': ts, 'era5_ok': False})
            continue
        hour = int(ts.split('T')[1])
        cache = ctx.era5_messages('sl')

        def era(short, h):
            for key, values in cache.items():
                if key[0] == short and key[2] == h * 100:
                    return values
            return None

        def accumulate(short):
            """ERA5 accumulates over the hour ending at validity; ours since 00Z."""
            if hour == 0:
                return None
            total = None
            for h in range(1, hour + 1):
                f = era(short, h)
                if f is None:
                    return None
                total = f.copy() if total is None else total + f
            return total

        def compare(ours, ref, name):
            if ref is None:
                return {'pair': name, 'available': False}
            up = ctx.upscale(ours)
            out = {'pair': name, 'available': True, 'regions': {}}
            for rname, mask in ctx.era5_regions().items():
                both = mask & np.isfinite(up) & np.isfinite(ref)
                a, b = up[both], ref[both]
                out['regions'][rname] = {
                    'n': int(both.sum()),
                    'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
                    'ratio_means': float(a.mean() / b.mean()) if b.mean() else None,
                    'bias': float((a - b).mean()),
                    'rmse': float(np.sqrt(((a - b) ** 2).mean())),
                    'corr': float(np.corrcoef(a, b)[0, 1])
                            if a.std() > 0 and b.std() > 0 else None,
                }
            return out

        entry = {'timestep': ts, 'era5_ok': True, 'pairs': []}
        lsp, lsf = accumulate('lsp'), accumulate('lsf')
        entry['pairs'].append(compare(got['tp'], accumulate('tp'), 'tp vs ERA5 tp'))
        entry['pairs'].append(compare(got['tp'], lsp, 'tp vs ERA5 lsp (large scale only)'))
        entry['pairs'].append(compare(got['sf'], accumulate('sf'), 'sf vs ERA5 sf'))
        entry['pairs'].append(compare(got['sf'], lsf, 'sf vs ERA5 lsf (large scale only)'))
        # tirf is kg/m2; lsp and lsf are metres of water.
        rain_only = None if (lsp is None or lsf is None) else (lsp - lsf) * 1000.0
        entry['pairs'].append(compare(got['tirf'], rain_only, 'tirf vs ERA5 lsp - lsf (large-scale rain)'))
        # The pairing that turns out to be the right one: at 3 km the run has
        # no cumulus scheme, so WRF's "grid scale" precipitation contains the
        # convection IFS parameterises. ERA5's TOTAL minus its TOTAL snowfall
        # is therefore the rain-only counterpart, not its large-scale part.
        era_tp, era_sf = accumulate('tp'), accumulate('sf')
        all_rain = None if (era_tp is None or era_sf is None) else (era_tp - era_sf) * 1000.0
        entry['pairs'].append(compare(got['tirf'], all_rain, 'tirf vs ERA5 tp - sf (all rain)'))
        entry['pairs'].append(compare(got['10fg'], era('10fg', hour), '10fg vs ERA5 10fg (gust scheme, hourly max)'))
        entry['pairs'].append(compare(got['10fg'], era('i10fg', hour), '10fg vs ERA5 i10fg (gust scheme, instantaneous)'))
        rows.append(entry)
    return rows



def m_marker(steps):
    """Is generatingProcessIdentifier=128 a marker, or the sample's default?

    `CLAUDE.md` and `fix_tp_accum.py` treat 128 as the flag that says an
    accumulation is referred to 00Z, against 127 for the old run-init archive.
    The converter sets it only for stepType 'accum' -- yet `10fg`, which is not
    'accum', carries 128 too. Either eccodes' GRIB2 sample already defaults to
    128, in which case the marker distinguishes nothing inside grib_v3, or
    something else sets it.
    """
    rows = []
    for ts in steps:
        counts = {}
        with open(H.grib_path(ts), 'rb') as fh:
            while True:
                gid = eccodes.codes_grib_new_from_file(fh)
                if gid is None:
                    break
                try:
                    g = eccodes.codes_get(gid, 'generatingProcessIdentifier')
                    st = eccodes.codes_get(gid, 'stepType')
                    counts.setdefault((st, g), 0)
                    counts[(st, g)] += 1
                finally:
                    eccodes.codes_release(gid)
        sample = eccodes.codes_grib_new_from_samples('GRIB2')
        default = eccodes.codes_get(sample, 'generatingProcessIdentifier')
        eccodes.codes_release(sample)
        rows.append({'timestep': ts,
                     'by_steptype_and_genproc':
                         {f'{k[0]}/{k[1]}': v for k, v in sorted(counts.items())},
                     'eccodes_GRIB2_sample_default': default})
    return rows


def m_gustreset(_steps):
    """Four hours of 2024-07-15 show NO point below the previous hour. Why?"""
    from netCDF4 import Dataset
    folder = DAYS['2024-07-15']
    files = sorted(folder.glob('wrfout_d02_2024-07-15_*'))
    prev = None
    rows = []
    for path in files:
        hour = int(path.name[-8:-6])
        nc = Dataset(path)
        g = np.asarray(nc.variables['WSPD10MAX'][0], dtype=np.float64)
        w = np.hypot(np.asarray(nc.variables['U10'][0], dtype=np.float64),
                     np.asarray(nc.variables['V10'][0], dtype=np.float64))
        nc.close()
        e = {'hour': hour, 'mean': float(g.mean()), 'max': float(g.max()),
             'min': float(g.min()),
             'n_zero': int(np.sum(g == 0.0)),
             'n_equal_instant': int(np.sum(np.abs(g - w) < 1e-6)),
             'mean_instant': float(w.mean())}
        if prev is not None:
            d = g - prev
            e['n_below'] = int(np.sum(d < -1e-3))
            e['n_above'] = int(np.sum(d > 1e-3))
            e['n_equal'] = int(np.sum(np.abs(d) <= 1e-3))
            e['max_drop'] = float(d.min())
        rows.append(e)
        prev = g
    return rows



# Whole days on disk at hourly resolution, beyond the two sample days, used
# only to ask how often WSPD10MAX misses its reset.
RESET_DAYS = {
    '2024-07-15': WORK / 'wrfout_share' / '2024-07-15',
    '2024-02-15': WORK / 'wrfout_rebuild' / '2024-02-15',
    '2024-03-20': WORK / 'wrfout_2024fill' / '2024-03-20',
    '2019-07-15': WORK / 'wrfout_share' / '2019-07-15',
    '2024-08-15': WORK / 'wrfout_share' / '2024-08-15',
    '2024-02-01': WORK / 'wrfout_rebuild' / '2024-02-01',
}


def m_resetcensus(_steps):
    """How often is WSPD10MAX NOT reset at the history write?

    A one-hour maximum over 2.2 million points must fall somewhere between two
    hours: the wind cannot rise at every point of the domain. An hour with ZERO
    points below the previous hour, and a large population exactly equal to it,
    is an hour whose maximum was carried over -- the field is then a maximum
    over more than one hour while the GRIB says `0-1`.
    """
    from netCDF4 import Dataset
    rows = []
    for day, folder in RESET_DAYS.items():
        files = sorted(folder.glob(f'wrfout_d02_{day}_*'))
        if len(files) < 24:
            rows.append({'day': day, 'n_files': len(files), 'skipped': True})
            continue
        prev = None
        missed, ok = [], []
        detail = []
        for path in files:
            hour = int(path.name[-8:-6])
            nc = Dataset(path)
            g = np.asarray(nc.variables['WSPD10MAX'][0], dtype=np.float64)
            w = np.hypot(np.asarray(nc.variables['U10'][0], dtype=np.float64),
                         np.asarray(nc.variables['V10'][0], dtype=np.float64))
            nc.close()
            if prev is not None:
                d = g - prev
                below = int(np.sum(d < -1e-3))
                equal = int(np.sum(np.abs(d) <= 1e-3))
                carried = below == 0
                (missed if carried else ok).append(hour)
                detail.append({'hour': hour, 'n_below': below,
                               'n_equal_previous': equal,
                               'mean': float(g.mean()),
                               'mean_instant': float(w.mean()),
                               'excess_over_instant': float((g - w).mean()),
                               'carried_over': carried})
            prev = g
        rows.append({
            'day': day, 'n_files': len(files),
            'n_transitions': len(missed) + len(ok),
            'hours_not_reset': missed,
            'n_not_reset': len(missed),
            'mean_excess_reset_hours': float(np.mean(
                [x['excess_over_instant'] for x in detail if not x['carried_over']])),
            'mean_excess_carried_hours': float(np.mean(
                [x['excess_over_instant'] for x in detail if x['carried_over']]))
                if missed else None,
            'detail': detail,
        })
    return rows


MEASURES = {'encoding': m_encoding, 'daycycle': m_daycycle,
            'partition': m_partition, 'gust': m_gust, 'runoff': m_runoff,
            'controls': m_controls, 'marker': m_marker,
            'gustreset': m_gustreset, 'resetcensus': m_resetcensus}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--measure', action='append', choices=sorted(MEASURES))
    ap.add_argument('--timestep', action='append')
    ap.add_argument('--out')
    args = ap.parse_args()
    steps = args.timestep or SPREAD
    out = {}
    for name in args.measure or sorted(MEASURES):
        print(f'--- {name} ---', flush=True)
        out[name] = MEASURES[name](steps)
        print(json.dumps(out[name], indent=1)[:5000], flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))
        print(f'wrote {args.out}')


if __name__ == '__main__':
    main()
