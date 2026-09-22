#!/usr/bin/env python3
"""Family 7, third pass: the one mask this family turns on.

`lsm` separates land from water; nothing in the archive separates OCEAN from
INLAND water. Two published fields assume that separation exists -- `sst`,
which ERA5 defines on the ocean, and `cl`, which ERA5 defines on lakes -- so
this measures what each of them actually holds on the other side.
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

SEAWATER_FREEZING = 271.35      # K, at 35 PSU

_lat1d, _lon1d = H.wrf_grid()
lat, lon = np.meshgrid(_lat1d, _lon1d, indexing='ij')
out = {'seawater_freezing_K': SEAWATER_FREEZING}

for ts in ('2024-01-15T12', '2024-02-15T12', '2025-02-15T12', '2024-07-15T12'):
    m = F.read_family(H.grib_path(ts))
    sst, cl = m['sst']['values'], m['cl']['values']
    ci = m['ci']['values']
    water = np.isfinite(sst)
    lake = water & (cl > 0.5)
    ocean = water & (cl <= 0.5)
    cold = water & (sst < SEAWATER_FREEZING)
    entry = {
        'n_water': int(water.sum()),
        'n_lake_by_cl': int(lake.sum()),
        'n_below_freezing': int(cold.sum()),
        'n_below_freezing_on_lake': int((cold & lake).sum()),
        'n_below_freezing_on_ocean': int((cold & ocean).sum()),
        'min_sst_lake': float(np.nanmin(sst[lake])) if lake.any() else None,
        'min_sst_ocean': float(np.nanmin(sst[ocean])) if ocean.any() else None,
        'n_ice_flag': int((ci > 0).sum()),
        'n_below_freezing_without_ice_flag': int((cold & (ci <= 0)).sum()),
    }
    if cold.any():
        i = int(np.argmin(np.where(cold, sst, np.inf)))
        yy, xx = np.unravel_index(i, sst.shape)
        entry['coldest'] = {'lat': float(lat[yy, xx]), 'lon': float(lon[yy, xx]),
                            'sst': float(sst[yy, xx]), 'cl': float(cl[yy, xx]),
                            'ci': float(ci[yy, xx])}
    # The Black Sea, as a named case: ERA5 calls it ocean, our `cl` calls it lake.
    box = (lat >= 41.0) & (lat <= 47.0) & (lon >= 28.0) & (lon <= 42.0) & water
    entry['black_sea'] = {
        'n_water_cells': int(box.sum()),
        'mean_cl': float(np.nanmean(cl[box])),
        'n_cl_full': int((box & (cl >= 0.999)).sum()),
        'mean_sst': float(np.nanmean(sst[box])),
        'mean_dl': float(np.nanmean(m['dl']['values'][box])),
        'n_dl_at_wps_default': int(np.isclose(m['dl']['values'][box], 10.0).sum()),
    }
    out[ts] = entry
    del m

print(json.dumps(out, indent=1, default=float))
