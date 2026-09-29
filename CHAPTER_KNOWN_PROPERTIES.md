# CHAPTER 3 km reanalysis — known properties of the archive

Third of the three documents that ship with this archive. `CHAPTER_VARIABLES.md` says what is
in the files; `MISSING_VARIABLES.md` says what is not and why. This one answers the question
neither of those asks: **what is in the files that will surprise you.**

Everything below is a property of the data as delivered. None of it is a defect awaiting
repair: the defects the audit found were repaired before the archive was produced, and they
are not listed here. What is listed is the archive behaving correctly in ways a user comparing
it against ERA5, against observations, or against their own expectations will otherwise
discover alone — and, having discovered one, will reasonably stop trusting the rest.

Every number here was measured, not estimated. They come from a variable-by-variable audit run
in September 2026 over a **34-timestep sample** spanning both sampled years and all four
seasons (the sample is listed in `docs/audit/sample.md`); where a comparison against ERA5 is
quoted, our 3 km field was upscaled to the ERA5 grid first. Each entry links to the issue that
holds the measurement and the method.

## How to read this document

Section 0 is the short list: the things that change what you do, in one line each. The rest
states each property in full, with its number and what to do about it.

Two kinds of entry are mixed together deliberately, because a user does not care which is
which:

- **properties of the run** — the model was configured a certain way and the data reflect it.
  Nothing can be done after the fact; the run would have to be repeated.
- **properties of the conversion** — a deliberate convention, chosen and documented. These
  could be changed, and the entry says what was chosen instead and why.

## Which archive this describes

The GRIB2 archive, `grib_v3`, **246 messages per hourly file**, as produced by the converter
from 2026-09-29 onward. (The six repairs below landed on 2026-09-25; one further change on
2026-09-29 moved the snow-emissivity threshold, which shifts `skt` over snow-covered land by
about 0.05 K RMSE and is already reflected in the figures in section 4.) Files written before that date carry six defects that were repaired on
that date — relative humidity, specific humidity, the column integrals, snowfall, the water
masks and convective inhibition. They are listed in the repository's audit record
(`docs/audit/re-verification.md`) and are **not** properties of this archive. If you hold
files from before the rebuild, replace them rather than reconciling them.

## 0. The short list

| # | Property | The number |
|---|---|---|
| 1.1 | Surface shortwave is high under clear sky: the run carried **no aerosol** | **+8.5 %** clear-sky, +13.6 % all-sky vs ERA5 |
| 1.2 | Total cloud cover is low, high cloud lowest — it is `CLDFRA`, not the overlap | **0.78** and **0.61** of ERA5 |
| 1.3 | Land skin temperature is cold, and the archive cannot say why | **−1.64 K** mean, **−3.24 K** at midday |
| 2.1 | `fsr` is WRF's **local** roughness, ERA5's is **effective** | **0.32–0.48** of ERA5 over land |
| 2.2 | `zust` over land responds to resolved terrain | **1.6–2.1×** ERA5 over land, 1.1× over sea |
| 3.1 | **`r` and `2r` saturate differently, and each is right** | mixed phase vs liquid water |
| 3.2 | `r` above 100 % is normal and is not clipped | up to **139.7 %** at 300 hPa |
| 3.3 | Humidity rebuilt from `2t` and `2d` overshoots at saturation | peaks at **100.09 %** |
| 4.1 | Below ground the pressure levels are **clamped**, not extrapolated — ERA5 extrapolates | affects **47.6 %** of the domain at 1000 hPa |
| 4.2 | `z` is exactly `9.80665 × z_WRF`; WRF integrated with 9.81 | **0.034 %** off hydrostatic balance |
| 5.1 | `10fg` is the resolved 10 m wind, **not a gust parameterisation** | **0.625** of ERA5's gust |
| 5.2 | Its declared one-hour window is right **88 %** of the time | excess **0.499–0.784 m/s** on the bad hours |
| 6.1 | Three runoff variables carry one field's information | `ssro` non-zero at ≤ **19** points |
| 6.2 | `tcw` sums **six** species where ECMWF defines five | graupel residual to **26 kg/m²** |
| 7.1 | One masking rule: a point is missing where the ERA5 parameter is undefined | bitmaps, never zeros |
| 7.2 | `mucin` is **masked**, not zero-filled, where the scheme declined | missing on **71–96 %** of the domain |
| 8.1 | `generatingProcessIdentifier = 128` marks **every** message and discriminates nothing | 246 of 246 |
| 8.2 | `al` is a two-season table value by category, not a continuous field | 8–11 distinct values domain-wide |
| 8.3 | `slor` is the slope of the **resolved** 3 km terrain, not of sub-grid orography | eccodes shows the ECMWF name |

---

## 1. Radiation, cloud and the surface energy budget

These three belong together. Read any one of them alone and you will predict the other two
wrongly.

### 1.1 Surface shortwave is 8.5 % high under clear sky, because the run carried no aerosol

RRTMG ran with a CAM ozone climatology and **no aerosol at all** (`aer_opt = 0`). ERA5 carries
the Tegen aerosol climatology. Over this domain — Europe, the Mediterranean and the Saharan
margin — an aerosol optical depth of 0.1 to 0.2 attenuates the direct beam by about the amount
measured.

Ratio of means against ERA5 over the sample:

| field | ours / ERA5 |
|---|---|
| `ssrdc` surface solar down, **clear sky** | **1.085** |
| `ssrd` surface solar down, all sky | **1.136** |
| `ssrc` surface net solar, clear sky | 1.116 |
| `ssr` surface net solar, all sky | 1.178 |
| `tsrc` top net solar, clear sky | 1.031 |
| `strd`, `strdc` downward thermal | 0.989, 0.996 |
| `ttr`, `ttrc` outgoing thermal | 1.009, 0.990 |

The decomposition is the useful part: the clear-sky figure isolates the atmosphere with no
cloud involved, and the thermal fields — untouched by aerosol — agree with ERA5 to within
1.1 %, which is the control that makes the attribution credible rather than a guess.

**What to do.** If you use this archive for solar resource, for an energy application, or as
training data against pyranometer observations, expect a systematic high bias in surface
shortwave of about this size. It is a property of the run and cannot be removed after the
fact. Measured in [#45](https://github.com/meteocima/CHAPTER/issues/45).

### 1.2 Total cloud cover runs 22 % below ERA5, and high cloud 39 % below

Sample means, upscaled to the ERA5 grid:

| | ours | ERA5 | ratio |
|---|---|---|---|
| `tcc` | 0.381 | 0.487 | **0.783** |
| `hcc` | 0.169 | 0.276 | **0.610** |
| `mcc` | 0.161 | 0.205 | 0.786 |
| `lcc` | 0.231 | 0.268 | 0.862 |
| `tciw` | 0.0185 | 0.0166 | **1.109** |

The deficit holds at **every one of the 34 timesteps**, both years, every month.

**It is not the overlap assumption, and that was checked first.** The converter uses
maximum-random overlap where ECMWF uses exponential-random, which would yield more cover — the
right direction. But random overlap is the *most* total cover any assumption can extract from a
given profile, and computed point by point on our own `CLDFRA` the entire span of possible
assumptions is only **2 to 4 % wide**, because `CLDFRA` is strongly bimodal. ERA5 is 28 % above
us. The overlap accounts for at most a seventh of the gap.

The gap is in `CLDFRA` itself — WRF's Xu–Randall diagnostic under `ICLOUD = 1`. The sharpest
statement of it: **we carry 11 % more cloud ice than ERA5 and diagnose 39 % less high cloud.**
The condensate is there; the fraction the scheme assigns to it is not.

**One caveat, stated rather than buried.** Part of the gap is resolution. Our `tcc` is
overlapped at 3 km and then averaged to 31 km; ERA5's is overlapped on an already-smooth 31 km
profile, which yields somewhat more cover. That effect is bounded by the same 2–4 % span, so it
cannot account for 22 % — but it is real, and the figure should not be quoted as if it were all
model error. Measured in [#48](https://github.com/meteocima/CHAPTER/issues/48).

### 1.3 Land skin temperature runs 1.6 K below ERA5, 3.2 K at midday — and this contradicts the two above

`skt` against ERA5, mean over the whole sample:

| region | bias | correlation |
|---|---|---|
| **sea** | **+0.01 K** | 0.95–0.98 |
| **land** | **−1.64 K**, reaching **−3.24 K** at midday | 0.95–0.98 |

At 00Z the land bias is −0.5 to −1.2 K; at 12Z it is −0.8 to −3.2 K.

**The sea number is the control.** Over open water the model's skin temperature *is* the SST,
and both reanalyses see nearly the same one. A bias of +0.01 K there says the derivation, the
emissivity and the encoding are not the cause of anything (see 2.3): the land bias is the run.

**And it pulls against §1.1 and §1.2.** More shortwave reaching the ground and less cloud
overhead both put energy *into* the land surface, and the surface comes out colder — most so at
the hour when the excess solar is largest. That is not a contradiction in the measurements; it
is an unexplained partition, and reconciling it needs the surface energy budget. **`HFX`, `LH`
and the ground heat flux are precisely the three fields this archive does not have** (see
`MISSING_VARIABLES.md`), so it cannot be settled from the published data. Candidates that
cannot be separated: the land-surface scheme partitioning more of the available energy into
latent heat, a different soil-moisture climate, the resolved 3 km orography raising the mean
elevation of an upscaled land cell, or a genuine cold bias.

**What to do.** If you use `skt` over land for evaluation, bias correction, or ML training
against satellite land surface temperature, apply the number. Do not predict a warm land
surface from the radiation findings — the archive does the opposite. Measured in
[#57](https://github.com/meteocima/CHAPTER/issues/57).

---

## 2. Surface exchange

### 2.1 `fsr` is a local roughness where ERA5's is effective

| | ours | ERA5 | ratio of medians |
|---|---|---|---|
| `fsr`, **land** | 0.188–0.217 m | 0.375–0.394 m | **0.32–0.48** |
| `fsr`, sea | 0.0089–0.0091 m | 0.0103–0.0105 m | 1.5–1.9 |

ERA5's `fsr` is an **effective** roughness that carries the orographic drag the IFS
parameterises at 31 km. WRF's `ZNT`, which is what this field is, is the **local** surface
roughness of the land-use class — the orography is resolved at 3 km instead of parameterised.
Over sea the two agree, because both are Charnock.

`ZNT` is a land-use lookup with a snow override: one value per category — 0.70 m for the forest
classes, 0.15 for savannas and grassland, 0.065 for barren, exactly 1.00 m on the 19 867 urban
points — with a floor of 0.011 m where snow covers the surface. Nothing is capped or mis-scaled.

**What to do.** Do not take `fsr` from this archive and `fsr` from ERA5 as the same quantity:
over land they differ by a factor of two to three. A drag coefficient computed from ours and
compared against one computed from ERA5's will show a discrepancy that is not physical.
Measured in [#56](https://github.com/meteocima/CHAPTER/issues/56).

### 2.2 `zust` runs 1.6 to 2.1 times ERA5's over land, and agrees over sea

| | ours | ERA5 | ratio |
|---|---|---|---|
| `zust`, **land** | 0.44–0.52 m/s | 0.23–0.28 m/s | **1.62–2.06** |
| `zust`, sea | 0.21–0.34 m/s | 0.19–0.31 m/s | **1.08–1.12**, corr 0.85–0.90 |

This is the other half of §2.1's story, and the split is what identifies it: our roughness is a
third of ERA5's while our friction velocity is twice it, and those cannot both be a scaling
error on the same `z0`. At 3 km the terrain-driven wind is resolved rather than smoothed, and
the friction velocity responds to it. The excess is largest at midday — 1.06–1.13 at 00Z
against 1.40–1.75 at 12Z, in every region.

The field is internally consistent with the published stresses: `|τ| = ρu*²` holds to
1.8e-6 N/m² and `zust = sqrt(|τ|/ρ)` to 2.7e-4 m/s, at every point of every timestep checked.
Measured in [#56](https://github.com/meteocima/CHAPTER/issues/56).

### 2.3 `skt` is derived, its accuracy is known, and it is seasonal

`TSK` was not written out by the run, so `skt` is inverted from the upward longwave flux:
`LWUPB = ε σ T⁴ + (1−ε) GLW`, with the per-category emissivity **measured from the run itself**
rather than looked up in a table. The derivation is verified; what is seasonal is how well it
reproduces the model's own state:

| | figure |
|---|---|
| water gate — `skt` against the model's own SST | **0.0005 K RMSE**, absmax 0.002 K, ~910 000 points, every timestep |
| land points reproduced to 1e-4 | **99.98 % in July … 93.05 % in January** |
| land `skt` RMSE from the emissivity table | **0.0012 K in July … 0.084–0.119 K in January and February**, p99 0.81 K, absmax 2.79 K |

The whole of the seasonal spread is the snow rule: emissivity switches to a flat 0.98 under
snow, and the switch is applied slightly earlier than the model's own transition completes.
Over water, where the answer is known independently, the derivation is exact.

**What to do.** Treat `skt` over water as the model's SST to a thousandth of a kelvin. Over
land in winter, allow a tenth of a kelvin of derivation error on top of the physical bias of
§1.3 — the two are unrelated and the derivation error (at most 0.119 K RMSE, in February) is more
than ten times smaller. Measured in
[#55](https://github.com/meteocima/CHAPTER/issues/55).

---

## 3. Humidity — read this before using `r` or `2r`

### 3.1 `r` and `2r` saturate against different phases, and each is right for what it is

This is the single most likely misreading of the archive, so it gets the plainest sentence
available:

> **`r` (paramId 157, pressure levels) is relative humidity over the mixed phase.
> `2r` (paramId 260242, 2 m) is relative humidity over liquid water at every temperature.
> They are not the same quantity and will not agree at cold points.**

The reason is that each follows its own definition rather than a single house convention:

- **`r`** is ECMWF's paramId 157, which saturates over ice below 250.16 K, over water above
  273.16 K, and quadratically between. The archive computes it from IFS Cy41r2's own equations
  (7.5, 7.6, 7.89, 7.90) with every constant taken from that cycle — the one ERA5 was produced
  with — so it is directly comparable with ERA5's `r`. Over ice the mixed-phase and
  over-water definitions differ by up to a factor **1.8**.
- **`2r`** follows the **WMO screen convention**, which saturates over liquid water at all
  temperatures. ERA5 publishes no 2 m relative humidity, so there is no ERA5 field to follow;
  the choice is the meteorological standard for a screen-level observation, which is what a 2 m
  humidity is compared against.

**What to do.** Do not build a profile that puts `2r` at the bottom of `r`. Do not compute a
vertical humidity gradient across the two. If you need them on one convention, recompute the
one you need from `q`, `t` and `sp` — all three are published. Decided and measured in
[#40](https://github.com/meteocima/CHAPTER/issues/40).

### 3.2 `r` above 100 % is normal, not a defect

There is no clip. Supersaturation is physical, the model produces it, and ERA5 publishes it too
— so the archive publishes it. Measured on a single file: **139.7 % at 300 hPa** in the ice
regime, and **34 785 points above 100 %** at 400 hPa.

Below ground, values reach further still — up to about 163 % — and that is the clamping of §4.1
rather than the humidity: the lowest model level's moisture, from 24 to 27 m above the
terrain (§4.1), read at a nominal pressure of 1000 hPa. See §4.1 before treating it as a moisture
error.

If your ingest pipeline rejects relative humidity above 100, it will reject valid data from
this archive. Measured in [#40](https://github.com/meteocima/CHAPTER/issues/40) and
[#44](https://github.com/meteocima/CHAPTER/issues/44).

### 3.3 Humidity reconstructed from `2t` and `2d` peaks at 100.09 %

At saturated points `2d` exceeds `2t` by a fixed **0.0133 K**, on 6 000 to 64 000 points per
timestep. Every violating point is at relative humidity 100 — it is the dewpoint inversion
overshooting by a constant at exactly saturation, and the constant is the same number at every
timestep in every season, which is what identifies it as arithmetic rather than noise.

It was left in place deliberately. Clipping `2d` to `2t` would remove the visible crossings
while leaving the same bias at every unsaturated point, put a kink in the field at RH 100, and
break the exact consistency between `2d` and `Q2` that the audit verified at 3.6e-4 to 1.1e-2
in vapour pressure. That trades a constraint for the appearance of one.

**What to do.** Expect a reconstruction that peaks a tenth of a per cent above saturation. If
you need a hard bound, clip your own reconstruction rather than reading it as an inconsistency
in the archive. Measured in [#42](https://github.com/meteocima/CHAPTER/issues/42).

---

## 4. Vertical structure

### 4.1 Below ground the pressure levels are clamped to the lowest model level — ERA5 extrapolates

Where a pressure level lies below the terrain, this archive publishes **the lowest model
level's value, verbatim**. It is not an extrapolation and not a fill: `t` matches the lowest
model level to **exactly 0.0** at 100 % of below-ground points, `q` to 1e-9, `z` to 2.5e-4 m.

There is a good half and a bad half, and both matter.

**The good half.** The number is a real model state from about 24 to 27 m above the ground, not
an invention. A user reading 1000 hPa over the Alps is reading near-surface air, which is a more
defensible thing to publish than a synthetic lapse-rate extrapolation. It is also why the
archive is coherent across the surface join: `2t − t(1000 hPa)` below ground is −0.9 K at
midnight and +1.4 K at noon in July, which is a nocturnal inversion and a superadiabatic
daytime surface layer over the ~22 m between the 2 m level and the lowest model level.

**The bad half.** `z` then contradicts `sp`. Where the surface pressure says the 1000 hPa
surface is underground, the published `z` at 1000 hPa puts it a median of **24 to 27 m above**
the terrain. Both messages are in the same file. Anyone deriving a height from `z`, or a
thickness between levels, meets that self-contradiction on **47.6 % of the domain at 1000 hPa**
and 9 % at 925 hPa.

**And ERA5 does not do this.** ERA5 extrapolates below ground with a lapse rate, so the two
archives differ in *convention* exactly where 1000 hPa is underground — which is most of the
land. This difference, not any defect, is the whole of the 1000 hPa discrepancy against ERA5:
a `t` bias of −1.71 K at 1000 hPa against −0.05 K at 850 hPa, and a `z` correlation of 0.108.

**What to do.** Mask the pressure levels against `sp` yourself if you need a clean comparison
against ERA5 or a thickness computation. Every field needed to do it is in the same file.
Measured in [#44](https://github.com/meteocima/CHAPTER/issues/44).

### 4.2 `z` is exactly 9.80665 × WRF's height, and the run integrated with 9.81

Both halves of this are true and a user will find one of them alone:

- **By construction**, the published geopotential is standard gravity times WRF's own
  geopotential height. Divide `z` by 9.80665 and you recover the model's height in metres,
  exactly — at the surface and on every pressure level, with no residual.
- **WRF integrated the hydrostatic equation with 9.81.** So the same archive sits **0.034 %**
  off hydrostatic balance against its own `t` and `p`. That is 1 part in 2 900: about 2 m at
  500 hPa, 7 m at 50 hPa.

Neither number can be removed without breaking the other. The convention chosen is the one that
makes `z` a correct ECMWF geopotential and makes the surface and pressure-level geopotentials
agree with each other exactly — which they do, verified point by point over 1 349 910 land
points. Measured in [#39](https://github.com/meteocima/CHAPTER/issues/39).

---

## 5. Wind

### 5.1 `10fg` is the strongest wind the model actually simulated, not an estimate of the gusts above it

**What ERA5 does.** A 31 km model cannot see a gust: the peak happens on scales of metres and
seconds it never represents. ERA5 therefore *estimates* it — the mean 10 m wind, plus a term
standing in for the turbulence the model has smoothed away, sized from the surface friction,
plus, in convective conditions, a term proportional to the wind shear between 850 and 950 hPa
(IFS Cy41r2 Part IV, §3.10.4, eq. 3.99). It is a calculated estimate of something the
model does not resolve.

**What CHAPTER does.** Nothing of the kind. This field is simply the highest 10 m wind speed
the simulation itself produced during the hour. No turbulence term, no estimate — the model's
own wind, at its own resolution, at its strongest moment of the hour.

| comparison | ratio | corr |
|---|---|---|
| ours vs ERA5 `10fg` (gust scheme, hourly max) | **0.625** | 0.813 |
| ours vs ERA5 `i10fg` (gust scheme, instantaneous) | **0.644** | 0.820 |
| ours vs **our own instantaneous 10 m wind, same file** | **1.004–1.032** | — |

The last row explains the first two. Taking the maximum over an hour raises the value by **half
a per cent to three per cent** and no more — and it is below the instantaneous wind at zero
points out of 2 220 273, which is the consistency check an hourly maximum must pass. So what is
published under paramId 49 is, in practice, the 10 m wind speed. ERA5's gust runs at roughly
1.6 times its own mean wind.

The offset is a definition, not weather: 0.593 to 0.673 across all 34 sample timesteps, both
years, every month, every hour.

**"But CHAPTER is a downscaling of ERA5 — shouldn't the two agree?"** It is a reasonable
expectation, and it does not hold, for a specific reason: **a downscaling inherits the *flow*,
not the *diagnostics*.** ERA5 supplies the boundary conditions — wind, temperature, humidity,
pressure — and those are carried into the simulation. A gust is not among them. It is an output
of the IFS's own boundary-layer post-processing, recomputed and discarded at every step, and it
never enters the nested model. WRF then rebuilds everything from its own physics, and this run
did not write out a gust diagnostic of its own. What is published here is the one gust-like
field the run produced.

There is a second half to this, and it pulls the other way. At 3 km, part of what ERA5 must
parameterise is **resolved**: our friction velocity over land runs 1.6 to 2.1 times ERA5's
(§2.2) precisely because the terrain-driven wind is computed rather than smoothed. So a 3 km
model genuinely needs a *smaller* gust increment than a 31 km one — smaller, but not zero, and
this archive applies zero.

**What to do.** Reading `10fg` as a wind gust **under-predicts by about 38 %**, and no bias
correction repairs that, because it is a different quantity rather than a mis-scaled one. The
correlation of 0.81 means it ranks windy places and windy hours correctly, so it is usable for
ranking, for patterns, and as a lower bound. It will not give you a gust threshold. Measured in
[#50](https://github.com/meteocima/CHAPTER/issues/50).

### 5.2 And its declared one-hour window is right only 88 % of the time

**The length of the window is not the difference.** ERA5's hourly gust is also a maximum over
the preceding hour, and our messages declare the same one: `stepType = max`, `stepRange = 0-1`,
`typeOfStatisticalProcessing = 2`, reference time H−1. That encoding was verified correct. What
the field does not always respect is its own label.

**It is not always a one-hour maximum.** WRF resets `WSPD10MAX` at the history write,
and measured over six whole days, 138 hourly transitions, **the reset was missed at 17 of them
(12.3 %)**. Those hours carry a maximum over two hours or more under a message that declares
one.

How much it costs, as mean excess over the instantaneous 10 m wind of the same file:

| | mean excess |
|---|---|
| hours that reset | **0.068–0.311 m/s** |
| hours that did not | **0.499–0.784 m/s** |

Three to eight times larger — a 10 to 17 % overstatement on a domain mean of about 4.5 m/s, at
hours whose message says one hour. **Worse, it moves those hours *closer* to ERA5's gust for
the wrong reason**, so the error is not detectable from the value.

It was left as `0-1` and stated here rather than repaired: detecting the carry-over requires the
previous hour's wrfout, which is not on disk when a file is converted, and no intra-file
detector exists — all seven of WRF's diagnostic maxima reset on the same alarm, so when it is
missed they carry over together and none can witness for another. The hourly misses correlate
with adaptive-timestep variability, but the mechanism was not established.

**What to do.** Do not treat the `10fg` time window as exact when a single hour matters. Over a
season or a distribution the effect is the 12 % contamination above, which is quantified; for a
specific hour there is no flag in the file. Measured in
[#49](https://github.com/meteocima/CHAPTER/issues/49).

---

## 6. Water cycle

### 6.1 Three runoff variables carry one field's information

| timestep | `sro` mean (m) | `ssro` mean (m) | `ssro` non-zero points | `ro` mean (m) |
|---|---|---|---|---|
| 2024-02-15T12 | 3.093e-5 | **0** | **0 of 2 220 273** | 3.093e-5 |
| 2024-07-15T12 | 2.347e-5 | 2.7e-8 | **19** | 2.350e-5 |
| 2024-07-15T18 | 1.064e-4 | 3.9e-8 | **19** | 1.065e-4 |
| 2024-08-15T12 | 1.453e-5 | **0** | **0** | 1.453e-5 |

`ssro` is identically zero on five of the eighteen non-00Z sample timesteps, and where it is
not, its domain mean is four to eight orders of magnitude below `sro`. **`ro` equals `sro` to
four significant figures at every timestep.** The identity `ro = sro + ssro` holds to 3.7e-9 m;
there is simply nothing in the second term.

The cause is the time reference, not the conversion. The model's sub-surface drainage counter is
alive — non-zero at 462 to 8 363 points with maxima of 11 to 106 mm — but it barely moves *within
a day*: on 2024-07-15 the same 1 647 points carry drainage at 00, 06, 12 and 18Z and only 19 of
them grow. The published `ssro` is the accumulation since 00Z, so the daily field is almost
always empty.

Against ERA5 the partition is the opposite way round: `sro` at 1.0–4.6 of ERA5's, `ssro` at
0.000–0.004, `ro` at 0.19–0.85.

**What to do.** Do not close a water budget on the assumption that this archive has a drainage
term — it does not, at daily scale. `ro` and `sro` are, knowingly, duplicate messages. We are
not short of surface runoff; we are missing the other half of the partition, and ERA5's
dominant term is the one we do not carry. Measured in
[#51](https://github.com/meteocima/CHAPTER/issues/51).

### 6.2 `tcw` sums six species where ECMWF defines five

ECMWF defines paramId 136 `tcw` as the sum of water vapour, liquid water, cloud ice, rain and
snow — **five species**. This archive builds it from **six**, adding graupel, and there is no
graupel column published separately because ERA5 has no parameter for one.

The residual, `tcw` minus the five published components, against the independently computed
graupel column:

| timestep | residual (mean) | graupel column (mean) | **residual max** |
|---|---|---|---|
| 2024-01-15T12 | 0.003525 | 0.003396 | **5.69 kg/m²** |
| 2024-04-15T12 | 0.010819 | 0.010863 | **13.89 kg/m²** |
| 2024-07-15T12 | 0.009762 | 0.010219 | **26.46 kg/m²** |
| 2024-10-15T12 | 0.007046 | 0.007267 | **16.73 kg/m²** |

In the domain mean it is 0.4 % of the condensate and invisible. **Inside a July convective cell
it reaches 26 kg/m² — larger than the whole of the rest of the column's condensate.**

Keeping graupel inside `tcw` was the deliberate choice: dropping it would make `tcw` match
ECMWF's definition exactly and the closure identity hold, at the cost of the graupel mass
leaving the archive altogether.

**What to do.** If you reconstruct `tcw` from `tcwv + tclw + tciw + tcrw + tcsw`, you will not
get `tcw`, and the difference is graupel. In convective conditions it is not small. Measured in
[#47](https://github.com/meteocima/CHAPTER/issues/47).

---

## 7. Masks and missing values

### 7.1 One masking rule for the whole archive

**A point is masked where the ERA5 parameter is not defined there** — not where the model has
nothing to say, and not where the number looks wrong. Masked points are a GRIB **bitmap**,
never zeros, so a consumer can always tell "not defined here" from "zero here".

Applied:

| field | masked where |
|---|---|
| `sst`, `ci` | not sea |
| `cl` (zero) and `dl` (missing) | sea |
| `swvl1-4`, `stl1-4` | not **permanent** land |
| `tvl` | shrubland dominates — MODIS carries no shrub phenology and guessing was refused |
| `slt` | not permanent land |
| `mucin` | see §7.2 |

Two consequences are worth stating on their own.

**The sea/inland-water distinction is not the land-use lake class.** WPS's MODIS class 21 calls
the Black Sea, the Sea of Azov and part of the Baltic a lake — together 89 % of the cells this
domain marks fully lake. Masking on it would have deleted `sst` from the Black Sea. The
discriminator is connected-component **size**: the water components here are 844 431 cells
(Atlantic + Mediterranean + Baltic + North Sea), 49 841 (Black Sea + Azov), 8 583 (Red Sea),
then 1 225 (Vänern, the largest genuine inland lake) and smaller. The threshold sits in that
gap with a factor of seven of slack.

**The soil columns are masked off sea ice, and that discards something.** WRF reclassifies a
water cell carrying sea ice as land, gives it soil type 16 and fills the column with water —
`swvl` reaches exactly 1.000 against that soil type's porosity of 0.435. Those columns are the
model's own state, but they are not soil, and ERA5 has no soil there because its land-sea mask
is permanent. They are masked. Nothing is lost that cannot be recovered: `ci` is published, so
the ice itself is in the file.

Note the related fact that **`lsm` and `al` are *not* constant in time** in this archive — they
follow the model hour by hour, because that is what it integrated, and WRF moves the land mask
where sea ice appears. They are written in every message and must not be treated as
one-per-archive statics. Decided and measured in
[#34](https://github.com/meteocima/CHAPTER/issues/34),
[#36](https://github.com/meteocima/CHAPTER/issues/36) and
[#38](https://github.com/meteocima/CHAPTER/issues/38).

### 7.2 `mucin` is masked where the scheme declined, on most of the domain

The CAPE routine flags convective inhibition as missing wherever CAPE is below 100 J/kg. The
archive writes a bitmap there rather than a zero, because zero would read as "nothing is
stopping convection" at precisely the columns where the most is — a column with no CAPE is
usually a column with a great deal of inhibition, and that is often *why* there is no CAPE.

How much of the field is absent:

| timestep | `mucin` present on | masked |
|---|---|---|
| 2024-01-15T12 | 3.8 % | **96.2 %** |
| 2024-02-15T12 | 5.7 % | 94.3 % |
| 2024-03-15T12 | 4.8 % | 95.2 % |
| 2024-07-15T12 | **28.8 %** | 71.2 % |
| 2024-10-15T12 | 15.2 % | 84.8 % |
| 2025-02-15T12 | 5.5 % | 94.5 % |

**On a winter day, 96 % of the `mucin` field is missing.** Where we are silent, ERA5 carries an
inhibition averaging 25 to 265 J/kg. And even where ours is present, it is 0.03 to 0.24 of
ERA5's — because ours exists only in columns with CAPE ≥ 100, which are the least inhibited
ones, while ERA5 reports the field more widely.

**What to do.** Expect a sparse field, most sparse in winter. Do not fill the gaps with zero:
that is the state the archive deliberately does not publish, and a model trained on it learns
that low-CAPE situations have no convective inhibition, which is the inverse of the physics.
`mucape` is dense and its zeros are real — no CAPE genuinely is no available energy. Decided
and measured in [#54](https://github.com/meteocima/CHAPTER/issues/54).

---

## 8. Conventions that do not mean what they look like

### 8.1 `generatingProcessIdentifier = 128` marks every message in the file

Within `grib_v3` this key **discriminates nothing**: all 246 messages carry 128, because that is
eccodes' own GRIB2 sample default and the converter sets it explicitly only for the
accumulations. A consumer filtering on `generatingProcessIdentifier == 128` to find the
00Z-referred accumulations selects the entire file, including every instantaneous field.

Nothing in the data is wrong — the accumulations *are* referred to 00 UTC and 128 does say so.
It simply says it of everything else too. The value's only real meaning is against the older
GRIB1 archive, where 127 marks the run-init-referred messages.

**What to do.** Test `stepType` / `typeOfStatisticalProcessing` and `stepRange`, which state it
unambiguously and were both verified. See §3 of `CHAPTER_VARIABLES.md` for the time convention
itself. Measured in [#53](https://github.com/meteocima/CHAPTER/issues/53).

### 8.2 `al` is a two-season table value by land-use category, not a continuous field

The run used no monthly satellite albedo (`usemonalb = .false.`), so the background albedo comes
from the land-use table's WINTER and SUMMER columns by dominant category. Consequences:

- the field takes only **8 to 11 distinct values** over the whole domain;
- it changes at **1 171 937 land points — 89.9 % of the land mask — at the winter/summer
  boundary**, and every transition is a table row with no residue (0.20→0.17 croplands on
  497 649 points, 0.23→0.25 barren on 369 219, and so on);
- SUMMER applies April to October and WINTER November to March, so on land the table part does
  not move within a day; only the sea-ice points, which follow the hourly land mask, can;
- off land it is 0.08 on water and **0.65 on sea ice**, the model's default ice albedo.

**What to do.** Do not read `al` as an observed or evolving albedo, and do not difference it
across the seasonal boundary expecting a physical signal. Note also that it moves *twice* for
another reason: at sea-ice points, following the land mask of §7.1. Measured in
[#37](https://github.com/meteocima/CHAPTER/issues/37).

### 8.3 `slor` is the slope of the resolved terrain, and `sdor` is ERA5's quantity at 3 km

Two orography parameters, differing from ERA5 in two different ways:

- **`slor`** is published as the gradient magnitude of the **resolved** 3 km terrain, while
  paramId 163 is defined as the slope of the **sub-grid** orography. eccodes will show you the
  parameter's own name, *Slope of sub-gridscale orography*, and nothing in the message says
  otherwise — which is why it is stated here.
- **`sdor`** *is* the ERA5 quantity, evaluated on a 3 km cell instead of a 31 km one. The
  measured ratio of medians against ERA5 is 0.244, which is (3/31)^0.605 — a resolution
  rescaling, not a different definition.

Measured in [#37](https://github.com/meteocima/CHAPTER/issues/37).

### 8.4 "No ERA5 parameter fits" usually means "ERA5 does not publish it"

Several model fields are absent from this archive under a reason recorded as *no ERA5 parameter
fits*. For most of them the accurate statement is different, and the distinction matters to
anyone deciding whether to ask for the field:

| field | the accurate reason |
|---|---|
| `SNOALB` | ECMWF defines **260161 `mxsalb`**, maximum snow albedo — exactly this quantity. ERA5 does not publish it |
| `QGRAUP` | ECMWF defines **260028 `grle`** and **260001 `tcolg`**. ERA5 does not publish them |
| `REFL_10CM` | ECMWF defines **260134 `bref`**. ERA5 does not publish it |
| `LPI` | ECMWF defines the **228050 `litoti`** family, unpublished by ERA5 — and `LPI` is a potential index, not a flash density, so it would not be `litoti` in any case |
| `SNOWFALLAC` | it is a geometric snow depth, not a water equivalent; ECMWF's **3066 `sde`** is the matching parameter and ERA5 does not publish it |

The exclusions stand either way: this archive's publication rule is that a field ships only when
the WRF quantity **is** the ERA5 one. But "no parameter exists" and "ERA5 does not publish it"
are different claims, and only the second is true here.

One field is worth naming separately. **`LAI` is in the model output and is not published.**
`CHAPTER_VARIABLES.md` §6 explains at length why `lai_lv`/`lai_hv` are refused — the model
carries one leaf area index per cell and ERA5 wants one per vegetation class, so any split would
be our invention — without mentioning that the underlying field exists. It does. Note that
`rdlai2d = .false.`, so it is a table lookup on the dominant category rather than an observed
LAI, which is a second reason not to split it. Measured in
[#35](https://github.com/meteocima/CHAPTER/issues/35).

---

## Where the measurements live

Every number in this document was produced by a script in `tools/audit/` of the
[CHAPTER repository](https://github.com/meteocima/CHAPTER) and is written up, with its method,
in `docs/audit/`:

| document | covers |
|---|---|
| `docs/audit/sample.md` | the 34 timesteps and why they were chosen |
| `docs/audit/harness.md` | how a field is compared against ERA5 |
| `docs/audit/f1-pressure-levels.md` | §3, §4 |
| `docs/audit/f2-near-surface.md` | §3.3 |
| `docs/audit/f3-column-integrals.md` | §1.2, §6.2 |
| `docs/audit/f4-radiation.md` | §1.1 |
| `docs/audit/f5-water-cycle.md` | §5, §6.1, §8.1 |
| `docs/audit/f6-soil-and-snow.md` | §7.1 |
| `docs/audit/f7-static-and-surface.md` | §7.1, §8.2, §8.3 |
| `docs/audit/f8-surface-exchange.md` | §1.3, §2, §7.2 |
| `docs/audit/re-verification.md` | the gate the repaired converter passed before this archive was produced |

Document written 2026-09-28, from measurements made 2026-09-18 to 2026-09-25.
