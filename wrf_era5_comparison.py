#!/usr/bin/env python3
"""WRF -> ECMWF variable registry for the CHAPTER GRIB archive.

Each entry of WRF_TO_ECMWF_PARAMID maps one produced field to its ECMWF
identity and to the GRIB level it is written on. The key is either a native
wrfout variable name (`T2`, `U`, `RAINNC`) or the name of a derived field
computed in convert_to_pressure_levels.py (`tk`, `q`, `mucape`, `u100`).

Entry format
------------
    'T2': {
        'shortName': '2t', 'paramId': 167, 'long_name': ..., 'units': 'K',
        'levelType': 'heightAboveGround',   # GRIB2 typeOfLevel, or None
        'levels': [2],                      # one GRIB message per entry
    }

`levelType=None` means: do not touch the level, let eccodes apply the one the
parameter definition prescribes (this is how `mucape`/`mucin` end up on
`mostUnstableParcel`).

`stepType` is absent for instantaneous fields. Fields accumulated since 00Z of
the same day carry `'stepType': 'accum'`; `'max1h'` marks a maximum over the
preceding hour (see accum_ref.py and the writer in convert_to_pressure_levels).

Deliberately NOT produced
-------------------------
Fields that are absent from the wrfout, or present but useless, are documented
in MISSING_VARIABLES.md together with the routes by which some of them could
still be obtained. The short list:

* not in the run at all: TKE and PBLH (the PBL scheme is YSU, non-local), TSK,
  HFX/LH, ALBEDO, and everything to do with ocean waves, currents and sea-ice
  properties (no ocean or wave coupling);
* not in the hourly output but recovered from the WPS static file geo_em_d02,
  which arrived from LRZ on 2026-09-18 after this file had recorded it as lost:
  LANDUSEF/SOILCTOP/CLAYFRAC/SANDFRAC/LAKE_DEPTH, hence cvl/cvh/tvl/tvh/slt/
  cl/dl. GREENFRAC came with them but has no ERA5 parameter;
* present but identically zero on every sampled timestep: ACHFX, ACLHF,
  ACGRDFLX, NOAHRES, SSTSK, SST_INPUT, SWNORM, ACSNOW, HAILNC, ACLWDNT, and --
  because CU_PHYSICS=0 -- RAINC/RAINSH/PREC_ACC_C, hence no `cp` and no `csf`;
* present and alive but with no ERA5 parameter: QGRAUP (no graupel in ERA5),
  REFL_10CM/REFD_MAX/UP_HELI_MAX/W_UP_MAX/LPI/HAIL_MAX2D, SR, RHOSNF,
  SNOWFALLAC (snow DEPTH, not water equivalent), Q2, SH2O, TMN, SHDMAX/SHDMIN;
* redundant: ACRUNOFF (verified identical to SFROFF, not the total), `lsp`
  (identical to tp since RAINC is zero), SNOALB (an annual climatological cap,
  not ERA5's `asn`);
* excluded by decision: the gust components 10efg/10nfg (only a resolved-wind
  maximum exists, so their direction would be an assumption); lai_lv/lai_hv,
  because the model carries a single LAI per cell while ERA5 wants one per
  vegetation class, and any split between the two would be our assumption.
"""

# Pressure levels shared with convert_to_pressure_levels.PRESSURE_LEVELS.
PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

_PL = dict(levelType='isobaricInhPa', levels=PRESSURE_LEVELS)
_SFC = dict(levelType='surface', levels=[0])
_ATM = dict(levelType='entireAtmosphere', levels=[0])
# Top of atmosphere: leave the level alone so eccodes applies the `nominalTop`
# that the parameter definition prescribes (tsr, ttr, tisr, tsrc, ttrc).
_TOP = dict(levelType=None, levels=[None])
# Lake depth: same trick, so eccodes applies the `entireLake` surface its own
# definition prescribes (verified on read-back).
_LAKE = dict(levelType=None, levels=[None])


def _h(z):
    """Height above ground, in metres."""
    return dict(levelType='heightAboveGround', levels=[z])


WRF_TO_ECMWF_PARAMID = {

    # ---------------- pressure levels (13) ----------------
    'U':      {'shortName': 'u',    'paramId': 131,    'long_name': 'U component of wind', 'units': 'm/s', **_PL},
    'V':      {'shortName': 'v',    'paramId': 132,    'long_name': 'V component of wind', 'units': 'm/s', **_PL},
    'tk':     {'shortName': 't',    'paramId': 130,    'long_name': 'Temperature', 'units': 'K', **_PL},
    'z':      {'shortName': 'z',    'paramId': 129,    'long_name': 'Geopotential', 'units': 'm^2/s^2', **_PL},
    'q':      {'shortName': 'q',    'paramId': 133,    'long_name': 'Specific humidity', 'units': 'kg/kg', **_PL},
    'rh':     {'shortName': 'r',    'paramId': 157,    'long_name': 'Relative humidity', 'units': '%', **_PL},
    'QCLOUD': {'shortName': 'clwc', 'paramId': 246,    'long_name': 'Specific cloud liquid water content', 'units': 'kg/kg', **_PL},
    'QICE':   {'shortName': 'ciwc', 'paramId': 247,    'long_name': 'Specific cloud ice water content', 'units': 'kg/kg', **_PL},
    # Both vertical-velocity conventions: omega in Pa/s and the geometric w in m/s.
    'omega':  {'shortName': 'w',    'paramId': 135,    'long_name': 'Vertical velocity (pressure)', 'units': 'Pa/s', **_PL},
    'wa':     {'shortName': 'wz',   'paramId': 260238, 'long_name': 'Geometric vertical velocity', 'units': 'm/s', **_PL},
    # CLDFRA is a FRACTIONAL cloud field (ICLOUD=1 is Xu-Randall): measured, only
    # 18-22% of cloudy points sit exactly at 1, the rest spread over 0-1.
    'CLDFRA': {'shortName': 'cc',   'paramId': 248,    'long_name': 'Fraction of cloud cover', 'units': '(0-1)', **_PL},
    'QRAIN':  {'shortName': 'crwc', 'paramId': 75,     'long_name': 'Specific rain water content', 'units': 'kg/kg', **_PL},
    'QSNOW':  {'shortName': 'cswc', 'paramId': 76,     'long_name': 'Specific snow water content', 'units': 'kg/kg', **_PL},

    # ---------------- 2 m ----------------
    'T2':     {'shortName': '2t',   'paramId': 167,    'long_name': '2m temperature', 'units': 'K', **_h(2)},
    'td2':    {'shortName': '2d',   'paramId': 168,    'long_name': '2m dewpoint temperature', 'units': 'K', **_h(2)},
    'rh2':    {'shortName': '2r',   'paramId': 260242, 'long_name': '2m relative humidity', 'units': '%', **_h(2)},

    # ---------------- 10 m / 100 m / 200 m ----------------
    'U10':    {'shortName': '10u',  'paramId': 165,    'long_name': '10m U component of wind', 'units': 'm/s', **_h(10)},
    'V10':    {'shortName': '10v',  'paramId': 166,    'long_name': '10m V component of wind', 'units': 'm/s', **_h(10)},
    # WSPD10MAX is the maximum of the RESOLVED 10 m wind over the output hour,
    # not a gust parameterisation -- hence stepType max1h. See MISSING_VARIABLES.md.
    'WSPD10MAX': {'shortName': '10fg', 'paramId': 49, 'long_name': '10m wind gust (hourly max of resolved wind)', 'units': 'm/s', 'stepType': 'max1h', **_h(10)},
    'u100':   {'shortName': '100u', 'paramId': 228246, 'long_name': '100m U component of wind', 'units': 'm/s', **_h(100)},
    'v100':   {'shortName': '100v', 'paramId': 228247, 'long_name': '100m V component of wind', 'units': 'm/s', **_h(100)},
    'u200':   {'shortName': '200u', 'paramId': 228239, 'long_name': '200m U component of wind', 'units': 'm/s', **_h(200)},
    'v200':   {'shortName': '200v', 'paramId': 228240, 'long_name': '200m V component of wind', 'units': 'm/s', **_h(200)},
    # Bulk 10 m -> 100 m shear, written at the top of the layer.
    'vwsh':   {'shortName': 'vwsh', 'paramId': 260068, 'long_name': 'Vertical speed shear (bulk 10-100 m)', 'units': 's^-1', **_h(100)},

    # ---------------- column / cloud ----------------
    'slp':    {'shortName': 'msl',  'paramId': 151,    'long_name': 'Mean sea level pressure', 'units': 'Pa', 'levelType': 'meanSea', 'levels': [0]},
    'tcw':    {'shortName': 'tcw',  'paramId': 136,    'long_name': 'Total column water', 'units': 'kg/m^2', **_ATM},
    'tqv':    {'shortName': 'tcwv', 'paramId': 137,    'long_name': 'Total column water vapour', 'units': 'kg/m^2', **_ATM},
    # Per-species column integrals, from the same dp the tcw block already builds.
    # Graupel has no ERA5 parameter, so QGRAUP enters tcw but is not written alone.
    'tclw':   {'shortName': 'tclw', 'paramId': 78,     'long_name': 'Total column cloud liquid water', 'units': 'kg/m^2', **_ATM},
    'tciw':   {'shortName': 'tciw', 'paramId': 79,     'long_name': 'Total column cloud ice water', 'units': 'kg/m^2', **_ATM},
    'tcrw':   {'shortName': 'tcrw', 'paramId': 228089, 'long_name': 'Total column rain water', 'units': 'kg/m^2', **_ATM},
    'tcsw':   {'shortName': 'tcsw', 'paramId': 228090, 'long_name': 'Total column snow water', 'units': 'kg/m^2', **_ATM},
    'tcc':    {'shortName': 'tcc',  'paramId': 164,    'long_name': 'Total cloud cover', 'units': '(0-1)', **_ATM},
    'hcc':    {'shortName': 'hcc',  'paramId': 188,    'long_name': 'High cloud cover', 'units': '(0-1)', **_ATM},
    'mcc':    {'shortName': 'mcc',  'paramId': 187,    'long_name': 'Medium cloud cover', 'units': '(0-1)', **_ATM},
    'lcc':    {'shortName': 'lcc',  'paramId': 186,    'long_name': 'Low cloud cover', 'units': '(0-1)', **_ATM},

    # ---------------- instability ----------------
    # levelType None: eccodes puts these on 'mostUnstableParcel' by definition.
    'mucape': {'shortName': 'mucape', 'paramId': 228235, 'long_name': 'Most-unstable CAPE', 'units': 'J/kg', 'levelType': None, 'levels': [None]},
    'mucin':  {'shortName': 'mucin',  'paramId': 228236, 'long_name': 'Most-unstable CIN', 'units': 'J/kg', 'levelType': None, 'levels': [None]},

    # ---------------- surface, instantaneous ----------------
    'HGT':      {'shortName': 'z',    'paramId': 129,    'long_name': 'Geopotential (surface)', 'units': 'm^2/s^2', **_SFC},
    'LANDMASK': {'shortName': 'lsm',  'paramId': 172,    'long_name': 'Land-sea mask', 'units': '(0-1)', **_SFC},
    'PSFC':     {'shortName': 'sp',   'paramId': 134,    'long_name': 'Surface pressure', 'units': 'Pa', **_SFC},
    'VAR_SSO':  {'shortName': 'sdor', 'paramId': 160,    'long_name': 'Standard deviation of orography', 'units': 'm', **_SFC},
    # DECLARED APPROXIMATION: ERA5's slor is the slope of the SUB-GRID orography,
    # a parameter of the form-drag scheme derived from a finer dataset inside the
    # box. What we write is |grad HGT| of the RESOLVED 3 km terrain. At 3 km the
    # two are close in spirit but they are not the same quantity; kept, declared.
    'slor':     {'shortName': 'slor', 'paramId': 163,    'long_name': 'Slope of orography (resolved, 3 km)', 'units': 'Numeric', **_SFC},
    'skt':      {'shortName': 'skt',  'paramId': 235,    'long_name': 'Skin temperature (inverted from upward longwave)', 'units': 'K', **_SFC},
    'SST':      {'shortName': 'sst',  'paramId': 34,     'long_name': 'Sea surface temperature', 'units': 'K', **_SFC},
    'SEAICE':   {'shortName': 'ci',   'paramId': 31,     'long_name': 'Sea ice area fraction', 'units': '(0-1)', **_SFC},

    # ---------------- land surface, static (from geo_em.d02) ----------------
    # These seven were dropped on 2026-09-17 for want of the fractional cover,
    # which lives in geo_em_d02 -- recovered from LRZ on 2026-09-18, after this
    # file had recorded it as irrecoverable. The hourly wrfout carry only the
    # DOMINANT category, and over this domain that category holds just 90.1% of
    # a land cell on average while 17.9% of land cells carry both high and low
    # vegetation above 5%: a state one category per cell cannot express at all.
    # Every mapping decision lives in static_ref.py, which writes the sidecar
    # these are filled from; the sidecar meta records the table that produced
    # the numbers. Verified: LU_INDEX agrees with the wrfout IVGTYP on 100.00%
    # of points once the lake recode (sf_lake_physics=0) is excluded.
    'cvl':  {'shortName': 'cvl',  'paramId': 27,     'long_name': 'Low vegetation cover', 'units': '(0-1)', **_SFC},
    'cvh':  {'shortName': 'cvh',  'paramId': 28,     'long_name': 'High vegetation cover', 'units': '(0-1)', **_SFC},
    # The dominant low/high MODIS-IGBP class translated to ECMWF code table
    # 4.234 (static_ref.VEG_TYPE_4234). Every row of that table is a semantic
    # identity -- the ECMWF type names the same vegetation as the MODIS class --
    # with one exception: MODIS carries no shrub phenology while 4.234 splits
    # evergreen (16) from deciduous (17) shrubs. Rather than invent one, tvl is
    # MISSING where a shrubland dominates the low cover (124672 cells, 15.8% of
    # those with cvl > 0, essentially Iberia and the North African margin); cvl
    # still carries the cover there. tvh needs no mask.
    'tvl':  {'shortName': 'tvl',  'paramId': 29,     'long_name': 'Type of low vegetation (ECMWF code table 4.234)', 'units': '~', **_SFC},
    'tvh':  {'shortName': 'tvh',  'paramId': 30,     'long_name': 'Type of high vegetation (ECMWF code table 4.234)', 'units': '~', **_SFC},
    # Computed with the FAO clay/sand thresholds that DEFINE ECMWF's seven soil
    # types, applied to geo_em's CLAYFRAC/SANDFRAC -- so the quantity IS the
    # ERA5 one, where translating STATSGO category numbers would have been our
    # invention. Every land point classifies; type 7 (tropical organic) never
    # occurs here. One collision to know about: eccodes resolves slt to
    # discipline 2/3/0, which WMO table 4.213 reads as a different 11-value
    # list. This archive is ECMWF semantics throughout, and so is this message.
    'slt':  {'shortName': 'slt',  'paramId': 43,     'long_name': 'Soil type (ECMWF 7 classes)', 'units': '~', **_SFC},
    # cl is NOT redundant with lsm, as an earlier note in this file claimed:
    # 19309 cells with LANDMASK=1 carry a sub-grid lake, and WRF discarded the
    # class at runtime (sf_lake_physics=0 recodes 21 -> 17). dl is the GLDB
    # depth that came with it, masked off-lake -- LAKE_DEPTH is the 10 m WPS
    # default fill on 99.56% of the domain, so unmasked it would ship a fake
    # lake everywhere. No model state responds to either: they are boundary
    # data, published as such.
    'cl':   {'shortName': 'cl',   'paramId': 26,     'long_name': 'Lake cover', 'units': '(0-1)', **_SFC},
    'dl':   {'shortName': 'dl',   'paramId': 228007, 'long_name': 'Lake total depth', 'units': 'm', **_LAKE},

    'ALBBCK':  {'shortName': 'al',     'paramId': 174,    'long_name': 'Albedo (climatological, snow-free background)', 'units': '(0-1)', **_SFC},
    # Actual all-sky albedo; undefined at night -> written as a bitmap there.
    'fal':     {'shortName': 'fal',    'paramId': 243,    'long_name': 'Forecast albedo (upward/downward SW at surface)', 'units': '(0-1)', **_SFC},
    'UST':     {'shortName': 'zust',   'paramId': 228003, 'long_name': 'Friction velocity', 'units': 'm/s', **_SFC},
    'ZNT':     {'shortName': 'fsr',    'paramId': 244,    'long_name': 'Forecast surface roughness', 'units': 'm', **_SFC},
    # tau = rho u*^2, projected on the 10 m wind direction (similarity theory,
    # the same one WRF used to produce UST). Instantaneous, not time-integrated.
    'iews':    {'shortName': 'iews',   'paramId': 229,    'long_name': 'Instantaneous eastward turbulent surface stress', 'units': 'N/m^2', **_SFC},
    'inss':    {'shortName': 'inss',   'paramId': 230,    'long_name': 'Instantaneous northward turbulent surface stress', 'units': 'N/m^2', **_SFC},
    'SNOW':    {'shortName': 'sd',     'paramId': 141,    'long_name': 'Snow depth (water equivalent)', 'units': 'm', **_SFC},
    'rsn':     {'shortName': 'rsn',    'paramId': 33,     'long_name': 'Snow density', 'units': 'kg/m^3', **_SFC},
    # SNOWC is described as a flag but is continuous (measured 267824 distinct
    # values); ERA5 reports snow cover in per cent, hence UNIT_SCALE 100.
    'SNOWC':   {'shortName': 'snowc',  'paramId': 260038, 'long_name': 'Snow cover', 'units': '%', **_SFC},
    # SOILT1 is the temperature at the top of the snow/soil column; it is only a
    # snow temperature where the pack really covers the cell, so it is masked to
    # SNOWC > 0.9 (see the tsn block in convert_to_pressure_levels.py). Out of
    # season the message is legitimately empty: summer 2019 has no such point.
    'tsn':     {'shortName': 'tsn',    'paramId': 238,    'long_name': 'Temperature of snow layer', 'units': 'K', **_SFC},
    'CANWAT':  {'shortName': 'src',    'paramId': 198,    'long_name': 'Skin reservoir content', 'units': 'm', **_SFC},
    # ---------------- soil: ERA5 layer averages of the RUC profile ----------
    # Dropped on 2026-09-17, and rightly so: RUC's point values at 0, 5, 20, 40,
    # 160 and 300 cm are not ERA5's averages over 0-7, 7-28, 28-100 and
    # 100-289 cm. But they can be integrated into them. The whole ERA5 column
    # lies INSIDE the RUC nodes -- 289 cm is above the deepest node, 0 cm is the
    # first one -- so each layer average is the exact integral of RUC's own
    # piecewise-linear profile and nothing is extrapolated anywhere. The 4x6
    # weight matrix is in convert_to_pressure_levels.SOIL_LAYER_WEIGHTS.
    # swvl uses SMOIS (total water, liquid + ice), which is what swvl means;
    # SH2O is the liquid part only. Masked over water, where RUC integrates no
    # soil column -- and that mask MOVES, because the sea-ice reclassification
    # turns ~2469 sea points into land between seasons.
    'swvl1': {'shortName': 'swvl1', 'paramId': 39,  'long_name': 'Volumetric soil water layer 1 (0-7 cm)', 'units': 'm^3/m^3', **_SFC},
    'swvl2': {'shortName': 'swvl2', 'paramId': 40,  'long_name': 'Volumetric soil water layer 2 (7-28 cm)', 'units': 'm^3/m^3', **_SFC},
    'swvl3': {'shortName': 'swvl3', 'paramId': 41,  'long_name': 'Volumetric soil water layer 3 (28-100 cm)', 'units': 'm^3/m^3', **_SFC},
    'swvl4': {'shortName': 'swvl4', 'paramId': 42,  'long_name': 'Volumetric soil water layer 4 (100-289 cm)', 'units': 'm^3/m^3', **_SFC},
    'stl1':  {'shortName': 'stl1',  'paramId': 139, 'long_name': 'Soil temperature level 1 (0-7 cm)', 'units': 'K', **_SFC},
    'stl2':  {'shortName': 'stl2',  'paramId': 170, 'long_name': 'Soil temperature level 2 (7-28 cm)', 'units': 'K', **_SFC},
    'stl3':  {'shortName': 'stl3',  'paramId': 183, 'long_name': 'Soil temperature level 3 (28-100 cm)', 'units': 'K', **_SFC},
    'stl4':  {'shortName': 'stl4',  'paramId': 236, 'long_name': 'Soil temperature level 4 (100-289 cm)', 'units': 'K', **_SFC},

    # ---------------- accumulated since 00Z of the same day ----------------
    'RAINNC':  {'shortName': 'tp',   'paramId': 228,    'long_name': 'Total precipitation', 'units': 'm', 'stepType': 'accum', **_SFC},
    'tirf':    {'shortName': 'tirf', 'paramId': 235015, 'long_name': 'Time integral of rain flux (rain only)', 'units': 'kg/m^2', 'stepType': 'accum', **_SFC},
    'SNOWNC':  {'shortName': 'sf',   'paramId': 144,    'long_name': 'Snowfall (water equivalent)', 'units': 'm', 'stepType': 'accum', **_SFC},
    'SFROFF':  {'shortName': 'sro',  'paramId': 8,      'long_name': 'Surface runoff', 'units': 'm', 'stepType': 'accum', **_SFC},
    'UDROFF':  {'shortName': 'ssro', 'paramId': 9,      'long_name': 'Sub-surface runoff', 'units': 'm', 'stepType': 'accum', **_SFC},
    'ro':      {'shortName': 'ro',   'paramId': 205,    'long_name': 'Runoff (surface + sub-surface)', 'units': 'm', 'stepType': 'accum', **_SFC},

    # ---------------- radiation, accumulated since 00Z --------------------------
    # Every one of these is monotone within a run (verified on March and July,
    # five hours each), so referring them to 00Z is sound. ECMWF sign convention:
    # a net flux is downward minus upward, so ttr/ttrc come out negative.
    # Downward (native, straight through the accumulated branch):
    'ACSWDNB':  {'shortName': 'ssrd',  'paramId': 169,    'long_name': 'Surface solar radiation downwards', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'ACLWDNB':  {'shortName': 'strd',  'paramId': 175,    'long_name': 'Surface thermal radiation downwards', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'ACSWDNBC': {'shortName': 'ssrdc', 'paramId': 228129, 'long_name': 'Surface solar radiation downwards, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'ACLWDNBC': {'shortName': 'strdc', 'paramId': 228130, 'long_name': 'Surface thermal radiation downwards, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'ACSWDNT':  {'shortName': 'tisr',  'paramId': 212,    'long_name': 'TOA incident solar radiation', 'units': 'J/m^2', 'stepType': 'accum', **_TOP},
    # Net (derived: downward minus upward):
    'ssr':      {'shortName': 'ssr',   'paramId': 176,    'long_name': 'Surface net solar radiation', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'str':      {'shortName': 'str',   'paramId': 177,    'long_name': 'Surface net thermal radiation', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'ssrc':     {'shortName': 'ssrc',  'paramId': 210,    'long_name': 'Surface net solar radiation, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'strc':     {'shortName': 'strc',  'paramId': 211,    'long_name': 'Surface net thermal radiation, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    'tsr':      {'shortName': 'tsr',   'paramId': 178,    'long_name': 'Top net solar radiation', 'units': 'J/m^2', 'stepType': 'accum', **_TOP},
    'tsrc':     {'shortName': 'tsrc',  'paramId': 208,    'long_name': 'Top net solar radiation, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_TOP},
    'ttr':      {'shortName': 'ttr',   'paramId': 179,    'long_name': 'Top net thermal radiation', 'units': 'J/m^2', 'stepType': 'accum', **_TOP},
    'ttrc':     {'shortName': 'ttrc',  'paramId': 209,    'long_name': 'Top net thermal radiation, clear sky', 'units': 'J/m^2', 'stepType': 'accum', **_TOP},
    # ACSNOM ('smlt') is deliberately absent: it is NOT a monotone run-init
    # accumulator -- individual points drop back to zero within a run (measured
    # -7.26 mm against 00Z on 2024-07-01), so referring it to 00Z would publish
    # a field that is wrong under the ERA5 name. See MISSING_VARIABLES.md.
}

# Number of GRIB messages a complete file must contain.
EXPECTED_MESSAGES = sum(len(v['levels']) for v in WRF_TO_ECMWF_PARAMID.values())


# ==============================================================================
# WRF VARIABLES
# ==============================================================================

# WRF variables from selection
wrf_variables = {
    # Invariants / Static fields
    'LU_INDEX': 'LAND USE CATEGORY',
    'VAR_SSO': 'standard deviation of subgrid-scale orography',
    'HGT': 'Terrain Height',
    'LANDMASK': 'LAND MASK (1 FOR LAND, 0 FOR WATER)',
    'LAKEMASK': 'LAKE MASK (1 FOR LAKE, 0 FOR NON-LAKE)',
    'XLAT': 'LATITUDE, SOUTH IS NEGATIVE',
    'XLONG': 'LONGITUDE, WEST IS NEGATIVE',
    'XLAND': 'LAND MASK (1 FOR LAND, 2 FOR WATER)',
    'IVGTYP': 'DOMINANT VEGETATION CATEGORY',
    'ISLTYP': 'DOMINANT SOIL CATEGORY',
    'SHDMAX': 'ANNUAL MAX VEG FRACTION',
    'SHDMIN': 'ANNUAL MIN VEG FRACTION',
    'VEGFRA': 'VEGETATION FRACTION',
    'LAI': 'LEAF AREA INDEX',
    'VAR': 'OROGRAPHIC VARIANCE',
    
    # Atmospheric state variables
    'U': 'x-wind component',
    'V': 'y-wind component', 
    'W': 'z-wind component',
    'T': 'perturbation potential temperature theta-t0',
    'P': 'perturbation pressure',
    'PB': 'BASE STATE PRESSURE',
    'PH': 'perturbation geopotential',
    'PHB': 'base-state geopotential',
    'P_HYD': 'hydrostatic pressure',
    
    # Moisture variables
    'QVAPOR': 'Water vapor mixing ratio',
    'QCLOUD': 'Cloud water mixing ratio',
    'QRAIN': 'Rain water mixing ratio',
    'QICE': 'Ice mixing ratio',
    'QSNOW': 'Snow mixing ratio',
    'QGRAUP': 'Graupel mixing ratio',
    'CLDFRA': 'CLOUD FRACTION',
    'REFL_10CM': 'Radar reflectivity (lamda = 10 cm)',
    
    # Surface variables
    'T2': 'TEMP at 2 M',
    'Q2': 'QV at 2 M',
    'PSFC': 'SFC PRESSURE',
    'U10': 'U at 10 M',
    'V10': 'V at 10 M',
    'TSK': 'SKIN SEA SURFACE TEMPERATURE (from SSTSK)',
    'SSTSK': 'SKIN SEA SURFACE TEMPERATURE',
    'SST': 'SEA SURFACE TEMPERATURE',
    'SEAICE': 'SEA ICE FLAG',
    
    # Soil variables
    'TSLB': 'SOIL TEMPERATURE',
    'SMOIS': 'SOIL MOISTURE',
    'SH2O': 'SOIL LIQUID WATER',
    'TMN': 'SOIL TEMPERATURE AT LOWER BOUNDARY',
    
    # Snow variables
    'SNOW': 'SNOW WATER EQUIVALENT',
    'SNOWH': 'PHYSICAL SNOW DEPTH',
    'SNOWC': 'FLAG INDICATING SNOW COVERAGE (1 FOR SNOW COVER)',
    'SNOWNC': 'ACCUMULATED TOTAL GRID SCALE SNOW AND ICE',
    'SNOWFALLAC': 'RUN-TOTAL ACCUMULATED SNOWFALL [mm]',
    
    # Precipitation
    'RAINC': 'ACCUMULATED TOTAL CUMULUS PRECIPITATION',
    'RAINNC': 'ACCUMULATED TOTAL GRID SCALE PRECIPITATION',
    'RAINSH': 'ACCUMULATED SHALLOW CUMULUS PRECIPITATION',
    'GRAUPELNC': 'ACCUMULATED TOTAL GRID SCALE GRAUPEL',
    'HAILNC': 'ACCUMULATED TOTAL GRID SCALE HAIL',
    
    # Radiation
    'SWDOWN': 'DOWNWARD SHORT WAVE FLUX AT GROUND SURFACE',
    'SWDOWNC': 'DOWNWARD CLEAR-SKY SHORT WAVE FLUX AT GROUND SURFACE',
    'GLW': 'DOWNWARD LONG WAVE FLUX AT GROUND SURFACE',
    'SWUPB': 'INSTANTANEOUS UPWELLING SHORTWAVE FLUX AT BOTTOM',
    'SWUPBC': 'INSTANTANEOUS UPWELLING CLEAR SKY SHORTWAVE FLUX AT BOTTOM',
    'SWDNB': 'INSTANTANEOUS DOWNWELLING SHORTWAVE FLUX AT BOTTOM',
    'SWDNBC': 'INSTANTANEOUS DOWNWELLING CLEAR SKY SHORTWAVE FLUX AT BOTTOM',
    'LWUPB': 'INSTANTANEOUS UPWELLING LONGWAVE FLUX AT BOTTOM',
    'LWUPBC': 'INSTANTANEOUS UPWELLING CLEAR SKY LONGWAVE FLUX AT BOTTOM',
    'LWDNB': 'INSTANTANEOUS DOWNWELLING LONGWAVE FLUX AT BOTTOM',
    'LWDNBC': 'INSTANTANEOUS DOWNWELLING CLEAR SKY LONGWAVE FLUX AT BOTTOM',
    'SWUPT': 'INSTANTANEOUS UPWELLING SHORTWAVE FLUX AT TOP',
    'SWUPTC': 'INSTANTANEOUS UPWELLING CLEAR SKY SHORTWAVE FLUX AT TOP',
    'SWDNT': 'INSTANTANEOUS DOWNWELLING SHORTWAVE FLUX AT TOP',
    'SWDNTC': 'INSTANTANEOUS DOWNWELLING CLEAR SKY SHORTWAVE FLUX AT TOP',
    'LWUPT': 'INSTANTANEOUS UPWELLING LONGWAVE FLUX AT TOP',
    'LWUPTC': 'INSTANTANEOUS UPWELLING CLEAR SKY LONGWAVE FLUX AT TOP',
    'LWDNT': 'INSTANTANEOUS DOWNWELLING LONGWAVE FLUX AT TOP',
    'LWDNTC': 'INSTANTANEOUS DOWNWELLING CLEAR SKY LONGWAVE FLUX AT TOP',
    'OLR': 'TOA OUTGOING LONG WAVE',
    'ACSWUPB': 'ACCUMULATED UPWELLING SHORTWAVE FLUX AT BOTTOM',
    'ACSWDNB': 'ACCUMULATED DOWNWELLING SHORTWAVE FLUX AT BOTTOM',
    'ACLWUPB': 'ACCUMULATED UPWELLING LONGWAVE FLUX AT BOTTOM',
    'ACLWDNB': 'ACCUMULATED DOWNWELLING LONGWAVE FLUX AT BOTTOM',
    
    # Boundary layer / Surface fluxes
    'UST': 'U* IN SIMILARITY THEORY',
    'ZNT': 'TIME-VARYING ROUGHNESS LENGTH',
    'ACHFX': 'ACCUMULATED UPWARD HEAT FLUX AT THE SURFACE',
    'ACLHF': 'ACCUMULATED UPWARD LATENT HEAT FLUX AT THE SURFACE',
    
    # Cloud / Atmospheric
    'CAPE': 'CONVECTIVE AVAILABLE POTENTIAL ENERGY',
    'LPI': 'Lightning Potential Index',
    
    # Other
    'CANWAT': 'CANOPY WATER',
    'SFROFF': 'SURFACE RUNOFF',
    'UDROFF': 'UNDERGROUND RUNOFF',
    'ACRUNOFF': 'ACCUMULATED RUNOFF',
    'ALBBCK': 'BACKGROUND ALBEDO',
    'COSZEN': 'COS of SOLAR ZENITH ANGLE',
    'SR': 'fraction of frozen precipitation',
}
