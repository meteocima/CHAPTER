# Family 1: the thirteen pressure-level variables

169 of the archive's 246 messages: `t` `q` `r` `u` `v` `w` `wz` `z` `cc` `clwc`
`ciwc` `crwc` `cswc`, each on 13 levels from 1000 to 50 hPa.

Measured over the 34-timestep sample. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl` (5746 of them for this family); the
measurements the harness cannot make are `tools/audit/f1_pressure.py`,
`f1_humidity.py` and `f1_rh_clip.py`, with their output beside the rows.

**Leg B is unavailable for all thirteen.** A pressure-level message is the
converter's vertical interpolation, not a field that exists to be read back, so
the harness carries legs A, C and D only. Everything below that is stronger than
leg C was obtained by going to the wrfout, to the interpolation itself, or to the
Fortran kernel.

**Ten of the thirteen are verified. Three are wrong**, and all three are
arithmetic rather than physics: a constant, a saturation definition and a
denominator.

## The table

| variable | paramId | leg A | leg C (ERA5) | verdict |
|---|---|---|---|---|
| `t` | 130 | ok | bias −0.01 to −0.19 K, corr ≥ 0.987, 850–100 hPa | **verified** |
| `q` | 133 | ok | ratio 0.96–1.01, corr 0.86–0.96 | **verified**, denominator → [#41](https://github.com/meteocima/CHAPTER/issues/41) |
| `r` | 157 | ok | ratio **0.51–0.67 above 400 hPa** | **wrong** ([#40](https://github.com/meteocima/CHAPTER/issues/40)) |
| `u` | 131 | ok | bias ≤ 0.21 m/s, corr 0.94–0.99 | **verified** |
| `v` | 132 | ok | bias ≤ 0.09 m/s, corr 0.94–0.99 | **verified** |
| `w` | 135 | ok | corr 0.22–0.56, see below | **verified** |
| `wz` | 260238 | ok | ERA5 does not carry it; leg D median 8.9e-05 m/s | **verified** |
| `z` | 129 | ok | bias +8 to +63 m²/s² mid-troposphere | **wrong** ([#39](https://github.com/meteocima/CHAPTER/issues/39)) |
| `cc` | 248 | ok | corr 0.21–0.63 | **verified** |
| `clwc` | 246 | ok | see the partition below | **verified** |
| `ciwc` | 247 | ok | see the partition below | **verified** |
| `crwc` | 75 | ok | 2.4–2.6× ERA5 below 850 hPa | **verified** |
| `cswc` | 76 | ok | 0.80–0.90× ERA5 below 500 hPa | **verified** |

Leg A failures across the family: **none**, at any level, at any of the 34
timesteps.

**Read this family per level, never in one line.** The harness's report averages
leg C over all 13 levels, and where a level's mean is near zero the ratio of
means explodes: the one-line row for `crwc` reads 756 and for `cc` reads 6.0,
both meaningless. Every number in this document is per level.

## The three findings

### 1. `z` is 0.034 per cent low, at every point of every level ([#39](https://github.com/meteocima/CHAPTER/issues/39))

The converter writes `to_levels(getvar('z')) * 9.80665`, but wrf-python built
that height by dividing WRF's own geopotential by **its own** constant,
`Constants.G = 9.81` (`fortran/wrf_constants.f90:31`). The published field is
therefore `(PH+PHB) × 9.80665/9.81`.

Measured rather than inferred: `geopt / z` on a real wrfout is 9.81 at every
point (9.809999999999999 to 9.810000000000002), and `wrf.vinterp` is **exactly**
linear in the field — `vinterp(2f) − 2·vinterp(f) = 0` — so the constant survives
the interpolation. Against `to_levels(getvar('geopt'))`:

| level | published − geopt | in metres | relative |
|---|---|---|---|
| 1000 hPa | −0.99 m²/s² | −0.10 m | −3.415e-04 |
| 500 hPa | −19.49 m²/s² | −1.99 m | −3.415e-04 |
| 250 hPa | −36.19 m²/s² | −3.69 m | −3.415e-04 |
| 100 hPa | −55.94 m²/s² | −5.70 m | −3.415e-04 |
| 50 hPa | −69.60 m²/s² | −7.10 m | −3.415e-04 |

The same relative error to four digits at all thirteen levels: that is what a
constant factor looks like. It also makes the archive's two geopotentials
inconsistent — family 7 verified the **surface** `z` as `HGT × 9.80665`, which is
right, because `HGT` is a genuine height and not a round trip.

### 2. `r` is humidity over liquid water, clipped at 100 ([#40](https://github.com/meteocima/CHAPTER/issues/40))

Leg C shows `r` agreeing within 3 per cent to 700 hPa and then collapsing, while
`q` and `t` — the two fields `r` is made of — agree within a few per cent at the
same levels. Two fields agreeing and the third not is a definition difference.

`fortran/wrf_user.f90:722` computes saturation over **liquid water** at every
temperature; ECMWF defines paramId 157 over the **mixed phase**. Recomputing `r`
from our own published `q` and `t` in ECMWF's definition:

| level | mean T | published / ERA5 | **mixed-phase / ERA5** |
|---|---|---|---|
| 700 hPa | 280.2 K | 1.024 | 1.027 |
| 500 hPa | 263.4 K | 0.914 | 0.971 |
| 400 hPa | 251.9 K | 0.778 | 0.959 |
| 300 hPa | 237.2 K | **0.672** | **0.975** |
| 250 hPa | 229.3 K | **0.619** | **0.976** |
| 150 hPa | 218.9 K | **0.558** | **0.973** |
| 100 hPa | 212.6 K | **0.505** | **0.943** |

Nothing about the moisture changes, only the saturation it is divided by, and a
ratio of one half becomes a ratio of one. `r` above 400 hPa is roughly half what
the parameter it is published under means.

The same kernel also **clips at 100**: `rh = 100·MAX(MIN(qv/qvs, 1), 0)`. On
pressure levels the clip removes real supersaturation at 27 137 points at
1000 hPa and 75 124 at 925 hPa in one file, while ERA5 on those dates reaches 128
per cent.

**This corrects [#33](https://github.com/meteocima/CHAPTER/issues/33)**, which
concluded `2r` has no clip — see the last section.

### The definition that replaces it, from the IFS documentation

Settled 2026-09-22 with the user. Every constant is quoted from **IFS
Documentation Cy41r2, Part IV: Physical Processes** — Cy41r2 because that is the
cycle ERA5 was produced with, so it is the cycle whose definition paramId 157
has to match. The implementation is `tools/audit/ifs_humidity.py`.

Page 112, in words, above Eq. (7.89):

> "currently defined as relative humidity with respect to water for temperatures
> warmer than 0 °C, with respect to ice for temperatures colder than −23 °C, and
> a mix of the two in the 0 °C to −23 °C temperature range."

| | |
|---|---|
| Eq. (7.89) | `e/esat = p q (1/ε) / (esat (1 + q(1/ε − 1)))`, **ε = R_dry/R_vap = 0.621981** |
| Eq. (7.90) | `esat = α·esat_water + (1 − α)·esat_ice` |
| Eq. (7.5), water, Buck (1981) | `a1 = 611.21 Pa, a3 = 17.502, a4 = 32.19 K` |
| Eq. (7.5), ice, Alduchov & Eskridge (1996) | `a1 = 611.21 Pa, a3 = 22.587, a4 = −0.7 K` |
| Eq. (7.6), α = **liquid** fraction | 0 below `T_ice`; `((T − T_ice)/(T0 − T_ice))²` between; 1 above `T0` |
| thresholds | `T_ice = 250.16 K`, `T0 = 273.16 K` |

**α is quadratic, not linear.** The first measurement in this family used a
linear ice fraction; it got the pure-ice levels right, where both agree, and was
approximate between 250 and 273 K. The correct quadratic improves exactly there
— at 500 hPa the ratio against ERA5 goes from 0.971 to **0.995**.

**Nothing in the definition clips.**

The module's `self_check()` verifies the identities rather than assuming them:
the mixed curve equals the water curve exactly at `T ≥ T0` and the ice curve
exactly at `T ≤ T_ice`, α is 0 and 1 at the thresholds and **0.25 at the
midpoint** (a linear α would give 0.5), the curve is monotone and lies between
the two pure ones, and **saturated air reads exactly 100** in all three regimes.

### Phase or formula? The two changes, separated

Adopting the IFS definition changes two things at once. They are separated here
so the second is not credited to the first (2024-07-15T12, mean over each level):

| level | phase: `mixed / water` | formula: `Buck / Magnus` |
|---|---|---|
| 1000 hPa | 1.000 | 0.994 |
| 700 hPa | 1.001 | 0.999 |
| 500 hPa | 1.091 | 1.002 |
| 400 hPa | 1.248 | 1.005 |
| 300 hPa | 1.440 | 1.011 |
| 200 hPa | 1.607 | 1.019 |
| 100 hPa | **1.793** | 1.039 |

**The phase is the whole story**; the change of formula is under 1 per cent below
500 hPa and never above 4. And ε = 0.621981 against the kernel's 0.622 is
3.1e-05 relative — noise.

With the correct constants the agreement with ERA5 is 0.945 to 1.058 at **every**
level from 1000 to 100 hPa, against 0.505 to 1.052 as published.

### How far above 100 the field actually goes, and where

The clip means nobody has ever seen the real maximum. Measured on three
timesteps, unclipped and mixed-phase:

| | |
|---|---|
| **above ground**, maximum | **141.9 %** at 300–400 hPa, in the ice regime |
| points above 100 at 400–500 hPa | **32 500 to 117 493** per timestep |
| **below ground**, maximum | **163.1 %** at 1000 hPa |
| points above 130 at 1000, 925, 850 hPa | **every one of them is below ground** |
| the same levels, above ground only | 100.3, 109.4, 115.6 |
| **at 2 m**, maximum over all 34 timesteps | **100.2 %** |

Two things follow.

**WSM6 does permit ice supersaturation**, and a lot of it — tens of thousands of
points per timestep at 400–500 hPa, reaching 142 per cent, which is below the
homogeneous freezing threshold, where it should stop. That signal is **entirely
absent from the archive today**: first halved by the wrong saturation, then what
survived was clipped away.

**The extremes above 130 are an artifact of this measurement, not of the
archive.** Below ground `q` and `t` are clamped from about 25 m AGL
([#44](https://github.com/meteocima/CHAPTER/issues/44)), where the real pressure
may be 700 hPa; pairing them with the *nominal* 1000 hPa inflates the vapour
pressure by up to a factor 1.4 and manufactures the 163 per cent. The archive's
own `r` below ground is the model's own value and is sound.

**That settles how the fix must compute it**: `r` has to be evaluated on model
levels and then interpolated, exactly as now, and not recomputed from the
interpolated `q` and `t` at the nominal level pressure. Noted on
[#40](https://github.com/meteocima/CHAPTER/issues/40).

So `RANGE_OVERRIDE['r']` is now **(0, 200)**: enough room for the extrapolation,
still tight enough to catch a doubling or a unit error. `2r` stays at (0, 130),
which its measured maximum of 100.2 leaves untouched.

### `r` takes the mixed phase; `2r` stays over water — two conventions, both right

Decided 2026-09-22 and **revised the same day**, after
[#44](https://github.com/meteocima/CHAPTER/issues/44) showed why the first
version of the argument did not hold.

The first decision moved **both** `r` and `2r` to the mixed phase, on the ground
that two fields called "relative humidity" in one archive must not use two
saturations. That argument assumes `r` and `2r` are neighbours a reader joins.
**They are not.** On 47.6 per cent of the domain `r` at 1000 hPa is not at
1000 hPa at all — it is the lowest model level, clamped, at 24 to 27 m above
ground (#44); where it *is* above ground it sits at 84 to 126 m, with the
unresolved surface layer in between. The join is not operationally available.

What *is* available is `2t`, `2d`, `2r`: same level, same message group, and
anyone will combine them.

| | saturation | why |
|---|---|---|
| `r`, paramId 157, pressure levels | **mixed phase** | the IFS's own definition of the parameter, and **measured**: recomputing it that way moves the ratio against ERA5 from 0.505 to 0.945 at 100 hPa |
| `2r`, paramId 260242, screen level | **liquid water** | the WMO convention for a surface humidity at every temperature — a station at −20 °C reports over water — and **ERA5 publishes no 2 m relative humidity at all**, so there is no ECMWF practice to follow |
| `2d`, paramId 168 | **liquid water** | a dewpoint is over water by definition |

So the two saturations are not an inconsistency: they are the observational
convention at the surface and the model convention aloft. And `2d` and `2r` agree
again, so the reconstruction a user makes from `2t` and `2d` **returns `2r`**,
its only residue being the dewpoint round trip — `2d` and `Q2` are mutually
consistent to **3.6e-4 to 1.1e-2** relative in vapour pressure across the whole
sample.

**The clip remains the defect in both**, and it is the part that was never in
doubt.

**The price, which must be stated where a data user will meet it and not only
here:** `r` and `2r` use different saturations. Someone who reads `r` at 1000 hPa
and `2r` together and assumes they are the same quantity will be wrong at cold
points — the mirror image of the trap this audit just removed.

### 3. `q` and the hydrometeors use different moist air ([#41](https://github.com/meteocima/CHAPTER/issues/41))

The hydrometeors divide by `1 + r_total` (all six species); `q` is written as
`r_v / (1 + r_v)`. ECMWF's moist air includes the condensate, so `q` should carry
the same denominator. Measured: **0 in the median** (no condensate) and **1.13
per cent at most** — the same order as the correction its neighbours already get.

While there: the correction's size on file, "0.8 % in the median, 2.2 % at most",
reproduces at the top — **2.26 per cent** — and not in the middle. Over the full
3-D field the median is **0.011 per cent** and the 99th percentile 1.44 per cent.
A median with no population is not a measurement; most of a 49-level column is
dry upper troposphere.

## What is verified, and on what

### `t`, `u`, `v`

`t` is within 0.19 K of ERA5 at every level from 850 to 100 hPa, correlation
0.987 to 0.997. `u` and `v` are within 0.21 and 0.09 m/s, correlation 0.94 to
0.99. Two levels stand out and both are explained below: 1000 hPa (below ground)
and 50 hPa (the lid).

The wind components need no rotation: `MAP_PROJ = 3` is Mercator, whose axes are
aligned with the meridians, so the destaggered `U`/`V` are already earth-relative.
That is a configuration fact, not an inference from the values.

### `w` and `wz` are the same field in two conventions, and are not swapped

| | |
|---|---|
| points where `w` and `wz` have opposite sign | **99.73 to 100 per cent**, every level |
| correlation between them | **−0.9977 to −0.9999**, every level |
| leg D, `w_z = −ω/(ρg)` from the published `w` and `t` | median **8.9e-05 m/s** over 442 rows |

The sign convention is ERA5's: `w` is ω in Pa/s, positive downward; `wz` is
positive upward. The residual fraction of a per cent is points where `w` passes
through zero.

The magnitudes are worth recording because they will look wrong to anyone used to
ERA5: `w` reaches −137 Pa/s and `wz` +23.5 m/s at 400 hPa. At 3 km the model is
convection-permitting and those are ordinary July updraughts. That is also why
leg C's correlation for `w` is only 0.22 to 0.56 — ERA5 at 31 km cannot have the
field we have, and this is the resolution gap, not a defect.

### `cc` is fractional, and the old note in `CLAUDE.md` was wrong

Over all 13 levels of one file, 28 863 549 values:

| | |
|---|---|
| distinct values, rounded to 4 dp | **10 001** |
| cloudy points exactly at 1 | **6.9 per cent** |
| deciles of the cloudy points | 0.013 / 0.062 / 0.295 / 0.815 / 0.998 |

`ICLOUD = 1` is Xu-Randall and it produces a continuum. The claim that `CLDFRA`
is binary, already corrected in `CLAUDE.md`, is refuted again here on the
pressure levels.

### The hydrometeors: the partition differs, the total much less

Reading `clwc` or `ciwc` alone against ERA5 is misleading, because WSM6 and the
IFS split condensate between liquid and ice differently:

| level | `clwc` ours/ERA5 | `ciwc` ours/ERA5 | **(clwc+ciwc) ours/ERA5** |
|---|---|---|---|
| 925 hPa | 0.93 | 6.7 | **0.96** |
| 850 hPa | 0.77 | 74 | **0.81** |
| 700 hPa | 0.43 | 2.3 | **0.63** |
| 600 hPa | 0.15 | 1.8 | **0.65** |
| 500 hPa | 0.08 | 1.3 | **0.90** |

Our supercooled liquid is converted to ice where the IFS keeps it. The total
condensate agrees to 0.63–0.96; neither species does alone. `cswc` is a steady
0.80–0.90 of ERA5 below 500 hPa, and `crwc` is 2.4–2.6× ERA5 below 850 hPa,
which is what a convection-permitting model does with rain water that a 31 km
model parameterises away.

The dry-to-moist division is applied to all four as a **single multiply of the
whole pressure-level array** (`values * moist_factor(True)`), so "at every level"
is structural rather than a coincidence; its size is in finding 3.

## Two levels that are not like the others

### 1000 hPa is below ground on half the domain

`wrf.vinterp` is called with `extrapolate=True`, so below-ground points carry a
value and **not** a bitmap. **But it does not extrapolate** — see the correction
below. At 2024-07-15T12:

| level | points below ground | mean `t` there | mean `t` above ground |
|---|---|---|---|
| 1000 hPa | 1 056 120 (**47.6 %**) | 304.7 K | 293.9 K |
| 925 hPa | 207 640 (9.4 %) | 302.2 K | 294.8 K |
| 850 hPa | 33 133 (1.5 %) | 294.7 K | 290.7 K |
| 700 hPa | 12 | 280.3 K | 280.2 K |
| 600 hPa and above | **0** | — | — |

Nothing is missing: `n_missing` is 0 everywhere.

#### Correction: it is a clamp, not an extrapolation ([#44](https://github.com/meteocima/CHAPTER/issues/44))

This section first said those values were an extrapolation, and that ERA5
extrapolates too so the convention matches. **Both halves are wrong**, found by
joining this family to family 2.

`wrf.vinterp` extrapolates only the field *types* it recognises (`ght`, `t`,
`p`). The converter hands it a **raw array**, so below ground it **clamps to the
lowest model level**. Tested against the wrfout at three timesteps and both
levels, on up to 1 271 533 points:

| | |
|---|---|
| `t` against the lowest model level | **max absolute difference exactly 0.0**, 100 % of points |
| `z` against it | 5e-05 m median |
| `q` against it | 1e-09 max, 7e-08 relative |

So a user reading 1000 hPa over the Alps is reading **the air at about 25 m above
the ground there** — a real model state, not an invention, which is better than
this section originally claimed. It is also why the surface join works:
`2t − t(1000 hPa)` below ground is −0.9 K at midnight and +1.4 K at noon in July,
a nocturnal inversion and a superadiabatic daytime surface layer over a 22 m
interval.

Two things follow that are worse. **`z` contradicts `sp`**: where the surface
pressure says the 1000 hPa surface is below the terrain, the published `z` puts
it at a median of +24 to +27 m *above* it, and both messages sit in the same
file. And **ERA5 does extrapolate**, with a lapse rate, so the two archives
differ in convention exactly where 1000 hPa is underground — which is most of the
land, and which is the whole of 1000 hPa's leg C anomaly (`t` bias −1.71 K
against −0.05 K at 850, `z` correlation 0.108). Filed as
[#44](https://github.com/meteocima/CHAPTER/issues/44); it needs a decision, not a
patch.

### 50 hPa is the model lid, and three independent measurements say so

[#12](https://github.com/meteocima/CHAPTER/issues/12) established that 50 hPa is
exactly `p_top` with no damping. This family puts numbers on it:

| | 50 hPa | 100 hPa |
|---|---|---|
| `q` correlation with ERA5 | **0.108** | 0.864 |
| `t` correlation with ERA5 | 0.910 | 0.988 |
| hypsometric closure of the layer below | **−5.9 %** | −0.32 % |

The hypsometric check is the strongest of the three because it needs no ERA5 at
all: from the published `z`, `t` and `q`, every layer from 850 to 100 hPa closes
to a median of 0.02 to 0.33 per cent — the layer-mean approximation's own
accuracy. The 100–50 hPa layer closes to −5.9 per cent. **The topmost level
should carry a warning wherever the archive is described.**

## Correcting a closed ticket

[#33](https://github.com/meteocima/CHAPTER/issues/33) examined whether `2r` is
clipped, concluded it is not, and recorded that in
`docs/audit/harness.md` under *A measurement that killed its own suspicion*. The
suspicion was right.

It is clipped, and each piece of the refutation is the clip's own signature:

| #33's evidence | what it is |
|---|---|
| maxima bracket 100 within ±3e-6 | a value pinned at exactly 100, returned by 24-bit CCSDS packing. **The largest excursion, 2.9e-6, is half the packing quantum of 6.0e-6** |
| 28 629 points above 100 on 2024-01-15T12 | **exactly** the 28 629 the unclipped kernel puts above 100 |
| 61 250 points at RH 100 in July, read as dew | the 61 244 the unclipped kernel puts above 100 |
| `src/wrf/g_rh.py:152` has no truncation | the truncation is in the Fortran the wrapper calls, `wrf_user.f90:730` |

Recomputing the kernel from the wrfout's own `Q2`, `PSFC`, `T2`:

| timestep | published at 100 | unclipped above 100 | unclipped max | mean excess removed |
|---|---|---|---|---|
| 2024-01-15T12 | 28 629 | 28 629 | 101.35 | 0.55 %RH |
| 2024-07-15T00 | 61 245 | 61 244 | 101.96 | 0.81 %RH |
| 2024-07-15T12 | 18 316 | 18 316 | 101.80 | 0.91 %RH |
| 2025-02-15T12 | 20 305 | 20 305 | 101.13 | 0.59 %RH |

The published field reproduces `clip(kernel, 0, 100)` to a median of 2.4e-6 %RH
and differs from the unclipped kernel by up to 1.96 %RH.

**The general lesson is worth more than the correction: a clip cannot be seen in
the packed maxima.** Packing scatters the pinned value, and the scatter looks
exactly like float noise on a ratio reaching 1. Only recomputing from the source
distinguishes them.

## What this family contaminates

- **Family 2 ([#20](https://github.com/meteocima/CHAPTER/issues/20))** owns `2r`
  and must read [#40](https://github.com/meteocima/CHAPTER/issues/40) before
  judging it. `2t` and `2d` are untouched.
- **[#33](https://github.com/meteocima/CHAPTER/issues/33)'s resolution** on the
  `2r` clip, and the section of `docs/audit/harness.md` that records it.
- **Family 7's `z`** is *not* contaminated — the surface geopotential is right,
  and that is what makes the pressure-level one inconsistent with it.
- **Family 3 ([#21](https://github.com/meteocima/CHAPTER/issues/21))** is *not*
  contaminated by [#41](https://github.com/meteocima/CHAPTER/issues/41): the
  column integrals already use the all-species denominator. Family 3 should
  however expect the same liquid/ice partition difference in `tclw` and `tciw`
  that appears here, and read their sum.
