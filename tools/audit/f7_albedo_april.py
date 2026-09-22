#!/usr/bin/env python3
"""Family 7: the one month that is neither table.

`al` matches LANDUSE.TBL's SUMMER block from May to October and its WINTER
block from November to March. April is neither, so it is measured separately:
either it is a third value set, which would break the two-table account, or it
is the same two sets applied to different cells.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import harness as H                              # noqa: E402
import f7_static as F                            # noqa: E402

_lat1d, _lon1d = H.wrf_grid()
lat, _ = np.meshgrid(_lat1d, _lon1d, indexing='ij')
out = {}
fields = {}
for ts in ('2024-03-15T12', '2024-04-15T12', '2024-05-15T12',
           '2024-10-15T12', '2024-11-15T12', '2024-07-15T12'):
    m = F.read_family(H.grib_path(ts))
    fields[ts] = m['al']['values']
    if 'land' not in out:
        land = m['lsm']['values'] > 0.5
        out['land'] = int(land.sum())
    v, c = np.unique(np.round(fields[ts][land], 3), return_counts=True)
    out[ts] = {'n_distinct': int(v.size),
               'values': [[float(x), int(n)] for x, n in zip(v, c)]}
    del m

# April against both tables, cell by cell.
apr, jul, mar = fields['2024-04-15T12'], fields['2024-07-15T12'], fields['2024-03-15T12']
like_summer = np.isclose(apr, jul, atol=1e-6) & land
like_winter = np.isclose(apr, mar, atol=1e-6) & land
out['april'] = {
    'n_like_summer': int(like_summer.sum()),
    'n_like_winter': int(like_winter.sum()),
    'n_like_neither': int((~like_summer & ~like_winter & land).sum()),
    'n_like_both': int((like_summer & like_winter).sum()),
}
for name, mask in (('summer', like_summer), ('winter', like_winter)):
    if mask.any():
        out['april'][f'{name}_lat_range'] = [float(lat[mask].min()),
                                             float(lat[mask].max())]
        out['april'][f'{name}_lat_mean'] = float(lat[mask].mean())
print(json.dumps(out, indent=1, default=float))
