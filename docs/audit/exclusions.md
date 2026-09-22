# The deliberate exclusions, re-tested

Every field present in the wrfout and deliberately left out, with its stated
reason tested against the data or against ERA5's actual catalogue rather than
accepted.

**No exclusion is overturned into a publication.** The variable set is fixed at
ninety by decision. What this file can change is a *reason*: a wrong reason in a
document that ships with the archive is a defect whether or not the schema moves.

Two of the reasons turn out to be measurements, and both hold. Several turn out
to be imprecise in the same way, and one is simply false. And the list itself is
incomplete.

## The two measurable claims: both confirmed

### `ACRUNOFF` is identical to `SFROFF`, and is not the total

The claim on file is that `ACRUNOFF` is not the total runoff, which is why `ro`
is built as `SFROFF + UDROFF`. Measured over all 34 timesteps of the sample:

| | |
|---|---|
| `max abs(ACRUNOFF − SFROFF)` over the whole sample | **exactly 0** |
| `max abs(ACRUNOFF − (SFROFF + UDROFF))` | 11 to 23 mm depending on the day |

Not "close to": zero, at every point of every timestep in every season. The
reason holds exactly, and `ro`'s construction is right — which matters, because
`ro` **is** published.

### `ACSNOM` is not monotone

The claim is that points reset within a run, which is why `smlt` is not
published. Tested between 00Z and 12Z of the same run, sixteen days:

**Fifteen of sixteen days have points that fall.** Up to 8.2 mm, and tens of
thousands of points in the cold half of the year — 70 647 on 2024-11-15, 60 377
on 2025-01-15, 53 575 on 2024-03-15. The one clean day is 2019-08-15, where the
whole field is of order 1e-23, that is numerically zero.

An accumulator that decreases cannot be published as an accumulation. The reason
holds.

## Reasons that are imprecise in the same way

Four exclusions are on file as "no ERA5 parameter fits". Tested against ECMWF's
own tables and the CDS catalogue together, the truthful statement is different
and the distinction is the one the ERA5 ticket already had to draw for `al`:
**ECMWF defines the parameter; ERA5 does not publish it.**

| ours | ECMWF defines | in ERA5? |
|---|---|---|
| `QGRAUP` | `260028 grle` graupel, `260001 tcolg` total column graupel | **no** — ERA5's pressure levels carry sixteen variables and none is graupel |
| `REFL_10CM`, `REFD_MAX` | `260134 bref` base reflectivity | **no** |
| `LPI` | `228050 litoti` and a family of lightning densities | **no** — and `LPI` is a potential index, not a flash density, so even if ERA5 published them it would not be the same quantity |
| `SNOWFALLAC` | `3066 sde` snow depth, geometric | **no** — ERA5 publishes `141 sd`, which is water equivalent, and that is what we already write from `SNOW` |

The exclusions all stand. The wording does not: "no parameter fits" and "ERA5
does not publish it" are different claims, and the archive's own rule turns on
which one is true.

## One reason that is simply wrong

**`SNOALB`.** On file as having no ERA5 counterpart. ECMWF defines
**`260161 mxsalb`, "Maximum snow albedo"** — which is exactly what `SNOALB` is,
the MODIS maximum snow albedo, under exactly that name.

The exclusion still stands, because ERA5 does not publish `mxsalb` and the set is
not being expanded. But the reason as written is false and should be replaced by
the true one.

## Reasons confirmed, restated precisely

- **`SHDMAX` / `SHDMIN`** — annual maximum and minimum green vegetation fraction.
  ECMWF's nearest is `260180 veg`, an instantaneous vegetation fraction, not an
  annual extreme. Different quantity; reason holds.
- **`TMN`** — deep soil temperature used as the model's lower boundary, an annual
  mean. ECMWF's soil temperatures (`228139 st`, `260360 sot`, and ERA5's
  `stl1-4`) are all temperatures of a defined layer at the valid time. We already
  publish `stl4` over 100-289 cm. Different quantity; reason holds.
- **`SR`** — the frozen fraction of surface precipitation. ERA5's nearest is
  `260015 ptype`, a categorical precipitation type, which is a classification and
  not a fraction. Reason holds.
- **`RHOSNF`** — the density of *falling* snow. ERA5's `33 rsn` is the density of
  the snow *pack*, which we publish. Two different densities; reason holds, and
  it is worth stating in the file because the names invite the confusion.
- **`lai_lv` / `lai_hv`** — ERA5 **does** publish these (`66`, `67`). The refusal
  was never about availability: the model carries one LAI per cell and ERA5 wants
  one per vegetation class, so any split is our assumption. Reason holds. Note
  that `geo_em` carries `LAI12M`, twelve months of observed MODIS LAI, which the
  inventory sweep records — it changes what a future effort could attempt, and it
  does not change this refusal, because the per-class split is still an
  assumption.
- **`anor` / `isor`** — ERA5 publishes both (`162`, `161`). `OA1-4`/`OL1-4` are
  Kim-Arakawa asymmetry and effective length, not ECMWF's gradient-covariance
  eigenstructure. Reason holds.
- **`10efg` / `10nfg`, TKE** — excluded by decision and by absence respectively,
  and the configuration ticket settled the TKE half: `BL_PBL_PHYSICS = 1`, YSU is
  non-local, and `KM_OPT = 4`.

## The list is incomplete: fifteen fields nobody deliberated

The exclusions on file are twelve. Crossing the census's 162 alive fields against
the registry, the converter's inputs, that list and the model's own
infrastructure leaves **fifteen alive fields that are unpublished with no reason
recorded anywhere**. They were not refused; they were never considered.

None of them should be published, and the set is fixed regardless — but an
exclusion that was never deliberated is not an exclusion, it is an oversight, and
the file should say what it is:

| | what it is | why not |
|---|---|---|
| `LWDNB`, `LWDNBC`, `ACSWDNTC` | instantaneous or clear-sky forms of surface and TOA fluxes | we publish the accumulated forms `strd`, `strdc`, `tisr` |
| `PREC_ACC_NC`, `SNOW_ACC_NC` | precipitation and snowfall over the output interval | we publish `tp` and `sf` since 00Z; these are the same quantity on a different interval, and `PREC_ACC_NC` is a free cross-check on `tp` |
| `LAKEMASK` | the runtime lake mask | we publish `cl` from `geo_em`, which is the fractional cover and carries more |
| `COSZEN` | cosine of the solar zenith angle | pure geometry from time and position, no model content; ECMWF defines `260225 solza` and ERA5 does not publish it |
| `LAI` | the model's leaf area index | **belongs with the `lai_lv`/`lai_hv` refusal and is not listed there.** `rdlai2d = .false.`, so this is a table lookup on the dominant category, not observed |
| `SH2O` | unfrozen soil moisture | ERA5's `swvl1-4` are total soil water; there is no separate liquid fraction |
| `HAIL_MAX2D`, `HAIL_MAXK1`, `REFD_MAX`, `UP_HELI_MAX`, `W_UP_MAX`, `W_DN_MAX` | severe-weather diagnostics | no ERA5 parameter of any kind; a 31 km reanalysis does not carry updraft helicity |

## What this changes

Nothing in the archive. Four documentation corrections, all in the same family —
a claim that no parameter exists where one does, and a list that is missing
fifteen entries.
