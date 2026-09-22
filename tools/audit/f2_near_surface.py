#!/usr/bin/env python3
"""Family 2: the near-surface profile, which is built two different ways.

The ten fields of this family do not come from one place, and that is the thing
the harness cannot see:

  10u, 10v, 2t   WRF's own surface-layer diagnostics, from similarity theory.
                 Leg B is exact for them because they are wrfout variables.
  100u/v, 200u/v `wrf.interplevel` on height above ground, i.e. an interpolation
                 of the RESOLVED profile between model levels.
  2d, 2r         wrf-python diagnostics from Q2/PSFC/T2.
  vwsh           the converter's own difference of the two kinds.

So the bottom of the profile is a parameterisation and everything above it is an
interpolation, and nothing guarantees they agree. This measures whether they do.

  levels      the height of the lowest model level, against the claim that 100 m
              and 200 m are inside the column so `interplevel` never has to
              extrapolate and never returns a gap.
  profile     wind speed at 10, 100 and 200 m and at the lowest pressure level
              above ground: is it monotone, and is it still monotone at night,
              which is where a stable boundary layer makes an interpolation
              error visible.
  dewpoint    2d <= 2t, which no atmosphere violates.
  masks       none of the ten should carry a bitmap.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402
import ifs_humidity as IFS                       # noqa: E402

TOKENS = ['10u', '10v', '100u', '100v', '200u', '200v', '2t', '2d', '2r', 'vwsh']
LEVEL_OF = {'10u': 10, '10v': 10, '100u': 100, '100v': 100, '200u': 200,
            '200v': 200, '2t': 2, '2d': 2, '2r': 2, 'vwsh': 100}


def read_family(path):
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s not in LEVEL_OF or s in out:
                    continue
                if eccodes.codes_get(gid, 'level') != LEVEL_OF[s]:
                    continue
                out[s] = {'values': H._message_field(gid),
                          'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent')),
                          'typeOfLevel': eccodes.codes_get(gid, 'typeOfLevel'),
                          'units': eccodes.codes_get(gid, 'units')}
            finally:
                eccodes.codes_release(gid)
    return out


def read_lowest_pl_speed(path):
    """Wind speed on the lowest pressure level, for the top of the profile."""
    u = v = None
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if eccodes.codes_get(gid, 'typeOfLevel') != 'isobaricInhPa':
                    continue
                if eccodes.codes_get(gid, 'level') != 1000:
                    continue
                if s == 'u' and u is None:
                    u = H._message_field(gid)
                elif s == 'v' and v is None:
                    v = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
            if u is not None and v is not None:
                break
    return u, v


out = {'levels': {}, 'profile': {}, 'dewpoint': {}, 'masks': {}}

# --- 1. the lowest model level, over the sample ------------------------------
import netCDF4
for ts in H.sample_timesteps():
    with netCDF4.Dataset(H.wrfout_path(ts)) as nc:
        ph = np.asarray(nc.variables['PH'][0], dtype=float)
        phb = np.asarray(nc.variables['PHB'][0], dtype=float)
        hgt = np.asarray(nc.variables['HGT'][0], dtype=float)
        # geopotential height on the staggered levels, then the first MASS level
        z_stag = (ph + phb) / 9.81
        z_mass0 = 0.5 * (z_stag[0] + z_stag[1]) - hgt
        z_mass1 = 0.5 * (z_stag[1] + z_stag[2]) - hgt
    out['levels'][ts] = {
        'lowest_mass_level_agl_min': float(z_mass0.min()),
        'lowest_mass_level_agl_max': float(z_mass0.max()),
        'lowest_mass_level_agl_mean': float(z_mass0.mean()),
        'second_mass_level_agl_mean': float(z_mass1.mean()),
        'n_points_with_lowest_above_100m': int((z_mass0 > 100.0).sum()),
        'n_points_with_lowest_above_200m': int((z_mass0 > 200.0).sum()),
    }
    print(ts, 'levels done', flush=True)

# --- 2, 3, 4: the profile, the dewpoint and the masks ------------------------
PROFILE_TIMESTEPS = ['2024-01-15T00', '2024-01-15T12', '2024-07-15T00',
                     '2024-07-15T12', '2025-02-15T00', '2024-07-15T18']
for ts in PROFILE_TIMESTEPS:
    m = read_family(H.grib_path(ts))
    lsm = H.read_grib(H.grib_path(ts), 'lsm')['values'] > 0.5
    s10 = np.hypot(m['10u']['values'], m['10v']['values'])
    s100 = np.hypot(m['100u']['values'], m['100v']['values'])
    s200 = np.hypot(m['200u']['values'], m['200v']['values'])
    u1000, v1000 = read_lowest_pl_speed(H.grib_path(ts))
    s1000 = np.hypot(u1000, v1000)
    sp = H._read_wrfout_vars(ts, ['PSFC'])['PSFC'][0]
    above = sp >= 100000.0          # 1000 hPa genuinely above ground

    def frac(mask, cond):
        n = int(mask.sum())
        return None if n == 0 else float((cond & mask).sum() / n)

    everywhere = np.ones_like(lsm, dtype=bool)
    entry = {}
    for name, region in (('all', everywhere), ('land', lsm), ('sea', ~lsm)):
        entry[name] = {
            'n': int(region.sum()),
            'frac_10_to_100_non_falling': frac(region, s100 >= s10),
            'frac_100_to_200_non_falling': frac(region, s200 >= s100),
            'frac_monotone_10_100_200': frac(region, (s100 >= s10) & (s200 >= s100)),
            'mean_s10': float(s10[region].mean()),
            'mean_s100': float(s100[region].mean()),
            'mean_s200': float(s200[region].mean()),
        }
    if above.any():
        entry['vs_1000hPa'] = {
            'n_above_ground': int(above.sum()),
            'frac_200_to_1000hPa_non_falling': frac(above, s1000 >= s200),
            'mean_s200': float(s200[above].mean()),
            'mean_s1000hPa': float(s1000[above].mean()),
        }
    # the shear, recomputed: it is the converter's own formula, so this only
    # confirms the encoding, and leg D already does it over the whole sample
    entry['vwsh'] = {
        'max_abs_diff_vs_formula': float(np.nanmax(np.abs(
            m['vwsh']['values'] - np.hypot(
                m['100u']['values'] - m['10u']['values'],
                m['100v']['values'] - m['10v']['values']) / 90.0))),
        'min': float(np.nanmin(m['vwsh']['values'])),
        'max': float(np.nanmax(m['vwsh']['values'])),
    }
    out['profile'][ts] = entry

    # dewpoint
    t2, d2 = m['2t']['values'], m['2d']['values']
    viol = d2 > t2
    out['dewpoint'][ts] = {
        'n_dewpoint_above_temperature': int(viol.sum()),
        'max_excess_K': float((d2 - t2)[viol].max()) if viol.any() else 0.0,
        't2_range': [float(t2.min()), float(t2.max())],
        'd2_range': [float(d2.min()), float(d2.max())],
        'n_t2_below_200K_or_above_350K': int(((t2 < 200) | (t2 > 350)).sum()),
        # the IFS humidity the published 2r should hold once #40 is fixed
        'ifs_2r_from_2t_2d_max': float(np.nanmax(
            100.0 * IFS.esat_water(d2) / IFS.esat_mixed(t2))),
        'published_2r_max': float(np.nanmax(m['2r']['values'])),
    }
    out['masks'][ts] = {k: {'bitmap': v['bitmap'],
                            'n_missing': int((~np.isfinite(v['values'])).sum()),
                            'typeOfLevel': v['typeOfLevel'],
                            'units': v['units']}
                        for k, v in m.items()}
    print(ts, 'profile done', flush=True)
    del m

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f2_near_surface.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
