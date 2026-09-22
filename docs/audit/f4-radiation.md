# Family 4: radiation

Thirteen fields, **all accumulated since 00Z**: `ssr` `ssrc` `ssrd` `ssrdc`
`str` `strc` `strd` `strdc` `tisr` `tsr` `tsrc` `ttr` `ttrc`.

Measured over the 34-timestep sample. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl` (442 for this family); the measurements
the harness cannot make are `tools/audit/f4_radiation.py`, `f4_tisr_clearsky.py`
and `f4_decisive.py`, output beside the rows.

**All thirteen are verified.** One finding is filed and it is not a defect but an
undocumented property of the run:
[#45](https://github.com/meteocima/CHAPTER/issues/45).

This is the first family where **leg B is exact for every member** — four are
wrfout accumulators read straight through, one is `ACSWDNT`, and the other eight
are identities restated from the same file. It is also the first to test the
accumulation machinery, on which nineteen accumulators in the archive depend.

## The table

| variable | paramId | leg A | leg B | leg C (ours/ERA5) | verdict |
|---|---|---|---|---|---|
| `ssrd` | 169 | ok | **exact**, `ACSWDNB` | 1.136, corr 0.960 | **verified**, bias → [#45](https://github.com/meteocima/CHAPTER/issues/45) |
| `ssrdc` | 228129 | ok | **exact**, `ACSWDNBC` | **1.085**, corr 0.993 | **verified**, bias → [#45](https://github.com/meteocima/CHAPTER/issues/45) |
| `ssr` | 176 | ok | **exact**, identity | 1.178, corr 0.925 | **verified** |
| `ssrc` | 210 | ok | **exact**, identity | 1.116, corr 0.933 | **verified** |
| `strd` | 175 | ok | **exact**, `ACLWDNB` | 0.989, corr 0.927 | **verified** |
| `strdc` | 228130 | ok | **exact**, `ACLWDNBC` | 0.996, corr 0.987 | **verified** |
| `str` | 177 | ok | **exact**, identity | 0.939, corr 0.910 | **verified** |
| `strc` | 211 | ok | **exact**, identity | 0.941, corr 0.908 | **verified** |
| `tisr` | 212 | ok | **exact**, `ACSWDNT` | **0.9969, corr 0.9999** | **verified** |
| `tsr` | 178 | ok | **exact**, identity | 1.060, corr 0.961 | **verified** |
| `tsrc` | 208 | ok | **exact**, identity | 1.031, corr 0.974 | **verified** |
| `ttr` | 179 | ok | **exact**, identity | 1.009, corr 0.951 | **verified** |
| `ttrc` | 209 | ok | **exact**, identity | 0.990, corr 0.976 | **verified** |

No leg A failure, no bitmap, no missing point, at any of the 34 timesteps.

## The accumulation machinery, tested for the first time

### The encoding is exactly what the schema claims

Read off the messages themselves at 2024-07-15T12:

| key | value |
|---|---|
| `productDefinitionTemplateNumber` | **8** |
| `typeOfStatisticalProcessing` | **1** (accumulation) |
| `stepType` / `stepRange` | `accum` / **`0-12`** |
| `dataDate` / `dataTime` | **20240715 / 0000** — the 00Z reference |
| `validityDate` / `validityTime` | **20240715 / 1200** — the timestep |
| `generatingProcessIdentifier` | **128**, the 00Z-referred marker |
| level | `surface` for the eight surface fields, **`nominalTop`** for the five top-of-atmosphere ones |
| units | `J m**-2` |

At 00Z the step collapses to `0` and reference and validity coincide. A consumer
indexing on validity gets the right hour; one indexing on `dataTime` gets 00Z for
every accumulated message of the day, which is why the schema says never to.

### Zero at 00Z: exactly zero

| | |
|---|---|
| timesteps at 00Z in the sample | 16 |
| fields | 13 |
| **maximum `abs(value)` over all 208 combinations** | **0.0** |

Not "below a threshold": zero. An accumulation since 00Z has no other possible
value there, and the sidecar subtraction is what makes it so.

### Monotone within a run

The sample's diurnal day gives 00, 06, 12 and 18Z of a single run. Nine of the
thirteen never fall at any point of any step. The other four — `str`, `strc`,
`ttr`, `ttrc` — fall at essentially every point of every step, **and that is
correct**: they are net thermal fluxes, counted downward-positive, so the surface
and the top of the atmosphere lose energy and the accumulation grows more
negative. Monotone in magnitude, decreasing in value.

The property the sidecar actually needs is that the *native* accumulators never
fall, and it holds: `ssrd`, `ssrdc`, `strd`, `strdc` and `tisr` are read straight
from them and are monotone increasing, with median gains of 7.4e6 to 2.1e7 J/m²
per six-hour step.

## `tisr` against astronomy, twice

`tisr` is the incident solar flux at the top of the atmosphere: geometry and a
solar constant, nothing else. It is the one field in the archive that can be
checked against something entirely outside the model.

### The strong check is ERA5's own

ERA5's `tisr` is the same astronomy computed independently by ECMWF:

| | |
|---|---|
| ratio of means, ours / ERA5 | **0.9969** |
| correlation | **0.9999** |

**0.31 per cent, and the highest correlation of any field in the archive.** No
missing cosine, no wrong hemisphere, no factor: the geometry is right, verified
against an authority rather than against our own arithmetic.

### The independent recomputation is weaker, and says so

Recomputing the orbit here (Spencer series for declination, the equation of time,
the Earth–Sun distance factor, integrated at the model's own `radt = 5 min`)
gives the solar constant the archive implies:

| timestep | implied S₀, W/m² | spatial IQR |
|---|---|---|
| 2024-04-15T12 | 1377.7 | **5.0** |
| 2024-07-15T12 | 1374.0 | **5.8** |
| 2024-07-15T18 | 1365.0 | **3.9** |
| 2025-02-15T12 | 1387.3 | 10.0 |
| 2024-01-15T12 | 1399.3 | 17.2 |
| 2024-10-15T12 | 1320.4 | 41.9 |

The **spatial** agreement is tight where the geometry is unambiguous — an IQR of
4 to 6 W/m² on ~1370, i.e. 0.3 to 0.4 per cent — which is what verifies the
cosine field. The **date-to-date** spread of 1320 to 1399 brackets WRF's
documented default of 1370 but does not pin it: it is the difference between this
series and WRF's own orbital code, and this check cannot resolve it further.

Two things were tested along the way and are worth recording so they are not
retried. The model integrates the shortwave as a **step function** —
`swint_opt = 0` with `radt = 5`, settled by
[#12](https://github.com/meteocima/CHAPTER/issues/12) — so the quadrature was
repeated with a left-endpoint rule instead of a midpoint one; it moves the answer
by about 1 per cent and does not remove the date dependence. And the equation of
time **must be kept**: dropping it widens the spatial IQR at five of the six
dates, from 17.2 to 25.3 in January and from 10.0 to 42.4 in February. WRF
applies one.

So `tisr`'s verdict rests on the ERA5 comparison, and the independent
recomputation is a bracket that confirms there is no gross error.

## The clear-sky pairs, and what looked like a defect

The six pairs must bound each other in the direction physics fixes. Over the
sample they are violated at up to **247 289 points**, which needed explaining.

**It is not a clear-sky/all-sky mix-up and not an accumulation error.** The
discriminating test is the *instantaneous* flux in the wrfout, where a
one-dimensional radiation scheme must satisfy the inequality at each call:

| instantaneous pair | violating | worst |
|---|---|---|
| `SWDNBC ≥ SWDNB` | 0.000–0.075 % | **0.73–7.8 W/m²** |
| `SWUPTC ≤ SWUPT` | 0.044–0.068 % | 1.4–40 W/m² |
| `LWDNBC ≤ LWDNB` | 0.001–0.002 % | **0.05–0.11 W/m²** |
| `LWUPTC ≥ LWUPT` | 0.014–5.50 % | **2.3–10.6 W/m²** |

RRTMG's own clear-sky and all-sky calls disagree by a few watts on a small
fraction of points — its numerics, not ours. And the accumulated violations are
that, integrated:

> worst accumulated `ttrc − ttr` violation **4.915e5 J/m²** ÷ 43 200 s =
> **11.4 W/m²**, against a worst instantaneous `LWUPTC − LWUPT` of
> **10.56 W/m²**.

The two numbers are the same number. The accumulation reproduces the
instantaneous inconsistency and adds nothing of its own, which is the strongest
statement this family can make about the machinery.

A test that did **not** settle it, recorded so it is not repeated: cross-tabbing
the violations against `tcc` showed 99.9 per cent of them in columns that are
cloud-free *at the validity time*. That proves nothing — the fields accumulate
since 00Z and a column clear at noon may have been cloudy at 08Z. The
instantaneous comparison is the one that discriminates.

## The one finding: surface solar is high, and the reason is not in any document

Leg C, decomposed:

| | ours / ERA5 |
|---|---|
| `ssrdc`, surface solar down, **clear sky** | **1.085** |
| `ssrd`, surface solar down, all sky | **1.136** |
| `strd`/`strdc`, downward thermal | 0.989 / 0.996 |
| `ttr`/`ttrc`, outgoing thermal | 1.009 / 0.990 |

**Under clear sky, with no cloud involved at all, we deliver 8.5 per cent more
solar to the surface than ERA5.** The thermal fields agree to about 1 per cent,
which is the control that makes the attribution credible.

[#12](https://github.com/meteocima/CHAPTER/issues/12) established from the
configuration that RRTMG ran with **no aerosol**. ERA5 carries the Tegen
climatology, and over Europe, the Mediterranean and the Saharan margin an optical
depth of 0.1 to 0.2 is the right order for 8.5 per cent. The further 5 points in
the all-sky figure are a cloud difference on top of it.

It is a property of the run and cannot be removed after the fact, but a user of
this archive for solar resource or as training data against observations needs to
know. Filed as [#45](https://github.com/meteocima/CHAPTER/issues/45).

## Two notes, neither a defect

**The net solar fields reach −0.28 J/m².** `ssr`, `ssrc`, `tsr` and `tsrc` are
differences of two large accumulations and go very slightly negative at night, on
up to 104 000 points. The magnitude is 8e-9 of the field's range. The converter
clips *native* accumulators at zero but deliberately does not clip the net ones,
and it is right not to: `str` and `ttr` are legitimately negative everywhere.

**The dead TOA downward thermal fields are not used.** `LWDNT`, `LWDNTC`,
`ACLWDNT`, `ACLWDNTC` are identically zero, and `NET_RADIATION` confirms it by
construction: `ttr` and `ttrc` are written as `−ACLWUPT` and `−ACLWUPTC`, with no
downward term. Which is right — the downward thermal flux at the top of the
atmosphere is physically zero, so the field being dead is the correct answer and
not a missing input.

## What this family contaminates

- **Nothing.** No other family's variables are touched and no ticket is
  invalidated.
- **Family 5 ([#23](https://github.com/meteocima/CHAPTER/issues/23)) inherits the
  machinery verdict**: the PDT-8 encoding, the 00Z reference, the exact zero at
  00Z and the sidecar subtraction are verified here on thirteen fields and need
  not be re-established for the water-cycle six. What family 5 still owns is
  `10fg`, whose time convention is different, and the `tp` cross-check against
  `PREC_ACC_NC`.
- **Family 8 ([#26](https://github.com/meteocima/CHAPTER/issues/26))** should note
  that `skt` is inverted from `LWUPB` and `LWUPBC`, whose instantaneous
  clear-sky/all-sky consistency is measured here: they disagree by at most
  0.11 W/m² on 0.002 per cent of points, so the emissivity identity that divides
  them rests on a sound pair.
