#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script to convert WRF files to pressure levels in GRIB1 format.

Usage:
    python convert_to_pressure_levels.py --input <wrfout_file> --output <grib_file>
    python convert_to_pressure_levels.py --input <wrfout_file> --output <grib_file> --debug-vars T2 tk slor
"""

import argparse
import os
import sys

import numpy as np
from netCDF4 import Dataset
import wrf
import pandas as pd
from eccodes import codes_grib_new_from_samples, codes_set, codes_set_values, codes_write, codes_release

# Import WRF -> ECMWF paramId mapping
from wrf_era5_comparison import WRF_TO_ECMWF_PARAMID

# Desired pressure levels (hPa)
PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

# WRF output interval (seconds) for radiation conversion W/m² -> J/m²
# Typically: 3600 for hourly output, 10800 for 3-hourly output
OUTPUT_INTERVAL_SECONDS = 3600  # 1 hour


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert WRF wrfout to ECMWF-compatible GRIB1 format"
    )
    parser.add_argument("--input", required=True, help="Path to wrfout NetCDF file")
    parser.add_argument("--output", required=True, help="Output GRIB1 file path")
    parser.add_argument(
        "--debug-vars", nargs="*", default=[],
        help="Limit processing to these variables only (default: all)"
    )
    return parser.parse_args()


def main(input_file, output_file, debug_vars=None):
    if debug_vars is None:
        debug_vars = []

    pressure_levels = PRESSURE_LEVELS

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    print(f"Opening file: {input_file}")
    ncfile = Dataset(input_file)

    # Extract projection parameters from WRF file
    print("\nExtracting WRF projection parameters...")
    map_proj = ncfile.MAP_PROJ  # Should be 3=Mercator for CHAPTER
    truelat1 = ncfile.TRUELAT1  # Latitude where DX/DY are exact
    stand_lon = ncfile.STAND_LON  # Grid orientation
    dx = ncfile.DX  # meters
    dy = ncfile.DY  # meters

    print(f"  MAP_PROJ: {map_proj}")
    print(f"  TRUELAT1: {truelat1}")
    print(f"  STAND_LON: {stand_lon}")
    print(f"  DX: {dx} m, DY: {dy} m")

    # Verify it's Mercator projection
    if map_proj != 3:
        raise ValueError(f"Expected Mercator projection (MAP_PROJ=3), got MAP_PROJ={map_proj}")

    grid_type = 'mercator'
    print(f"  Grid type: {grid_type}")

    # Use generic GRIB1 template
    grib_template_pl = 'GRIB1'
    grib_template_sfc = 'GRIB1'

    # Extract coordinates and time
    times = wrf.extract_times(ncfile, timeidx=wrf.ALL_TIMES)
    time_value = times[0]  # Use first timestep
    lat = wrf.getvar(ncfile, "lat")
    lon = wrf.getvar(ncfile, "lon")
    lat_2d = lat.values  # (south_north, west_east)
    lon_2d = lon.values  # (south_north, west_east)

    print(f"\nGrid dimensions: {lat_2d.shape}")
    print(f"Timestep to process: {time_value}")

    # Convert datetime64 to GRIB components
    date_time = pd.Timestamp(time_value)
    data_date = int(date_time.strftime('%Y%m%d'))
    data_time = int(date_time.strftime('%H%M'))

    # Output dictionary
    output_vars = {}

    # Read LANDMASK for land/ocean masking
    print("\n=== READING LANDMASK ===")
    try:
        landmask = wrf.getvar(ncfile, "LANDMASK", timeidx=0).values  # 1=land, 0=water
        ocean_mask = (landmask == 0)  # Mask for ocean
        land_mask = (landmask == 1)   # Mask for land
        print(f"LANDMASK loaded: {landmask.shape}")
        print(f"  Ocean points: {ocean_mask.sum()} ({100*ocean_mask.sum()/ocean_mask.size:.1f}%)")
        print(f"  Land points: {land_mask.sum()} ({100*land_mask.sum()/land_mask.size:.1f}%)")
    except Exception as e:
        print(f"Unable to load LANDMASK: {e}")
        print("  Land/ocean masking NOT applied")
        ocean_mask = None
        land_mask = None

    def is_staggered(var_name):
        """Determine if a variable is staggered and in which dimension"""
        if var_name not in ncfile.variables:
            return None
        dims = ncfile.variables[var_name].dimensions
        if 'bottom_top_stag' in dims:
            return 'vertical'
        elif 'west_east_stag' in dims:
            return 'west_east'
        elif 'south_north_stag' in dims:
            return 'south_north'
        return None

    # ==================== PROCESSING NATIVE VARIABLES ====================
    print("\n=== PROCESSING WRF NATIVE VARIABLES ===")
    if debug_vars:
        print(f"DEBUG MODE: processing limited to {debug_vars}")

    for var_name in ncfile.variables:
        # Skip if not in mapping dictionary
        if var_name not in WRF_TO_ECMWF_PARAMID:
            continue

        # DEBUG: skip if debug_vars is populated and var_name is not in list
        if debug_vars and var_name not in debug_vars:
            continue

        var = ncfile.variables[var_name]
        dims = var.dimensions

        # Determine if it's 3D (has atmospheric vertical dimension)
        has_vertical = any(d in dims for d in ['bottom_top', 'bottom_top_stag'])

        if has_vertical:
            # 3D variable - interpolate to pressure levels
            print(f"3D interpolation: {var_name}...")
            try:
                var_data = wrf.getvar(ncfile, var_name, timeidx=0)

                # Destaggering if necessary
                stagger_type = is_staggered(var_name)
                if stagger_type:
                    print(f"  Destaggering {var_name} ({stagger_type})...")
                    if stagger_type == 'vertical':
                        var_data = wrf.destagger(var_data, stagger_dim=-3)
                    elif stagger_type == 'west_east':
                        var_data = wrf.destagger(var_data, stagger_dim=-1)
                    elif stagger_type == 'south_north':
                        var_data = wrf.destagger(var_data, stagger_dim=-2)

                # Interpolate to pressure levels
                var_interp = wrf.vinterp(ncfile,
                                         field=var_data,
                                         vert_coord="pressure",
                                         interp_levels=pressure_levels,
                                         extrapolate=True,
                                         timeidx=0)

                output_vars[var_name] = var_interp.values
                print(f"  {var_name} (3D interpolated, shape: {var_interp.shape})")
            except Exception as e:
                print(f"  {var_name}: {str(e)}")
        else:
            # 2D variable - copy directly
            print(f"2D copy: {var_name}...")
            try:
                var_data = wrf.getvar(ncfile, var_name, timeidx=0)

                # Special conversion: HGT (m) -> geopotential (m²/s²)
                if var_name == 'HGT':
                    g = 9.80665  # m/s²
                    output_vars[var_name] = var_data.values * g
                    print(f"  {var_name} (2D, converted to geopotential: {var_data.values.min()*g:.1f}-{var_data.values.max()*g:.1f} m²/s²)")
                # Special conversion: VAR_SSO (variance m²) -> sdor (standard deviation m)
                elif var_name == 'VAR_SSO':
                    output_vars[var_name] = np.sqrt(var_data.values)
                    print(f"  {var_name} (2D, converted to standard deviation: {np.sqrt(var_data.values).min():.2f}-{np.sqrt(var_data.values).max():.2f} m)")
                # Special conversion: RAINNC, RAINC (mm) -> tp (m)
                elif var_name in ['RAINNC', 'RAINC']:
                    output_vars[var_name] = var_data.values / 1000.0  # mm -> m
                    print(f"  {var_name} (2D, converted to m: {var_data.values.min()/1000.0:.6f}-{var_data.values.max()/1000.0:.6f} m)")
                # Special conversion: SWDOWN, GLW (W/m²) -> ssrd, strd (J/m²)
                elif var_name in ['SWDOWN', 'GLW']:
                    output_vars[var_name] = var_data.values * OUTPUT_INTERVAL_SECONDS  # W/m² -> J/m²
                    print(f"  {var_name} (2D, converted to J/m²: {var_data.values.min()*OUTPUT_INTERVAL_SECONDS:.1f}-{var_data.values.max()*OUTPUT_INTERVAL_SECONDS:.1f} J/m²)")
                else:
                    output_vars[var_name] = var_data.values
                    print(f"  {var_name} (2D, shape: {var_data.shape})")
            except Exception as e:
                print(f"  {var_name}: {str(e)}")

    # ==================== DERIVED VARIABLES ====================
    print("\n=== CALCULATING DERIVED VARIABLES ===")

    # 3D derived variables to interpolate
    derived_3d = ['tk', 'theta', 'rh', 'z', 'pvo']
    for var_name in derived_3d:
        if var_name not in WRF_TO_ECMWF_PARAMID:
            continue

        # DEBUG: skip if debug_vars is populated and var_name is not in list
        if debug_vars and var_name not in debug_vars:
            continue

        print(f"3D derived interpolation: {var_name}...")
        try:
            var_data = wrf.getvar(ncfile, var_name, timeidx=0)
            var_interp = wrf.vinterp(ncfile,
                                     field=var_data,
                                     vert_coord="pressure",
                                     interp_levels=pressure_levels,
                                     extrapolate=True,
                                     timeidx=0)

            # Special conversion: z (geopotential height m) -> geopotential (m²/s²)
            if var_name == 'z':
                g = 9.80665  # m/s²
                output_vars[var_name] = var_interp.values * g
                print(f"  {var_name} (converted to geopotential: shape {var_interp.shape})")
            else:
                output_vars[var_name] = var_interp.values
                print(f"  {var_name} (shape: {var_interp.shape})")
        except Exception as e:
            print(f"  {var_name}: {str(e)}")

    # 2D derived variables
    derived_2d = ['td2', 'slp']
    for var_name in derived_2d:
        if var_name not in WRF_TO_ECMWF_PARAMID:
            continue

        # DEBUG: skip if debug_vars is populated and var_name is not in list
        if debug_vars and var_name not in debug_vars:
            continue

        print(f"2D derived calculation: {var_name}...")
        try:
            var_data = wrf.getvar(ncfile, var_name, timeidx=0)

            # Special conversion: slp (hPa) -> msl (Pa)
            if var_name == 'slp':
                output_vars[var_name] = var_data.values * 100  # hPa -> Pa
                print(f"  {var_name} (converted to Pa: {var_data.values.min()*100:.1f}-{var_data.values.max()*100:.1f} Pa)")
            else:
                output_vars[var_name] = var_data.values
                print(f"  {var_name} (shape: {var_data.shape})")
        except Exception as e:
            print(f"  {var_name}: {str(e)}")

    # Surface Pressure (PSFC) - no masking needed
    if 'PSFC' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'PSFC' in debug_vars):
        print("Processing PSFC (surface pressure)...")
        try:
            psfc = wrf.getvar(ncfile, "PSFC", timeidx=0)  # Pa
            output_vars['PSFC'] = psfc.values
            print(f"  PSFC -> sp ({psfc.values.min():.1f}-{psfc.values.max():.1f} Pa)")
        except Exception as e:
            print(f"  PSFC: {str(e)}")

    # Sea Surface Temperature (SST) - ocean only
    if 'SST' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'SST' in debug_vars):
        print("Processing SST (sea surface temperature - ocean only)...")
        try:
            sst_var = wrf.getvar(ncfile, "SST", timeidx=0)  # K
            sst_data = sst_var.values.astype(float)

            # Mask: sst only over ocean
            if ocean_mask is not None:
                sst_data[~ocean_mask] = np.nan
                valid_points = np.sum(~np.isnan(sst_data))
                print(f"  SST (OCEAN ONLY, {valid_points} valid points, {sst_data[ocean_mask].min():.1f}-{sst_data[ocean_mask].max():.1f} K)")
            else:
                print(f"  SST (NO MASK, {sst_data.min():.1f}-{sst_data.max():.1f} K)")

            output_vars['SST'] = sst_data
        except Exception as e:
            print(f"  SST: {str(e)}")

    # Specific humidity from QVAPOR (interpolated)
    if 'q' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'q' in debug_vars):
        print("Calculating specific_humidity from QVAPOR...")
        try:
            qvapor = wrf.getvar(ncfile, "QVAPOR", timeidx=0)
            qvapor_interp = wrf.vinterp(ncfile,
                                        field=qvapor,
                                        vert_coord="pressure",
                                        interp_levels=pressure_levels,
                                        extrapolate=True,
                                        timeidx=0)
            # q = w / (1 + w)
            specific_humidity = qvapor_interp / (1.0 + qvapor_interp)
            output_vars['q'] = specific_humidity.values
            print(f"  specific_humidity (shape: {specific_humidity.shape})")
        except Exception as e:
            print(f"  specific_humidity: {str(e)}")

    # Total Column Water (TCW) from all hydrometeor components
    if 'tcw' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'tcw' in debug_vars):
        print("Calculating TCW (Total Column Water)...")
        try:
            # Read all water components (kg/kg mixing ratio)
            qvapor = wrf.getvar(ncfile, "QVAPOR", timeidx=0)
            qcloud = wrf.getvar(ncfile, "QCLOUD", timeidx=0)
            qrain = wrf.getvar(ncfile, "QRAIN", timeidx=0)
            qice = wrf.getvar(ncfile, "QICE", timeidx=0)
            qsnow = wrf.getvar(ncfile, "QSNOW", timeidx=0)
            qgraup = wrf.getvar(ncfile, "QGRAUP", timeidx=0)

            # Sum all components
            q_total = qvapor + qcloud + qrain + qice + qsnow + qgraup

            # Calculate pressure
            pressure = wrf.getvar(ncfile, "pressure", timeidx=0)  # hPa

            # Vertical integration: TCW = integral q_total * (dp/g)
            g = 9.81  # m/s^2
            # Calculate dp between levels (in Pa)
            dp = np.diff(pressure.values * 100, axis=0)  # hPa -> Pa
            dp = np.concatenate([dp, dp[-1:, :, :]], axis=0)  # Add dummy layer at top

            # TCW = integral q * (dp/g) [kg/m^2]
            tcw = np.sum(q_total.values * dp / g, axis=0)

            output_vars['tcw'] = tcw
            print(f"  tcw (shape: {tcw.shape}, range: {np.nanmin(tcw):.2f}-{np.nanmax(tcw):.2f} kg/m^2)")
        except Exception as e:
            print(f"  tcw: {str(e)}")

    # Skin temperature from longwave radiation (Stefan-Boltzmann)
    if 'skt' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'skt' in debug_vars):
        print("Calculating skin temperature (Stefan-Boltzmann)...")
        try:
            # LWUPB = emissivity * sigma * T_skin^4
            # T_skin = (LWUPB / (emissivity * sigma))^(1/4)
            emissivity = 0.98
            stefan_boltzmann = 5.67e-8  # W m^-2 K^-4

            lwupb = wrf.getvar(ncfile, "LWUPB", timeidx=0)
            skin_temp = (lwupb.values / (emissivity * stefan_boltzmann)) ** 0.25

            output_vars['skt'] = skin_temp
            print(f"  skt (shape: {skin_temp.shape})")
        except Exception as e:
            print(f"  skt: {str(e)}")

    # Slope of orography (topography gradient)
    if 'slor' in WRF_TO_ECMWF_PARAMID and (not debug_vars or 'slor' in debug_vars):
        print("Calculating slope of orography...")
        try:
            hgt = wrf.getvar(ncfile, "HGT", timeidx=0)

            # Gradients (returns grad_y, grad_x)
            grad_y, grad_x = np.gradient(hgt.values, dy, dx)

            # Slope magnitude
            slope = np.sqrt(grad_x**2 + grad_y**2)

            output_vars['slor'] = slope
            print(f"  slor (shape: {slope.shape})")
        except Exception as e:
            print(f"  slor: {str(e)}")

    # ==================== GRIB1 SAVING ====================
    print(f"\n=== GRIB1 SAVING ===")
    print(f"Output file: {output_file}")
    print(f"Variables to write: {len(output_vars)}")
    if debug_vars:
        print(f"DEBUG MODE: saving only {list(output_vars.keys())}")

    # Coordinates for GRIB (always 2D for Mercator)
    lats = lat_2d  # 2D
    lons = lon_2d  # 2D

    # Verify there are variables to write
    if not output_vars:
        print("\nERROR: No variables to write to GRIB file!")
        print("Verify that WRF variables are present in WRF_TO_ECMWF_PARAMID dictionary")
        ncfile.close()
        sys.exit(1)

    print(f"\n=== WRITING GRIB FILE ===")
    print(f"Variables to write: {len(output_vars)}")

    with open(output_file, 'wb') as fout:
        written_count = 0

        for var_name, var_data in output_vars.items():
            param_info = WRF_TO_ECMWF_PARAMID[var_name]
            param_id = param_info['paramId']
            short_name = param_info['shortName']

            # Determine if 3D or 2D from shape
            is_3d = len(var_data.shape) == 3  # (pressure, lat, lon)

            if is_3d:
                # 3D variable - write for each pressure level
                for lev_idx, lev_val in enumerate(pressure_levels):
                    gid = codes_grib_new_from_samples(grib_template_pl)

                    # Time metadata
                    codes_set(gid, 'dataDate', data_date)
                    codes_set(gid, 'dataTime', data_time)
                    codes_set(gid, 'startStep', 0)
                    codes_set(gid, 'endStep', 0)

                    # Grid representation type (GRIB1) - Mercator
                    codes_set(gid, 'dataRepresentationType', 1)  # Mercator

                    # Grid dimensions
                    nj = lats.shape[0]
                    ni = lats.shape[1]
                    codes_set(gid, 'Ni', ni)
                    codes_set(gid, 'Nj', nj)

                    # Mercator projection parameters
                    codes_set(gid, 'latitudeOfFirstGridPointInDegrees', float(lats[0, 0]))
                    codes_set(gid, 'longitudeOfFirstGridPointInDegrees', float(lons[0, 0]))
                    codes_set(gid, 'latitudeOfLastGridPointInDegrees', float(lats[-1, -1]))
                    codes_set(gid, 'longitudeOfLastGridPointInDegrees', float(lons[-1, -1]))
                    codes_set(gid, 'LaDInDegrees', float(truelat1))  # Latitude where DX/DY are specified
                    codes_set(gid, 'DiInMetres', float(dx))
                    codes_set(gid, 'DjInMetres', float(dy))
                    codes_set(gid, 'resolutionAndComponentFlags', 8)  # DX/DY are valid

                    # Scanning mode
                    codes_set(gid, 'jScansPositively', 0)
                    codes_set(gid, 'iScansNegatively', 0)

                    # Level
                    codes_set(gid, 'indicatorOfTypeOfLevel', 100)  # isobaric
                    codes_set(gid, 'level', int(lev_val))

                    # Parameter
                    codes_set(gid, 'table2Version', 128)
                    codes_set(gid, 'indicatorOfParameter', param_id)

                    # Data
                    data_slice = var_data[lev_idx, :, :]

                    # NaN handling: GRIB1 requires bitmap for missing values
                    data_flat = data_slice.flatten()
                    if np.any(np.isnan(data_flat)):
                        # Enable bitmap to indicate valid/missing points
                        codes_set(gid, 'bitmapPresent', 1)
                        # Replace NaN with 0 (bitmap will indicate which are missing)
                        data_flat = np.where(np.isnan(data_flat), 0.0, data_flat)

                    codes_set_values(gid, data_flat)
                    codes_write(gid, fout)
                    codes_release(gid)
                    written_count += 1
            else:
                # 2D variable - surface
                gid = codes_grib_new_from_samples(grib_template_sfc)

                # Time metadata
                codes_set(gid, 'dataDate', data_date)
                codes_set(gid, 'dataTime', data_time)
                codes_set(gid, 'startStep', 0)
                codes_set(gid, 'endStep', 0)

                # Grid representation type (GRIB1) - Mercator
                codes_set(gid, 'dataRepresentationType', 1)  # Mercator

                # Grid dimensions
                nj = lats.shape[0]
                ni = lats.shape[1]
                codes_set(gid, 'Ni', ni)
                codes_set(gid, 'Nj', nj)

                # Mercator projection parameters
                codes_set(gid, 'latitudeOfFirstGridPointInDegrees', float(lats[0, 0]))
                codes_set(gid, 'longitudeOfFirstGridPointInDegrees', float(lons[0, 0]))
                codes_set(gid, 'latitudeOfLastGridPointInDegrees', float(lats[-1, -1]))
                codes_set(gid, 'longitudeOfLastGridPointInDegrees', float(lons[-1, -1]))
                codes_set(gid, 'LaDInDegrees', float(truelat1))  # Latitude where DX/DY are specified
                codes_set(gid, 'DiInMetres', float(dx))
                codes_set(gid, 'DjInMetres', float(dy))
                codes_set(gid, 'resolutionAndComponentFlags', 8)  # DX/DY are valid

                # Scanning mode
                codes_set(gid, 'jScansPositively', 0)
                codes_set(gid, 'iScansNegatively', 0)

                # Determine level type based on variable
                # 2m variables: T2, Q2, td2
                if var_name in ['T2', 'Q2', 'td2']:
                    codes_set(gid, 'indicatorOfTypeOfLevel', 105)  # height above ground
                    codes_set(gid, 'level', 2)  # 2 meters
                # 10m variables: U10, V10
                elif var_name in ['U10', 'V10']:
                    codes_set(gid, 'indicatorOfTypeOfLevel', 105)  # height above ground
                    codes_set(gid, 'level', 10)  # 10 meters
                # Other variables: surface
                else:
                    codes_set(gid, 'indicatorOfTypeOfLevel', 1)  # surface
                    codes_set(gid, 'level', 0)

                # Parameter
                codes_set(gid, 'table2Version', 128)
                codes_set(gid, 'indicatorOfParameter', param_id)

                # Data
                data_slice = var_data

                # NaN handling: GRIB1 requires bitmap for missing values
                data_flat = data_slice.flatten()
                if np.any(np.isnan(data_flat)):
                    # Enable bitmap to indicate valid/missing points
                    codes_set(gid, 'bitmapPresent', 1)
                    # Replace NaN with 0 (bitmap will indicate which are missing)
                    data_flat = np.where(np.isnan(data_flat), 0.0, data_flat)

                codes_set_values(gid, data_flat)
                codes_write(gid, fout)
                codes_release(gid)
                written_count += 1

            print(f"  {var_name} -> {short_name} (paramId={param_id})")

    print(f"\nConversion completed!")
    print(f"Output GRIB file: {output_file}")
    print(f"Projection: Mercator")
    print(f"GRIB messages written: {written_count}")
    print(f"Pressure levels: {pressure_levels}")

    # Verify file was written correctly
    if os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        print(f"File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        if file_size == 0:
            print("WARNING: GRIB file is empty!")
        if written_count == 0:
            print("WARNING: No GRIB messages written!")
    else:
        print(f"ERROR: File {output_file} was not created!")

    ncfile.close()


if __name__ == "__main__":
    args = parse_args()
    main(args.input, args.output, debug_vars=args.debug_vars)
