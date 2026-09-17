# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CHAPTER (Computational Hydrometeorology with Advanced Performance to Enhanced Realism) is a high-resolution (3km) regional reanalysis dataset over Europe and the Mediterranean basin produced with WRF. This project converts CHAPTER's WRF output (wrfout files) to ECMWF-compatible **GRIB2** format and then to Anemoi ML framework datasets.

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
# Fetch via CINECA datamover (data.leonardo.cineca.it -> LRZ data relay), convert on dcgp_usr_prod.
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

There is no `test/` directory in this repo (the test commands of upstream wrf-python do not apply).
No CI/CD pipeline, no linter configuration. Changes are verified by hand, in this order:

1. `--debug-vars` on a real wrfout for the field you touched. A run that asks only for plain 2D
   native fields skips the shared 3D cache and takes ~15 s; anything else reads 2.6 GB first.
2. A full conversion **as a SLURM job**, never on a login node: the login limit is 600 s of CPU per
   process and a full file costs ~110 s user + ~60 s system — close enough that `cape_2d` alone on
   the full domain will be killed there.
   ```bash
   W=/leonardo_work/AIFPT_AILAMIT/CHAPTER
   sbatch --partition dcgp_usr_prod --account aifpt_ailamit_0 --nodes 1 --ntasks 1 \
     --cpus-per-task 1 --mem 32G --time 01:00:00 --wrap "cd $PWD
   source tools/eccodes_env.sh
   /usr/bin/time -v \$HOME/.local/bin/uv run python convert_to_pressure_levels.py \
     --input \$W/wrfout_share/2024-07-01/wrfout_d02_2024-07-01_14:00:00 \
     --output \$W/grib_test/test.grib --accum-ref-dir \$W/accum_ref_test"
   ```
3. `uv run python hpc/check_grib_sanity.py <file>` — it enforces the full message inventory, so a
   field that failed to compute cannot slip through.
4. Read the values back and compare against the wrfout. Do it on a 00Z file too (accumulations must
   be exactly zero) and on a March file (`SEAICE` non-zero, snow present): summer-only testing
   cannot distinguish a dead field from a seasonally-zero one.

## Architecture

### Two-Stage Conversion Pipeline

1. **WRF Diagnostics** (`src/wrf/`): Python wrappers around Fortran kernels compute derived variables and interpolate WRF model levels to 13 pressure levels (1000-50 hPa)
2. **Encoding**: eccodes encodes GRIB2 (Mercator, grid template 3.10, `grid_ccsds` packing) with ECMWF paramIds; anemoi-datasets creates Zarr with Zstd compression

### Key Modules

- **`src/wrf/`** - Custom wrf-python (v1.4.2) with decorator-based metadata attachment and LRU computation caching. Diagnostic generators are in `g_*.py` files (wind, pressure, cape, etc.)
- **`fortran/`** - Core computation kernels (vertical interpolation, CAPE, humidity, PV). OpenMP parallelization generated from `ompgen.F90.template`
- **`convert_to_pressure_levels.py`** - Main conversion script: reads WRF NetCDF, computes diagnostics, encodes GRIB2 with projection metadata. Accepts `--input`/`--output` CLI args. **What is produced and on which level lives entirely in the registry** (`wrf_era5_comparison.WRF_TO_ECMWF_PARAMID`); this module only knows how to compute each field and hand it to eccodes, so adding a variable is a registry entry plus (if derived) one block
- **`accum_ref.py`** - 00Z reference sidecars for accumulated fields (tp referred to 00Z of the same day); `python accum_ref.py extract <wrfout_00Z> <ref_dir>`
- **`wrf_era5_comparison.py`** - The variable registry: WRF/derived key -> shortName, paramId, units, GRIB level type and levels, and `stepType` for statistically-processed fields. `EXPECTED_MESSAGES` is derived from it and is what `check_grib_sanity.py` enforces
- **`MISSING_VARIABLES.md`** (+ `.pdf`) - What was requested but cannot be produced from these wrfout, and by which other route some of it could still be obtained. Read it before promising a variable
- **`tools/md2pdf.py`** - Minimal Markdown -> LaTeX -> PDF (no pandoc on Leonardo; xelatex + DejaVu handles Unicode). `tools/eccodes_env.sh` - source it before any interactive script that imports the eccodes bindings
- **`wrf_anemoi_recipe.yaml`** - Anemoi dataset recipe (input patterns, date ranges, compression settings)
- **`conf/pipeline.yaml`** - Hydra configuration for the HPC pipeline (date range, paths, SuperMUC remote config, SLURM settings, GRIB naming template)
- **`hpc/`** - HPC pipeline for Leonardo (CINECA). Uses Hydra config (`conf/pipeline.yaml`) with CLI overrides.
  - `submit_pipeline.py` - Orchestrator with two modes: entry (submits itself to SLURM) and worker (`--worker`, runs the job submission loop)
  - `fetch_day.sh` - SLURM job: rsync 24 hourly wrfout files from SuperMUC via SSH control socket
  - `convert_day.sh` - SLURM array job (0-23): convert each hour's wrfout to GRIB, delete wrfout on success. Re-entrant (skips existing outputs)
  - **Output tree is `grib_v2/`** (GRIB2, 246 messages), not the old `grib/` (GRIB1, 93): re-entrancy keys on the output GRIB existing, so writing the new schema into the old tree would silently skip every hour already converted
  - `orchestrator.sh` - SLURM wrapper for submit_pipeline.py in worker mode
  - `submit_step_pipeline.py` - Launcher for the step-by-step (hourly window) pipeline. Submits one recursive driver job; supports `dry_run=true` for a no-SLURM/no-network preview
  - `fetch_step.sh` - Recursive driver (lrd_all_serial). Fetches each timestep via the CINECA datamover (`ssh -xT data.leonardo.cineca.it "sftp -i <key> -B 262144 -R 256 -p datarelay@rdmtests.srv.lrz.de:<remote> <local>/"`, with `timeout`+retries and a NetCDF readability check), submits a convert job per timestep, then resubmits itself for the next batch until the window edge (backward by default). Writes the per-timestep status ledger; re-entrant (skips timesteps whose GRIB exists); logs and skips missing/on-tape files. With `pipeline.download_only=true` it stops after the fetch: no convert is submitted and the wrfout is **kept** (for staging raw files to hand to someone else)
  - `convert_step.sh` - Single-timestep convert job (dcgp_usr_prod), non-array variant of `convert_day.sh`. **Deletes its input wrfout on success** (unless `KEEP_WRFOUT=1`, from `pipeline.keep_wrfout`) — which is why download-only mode must never submit it, and why staged files belong in their own directory. It never deletes a 00Z wrfout whose `accum_ref` sidecar is missing
  - `lrz/` - Bash-only helpers to run **on LRZ** (no python env available there): `chapter_scan.sh` classifies a date window into ONLINE / OFFLINE (on tape) / ASSENTE via `mmlsattr`, `chapter_recall.sh` submits the `dsacli` stage job for the OFFLINE ones (dry-run unless `--run`), `chapter_common.sh` holds the shared date/path helpers. Dates accept `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`. Scan once over a wide window, recall in chunks: when no scan matches the recall window exactly, `chapter_recall.sh` picks the narrowest scan in `-o` that *contains* it and trims the offline list to the requested dates (written as `recall_<tag>_offline.txt`) — a stage of tens of TB should be split by month anyway
  - `fix_tp_accum.py` / `fix_tp_accum.sh` - One-off (idempotent) correction of GRIBs produced before commit 1eaffb8, whose tp was accumulated since run init: `tp(H) -= tp(00Z)` per day, 00Z zeroed last, only the tp message re-encoded, atomic per file, marker genproc=128, ledger `logs/fix_tp_accum_status.log`. Per-month SLURM array on dcgp_usr_prod. Days with no 00Z GRIB and no sidecar are `NO_REFERENCE`: re-run the step pipeline on that day's 00Z, then the fix
  - `dates.py` - Date-to-run-folder mapping (target date -> SuperMUC init folder with 6h spinoff). Handles different base paths for pre-2023 vs 2023+ data. Reused by both pipelines
- **`functions_supermuc.sh`** - Shell helper functions (`supermuc-put`, `supermuc-get`) for rsync transfers via SSH control socket

### Data Flow

WRF NetCDF (`wrfout_d02_*`) -> wrf-python diagnostics + pressure interpolation -> GRIB2 with ECMWF paramIds -> Anemoi Zarr dataset

### HPC Pipeline Flow (Leonardo ↔ SuperMUC)

Per day: orchestrator submits fetch job (lrd_all_serial, rsync 24 wrfout) -> convert array job (0-23, each hour independently, depends on fetch via `afterok`) -> delete wrfout on success. Config via Hydra (`conf/pipeline.yaml`) with CLI overrides. SSH control socket must be pre-activated in tmux. Pipeline is re-entrant: skips dates where all 24 GRIBs already exist, and individual convert tasks skip if the output GRIB exists. SuperMUC has different base paths for pre-2023 vs 2023+ runs.

**Step-by-step flow (datamover, hourly window):** an alternative to the day-based flow. `submit_step_pipeline.py` launches a **login-node** driver (`fetch_step.sh`) as a detached process — the CINECA datamover is reachable only from login nodes, NOT from `lrd_all_serial`/compute. The driver fetches each hourly timestep via the datamover and submits an independent convert job per timestep on `dcgp_usr_prod`. The driver works to a wall-time budget (`pipeline.driver_max_seconds`) and then **re-spawns itself detached** (`setsid`) for the next batch until the window edge. `pipeline.direction` (default `backward`) walks newest→oldest so recent GRIBs land first. Each timestep's outcome is appended to `paths.status_log` (`step_pipeline_status.log`); missing/on-tape files on LRZ are logged (`MISSING_ON_LRZ`/`TAPE_TIMEOUT`/`UNREADABLE_TAPE`) and skipped, never fatal — recall them on LRZ and re-run (re-entrant). The fetch is wrapped in `timeout` (catches tape-recall hangs) with retries, and the downloaded file is checked as a readable NetCDF before convert. `report=true` prints a read-only DONE/MISSING/RECALL table (keyed on the staged wrfout, size-checked, when `download_only=true`).

**Download-only mode:** `pipeline.download_only=true` fetches the wrfout files and stops — no convert, nothing deleted. Used to stage raw wrfout for another user. Always pair it with a dedicated `paths.wrfout_dir` **and** its own `paths.status_log` / `paths.driver_log` / `paths.stop_flag`, otherwise a stop request or ledger entry from one driver chain hits the other. Re-entrancy keys on the staged wrfout existing at a plausible size (`SKIP_RAW_EXISTS`) instead of on the GRIB. To convert those staged files later, re-run the **normal** pipeline with `paths.wrfout_dir` pointed at the staging dir: the driver finds each file already local, skips the sftp, converts, and `convert_step.sh` deletes it — which is exactly the cleanup step (add `pipeline.keep_wrfout=true` to convert and keep the files). `batch.max_queued_converts=N` (0 = off) makes each batch wait until the user has no `conv_*` job queued and caps `batch.size` to N: CINECA cancels and warns on hundreds of queued jobs, so use `batch.size=48 batch.max_queued_converts=48` (two days at a time). `hpc/run_share_conversion.sh` converts **every wrfout still on local disk** (4380 h: wrfout_share 2024-06-18..09-12, then wrfout_share 2019-06-17..09-06, then wrfout_2024fill 2024-03-18..03-31 — each window names its own wrfout subdir in the `WINDOWS` table; keep_wrfout, gate 48, then report + `check_grib_sanity` job) as a self-detaching, snapshotted login-node sequence; log `logs/share_conv_sequence.log`, stop `logs/share_conv_sequence.stop`. 2024-03-18 has no 00Z on disk, so `ensure_ref` fetches that one wrfout from the relay. `hpc/run_2024_fill.sh` closes the 2024 gap (5088 hours: 2024-09-13..10-25 then 2024-01-01..06-17) with the same machinery but **two chains per phase**: the window is cut into ~monthly phases and, as soon as a phase finishes downloading (`download_only`, staging `wrfout_2024fill`, `fetch_parallel=3`), its convert chain is launched in the background while the next phase downloads — the convert chain only sees local files, so it never competes for the datamover, and at most two phases sit on disk (peak ~58 TB instead of the ~88 TB a download-everything-first run would need). It holds a new download while the project is above `QUOTA_STOP_TB`; log `logs/fill2024_sequence.log`, stop `logs/fill2024_sequence.stop`, per-chain ledgers `logs/fill2024_<phase>_{dl,cv}_*`. `KEEP_WRFOUT` (default **true** since 2026-09-16: more variables may have to be extracted from these years, and re-fetching costs 9 GB/timestep over the relay) keeps the staged wrfout after conversion — with it nothing frees space, so a `QUOTA_HOLD` can no longer resolve itself. `PHASES_ONLY="p3_mar p4_apr"` restricts the run to some phases: **required when resuming a stopped sequence**, because a phase whose wrfout were already deleted is no longer re-entrant on the download side (`SKIP_RAW_EXISTS` keys on the staged file) and would be re-downloaded in full. **Paused 2026-09-16** pending the new-variables work: all the fill2024 stop flags are set. That work is now DONE on the code side (GRIB2, 246 messages) but the campaign has NOT been restarted and must not be without an explicit go-ahead; `HANDOFF_nuove_variabili.md` (repo root) holds the current state, the measured costs and the restart order. The datamover/relay paths live under `datamover.*` in `conf/pipeline.yaml` (transfer is `sftp` from `datamover.remote_host` with `datamover.identity_file` + `datamover.sftp_opts`; distinct from the rsync/DSS paths under `supermuc.*`); both share the init-folder mapping in `dates.py`. Use `dry_run=true` to preview all commands without SLURM or network. DCGP bills per core (measured `billing=1`), so 1 core/timestep is cost-optimal; RAM is not billed (32G since the GRIB2 schema: measured peak 18.2 GB).

### HPC gotchas (Leonardo / CINECA) — learned the hard way

- **Datamover reachability (CRITICAL):** `data.leonardo.cineca.it` is reachable **only from regular login nodes** (e.g. login02), **NOT from `lrd_all_serial`** — that partition runs on `login08`/`login13`, both firewalled off from the datamover (TCP :22 times out; confirmed by test). A fetch driver submitted to `lrd_all_serial` logs `FETCH_ERROR ... Connection timed out` for every timestep. Hence the step pipeline runs `fetch_step.sh` **on the login node** (detached, `setsid`, time-budgeted self-respawn) and `sbatch`'s only the convert to `dcgp_usr_prod`; `submit_step_pipeline.py` TCP-probes the datamover and refuses to launch from a node that can't reach it. Probe manually with `bash -c 'cat </dev/null >/dev/tcp/data.leonardo.cineca.it/22'` (the datamover's restricted shell rejects `echo`/nested-`ssh`/compound commands, so you can't `ls` through it). The transfer run on the datamover is now **`sftp`** (not `scp`) against the LRZ relay `datarelay@rdmtests.srv.lrz.de`, with an explicit `-i <key>` and `-B 262144 -R 256 -p`.
- **DCGP billing** is per **core** (`billing=1` for a 1-core job; nodes shared, not exclusive). RAM/tmpfs don't inflate it → 1 core/timestep is cost-optimal; RAM is free (32G requested, 18.2 GB measured peak for the GRIB2 schema). DCGP node = 112 cores / 514 GB / 3 TB tmpfs. Account `aifpt_ailamit_0` (DCGP), `aifpt_ailamit` (Booster). `lrd_all_serial` needs no account.
- **Login-node process limit is CPU time, not wall time:** `ulimit -t` = **600 s of CPU per process**. The step pipeline never approaches it because the transfer runs *on the datamover* — data flows LRZ -> datamover -> `/leonardo_work` (which the datamover mounts) and never through the login node, so the driver and its `ssh` sit at ~0 s CPU. Measured: a driver alive for hours with 0 s CPU; the only real cost is the NetCDF check at ~1.9 s CPU/file, in its own python process. A **direct** `scp`/`rsync` from LRZ to Leonardo would instead do all the crypto here and hit 600 s within minutes — that is the case this architecture avoids. There is no watchdog: a driver killed for any other reason (node drain, reboot, `pkill`) dies without respawning, so check liveness via `find <driver_log> -mmin +25` on the shared FS, never `pgrep` (which is per-login-node).
- **The fetch driver is live code:** `fetch_step.sh` re-execs itself from disk on every respawn (~18 min), so while a chain is running the file on disk *is* the running program. The launcher therefore snapshots it to `<log_dir>/.driver_<chain>_<ts>.sh` and respawns from there, which makes a live chain immune to edits — before that fix, a documentation edit landing during a respawn read a half-written file and killed the 2024 staging run silently after 22/2088 files. `respawn()` also `bash -n`-validates and logs `RESPAWN_FAILED` rather than dying quietly. Note the chain keeps using the snapshot from its launch, so a code fix only reaches it on a relaunch.
- **`uv` is a shell function** (in the user profile) that wraps `uv sync` to load the python module; the real binary is `~/.local/bin/uv` (on PATH in batch jobs), so `uv run ...` works in scripts.
- **eccodes runtime:** the convert jobs must `module load eccodes/2.34.0--gcc--12.2.0` and set `LD_PRELOAD`/`LD_LIBRARY_PATH` to the gcc-12 runtime + eccodes lib64; the `grib_*` CLI tools are not on PATH by default and the python eccodes bindings fail to find the C lib without this env. `source tools/eccodes_env.sh` does exactly this for interactive use (`hpc/convert_step.sh` inlines the same paths).
- **Date math:** login node TZ is CEST; GNU `date -d "<date> <H>:00:00 +1 hour"` misparses (`+1` read as a timezone) → do all timestep arithmetic in **UTC via epoch seconds** (as `fetch_step.sh` does).
- `lrd_all_serial` `/tmp` is **node-local** (login08/13), not shared with your login session — write job output to `/leonardo_work` or `$HOME`.
- A CHAPTER wrfout is ~9.14 GB; one timestep converts to a **~770 MB GRIB2 (246 messages, 13 pressure levels) in ~5 min on 1 DCGP core**, peak RSS **19.0 GB** (hence `slurm.step_convert_mem: 32G`). Measured 2026-09-17 on three files: 761 MB for a summer afternoon, 661 MB for a 00Z (accumulations are zero there), 784 MB for a March file with snow and sea ice; day-weighted average ~767 MB, so ~19 GB/day and **~7 TB/year**. The previous 182-message schema was 663 MB in ~2:47. It is still *faster* than the old 93-message GRIB1 (~7.5 min): `grid_ccsds` packs both smaller and much faster than `grid_second_order`.

### Important Domain Details

- Mercator projection (MAP_PROJ=3), grid 1353x1641 at 3km resolution
- **Declare WRF's sphere in the GRIB.** `shapeOfTheEarth=1` with radius 6370000 m: WRF integrates on that sphere, and without it eccodes derives a grid off by ~1.1 km at the northern edge (measured; GRIB1 had no way to express it, so the old archive carries that error)
- **Variable schema**: 90 entries -> 246 messages, defined once in `wrf_era5_comparison.WRF_TO_ECMWF_PARAMID` (13 variables x 13 pressure levels + 77 single-level). `EXPECTED_MESSAGES` comes from it and `hpc/check_grib_sanity.py` enforces it, so a field that silently fails to compute is caught. The 13 pressure-level variables are the ERA5 set plus both vertical-velocity conventions (`w` in Pa/s, `wz` in m/s) and the three hydrometeor/cloud fields `cc`/`crwc`/`cswc`
- **What the run cannot give**, whatever we do to the converter: no TKE and no PBLH (`BL_PBL_PHYSICS=1`, YSU is non-local, `KM_OPT=4`), no ocean/wave coupling (`SF_OCEAN_PHYSICS=0`) so no waves/currents/SSH/ice thickness, no `TSK`, `HFX`, `LH`, no `LANDUSEF`/`GREENFRAC`/`SOILCTOP` — those live in `geo_em_d02`, which is **irrecoverable** (the scratch tree was deleted and LRZ has already been asked), so fractional land cover is gone for good and only the dominant category survives. `ACHFX`/`ACLHF` exist but are identically zero. The gust components `10efg`/`10nfg` and TKE are excluded by decision, not by impossibility alone. Full reasoning and the possible workarounds: `MISSING_VARIABLES.md`
- **Fields present but dead** (identically zero on every sampled timestep, 2019 + 2024 + 2024-03): `ACHFX`, `ACLHF`, `ACGRDFLX`, `NOAHRES`, `SSTSK`, `SST_INPUT`, `SWNORM`, `ACSNOW`, `HAILNC`, `RAINC`, `RAINSH`, `PREC_ACC_C`, `LWDNT`/`LWDNTC`/`ACLWDNT`/`ACLWDNTC`. `RAINC` is dead because `CU_PHYSICS=0`, so `cp` and `csf` are **not** published as "physically correct zeros" — a field that is always zero is a dead field whatever the reason. `ACSNOM` is alive but **not monotone** (points reset within a run), so it is not published as `smlt`. Alive but deliberately unpublished: `ACRUNOFF` (measured identical to `SFROFF`, not the total — `ro` is computed as `SFROFF+UDROFF`), `QGRAUP`, `REFL_10CM`, `LPI`, `SR`, `RHOSNF`, `SNOWFALLAC` (snow depth, not water equivalent), `SNOALB`, `SHDMAX`/`SHDMIN`, `TMN` — no ERA5 parameter fits them
- **`CLDFRA` is fractional, not binary.** `ICLOUD=1` is the Xu-Randall scheme: measured histogram over a 500x600 subdomain, only 18-22% of cloudy points sit exactly at 1 and the rest spread over the whole 0-1 range (614k distinct values). An earlier note in this file claimed it was binary — it was wrong. So `tcc`/`hcc`/`mcc`/`lcc` are honest maximum-random overlaps and `cc` on pressure levels is a legitimate ERA5 field. `SST` is constant within each 24 h run (`SST_UPDATE=0`). `skt` is derived from `LWUPB` because `TSK` was not written out
- **The land/sea mask is NOT constant in time.** WRF reclassifies points with `SEAICE>0` as ice: `LANDMASK` 0->1, `IVGTYP` 17->15, `ISLTYP` 14->16, and `ALBBCK`/`SNOALB` change with them (measured: 2469 points on 2024-03-20, exactly the sea-ice points; identical fields between 2019-06 and 2024-07). `lsm`, `tvl`, `tvh`, `slt`, `al` are therefore written in every message and must not be treated as one-per-archive statics
- Ocean masking uses LANDMASK field for SST/sea-ice distinction (masked points are written as a GRIB bitmap, not as zeros)
- Unit conversions required: geopotential (m -> m^2/s^2), radiation, precipitation. **Ask wrf-python for the target units** (`getvar('td2', units='K')`, `getvar('slp', units='Pa')`) rather than converting afterwards: its defaults are degC and hPa, and the GRIB1 archive wrote `2d` straight through, i.e. in degC under a paramId defined in K
- **Accumulated fields are referred to 00Z of the same day.** WRF accumulates from run init (18Z of the previous day, 6 h spinup), so `tp(H) = (RAINNC(H) - RAINNC(00Z same day, same run)) / 1000`, zero at 00Z. Same rule for every name in `accum_ref.ACCUMULATED_VARS`. RAINC is identically 0 (CU_PHYSICS=0), so tp = RAINNC is complete; no bucket reset (no I_RAINNC). They carry `generatingProcessIdentifier=128` (127 = old, run-init-referred)
- **In GRIB2 the accumulated fields MUST use product definition template 8.** Their ECMWF definitions mandate `typeOfStatisticalProcessing`, which does not exist in the instantaneous template: setting `paramId` for `tp`/`ssrd`/`tsr`/`tirf`/`sf`/`sro`/`ssro`/`smlt`/`10fg` on a PDT-0 message fails with "Key/value not found". So they are written with reference time = 00Z of the day and step `0-H`, and `validityDate`/`validityTime` still resolve to the timestep. Instantaneous fields keep `dataDate`/`dataTime` = valid time. A file therefore mixes reference times on purpose — index on validity, never on dataTime
- **`10fg` is the one non-00Z accumulation.** `WSPD10MAX` is reset by WRF at every history write (verified: it is not monotonic across consecutive hours), so it is a 1-hour maximum and is encoded with reference time H-1 and step `0-1`, `stepType=max`. It is the max of the *resolved* 10 m wind, not a gust parameterisation
- **00Z reference sidecar** (`accum_ref.py`): `<work_dir>/accum_ref_v2/YYYY/MM/accum_ref_YYYYMMDD.npz`, native WRF units. **Adding a name to `ACCUMULATED_VARS` makes every existing sidecar incomplete** (`load_ref` raises `KeyError`), so those days must be re-extracted from their 00Z wrfout. The 246-message schema needs **19** accumulators (precipitation, runoff and the full radiation set, all verified monotone within a run), against the 12 of the previous schema and the 6 the sidecars on disk actually carry — which is why the tree is `accum_ref_v2` and the old `accum_ref` is left alone for `grib/` and `fix_tp_accum.py`. Beware that `ensure_ref` trusts any non-empty sidecar it finds without checking its contents. Sidecar contents: written atomically by the converter for 00Z input, by `fetch_step.sh` `ensure_ref` (which fetches the 00Z first when needed — in backward order it would arrive last) and by `fix_tp_accum.py` (from the old 00Z GRIB). Invariant: the 00Z wrfout is never deleted without its sidecar. A convert with no reference fails loudly (no GRIB) rather than writing run-init-referred tp
- Derived variables: specific humidity from mixing ratio, TCW, skin temperature, slope of orography
