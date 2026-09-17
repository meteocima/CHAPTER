# CHAPTER 3 km — requested variables that are not directly available

**Date:** 2026-09-17 · **Scope:** the variable list requested for the CHAPTER regional reanalysis
(atmosphere, static, land-surface, ocean waves, sea ice, surface ocean).

This note answers one question: of the variables you asked for, which ones can we actually put in
the GRIB archive, which ones we can obtain by some other route, and which ones are simply not in
the data. It is meant to be read before we commit to a re-conversion of the whole archive, because
that re-conversion costs several days of data transfer and has to be done only once.

Everything below was verified against the actual files, not against documentation: model
configuration read from the wrfout global attributes, and every field checked for real values on
independent timesteps in summer 2019, summer 2024 (00/06/12/13/14/18/23 UTC) and March 2024, so
that fields which exist in the file but are identically zero are not mistaken for usable data.
Accumulated fields were additionally checked for monotonicity within a run, and every ECMWF
parameter identifier was round-tripped through the GRIB encoder to confirm name and units.

---

## 1. Summary

| requested block | verdict |
|---|---|
| Atmosphere, surface (24 variables + wind shear) | **22 of 24 delivered**, plus wind shear. Only the two gust components are missing, and they are excluded by decision (see §4) |
| Atmosphere, pressure levels (9 variables × 13 levels) | **all delivered**, plus both vertical-velocity forms (`w` in Pa/s and `wz` in m/s) and three extra ERA5 fields: cloud fraction `cc`, rain `crwc` and snow `cswc` water content |
| TKE at 3 height levels | **not available** — the model does not compute it |
| Static: orography | **delivered** |
| Static: land-use / land-cover | **dominant category only, never fractions** — the file that holds the fractions no longer exists (see §4) |
| Land-surface | **delivered** as the subset that exists, with ERA5 names — now including the complete radiation budget, runoff, snow cover, snow temperature, albedo, surface stress and the high/low vegetation split |
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
| `ICLOUD` | 1 (Xu-Randall) | cloud fraction is **continuous**, not a 0/1 flag — see §5 |
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
implemented: each needs a decision first. Two items that appeared here in the previous version
have moved: **surface albedo is now delivered** (`al`, the snow-free background, and `fal`, the
actual all-sky ratio), and **fractional land cover has moved to §4**, because the static file it
would have come from turned out to be irrecoverable.

| variable | route | confidence | cost |
|---|---|---|---|
| Sea-ice surface temperature | Use the skin temperature we already derive, restricted to points where sea-ice concentration > 0 | **Medium.** It is a radiative skin temperature, consistent with the model's own longwave emission, but not a dedicated ice-surface temperature | Free |
| Drag coefficient **without** wave effect | From the model's own roughness length: `Cd = (κ / ln(10/z0))²` | **Exact** — this is precisely the drag the simulation used (Charnock, no wave coupling) | Free |
| Planetary boundary layer height | Bulk Richardson number on the virtual potential temperature profile; all required fields are present | **Reasonable** — the same class of diagnostic the model itself would apply | Free |

---

## 4. Variables we cannot provide

| variable | why | the only way to get it |
|---|---|---|
| **Fractional land cover** (forest, crops, urban as fractions), `GREENFRAC`, soil texture fractions | They live in the WRF static file `geo_em_d02`, which is not part of the hourly output. That file was written to a scratch directory that has since been deleted, and it is no longer available from LRZ either — it was asked for | Re-running the WPS pre-processor (`geogrid`) with the original namelist and the ~50 GB public terrestrial dataset. The domain itself is exactly reconstructable from the wrfout attributes, so this is feasible but it is a separate exercise. What we deliver instead is the **dominant** category per grid point: 19.5 % of the land is forest, 38.2 % cropland, 1.5 % urban |
| **`10efg`, `10nfg`** (eastward / northward gust components) | Only a gust *magnitude* proxy exists (see §5), and it is the maximum of the resolved wind, not a gust scheme. Their direction would have to be assumed equal to the mean wind, at an instant that does not even coincide with the maximum | Decomposing the magnitude along the 10 m wind is possible and cheap, but it was judged too weak to publish under ERA5 names, so **it was decided not to produce them** |
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

- **Cloud cover is fractional.** An earlier draft of this note said the model's cloud fraction was
  binary; that was wrong, and the correction is in our favour. The scheme is Xu-Randall and the
  field is genuinely continuous: over a 500 × 600 sub-domain only 18-22 % of cloudy points sit
  exactly at 1, the rest spread across the whole 0-1 range. Total, high, medium and low cloud cover
  are maximum-random overlaps of that field, and the cloud fraction is also delivered per pressure
  level as `cc`.
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
- **The land/sea mask changes with the season.** Where sea ice forms, the model reclassifies the
  point as ice: the land mask, the vegetation and soil types and the background albedo all change
  there (2469 points on 20 March 2024, exactly the sea-ice points). These fields are therefore
  written in every hourly file and must not be treated as a single static field for the archive.
- **Surface stress is a diagnostic, not a model output.** The eastward and northward stresses are
  reconstructed as density × friction velocity squared, aligned with the 10 m wind. The friction
  velocity is the model's own, so this is the same similarity theory the simulation used, but the
  alignment with the mean wind is an assumption.
- **Snow temperature only exists where there is snow.** The field is the temperature at the top of
  the snow/soil column; away from snow it is simply a soil temperature, so it is written as missing
  there rather than published as a snow temperature that does not exist.
- **Albedo comes in two forms.** `al` is the snow-free climatological background the model was
  initialised with; `fal` is the actual ratio of upward to downward shortwave, which is what the
  simulation really used — but it is undefined at night and is written as missing below
  50 W/m² of incoming shortwave.
- **Total runoff is almost entirely surface runoff.** The sub-surface component is active on only
  0.06 % of the points in July and 0.5 % in March, so `ro` and `sro` differ over a very small
  fraction of the domain. Both are published because `ro` is the ERA5-canonical total.
- **There is no graupel field**, although the microphysics produces graupel and it is not
  negligible at 3 km (column integrals up to 27 kg/m²): ERA5 simply has no parameter for it. The
  graupel is included in total column water, but cannot be published separately under an ERA5 name.
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

The questions about the gust components and about TKE that appeared here previously have been
settled: neither is produced. The one about requesting the static `geo_em` file is also closed —
the file is gone (§4).

1. **The land-surface list.** The original proposal was lost. We deliver the subset that exists in
   the output, under ERA5 names: soil moisture and soil temperature (4 layers), snow depth,
   density, cover and temperature, snowfall, surface, sub-surface and total runoff, skin reservoir
   content, high and low vegetation cover, leaf area index and type, soil type, friction velocity,
   surface roughness, the two surface albedos, the two components of surface stress, and the
   complete radiation budget (downward, net and clear-sky, at the surface and at the top of the
   atmosphere). **Snowmelt is not among them**: the field exists but is not a monotone accumulator,
   see §4. Please confirm or amend.
2. **Wind shear: which definition?** We currently deliver the bulk 10 m to 100 m shear. Any other
   definition (fixed layers, per pressure level, 0-6 km bulk) is a one-line change, but it has to
   be decided before the archive is re-converted.
3. **Vertical levels.** We deliver 13 pressure levels. ERA5 uses 37, of which 29 would be within
   this model's domain (the model top is at 50 hPa, so nothing above it can be produced). Going to
   29 levels would take the hourly file from ~0.8 GB to ~1.45 GB and a year of archive from 7.0 to
   18.1 TB; on those grounds we kept 13. Say so now if the denser set matters for your use.
