#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CHAPTER step-by-step pipeline launcher.

Submits a single recursive driver job (hpc/fetch_step.sh) on a partition with
outbound connectivity (lrd_all_serial). The driver fetches wrfout files via the
CINECA datamover, submits per-timestep convert jobs on a compute node
(dcgp_usr_prod), and resubmits itself batch by batch until the end of the window.

Usage:
    python hpc/submit_step_pipeline.py                                     # use conf defaults
    python hpc/submit_step_pipeline.py window.start_date=2023-05-23 \\
        window.start_hour=0 window.end_date=2023-05-25 window.end_hour=23
    python hpc/submit_step_pipeline.py ... dry_run=true                    # local preview, no SLURM
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import hydra
from omegaconf import DictConfig, OmegaConf

# Add project root to path for consistency with submit_pipeline.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def parse_sbatch_jobid(output: str) -> str:
    """Extract job ID from sbatch output like 'Submitted batch job 12345'."""
    match = re.search(r"Submitted batch job (\d+)", output)
    if not match:
        raise RuntimeError(f"Could not parse job ID from sbatch output: {output}")
    return match.group(1)


def submit_sbatch(args: list[str]) -> str:
    """Submit a SLURM job and return the job ID."""
    result = subprocess.run(["sbatch"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"sbatch failed (exit {result.returncode})\n"
            f"  args: {args}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return parse_sbatch_jobid(result.stdout)


@hydra.main(config_path="../conf", config_name="pipeline", version_base=None)
def app(cfg: DictConfig):
    OmegaConf.resolve(cfg)

    project_dir = os.path.abspath(cfg.paths.project_dir)
    wrfout_dir = cfg.paths.wrfout_dir
    grib_dir = cfg.paths.grib_dir
    log_dir = cfg.paths.log_dir
    grib_template = cfg.grib.name_template
    dry_run = bool(cfg.get("dry_run", False))

    # Build start/end timestamps "YYYY-MM-DDTHH" and validate ordering
    start_dt = f"{cfg.window.start_date}T{int(cfg.window.start_hour):02d}"
    end_dt = f"{cfg.window.end_date}T{int(cfg.window.end_hour):02d}"
    if datetime.strptime(start_dt, "%Y-%m-%dT%H") > datetime.strptime(end_dt, "%Y-%m-%dT%H"):
        raise ValueError(f"window start ({start_dt}) is after end ({end_dt})")

    # Create directories
    for d in [wrfout_dir, grib_dir, log_dir]:
        os.makedirs(d, exist_ok=True)

    hpc_dir = os.path.join(project_dir, "hpc")
    driver_script = os.path.join(hpc_dir, "fetch_step.sh")
    convert_script = os.path.join(hpc_dir, "convert_step.sh")

    # Driver runs on lrd_all_serial (no budget); convert runs on dcgp_usr_prod and
    # must charge the DCGP-budget association.
    driver_account = cfg.slurm.account or ""
    convert_account = cfg.slurm.step_convert_account or cfg.slurm.account or ""

    # Environment carried by the driver (and propagated to its resubmissions via --export=ALL)
    driver_env = {
        "START_DT": start_dt,
        "END_DT": end_dt,
        "CURRENT_DT": start_dt,
        "BATCH_SIZE": str(cfg.batch.size),
        "FETCH_PARALLEL": str(cfg.batch.fetch_parallel),
        "WRFOUT_DIR": wrfout_dir,
        "GRIB_DIR": grib_dir,
        "GRIB_TEMPLATE": grib_template,
        "PROJECT_DIR": project_dir,
        "DATAMOVER_HOST": cfg.datamover.host,
        "SSH_CONFIG": cfg.datamover.ssh_config,
        "REMOTE_HOST": cfg.datamover.remote_host,
        "BASE_2023": cfg.datamover.base_2023,
        "BASE_PRE2023": cfg.datamover.base_pre2023,
        "INIT_HOUR": str(cfg.datamover.init_hour),
        "LOG_DIR": log_dir,
        "DRIVER_SCRIPT": driver_script,
        "CONVERT_SCRIPT": convert_script,
        "DRIVER_PARTITION": cfg.slurm.driver_partition,
        "DRIVER_WALLTIME": cfg.slurm.driver_walltime,
        "DRIVER_ACCOUNT": driver_account,
        "CONVERT_PARTITION": cfg.slurm.step_convert_partition,
        "CONVERT_WALLTIME": cfg.slurm.step_convert_walltime,
        "CONVERT_MEM": cfg.slurm.step_convert_mem,
        "CONVERT_ACCOUNT": convert_account,
        "DRY_RUN": "1" if dry_run else "0",
    }
    env_str = ",".join(f"{k}={v}" for k, v in driver_env.items())

    account_args = ["--account", driver_account] if driver_account else []
    sbatch_args = [
        "--partition", cfg.slurm.driver_partition,
        "--time", cfg.slurm.driver_walltime,
        "--job-name", f"fetch_step_{start_dt.replace('-', '').replace('T', '')}",
        "--output", os.path.join(log_dir, "fetch_step_%j.out"),
        "--export", env_str,
    ] + account_args + [driver_script]

    if dry_run:
        # Preview locally without SLURM: print the sbatch command, then run the
        # driver directly (DRY_RUN=1) to show the planned fetch/convert/recursion.
        print("DRY RUN — would submit:")
        print("  sbatch " + " ".join(sbatch_args))
        print("\n--- driver preview (first batch) ---", flush=True)
        run_env = {**os.environ, **driver_env}
        subprocess.run(["bash", driver_script], env=run_env, check=True)
        return

    job_id = submit_sbatch(sbatch_args)
    print(f"Driver submitted as SLURM job {job_id}")
    print(f"Window: {start_dt} -> {end_dt}  (batch={cfg.batch.size}, parallel={cfg.batch.fetch_parallel})")
    print(f"Monitor with: squeue -u $USER")
    print(f"Logs in: {log_dir}")


if __name__ == "__main__":
    app()
