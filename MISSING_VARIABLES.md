# CHAPTER 3 km — requested variables that are not directly available

**Date:** 2026-09-16 · **Scope:** the variable list requested for the CHAPTER regional reanalysis
(atmosphere, static, land-surface, ocean waves, sea ice, surface ocean).

This note answers one question: of the variables you asked for, which ones can we actually put in
the GRIB archive, which ones we can obtain by some other route, and which ones are simply not in
the data. It is meant to be read before we commit to a re-conversion of the whole archive, because
that re-conversion costs several days of data transfer and has to be done only once.

Everything below was verified against the actual files, not against documentation: model
configuration read from the wrfout global attributes, and every field checked for real values on
four independent timesteps (summer 2019, summer 2024 at 00/06/12/18 UTC, and March 2024) so that
fields which exist in the file but are identically zero are not mistaken for usable data.

---

## 1. Summary

| requested block | verdict |
|---|---|
| Atmosphere, surface (24 variables + wind shear) | **22 of 24 delivered**, plus wind shear. Only the two gust components are missing |
| Atmosphere, pressure levels (9 variables × 13 levels) | **all delivered**, and both vertical-velocity forms (`w` in Pa/s and `wz` in m/s) |
| TKE at 3 height levels | **not available** — the model does not compute it |
| Static: orography | **delivered** |
| Static: land-use / land-cover | **partially** — dominant category only, not fractions. Fractions obtainable from other files |
| Land-surface | **delivered** as the subset that exists, with ERA5 names |
| Ocean waves (SWH, period, direction, wave-dependent Cd) | **not available** — no wave model |
| Sea ice | **concentration delivered**; thickness, snow on ice, ice temperature and albedo not available |
| Surface ocean (SSH, currents, SST) | **SST delivered**; SSH and currents not available |

---

## 2. Why: how the archive is produced

The archive is produced from hourly WRF 4.1.1 output (domain d02, Mercator, 1641 × 1353 points at
3 km, 49 vertical levels). The relevant configuration is identical across all periods we checked
(2019, March 2024, July 2024):

| option | value | consequence for this list |
|---|---|---|
| `BL_PBL_PHYSICS` | 1 (YSU) | non-local scheme: **no prognostic TKE**. `PBLH` was also not written out |
| `KM_OPT` | 4 | no prognostic turbulent kinetic energy array either |
| `SF_OCEAN_PHYSICS` | 0 | **the ocean is not simulated**: no currents, no sea surface height, no mixed layer |
| (no wave model) | — | **no wave fields** of any kind, and therefore no wave-dependent drag coefficient |
| `SST_UPDATE` | 0 | SST is **constant within each 24 h run**, re-initialised at every daily run |
| `CU_PHYSICS` | 0 | convection-permitting: `RAINC` is identically zero, so total precipitation is complete in `RAINNC` |
| `MP_PHYSICS` | 6 (WSM6) | cloud, rain, ice, snow and graupel are available; **no hail category** |
| `SF_SURFACE_PHYSICS` | 3 (RUC) | 6 soil levels at 0, 5, 20, 40, 160, 300 cm (ERA5 uses 4 layers) |
| `SF_LAKE_PHYSICS`, `SF_URBAN_PHYSICS` | 0, 0 | no lake model, no urban canopy |
| `ICLOUD` | 1 | the cloud fraction field is **binary 0/1**, not fractional |

A separate point worth making explicitly: some fields are present in the files but are
**identically zero on every timestep we sampled**, and are therefore not usable. These are
`ACHFX`, `ACLHF`, `ACGRDFLX`, `NOAHRES`, `SSTSK`, `SST_INPUT`, `SWNORM`, `ACSNOW`, `HAILNC`,
`RAINC`, `RAINSH`, `PREC_ACC_C`, and the downward longwave at the top of the atmosphere. None of
them will be written to the GRIB files.

---

## 3. Variables we can obtain by another route

These are not in the model output, but there is a defensible way to get them. None of them is
implemented yet: each needs a decision first.

| variable | route | confidence | cost |
|---|---|---|---|
| Fractional land cover (forest, crops, urban as **fractions**), `GREENFRAC`, soil texture fractions | They exist in the WRF **static `geo_em_d02` file**, which is not part of the hourly output. It is a single file of a few tens of MB | **Exact** — these are the very fields WRF was initialised with | One request to LRZ, then a one-off ingest. Clearly the best option |
| `10efg`, `10nfg` (eastward / northward gust components) | Decompose the available gust proxy along the mean wind direction: `10efg = 10fg · U10/\|U10\|`, likewise for the northward component | **Low to medium.** The magnitude is a diagnostic, see the caveat in §5; the direction assumption (gust aligned with the mean wind) is standard but crude | Free |
| Sea-ice surface temperature | Use the skin temperature we already derive, restricted to points where sea-ice concentration > 0 | **Medium.** It is a radiative skin temperature, consistent with the model's own longwave emission, but not a dedicated ice-surface temperature | Free |
| Surface albedo (including over ice) | Ratio of upward to downward shortwave at the surface, both available | **Good during daytime**, undefined at night and near sunrise/sunset | Free |
| Drag coefficient **without** wave effect | From the model's own roughness length: `Cd = (κ / ln(10/z0))²` | **Exact** — this is precisely the drag the simulation used (Charnock, no wave coupling) | Free |
| Planetary boundary layer height | Bulk Richardson number on the virtual potential temperature profile; all required fields are present | **Reasonable** — the same class of diagnostic the model itself would apply | Free |

---

## 4. Variables we cannot provide

| variable | why | the only way to get it |
|---|---|---|
| **TKE** (at any level) | The PBL scheme is YSU, which is non-local and carries no turbulent kinetic energy; the diffusion option does not produce one either. The field does not exist, at any height | Re-run WRF with a TKE-carrying PBL scheme (MYNN or MYJ). A similarity-theory estimate would need boundary-layer height *and* surface heat flux, both themselves missing, so the errors compound: it would look plausible but would not be consistent with the simulation |
| **Significant wave height, mean wave period, wave direction** | No wave model was coupled to the atmosphere | A wave model run, or an external wave reanalysis (ERA5 waves at ~31 km) — which loses exactly the coastal detail that motivates a 3 km product |
| **Drag coefficient including wave effect** | Same reason: the surface exchange used Charnock roughness with no sea state | As above. The wave-free drag coefficient *is* available (§3) |
| **Sea surface height, ocean currents (u, v)** | The ocean is not simulated | An ocean reanalysis (e.g. CMEMS), regridded |
| **Sea-ice thickness, snow thickness on sea ice** | Not simulated. Sea ice enters only as a concentration boundary field | An external sea-ice product |
| **Sea-ice albedo** as a prognostic ice property | Not simulated | Approximable radiatively (§3), but not as an ice-model variable |
| **Snowmelt** | The field exists (`ACSNOM`) but is **not a monotone accumulator**: individual points drop back to zero within a single run (measured -7.26 mm against 00 UTC on 2024-07-01), so it cannot be referred to 00 UTC the way the other accumulations are. Published under the ERA5 name it would be wrong | Would need the melt diagnosed per timestep inside the model |
| **Surface sensible and latent heat flux** | The instantaneous fields were not written out, and the accumulated ones are identically zero in every file we checked | Partially reconstructable from the surface energy budget, but the ground heat flux is also missing, leaving two unknowns in one equation. Best treated as unavailable |
| **Skin temperature as a model variable** | `TSK` was not written out | We already provide `skt`, obtained by inverting the upward longwave flux (see §5) |

---

## 5. Caveats on the variables we *do* provide

These matter for correct use and should be read together with the variable list.

- **Cloud cover is built from a binary cloud field.** The model's cloud fraction is 0 or 1 at each
  level. Total, high, medium and low cloud cover are computed from it with maximum-random overlap,
  so the column values are fractional and well behaved, but they inherit a cloud field that has no
  sub-grid fractional information.
- **SST is constant within each day.** Each daily run is initialised with a fixed sea surface
  temperature and does not update it. The field therefore has a daily, not hourly, time resolution.
- **Skin temperature is derived, not modelled.** It is obtained by inverting the upward longwave
  flux assuming an emissivity of 0.98.
- **Soil layers are a mapping, not an identity.** The land-surface scheme uses 6 levels at 0, 5,
  20, 40, 160 and 300 cm; ERA5 uses 4 layers at 0-7, 7-28, 28-100 and 100-289 cm. We map the first
  four onto the ERA5 names; the two deepest levels have no ERA5 counterpart and are not written.
- **Convective inhibition is not defined everywhere.** By construction it is only computed where
  CAPE exceeds 100 J/kg, and CAPE itself is undefined at the few percent of points with no
  equilibrium level. We write **zero** at those points rather than a missing value, so that the
  fields stay dense; zero is also the physically correct reading (no inhibition, no available
  energy). If you would rather have them flagged as missing, say so now.
- **CAPE and CIN are most-unstable**, computed from the 500 m deep parcel with the highest
  equivalent potential temperature in the lowest 3 km — not surface-based.
- **The gust field is not a gust parameterisation.** It is the maximum of the *resolved* 10 m wind
  speed over the output hour. It behaves like a gust and is the best proxy available, but it is not
  produced by a gust scheme.
- **Rainfall excludes snow and graupel, not hail.** The microphysics has no hail category, so rain
  is total precipitation minus snow minus graupel.
- **2 m dewpoint is now in kelvin.** The previous GRIB1 archive wrote it in degrees Celsius under
  a parameter that ECMWF defines in kelvin. If you read `2d` from the old files, it needs +273.15.
- **Accumulated fields are referred to 00 UTC of the same day**, not to the start of the model run.
  They are exactly zero at 00 UTC. In the GRIB files they carry a 0-to-H accumulation step with a
  00 UTC reference time, so the validity time is the timestep itself. The 10 m wind maximum is the
  exception: it covers the preceding hour only, because the model resets it at every output.
- **Geolocation is now exact to ~2 m.** The grid declares the spherical earth of radius 6370 km
  that WRF actually integrates on. The previous GRIB1 files could not express this and were off by
  up to ~1.1 km at the northern edge of the domain.

---

## 6. What we need from you

1. **The land-surface list.** The original proposal was lost. We are currently delivering the
   subset that exists in the output, under ERA5 names: soil moisture and soil temperature (4
   layers), snow depth and density, snowfall, snowmelt, surface and sub-surface runoff, skin
   reservoir content, vegetation cover and leaf area index, vegetation and soil type, friction
   velocity and surface roughness. Please confirm or amend.
2. **Should we request the static `geo_em` file from LRZ?** It is the clean way to get fractional
   land cover, and it is cheap. Without it, land cover is a dominant-category field only.
3. **Are the gust components needed as components**, given that only a magnitude proxy exists? If
   the decomposition in §3 is acceptable we can produce them; otherwise we deliver the magnitude
   only.
4. **Is TKE a requirement or a preference?** If it is a requirement, it changes the nature of the
   project: it means re-running the simulation, not re-processing its output.
5. **Wind shear: which definition?** We currently assume the bulk 10 m to 100 m shear. Any other
   definition (fixed layers, per pressure level, 0-6 km bulk) is a one-line change, but it has to
   be decided before the archive is re-converted.
