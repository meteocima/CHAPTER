#!/usr/bin/env python3
"""Family 1: why our `r` is half ERA5's above 300 hPa.

Leg C shows `r` agreeing within 3 per cent up to 700 hPa and then falling away
to a ratio of 0.53 at 100 hPa, while `q` and `t` -- the two fields `r` is made
of -- agree within a few per cent at the same levels. Two fields agreeing and
the third not is a definition difference, not a data error, and this identifies
which one.

The candidate is in the kernel: wrf-python's DCOMPUTERH is

    es = 6.112 exp(17.67 (T - 273.15)/(T - 29.65))        Magnus, over LIQUID
    rh = 100 max(min(qv/qvs, 1), 0)                        CLIPPED at 100

while ECMWF defines paramId 157 against saturation over the MIXED phase, with
an ice fraction that is 1 below 250.16 K and 0 above 273.16 K, and does not clip.

So the published `r` is recomputed here in both conventions from the published
`q`, `t` and the level pressure, and both are put against ERA5.
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

TS = '2024-07-15T12'
EPS = 0.622


def es_water(t):
    """Magnus over liquid, exactly the kernel's constants."""
    return 6.112 * np.exp(17.67 * (t - 273.15) / (t - 29.65))


def es_ice(t):
    """Magnus over ice (Alduchov-Eskridge), hPa."""
    return 6.1121 * np.exp(22.587 * (t - 273.15) / (t + 0.71))


def ice_fraction(t):
    """The IFS mixed-phase weight: all ice below 250.16 K, all water above 273.16."""
    a = (273.16 - t) / (273.16 - 250.16)
    return np.clip(a, 0.0, 1.0)


def main():
    import wrf_era5_comparison as REG
    levels = list(REG.PRESSURE_LEVELS)
    msgs = F1.read_levels(H.grib_path(TS), {'q', 't', 'r'})
    ctx = H.Context(TS)
    out = {'timestep': TS, 'levels': {}}

    for lev in levels:
        q = msgs[('q', lev)]
        t = msgs[('t', lev)]
        r = msgs[('r', lev)]
        p_hpa = float(lev)
        # vapour pressure from the published specific humidity
        mr = q / np.maximum(1.0 - q, 1e-30)            # specific -> mixing ratio
        ew = es_water(t)
        ei = es_ice(t)
        fi = ice_fraction(t)
        emix = (1.0 - fi) * ew + fi * ei
        qvs_w = EPS * ew / np.maximum(p_hpa - (1.0 - EPS) * ew, 1e-30)
        qvs_m = EPS * emix / np.maximum(p_hpa - (1.0 - EPS) * emix, 1e-30)
        r_water = 100.0 * mr / qvs_w
        r_mixed = 100.0 * mr / qvs_m
        r_water_clipped = np.clip(r_water, 0.0, 100.0)

        counterpart, why = H.era5_counterpart('r', ctx, level=lev)
        entry = {
            'published_max': float(np.nanmax(r)),
            'published_n_at_100': int(np.isclose(r, 100.0, atol=1e-4).sum()),
            'published_n_above_100': int((r > 100.0 + 1e-4).sum()),
            'mean_t': float(np.nanmean(t)),
            'mean_ice_fraction': float(np.nanmean(fi)),
            'es_water_over_es_mixed_at_mean_t': float(
                es_water(np.nanmean(t)) / ((1 - ice_fraction(np.nanmean(t))) *
                                           es_water(np.nanmean(t)) +
                                           ice_fraction(np.nanmean(t)) *
                                           es_ice(np.nanmean(t)))),
            'recomputed_water_clipped_vs_published': {
                'median_abs_diff': float(np.nanmedian(np.abs(r_water_clipped - r))),
                'p95_abs_diff': float(np.nanpercentile(np.abs(r_water_clipped - r), 95)),
            },
            'n_would_exceed_100_unclipped': int((r_water > 100.0).sum()),
            'r_mixed_mean': float(np.nanmean(r_mixed)),
            'r_water_mean': float(np.nanmean(r_water)),
        }
        if counterpart is not None:
            up_pub = ctx.upscale(r)
            up_mix = ctx.upscale(np.clip(r_mixed, 0, 200))
            ok = np.isfinite(up_pub) & np.isfinite(counterpart) & np.isfinite(up_mix)
            a, b, c = up_pub[ok], counterpart[ok], up_mix[ok]
            entry['era5'] = {
                'era5_mean': float(b.mean()),
                'published_mean': float(a.mean()),
                'mixed_phase_mean': float(c.mean()),
                'ratio_published': float(a.mean() / b.mean()),
                'ratio_mixed_phase': float(c.mean() / b.mean()),
                'corr_published': float(np.corrcoef(a, b)[0, 1]),
                'corr_mixed_phase': float(np.corrcoef(c, b)[0, 1]),
                'era5_max': float(b.max()),
                'era5_n_above_100': int((b > 100.0).sum()),
                'n_cells': int(ok.sum()),
            }
        else:
            entry['era5'] = {'why': why}
        out['levels'][lev] = entry
        print(f'{lev} done', flush=True)

    Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/audit_rows/f1_humidity.json').write_text(
        json.dumps(out, indent=1, default=float))
    print('written')


if __name__ == '__main__':
    main()
