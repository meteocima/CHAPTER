#!/usr/bin/env python3
"""The audit harness: one comparison row per variable, level, timestep and region.

    source tools/eccodes_env.sh
    uv run python tools/audit/harness.py compare --family 2 --timestep 2024-07-15T12
    uv run python tools/audit/harness.py compare --variable 2t --all-timesteps
    uv run python tools/audit/harness.py report --family 2 > docs/audit/family2.md

Every family ticket calls this; none reimplements it. What it measures and what
it cannot is settled in the resolution of "Build the audit harness" and repeated
here because a harness whose limits are only in an issue comment will be trusted
past them.

THREE LEGS, AND THEY ARE NOT EQUALLY STRONG.

  A. The GRIB against itself and against the eccodes parameter definition.
     Same grid, no other data. Catches an impossible range, a wrong sign, a
     missing bitmap, a unit that cannot be the declared one.

  B. The GRIB against the wrfout it was made from. SAME GRID, SAME INSTANT, so
     a factor, a sign or a unit conversion is caught to machine precision. This
     is the strong leg and it needs no ERA5 at all. It is also the leg that is
     unavailable for most derived variables -- see LEG_B below.

  C. The GRIB against ERA5. The only leg with a resolution gap: 59 WRF cells per
     ERA5 cell on average, 43 at 60 N and 78 at 25 N. It can see a factor, a
     sign, a unit and a missing mask. It CANNOT see a 5 per cent bias, a
     smoother field or a lower extreme, and it must never be asked to: those are
     the resolution difference, not a defect.

WHY LEG B DOES NOT IMPORT THE CONVERTER'S TABLES. The defect leg B exists to
catch is a wrong unit factor, and `convert_to_pressure_levels.UNIT_SCALE` is
where such a factor would live. A harness that read that table would apply the
same wrong number to the source field and report agreement. So the expected
factor is derived here, independently, from the wrfout variable's own `units`
attribute and the unit eccodes says the paramId is defined in -- metadata on
both sides, written by neither of us. The converter's table is then compared
against the derived factor and a disagreement is reported as a finding.

UPSCALING. WRF to ERA5, never the other way: averaging discards information WRF
has and what survives is what ERA5 should hold, whereas interpolating ERA5 up
invents structure and then compares it against the real thing. The WRF grid is
Mercator and ERA5's is regular lat/lon, so the mapping is separable -- every WRF
row falls in one ERA5 latitude band and every column in one longitude band --
and the upscale is exact index bucketing with no interpolation weights. Cells
are weighted by cos^2(latitude): with dlon constant, a Mercator cell's physical
area goes as cos^2, confirmed on this grid to 0.04 per cent against the measured
row spacing.

WHAT IS ASSERTED AND WHAT IS ONLY REPORTED. The harness fails a variable only on
what cannot be a resolution difference: wrong order of magnitude, wrong sign, a
value outside the physically possible range for the declared unit, and a mask
that disagrees with the land-sea mask. Everything else is a number for a person
to read. There is deliberately no per-variable tolerance table: those numbers
would be invented here, and an invented tolerance turns "I do not know" into
"pass", which is the failure this audit exists to undo.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eccodes                                    # noqa: E402
import wrf_era5_comparison as REG                 # noqa: E402
import era5_crosswalk as X                        # noqa: E402
import ifs_humidity as IFS                        # noqa: E402

WORK = Path(os.environ.get('WORK_DIR', '/leonardo_work/AIFPT_AILAMIT/CHAPTER'))
GRIB_DIR = WORK / 'grib_audit'
WRFOUT_DIR = WORK / 'wrfout_audit'
ERA5_DIR = WORK / 'era5_audit'
STATIC = WORK / 'static_v1' / 'chapter_static_d02.npz'
GRID_CACHE = ERA5_DIR / 'wrf_grid.npz'
SAMPLE_MD = PROJECT / 'docs' / 'audit' / 'sample.md'

G = 9.80665

# --- The families, as the eight family tickets partition the registry --------
FAMILIES = {
    1: ['t', 'q', 'r', 'u', 'v', 'w', 'wz', 'z_pl', 'cc', 'clwc', 'ciwc',
        'crwc', 'cswc'],
    2: ['2t', '2d', '2r', '10u', '10v', '100u', '100v', '200u', '200v', 'vwsh'],
    3: ['tcw', 'tcwv', 'tclw', 'tciw', 'tcrw', 'tcsw', 'tcc', 'hcc', 'mcc',
        'lcc'],
    4: ['ssrd', 'strd', 'ssrdc', 'strdc', 'ssr', 'str', 'ssrc', 'strc',
        'tisr', 'tsr', 'tsrc', 'ttr', 'ttrc'],
    5: ['tp', 'sf', 'tirf', 'sro', 'ssro', 'ro', '10fg'],
    6: ['swvl1', 'swvl2', 'swvl3', 'swvl4', 'stl1', 'stl2', 'stl3', 'stl4',
        'sd', 'rsn', 'snowc', 'tsn', 'src'],
    7: ['z_sfc', 'lsm', 'sdor', 'slor', 'cvl', 'cvh', 'tvl', 'tvh', 'slt', 'cl',
        'dl', 'al', 'fal'],
    8: ['sp', 'msl', 'skt', 'sst', 'ci', 'zust', 'fsr', 'iews', 'inss',
        'mucape', 'mucin'],
}

# --- Leg B: what independent source exists for each variable -----------------
# 'direct'   the registry key IS a wrfout variable (or a static sidecar field):
#            read it, convert it here, compare point for point.
# 'identity' the quantity is a short combination of wrfout variables whose
#            definition is not a choice of ours -- net radiation is downward
#            minus upward whoever writes it -- so restating it here is a second
#            opinion, not a copy of the converter.
# 'none'     the derivation IS the converter's own algorithm (vertical
#            interpolation, the skt inversion, CAPE). Recomputing it
#            independently means writing a second converter. Leg B is
#            unavailable and the verdict rests on legs A and C, plus reading
#            the code. This is a limit of the harness, not a defect.
#
# THE COLUMN INTEGRALS USED TO BE IN THAT LAST LIST AND SHOULD NOT HAVE BEEN.
# Family 3 (#21) found leg B for all six of them: WRF integrates on a DRY-MASS
# coordinate, so the column water of species X is not an integral to approximate
# but the weighted sum sum_k X_k (MU+MUB) |DNW_k| / g, with weights the model
# itself wrote out. That uses three wrfout fields the converter never opens, so
# it is a second opinion and not a copy -- and it is exact, where the converter's
# own pressure quadrature is 3 to 8 per cent off (#46). The six rows below still
# say 'none' because the measurement lives in tools/audit/f3_columns.py rather
# than here: moving it in would mean re-running the 34-timestep campaign, and
# the harness is deliberately not changed under the audit that uses it.
STATIC_FIELDS = {'cvl', 'cvh', 'tvl', 'tvh', 'slt', 'cl', 'dl'}

# Two registry entries share the shortName `z`: surface orography (key HGT) and
# pressure-level geopotential (key z). A shortName is therefore not an identity
# and every caller uses a TOKEN instead. Getting this wrong is not academic --
# the harness's first run judged 200 hPa geopotential against an orography range
# and reported five failures that were its own.
TOKEN_TO_KEY = {'z_pl': 'z', 'z_sfc': 'HGT'}

# Fields whose values are class codes. Averaging them is meaningless, so leg C
# compares the dominant class per ERA5 cell instead of the mean.
CATEGORICAL = {'tvl', 'tvh', 'slt'}

# Fields that legitimately carry a bitmap. `fal` is undefined wherever there is
# no downward shortwave, which at 00Z is the whole domain: measured 2 220 273
# missing points at 2024-07-15T00 against 1670 at noon.
BITMAP_EXPECTED = {
    'sst', 'ci',                          # ocean fields, undefined on land
    'tvl', 'slt', 'dl',                   # masked where the class or lake is absent
    'tsn',                                # a snow layer that may not exist
    'fal',                                # albedo, undefined without downward shortwave
    'swvl1', 'swvl2', 'swvl3', 'swvl4',   # soil is undefined over water
    'stl1', 'stl2', 'stl3', 'stl4',
}

LEG_B_IDENTITY = {
    # net radiation, ECMWF sign convention: downward minus upward
    'ssr':  (('ACSWDNB',), ('ACSWUPB',)),
    'ssrc': (('ACSWDNBC',), ('ACSWUPBC',)),
    'str':  (('ACLWDNB',), ('ACLWUPB',)),
    'strc': (('ACLWDNBC',), ('ACLWUPBC',)),
    'tsr':  (('ACSWDNT',), ('ACSWUPT',)),
    'tsrc': (('ACSWDNTC',), ('ACSWUPTC',)),
    'ttr':  ((), ('ACLWUPT',)),
    'ttrc': ((), ('ACLWUPTC',)),
    # total runoff is the sum of its two components
    'ro':   (('SFROFF', 'UDROFF'), ()),
    # rainfall is precipitation less its frozen parts
    'tirf': (('RAINNC',), ('SNOWNC', 'GRAUPELNC')),
}

# --- Leg D: identities inside the published archive --------------------------
# A variable recomputed from OTHER MESSAGES OF THE SAME FILE. No wrfout, no ERA5,
# so it is repeatable on every file of the archive for ever, not only on the
# sample -- and it checks the internal consistency of what a user will actually
# read, which is something legs B and C cannot see.
#
# It exists because of the ten variables ERA5 does not carry. For three of them
# this is the only exact evidence available: leg C is impossible by definition
# and leg B is unavailable because the converter derives them itself.
#
# 'exact'       the formula IS the converter's, restated; a disagreement is a
#               defect and is asserted.
# 'approximate' the formula is a physical relation that holds to a tolerance
#               (a thermodynamic approximation, a different saturation formula).
#               REPORTED, never asserted: the scatter is the physics, not a bug.
# 'bracket'     no formula at all, only an inequality that ought to hold at most
#               points. The weakest kind, and the report says so.
R_DRY = 287.058

# Siblings are named by shortName alone and their level is resolved from the
# registry. Writing the level here by hand is how the first version broke: 2t
# sits on heightAboveGround level 2 and 10u on level 10, not on 0, so every
# sibling lookup but wz's missed and the rows said "sibling absent". The same
# class of mistake as assuming a shortName is an identity.
LEG_D = {
    'vwsh':  ('exact',
              'sqrt((100u-10u)^2 + (100v-10v)^2) / 90, the bulk 10-100 m shear',
              ('100u', '100v', '10u', '10v')),
    'wz':    ('approximate',
              'w_z = -omega / (rho g) with rho = p / (R_d T): the two published '
              'vertical-velocity conventions of the same quantity',
              ('w', 't')),
    '2r':    ('approximate',
              'the reconstruction from the published 2t and 2d, both over '
              'liquid water: esat_water(2d)/esat_water(2t)',
              ('2t', '2d')),
    '200u':  ('bracket',
              'wind speed should not fall from 100 m to 200 m at most points',
              ('100u', '100v', '200v')),
    '200v':  ('bracket',
              'the 100 m and 200 m wind vectors should be nearly parallel',
              ('100u', '100v', '200u')),
}


def _sibling_level(short, own_level):
    """The level a sibling lives on, from the registry -- never guessed."""
    entry = _registry_entry(short)
    if entry is None:
        return own_level
    if entry.get('levelType') == 'isobaricInhPa':
        return own_level          # the same pressure level as the row asking
    levels = entry['levels']
    return levels[0] if levels else own_level


# Saturation comes from `ifs_humidity`, which carries ECMWF's own constants with
# the equation numbers they come from. The Magnus formula that used to stand
# here was wrf-python's, over liquid water at every temperature, and checking a
# parameter ECMWF defines over the MIXED phase against it is how leg D missed
# the defect in `2r` (issue #40) instead of finding it.


# --- Leg A: what cannot be true, whatever the resolution ---------------------
# Keyed on the unit eccodes declares for the paramId, with per-variable
# overrides. These are physical impossibilities, not tolerances: a value outside
# them is a defect in any season, at any resolution, on any grid.
RANGE_BY_UNIT = {
    'K':            (150.0, 350.0),
    '(0 - 1)':      (0.0, 1.0),
    '%':            (0.0, 100.0),
    'kg kg**-1':    (0.0, 0.1),
    'Pa':           (1000.0, 120000.0),
    'm s**-1':      (-200.0, 200.0),
    'kg m**-3':     (0.0, 1000.0),
    'N m**-2':      (-50.0, 50.0),
    'm**2 s**-2':   (-1000.0, 100000.0),
}
RANGE_OVERRIDE = {
    'msl': (87000.0, 112000.0),
    'sp':  (40000.0, 112000.0),
    # Supersaturation is physical and the ceiling has to hold the real field,
    # not the clipped one. The archive's `r` today never exceeds 100 because
    # `fortran/wrf_user.f90:730` applies MIN(qv/qvs, 1) -- issue #40 -- so these
    # bounds are set from what the field becomes once that clip is gone AND the
    # saturation is ECMWF's mixed phase, measured on three timesteps:
    #
    #   above ground   max 141.9 per cent, at 300-400 hPa in the ice regime.
    #                  That is real ice supersaturation, and it is below the
    #                  homogeneous freezing threshold, which is where it should
    #                  stop.
    #   below ground   max 163.1 per cent at 1000 hPa -- BUT that figure is an
    #                  artifact of the measurement, not of the archive, and
    #                  issue #44 says why: below ground `vinterp` CLAMPS to the
    #                  lowest model level rather than extrapolating, so `q` and
    #                  `t` there come from about 25 m AGL where the real
    #                  pressure may be 700 hPa. Pairing them with the nominal
    #                  1000 hPa inflates the vapour pressure by up to a factor
    #                  1.4. The archive's own `r` below ground is the model's
    #                  own value and is sound. Every point above 130 at 1000,
    #                  925 and 850 hPa is below ground; above ground those
    #                  levels stop at 100.3, 109.4, 115.6.
    #   at 2 m         max 100.2 over all 34 timesteps: the surface field is
    #                  pinned by the model's own saturation adjustment, so the
    #                  clip costs almost nothing there and the bound can be
    #                  tighter.
    #
    # 200 leaves the extrapolation room and still catches a doubling or a unit
    # error; it is not a tolerance on the physics.
    'r':   (0.0, 200.0),
    '2r':  (0.0, 130.0),
    # The floor is not zero: the domain contains the Dead Sea, and the lowest
    # point of this orography is -465.6 m at lat 31.345, lon 35.464, which is
    # exactly it. 4751 points (0.214 per cent) are below sea level.
    'z_sfc': (-6000.0, 100000.0),      # orography: -600 m to 10.2 km of height
    'z_pl':  (-1000.0, 400000.0),      # geopotential up to the 50 hPa lid
    # Pa/s, not m/s. The floor is wide because 3 km is convection-permitting:
    # -136.8 Pa/s measured on 2024-07-15T12 is about a 20 m/s updraft, which is
    # an ordinary July storm at this resolution and impossible at ERA5's.
    'w':   (-300.0, 300.0),
    'sdor': (0.0, 5000.0),
    'dl':  (0.0, 2000.0),
    'sd':  (0.0, 20.0),
    'src': (0.0, 1.0),
    'mucape': (0.0, 10000.0),
    # CIN is a positive MAGNITUDE in the ECMWF convention, not a negative
    # energy, so the floor is zero and not -2000 as an earlier version of this
    # table guessed. The authority is ECMWF's own documentation of the 47r3 CAPE
    # and CIN parameters, which speaks of values that "exceed 1000 J/kg" and
    # shades "CIN values over 50 J.kg-1".
    #
    # It is NOT ERA5's cin field, which an earlier version of this comment cited.
    # That field cannot be read for a range at all: ECMWF encodes CIN as missing
    # above 1000 J/kg and the missing value arrives as the number 9999, so on
    # 2024-07-15T12 32096 of its 37548 points -- 85.5 per cent -- are exactly
    # 9999 and its genuine values stop at 999.5. Citing it was reading a
    # sentinel as data.
    #
    # The ceiling here is a physical impossibility, not ECMWF's 1000 J/kg cap:
    # we do not apply that cap, and our mucin reaches 1236 J/kg. Whether to
    # adopt the cap is family 8's decision, so it is reported and not asserted.
    'mucin':  (0.0, 20000.0),
}
# Sign the field must have everywhere, whatever the season.
SIGN = {
    'ttr': 'nonpositive', 'ttrc': 'nonpositive',
    'tisr': 'nonnegative', 'ssrd': 'nonnegative', 'strd': 'nonnegative',
    'ssrdc': 'nonnegative', 'strdc': 'nonnegative',
    'tp': 'nonnegative', 'sf': 'nonnegative', 'tirf': 'nonnegative',
    'sro': 'nonnegative', 'ssro': 'nonnegative', 'ro': 'nonnegative',
    'ssr': 'nonnegative', 'ssrc': 'nonnegative',
    '10fg': 'nonnegative', 'mucape': 'nonnegative',
}
# Which points must be missing. 'sea' means the field is defined over water
# only, so land must carry a bitmap rather than a number.
MASK_EXPECTED = {'sst': 'sea', 'ci': 'sea'}


# =============================================================================
# The sample, the grids, the readers
# =============================================================================

def sample_timesteps():
    """Every timestep of the audit sample, from docs/audit/sample.md."""
    import re
    out = []
    pattern = re.compile(r'^\|\s*(\d{4}-\d{2}-\d{2})T(\d{2})\s*\|')
    for line in SAMPLE_MD.read_text().splitlines():
        m = pattern.match(line)
        if m:
            out.append(f'{m.group(1)}T{m.group(2)}')
    return sorted(set(out))


def grib_path(timestep):
    date, hour = timestep.split('T')
    y, m, _ = date.split('-')
    compact = date.replace('-', '')
    return (GRIB_DIR / y / m /
            f'ailam-an-cima-3km-{y}-{y}-1h-v1-{compact}{hour}.grib')


def wrfout_path(timestep):
    date, hour = timestep.split('T')
    return WRFOUT_DIR / date / f'wrfout_d02_{date}_{hour}:00:00'


def era5_path(kind, timestep):
    date = timestep.split('T')[0].replace('-', '')
    return ERA5_DIR / kind / f'era5_{kind}_{date}.grib'


def _message_field(gid):
    nj, ni = eccodes.codes_get(gid, 'Nj'), eccodes.codes_get(gid, 'Ni')
    values = eccodes.codes_get_array(gid, 'values').astype(np.float64)
    if eccodes.codes_get(gid, 'bitmapPresent'):
        values = np.where(values == eccodes.codes_get(gid, 'missingValue'),
                          np.nan, values)
    return values.reshape(nj, ni)


def read_grib(path, shortname, level=None, validity_time=None):
    """One message as a 2-D array plus the keys leg A needs.

    Matching is on shortName and, where given, level and validity -- never on
    typeOfLevel, because ERA5 is GRIB edition 1 and we are edition 2 and the two
    put the same parameter on different level types.
    """
    with open(path, 'rb') as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                return None
            try:
                if eccodes.codes_get(gid, 'shortName') != shortname:
                    continue
                if level is not None and eccodes.codes_get(gid, 'level') != level:
                    continue
                if (validity_time is not None
                        and eccodes.codes_get(gid, 'validityTime') != validity_time):
                    continue
                return {
                    'values': _message_field(gid),
                    'paramId': eccodes.codes_get(gid, 'paramId'),
                    'units': eccodes.codes_get(gid, 'units'),
                    'name': eccodes.codes_get(gid, 'name'),
                    'typeOfLevel': eccodes.codes_get(gid, 'typeOfLevel'),
                    'level': eccodes.codes_get(gid, 'level'),
                    'stepType': eccodes.codes_get(gid, 'stepType'),
                    'stepRange': eccodes.codes_get(gid, 'stepRange'),
                    'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent')),
                    'validityTime': eccodes.codes_get(gid, 'validityTime'),
                    'validityDate': eccodes.codes_get(gid, 'validityDate'),
                }
            finally:
                eccodes.codes_release(gid)


def wrf_grid():
    """The WRF row latitudes and column longitudes, cached.

    Identical for every message of every timestep of the archive, and ~2 s to
    derive, so it is computed once and kept beside the ERA5 set.
    """
    if GRID_CACHE.exists():
        cached = np.load(GRID_CACHE)
        return cached['lat'], cached['lon']
    sample = sample_timesteps()[0]
    with open(grib_path(sample), 'rb') as fh:
        gid = eccodes.codes_grib_new_from_file(fh)
    nj, ni = eccodes.codes_get(gid, 'Nj'), eccodes.codes_get(gid, 'Ni')
    lat = eccodes.codes_get_array(gid, 'latitudes').reshape(nj, ni)[:, 0].copy()
    lon = eccodes.codes_get_array(gid, 'longitudes').reshape(nj, ni)[0, :].copy()
    eccodes.codes_release(gid)
    lon = np.where(lon > 180.0, lon - 360.0, lon)
    GRID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(GRID_CACHE, lat=lat, lon=lon)
    return lat, lon


def era5_grid(path):
    with open(path, 'rb') as fh:
        gid = eccodes.codes_grib_new_from_file(fh)
    nj, ni = eccodes.codes_get(gid, 'Nj'), eccodes.codes_get(gid, 'Ni')
    lat = eccodes.codes_get_array(gid, 'latitudes').reshape(nj, ni)[:, 0].copy()
    lon = eccodes.codes_get_array(gid, 'longitudes').reshape(nj, ni)[0, :].copy()
    eccodes.codes_release(gid)
    return lat, np.where(lon > 180.0, lon - 360.0, lon)


class Upscaler:
    """WRF -> ERA5 by area-weighted box average.

    Separable because the WRF grid is Mercator: constant dlon, and rows at fixed
    latitudes. Every WRF cell therefore falls wholly inside one ERA5 cell and
    the average is a weighted bincount, not an interpolation.
    """

    def __init__(self, wlat, wlon, elat, elon):
        self.shape = (elat.size, elon.size)
        iy = self._bucket(wlat, elat)
        ix = self._bucket(wlon, elon)
        self.flat = (iy[:, None] * elon.size + ix[None, :]).ravel()
        # A Mercator cell's physical area goes as cos^2(latitude) when dlon is
        # constant; measured on this grid to 0.04 per cent against the row
        # spacing, so it is derived rather than assumed.
        weight = np.cos(np.radians(wlat)) ** 2
        self.weight = np.broadcast_to(weight[:, None],
                                      (wlat.size, wlon.size)).ravel()
        self.full_den = np.bincount(self.flat, weights=self.weight,
                                    minlength=elat.size * elon.size)

    @staticmethod
    def _bucket(coarse_from, edges):
        step = abs(edges[1] - edges[0])
        ascending = edges[1] > edges[0]
        axis = edges if ascending else edges[::-1]
        idx = np.clip(np.round((coarse_from - axis[0]) / step).astype(int),
                      0, axis.size - 1)
        return idx if ascending else axis.size - 1 - idx

    def mode(self, field, n_classes=64):
        """The dominant class per ERA5 cell, for fields whose values are codes.

        Averaging a code table is meaningless -- halfway between evergreen
        broadleaf and short grass is not a vegetation type -- so categorical
        fields are upscaled by majority instead.
        """
        flat_field = field.ravel()
        finite = np.isfinite(flat_field)
        codes = np.zeros(flat_field.shape, dtype=np.int64)
        codes[finite] = np.clip(np.rint(flat_field[finite]), 0,
                                n_classes - 1).astype(np.int64)
        n = self.shape[0] * self.shape[1]
        counts = np.bincount(self.flat[finite] * n_classes + codes[finite],
                             weights=self.weight[finite],
                             minlength=n * n_classes).reshape(n, n_classes)
        winner = counts.argmax(axis=1).astype(np.float64)
        winner[counts.sum(axis=1) == 0] = np.nan
        return winner.reshape(self.shape)

    def __call__(self, field):
        flat_field = field.ravel()
        finite = np.isfinite(flat_field)
        n = self.shape[0] * self.shape[1]
        if finite.all():
            num = np.bincount(self.flat, weights=flat_field * self.weight,
                              minlength=n)
            den = self.full_den
        else:
            num = np.bincount(self.flat[finite],
                              weights=(flat_field * self.weight)[finite],
                              minlength=n)
            den = np.bincount(self.flat[finite], weights=self.weight[finite],
                              minlength=n)
        with np.errstate(invalid='ignore', divide='ignore'):
            out = np.where(den > 0, num / den, np.nan)
        return out.reshape(self.shape)


# =============================================================================
# Units, derived independently of the converter
# =============================================================================

def _norm_unit(unit):
    if unit is None:
        return ''
    u = unit.strip().replace('**', '').replace(' ', '').replace('-', '')
    # eccodes spells a water-equivalent depth "m of water equivalent"; the
    # wrfout spells the same thing "m". They are one unit.
    u = {'mofwaterequivalent': 'm', 'kgm2': 'kgm2', 'kgm**2': 'kgm2'}.get(u, u)
    return {'': 'fraction', '1': 'fraction', '(01)': 'fraction'}.get(u, u)


# (source unit as the wrfout declares it, target unit as eccodes declares it)
# -> the factor that takes one to the other. Physical conversions only; nothing
# here is a choice, which is what makes it an independent check of the
# converter's own UNIT_SCALE rather than a copy of it.
UNIT_FACTOR = {
    ('mm', 'm'): 1e-3,                 # depth of water
    ('kgm2', 'm'): 1e-3,               # mass per area -> depth, water at 1000 kg/m3
    ('mm', 'kgm2'): 1.0,               # 1 mm of water over 1 m2 IS 1 kg
    ('m', 'kgm2'): 1000.0,
    ('m', 'm2s2'): G,                  # height -> geopotential
    ('fraction', '%'): 100.0,
    ('%', 'fraction'): 0.01,
}


# Conversions that are not a multiplication. `sdor` is the standard deviation of
# sub-grid orography and WRF's VAR_SSO is its variance, so the two differ by a
# square root; a harness that only knew factors would refuse the comparison and
# call it an unknown unit pair.
UNIT_TRANSFORM = {
    ('m2', 'm'): (np.sqrt, 'sqrt'),
}


def unit_factor(src_units, dst_units):
    """The factor taking the wrfout's unit to the one eccodes declares.

    Returns (factor, how). `how` is 'identity', 'table' or 'unknown'; an unknown
    pair is reported, never guessed at as 1.0 -- a silent 1.0 is exactly the
    defect the GRIB1 archive carried when 2d went out in degC under a paramId
    defined in K.
    """
    src, dst = _norm_unit(src_units), _norm_unit(dst_units)
    if src == dst:
        return 1.0, 'identity'
    if (src, dst) in UNIT_FACTOR:
        return UNIT_FACTOR[(src, dst)], 'table'
    if (src, dst) in UNIT_TRANSFORM:
        return UNIT_TRANSFORM[(src, dst)][0], UNIT_TRANSFORM[(src, dst)][1]
    return None, 'unknown'


# =============================================================================
# The ERA5 counterpart
# =============================================================================

def era5_counterpart(token, ctx, level=None):
    """The ERA5 field our message at this timestep should be compared against.

    Accumulated variables are summed: ERA5 accumulates over the hour ending at
    the validity time, we accumulate since 00Z, so the counterpart at hour H is
    the sum of ERA5's hourly values valid 01Z..HZ of the same day. The message
    stamped 00Z is the hour 23Z->00Z of the day before and is excluded. `10fg`
    is not summed: it is a one-hour maximum on both sides.
    """
    kind = 'pl' if level is not None else 'sl'
    shortname = short_of(token)
    cds_name = (X.PL_CROSSWALK if kind == 'pl' else X.SL_CROSSWALK).get(shortname)
    if cds_name is None:
        return None, 'ERA5 does not carry this parameter'
    cache = ctx.era5_messages(kind)
    if not cache:
        return None, f'no ERA5 {kind} file for {ctx.timestep.split("T")[0]}'
    era_level = level if level is not None else None
    hour = int(ctx.timestep.split('T')[1])
    registry = _registry_entry(token)
    accumulated = registry is not None and registry.get('stepType') == 'accum'

    def at(h):
        if era_level is not None:
            return cache.get((shortname, era_level, h * 100))
        for key, values in cache.items():
            if key[0] == shortname and key[2] == h * 100:
                return values
        return None

    if not accumulated:
        field = at(hour)
        if field is None:
            return None, f'no ERA5 {shortname} valid at {hour:02d}Z'
        return field, None

    if hour == 0:
        return None, ('accumulated since 00Z, so ours is zero by construction '
                      'and there is nothing to compare at 00Z')
    total = None
    for h in range(1, hour + 1):
        field = at(h)
        if field is None:
            return None, f'no ERA5 {shortname} valid at {h:02d}Z'
        total = field if total is None else total + field
    return total, None


def _registry_entry(token):
    """The registry row a token names. Tokens, not shortNames: see TOKEN_TO_KEY."""
    key = TOKEN_TO_KEY.get(token)
    if key is not None:
        return dict(REG.WRF_TO_ECMWF_PARAMID[key], _key=key)
    for key, entry in REG.WRF_TO_ECMWF_PARAMID.items():
        if entry['shortName'] == token:
            return dict(entry, _key=key)
    return None


def short_of(token):
    entry = _registry_entry(token)
    return entry['shortName'] if entry else token


# =============================================================================
# Statistics and the four assertions
# =============================================================================

def stats(field, region_mask):
    sel = field[region_mask]
    finite = np.isfinite(sel)
    if not finite.any():
        return {'n': int(sel.size), 'n_missing': int(sel.size),
                'min': None, 'max': None, 'mean': None, 'std': None}
    good = sel[finite]
    return {
        'n': int(sel.size),
        'n_missing': int(sel.size - good.size),
        'min': float(good.min()), 'max': float(good.max()),
        'mean': float(good.mean()), 'std': float(good.std()),
    }


def assertions(token, message, values, land_mask):
    """What cannot be true whatever the season, the grid or the resolution.

    Returns (failures, notes). A note is something a family ticket should see and
    that is not a defect. Keeping the two apart matters: an earlier version called
    an all-missing `fal` a failure at all sixteen 00Z timesteps, when an albedo
    with no downward shortwave is undefined and missing is the correct answer.
    """
    failures, notes = [], []
    good = values[np.isfinite(values)]
    if good.size == 0:
        if token in BITMAP_EXPECTED:
            notes.append('entirely missing; this field is maskable, so that is '
                         'legitimate where the condition it depends on is absent '
                         'from the whole domain')
            return failures, notes
        return ['every value is missing'], notes

    lo, hi = RANGE_OVERRIDE.get(token,
                                RANGE_BY_UNIT.get(message['units'], (None, None)))
    if lo is not None and (good.min() < lo or good.max() > hi):
        failures.append(
            f'outside the possible range for {message["units"]}: '
            f'[{good.min():.6g}, {good.max():.6g}] against [{lo:g}, {hi:g}]')

    want_sign = SIGN.get(token)
    if want_sign == 'nonnegative' and good.min() < -1e-6 * max(abs(good.max()), 1):
        failures.append(f'must be non-negative but reaches {good.min():.6g}')
    if want_sign == 'nonpositive' and good.max() > 1e-6 * max(abs(good.min()), 1):
        failures.append(f'must be non-positive but reaches {good.max():.6g}')

    expected_mask = MASK_EXPECTED.get(token)
    if expected_mask == 'sea':
        if not message['bitmap']:
            failures.append('defined over water only but carries no bitmap')
        elif land_mask is not None:
            on_land = np.isfinite(values) & land_mask
            if on_land.sum() > 0.01 * land_mask.sum():
                failures.append(
                    f'{int(on_land.sum())} land points carry a value '
                    f'({100 * on_land.sum() / land_mask.sum():.1f} per cent of land)')
    elif message['bitmap'] and token not in BITMAP_EXPECTED:
        failures.append('carries a bitmap where none was expected')
    return failures, notes


def read_grib_many(path, wanted):
    """Several messages in ONE pass over the file.

    A pressure-level family is 169 messages; one pass per message would read the
    same 700 MB 169 times.
    """
    remaining = set(wanted)
    out = {}
    with open(path, 'rb') as fh:
        while remaining:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                key = (eccodes.codes_get(gid, 'shortName'),
                       eccodes.codes_get(gid, 'level'))
                if key not in remaining:
                    continue
                remaining.discard(key)
                out[key] = {
                    'values': _message_field(gid),
                    'paramId': eccodes.codes_get(gid, 'paramId'),
                    'units': eccodes.codes_get(gid, 'units'),
                    'typeOfLevel': eccodes.codes_get(gid, 'typeOfLevel'),
                    'level': eccodes.codes_get(gid, 'level'),
                    'stepType': eccodes.codes_get(gid, 'stepType'),
                    'stepRange': eccodes.codes_get(gid, 'stepRange'),
                    'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent')),
                }
            finally:
                eccodes.codes_release(gid)
    return out


# =============================================================================
# Leg B: the GRIB against its own source, on the same grid
# =============================================================================

def leg_b_kind(token):
    entry = _registry_entry(token)
    if entry is None:
        return 'none', None
    key = entry['_key']
    if token in STATIC_FIELDS:
        return 'direct', f'static sidecar {key}'
    if entry.get('levelType') == 'isobaricInhPa':
        # The wrfout holds these on model levels; a pressure-level message is
        # the converter's vertical interpolation, not a field that exists to be
        # read back.
        return 'none', 'vertical interpolation to pressure levels'
    if token in LEG_B_IDENTITY:
        plus, minus = LEG_B_IDENTITY[token]
        expr = ' + '.join(plus) if plus else '0'
        if minus:
            expr += ' - ' + ' - '.join(minus)
        return 'identity', expr
    if _is_wrfout_variable(key):
        return 'direct', key
    return 'none', f'{key} is computed by the converter'


_WRFOUT_VARS = None


def _is_wrfout_variable(name):
    global _WRFOUT_VARS
    if _WRFOUT_VARS is None:
        import netCDF4
        sample = sample_timesteps()[0]
        with netCDF4.Dataset(wrfout_path(sample)) as nc:
            _WRFOUT_VARS = set(nc.variables)
    return name in _WRFOUT_VARS


def _read_wrfout_vars(timestep, names):
    import netCDF4
    out = {}
    with netCDF4.Dataset(wrfout_path(timestep)) as nc:
        for name in names:
            if name not in nc.variables:
                out[name] = (None, None)
                continue
            var = nc.variables[name]
            out[name] = (np.asarray(var[0]).astype(np.float64),
                         getattr(var, 'units', ''))
    return out


def leg_b(token, message, timestep):
    """Compare the encoded field against the source it was made from.

    Same grid, same instant: a factor, a sign or a unit conversion shows up to
    machine precision. Accumulated variables are referred to 00Z of the same
    day, so the source is read at this hour AND at 00Z and subtracted here --
    independently of the accumulation sidecar, which is therefore also under
    test.
    """
    kind, source = leg_b_kind(token)
    result = {'kind': kind, 'source': source}
    if kind == 'none':
        result['note'] = ('no independent source field: ' + str(source) +
                          '. Legs A and C carry the verdict.')
        return result

    entry = _registry_entry(token)
    accumulated = entry.get('stepType') == 'accum'
    date = timestep.split('T')[0]
    zero_hour = f'{date}T00'

    if kind == 'direct' and token in STATIC_FIELDS:
        static = np.load(STATIC, allow_pickle=True)
        field = np.asarray(static[f'var_{token}']).astype(np.float64)
        src_units = message['units']          # the sidecar is already in them
    elif kind == 'direct':
        name = entry['_key']
        values, src_units = _read_wrfout_vars(timestep, [name])[name]
        if values is None:
            result['note'] = f'{name} is absent from the wrfout'
            return result
        field = values
        if accumulated:
            base = _read_wrfout_vars(zero_hour, [name])[name][0]
            if base is None:
                result['note'] = f'{name} is absent from the 00Z wrfout'
                return result
            field = field - base
    else:                                       # identity
        plus, minus = LEG_B_IDENTITY[token]
        needed = list(plus) + list(minus)
        now = _read_wrfout_vars(timestep, needed)
        missing = [n for n in needed if now[n][0] is None]
        if missing:
            result['note'] = f'absent from the wrfout: {missing}'
            return result
        base = _read_wrfout_vars(zero_hour, needed) if accumulated else None
        field = np.zeros_like(now[needed[0]][0])
        for name in plus:
            field = field + (now[name][0] - base[name][0] if accumulated
                             else now[name][0])
        for name in minus:
            field = field - (now[name][0] - base[name][0] if accumulated
                             else now[name][0])
        src_units = now[needed[0]][1]

    factor, how = unit_factor(src_units, message['units'])
    result.update({'src_units': src_units, 'dst_units': message['units'],
                   'factor': how if callable(factor) else factor,
                   'factor_from': how})
    if factor is None:
        result['note'] = (f'no conversion known from {src_units!r} to '
                          f'{message["units"]!r}; not compared rather than '
                          f'compared with a guessed factor')
        return result

    expected = factor(field) if callable(factor) else field * factor
    ours = message['values']
    if expected.shape != ours.shape:
        result['note'] = f'shape {expected.shape} against {ours.shape}'
        return result
    both = np.isfinite(expected) & np.isfinite(ours)
    diff = np.abs(ours[both] - expected[both])
    scale = max(float(np.abs(expected[both]).max()), 1e-30)
    result.update({
        'n_compared': int(both.sum()),
        'max_abs_diff': float(diff.max()) if diff.size else None,
        'max_rel_diff': float(diff.max() / scale) if diff.size else None,
        'agrees': bool(diff.size and diff.max() <= 1e-4 * scale),
    })
    # Second opinion on the converter's own factor, which leg B must not import.
    converter = _converter_unit_scale().get(entry['_key'])
    if converter is not None and not callable(factor):
        result['converter_factor'] = converter
        if not math.isclose(converter, factor, rel_tol=1e-9):
            result['note'] = (f'the converter scales by {converter:g} where the '
                              f'unit metadata implies {factor:g}')
    return result


_UNIT_SCALE = None


def _converter_unit_scale():
    """Read, never applied. Imported only to be disagreed with."""
    global _UNIT_SCALE
    if _UNIT_SCALE is None:
        import importlib
        _UNIT_SCALE = dict(
            importlib.import_module('convert_to_pressure_levels').UNIT_SCALE)
    return _UNIT_SCALE


# =============================================================================
# Leg C: against ERA5, across the resolution gap
# =============================================================================

class Context:
    """Everything that is the same for every variable at one timestep."""

    def __init__(self, timestep):
        self.timestep = timestep
        self.wlat, self.wlon = wrf_grid()
        ours = read_grib(grib_path(timestep), 'lsm')
        self.our_land = ours['values'] > 0.5
        sl = era5_path('sl', timestep)
        self.era5_ok = sl.exists()
        if self.era5_ok:
            self.elat, self.elon = era5_grid(sl)
            self.upscale = Upscaler(self.wlat, self.wlon, self.elat, self.elon)
            hour = int(timestep.split('T')[1])
            era_lsm = read_grib(sl, 'lsm', validity_time=hour * 100)
            self.era_land = era_lsm['values'] > 0.5
        self._sp = None
        self._era5_cache = {}
        self._siblings = None

    def siblings(self):
        """Every message leg D needs, from ONE pass over our own file.

        Leg D recomputes a variable from other published messages, so it needs
        its siblings; reading them per row would walk a 703 MB file once per
        row. The set is fixed and small -- the near-surface winds, 2t, 2d, and
        w and t on every pressure level.
        """
        if self._siblings is not None:
            return self._siblings
        wanted_shorts = set()
        for spec in LEG_D.values():
            wanted_shorts.update(spec[2])
        cache = {}
        with open(grib_path(self.timestep), 'rb') as fh:
            while True:
                gid = eccodes.codes_grib_new_from_file(fh)
                if gid is None:
                    break
                try:
                    short = eccodes.codes_get(gid, 'shortName')
                    if short not in wanted_shorts:
                        continue
                    cache[(short, eccodes.codes_get(gid, 'level'))] = \
                        _message_field(gid)
                finally:
                    eccodes.codes_release(gid)
        self._siblings = cache
        return cache

    def era5_messages(self, kind):
        """Every message of one ERA5 file, read once.

        Re-walking the file per row cost more than the comparison did: a
        pressure-level family asks 169 times for messages that live in one
        21 MB file.
        """
        if kind not in self._era5_cache:
            path = era5_path(kind, self.timestep)
            cache = {}
            if path.exists():
                with open(path, 'rb') as fh:
                    while True:
                        gid = eccodes.codes_grib_new_from_file(fh)
                        if gid is None:
                            break
                        try:
                            cache[(eccodes.codes_get(gid, 'shortName'),
                                   eccodes.codes_get(gid, 'level'),
                                   eccodes.codes_get(gid, 'validityTime'))] = \
                                _message_field(gid)
                        finally:
                            eccodes.codes_release(gid)
            self._era5_cache[kind] = cache
        return self._era5_cache[kind]

    def surface_pressure(self):
        if self._sp is None:
            self._sp = read_grib(grib_path(self.timestep), 'sp')['values']
        return self._sp

    def wrf_regions(self, level_hpa=None):
        everywhere = np.ones_like(self.our_land, dtype=bool)
        regions = {'all': everywhere, 'land': self.our_land,
                   'sea': ~self.our_land}
        if level_hpa is not None:
            regions['above_ground'] = self.surface_pressure() >= level_hpa * 100.0
        return regions

    def era5_regions(self):
        everywhere = np.ones_like(self.era_land, dtype=bool)
        return {'all': everywhere, 'land': self.era_land,
                'sea': ~self.era_land}


def leg_c(token, message, ctx, level=None):
    if not ctx.era5_ok:
        return {'available': False,
                'why': f'no ERA5 file for {ctx.timestep.split("T")[0]}'}
    counterpart, why = era5_counterpart(token, ctx, level=level)
    if counterpart is None:
        return {'available': False, 'why': why}
    categorical = token in CATEGORICAL
    if categorical:
        upscaled = ctx.upscale.mode(message['values'])
        out = {'available': True, 'categorical': True, 'regions': {}}
        for name, mask in ctx.era5_regions().items():
            both = mask & np.isfinite(upscaled) & np.isfinite(counterpart)
            if both.sum() < 10:
                out['regions'][name] = {'n': int(both.sum())}
                continue
            ours_code = np.rint(upscaled[both]).astype(int)
            era_code = np.rint(counterpart[both]).astype(int)
            agree = float((ours_code == era_code).mean())
            out['regions'][name] = {
                'n': int(both.sum()),
                'class_agreement': agree,
                'ours_classes': {int(k): int(v) for k, v in
                                 zip(*np.unique(ours_code, return_counts=True))},
                'era5_classes': {int(k): int(v) for k, v in
                                 zip(*np.unique(era_code, return_counts=True))},
            }
        return out

    upscaled = ctx.upscale(message['values'])
    out = {'available': True, 'regions': {}}
    for name, mask in ctx.era5_regions().items():
        both = mask & np.isfinite(upscaled) & np.isfinite(counterpart)
        if both.sum() < 10:
            out['regions'][name] = {'n': int(both.sum())}
            continue
        a, b = upscaled[both], counterpart[both]
        diff = a - b
        denom = float(np.mean(b))
        out['regions'][name] = {
            'n': int(both.sum()),
            'ours_mean': float(a.mean()), 'era5_mean': float(b.mean()),
            'ours_std': float(a.std()), 'era5_std': float(b.std()),
            'bias': float(diff.mean()),
            'rmse': float(np.sqrt((diff ** 2).mean())),
            'corr': float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0
                    else None,
            'ratio_means': float(a.mean() / denom) if abs(denom) > 1e-30 else None,
            'ratio_stds': float(a.std() / b.std()) if b.std() > 1e-30 else None,
        }
    return out


def leg_d(token, message, ctx, level=None):
    """Recompute the variable from its siblings in the same file."""
    spec = LEG_D.get(token)
    if spec is None:
        return {'available': False,
                'why': 'no identity inside the archive relates this variable to '
                       'others we publish'}
    kind, formula = spec[0], spec[1]
    siblings = ctx.siblings()

    def sib(short):
        return siblings.get((short, _sibling_level(short, level)))

    ours = message['values']
    if token == 'vwsh':
        u100, v100 = sib('100u'), sib('100v')
        u10, v10 = sib('10u'), sib('10v')
        if any(x is None for x in (u100, v100, u10, v10)):
            return {'available': False, 'why': 'a sibling message is absent'}
        expected = np.sqrt((u100 - u10) ** 2 + (v100 - v10) ** 2) / 90.0
    elif token == 'wz':
        omega, temperature = sib('w'), sib('t')
        if omega is None or temperature is None or level is None:
            return {'available': False, 'why': 'w or t absent at this level'}
        rho = (level * 100.0) / (R_DRY * temperature)
        expected = -omega / (rho * G)
    elif token == '2r':
        t2, d2 = sib('2t'), sib('2d')
        if t2 is None or d2 is None:
            return {'available': False, 'why': '2t or 2d absent'}
        # Both over LIQUID water. `2d` is a dewpoint, which is over water by
        # definition; `2r` is a SCREEN-LEVEL humidity, and the WMO convention
        # for those is over water at all temperatures, which is what a station
        # reports at -20 C. The mixed phase belongs to `r` on pressure levels,
        # where it is the IFS's own definition of paramId 157 and where it was
        # measured against ERA5 -- and nothing joins 2 m to 1000 hPa anyway
        # (issue #44). Decided 2026-09-22; see #40.
        #
        # So this is the reconstruction a user makes from the two neighbours,
        # and after #40 removes the clip its only residue should be the
        # dewpoint round trip: `2d` and `Q2` agree to 3.6e-4..1.1e-2 relative
        # in vapour pressure, measured over the whole sample by family 2.
        expected = 100.0 * IFS.esat_water(d2) / IFS.esat_water(t2)
    elif token in ('200u', '200v'):
        u100, v100 = sib('100u'), sib('100v')
        u200 = ours if token == '200u' else sib('200u')
        v200 = sib('200v') if token == '200u' else ours
        if any(x is None for x in (u100, v100, u200, v200)):
            return {'available': False, 'why': 'a sibling wind component is absent'}
        speed100 = np.hypot(u100, v100)
        speed200 = np.hypot(u200, v200)
        finite = np.isfinite(speed100) & np.isfinite(speed200)
        rising = float((speed200[finite] >= speed100[finite]).mean())
        dot = (u100 * u200 + v100 * v200)
        norm = speed100 * speed200
        with np.errstate(invalid='ignore', divide='ignore'):
            cosine = np.where(norm > 1e-6, dot / np.maximum(norm, 1e-30), np.nan)
        ok = np.isfinite(cosine)
        return {
            'available': True, 'kind': kind, 'formula': formula,
            'n_compared': int(finite.sum()),
            'fraction_speed_not_falling': rising,
            'fraction_within_20_degrees': float(
                (cosine[ok] > math.cos(math.radians(20))).mean()),
            'note': 'a bracket, not an identity: it catches a swapped level or a '
                    'flipped sign, and cannot catch an error in the interpolation '
                    'height',
        }
    else:
        return {'available': False, 'why': 'unhandled'}

    both = np.isfinite(ours) & np.isfinite(expected)
    if both.sum() == 0:
        return {'available': False, 'why': 'nothing comparable'}
    diff = np.abs(ours[both] - expected[both])
    scale = max(float(np.abs(expected[both]).max()), 1e-30)
    result = {
        'available': True, 'kind': kind, 'formula': formula,
        'n_compared': int(both.sum()),
        'max_abs_diff': float(diff.max()),
        'max_rel_diff': float(diff.max() / scale),
        'median_abs_diff': float(np.median(diff)),
    }
    if kind == 'exact':
        result['agrees'] = bool(diff.max() <= 1e-4 * scale)
    else:
        result['note'] = ('a physical approximation, so the scatter is the '
                          'physics and is reported rather than asserted')
    return result


# =============================================================================
# One row
# =============================================================================

def compare_one(token, message, ctx, level=None):
    level_hpa = level if message['typeOfLevel'] == 'isobaricInhPa' else None
    regions = ctx.wrf_regions(level_hpa)
    _fail, _note = assertions(token, message, message['values'], ctx.our_land)
    row = {
        'timestep': ctx.timestep,
        'variable': token,
        'shortName': short_of(token),
        'paramId': message['paramId'],
        'level': message['level'],
        'levelType': message['typeOfLevel'],
        'leg_a': {
            'units_declared': message['units'],
            'stepType': message['stepType'],
            'stepRange': message['stepRange'],
            'bitmap': message['bitmap'],
            'stats': {name: stats(message['values'], mask)
                      for name, mask in regions.items()},
            'failures': _fail,
            'notes': _note,
        },
        'leg_b': leg_b(token, message, ctx.timestep),
        'leg_c': leg_c(token, message, ctx, level=level),
        'leg_d': leg_d(token, message, ctx, level=level),
    }
    return row


def all_tokens():
    seen, tokens = {}, []
    for key, entry in REG.WRF_TO_ECMWF_PARAMID.items():
        short = entry['shortName']
        token = next((t for t, k in TOKEN_TO_KEY.items() if k == key), short)
        if short in seen and token == short:
            continue
        seen[short] = token
        tokens.append(token)
    return tokens


def variables_for(args):
    """(token, shortName, level, is_pressure_level) tuples to measure."""
    if args.variable:
        names = args.variable
    elif args.family:
        names = FAMILIES[args.family]
    else:
        names = all_tokens()
    wanted = []
    for token in names:
        entry = _registry_entry(token)
        if entry is None:
            print(f'  ! {token} is not in the registry', file=sys.stderr)
            continue
        levels = entry['levels'] if args.level is None else [args.level]
        is_pl = entry.get('levelType') == 'isobaricInhPa'
        for lev in levels:
            wanted.append((token, entry['shortName'], lev, is_pl))
    return wanted


def cmd_compare(args):
    timesteps = sample_timesteps() if args.all_timesteps else args.timestep
    wanted = variables_for(args)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    incomplete = []
    expected = len(timesteps) * len(wanted)
    with out_path.open('w') as sink:
        for timestep in timesteps:
            if not grib_path(timestep).exists():
                print(f'{timestep}: no GRIB, skipped', file=sys.stderr)
                continue
            ctx = Context(timestep)
            # ONE pass over the GRIB, each message released as soon as it has
            # been used. Holding a whole pressure-level family at once is 169
            # fields of 2.2 million points -- 3 GB -- for no reason.
            # Eight registry entries carry `levels=[None]`: the converter leaves
            # the level alone so eccodes applies the one the parameter
            # definition prescribes -- mostUnstableParcel for mucape/mucin,
            # nominalTop for tisr/tsr/tsrc/ttr/ttrc, and dl. Keying those on
            # (shortName, None) matches nothing, so they are matched on
            # shortName alone and take whatever level the message carries.
            by_key, by_short = {}, {}
            for token, short, lev, is_pl in wanted:
                if lev is None:
                    by_short.setdefault(short, []).append((token, is_pl))
                else:
                    by_key.setdefault((short, lev), []).append((token, is_pl))
            seen = set()
            with open(grib_path(timestep), 'rb') as fh:
                while True:
                    gid = eccodes.codes_grib_new_from_file(fh)
                    if gid is None:
                        break
                    try:
                        short = eccodes.codes_get(gid, 'shortName')
                        key = (short, eccodes.codes_get(gid, 'level'))
                        targets = by_key.get(key) or by_short.get(short)
                        if not targets:
                            continue
                        message = {
                            'values': _message_field(gid),
                            'paramId': eccodes.codes_get(gid, 'paramId'),
                            'units': eccodes.codes_get(gid, 'units'),
                            'typeOfLevel': eccodes.codes_get(gid, 'typeOfLevel'),
                            'level': eccodes.codes_get(gid, 'level'),
                            'stepType': eccodes.codes_get(gid, 'stepType'),
                            'stepRange': eccodes.codes_get(gid, 'stepRange'),
                            'bitmap': bool(eccodes.codes_get(gid, 'bitmapPresent')),
                        }
                    finally:
                        eccodes.codes_release(gid)
                    for token, is_pl in targets:
                        row = compare_one(token, message, ctx,
                                          level=key[1] if is_pl else None)
                        sink.write(json.dumps(row) + '\n')
                        sink.flush()
                        written += 1
                        seen.add((token, key[1] if key in by_key else None))
                        d = row['leg_d']
                        if d.get('kind') == 'exact' and d.get('agrees') is False:
                            row['leg_a']['failures'].append(
                                'leg D identity disagrees: ' + d['formula'])
                        flag = 'FAIL' if row['leg_a']['failures'] else 'ok  '
                        print(f'  {flag} {timestep} {token:<7} lev {key[1]:<5}',
                              flush=True)
            for token, short, lev, is_pl in wanted:
                if (token, lev) not in seen:
                    print(f'{timestep}: {short} level {lev} NOT IN THE GRIB',
                          file=sys.stderr)
                    incomplete.append(f'{timestep} {token} {lev}')
    # Say whether the run finished. A partial file that looks complete is the
    # failure this repo keeps meeting: the staging fetch declared success after
    # 3 of 21 files, and this command's own first pressure-level run was cut off
    # at 154 of 169 rows by a shell timeout while the report that followed it
    # exited 0 on the truncated output.
    print(f'{written} of {expected} expected rows -> {out_path}')
    if incomplete:
        print(f'INCOMPLETE: {len(incomplete)} missing', file=sys.stderr)
        return 1
    if written != expected:
        print(f'INCOMPLETE: {expected - written} rows never written',
              file=sys.stderr)
        return 1
    return 0


# =============================================================================
# The formatter: eight family docs, one table shape
# =============================================================================

def _fmt(value, digits=4):
    if value is None:
        return '--'
    if isinstance(value, bool):
        return 'yes' if value else 'NO'
    if isinstance(value, float):
        if value == 0:
            return '0'
        if abs(value) >= 1e5 or abs(value) < 1e-3:
            return f'{value:.{digits}g}'
        return f'{value:.{digits}g}'
    return str(value)


def cmd_report(args):
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines()
            if line.strip()]
    if not rows:
        print('no rows')
        return 1
    by_var = {}
    for row in rows:
        by_var.setdefault(row['variable'], []).append(row)

    print('| variable | paramId | unit | leg A | leg B | leg C bias | ratio | corr |')
    print('|---|---|---|---|---|---|---|---|')
    for short in sorted(by_var):
        group = by_var[short]
        first = group[0]
        failures = sorted({f for r in group for f in r['leg_a']['failures']})
        leg_a = 'ok' if not failures else f'**{len(failures)} failure(s)**'
        b = first['leg_b']
        if b['kind'] == 'none':
            leg_b_cell = 'not available'
        elif 'agrees' in b:
            worst = max(r['leg_b'].get('max_rel_diff') or 0.0 for r in group)
            leg_b_cell = ('exact' if all(r['leg_b'].get('agrees') for r in group)
                          else f'differs, max rel {worst:.3g}')
        else:
            leg_b_cell = b.get('note', '?')[:40]
        cats = [r['leg_c']['regions']['all'] for r in group
                if r['leg_c'].get('categorical')
                and 'class_agreement' in r['leg_c'].get('regions', {}).get('all', {})]
        cs = [r['leg_c']['regions']['all'] for r in group
              if r['leg_c'].get('available') and 'all' in r['leg_c'].get('regions', {})
              and 'bias' in r['leg_c']['regions']['all']]
        if cats:
            agree = float(np.mean([c['class_agreement'] for c in cats]))
            n_ours = len({k for c in cats for k in c['ours_classes']})
            n_era = len({k for c in cats for k in c['era5_classes']})
            c_cells = (f'{100 * agree:.1f}% same class',
                       f'{n_ours} vs {n_era} classes', 'n/a (codes)')
        elif cs:
            bias = np.mean([c['bias'] for c in cs])
            ratio = np.mean([c['ratio_means'] for c in cs
                             if c['ratio_means'] is not None] or [np.nan])
            corr = np.mean([c['corr'] for c in cs if c['corr'] is not None]
                           or [np.nan])
            c_cells = (_fmt(float(bias)), _fmt(float(ratio)), _fmt(float(corr)))
        else:
            why = next((r['leg_c'].get('why') for r in group
                        if not r['leg_c'].get('available')), 'not available')
            c_cells = (why[:40], '--', '--')
        print(f'| `{short}` | {first["paramId"]} | {first["leg_a"]["units_declared"]} '
              f'| {leg_a} | {leg_b_cell} | {c_cells[0]} | {c_cells[1]} | {c_cells[2]} |')

    print()
    for short in sorted(by_var):
        failures = sorted({f for r in by_var[short] for f in r['leg_a']['failures']})
        for failure in failures:
            print(f'- **`{short}`**: {failure}')
    notes = [(s2, n) for s2 in sorted(by_var)
             for n in sorted({x for r in by_var[s2] for x in r['leg_a'].get('notes', [])})]
    if notes:
        print()
        print('Notes (not failures):')
        for short, note in notes:
            n_at = sum(1 for r in by_var[short] if note in r['leg_a'].get('notes', []))
            print(f'- `{short}` at {n_at} of {len(by_var[short])} rows: {note}')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('compare')
    c.add_argument('--family', type=int, choices=sorted(FAMILIES))
    c.add_argument('--variable', nargs='+')
    c.add_argument('--level', type=int)
    c.add_argument('--timestep', nargs='+', default=['2024-07-15T12'])
    c.add_argument('--all-timesteps', action='store_true')
    c.add_argument('--out', default='audit_rows.jsonl')
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser('report')
    r.add_argument('--rows', default='audit_rows.jsonl')
    r.set_defaults(func=cmd_report)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
