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

Adding a field is a registry entry plus, if it is derived, one block here. A
native wrfout variable needs no code at all: the pass-through loop below already
knows how to interpolate it to the pressure levels and how to refer an
accumulator to 00Z. A derived accumulator needs its native dependencies listed
in ACCUM_DEPS as well, or its 00Z reference will not be loaded.
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
# Static land fields come from a geo_em sidecar (see static_ref.py)
import static_ref

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
    'RAINNC': 1e-3,     # mm     -> m
    'SNOWNC': 1e-3,     # mm     -> m
    'SFROFF': 1e-3,     # mm     -> m
    'UDROFF': 1e-3,     # mm     -> m
    'ACSNOM': 1e-3,     # kg/m^2 -> m of water equivalent
    'SNOWC': 100.0,     # (0-1)  -> % (ERA5 reports snow cover in per cent)
}

SIGMA = 5.670374419e-8      # W m^-2 K^-4, Stefan-Boltzmann

# ---------------------------------------------------------------------------
# Soil: RUC's profile integrated onto the ERA5 layers
# ---------------------------------------------------------------------------
# RUC is a LEVEL scheme: TSLB/SMOIS are point values at these nodes and the
# profile between them is linear, so an ERA5 layer average is the exact integral
# of that interpolant. The whole ERA5 column lies inside the RUC nodes (289 cm
# is above the deepest node, 0 cm is the first one), so nothing is extrapolated.
RUC_SOIL_NODES = (0.0, 0.05, 0.20, 0.40, 1.60, 3.00)          # m, = ZS in the wrfout
ERA5_SOIL_LAYERS = ((0.0, 0.07), (0.07, 0.28), (0.28, 1.00), (1.00, 2.89))  # m


def _soil_layer_weights(nodes, layers):
    """Constant matrix W such that layer_k = sum_i W[k,i] * value_at_node_i.

    Each ERA5 layer is split at every RUC node inside it, the trapezoid rule is
    applied on each sub-interval of the linear interpolant, and the result is
    divided by the layer thickness.
    """
    z = np.asarray(nodes, dtype=float)
    w = np.zeros((len(layers), len(z)))
    for k, (a, b) in enumerate(layers):
        edges = sorted({a, b} | {float(v) for v in z if a < v < b})
        for lo, hi in zip(edges[:-1], edges[1:]):
            i = max(j for j in range(len(z) - 1) if z[j] <= lo + 1e-12)
            thick = hi - lo
            for x, share in ((lo, 0.5), (hi, 0.5)):
                f = (x - z[i]) / (z[i + 1] - z[i])
                w[k, i] += share * thick * (1.0 - f)
                w[k, i + 1] += share * thick * f
        w[k] /= (b - a)
    return w


SOIL_LAYER_WEIGHTS = _soil_layer_weights(RUC_SOIL_NODES, ERA5_SOIL_LAYERS)
assert np.allclose(SOIL_LAYER_WEIGHTS.sum(axis=1), 1.0, atol=1e-12), \
    "soil layer weights must average, not sum"

# Derived fields that need no 3D field at all, so that a --debug-vars run asking
# only for these can skip the 2.6 GB shared cache. An ALLOWLIST on purpose: a key
# forgotten here merely loads the cache it did not need, while a key wrongly
# listed would crash. The static ones come straight from the geo_em sidecar, the
# soil ones from SMOIS/TSLB.
FLAT_DERIVED = set(static_ref.STATIC_VARS) | {
    f'{prefix}{i}' for prefix in ('swvl', 'stl') for i in range(1, 5)}

# Surface emissivity by dominant land-use category: the EMISSMIN column of
# VEGPARM.TBL, section MODIFIED_IGBP_MODIS_NOAH (this run's MMINLU), indexed by
# IVGTYP. Hard-coded rather than read at runtime because the table is a WRF
# static that lives outside this repo. Measured against the two cases where the
# skin temperature is known (SST over open water, the 0 cm soil level on
# snow-free land), EMISSMIN beats both a fixed 0.98 and the green-fraction blend
# between EMISSMIN and EMISSMAX. Index 0 is unused; a category outside 1-20
# (none measured) is clipped into range.
LANDUSE_EMISS = np.array([
    0.98,        # 0  unused
    0.95, 0.95, 0.93, 0.93, 0.93,   #  1-5  forests
    0.93, 0.93, 0.93, 0.92, 0.92,   #  6-10 shrubs, savannas, grassland
    0.95, 0.92, 0.88, 0.92, 0.95,   # 11-15 wetlands, crops, urban, mosaic, snow/ice
    0.90, 0.98, 0.93, 0.92, 0.90,   # 16-20 barren, water, tundra
])

# Cloud bands, as fractions of surface pressure (ECMWF convention).
CLOUD_BANDS = {'lcc': (1.00, 0.80), 'mcc': (0.80, 0.45), 'hcc': (0.45, 0.00)}

# Net radiation, ECMWF sign convention: downward minus upward. There is no
# downward longwave at the top of the atmosphere (ACLWDNT is identically zero),
# so ttr/ttrc are just minus the upward flux and come out negative.
NET_RADIATION = {
    'ssr':  ('ACSWDNB', 'ACSWUPB'),    'ssrc': ('ACSWDNBC', 'ACSWUPBC'),
    'str':  ('ACLWDNB', 'ACLWUPB'),    'strc': ('ACLWDNBC', 'ACLWUPBC'),
    'tsr':  ('ACSWDNT', 'ACSWUPT'),    'tsrc': ('ACSWDNTC', 'ACSWUPTC'),
    'ttr':  (None, 'ACLWUPT'),         'ttrc': (None, 'ACLWUPTC'),
}

# Accumulated fields that are a combination of native accumulators: which native
# names their 00Z reference has to carry. Anything not listed references itself.
# Every name here must also be in accum_ref.ACCUMULATED_VARS, or the sidecar will
# not hold it and the conversion will abort.
ACCUM_DEPS = {
    'tirf': ('RAINNC', 'SNOWNC', 'GRAUPELNC'),
    'ro':   ('SFROFF', 'UDROFF'),
    **{k: tuple(n for n in pair if n) for k, pair in NET_RADIATION.items()},
}

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a WRF wrfout to ECMWF-compatible GRIB2")
    parser.add_argument("--input", required=True, help="Path to wrfout NetCDF file")
    parser.add_argument("--output", required=True, help="Output GRIB2 file path")
    parser.add_argument(
        "--debug-vars", nargs="*", default=[],
        help="Limit processing to these registry keys only (default: all)")
    parser.add_argument(
        "--static-ref-dir", default=None,
        help="Directory holding the geo_em static sidecar (static_ref.py). "
             "Required for the static land fields "
             + "/".join(static_ref.STATIC_VARS))
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

def main(input_file, output_file, debug_vars=None, accum_ref_dir=None,
         static_ref_dir=None):
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

    # Static land fields, loaded OUTSIDE any try/except -- the same contract as
    # the 00Z accumulation reference. A missing or mismatched sidecar must abort
    # the run rather than quietly write a file without the static block.
    static_fields = {}
    wanted_static = [k for k in static_ref.STATIC_VARS if want(k)]
    if wanted_static:
        if not static_ref_dir:
            sys.exit(f"ERROR: --static-ref-dir is required for {wanted_static}")
        static_fields, static_meta = static_ref.load_static(static_ref_dir)
        # The one guard that stops a geo_em from another domain from silently
        # poisoning the archive: every field would still encode, on the right
        # number of points, with the wrong geography.
        static_ref.assert_grid(static_meta, grid, source=input_file)
        print(f"Static sidecar: {static_ref.static_path(static_ref_dir)} "
              f"(geo_em {static_meta['source_path']})")

    # Shared by every 3D diagnostic; read once instead of once per getvar call.
    # Skipped when the run only asks for plain 2D fields, so that a --debug-vars
    # check on a surface variable stays a few seconds instead of reading 2.6 GB.
    # Derived 2D fields count as flat too (FLAT_DERIVED), otherwise asking for
    # one of them alone would read the whole 3D cache it never touches.
    flat_only = all((WRF_TO_ECMWF_PARAMID[k]['levelType'] in ('surface', 'heightAboveGround')
                     and k in ncfile.variables) or k in FLAT_DERIVED
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
    # Some are combinations, so ask for the native fields they need.
    needed = set()
    for k in accum_keys:
        needed.update(ACCUM_DEPS.get(k, (k,)))
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

    # WRF's Q* are mixing ratios, per kg of DRY air; every ECMWF water content
    # (clwc, ciwc, crwc, cswc, and the column integrals) is a SPECIFIC content,
    # per kg of MOIST air. The conversion is a division by 1 + the total water
    # mixing ratio. Measured on 2024-07-01T14: 0.8% in the median, 2.2% at most,
    # always in excess. Computed once on model levels and cached, because the
    # interpolation to pressure levels is the expensive part.
    HYDROMETEORS = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP")
    _moist_cache = {}

    def moist_factor(on_levels):
        """1 / (1 + total water mixing ratio), on model or pressure levels."""
        if on_levels not in _moist_cache:
            rtot = sum(np.asarray(gv(n).values, dtype=float) for n in HYDROMETEORS)
            _moist_cache[on_levels] = 1.0 / (1.0 + (to_levels(rtot) if on_levels else rtot))
        return _moist_cache[on_levels]

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
                if key in ('QCLOUD', 'QICE', 'QRAIN', 'QSNOW'):
                    # Advection undershoot leaves ~-1e-6 kg/kg; a mixing ratio
                    # cannot be negative and ERA5 never publishes one.
                    values = np.maximum(values, 0.0)
                    # WRF carries mixing ratios (per kg of DRY air); clwc/ciwc/
                    # crwc/cswc are SPECIFIC contents (per kg of moist air), so
                    # divide by 1 + the total water mixing ratio. Measured: the
                    # difference is 0.8% in the median and 2.2% at most, always
                    # in excess, and it is systematic.
                    values = values * moist_factor(True)
                elif key == 'CLDFRA':
                    values = np.clip(values, 0.0, 1.0)
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
            # TSK was not written out, so the skin temperature is inverted from
            # the upward longwave. WRF's radiation driver computes
            #     LWUPB = eps * sigma * T^4 + (1 - eps) * GLW
            # so BOTH the reflected downward term and a per-point emissivity are
            # needed. Validated where the answer is known exactly: over open
            # water WRF's skin temperature IS the SST (no ocean model), and this
            # inversion recovers it to 0.005 K on every file tested, summer and
            # March. Dropping the reflected term costs +1.25 K there; a fixed
            # eps = 0.98 over land costs up to 4 K on low-emissivity surfaces.
            # Against the 0 cm soil level on snow-free land the RMSE halves
            # (1.68 -> 0.98 K in July, 1.85 -> 1.03 K in March).
            lwupb, glw = gv("LWUPB").values, gv("GLW").values
            cat = np.clip(np.asarray(gv("IVGTYP").values, dtype=int), 1, len(LANDUSE_EMISS) - 1)
            eps = LANDUSE_EMISS[cat]
            emit('skt', (np.maximum(lwupb - (1.0 - eps) * glw, 1.0) / (eps * SIGMA)) ** 0.25,
                 f"(eps {eps.min():.3f}-{eps.max():.3f} by land use, reflected term included)")
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

    if want('tsn'):
        try:
            # SOILT1 is a snow temperature only where the snow pack actually
            # covers the cell; elsewhere RUC falls back to the soil/skin
            # temperature. SNOWC is not the flag its WRF description claims but
            # a cover fraction, measured ~ min(1, SWE/32mm), and the melting
            # point is respected only above 0.9: over 36 files spanning every
            # month on disk, max(SOILT1 | SNOWC > 0.9) is 273.17 K everywhere
            # (273.16 plus float32 rounding), against 282 K in the 0.5-0.9
            # mosaic band, where more than half the points sit above freezing at
            # noon, and 295-310 K on patchy or bare ground. So 0.9 it is
            # (SWE >~ 29 mm, snow depth >~ 0.2 m); everything else is missing.
            covered = gv("SNOWC").values > 0.9
            emit('tsn', np.where(covered, gv("SOILT1").values, np.nan),
                 f"(snow-covered cells only, {100 * np.mean(covered):.2f}% of the grid)")
        except Exception as exc:
            print(f"  tsn: FAILED: {exc}")

    if want('fal'):
        try:
            # All-sky albedo from the model's own fluxes. Undefined at night and
            # numerically unstable at very low sun, so it is written as a bitmap
            # below 50 W/m^2 of incoming shortwave.
            down = gv("SWDNB").values
            lit = down > 50.0
            emit('fal', np.where(lit, gv("SWUPB").values / np.where(lit, down, 1.0), np.nan),
                 f"(daytime only, {100 * np.mean(lit):.0f}% of the domain)")
        except Exception as exc:
            print(f"  fal: FAILED: {exc}")

    if want('iews') or want('inss'):
        try:
            # Surface stress from similarity theory, the same one that produced
            # UST: tau = rho u*^2, aligned with the 10 m wind.
            rho = gv("PSFC").values / (287.05 * gv("T2").values
                                       * (1.0 + 0.608 * gv("Q2").values))
            tau = rho * gv("UST").values ** 2
            u10, v10 = gv("U10").values, gv("V10").values
            speed = np.hypot(u10, v10)
            moving = speed > 1e-6
            safe = np.where(moving, speed, 1.0)
            if want('iews'):
                emit('iews', np.where(moving, tau * u10 / safe, 0.0), "(rho u*^2 along U10)")
            if want('inss'):
                emit('inss', np.where(moving, tau * v10 / safe, 0.0), "(rho u*^2 along V10)")
        except Exception as exc:
            print(f"  iews/inss: FAILED: {exc}")


    # ---------------- static land fields (geo_em sidecar) -------------------
    # Time-invariant, so they are read from a sidecar built once by static_ref.py
    # instead of opening a 2.4 GB NetCDF per timestep. tvl and dl already carry
    # NaN where they are undefined; write_message turns that into a bitmap.
    for key in wanted_static:
        try:
            emit(key, static_fields[key], "(geo_em static)")
        except Exception as exc:
            print(f"  {key}: FAILED: {exc}")

    # ---------------- soil: ERA5 layer averages of the RUC profile ----------
    soil_keys = [f'{prefix}{i}' for prefix in ('swvl', 'stl') for i in range(1, 5)]
    if any(want(k) for k in soil_keys):
        try:
            zs = np.asarray(ncfile.variables['ZS'][0], dtype=float)
            if not np.allclose(zs, RUC_SOIL_NODES, atol=1e-6):
                raise ValueError(f"soil nodes are {zs.tolist()} m, but the ERA5 layer "
                                 f"weights were built for {list(RUC_SOIL_NODES)} m")
            for native, prefix in (('SMOIS', 'swvl'), ('TSLB', 'stl')):
                keys = [f'{prefix}{i}' for i in range(1, 5)]
                if not any(want(k) for k in keys):
                    continue
                profile = np.asarray(ncfile.variables[native][0], dtype=float)
                layers = np.tensordot(SOIL_LAYER_WEIGHTS, profile, axes=(1, 0))
                for i, key in enumerate(keys):
                    if not want(key):
                        continue
                    lo, hi = ERA5_SOIL_LAYERS[i]
                    # RUC integrates no soil column over water. The mask MOVES with
                    # the sea-ice reclassification, so it is the wrfout's own
                    # landmask, never the static one.
                    emit(key, np.where(ocean, np.nan, layers[i]),
                         f"({100 * lo:.0f}-{100 * hi:.0f} cm layer average)")
        except Exception as exc:
            print(f"  soil layers: FAILED: {exc}")

    if want('tirf'):
        try:
            rain = since_00z('RAINNC') - since_00z('SNOWNC') - since_00z('GRAUPELNC')
            emit('tirf', np.where(rain < 0, 0.0, rain), "(rain only, mm)")
        except Exception as exc:
            print(f"  tirf: FAILED: {exc}")

    if want('ro'):
        try:
            # Both are monotone, so the clip only guards against reference noise.
            total = since_00z('SFROFF') + since_00z('UDROFF')
            emit('ro', np.where(total < 0, 0.0, total) * 1e-3, "(surface + sub-surface)")
        except Exception as exc:
            print(f"  ro: FAILED: {exc}")

    # Net radiation: downward minus upward, all in J/m^2 already.
    for key, (down, up) in NET_RADIATION.items():
        if not want(key):
            continue
        try:
            net = -since_00z(up) if down is None else since_00z(down) - since_00z(up)
            emit(key, net, f"(net, {down or '0'} - {up})")
        except Exception as exc:
            print(f"  {key}: FAILED: {exc}")

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
    species_keys = {'QCLOUD': 'tclw', 'QICE': 'tciw', 'QRAIN': 'tcrw', 'QSNOW': 'tcsw'}
    if want('tcw') or want('tqv') or any(want(k) for k in species_keys.values()):
        try:
            pres_pa = gv("pressure").values * 100.0
            dp = np.abs(np.diff(pres_pa, axis=0))
            dp = np.concatenate([dp, np.zeros_like(dp[-1:])], axis=0)
            # Same mixing-ratio -> specific-content conversion as on the
            # pressure levels: the column integral of a specific content.
            moist = moist_factor(False)
            qv = gv("QVAPOR").values * moist
            if want('tqv'):
                emit('tqv', np.sum(qv * dp / G, axis=0))
            if want('tcw'):
                total = qv.copy()
                for name in ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP"):
                    total += gv(name).values * moist
                emit('tcw', np.sum(total * dp / G, axis=0))
                del total
            # Per-species columns, from the same dp. The fields are already in
            # the cache from tcw, so this costs one reduction each.
            for name, key in species_keys.items():
                if want(key):
                    emit(key, np.sum(np.maximum(gv(name).values, 0.0) * moist * dp / G, axis=0))
            del dp, pres_pa, qv
        except Exception as exc:
            print(f"  column integrals: FAILED: {exc}")

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
    main(args.input, args.output, args.debug_vars, args.accum_ref_dir,
         args.static_ref_dir)
