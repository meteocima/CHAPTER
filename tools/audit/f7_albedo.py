#!/usr/bin/env python3
"""Family 7, fourth pass: is `al` seasonal, and how much of its motion is packing?

The first pass compared decoded values for exact equality, which is right for a
field whose message is byte-identical from one file to the next -- the seven
static ones are -- but wrong for one whose extremes change, because
`grid_ccsds` then picks a different reference and scale and the same physical
value decodes a little differently. So the motion is measured again here at the
packing precision the message itself declares.
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
import f7_static as F                            # noqa: E402

WINTER, SUMMER = '2024-02-15T12', '2024-07-15T12'
out = {}


def packing(path, shorts):
    info = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s not in shorts or s in info:
                    continue
                info[s] = {k: eccodes.codes_get(gid, k) for k in
                           ('bitsPerValue', 'packingType', 'referenceValue',
                            'binaryScaleFactor', 'decimalScaleFactor')}
            finally:
                eccodes.codes_release(gid)
    return info


out['packing_winter'] = packing(H.grib_path(WINTER), {'al', 'cvl', 'tvl', 'lsm'})
out['packing_summer'] = packing(H.grib_path(SUMMER), {'al', 'cvl', 'tvl', 'lsm'})

w = F.read_family(H.grib_path(WINTER))
s = F.read_family(H.grib_path(SUMMER))
land = s['lsm']['values'] > 0.5
aw, asu = w['al']['values'], s['al']['values']
# The quantum of the packing, from the message itself.
q = 2.0 ** out['packing_winter']['al']['binaryScaleFactor']
out['quantum'] = float(q)
for tol, name in ((0.0, 'exact'), (q, 'one_quantum'), (1e-3, 'thousandth')):
    moved = np.abs(aw - asu) > tol
    out[f'n_moved_on_land_{name}'] = int((moved & land).sum())
    out[f'n_moved_off_land_{name}'] = int((moved & ~land).sum())

rw = np.round(aw, 3)
rs = np.round(asu, 3)
pairs = {}
for a, b in zip(rw[land], rs[land]):
    k = f'{a:.3f}->{b:.3f}'
    pairs[k] = pairs.get(k, 0) + 1
out['winter_to_summer_on_land'] = dict(sorted(pairs.items(), key=lambda kv: -kv[1]))
out['n_unchanged_pairs'] = int(sum(v for k, v in pairs.items()
                                   if k.split('->')[0] == k.split('->')[1]))
out['land_points'] = int(land.sum())

# Two hours of the same day, as a control on the packing argument: the field
# cannot have changed, so whatever moves here is the encoder.
a00 = F.read_family(H.grib_path('2024-07-15T00'))['al']['values']
out['same_day_00Z_vs_12Z'] = {
    'n_exactly_different': int((a00 != asu).sum()),
    'max_abs_diff': float(np.abs(a00 - asu).max()),
}
# And the same control for a static field, which must be identical.
out['same_day_static_control'] = {
    'cvl_max_abs_diff': float(np.abs(
        F.read_family(H.grib_path('2024-07-15T00'))['cvl']['values']
        - s['cvl']['values']).max()),
}
print(json.dumps(out, indent=1, default=float))
