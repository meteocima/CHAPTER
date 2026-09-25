# Family 8: surface exchange, pressure and instability

Nine fields: `skt` `sp` `msl` `iews` `inss` `zust` `fsr` `mucape` `mucin`.

Measured over the 34-timestep sample plus six 12Z timesteps chosen to put snow
under the `skt` claim. Harness rows in `$WORK/CHAPTER/audit_rows/rows_*.jsonl`
(306 for this family); the measurements the harness cannot make are
`tools/audit/f8_surface.py`, output beside the rows as `f8_surface.json`,
`f8_legc.json`, `f8_probe.json`, `f8_cin.json` and `f8_selfcheck.json`.

This is the family with the fewest independent sources: **six of the nine have
no leg B at all**, because `skt`, `msl`, `iews`, `inss`, `mucape` and `mucin`
are the converter's own derivations. Three of them turned out to have one
anyway, for the same reason family 3's column integrals did — the model wrote
down enough to check the answer a second way.

**Eight of the nine are verified. `mucin` is not**: on 71 to 96 per cent of the
domain it is the literal constant 0, and 0 there means the opposite of the truth
([#54](https://github.com/meteocima/CHAPTER/issues/54)). Three further findings
are properties of the run or of definitions, not conversion defects
([#55](https://github.com/meteocima/CHAPTER/issues/55),
[#56](https://github.com/meteocima/CHAPTER/issues/56),
[#57](https://github.com/meteocima/CHAPTER/issues/57)).

## The table

| variable | paramId | leg A | leg B | leg C | verdict |
|---|---|---|---|---|---|
| `sp` | 134 | ok | **exact**, `PSFC` | 1.000–1.001, corr 0.99 | **verified** |
| `msl` | 151 | ok | **agrees with `sp` at sea level to 25–34 Pa (p99)** | 1.000–1.001, corr 0.99 | **verified** |
| `skt` | 235 | ok | **0.0005 K RMSE against SST over water** | sea **+0.01 K**, land **−1.64 K**, corr 0.98 | **verified**, → [#55](https://github.com/meteocima/CHAPTER/issues/55), [#57](https://github.com/meteocima/CHAPTER/issues/57) |
| `iews` | 229 | ok | **identity**, ρu\*² to 1.8e-6 | corr **+0.80 … +0.89**, sign 0.87–0.92 | **verified** |
| `inss` | 230 | ok | **identity**, ρu\*² to 1.8e-6 | corr **+0.82 … +0.89**, sign 0.87–0.92 | **verified** |
| `zust` | 228003 | ok | **exact**, `UST` | sea 1.08–1.12, **land 1.62–2.06** | **verified**, → [#56](https://github.com/meteocima/CHAPTER/issues/56) |
| `fsr` | 244 | ok | **exact**, `ZNT` | **land 0.32–0.48 (median)**, sea 1.5–1.9 | **verified**, → [#56](https://github.com/meteocima/CHAPTER/issues/56) |
| `mucape` | 228235 | ok | parcel fixed by the Fortran | 0.52–2.05 where ERA5 active | **verified** |
| `mucin` | 228236 | ok | parcel fixed by the Fortran | **0.03–0.24, and 0 against 25–265 J/kg where filled** | **wrong** → [#54](https://github.com/meteocima/CHAPTER/issues/54) |

No leg A failure, no bitmap, no missing point, at any of the 34 timesteps.

### The sphere, on all 246 messages

The ticket asked for it explicitly. At six timesteps, **every one of the 246
messages** carries `shapeOfTheEarth = 1` with `radius = 6370000.0`. WRF's own
sphere is declared on the whole file, not only on the fields this family owns.

## `skt`: the emissivity identity holds, exactly

`TSK` was not written out, so the skin temperature is inverted from
`LWUPB = eps·σT⁴ + (1−eps)·LWDNB`. The emissivity is not assumed: RRTMG's
clear-sky diagnostic shares that equation's `eps` and `T` and differs only in the
downward flux, so

    eps = 1 − (LWUPB − LWUPBC) / (LWDNB − LWDNBC)

with the temperature eliminated. That makes the published `WRF_EMISS` table
**falsifiable at every cloudy point of every file**, and it was re-tested here on
six timesteps across the seasons rather than the one it was derived from.

### The table is exact

2024-01-15T12 and 2024-07-15T12, every category present on land:

| category | median measured | table | difference | IQR |
|---|---|---|---|---|
| 1, 2 | 0.95000 | 0.95000 | 5e-8 | 1.1e-6 |
| 4, 6, 8 | 0.93000 | 0.93000 | 3e-8 | 1.2e-6 |
| 5 | 0.94000 | 0.94000 | 1e-7 | 1.5e-6 |
| **7, 13** | **0.88000** | 0.88000 | 0 | 1.8e-6 |
| 9, 10 | 0.92000 | 0.92000 | 3e-8 | 1.0e-6 |
| **12** | **0.93500** | 0.93500 | 6e-8 | 1.4e-6 |
| 15 | 0.98000 | 0.98000 | 5e-8 | 7e-7 |
| **16 (barren)** | **0.85000** | 0.85000 | 0 | 7.4e-6 |
| 17 (water) | **0.98000** | 0.98000 | 2e-8 | 1.3e-6 |

Every median matches to 1e-7 or better, IQR ~1e-6, winter and summer alike. The
four categories that disagree with VEGPARM's `EMISSMIN` — 3 and 5 at 0.940, 7 at
0.880, 12 at 0.935, 16 at **0.850 against the table's 0.900** — are confirmed
again on the wider sample. Over water it is **0.98000 with an IQR of 1.3e-6**,
which is the independent gate, since water's emissivity is known.

The refuted green-fraction hypothesis stays refuted: the correlation of the
measured `eps` with `VEGFRA`, within category, is recorded per timestep and is
not what a `EMISSMIN + shdfac·(EMISSMAX−EMISSMIN)` blend would produce.

### The water gate is three times better than recorded, and the land claim is seasonal

| | recorded claim | measured here |
|---|---|---|
| water gate, skt vs SST | 0.0015 K | **0.0005 K RMSE, bias −0.0002 K, absmax 0.002 K**, on ~910 000 points, all six timesteps |
| land, reproduced to 1e-4 | 97.96 % | **99.98 % in July, 93.05 % in January** |
| land skt RMSE (table eps vs measured eps) | 0.032 K | **0.0012 K in July, 0.115–0.133 K in January and February**, p99 0.85 K, absmax 2.8 K |

The recorded numbers were measured on a **summer** file. On that class of file
the inversion is better than claimed; on the snowiest sampled day it is four
times worse, and the whole of the difference is the snow rule.

### The snow switch fires about a hundredth too early

The identity gives the truth at every cloudy point, so the rule can be read off
rather than asserted. Binned by snow cover, 2024-01-15T12, showing where the
measured emissivity sits between the bare-soil value and 0.98:

| `SNOWC` | n | median eps | bare value | position between them |
|---|---|---|---|---|
| 0.000–0.005 | 315 199 | 0.93498 | 0.93500 | **0.000** |
| 0.005–0.010 | 4 164 | 0.93539 | 0.93500 | 0.008 |
| **0.010–0.020** | **7 340** | **0.94066** | 0.93500 | **0.016** |
| 0.020–0.050 | 21 381 | 0.98000 | 0.93500 | **1.000** |
| above 0.05 | 348 970 | 0.98000 | 0.93500 | **1.000** |

It **is** a switch and not a blend — the position jumps from 0.016 to 1.000
between the 0.01–0.02 bin and the next — but the converter switches at
`SNOWC ≥ 0.01`, and the data says the transition completes between 0.02 and
0.05. In the 0.010–0.020 bin only **45.6 per cent** of points are at 0.98; the
converter puts all of them there.

Scored against the alternatives on the same points, the current rule is still
the best of those tested (January: current **0.940**, pure blend 0.692, no snow
rule 0.439, a plain switch at any single threshold 0.76–0.93), so this is a
refinement and not a replacement.

### I checked whether that miss was my own estimator, and it mostly is not

`eps` is a ratio of two differences of packed fluxes: where the clear-sky and
all-sky downward fluxes are close, the denominator is small and the quotient is
noise. Reporting a "fraction within 1e-4" at one arbitrary cut would let a noisy
estimator be read as a wrong rule — the trap family 1's below-ground humidity
fell into. So the fraction is reported against the denominator:

| `|LWDNB−LWDNBC|` cut | n (Jan) | land within 1e-4 | snow within 1e-4 | median abs residual |
|---|---|---|---|---|
| > 1 W/m² | 717 054 | 0.9399 | 0.8921 | 6.6e-7 |
| > 10 | 569 941 | 0.9559 | 0.9277 | 5.0e-7 |
| > 50 | 399 572 | 0.9719 | 0.9564 | 3.9e-7 |

**The median residual is 4 to 7 parts in ten million** — the rule is exact where
it is right. Tightening the cut by fifty times moves the reproduction fraction
by only three points, so the tail is a real population and not noise. On
2024-10-15 the snow fraction is **0.458 and does not move at all** with the cut,
which is the low-snow-cover transition above, seen from the other side.

## `msl`: verified, after correcting my own mask

`msl − sp` correlates with orography at **0.9994–0.9995** and `msl ≥ sp` at every
land point above 10 m — 0 violations, six timesteps.

My first sea-level test reported excursions of 5 752 Pa and looked like a defect.
It was the mask: `HGT < 1.0` admits **negative** heights. Corrected to
`|HGT| < 0.5` on water, 850 461 points:

| | |
|---|---|
| absolute maximum `|msl − sp|` | **100–133 Pa** |
| p99.9 | **43 Pa** |
| p99 | 25–34 Pa |
| mean | **−12 to −18 Pa** |

The 8 545 excursions above 1 000 Pa are all inland water at altitude or below
sea level — `HGT` from **−466 m** (the Dead Sea) to **+3 171 m** — where
`msl ≠ sp` is arithmetic, not error. The residual −0.15 hPa systematic at true
sea level is wrf-python's own `slp` smoothing and is recorded, not filed.

## `iews` / `inss`: the sign is ERA5's, and the alignment assumption is priced

The stress is `ρu*²` aligned with the 10 m wind. The magnitude is the model's
own similarity theory; only the **alignment** is ours.

Internal consistency, six timesteps:

| check | worst |
|---|---|
| `|τ|` against `ρ u*²` | **1.8e-6 N/m²** |
| `zust` against `sqrt(|τ|/ρ)` | **2.7e-4 m/s** |
| angle between our stress and `U10` | p99 **0.003°**; the 4–10 k points above 0.01° all have wind below 0.014 m/s, the calm cut-off |

Against ERA5: correlation **+0.80 to +0.89** on both components with **87–92 per
cent sign agreement**, and `|τ|` at 0.90–1.26 with corr 0.73–0.80. A flipped
convention would give correlation near −0.85. **The sign is right.**

And the assumption can be priced, because ERA5 publishes both its stress and its
10 m wind, so the angle between them is measurable on ERA5 itself:

| | median | p90 | p99 |
|---|---|---|---|
| ERA5's own stress vs ERA5's own 10 m wind | **0.92–1.10°** | 5.1–8.6° | **28–57°** |

So aligning the stress with the 10 m wind is worth about **one degree in the
median** and can be tens of degrees in the tail. That is the honest bound
`MISSING_VARIABLES.md` asserts without a number, and it is a small assumption.

## `fsr` and `zust`: the same physics, two definitions

| | ours | ERA5 | ratio of means | ratio of medians |
|---|---|---|---|---|
| `fsr`, land | 0.188–0.217 m | 0.375–0.394 m | 0.48–0.55 | **0.32–0.48** |
| `fsr`, sea | 0.0089–0.0091 m | 0.0103–0.0105 m | 0.85–0.88 | 1.5–1.9 |
| `zust`, land | 0.44–0.52 m/s | 0.23–0.28 m/s | **1.62–2.06** | |
| `zust`, sea | 0.21–0.34 m/s | 0.19–0.31 m/s | **1.08–1.12** | corr 0.85–0.90 |

The split is the answer. **Over sea the two agree**: both are Charnock roughness
and both friction velocities land within 12 per cent, correlation 0.9. **Over
land they diverge in opposite directions** — our roughness is a third of ERA5's
while our friction velocity is twice it — which cannot both be true of the same
`z0`. It is not one field being wrong: ERA5's `fsr` is an **effective** roughness
carrying the orographic drag that IFS parameterises, while WRF's `ZNT` is the
local surface roughness of the land-use class, with the orography resolved
instead of parameterised.

`ZNT` confirms it directly: it is a land-use lookup with a snow override, one
value per category — 0.70 m for the forest classes, 0.15 for 8 and 9, 0.065 for
barren, **1.00 m on exactly 19 867 points, all of them category 13, urban** —
and a floor of 0.011 m where snow covers the surface. Nothing is capped or
clipped; the field is what MODIS and `LANDUSE.TBL` say.
[#56](https://github.com/meteocima/CHAPTER/issues/56).

## The finding: `mucin` is a constant on most of the domain

`cape_2d`'s Fortran (`fortran/rip_cape.f90`, lines 587–589 and 731) fixes the
parcel: *"CAPE and CIN only for the parcel with max theta-e in the column… a
500-m deep parcel… find parcel with max theta-e in lowest 3 km agl"*. Most
unstable, mixed over 500 m, searched in the lowest 3 km. ERA5's is also
most-unstable but uses **undiluted single-level parcels below 350 hPa** — a
different parcel, and the comparison has to be read knowing that.

That is not the problem. The problem is what happens where the Fortran declines
to answer. **It flags CIN missing wherever CAPE < 100 J/kg**, and `dense()`
writes **zero** there:

| timestep | CIN is a real number on | filled with zero | ERA5's CIN where we are >95 % fill |
|---|---|---|---|
| 2024-01-15T12 | **3.8 %** | 96.2 % | **41.0 J/kg** |
| 2024-02-15T12 | 5.7 % | 94.3 % | **85.6 J/kg** |
| 2024-03-15T12 | 4.8 % | 95.2 % | 24.7 J/kg |
| 2024-07-15T12 | **28.8 %** | 71.2 % | **264.9 J/kg** |
| 2024-10-15T12 | 15.2 % | 84.8 % | **239.2 J/kg** |
| 2025-02-15T12 | 5.5 % | 94.5 % | 66.7 J/kg |

Zero is defended in `MISSING_VARIABLES.md` as "the physical reading (no
available energy, no inhibition)". For **CAPE** that is right: no CAPE is no
available energy. For **CIN it is backwards.** A column with no CAPE is normally
a column with a great deal of inhibition — that is usually *why* there is no
CAPE — and the archive writes 0, which reads as "nothing is stopping
convection", precisely where the most is.

ERA5 masks the same field rather than filling it, which is what makes the price
measurable: where we are essentially all fill, ERA5 carries **25 to 265 J/kg**.
And even where our CIN is real the ratio is **0.03 to 0.24**, because our CIN
exists only in columns with CAPE ≥ 100 — the *least* inhibited ones — while
ERA5 reports it more widely.

`mucape` is untouched by this: its zero fill is 46–80 per cent of the domain but
zero is the correct reading, and where ERA5 is active the ratio is 0.52–2.05
with correlation 0.24–0.75, which is parcel choice and 3 km spikiness, not a
factor. `mucin` is never negative and is never non-zero where `mucape < 100` —
both confirmed at every point of every timestep, so the construction is exactly
what the code says.
[#54](https://github.com/meteocima/CHAPTER/issues/54).

## The land skin temperature, and a tension with family 4

`skt` against ERA5, mean over the 34-timestep sample:

| region | bias |
|---|---|
| sea | **+0.01 K** |
| land | **−1.64 K**, reaching −3.24 K at midday in September |
| correlation | 0.95–0.98 |

The sea number is the control: over water the model's skin temperature is the
SST and both reanalyses see nearly the same one, so +0.01 K says the inversion
and the encoding are not the cause of anything. The land bias is the run.

It sits awkwardly against
[#45](https://github.com/meteocima/CHAPTER/issues/45) and
[#48](https://github.com/meteocima/CHAPTER/issues/48): we deliver **8.5 per cent
more clear-sky surface solar** than ERA5 and **22 per cent less cloud**, both of
which put more energy into the land surface, and the land skin comes out
**colder** at midday. Reconciling that needs the surface energy budget, and
`HFX`, `LH` and the ground heat flux are the three fields this archive does not
have (`MISSING_VARIABLES.md`). **It is recorded as an open tension, not
explained.** [#57](https://github.com/meteocima/CHAPTER/issues/57).

## What this family contaminates

- **Nothing in the other seven.** Every finding here is confined to its own
  variable: `mucin`'s fill is one message, `fsr`/`zust` are definitions, the
  `skt` numbers are a documentation correction.
- **[#12](https://github.com/meteocima/CHAPTER/issues/12)'s emissivity work is
  confirmed, not corrected.** The measured table, the four categories that
  disagree with `EMISSMIN`, the 0.850 for barren and the snow switch all survive
  the wider sample. Only the accuracy *figures* attached to them were
  season-specific.
- **Family 4's `str`/`strc`** rest on the same `LWUPB`/`LWDNB` pair this
  inversion uses; nothing here disturbs them, and the emissivity identity is an
  independent confirmation that those four fields are self-consistent.

## What was *not* measured

- **Five land-use categories never occur in this domain** and keep `EMISSMIN`
  unmeasured. The sample adds no new categories: the sixteen present in January
  are the sixteen present in July.
- **Why the land skin is cold.** Stated as a tension; the fields that would
  settle it are not in the archive.
- **`mucape` against a matched parcel.** ERA5's parcel is not ours and cannot be
  made so from what is published; the comparison is reported as a bracket.
