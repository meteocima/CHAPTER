#!/usr/bin/env python3
"""What is actually written below ground: an extrapolation, or the lowest level?

Family 1 called the below-ground values an extrapolation, because `wrf.vinterp`
is called with `extrapolate=True`. The surface-join measurement contradicts that:
where the surface pressure says the 1000 hPa surface is BELOW the terrain, the
published `z` puts it at about +24 m ABOVE it -- and 24 m is the lowest model
level.

So the hypothesis is that `vinterp`, handed a raw array rather than one of the
field types it knows (`ght`, `t`, `p`), does not extrapolate at all: it CLAMPS to
the lowest model level. That is a different statement about the archive, and a
much better one, so it is tested directly against the wrfout rather than argued.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import harness as H                              # noqa: E402
import f1_pressure as F1                         # noqa: E402

G = 9.80665
out = {}
for ts in ['2024-01-15T12', '2024-07-15T12', '2025-02-15T00']:
    import wrf
    import netCDF4
    nc = netCDF4.Dataset(H.wrfout_path(ts))
    cache = wrf.extract_vars(nc, 0, ('P', 'PSFC', 'PB', 'PH', 'PHB', 'T', 'QVAPOR', 'HGT'))
    tk = np.asarray(wrf.getvar(nc, 'tk', timeidx=0, cache=cache).values, dtype=float)
    zm = np.asarray(wrf.getvar(nc, 'z', timeidx=0, cache=cache).values, dtype=float)
    q = np.asarray(wrf.getvar(nc, 'QVAPOR', timeidx=0, cache=cache).values, dtype=float)
    sp = np.asarray(nc.variables['PSFC'][0], dtype=float)
    hgt = np.asarray(nc.variables['HGT'][0], dtype=float)
    nc.close()

    msgs = F1.read_levels(H.grib_path(ts), {'t', 'z', 'q'})
    entry = {}
    for lev in (1000, 925):
        under = sp < lev * 100.0
        if not under.any():
            entry[lev] = None
            continue
        t_pub = msgs[('t', lev)][under]
        z_pub = msgs[('z', lev)][under] / G
        q_pub = msgs[('q', lev)][under]
        t_low = tk[0][under]                      # lowest MASS level
        z_low = zm[0][under]
        # q published is specific; the wrfout carries a mixing ratio
        q_low = q[0][under] / (1.0 + q[0][under])
        entry[lev] = {
            'n_below_ground': int(under.sum()),
            't_vs_lowest_model_level': {
                'max_abs_diff': float(np.abs(t_pub - t_low).max()),
                'median_abs_diff': float(np.median(np.abs(t_pub - t_low))),
                'frac_within_0p01K': float((np.abs(t_pub - t_low) < 0.01).mean()),
            },
            'z_vs_lowest_model_level': {
                'max_abs_diff_m': float(np.abs(z_pub - z_low).max()),
                'median_abs_diff_m': float(np.median(np.abs(z_pub - z_low))),
                'frac_within_0p1m': float((np.abs(z_pub - z_low) < 0.1).mean()),
            },
            'q_vs_lowest_model_level': {
                'max_abs_diff': float(np.abs(q_pub - q_low).max()),
                'median_rel_diff': float(np.median(np.abs(q_pub - q_low)
                                                   / np.maximum(q_low, 1e-12))),
                'frac_within_1e-6': float((np.abs(q_pub - q_low) < 1e-6).mean()),
            },
            'published_z_agl_median_m': float(np.median(z_pub - hgt[under])),
            'lowest_level_agl_median_m': float(np.median(z_low - hgt[under])),
        }
    out[ts] = entry
    print(ts, 'done', flush=True)

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f1_below_ground.json').write_text(
    json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=float))
