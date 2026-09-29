# CHAPTER 3 km reanalysis — GRIB2 archive contents

**90 variables, 246 GRIB messages per hourly file.** Taken from the converter's own
registry (`wrf_era5_comparison.WRF_TO_ECMWF_PARAMID`), which is what the pipeline and its
sanity check use, so this document describes what is actually written.

Document updated on 2026-09-18, when the WPS static file `geo_em.d02` was recovered from
LRZ after having been recorded as lost. It carries the FRACTIONAL land cover, soil texture
and lake data that the hourly output had reduced to a single dominant category per cell,
and it added fifteen fields: `cvl`, `cvh`, `tvl`, `tvh`, `slt`, `cl`, `dl` and the eight
ERA5 soil layers. Nothing was removed.

Every field here is one we can defend row by row. Where the WRF quantity is not
exactly the ERA5 one, it is said so below rather than hidden; where it could not be made
to correspond at all, the field was dropped instead of published under a name that would
mislead (see §6).

This document says what is in the files. Two companions say the rest:
[`MISSING_VARIABLES.md`](MISSING_VARIABLES.md) says what is not and why, and
[`CHAPTER_KNOWN_PROPERTIES.md`](CHAPTER_KNOWN_PROPERTIES.md) states the **known properties and
biases** of what is — the places where the archive is correct and surprising, each with the
measured number. Read the third one before comparing this archive against ERA5 or against
observations.

## 1. What the files are

| | |
|---|---|
| Model | WRF 4.1.1, domain d02, 49 vertical levels, model top 50 hPa |
| Horizontal grid | Mercator, **1641 × 1353** points, **3 km** spacing (2 220 273 points/field) |
| Domain corners | 23.472 N, 19.972 W → 60.001 N, 42.256 E; standard parallel 44.671 N |
| Earth shape | **Sphere of radius 6 370 000 m** (`shapeOfTheEarth=1`) — WRF's own sphere, declared explicitly |
| GRIB edition | **GRIB2**, grid definition template **3.10** (Mercator), originating centre `ecmf` |
| Packing | `grid_ccsds`, **24 bits per value**; masked fields carry a proper GRIB bitmap |
| Parameter identity | **ECMWF paramId / shortName** throughout, so the archive is directly comparable with ERA5 |
| File | one file per hour, **~747 MB** (~17.9 GB/day, ~6.6 TB/year) — measured, not estimated |
| Naming | `ailam-an-cima-3km-{year}-{year}-1h-v1-{YYYYMMDD}{HH}.grib` |
| Period | 2019, 2024 and 2025-01-01 → 2025-06-30, hourly (2020–2023 to follow) |

## 2. Vertical levels

**13 pressure levels**, the same for every 3-D variable:

> **1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50 hPa**

They are the ERA5 set truncated at the model top: the 8 ERA5 levels above 50 hPa are above
WRF's `P_TOP` and cannot be produced. Single-level fields sit on `surface`,
`heightAboveGround` (2, 10, 100 and 200 m), `meanSea`, `entireAtmosphere` (column integrals)
or, for the radiation budget at the top of the atmosphere, `nominalTop`.

## 3. Time convention — read this before indexing the archive

- **Instantaneous fields** use product definition template **0**: `dataDate`/`dataTime` are the
  valid time.
- **Accumulated fields** (`tp`, `tirf`, `sf`, `sro`, `ssro`, `ro`, and the whole radiation
  budget) use template **8**, as their ECMWF definitions require. They are accumulated **from
  00 UTC of the same day**: reference time 00 UTC, step `0–H`. They are exactly zero in the 00
  UTC file.
- **`10fg`** is the one exception: it is a **maximum over the preceding hour** (reference time
  H−1, step `0–1`), and it is the maximum of the *resolved* 10 m wind, not a gust
  parameterisation.
- A file therefore mixes reference times on purpose. **Index on validity
  (`validityDate`/`validityTime`), never on `dataTime`.**
- Accumulated messages carry `generatingProcessIdentifier = 128` as the marker of the 00 UTC
  reference.

## 4. Declared approximations

Four fields are not exactly their ERA5 namesake, and are published with that said:

| field | what ERA5 means | what we write |
|---|---|---|
| `slor` | slope of the **sub-grid** orography, a parameter of the form-drag scheme | the slope of the **resolved** 3 km terrain, `\|grad z\|`. Note eccodes will show you the parameter's own name, *Slope of sub-gridscale orography*, so nothing in the message itself says this. `sdor` beside it **is** the ERA5 quantity, only evaluated on a 3 km cell instead of a 31 km one: the measured ratio of medians is 0.244, which is (3/31)^0.605 — a resolution rescaling, not a different definition |
| `10fg` | gust from a parameterisation (turbulent + convective) | the hourly maximum of the **resolved** 10 m wind |
| `iews`, `inss` | the model's own stress components | the magnitude `rho u*^2`, projected on the 10 m wind direction |
| `fsr` | an **effective** roughness, carrying the orographic drag the IFS parameterises at 31 km | WRF's **local** `ZNT`: the land-use roughness with a snow override. Over land it runs at **0.32–0.48 of ERA5's** in the median; over sea the two agree, both being Charnock. `zust` beside it is the model's own friction velocity and runs **1.6–2.1× ERA5's over land** (1.1× over sea) — the other half of the same story, because at 3 km the terrain-driven wind is resolved rather than smoothed |
| `lsm` | a **permanent** land-sea mask; sea ice is carried separately in `ci` | WRF's `LANDMASK`, which reclassifies sea-ice points as land, so the mask **grows in winter**. `lsm & ~(ci > 0)` recovers the ERA5 sense exactly, and `ci` is published |

`lsm` is now the **only** field that follows the model hour by hour (with `al`, which moves with it). The soil columns used to as well, and no longer do: under new sea ice the scheme grows a column that is not soil — `swvl` reached exactly 1.000 against its own soil type's porosity of 0.435 — so since 2026-09-25 they are masked on the **permanent** land of the static file, as ERA5 does. Nothing is lost that cannot be recovered: `ci` is published.

Three more deserve a note rather than a warning:

- **`skt`** is not a model output here (`TSK` was not written): it is inverted from the
  upward longwave, `LWUPB = eps sigma T^4 + (1-eps) LWDN`. The emissivity is not assumed —
  it was **read out of the run itself**. The radiation scheme computes a clear-sky
  diagnostic with the same emissivity and the same skin temperature, changing only the
  downward flux, so the two equations together eliminate the unknown temperature and leave
  `eps = 1 - (LWUPB - LWUPBC)/(LWDN - LWDNC)`. That is an identity, not a fit. Measured this
  way the emissivity came out identical in every cell of a given land-use category (spread
  0.0000 to four decimals), and the control is exact: over open water, where the model's
  skin temperature IS the sea surface temperature, it returns 0.98000.

  **The accuracy is seasonal, and both numbers matter.** The reconstruction reproduces the
  model's own emissivity to 1e-4 on **99.98 % of land points in July and 93.05 % in January**,
  for a land `skt` error of **0.0012 K RMSE in July against 0.115–0.133 K in January and
  February** (p99 0.85 K, worst point 2.8 K). All of that spread is the snow rule: snow raises
  the emissivity to a flat 0.98 in every category, applied from 1.5 % snow cover upwards, with a
  blend below it. That threshold is the only quantity in this derivation that was chosen rather
  than read out of the run, so it was measured: swept over all 34 sample timesteps against the
  emissivity the model actually used, 1.5 % is the minimum of the resulting skin-temperature
  error. Over open water, where the answer
  is known independently, it recovers the sea surface temperature to **0.0005 K RMSE** on about
  910 000 points at every timestep of every season. Note this derivation error is thirty times
  smaller than the physical cold bias of the land skin itself — which is the separate and
  much larger fact: **`skt` over land runs about 1.6 K below ERA5, reaching 3.2 K at midday**,
  while over sea it is exact (+0.01 K). That is the run, not the derivation; the sea number is
  the control that proves it. Reconciling it against the extra shortwave and the missing cloud
  above would need the surface energy budget, and `HFX`, `LH` and the ground heat flux are the
  three fields this archive does not have.

- **`al`** is a two-season table value, not a field. No monthly satellite albedo was used
  (`usemonalb = .false.`), so the snow-free background comes from the land-use table's WINTER
  and SUMMER columns by dominant category: it takes only **8 to 11 distinct values** over the
  whole domain, and it changes at **1 171 937 land points — 89.9 % of the land mask — at the
  seasonal boundary**, which is April and November, not a physical transition. Off land it is
  0.08 on water and 0.65 on sea ice. Do not read it as an observed or evolving albedo, and do
  not difference it across the boundary expecting a signal. `fal`, beside it, is the actual
  ratio the simulation used and does evolve.
- **The surface shortwave carries a systematic high bias.** RRTMG ran with an ozone
  climatology and **no aerosol at all** (`aer_opt = 0`), while ERA5 carries the Tegen aerosol
  climatology; over this domain an optical depth of 0.1 to 0.2 accounts for the size. Measured
  against ERA5: **+8.5 % under clear sky** (`ssrdc`) and **+13.6 % all-sky** (`ssrd`). The
  thermal fields are untouched by it and agree to within 1.1 %, which is the control that
  makes the attribution credible. Total cloud cover also runs **22 % below** ERA5 and high
  cloud **39 % below**, which pushes surface solar the same way. Both are properties of the
  run and cannot be removed after the fact; they and the rest of the archive's measured
  biases are stated in full in `CHAPTER_KNOWN_PROPERTIES.md`.
- **Below the ground the pressure levels are clamped, not extrapolated.** Where a level lies
  under the terrain, the archive repeats the **lowest model level's value verbatim** — matched
  to exactly 0.0 for `t`, 1e-9 for `q`. That is a real model state from about 24 to 27 m above
  the ground rather than synthetic air, and it keeps the surface join coherent. But **ERA5
  extrapolates there with a lapse rate**, so the two archives differ in convention exactly
  where 1000 hPa is underground, which is most of the land; and our `z` at 1000 hPa then sits a
  median of 24 to 27 m *above* the terrain that `sp` puts it below, on **47.6 % of the domain**
  at 1000 hPa and 9 % at 925. Mask the levels against `sp` if you need a clean comparison —
  every field needed to do it is in the same file.
- **`sst`** is constant within each 24 h run (`SST_UPDATE=0`), re-initialised daily.
- **`dl`** is the lake depth database the run was built with, not a model state: lake
  physics was off (`sf_lake_physics=0`), so nothing in the simulation responds to it. It
  is published as the boundary dataset it is, and masked off-lake — the raw field is the
  10 m WPS default fill on 99.56 % of the domain, and 79 464 of the 88 785 lake cells
  carry that same default (ERA5's own `dl` does the same where the database is silent).

## 5. Masked fields

Written with a GRIB bitmap rather than fake zeros, so missing means missing:

| field | defined where |
|---|---|
| `sst`, `ci` | **sea** points only — and sea here is not simply "not land": WPS's land-use class calls the Black Sea, the Sea of Azov and part of the Baltic a *lake*, so masking on that class would have deleted `sst` from the Black Sea. The discriminator is connected-component size, measured: the water bodies of this domain are 844 431 cells (Atlantic + Mediterranean + Baltic + North Sea), 49 841 (Black Sea + Azov), 8 583 (Red Sea), then 1 225 (Vänern, the largest genuine lake) and smaller, so the cut sits in a gap with a factor of seven of slack |
| `cl` | zero on the sea rather than missing, since a sea point genuinely has no lake cover |
| `mucin` | the columns where the CAPE routine returns a value at all, i.e. where CAPE reaches 100 J/kg. **That is 4 % to 29 % of the domain**, least in winter. The gaps are written as missing rather than zero, because zero would read as "nothing inhibits convection" at precisely the columns where the most does |
| `tsn` | cells whose snow cover exceeds 0.9 (≈ 29 mm water equivalent); out of season the field is legitimately empty |
| `fal` | daytime only (incoming shortwave above 50 W/m²) |
| `swvl1-4`, `stl1-4` | the **permanent** land of the static file — a fixed outline, the same in every file of the archive. Sea ice therefore carries no soil column, which is what ERA5 does too |
| `slt` | land points of the static file (1 304 109 cells) |
| `tvl` | everywhere except the cells where a shrubland dominates the low vegetation (124 672 cells, 15.8 % of those with `cvl > 0`). MODIS carries no shrub phenology while ECMWF's table splits evergreen from deciduous shrubs, and rather than invent one the field is left missing. `cvl` still gives the cover there |
| `dl` | lake cells only (88 785) |

## 6. What is not in the archive

No TKE and no boundary-layer height (the PBL scheme is YSU, non-local); no ocean waves,
currents, sea surface height or sea-ice thickness (no ocean or wave coupling); no convective
precipitation (`CU_PHYSICS=0`, so it is identically zero and would be a dead field).

Deliberately dropped rather than approximated:

- **leaf area index** (`lai_lv`, `lai_hv`): the model carries a single LAI per cell, while
  ERA5 wants one per vegetation class, defined per unit of vegetated area. Any split between
  the two would be our assumption, so neither field is written. **The single field itself is
  in the model output** — alive, and unpublished for that reason alone; it can be delivered
  under its own name, `LAI`, if it is wanted. Note `rdlai2d = .false.`, so it is a table
  lookup on the dominant category rather than an observation, which is a second reason not
  to split it;
- **sub-grid orography angle and anisotropy** (`anor`, `isor`): the static file carries the
  Kim-Arakawa asymmetry and effective-length parameters, which are not ECMWF's, and the
  difference does not fit in one line.

Four entries that stood here until 2026-09-17 have moved into the archive, because
`geo_em.d02` came back and because the soil objection had an answer:

- **`swvl1-4` / `stl1-4`** are now the true ERA5 layer averages. The land-surface scheme is a
  *level* scheme — point values at 0, 5, 20, 40, 160 and 300 cm with a linear profile between
  them — and the whole ERA5 column lies inside those nodes (289 cm is above the deepest, 0 cm
  is the first). So each layer average is the exact integral of the model's own profile and
  **nothing is extrapolated**. The objection was against writing the point values, not against
  integrating them;
- **`cvl` / `cvh`** are sums of the fractional cover over the MODIS-IGBP classes that are low
  and high vegetation — the same quantity ERA5 means. This is what the dominant category could
  not express: it holds only 90.1 % of a land cell on average, and 17.9 % of land cells carry
  both high and low vegetation above 5 %;
- **`tvl` / `tvh`** are the dominant low and high class translated to ECMWF code table 4.234
  by the table in §8, where each row is a semantic identity. The one place MODIS cannot answer
  the question — evergreen versus deciduous shrubs — is left missing rather than guessed;
- **`slt`** is computed with the FAO clay/sand thresholds that *define* ECMWF's seven soil
  types, applied to the static file's own clay and sand fractions. No category crosswalk is
  involved, so the quantity is ERA5's by construction. One caveat for a strict WMO reader:
  eccodes resolves `slt` to discipline 2/3/0, which WMO table 4.213 reads as a different
  11-value list. This archive is ECMWF semantics throughout, and so is this message.

`cl` and `dl` came with them. `cl` is not redundant with the land-sea mask: 19 309 cells that
the mask calls land carry a sub-grid lake, and the model itself discarded the class at runtime.

The full reasoning, and the routes by which some of it could still be obtained, is in
`MISSING_VARIABLES.pdf`.

## 7. The variables

Descriptions and units are the ECMWF ones. "Time" says how the field is sampled. There are 90
rows and 89 distinct shortNames, because `z` is written twice: as geopotential on the pressure
levels and as the surface geopotential (orography).
variables=90 messages=246

### Pressure levels (13) — 13 variables, 169 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `cc` | 248 | Fraction of cloud cover | (0-1) | 13 levels | instantaneous |
| `ciwc` | 247 | Specific cloud ice water content | kg/kg | 13 levels | instantaneous |
| `clwc` | 246 | Specific cloud liquid water content | kg/kg | 13 levels | instantaneous |
| `crwc` | 75 | Specific rain water content | kg/kg | 13 levels | instantaneous |
| `cswc` | 76 | Specific snow water content | kg/kg | 13 levels | instantaneous |
| `q` | 133 | Specific humidity | kg/kg | 13 levels | instantaneous |
| `r` | 157 | Relative humidity | % | 13 levels | instantaneous |
| `t` | 130 | Temperature | K | 13 levels | instantaneous |
| `u` | 131 | U component of wind | m/s | 13 levels | instantaneous |
| `v` | 132 | V component of wind | m/s | 13 levels | instantaneous |
| `w` | 135 | Vertical velocity (pressure) | Pa/s | 13 levels | instantaneous |
| `wz` | 260238 | Geometric vertical velocity | m/s | 13 levels | instantaneous |
| `z` | 129 | Geopotential | m^2/s^2 | 13 levels | instantaneous |


### Height above ground — 11 variables, 11 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `100u` | 228246 | 100m U component of wind | m/s | 100 m | instantaneous |
| `100v` | 228247 | 100m V component of wind | m/s | 100 m | instantaneous |
| `10fg` | 49 | 10m wind gust (hourly max of resolved wind) | m/s | 10 m | max over the previous hour |
| `10u` | 165 | 10m U component of wind | m/s | 10 m | instantaneous |
| `10v` | 166 | 10m V component of wind | m/s | 10 m | instantaneous |
| `200u` | 228239 | 200m U component of wind | m/s | 200 m | instantaneous |
| `200v` | 228240 | 200m V component of wind | m/s | 200 m | instantaneous |
| `2d` | 168 | 2m dewpoint temperature | K | 2 m | instantaneous |
| `2r` | 260242 | 2m relative humidity | % | 2 m | instantaneous |
| `2t` | 167 | 2m temperature | K | 2 m | instantaneous |
| `vwsh` | 260068 | Vertical speed shear (bulk 10-100 m) | s^-1 | 100 m | instantaneous |


### Mean sea level — 1 variables, 1 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `msl` | 151 | Mean sea level pressure | Pa | mean sea level | instantaneous |


### Total column — 10 variables, 10 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `hcc` | 188 | High cloud cover | (0-1) | column | instantaneous |
| `lcc` | 186 | Low cloud cover | (0-1) | column | instantaneous |
| `mcc` | 187 | Medium cloud cover | (0-1) | column | instantaneous |
| `tcc` | 164 | Total cloud cover | (0-1) | column | instantaneous |
| `tciw` | 79 | Total column cloud ice water | kg/m^2 | column | instantaneous |
| `tclw` | 78 | Total column cloud liquid water | kg/m^2 | column | instantaneous |
| `tcrw` | 228089 | Total column rain water | kg/m^2 | column | instantaneous |
| `tcsw` | 228090 | Total column snow water | kg/m^2 | column | instantaneous |
| `tcw` | 136 | Total column water | kg/m^2 | column | instantaneous |
| `tcwv` | 137 | Total column water vapour | kg/m^2 | column | instantaneous |


### Surface / single level — 47 variables, 47 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `al` | 174 | Albedo (climatological, snow-free background) | (0-1) | surface | instantaneous |
| `ci` | 31 | Sea ice area fraction | (0-1) | surface | instantaneous |
| `cl` | 26 | Lake cover | (0-1) | surface | instantaneous, static |
| `cvh` | 28 | High vegetation cover | (0-1) | surface | instantaneous, static |
| `cvl` | 27 | Low vegetation cover | (0-1) | surface | instantaneous, static |
| `fal` | 243 | Forecast albedo (upward/downward SW at surface) | (0-1) | surface | instantaneous |
| `fsr` | 244 | Forecast surface roughness | m | surface | instantaneous |
| `iews` | 229 | Instantaneous eastward turbulent surface stress | N/m^2 | surface | instantaneous |
| `inss` | 230 | Instantaneous northward turbulent surface stress | N/m^2 | surface | instantaneous |
| `lsm` | 172 | Land-sea mask | (0-1) | surface | instantaneous |
| `ro` | 205 | Runoff (surface + sub-surface) | m | surface | accumulated since 00 UTC |
| `rsn` | 33 | Snow density | kg/m^3 | surface | instantaneous |
| `sd` | 141 | Snow depth (water equivalent) | m | surface | instantaneous |
| `sdor` | 160 | Standard deviation of orography | m | surface | instantaneous |
| `sf` | 144 | Snowfall (water equivalent) | m | surface | accumulated since 00 UTC |
| `skt` | 235 | Skin temperature (inverted from upward longwave) | K | surface | instantaneous |
| `slor` | 163 | Slope of orography (resolved, 3 km) | Numeric | surface | instantaneous |
| `slt` | 43 | Soil type (ECMWF 7 classes) | ~ | surface | instantaneous, static |
| `snowc` | 260038 | Snow cover | % | surface | instantaneous |
| `sp` | 134 | Surface pressure | Pa | surface | instantaneous |
| `src` | 198 | Skin reservoir content | m | surface | instantaneous |
| `sro` | 8 | Surface runoff | m | surface | accumulated since 00 UTC |
| `ssr` | 176 | Surface net solar radiation | J/m^2 | surface | accumulated since 00 UTC |
| `ssrc` | 210 | Surface net solar radiation, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `ssrd` | 169 | Surface solar radiation downwards | J/m^2 | surface | accumulated since 00 UTC |
| `ssrdc` | 228129 | Surface solar radiation downwards, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `ssro` | 9 | Sub-surface runoff | m | surface | accumulated since 00 UTC |
| `sst` | 34 | Sea surface temperature | K | surface | instantaneous |
| `stl1` | 139 | Soil temperature level 1 (0-7 cm) | K | surface | instantaneous |
| `stl2` | 170 | Soil temperature level 2 (7-28 cm) | K | surface | instantaneous |
| `stl3` | 183 | Soil temperature level 3 (28-100 cm) | K | surface | instantaneous |
| `stl4` | 236 | Soil temperature level 4 (100-289 cm) | K | surface | instantaneous |
| `str` | 177 | Surface net thermal radiation | J/m^2 | surface | accumulated since 00 UTC |
| `strc` | 211 | Surface net thermal radiation, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `strd` | 175 | Surface thermal radiation downwards | J/m^2 | surface | accumulated since 00 UTC |
| `strdc` | 228130 | Surface thermal radiation downwards, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `swvl1` | 39 | Volumetric soil water layer 1 (0-7 cm) | m^3/m^3 | surface | instantaneous |
| `swvl2` | 40 | Volumetric soil water layer 2 (7-28 cm) | m^3/m^3 | surface | instantaneous |
| `swvl3` | 41 | Volumetric soil water layer 3 (28-100 cm) | m^3/m^3 | surface | instantaneous |
| `swvl4` | 42 | Volumetric soil water layer 4 (100-289 cm) | m^3/m^3 | surface | instantaneous |
| `tirf` | 235015 | Time integral of rain flux (rain only) | kg/m^2 | surface | accumulated since 00 UTC |
| `tp` | 228 | Total precipitation | m | surface | accumulated since 00 UTC |
| `tsn` | 238 | Temperature of snow layer | K | surface | instantaneous |
| `tvh` | 30 | Type of high vegetation (ECMWF code table 4.234) | ~ | surface | instantaneous, static |
| `tvl` | 29 | Type of low vegetation (ECMWF code table 4.234) | ~ | surface | instantaneous, static |
| `z` | 129 | Geopotential (surface) | m^2/s^2 | surface | instantaneous |
| `zust` | 228003 | Friction velocity | m/s | surface | instantaneous |


"static" in the Time column means the field is identical in every file of the archive: it
comes from the run's static input, not from the hourly state. `lsm` is deliberately NOT
static — the model reclassifies sea points as land where sea ice appears, so it changes
with the season.

### Entire lake — 1 variable, 1 message

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `dl` | 228007 | Lake total depth | m | entireLake | instantaneous, static |

### Top of atmosphere / most unstable parcel — 7 variables, 7 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `mucape` | 228235 | Most-unstable CAPE | J/kg | most unstable parcel | instantaneous |
| `mucin` | 228236 | Most-unstable CIN | J/kg | most unstable parcel | instantaneous |
| `tisr` | 212 | TOA incident solar radiation | J/m^2 | top of atmosphere | accumulated since 00 UTC |
| `tsr` | 178 | Top net solar radiation | J/m^2 | top of atmosphere | accumulated since 00 UTC |
| `tsrc` | 208 | Top net solar radiation, clear sky | J/m^2 | top of atmosphere | accumulated since 00 UTC |
| `ttr` | 179 | Top net thermal radiation | J/m^2 | top of atmosphere | accumulated since 00 UTC |
| `ttrc` | 209 | Top net thermal radiation, clear sky | J/m^2 | top of atmosphere | accumulated since 00 UTC |


## 8. How the land-surface categories were translated

`tvl`, `tvh` and `slt` are the only fields in the archive that carry a *code* rather than a
number, so the tables that produced them are published here: without them the codes cannot be
read, and the mapping cannot be checked.

The source is the run's own static file `geo_em.d02` (MODIS-IGBP 21 classes, WPS
`MMINLU=MODIFIED_IGBP_MODIS_NOAH`). Its land use was verified against the hourly output: it
agrees with the model's dominant category on **100.00 %** of points once one expected
difference is excluded — the model recodes lake to water at runtime, because lake physics was
off. This is what makes `cl` recoverable at all.

### `tvl` / `tvh`: MODIS-IGBP → ECMWF code table 4.234

High and low follow the IGBP class definitions of tree cover, not a canopy-height table.

| MODIS-IGBP class | set | ECMWF 4.234 |
|---|---|---|
| 1 Evergreen Needleleaf Forest | high | 3 Evergreen needleleaf trees |
| 2 Evergreen Broadleaf Forest | high | 6 Evergreen broadleaf trees |
| 3 Deciduous Needleleaf Forest | high | 4 Deciduous needleleaf trees |
| 4 Deciduous Broadleaf Forest | high | 5 Deciduous broadleaf trees |
| 5 Mixed Forests | high | 18 Mixed forest/woodland |
| 8 Woody Savannas | high | 19 Interrupted forest (both are 30–60 % tree cover) |
| 9 Savannas | low | 7 Tall grass |
| 10 Grasslands | low | 2 Short grass |
| 11 Permanent Wetlands | low | 13 Bogs and marshes (absent from this domain) |
| 12 Croplands | low | 1 Crops, mixed farming |
| 14 Cropland/Natural Mosaic | low | 1 Crops, mixed farming (absent from this domain) |
| 18 Wooded Tundra, 19 Mixed Tundra, 20 Barren Tundra | low | 9 Tundra |
| **6 Closed Shrublands, 7 Open Shrublands** | low | **not translated — `tvl` is missing there** |
| 13 Urban, 15 Snow and Ice, 16 Barren, 17 Water, 21 Lake | neither | — (not vegetation; they are the remainder of `1 − cvl − cvh`) |

Every translated row is a semantic identity: the ECMWF type names the same vegetation as the
MODIS class. The two shrubland classes are the exception and are the reason `tvl` carries a
mask. MODIS does not record whether a shrubland is evergreen or deciduous, while table 4.234
has separate codes for the two (16 and 17). Choosing one would have been our invention over
16.2 % of the vegetated cells, so the field is left missing there instead; `cvl` still reports
the cover. The classes that would have been the other ambiguous rows, 11 and 14, do not occur
in this domain at all.

### `slt`: computed, not translated

No category crosswalk is involved. ECMWF's seven soil types are *defined* by clay and sand
percentage thresholds, and the static file carries clay and sand fractions, so the definition
is applied directly:

| condition (percent) | ECMWF soil type |
|---|---|
| clay ≥ 60 | 5 very fine |
| 35 ≤ clay < 60 | 4 fine |
| clay < 35 and sand ≤ 15 | 3 medium fine |
| (18 ≤ clay < 35 and sand > 15) or (clay < 18 and 15 < sand ≤ 65) | 2 medium |
| clay < 18 and sand > 65 | 1 coarse |
| dominant soil category is *organic material* | 6 organic |

Every land point classifies; type 7 (tropical organic) does not occur here. Distribution over
the 1 304 109 land points: 1 069 456 medium, 187 378 coarse, 45 450 fine, 1 498 organic, 327
very fine.

### `swvl1-4` / `stl1-4`: integrated, not relabelled

The land-surface scheme is a *level* scheme: it carries point values at 0, 5, 20, 40, 160 and
300 cm, with a linear profile between them. ERA5 wants averages over 0–7, 7–28, 28–100 and
100–289 cm. Those four intervals lie entirely inside the model's own nodes — 289 cm is above
the deepest one and 0 cm is the first — so each ERA5 layer is the **exact integral** of the
model's profile over it, and nothing is extrapolated at either end. In practice this is a
fixed 4 × 6 matrix of weights, applied to the six model levels.

`swvl` uses the total soil moisture (liquid plus ice), which is what the ERA5 name means; the
liquid-only field is not used. Both sets are masked over water.
