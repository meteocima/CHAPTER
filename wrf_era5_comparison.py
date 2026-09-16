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
Fields that are absent from the wrfout, or present but identically zero on
every sampled timestep, are documented in MISSING_VARIABLES.md together with
the routes by which some of them could still be obtained. The short list:
TKE and PBLH (the PBL scheme is YSU, non-local), TSK, HFX/LH (ACHFX/ACLHF are
identically zero), ALBEDO, LANDUSEF/GREENFRAC/SOILCTOP, and everything to do
with ocean waves, currents and sea-ice properties (no ocean or wave coupling).
"""

# Pressure levels shared with convert_to_pressure_levels.PRESSURE_LEVELS.
PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

_PL = dict(levelType='isobaricInhPa', levels=PRESSURE_LEVELS)
_SFC = dict(levelType='surface', levels=[0])
_ATM = dict(levelType='entireAtmosphere', levels=[0])


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
    'slor':     {'shortName': 'slor', 'paramId': 163,    'long_name': 'Slope of sub-gridscale orography', 'units': 'Numeric', **_SFC},
    'skt':      {'shortName': 'skt',  'paramId': 235,    'long_name': 'Skin temperature (from upward longwave)', 'units': 'K', **_SFC},
    'SST':      {'shortName': 'sst',  'paramId': 34,     'long_name': 'Sea surface temperature', 'units': 'K', **_SFC},
    'SEAICE':   {'shortName': 'ci',   'paramId': 31,     'long_name': 'Sea ice area fraction', 'units': '(0-1)', **_SFC},

    # ---------------- land surface (ERA5 names for the fields we have) ----------------
    'IVGTYP':  {'shortName': 'tvl',    'paramId': 29,     'long_name': 'Type of low vegetation (WRF dominant category)', 'units': 'category', **_SFC},
    'ISLTYP':  {'shortName': 'slt',    'paramId': 43,     'long_name': 'Soil type (WRF dominant category)', 'units': 'category', **_SFC},
    'VEGFRA':  {'shortName': 'cvl',    'paramId': 27,     'long_name': 'Low vegetation cover', 'units': '(0-1)', **_SFC},
    'LAI':     {'shortName': 'lai_lv', 'paramId': 66,     'long_name': 'Leaf area index, low vegetation', 'units': 'm^2/m^2', **_SFC},
    'UST':     {'shortName': 'zust',   'paramId': 228003, 'long_name': 'Friction velocity', 'units': 'm/s', **_SFC},
    'ZNT':     {'shortName': 'fsr',    'paramId': 244,    'long_name': 'Forecast surface roughness', 'units': 'm', **_SFC},
    'SNOW':    {'shortName': 'sd',     'paramId': 141,    'long_name': 'Snow depth (water equivalent)', 'units': 'm', **_SFC},
    'rsn':     {'shortName': 'rsn',    'paramId': 33,     'long_name': 'Snow density', 'units': 'kg/m^3', **_SFC},
    'CANWAT':  {'shortName': 'src',    'paramId': 198,    'long_name': 'Skin reservoir content', 'units': 'm', **_SFC},
    # RUC has 6 soil levels (0, 5, 20, 40, 160, 300 cm); ERA5 has 4 layers. The
    # first four are mapped 1:1 -- an approximation, see MISSING_VARIABLES.md --
    # and the two deepest RUC levels are not written.
    'SMOIS1':  {'shortName': 'swvl1',  'paramId': 39,     'long_name': 'Volumetric soil water layer 1', 'units': 'm^3/m^3', **_SFC},
    'SMOIS2':  {'shortName': 'swvl2',  'paramId': 40,     'long_name': 'Volumetric soil water layer 2', 'units': 'm^3/m^3', **_SFC},
    'SMOIS3':  {'shortName': 'swvl3',  'paramId': 41,     'long_name': 'Volumetric soil water layer 3', 'units': 'm^3/m^3', **_SFC},
    'SMOIS4':  {'shortName': 'swvl4',  'paramId': 42,     'long_name': 'Volumetric soil water layer 4', 'units': 'm^3/m^3', **_SFC},
    'TSLB1':   {'shortName': 'stl1',   'paramId': 139,    'long_name': 'Soil temperature level 1', 'units': 'K', **_SFC},
    'TSLB2':   {'shortName': 'stl2',   'paramId': 170,    'long_name': 'Soil temperature level 2', 'units': 'K', **_SFC},
    'TSLB3':   {'shortName': 'stl3',   'paramId': 183,    'long_name': 'Soil temperature level 3', 'units': 'K', **_SFC},
    'TSLB4':   {'shortName': 'stl4',   'paramId': 236,    'long_name': 'Soil temperature level 4', 'units': 'K', **_SFC},

    # ---------------- accumulated since 00Z of the same day ----------------
    'RAINNC':  {'shortName': 'tp',   'paramId': 228,    'long_name': 'Total precipitation', 'units': 'm', 'stepType': 'accum', **_SFC},
    'tirf':    {'shortName': 'tirf', 'paramId': 235015, 'long_name': 'Time integral of rain flux (rain only)', 'units': 'kg/m^2', 'stepType': 'accum', **_SFC},
    'SNOWNC':  {'shortName': 'sf',   'paramId': 144,    'long_name': 'Snowfall (water equivalent)', 'units': 'm', 'stepType': 'accum', **_SFC},
    'ACSWDNB': {'shortName': 'ssrd', 'paramId': 169,    'long_name': 'Surface solar radiation downwards', 'units': 'J/m^2', 'stepType': 'accum', **_SFC},
    # tsr sits on nominalTop by definition -> levelType None.
    'tsr':     {'shortName': 'tsr',  'paramId': 178,    'long_name': 'Top net solar radiation', 'units': 'J/m^2', 'stepType': 'accum', 'levelType': None, 'levels': [None]},
    'SFROFF':  {'shortName': 'sro',  'paramId': 8,      'long_name': 'Surface runoff', 'units': 'm', 'stepType': 'accum', **_SFC},
    'UDROFF':  {'shortName': 'ssro', 'paramId': 9,      'long_name': 'Sub-surface runoff', 'units': 'm', 'stepType': 'accum', **_SFC},
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
