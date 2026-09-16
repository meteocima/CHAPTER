#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convert one hourly WRF wrfout to an ECMWF-compatible GRIB2 file.

Usage:
    python convert_to_pressure_levels.py --input <wrfout_file> --output <grib_file>
    python convert_to_pressure_levels.py --input <wrfout> --output <grib> --debug-vars T2 tk

What is produced, and on which level, is entirely described by
WRF_TO_ECMWF_PARAMID in wrf_era5_comparison.py: this module only knows how to
compute each field and how to hand it to eccodes.

GRIB2 rather than GRIB1: several of the required parameters (2r, tirf, mucape,
mucin, wz) have no GRIB1 representation at all, and GRIB1 cannot declare the
spherical earth WRF integrates on -- doing so removes a ~1.1 km geolocation
error at the northern edge of the domain.
"""

import argparse
import os
import sys

import numpy as np
from netCDF4 import Dataset
import wrf
import pandas as pd
from eccodes import (codes_grib_new_from_samples, codes_set, codes_set_values,
                     codes_write, codes_release)

from wrf_era5_comparison import WRF_TO_ECMWF_PARAMID, PRESSURE_LEVELS, EXPECTED_MESSAGES
# Accumulated fields are referred to 00Z of the same day (see accum_ref.py)
import accum_ref

G = 9.80665                 # m/s^2, standard gravity (geopotential)
WRF_EARTH_RADIUS = 6370000  # m, the sphere WRF integrates on
MISSING = 9999.0            # GRIB missing-value sentinel, paired with a bitmap
PACKING = 'grid_ccsds'      # lossless; ~same size as second-order, much faster

# Multiplicative factor applied to a native field (after the 00Z subtraction,
# where one applies) to reach the units its ECMWF parameter is defined in.
UNIT_SCALE = {
    'HGT': G,           # m -> m^2/s^2
    'SNOW': 1e-3,       # kg/m^2 -> m of water equivalent
    'CANWAT': 1e-3,     # kg/m^2 -> m of water equivalent
    'VEGFRA': 1e-2,     # %      -> (0-1)
    'RAINNC': 1e-3,     # mm     -> m
    'SNOWNC': 1e-3,     # mm     -> m
    'SFROFF': 1e-3,     # mm     -> m
    'UDROFF': 1e-3,     # mm     -> m
    'ACSNOM': 1e-3,     # kg/m^2 -> m of water equivalent
}

# Cloud bands, as fractions of surface pressure (ECMWF convention).
CLOUD_BANDS = {'lcc': (1.00, 0.80), 'mcc': (0.80, 0.45), 'hcc': (0.45, 0.00)}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a WRF wrfout to ECMWF-compatible GRIB2")
    parser.add_argument("--input", required=True, help="Path to wrfout NetCDF file")
    parser.add_argument("--output", required=True, help="Output GRIB2 file path")
    parser.add_argument(
        "--debug-vars", nargs="*", default=[],
        help="Limit processing to these registry keys only (default: all)")
    parser.add_argument(
        "--accum-ref-dir", default=None,
        help="Directory of 00Z reference sidecars for accumulated fields (accum_ref.py). "
             "Without it, the 00Z wrfout must sit next to --input")
    return parser.parse_args()


# ============================================================================
# GRIB2 writing
# ============================================================================

def _set_grid(gid, grid):
    codes_set(gid, 'gridType', 'mercator')
    # WRF integrates on a sphere of radius 6370 km. Declaring it explicitly
    # brings the grid eccodes derives to within ~2 m of the WRF coordinates;
    # with the default earth shape the northern edge is off by ~1.1 km.
    codes_set(gid, 'shapeOfTheEarth', 1)
    codes_set(gid, 'scaleFactorOfRadiusOfSphericalEarth', 0)
    codes_set(gid, 'scaledValueOfRadiusOfSphericalEarth', WRF_EARTH_RADIUS)
    codes_set(gid, 'Ni', grid['ni'])
    codes_set(gid, 'Nj', grid['nj'])
    codes_set(gid, 'latitudeOfFirstGridPointInDegrees', grid['lat0'])
    codes_set(gid, 'longitudeOfFirstGridPointInDegrees', grid['lon0'])
    codes_set(gid, 'latitudeOfLastGridPointInDegrees', grid['lat1'])
    codes_set(gid, 'longitudeOfLastGridPointInDegrees', grid['lon1'])
    codes_set(gid, 'LaDInDegrees', grid['truelat1'])
    codes_set(gid, 'DiInMetres', grid['dx'])
    codes_set(gid, 'DjInMetres', grid['dy'])
    codes_set(gid, 'orientationOfTheGridInDegrees', 0.0)
    # Row 0 of a WRF array is the southernmost one.
    codes_set(gid, 'jScansPositively', 1)
    codes_set(gid, 'iScansNegatively', 0)


def _set_time(gid, info, valid):
    """Instantaneous by default; statistically processed fields use template 8.

    'accum' fields are accumulated from 00Z of the same day, so the reference
    time is that 00Z and the step runs 0..H. 'max1h' fields (the 10 m wind
    maximum, which WRF resets at every output) cover the preceding hour only.
    Either way validityDate/validityTime resolve to this timestep.
    """
    step = info.get('stepType')
    if step is None:
        codes_set(gid, 'dataDate', int(valid.strftime('%Y%m%d')))
        codes_set(gid, 'dataTime', int(valid.strftime('%H%M')))
        codes_set(gid, 'startStep', 0)
        codes_set(gid, 'endStep', 0)
        return

    if step == 'accum':
        ref, end = valid.normalize(), valid.hour
    elif step == 'max1h':
        ref, end = valid - pd.Timedelta(hours=1), 1
    else:
        raise ValueError(f"unknown stepType {step!r}")

    codes_set(gid, 'productDefinitionTemplateNumber', 8)
    codes_set(gid, 'dataDate', int(ref.strftime('%Y%m%d')))
    codes_set(gid, 'dataTime', int(ref.strftime('%H%M')))
    codes_set(gid, 'stepUnits', 'h')
    codes_set(gid, 'startStep', 0)
    codes_set(gid, 'endStep', end)


def write_message(fout, values, info, level, grid, valid):
    """Write one 2D field as a single GRIB2 message."""
    gid = codes_grib_new_from_samples('GRIB2')
    try:
        _set_time(gid, info, valid)
        _set_grid(gid, grid)
        # paramId first: it carries the level type the definition prescribes,
        # which an explicit typeOfLevel then overrides where we want one.
        codes_set(gid, 'paramId', info['paramId'])
        if info['levelType'] is not None:
            codes_set(gid, 'typeOfLevel', info['levelType'])
            codes_set(gid, 'level', int(level))
        if info.get('stepType') == 'accum':
            # Marker kept from the GRIB1 schema: accumulation referred to 00Z.
            codes_set(gid, 'generatingProcessIdentifier', accum_ref.ACCUM_FROM_00Z_GENPROC)

        flat = np.asarray(values, dtype=np.float64).ravel()
        if np.isnan(flat).any():
            codes_set(gid, 'missingValue', MISSING)
            codes_set(gid, 'bitmapPresent', 1)
            flat = np.where(np.isnan(flat), MISSING, flat)
        codes_set_values(gid, flat)
        codes_set(gid, 'packingType', PACKING)
        codes_write(gid, fout)
    finally:
        codes_release(gid)


# ============================================================================
# main
# ============================================================================

def main(input_file, output_file, debug_vars=None, accum_ref_dir=None):
    debug_vars = debug_vars or []

    def want(key):
        """Is this registry key to be produced in this run?"""
        return key in WRF_TO_ECMWF_PARAMID and (not debug_vars or key in debug_vars)

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    print(f"Opening file: {input_file}")
    ncfile = Dataset(input_file)

    if ncfile.MAP_PROJ != 3:
        raise ValueError(f"Expected Mercator (MAP_PROJ=3), got {ncfile.MAP_PROJ}")

    lat_2d = wrf.getvar(ncfile, "lat").values
    lon_2d = wrf.getvar(ncfile, "lon").values
    grid = {
        'nj': lat_2d.shape[0], 'ni': lat_2d.shape[1],
        'lat0': float(lat_2d[0, 0]), 'lon0': float(lon_2d[0, 0]),
        'lat1': float(lat_2d[-1, -1]), 'lon1': float(lon_2d[-1, -1]),
        'truelat1': float(ncfile.TRUELAT1),
        'dx': float(ncfile.DX), 'dy': float(ncfile.DY),
    }
    dx, dy = grid['dx'], grid['dy']
    valid = pd.Timestamp(wrf.extract_times(ncfile, timeidx=wrf.ALL_TIMES)[0])
    print(f"Grid {grid['ni']}x{grid['nj']}, timestep {valid}")

    # Shared by every 3D diagnostic; read once instead of once per getvar call.
    # Skipped when the run only asks for plain 2D fields, so that a --debug-vars
    # check on a surface variable stays a few seconds instead of reading 2.6 GB.
    flat_only = all(WRF_TO_ECMWF_PARAMID[k]['levelType'] in ('surface', 'heightAboveGround')
                    and k in ncfile.variables
                    for k in WRF_TO_ECMWF_PARAMID if want(k))
    cache = {} if flat_only else wrf.extract_vars(
        ncfile, 0, ('P', 'PB', 'PH', 'PHB', 'T', 'QVAPOR', 'PSFC', 'HGT'))
    print(f"Shared cache: {'skipped (2D-only run)' if flat_only else sorted(cache)}")

    def gv(name, **kwargs):
        return wrf.getvar(ncfile, name, timeidx=0, cache=cache, **kwargs)

    def to_levels(field):
        """Interpolate a mass-point 3D field onto the pressure levels."""
        return wrf.vinterp(ncfile, field=field, vert_coord="pressure",
                           interp_levels=PRESSURE_LEVELS, extrapolate=True,
                           timeidx=0, cache=cache).values

    out = {}

    def emit(key, values, note=""):
        out[key] = values
        a = np.asarray(values, dtype=float)
        finite = a[np.isfinite(a)]
        rng = f"{finite.min():.4g}..{finite.max():.4g}" if finite.size else "all-missing"
        print(f"  {key:10s} -> {WRF_TO_ECMWF_PARAMID[key]['shortName']:7s} {rng} {note}")

    # ---------------- land / ocean mask -------------------------------------
    landmask = gv("LANDMASK").values
    ocean = (landmask == 0)

    # ---------------- 00Z reference for accumulated fields ------------------
    # Loaded outside any try/except: a missing reference must abort the run
    # rather than silently produce run-init-referred accumulations.
    accum_keys = [k for k, v in WRF_TO_ECMWF_PARAMID.items()
                  if v.get('stepType') == 'accum' and (not debug_vars or k in debug_vars)]
    # tirf and tsr are combinations, so ask for the native fields they need.
    needed = set()
    for k in accum_keys:
        needed.update({'tirf': ('RAINNC', 'SNOWNC', 'GRAUPELNC'),
                       'tsr': ('ACSWDNT', 'ACSWUPT')}.get(k, (k,)))
    needed = sorted(n for n in needed if n in ncfile.variables)
    accum_00z = {}
    if needed:
        print("\n=== 00Z REFERENCE FOR ACCUMULATED FIELDS ===")
        if valid.hour == 0:
            fields, meta = accum_ref.extract_from_wrfout(input_file)
            accum_00z = {v: fields[v] for v in needed}
            if accum_ref_dir:
                sidecar = accum_ref.ref_path(accum_ref_dir, valid)
                if not os.path.isfile(sidecar):
                    accum_ref.write_ref(sidecar, fields, meta)
                    print(f"  wrote 00Z sidecar: {sidecar}")
            print(f"  input is 00Z: {needed} are zero by construction")
        else:
            accum_00z, src = accum_ref.get_reference(
                input_file, valid, needed,
                sim_start=getattr(ncfile, 'SIMULATION_START_DATE', None),
                ref_dir=accum_ref_dir)
            print(f"  {needed} referred to 00Z from {src}")

    def since_00z(name):
        """Native accumulated field, referred to 00Z of the same day."""
        return np.asarray(ncfile.variables[name][0], dtype=float) - accum_00z[name]

    # ---------------- native fields -----------------------------------------
    print("\n=== NATIVE FIELDS ===")
    for key in [k for k in WRF_TO_ECMWF_PARAMID if k in ncfile.variables]:
        if not want(key):
            continue
        info = WRF_TO_ECMWF_PARAMID[key]
        try:
            if info['levelType'] == 'isobaricInhPa':
                data = gv(key)
                dims = ncfile.variables[key].dimensions
                if 'bottom_top_stag' in dims:
                    data = wrf.destagger(data, stagger_dim=-3)
                elif 'west_east_stag' in dims:
                    data = wrf.destagger(data, stagger_dim=-1)
                elif 'south_north_stag' in dims:
                    data = wrf.destagger(data, stagger_dim=-2)
                values = to_levels(data)
                if key in ('QCLOUD', 'QICE'):
                    values = np.maximum(values, 0.0)
                emit(key, values, "(pressure levels)")
                continue

            if info.get('stepType') == 'accum':
                values = since_00z(key)
                low = np.nanmin(values)
                if low < 0:
                    # A GRIB-sourced reference carries ~1e-8 of packing noise;
                    # clip only that, so a real negative stays visible.
                    if low < -1e-3:
                        print(f"  WARNING: {key} minus 00Z reaches {low:.3e}")
                    values = np.where(values < 0, 0.0, values)
            else:
                values = np.asarray(gv(key).values, dtype=float)

            if key == 'VAR_SSO':
                values = np.sqrt(values)          # variance -> standard deviation
            elif key == 'SST':
                values = np.where(ocean, values, np.nan)
            values = values * UNIT_SCALE.get(key, 1.0)
            emit(key, values)
        except Exception as exc:                  # noqa: BLE001 - reported below
            print(f"  {key}: FAILED: {exc}")

    # ---------------- derived, pressure levels ------------------------------
    print("\n=== DERIVED (pressure levels) ===")
    for key in ('tk', 'z', 'rh', 'omega', 'wa'):
        if not want(key):
            continue
        try:
            values = to_levels(gv(key))
            if key == 'z':
                values = values * G           # geopotential height -> geopotential
            emit(key, values)
        except Exception as exc:
            print(f"  {key}: FAILED: {exc}")

    if want('q'):
        try:
            mr = np.maximum(to_levels(gv("QVAPOR")), 0.0)   # mixing ratio
            emit('q', mr / (1.0 + mr), "(mixing ratio -> specific humidity)")
        except Exception as exc:
            print(f"  q: FAILED: {exc}")

    # ---------------- derived, single level ---------------------------------
    print("\n=== DERIVED (single level) ===")
    # wrf-python defaults to degC for dewpoint and hPa for sea level pressure;
    # ask it for the units the ECMWF parameters are defined in. (The GRIB1
    # archive wrote 2d straight through, so its 2d is in degC under paramId 168.)
    for key, kwargs in (('td2', dict(units='K')), ('rh2', {}), ('slp', dict(units='Pa'))):
        if not want(key):
            continue
        try:
            emit(key, np.asarray(gv(key, **kwargs).values, dtype=float))
        except Exception as exc:
            print(f"  {key}: FAILED: {exc}")

    if want('skt'):
        try:
            # LWUPB = emissivity * sigma * T^4
            lwupb = gv("LWUPB").values
            emit('skt', (lwupb / (0.98 * 5.67e-8)) ** 0.25)
        except Exception as exc:
            print(f"  skt: FAILED: {exc}")

    if want('slor'):
        try:
            gy, gx = np.gradient(gv("HGT").values, dy, dx)
            emit('slor', np.sqrt(gx ** 2 + gy ** 2))
        except Exception as exc:
            print(f"  slor: FAILED: {exc}")

    if want('rsn'):
        try:
            swe = gv("SNOW").values          # kg/m^2
            depth = gv("SNOWH").values       # m
            # ERA5 reports the fresh-snow default where there is no snow pack.
            emit('rsn', np.where(depth > 1e-6, swe / np.maximum(depth, 1e-6), 100.0))
        except Exception as exc:
            print(f"  rsn: FAILED: {exc}")

    # Soil: RUC's first four levels mapped onto the ERA5 layer names.
    for native, prefix in (('SMOIS', 'SMOIS'), ('TSLB', 'TSLB')):
        keys = [f'{prefix}{i}' for i in range(1, 5)]
        if not any(want(k) for k in keys):
            continue
        try:
            layers = np.asarray(ncfile.variables[native][0], dtype=float)
            for i, key in enumerate(keys):
                if want(key):
                    emit(key, layers[i])
        except Exception as exc:
            print(f"  {native}: FAILED: {exc}")

    if want('tirf'):
        try:
            rain = since_00z('RAINNC') - since_00z('SNOWNC') - since_00z('GRAUPELNC')
            emit('tirf', np.where(rain < 0, 0.0, rain), "(rain only, mm)")
        except Exception as exc:
            print(f"  tirf: FAILED: {exc}")

    if want('tsr'):
        try:
            emit('tsr', since_00z('ACSWDNT') - since_00z('ACSWUPT'), "(net SW at top)")
        except Exception as exc:
            print(f"  tsr: FAILED: {exc}")

    if want('mucape') or want('mucin'):
        try:
            cape = wrf.getvar(ncfile, "cape_2d", timeidx=0, cache=cache)

            def dense(arr):
                """Fill the gaps cape_2d leaves with zero.

                The Fortran flags CIN as missing wherever CAPE < 100 J/kg, and
                CAPE where the parcel has no equilibrium level -- half the
                domain on a quiet day. wrf-python surfaces that as NaN (not as
                a mask, so ma.filled would be a no-op) and sometimes as the
                9.97e36 fill value. Zero is both the physical reading (no
                available energy, no inhibition) and what keeps the field dense
                for training; see MISSING_VARIABLES.md.
                """
                a = np.asarray(arr, dtype=float)
                return np.where(np.isfinite(a) & (np.abs(a) < 1e30), a, 0.0)

            if want('mucape'):
                emit('mucape', dense(cape[0].values), "(most unstable, gaps -> 0)")
            if want('mucin'):
                emit('mucin', dense(cape[1].values), "(most unstable, gaps -> 0)")
            del cape
        except Exception as exc:
            print(f"  mucape/mucin: FAILED: {exc}")

    # ---------------- winds at fixed heights --------------------------------
    height_keys = ('u100', 'v100', 'u200', 'v200', 'vwsh')
    if any(want(k) for k in height_keys):
        try:
            zagl = gv("height_agl")
            ua, va = gv("ua"), gv("va")
            # interplevel takes metres and does not extrapolate; the lowest mass
            # level sits at ~25 m AGL so 100 m and 200 m are inside the column.
            uh = wrf.interplevel(ua, zagl, [100., 200.], meta=False)
            vh = wrf.interplevel(va, zagl, [100., 200.], meta=False)
            for key, arr in (('u100', uh[0]), ('v100', vh[0]),
                             ('u200', uh[1]), ('v200', vh[1])):
                if want(key):
                    emit(key, np.ma.filled(arr, np.nan))
            if want('vwsh'):
                du = np.ma.filled(uh[0], np.nan) - gv("U10").values
                dv = np.ma.filled(vh[0], np.nan) - gv("V10").values
                emit('vwsh', np.sqrt(du ** 2 + dv ** 2) / 90.0, "(bulk 10-100 m)")
            del zagl, ua, va, uh, vh
        except Exception as exc:
            print(f"  winds at height: FAILED: {exc}")

    # ---------------- column integrals and cloud ----------------------------
    if want('tcw') or want('tqv'):
        try:
            pres_pa = gv("pressure").values * 100.0
            dp = np.abs(np.diff(pres_pa, axis=0))
            dp = np.concatenate([dp, np.zeros_like(dp[-1:])], axis=0)
            qv = gv("QVAPOR").values
            if want('tqv'):
                emit('tqv', np.sum(qv * dp / G, axis=0))
            if want('tcw'):
                total = qv.copy()
                for name in ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP"):
                    total += gv(name).values
                emit('tcw', np.sum(total * dp / G, axis=0))
                del total
            del dp, pres_pa, qv
        except Exception as exc:
            print(f"  tcw/tqv: FAILED: {exc}")

    cloud_keys = ('tcc', 'lcc', 'mcc', 'hcc')
    if any(want(k) for k in cloud_keys):
        try:
            cldfra = np.clip(gv("CLDFRA").values, 0.0, 1.0)

            def overlap(frac):
                """Maximum-random overlap, as ECMWF/RRTMG."""
                clear = 1.0 - frac[0]
                prev = frac[0]
                for k in range(1, frac.shape[0]):
                    cur = frac[k]
                    clear = clear * (1.0 - np.maximum(cur, prev)) / np.maximum(1.0 - prev, 1e-6)
                    prev = cur
                return np.clip(1.0 - clear, 0.0, 1.0)

            if want('tcc'):
                emit('tcc', overlap(cldfra))
            if any(want(k) for k in ('lcc', 'mcc', 'hcc')):
                sigma = gv("pressure").values * 100.0 / gv("PSFC").values[None, :, :]
                for key, (hi, lo) in CLOUD_BANDS.items():
                    if want(key):
                        band = (sigma <= hi) & (sigma > lo)
                        emit(key, overlap(np.where(band, cldfra, 0.0)))
                del sigma
            del cldfra
        except Exception as exc:
            print(f"  cloud cover: FAILED: {exc}")

    # ---------------- write --------------------------------------------------
    missing = [k for k in WRF_TO_ECMWF_PARAMID if want(k) and k not in out]
    if missing:
        print(f"\nERROR: {len(missing)} field(s) could not be produced: {missing}")
        ncfile.close()
        sys.exit(1)
    if not out:
        print("\nERROR: nothing to write")
        ncfile.close()
        sys.exit(1)

    print(f"\n=== WRITING GRIB2: {output_file} ===")
    written = 0
    with open(output_file, 'wb') as fout:
        for key, data in out.items():
            info = WRF_TO_ECMWF_PARAMID[key]
            data = np.asarray(data)
            for idx, level in enumerate(info['levels']):
                field = data[idx] if data.ndim == 3 else data
                write_message(fout, field, info, level, grid, valid)
                written += 1
    ncfile.close()

    expected = EXPECTED_MESSAGES if not debug_vars else sum(
        len(WRF_TO_ECMWF_PARAMID[k]['levels']) for k in out)
    print(f"Written {written} messages (expected {expected})")
    if written != expected:
        sys.exit(f"ERROR: wrote {written} messages, expected {expected}")


if __name__ == "__main__":
    args = parse_args()
    main(args.input, args.output, args.debug_vars, args.accum_ref_dir)
