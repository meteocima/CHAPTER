# The ERA5 comparison set

The audit asks, of every variable, whether the WRF quantity **is** the ERA5 one.
Half of that question is answered by the parameter table and half only by the
data, and this file is about getting the data onto disk so the second half can
be asked at all.

It records four things: what ERA5 turns out to carry of our ninety, what it does
not, the step convention its accumulated fields arrive in, and where the files
live.

Companion to [the audit sample](sample.md), which fixes the timesteps. Nothing
here compares anything; the comparison is the harness ticket's job.

## What ERA5 carries of our ninety

**Eighty of the ninety.** Measured against the `variable` widget of the two CDS
collection forms, not against a table we typed out: `tools/audit/era5_crosswalk.py`
holds the crosswalk and re-reads the live catalogue to check itself, so a name
that changes or an absence that stops being true is a failure and not a silence.

| | of 90 |
|---|---|
| pressure level, carried | 12 of our 13 |
| single level, carried | 68 of our 77 |
| **not carried** | **10** |

## The ten ERA5 does not carry

This is a result, not an obstacle. Publishing a paramId that ERA5 *defines* but
never populates is a different kind of claim from matching a field it publishes,
and these ten can never be validated against ERA5 whatever the harness does.
The right-hand column is what CDS offers in the neighbourhood, so that a family
ticket knows whether it has a control or nothing at all.

| ours | paramId | where | what ERA5 has instead |
|---|---|---|---|
| `wz` | 260238 | pressure | nothing: only `w` in Pa/s. The m/s convention is ours alone |
| `2r` | 260242 | single | nothing published; derivable from `2t` and `2d` |
| `200u` | 228239 | single | winds at 10 m and 100 m only |
| `200v` | 228240 | single | winds at 10 m and 100 m only |
| `vwsh` | 260068 | single | no vertical speed shear at any level |
| `mucape` | 228235 | single | `cape` (59), the **surface** parcel, not the most unstable one |
| `mucin` | 228236 | single | `cin` (228001), likewise surface-parcel |
| `al` | 174 | single | no background albedo; four spectral albedos, `asn` and `fal` |
| `snowc` | 260038 | single | no snow cover fraction in ERA5 single levels |
| `tirf` | 235015 | single | no time-integral of rain flux; `lsp` is the nearest |

Two of these deserve a line of their own, because the gap is not the same size
in each case.

`mucape`/`mucin` are the sharpest: ERA5 has a CAPE and a CIN, with a paramId
each, and they are **not** ours. A comparison that lines up `mucape` against
`cape` and reports a bias is measuring the difference between two parcel
choices, not an error in our converter. The surface-parcel pair is retrieved as
a control precisely so that the difference can be shown to be that and nothing
else.

`al` is the opposite shape: we publish paramId 174 from `ALBBCK`, and ERA5
simply has no 174. Whatever `al` is validated against, it will not be a field of
the same name.

## Eleven controls, retrieved alongside

Not part of the ninety, one extra field per timestep each, and each of them the
nearest ERA5 quantity to something we either refuse to publish or publish from a
different definition. They are on disk so that a family ticket has its
comparison already there rather than coming back to CDS for it.

`cape` and `cin` (the surface parcel, against our most-unstable pair);
`instantaneous_10m_wind_gust` (the other gust convention, against our
resolved-wind `10fg`); `asn` (the albedo we do not publish, `SNOALB` being an
annual climatological cap); `lai_lv` and `lai_hv` (refused because the model
carries one LAI per cell and ERA5 wants one per class); `cp` and `csf` (what
`CU_PHYSICS=0` makes identically zero for us); `lsp` (the rain-only control
`tirf` would have been); `lsf` (against our `sf`, which has no convective part
to subtract); `smlt` (refused because `ACSNOM` is not monotone).

## The step convention, measured

The obvious way to get a factor wrong in this audit is to compare our
accumulation against ERA5's without checking what interval each covers. So it
was read off the GRIB keys of a probe retrieval rather than remembered:

```
tp    base=20240714T1800 step=5-6   valid=20240715T0000 stepType=accum
2t    base=20240715T0000 step=0     valid=20240715T0000 stepType=instant
tp    base=20240714T1800 step=6-7   valid=20240715T0100 stepType=accum
2t    base=20240715T0100 step=0     valid=20240715T0100 stepType=instant
tp    base=20240715T0600 step=5-6   valid=20240715T1200 stepType=accum
2t    base=20240715T1200 step=0     valid=20240715T1200 stepType=instant
```

**ERA5 accumulates over one hour, the hour ending at the validity time**, from a
forecast based at 06Z or 18Z, and encodes it as a one-hour step range against
that base. Instantaneous fields carry base = validity and step 0.

Ours are accumulated **since 00Z of the same day**. The two are reconciled by a
sum and nothing else:

> ERA5's 00Z-referred accumulation at hour *H* of a day is the sum of its hourly
> values valid at 01Z, 02Z, ..., *H*Z of that same day.

With one trap in it. ERA5's message stamped 00Z is the hour *23Z → 00Z of the
previous day*: it belongs to the day before and must be left out of the sum.
Our own 00Z value is exactly zero by construction, so at 00Z there is nothing to
compare, and the smallest hour at which the comparison means anything is 01Z.

This is why the single-level retrieval takes **all twenty-four hours of each
sample date** although only two or four of them are sample timesteps: the sum
needs the whole run-up. The pressure levels are instantaneous throughout, so
only the sample hours are retrieved.

### What the retrieved files actually say

The probe settled `tp`; the first full day settles the rest. Read back from
`era5_sl_20190715.grib`, 1896 messages, 79 parameters, 24 hours:

- **Every accumulated field carries a one-hour range**, `0-1` through `11-12`,
  twelve ranges per base and two bases a day. The convention is uniform across
  `tp`, `sf`, `sro`, `ssro`, `ro`, the whole radiation set and the controls —
  there is no field that quietly accumulates over something else.
- **`10fg` arrives as `stepType=max` over `0-1`..`11-12`**: a one-hour maximum,
  exactly the interval and the statistic we encode. It is the one accumulated
  variable that needs **no sum at all**, and the only one our convention already
  agrees with.
- **Not every instantaneous field comes from the analysis.** `cin`, `zust` and
  the control `i10fg` carry `stepRange` 1..12 rather than 0: they are forecast
  fields, instantaneous at their validity time but stamped against the 06Z/18Z
  base like the accumulations. Index on validity, never on `dataTime` — the same
  rule our own archive needs, for the same reason.
- **ERA5 from CDS is GRIB edition 1.** Ours is edition 2, and CDS offers only
  `grib` or `netcdf` — there is no GRIB2 to ask for. The two archives therefore
  encode the same parameter on different levels, and the differences are not
  cosmetic:

  | | ERA5 (edition 1) | CHAPTER (edition 2) |
  |---|---|---|
  | `2t`, `2d`, `10u`, `10v`, `10fg`, `100u`, `100v` | `surface`, level 0 | `heightAboveGround`, level 2 or 10 |
  | `stl1..4`, `swvl1..4` | `depthBelowLandLayer`, level 0 / 7 / 28 / 100 (the layer top, cm) | `surface`, level 0 |
  | packing | `grid_simple` | `grid_ccsds` |

  **The harness has to match on `paramId`**, not on level type and level. A
  match keyed on the level would find nothing for fifteen variables and would
  report the absence as a defect.
- Every paramId came back as the one we publish under. No surprises there: 167
  for `2t`, 235 for `skt`, 228 for `tp`, and so on down the list.

`10fg` aside, ours are accumulated since 00Z and ERA5's hourly, so the sum above
is what every other accumulated comparison has to go through.

## Where it lives

| what | where |
|---|---|
| single level | `$WORK/CHAPTER/era5_audit/sl/era5_sl_<yyyymmdd>.grib` |
| pressure level | `$WORK/CHAPTER/era5_audit/pl/era5_pl_<yyyymmdd>.grib` |
| driver log | `$WORK/CHAPTER/logs/era5_audit_fetch.log` |
| lock | `$WORK/CHAPTER/era5_audit/.fetch_era5.lock` |
| the crosswalk | `tools/audit/era5_crosswalk.py` |
| the retrieval | `tools/audit/fetch_era5.py` |
| the reader | `tools/audit/era5_inventory.py` |

One file per date per product, sixteen dates. The retrieval is re-entrant: a
target that already exists at a plausible size is skipped, so a queue timeout
costs a re-run and nothing else.

**Grid and box.** 0.25 degrees, ERA5's own archived resolution — ask for it
explicitly and the server ships the archived field, ask for anything else and it
interpolates. The box is `60.25 / -20.25 / 23.25 / 42.50` (N/W/S/E), the CHAPTER
domain rounded *outward* by a cell so that every WRF point has ERA5 neighbours
on all sides and no comparison has to extrapolate at the edge. The corners were
read off a sample GRIB rather than taken from the ticket: 23.4719..60.0006 N,
-19.9722..42.2555 E, and the box clears all four. What comes back is
`regular_ll`, **252 x 149** points.

**Not the colleague's tree.** There are ERA5 files in
`/leonardo_work/AIFPT_AILAMIT/datasets/era5/n320/`, built for Anemoi, and they
are the wrong ones for this. Read off their headers: `reduced_gg` N320 (542080
points) rather than a lat/lon box, 6-hourly, and **fifteen** of our ninety
variables — seven at the surface (`2t`, `2d`, `10u`, `10v`, `msl`, `sp`, `skt`),
five on pressure levels (`t`, `q`, `u`, `v`, `z`) over **twelve levels with no
600 hPa**, `tp` in a separate forecast stream, and `lsm`/`z` in a constants
file. They also start at 2024-04, so the 2019 and 2024-01..03 thirds of the
sample are simply not there. Re-retrieving costs a couple of gigabytes and
removes a dependency on a tree we do not own.

## Where `cdsapi` lives, and why not in the venv

`tools/audit/fetch_era5.py` declares `cdsapi` in a PEP 723 inline block and is
run with `uv run --no-project`, which builds a throwaway environment from it.

The shared `.venv` is read by every compute node on every convert job, and
`CLAUDE.md` already argues one dependency into it on the grounds that a test
nobody runs costs more than its megabytes. That argument does not transfer here:
nothing in the pipeline imports `cdsapi`, no compute node will ever reach for
it, and it is used by hand on a login node for one retrieval. A dependency group
would have the same effect on the venv as adding it outright, since `uv sync`
installs the default groups. Declaring it in the file that uses it keeps the
version pinned next to the code and reaches nothing else.

## A licence had to be accepted

The first retrieval returned `403 required licences not accepted`. The account
had `terms-of-use-cds` and the privacy statement, and ERA5 additionally requires
the licence the collection's own metadata names — which is **`cc-by` revision 1**
(CC-BY-4.0), not the `licence-to-use-copernicus-products` that the error
message's link points at. Both are now accepted on the account, with the user's
go-ahead. Worth recording because the error text sends you to the wrong licence
and the right one is only visible in the collection JSON's `links` array.
