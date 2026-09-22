#!/usr/bin/env python3
"""Family 3: the column integrals, and the leg B the harness said did not exist.

The harness records `leg_b: none` for all ten members of this family, on the
rule that the derivation IS the converter's algorithm and restating it would be
a copy. For the six column integrals that rule is wrong, and this script is the
reason: WRF integrates on a DRY-MASS vertical coordinate, so the water mass in
a column is not an integral to be approximated at all -- it is a weighted sum
with weights the model itself wrote out.

    column dry mass of layer k  =  (MU + MUB) * |DNW_k| / g          [kg/m2]
    water mass of species X     =  sum_k  X_k * (MU + MUB) * |DNW_k| / g

because WRF's `Q*` are mixing ratios, per kg of DRY air, and `DNW` sums to
exactly -1 over the 49 layers (checked here, not assumed). No pressure
differencing, no endpoint rule, no missing surface layer: this is the answer.

It is also the SAME quantity ECMWF defines. ERA5's tcwv is the integral of
SPECIFIC humidity against TOTAL pressure, and

    q_specific * dm_total  =  (m_v/m_tot) dm_tot  =  dm_v  =  (m_v/m_dry) dm_dry
                           =  r_mixing * dm_dry

so the two formulations are the same integral written twice. The converter uses
the first; this script uses the second; they must agree, and where they do not
the difference is discretisation and nothing else.

    source tools/eccodes_env.sh
    uv run python tools/audit/f3_columns.py --out $WORK/CHAPTER/audit_rows/f3.json

Six measurements:

  massbudget  DNW sums to -1 and the reconstructed surface pressure from the
              layer masses matches PSFC. If this fails nothing below is worth
              reading, because the coordinate is not what it is claimed to be.
  massint     every published column integral against the dry-mass sum, and the
              converter's own rule restated, so the error is ATTRIBUTED: the
              missing layer below the lowest model level, the endpoint rule,
              the discarded top.
  closure     tcw against the sum of the five published components. The
              converter puts QGRAUP in tcw and publishes no graupel column, so
              the residual must equal the graupel column exactly.
  bounds      tcc against the two bounds any overlap assumption must satisfy:
              at least the largest single layer (maximum overlap), at most the
              product of the clear fractions (random overlap). Independent of
              how the overlap is coded.
  bands       the sigma partition: how many model levels fall in each band, the
              boundaries against ECMWF's, and whether the three bands combine
              back to tcc.
  overlap     tcc and the three bands recomputed from CLDFRA by a second
              implementation, compared point for point with the published
              messages.
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

G = 9.80665

TOKENS = ['tcw', 'tcwv', 'tclw', 'tciw', 'tcrw', 'tcsw',
          'tcc', 'hcc', 'mcc', 'lcc']

# species -> the published shortName of its column, and whether tcw carries it.
SPECIES = {
    'QVAPOR': ('tcwv', True),
    'QCLOUD': ('tclw', True),
    'QRAIN':  ('tcrw', True),
    'QICE':   ('tciw', True),
    'QSNOW':  ('tcsw', True),
    'QGRAUP': (None,   True),      # in tcw, never published on its own
}

# The converter's bands, as fractions of surface pressure.
BANDS = {'lcc': (1.00, 0.80), 'mcc': (0.80, 0.45), 'hcc': (0.45, 0.00)}

SPREAD = ['2024-01-15T12', '2024-04-15T12', '2024-07-15T12', '2024-10-15T12']
CHUNK = 160          # south_north rows per pass; 49x160x1641 float64 = 103 MB


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
                    for name in ('paramId', 'units', 'name', 'typeOfLevel',
                                 'level', 'stepType', 'stepRange',
                                 'bitmapPresent', 'packingType',
                                 'bitsPerValue', 'typeOfFirstFixedSurface',
                                 'typeOfSecondFixedSurface'):
                        try:
                            k[name] = eccodes.codes_get(gid, name)
                        except Exception as exc:          # noqa: BLE001
                            k[name] = f'<{type(exc).__name__}>'
                    keys[s] = k
            finally:
                eccodes.codes_release(gid)
    return (out, keys) if with_keys else out


def overlap(frac):
    """Maximum-random overlap, restated. frac is (nz, ny, nx), k=0 at the ground."""
    clear = 1.0 - frac[0]
    prev = frac[0]
    for k in range(1, frac.shape[0]):
        cur = frac[k]
        clear = clear * (1.0 - np.maximum(cur, prev)) / np.maximum(1.0 - prev, 1e-6)
        prev = cur
    return np.clip(1.0 - clear, 0.0, 1.0)


def _stats(a):
    a = np.asarray(a, dtype=float).ravel()
    return {'n': int(a.size), 'min': float(np.min(a)), 'max': float(np.max(a)),
            'mean': float(np.mean(a)), 'std': float(np.std(a))}


def _cmp(ours, ref, name):
    d = ours - ref
    denom = float(np.sum(ref))
    return {
        'field': name,
        'mean_ours': float(np.mean(ours)),
        'mean_ref': float(np.mean(ref)),
        'ratio_means': float(np.mean(ours) / np.mean(ref)) if np.mean(ref) else None,
        'domain_ratio': float(np.sum(ours) / denom) if denom else None,
        'bias': float(np.mean(d)),
        'rmse': float(np.sqrt(np.mean(d ** 2))),
        'absmax': float(np.max(np.abs(d))),
        'p99_abs': float(np.percentile(np.abs(d), 99)),
    }


# ---------------------------------------------------------------------------
# the vertical integrals
# ---------------------------------------------------------------------------

_INT_CACHE = {}


def integrals(timestep):
    """Exact dry-mass columns, the converter's rule restated, and the pieces."""
    if timestep in _INT_CACHE:
        return _INT_CACHE[timestep]
    from netCDF4 import Dataset
    nc = Dataset(H.wrfout_path(timestep))
    dnw = np.abs(np.asarray(nc.variables['DNW'][0], dtype=np.float64))   # (nz,)
    nz = dnw.size
    ny = len(nc.dimensions['south_north'])
    ptop = float(np.asarray(nc.variables['P_TOP'][0]))

    names = list(SPECIES)
    exact = {n: np.empty(ny, dtype=np.float64) for n in names}     # row sums
    conv = {n: np.empty(ny, dtype=np.float64) for n in names}
    trap = {n: np.empty(ny, dtype=np.float64) for n in names}
    sliver = {n: np.empty(ny, dtype=np.float64) for n in names}
    topbit = {n: np.empty(ny, dtype=np.float64) for n in names}
    # full 2-D fields we will compare against the GRIB
    f_exact = {n: np.empty((ny, len(nc.dimensions['west_east']))) for n in names}
    f_conv = {n: np.empty_like(f_exact[names[0]]) for n in names}
    f_full = {n: np.empty_like(f_exact[names[0]]) for n in names}

    psfc_err = []
    lev_in_band = np.zeros((len(BANDS), nz), dtype=np.int64)
    band_names = list(BANDS)

    for j0 in range(0, ny, CHUNK):
        j1 = min(j0 + CHUNK, ny)
        sl = (0, slice(None), slice(j0, j1), slice(None))
        mu = (np.asarray(nc.variables['MU'][0, j0:j1], dtype=np.float64)
              + np.asarray(nc.variables['MUB'][0, j0:j1], dtype=np.float64))
        psfc = np.asarray(nc.variables['PSFC'][0, j0:j1], dtype=np.float64)
        p = (np.asarray(nc.variables['P'][sl], dtype=np.float64)
             + np.asarray(nc.variables['PB'][sl], dtype=np.float64))
        q = {n: np.asarray(nc.variables[n][sl], dtype=np.float64) for n in names}
        rtot = sum(q.values())
        moist = 1.0 / (1.0 + rtot)

        # -- dry mass of each layer, exactly as WRF carries it ---------------
        dm = dnw[:, None, None] * mu[None, :, :] / G            # kg/m2 per layer
        # -- the converter's dp: mass-level differences, top layer zeroed -----
        dp = np.abs(np.diff(p, axis=0))
        dp = np.concatenate([dp, np.zeros_like(dp[-1:])], axis=0)
        # -- the two pieces the converter's range leaves out -----------------
        dp_sliver = psfc - p[0]                                  # ground to level 0
        dp_top = p[-1] - ptop                                    # level 48 to model top

        # mass budget: rebuild PSFC from the layer masses
        dp_moist = dnw[:, None, None] * mu[None, :, :] * (1.0 + rtot)
        psfc_rebuilt = ptop + np.sum(dp_moist, axis=0)
        psfc_err.append((float(np.mean(psfc_rebuilt - psfc)),
                         float(np.max(np.abs(psfc_rebuilt - psfc)))))

        for n in names:
            spec = q[n] * moist                                  # specific content
            e = np.sum(q[n] * dm, axis=0)                        # EXACT
            c = np.sum(spec * dp, axis=0) / G                    # the converter
            t = np.sum(0.5 * (spec[:-1] + spec[1:]) * dp[:-1], axis=0) / G
            s = spec[0] * dp_sliver / G
            tb = spec[-1] * dp_top / G
            exact[n][j0:j1] = np.sum(e, axis=1)
            conv[n][j0:j1] = np.sum(c, axis=1)
            trap[n][j0:j1] = np.sum(t, axis=1)
            sliver[n][j0:j1] = np.sum(s, axis=1)
            topbit[n][j0:j1] = np.sum(tb, axis=1)
            f_exact[n][j0:j1] = e
            f_conv[n][j0:j1] = c
            f_full[n][j0:j1] = t + s + tb

        sigma = p / psfc[None, :, :]
        for bi, bn in enumerate(band_names):
            hi, lo = BANDS[bn]
            lev_in_band[bi] += np.sum((sigma <= hi) & (sigma > lo),
                                      axis=(1, 2)).astype(np.int64)
        del p, q, rtot, moist, dm, dp, sigma, dp_moist
    npoints = ny * len(nc.dimensions['west_east'])
    nc.close()
    result = {
        'nz': nz, 'npoints': npoints, 'ptop': ptop,
        'dnw_sum': float(np.sum(dnw)),
        'psfc_rebuild_bias': float(np.mean([a for a, _ in psfc_err])),
        'psfc_rebuild_absmax': float(max(b for _, b in psfc_err)),
        'levels_per_band': {bn: lev_in_band[bi].tolist()
                            for bi, bn in enumerate(band_names)},
        'means': {n: {'exact': float(exact[n].sum() / npoints),
                      'converter': float(conv[n].sum() / npoints),
                      'trapezoid': float(trap[n].sum() / npoints),
                      'sliver': float(sliver[n].sum() / npoints),
                      'top': float(topbit[n].sum() / npoints)}
                  for n in names},
        'fields': (f_exact, f_conv, f_full),
    }
    _INT_CACHE[timestep] = result
    return result


def clouds(timestep):
    """CLDFRA, the two bounds on tcc, and a second implementation of the overlap."""
    from netCDF4 import Dataset
    nc = Dataset(H.wrfout_path(timestep))
    ny = len(nc.dimensions['south_north'])
    nx = len(nc.dimensions['west_east'])
    out = {k: np.empty((ny, nx)) for k in ('tcc', 'lcc', 'mcc', 'hcc',
                                           'maxlayer', 'randomall')}
    hist = np.zeros(11, dtype=np.int64)
    n_gt1 = n_lt0 = 0
    for j0 in range(0, ny, CHUNK):
        j1 = min(j0 + CHUNK, ny)
        sl = (0, slice(None), slice(j0, j1), slice(None))
        raw = np.asarray(nc.variables['CLDFRA'][sl], dtype=np.float64)
        n_gt1 += int(np.sum(raw > 1.0))
        n_lt0 += int(np.sum(raw < 0.0))
        c = np.clip(raw, 0.0, 1.0)
        hist += np.histogram(c, bins=np.linspace(0, 1, 12))[0].astype(np.int64)
        out['tcc'][j0:j1] = overlap(c)
        out['maxlayer'][j0:j1] = np.max(c, axis=0)
        out['randomall'][j0:j1] = 1.0 - np.prod(1.0 - c, axis=0)
        p = (np.asarray(nc.variables['P'][sl], dtype=np.float64)
             + np.asarray(nc.variables['PB'][sl], dtype=np.float64))
        psfc = np.asarray(nc.variables['PSFC'][0, j0:j1], dtype=np.float64)
        sigma = p / psfc[None, :, :]
        for bn, (hi, lo) in BANDS.items():
            band = (sigma <= hi) & (sigma > lo)
            out[bn][j0:j1] = overlap(np.where(band, c, 0.0))
        del raw, c, p, sigma
    nc.close()
    return out, hist, n_gt1, n_lt0


# ---------------------------------------------------------------------------
# the measurements
# ---------------------------------------------------------------------------

def m_massint(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        r = integrals(ts)
        f_exact, f_conv, f_full = r['fields']
        entry = {'timestep': ts, 'against_grib': [], 'attribution': [],
                 **{k: v for k, v in r.items() if k != 'fields'}}
        for wrfname, (short, _) in SPECIES.items():
            m = r['means'][wrfname]
            entry['attribution'].append({
                'species': wrfname, 'published_as': short,
                'exact': m['exact'], 'converter': m['converter'],
                'converter_minus_exact': m['converter'] - m['exact'],
                'relative_error': ((m['converter'] - m['exact']) / m['exact']
                                   if m['exact'] else None),
                'missing_below_level0': m['sliver'],
                'missing_above_level48': m['top'],
                'endpoint_rule': m['converter'] - m['trapezoid'],
                'trapezoid_plus_both_ends': m['trapezoid'] + m['sliver'] + m['top'],
                'full_rule_minus_exact': (m['trapezoid'] + m['sliver'] + m['top']
                                          - m['exact']),
            })
            if short and short in got:
                entry['against_grib'].append({
                    'shortName': short,
                    'vs_converter_rule': _cmp(got[short], f_conv[wrfname],
                                              f'{short} grib vs converter rule'),
                    'vs_exact': _cmp(got[short], f_exact[wrfname],
                                     f'{short} grib vs exact dry-mass'),
                })
        # tcw against the exact sum of all six species
        if 'tcw' in got:
            tot_exact = sum(f_exact[n] for n in SPECIES)
            tot_conv = sum(f_conv[n] for n in SPECIES)
            entry['against_grib'].append({
                'shortName': 'tcw',
                'vs_converter_rule': _cmp(got['tcw'], tot_conv, 'tcw grib vs converter rule'),
                'vs_exact': _cmp(got['tcw'], tot_exact, 'tcw grib vs exact dry-mass'),
            })
        rows.append(entry)
    return rows


def m_closure(steps):
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        parts = sum(got[k] for k in ('tcwv', 'tclw', 'tciw', 'tcrw', 'tcsw'))
        resid = got['tcw'] - parts
        r = integrals(ts)
        f_exact, _, _ = r['fields']
        graupel = f_exact['QGRAUP']
        rows.append({
            'timestep': ts,
            'residual': _stats(resid),
            'graupel_exact': _stats(graupel),
            'residual_vs_graupel': _cmp(resid, graupel, 'tcw residual vs graupel'),
            'n_residual_negative': int(np.sum(resid < -1e-6)),
            'n_residual_gt_1e_3': int(np.sum(np.abs(resid) > 1e-3)),
        })
    return rows


def m_cloud(steps):
    rows = []
    for ts in steps:
        got, keys = read_family(H.grib_path(ts), with_keys=True)
        ours, hist, n_gt1, n_lt0 = clouds(ts)
        tcc = got['tcc']
        entry = {
            'timestep': ts,
            'cldfra_histogram': hist.tolist(),
            'cldfra_above_one': n_gt1, 'cldfra_below_zero': n_lt0,
            'bounds': {
                'n_below_max_layer': int(np.sum(tcc < ours['maxlayer'] - 1e-6)),
                'worst_below_max_layer': float(np.max(ours['maxlayer'] - tcc)),
                'n_above_random': int(np.sum(tcc > ours['randomall'] + 1e-6)),
                'worst_above_random': float(np.max(tcc - ours['randomall'])),
                'mean_max_layer': float(np.mean(ours['maxlayer'])),
                'mean_random': float(np.mean(ours['randomall'])),
                'mean_tcc': float(np.mean(tcc)),
            },
            'recomputed': {k: _cmp(got[k], ours[k], f'{k} grib vs recomputed')
                           for k in ('tcc', 'lcc', 'mcc', 'hcc')},
            'bands_vs_total': {
                'n_tcc_below_band_max': int(np.sum(
                    tcc < np.maximum.reduce([got['lcc'], got['mcc'], got['hcc']]) - 1e-6)),
                'n_tcc_above_band_random': int(np.sum(
                    tcc > 1.0 - (1 - got['lcc']) * (1 - got['mcc']) * (1 - got['hcc']) + 1e-6)),
                'mean_band_random': float(np.mean(
                    1.0 - (1 - got['lcc']) * (1 - got['mcc']) * (1 - got['hcc']))),
            },
            'keys': {k: keys[k] for k in ('tcc', 'lcc', 'mcc', 'hcc') if k in keys},
        }
        rows.append(entry)
    return rows


def m_bands(steps):
    rows = []
    for ts in steps:
        r = integrals(ts)
        rows.append({'timestep': ts, 'levels_per_band': r['levels_per_band'],
                     'npoints': r['npoints'], 'nz': r['nz']})
    return rows


def m_encoding(steps):
    rows = []
    for ts in steps:
        _, keys = read_family(H.grib_path(ts), with_keys=True)
        rows.append({'timestep': ts, 'keys': keys})
    return rows



def m_lccdiff(steps):
    """Where the recomputed lcc parts company with the published one, and why.

    The recomputation above is the converter's own formula, so a disagreement
    can only come from the arithmetic and not from the algorithm. The converter
    works in float32, because that is what wrf-python hands back; this repeats
    the overlap in both precisions and reports which one the GRIB followed.
    """
    from netCDF4 import Dataset
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        nc = Dataset(H.wrfout_path(ts))
        ny = len(nc.dimensions['south_north'])
        nx = len(nc.dimensions['west_east'])
        d64 = np.empty((ny, nx))
        d32 = np.empty((ny, nx))
        worst = []
        for j0 in range(0, ny, CHUNK):
            j1 = min(j0 + CHUNK, ny)
            sl = (0, slice(None), slice(j0, j1), slice(None))
            c_raw = np.asarray(nc.variables['CLDFRA'][sl], dtype=np.float32)
            p_raw = (np.asarray(nc.variables['P'][sl], dtype=np.float32)
                     + np.asarray(nc.variables['PB'][sl], dtype=np.float32))
            psfc = np.asarray(nc.variables['PSFC'][0, j0:j1], dtype=np.float32)
            sig32 = p_raw / psfc[None, :, :]
            hi, lo = BANDS['lcc']
            band32 = (sig32 <= hi) & (sig32 > lo)
            f32 = overlap(np.where(band32, np.clip(c_raw, 0.0, 1.0), np.float32(0.0)))
            c64 = np.clip(c_raw.astype(np.float64), 0.0, 1.0)
            sig64 = p_raw.astype(np.float64) / psfc.astype(np.float64)[None, :, :]
            band64 = (sig64 <= hi) & (sig64 > lo)
            f64 = overlap(np.where(band64, c64, 0.0))
            d32[j0:j1] = f32
            d64[j0:j1] = f64
            diff = np.abs(f64 - got['lcc'][j0:j1])
            for jj, ii in zip(*np.where(diff > 1e-3)):
                col = c64[:, jj, ii]
                inb = np.where(band64[:, jj, ii])[0]
                worst.append({
                    'j': int(j0 + jj), 'i': int(ii),
                    'grib': float(got['lcc'][j0 + jj, ii]),
                    'float64': float(f64[jj, ii]), 'float32': float(f32[jj, ii]),
                    'band_levels': inb.tolist(),
                    'cldfra_in_band': [float(x) for x in col[inb]],
                    'max_in_band': float(col[inb].max()) if inb.size else None,
                    'n_at_one': int(np.sum(col[inb] == 1.0)),
                    'closest_to_one': float(np.max(col[inb])) if inb.size else None,
                })
            del c_raw, p_raw, sig32, sig64, band32, band64, c64
        nc.close()
        rows.append({
            'timestep': ts,
            'n_diff_gt_1e_3_float64': int(np.sum(np.abs(d64 - got['lcc']) > 1e-3)),
            'n_diff_gt_1e_3_float32': int(np.sum(np.abs(d32 - got['lcc']) > 1e-3)),
            'absmax_float64': float(np.max(np.abs(d64 - got['lcc']))),
            'absmax_float32': float(np.max(np.abs(d32 - got['lcc']))),
            'rmse_float64': float(np.sqrt(np.mean((d64 - got['lcc']) ** 2))),
            'rmse_float32': float(np.sqrt(np.mean((d32 - got['lcc']) ** 2))),
            'points': sorted(worst, key=lambda r: -abs(r['float64'] - r['grib']))[:12],
        })
    return rows



def m_legc_exact(steps):
    """Leg C run twice: on the published message, and on the exact integral.

    The harness already reports how far each column integral sits from ERA5.
    What it cannot say is how much of that distance is the quadrature and how
    much is the model. Running the SAME upscaling and the SAME ERA5 counterpart
    against the exact dry-mass integral answers it directly, with no arithmetic
    of mine in between.
    """
    rows = []
    for ts in steps:
        got = read_family(H.grib_path(ts))
        r = integrals(ts)
        f_exact, _, _ = r['fields']
        ctx = H.Context(ts)
        entry = {'timestep': ts, 'era5_ok': bool(ctx.era5_ok), 'fields': []}
        if ctx.era5_ok:
            pairs = [('tcwv', 'QVAPOR'), ('tclw', 'QCLOUD'), ('tciw', 'QICE'),
                     ('tcrw', 'QRAIN'), ('tcsw', 'QSNOW')]
            exact_map = {short: f_exact[wrf] for short, wrf in pairs}
            exact_map['tcw'] = sum(f_exact[n] for n in SPECIES)
            for short in ('tcwv', 'tcw', 'tclw', 'tciw', 'tcrw', 'tcsw'):
                token = short   # the harness keys family 3 by shortName, not by registry key
                pub = H.leg_c(token, {'values': got[short]}, ctx)
                exa = H.leg_c(token, {'values': exact_map[short]}, ctx)
                if not pub.get('available'):
                    continue
                entry['fields'].append({
                    'shortName': short,
                    'published': {k: pub['regions'][k] for k in ('all', 'land', 'sea')},
                    'exact': {k: exa['regions'][k] for k in ('all', 'land', 'sea')},
                })
        rows.append(entry)
        _INT_CACHE.pop(ts, None)
    return rows


MEASURES = {
    'massint': m_massint,
    'closure': m_closure,
    'cloud': m_cloud,
    'bands': m_bands,
    'encoding': m_encoding,
    'lccdiff': m_lccdiff,
    'legc_exact': m_legc_exact,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--measure', action='append', choices=sorted(MEASURES))
    ap.add_argument('--timestep', action='append')
    ap.add_argument('--out')
    args = ap.parse_args()
    steps = args.timestep or SPREAD
    todo = args.measure or sorted(MEASURES)
    out = {}
    for name in todo:
        print(f'--- {name} ---', flush=True)
        out[name] = MEASURES[name](steps)
        print(json.dumps(out[name], indent=1)[:6000], flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))
        print(f'wrote {args.out}')


if __name__ == '__main__':
    main()
