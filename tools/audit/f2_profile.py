#!/usr/bin/env python3
"""Family 2, second pass: two checks the first pass posed badly.

1. "Is the wind non-falling from 200 m to the 1000 hPa level?" is the wrong
   question: over the sea the 1000 hPa surface sits at about 110 m, BELOW 200 m,
   so a falling wind there is correct. The right check is whether the 1000 hPa
   wind lands between the 100 m and 200 m winds, at the height it actually has,
   which the published `z` gives directly.

2. "What fraction of points has the wind falling from 100 m to 200 m?" counts
   sign flips without asking how big they are. In a well-mixed summer boundary
   layer the profile is nearly flat, so the sign is noise and the fraction says
   nothing. The size of the fall is what separates noise from a low-level jet.

Also: are the points where `2d` exceeds `2t` exactly the saturated ones?
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
import f2_near_surface as F2                     # noqa: E402

G = 9.80665
TIMESTEPS = ['2024-01-15T00', '2024-07-15T00', '2024-07-15T12', '2025-02-15T00']
out = {}

for ts in TIMESTEPS:
    m = F2.read_family(H.grib_path(ts))
    # the 1000 hPa wind and geopotential, in one pass
    got = {}
    with open(H.grib_path(ts), 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                if eccodes.codes_get(gid, 'typeOfLevel') != 'isobaricInhPa':
                    continue
                if eccodes.codes_get(gid, 'level') != 1000:
                    continue
                s = eccodes.codes_get(gid, 'shortName')
                if s in ('u', 'v', 'z') and s not in got:
                    got[s] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)

    sp = H._read_wrfout_vars(ts, ['PSFC', 'HGT'])
    above = sp['PSFC'][0] >= 100000.0
    # height of the 1000 hPa surface ABOVE GROUND, from the published fields
    z_agl = got['z'] / G - sp['HGT'][0]
    s10 = np.hypot(m['10u']['values'], m['10v']['values'])
    s100 = np.hypot(m['100u']['values'], m['100v']['values'])
    s200 = np.hypot(m['200u']['values'], m['200v']['values'])
    s1000 = np.hypot(got['u'], got['v'])

    # where the 1000 hPa surface genuinely lies between 100 and 200 m, the wind
    # there must lie between the two interpolated winds
    band = above & (z_agl > 100.0) & (z_agl < 200.0)
    lo, hi = np.minimum(s100, s200), np.maximum(s100, s200)
    inside = band & (s1000 >= lo - 1e-6) & (s1000 <= hi + 1e-6)

    fall = s200 < s100
    drop = (s100 - s200)[fall]
    entry = {
        'z_1000hPa_agl': {
            'n_above_ground': int(above.sum()),
            'median_m': float(np.median(z_agl[above])),
            'p10_m': float(np.percentile(z_agl[above], 10)),
            'p90_m': float(np.percentile(z_agl[above], 90)),
            'n_between_100_and_200m': int(band.sum()),
        },
        'consistency_1000hPa_with_interpolation': {
            'n_in_band': int(band.sum()),
            'frac_between_s100_and_s200': float(inside.sum() / max(band.sum(), 1)),
            'mean_abs_excursion_ms': float(np.mean(np.maximum(
                0.0, np.maximum(lo[band] - s1000[band], s1000[band] - hi[band]))))
            if band.any() else None,
        },
        'fall_100_to_200': {
            'n_falling': int(fall.sum()),
            'frac_falling': float(fall.mean()),
            'median_drop_ms': float(np.median(drop)) if drop.size else None,
            'p95_drop_ms': float(np.percentile(drop, 95)) if drop.size else None,
            'max_drop_ms': float(drop.max()) if drop.size else None,
            'frac_of_falls_below_0p1_ms': float((drop < 0.1).mean()) if drop.size else None,
            'frac_of_falls_below_0p5_ms': float((drop < 0.5).mean()) if drop.size else None,
            'mean_s100': float(s100.mean()), 'mean_s200': float(s200.mean()),
        },
        'shear_10_to_100': {
            'frac_falling': float((s100 < s10).mean()),
            'median_gain_ms': float(np.median(s100 - s10)),
        },
    }
    # 2d > 2t: is it exactly saturation?
    t2, d2, r2 = m['2t']['values'], m['2d']['values'], m['2r']['values']
    viol = d2 > t2
    entry['dewpoint_violation'] = {
        'n': int(viol.sum()),
        'max_excess_K': float((d2 - t2)[viol].max()) if viol.any() else 0.0,
        'min_2r_where_violating': float(r2[viol].min()) if viol.any() else None,
        'frac_violating_that_are_at_100pc': float(
            (r2[viol] >= 99.999).mean()) if viol.any() else None,
        'n_at_100pc': int((r2 >= 99.999).sum()),
    }
    out[ts] = entry
    print(ts, 'done', flush=True)
    del m, got

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f2_profile.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
