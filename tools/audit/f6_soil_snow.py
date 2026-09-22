#!/usr/bin/env python3
"""Family 6: the soil integral, the snow masks, and what the harness cannot see.

Leg B is unavailable for all eight soil layers, for `rsn` and for `tsn`, because
the converter derives them itself -- so the harness rows carry legs A and C
only. The claim that the layers are the EXACT integral of RUC's own profile is
therefore untested by the harness, and it is the central claim of this family.

    source tools/eccodes_env.sh
    uv run python tools/audit/f6_soil_snow.py --out $WORK/CHAPTER/audit_rows/f6.json

Seven measurements:

  weights    the layer-average operator, derived a SECOND time by dense
             numerical integration of the piecewise-linear profile, and
             compared against the converter's analytic trapezoid matrix. A
             restatement of the same algebra would prove nothing; integrating
             numerically does.
  integral   the published layers against that operator applied to the wrfout's
             own TSLB/SMOIS. This is the leg B the harness does not have.
  nodes      ZS at every sample timestep: the weights are a compile-time
             constant, so a file whose nodes differ would be silently wrong.
  masks      the soil bitmap against the hourly land mask, at the timesteps
             where the sea ice moves it.
  soilt1     stl1 against SOILT1, to show the two are not the same field.
  snow       what SNOWC, SNOW, SNOWH actually hold, and whether tsn's 0.9
             threshold is where the snow temperature stops being a soil one.
  porosity   swvl against the porosity of its own soil type, from SOILPARM.TBL.
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

import harness as H                              # noqa: E402
import f7_static as F                            # noqa: E402

SOILPARM = Path('/leonardo_work/AIFPT_AILAMIT/CHAPTER/WPS/SOILPARM.TBL')

TOKENS = ['stl1', 'stl2', 'stl3', 'stl4', 'swvl1', 'swvl2', 'swvl3', 'swvl4',
          'rsn', 'sd', 'snowc', 'src', 'tsn']
SHORT = {t: t for t in TOKENS}

WINTER = ['2024-01-15T12', '2024-02-15T12', '2024-12-15T12', '2025-02-15T12']
SPREAD = ['2019-07-15T00', '2024-03-15T12', '2024-07-15T12', '2024-11-15T12']


def read_soil_family(path):
    import eccodes
    want = set(TOKENS)
    out = {}
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                s = eccodes.codes_get(gid, 'shortName')
                if s not in want or s in out:
                    continue
                out[s] = {'values': H._message_field(gid),
                          'units': eccodes.codes_get(gid, 'units'),
                          'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent'))}
            finally:
                eccodes.codes_release(gid)
    return out


def dense_weights(nodes, layers, n=2_000_001):
    """The same operator, by brute force.

    For each RUC node, take the profile that is 1 at that node and 0 at the
    others, sample the linear interpolant on a very fine grid and average it
    over the ERA5 layer. The column of the matrix that comes out is the weight
    of that node, computed with no trapezoid formula anywhere.
    """
    z = np.asarray(nodes, dtype=float)
    w = np.zeros((len(layers), len(z)))
    for i in range(len(z)):
        basis = np.zeros(len(z))
        basis[i] = 1.0
        for k, (a, b) in enumerate(layers):
            x = np.linspace(a, b, n)
            w[k, i] = np.trapezoid(np.interp(x, z, basis), x) / (b - a)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    import convert_to_pressure_levels as C

    out = {}

    # --- 1. the operator, twice -------------------------------------------
    mine = dense_weights(C.RUC_SOIL_NODES, C.ERA5_SOIL_LAYERS)
    theirs = C.SOIL_LAYER_WEIGHTS
    out['weights'] = {
        'ruc_nodes_m': list(C.RUC_SOIL_NODES),
        'era5_layers_m': [list(x) for x in C.ERA5_SOIL_LAYERS],
        'converter': theirs.tolist(),
        'dense_integration': mine.tolist(),
        'max_abs_difference': float(np.abs(mine - theirs).max()),
        'row_sums_converter': theirs.sum(axis=1).tolist(),
        'deepest_era5_boundary_m': C.ERA5_SOIL_LAYERS[-1][1],
        'deepest_ruc_node_m': C.RUC_SOIL_NODES[-1],
        'extrapolation_needed': bool(C.ERA5_SOIL_LAYERS[-1][1] > C.RUC_SOIL_NODES[-1]),
        'nodes_touched_per_layer': [[i for i, v in enumerate(row) if abs(v) > 1e-12]
                                    for row in theirs],
    }

    # --- 2. ZS at every timestep -------------------------------------------
    import netCDF4
    nodes_seen = {}
    for ts in H.sample_timesteps():
        with netCDF4.Dataset(H.wrfout_path(ts)) as nc:
            zs = tuple(round(float(v), 6) for v in np.asarray(nc.variables['ZS'][0]))
        nodes_seen.setdefault(zs, []).append(ts)
    out['nodes'] = {
        'distinct_ZS_over_sample': [{'nodes': list(k), 'n_timesteps': len(v)}
                                    for k, v in nodes_seen.items()],
        'matches_converter_constant': all(
            np.allclose(k, C.RUC_SOIL_NODES, atol=1e-6) for k in nodes_seen),
    }

    # --- 3. the integral, against the wrfout -------------------------------
    out['integral'] = {}
    out['masks'] = {}
    out['soilt1'] = {}
    for ts in WINTER[:2] + SPREAD[:3]:
        src = H._read_wrfout_vars(ts, ['TSLB', 'SMOIS', 'SOILT1', 'LANDMASK',
                                       'SEAICE', 'SNOWC'])
        msgs = read_soil_family(H.grib_path(ts))
        land = src['LANDMASK'][0] > 0.5
        entry, maskentry = {}, {}
        for native, prefix in (('TSLB', 'stl'), ('SMOIS', 'swvl')):
            profile = src[native][0]
            layers = np.tensordot(mine, profile, axes=(1, 0))
            for i in range(4):
                token = f'{prefix}{i + 1}'
                ours = msgs[token]['values']
                expect = np.where(land, layers[i], np.nan)
                both = np.isfinite(ours) & np.isfinite(expect)
                d = np.abs(ours[both] - expect[both])
                entry[token] = {
                    'n_compared': int(both.sum()),
                    'max_abs_diff': float(d.max()) if d.size else None,
                    'mean_abs_diff': float(d.mean()) if d.size else None,
                    'n_mask_disagree': int((np.isfinite(ours) != np.isfinite(expect)).sum()),
                    'min': float(np.nanmin(ours)), 'max': float(np.nanmax(ours)),
                }
                maskentry[token] = {
                    'n_missing': int((~np.isfinite(ours)).sum()),
                    'n_water': int((~land).sum()),
                    'missing_equals_water': bool(
                        int((~np.isfinite(ours)).sum()) == int((~land).sum())
                        and not (np.isfinite(ours) & ~land).any()),
                    'bitmap': msgs[token]['bitmap'],
                }
        out['integral'][ts] = entry
        out['masks'][ts] = {'n_seaice': int((src['SEAICE'][0] > 0).sum()),
                            'layers': maskentry}
        # stl1 is the 0-7 cm average of TSLB, NOT SOILT1.
        stl1 = msgs['stl1']['values']
        s1 = src['SOILT1'][0]
        t0 = src['TSLB'][0][0]
        cmp_ = lambda a, b: {
            'max_abs_diff': float(np.nanmax(np.abs(a - b)[land])),
            'rms': float(np.sqrt(np.nanmean(((a - b) ** 2)[land]))),
            'n_equal': int(np.sum(a[land] == b[land])),
        }
        out['soilt1'][ts] = {
            'stl1_vs_SOILT1': cmp_(stl1, s1),
            'stl1_vs_TSLB0': cmp_(stl1, t0),
            'SOILT1_vs_TSLB0': cmp_(s1, t0),
            'n_land': int(land.sum()),
        }
        del src, msgs

    # --- 4. snow: what the fields hold -------------------------------------
    out['snow'] = {}
    for ts in SPREAD + WINTER:
        src = H._read_wrfout_vars(ts, ['SNOWC', 'SNOW', 'SNOWH', 'SOILT1',
                                       'LANDMASK', 'CANWAT'])
        msgs = read_soil_family(H.grib_path(ts))
        land = src['LANDMASK'][0] > 0.5
        snowc, swe, depth = src['SNOWC'][0], src['SNOW'][0], src['SNOWH'][0]
        s1 = src['SOILT1'][0]
        v, c = np.unique(np.round(snowc[land], 4), return_counts=True)
        tsn = msgs['tsn']['values']
        covered = snowc > 0.9
        bands = {}
        for lo, hi in ((0.0, 0.01), (0.01, 0.5), (0.5, 0.9), (0.9, 1.01)):
            b = land & (snowc >= lo) & (snowc < hi)
            if b.sum():
                bands[f'{lo}-{hi}'] = {
                    'n': int(b.sum()), 'max_SOILT1': float(np.nanmax(s1[b])),
                    'frac_above_freezing': float(np.mean(s1[b] > 273.16)),
                }
        out['snow'][ts] = {
            'snowc_distinct_on_land': int(v.size),
            'snowc_is_binary': bool(v.size <= 2),
            'snowc_head': [[float(a), int(b2)] for a, b2 in list(zip(v, c))[:6]],
            'n_snowc_positive': int((snowc > 0).sum()),
            'n_swe_positive': int((swe > 0).sum()),
            'swe_max_kg_m2': float(swe.max()),
            'depth_max_m': float(depth.max()),
            'sd_max_published_m': float(np.nanmax(msgs['sd']['values'])),
            'sd_equals_swe_over_1000': float(np.nanmax(
                np.abs(msgs['sd']['values'] - swe * 1e-3))),
            'sd_vs_snowh_max_abs': float(np.nanmax(
                np.abs(msgs['sd']['values'] - depth))),
            'rsn_min': float(np.nanmin(msgs['rsn']['values'])),
            'rsn_max': float(np.nanmax(msgs['rsn']['values'])),
            'n_rsn_at_100_default': int(np.isclose(msgs['rsn']['values'], 100.0).sum()),
            'n_no_snow_depth': int((depth <= 1e-6).sum()),
            'tsn_n_present': int(np.isfinite(tsn).sum()),
            'n_snowc_above_0p9': int(covered.sum()),
            'tsn_mask_equals_snowc_gt_0p9': bool(
                int(np.isfinite(tsn).sum()) == int(covered.sum())
                and not (np.isfinite(tsn) & ~covered).any()),
            'SOILT1_by_snowc_band': bands,
            'snowc_published_is_percent': float(np.nanmax(msgs['snowc']['values'])),
            'src_max_published_m': float(np.nanmax(msgs['src']['values'])),
            'src_equals_canwat_over_1000': float(np.nanmax(
                np.abs(msgs['src']['values'] - src['CANWAT'][0] * 1e-3))),
        }
        del src, msgs

    # --- 5. swvl against the porosity of its own soil type -----------------
    maxsmc = {}
    block, rows = None, 0
    for line in SOILPARM.read_text().splitlines():
        s = line.strip()
        if s in ('STAS', 'STAS-RUC'):
            block, rows = s, 0
            continue
        if block and s and s[0].isdigit() and ',' in s:
            parts = [p.strip() for p in s.split(',')]
            try:
                idx = int(parts[0])
                maxsmc.setdefault(block, {})[idx] = float(parts[4])
            except (ValueError, IndexError):
                pass
    out['porosity_table'] = {k: v for k, v in maxsmc.items()}
    ts = '2024-07-15T12'
    src = H._read_wrfout_vars(ts, ['ISLTYP', 'LANDMASK'])
    msgs = read_soil_family(H.grib_path(ts))
    isltyp = np.rint(src['ISLTYP'][0]).astype(int)
    land = src['LANDMASK'][0] > 0.5
    for block in maxsmc:
        table = np.zeros(20)
        for k, v in maxsmc[block].items():
            if k < 20:
                table[k] = v
        por = table[np.clip(isltyp, 0, 19)]
        res = {}
        for i in range(1, 5):
            v = msgs[f'swvl{i}']['values']
            ok = land & np.isfinite(v) & (por > 0)
            res[f'swvl{i}'] = {
                'n': int(ok.sum()),
                'n_above_porosity': int((v[ok] > por[ok] + 1e-6).sum()),
                'max_excess': float((v[ok] - por[ok]).max()),
                'max_value': float(v[ok].max()),
                'min_value': float(v[ok].min()),
            }
        out[f'porosity_check_{block}'] = res

    text = json.dumps(out, indent=1, default=float)
    if args.out:
        Path(args.out).write_text(text)
        print(f'-> {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
