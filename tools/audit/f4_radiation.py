#!/usr/bin/env python3
"""Family 4: the accumulation machinery, and three checks that need no ERA5.

All thirteen are accumulated since 00Z and written with product definition
template 8, which nothing in this audit has tested yet -- nineteen accumulators
in the archive depend on the same machinery, and `CLAUDE.md` records that
`ensure_ref` trusts any non-empty sidecar without checking its contents.

  encoding    the GRIB keys themselves: stepType, stepRange, the reference time
              against the validity time, and the genproc marker that says the
              file carries the 00Z convention rather than the run-init one.
  zero        exactly zero at 00Z, every field, every sampled day. An
              accumulation since 00Z has no other possible value there.
  sign        which fields are negative and where, against the ECMWF convention
              that every one of them is a NET flux counted downward-positive.
  clearsky    the six clear-sky pairs must bound their all-sky partners in the
              direction physics fixes, at every point. Free, and no ERA5.
  monotone    within one run the published accumulation must never fall. The
              sample's diurnal day gives 00, 06, 12 and 18Z of a single run.
  geometry    `tisr` is the incident solar at the top of the atmosphere, which
              is astronomy and nothing else. Recomputing it from the orbit gives
              the SOLAR CONSTANT the archive implies, which is a number that can
              be recognised or not.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import eccodes                                   # noqa: E402
import harness as H                              # noqa: E402

TOKENS = ['ssr', 'ssrc', 'ssrd', 'ssrdc', 'str', 'strc', 'strd', 'strdc',
          'tisr', 'tsr', 'tsrc', 'ttr', 'ttrc']
# (clear-sky, all-sky, direction): 'ge' means the clear-sky member must be the
# greater. Clouds cut the solar down and add to the downward thermal, so the two
# families point opposite ways.
CLEAR_PAIRS = [
    ('ssrdc', 'ssrd', 'ge'),    # clear sky lets more solar reach the ground
    ('ssrc', 'ssr', 'ge'),      # and so the net solar is larger
    ('tsrc', 'tsr', 'ge'),      # clouds reflect solar back to space
    ('strdc', 'strd', 'le'),    # clouds EMIT downward thermal, clear sky less
    ('strc', 'str', 'le'),      # so the net thermal loss is larger under clear sky
    ('ttrc', 'ttr', 'le'),      # and the outgoing thermal (negative) more negative
]
KEYS = ('stepType', 'stepRange', 'dataDate', 'dataTime', 'validityDate',
        'validityTime', 'generatingProcessIdentifier', 'productDefinitionTemplateNumber',
        'typeOfLevel', 'level', 'units', 'typeOfStatisticalProcessing')


def read_family(path, with_keys=False):
    out, keys = {}, {}
    want = set(TOKENS)
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s not in want or s in out:
                    continue
                out[s] = H._message_field(gid)
                if with_keys:
                    k = {}
                    for name in KEYS:
                        try:
                            k[name] = eccodes.codes_get(gid, name)
                        except Exception as exc:          # noqa: BLE001
                            k[name] = f'<{type(exc).__name__}>'
                    keys[s] = k
            finally:
                eccodes.codes_release(gid)
    return (out, keys) if with_keys else out


def solar_cos_zenith(lat_deg, lon_deg, when):
    """cos of the solar zenith angle, clipped at 0. Spencer (1971) series."""
    n = when.timetuple().tm_yday
    frac = when.hour + when.minute / 60.0 + when.second / 3600.0
    gamma = 2.0 * np.pi * (n - 1 + (frac - 12.0) / 24.0) / 365.0
    decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma)
            - 0.006758 * np.cos(2 * gamma) + 0.000907 * np.sin(2 * gamma)
            - 0.002697 * np.cos(3 * gamma) + 0.001480 * np.sin(3 * gamma))
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                    - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
    e0 = (1.000110 + 0.034221 * np.cos(gamma) + 0.001280 * np.sin(gamma)
          + 0.000719 * np.cos(2 * gamma) + 0.000077 * np.sin(2 * gamma))
    lat = np.radians(lat_deg)
    solar_time = frac + lon_deg / 15.0 + eot / 60.0
    hour_angle = np.radians(15.0 * (solar_time - 12.0))
    cosz = (np.sin(lat) * np.sin(decl)
            + np.cos(lat) * np.cos(decl) * np.cos(hour_angle))
    return np.maximum(cosz, 0.0), e0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    out = {}

    # --- 1. encoding, at one timestep of each kind --------------------------
    out['encoding'] = {}
    for ts in ('2024-07-15T00', '2024-07-15T12'):
        _, keys = read_family(H.grib_path(ts), with_keys=True)
        out['encoding'][ts] = keys
        print(ts, 'keys done', flush=True)

    # --- 2. zero at 00Z, sign, and non-negativity, over the whole sample ----
    out['per_timestep'] = {}
    for ts in H.sample_timesteps():
        m = read_family(H.grib_path(ts))
        entry = {}
        for tok in TOKENS:
            v = m[tok]
            entry[tok] = {
                'min': float(np.nanmin(v)), 'max': float(np.nanmax(v)),
                'mean': float(np.nanmean(v)),
                'max_abs': float(np.nanmax(np.abs(v))),
                'n_negative': int((v < 0).sum()),
                'n_positive': int((v > 0).sum()),
            }
        # the clear-sky pairs
        pairs = {}
        for clear, allsky, direction in CLEAR_PAIRS:
            c, a = m[clear], m[allsky]
            ok = (c >= a - 1.0) if direction == 'ge' else (c <= a + 1.0)
            bad = ~ok
            pairs[f'{clear}_{direction}_{allsky}'] = {
                'frac_satisfied': float(ok.mean()),
                'n_violating': int(bad.sum()),
                'worst_violation_Jm2': float(np.abs(c - a)[bad].max()) if bad.any() else 0.0,
            }
        entry['_clear_sky_pairs'] = pairs
        out['per_timestep'][ts] = entry
        print(ts, 'values done', flush=True)
        del m

    # --- 3. monotone within one run: the diurnal day ------------------------
    day = sorted(t for t in H.sample_timesteps() if t.startswith('2024-07-15'))
    series = {t: read_family(H.grib_path(t)) for t in day}
    mono = {}
    for tok in TOKENS:
        steps = {}
        for a, b in zip(day[:-1], day[1:]):
            d = series[b][tok] - series[a][tok]
            steps[f'{a[-2:]}->{b[-2:]}'] = {
                'n_decreasing': int((d < -1.0).sum()),
                'worst_decrease_Jm2': float(-d.min()) if (d < 0).any() else 0.0,
                'median_increase_Jm2': float(np.median(d)),
            }
        mono[tok] = steps
    out['monotone_within_run'] = {'day': '2024-07-15', 'hours': day, 'steps': mono}
    print('monotonicity done', flush=True)

    # --- 4. tisr against the orbit ------------------------------------------
    lat1d, lon1d = H.wrf_grid()
    lat, lon = np.meshgrid(lat1d, lon1d, indexing='ij')
    geo = {}
    for ts in ('2024-07-15T06', '2024-07-15T12', '2024-07-15T18',
               '2024-01-15T12', '2025-02-15T12'):
        date, hour = ts.split('T')
        end = datetime.strptime(date, '%Y-%m-%d') + timedelta(hours=int(hour))
        start = datetime.strptime(date, '%Y-%m-%d')
        step = 300.0                                  # seconds
        total = np.zeros(lat.shape)
        t = start
        while t < end:                                 # midpoint rule
            mid = t + timedelta(seconds=step / 2.0)
            cosz, e0 = solar_cos_zenith(lat, lon, mid)
            total += cosz * e0 * step
            t += timedelta(seconds=step)
        pub = read_family(H.grib_path(ts))['tisr']
        lit = total > 1000.0                          # avoid dividing by twilight
        implied = pub[lit] / total[lit]
        geo[ts] = {
            'n_lit': int(lit.sum()),
            'implied_solar_constant_W_m2': {
                'median': float(np.median(implied)),
                'p5': float(np.percentile(implied, 5)),
                'p95': float(np.percentile(implied, 95)),
                'mean': float(implied.mean()),
            },
            'published_max_Jm2': float(np.nanmax(pub)),
            'geometry_max_s': float(total.max()),
        }
        print(ts, 'geometry done', flush=True)
    out['tisr_geometry'] = geo

    text = json.dumps(out, indent=1, default=float)
    if args.out:
        Path(args.out).write_text(text)
        print(f'-> {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
