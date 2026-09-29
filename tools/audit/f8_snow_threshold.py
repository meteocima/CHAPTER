#!/usr/bin/env python3
"""The snow emissivity threshold, swept over every timestep on disk.

The first sweep used three deep-snow days and found a clean minimum at 0.015.
But the two LIGHT-snow days in it (October, February 2024) kept improving past
0.015, all the way to 0.05 and beyond -- so the optimum depends on the snow
regime, and the regimes that were missing (November, December, April: onset and
melt, snow that is thin and patchy) are exactly the ones that pull the other
way. If they behave like October, no single constant is clearly better than
another and the honest answer is to leave 0.01 alone.

So: all 34 timesteps of the audit sample, 00Z and 12Z, every month of 2024 plus
2019 summer and 2025 winter. Per timestep, and then POOLED -- weighting each
point equally, which is the population the archive actually contains.

CORRECTED after a first run scored the wrong rule. The converter does NOT apply
a plain switch: below the threshold it applies a linear blend between the bare
value and 0.98, weighted by snow cover, and only above it goes flat. Scoring a
plain switch measured something the archive does not do -- and it is also what
made #55's "current 0.940 against a plain switch at 0.76-0.93" look like a
contradiction. It is not one: those are two different rules. Both forms are
swept here, so the comparison is against what actually ships.
"""
import glob
import os
import re
import sys
import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, '/leonardo/home/userexternal/lmonaco0/CHAPTER')
from convert_to_pressure_levels import WRF_EMISS, EMISS_SNOW          # noqa: E402

SIGMA = 5.670374419e-8
DENOM_MIN = 10.0
THRESHOLDS = [0.005, 0.010, 0.015, 0.020, 0.030, 0.050]
# (key, threshold, form). 'blend' is what the converter ships: a linear blend
# between the bare value and 0.98 below the threshold, flat 0.98 above it.
VARIANTS = ([(f'b{t:.3f}', t, 'blend') for t in THRESHOLDS]
            + [(f's{t:.3f}', t, 'switch') for t in THRESHOLDS])
ROOT = '/leonardo_work/AIFPT_AILAMIT/CHAPTER/wrfout_audit'


def skt_from(eps, lwupb, lwdnb):
    return ((lwupb - (1.0 - eps) * lwdnb) / (eps * SIGMA)) ** 0.25


pool = {k: [] for k, _, _ in VARIANTS}        # squared skt errors, per threshold
pool_ok = {k: [] for k, _, _ in VARIANTS}     # emissivity hits
rows = []

for path in sorted(glob.glob(f'{ROOT}/*/wrfout_d02_*')):
    tag = re.search(r'wrfout_d02_(\d{4}-\d{2}-\d{2})_(\d{2})', path)
    label = f'{tag.group(1)} {tag.group(2)}Z'
    with Dataset(path) as d:
        g = lambda k: np.asarray(d.variables[k][0], dtype=float)
        lwupb, lwupbc = g('LWUPB'), g('LWUPBC')
        lwdnb, lwdnbc = g('LWDNB'), g('LWDNBC')
        snowc = np.clip(g('SNOWC'), 0.0, 1.0)
        ivgtyp = np.asarray(d.variables['IVGTYP'][0], dtype=int)
        land = g('LANDMASK') > 0.5

    denom = lwdnb - lwdnbc
    ok = land & (np.abs(denom) > DENOM_MIN)
    if ok.sum() < 1000:
        rows.append((label, int(ok.sum()), 0, None, {}))
        continue
    truth = 1.0 - (lwupb - lwupbc) / np.where(ok, denom, 1.0)
    bare = np.asarray(WRF_EMISS)[np.clip(ivgtyp, 0, len(WRF_EMISS) - 1)]
    t_true = skt_from(truth[ok], lwupb[ok], lwdnb[ok])
    n_snow = int((ok & (snowc > 0)).sum())
    # how many points sit in the band the threshold actually governs
    n_band = int((ok & (snowc > 0.0005) & (snowc < 0.06)).sum())

    blended = (1.0 - snowc) * bare + snowc * EMISS_SNOW
    per = {}
    for key, thr, form in VARIANTS:
        below = blended if form == 'blend' else bare
        eps = np.where(snowc >= thr, EMISS_SNOW, below)[ok]
        d_t = skt_from(eps, lwupb[ok], lwdnb[ok]) - t_true
        per[key] = float(np.sqrt(np.mean(d_t ** 2)))
        pool[key].append(d_t ** 2)
        pool_ok[key].append(np.abs(eps - truth[ok]) <= 1e-4)
    best = min(per, key=per.get)
    rows.append((label, int(ok.sum()), n_snow, best, per, n_band))

print(f'{"timestep":>14} {"nuvolosi":>9} {"con neve":>9} {"in banda":>9} '
      + ' '.join(f'{k:>7}' for k, _, _ in VARIANTS) + '   migliore')
for r in rows:
    if r[3] is None:
        print(f'{r[0]:>14} {r[1]:>9}  (troppo pochi punti nuvolosi)')
        continue
    label, n, n_snow, best, per, n_band = r
    cells = ' '.join(f'{per[k]:7.4f}' for k, _, _ in VARIANTS)
    print(f'{label:>14} {n:>9} {n_snow:>9} {n_band:>9} {cells}   {best}')

print('\n=== POOLED su tutti i punti di tutti i timestep ===')
print(f'{"variante":>10} {"skt RMSE (K)":>13} {"frac eps 1e-4":>14}')
res = {}
for k, thr, form in VARIANTS:
    sq = np.concatenate(pool[k]); hit = np.concatenate(pool_ok[k])
    res[k] = float(np.sqrt(sq.mean()))
    print(f'{k:>10} {res[k]:13.5f} {float(hit.mean()):14.5f}   ({form} a {thr})')
b = min(res, key=res.get)
cur = res['b0.010']
print(f'\nSHIPPING (blend, soglia 0.010): {cur:.5f} K')
print(f'migliore assoluta: {b}  ({res[b]:.5f} K)   guadagno: {100*(cur-res[b])/cur:.1f}%')
