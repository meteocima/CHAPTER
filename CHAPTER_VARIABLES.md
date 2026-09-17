# CHAPTER 3 km reanalysis — GRIB2 archive contents

**90 variables, 246 GRIB messages per hourly file.** Generated from the converter's own
registry (`wrf_era5_comparison.WRF_TO_ECMWF_PARAMID`), which is what the pipeline and its
sanity check use, so this document cannot drift from what is actually written.

Document generated on 2026-09-17.

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
| File | one file per hour, **~770 MB** (~19 GB/day, ~7 TB/year) |
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

## 4. Masked fields

Written with a GRIB bitmap rather than fake zeros, so missing means missing:

| field | defined where |
|---|---|
| `sst`, `ci` | sea points only |
| `tsn` | cells whose snow cover exceeds 0.9 (≈ 29 mm water equivalent); out of season the field is legitimately empty |
| `fal` | daytime only (incoming shortwave above 50 W/m²) |

## 5. What is not in the archive

No TKE and no boundary-layer height (the PBL scheme is YSU, non-local); no ocean waves,
currents, sea surface height or sea-ice thickness (no ocean or wave coupling); no convective
precipitation (`CU_PHYSICS=0`, so it is identically zero and would be a dead field); no
fractional land cover (only the dominant category survives). The full reasoning, and the routes
by which some of it could still be obtained, is in `MISSING_VARIABLES.pdf`.

## 6. The variables

Descriptions and units are the ECMWF ones. "Time" says how the field is sampled.

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


### Surface / single level — 48 variables, 48 messages

| shortName | paramId | Description | Units | Level | Time |
|---|---|---|---|---|---|
| `al` | 174 | Albedo (climatological, snow-free background) | (0-1) | surface | instantaneous |
| `ci` | 31 | Sea ice area fraction | (0-1) | surface | instantaneous |
| `cvh` | 28 | High vegetation cover | (0-1) | surface | instantaneous |
| `cvl` | 27 | Low vegetation cover | (0-1) | surface | instantaneous |
| `fal` | 243 | Forecast albedo (upward/downward SW at surface) | (0-1) | surface | instantaneous |
| `fsr` | 244 | Forecast surface roughness | m | surface | instantaneous |
| `iews` | 229 | Instantaneous eastward turbulent surface stress | N/m^2 | surface | instantaneous |
| `inss` | 230 | Instantaneous northward turbulent surface stress | N/m^2 | surface | instantaneous |
| `lai_hv` | 67 | Leaf area index, high vegetation | m^2/m^2 | surface | instantaneous |
| `lai_lv` | 66 | Leaf area index, low vegetation | m^2/m^2 | surface | instantaneous |
| `lsm` | 172 | Land-sea mask | (0-1) | surface | instantaneous |
| `ro` | 205 | Runoff (surface + sub-surface) | m | surface | accumulated since 00 UTC |
| `rsn` | 33 | Snow density | kg/m^3 | surface | instantaneous |
| `sd` | 141 | Snow depth (water equivalent) | m | surface | instantaneous |
| `sdor` | 160 | Standard deviation of orography | m | surface | instantaneous |
| `sf` | 144 | Snowfall (water equivalent) | m | surface | accumulated since 00 UTC |
| `skt` | 235 | Skin temperature (from upward longwave) | K | surface | instantaneous |
| `slor` | 163 | Slope of sub-gridscale orography | Numeric | surface | instantaneous |
| `slt` | 43 | Soil type (WRF dominant category) | category | surface | instantaneous |
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
| `stl1` | 139 | Soil temperature level 1 | K | surface | instantaneous |
| `stl2` | 170 | Soil temperature level 2 | K | surface | instantaneous |
| `stl3` | 183 | Soil temperature level 3 | K | surface | instantaneous |
| `stl4` | 236 | Soil temperature level 4 | K | surface | instantaneous |
| `str` | 177 | Surface net thermal radiation | J/m^2 | surface | accumulated since 00 UTC |
| `strc` | 211 | Surface net thermal radiation, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `strd` | 175 | Surface thermal radiation downwards | J/m^2 | surface | accumulated since 00 UTC |
| `strdc` | 228130 | Surface thermal radiation downwards, clear sky | J/m^2 | surface | accumulated since 00 UTC |
| `swvl1` | 39 | Volumetric soil water layer 1 | m^3/m^3 | surface | instantaneous |
| `swvl2` | 40 | Volumetric soil water layer 2 | m^3/m^3 | surface | instantaneous |
| `swvl3` | 41 | Volumetric soil water layer 3 | m^3/m^3 | surface | instantaneous |
| `swvl4` | 42 | Volumetric soil water layer 4 | m^3/m^3 | surface | instantaneous |
| `tirf` | 235015 | Time integral of rain flux (rain only) | kg/m^2 | surface | accumulated since 00 UTC |
| `tp` | 228 | Total precipitation | m | surface | accumulated since 00 UTC |
| `tsn` | 238 | Temperature of snow layer | K | surface | instantaneous |
| `tvh` | 30 | Type of high vegetation (WRF/MODIS dominant category) | category | surface | instantaneous |
| `tvl` | 29 | Type of low vegetation (WRF/MODIS dominant category) | category | surface | instantaneous |
| `z` | 129 | Geopotential (surface) | m^2/s^2 | surface | instantaneous |
| `zust` | 228003 | Friction velocity | m/s | surface | instantaneous |


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

