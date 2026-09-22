#!/usr/bin/env python3
"""The two questions the radiation family still had open, each settled directly.

1. The clear-sky pairs are violated at up to 247 289 points, and the violations
   are almost all in columns that are cloud-free AT THE VALIDITY TIME -- which
   proves nothing, because the fields are accumulated since 00Z and the column
   may have been cloudy at 08Z. The discriminating test is the INSTANTANEOUS
   flux: at one instant, in a one-dimensional radiation scheme, the clear-sky
   member must bound the all-sky one. If the instantaneous fields obey the
   inequality and the accumulated ones do not, the fault is in the accumulation,
   not in RRTMG.

2. `tisr` implies a solar constant that moves with the date: 1399 W/m2 in
   January, 1374 in July, 1320 in October, and the spatial spread within one
   timestep is only 0.4 to 1.2 per cent. A constant that varies only with the
   date, and most in late October and early February, is the EQUATION OF TIME --
   which peaks at +16 minutes in early November and -14 in early February, and
   which WRF's orbital code may not apply at all. So the integration is repeated
   without it.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import harness as H                              # noqa: E402
import f4_radiation as F4                        # noqa: E402

out = {}
lat1d, lon1d = H.wrf_grid()
lat, lon = np.meshgrid(lat1d, lon1d, indexing='ij')


def cos_zenith(when, use_eot):
    n = when.timetuple().tm_yday
    frac = when.hour + when.minute / 60.0 + when.second / 3600.0
    gamma = 2.0 * np.pi * (n - 1 + (frac - 12.0) / 24.0) / 365.0
    decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma)
            - 0.006758 * np.cos(2 * gamma) + 0.000907 * np.sin(2 * gamma)
            - 0.002697 * np.cos(3 * gamma) + 0.001480 * np.sin(3 * gamma))
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                    - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
    e0 = (1.000110 + 0.034221 * np.cos(gamma) + 0.001280 * np.sin(gamma)
          + 0.000719 * np.cos(2 * gamma) + 0.000077 * np.sin(2 * gamma))
    st = frac + lon / 15.0 + (eot / 60.0 if use_eot else 0.0)
    ha = np.radians(15.0 * (st - 12.0))
    la = np.radians(lat)
    return np.maximum(np.sin(la) * np.sin(decl)
                      + np.cos(la) * np.cos(decl) * np.cos(ha), 0.0), e0


RADT = 300.0
geo = {}
for ts in ('2024-01-15T12', '2024-04-15T12', '2024-07-15T12', '2024-10-15T12',
           '2025-02-15T12', '2024-07-15T18'):
    date, hour = ts.split('T')
    start = datetime.strptime(date, '%Y-%m-%d')
    end = start + timedelta(hours=int(hour))
    pub = F4.read_family(H.grib_path(ts))['tisr']
    entry = {}
    for use_eot in (True, False):
        total = np.zeros(lat.shape)
        t = start
        while t < end:
            cosz, e0 = cos_zenith(t, use_eot)
            total += cosz * e0 * RADT
            t += timedelta(seconds=RADT)
        lit = total > 1000.0
        imp = pub[lit] / total[lit]
        entry['with_eot' if use_eot else 'no_eot'] = {
            'median': float(np.median(imp)),
            'iqr': float(np.percentile(imp, 75) - np.percentile(imp, 25)),
            'p5': float(np.percentile(imp, 5)), 'p95': float(np.percentile(imp, 95)),
        }
    geo[ts] = entry
    print(ts, 'tisr done', flush=True)
out['tisr'] = geo

# --- the instantaneous clear-sky inequality ---------------------------------
PAIRS_INST = [
    ('SWDNBC', 'SWDNB', 'ge'),        # downward solar at the surface
    ('SWUPBC', 'SWUPB', 'any'),       # upward solar at the surface, for context
    ('SWUPTC', 'SWUPT', 'le'),        # reflected to space: clouds reflect MORE
    ('LWDNBC', 'LWDNB', 'le'),        # downward thermal: clouds emit MORE
    ('LWUPTC', 'LWUPT', 'ge'),        # outgoing thermal: clear sky emits MORE
]
inst = {}
for ts in ('2024-11-15T12', '2025-01-15T12', '2024-06-15T12'):
    names = sorted({n for p in PAIRS_INST for n in p[:2]})
    src = H._read_wrfout_vars(ts, names)
    entry = {}
    for c, a, direction in PAIRS_INST:
        if src[c][0] is None or src[a][0] is None:
            entry[f'{c}_vs_{a}'] = {'note': 'absent from the wrfout'}
            continue
        cv, av = src[c][0], src[a][0]
        d = cv - av
        if direction == 'ge':
            bad = d < -1e-3
        elif direction == 'le':
            bad = d > 1e-3
        else:
            bad = np.zeros(d.shape, dtype=bool)
        entry[f'{c}_vs_{a}'] = {
            'direction': direction,
            'n_violating': int(bad.sum()),
            'frac_violating': float(bad.mean()),
            'worst_W_m2': float(np.abs(d)[bad].max()) if bad.any() else 0.0,
            'median_abs_diff_W_m2': float(np.median(np.abs(d))),
            'max_abs_diff_W_m2': float(np.abs(d).max()),
        }
    inst[ts] = entry
    print(ts, 'instantaneous done', flush=True)
    del src
out['instantaneous'] = inst

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f4_decisive.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
