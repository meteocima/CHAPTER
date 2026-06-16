#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CHAPTER pipeline orchestrator: submit SLURM jobs for fetch + convert over a date range.

Two modes:
  - Entry mode (default): submits itself as a SLURM job on lrd_all_serial, then exits.
  - Worker mode (--worker): runs the actual job submission loop inside a SLURM job.

Usage:
    python hpc/submit_pipeline.py                                   # submit orchestrator to SLURM
    python hpc/submit_pipeline.py dates.start=2023-03-01            # with Hydra overrides
    python hpc/submit_pipeline.py --worker                          # run submission loop directly
"""

import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import hydra
from omegaconf import DictConfig, OmegaConf

# Add project root to path so hpc.dates is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hpc.dates import get_remote_run_path


def parse_sbatch_jobid(output: str) -> str:
    """Extract job ID from sbatch output like 'Submitted batch job 12345'."""
    match = re.search(r"Submitted batch job (\d+)", output)
    if not match:
        raise RuntimeError(f"Could not parse job ID from sbatch output: {output}")
    return match.group(1)


def submit_sbatch(args: list[str]) -> str:
    """Submit a SLURM job and return the job ID."""
    result = subprocess.run(
        ["sbatch"] + args,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sbatch failed (exit {result.returncode})\n"
            f"  args: {args}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return parse_sbatch_jobid(result.stdout)


def grib_filename(template: str, target_date: date, hour: int) -> str:
    """Generate GRIB filename from template."""
    return template.format(
        year=target_date.year,
        date_compact=target_date.strftime("%Y%m%d"),
        hour=hour,
    )


def all_gribs_exist(grib_dir: str, template: str, target_date: date) -> bool:
    """Check if all 24 hourly GRIB files exist for a date."""
    for hour in range(24):
        path = os.path.join(grib_dir, grib_filename(template, target_date, hour))
        if not os.path.exists(path):
            return False
    return True


def run_worker(cfg: DictConfig):
    """Worker mode: iterate over dates and submit fetch + convert jobs."""
    start = date.fromisoformat(cfg.dates.start)
    end = date.fromisoformat(cfg.dates.end)
    grib_dir = cfg.paths.grib_dir
    wrfout_dir = cfg.paths.wrfout_dir
    log_dir = cfg.paths.log_dir
    project_dir = os.path.abspath(cfg.paths.project_dir)
    grib_template = cfg.grib.name_template

    # Create directories
    for d in [grib_dir, wrfout_dir, log_dir]:
        os.makedirs(d, exist_ok=True)

    # Build common SLURM args
    slurm_account = cfg.slurm.account
    account_args = ["--account", slurm_account] if slurm_account else []

    hpc_dir = os.path.join(project_dir, "hpc")
    fetch_script = os.path.join(hpc_dir, "fetch_day.sh")
    convert_script = os.path.join(hpc_dir, "convert_day.sh")

    total_days = 0
    skipped_days = 0
    submitted_jobs = []

    current = start
    while current <= end:
        date_str = current.isoformat()  # YYYY-MM-DD
        date_compact = current.strftime("%Y%m%d")

        # Skip if all GRIBs already exist
        if all_gribs_exist(grib_dir, grib_template, current):
            print(f"[{date_str}] All 24 GRIBs exist, skipping.")
            skipped_days += 1
            current += timedelta(days=1)
            continue

        # Compute remote path
        remote_path = get_remote_run_path(
            current,
            base_2023=cfg.supermuc.base_2023,
            base_pre2023=cfg.supermuc.base_pre2023,
            init_hour=cfg.supermuc.init_hour,
        )

        local_wrfout_dir = os.path.join(wrfout_dir, date_str)

        # --- Submit fetch job ---
        fetch_env = (
            f"TARGET_DATE={date_str},"
            f"REMOTE_PATH={remote_path},"
            f"LOCAL_DIR={local_wrfout_dir},"
            f"SUPERMUC_HOST={cfg.supermuc.host}"
        )
        fetch_args = [
            "--partition", cfg.slurm.fetch_partition,
            "--time", cfg.slurm.fetch_walltime,
            "--job-name", f"fetch_{date_compact}",
            "--output", os.path.join(log_dir, f"fetch_{date_compact}_%j.out"),
            "--export", fetch_env,
        ] + account_args + [fetch_script]

        fetch_id = submit_sbatch(fetch_args)

        # --- Submit convert array job (depends on fetch) ---
        convert_env = (
            f"TARGET_DATE={date_str},"
            f"WRFOUT_DIR={local_wrfout_dir},"
            f"GRIB_DIR={grib_dir},"
            f"PROJECT_DIR={project_dir},"
            f"GRIB_TEMPLATE={grib_template}"
        )
        convert_args = [
            "--partition", cfg.slurm.convert_partition,
            "--time", cfg.slurm.convert_walltime,
            "--mem", cfg.slurm.convert_mem,
            "--job-name", f"conv_{date_compact}",
            "--output", os.path.join(log_dir, f"convert_{date_compact}_%A_%a.out"),
            "--dependency", f"afterok:{fetch_id}",
            "--export", convert_env,
        ] + account_args + [convert_script]

        convert_id = submit_sbatch(convert_args)

        print(f"[{date_str}] fetch={fetch_id}  convert={convert_id}  remote={remote_path}")
        submitted_jobs.append((date_str, fetch_id, convert_id))
        total_days += 1
        current += timedelta(days=1)

    # Summary
    print(f"\n{'='*60}")
    print(f"Pipeline submission complete.")
    print(f"  Days submitted: {total_days}")
    print(f"  Days skipped (already done): {skipped_days}")
    print(f"  Total SLURM jobs: {total_days * 2} ({total_days} fetch + {total_days} array)")
    print(f"\nMonitor with: squeue -u $USER")
    print(f"Logs in: {log_dir}")


def run_entry(cfg: DictConfig):
    """Entry mode: submit the orchestrator itself as a SLURM job."""
    project_dir = os.path.abspath(cfg.paths.project_dir)
    log_dir = cfg.paths.log_dir
    os.makedirs(log_dir, exist_ok=True)

    # Reconstruct Hydra overrides from sys.argv (everything that's not --worker)
    hydra_overrides = " ".join(
        arg for arg in sys.argv[1:] if arg != "--worker"
    )

    slurm_account = cfg.slurm.account
    account_args = ["--account", slurm_account] if slurm_account else []

    orchestrator_script = os.path.join(project_dir, "hpc", "orchestrator.sh")
    orch_env = (
        f"PROJECT_DIR={project_dir},"
        f"HYDRA_OVERRIDES={hydra_overrides}"
    )

    orch_args = [
        "--partition", cfg.slurm.fetch_partition,
        "--time", cfg.slurm.orchestrator_walltime,
        "--job-name", "chapter_orch",
        "--output", os.path.join(log_dir, "orchestrator_%j.out"),
        "--export", orch_env,
    ] + account_args + [orchestrator_script]

    orch_id = submit_sbatch(orch_args)
    print(f"Orchestrator submitted as SLURM job {orch_id}")
    print(f"Monitor with: squeue -u $USER")
    print(f"Log: {log_dir}/orchestrator_{orch_id}.out")


# Detect --worker before Hydra parses sys.argv (it would reject the flag)
WORKER_MODE = "--worker" in sys.argv
if WORKER_MODE:
    sys.argv.remove("--worker")


@hydra.main(config_path="../conf", config_name="pipeline", version_base=None)
def app(cfg: DictConfig):
    # Resolve all interpolations
    OmegaConf.resolve(cfg)

    if WORKER_MODE:
        run_worker(cfg)
    else:
        run_entry(cfg)


if __name__ == "__main__":
    app()
