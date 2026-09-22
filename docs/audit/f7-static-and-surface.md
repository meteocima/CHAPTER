# Family 7: static fields and surface characteristics

The fifteen fields that describe the surface rather than the weather over it:
`cvl` `cvh` `tvl` `tvh` `slt` `cl` `dl` `al` `fal` `lsm` `sdor` `slor` `z` `sst` `ci`.

Measured over the whole 34-timestep sample. The harness rows are
`$WORK/CHAPTER/audit_rows/rows_*.jsonl`; the four measurements it cannot make —
invariance across timesteps, the sea-ice motion, geo_em as an independent
source, and the joint distribution against ERA5 — are in
`tools/audit/f7_static.py`, `f7_probe.py`, `f7_water.py`, `f7_albedo.py` and
`f7_albedo_april.py`, with their output beside the rows.

**Twelve of the fifteen are verified.** Three carry a defect, and the three are
one defect: the archive has a single water mask where three different ones are
needed.

## The table

| variable | paramId | leg A | leg B | leg C (ERA5) | verdict |
|---|---|---|---|---|---|
| `z` (surface) | 129 | ok | exact | bias 5.13 m²/s² = 0.52 m, corr 0.992 | **verified** |
| `lsm` | 172 | ok | exact | bias 0.0019, corr 0.993 | **verified** |
| `sdor` | 160 | ok | exact | ratio 0.244, see below | **verified** |
| `slor` | 163 | ok | not available | ratio 0.93, but see below | **verified, different quantity** |
| `cvl` | 27 | ok | exact | bias +0.060, corr 0.778 | **verified** |
| `cvh` | 28 | ok | exact | bias −0.064, corr 0.700 | **verified** |
| `tvl` | 29 | ok | exact | 71.7 % same class | **verified** |
| `tvh` | 30 | ok | exact | 42.7 % same class, see below | **verified** |
| `slt` | 43 | ok | exact | 68.7 % same class | **verified** |
| `cl` | 26 | ok | exact | ratio 2.55, corr 0.31 | **wrong** ([#36](https://github.com/meteocima/CHAPTER/issues/36)) |
| `dl` | 228007 | ok | exact | bias −208 m, corr −0.014 | **wrong** ([#36](https://github.com/meteocima/CHAPTER/issues/36)) |
| `al` | 174 | ok | exact | ERA5 does not publish it | **verified, documented wrongly** ([#37](https://github.com/meteocima/CHAPTER/issues/37)) |
| `fal` | 243 | ok | not available | bias −0.010, corr 0.935 | **verified** |
| `sst` | 34 | ok | exact | bias −0.065 K, corr 0.992 | **wrong** ([#36](https://github.com/meteocima/CHAPTER/issues/36)) |
| `ci` | 31 | **1 failure** | exact | ratio 0.485 | **wrong** ([#34](https://github.com/meteocima/CHAPTER/issues/34)), and see below |

## Claim A: the seven static fields are invariant. Verified, to exactly zero

`cvl` `cvh` `tvl` `tvh` `slt` `cl` `dl` are read once from the geo_em sidecar and
asserted invariant across the archive. Every message was decoded at all 34
timesteps and compared against the first, 2019-07-15T00:

| | points that ever differ | largest difference |
|---|---|---|
| `cvl` `cvh` `tvl` `tvh` `slt` `cl` `dl` | **0** | **0** |

Not "within rounding": bitwise identical, across six years, both hemispheres of
the seasonal cycle, and the two 2025 months. The bitmaps do not move either.

Three fields the converter recomputes from the wrfout at every single timestep
are **also** exactly invariant, which is worth more than the seven because
nothing forced them to be: `z` (surface), `sdor` and `slor`, 0 differing points
over the whole sample.

## Claim B: `lsm` and `al` move, and only where the sea ice does

Half verified, and the half that fails is the more interesting one.

**`lsm` is exactly right.** It moves at 14 of the 34 timesteps, 5627 distinct
points over the sample, and at every one of those timesteps:

| | |
|---|---|
| points where `lsm` changed but `SEAICE` = 0 | **0** |
| points where `SEAICE` > 0 but `lsm` did not change | **0** |

At all fourteen. January 3225, February 5259, March 2146, April 591, December
1463, and the two 2025 months 1519 and 2735 — each count is exactly that
timestep's sea-ice count, in both directions. `ci` moves at the same points at
the same timesteps, so `lsm & ~(ci > 0)` recovers ERA5's permanent mask exactly,
as `CHAPTER_VARIABLES.md` §4 claims.

**`al` moves over the whole of land.** 1 171 937 land points, 89.9 % of the land
mask, at every winter timestep — not the 2469 sea-ice points `CLAUDE.md`
describes. The claim on file is not merely incomplete, and the reason it is
wrong is instructive: the measurement behind it compared 2019-06 against
2024-07, **two summer files**. This is the same failure the seasonal sample was
built to catch, and the third time on this repo that a summer-only comparison
has produced a wrong statement about a seasonal field.

What `al` actually is, read off the tables rather than inferred:

| winter → summer | points | LANDUSE.TBL `MODIFIED_IGBP_MODIS_NOAH` |
|---|---|---|
| 0.20 → 0.17 | 497 649 | 12 Croplands, WINTER 20 / SUMMER 17 |
| 0.23 → 0.25 | 369 219 | 16 Barren or Sparsely Vegetated, 23 / 25 |
| 0.14 → 0.13 | 174 349 | 5 Mixed Forests, 14 / 13 |
| 0.22 → 0.20 | 87 834 | 7 Open Shrublands, 22 / 20 |
| 0.23 → 0.19 | 29 748 | 10 Grasslands, 23 / 19 |
| 0.17 → 0.16 | 12 913 | 4 Deciduous Broadleaf Forest, 17 / 16 |
| 0.70 → 0.55 | 174 | 15 Snow and Ice, 70 / 55 |
| 0.15 → 0.14 | 51 | 3 Deciduous Needleleaf Forest, 15 / 14 |
| unchanged | 132 172 | 1, 2 (12/12), 6, 8 (22/22), 9 (20/20), 13, 18–20 (15/15) |

Twelve transitions, twelve exact table rows, no residue. The switch is the
SUMMER block from April to October and the WINTER block from November to March
(April matches July to 1e-6 on 1 305 664 of 1 306 255 land points, the remainder
being that day's sea ice), and it does not move within a day: 00Z and 12Z of
2024-07-15 are bitwise identical.

Off land, `al` is 0.08 on water — LANDUSE.TBL class 17, both seasons — and
**0.65 on sea ice**, which is WRF's `seaice_albedo_default` and follows from
`SEAICE_ALBEDO_OPT = 0` in the namelist.

### This corrects a closed ticket

`docs/audit/run-configuration.md` §j, from
[Read the run's configuration](https://github.com/meteocima/CHAPTER/issues/12),
says `ALBBCK` is "the `MODI-RUC` `ALBEDO` column by dominant category — no
seasonal cycle from observation". The second half is true and the first is not:
VEGPARM's `MODI-RUC` column gives 0.18 for croplands and 0.18 **never occurs in
the archive**, while LANDUSE.TBL's 0.17 and 0.20 both do, on half a million
points each. The source is LANDUSE.TBL, and the phrase "no seasonal cycle from
observation" reads as "no seasonal cycle", which is how it got into `CLAUDE.md`.
Filed as [#37](https://github.com/meteocima/CHAPTER/issues/37).

## geo_em as an independent source, not the sidecar

Leg B compares these fields against the sidecar the converter itself read, so it
can only catch the encoder. The crosswalk that *built* the sidecar — the
LANDUSEF sums, code table 4.234, the FAO thresholds — is untested until it is
recomputed from geo_em. Restated here from the rule sentences rather than copied
from `static_ref.py`:

| | agreement |
|---|---|
| `z` against the wrfout's `HGT` × 9.80665 | 2e-4 m²/s², i.e. exact in float32 |
| `z` against geo_em's `HGT_M` × 9.80665 | rms 8.24 m of height — real.exe's terrain adjustment, and the published field is the **model's** orography, which is the right one |
| `lsm` against geo_em `LANDMASK` (ice-free timestep) | **0 differing points** |
| `sdor` against √`VAR_SSO`, geo_em and wrfout alike | 1.5e-5 m |
| `cvl`, `cvh` against the `LANDUSEF` sums | 8.6e-8 |
| `tvl`, `tvh` against code table 4.234 | **0 differing points** |
| `cl`, `dl` against `LANDUSEF[21]` and `LAKE_DEPTH` | 6e-8 |
| `slt` against the FAO thresholds | 3926 of 1 304 109 land points |

The 3926 are worth the sentence they cost. 3924 of them sit at `CLAYFRAC` =
34.999999 and 2 at 17.999999 — float32 for 35 % and 18 %, the two thresholds
themselves. `static_ref.py` rounds to four decimals before applying the rule and
so reads them as 35 and 18; the naive restatement does not. **The published
value is the right one**, and 0.30 % of land points depend on that rounding.

Every count `CLAUDE.md` quotes for this family is confirmed exactly: 1 304 109
land points, 124 672 `tvl` cells masked for shrubland, 88 785 lake cells, 19 309
of them on land, and 233 844 land cells (17.93 %) carrying both high and low
vegetation above 5 %. `cvl + cvh` never exceeds 1 (max 1.0000001, float32) and
averages 0.696 on land.

## The one defect, wearing three names

`lsm` separates land from water. Nothing in the archive separates **ocean** from
**inland water**, and three published fields need that distinction.

### `cl` and `dl`: the Black Sea is published as a lake, 10 m deep

`cl` is geo_em's `LANDUSEF` fraction of MODIS class 21, and WPS's lake class
covers the Black Sea:

| | ours | ERA5 |
|---|---|---|
| open Black Sea, 41.5–45.5 N 30–40 E | `cl` = 0.993 mean, 48 313 cells at ≥ 0.999 | `cl` = 0.0001 mean, max 0.02 |
| `dl` on the same water | **10.0 m** on 49 511 of 49 662 cells | 1603 m mean, max **2209.8 m** |

2209.8 m is the real maximum depth of the Black Sea to within a few metres. 10 m
is the WPS default fill. The Sea of Azov (4702 cells) and part of the Baltic
(3013 cells) go the same way; together they are 89 % of the 55 881 cells the
archive calls fully lake, and they account for the whole of `cl`'s 2.55 ratio
against ERA5 and for `dl`'s correlation of −0.014.

`dl`'s wider weakness is already on file and confirmed: 89.5 % of its 88 785
cells carry the 10 m default, 2564 distinct values in all. But being a poor
field where it is a lake is a different thing from naming a sea a lake.

### `sst`: published on lakes, 19 K below the freezing point of seawater

`sst` is masked by `lsm` alone, so every inland water body carries one:

| timestep | points below 271.35 K | of which `cl` > 0.5 | minimum | carrying the ice flag |
|---|---|---|---|---|
| 2024-01-15T12 | 4856 | 4254 | 258.1 K | **0** |
| 2024-02-15T12 | 1843 | 1618 | **252.3 K** | **0** |
| 2025-02-15T12 | 5957 | 5286 | 262.7 K | **0** |
| 2024-07-15T12 | 0 | — | 283.1 K | — |

271.35 K is the freezing point of seawater at 35 PSU. A user reading `sst` and
filtering on nothing else gets a sea surface at 252 K, with `ci` = 0 beside it.
The values are not wrong for what they are — the model's water skin temperature
over a frozen inland lake — they are wrong for the parameter they are published
under.

Filed together as [#36](https://github.com/meteocima/CHAPTER/issues/36): one
mask would fix all three.

### `sst` is otherwise exactly as claimed

Constant within the 24 h run — 00, 06, 12 and 18Z of 2024-07-15 are **bitwise
identical**, `SST_UPDATE = 0` — and masked on exactly the 1 304 109 land points.

### `ci` is a flag, not a fraction

Two distinct values in the whole domain, 0 and 1, and the wrfout's `SEAICE` is
the same two. That follows from `FRACTIONAL_SEAICE = 0`, already established in
[#12](https://github.com/meteocima/CHAPTER/issues/12): the model knows only
whether a cell is ice. Published under paramId 31, *Sea ice area fraction*.

At 3 km a binary cell is a defensible fraction and upscaling recovers a real
one, so this is not a value defect — but it explains the leg C ratio of 0.485
without appeal to any error: our threshold discards every ERA5 cell whose ice
fraction is below a half, and this domain reaches only 60 N, where the marginal
ice zone is most of the ice there is. It is also the field of
[#34](https://github.com/meteocima/CHAPTER/issues/34), written as zeros over
land while `sst`, on the same mask, is bitmapped.

## What leg C can and cannot settle for this family

### `sdor`: the ratio is the scale, and it is the right one

Ours is 0.244 of ERA5's in the median, 8.4 m against 38.1 m in the mean. That is
not a disagreement: both are the standard deviation of the orography *within a
grid cell*, and the cells are 3 km and 31 km. For terrain with a Hurst exponent
H, σ scales as L^H, and 0.2436 = (3/31)^0.605 — H = 0.605, inside the 0.5–0.7
range topography is observed to have. The log-correlation is 0.80. The parameter
is the ERA5 one, evaluated on our grid; a user must not compare the numbers
across the two archives without rescaling.

### `slor`: the agreement is a coincidence, and the difference is invisible

`slor` is published as |∇z| of the resolved 3 km terrain, while paramId 163 is
defined as the slope of the **sub-grid** orography. `CHAPTER_VARIABLES.md` §4
declares this, and the registry's `long_name` says "(resolved, 3 km)". Leg C
gives a ratio of medians of 0.93 and a correlation of 0.918 — and **none of that
is evidence**, because the two quantities are not the same one; at these two
scales they merely happen to have similar magnitudes.

What matters for a user is that the declaration lives in our documentation and
in a `long_name` eccodes does not show: read the message, and it says *Slope of
sub-gridscale orography*. Recorded in [#37](https://github.com/meteocima/CHAPTER/issues/37).

### `tvh`'s 42.7 % is a land-cover difference, not a crosswalk error

The confusion matrix separates the two, which the agreement rate cannot:

| our class | cells | where ERA5 puts them |
|---|---|---|
| 0, no high vegetation | 16 587 | 0 (7998), **19 interrupted forest (7555)** |
| 18 mixed forest/woodland | 3558 | **19 (2929)**, 3 (362), 18 (129) |
| 19 interrupted forest | 757 | 19 (673) |
| 3 evergreen needleleaf | 686 | 3 (512) |

Two facts do the work. ERA5 uses class 19 on 53 % of land cells and class 18 on
0.8 %, so a MODIS *Mixed Forest* mapped to 18 — a semantic identity in code
table 4.234 — is bound to disagree with an ERA5 that hardly uses 18. And where
we say there is no high vegetation at all, ERA5 often says sparse interrupted
forest. Both are the underlying land-cover datasets disagreeing, MODIS against
ECMWF's own; our crosswalk rows are not implicated. Where we and ERA5 both name
a forest, we agree: 3 → 3 on 75 %, 19 → 19 on 89 %.

`tvl` behaves the same way: 1 → 1 on 94 % of 9893 cells, and the bulk of the
disagreement is our 0 (barren, no low vegetation) against ERA5's 11 (semidesert),
a class our crosswalk deliberately has no row for.

`slt`'s 68.7 % is 2 → 2 on 72 % of 18 092 cells, with the residue one class away
(3, medium fine) — two soil databases read through the same FAO thresholds.

### `cvl`/`cvh` and the coastal cells

17 876 sea points carry a non-zero `cvl + cvh`, never above 0.5, 94 % of them
adjacent to land. These are cells whose *dominant* class is water but which hold
real vegetation fraction — exactly the information `geo_em` was recovered for.
ERA5, whose `lsm` is itself fractional, does the same. A note, not a defect.

### `fal`

Entirely missing at 16 of the 17 00Z timesteps, the exception being
2024-06-15T00 when the domain's north-east corner is in daylight — the same
finding the dead-field census reached from the other side. That is the bitmap
doing its job, not an empty field. Against ERA5, bias −0.010 and correlation
0.935. The difference to state is that ours is the model's own flux ratio
`SWUPB/SWDNB` above 50 W/m² of incoming shortwave, so it carries the zenith-angle
dependence of that hour and is undefined at night, where ERA5's `fal` is defined
everywhere.

### `al` has no ERA5 counterpart, and the reason is the right kind

`tools/audit/era5_crosswalk.py` records it as "no background albedo; four
spectral albedos, `snow_albedo` and `fal` instead". That is a claim about what
ERA5 *publishes*, not about what ECMWF *defines* — paramId 174 exists and is
`Albedo (climatological)`. This is the distinction
[#17](https://github.com/meteocima/CHAPTER/issues/17) found four reasons failing;
this one passes it. The verdict rests on legs A and B and on the table above.

## What this family contaminates

- **[#12](https://github.com/meteocima/CHAPTER/issues/12)'s reading of `ALBBCK`**
  is wrong on the table it names. `docs/audit/run-configuration.md` §j, [#37](https://github.com/meteocima/CHAPTER/issues/37).
- **No other family ticket.** `sst` and `ci` appear in family 7's ticket and not
  in family 8's, so nothing is measured twice — note that the harness's own
  `FAMILIES` table disagrees with the tickets and puts them in 8. The tickets
  partition the ninety; the table does not.
- **Family 6** shares the moving mask: `swvl1-4` and `stl1-4` follow the hourly
  `lsm`, which is verified here to move exactly with the sea ice. That is a
  result family 6 can use rather than re-measure.
