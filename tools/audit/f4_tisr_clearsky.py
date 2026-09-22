#!/usr/bin/env python3
"""Two questions the first radiation pass left open.

1. `tisr` implied a solar constant of 1350 to 1382 W/m2 depending on the date, a
   1.4 per cent spread that a constant cannot have. The first integration used a
   MIDPOINT rule; the model does not. `swint_opt = 0` with `radt = 5` (settled by
   #12) means WRF evaluates the shortwave every 5 minutes and HOLDS IT CONSTANT
   until the next call -- a left-endpoint step function. Over a window truncated
   at 12Z, in winter, when the sun is still climbing, that difference does not
   cancel. So the integration is repeated with the model's own quadrature.

2. The clear-sky pairs are violated at up to 247 289 points. In a 1-D radiation
   scheme the clear-sky downward solar cannot exceed the all-sky one UNLESS the
   surface is bright: light reflected up from snow and returned downward by the
   cloud base adds to the all-sky flux and has nowhere to come from under clear
   sky. The same argument inverted explains an outgoing thermal flux larger with
   cloud than without, over a surface colder than the cloud. Both are testable:
   if the violations need cloud, they vanish where there is none.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402
import f4_radiation as F4                        # noqa: E402

out = {}
lat1d, lon1d = H.wrf_grid()
lat, lon = np.meshgrid(lat1d, lon1d, indexing='ij')

# --- 1. tisr with the model's own quadrature --------------------------------
RADT = 300.0          # seconds, radt = 5 minutes
geo = {}
for ts in ('2024-07-15T12', '2024-07-15T18', '2024-01-15T12', '2025-02-15T12',
           '2024-04-15T12', '2024-10-15T12'):
    date, hour = ts.split('T')
    start = datetime.strptime(date, '%Y-%m-%d')
    end = start + timedelta(hours=int(hour))
    totals = {}
    for scheme in ('left', 'mid'):
        total = np.zeros(lat.shape)
        t = start
        while t < end:
            at = t if scheme == 'left' else t + timedelta(seconds=RADT / 2.0)
            cosz, e0 = F4.solar_cos_zenith(lat, lon, at)
            total += cosz * e0 * RADT
            t += timedelta(seconds=RADT)
        totals[scheme] = total
    pub = F4.read_family(H.grib_path(ts))['tisr']
    entry = {}
    for scheme, total in totals.items():
        lit = total > 1000.0
        implied = pub[lit] / total[lit]
        entry[scheme] = {
            'median': float(np.median(implied)),
            'p5': float(np.percentile(implied, 5)),
            'p95': float(np.percentile(implied, 95)),
            'iqr': float(np.percentile(implied, 75) - np.percentile(implied, 25)),
            'n_lit': int(lit.sum()),
        }
    geo[ts] = entry
    print(ts, 'tisr done', flush=True)
out['tisr'] = geo

# --- 2. do the clear-sky violations need cloud? ------------------------------
def read_extra(path, shorts):
    got = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s in shorts and s not in got and \
                        eccodes.codes_get(gid, 'typeOfLevel') != 'isobaricInhPa':
                    got[s] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
    return got


clear = {}
for ts in ('2024-11-15T12', '2025-01-15T12', '2024-06-15T12', '2024-04-15T12'):
    m = F4.read_family(H.grib_path(ts))
    ex = read_extra(H.grib_path(ts), {'tcc', 'al', 'fal', 'sd', 'skt', 'lsm'})
    tcc = ex['tcc']
    clearsky = tcc < 0.01
    entry = {'n_cloud_free': int(clearsky.sum()),
             'frac_cloud_free': float(clearsky.mean())}
    for c, a, direction in F4.CLEAR_PAIRS:
        diff = m[c] - m[a]
        bad = (diff < -1.0) if direction == 'ge' else (diff > 1.0)
        entry[f'{c}_vs_{a}'] = {
            'n_violating': int(bad.sum()),
            'n_violating_where_cloud_free': int((bad & clearsky).sum()),
            'worst_Jm2': float(np.abs(diff)[bad].max()) if bad.any() else 0.0,
            'median_albedo_where_violating': float(np.median(ex['al'][bad]))
            if bad.any() else None,
            'median_albedo_overall': float(np.median(ex['al'])),
            'median_snow_where_violating_m': float(np.median(ex['sd'][bad]))
            if bad.any() else None,
            'frac_violating_on_land': float(np.mean(ex['lsm'][bad] > 0.5))
            if bad.any() else None,
        }
    clear[ts] = entry
    print(ts, 'clear-sky done', flush=True)
    del m, ex
out['clear_sky'] = clear

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f4_tisr_clearsky.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
