#!/usr/bin/env python3
"""Family 1: what the harness cannot see about the thirteen pressure levels.

Leg B is unavailable for every one of them -- a pressure-level message is the
converter's vertical interpolation, not a field that exists to be read back --
so the harness carries legs A, C and D only. Five things it therefore cannot
settle, and each is measured here against the wrfout or against the converter's
own machinery:

  gravity     the published `z` is wrf-python's geopotential HEIGHT multiplied
              by 9.80665, and wrf-python divided WRF's own geopotential by 9.81
              to make it. Whether that round trip leaves the field short is the
              first thing to measure, because it would be a constant error on
              169 messages of every file in the archive.
  linearity   the algebra above only generalises if `wrf.vinterp` is linear in
              the field, so that is tested rather than assumed.
  moist       the size of the dry-to-moist correction on the hydrometeors, and
              the fact that `q` is normalised by a DIFFERENT denominator.
  below       what is written at 1000 and 925 hPa where the ground is above
              them; `extrapolate=True`, so it is a value and not a gap.
  clouds      the distribution of `cc`, which CLAUDE.md once called binary.
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

LEVELS = None      # filled from the registry


def read_levels(path, shorts):
    """Every pressure-level message of the wanted shortNames, by (short, level)."""
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                lev = eccodes.codes_get(gid, 'level')
                if s not in shorts or eccodes.codes_get(gid, 'typeOfLevel') != 'isobaricInhPa':
                    continue
                out[(s, lev)] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timestep', default='2024-07-15T12')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    import wrf
    import netCDF4
    from wrf import Constants
    import wrf_era5_comparison as REG
    global LEVELS
    LEVELS = list(REG.PRESSURE_LEVELS)

    ts = args.timestep
    out = {'timestep': ts, 'levels_hPa': LEVELS}
    nc = netCDF4.Dataset(H.wrfout_path(ts))

    # --- 1. the gravity round trip ----------------------------------------
    G_CONVERTER = 9.80665
    geopt = np.asarray(wrf.getvar(nc, 'geopt', timeidx=0).values, dtype=float)
    zm = np.asarray(wrf.getvar(nc, 'z', timeidx=0).values, dtype=float)
    ratio = geopt / np.where(zm == 0, np.nan, zm)
    out['gravity'] = {
        'wrf_python_Constants_G': float(Constants.G),
        'converter_G': G_CONVERTER,
        'geopt_over_z_median': float(np.nanmedian(ratio)),
        'geopt_over_z_min': float(np.nanmin(ratio)),
        'geopt_over_z_max': float(np.nanmax(ratio)),
        'implied_factor': G_CONVERTER / float(Constants.G),
        'implied_relative_error': G_CONVERTER / float(Constants.G) - 1.0,
    }

    # --- 2. is vinterp linear in the field? --------------------------------
    cache = wrf.extract_vars(nc, 0, ('P', 'PSFC', 'PB', 'PH', 'PHB', 'T', 'QVAPOR', 'HGT'))
    def to_levels(field):
        return wrf.vinterp(nc, field=field, vert_coord='pressure',
                           interp_levels=LEVELS, extrapolate=True,
                           timeidx=0, cache=cache).values
    one = to_levels(wrf.getvar(nc, 'z', timeidx=0, cache=cache))
    twice = to_levels(wrf.getvar(nc, 'z', timeidx=0, cache=cache) * 2.0)
    d = np.abs(twice - 2.0 * one)
    out['linearity'] = {
        'max_abs_diff_2f_vs_2xf': float(np.nanmax(d)),
        'max_rel': float(np.nanmax(d) / np.nanmax(np.abs(2.0 * one))),
    }

    # --- 3. the published z against both candidates ------------------------
    msgs = read_levels(H.grib_path(ts), {'z', 't', 'q', 'cc', 'w', 'wz', 'r'})
    z_from_height = one * G_CONVERTER                      # what the converter writes
    z_from_geopt = to_levels(wrf.getvar(nc, 'geopt', timeidx=0, cache=cache))
    per_level = {}
    for k, lev in enumerate(LEVELS):
        pub = msgs[('z', lev)]
        a = np.abs(pub - z_from_height[k])
        b = pub - z_from_geopt[k]
        per_level[lev] = {
            'published_vs_height_times_9_80665': float(np.nanmax(a)),
            'published_minus_geopt_mean_m2s2': float(np.nanmean(b)),
            'published_minus_geopt_mean_metres': float(np.nanmean(b) / G_CONVERTER),
            'relative': float(np.nanmean(b) / np.nanmean(np.abs(z_from_geopt[k]))),
            'geopt_mean': float(np.nanmean(z_from_geopt[k])),
        }
    out['z_check'] = per_level

    # --- 4. the moist correction, and q's different denominator ------------
    HYD = ('QVAPOR', 'QCLOUD', 'QRAIN', 'QICE', 'QSNOW', 'QGRAUP')
    rtot = sum(np.asarray(wrf.getvar(nc, n, timeidx=0, cache=cache).values, dtype=float)
               for n in HYD)
    rv = np.asarray(wrf.getvar(nc, 'QVAPOR', timeidx=0, cache=cache).values, dtype=float)
    corr = 1.0 / (1.0 + rtot)
    out['moist'] = {
        'correction_median_pc': float(100 * (1 - np.median(corr))),
        'correction_max_pc': float(100 * (1 - corr.min())),
        'correction_p99_pc': float(100 * (1 - np.percentile(corr, 1))),
        'condensate_fraction_of_total_median': float(
            np.median((rtot - rv) / np.maximum(rtot, 1e-30))),
        # q is written as rv/(1+rv); the hydrometeors as X/(1+rtot).
        'q_uses_denominator': '1 + QVAPOR only',
        'hydrometeors_use_denominator': '1 + all six mixing ratios',
        'q_relative_difference_between_the_two_median': float(np.median(
            (rv / (1 + rv) - rv / (1 + rtot)) / np.maximum(rv / (1 + rtot), 1e-30))),
        'q_relative_difference_between_the_two_max': float(np.nanmax(
            (rv / (1 + rv) - rv / (1 + rtot)) / np.maximum(rv / (1 + rtot), 1e-30))),
        'q_absolute_difference_max_kgkg': float(np.nanmax(
            rv / (1 + rv) - rv / (1 + rtot))),
    }

    # --- 5. below ground ---------------------------------------------------
    sp = np.asarray(nc.variables['PSFC'][0], dtype=float)
    below = {}
    for lev in LEVELS:
        under = sp < lev * 100.0
        entry = {'n_below_ground': int(under.sum()),
                 'fraction': float(under.mean())}
        if under.any():
            for short in ('t', 'q', 'z', 'r'):
                v = msgs[(short, lev)]
                entry[short] = {'min': float(np.nanmin(v[under])),
                                'max': float(np.nanmax(v[under])),
                                'mean': float(np.nanmean(v[under])),
                                'n_missing': int((~np.isfinite(v[under])).sum())}
            # and above ground, for contrast
            entry['t_above_ground_mean'] = float(np.nanmean(msgs[('t', lev)][~under]))
        below[lev] = entry
    out['below_ground'] = below

    # --- 6. cc: fractional or binary? --------------------------------------
    cc_all = np.concatenate([msgs[('cc', lev)].ravel() for lev in LEVELS])
    finite = cc_all[np.isfinite(cc_all)]
    cloudy = finite[finite > 0]
    out['cc'] = {
        'n': int(finite.size),
        'n_zero': int((finite == 0).sum()),
        'n_exactly_one': int((finite >= 0.999999).sum()),
        'n_cloudy': int(cloudy.size),
        'fraction_of_cloudy_at_one': float((cloudy >= 0.999999).mean()) if cloudy.size else None,
        'n_distinct_rounded_4dp': int(np.unique(np.round(finite, 4)).size),
        'min': float(finite.min()), 'max': float(finite.max()),
        'deciles_of_cloudy': [float(x) for x in
                              np.percentile(cloudy, [10, 25, 50, 75, 90])] if cloudy.size else None,
    }

    # --- 7. w and wz: two conventions, opposite signs -----------------------
    wz_sign = {}
    for lev in LEVELS:
        w = msgs[('w', lev)]
        wz = msgs[('wz', lev)]
        both = np.isfinite(w) & np.isfinite(wz) & (np.abs(w) > 1e-6)
        wz_sign[lev] = {
            'n': int(both.sum()),
            'fraction_opposite_sign': float(np.mean(np.sign(w[both]) != np.sign(wz[both]))),
            'corr': float(np.corrcoef(w[both], wz[both])[0, 1]),
            'w_range': [float(np.nanmin(w)), float(np.nanmax(w))],
            'wz_range': [float(np.nanmin(wz)), float(np.nanmax(wz))],
        }
    out['w_wz'] = wz_sign

    # --- 8. hypsometric consistency of the published z and t ----------------
    RD = 287.058
    hyps = {}
    for lo, hi in zip(LEVELS[:-1], LEVELS[1:]):        # 1000 -> 50, descending p
        z1, z2 = msgs[('z', lo)], msgs[('z', hi)]
        t1, t2 = msgs[('t', lo)], msgs[('t', hi)]
        q1, q2 = msgs[('q', lo)], msgs[('q', hi)]
        tv = 0.5 * (t1 * (1 + 0.608 * q1) + t2 * (1 + 0.608 * q2))
        expect = RD * tv * np.log(lo / hi)
        actual = z2 - z1
        ok = np.isfinite(expect) & np.isfinite(actual)
        rel = (actual[ok] - expect[ok]) / expect[ok]
        hyps[f'{lo}-{hi}'] = {
            'median_rel_error': float(np.median(rel)),
            'p95_abs_rel_error': float(np.percentile(np.abs(rel), 95)),
            'mean_thickness_m': float(np.mean(actual[ok]) / 9.80665),
        }
    out['hypsometric'] = hyps

    nc.close()
    text = json.dumps(out, indent=1, default=float)
    if args.out:
        Path(args.out).write_text(text)
        print(f'-> {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
