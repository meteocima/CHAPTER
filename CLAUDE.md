# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CHAPTER (Computational Hydrometeorology with Advanced Performance to Enhanced Realism) is a high-resolution (3km) regional reanalysis dataset over Europe and the Mediterranean basin produced with WRF. This project converts CHAPTER's WRF output (wrfout files) to ECMWF-compatible GRIB1 format and then to Anemoi ML framework datasets.

## Build & Development

Package manager is **uv** with **scikit-build-core** backend (compiles Fortran extensions via CMake + F2PY). HPC pipeline uses **Hydra** (`hydra-core` + `omegaconf`) for configuration.

```bash
uv sync                # install all dependencies and build Fortran extensions
uv run <script.py>     # run any script with the project environment
```

### Build Fortran Extensions

The `fortran/` directory contains F90 sources compiled into the `_wrffortran` Python module via F2PY. CMake handles the build automatically through scikit-build-core. Requires gcc/gfortran and optionally OpenMP.

```bash
uv build               # full wheel build
uv pip install -e .    # editable install for development
```

## Running the Pipeline

**Single file conversion (local):**
```bash
uv run python convert_to_pressure_levels.py --input <wrfout_file> --output <grib_file>
uv run python convert_to_pressure_levels.py --input <wrfout_file> --output <grib_file> --debug-vars T2 tk
```

**HPC pipeline (Leonardo ↔ SuperMUC via SLURM + Hydra):**
```bash
# Submits orchestrator job to lrd_all_serial, which submits fetch+convert jobs per day
python hpc/submit_pipeline.py                                         # uses conf/pipeline.yaml defaults
python hpc/submit_pipeline.py dates.start=2023-03-01 dates.end=2023-03-31
python hpc/submit_pipeline.py slurm.account=my_project                # Hydra CLI overrides
python hpc/submit_pipeline.py --worker                                # run submission loop directly (skip SLURM self-submit)
```

**Step-by-step HPC pipeline (datamover fetch, hourly window):**
```bash
# Fetch via CINECA datamover (data.leonardo.cineca.it -> chapteradmin VM), convert on dcgp_usr_prod.
python hpc/submit_step_pipeline.py window.start_date=2023-05-23 window.start_hour=0 \
    window.end_date=2023-05-25 window.end_hour=23   # convert charges slurm.step_convert_account (default aifpt_ailamit_0)
python hpc/submit_step_pipeline.py ... dry_run=true                   # local preview, no SLURM/network
```

**SuperMUC file transfer helpers (source in shell):**
```bash
source functions_supermuc.sh
supermuc-put <local_path> <remote_path>    # rsync upload via SSH socket
supermuc-get <remote_path> <local_path>    # rsync download via SSH socket
```

**WRF to Anemoi ZARR:**
```bash
./run_anemoi_pipeline.sh [recipe.yaml] [output.zarr]
```

## Testing

```bash
python -m pytest test/utests.py -v       # main test suite
python test/comp_utest.py                # computation tests
python test/test_proj_params.py          # projection parameter tests
python test/test_omp.py                  # OpenMP tests
python test/test_units.py                # unit conversion tests
```

No CI/CD pipeline is configured. No linter configuration exists.

## Architecture

### Two-Stage Conversion Pipeline

1. **WRF Diagnostics** (`src/wrf/`): Python wrappers around Fortran kernels compute derived variables and interpolate WRF model levels to 13 pressure levels (1000-50 hPa)
2. **Encoding**: eccodes encodes GRIB1 with ECMWF paramIds (table 128); anemoi-datasets creates Zarr with Zstd compression

### Key Modules

- **`src/wrf/`** - Custom wrf-python (v1.4.2) with decorator-based metadata attachment and LRU computation caching. Diagnostic generators are in `g_*.py` files (wind, pressure, cape, etc.)
- **`fortran/`** - Core computation kernels (vertical interpolation, CAPE, humidity, PV). OpenMP parallelization generated from `ompgen.F90.template`
- **`convert_to_pressure_levels.py`** - Main conversion script: reads WRF NetCDF, computes diagnostics, encodes GRIB1 with projection metadata. Accepts `--input`/`--output` CLI args.
- **`wrf_era5_comparison.py`** - WRF-to-ECMWF variable mapping and paramId definitions (imported by conversion scripts)
- **`wrf_anemoi_recipe.yaml`** - Anemoi dataset recipe (input patterns, date ranges, compression settings)
- **`conf/pipeline.yaml`** - Hydra configuration for the HPC pipeline (date range, paths, SuperMUC remote config, SLURM settings, GRIB naming template)
- **`hpc/`** - HPC pipeline for Leonardo (CINECA). Uses Hydra config (`conf/pipeline.yaml`) with CLI overrides.
  - `submit_pipeline.py` - Orchestrator with two modes: entry (submits itself to SLURM) and worker (`--worker`, runs the job submission loop)
  - `fetch_day.sh` - SLURM job: rsync 24 hourly wrfout files from SuperMUC via SSH control socket
  - `convert_day.sh` - SLURM array job (0-23): convert each hour's wrfout to GRIB, delete wrfout on success. Re-entrant (skips existing outputs)
  - `orchestrator.sh` - SLURM wrapper for submit_pipeline.py in worker mode
  - `submit_step_pipeline.py` - Launcher for the step-by-step (hourly window) pipeline. Submits one recursive driver job; supports `dry_run=true` for a no-SLURM/no-network preview
  - `fetch_step.sh` - Recursive driver (lrd_all_serial). Fetches each timestep via the CINECA datamover (`ssh -xT data.leonardo.cineca.it "scp -F <cfg> supermuc-vm:<remote> <local>/"`), submits a convert job per timestep, then resubmits itself for the next batch until the window end. Re-entrant (skips timesteps whose GRIB exists)
  - `convert_step.sh` - Single-timestep convert job (dcgp_usr_prod), non-array variant of `convert_day.sh`
  - `dates.py` - Date-to-run-folder mapping (target date -> SuperMUC init folder with 6h spinoff). Handles different base paths for pre-2023 vs 2023+ data. Reused by both pipelines
- **`functions_supermuc.sh`** - Shell helper functions (`supermuc-put`, `supermuc-get`) for rsync transfers via SSH control socket

### Data Flow

WRF NetCDF (`wrfout_d02_*`) -> wrf-python diagnostics + pressure interpolation -> GRIB1 with ECMWF paramIds -> Anemoi Zarr dataset

### HPC Pipeline Flow (Leonardo ↔ SuperMUC)

Per day: orchestrator submits fetch job (lrd_all_serial, rsync 24 wrfout) -> convert array job (0-23, each hour independently, depends on fetch via `afterok`) -> delete wrfout on success. Config via Hydra (`conf/pipeline.yaml`) with CLI overrides. SSH control socket must be pre-activated in tmux. Pipeline is re-entrant: skips dates where all 24 GRIBs already exist, and individual convert tasks skip if the output GRIB exists. SuperMUC has different base paths for pre-2023 vs 2023+ runs.

**Step-by-step flow (datamover, hourly window):** an alternative to the day-based flow. `submit_step_pipeline.py` submits one recursive driver (`fetch_step.sh`) on `lrd_all_serial`. The driver processes a batch of hourly timesteps — fetching each via the CINECA datamover (compute nodes have no internet, so the fetch cannot run on a compute node) and submitting an independent convert job per timestep on `dcgp_usr_prod` — then resubmits itself for the next batch until `window.end_*`. The datamover/VM paths live under `datamover.*` in `conf/pipeline.yaml` (distinct from the rsync/DSS paths under `supermuc.*`); both share the init-folder mapping in `dates.py`. Use `dry_run=true` to preview all commands without SLURM or network.

### Important Domain Details

- Mercator projection (MAP_PROJ=3), grid 1353x1641 at 3km resolution
- Ocean masking uses LANDMASK field for SST/sea-ice distinction
- Unit conversions required: geopotential (m -> m^2/s^2), radiation, precipitation
- Derived variables: specific humidity from mixing ratio, TCW, skin temperature, slope of orography
