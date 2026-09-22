#!/usr/bin/env python3
"""Is the relative humidity clipped at 100? Settled from the source field.

"Re-test every deliberate exclusion" concluded `2r` has no clip, reading
`src/wrf/g_rh.py:152` -- `_rh(q2, psfc, t2)` -- and finding nothing that
truncates. The truncation is one level down, in the Fortran the wrapper calls:

    fortran/wrf_user.f90:730   rh(i) = 100*MAX(MIN(qv(i)/qvs, 1.0), 0.0)

So this recomputes the kernel from the wrfout's own Q2, PSFC and T2 WITHOUT the
min, and counts the points the min removed. A clip cannot be seen by looking at
the published maxima -- a clipped value of exactly 100 comes back from 24-bit
CCSDS packing scattered by a few 1e-6, which is what was read as float noise.
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

EZERO, ESLCON1, ESLCON2, CELKEL, EPS = 6.112, 17.67, 29.65, 273.15, 0.622


def kernel_rh(qv, p_pa, t_k):
    """DCOMPUTERH, unclipped: the same constants, without the MIN."""
    es = EZERO * np.exp(ESLCON1 * (t_k - CELKEL) / (t_k - ESLCON2))
    qvs = EPS * es / (0.01 * p_pa - (1.0 - EPS) * es)
    return 100.0 * qv / qvs


def read_one(path, short, level=None):
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                return None
            try:
                if eccodes.codes_get(gid, 'shortName') != short:
                    continue
                if level is not None and eccodes.codes_get(gid, 'level') != level:
                    continue
                return H._message_field(gid)
            finally:
                eccodes.codes_release(gid)


out = {}
for ts in ('2024-01-15T12', '2024-07-15T00', '2024-07-15T12', '2025-02-15T12'):
    pub = read_one(H.grib_path(ts), '2r', 2)
    src = H._read_wrfout_vars(ts, ['Q2', 'PSFC', 'T2'])
    q2 = np.maximum(src['Q2'][0], 0.0)
    raw = kernel_rh(q2, src['PSFC'][0], src['T2'][0])
    clipped = np.clip(raw, 0.0, 100.0)
    out[ts] = {
        'published_max': float(np.nanmax(pub)),
        'published_min': float(np.nanmin(pub)),
        'published_n_within_1e-5_of_100': int((np.abs(pub - 100.0) < 1e-5).sum()),
        'published_n_above_100': int((pub > 100.0).sum()),
        'published_largest_excursion_above_100': float(max(0.0, np.nanmax(pub) - 100.0)),
        'packing_quantum_estimate': float(100.0 / 2 ** 24),
        'unclipped_max': float(np.nanmax(raw)),
        'unclipped_n_above_100': int((raw > 100.0).sum()),
        'unclipped_n_above_101': int((raw > 101.0).sum()),
        'unclipped_n_above_105': int((raw > 105.0).sum()),
        'unclipped_mean_excess_where_above': float(
            np.mean(raw[raw > 100.0] - 100.0)) if (raw > 100.0).any() else None,
        'clipped_vs_published_median_abs': float(np.nanmedian(np.abs(clipped - pub))),
        'clipped_vs_published_max_abs': float(np.nanmax(np.abs(clipped - pub))),
        'unclipped_vs_published_max_abs': float(np.nanmax(np.abs(raw - pub))),
    }
    print(ts, 'done', flush=True)
    del src

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f1_rh_clip.json').write_text(
    json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=float))
