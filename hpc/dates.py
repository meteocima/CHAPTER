"""Date utilities for CHAPTER pipeline: target date -> SuperMUC run folder mapping."""

from datetime import date, timedelta


def get_run_folder(target_date: date, init_hour: int = 18) -> str:
    """Return the WRF run folder name for a given target date.

    CHAPTER runs start at init_hour (default 18Z) on the previous day,
    with 6 hours of spinoff before the target date begins.

    Example: target_date=2023-02-01 -> "2023013118" (init: 2023-01-31 18Z)
    """
    init_date = target_date - timedelta(days=1)
    return f"{init_date:%Y%m%d}{init_hour:02d}"


def get_supermuc_base(target_date: date, base_2023: str, base_pre2023: str) -> str:
    """Return the correct SuperMUC base path based on target year."""
    if target_date.year >= 2023:
        return base_2023
    return base_pre2023


def get_remote_run_path(target_date: date, base_2023: str, base_pre2023: str,
                        init_hour: int = 18) -> str:
    """Return full remote path to the run folder on SuperMUC."""
    base = get_supermuc_base(target_date, base_2023, base_pre2023)
    folder = get_run_folder(target_date, init_hour)
    return f"{base}/{folder}"
