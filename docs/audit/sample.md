# The audit sample

The fixture every ticket of the variable audit measures. Thirty-four timesteps,
staged as wrfout and converted to GRIB2 at the current 246-message schema, kept on
disk for the duration of the audit.

Its point is comparability. Two tickets that measure different files can disagree
without either being wrong, and there is then no way to tell which. A ticket that
needs a date outside the sample adds it and says why.

## What the sample is

Three axes, each answering a question a single timestep cannot.

| axis | what it separates | timesteps |
|---|---|---|
| seasonal | a dead field from a seasonally-zero one; snow, sea ice, the radiation range | the 15th of each month of 2024 at 00Z and 12Z (24) |
| interannual | a physical signal from a code artefact | 2019-07-15 and 2019-08-15 against their 2024 twins, 2025-01-15 and 2025-02-15 against theirs (8) |
| diurnal | radiation, accumulations, the `skt` and `2t` cycle | 2024-07-15 also at 06Z and 18Z (2) |

The 15th every month, with no substitutions: every date asked for was present at
the source.

00Z is never optional. Accumulated variables are referred to 00Z of the same day,
so a 12Z cannot be converted at all without its day's 00Z — which is why the
seasonal axis is a pair per month rather than a single midday hour, and why the
sample is 34 timesteps and not 22.

The interannual pairs are 2019-07-15 / 2024-07-15, 2019-08-15 / 2024-08-15,
2025-01-15 / 2024-01-15 and 2025-02-15 / 2024-02-15: same month, same hour,
different year, so anything that moves is either weather or the code.

## Where it lives

| what | where |
|---|---|
| wrfout | `$WORK/CHAPTER/wrfout_audit/<date>/wrfout_d02_<date>_<hh>:00:00` |
| GRIB2 | `$WORK/CHAPTER/grib_audit/<yyyy>/<mm>/` |
| accumulation sidecars | `$WORK/CHAPTER/accum_ref_v2/` (shared with the archive) |
| static sidecar | `$WORK/CHAPTER/static_v1/chapter_static_d02.npz` (shared) |
| ledger | `$WORK/CHAPTER/logs/audit_sample_status.log` |
| driver log | `$WORK/CHAPTER/logs/audit_sample_driver.log` |
| stop flag | `$WORK/CHAPTER/logs/audit_sample.stop` |
| the script | `tools/audit/stage_sample.sh` |

Thirteen of the thirty-four are **symlinks** into `wrfout_share` and
`wrfout_rebuild`, which already hold them; twenty-one were fetched from the relay.
The staging directory is therefore uniform to read and costs only what was
actually missing.

## Three decisions taken while staging

**The sample's GRIB does not go in `grib_v3`.** It gets `grib_audit`, a tree of its
own. `convert_step.sh` keys its re-entrancy on the **message count** of an existing
output (`hpc/grib_schema_ok.py`), not on its values: a file with 246 correct-count
but wrong-valued messages would be skipped by the rebuild campaign forever. Finding
exactly that kind of file is what the audit is for, so its output must not sit
where the campaign would inherit it. If the audit passes, the 34 files can be moved
across; if it does not, they are deleted with nothing else touched.

**Every path this effort touches is its own.** Staging directory, ledger, driver log
and stop flag, none shared with a campaign chain. The 2024-fill chains are paused,
not finished, and their stop flags are still posted: two chains sharing any of those
four collide, and a stop request meant for one would kill the other.

**The wrfout are kept.** `convert_step.sh` deletes its input on success; every
convert here runs with `KEEP_WRFOUT=1`. The sample is a fixture, and a ticket that
has to go back to the model level — comparing a GRIB message against the wrfout
field it came from is the audit's core measurement — needs the input still there.

## A correction to the ticket

The ticket said 2019-06..09, 2024-02, 2024-03 and 2024-06..09 were already local
and only about 16 files needed fetching. Measured, the local inventory is smaller:
the date directories of 2024-01, 2024-09-13..30 and the whole of 2024-10 exist but
are **empty** — the rebuild chain converted them and deleted the wrfout — 2024-06
starts at the 18th, not the 1st, and 2024-03-15 has hours 04..23 only, so it has no
00Z. Twenty-one files had to be fetched, not sixteen.

The lesson is narrow but worth writing down: on this filesystem **a date directory
existing says nothing about the wrfout being there**. Check the file, and its size.

## Cost

<!-- filled on completion -->

## The timestep list

<!-- filled on completion -->
