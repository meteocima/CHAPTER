# The inventory sweep: everything ERA5 publishes that we do not

What could be added to the archive, and what could not. **Nothing here is being
added** — the variable set was fixed at ninety by decision on 2026-09-22 — but
the decision is worth more taken knowing what was on the table than taken by not
looking, and this is the table.

Regenerate the lists with `tools/audit/inventory_sweep.py`; the judgements below
are hand-made and each is a claim that can be checked.

Three sources, all local, nothing downloaded: the CDS catalogue forms, eccodes'
own `grib2/{paramId,shortName,name}.def`, and **ECMWF local table 162**
(`grib1/2.98.162.table`), which is where the whole vertical-integral family lives
and which the grib2 tables do not carry — they hold six of its forty.

## The arithmetic

| | |
|---|---|
| ERA5 single-level parameters offered by CDS | 262 |
| of which we map, or retrieve as a control | 79 |
| **residue** | **183** |
| less ocean waves — `SF_OCEAN_PHYSICS = 0`, no wave model, impossible | −43 |
| less "mean rate" forms — by construction an accumulation we publish, divided by 3600 | −39 |
| **left to judge** | **101** |

## What is obtainable, and was not taken

Each of these satisfies the published rule — the WRF quantity **is** the ERA5
one — and needs no assumption. This is the answer to the ticket's question, and
it is yes.

### Diagnostics from fields we already publish

These need nothing but the archive itself; they are computable from messages
already in every GRIB file.

| paramId | short | what it is | from |
|---|---|---|---|
| 260121 | `kx` | K index | T and Td at 850/700/500 hPa — levels we publish |
| 260123 | `totalx` | Total totals index | the same three levels |
| 228024 | `deg0l` | zero degree level | the 0 °C isotherm height from `t` and `z` |
| 228131 | `u10n` | 10 m neutral u | `u*/κ · ln(10/z0)`, and both `zust` and `fsr` are published |
| 228132 | `v10n` | 10 m neutral v | the same |

### Column quantities from the model levels

| paramId | short | what it is |
|---|---|---|
| 228088 | `tcslw` | total column supercooled liquid water — `QCLOUD` where T < 0 °C |
| 162053 | `vima` | vertical integral of mass of atmosphere |
| 162054 | `vit` | vertical integral of temperature |
| 162059 | `vike` | vertical integral of kinetic energy |
| 162060 | `vithe` | vertical integral of thermal energy |
| 162061 | `vipie` | potential + internal energy |
| 162062 | `vipile` | potential + internal + latent energy |
| 162063 | `vitoe` | total energy |
| 162064 | `viec` | energy conversion |

### Column transports — the large class

ERA5 publishes the eastward and northward column fluxes of mass, kinetic energy,
heat, water vapour, geopotential, total energy and the two cloud species. All are
`∫ u·X dp/g` over the column, all computable from `U`, `V`, `T`, `QVAPOR`,
`QCLOUD`, `QICE` and the pressure on the 49 model levels, and **we publish none
of them**.

| paramId | short | | paramId | short | |
|---|---|---|---|---|---|
| 162065 | `vimae` | eastward mass flux | 162066 | `viman` | northward mass flux |
| 162067 | `vikee` | eastward kinetic energy | 162068 | `viken` | northward kinetic energy |
| 162069 | `vithee` | eastward heat | 162070 | `vithen` | northward heat |
| 162071 | `viwve` | eastward water vapour | 162072 | `viwvn` | northward water vapour |
| 162073 | `vige` | eastward geopotential | 162074 | `vign` | northward geopotential |
| 162075 | `vitoee` | eastward total energy | 162076 | `vitoen` | northward total energy |
| 162088 | `vilwe` | eastward cloud liquid water | 162089 | `vilwn` | northward cloud liquid water |
| 162090 | `viiwe` | eastward cloud frozen water | 162091 | `viiwn` | northward cloud frozen water |

### The divergences — obtainable, with one caveat

`162079` `vilwd`, `162080` `viiwd`, `162081` `vimad`, `162082` `viked`,
`162083` `vithed`, `162084` `viwvd`, `162085` `vigd`, `162086` `vitoed`, plus
`213` `vimd` (vertically integrated moisture divergence) and `162092` `vimat`
(mass tendency).

All are computable, but they are horizontal derivatives on a Mercator grid, so
they need the **map factors** — which the wrfout carries (`MAPFAC_M`, `MAPFAC_U`,
`MAPFAC_V`) and which nothing in the converter currently uses. `vimat` needs a
time derivative, so it needs two consecutive timesteps rather than one.

## Three ERA5 parameters we already publish under a different number

Worth its own heading because it is not a gap, it is a naming fact that could be
mistaken for one:

| ERA5 also calls it | and we publish | |
|---|---|---|
| `162055` `viwv` — vertical integral of water vapour | `137` `tcwv` — total column water vapour | the same quantity |
| `162056` `vilw` — vertical integral of cloud liquid water | `78` `tclw` | the same quantity |
| `162057` `viiw` — vertical integral of cloud frozen water | `79` `tciw` | the same quantity |

So of table 162's forty entries, three are already in the archive under their
other paramId and three are ozone.

## What is genuinely impossible

| | why |
|---|---|
| ocean waves (43 parameters), Stokes drift, Charnock, Benjamin-Feir | `SF_OCEAN_PHYSICS = 0`, no wave or ocean model |
| `162058` `vioz`, `162077` `vioze`, `162078` `viozn`, `206` `tco3` | no prognostic ozone in this configuration |
| `147` `slhf`, `146` `sshf`, `231` `ishf`, `232` `ie`, `182` `e`, `228251` `pev` | `HFX`, `LH` and `QFX` were removed from the run's Registry and never written — see issue #31 |
| `159` `blh` | `PBLH` likewise never written; a bulk-Richardson diagnosis from the profile would be **our** diagnosis, not the model's, so it fails the publication rule |
| `145` `bld` | the PBL scheme's own dissipation diagnostic, not written |
| lake fields (7), `35`–`38` ice temperature layers | `sf_lake_physics = 0`, no sea-ice model |
| `201` `mx2t`, `202` `mn2t` | impossible and unrecorded, settled by the configuration ticket |
| `228226` `mxtpr`, `228227` `mntpr` | need a sub-hourly maximum; the output is hourly |
| `15`–`18` spectral albedos, `57` `uvb`, `228021` `cdir`, `228022` `fdir` | RRTMG writes a broadband albedo and no direct/diffuse or spectral split |
| gravity-wave stress and dissipation | no gravity-wave drag scheme in this configuration |

## Judged obtainable but refused on the publication rule

- **`228023` `cbh`, cloud base height** — the lowest level where `CLDFRA`
  exceeds a threshold, and the threshold is a choice. An assumption, so it fails
  the rule.
- **`260015` `ptype`, precipitation type** — a categorical diagnosis from the
  hydrometeor species with thresholds. Same objection.
- **`180` `ewss`, `181` `nsss`** — the accumulated forms of `iews`/`inss`, which
  we publish instantaneously. Accumulating our instantaneous field is not the
  model's accumulation.
- **`74` `sdfor`** — standard deviation of *filtered* subgrid orography, which is
  not `sdor`. geo_em carries `VAR` alongside `VAR_SSO`; whether either is
  `sdfor`'s quantity is left open, and the related question of whether `VAR_SSO`
  is the right source for the `sdor` we *do* publish goes to family 7.

## geo_em: 57 variables, 8 read

`static_ref.py` reads `LANDUSEF`, `SOILCTOP`, `CLAYFRAC`, `SANDFRAC`,
`LAKE_DEPTH`, `LU_INDEX`, `XLAT_M`, `XLONG_M`. Of the rest:

- **bearing on variables we already publish**, and therefore *in* scope — moved
  to family 7: `VAR_SSO` and `VAR` (is `sdor`'s source right?), `ALBEDO12M` and
  `SNOALB` (is `al`'s source right, given `usemonalb = .false.`?), `HGT_M` and
  `LANDMASK` (independent copies of `z_sfc` and `lsm`).
- **expansion candidates**, out with the rest: `LAI12M` (observed monthly MODIS
  LAI, which bears on the `lai_lv`/`lai_hv` refusal), `GREENFRAC`, `SOILTEMP`
  (the same quantity as the wrfout's `TMN`), `SOILCBOT`, `SCT_DOM`/`SCB_DOM`,
  `EROD`, `URB_PARAM` (132 layers, unused since `sf_urban_physics = 0`), the
  `OA1-4`/`OL1-4` orography descriptors.
- **grid metadata**, never candidates: map factors, `COSALPHA`/`SINALPHA` and
  their staggered twins, `XLAT_*`/`XLONG_*`, `CLAT`/`CLONG`, `E`, `F`.

## The wrfout: 200 variables, and almost nothing in the residue

Subtract the 90 published, the inputs to derived fields, the exclusions family
ticket #17 covers and the 37 the census found dead, and what remains is model
infrastructure: map factors, eta levels, base state, grid coordinates. The only
substantive names are `VAR` (above) and a set of **redundancies worth recording
so nobody rediscovers them as gaps**:

| wrfout | is the instantaneous or per-interval form of | which we publish as |
|---|---|---|
| `OLR` | top-of-atmosphere outgoing longwave | `ttr` (accumulated) |
| `SWDNT`, `SWDNTC` | downward shortwave at the top | `tisr` |
| `SWDOWNC`, `SWDNBC` | clear-sky downward shortwave at the surface | `ssrdc` |
| `PREC_ACC_NC` | grid-scale precipitation over the output interval | `tp` |
| `SNOW_ACC_NC` | snow water equivalent over the output interval | `sf` |

`PREC_ACC_NC` is not only a redundancy: the configuration ticket already noted it
gives a `tp` cross-check needing neither the accumulation sidecar nor ERA5.

## The decision

**Nothing above is added.** The archive stays at 90 variables and 246 messages.

The sweep's value is that the refusal is now informed: there are roughly thirty
ERA5 parameters this run could legitimately produce, they are named here with
their paramIds, and if the destination is ever redrawn this file is where that
effort starts rather than starting again from the catalogue.
