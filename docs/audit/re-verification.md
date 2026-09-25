# The re-verification gate

Run 2026-09-25, after the six repairs of the go/no-go
([#27](https://github.com/meteocima/CHAPTER/issues/27)) were merged. This is the
gate that issue made a condition of the release, and this document is its
result.

## What was run, and what "passing" means

The audit sample — 34 timesteps, `docs/audit/sample.md` — regenerated from the
wrfout with the repaired converter, then the audit scripts of the **seven
families a repair touches**. Family 4 (radiation) is the only one untouched and
was not re-run.

**The gate's question is not "is everything the same".** Some numbers must move;
that is what a repair is. The question is whether *exactly* the repaired fields
moved, in the predicted direction and magnitude, and whether everything else
stayed put. The second half is the one that would catch a mistake.

Three copies of the pre-repair state were kept so the comparison is against data
and not memory:

| | |
|---|---|
| `$WORK/CHAPTER/grib_audit_prerepair/` | the 34 GRIBs as the audit measured them, 23 GB |
| `$WORK/CHAPTER/audit_rows_prerepair/` | the 69 result JSONs behind every published number |
| `$WORK/CHAPTER/wrfout_audit/` | the 34 wrfout, 179 GB, never deleted (`KEEP_WRFOUT=1`) |

## Production

| | |
|---|---|
| convert jobs | **34 of 34 `COMPLETED 0:0`** |
| GRIBs produced | **34 of 34** |
| `hpc/check_grib_sanity.py` | **`checked=34 bad=0`** |
| family scripts | **11 of 11 `COMPLETED`**, no traceback in any log |

## What moved

### Family 1 — `r` ([#40](https://github.com/meteocima/CHAPTER/issues/40))

| level | ratio to ERA5, before | after | points pinned at exactly 100 |
|---|---|---|---|
| 1000 hPa | 1.049 | 1.042 | **18 509 → 0** |
| 850 hPa | 1.052 | 1.049 | 42 600 → 4 |
| 500 hPa | 0.914 | **0.992** | 917 → 19 |
| 300 hPa | 0.672 | **0.973** | — |
| 200 hPa | 0.636 | 1.040 | — |
| 100 hPa | **0.505** | **0.945** | — |

The family document predicted "0.945 to 1.058 at every level" from the
mixed-phase recomputation. Measured on the rebuilt archive: **0.945 to 1.049**.

### Family 3 — the column integrals ([#46](https://github.com/meteocima/CHAPTER/issues/46))

| `tcwv`, 2024-01-15T12 | before | after |
|---|---|---|
| published ÷ **exact** dry-mass sum | 1.0513 | **1.0000000014** |
| published ÷ the **old** converter rule | 1.0000 | 0.9512 |

Mirror images, which is what a correct swap looks like: the published field used
to be the old rule and 5.1 % above the exact one; it is now the exact one and
4.9 % below the old rule.

Closure, `tcw` minus its five components against the graupel column, worst point:

| timestep | before | after |
|---|---|---|
| 2024-01-15T12 | 0.199 | **4.5e-06** |
| 2024-04-15T12 | 1.066 | **4.7e-06** |
| 2024-07-15T12 | 1.431 | **7.1e-06** |
| 2024-10-15T12 | 1.581 | **7.0e-06** |

### Family 5 — `sf` ([#52](https://github.com/meteocima/CHAPTER/issues/52))

| 2024-02-15T12 | before | after |
|---|---|---|
| `tp − sf − tirf`, max | **11.9747 mm** | **5.5e-06 mm** |
| points above 1e-3 mm | **138 026** | **0** |
| `sf` max | 34.57 mm | 46.35 mm |

### Family 6 — the soil columns ([#38](https://github.com/meteocima/CHAPTER/issues/38))

| | before | after |
|---|---|---|
| `n_saturated_ever`, whole sample | **5 259** | **0** |
| `swvl1` above its own porosity, 2024-01-15T12 | 3 225 | **0** |
| worst excess over porosity | **0.565** | **5.2e-10** |
| land cells carrying a column | 1 307 334 | 1 304 109 |

The 3 225 difference in the land count is exactly the sea ice of that timestep.

### Family 7 — `sst`, `cl`, `dl` ([#36](https://github.com/meteocima/CHAPTER/issues/36))

| | 2024-01-15T12 | 2024-02-15T12 | 2025-02-15T12 |
|---|---|---|---|
| `sst` below 271.35 K | 4 856 → **49** | 1 843 → **7** | 5 957 → **116** |
| of those on inland water | 4 254 → **0** | 1 618 → **0** | 5 286 → **0** |
| coldest point's minimum | 258.14 → **262.38 K** | 252.27 → **266.24 K** | 262.65 → **263.43 K** |
| Black Sea `mean_cl` | 0.9926 → **0.0** | ″ | ″ |
| Black Sea `dl` at the WPS 10 m default | 49 511 → **0** | ″ | ″ |

The strongest single line: **the coldest published `sst` on 2024-01-15 is now at
59.906 N, 29.848 E carrying `ci` = 1.0** — the Gulf of Finland under full sea
ice. Before the repair it was a cell with `cl` = 0.5 and **no ice at all**:
inland water. The field's own extreme moved from an artefact to a physical one.

### Family 8 — `mucin` ([#54](https://github.com/meteocima/CHAPTER/issues/54))

| timestep | fill fraction before | **masked** fraction after | zeros among published | `mucin` max |
|---|---|---|---|---|
| 2024-01-15T12 | 96.2 % | **96.2 %** | **0** | 458.65 |
| 2024-02-15T12 | 94.3 % | **94.3 %** | **0** | 749.62 |
| 2024-03-15T12 | 95.2 % | **95.2 %** | **0** | 490.07 |
| 2024-07-15T12 | 71.2 % | **71.2 %** | **0** | 1236.13 |
| 2024-10-15T12 | 84.8 % | **84.8 %** | **0** | 681.87 |
| 2025-02-15T12 | 94.5 % | **94.5 %** | **0** | 207.48 |

The two columns are equal to the tenth of a per cent: the same points, relabelled
from a false zero to an honest absence. And the maxima are **unchanged** from
before the repair, so the values where the field is present did not move — only
the gaps did.

## What did not move, which is the half that would have caught a mistake

- **Family 2 changed 6 leaves out of 666**, and all six are `published_2r_max`
  going from ~100.0000 to ~100.122. `2t`, `2d`, `10u`/`10v`, `100u`/`100v`,
  `200u`/`200v` and `vwsh`: identical.
- **Family 8's `mucape` is untouched** — zero fraction 0.7693 before and after,
  same maximum, same mean where non-zero — as are `skt`, the stresses, the
  roughness and `msl`.
- **Family 6 changed 14 of 34 timesteps**, exactly the 14 the sea-ice census
  counted; the other 20 are identical.
- **Family 7's July timestep** shows only the mask counts moving: no
  sub-freezing `sst` existed there to fix, and none appeared.

## The gate found a defect in its own instruments

`f8_surface.py` reported `mucin_max: NaN`. That is not the archive: the script
used `.max()` where the field is now **masked**, so a single missing value
poisoned the reduction. A measurement written against the broken field stopped
working when the field was fixed.

Corrected to `nanmax`, with `mucin_masked_fraction` added alongside the zero
fraction so the two states are distinguishable in the record rather than
inferred. It is worth stating plainly: a wrong number in a verification report is
worse than no number, because it is read as evidence.

## Verdict

The gate passes. Every repaired field moved in the predicted direction and, where
the audit had published a prediction, to the predicted value; no unrepaired field
moved at all.
