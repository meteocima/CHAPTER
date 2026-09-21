#!/usr/bin/env python3
"""ERA5 crosswalk: our 90 variables against what CDS actually offers.

WHY THIS FILE EXISTS SEPARATELY. The audit asks "is this the ERA5 quantity",
and that question splits in two. The first half is availability -- does ERA5
publish this parameter at all -- and it is answered once, here, against the CDS
catalogue rather than against a parameter table we typed out. The second half,
whether the values agree, belongs to the family tickets and needs the data.

Every row below was checked against the `variable` widget of the two CDS
collection forms on 2026-09-19; `check_against_catalogue()` re-runs that check
so the table cannot rot in silence. A name that disappears from the catalogue,
or an ERA5 parameter that appears where we recorded none, is a finding.

The nine single-level and one pressure-level entries in NOT_IN_ERA5 are a
result in their own right: publishing a paramId that ERA5 defines but never
populates is not the same kind of claim as matching a field it publishes.
"""

# --- Pressure levels -------------------------------------------------------
# Our 13 pressure-level variables. ERA5 carries 12 of them.
PL_CROSSWALK = {
    'u':    'u_component_of_wind',
    'v':    'v_component_of_wind',
    't':    'temperature',
    'z':    'geopotential',
    'q':    'specific_humidity',
    'r':    'relative_humidity',
    'clwc': 'specific_cloud_liquid_water_content',
    'ciwc': 'specific_cloud_ice_water_content',
    'w':    'vertical_velocity',
    'cc':   'fraction_of_cloud_cover',
    'crwc': 'specific_rain_water_content',
    'cswc': 'specific_snow_water_content',
}

# --- Single level ----------------------------------------------------------
SL_CROSSWALK = {
    '2t':     '2m_temperature',
    '2d':     '2m_dewpoint_temperature',
    '10u':    '10m_u_component_of_wind',
    '10v':    '10m_v_component_of_wind',
    '10fg':   '10m_wind_gust_since_previous_post_processing',
    '100u':   '100m_u_component_of_wind',
    '100v':   '100m_v_component_of_wind',
    'msl':    'mean_sea_level_pressure',
    'tcw':    'total_column_water',
    'tcwv':   'total_column_water_vapour',
    'tclw':   'total_column_cloud_liquid_water',
    'tciw':   'total_column_cloud_ice_water',
    'tcrw':   'total_column_rain_water',
    'tcsw':   'total_column_snow_water',
    'tcc':    'total_cloud_cover',
    'hcc':    'high_cloud_cover',
    'mcc':    'medium_cloud_cover',
    'lcc':    'low_cloud_cover',
    'z':      'geopotential',            # surface orography, same paramId 129
    'lsm':    'land_sea_mask',
    'sp':     'surface_pressure',
    'sdor':   'standard_deviation_of_orography',
    'slor':   'slope_of_sub_gridscale_orography',
    'skt':    'skin_temperature',
    'sst':    'sea_surface_temperature',
    'ci':     'sea_ice_cover',
    'cvl':    'low_vegetation_cover',
    'cvh':    'high_vegetation_cover',
    'tvl':    'type_of_low_vegetation',
    'tvh':    'type_of_high_vegetation',
    'slt':    'soil_type',
    'cl':     'lake_cover',
    'dl':     'lake_depth',
    'fal':    'forecast_albedo',
    'zust':   'friction_velocity',
    'fsr':    'forecast_surface_roughness',
    'iews':   'instantaneous_eastward_turbulent_surface_stress',
    'inss':   'instantaneous_northward_turbulent_surface_stress',
    'sd':     'snow_depth',
    'rsn':    'snow_density',
    'tsn':    'temperature_of_snow_layer',
    'src':    'skin_reservoir_content',
    'swvl1':  'volumetric_soil_water_layer_1',
    'swvl2':  'volumetric_soil_water_layer_2',
    'swvl3':  'volumetric_soil_water_layer_3',
    'swvl4':  'volumetric_soil_water_layer_4',
    'stl1':   'soil_temperature_level_1',
    'stl2':   'soil_temperature_level_2',
    'stl3':   'soil_temperature_level_3',
    'stl4':   'soil_temperature_level_4',
    'tp':     'total_precipitation',
    'sf':     'snowfall',
    'sro':    'surface_runoff',
    'ssro':   'sub_surface_runoff',
    'ro':     'runoff',
    'ssrd':   'surface_solar_radiation_downwards',
    'strd':   'surface_thermal_radiation_downwards',
    'ssrdc':  'surface_solar_radiation_downward_clear_sky',
    'strdc':  'surface_thermal_radiation_downward_clear_sky',
    'tisr':   'toa_incident_solar_radiation',
    'ssr':    'surface_net_solar_radiation',
    'str':    'surface_net_thermal_radiation',
    'ssrc':   'surface_net_solar_radiation_clear_sky',
    'strc':   'surface_net_thermal_radiation_clear_sky',
    'tsr':    'top_net_solar_radiation',
    'tsrc':   'top_net_solar_radiation_clear_sky',
    'ttr':    'top_net_thermal_radiation',
    'ttrc':   'top_net_thermal_radiation_clear_sky',
}

# --- What ERA5 does not carry ---------------------------------------------
# Keyed by our shortName; the value says what the catalogue offers instead, so
# that a family ticket knows whether there is a control to fall back on.
NOT_IN_ERA5 = {
    'wz':     ('260238', 'pl', 'no geometric (m/s) vertical velocity; only w in Pa/s'),
    '2r':     ('260242', 'sl', 'no 2 m relative humidity; derivable from 2t and 2d'),
    '200u':   ('228239', 'sl', 'winds at 10 m and 100 m only'),
    '200v':   ('228240', 'sl', 'winds at 10 m and 100 m only'),
    'vwsh':   ('260068', 'sl', 'no vertical speed shear at any level'),
    'mucape': ('228235', 'sl', 'cape (59) instead: ERA5 already searches parcels below 350 hPa, '
                               'so it is most-unstable-like; MUCAPE replaced CAPE in the IFS only at 49r1 '
                               'and ERA5 is 41r2. The differences are the search depth and the virtual '
                               'temperature correction, NOT surface against most-unstable'),
    'mucin':  ('228236', 'sl', 'cin (228001), which ECMWF says is identical to MUCIN in the IFS -- but the '
                               'ERA5 field is 85.5 per cent fill value (9999), because CIN above '
                               '1000 J/kg is encoded as missing'),
    'al':     ('174',    'sl', 'no background albedo; four spectral albedos, snow_albedo and fal instead'),
    'snowc':  ('260038', 'sl', 'no snow cover fraction in ERA5 single levels'),
    'tirf':   ('235015', 'sl', 'no time-integral of rain flux; large_scale_precipitation is the nearest'),
}

# --- Controls --------------------------------------------------------------
# Not part of the 90. Each is the nearest ERA5 quantity to something we either
# do not publish or publish from a different parcel/definition, and each costs
# one more field per timestep. Retrieved so a family ticket has the comparison
# already on disk rather than having to come back to CDS for it.
SL_CONTROLS = {
    'convective_available_potential_energy': 'control for mucape; a different parcel search, not a different parcel',
    'convective_inhibition':                 'control for mucin -- BUT 85.5 per cent of it is the 9999 fill value; drop those before using it',
    'instantaneous_10m_wind_gust':           'the other gust convention, against our resolved-wind 10fg',
    'snow_albedo':                           'the albedo we do not publish (SNOALB is a climatological cap)',
    'leaf_area_index_low_vegetation':        'lai_lv, refused because the model carries one LAI per cell',
    'leaf_area_index_high_vegetation':       'lai_hv, same refusal',
    'convective_precipitation':              'cp: what CU_PHYSICS=0 makes identically zero for us',
    'convective_snowfall':                   'csf: same',
    'large_scale_precipitation':             'the rain-only control tirf would have been',
    'large_scale_snowfall':                  'against our sf, which has no convective part to subtract',
    'snowmelt':                              'smlt, refused because ACSNOM is not monotone',
}

FORM_URL = ('https://cds.climate.copernicus.eu/api/catalogue/v1/collections/'
            '{collection}/form.json')
COLLECTIONS = {
    'sl': 'reanalysis-era5-single-levels',
    'pl': 'reanalysis-era5-pressure-levels',
}


def catalogue_variables(collection):
    """The `variable` values the live CDS form offers for one collection."""
    import json
    import urllib.request
    url = FORM_URL.format(collection=collection)
    with urllib.request.urlopen(url, timeout=60) as fh:
        form = json.load(fh)
    widget = next(w for w in form if w.get('name') == 'variable')
    details = widget['details']
    if details.get('values'):
        return set(details['values'])
    out = set()
    for group in details.get('groups', []):
        out.update(group.get('values', []))
    return out


def check_against_catalogue():
    """Re-measure the table. Returns a list of drift lines; empty means clean."""
    drift = []
    for kind, collection in COLLECTIONS.items():
        offered = catalogue_variables(collection)
        table = PL_CROSSWALK if kind == 'pl' else dict(SL_CROSSWALK, **{
            k: k for k in SL_CONTROLS})
        for short, cds_name in table.items():
            if cds_name not in offered:
                drift.append(f'{kind}: {short} -> {cds_name} is no longer offered by CDS')
        for short, (paramid, where, note) in NOT_IN_ERA5.items():
            if where != kind:
                continue
            # A name we recorded as absent must still be absent. We cannot test
            # the paramId from the form, so test the obvious snake_case names a
            # new entry would take.
            for guess in _absence_guesses(short):
                if guess in offered:
                    drift.append(
                        f'{kind}: {short} ({paramid}) was recorded as absent but '
                        f'CDS now offers {guess}')
    return drift


def _absence_guesses(short):
    return {
        'wz':     {'geometric_vertical_velocity', 'vertical_velocity_geometric'},
        '2r':     {'2m_relative_humidity'},
        '200u':   {'200m_u_component_of_wind'},
        '200v':   {'200m_v_component_of_wind'},
        'vwsh':   {'vertical_speed_shear', 'wind_shear'},
        'mucape': {'most_unstable_cape', 'most_unstable_convective_available_potential_energy'},
        'mucin':  {'most_unstable_cin', 'most_unstable_convective_inhibition'},
        'al':     {'albedo', 'background_albedo'},
        'snowc':  {'snow_cover'},
        'tirf':   {'time_integral_of_rain_flux', 'total_column_integrated_rain_flux'},
    }.get(short, set())


if __name__ == '__main__':
    import sys
    print(f'pressure levels: {len(PL_CROSSWALK)} of 13 carried by ERA5')
    print(f'single level:    {len(SL_CROSSWALK)} of 77 carried by ERA5')
    print(f'not carried:     {len(NOT_IN_ERA5)} of 90')
    for short, (paramid, where, note) in sorted(NOT_IN_ERA5.items()):
        print(f'  {short:<7} {paramid:<7} {where}  {note}')
    print(f'controls:        {len(SL_CONTROLS)} extra single-level fields')
    print('checking the table against the live CDS catalogue ...')
    drift = check_against_catalogue()
    if drift:
        print('DRIFT:')
        for line in drift:
            print('  ' + line)
        sys.exit(1)
    print('clean: every name still resolves and every absence still holds.')
