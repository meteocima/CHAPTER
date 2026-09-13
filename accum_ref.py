#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
00Z reference for WRF accumulated variables.

WRF accumulates from the run initialisation. CHAPTER runs start at 18Z of the
previous day (6 h spinup), so RAINNC at 00Z of the target day already holds the
spinup precipitation. CHAPTER GRIBs store accumulations referred to 00Z of the
SAME day (same run):

    field(H) = WRF(H) - WRF(00Z same day)        -> field(00Z) == 0

The 00Z fields are kept in a small sidecar file (accum_ref_YYYYMMDD.npz, native
WRF units) so that convert jobs, which run independently and in any order, never
depend on the 00Z wrfout still being on disk. Invariant kept by the pipeline:
the 00Z wrfout is never deleted unless its sidecar exists.

CLI (used by hpc/fetch_step.sh on the login node):
    python accum_ref.py extract <wrfout_00Z> <ref_dir>
"""

import os
import sys
import tempfile
from datetime import datetime

import numpy as np

# WRF accumulated fields (accumulate from run init). Any of these that is in the
# GRIB mapping gets referred to 00Z of the same day.
ACCUMULATED_VARS = ['RAINNC', 'RAINC', 'ACSWDNB', 'ACLWDNB', 'ACHFX', 'ACLHF']

# GRIB1 marker on messages holding a 00Z-referred accumulation
# (default generatingProcessIdentifier of the GRIB1 sample is 127).
ACCUM_FROM_00Z_GENPROC = 128


def ref_path(ref_dir, target_date):
    """Sidecar path for a target date (datetime/date or 'YYYY-MM-DD')."""
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d')
    return os.path.join(ref_dir, f"{target_date:%Y}", f"{target_date:%m}",
                        f"accum_ref_{target_date:%Y%m%d}.npz")


def write_ref(path, fields, meta):
    """Atomically write the sidecar (unique tmp in the same dir + os.replace),
    so concurrent writers and readers never see a partial file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arrays = {f"var_{k}": np.asarray(v, dtype=np.float32) for k, v in fields.items()}
    arrays.update({f"meta_{k}": np.array(str(v)) for k, v in meta.items()})
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + '.', suffix='.tmp',
                               dir=os.path.dirname(path))
    try:
        os.chmod(tmp, 0o644)  # mkstemp creates 0600
        with os.fdopen(fd, 'wb') as fh:
            np.savez_compressed(fh, **arrays)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_ref(path):
    """Return (fields, meta) from a sidecar."""
    with np.load(path) as z:
        fields = {k[4:]: z[k] for k in z.files if k.startswith('var_')}
        meta = {k[5:]: str(z[k]) for k in z.files if k.startswith('meta_')}
    return fields, meta


def extract_from_wrfout(path):
    """Read every accumulated 2D field present (first time) + run metadata.
    All of them, not just the mapped ones, so a variable re-enabled later still
    finds its reference in sidecars written today."""
    from netCDF4 import Dataset
    with Dataset(path) as ds:
        fields = {v: np.ma.filled(ds.variables[v][0], np.nan).astype(np.float32)
                  for v in ACCUMULATED_VARS if v in ds.variables}
        meta = {
            'SIMULATION_START_DATE': ds.SIMULATION_START_DATE,
            'valid_time': ds.variables['Times'][0].tobytes().decode(),
            'source': 'wrfout',
            'source_path': path,
        }
    return fields, meta


def wrfout_00z_path(input_file, target_date):
    """Path of the 00Z wrfout of the same day, in the same directory as input_file."""
    return os.path.join(os.path.dirname(os.path.abspath(input_file)),
                        f"wrfout_d02_{target_date:%Y-%m-%d}_00:00:00")


def get_reference(input_file, target_date, var_names, sim_start, ref_dir=None):
    """Return the 00Z fields {var: array} for target_date, native WRF units.

    Lookup: sidecar -> 00Z wrfout next to input_file (materialised as sidecar when
    ref_dir is set) -> sidecar again (the 00Z convert may have written it and deleted
    the wrfout between our two checks) -> FileNotFoundError.
    sim_start: SIMULATION_START_DATE of the input, checked against the reference.
    """
    sidecar = ref_path(ref_dir, target_date) if ref_dir else None
    w00 = wrfout_00z_path(input_file, target_date)

    def from_sidecar():
        if sidecar and os.path.isfile(sidecar):
            fields, meta = load_ref(sidecar)
            return fields, meta, sidecar
        return None

    found = from_sidecar()
    if found is None and os.path.isfile(w00):
        try:
            fields, meta = extract_from_wrfout(w00)
            if sidecar and not os.path.isfile(sidecar):
                write_ref(sidecar, fields, meta)
            found = (fields, meta, w00)
        except (OSError, RuntimeError):
            found = None  # deleted/being deleted under us: fall through to sidecar
    if found is None:
        found = from_sidecar()
    if found is None:
        raise FileNotFoundError(
            f"00Z reference for accumulated fields not found for {target_date:%Y-%m-%d}.\n"
            f"  looked for sidecar: {sidecar or '(no --accum-ref-dir given)'}\n"
            f"  looked for wrfout : {w00}\n"
            f"  Accumulations must be referred to 00Z of the same day; refusing to write "
            f"run-init-referred values. Fetch the 00Z wrfout (or create the sidecar with "
            f"'python accum_ref.py extract <wrfout_00Z> <ref_dir>') and re-run.")

    fields, meta, src = found
    missing = [v for v in var_names if v not in fields]
    if missing:
        raise KeyError(f"00Z reference {src} lacks {missing}")
    ref_start = meta.get('SIMULATION_START_DATE')
    if ref_start and sim_start and ref_start != sim_start:
        raise ValueError(f"00Z reference {src} is from run {ref_start}, input is from run "
                         f"{sim_start}: not the same run")
    return {v: fields[v] for v in var_names}, src


def _cli(argv):
    if len(argv) != 3 or argv[0] != 'extract':
        print(__doc__)
        return 2
    wrfout, ref_dir = argv[1], argv[2]
    fields, meta = extract_from_wrfout(wrfout)
    valid = datetime.strptime(meta['valid_time'], '%Y-%m-%d_%H:%M:%S')
    if valid.hour != 0:
        print(f"ERROR: {wrfout} is {meta['valid_time']}, not a 00Z file", file=sys.stderr)
        return 1
    path = ref_path(ref_dir, valid)
    if os.path.isfile(path):
        print(f"exists: {path}")
        return 0
    write_ref(path, fields, meta)
    print(f"written: {path}")
    return 0


if __name__ == '__main__':
    sys.exit(_cli(sys.argv[1:]))
