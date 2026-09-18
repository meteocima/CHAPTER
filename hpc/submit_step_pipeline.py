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
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import hydra
from omegaconf import DictConfig, OmegaConf

# Add project root to path for consistency with submit_pipeline.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hpc import ledger  # noqa: E402  (needs the path insert above)

# Width of the report's state column. Derived from the ledger vocabulary, because
# the longest state is "RECALL:<longest problem token>" and hardcoding it means
# the table stops lining up the day a longer token is added. "GRIB_MISSING" and
# "DONE" are shorter than every one of these, so they do not enter the maximum.
STATE_WIDTH = max(len(f"RECALL:{tag}")
                  for tag, kind in ledger.TOKEN_KINDS.items() if kind == ledger.PROBLEM)


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


# A genuine CHAPTER wrfout is ~9.1 GB; anything far below this is a tape stub or a
# truncated transfer. Mirrors MIN_WRFOUT_BYTES in hpc/fetch_step.sh.
MIN_WRFOUT_BYTES = 1073741824  # 1 GiB



def do_report(start_dt, end_dt, direction, grib_dir, grib_template, status_log,
              download_only=False, wrfout_dir=None, min_bytes=MIN_WRFOUT_BYTES):
    """Read-only consolidated status: per-timestep DONE / MISSING / RECALL.

    Cross-references the produced artefacts with the driver status ledger so it is
    easy to see which timesteps still need a tape recall on LRZ.

    In download-only mode there is no GRIB, so the artefact is the staged wrfout --
    and it is checked by SIZE, not mere existence: with no convert downstream, that
    size gate is the only thing separating an intact delivery from a truncated one.
    """
    start = datetime.strptime(start_dt, "%Y-%m-%dT%H")
    end = datetime.strptime(end_dt, "%Y-%m-%dT%H")

    hours, t = [], start
    while t <= end:
        hours.append(t)
        t += timedelta(hours=1)
    if direction == "backward":
        hours.reverse()

    lines = []
    if os.path.exists(status_log):
        with open(status_log) as f:
            lines = f.readlines()
    summary = ledger.classify(lines)
    problems = summary.problems

    def produced(dt):
        """(exists, path) for the artefact this mode is supposed to produce."""
        if download_only:
            p = os.path.join(wrfout_dir, dt.strftime("%Y-%m-%d"),
                             f"wrfout_d02_{dt:%Y-%m-%d}_{dt:%H}:00:00")
            try:
                return os.path.getsize(p) >= min_bytes, p
            except OSError:
                return False, p
        p = os.path.join(grib_dir, f"{dt.year:04d}", f"{dt.month:02d}",
                         grib_name(grib_template, dt))
        return os.path.exists(p), p

    missing_label = "RAW_MISSING" if download_only else "GRIB_MISSING"
    done = missing = recall = 0
    recall_list = []
    print(f"# Step pipeline report  window {start_dt}..{end_dt}  ({direction})")
    if download_only:
        print(f"# mode:       DOWNLOAD_ONLY (staged wrfout, >= {min_bytes} B)")
        print(f"# wrfout_dir: {wrfout_dir}")
    else:
        print(f"# grib_dir:   {grib_dir}")
    print(f"# status_log: {status_log}")
    print(f"#  {'timestep':16}  {'state':{STATE_WIDTH}}  detail")
    for dt in hours:
        dts = dt.strftime("%Y-%m-%dT%H")
        ok, _ = produced(dt)
        if ok:
            state, detail = "DONE", ""
            done += 1
        elif dts in problems:
            tag, detail = problems[dts]
            state = f"RECALL:{tag}"
            recall += 1
            recall_list.append(dts)
        else:
            state = missing_label
            detail = "(no problem logged; fetch pending or not attempted)"
            missing += 1
        print(f"   {dts:16}  {state:{STATE_WIDTH}}  {detail[:80]}")
    if summary.chain_events:
        # Not timesteps: these are about the driver itself, and they mean the chain
        # stopped early -- so the pending rows above may never have been attempted.
        print("\n# chain events")
        for key, tag, detail in summary.chain_events:
            # Not truncated: these are few, and the actionable half of the
            # driver's message ("re-launch the window, it is re-entrant") is at
            # the end of it.
            print(f"   {key:16}  {tag:22}  {detail}")
    print(f"\n# summary: {done} done, {missing} pending, {recall} need recall/attention")
    if summary.unknown:
        counted = ", ".join(f"{tag} ({n}x)" for tag, n in sorted(summary.unknown.items()))
        n_lines = sum(summary.unknown.values())
        subject = "entry carries" if n_lines == 1 else "entries carry"
        print(f"# WARNING: {n_lines} ledger {subject} a token this report does "
              f"not know: {counted}")
    if recall_list:
        print("# timesteps to recall on LRZ:\n " + " ".join(recall_list))


@hydra.main(config_path="../conf", config_name="pipeline", version_base=None)
def app(cfg: DictConfig):
    OmegaConf.resolve(cfg)

    project_dir = os.path.abspath(cfg.paths.project_dir)
    wrfout_dir = cfg.paths.wrfout_dir
    grib_dir = cfg.paths.grib_dir
    accum_ref_dir = cfg.paths.accum_ref_dir
    static_ref_dir = cfg.paths.static_ref_dir
    log_dir = cfg.paths.log_dir
    grib_template = cfg.grib.name_template
    status_log = cfg.paths.status_log
    skip_list = cfg.paths.get("skip_list", "") or ""
    if skip_list:
        skip_list = os.path.abspath(skip_list)
        if not os.path.exists(skip_list):
            raise SystemExit(f"ERROR: paths.skip_list does not exist: {skip_list}")
    download_only = bool(cfg.pipeline.get("download_only", False))
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
        do_report(start_dt, end_dt, direction, grib_dir, grib_template, status_log,
                  download_only=download_only, wrfout_dir=wrfout_dir)
        return

    # backward walks from the NEWEST edge; forward from the OLDEST edge
    current_dt = end_dt if direction == "backward" else start_dt

    # Create directories
    for d in ([wrfout_dir, log_dir] if download_only else [wrfout_dir, grib_dir, log_dir]):
        os.makedirs(d, exist_ok=True)

    hpc_dir = os.path.join(project_dir, "hpc")
    driver_script = os.path.join(hpc_dir, "fetch_step.sh")
    convert_script = os.path.join(hpc_dir, "convert_step.sh")
    driver_log = cfg.paths.get("driver_log") or os.path.join(log_dir, "fetch_step_driver.log")
    stop_flag = cfg.paths.get("stop_flag") or os.path.join(log_dir, "fetch_step.stop")

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
        "ACCUM_REF_DIR": accum_ref_dir,
        "STATIC_REF_DIR": static_ref_dir,
        "PROJECT_DIR": project_dir,
        "DATAMOVER_HOST": cfg.datamover.host,
        "REMOTE_HOST": cfg.datamover.remote_host,
        "IDENTITY_FILE": cfg.datamover.identity_file,
        "SFTP_OPTS": cfg.datamover.sftp_opts,
        "BASE_2023": cfg.datamover.base_2023,
        "BASE_PRE2023": cfg.datamover.base_pre2023,
        "INIT_HOUR": str(cfg.datamover.init_hour),
        "LOG_DIR": log_dir,
        "STATUS_LOG": status_log,
        "SKIP_LIST": skip_list,
        "DRIVER_LOG": driver_log,
        "DRIVER_SCRIPT": driver_script,
        "CONVERT_SCRIPT": convert_script,
        "CONVERT_PARTITION": cfg.slurm.step_convert_partition,
        "CONVERT_WALLTIME": cfg.slurm.step_convert_walltime,
        "CONVERT_MEM": cfg.slurm.step_convert_mem,
        "CONVERT_ACCOUNT": convert_account,
        "STOP_FLAG": stop_flag,
        "MIN_WRFOUT_BYTES": str(MIN_WRFOUT_BYTES),
        "DOWNLOAD_ONLY": "1" if download_only else "0",
        "KEEP_WRFOUT": "1" if cfg.pipeline.get("keep_wrfout", False) else "0",
        "MAX_QUEUED_CONVERTS": str(int(cfg.batch.get("max_queued_converts", 0))),
        "DRY_RUN": "1" if dry_run else "0",
    }
    run_env = {**os.environ, **driver_env}

    if dry_run:
        # Preview locally without network: run the driver directly (DRY_RUN=1) to
        # show the planned fetch/convert and the detached respawn for the next batch.
        print(f"DRY RUN — would launch the driver on this login node ({socket.gethostname()})")
        print(f"  bash {driver_script}   (detached, logs -> {driver_log})")
        if skip_list:
            print(f"  skip-list: {skip_list}")
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

    # Launch the driver detached on THIS login node (survives logout); it sftp's via
    # the datamover, sbatch's converts to dcgp_usr_prod, and respawns itself.
    os.makedirs(log_dir, exist_ok=True)
    logf = open(driver_log, "ab")
    # Respawn from a SNAPSHOT of the driver, not from the repo copy. The chain
    # re-execs the script from disk every ~18 min, so editing hpc/fetch_step.sh while
    # a chain is live swaps its code underneath it -- and a non-atomic rewrite caught
    # mid-respawn kills the chain outright (that is exactly how the 2024 window died
    # on 2026-09-07, after 22 files). The snapshot makes a live chain immune to edits.
    snapshot = os.path.join(
        log_dir, f".driver_{os.path.basename(driver_log).removesuffix('.log')}_"
                 f"{datetime.now():%Y%m%d%H%M%S}.sh")
    tmp = snapshot + ".tmp"
    shutil.copy2(driver_script, tmp)
    os.replace(tmp, snapshot)          # atomic: a respawn never sees a partial file
    run_env["DRIVER_SCRIPT"] = snapshot
    print(f"Driver snapshot: {snapshot}")

    proc = subprocess.Popen(
        ["bash", snapshot],
        env=run_env, cwd=project_dir,
        stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Fetch driver launched on login node {host} (pid {proc.pid})")
    print(f"Window: {start_dt}..{end_dt}  direction={direction}  start={current_dt}  "
          f"(batch<={cfg.batch.size}, parallel={cfg.batch.fetch_parallel}, "
          f"budget={cfg.pipeline.driver_max_seconds}s/process)")
    if skip_list:
        print(f"Skip-list:     {skip_list}")
    print(f"Driver log:    {driver_log}")
    print(f"Status ledger: {status_log}")
    if download_only:
        print(f"Mode:          DOWNLOAD_ONLY - no convert, wrfout kept in {wrfout_dir}")
    else:
        print(f"Converts:      squeue -u $USER   (dcgp_usr_prod, account {convert_account})")
    # The stop flag is the per-chain control and works from any login node; pkill only
    # reaches the node the chain happens to live on, and hits every chain at once.
    print(f"Stop the chain with:  touch {stop_flag}    (rm it to resume; the run is re-entrant)")


if __name__ == "__main__":
    app()
