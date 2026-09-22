#!/usr/bin/env python3
"""Family 7: the measurements the harness does not make.

The harness compares one timestep at a time, so it cannot see the one claim
this family rests on: that seven fields are INVARIANT across the archive and
two others move, and move only with the sea ice. It also cannot say whether a
class disagreement with ERA5 is scatter or a wrong row in the crosswalk -- for
that you need the joint distribution, not the agreement rate.

    source tools/eccodes_env.sh
    uv run python tools/audit/f7_static.py all --out $WORK/CHAPTER/audit_rows/f7.json

Four measurements:

  invariance  every family-7 message at all 34 sample timesteps, each compared
              against the first. Reports the points that ever change and the
              largest change. Claim A (static) is n_changed == 0; claim B
              (lsm/al move with sea ice) is n_changed > 0 AND every changed
              point carrying SEAICE > 0 in the wrfout of that timestep.
  geoem       the published field against geo_em ITSELF, not against the
              sidecar the converter read. Leg B compares the GRIB to that
              sidecar, so it can only catch the encoder; the crosswalk that
              built the sidecar -- the LANDUSEF sums, code table 4.234, the FAO
              thresholds -- is never under test until it is recomputed here
              from the source file.
  classes     the confusion matrix of tvl/tvh/slt against ERA5. A crosswalk row
              that is wrong shows up as one of our classes landing, in bulk, on
              one particular ERA5 class; resolution scatter does not.
  values      what dl, cl and sst actually hold: the distributions behind the
              counts CLAUDE.md quotes.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402

WORK = Path(os.environ.get('WORK_DIR', '/leonardo_work/AIFPT_AILAMIT/CHAPTER'))
GEO_EM = WORK / 'geo_em' / '2022123118' / 'WPS' / 'geo_em.d02.nc'

G = 9.80665

# The ticket's fifteen. Note that the harness's FAMILIES table puts sst and ci
# in family 8 while the two tickets put them here and family 8's ticket does
# not name them; the tickets partition the ninety, the table does not.
TOKENS = ['z_sfc', 'lsm', 'sdor', 'slor', 'cvl', 'cvh', 'tvl', 'tvh', 'slt',
          'cl', 'dl', 'al', 'fal', 'sst', 'ci']
SHORT = {'z_sfc': 'z', 'lsm': 'lsm', 'sdor': 'sdor', 'slor': 'slor',
         'cvl': 'cvl', 'cvh': 'cvh', 'tvl': 'tvl', 'tvh': 'tvh', 'slt': 'slt',
         'cl': 'cl', 'dl': 'dl', 'al': 'al', 'fal': 'fal', 'sst': 'sst',
         'ci': 'ci'}
STATIC_CLAIMED = ['cvl', 'cvh', 'tvl', 'tvh', 'slt', 'cl', 'dl']
MOVING_CLAIMED = ['lsm', 'al']


def read_family(path):
    """The fifteen messages in one pass. `z` is taken at level 0 only: the same
    shortName carries the thirteen pressure levels."""
    want = {SHORT[t] for t in TOKENS}
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                short = eccodes.codes_get(gid, 'shortName')
                level = eccodes.codes_get(gid, 'level')
                if short not in want or (short == 'z' and level != 0):
                    continue
                out[short] = {
                    'values': H._message_field(gid),
                    'paramId': eccodes.codes_get(gid, 'paramId'),
                    'units': eccodes.codes_get(gid, 'units'),
                    'typeOfLevel': eccodes.codes_get(gid, 'typeOfLevel'),
                    'level': level,
                    'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent')),
                }
            finally:
                eccodes.codes_release(gid)
    return out


def cmd_invariance(args):
    timesteps = H.sample_timesteps()
    ref, ever, result = {}, {}, {}
    per_step = {t: [] for t in TOKENS}
    for i, ts in enumerate(timesteps):
        path = H.grib_path(ts)
        if not path.exists():
            print(f'{ts}: no GRIB', file=sys.stderr)
            continue
        msgs = read_family(path)
        print(f'{ts}: {len(msgs)} messages', flush=True)
        for token in TOKENS:
            short = SHORT[token]
            if short not in msgs:
                print(f'  ! {token} absent at {ts}', file=sys.stderr)
                continue
            values = msgs[short]['values']
            finite = np.isfinite(values)
            per_step[token].append({
                'timestep': ts,
                'bitmap': msgs[short]['bitmap'],
                'n_missing': int((~finite).sum()),
                'min': float(np.nanmin(values)) if finite.any() else None,
                'max': float(np.nanmax(values)) if finite.any() else None,
                'mean': float(np.nanmean(values)) if finite.any() else None,
            })
            if token not in ref:
                ref[token] = values.copy()
                ever[token] = np.zeros(values.shape, dtype=bool)
                result[token] = {'reference': ts, 'paramId': msgs[short]['paramId'],
                                 'units': msgs[short]['units'],
                                 'typeOfLevel': msgs[short]['typeOfLevel'],
                                 'level': msgs[short]['level'],
                                 'max_abs_change': 0.0, 'changed_at': {}}
                continue
            base = ref[token]
            both = np.isfinite(base) & np.isfinite(values)
            mask_moved = np.isfinite(base) != np.isfinite(values)
            changed = np.zeros(values.shape, dtype=bool)
            changed[both] = base[both] != values[both]
            changed |= mask_moved
            ever[token] |= changed
            n = int(changed.sum())
            if n:
                delta = float(np.nanmax(np.abs(values[both] - base[both]))) \
                    if both.any() else float('nan')
                result[token]['max_abs_change'] = max(
                    result[token]['max_abs_change'], 0.0 if np.isnan(delta) else delta)
                result[token]['changed_at'][ts] = {
                    'n_changed': n,
                    'n_mask_moved': int(mask_moved.sum()),
                    'max_abs_diff': delta,
                }
        del msgs
    for token in TOKENS:
        if token in ever:
            result[token]['n_points_ever_changed'] = int(ever[token].sum())
            result[token]['n_timesteps_changed'] = len(result[token]['changed_at'])
        result.setdefault(token, {})['per_timestep'] = per_step[token]

    # Claim B: the points that move must be exactly the sea-ice points.
    seaice = {}
    for token in MOVING_CLAIMED:
        if token not in ever or not ever[token].any():
            continue
        checks = {}
        for ts in sorted(result[token]['changed_at']):
            if ts not in seaice:
                vals = H._read_wrfout_vars(ts, ['SEAICE'])['SEAICE'][0]
                seaice[ts] = None if vals is None else vals > 0.0
            ice = seaice[ts]
            if ice is None:
                checks[ts] = {'note': 'SEAICE absent from the wrfout'}
                continue
            msgs = read_family(H.grib_path(ts))
            values = msgs[SHORT[token]]['values']
            base = ref[token]
            both = np.isfinite(base) & np.isfinite(values)
            changed = np.zeros(values.shape, dtype=bool)
            changed[both] = base[both] != values[both]
            changed |= np.isfinite(base) != np.isfinite(values)
            checks[ts] = {
                'n_changed': int(changed.sum()),
                'n_seaice': int(ice.sum()),
                'n_changed_with_ice': int((changed & ice).sum()),
                'n_changed_without_ice': int((changed & ~ice).sum()),
                'n_ice_unchanged': int((ice & ~changed).sum()),
            }
            del msgs
        result[token]['sea_ice_check'] = checks
    # The reference timestep's own sea ice, so "unchanged" is read correctly.
    ref_ts = result['lsm']['reference']
    ice0 = H._read_wrfout_vars(ref_ts, ['SEAICE'])['SEAICE'][0]
    result['_reference_sea_ice'] = {
        'timestep': ref_ts,
        'n_points': None if ice0 is None else int((ice0 > 0).sum())}
    return result


def _geoem():
    import netCDF4
    with netCDF4.Dataset(GEO_EM) as nc:
        get = lambda n: np.asarray(nc.variables[n][0]).astype(np.float64)
        data = {n: get(n) for n in ('HGT_M', 'LANDMASK', 'VAR_SSO', 'LU_INDEX',
                                    'CLAYFRAC', 'SANDFRAC', 'SCT_DOM',
                                    'LAKE_DEPTH')}
        data['LANDUSEF'] = np.asarray(nc.variables['LANDUSEF'][0]).astype(np.float64)
    return data


def _recompute_static(geo):
    """The crosswalk, restated from geo_em and from the documented rules.

    This is not a copy of static_ref.py: it is written from the rule sentences
    (the IGBP high/low split, code table 4.234, the FAO thresholds) so that a
    disagreement points at either the code or the rule, and the sidecar is no
    longer taken on trust.
    """
    import static_ref as S
    luf = geo['LANDUSEF']                       # (class, y, x), fractions
    lu = np.rint(geo['LU_INDEX']).astype(int)
    land = geo['LANDMASK'] > 0.5
    idx = lambda classes: np.sum([luf[c - 1] for c in classes], axis=0)
    cvl = idx(S.VEG_LOW)
    cvh = idx(S.VEG_HIGH)
    # The dominant low / high class, over the classes of each group only.
    def dominant(classes):
        stack = np.stack([luf[c - 1] for c in classes])
        best = np.argmax(stack, axis=0)
        cover = np.max(stack, axis=0)
        code = np.array(classes)[best]
        return np.where(cover > 0, code, 0), cover
    low_class, low_cover = dominant(S.VEG_LOW)
    high_class, high_cover = dominant(S.VEG_HIGH)
    to4234 = np.zeros(22, dtype=float)
    for k, v in S.VEG_TYPE_4234.items():
        to4234[k] = v
    tvl = np.where(low_cover > 0, to4234[low_class], 0.0)
    tvh = np.where(high_cover > 0, to4234[high_class], 0.0)
    masked_low = np.isin(low_class, S.VEG_TVL_MASKED) & (low_cover > 0)
    tvl = np.where(masked_low, np.nan, tvl)
    clay = geo['CLAYFRAC'] * 100.0
    sand = geo['SANDFRAC'] * 100.0
    slt = np.full(clay.shape, np.nan)
    slt = np.where((clay < 18) & (sand > 65), 1.0, slt)
    slt = np.where(((clay >= 18) & (clay < 35) & (sand > 15)) |
                   ((clay < 18) & (sand > 15) & (sand <= 65)), 2.0, slt)
    slt = np.where((clay < 35) & (sand <= 15), 3.0, slt)
    slt = np.where((clay >= 35) & (clay < 60), 4.0, slt)
    slt = np.where(clay >= 60, 5.0, slt)
    slt = np.where(np.rint(geo['SCT_DOM']).astype(int) == S.SOILCAT_ORGANIC, 6.0, slt)
    slt = np.where(land, slt, np.nan)
    cl = luf[S.LAKE_CLASS - 1]
    dl = np.where(cl > 0, geo['LAKE_DEPTH'], np.nan)
    return {'cvl': cvl, 'cvh': cvh, 'tvl': tvl, 'tvh': tvh, 'slt': slt,
            'cl': cl, 'dl': dl, 'lu': lu, 'land': land}


def cmd_geoem(args):
    ts = args.timestep
    geo = _geoem()
    rc = _recompute_static(geo)
    msgs = read_family(H.grib_path(ts))
    wrf = H._read_wrfout_vars(ts, ['HGT', 'LANDMASK', 'VAR_SSO', 'SEAICE'])
    out = {'timestep': ts, 'geo_em': str(GEO_EM)}

    def cmp(name, ours, theirs, scale=1.0):
        theirs = theirs * scale
        both = np.isfinite(ours) & np.isfinite(theirs)
        d = np.abs(ours[both] - theirs[both]) if both.any() else np.array([0.0])
        return {
            'n_compared': int(both.sum()),
            'n_mask_disagree': int((np.isfinite(ours) != np.isfinite(theirs)).sum()),
            'max_abs_diff': float(d.max()),
            'rms_diff': float(np.sqrt((d ** 2).mean())),
            'n_differing': int((d > 0).sum()),
            'ours_range': [float(np.nanmin(ours)), float(np.nanmax(ours))],
            'theirs_range': [float(np.nanmin(theirs)), float(np.nanmax(theirs))],
        }

    out['z_sfc_vs_geoem_HGT_M'] = cmp('z', msgs['z']['values'], geo['HGT_M'], G)
    out['z_sfc_vs_wrfout_HGT'] = cmp('z', msgs['z']['values'], wrf['HGT'][0], G)
    out['lsm_vs_geoem_LANDMASK'] = cmp('lsm', msgs['lsm']['values'], geo['LANDMASK'])
    out['lsm_vs_wrfout_LANDMASK'] = cmp('lsm', msgs['lsm']['values'], wrf['LANDMASK'][0])
    out['sdor_vs_geoem_VAR_SSO'] = cmp('sdor', msgs['sdor']['values'],
                                       np.sqrt(np.maximum(geo['VAR_SSO'], 0)))
    out['sdor_vs_wrfout_VAR_SSO'] = cmp('sdor', msgs['sdor']['values'],
                                        np.sqrt(np.maximum(wrf['VAR_SSO'][0], 0)))
    for token in STATIC_CLAIMED:
        out[f'{token}_vs_geoem_recomputed'] = cmp(token, msgs[SHORT[token]]['values'],
                                                  rc[token])
    # slor: the published field is the RESOLVED gradient of the 3 km orography.
    # Recompute it here from the geo_em orography to see whether that is what it
    # is, and report the subgrid alternative the paramId actually names.
    dx = dy = 3000.0
    gy, gx = np.gradient(geo['HGT_M'], dy, dx)
    out['slor_vs_resolved_gradient'] = cmp('slor', msgs['slor']['values'],
                                           np.sqrt(gx ** 2 + gy ** 2))
    out['counts'] = {
        'land_points_grib': int((msgs['lsm']['values'] > 0.5).sum()),
        'land_points_geoem': int(rc['land'].sum()),
        'tvl_masked_grib': int((~np.isfinite(msgs['tvl']['values'])).sum()),
        'tvl_masked_recomputed': int((~np.isfinite(rc['tvl'])).sum()),
        'dl_present_grib': int(np.isfinite(msgs['dl']['values']).sum()),
        'dl_present_recomputed': int(np.isfinite(rc['dl']).sum()),
        'cl_positive_grib': int((msgs['cl']['values'] > 0).sum()),
        'cl_positive_on_land_grib': int(((msgs['cl']['values'] > 0) &
                                         (msgs['lsm']['values'] > 0.5)).sum()),
        'lake_class_cells_geoem': int((rc['lu'] == 21).sum()),
        'slt_masked_grib': int((~np.isfinite(msgs['slt']['values'])).sum()),
        'sst_masked_grib': int((~np.isfinite(msgs['sst']['values'])).sum()),
        'ci_masked_grib': int((~np.isfinite(msgs['ci']['values'])).sum()),
        'seaice_points_wrfout': int((wrf['SEAICE'][0] > 0).sum()),
    }
    # cvl+cvh must not exceed 1, and must be 0 off land.
    cvl, cvh = msgs['cvl']['values'], msgs['cvh']['values']
    land = msgs['lsm']['values'] > 0.5
    total = cvl + cvh
    out['vegetation'] = {
        'max_cvl_plus_cvh': float(np.nanmax(total)),
        'n_over_one': int((total > 1.0 + 1e-6).sum()),
        'n_nonzero_off_land': int(((total > 0) & ~land).sum()),
        'mean_total_on_land': float(np.nanmean(total[land])),
        'n_land_with_both_above_5pc': int(((cvl > 0.05) & (cvh > 0.05) & land).sum()),
    }
    return out


def cmd_values(args):
    """What dl, cl and sst actually hold, and whether sst moves within a run."""
    out = {}
    msgs = read_family(H.grib_path(args.timestep))
    dl = msgs['dl']['values']
    present = np.isfinite(dl)
    vals, counts = np.unique(np.round(dl[present], 3), return_counts=True)
    order = np.argsort(-counts)[:12]
    out['dl'] = {
        'timestep': args.timestep,
        'n_present': int(present.sum()),
        'min': float(dl[present].min()), 'max': float(dl[present].max()),
        'most_common': [[float(vals[i]), int(counts[i])] for i in order],
        'n_distinct': int(vals.size),
        'fraction_at_mode': float(counts.max() / counts.sum()),
    }
    cl = msgs['cl']['values']
    lsm = msgs['lsm']['values'] > 0.5
    out['cl'] = {
        'n_positive': int((cl > 0).sum()),
        'n_positive_on_land': int(((cl > 0) & lsm).sum()),
        'n_positive_on_sea': int(((cl > 0) & ~lsm).sum()),
        'n_equal_one': int((cl >= 0.999).sum()),
        'mean_where_positive': float(cl[cl > 0].mean()),
        'sum': float(cl.sum()),
    }
    # sst within one 24 h run: the diurnal day carries 00/06/12/18.
    day = [t for t in H.sample_timesteps() if t.startswith('2024-07-15')]
    ssts = {}
    base = None
    for ts in sorted(day):
        m = read_family(H.grib_path(ts))['sst']['values']
        if base is None:
            base = m
            ssts[ts] = {'n_missing': int((~np.isfinite(m)).sum()), 'max_abs_diff': 0.0}
            continue
        both = np.isfinite(base) & np.isfinite(m)
        ssts[ts] = {
            'n_missing': int((~np.isfinite(m)).sum()),
            'max_abs_diff': float(np.abs(m[both] - base[both]).max()),
            'n_changed': int((m[both] != base[both]).sum()),
            'n_mask_moved': int((np.isfinite(base) != np.isfinite(m)).sum()),
        }
    out['sst_within_run'] = {'day': '2024-07-15', 'timesteps': ssts}
    return out


def cmd_classes(args):
    """The joint distribution against ERA5, not just the agreement rate."""
    ts = args.timestep
    ctx = H.Context(ts)
    msgs = read_family(H.grib_path(ts))
    out = {'timestep': ts}
    for token in ('tvl', 'tvh', 'slt'):
        counterpart, why = H.era5_counterpart(token, ctx, level=None)
        if counterpart is None:
            out[token] = {'available': False, 'why': why}
            continue
        ours = ctx.upscale.mode(msgs[SHORT[token]]['values'])
        both = np.isfinite(ours) & np.isfinite(counterpart) & ctx.era_land
        a = np.rint(ours[both]).astype(int)
        b = np.rint(counterpart[both]).astype(int)
        matrix = {}
        for oc in np.unique(a):
            row = {}
            for ec, n in zip(*np.unique(b[a == oc], return_counts=True)):
                row[int(ec)] = int(n)
            matrix[int(oc)] = dict(sorted(row.items(), key=lambda kv: -kv[1]))
        out[token] = {
            'available': True,
            'n_cells': int(both.sum()),
            'agreement': float((a == b).mean()),
            'confusion_ours_to_era5': matrix,
        }
    # cl and the continuous statics, on the same cells, with the scatter that
    # the single correlation number hides.
    for token in ('cl', 'cvl', 'cvh', 'sdor', 'slor', 'z_sfc', 'fal'):
        counterpart, why = H.era5_counterpart(token, ctx, level=None)
        if counterpart is None:
            out[token] = {'available': False, 'why': why}
            continue
        ours = ctx.upscale(msgs[SHORT[token]]['values'])
        both = np.isfinite(ours) & np.isfinite(counterpart)
        a, b = ours[both], counterpart[both]
        entry = {'n': int(both.sum()),
                 'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
                 'corr': float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None}
        if token == 'cl':
            entry.update({
                'n_ours_positive': int((a > 0.01).sum()),
                'n_era5_positive': int((b > 0.01).sum()),
                'n_both_positive': int(((a > 0.01) & (b > 0.01)).sum()),
                'corr_where_either_positive': float(np.corrcoef(
                    a[(a > 0.01) | (b > 0.01)], b[(a > 0.01) | (b > 0.01)])[0, 1]),
                'ours_sum': float(a.sum()), 'era5_sum': float(b.sum()),
            })
        if token in ('sdor', 'slor'):
            nz = (a > 0) & (b > 0)
            entry.update({
                'ratio_of_medians': float(np.median(a[nz]) / np.median(b[nz])),
                'corr_log': float(np.corrcoef(np.log(a[nz]), np.log(b[nz]))[0, 1]),
                'ours_p99': float(np.percentile(a, 99)),
                'era5_p99': float(np.percentile(b, 99)),
            })
        out[token] = entry
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('invariance', 'geoem', 'classes', 'values', 'all'):
        p = sub.add_parser(name)
        p.add_argument('--timestep', default='2024-07-15T12')
        p.add_argument('--out', default=None)
    args = ap.parse_args()
    parts = (['geoem', 'classes', 'values', 'invariance'] if args.cmd == 'all'
             else [args.cmd])
    result = {}
    for part in parts:
        print(f'=== {part} ===', flush=True)
        result[part] = {'invariance': cmd_invariance, 'geoem': cmd_geoem,
                        'classes': cmd_classes, 'values': cmd_values}[part](args)
    text = json.dumps(result, indent=1, default=float)
    if args.out:
        Path(args.out).write_text(text)
        print(f'-> {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
