#!/usr/bin/env python3
"""
Comparison between WRF variables and ERA5 variables

IMPORTANT NOTES:
- wrf-python provides numerous diagnostics calculable from basic WRF variables
- Main diagnostics available in wrf-python:
  * theta, theta_e: potential temperature, equivalent potential temperature
  * cape_2d, cape_3d, cin2d_only, cin3d_only: CAPE and CIN
  * slp: sea level pressure
  * rh, rh2m: relative humidity
  * dp, dp2m: dewpoint temperature
  * pvo: potential vorticity  
  * avo: absolute vorticity
  * omega: vertical velocity in pressure coordinates
  * geopt: geopotential height
  * ctt: cloud top temperature
  * low_cloudfrac, mid_cloudfrac, high_cloudfrac: cloud fraction by levels
  * lcl, lfc: lifted condensation level, level of free convection
  * pw: precipitable water
  * tk, tc: temperature in K and C
  * dbz: radar reflectivity

CORRECTIONS from previous version:
- CAPE removed from wrf_to_era5_direct (not present in WRF selection)
- Potential temperature (pt), CIN, cloud diagnostics moved to era5_calculable_from_wrf
"""

# ==============================================================================
# WRF -> ECMWF paramId MAPPING
# ==============================================================================
# Dictionary with ECMWF paramId verified from official ECMWF table
# Source: emcwf_table_202602.csv (official ECMWF table)
# Structure: {wrf_var: {'shortName': ecmwf_shortname, 'paramId': ecmwf_paramid, 'long_name': description, 'units': units}}

WRF_TO_ECMWF_PARAMID = {
    'CLDFRA': {'shortName': 'cc', 'paramId': 248, 'long_name': 'Cloud Fraction', 'units': 'fraction'},
    'ACLWDNB': {'shortName': 'strd', 'paramId': 175, 'long_name': 'Surface Thermal Radiation Downwards (accumulated)', 'units': 'J/m^2'},
    #'HFX': {'shortName': 'sshf', 'paramId': 146, 'long_name': 'Time-Integrated Surface Sensible Heat Net Flux', 'units': 'J/m^2'},
    'HGT': {'shortName': 'z', 'paramId': 129, 'long_name': 'Geopotential', 'units': 'm^2/s^2'},
    'ISLTYP': {'shortName': 'slt', 'paramId': 43, 'long_name': 'Dominant Soil Category', 'units': 'category'},
    #'IVGTYP': {'shortName': 'tvl', 'paramId': 29, 'long_name': 'Dominant Vegetation Category', 'units': 'category'},
    'LANDMASK': {'shortName': 'lsm', 'paramId': 172, 'long_name': 'Land Mask (1=land, 0=water)', 'units': 'fraction'},
    #'LH': {'shortName': 'slhf', 'paramId': 147, 'long_name': 'Time-Integrated Surface Latent Heat Net Flux', 'units': 'J/m^2'},
    #'LU_INDEX': {'shortName': 'tvh', 'paramId': 30, 'long_name': 'Land Use Category', 'units': 'category'},
    'PSFC': {'shortName': 'sp', 'paramId': 134, 'long_name': 'Surface Pressure', 'units': 'Pa'},
    'Q2': {'shortName': 'q', 'paramId': 133, 'long_name': '2m Specific Humidity', 'units': 'kg/kg'},
    #'QCLOUD': {'shortName': 'clwc', 'paramId': 246, 'long_name': 'Specific Cloud Liquid Water Content', 'units': 'kg/kg'},
    #'QICE': {'shortName': 'ciwc', 'paramId': 247, 'long_name': 'Specific Cloud Ice Water Content', 'units': 'kg/kg'},
    #'QRAIN': {'shortName': 'crwc', 'paramId': 75, 'long_name': 'Specific Rain Water Content', 'units': 'kg/kg'},
    #'QSNOW': {'shortName': 'cswc', 'paramId': 76, 'long_name': 'Specific Snow Water Content', 'units': 'kg/kg'},
    #'QVAPOR': {'shortName': 'q', 'paramId': 133, 'long_name': 'Specific Humidity', 'units': 'kg/kg'},
    #'RAINC': {'shortName': 'cp', 'paramId': 228143, 'long_name': 'Accumulated Convective Precipitation', 'units': 'mm'},
    'RAINNC': {'shortName': 'tp', 'paramId': 228, 'long_name': 'Total precipitation', 'units': 'm'},
    'SEAICE': {'shortName': 'ci', 'paramId': 31, 'long_name': 'Sea Ice Flag', 'units': 'fraction'},
    #'SMOIS': {'shortName': 'swvl1', 'paramId': 39, 'long_name': 'Volumetric Soil Water Layer 1', 'units': 'm^3/m^3'},
    #'SNOW': {'shortName': 'sf', 'paramId': 228144, 'long_name': 'Snow Water Equivalent', 'units': 'kg/m^2'},
    #'SNOWH': {'shortName': 'sd', 'paramId': 228141, 'long_name': 'Physical Snow Depth', 'units': 'm'},
    'SST': {'shortName': 'sst', 'paramId': 34, 'long_name': 'Sea Surface Temperature', 'units': 'K'},
    'ACSWDNB': {'shortName': 'ssrd', 'paramId': 169, 'long_name': 'Surface Solar Radiation Downwards (accumulated)', 'units': 'J/m^2'},
    #'T': {'shortName': 't', 'paramId': 500014, 'long_name': 'Temperature', 'units': 'K'},
    'T2': {'shortName': '2t', 'paramId': 167, 'long_name': '2m Temperature', 'units': 'K'},
    #'TSLB': {'shortName': 'stl1', 'paramId': 139, 'long_name': 'Soil Temperature Level 1', 'units': 'K'},
    'U': {'shortName': 'u', 'paramId': 131, 'long_name': 'U Component of Wind', 'units': 'm/s'},
    'U10': {'shortName': '10u', 'paramId': 165, 'long_name': '10m U-Component of Wind', 'units': 'm/s'},
    #'UST': {'shortName': 'zust', 'paramId': 228003, 'long_name': 'Friction Velocity', 'units': 'm/s'},
    'V': {'shortName': 'v', 'paramId': 132, 'long_name': 'V Component of Wind', 'units': 'm/s'},
    'V10': {'shortName': '10v', 'paramId': 166, 'long_name': '10m V-Component of Wind', 'units': 'm/s'},
    #'VAR': {'shortName': 'sdor', 'paramId': 160, 'long_name': 'Variance of Orography', 'units': 'm^2'},
    'VAR_SSO': {'shortName': 'sdor', 'paramId': 160, 'long_name': 'Standard Deviation of Subgrid-Scale Orography', 'units': 'm'},
    'W': {'shortName': 'w', 'paramId': 40, 'long_name': 'Vertical Velocity', 'units': 'm/s'},
    'pvo': {'shortName': 'pv', 'paramId': 60, 'long_name': 'Potential Vorticity', 'units': 'PVU'},
    'rh': {'shortName': 'r', 'paramId': 157, 'long_name': 'Relative Humidity', 'units': '%'},
    'skt': {'shortName': 'skt', 'paramId': 235, 'long_name': 'Skin Temperature (from longwave radiation)', 'units': 'K'},
    'slp': {'shortName': 'msl', 'paramId': 151, 'long_name': 'Mean Sea Level Pressure', 'units': 'Pa'},
    'q': {'shortName': 'q', 'paramId': 133, 'long_name': 'Specific Humidity', 'units': 'kg/kg'},
    'td2': {'shortName': '2d', 'paramId': 168, 'long_name': '2m Dewpoint Temperature', 'units': 'K'},
    'theta': {'shortName': 'pt', 'paramId': 3, 'long_name': 'Potential Temperature', 'units': 'K'},
    'tk': {'shortName': 't', 'paramId': 130, 'long_name': 'Temperature', 'units': 'K'},
    'z': {'shortName': 'z', 'paramId': 129, 'long_name': 'Geopotential', 'units': 'm^2/s^2'},
    'tcw': {'shortName': 'tcw', 'paramId': 136, 'long_name': 'Total column water', 'units': 'kg/m^2'},
    'slor': {'shortName': 'slor', 'paramId': 163, 'long_name': 'Slope of sub-gridscale orography', 'units': 'Numeric'},

}

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
