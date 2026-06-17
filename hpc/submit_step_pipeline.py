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
import socket
import subprocess
import sys
from datetime import datetime, timedelta
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


def datamover_reachable(host: str, port: int = 22, timeout: int = 15) -> bool:
    """TCP-probe the datamover. It is reachable from regular login nodes only."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def grib_name(template: str, dt: datetime) -> str:
    return template.format(year=dt.year, date_compact=dt.strftime("%Y%m%d"), hour=dt.hour)


# Status-log tags that mean the timestep needs attention / a tape recall on LRZ.
PROBLEM_TAGS = {"MISSING_ON_LRZ", "TAPE_TIMEOUT", "UNREADABLE_TAPE", "FETCH_ERROR"}
CLEAR_TAGS = {"FETCH_OK", "CONVERT_SUBMITTED", "SKIP_GRIB_EXISTS"}


def do_report(start_dt, end_dt, direction, grib_dir, grib_template, status_log):
    """Read-only consolidated status: per-timestep DONE / GRIB_MISSING / RECALL.

    Cross-references the produced GRIBs with the driver status ledger so it is
    easy to see which timesteps still need a tape recall on LRZ.
    """
    start = datetime.strptime(start_dt, "%Y-%m-%dT%H")
    end = datetime.strptime(end_dt, "%Y-%m-%dT%H")

    hours, t = [], start
    while t <= end:
        hours.append(t)
        t += timedelta(hours=1)
    if direction == "backward":
        hours.reverse()

    # Last-wins parse of the ledger: a later success clears an earlier problem.
    problems = {}
    if os.path.exists(status_log):
        with open(status_log) as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue
                dtv, status = parts[1], parts[2]
                detail = parts[3] if len(parts) > 3 else ""
                if status in PROBLEM_TAGS:
                    problems[dtv] = (status, detail)
                elif status in CLEAR_TAGS:
                    problems.pop(dtv, None)

    done = missing = recall = 0
    recall_list = []
    print(f"# Step pipeline report  window {start_dt}..{end_dt}  ({direction})")
    print(f"# grib_dir:   {grib_dir}")
    print(f"# status_log: {status_log}")
    print(f"#  {'timestep':16}  {'state':18}  detail")
    for dt in hours:
        dts = dt.strftime("%Y-%m-%dT%H")
        gp = os.path.join(grib_dir, grib_name(grib_template, dt))
        if os.path.exists(gp):
            state, detail = "DONE", ""
            done += 1
        elif dts in problems:
            tag, detail = problems[dts]
            state = f"RECALL:{tag}"
            recall += 1
            recall_list.append(dts)
        else:
            state, detail = "GRIB_MISSING", "(no problem logged; fetch/convert pending or not attempted)"
            missing += 1
        print(f"   {dts:16}  {state:18}  {detail[:80]}")
    print(f"\n# summary: {done} done, {missing} pending, {recall} need recall/attention")
    if recall_list:
        print("# timesteps to recall on LRZ:\n " + " ".join(recall_list))


@hydra.main(config_path="../conf", config_name="pipeline", version_base=None)
def app(cfg: DictConfig):
    OmegaConf.resolve(cfg)

    project_dir = os.path.abspath(cfg.paths.project_dir)
    wrfout_dir = cfg.paths.wrfout_dir
    grib_dir = cfg.paths.grib_dir
    log_dir = cfg.paths.log_dir
    grib_template = cfg.grib.name_template
    status_log = cfg.paths.status_log
    dry_run = bool(cfg.get("dry_run", False))
    report = bool(cfg.get("report", False))
    direction = str(cfg.pipeline.direction)
    if direction not in ("backward", "forward"):
        raise ValueError(f"pipeline.direction must be 'backward' or 'forward', got {direction!r}")

    # Build start/end timestamps "YYYY-MM-DDTHH" (START=oldest, END=newest) and validate
    start_dt = f"{cfg.window.start_date}T{int(cfg.window.start_hour):02d}"
    end_dt = f"{cfg.window.end_date}T{int(cfg.window.end_hour):02d}"
    if datetime.strptime(start_dt, "%Y-%m-%dT%H") > datetime.strptime(end_dt, "%Y-%m-%dT%H"):
        raise ValueError(f"window start ({start_dt}) is after end ({end_dt})")

    # Read-only consolidated report, no SLURM submission
    if report:
        do_report(start_dt, end_dt, direction, grib_dir, grib_template, status_log)
        return

    # backward walks from the NEWEST edge; forward from the OLDEST edge
    current_dt = end_dt if direction == "backward" else start_dt

    # Create directories
    for d in [wrfout_dir, grib_dir, log_dir]:
        os.makedirs(d, exist_ok=True)

    hpc_dir = os.path.join(project_dir, "hpc")
    driver_script = os.path.join(hpc_dir, "fetch_step.sh")
    convert_script = os.path.join(hpc_dir, "convert_step.sh")
    driver_log = os.path.join(log_dir, "fetch_step_driver.log")

    # Convert runs on dcgp_usr_prod and must charge the DCGP-budget association.
    convert_account = cfg.slurm.step_convert_account or cfg.slurm.account or ""

    # Environment carried by the driver (inherited verbatim by each detached respawn)
    driver_env = {
        "START_DT": start_dt,
        "END_DT": end_dt,
        "CURRENT_DT": current_dt,
        "DIRECTION": direction,
        "BATCH_SIZE": str(cfg.batch.size),
        "DRIVER_MAX_SECONDS": str(cfg.pipeline.driver_max_seconds),
        "FETCH_PARALLEL": str(cfg.batch.fetch_parallel),
        "FETCH_TIMEOUT": str(cfg.datamover.fetch_timeout),
        "FETCH_RETRIES": str(cfg.datamover.fetch_retries),
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
        "STATUS_LOG": status_log,
        "DRIVER_LOG": driver_log,
        "DRIVER_SCRIPT": driver_script,
        "CONVERT_SCRIPT": convert_script,
        "CONVERT_PARTITION": cfg.slurm.step_convert_partition,
        "CONVERT_WALLTIME": cfg.slurm.step_convert_walltime,
        "CONVERT_MEM": cfg.slurm.step_convert_mem,
        "CONVERT_ACCOUNT": convert_account,
        "DRY_RUN": "1" if dry_run else "0",
    }
    run_env = {**os.environ, **driver_env}

    if dry_run:
        # Preview locally without network: run the driver directly (DRY_RUN=1) to
        # show the planned fetch/convert and the detached respawn for the next batch.
        print(f"DRY RUN — would launch the driver on this login node ({socket.gethostname()})")
        print(f"  bash {driver_script}   (detached, logs -> {driver_log})")
        print("\n--- driver preview (first batch) ---", flush=True)
        subprocess.run(["bash", driver_script], env=run_env, check=True)
        return

    # The datamover is reachable only from regular login nodes. Fail fast with a
    # clear message rather than launching a driver that can never fetch.
    host = socket.gethostname()
    if not datamover_reachable(cfg.datamover.host):
        raise SystemExit(
            f"ERROR: datamover {cfg.datamover.host}:22 is not reachable from this node ({host}).\n"
            f"Run this launcher from a regular login node (NOT lrd_all_serial / compute)."
        )

    # Launch the driver detached on THIS login node (survives logout); it scp's via
    # the datamover, sbatch's converts to dcgp_usr_prod, and respawns itself.
    os.makedirs(log_dir, exist_ok=True)
    logf = open(driver_log, "ab")
    proc = subprocess.Popen(
        ["bash", driver_script],
        env=run_env, cwd=project_dir,
        stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Fetch driver launched on login node {host} (pid {proc.pid})")
    print(f"Window: {start_dt}..{end_dt}  direction={direction}  start={current_dt}  "
          f"(batch<={cfg.batch.size}, parallel={cfg.batch.fetch_parallel}, "
          f"budget={cfg.pipeline.driver_max_seconds}s/process)")
    print(f"Driver log:    {driver_log}")
    print(f"Status ledger: {status_log}")
    print(f"Converts:      squeue -u $USER   (dcgp_usr_prod, account {convert_account})")
    print("Stop the chain with:  pkill -f hpc/fetch_step.sh")


if __name__ == "__main__":
    app()
