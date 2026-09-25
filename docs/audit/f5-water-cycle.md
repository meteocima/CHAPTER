# Family 5: water-cycle accumulations and `10fg`

Seven fields: six accumulated since 00Z — `tp` `sf` `tirf` `ro` `sro` `ssro` —
and `10fg`, the one field in the archive with a different time convention.

Measured over the 34-timestep sample, plus **six whole days at hourly
resolution** that the sample does not contain. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl` (238 for this family); the measurements
the harness cannot make are `tools/audit/f5_water.py`, output beside the rows as
`f5_water.json`, `f5_controls.json`, `f5_extra.json` and `f5_reset.json`.

**Six of the seven are verified.** `10fg` is not: its message says a one-hour
maximum and on 12 per cent of hours it is a maximum over more than one hour
([#49](https://github.com/meteocima/CHAPTER/issues/49)). Three further findings
are not conversion defects but properties nothing states: `10fg` is not a gust
in any useful sense ([#50](https://github.com/meteocima/CHAPTER/issues/50)),
`ssro` is empty and `ro` therefore carries no information `sro` does not
([#51](https://github.com/meteocima/CHAPTER/issues/51)), and graupel
precipitation falls out of both published components of `tp`
([#52](https://github.com/meteocima/CHAPTER/issues/52)).

## The sample is not enough for this family, and saying so is the point

The audit sample holds 00, 06, 12 and 18Z of one day. The two central claims of
this ticket are about **consecutive** hours — that `PREC_ACC_NC` equals the
hour-to-hour difference of `RAINNC`, and that `WSPD10MAX` is reset at every
history write — and neither can be tested on four points of a day.

Both sample days are on disk at full hourly resolution: **2024-07-15** in
`wrfout_share` (convective) and **2024-02-15** in `wrfout_rebuild` (snow), 24
files each. Four more whole days were added for the reset census alone. Nothing
here rests on a timestep the rest of the audit did not also measure.

## The table

| variable | paramId | leg A | leg B | leg C | verdict |
|---|---|---|---|---|---|
| `tp` | 228 | ok | **exact**, `RAINNC` | **0.971** vs ERA5 `tp`, corr 0.77 | **verified** |
| `sf` | 144 | ok | **exact**, `SNOWNC` | **1.016** vs ERA5 `sf`, corr 0.80 | **verified**, → [#52](https://github.com/meteocima/CHAPTER/issues/52) |
| `tirf` | 235015 | ok | **exact**, identity | **0.960** vs ERA5 `tp − sf`, corr 0.76 | **verified**, → [#52](https://github.com/meteocima/CHAPTER/issues/52) |
| `sro` | 8 | ok | **exact**, `SFROFF` | 1.0–4.6 vs ERA5 | **verified**, → [#51](https://github.com/meteocima/CHAPTER/issues/51) |
| `ssro` | 9 | ok | **exact**, `UDROFF` | **0.000–0.004** | **verified but empty** → [#51](https://github.com/meteocima/CHAPTER/issues/51) |
| `ro` | 205 | ok | **exact**, identity | 0.19–0.85 vs ERA5 | **verified**, → [#51](https://github.com/meteocima/CHAPTER/issues/51) |
| `10fg` | 49 | ok | **exact**, `WSPD10MAX` | **0.625** vs ERA5 `10fg` | **wrong window** → [#49](https://github.com/meteocima/CHAPTER/issues/49), not a gust → [#50](https://github.com/meteocima/CHAPTER/issues/50) |

No leg A failure, no bitmap, no missing point, at any of the 34 timesteps. Leg B
is **exact for all seven** — four read straight through from the wrfout and
three restated as identities — and agrees to 1.5e-8 or better on the six water
fields, 1.9e-6 m/s on `10fg`.

### Leg C needed the right counterpart, and it is not the obvious one

The ERA5 controls retrieved with the audit set make three better comparisons
possible than the harness's default pairing by shortName. One of them **refuted
the hypothesis that motivated it**, and that is worth writing down.

`CU_PHYSICS = 0`, so every millimetre this run produces is WRF "grid scale". The
natural inference is that our `tp` should be compared against ERA5's
*large-scale* precipitation `lsp` rather than its total, because the total
contains a convective part we structurally cannot have. Measured, over sixteen
timesteps:

| pair | ratio | corr |
|---|---|---|
| `tp` vs ERA5 `tp` | **0.971** | 0.766 |
| `tp` vs ERA5 `lsp` | 1.891 | 0.688 |
| `sf` vs ERA5 `sf` | **1.016** | 0.803 |
| `sf` vs ERA5 `lsf` | 1.179 | 0.818 |
| `tirf` vs ERA5 `lsp − lsf` | 1.987 | 0.685 |
| `tirf` vs ERA5 `tp − sf` | **0.960** | 0.762 |

The inference was wrong, and the error is instructive: **"grid scale" in a
3 km convection-permitting run is not "large scale" in IFS.** WRF's bookkeeping
calls a resolved thunderstorm grid-scale because no cumulus scheme produced it;
IFS calls the same storm convective because its scheme did. The names coincide
and the physics does not. ERA5's *total* is the counterpart for our total, and
`lsp` is only half of it.

That also hands `tirf` a leg C the harness says does not exist: the crosswalk
records "no time-integral of rain flux" for paramId 235015, but ERA5's
`tp − sf` **is** an all-rain accumulation, and `tirf` sits at 0.960 against it —
the same quality as `tp`, month by month between 0.85 and 1.12.

## The accumulation convention, tested hour by hour

Family 4 verified the accumulation *machinery* — template 8, the 00Z reference,
exact zero at 00Z, the sidecar subtraction — on thirteen radiation fields. What
this family owns is whether WRF's own counters behave the way the convention
assumes them to.

### Every accumulator is monotone. No exceptions.

Across 2 days × 23 hourly transitions × 8 counters × 2 220 273 points —
**817 million comparisons** — the number of points at which an accumulator fell
is **zero**:

| counter | points where it fell | worst |
|---|---|---|
| `RAINNC` `SNOWNC` `GRAUPELNC` `HAILNC` | **0** | 0 |
| `SFROFF` `UDROFF` `RAINC` `ACRUNOFF` | **0** | 0 |

That settles "no bucket reset" empirically and not merely from the absence of
`I_RAINNC` in the file.

### The bucket check: the strongest test available, and it passes

`prec_acc_dt = 60`, so WRF writes its own 60-minute bucket `PREC_ACC_NC`. If our
convention is right then

    PREC_ACC_NC(H)  ==  RAINNC(H) − RAINNC(H−1)

at every point. Over 46 hourly transitions on the two days:

| | |
|---|---|
| worst absolute disagreement | **2.52e-4 mm** (2024-02-15, hour 21) |
| worst relative disagreement | **7.9e-6** |
| points above 1e-4 mm | 0 to 31 per hour, out of 2 220 273 |

That residual is single precision. `RAINNC` is a float32 accumulator that
reaches hundreds of millimetres locally, so its quantum near 100 mm is ~1e-5 mm
and the difference of two such numbers carries a few times that. **The
convention is exact; the arithmetic is float32.**

### `RAINC` and `HAILNC` are zero all day, both days

Maximum over 24 hours: **0.0** for both, on the convective July day and the
February one. `CU_PHYSICS = 0` is confirmed at the level of the data, so
`tp = RAINNC` is complete, and `mp_physics = 6` (WSM6) indeed has no hail
category. `ACRUNOFF == SFROFF` at every one of the 48 hours, which confirms the
recorded reason it is not published as `ro`.

### Zero at 00Z, exactly

All six 00Z-referred fields, all 16 00Z files of the sample: **max = 0.0 and
min = 0.0**. Not below a threshold — zero.

`RAINNC` at 00Z is *not* zero (domain mean 0.125 mm on 15 July, 0.365 mm on
15 February): the run started at 18Z the previous day and six hours of spinup
are already in the counter. That is the entire reason the 00Z sidecar exists,
and the contrast between those two numbers is the cleanest illustration of it
in this audit.

### The encoding is exactly what the schema claims

Read off the messages at 2024-07-15T12:

| key | six accumulations | `10fg` |
|---|---|---|
| `productDefinitionTemplateNumber` | **8** | **8** |
| `typeOfStatisticalProcessing` | **1** (accumulation) | **2** (maximum) |
| `stepType` / `stepRange` | `accum` / `0-12` | `max` / **`0-1`** |
| `dataDate` / `dataTime` | 20240715 / **0000** | 20240715 / **1100** |
| `validityDate` / `validityTime` | 20240715 / 1200 | 20240715 / 1200 |
| `lengthOfTimeRange` | 12 | 1 |

At 00Z the accumulations collapse to step `0`, length `0`. `10fg` at 00Z
correctly crosses the day boundary: reference **20240714 / 2300**. The `H−1`
reference the ticket asks about is there, and so is
`typeOfStatisticalProcessing = 2`, which the converter never sets explicitly —
it comes from `paramId 49`'s own definition, applied after the template.

## The finding: `10fg` is not reset at every history write

`WSPD10MAX` is one of the seven maxima `nwp_diagnostics = 1` adds, and with
`history_interval = 60` it is supposed to be a one-hour maximum. The GRIB says
so: `stepType = max`, `stepRange = 0-1`, reference time H−1.

A one-hour maximum over 2 220 273 points **must fall somewhere** between two
consecutive hours: the wind cannot rise at every point of a 1641 × 1353 domain.
An hour with *zero* points below the previous hour, and a large population
exactly equal to it, is an hour whose maximum was carried over.

| day | transitions | not reset | which hours |
|---|---|---|---|
| 2024-07-15 | 23 | **4** | 16, 19, 21, 22 |
| 2024-08-15 | 23 | **9** | 2, 4, 5, 9, 16, 17, 18, 20, 23 |
| 2019-07-15 | 23 | **2** | 4, 6 |
| 2024-02-01 | 23 | **2** | 13, 17 |
| 2024-02-15 | 23 | 0 | — |
| 2024-03-20 | 23 | 0 | — |
| **total** | **138** | **17 (12.3 %)** | |

At hour 16 of 2024-07-15, **848 867 points** are bit-for-bit equal to hour 15
and not one is below it. At hour 22, 1 327 993 are.

### How much it matters

The published value at a carried-over hour is a maximum over two hours or more,
so it is too high. Measured as the mean excess of `WSPD10MAX` over the
instantaneous 10 m wind of the same file:

| | mean excess |
|---|---|
| hours that reset | **0.068 to 0.311 m/s** |
| hours that did not | **0.499 to 0.784 m/s** |

Three to eight times larger. On a domain mean of ~4.5 m/s that is a 10–17 per
cent overstatement at those hours, under a message that declares a one-hour
window.

### Why, stated as a hypothesis and not a conclusion

The run uses `use_adaptive_time_step = .true.` with `adaptation_domain = 2` and
`step_to_output_time = .true.`. The output times are exact — that is what makes
the bucket check above agree to float32 — but the diagnostic reset and the
history write are separate events, and the census correlates with the timestep's
variability: the two convective summer days account for 13 of the 17 misses,
the two winter days for 4, and the March day for none. That is a correlation on
six days, not a mechanism. **The measurement is the finding; the cause is not
established here.**

### It corrects a closed ticket

`docs/audit/run-configuration.md` §e, the output of
[#12](https://github.com/meteocima/CHAPTER/issues/12), says:

> `CLAUDE.md` established for `WSPD10MAX` alone, by testing monotonicity across
> hours, that it is reset at every history write. **That is now settled from the
> configuration, and it generalises**: with `history_interval = 60`, all seven
> are 1-hour maxima.

The configuration says what WRF intends. The data says the intent is missed on
12 per cent of hours, so neither the claim for `WSPD10MAX` nor its
generalisation to the other six maxima is safe. None of the other six is
published, so nothing else in the archive depends on it — but a future ticket
reaching for `W_UP_MAX` or `UP_HELI_MAX` must not inherit the window without
testing it. A correction is posted on
[#12](https://github.com/meteocima/CHAPTER/issues/12).

## `10fg` is not a gust, and now there is a number

`MISSING_VARIABLES.md` §5 already says the right thing qualitatively — "it is
the maximum of the *resolved* 10 m wind speed over the output hour… not produced
by a gust scheme". What it does not say is how far that is from ERA5's, and the
distance is the whole story.

| comparison | ratio | corr |
|---|---|---|
| ours vs ERA5 `10fg` (gust scheme, hourly max) | **0.625** | 0.813 |
| ours vs ERA5 `i10fg` (gust scheme, instantaneous) | **0.644** | 0.820 |
| ours vs **our own instantaneous 10 m wind** | **1.004 to 1.032** | — |

The last row is the one that settles it. On the four sample timesteps, `10fg`
exceeds the instantaneous 10 m wind speed of the same file by **0.5 to 3.2 per
cent** in the mean, and it is below it at **zero points** out of 2 220 273
(worst excursion 2.0e-6, the packing) — which is the consistency check an hourly
maximum has to pass, and it passes.

But it means the "maximum" adds almost nothing. Published under paramId 49,
`10fg` is the 10 m wind speed with a two-per-cent premium, where ERA5's is a
parameterised gust roughly 1.6 times the mean wind. A user who reads it as a
gust under-predicts by 38 per cent, and no document carries that number.
[#50](https://github.com/meteocima/CHAPTER/issues/50).

## The runoff triplet carries one field's worth of information

| timestep | `sro` mean | `ssro` mean | `ssro` non-zero points | `ro` mean |
|---|---|---|---|---|
| 2024-02-15T12 | 3.093e-5 | **0** | **0** | 3.093e-5 |
| 2024-07-15T12 | 2.347e-5 | 2.7e-8 | **19** | 2.350e-5 |
| 2024-07-15T18 | 1.064e-4 | 3.9e-8 | **19** | 1.065e-4 |
| 2024-08-15T12 | 1.453e-5 | **0** | **0** | 1.453e-5 |

Across the 34-timestep sample `ssro` is **identically zero on five of the
eighteen** non-00Z timesteps, and where it is not, its domain mean is four to
eight orders of magnitude below `sro`. `ro` equals `sro` to four significant
figures at every timestep. `ro − sro − ssro` is at most 3.7e-9 m, so the
identity itself is right; there is simply nothing in the second term.

**This is not a conversion defect.** Leg B is exact, and the underlying
`UDROFF` is not dead: the census finds it non-zero at 462 to 8 363 points with
maxima of 11 to 106 mm. The point is that `UDROFF` barely *moves within a day* —
on 2024-07-15 the same 1 647 points carry drainage at 00, 06, 12 and 18Z and
only 19 of them grow — and the published field is an accumulation **since 00Z**,
so it is almost always empty.

ERA5's partition is the opposite: its `ssro` dominates its `ro`, which is why
our `sro` runs 1.0–4.6 times ERA5's while our `ro` runs 0.19–0.85 of it. Anyone
closing a water budget on this archive gets "no drainage", and three published
variables deliver one field.
[#51](https://github.com/meteocima/CHAPTER/issues/51).

## Graupel falls out of both components of `tp`

`sf = SNOWNC` and `tirf = RAINNC − SNOWNC − GRAUPELNC`, so
`tp − sf − tirf = GRAUPELNC`, and graupel is published nowhere:

| timestep | residual mean | residual max | points > 1e-3 mm |
|---|---|---|---|
| 2024-02-15T12 | 0.0094 mm | **11.97 mm** | **138 026** |
| 2024-07-15T12 | 0 | 7.5e-6 mm | 0 |
| 2024-07-15T18 | 0 | 7.5e-6 mm | 0 |

On the February day the missing graupel is **6.4 per cent of the published
snowfall** in the domain mean and 12 mm at a point. ECMWF defines paramId 144
`sf` as the accumulated snow reaching the surface from large-scale *and*
convective precipitation — all solid precipitation, since IFS has no graupel
category. Ours excludes it, so the archive's solid precipitation is short by
whatever WSM6 froze into graupel rather than snow.
[#52](https://github.com/meteocima/CHAPTER/issues/52).

This is the same shape as [#47](https://github.com/meteocima/CHAPTER/issues/47)
in family 3, and a degree worse: there graupel had no ERA5 home, here it has
one.

**The `tirf` clip fires, and it is noise.** `RAINNC − SNOWNC − GRAUPELNC` goes
negative at 24 788 points on the February day, worst −7.2e-5 mm: float32
cancellation between three large accumulators, exactly the scale the bucket
check found. The `np.where(rain < 0, 0.0, rain)` clip is correct and removes
nothing real.

## A marker that marks nothing

`CLAUDE.md` and `fix_tp_accum.py` treat `generatingProcessIdentifier = 128` as
the flag saying an accumulation is referred to 00Z, against 127 for the old
run-init archive. The converter sets it only for `stepType == 'accum'`.

Counted over a whole file: **all 246 messages carry 128** — 226 instantaneous,
19 accumulations, 1 maximum. eccodes' own GRIB2 sample defaults to
`generatingProcessIdentifier = 128`, so the 227 messages the converter never
touches carry it for free.

Nothing is wrong: the accumulations are 00Z-referred and 128 does say so. But
inside `grib_v3` the value **discriminates nothing**, and a consumer who tests
it to find the 00Z-referred messages selects the entire file.
[#53](https://github.com/meteocima/CHAPTER/issues/53).

## What this family contaminates

- **[#12 run configuration](https://github.com/meteocima/CHAPTER/issues/12)** —
  corrected, as above: the one-hour window for the `nwp_diagnostics` maxima is
  the configuration's intent, not the data's behaviour.
- **Family 4** ([#22](https://github.com/meteocima/CHAPTER/issues/22), closed) —
  **confirmed, not contradicted**. Family 4 verified the machinery on thirteen
  radiation fields; this family verified WRF's counters underneath it on two
  whole days. The nineteen accumulators of the schema now rest on both.
- **Family 3** ([#21](https://github.com/meteocima/CHAPTER/issues/21), closed) —
  its quadrature defect does **not** reach here. These are WRF's own counters,
  differenced; there is no vertical integral in this family.
- **Nothing else.** `10fg`'s window defect is confined to one message of 246.

## What was *not* measured

- **The cause of the missed resets.** Six days give the rate and the
  correlation with convective days; establishing the mechanism means reading
  WRF's diagnostic driver against the adaptive-timestep alarm, which is a
  separate piece of work and is named in
  [#49](https://github.com/meteocima/CHAPTER/issues/49).
- **Whether the miss rate is stable across the archive.** 17 of 138 is six
  days, chosen because they were whole on disk, not sampled at random.
- **`ssro` outside the sample.** The claim that `UDROFF` barely moves within a
  day rests on one day at four hours plus the 34-timestep census.
