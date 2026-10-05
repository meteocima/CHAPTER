"""The archive -> Anemoi dataset step, end to end on three real timesteps.

The production recipe (`wrf_anemoi_recipe.yaml`) is built with `anemoi-datasets create`
over 2024-07-01T23..07-02T01, and the dataset that comes out is compared against the
GRIB files read directly with eccodes. The window straddles 00Z on purpose: the
accumulated variables change reference time there, and are exactly zero at 00Z.

The recipe is used as shipped except for two keys. `dates` is narrowed to the window,
and `statistics` is widened to all three dates: anemoi's default statistics window is
the first 80% of the dates, here 23Z and 00Z, both night, and `fal` is missing on every
point at night, so it would have no sample. A real period always holds daylight. The
lists the test needs from the recipe (forcings, variables allowed to hold NaN, the GRIB
path) are read from it rather than copied, so this tests the recipe that will build the
real dataset and not a copy of it.

The build reads ~2.2 GB of GRIB and writes a multi-GB zarr, far past the login node's
600 s CPU limit, so the test is opt-in: `tools/run_anemoi_test.sh` submits it as a SLURM
job in the `anemoi/` environment (anemoi-datasets 0.5.45; anemoi/pyproject.toml says why
it is separate) and sets CHAPTER_ANEMOI_TEST_DIR, where the dataset is kept. A re-run
reuses the dataset until the rendered recipe or one of the three GRIB files changes.
"""
import datetime
import hashlib
import os
import pathlib
import re
import subprocess
import sys

import numpy as np
import pytest
import yaml

import wrf_era5_comparison as registry

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECIPE = yaml.safe_load((ROOT / "wrf_anemoi_recipe.yaml").read_text())
DATES = [datetime.datetime(2024, 7, 1, 23) + datetime.timedelta(hours=h) for h in range(3)]
T00 = DATES.index(datetime.datetime(2024, 7, 2, 0))
T01 = DATES.index(datetime.datetime(2024, 7, 2, 1))
DATE_IDS = [d.strftime("%Y%m%dT%H") for d in DATES]

GRIB_SOURCE = RECIPE["input"]["join"][0]["grib"]
FORCINGS = set(RECIPE["input"]["join"][1]["forcings"]["param"])
ALLOW_NANS = set(RECIPE["statistics"]["allow_nans"])

pytestmark = pytest.mark.skipif(
    "CHAPTER_ANEMOI_TEST_DIR" not in os.environ,
    reason="builds a multi-GB dataset: run as a SLURM job via tools/run_anemoi_test.sh, "
           "which also selects the anemoi/ environment")


def grib_path(date):
    """The recipe's own path template, with anemoi's `{date:strftime(...)}` expanded."""
    return re.sub(r"\{date:strftime\(([^)]*)\)\}", lambda m: date.strftime(m.group(1)),
                  GRIB_SOURCE["path"])


def dataset_variable(short_name, level_type, level):
    """Anemoi's name for one GRIB message: `param_level` on pressure levels, the bare
    shortName everywhere else (the recipe's flavour drops the level there, and the level
    of a single-level variable is part of its shortName already: 2t, 100u)."""
    return f"{short_name}_{level}" if level_type == "isobaricInhPa" else short_name


def expected_dataset_variables():
    return {dataset_variable(row["shortName"], row["levelType"], level)
            for row in registry.WRF_TO_ECMWF_PARAMID.values() for level in row["levels"]}


@pytest.fixture(scope="module")
def dataset_path():
    recipe = dict(RECIPE)
    recipe["dates"] = {"start": DATES[0].isoformat(), "end": DATES[-1].isoformat(),
                       "frequency": "1h"}
    recipe["statistics"] = dict(RECIPE["statistics"], start=DATES[0].isoformat(),
                                end=DATES[-1].isoformat())
    text = yaml.safe_dump(recipe, sort_keys=False)
    inputs = [os.stat(grib_path(d)) for d in DATES]
    key = text + "".join(f"{s.st_size}:{s.st_mtime_ns}\n" for s in inputs)
    tag = hashlib.sha256(key.encode()).hexdigest()[:12]

    out_dir = pathlib.Path(os.environ["CHAPTER_ANEMOI_TEST_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    recipe_path = out_dir / f"recipe_{tag}.yaml"
    zarr = out_dir / f"ailam-an-cima-3km-2024-2024-1h-v1-test{tag}.zarr"
    # A failed build leaves a zarr behind, so reuse keys on a marker written only once
    # `create` has returned success, never on the zarr existing.
    built_marker = out_dir / f"{zarr.name}.built"
    if not built_marker.exists() or os.environ.get("CHAPTER_ANEMOI_REBUILD") == "1":
        built_marker.unlink(missing_ok=True)
        recipe_path.write_text(text)
        anemoi_datasets = pathlib.Path(sys.executable).parent / "anemoi-datasets"
        subprocess.run([str(anemoi_datasets), "create", "--overwrite", str(recipe_path), str(zarr)],
                       check=True)
        built_marker.touch()
    return zarr


@pytest.fixture(scope="module")
def ds(dataset_path):
    from anemoi.datasets import open_dataset
    return open_dataset(dataset_path)


def grib_messages(date):
    """(dataset variable, reference time, values) for every message of one archive file,
    decoded by eccodes itself, bitmap points as NaN. Every message must be valid at
    `date`: the file name alone does not prove it."""
    import eccodes

    def when(h, prefix):
        return datetime.datetime.strptime(
            f"{eccodes.codes_get(h, prefix + 'Date')}{eccodes.codes_get(h, prefix + 'Time'):04d}",
            "%Y%m%d%H%M")

    with open(grib_path(date), "rb") as f:
        while (h := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                name = dataset_variable(eccodes.codes_get(h, "shortName"),
                                        eccodes.codes_get(h, "typeOfLevel"),
                                        eccodes.codes_get(h, "level"))
                assert when(h, "validity") == date, f"{name} in {grib_path(date)}"
                values = eccodes.codes_get_values(h)
                if eccodes.codes_get(h, "bitmapPresent"):
                    values[eccodes.codes_get_array(h, "bitmap") == 0] = np.nan
                yield name, when(h, "data"), values
            finally:
                eccodes.codes_release(h)


def test_dataset_holds_exactly_the_requested_dates(ds):
    assert [d.astype("datetime64[s]").item() for d in ds.dates] == DATES


def test_every_grib_message_is_one_dataset_variable(ds):
    assert len(ds.variables) == len(set(ds.variables)), "duplicate variable names"
    assert set(ds.variables) == expected_dataset_variables() | FORCINGS
    assert len(ds.variables) == registry.EXPECTED_MESSAGES + len(FORCINGS)


@pytest.mark.parametrize("i_date", range(len(DATES)), ids=DATE_IDS)
def test_every_dataset_variable_equals_its_grib_message(ds, i_date):
    """Bit-identical in float32, NaN where the GRIB has a bitmap. Since every message is
    checked to be valid at the date it is compared at, this also proves that the
    messages whose reference time is not their validity (the accumulations, referred to
    00Z, and 10fg, referred to the previous hour) sit at their validity in the dataset."""
    index = {name: i for i, name in enumerate(ds.variables)}
    stored = ds[i_date][:, 0, :]
    seen, shifted = set(), set()
    for name, reference, values in grib_messages(DATES[i_date]):
        np.testing.assert_array_equal(stored[index[name]], values.astype(np.float32),
                                      err_msg=f"{name} at {DATES[i_date]}")
        seen.add(name)
        if reference != DATES[i_date]:
            shifted.add(name)
    assert seen == expected_dataset_variables()
    # The window has to exercise the shifted case, or the claim above is empty.
    if i_date == T01:
        assert {"tp", "10fg"} <= shifted, shifted


def test_accumulations_are_exactly_zero_at_00z_and_not_after(ds):
    names = sorted(row["shortName"] for row in registry.WRF_TO_ECMWF_PARAMID.values()
                   if row.get("stepType") == "accum")
    assert "tp" in names
    for name in names:
        assert np.all(ds[T00][ds.name_to_index[name], 0] == 0.0), f"{name} is not zero at 00Z"
    # 01Z holds the first hour of the day: precipitation and TOA insolation are not zero.
    for name in ("tp", "tisr"):
        assert np.nanmax(np.abs(ds[T01][ds.name_to_index[name], 0])) > 0.0, name


def test_grid_is_the_mercator_grid_eccodes_derives(ds):
    """Anemoi gets the coordinates through earthkit, which itself calls eccodes, so this
    is not an independent derivation: it catches a projection, ordering or flattening
    mismatch between the two, not an error in eccodes. Longitudes are compared modulo
    360, since the two may disagree on the convention without disagreeing on the point."""
    import eccodes
    with open(grib_path(DATES[0]), "rb") as f:
        h = eccodes.codes_grib_new_from_file(f)
        try:
            lat = eccodes.codes_get_array(h, "latitudes")
            lon = eccodes.codes_get_array(h, "longitudes")
        finally:
            eccodes.codes_release(h)
    assert ds.latitudes.shape == lat.shape
    np.testing.assert_allclose(ds.latitudes, lat, rtol=0, atol=1e-6)
    dlon = (ds.longitudes - lon + 180.0) % 360.0 - 180.0
    np.testing.assert_allclose(dlon, 0.0, rtol=0, atol=1e-6)


# Masked points per timestep, counted on the GRIB bitmaps of 2024-07-02T01, for the masks
# that do not depend on the weather (tsn, fal and mucin do). These are a second witness
# beside the GRIB: they fail if the archive's masks themselves change.
FIXED_MASKS = {"sst": 1317418, "ci": 1317418, "slt": 916164, "tvl": 124672, "dl": 2188273,
               **{f"swvl{k}": 916164 for k in range(1, 5)}, **{f"stl{k}": 916164 for k in range(1, 5)}}


@pytest.mark.parametrize("i_date", range(len(DATES)), ids=DATE_IDS)
def test_masked_points_stay_missing_not_zero(ds, i_date):
    stored = ds[i_date][:, 0, :]
    for name, count in FIXED_MASKS.items():
        assert np.isnan(stored[ds.name_to_index[name]]).sum() == count, name
    with_nans = {name for name in ds.variables if np.isnan(stored[ds.name_to_index[name]]).any()}
    assert with_nans <= ALLOW_NANS, f"NaNs outside allow_nans: {sorted(with_nans - ALLOW_NANS)}"


def test_statistics_are_finite_for_every_variable(ds):
    for key in ("mean", "stdev", "minimum", "maximum"):
        bad = [n for n, v in zip(ds.variables, ds.statistics[key]) if not np.isfinite(v)]
        assert not bad, f"non-finite {key} for {bad}"
