#!/usr/bin/env python3
"""Family 7, second pass: the six questions the first pass raised.

Each one is here because a number from `f7_static.py` could mean two things and
the difference matters for the verdict.
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

out = {}
_lat1d, _lon1d = H.wrf_grid()          # Mercator is separable: two 1-D axes
lat, lon = np.meshgrid(_lat1d, _lon1d, indexing='ij')

# --- 1. cl: WHERE is the lake cover? -----------------------------------------
m = F.read_family(H.grib_path('2024-07-15T12'))
cl = m['cl']['values']
lsm = m['lsm']['values'] > 0.5
sst = m['sst']['values']
boxes = {
    'black_sea':  (40.5, 47.5, 27.0, 42.5),
    'sea_of_azov': (45.0, 47.5, 34.0, 39.5),
    'baltic':     (53.0, 60.1, 9.0, 30.0),
    'north_sea':  (51.0, 60.1, -4.0, 9.0),
    'ladoga_onega': (58.0, 60.1, 29.0, 37.0),
    'alpine':     (45.0, 48.0, 5.0, 14.0),
}
full = cl >= 0.999
out['cl_where'] = {'n_full': int(full.sum()), 'n_positive': int((cl > 0).sum())}
covered = np.zeros_like(full)
for name, (la0, la1, lo0, lo1) in boxes.items():
    box = (lat >= la0) & (lat <= la1) & (lon >= lo0) & (lon <= lo1)
    covered |= box & full
    out['cl_where'][name] = {
        'n_full_in_box': int((full & box).sum()),
        'n_full_in_box_on_sea': int((full & box & ~lsm).sum()),
        'sst_defined_there': int(np.isfinite(sst[full & box]).sum()),
    }
out['cl_where']['n_full_outside_all_boxes'] = int((full & ~covered).sum())
rest = full & ~covered
if rest.any():
    out['cl_where']['rest_lat_range'] = [float(lat[rest].min()), float(lat[rest].max())]
    out['cl_where']['rest_lon_range'] = [float(lon[rest].min()), float(lon[rest].max())]

# --- 2. ci: a fraction or a flag? --------------------------------------------
w = F.read_family(H.grib_path('2024-02-15T12'))
ci = w['ci']['values']
vals, counts = np.unique(np.round(ci, 6), return_counts=True)
nz = vals > 0
out['ci'] = {
    'timestep': '2024-02-15T12',
    'bitmap': w['ci']['bitmap'],
    'n_distinct_values': int(vals.size),
    'n_distinct_nonzero': int(nz.sum()),
    'nonzero_values_head': [[float(v), int(c)] for v, c in
                            list(zip(vals[nz], counts[nz]))[:10]],
    'n_zero_on_land': int(((ci == 0) & (w['lsm']['values'] > 0.5)).sum()),
    'n_positive': int((ci > 0).sum()),
}
src = H._read_wrfout_vars('2024-02-15T12', ['SEAICE'])['SEAICE'][0]
sv, sc = np.unique(np.round(src, 6), return_counts=True)
out['ci']['wrfout_SEAICE_distinct'] = int(sv.size)
out['ci']['wrfout_SEAICE_nonzero_head'] = [[float(v), int(c)] for v, c in
                                           list(zip(sv[sv > 0], sc[sv > 0]))[:10]]

# --- 3. al: how many values does the seasonal switch take? -------------------
al_w = w['al']['values']
al_s = m['al']['values']
land = m['lsm']['values'] > 0.5
out['al'] = {}
for name, field in (('2024-02-15T12', al_w), ('2024-07-15T12', al_s)):
    v, c = np.unique(np.round(field[land], 6), return_counts=True)
    out['al'][name] = {'n_distinct_on_land': int(v.size),
                       'values': [[float(x), int(n)] for x, n in
                                  list(zip(v, c))[:25]]}
moved = al_w != al_s
out['al']['n_changed_winter_to_summer'] = int(moved.sum())
out['al']['n_changed_on_land'] = int((moved & land).sum())
out['al']['max_change'] = float(np.abs(al_w - al_s).max())
# Does it move between two hours of the same day?
al_00 = F.read_family(H.grib_path('2024-07-15T00'))['al']['values']
out['al']['n_changed_00Z_to_12Z_same_day'] = int((al_00 != al_s).sum())

# --- 4. slt: where does the restated rule disagree with static_ref.py? -------
geo = F._geoem()
rc = F._recompute_static(geo)
ours = m['slt']['values']
mine = rc['slt']
both = np.isfinite(ours) & np.isfinite(mine)
bad = both & (ours != mine)
clay = geo['CLAYFRAC'] * 100.0
sand = geo['SANDFRAC'] * 100.0
sct = np.rint(geo['SCT_DOM']).astype(int)
pairs = {}
for o, mv in zip(ours[bad].astype(int), mine[bad].astype(int)):
    pairs[f'{o}->{mv}'] = pairs.get(f'{o}->{mv}', 0) + 1
out['slt_disagreement'] = {
    'n': int(bad.sum()),
    'pairs_published_to_restated': dict(sorted(pairs.items(), key=lambda kv: -kv[1])),
    'clay_range': [float(clay[bad].min()), float(clay[bad].max())],
    'sand_range': [float(sand[bad].min()), float(sand[bad].max())],
    'clay_plus_sand_range': [float((clay + sand)[bad].min()),
                             float((clay + sand)[bad].max())],
    'n_with_zero_clay_and_sand': int(((clay[bad] == 0) & (sand[bad] == 0)).sum()),
    'sct_dom_counts': {int(k): int(v) for k, v in
                       zip(*np.unique(sct[bad], return_counts=True))},
    'examples': [{'clay': float(clay[bad][i]), 'sand': float(sand[bad][i]),
                  'sct_dom': int(sct[bad][i]), 'published': float(ours[bad][i]),
                  'restated': float(mine[bad][i])} for i in range(min(8, int(bad.sum())))],
}

# --- 5. cvl/cvh off the land mask --------------------------------------------
cvl, cvh = m['cvl']['values'], m['cvh']['values']
off = (cvl + cvh > 0) & ~land
out['vegetation_off_land'] = {
    'n': int(off.sum()),
    'max_total': float((cvl + cvh)[off].max()) if off.any() else 0.0,
    'mean_total': float((cvl + cvh)[off].mean()) if off.any() else 0.0,
    'n_with_lake_cover': int((off & (cl > 0)).sum()),
    'n_adjacent_to_land': None,
}
# "Coastal" = a land point within one cell.
pad = np.zeros_like(land)
pad[1:-1, 1:-1] = (land[:-2, 1:-1] | land[2:, 1:-1] |
                   land[1:-1, :-2] | land[1:-1, 2:])
out['vegetation_off_land']['n_adjacent_to_land'] = int((off & pad).sum())

# --- 6. sst: the 35 K spread across the sample -------------------------------
ref = F.read_family(H.grib_path('2019-07-15T00'))['sst']['values']
worst = {}
for ts in ('2025-02-15T12', '2024-02-15T12', '2024-01-15T12'):
    v = F.read_family(H.grib_path(ts))['sst']['values']
    b = np.isfinite(ref) & np.isfinite(v)
    d = np.abs(v - ref)
    d[~b] = 0
    i = int(np.argmax(d))
    yy, xx = np.unravel_index(i, d.shape)
    worst[ts] = {'max_abs_diff': float(d[yy, xx]),
                 'lat': float(lat[yy, xx]), 'lon': float(lon[yy, xx]),
                 'ref_value': float(ref[yy, xx]), 'value': float(v[yy, xx]),
                 'min': float(np.nanmin(v)), 'max': float(np.nanmax(v))}
out['sst_extremes'] = {'reference': '2019-07-15T00',
                       'ref_min': float(np.nanmin(ref)),
                       'ref_max': float(np.nanmax(ref)), 'worst': worst}

print(json.dumps(out, indent=1, default=float))
