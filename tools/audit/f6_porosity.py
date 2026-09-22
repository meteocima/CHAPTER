#!/usr/bin/env python3
"""Family 6: does swvl ever exceed the porosity of its OWN soil type?

The summer check found none. Summer has no sea ice, so it could not see the
cells the moving mask creates, and it could not see a winter-only excursion
either. This repeats the check on the four winter timesteps against STAS-RUC,
the block `sf_surface_physics = 3` uses, and separates the sea-ice cells out.
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

maxsmc, block = {}, None
for line in F6.SOILPARM.read_text().splitlines():
    s = line.strip()
    if s in ('STAS', 'STAS-RUC'):
        block = s
        continue
    if block == 'STAS-RUC' and s and s[0].isdigit() and ',' in s:
        p = [x.strip() for x in s.split(',')]
        try:
            maxsmc[int(p[0])] = float(p[4])
        except (ValueError, IndexError):
            pass
table = np.zeros(20)
for k, v in maxsmc.items():
    if k < 20:
        table[k] = v

out = {'STAS-RUC_MAXSMC': maxsmc, 'per_timestep': {}}
for ts in ['2024-01-15T12', '2024-02-15T12', '2024-12-15T12', '2025-02-15T12',
           '2024-11-15T12', '2019-07-15T00']:
    msgs = F6.read_soil_family(H.grib_path(ts))
    src = H._read_wrfout_vars(ts, ['ISLTYP', 'SEAICE'])
    isltyp = np.rint(src['ISLTYP'][0]).astype(int)
    ice = src['SEAICE'][0] > 0
    por = table[np.clip(isltyp, 0, 19)]
    entry = {'n_seaice': int(ice.sum())}
    for i in range(1, 5):
        v = msgs[f'swvl{i}']['values']
        ok = np.isfinite(v) & (por > 0)
        over = ok & (v > por + 1e-6)
        entry[f'swvl{i}'] = {
            'n_land': int(ok.sum()),
            'n_above_own_porosity': int(over.sum()),
            'n_above_and_ice': int((over & ice).sum()),
            'n_above_not_ice': int((over & ~ice).sum()),
            'max_excess': float((v[ok] - por[ok]).max()),
            'max_excess_off_ice': float((v[ok & ~ice] - por[ok & ~ice]).max()),
        }
    out['per_timestep'][ts] = entry
    print(ts, 'done', flush=True)
    del msgs, src

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f6_porosity.json').write_text(
    json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=float))
