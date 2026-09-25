# Family 6: soil and snow

The thirteen fields describing what is under and on top of the surface:
`stl1-4` `swvl1-4` `rsn` `sd` `snowc` `src` `tsn`.

Measured over the 34-timestep sample. Harness rows in
`$WORK/CHAPTER/audit_rows/rows_*.jsonl`; the measurements the harness cannot make
are `tools/audit/f6_soil_snow.py`, `f6_seaice_soil.py` and `f6_porosity.py`, with
their output beside the rows.

**Leg B is unavailable for ten of the thirteen** — the eight soil layers, `rsn`
and `tsn` are the converter's own derivations — so the harness carries legs A and
C only, and the central claim of this family, that the soil layers are the
*exact* integral of RUC's profile, is untested by it. That claim is the first
thing measured here, and it holds.

**Twelve of the thirteen are verified.** The thirteenth is not a field defect but
a mask one, and it is the same mask family 7 found.

## The table

| variable | paramId | leg A | leg B | leg C (ERA5) | verdict |
|---|---|---|---|---|---|
| `stl1` | 139 | ok | rebuilt here: **1.9e-6 K** | bias −1.31 K, corr 0.971 | **verified** |
| `stl2` | 170 | ok | rebuilt here: **1.9e-6 K** | bias −0.53 K, corr 0.990 | **verified** |
| `stl3` | 183 | ok | rebuilt here: **1.8e-6 K** | bias +0.05 K, corr 0.993 | **verified** |
| `stl4` | 236 | ok | rebuilt here: **1.9e-6 K** | bias −1.42 K, corr 0.986 | **verified** |
| `swvl1` | 39 | ok | rebuilt here: **3.0e-8** | bias +0.017, ratio 1.099 | **verified**, mask → [#38](https://github.com/meteocima/CHAPTER/issues/38) |
| `swvl2` | 40 | ok | rebuilt here: **3.0e-8** | bias +0.009, ratio 1.049 | **verified**, mask → [#38](https://github.com/meteocima/CHAPTER/issues/38) |
| `swvl3` | 41 | ok | rebuilt here: **3.0e-8** | bias +0.024, ratio 1.141 | **verified**, mask → [#38](https://github.com/meteocima/CHAPTER/issues/38) |
| `swvl4` | 42 | ok | rebuilt here: **3.0e-8** | bias +0.003, ratio 1.014 | **verified**, mask → [#38](https://github.com/meteocima/CHAPTER/issues/38) |
| `rsn` | 33 | ok | rebuilt here | bias −1.20 kg/m³, corr 0.734 | **verified** |
| `sd` | 141 | ok | exact | bias −2.9e-5 m, ratio 0.882 | **verified** |
| `snowc` | 260038 | ok | exact | ERA5 single levels do not carry it | **verified** |
| `src` | 198 | ok | exact | ratio 0.573, corr 0.550 | **verified, different capacity** |
| `tsn` | 238 | ok | rebuilt here | bias −0.37 K, corr 0.596 | **verified** |

## The soil layers are the integral, and the integral is right

Three separate things had to be true and each was measured separately.

### 1. The operator

`SOIL_LAYER_WEIGHTS` is an analytic trapezoid matrix. Restating that algebra
would prove nothing, so it was derived a second time by **dense numerical
integration**: for each RUC node, the profile that is 1 there and 0 elsewhere,
sampled on a two-million-point grid and averaged over each ERA5 layer.

| | |
|---|---|
| max abs difference, dense integration against the converter | **1.2e-13** |
| row sums | **exactly 1.0**, all four — averages, not sums |
| deepest ERA5 boundary against deepest RUC node | 2.89 m against 3.00 m, **no extrapolation** |
| nodes contributing per layer | (0,1,2), (1,2,3), (2,3,4), (3,4,5) — each layer sees only the nodes bracketing it |

The weights, for the record:

| layer | 0 cm | 5 cm | 20 cm | 40 cm | 160 cm | 300 cm |
|---|---|---|---|---|---|---|
| 1 (0–7 cm) | 0.357143 | 0.623810 | 0.019048 | | | |
| 2 (7–28 cm) | | 0.268254 | 0.655556 | 0.076190 | | |
| 3 (28–100 cm) | | | 0.050000 | 0.741667 | 0.208333 | |
| 4 (100–289 cm) | | | | 0.079365 | 0.606179 | 0.314456 |

### 2. The operator applied to the wrfout — the leg B the harness lacks

Published layers against that matrix applied to the wrfout's own `TSLB`/`SMOIS`,
at five timesteps spanning January, February, March, July and the 2019 year:

| | worst over all five timesteps |
|---|---|
| `stl1-4` | **1.9e-6 K** |
| `swvl1-4` | **3.0e-8 m³/m³** |
| mask disagreements | **0** |
| points compared per timestep | 1.30 to 1.31 million |

That is the float32 round trip through CCSDS packing and nothing else. The
layers are the integral.

### 3. The nodes the weights assume

`SOIL_LAYER_WEIGHTS` is a compile-time constant, so a file whose `ZS` differed
would be silently wrong. `ZS` was read at **all 34 timesteps**: one distinct
value, `(0, 0.05, 0.20, 0.40, 1.60, 3.00)` m, at every one.

### `stl1` is not `SOILT1`

The ticket names this as a trap that has been walked into before. It has not been
walked into here — the two fields are nowhere near each other:

| timestep | `stl1` vs `SOILT1` | `stl1` vs `TSLB[0]` | `SOILT1` vs `TSLB[0]` |
|---|---|---|---|
| 2024-01-15T12 | rms 4.81 K, 3 points equal | rms 3.83 K | rms 8.18 K |
| 2024-07-15T12 | rms 6.24 K, 0 points equal | rms 3.93 K | rms 9.29 K |

`stl1` is not `TSLB[0]` either, and it should not be: it is the 0–7 cm average,
which weights the 5 cm node more heavily than the surface one.

### Which `SOILPARM.TBL`

[#12](https://github.com/meteocima/CHAPTER/issues/12) settled that the
`_Kishne_2017` file is never opened. Two things add to it here. The `STAS-RUC`
blocks of the two files are **byte-identical**, so the choice is inert for the
soil columns whichever is read — and the *data* identifies which block the model
used: against `STAS-RUC` no land point exceeds its own porosity, while against
`STAS` 15 to 788 points per layer appear to. `sf_surface_physics = 3` reads
`STAS-RUC`, and the archive agrees.

### Soil moisture respects its own porosity

Off the sea ice, at six timesteps in three seasons and two years, in all four
layers:

| | |
|---|---|
| land points above their own soil type's porosity | **0** |
| largest value, relative to saturation | 0.0000 to 0.0132 **below** it |

## The one finding: the soil column the sea ice creates

`swvl` reaches **exactly 1.000** at every winter timestep. No RUC soil type has a
porosity above 0.485, so that cannot be soil water. It is not:

| | |
|---|---|
| points with `swvl1` above every RUC porosity | 591 to 5259, at 14 of 34 timesteps |
| of which sea-ice points | **all of them** |
| sea-ice points not among them | **0** |
| their soil type | 16, `OTHER(land-ice)`, at every point of every timestep |
| its porosity in `STAS-RUC` | **0.435** — the published value exceeds it by **+0.565** |
| their `stl1` | 254.9 to 271.4 K, the second being the seawater freezing point |

One-to-one in both directions, at all fourteen timesteps. When a water cell
carries sea ice, WRF makes it land, gives it soil type 16 and fills the column
with water, and the converter — whose soil mask correctly follows the *hourly*
land mask — publishes that column under ERA5's `swvl` and `stl` paramIds, where
ERA5 has no soil at all because its land-sea mask is permanent.

The values are the model's own and masking them would discard what it
integrated. But 1.000 m³/m³ is impossible for the soil type the same file
declares, and it is 2.3 times that type's porosity. Filed as
[#38](https://github.com/meteocima/CHAPTER/issues/38) — the same mask decision as
[#36](https://github.com/meteocima/CHAPTER/issues/36) and to be taken with it.

The mask itself is otherwise exactly right: bitmapped in every message, missing
on exactly the water points, and moving with the ice — 916 164 missing in July,
912 939 in January, 910 905 in February, tracking the sea ice one for one, which
is the behaviour family 7 verified from the `lsm` side.

## Snow

### `sd` is water equivalent, and is not snow depth

The classic confusion, checked directly rather than assumed:

| | |
|---|---|
| `sd` against `SNOW` × 1e-3 | agrees to **1.5e-8 m**, at every timestep |
| `sd` against `SNOWH`, the physical depth | differs by up to **1.09 m** |

`SNOWH` reaches 1.44 m where `sd` reaches 0.42 m of water equivalent. Had the
wrong one been written the field would still have passed every sanity check.

### `snowc` is a fraction, and the wrfout's own description is wrong

`SNOWC`'s description in the file reads *FLAG INDICATING SNOW COVERAGE (1 FOR
SNOW COVER)*. Measured on land: **up to 10 001 distinct values**, 9222 in March,
177 in July. It is a cover fraction, the converter treats it as one, and the
description is what is wrong. Published in per cent, reaching exactly 100.

### `rsn`: the fill matches ERA5's own convention

`rsn` is `SNOW/SNOWH` where there is snow and **100 kg/m³ where there is not**.
That fill was a claim; it is now measured on both sides:

| | |
|---|---|
| our points at exactly 100.0 | equal to the points with `SNOWH` ≤ 1e-6, to within one point |
| ERA5's `rsn` on land, July | exactly 100.0 on **22 432 of 22 494 cells** |
| range over the sample | 59.8 to 500.0 kg/m³ |

500.0 is RUC's own cap on snow density, not ours — the maxima sit on it to seven
digits at several timesteps.

### `tsn`: the mask is exactly the threshold, and the threshold is where it should be

`tsn` is `SOILT1` where `SNOWC > 0.9` and missing elsewhere. At all eight
timesteps examined the bitmap holds **exactly** the points with `SNOWC > 0.9` —
no point inside, none outside — and the field is entirely absent at 7 of the 34
sample timesteps, which is the summer.

The 0.9 threshold was chosen from a measurement on 36 files; it survives the
seasonal sample:

| `SNOWC` band | max `SOILT1` | fraction above freezing |
|---|---|---|
| 0.9–1.0 | 273.16 to 273.17 K at **every** timestep | 0 to 0.07 % |
| 0.5–0.9 | 277 to 280 K | 2 to 59 % |
| 0.01–0.5 | 284 to 292 K | 10 to 98 % |

Above 0.9, `SOILT1` is a snow temperature pinned to the melting point. Below it,
it is a mosaic of snow and bare ground and reaches 19 K above freezing. The
threshold is where the field changes meaning.

### `src` is the same quantity with a different capacity

`src` is `CANWAT` × 1e-3, exact to 2.9e-11, and it is **capped at 0.5 mm** at
every timestep of the sample. ERA5's skin reservoir reaches 0.8 mm on land and
its capacity depends on the vegetation. That, and not an error, is the leg C
ratio of 0.573 and the correlation of 0.55: two skin reservoirs with different
maximum capacities, correlated only through the rainfall that fills them. A user
must not read the ratio as a wet bias.

## What leg C can and cannot settle here

`stl1-4` correlate 0.97 to 0.99 with ERA5 and are biased by −1.4 to +0.05 K;
`swvl1-4` correlate 0.90 to 0.93 and run 1 to 14 per cent wetter. Neither is a
number leg C can adjudicate — a 14 per cent soil-moisture difference between two
different land-surface schemes with different soil databases is not a defect, and
the harness deliberately has no tolerance table to call it one. What leg C **can**
say is that no field is upside down, off by a factor, or in the wrong unit, and
none is.

`sd`'s ratio of 0.882 is the one worth flagging to a reader: we carry 12 per cent
less snow water equivalent than ERA5 in the domain mean. At 3 km against 31 km,
with different snow schemes, that is inside what the resolution gap can produce
and outside what leg C can attribute.

`snowc` has **no ERA5 single-level counterpart**, and the crosswalk says exactly
that rather than claiming no parameter exists — the distinction
[#17](https://github.com/meteocima/CHAPTER/issues/17) found four reasons failing.
Worth one more line of precision: **ERA5-Land does publish paramId 260038**, we
simply do not retrieve ERA5-Land. The verdict rests on legs A and B, and leg B is
exact.

## What this family contaminates

- **Nothing is invalidated.** No other family's variables are touched.
- **[#38](https://github.com/meteocima/CHAPTER/issues/38) must be decided with
  [#36](https://github.com/meteocima/CHAPTER/issues/36)**: both are the question
  of which water mask each field should carry, and two masks decided separately
  would be worse than either decision.
- **Family 7's result is used, not re-measured**: that the hourly mask moves
  exactly with the sea ice is verified there, and this family only had to check
  that the soil bitmap follows it, which it does.

## Repaired: the soil columns take geo_em's permanent land mask

Applied 2026-09-25, option 1 of [#38](https://github.com/meteocima/CHAPTER/issues/38),
decided with the user together with [#36](https://github.com/meteocima/CHAPTER/issues/36)
as that issue asked. One rule for the whole archive: *a point is masked where
the ERA5 parameter is not defined there*, and ERA5 has no soil under sea ice
because its land-sea mask does not move.

Verified on 2024-03-20T12, the sea-ice date, 2469 ice cells:

| | before | after |
|---|---|---|
| `swvl1` present on sea-ice cells | all of them | **0** |
| `swvl1` maximum anywhere | exactly **1.000** | **0.4693** |
| present exactly on geo_em's permanent land | — | **True** |
| `stl1` and `swvl4` masked the same way | — | **True** / **True** |

0.4693 is below every RUC porosity (the highest is 0.485), so the impossible
value is gone rather than merely hidden. The 532 remaining cells of soil type 16
are land ice — glaciers — not sea ice, and they keep their columns.

This knowingly discards values the model really integrated. It is the right
trade because 1.000 m³/m³ against the 0.435 porosity the same file declares is
an artefact of the hourly reclassification and not a measurement, and because
`ci` stays published, so "there is ice here" is not lost.

`lsm` is unaffected and still follows the model hour by hour — measured on the
same file, it differs from the permanent land mask on exactly the 2469 sea-ice
cells. That is the point: the archive says where the model put ice, and does not
pretend there is soil beneath it.
