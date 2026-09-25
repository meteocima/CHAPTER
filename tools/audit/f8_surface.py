#!/usr/bin/env python3
"""Family 8: the skin-temperature inversion re-measured, and the four leg-B gaps.

Five of the nine have no leg B at all -- `skt`, `msl`, `iews`, `inss`,
`mucape`, `mucin` are the converter's own derivations -- so this family is where
the harness is weakest and where reading the code has to be replaced by
measurement wherever a measurement exists. Three do:

  skt    the emissivity is an IDENTITY, not a fit. RRTMG's clear-sky longwave
         shares the all-sky equation's eps and T and differs only in the
         downward flux, so eps = 1 - (LWUPB-LWUPBC)/(LWDNB-LWDNBC) with the
         temperature eliminated. That makes the published table falsifiable
         against every timestep, and the inversion checkable against SST over
         open water, where the model's skin temperature IS the SST.
  iews   the stress is rho u*^2 aligned with the 10 m wind. The magnitude is
  inss   the model's own similarity theory; only the ALIGNMENT is an
         assumption, and ERA5 publishes both its stress and its 10 m wind, so
         the size of that assumption's error can be measured on ERA5 itself.
  mucape the parcel is fixed by the Fortran (max theta-e in the lowest 3 km,
  mucin  averaged over 500 m) and ERA5's is not the same one. The controls
         retrieved with the audit set make the comparison possible anyway.

    source tools/eccodes_env.sh
    uv run python tools/audit/f8_surface.py --out $WORK/CHAPTER/audit_rows/f8.json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402
import convert_to_pressure_levels as C           # noqa: E402

SIGMA = 5.670374419e-8
TOKENS = ['skt', 'sp', 'msl', 'iews', 'inss', 'zust', 'fsr', 'mucape', 'mucin']

# Winter first: the snow rule is the part of the skt claim the original
# measurement had least data for.
SPREAD = ['2024-01-15T12', '2024-02-15T12', '2024-07-15T12', '2024-10-15T12',
          '2025-02-15T12', '2024-03-15T12']


def read_family(path, names=None):
    want = set(names or TOKENS)
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s in want and s not in out:
                    out[s] = H._message_field(gid)
            finally:
                eccodes.codes_release(gid)
    return out


def wrf2d(timestep, names):
    from netCDF4 import Dataset
    nc = Dataset(H.wrfout_path(timestep))
    out = {n: np.asarray(nc.variables[n][0], dtype=np.float64) for n in names}
    nc.close()
    return out


def _iqr(a):
    return float(np.percentile(a, 75) - np.percentile(a, 25)) if a.size else None


# ---------------------------------------------------------------------------
# skt
# ---------------------------------------------------------------------------

def m_emissivity(steps):
    """The emissivity identity, per land-use category, on the wider sample."""
    rows = []
    for ts in steps:
        w = wrf2d(ts, ['LWUPB', 'LWUPBC', 'LWDNB', 'LWDNBC', 'IVGTYP',
                       'SNOWC', 'LANDMASK', 'VEGFRA'])
        num = w['LWUPB'] - w['LWUPBC']
        den = w['LWDNB'] - w['LWDNBC']
        # The identity only resolves where the clear-sky and all-sky downward
        # fluxes differ, i.e. under cloud. Elsewhere it is 0/0.
        usable = np.abs(den) > 1.0
        eps = np.full(num.shape, np.nan)
        eps[usable] = 1.0 - num[usable] / den[usable]
        cat = np.clip(w['IVGTYP'].astype(int), 0, len(C.WRF_EMISS) - 1)
        snow = w['SNOWC'] >= C.EMISS_SNOWC_FULL
        land = w['LANDMASK'] > 0.5

        cats = []
        for k in range(1, len(C.WRF_EMISS)):
            sel = usable & (cat == k) & ~snow
            if sel.sum() < 50:
                cats.append({'category': k, 'n': int(sel.sum())})
                continue
            v = eps[sel]
            cats.append({
                'category': k, 'n': int(sel.sum()),
                'median': float(np.median(v)), 'iqr': _iqr(v),
                'table': float(C.WRF_EMISS[k]),
                'median_minus_table': float(np.median(v) - C.WRF_EMISS[k]),
                'frac_within_1e_4': float(np.mean(
                    np.abs(v - C.WRF_EMISS[k]) < 1e-4)),
                # the refuted green-fraction blend, re-tested: if eps followed
                # VEGFRA the correlation would not be ~0.
                'corr_with_vegfra': float(np.corrcoef(
                    v, w['VEGFRA'][sel])[0, 1]) if np.std(w['VEGFRA'][sel]) > 0 else None,
            })

        snowy = usable & snow & land
        rows.append({
            'timestep': ts,
            'n_usable': int(usable.sum()),
            'usable_fraction': float(usable.mean()),
            'water': ({'n': int((usable & ~land).sum()),
                       'median': float(np.median(eps[usable & ~land])),
                       'iqr': _iqr(eps[usable & ~land])}
                      if (usable & ~land).sum() > 50 else None),
            'snow': ({'n': int(snowy.sum()),
                      'median': float(np.median(eps[snowy])),
                      'iqr': _iqr(eps[snowy]),
                      'frac_within_1e_4_of_098': float(np.mean(
                          np.abs(eps[snowy] - C.EMISS_SNOW) < 1e-4)),
                      'snow_cover_fraction_of_land': float(
                          np.mean(w['SNOWC'][land] >= C.EMISS_SNOWC_FULL))}
                     if snowy.sum() > 50 else {'n': int(snowy.sum())}),
            'categories': cats,
            'categories_present': sorted(set(np.unique(cat[land]).tolist())),
            # the headline claim, restated on this timestep
            'frac_land_reproduced_1e_4': float(np.mean(
                np.abs(eps[usable & land]
                       - np.where(snow[usable & land], C.EMISS_SNOW,
                                  C.WRF_EMISS[cat[usable & land]])) < 1e-4)),
        })
    return rows


def m_skt(steps):
    """The inversion itself: against SST over open water, and against the
    inversion that uses the model's OWN per-point emissivity."""
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['skt', 'sst'])
        w = wrf2d(ts, ['LWUPB', 'LWUPBC', 'LWDNB', 'LWDNBC', 'IVGTYP',
                       'SNOWC', 'LANDMASK', 'SST', 'SEAICE'])
        num = w['LWUPB'] - w['LWUPBC']
        den = w['LWDNB'] - w['LWDNBC']
        usable = np.abs(den) > 1.0
        eps_true = np.full(num.shape, np.nan)
        eps_true[usable] = 1.0 - num[usable] / den[usable]

        cat = np.clip(w['IVGTYP'].astype(int), 0, len(C.WRF_EMISS) - 1)
        snow = w['SNOWC'] >= C.EMISS_SNOWC_FULL
        eps_tab = np.where(snow, C.EMISS_SNOW, C.WRF_EMISS[cat])

        def invert(eps):
            return (np.maximum(w['LWUPB'] - (1.0 - eps) * w['LWDNB'], 1.0)
                    / (eps * SIGMA)) ** 0.25

        skt_tab = invert(eps_tab)
        skt_true = np.where(usable, invert(np.where(usable, eps_true, eps_tab)),
                            np.nan)
        land = w['LANDMASK'] > 0.5
        openwater = (~land) & (w['SEAICE'] < 0.01) & (w['SST'] > 270)

        d_grib = got['skt'] - skt_tab
        both = usable & land & np.isfinite(skt_true)
        d_floor = skt_tab[both] - skt_true[both]
        rows.append({
            'timestep': ts,
            'grib_vs_recomputed_absmax': float(np.max(np.abs(d_grib))),
            'water_gate': {
                'n': int(openwater.sum()),
                'rmse_vs_SST': float(np.sqrt(np.mean(
                    (got['skt'][openwater] - w['SST'][openwater]) ** 2))),
                'bias_vs_SST': float(np.mean(
                    got['skt'][openwater] - w['SST'][openwater])),
                'absmax_vs_SST': float(np.max(np.abs(
                    got['skt'][openwater] - w['SST'][openwater]))),
            },
            'land_table_vs_measured_eps': {
                'n': int(both.sum()),
                'rmse_K': float(np.sqrt(np.mean(d_floor ** 2))),
                'bias_K': float(np.mean(d_floor)),
                'p99_abs_K': float(np.percentile(np.abs(d_floor), 99)),
                'absmax_K': float(np.max(np.abs(d_floor))),
            },
        })
    return rows


# ---------------------------------------------------------------------------
# stress, roughness
# ---------------------------------------------------------------------------

def m_stress(steps):
    """Sign, and how big the alignment assumption is -- measured on ERA5."""
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['iews', 'inss', 'zust', 'fsr'])
        ctx = H.Context(ts)
        e = {'timestep': ts}
        w = wrf2d(ts, ['U10', 'V10', 'UST', 'PSFC', 'T2', 'Q2', 'LANDMASK'])
        # ours: aligned with the 10 m wind by construction -- confirm it
        ang_ours = np.degrees(np.arctan2(
            got['iews'] * w['V10'] - got['inss'] * w['U10'],
            got['iews'] * w['U10'] + got['inss'] * w['V10']))
        e['our_stress_angle_to_10m_wind'] = {
            'absmax_deg': float(np.max(np.abs(ang_ours))),
            'p99_deg': float(np.percentile(np.abs(ang_ours), 99)),
            'n_above_0_01_deg': int(np.sum(np.abs(ang_ours) > 0.01)),
            'min_10m_speed_of_those': float(np.min(
                np.hypot(w['U10'], w['V10'])[np.abs(ang_ours) > 0.01]))
                if np.any(np.abs(ang_ours) > 0.01) else None,
        }
        # magnitude against rho u*^2
        rho = w['PSFC'] / (287.05 * w['T2'] * (1.0 + 0.608 * w['Q2']))
        tau = rho * w['UST'] ** 2
        mag = np.hypot(got['iews'], got['inss'])
        e['magnitude_vs_rho_ustar2_absmax'] = float(np.max(np.abs(mag - tau)))
        # zust must be consistent with the published stress and that rho
        e['zust_vs_sqrt_tau_over_rho_absmax'] = float(np.max(np.abs(
            got['zust'] - np.sqrt(np.maximum(mag, 0) / rho))))
        if ctx.era5_ok:
            hour = int(ts.split('T')[1])
            cache = ctx.era5_messages('sl')

            def era(short):
                for k, v in cache.items():
                    if k[0] == short and k[2] == hour * 100:
                        return v
                return None

            ei, en = era('iews'), era('inss')
            eu, ev = era('10u'), era('10v')
            if ei is not None and eu is not None:
                ang_era = np.degrees(np.arctan2(ei * ev - en * eu,
                                                ei * eu + en * ev))
                e['era5_stress_angle_to_its_own_10m_wind'] = {
                    'median_abs_deg': float(np.median(np.abs(ang_era))),
                    'p90_abs_deg': float(np.percentile(np.abs(ang_era), 90)),
                    'p99_abs_deg': float(np.percentile(np.abs(ang_era), 99)),
                }
                ui, un = ctx.upscale(got['iews']), ctx.upscale(got['inss'])
                ok = (np.isfinite(ui) & np.isfinite(un) & np.isfinite(ei)
                      & np.isfinite(en))
                for name, a, b in (('iews', ui[ok], ei[ok]),
                                   ('inss', un[ok], en[ok])):
                    e[f'{name}_vs_era5'] = {
                        'n': int(ok.sum()),
                        'corr': float(np.corrcoef(a, b)[0, 1]),
                        'sign_agreement': float(np.mean(np.sign(a) == np.sign(b))),
                        'ours_mean_abs': float(np.mean(np.abs(a))),
                        'era5_mean_abs': float(np.mean(np.abs(b))),
                        'ratio_mean_abs': float(np.mean(np.abs(a))
                                                / np.mean(np.abs(b))),
                    }
                um, em = np.hypot(ui[ok], un[ok]), np.hypot(ei[ok], en[ok])
                # the alignment assumption, scored: how much of ERA5's stress
                # direction our wind-aligned construction would recover
                dot = (ui[ok] * ei[ok] + un[ok] * en[ok]) / np.maximum(um * em, 1e-12)
                e['stress_magnitude_vs_era5'] = {
                    'ours_mean': float(um.mean()), 'era5_mean': float(em.mean()),
                    'ratio': float(um.mean() / em.mean()),
                    'corr': float(np.corrcoef(um, em)[0, 1]),
                    'median_direction_agreement_deg': float(np.degrees(
                        np.arccos(np.clip(np.median(dot), -1, 1)))),
                }
        rows.append(e)
    return rows


def m_roughness(steps):
    """fsr runs at half ERA5's. Split land from sea: over water both are
    Charnock and must agree; over land ERA5's carries orographic drag."""
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['fsr', 'zust'])
        ctx = H.Context(ts)
        w = wrf2d(ts, ['ZNT', 'LANDMASK', 'IVGTYP'])
        e = {'timestep': ts,
             'znt_max': float(w['ZNT'].max()),
             'znt_n_at_max': int(np.sum(w['ZNT'] >= w['ZNT'].max() - 1e-9)),
             'grib_vs_znt_absmax': float(np.max(np.abs(got['fsr'] - w['ZNT'])))}
        if ctx.era5_ok:
            hour = int(ts.split('T')[1])
            cache = ctx.era5_messages('sl')
            efsr = ezust = None
            for k, v in cache.items():
                if k[2] != hour * 100:
                    continue
                if k[0] == 'fsr':
                    efsr = v
                if k[0] == 'zust':
                    ezust = v
            if efsr is not None:
                up = ctx.upscale(got['fsr'])
                fin = np.isfinite(up) & np.isfinite(efsr)
                for rname, mask0 in ctx.era5_regions().items():
                    mask = mask0 & fin
                    a, b = up[mask], efsr[mask]
                    e.setdefault('fsr_vs_era5', {})[rname] = {
                        'n': int(mask.sum()),
                        'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
                        'ratio_means': float(a.mean() / b.mean()),
                        'ratio_of_medians': float(np.median(a) / np.median(b)),
                        'median_log_ratio': float(np.median(
                            np.log(np.maximum(a, 1e-8) / np.maximum(b, 1e-8)))),
                        'corr_log': float(np.corrcoef(
                            np.log(np.maximum(a, 1e-8)),
                            np.log(np.maximum(b, 1e-8)))[0, 1]),
                    }
            if ezust is not None:
                up = ctx.upscale(got['zust'])
                fin = np.isfinite(up) & np.isfinite(ezust)
                for rname, mask0 in ctx.era5_regions().items():
                    mask = mask0 & fin
                    a, b = up[mask], ezust[mask]
                    e.setdefault('zust_vs_era5', {})[rname] = {
                        'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
                        'ratio_means': float(a.mean() / b.mean()),
                        'corr': float(np.corrcoef(a, b)[0, 1]),
                    }
        rows.append(e)
    return rows


# ---------------------------------------------------------------------------
# cape, the sphere, msl
# ---------------------------------------------------------------------------

def m_cape(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['mucape', 'mucin'])
        ctx = H.Context(ts)
        # NaN-aware throughout: since #54, `mucin` is MASKED where cape_2d
        # declined instead of zero-filled, so a plain .max() over the field
        # returns NaN and a plain == 0.0 counts nothing. The first run of this
        # gate reported `mucin_max: NaN` for exactly that reason -- the
        # measurement, not the archive. Comparisons against NaN are already
        # False, so the counts below are safe, but say so rather than rely on it.
        e = {'timestep': ts,
             'mucape_zero_fraction': float(np.mean(got['mucape'] == 0.0)),
             'mucin_zero_fraction': float(np.mean(got['mucin'] == 0.0)),
             'mucin_masked_fraction': float(np.mean(~np.isfinite(got['mucin']))),
             'mucape_max': float(np.nanmax(got['mucape'])),
             'mucin_max': float(np.nanmax(got['mucin'])),
             'mucin_negative_points': int(np.sum(got['mucin'] < 0)),
             'mucin_nonzero_where_mucape_below_100': int(np.sum(
                 (got['mucape'] < 100) & (got['mucin'] > 0))),
             'mucape_mean_where_nonzero': float(
                 got['mucape'][got['mucape'] > 0].mean())
                 if np.any(got['mucape'] > 0) else 0.0}
        if ctx.era5_ok:
            hour = int(ts.split('T')[1])
            cache = ctx.era5_messages('sl')
            ecape = ecin = None
            for k, v in cache.items():
                if k[2] != hour * 100:
                    continue
                if k[0] == 'cape':
                    ecape = v
                if k[0] == 'cin':
                    ecin = v
            if ecape is not None:
                up = ctx.upscale(got['mucape'])
                ok = np.isfinite(up) & np.isfinite(ecape)
                a, b = up[ok], ecape[ok]
                e['mucape_vs_era5_cape'] = {
                    'n': int(ok.sum()),
                    'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
                    'ratio_means': float(a.mean() / b.mean()),
                    'corr': float(np.corrcoef(a, b)[0, 1]),
                    'era5_zero_fraction': float(np.mean(b == 0.0)),
                    'ours_zero_fraction_upscaled': float(np.mean(a == 0.0)),
                }
            if ecin is not None:
                # the crosswalk warns 85.5 per cent of ERA5 cin is the fill value
                fill = ecin > 9000
                up = ctx.upscale(got['mucin'])
                good = ~fill & np.isfinite(ecin) & np.isfinite(up)
                e['mucin_vs_era5_cin'] = {
                    'era5_fill_fraction': float(np.mean(fill)),
                    'n_good': int(good.sum()),
                    'ours_mean': float(up[good].mean()),
                    'era5_mean': float(ecin[good].mean()),
                    'ratio_means': float(up[good].mean() / ecin[good].mean()),
                    'corr': float(np.corrcoef(up[good], ecin[good])[0, 1]),
                    'era5_min': float(np.min(ecin[good])),
                    'era5_max': float(np.max(ecin[good])),
                }
        rows.append(e)
    return rows


def m_earth(steps):
    """shapeOfTheEarth on every message of the file, not just this family."""
    rows = []
    for ts in steps:
        counts = {}
        radii = {}
        n = 0
        with open(H.grib_path(ts), 'rb') as fh:
            while True:
                gid = eccodes.codes_grib_new_from_file(fh)
                if gid is None:
                    break
                try:
                    n += 1
                    s = eccodes.codes_get(gid, 'shapeOfTheEarth')
                    counts[s] = counts.get(s, 0) + 1
                    try:
                        r = eccodes.codes_get(gid, 'radius')
                    except Exception:                      # noqa: BLE001
                        r = None
                    radii[r] = radii.get(r, 0) + 1
                finally:
                    eccodes.codes_release(gid)
        rows.append({'timestep': ts, 'n_messages': n,
                     'shapeOfTheEarth': {str(k): v for k, v in counts.items()},
                     'radius': {str(k): v for k, v in radii.items()}})
    return rows


def m_msl(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['msl', 'sp'])
        w = wrf2d(ts, ['HGT', 'LANDMASK'])
        sea = (w['LANDMASK'] < 0.5) & (w['HGT'] < 1.0)
        d = got['msl'] - got['sp']
        rows.append({
            'timestep': ts,
            'msl_minus_sp': {'min': float(d.min()), 'max': float(d.max()),
                             'mean': float(d.mean())},
            'at_sea_level': {
                'n': int(sea.sum()),
                'absmax_msl_minus_sp': float(np.max(np.abs(d[sea]))),
                'p99_abs': float(np.percentile(np.abs(d[sea]), 99)),
                'mean': float(d[sea].mean()),
            },
            'n_msl_below_sp_over_land': int(np.sum(
                (w['LANDMASK'] > 0.5) & (w['HGT'] > 10) & (d < 0))),
            'corr_of_difference_with_orography': float(np.corrcoef(
                d.ravel(), w['HGT'].ravel())[0, 1]),
        })
    return rows



def m_snowrule(steps):
    """What the emissivity actually does as snow cover grows.

    The converter switches to a flat 0.98 from SNOWC >= 0.01 and blends below
    it. On the wider sample that reproduces 84 to 93 per cent of snow-covered
    points, not the ~98 recorded, so the switch is worth re-deriving rather
    than re-asserting: the identity gives the true emissivity at every cloudy
    point, so the relation to SNOWC can simply be read off.
    """
    rows = []
    edges = np.array([0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7,
                      0.9, 0.99, 1.0001])
    for ts in steps:
        w = wrf2d(ts, ['LWUPB', 'LWUPBC', 'LWDNB', 'LWDNBC', 'IVGTYP',
                       'SNOWC', 'LANDMASK'])
        den = w['LWDNB'] - w['LWDNBC']
        usable = (np.abs(den) > 1.0) & (w['LANDMASK'] > 0.5)
        eps = np.where(usable, 1.0 - (w['LWUPB'] - w['LWUPBC']) / np.where(
            usable, den, 1.0), np.nan)
        cat = np.clip(w['IVGTYP'].astype(int), 0, len(C.WRF_EMISS) - 1)
        bare = C.WRF_EMISS[cat]
        snowc = np.clip(w['SNOWC'], 0.0, 1.0)
        bins = []
        for i in range(len(edges) - 1):
            sel = usable & (snowc >= edges[i]) & (snowc < edges[i + 1])
            if sel.sum() < 50:
                bins.append({'lo': float(edges[i]), 'hi': float(edges[i + 1]),
                             'n': int(sel.sum())})
                continue
            v, b = eps[sel], bare[sel]
            # where does the truth sit between the bare value and 0.98?
            frac = (v - b) / np.where(np.abs(C.EMISS_SNOW - b) > 1e-9,
                                      C.EMISS_SNOW - b, np.nan)
            bins.append({
                'lo': float(edges[i]), 'hi': float(edges[i + 1]),
                'n': int(sel.sum()),
                'median_eps': float(np.median(v)),
                'median_bare': float(np.median(b)),
                'median_blend_fraction': float(np.nanmedian(frac)),
                'frac_at_098': float(np.mean(np.abs(v - C.EMISS_SNOW) < 1e-4)),
                'frac_at_bare': float(np.mean(np.abs(v - b) < 1e-4)),
                'median_snowc': float(np.median(snowc[sel])),
            })
        # what the current rule costs, and what a pure switch at other
        # thresholds would give
        thresholds = {}
        for t in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5):
            pred = np.where(snowc >= t, C.EMISS_SNOW, bare)
            thresholds[str(t)] = float(np.mean(
                np.abs(eps[usable] - pred[usable]) < 1e-4))
        pure_blend = (1.0 - snowc) * bare + snowc * C.EMISS_SNOW
        rows.append({
            'timestep': ts,
            'bins': bins,
            'switch_threshold_score': thresholds,
            'current_rule_score': float(np.mean(np.abs(
                eps[usable] - np.where(snowc >= C.EMISS_SNOWC_FULL, C.EMISS_SNOW,
                                       (1 - snowc) * bare
                                       + snowc * C.EMISS_SNOW)[usable]) < 1e-4)),
            'pure_blend_score': float(np.mean(
                np.abs(eps[usable] - pure_blend[usable]) < 1e-4)),
            'no_snow_rule_score': float(np.mean(
                np.abs(eps[usable] - bare[usable]) < 1e-4)),
        })
    return rows


def m_mslout(steps):
    """The sea-level points where msl and sp disagree by hundreds of pascals."""
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['msl', 'sp'])
        w = wrf2d(ts, ['HGT', 'LANDMASK'])
        d = got['msl'] - got['sp']
        sea = (w['LANDMASK'] < 0.5) & (w['HGT'] < 1.0)
        bad = sea & (np.abs(d) > 100.0)
        js, iss = np.where(bad)
        # how far is each offender from land?
        land = w['LANDMASK'] > 0.5
        worst = []
        order = np.argsort(-np.abs(d[bad])) if bad.any() else []
        for k in list(order)[:8]:
            j, i = int(js[k]), int(iss[k])
            win = land[max(j - 5, 0):j + 6, max(i - 5, 0):i + 6]
            hwin = w['HGT'][max(j - 20, 0):j + 21, max(i - 20, 0):i + 21]
            worst.append({'j': j, 'i': i, 'msl_minus_sp': float(d[j, i]),
                          'sp': float(got['sp'][j, i]),
                          'land_within_5_cells': int(win.sum()),
                          'max_orography_within_20_cells': float(hwin.max())})
        rows.append({
            'timestep': ts,
            'n_sea_points': int(sea.sum()),
            'n_above_100Pa': int(bad.sum()),
            'fraction': float(bad.sum() / max(sea.sum(), 1)),
            'n_above_1000Pa': int((sea & (np.abs(d) > 1000.0)).sum()),
            'worst': worst,
        })
    return rows



def m_cinfill(steps):
    """Separate the real CIN from the fill, and price the fill against ERA5.

    The Fortran flags CIN missing wherever CAPE < 100 J/kg; `dense()` writes
    zero there. Zero reads as "no inhibition", but a column with no CAPE is
    usually a column with a LOT of inhibition -- so the fill may not merely be
    a gap-filling convention but a value with the wrong meaning. ERA5 masks the
    same field instead of filling it, which makes the price measurable.
    """
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts), ['mucape', 'mucin'])
        ctx = H.Context(ts)
        real = got['mucape'] >= 100.0          # where the Fortran gives CIN
        e = {'timestep': ts,
             'fraction_where_cin_is_real': float(real.mean()),
             'fraction_filled': float((~real).mean()),
             'mucin_mean_where_real': float(got['mucin'][real].mean())
                 if real.any() else None,
             'mucin_zero_within_real': float(np.mean(got['mucin'][real] == 0.0))
                 if real.any() else None,
             'mucape_between_0_and_100': float(np.mean(
                 (got['mucape'] > 0) & (got['mucape'] < 100))),
             'mucape_exactly_zero': float(np.mean(got['mucape'] == 0.0))}
        if ctx.era5_ok:
            hour = int(ts.split('T')[1])
            ecin = ecape = None
            for k, v in ctx.era5_messages('sl').items():
                if k[2] != hour * 100:
                    continue
                if k[0] == 'cin':
                    ecin = v
                if k[0] == 'cape':
                    ecape = v
            if ecin is not None:
                up_cin = ctx.upscale(got['mucin'])
                up_real = ctx.upscale(real.astype(float))     # fraction real
                ok = np.isfinite(up_cin) & np.isfinite(ecin) & (ecin < 9000)
                # cells where ERA5 has an inhibition and we wrote (almost) only fill
                mostly_fill = ok & (up_real < 0.05)
                mostly_real = ok & (up_real > 0.95)
                e['era5_cin_defined_cells'] = int(ok.sum())
                e['era5_cin_missing_cells'] = int(np.sum(~np.isfinite(ecin)))
                e['where_we_are_mostly_fill'] = {
                    'n': int(mostly_fill.sum()),
                    'our_mean': float(up_cin[mostly_fill].mean())
                        if mostly_fill.any() else None,
                    'era5_mean': float(ecin[mostly_fill].mean())
                        if mostly_fill.any() else None,
                }
                e['where_our_cin_is_real'] = {
                    'n': int(mostly_real.sum()),
                    'our_mean': float(up_cin[mostly_real].mean())
                        if mostly_real.any() else None,
                    'era5_mean': float(ecin[mostly_real].mean())
                        if mostly_real.any() else None,
                    'ratio': float(up_cin[mostly_real].mean()
                                   / ecin[mostly_real].mean())
                        if mostly_real.any() and ecin[mostly_real].mean() else None,
                    'corr': float(np.corrcoef(up_cin[mostly_real],
                                              ecin[mostly_real])[0, 1])
                        if mostly_real.sum() > 10 else None,
                }
            if ecape is not None:
                up = ctx.upscale(got['mucape'])
                ok = np.isfinite(up) & np.isfinite(ecape)
                a, b = up[ok], ecape[ok]
                active = ok & (ecape > 100)
                e['mucape_where_era5_active'] = {
                    'n': int(active.sum()),
                    'ours': float(up[active].mean()) if active.any() else None,
                    'era5': float(ecape[active].mean()) if active.any() else None,
                    'ratio': float(up[active].mean() / ecape[active].mean())
                        if active.any() else None,
                    'corr': float(np.corrcoef(up[active], ecape[active])[0, 1])
                        if active.sum() > 10 else None,
                }
        rows.append(e)
    return rows


def m_znt(steps):
    """ZNT sits at exactly 1.0 m on 19 867 points. Which land use is that?"""
    rows = []
    for ts in steps[:1]:
        w = wrf2d(ts, ['ZNT', 'IVGTYP', 'LANDMASK', 'LU_INDEX'])
        at_cap = w['ZNT'] >= 1.0 - 1e-9
        cats, counts = np.unique(w['IVGTYP'][at_cap].astype(int),
                                 return_counts=True)
        per_cat = {}
        for k in np.unique(w['IVGTYP'][w['LANDMASK'] > 0.5].astype(int)):
            sel = (w['IVGTYP'].astype(int) == k) & (w['LANDMASK'] > 0.5)
            per_cat[int(k)] = {'n': int(sel.sum()),
                               'znt_median': float(np.median(w['ZNT'][sel])),
                               'znt_min': float(w['ZNT'][sel].min()),
                               'znt_max': float(w['ZNT'][sel].max())}
        rows.append({'timestep': ts,
                     'n_at_1m': int(at_cap.sum()),
                     'categories_at_1m': dict(zip(cats.tolist(),
                                                  counts.tolist())),
                     'znt_by_category': per_cat})
    return rows



def m_epsnoise(steps):
    """Is the 6 per cent of snow points that miss 0.98 the rule, or my estimator?

    eps = 1 - (LWUPB-LWUPBC)/(LWDNB-LWDNBC) is exact, but it is a ratio of two
    differences of packed fluxes: where the clear-sky and all-sky downward
    fluxes are close the denominator is small and the quotient is noise. The
    reproduction fraction must therefore be reported AGAINST that denominator,
    not at one arbitrary cut -- otherwise a noisy estimator is read as a wrong
    rule. This is the same trap as the below-ground relative humidity in
    family 1.
    """
    rows = []
    for ts in steps:
        w = wrf2d(ts, ['LWUPB', 'LWUPBC', 'LWDNB', 'LWDNBC', 'IVGTYP',
                       'SNOWC', 'LANDMASK'])
        den = w['LWDNB'] - w['LWDNBC']
        land = w['LANDMASK'] > 0.5
        cat = np.clip(w['IVGTYP'].astype(int), 0, len(C.WRF_EMISS) - 1)
        snowc = np.clip(w['SNOWC'], 0.0, 1.0)
        bare = C.WRF_EMISS[cat]
        pred = np.where(snowc >= C.EMISS_SNOWC_FULL, C.EMISS_SNOW,
                        (1 - snowc) * bare + snowc * C.EMISS_SNOW)
        out = []
        for cut in (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0):
            sel = land & (np.abs(den) > cut)
            if sel.sum() < 100:
                out.append({'den_cut': cut, 'n': int(sel.sum())})
                continue
            eps = 1.0 - (w['LWUPB'][sel] - w['LWUPBC'][sel]) / den[sel]
            snowy = snowc[sel] >= C.EMISS_SNOWC_FULL
            out.append({
                'den_cut': cut, 'n': int(sel.sum()),
                'frac_land_within_1e_4': float(np.mean(
                    np.abs(eps - pred[sel]) < 1e-4)),
                'frac_snow_within_1e_4': float(np.mean(
                    np.abs(eps[snowy] - C.EMISS_SNOW) < 1e-4))
                    if snowy.any() else None,
                'n_snow': int(snowy.sum()),
                'median_abs_residual': float(np.median(np.abs(eps - pred[sel]))),
            })
        rows.append({'timestep': ts, 'by_denominator_cut': out})
    return rows


def m_mslsea(steps):
    """The 77 sea points where msl is far below sp: below-sea-level water."""
    rows = []
    for ts in steps[:2]:
        got = read_family(H.grib_path(ts), ['msl', 'sp'])
        w = wrf2d(ts, ['HGT', 'LANDMASK', 'XLAT', 'XLONG'])
        d = got['msl'] - got['sp']
        sea = w['LANDMASK'] < 0.5
        bad = sea & (np.abs(d) > 1000.0)
        js, iss = np.where(bad)
        pts = [{'j': int(j), 'i': int(i), 'lat': float(w['XLAT'][j, i]),
                'lon': float(w['XLONG'][j, i]), 'hgt': float(w['HGT'][j, i]),
                'msl_minus_sp': float(d[j, i])}
               for j, i in list(zip(js, iss))[:6]]
        # the honest sea-level set: water AND orography at true zero
        truesea = sea & (np.abs(w['HGT']) < 0.5)
        rows.append({
            'timestep': ts, 'n_bad': int(bad.sum()),
            'hgt_of_bad': {'min': float(w['HGT'][bad].min()),
                           'max': float(w['HGT'][bad].max())} if bad.any() else None,
            'examples': pts,
            'n_water_below_sea_level': int(np.sum(sea & (w['HGT'] < -1.0))),
            'at_true_sea_level': {
                'n': int(truesea.sum()),
                'absmax': float(np.max(np.abs(d[truesea]))),
                'p999': float(np.percentile(np.abs(d[truesea]), 99.9)),
                'p99': float(np.percentile(np.abs(d[truesea]), 99)),
                'mean': float(d[truesea].mean()),
            },
        })
    return rows


MEASURES = {'emissivity': m_emissivity, 'skt': m_skt, 'stress': m_stress,
            'roughness': m_roughness, 'cape': m_cape, 'earth': m_earth,
            'msl': m_msl, 'snowrule': m_snowrule, 'mslout': m_mslout,
            'cinfill': m_cinfill, 'znt': m_znt,
            'epsnoise': m_epsnoise, 'mslsea': m_mslsea}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--measure', action='append', choices=sorted(MEASURES))
    ap.add_argument('--timestep', action='append')
    ap.add_argument('--out')
    args = ap.parse_args()
    steps = args.timestep or SPREAD
    out = {}
    for name in args.measure or sorted(MEASURES):
        print(f'--- {name} ---', flush=True)
        out[name] = MEASURES[name](steps)
        print(json.dumps(out[name], indent=1)[:4000], flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))
        print(f'wrote {args.out}')


if __name__ == '__main__':
    main()
