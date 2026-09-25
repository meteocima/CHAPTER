# Family 2: near-surface state

Ten fields on `heightAboveGround`: `10u` `10v` `100u` `100v` `200u` `200v` `2t`
`2d` `2r` `vwsh`. `10fg` is deliberately elsewhere — it is an accumulation with
its own time convention and belongs to the water-cycle family.

Measured over the 34-timestep sample. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl` (340 for this family); the measurements
the harness cannot make are `tools/audit/f2_near_surface.py` and
`f2_profile.py`, output beside the rows.

**Nine of the ten are verified.** The tenth, `2r`, is wrong — but that was found
in family 1 and is [#40](https://github.com/meteocima/CHAPTER/issues/40); what
this family adds is the measurement of it over the whole sample. Two smaller
findings are filed: [#42](https://github.com/meteocima/CHAPTER/issues/42) and
[#43](https://github.com/meteocima/CHAPTER/issues/43).

## The table

| variable | paramId | leg A | leg B | leg C (ERA5) | verdict |
|---|---|---|---|---|---|
| `2t` | 167 | ok | **exact** | bias −0.57 K, corr 0.976 | **verified** |
| `2d` | 168 | ok | not available | bias **−0.02 K**, corr 0.957 | **verified**, note → [#42](https://github.com/meteocima/CHAPTER/issues/42) |
| `2r` | 260242 | ok | not available | ERA5 does not carry it | **wrong** ([#40](https://github.com/meteocima/CHAPTER/issues/40)) |
| `10u` | 165 | ok | **exact** | bias +0.099 m/s, corr 0.945 | **verified** |
| `10v` | 166 | ok | **exact** | bias −0.002 m/s, corr 0.944 | **verified** |
| `100u` | 228246 | ok | not available | bias +0.104 m/s, corr 0.945 | **verified** |
| `100v` | 228247 | ok | not available | bias −0.038 m/s, corr 0.943 | **verified** |
| `200u` | 228239 | ok | not available | ERA5 does not carry it | **verified** (leg D bracket) |
| `200v` | 228240 | ok | not available | ERA5 does not carry it | **verified** (leg D bracket) |
| `vwsh` | 260068 | ok | not available | ERA5 does not carry it | **verified** (leg D **exact**) |

No leg A failure anywhere in the family, at any of the 34 timesteps. **No field
carries a bitmap and none has a missing point**, all ten are on
`heightAboveGround` at the level their name claims, and the units eccodes reports
are K, m s⁻¹, % and s⁻¹ as declared.

**Ignore the report's ratio column for this family** — `100u` reads 0.305 over
the whole domain and **−2.376** over land, while its bias is +0.196 m/s and its
correlation 0.921. The wind components have means near zero, so a ratio of means
is not a measurement. Filed as
[#43](https://github.com/meteocima/CHAPTER/issues/43).

## The family is built two ways, and that is the thing to check

The ten fields do not come from one place:

| | how |
|---|---|
| `2t`, `10u`, `10v` | WRF's own surface-layer diagnostics, from similarity theory. **Leg B is exact** because they are wrfout variables read straight through |
| `100u/v`, `200u/v` | `wrf.interplevel` on height above ground — an interpolation of the **resolved** profile between model levels |
| `2d`, `2r` | wrf-python diagnostics from `Q2`, `PSFC`, `T2` |
| `vwsh` | the converter's own difference between the two kinds |

So the bottom of the profile is a parameterisation and everything above it is an
interpolation, and nothing in the code guarantees they agree. They do.

### The interpolation never has to extrapolate

`wrf.interplevel` does not extrapolate: asked for a height below the lowest model
level it returns a gap. The converter's comment claims the lowest mass level sits
at about 25 m so 100 m and 200 m are always inside the column. Measured at **all
34 timesteps**:

| | |
|---|---|
| lowest mass level above ground | **21.06 to 27.99 m**, mean 25.13 m |
| second mass level | 82.4 m on average |
| points where the lowest level is above 100 m | **0**, summed over the whole sample |
| points where it is above 200 m | **0** |

Which is why there is no bitmap and no missing point in the family: there was
never anything to mask.

### The two methods agree to millimetres per second

The strongest check available here needs no ERA5. The 1000 hPa surface sits at a
median of **84 to 126 m above ground**, i.e. between the 100 m and 200 m levels,
and it is reached by a completely different route — `wrf.vinterp` on pressure
rather than `interplevel` on height. Where its height genuinely falls between the
two:

| timestep | points in the band | wind lies between `s100` and `s200` | mean excursion when it does not |
|---|---|---|---|
| 2024-01-15T00 | 550 859 | **90.8 %** | 0.004 m/s |
| 2024-07-15T00 | 368 798 | **92.0 %** | 0.002 m/s |
| 2024-07-15T12 | 457 958 | **91.2 %** | 0.003 m/s |
| 2025-02-15T00 | 690 109 | **88.0 %** | 0.006 m/s |

Two independent interpolations of the same model field, on two different vertical
coordinates, bracketing each other on nine points in ten and disagreeing by
millimetres per second on the tenth.

### The profile is monotone where it means anything

| | 10 → 100 m falling | 100 → 200 m falling |
|---|---|---|
| 2024-01-15T00 | 3.5 % | 13.6 % |
| 2024-07-15T00 | 4.6 % | 27.7 % |
| 2024-07-15T12 | 2.8 % | 26.0 % |
| 2025-02-15T00 | 4.2 % | 19.9 % |

The 10 → 100 m step, which is the one that crosses from the parameterisation to
the interpolation, falls on **under 5 per cent** of points with a median gain of
+0.88 to +2.66 m/s. That is the check that mattered and it passes.

The 100 → 200 m step falls on up to 28 per cent, and the fraction is the wrong
statistic: **23 to 46 per cent of those falls are under 0.1 m/s and 60 to 86 per
cent under 0.5**, against mean speeds of 5 to 10 m/s. In a well-mixed summer
boundary layer the profile is nearly flat, so the *sign* of a small difference is
noise — which is exactly why summer (26–28 %) looks worse than winter (14 %)
while nothing is worse about it.

The tail is real and is not a defect either: the 95th percentile of the falls
reaches **1.8 to 1.9 m/s** and the maximum 8.8 to 10.7 m/s, largest at 00Z in
winter. That is a nocturnal low-level jet, which is what a 3 km model should
produce and a 31 km one should not.

## `2d` is in kelvin — the GRIB1 defect is not present

The named risk for this family: wrf-python's `td2` defaults to **degrees
Celsius**, and the GRIB1 archive wrote it straight through under a paramId
defined in K. The converter now asks explicitly:

```python
for key, kwargs in (('td2', dict(units='K')), ('rh2', {}), ('slp', dict(units='Pa'))):
```

and the data agrees: `2d` runs 233.8 to 302.6 K over the sample and its bias
against ERA5 is **−0.02 K** with a ratio of means of **1.0000**. A field in degC
under this paramId would sit 273 K away. Verified.

### But `2d` exceeds `2t` at saturation, by 0.0134 K

| timestep | points with `2d > 2t` | max excess | of those, at RH 100 |
|---|---|---|---|
| 2024-01-15T00 | 64 005 | 0.01337 K | **100.0 %** |
| 2024-07-15T00 | 22 807 | 0.01337 K | **100.0 %** |
| 2024-07-15T12 | 6 161 | 0.01334 K | **100.0 %** |
| 2025-02-15T00 | 38 958 | 0.01337 K | **100.0 %** |

The same number at every timestep, and every violating point saturated: it is the
dewpoint inversion in wrf-python overshooting at exactly saturation, not noise. A
dewpoint above its own temperature is impossible whatever the size, so it is
recorded as [#42](https://github.com/meteocima/CHAPTER/issues/42), with the
recommendation to document rather than clip — clipping would cost the exact
consistency with `Q2` measured below.

## `2r` over the whole sample, with the definition it should have had

Family 1 established that `r` and `2r` are humidity over **liquid water, clipped
at 100** ([#40](https://github.com/meteocima/CHAPTER/issues/40)). For `r` on
pressure levels the phase is wrong too — ECMWF defines paramId 157 over the mixed
phase, measured. **For `2r` it is not**: decided 2026-09-22, `2r` stays over
liquid water with `2t` and `2d`, because that is the WMO convention for a
screen-level humidity at every temperature, because ERA5 publishes no 2 m
relative humidity at all so there is no ECMWF practice to follow, and because
nothing joins 2 m to the 1000 hPa level anyway
([#44](https://github.com/meteocima/CHAPTER/issues/44)). **So `2r`'s only defect
is the clip.**

Leg D therefore makes the reconstruction a user makes from the two neighbours,
both over water, re-run over all 34 timesteps
(`$WORK/CHAPTER/audit_rows/legd_2r_water.jsonl` — the sample-wide rows carry the
superseded formula and a complete row set is never overwritten):

| leg D formula | median | worst |
|---|---|---|
| `esat_water(2d)/esat_mixed(2t)`, the decision of the morning | 0.40 %RH | **26.2 %RH** |
| `esat_water(2d)/esat_water(2t)`, the decision that stands | **0.39 %RH** | **2.48 %RH** |

Ten times tighter at the tail, and the residual is now essentially the clip
itself plus the dewpoint round trip. After #40 removes the clip it should fall to
the round trip alone: `2d` and `Q2` are mutually consistent to **3.6e-4 to
1.1e-2** relative in vapour pressure across the whole sample. That number is
family 2's, and it is what makes the reconstruction legitimate.

**The clip was removed on 2026-09-25** and the decision survived the repair
intact. `2r` is now computed in the converter from the model's own `Q2`, `PSFC`
and `T2` through `ifs_humidity.relative_humidity_over_water` — the saturation
unchanged, only the `MIN(qv/qvs, 1)` gone. Measured on the two verification
files:

| | 2024-07-15T12 | 2024-07-15T00 |
|---|---|---|
| maximum | **100.1218** | **100.1221** |
| points above 101 | 0 | 0 |
| points within 1e-4 of exactly 100 | **67** | 107 |

Against **18 316** piled at exactly 100 on the 12Z file before, which is the
clip's own signature and the thing that could never be seen in the packed maxima.
The maximum lands on the 100.2 measured here over all 34 timesteps, so nothing
about the field's magnitude changed — only that it is no longer truncated.

Worth recording that the repair had to be undone once: `r` and `2r` were both
given the mixed phase, following the literal text of #40's fix section, which had
overtaken this decision by three days. The measurement above is what caught it.

One correction to make in the other direction. This document first said the old
leg D — a Magnus ratio over liquid water — "confirmed nothing". That is too
strong for `2r`: under the decision that stands it was measuring the right ratio.
What it could not do was *distinguish* the clip from ordinary scatter, because at
2 m the clip removes at most about 2 %RH, which is inside the spread it reported.
The sharper criticism belongs to `r` on pressure levels, where the phase is wrong
by a factor of up to 1.8 and the check was built from the same wrong assumption.

**The price, which belongs where a data user meets it:** `r` and `2r` use
different saturations — mixed phase aloft, liquid water at the screen. A reader
who takes them as the same quantity will be wrong at cold points.

## `vwsh`: exact, and the layer is ours

`vwsh` is `sqrt((100u−10u)² + (100v−10v)²) / 90`, the bulk shear over the 10–100 m
layer. Leg D restates the converter's own formula, so it checks the encoding
rather than the physics, and it is **exact at all 34 timesteps**: worst relative
difference **5.39e-07**, worst absolute **6.6e-08 s⁻¹** against a field reaching
0.263 s⁻¹.

ECMWF's paramId 260068 is *Vertical speed shear*, `s**-1`, and **names no layer**.
The 10–100 m layer is our choice, declared in the registry's `long_name` and
encoded as `heightAboveGround` level 100. A user reading the message sees
"Vertical speed shear at 100 m" and cannot tell which layer it spans — the same
shape of problem as `slor` in family 7, and it belongs in the archive's own
documentation.

ERA5 does not publish it, and the crosswalk's reason — "no vertical speed shear
at any level" — is a claim about ERA5's catalogue rather than about what ECMWF
defines, which is the distinction
[#17](https://github.com/meteocima/CHAPTER/issues/17) found four reasons failing.
It passes.

## `200u`/`200v`: the weakest verdict in the family, and it says so

ERA5 publishes winds at 10 m and 100 m only, so there is no counterpart and leg B
does not exist. Leg D offers a **bracket**, declared weak when it was built: the
200 m wind should not generally be slower than the 100 m one, and the two vectors
should be nearly parallel. Over the sample, 81.8 per cent non-falling and 87.5 to
99.0 per cent within 20°.

What now supports them more than that bracket is the section above: they come
from the same `interplevel` call as `100u`/`100v` on a column whose lowest level
is 25 m, they never extrapolate, and the 1000 hPa cross-check lands between them
and the 100 m winds on nine points in ten. **The method is verified even where
the field cannot be.**

## What this family contaminates

- **Nothing new.** `2r`'s defect is [#40](https://github.com/meteocima/CHAPTER/issues/40),
  already filed by family 1 and already reflected in the harness.
- **[#43](https://github.com/meteocima/CHAPTER/issues/43) is about the instrument**,
  not the archive: the remaining families (3, 4, 5, 8) will meet the same
  misleading ratio column and should read the rows, not the summary.
- **Family 8 ([#26](https://github.com/meteocima/CHAPTER/issues/26))** can reuse
  two results rather than re-measure them: the lowest mass level is at 21–28 m
  above ground at every timestep of the sample, which bears on `zust` and the
  stress components, and `2t`/`10u`/`10v` are exact under leg B, which bears on
  the `iews`/`inss` construction that uses `U10`, `V10`, `T2` and `Q2`.
