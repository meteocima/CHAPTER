#!/usr/bin/env python3
"""What `r` and `2r` become under the IFS definition, measured before it is adopted.

Three questions, from the decision on #40:

  range     the published field is clipped at 100, so nobody has ever seen how
            far above it the model actually goes. If WSM6 permits ice
            supersaturation this is where it appears, and the harness's
            RANGE_OVERRIDE of (0, 130) has to be able to hold it.
  phase vs formula
            two things change at once -- saturation over the mixed phase
            instead of liquid, and Buck/AERKi instead of the kernel's Magnus.
            They are separated here so the second is not credited to the first.
  2r vs 2d  `2r` will be mixed-phase while `2d` stays a dewpoint over water, as
            ERA5 and the WMO both have it. A user who reconstructs humidity from
            `2t` and `2d` will therefore not get `2r` back at cold points, and
            the size of that divergence has to be in the documentation rather
            than discovered.
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

PL_TIMESTEPS = ['2024-01-15T12', '2024-07-15T12', '2025-02-15T12', '2024-07-15T00']
out = {'self_check': IFS.self_check(verbose=False), 'levels': {}, 'two_metre': {}}

import wrf_era5_comparison as REG
LEVELS = list(REG.PRESSURE_LEVELS)

# --- pressure levels ---------------------------------------------------------
for ts in PL_TIMESTEPS:
    msgs = F1.read_levels(H.grib_path(ts), {'q', 't', 'r'})
    ctx = H.Context(ts)
    per = {}
    for lev in LEVELS:
        q, t, r_pub = msgs[('q', lev)], msgs[('t', lev)], msgs[('r', lev)]
        p = lev * 100.0
        r_mixed = IFS.relative_humidity(q, p, t)
        r_water_ifs = IFS.relative_humidity_over_water(q, p, t)
        # the kernel's own formula, from the published q, unclipped
        mr = q / np.maximum(1.0 - q, 1e-30)
        qvs_magnus = 0.622 * IFS.esat_magnus_water(t) / np.maximum(
            p - (1.0 - 0.622) * IFS.esat_magnus_water(t), 1e-30)
        r_water_magnus = 100.0 * mr / qvs_magnus
        entry = {
            'mean_t': float(np.nanmean(t)),
            'mean_alpha_liquid': float(np.nanmean(IFS.alpha_liquid(t))),
            'published_max': float(np.nanmax(r_pub)),
            'mixed_max': float(np.nanmax(r_mixed)),
            'mixed_p999': float(np.nanpercentile(r_mixed, 99.9)),
            'mixed_n_above_100': int((r_mixed > 100).sum()),
            'mixed_n_above_130': int((r_mixed > 130).sum()),
            'mixed_n_above_150': int((r_mixed > 150).sum()),
            # phase change alone, and formula change alone
            'ratio_mixed_over_water_ifs': float(
                np.nanmean(r_mixed) / np.nanmean(r_water_ifs)),
            'ratio_water_ifs_over_water_magnus': float(
                np.nanmean(r_water_ifs) / np.nanmean(r_water_magnus)),
        }
        counterpart, _ = H.era5_counterpart('r', ctx, level=lev)
        if counterpart is not None:
            up_pub = ctx.upscale(r_pub)
            up_mix = ctx.upscale(r_mixed)
            ok = np.isfinite(up_pub) & np.isfinite(counterpart) & np.isfinite(up_mix)
            entry['era5'] = {
                'ratio_published': float(up_pub[ok].mean() / counterpart[ok].mean()),
                'ratio_mixed': float(up_mix[ok].mean() / counterpart[ok].mean()),
                'corr_mixed': float(np.corrcoef(up_mix[ok], counterpart[ok])[0, 1]),
                'era5_max': float(counterpart[ok].max()),
            }
        per[lev] = entry
    out['levels'][ts] = per
    print(ts, 'pressure levels done', flush=True)
    del msgs, ctx

# --- 2 m, over the whole sample ---------------------------------------------
import eccodes


def read_2m(path):
    want = {'2t': 2, '2d': 2, '2r': 2}
    got = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s in want and eccodes.codes_get(gid, 'level') == want[s] and s not in got:
                    got[s] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
    return got


for ts in H.sample_timesteps():
    g = read_2m(H.grib_path(ts))
    src = H._read_wrfout_vars(ts, ['Q2', 'PSFC', 'T2'])
    q2_mr = np.maximum(src['Q2'][0], 0.0)              # WRF Q2 is a mixing ratio
    q2 = IFS.mixing_ratio_to_specific(q2_mr)
    psfc, t2 = src['PSFC'][0], src['T2'][0]
    new_2r = IFS.relative_humidity(q2, psfc, t2)
    # what a user reconstructs from 2t and 2d, over water, as the WMO defines Td
    from_2d = 100.0 * IFS.esat_water(g['2d']) / IFS.esat_water(g['2t'])
    cold = t2 < IFS.T0
    very_cold = t2 < IFS.T_ICE
    diff = new_2r - from_2d
    out['two_metre'][ts] = {
        'published_2r_max': float(np.nanmax(g['2r'])),
        'new_2r_max': float(np.nanmax(new_2r)),
        'new_2r_n_above_100': int((new_2r > 100).sum()),
        'new_2r_n_above_130': int((new_2r > 130).sum()),
        'n_below_freezing': int(cold.sum()),
        'n_below_Tice': int(very_cold.sum()),
        'divergence_from_2d_median_where_cold': float(
            np.nanmedian(diff[cold])) if cold.any() else None,
        'divergence_from_2d_max': float(np.nanmax(np.abs(diff))),
        'divergence_from_2d_max_where_warm': float(
            np.nanmax(np.abs(diff[~cold]))) if (~cold).any() else None,
        'divergence_from_2d_max_where_very_cold': float(
            np.nanmax(np.abs(diff[very_cold]))) if very_cold.any() else None,
        # is 2d itself consistent with Q2? a leg-D check family 2 can reuse
        'e_from_q2_vs_esat_water_2d_max_rel': float(np.nanmax(np.abs(
            IFS.vapour_pressure(q2, psfc) / IFS.esat_water(g['2d']) - 1.0))),
        'e_from_q2_vs_esat_water_2d_median_rel': float(np.nanmedian(np.abs(
            IFS.vapour_pressure(q2, psfc) / IFS.esat_water(g['2d']) - 1.0))),
    }
    print(ts, '2m done', flush=True)
    del g, src

Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f1_rh_ifs.json').write_text(
    json.dumps(out, indent=1, default=float))
print('written')
