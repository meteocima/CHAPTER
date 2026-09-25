# Family 3: column integrals and cloud cover

Ten fields, all on `entireAtmosphere`: six column integrals `tcw` `tcwv` `tclw`
`tciw` `tcrw` `tcsw`, and four cloud covers `tcc` `hcc` `mcc` `lcc`.

Measured over the 34-timestep sample. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl` (340 for this family); the measurements
the harness cannot make are `tools/audit/f3_columns.py`, output beside the rows
as `f3_columns.json`, `f3_lccdiff.json` and `f3_legc_exact.json`.

**The four cloud covers are verified. The six column integrals are wrong by a
measurable factor** — between 3 and 8 per cent, always in the same direction for
water vapour — and the defect is the quadrature, not the physics:
[#46](https://github.com/meteocima/CHAPTER/issues/46). A second finding concerns
what `tcw` is the sum of ([#47](https://github.com/meteocima/CHAPTER/issues/47)),
and a third is not a conversion defect at all but a property of the run that no
document states: **we carry 22 per cent less total cloud than ERA5 and 39 per
cent less high cloud** ([#48](https://github.com/meteocima/CHAPTER/issues/48)),
which is the piece [#45](https://github.com/meteocima/CHAPTER/issues/45) could
not measure.

## The harness said leg B did not exist here. It was wrong.

`tools/audit/harness.py` records `leg_b: none` for all ten, on the rule that the
derivation IS the converter's algorithm and restating it would be a copy of the
thing under test. For a column integral that rule does not apply, and the reason
is worth stating because it is what makes this family's verdict possible at all.

**WRF does not integrate on pressure. It integrates on dry air mass.** The
vertical coordinate is dry hydrostatic pressure, and the model writes out the
column dry mass `MU + MUB` and the eta thickness `DNW` of every layer. So the
mass of water of species X in a column is not an integral to be approximated:

    layer dry mass       =  (MU + MUB) * |DNW_k| / g          [kg/m2]
    column water of X    =  sum_k  X_k * (MU + MUB) * |DNW_k| / g

because WRF's `Q*` are mixing ratios, per kg of **dry** air. There is no
quadrature rule in that sum, no endpoint choice, no missing surface layer. It is
a weighted sum whose weights the model itself wrote.

It is also the **same quantity ECMWF defines**. ERA5's `tcwv` is the integral of
*specific* humidity against *total* pressure, and

    q_specific dm_total = (m_v/m_tot) dm_tot = dm_v = (m_v/m_dry) dm_dry
                        = r_mixing dm_dry

so the two are one integral written twice. The converter uses the first form;
this audit uses the second; in the continuum they are equal, and any difference
between them is discretisation and nothing else.

**The coordinate was checked before being trusted.** `DNW` sums to
`1.0000000000` over the 49 layers at every sampled timestep, and rebuilding the
surface pressure from the layer masses,

    PSFC = P_TOP + sum_k (MU+MUB) |DNW_k| (1 + r_total,k)

reproduces the model's own `PSFC` to a mean of **0.45 to 1.9 Pa** out of
~100 000 Pa, worst point 79 Pa. The weights are what they are claimed to be.

## The table

| variable | paramId | leg A | leg B (exact dry mass) | leg C (ours/ERA5) | verdict |
|---|---|---|---|---|---|
| `tcwv` | 137 | ok | **+4.5 % to +5.1 %** | 1.063 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46) |
| `tcw` | 136 | ok | **+4.5 % to +5.1 %** | 1.062 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46), [#47](https://github.com/meteocima/CHAPTER/issues/47) |
| `tclw` | 78 | ok | **+3.3 % to +5.8 %** | 0.748 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46) |
| `tcrw` | 228089 | ok | **+3.4 % to +7.8 %** | 2.71 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46) |
| `tciw` | 79 | ok | **−3.3 % to +0.9 %** | 1.109 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46) |
| `tcsw` | 228090 | ok | **−3.6 % to +2.9 %** | 0.816 | **wrong** → [#46](https://github.com/meteocima/CHAPTER/issues/46) |
| `tcc` | 164 | ok | bounds hold, 0 violations | 0.783 | **verified**, deficit → [#48](https://github.com/meteocima/CHAPTER/issues/48) |
| `lcc` | 186 | ok | recomputed, ≤2 points differ | 0.862 | **verified**, deficit → [#48](https://github.com/meteocima/CHAPTER/issues/48) |
| `mcc` | 187 | ok | recomputed to 3e-7 | 0.786 | **verified**, deficit → [#48](https://github.com/meteocima/CHAPTER/issues/48) |
| `hcc` | 188 | ok | recomputed to 3e-7 | **0.610** | **verified**, deficit → [#48](https://github.com/meteocima/CHAPTER/issues/48) |

No leg A failure, no bitmap, no missing point, at any of the 34 timesteps. The
cloud covers never leave `[0, 1]` and the water columns are never negative.

The leg C column is the 34-timestep sample mean, from the harness rows. The
twelve-month 2024 figures quoted later differ slightly (1.0685 for `tcwv`)
because that set is twelve 12Z timesteps rather than 34 spread over three years
and four hours; both are reported where they were measured and neither is
rounded into the other.

### The encoding

Identical on all ten and on all 34 timesteps:

| key | value |
|---|---|
| `typeOfLevel` | `entireAtmosphere` |
| `typeOfFirstFixedSurface` / `Second` | **1 (surface) / 8 (nominal top)** |
| `level` / `stepType` / `stepRange` | `0` / `instant` / `0` |
| `bitmapPresent` | **0** — correct: none of the ten is masked anywhere |
| packing | `grid_ccsds`, 24 bits |
| units | `kg m**-2` for the six columns, `(0 - 1)` for the four covers |

The units in the message agree with the registry and with the ERA5 paramId in
every case. Nothing here is converted by hand: the column integrals are built
from `kg kg-1` mixing ratios and Pa, and `kg/m2` falls out of the arithmetic.

## The finding: the integrals use the wrong quadrature

The converter builds its own vertical increment from the pressure at the **mass
levels**:

```python
pres_pa = gv("pressure").values * 100.0
dp = np.abs(np.diff(pres_pa, axis=0))
dp = np.concatenate([dp, np.zeros_like(dp[-1:])], axis=0)
...
emit('tqv', np.sum(qv * dp / G, axis=0))
```

That is a **left-endpoint Riemann sum**: the value at level *k* is given the mass
between level *k* and level *k+1*, which lies entirely **above** it. Water vapour
falls off with height, so every layer is weighted by the largest value it
contains, and the sum is high. Two further errors ride along: the mass between
the ground and the lowest model level (~25 m AGL) is not in the sum at all, and
the top layer is given `dp = 0`.

Restating that rule here reproduces the published messages to **1e-5 kg/m²** —
packing precision — so what follows is a measurement of the converter, not of my
reading of it.

### Attributed, at four timesteps across the seasons

Domain means, kg/m², `tcwv`:

| timestep | exact | published | error | endpoint rule | missing surface layer | grid offset |
|---|---|---|---|---|---|---|
| 2024-01-15T12 | 11.104 | 11.674 | **+5.13 %** | +0.747 | −0.151 | −0.026 |
| 2024-04-15T12 | 14.126 | 14.807 | **+4.82 %** | +0.941 | −0.199 | −0.062 |
| 2024-07-15T12 | 25.542 | 26.702 | **+4.54 %** | +1.634 | −0.312 | −0.162 |
| 2024-10-15T12 | 21.602 | 22.631 | **+4.76 %** | +1.406 | −0.261 | −0.116 |

The endpoint rule is the whole of it. Filling in the missing surface layer and
switching to a trapezoid leaves **−0.6 %**, which is the residual half-level
offset between the mass-level increments and the true layer masses.

All six species, as a relative error on the domain mean:

| species | published as | 2024-01 | 2024-04 | 2024-07 | 2024-10 |
|---|---|---|---|---|---|
| `QVAPOR` | `tcwv` | +5.13 % | +4.82 % | +4.54 % | +4.76 % |
| `QCLOUD` | `tclw` | +5.81 % | +5.03 % | +3.30 % | +5.43 % |
| `QRAIN` | `tcrw` | +7.82 % | +7.37 % | +3.44 % | +5.41 % |
| `QICE` | `tciw` | +0.93 % | −1.60 % | −3.31 % | −2.72 % |
| `QSNOW` | `tcsw` | +2.94 % | −0.76 % | −3.58 % | −3.17 % |
| `QGRAUP` | (in `tcw`) | +3.80 % | −0.41 % | −4.48 % | −3.04 % |

**The sign flip is the proof that the diagnosis is right.** Vapour, cloud water
and rain decrease upward, so the left-endpoint rule over-weights them and the
error is positive. Ice, snow and graupel *increase* with height through the
mid-troposphere, so over those layers the same rule under-weights them and the
error turns negative — exactly where and when the frozen species sit high, in
spring and summer. No other explanation produces that pattern.

### What it does to the comparison against ERA5

Leg C was run twice at each of the twelve 12Z timesteps of 2024, with the same
upscaling and the same ERA5 counterpart: once on the published message and once
on the exact dry-mass integral. Ratio ours/ERA5, published → exact:

| month | `tcwv` | `tcw` | `tclw` | `tciw` | `tcrw` | `tcsw` |
|---|---|---|---|---|---|---|
| 2024-01 | 1.065 → **1.013** | 1.064 → 1.013 | 0.652 → 0.616 | 1.493 → 1.484 | 2.355 → 2.185 | 0.867 → 0.847 |
| 2024-04 | 1.072 → **1.024** | 1.072 → 1.024 | 0.656 → 0.626 | 0.890 → 0.907 | 3.471 → 3.248 | 1.027 → 1.041 |
| 2024-07 | 1.076 → **1.030** | 1.076 → 1.031 | 0.635 → 0.617 | 0.759 → 0.785 | 5.454 → 5.294 | 1.048 → 1.089 |
| 2024-10 | 1.060 → **1.013** | 1.060 → 1.013 | 0.805 → 0.766 | 1.066 → 1.097 | 3.103 → 2.950 | 0.831 → 0.860 |
| 2024-12 | 1.058 → **1.004** | 1.057 → 1.003 | 0.947 → 0.880 | 1.358 → 1.364 | 2.121 → 1.963 | 0.620 → 0.618 |
| **twelve-month** | **1.0685 → 1.0203** | 1.0681 → 1.0201 | 0.778 → 0.735 | 1.093 → 1.111 | 2.858 → 2.699 | 0.842 → 0.858 |

**The archive's apparent moist bias against ERA5 was mostly our own quadrature.**
+6.9 per cent becomes +2.0, which is inside what leg C can resolve at 59 WRF
cells per ERA5 cell — and this is the number the harness documentation warns
must never be called a defect. It very nearly was.

And it is not only the mean. RMSE against ERA5 falls from **2.165 to 1.745
kg/m²** for `tcwv` and from 2.238 to 1.834 for `tcw`, with the correlation
unchanged (0.9643 → 0.9633): the corrected field is closer to ERA5 point by
point, not merely rescaled.

**Stated honestly, it does not help everything.** For `tciw` and `tcsw` the
exact integral moves *away* from ERA5 (1.093 → 1.111 and 0.842 → 0.858) and
their RMSE rises slightly. That is what it should do if the remaining
disagreement in the frozen species is physical: a correction that is right by
construction is not obliged to flatter every comparison, and one that improved
all six would be the more suspicious result.

## `tcw` is the sum of six species; ERA5's is the sum of five

The converter builds `tcw` from `QVAPOR + QCLOUD + QRAIN + QICE + QSNOW +
QGRAUP`, but publishes only five component columns — there is no graupel column,
because ERA5 has no parameter for one (`docs/audit/exclusions.md`). ECMWF's own
definition of paramId 136 is "the sum of water vapour, liquid water, cloud ice,
rain and snow": **five species**.

So a user who reconstructs `tcw` from what we publish does not get `tcw`. The
residual is the graupel column, and it was measured as such:

| timestep | `tcw` − Σ components (mean) | exact graupel column (mean) | residual max |
|---|---|---|---|
| 2024-01-15T12 | 0.003525 | 0.003396 | **5.69** |
| 2024-04-15T12 | 0.010819 | 0.010863 | **13.89** |
| 2024-07-15T12 | 0.009762 | 0.010219 | **26.46** |
| 2024-10-15T12 | 0.007046 | 0.007267 | **16.73** |

The two agree to within the quadrature error of the previous section, which is
what identifies the residual as graupel and not as something else. In the domain
mean it is 0.4 per cent of the condensate and invisible; **inside a July
convective cell it is 26 kg/m², larger than the entire rest of the column's
condensate.**

That the archive keeps graupel inside `tcw` is a recorded decision
(`MISSING_VARIABLES.md`: "graupel is included in total column water, but cannot
be published separately under an ERA5 name"). What is not recorded anywhere a
user would look is that this makes the published `tcw` differ from its own
ECMWF definition, and by how much.
[#47](https://github.com/meteocima/CHAPTER/issues/47).

**A second, smaller inconsistency in the same block.** The five component
columns clip negative mixing ratios (`np.maximum(gv(name).values, 0.0)` — the
advection undershoot that `docs/audit/f1-pressure-levels.md` documents on the
pressure levels); `tcw` does not. So at points where the undershoot bites,
`tcw` is *below* the sum of its own components: 151 101 to 551 016 points per
timestep, by at most 8.8e-6 kg/m². Numerically trivial, and a real inconsistency
between two published fields that a consumer can see. It rides on the same
issue.

## The cloud covers: verified, and the deficit is not ours

### The bands are ECMWF's

`CLOUD_BANDS` in the converter is `lcc (1.00, 0.80]`, `mcc (0.80, 0.45]`,
`hcc (0.45, 0.00]` on σ = p/p_surface, applied as `(sigma <= hi) & (sigma > lo)`.
ECMWF's published definition is

> low: 1.0 > σ > 0.8 — medium: 0.8 ≥ σ > 0.45 — high: 0.45 ≥ σ

([ECMWF, *How are low, medium and high cloud cover
defined?*](https://confluence.ecmwf.int/pages/viewpage.action?pageId=111155326)).
Identical, **including which side of each boundary is closed**. The only formal
difference is at σ = 1.0, which the lowest mass level (≈25 m AGL, σ ≈ 0.997)
never reaches.

The partition is per point, not per level index: measured at 2024-07-15T12 the
low band draws on model levels 0–11, the medium band on 10–23 and the high band
on 19–48, the overlap in index being the terrain. Every (level, point) falls in
exactly one band.

### The overlap is maximum-random, and it satisfies both bounds

Whatever overlap assumption is used, the total cover must lie between the
largest single layer (maximum overlap) and one minus the product of the clear
fractions (random overlap). Those two bounds need no knowledge of how the
converter codes it. Measured at every point of four timesteps:

| timestep | max-overlap bound | published `tcc` | random-overlap bound | violations |
|---|---|---|---|---|
| 2024-01-15T12 | 0.5506 | 0.5529 | 0.5744 | **0 / 0** |
| 2024-04-15T12 | 0.4038 | 0.4059 | 0.4253 | **0 / 0** |
| 2024-07-15T12 | 0.2314 | 0.2331 | 0.2435 | **0 / 0** |
| 2024-10-15T12 | 0.4665 | 0.4691 | 0.4802 | **0 / 0** |

Worst excursion beyond either bound: 2.1e-7, which is the packing. And
recomputing the maximum-random overlap from `CLDFRA` reproduces `tcc`, `mcc` and
`hcc` to **3e-7** at every point.

The three bands also recombine: `tcc ≥ max(lcc, mcc, hcc)` and
`tcc ≤ 1 − (1−lcc)(1−mcc)(1−hcc)` at every point, 0 violations, and the mean of
the right-hand side (0.5544 in January) sits just above `tcc` (0.5529) as the
partition requires.

**`CLDFRA` never leaves `[0, 1]`** in the wrfout — 0 points above 1 and 0 below 0
at every sampled timestep — so the converter's clip is defensive and does
nothing. Its distribution is strongly bimodal: of 108.79 million (level, point)
cells at 2024-01-15T12, 98.18 million are below 0.09 and 5.59 million above
0.91. That bimodality is why the two overlap bounds sit only 2–4 per cent apart,
which matters below.

### Two points per file move between `lcc` and `mcc`

The recomputation of `lcc` disagrees with the published message at **0 to 2
points out of 2 220 273**, by as much as 0.94. Located and diagnosed: in every
case the differing point has all its low-band cloud in the single topmost level
of the band, sitting within rounding distance of σ = 0.80. The converter derives
σ from wrf-python's `pressure` diagnostic, which is float32 **hPa**, multiplied
by 100; this audit derives it from `P + PB` in Pa. The two straddle the boundary
differently and the level falls into `lcc` for one and `mcc` for the other.

Repeating the recomputation in float32 moves which points differ but not how
many, confirming it is precision at the boundary and not the algorithm. The
cloud is not lost — it moves between two published bands — and `tcc` is
unaffected, which is why it recomputes to 3e-7 while `lcc` does not. No boundary
can be knife-edge-free, so this is not filed as a defect; it is recorded here,
with the note that deriving σ from `P + PB` in Pa would be both cheaper and two
decimal digits sharper.

### Where the cloud deficit actually is

We carry markedly less cloud than ERA5 — `tcc` 0.783, and `hcc` **0.610** — and
the obvious suspect is the overlap assumption, because ECMWF does *not* use
maximum-random: its documentation says the overlap's randomness "is dependent
upon distance between layers", i.e. an exponential-random scheme, which for the
same layer fractions yields **more** total cover than maximum-random does. That
is the right direction to explain a deficit.

It is not enough. The random-overlap bound above is the **most** cloud any
overlap assumption can extract from our own `CLDFRA`, and it sits only 2 to 4
per cent above our `tcc`: 0.5744 against 0.5529 in January, 0.2435 against
0.2331 in July. ERA5 is 28 per cent above us. **The overlap accounts for at most
a seventh of the gap; the rest is `CLDFRA` itself**, which is WRF's Xu–Randall
diagnostic under `ICLOUD=1` — the run, not the conversion.

The sharpest form of it: **we carry 11 per cent more cloud ice than ERA5
(`tciw` 1.109) and diagnose 39 per cent less high cloud (`hcc` 0.610)**. The
condensate is there; the fraction the scheme assigns to it is not.

Part of the gap is resolution and not error — our `tcc` is overlapped at 3 km
and then averaged to 31 km, while ERA5's is overlapped on an already-smooth
31 km profile, which yields somewhat more cover. That effect is bounded by the
same 2–4 per cent overlap span, so it cannot carry 22 per cent either; it is
recorded so the number is not quoted as if it were all model error.

Filed as [#48](https://github.com/meteocima/CHAPTER/issues/48), and it closes a
loose end in family 4. [#45](https://github.com/meteocima/CHAPTER/issues/45)
measured surface downward solar at **1.085 of ERA5 under clear sky and 1.136
all-sky**, and attributed the extra five points to "a difference in cloudiness
above" with no number attached. This is the number. The two are one story — no
aerosol *and* too little cloud, both pushing surface solar the same way — and a
reader given either alone will attribute the whole excess to it.

### `tcrw`, and why 2.71 is not a defect

Rain water is the one column where we are far above ERA5, by a factor that
swings between 1.6 and 7.3 across the sample. `CU_PHYSICS = 0`: at 3 km every
raindrop in this run is resolved and lives in `QRAIN`. ERA5 at 31 km carries
prognostic rain from its large-scale scheme only, with convective rain handled
diagnostically and never entering `tcrw`. The two fields are not measuring the
same population, and the timesteps with the largest ratios (5.5 at
2024-07-15T12, 7.3 at 18Z) are precisely the convective afternoons. Recorded,
not filed.

## What this family contaminates

**Nothing else in the archive uses this quadrature.** The `dp` built from
mass-level pressure differences lives in one block of
`convert_to_pressure_levels.py` and feeds only these six messages. Checked
against the other families explicitly:

- **Family 1** ([#19](https://github.com/meteocima/CHAPTER/issues/19), closed).
  `q`, `clwc`, `ciwc`, `crwc`, `cswc` on pressure levels are point values
  interpolated by `to_levels`, not integrals. They share `moist_factor` with
  this family, and `moist_factor` is **not** where the error is — it is correct
  in both places. Family 1's verdicts stand.
- **Family 5** ([#23](https://github.com/meteocima/CHAPTER/issues/23), open).
  `tp`, `sf`, `tirf`, `sro`, `ssro`, `ro` are WRF's own accumulators read
  through and referred to 00Z. No vertical integral anywhere. **Not affected**,
  and family 5 should not spend any of its session re-checking this.
- **Family 8** ([#26](https://github.com/meteocima/CHAPTER/issues/26), open).
  `mucape`/`mucin` do their own vertical work inside wrf-python's Fortran
  kernel, on a different coordinate. Untouched by this.

It does, however, **name a technique family 8 can reuse**: whenever a field is a
vertical sum, WRF's `MU + MUB` and `DNW` give the answer with no quadrature at
all, and that is a genuine leg B for something the harness declares unverifiable.

## A correction to the harness

`tools/audit/harness.py` classifies all ten of these as `leg_b: none`, with the
reason that "the derivation IS the converter's own algorithm (vertical
interpolation, **column integrals**, the skt inversion, CAPE) — recomputing it
independently means writing a second converter."

For the column integrals that reason is wrong, and the whole of this family's
verdict comes from the leg it denied. The dry-mass sum is not a second converter:
it is a different and *exact* route to the same number, and it uses three wrfout
fields (`MU`, `MUB`, `DNW`) that the converter never opens. Had the harness been
taken at its word, the six integrals would have rested on legs A and C alone —
and leg C, correctly, refuses to call a 6 per cent bias a defect.

The classification is corrected in `harness.py` and `docs/audit/harness.md`. The
implementation stays in `tools/audit/f3_columns.py` rather than moving into the
harness: putting it there would mean re-running the 34-timestep campaign to
regenerate rows that the family script has already produced, and the harness is
deliberately not being changed under the audit that uses it.

## What was *not* measured

- **Leg B for the cloud covers is still `none`, honestly.** There is no second
  route to a maximum-random overlap; the recomputation here is the same formula
  in different precision, and it is reported as such. What carries the verdict
  for `tcc`/`lcc`/`mcc`/`hcc` is the pair of bounds, which are definitional and
  hold at every point.
- **`tcw` was not compared against ERA5's `tcw` minus graupel**, because ERA5
  has no graupel to subtract. The closure check inside our own file is the
  stronger statement anyway.
- **The quadrature error was attributed at four timesteps and confirmed on
  twelve**, not on all 34. The pattern is stable enough across seasons and
  species that a fifth significant figure would add nothing.

## Repaired, and verified against both rules

Applied 2026-09-25, commit below. The converter now sums against the dry mass.
Verified as a SLURM job on 2024-07-15T12: 246 messages, `check_grib_sanity`
clean, and the columns rebuilt independently of the converter — chunked over
rows, straight from the wrfout — with **both** rules computed so the change is
attributed rather than asserted.

The coordinate was checked before being trusted, not after:

| | |
|---|---|
| `DNW` sums to | **1.0000000000** |
| `PSFC` rebuilt from the layer masses | mean **+1.881 Pa**, worst **79.3 Pa** out of ~100 000 |

| field | published | exact | old rule | published − exact | old rule was off by |
|---|---|---|---|---|---|
| `tcwv` | 25.54199 | 25.54199 | 26.70224 | 1.9e-06 | **+4.54 %** |
| `tclw` | 0.02311 | 0.02311 | 0.02387 | 2.4e-07 | +3.30 % |
| `tcrw` | 0.01370 | 0.01370 | 0.01418 | 9.5e-07 | +3.44 % |
| `tciw` | 0.00896 | 0.00896 | 0.00866 | 1.5e-08 | **−3.31 %** |
| `tcsw` | 0.01858 | 0.01858 | 0.01791 | 4.8e-07 | **−3.58 %** |
| `tcw` | 25.61656 | 25.61656 | 26.77662 | 3.8e-06 | +4.53 % |

The published field is the exact one to **1.9e-06 kg/m²**, packing noise, and the
sign flip that identified the cause in the first place is reproduced at the
repair: positive on vapour, cloud water and rain, negative on ice and snow.

**Closure holds.** `tcw` minus its five published components equals the graupel
column to **7.1e-06 kg/m²**, on a timestep where graupel reaches 27.448 kg/m².
That is the check that would have caught a species dropped or double-counted, and
it now also confirms `tcw` uses the same zero clip as its components — which it
did not before ([#47](https://github.com/meteocima/CHAPTER/issues/47)).

