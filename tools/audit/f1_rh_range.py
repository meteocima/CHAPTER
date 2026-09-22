#!/usr/bin/env python3
"""Where does the unclipped mixed-phase RH exceed 130 per cent?

The answer decides the harness's RANGE_OVERRIDE for `r`. Two candidates: real
ice supersaturation, which is physical up to the homogeneous freezing threshold,
and below-ground extrapolation, which is not physical at all -- `q` and `t` are
extrapolated independently below the surface, so their ratio there is not a
humidity.
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
import ifs_humidity as IFS                       # noqa: E402
import wrf_era5_comparison as REG                # noqa: E402

LEVELS = list(REG.PRESSURE_LEVELS)
out = {}
for ts in ['2024-01-15T12', '2024-07-15T12', '2025-02-15T12']:
    msgs = F1.read_levels(H.grib_path(ts), {'q', 't'})
    sp = H._read_wrfout_vars(ts, ['PSFC'])['PSFC'][0]
    per = {}
    for lev in LEVELS:
        p = lev * 100.0
        r = IFS.relative_humidity(msgs[('q', lev)], p, msgs[('t', lev)])
        under = sp < p
        hot = r > 130.0
        over100 = r > 100.0
        per[lev] = {
            'max': float(np.nanmax(r)),
            'max_above_ground': float(np.nanmax(r[~under])) if (~under).any() else None,
            'n_above_100': int(over100.sum()),
            'n_above_100_above_ground': int((over100 & ~under).sum()),
            'n_above_130': int(hot.sum()),
            'n_above_130_below_ground': int((hot & under).sum()),
            'n_above_130_above_ground': int((hot & ~under).sum()),
            'n_below_ground': int(under.sum()),
            'mean_t': float(np.nanmean(msgs[('t', lev)])),
        }
    out[ts] = per
    print(ts, 'done', flush=True)
    del msgs

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f1_rh_range.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
