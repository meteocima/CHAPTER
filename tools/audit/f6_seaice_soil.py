#!/usr/bin/env python3
"""Family 6: the soil column the sea ice creates.

`swvl` reaches exactly 1.000 at the winter timesteps and 0.477 at the summer
ones. 1.000 is above the porosity of every soil type RUC has, so either the
field is wrong or those cells are not soil. This finds out which, and counts
them over the whole sample.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import harness as H                              # noqa: E402
import f6_soil_snow as F6                        # noqa: E402

out = {}
totals = {'n_saturated_ever': 0}
per_ts = {}
for ts in H.sample_timesteps():
    msgs = F6.read_soil_family(H.grib_path(ts))
    src = H._read_wrfout_vars(ts, ['SEAICE', 'ISLTYP', 'LANDMASK'])
    v1 = msgs['swvl1']['values']
    ice = src['SEAICE'][0] > 0
    isltyp = np.rint(src['ISLTYP'][0]).astype(int)
    sat = np.isfinite(v1) & (v1 > 0.55)      # above every RUC porosity (max 0.485)
    entry = {
        'n_seaice': int(ice.sum()),
        'n_swvl1_above_every_porosity': int(sat.sum()),
        'max_swvl1': float(np.nanmax(v1)),
        'n_sat_on_ice': int((sat & ice).sum()),
        'n_sat_off_ice': int((sat & ~ice).sum()),
        'n_ice_not_sat': int((ice & ~sat).sum()),
    }
    if sat.any():
        entry['isltyp_of_saturated'] = {int(k): int(n) for k, n in
                                        zip(*np.unique(isltyp[sat], return_counts=True))}
        entry['stl1_on_saturated'] = {
            'min': float(np.nanmin(msgs['stl1']['values'][sat])),
            'max': float(np.nanmax(msgs['stl1']['values'][sat])),
        }
        entry['swvl_values_on_saturated'] = {
            f'swvl{i}': [float(np.nanmin(msgs[f'swvl{i}']['values'][sat])),
                         float(np.nanmax(msgs[f'swvl{i}']['values'][sat]))]
            for i in range(1, 5)}
    if ice.any():
        entry['isltyp_of_ice'] = {int(k): int(n) for k, n in
                                  zip(*np.unique(isltyp[ice], return_counts=True))}
    per_ts[ts] = entry
    totals['n_saturated_ever'] = max(totals['n_saturated_ever'], int(sat.sum()))
    print(f'{ts}: ice={entry["n_seaice"]} saturated={entry["n_swvl1_above_every_porosity"]}',
          flush=True)
    del msgs, src

out['per_timestep'] = per_ts
out['totals'] = totals
print(json.dumps(out, indent=1, default=float), file=sys.stderr)
Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f6_seaice_soil.json').write_text(
    json.dumps(out, indent=1, default=float))
