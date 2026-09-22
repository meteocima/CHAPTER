#!/usr/bin/env python3
"""Does the pressure-level profile join the near-surface diagnostics?

The question, from the repo owner: `2t` and `2d` are one end of the atmosphere
and `t`, `q` at 1000 and 925 hPa are the other -- are they consistent?

THE DIRECTION OF INFERENCE MATTERS. `2t` is exact under leg B (it is `T2` read
straight through), so it is not the unknown. The unknown is the pressure-level
profile, which on 47.6 per cent of the domain is an EXTRAPOLATION below ground.
So this measures the extrapolation against the one trustworthy anchor near the
surface, and it is family 1's below-ground warning that gets a number on it.

It also deliberately does NOT extrapolate down to 2 m. Between 2 m and the
1000 hPa surface -- a median 84 to 126 m above ground -- lies the surface layer,
which the pressure levels do not resolve: logarithmic, superadiabatic by day,
strongly stable at night. Descending linearly through it would produce a scatter
that is physics and prove nothing. Instead the LAPSE RATE IMPLIED between the two
is reported, at the height each actually has, and the reader can judge whether it
is a possible atmosphere.

Reported separately for the points where 1000 hPa is above ground and where it is
below, because only the first is a physical comparison at all.
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

G = 9.80665
TIMESTEPS = ['2024-01-15T00', '2024-01-15T12', '2024-07-15T00', '2024-07-15T12',
             '2025-02-15T00']
WANT_PL = {('t', 1000), ('q', 1000), ('z', 1000), ('t', 925), ('q', 925), ('z', 925)}


def read_all(path):
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                lev = eccodes.codes_get(gid, 'level')
                tol = eccodes.codes_get(gid, 'typeOfLevel')
                if tol == 'isobaricInhPa' and (s, lev) in WANT_PL:
                    out[(s, lev)] = H._message_field(gid)
                elif tol == 'heightAboveGround' and s in ('2t', '2d') and lev == 2:
                    out[s] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
    return out


def describe(x):
    x = x[np.isfinite(x)]
    if x.size == 0:
        return None
    return {'n': int(x.size), 'median': float(np.median(x)),
            'p5': float(np.percentile(x, 5)), 'p95': float(np.percentile(x, 95)),
            'min': float(x.min()), 'max': float(x.max()),
            'mean': float(x.mean())}


out = {}
for ts in TIMESTEPS:
    m = read_all(H.grib_path(ts))
    src = H._read_wrfout_vars(ts, ['PSFC', 'HGT'])
    sp, hgt = src['PSFC'][0], src['HGT'][0]
    lsm = H.read_grib(H.grib_path(ts), 'lsm')['values'] > 0.5

    entry = {}
    for lev in (1000, 925):
        z_agl = m[('z', lev)] / G - hgt
        above = sp >= lev * 100.0
        t_lev = m[('t', lev)]
        # the lapse rate the archive implies between 2 m and this surface,
        # K per km, positive = temperature falling with height
        dz = z_agl - 2.0
        ok = np.abs(dz) > 1.0
        gamma = np.where(ok, (m['2t'] - t_lev) / np.where(ok, dz, 1.0) * 1000.0, np.nan)
        # moisture: specific humidity at 2 m from the dewpoint, against q at level
        e2 = IFS.esat_water(m['2d'])                 # dewpoint is over water
        q2 = IFS.EPSILON * e2 / (sp - (1.0 - IFS.EPSILON) * e2)
        dq = (q2 - m[('q', lev)]) * 1000.0           # g/kg
        sub = {}
        for name, mask in (('above_ground', above & ok),
                           ('below_ground', ~above & ok),
                           ('above_ground_land', above & ok & lsm),
                           ('above_ground_sea', above & ok & ~lsm)):
            if not mask.any():
                sub[name] = None
                continue
            sub[name] = {
                'n': int(mask.sum()),
                'fraction_of_domain': float(mask.mean()),
                'height_agl_m': describe(z_agl[mask]),
                'lapse_rate_K_per_km': describe(gamma[mask]),
                'dT_2m_minus_level_K': describe((m['2t'] - t_lev)[mask]),
                'dq_2m_minus_level_gkg': describe(dq[mask]),
            }
        entry[lev] = sub
    out[ts] = entry
    print(ts, 'done', flush=True)
    del m, src

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f12_surface_join.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
