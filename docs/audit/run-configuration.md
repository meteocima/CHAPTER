# The run's configuration, read out of its own files

Resolves issue #12. Everything below is **d02** — the second column of every `(max_dom)`
array. d01 is out of scope and differs in one physics option (`cu_physics`).

Until these files were recovered, every claim in `CLAUDE.md` about "which scheme is on" was
an inference from a field being zero. This note replaces the inferences with the lines that
settle them, and marks honestly the places where the configuration does **not** settle the
question.

## Sources

| file | what it is |
|---|---|
| `$WORK/CHAPTER/geo_em/namelist.input` | the run's namelist as written by the operator. Byte-identical to the two copies under `geo_em/2022123118/` and `geo_em/2022123118/WPS/` |
| `$WORK/CHAPTER/geo_em/2022123118/WPS/namelist.output` | **WRF's own dump of every namelist variable and its effective value.** This is the authority for options absent from `namelist.input`: it records the default WRF actually used, not the default we believe it has |
| `$WORK/CHAPTER/geo_em/2022123118/WPS/namelist.wps` | the geogrid configuration |
| `$WORK/CHAPTER/WPS/*.TBL` | the parameter tables shipped with the run |
| `$WORK/CHAPTER/WPS/README.namelist` | **WRF's own documentation of each option, shipped with this run.** Quoted throughout — it is a primary source for what an option means, at this version |
| a wrfout header (`wrfout_d02_2024-07-01_14:00:00`) | which variables the delivered files actually carry |

Version, from the wrfout global attributes:

```
TITLE = ' OUTPUT FROM WRF V4.1.1 MODEL'
```

and WPS 4.1, from `opt_geogrid_tbl_path = '.../WPS-4.1//geogrid/'` in `namelist.wps`.

The namelist is one run's (initialised `2022-12-31_18:00:00`), and the archive spans many
runs. It is treated here as representative because the hourly output is structurally
identical across the years already converted; a per-year check is not part of this ticket.

---

## 1. The scheme list

Every item `CLAUDE.md` states is **confirmed**. Two were not in `namelist.input` at all and
are confirmed from `namelist.output` instead — a distinction worth keeping, because it means
they were never chosen, only inherited.

### `cu_physics = 0` on d02 — CONFIRMED

`namelist.input`, `&physics`:

```
cu_physics               = 6,     0,     0,
```

`namelist.output`:

```
 CU_PHYSICS      =           6, 2*0, 8*-1,
 SHCU_PHYSICS    = 11*0,
```

d01 runs Tiedtke (6); **d02 runs no cumulus scheme at all**, and no shallow-cumulus scheme
either. Renders meaningless: `RAINC`, `RAINSH`, `PREC_ACC_C` (all identically zero, verified
on the 2024-07-01 14Z file), and with them ERA5's `cp` and `csf`, which cannot be produced.
`CU_DIAG = 11*0`, so no cumulus diagnostic tendencies either.

### `sf_ocean_physics = 0` — CONFIRMED, but **inherited, not chosen**

The option **does not appear in `namelist.input`**. `namelist.output`:

```
 SF_OCEAN_PHYSICS        =           0,
```

`README.namelist`: `sf_ocean_physics = 0 ! activate ocean model (0=no, 1=1d mixed layer;
2=3D PWP, no bathymetry)`. Renders meaningless: the whole ocean-mixed-layer set (`TML`,
`HML`, `T0ML`, `H0ML`, `HUML`, `HVML`), none of which is in the wrfout. No ocean coupling,
hence no waves, currents, SSH or ice thickness.

### `sst_update = 0` — CONFIRMED

`namelist.input`, `&physics`:

```
sst_update               =  0,
```

`namelist.output` adds two neighbours that matter:

```
 SST_UPDATE      =           0,
 SST_SKIN        =           0,
 TMN_UPDATE      =           0,
```

Renders meaningless: `SST` is frozen for the whole 30 h run, so all 24 output hours of a day
share one SST field. `SSTSK` is identically zero **because `sst_skin = 0`** — measured
min = max = 0 on the sample file. `TMN` is frozen likewise.

Worth recording: the namelist *configures* a lower-boundary update stream and then leaves it
switched off —

```
auxinput4_inname         = "wrflowinp_d<domain>",
auxinput4_interval       = 60,      60,   180,
```

With `sst_update = 0` that stream is never read. The intent was there; the switch was not
thrown.

### `bl_pbl_physics = 1` (YSU) with `km_opt = 4` — CONFIRMED, but the consequence `CLAUDE.md` draws is half wrong

```
bl_pbl_physics           = 1,     1,     1,
```

```
km_opt                   = 4,
diff_opt                 = 1,
khdif                    = 0,        0,        0,
kvdif                    = 0,        0,        0,
```

`README.namelist` on `km_opt`:

```
 km_opt(max_dom)                     = 1,	! eddy coefficient option
                                                  1 = constant (use khdif kvdif)
                                                  2 = 1.5 order TKE closure (3D)
                                                  3 = Smagorinsky first order closure (3D)
                                                  4 = horizontal Smagorinsky first order closure
                                                      (recommended for real-data cases)
```

Only option 2 carries a prognostic TKE. **So `CLAUDE.md` is right that there is no TKE**: the
run carries none, by configuration, and no amount of post-processing will produce one.

**`CLAUDE.md` is wrong about `PBLH`.** It gives the same reason for both ("no TKE and no
PBLH (`BL_PBL_PHYSICS=1`, YSU is non-local, `KM_OPT=4`)"). YSU is precisely a scheme that
diagnoses a PBL height — it is central to how it distributes the non-local flux — and WRF
writes `PBLH` to the history stream. `PBLH` is indeed absent from the delivered wrfout, but
not because it was not computed. See §6.24: the namelist does not restrict the output
stream, so the absence of `PBLH` is **not settled by the configuration**.

### `sf_lake_physics = 0` — CONFIRMED, and **inherited, not chosen**

The option **does not appear in `namelist.input`**. `namelist.output`:

```
 SF_LAKE_PHYSICS = 11*0,
```

Renders meaningless: the lake-model state (`T_LAKE3D` and the rest), absent from the wrfout.
Confirms the `cl` reasoning in `CLAUDE.md`: geogrid *did* resolve lakes —

`namelist.wps`, `&geogrid`:

```
 geog_data_res = 'modis_lakes+30s','modis_lakes+30s','modis_lakes+30s',
```

and the wrfout attributes carry `ISLAKE = 21` with `NUM_LAND_CAT = 21` — but with the lake
model off, category 21 is handled as ordinary water and `LU_INDEX` 21 becomes `IVGTYP` 17.
The sub-grid lake information survives only in `geo_em`, which is exactly why `static_ref.py`
reads it there.

### `icloud = 1` — CONFIRMED, and it settles the `CLDFRA` question outright

```
icloud                   = 1,
```

`README.namelist`:

```
 icloud                              = 1,	! cloud effect to the optical depth in radiation
                                                  (only works for ra_sw_physics = 1,4 and ra_lw_physics = 1,4)
                                                  Since 3.6, this also controls the cloud fraction options
                                                  1 = with cloud effect, and use cloud fraction option 1
                                                      (Xu-Randall method) 
                                                  0 = without cloud effect
                                                  2 = with cloud effect, and use cloud fraction option 2 (0/1 based
```

Option **2** is the binary one; this run uses **1**, Xu–Randall. The correction `CLAUDE.md`
already made on measured evidence — `CLDFRA` is fractional, not binary — is now confirmed
from the configuration. `ra_lw_physics = 4` and `ra_sw_physics = 4` (RRTMG) are in the list
of schemes `icloud` works for.

### `sf_surface_physics = 3` (RUC) — CONFIRMED

```
sf_surface_physics       = 3, 3, 3,
num_soil_layers          = 6,
```

The wrfout's `ZS` confirms the layer geometry exactly as `CLAUDE.md` states it:

```
ZS  = [0.   0.05 0.2  0.4  1.6  3.  ]   (m)
DZS = [0.025 0.125 0.175 0.7 1.3 0.7]   (m)
```

i.e. nodes at 0 / 5 / 20 / 40 / 160 / 300 cm. The `swvl1-4` / `stl1-4` derivation rests on
this and it holds.

Renders meaningless: **every Noah-only output**. Verified identically zero on the sample
file: `ACHFX`, `ACLHF`, `ACGRDFLX`, `NOAHRES`, `RESM`. `CLAUDE.md` lists the first four as
"dead" without a reason; the reason is that they are Noah's accumulators and this run is RUC.

This is not a bucket artefact — `bucket_J = -1` (§6.a) disables energy-bucket accumulation
for *all* accumulators, yet `ACSWDNB` (7.9e5 … 3.2e7 J m⁻²) and `ACLWDNB` are alive on the
same file. The energy accumulators that work, work; the Noah ones were never filled.

Also not read by this run, therefore irrelevant to anything we derive: the `STAS` block of
`SOILPARM.TBL`, the `MODIFIED_IGBP_MODIS_NOAH` block of `VEGPARM.TBL` (see §5 — this one
caused a real error), `MPTABLE.TBL` (Noah-MP, `sf_surface_physics` is 3 not 4) and
`URBPARM.TBL` (`sf_urban_physics = 0`).

---

## 2. Which `SOILPARM.TBL` was in force

**Short answer: the default — and it makes no difference, because the two files differ only
in a block this run does not read.**

There is **no namelist option that selects a soil table**; `README.namelist` has none and
neither namelist mentions one. WRF opens the file literally named `SOILPARM.TBL`, so the
file carrying the `_Kishne_2017` suffix is never opened. That much is settled by the
filename convention alone, not by the configuration — state it that way.

What *is* settled, from the files themselves, is that the question does not matter.
`SOILPARM.TBL` has two blocks:

```
1:Soil Parameters
2:STAS
23:Soil Parameters
24:STAS-RUC
```

`STAS` is Noah's; `STAS-RUC` is RUC's. `diff` between the two files returns changes only at
lines 3–16 and 18–22 — every one of them inside the `STAS` block (lines 1–22). The
`STAS-RUC` block is byte-identical:

```
$ sed -n '23,$p' SOILPARM.TBL              | md5sum
ce663a34d0d82983d3124ca6ba6b853d  -
$ sed -n '23,$p' SOILPARM.TBL_Kishne_2017  | md5sum
ce663a34d0d82983d3124ca6ba6b853d  -
```

So with `sf_surface_physics = 3`, the Kishné (2017) revision — which retunes `DRYSMC`,
`REFSMC`, `WLTSMC`, `MAXSMC`, `BB`, `SATDK`, `SATDW` for the 19 Noah categories — was
inert either way. **Neither `slt` nor the soil columns are affected.** `slt` is in any case
derived in `static_ref.py` from geo_em's `CLAYFRAC`/`SANDFRAC` against the FAO thresholds,
never from this table.

One caveat, stated rather than glossed: *that* RUC reads the `STAS-RUC` block rather than
`STAS` is not asserted by any file on disk — the WRF source is not here (§5). The block is
named for the scheme and the scheme is RUC, and the conclusion is robust regardless, since
both candidate files agree there.

Related, from `namelist.output`:

```
 NUM_SOIL_CAT    =          16,
```

16 soil categories (STATSGO) against the table's 19 rows, and `ISOILWATER = 14` in the wrfout
attributes.

---

## 3. `lightning_option = 3` and `do_radar_ref = 1`

Both **confirmed**, with one correction to how the ticket frames them.

`namelist.input`, `&physics`:

```
lightning_option         = 3,   3,   3,
lightning_dt             = 0,       0,       0, 
lightning_start_seconds  = 600,     600,    600,
flashrate_factor         = 1,        1,        1,
cellcount_method         = 2,        2,        2,
iccg_method              = 0,        0,        0,
cldtop_adjustment        = 0,        0,        0,
do_radar_ref             = 1,
```

`namelist.output` agrees (`LIGHTNING_OPTION = 3*3, 8*0`, `DO_RADAR_REF = 1`).

**The correction.** `README.namelist`:

```
 lightning_option (max_dom)                       Lightning parameterization option to allow flash rate prediction without chemistry
                                     = 3        ! Predicting the potential for lightning activity (based on Yair et al, 2010, ...)
```

and, for the two knobs the ticket names:

```
 flashrate_factor  (max_dom)         = 1.0      ! Factor to adjust the predicted number of flashes. ...
 cellcount_method (max_dom)                       Method for counting storm cells. Used by CRM options (lightning_options=1,2).
 cldtop_adjustment (max_dom)         = 0.       ! Adjustment from LNB in km. Used by lightning_option=11.
```

Option 3 is **not** a flash-rate scheme — it is the Lightning Potential Index of Yair et al.
(2010), and it predicts a potential, not a flash count. `flashrate_factor`,
`cellcount_method`, `cldtop_adjustment` and `iccg_method` are all set but belong to options
1, 2 and 11; with option 3 they are inert. The wrfout agrees: `LPI` is present,
`IC_FLASHCOUNT` and `CG_FLASHCOUNT` are absent.

So for the exclusions ticket: `LPI` is a live diagnostic of an enabled scheme, and there is
no flash-rate field to consider alongside it.

`do_radar_ref = 1`, `README.namelist`:

```
 do_radar_ref			     = 0, 	! 1 = allows radar reflectivity to be computed using mp-scheme-specific
 						  parameters.  Currently works for mp_physics = 2,4,6,7,8,10,14,16,28
```

`mp_physics = 6` is in that list, so `REFL_10CM` is a genuine WSM6-consistent reflectivity
(present in the wrfout on all 49 mass levels), and `REFD_MAX` is its per-hour maximum
(§6.e).

---

## 4. `prec_acc_dt = 60` and `PREC_ACC_NC`

**Confirmed, present, and verified to be exactly the hourly accumulation.**

`namelist.input`, `&physics`:

```
prec_acc_dt              = 60,60,60,
```

`namelist.output`:

```
 PREC_ACC_DT     = 3*60.00000       , 8*0.0000000E+00  ,
```

`README.namelist`:

```
 prec_acc_dt (max_dom)               = 0.,      ! number of minutes in precipitation bucket (ARW only) - will add three
                                                  new 2d output fields: prec_acc_c, prec_acc_nc and snow_acc_nc
```

All three are in the wrfout:

```
PREC_ACC_NC: dims=('Time','south_north','west_east') units='mm' desc='ACCUMULATED GRID SCALE  PRECIPITATION OVER prec_acc_dt PERIODS OF TIME'
PREC_ACC_C : dims=('Time','south_north','west_east') units='mm' desc='ACCUMULATED CUMULUS PRECIPITATION OVER prec_acc_dt PERIODS OF TIME'
SNOW_ACC_NC: present
```

Measured on the 2024-07-01 13Z and 14Z files, whole domain:

```
RAINNC 13->14 delta: min 0.000000 max 68.315801 sum 320023.927
PREC_ACC_NC @14    : min 0.000000 max 68.315811 sum 320024.141
max|PREC_ACC_NC - (RAINNC(14)-RAINNC(13))| = 1.08e-04 mm
```

The residual is float32 round-off on a ~1e5 mm sum. **`PREC_ACC_NC` is the exact 1-hour
grid-scale precipitation increment**, self-contained in each file and needing no 00Z
reference. `PREC_ACC_C` is identically zero, as `cu_physics = 0` requires.

For the water-cycle ticket: this gives `tp` an independent check that does not go through
the sidecar at all — the day's `tp(H)` should equal the running sum of `PREC_ACC_NC` over
hours 01Z…H. A disagreement would localise to a single hour rather than to the whole day.

Also settled, and confirming `CLAUDE.md`:

```
 BUCKET_MM       =  -1.000000    ,
 BUCKET_J        =  -1.000000    ,
```

`README.namelist`: `bucket_mm = -1. ! bucket reset value for water accumulations (value in
mm, -1.=inactive)`. The buckets are **off**, so `RAINNC` and the radiation accumulators never
reset within a run, and `I_RAINNC` is correctly absent from the wrfout. `CLAUDE.md`'s "no
bucket reset (no I_RAINNC)" is confirmed from the configuration.

---

## 5. The emissivity question — `CLAUDE.md` is wrong, and the table is fully reproducible

**The measured emissivities are not RUC's hard-coded values. All twenty-one of them are read
straight out of `VEGPARM.TBL`, from the `MODI-RUC` section, column `LEMI`.**

The earlier `skt` work read the `MODIFIED_IGBP_MODIS_NOAH` section of `VEGPARM.TBL` and
compared against its `EMISSMIN` column. That is Noah's section. `VEGPARM.TBL` also contains
a section written for the RUC LSM with MODIS land use:

```
205:MODI-RUC
```

whose header is a different set of columns, with emissivity under `LEMI`:

```
MODI-RUC
21,1, 'ALBEDO    Z0    LEMI    PC   SHDFAC IFOR   RS      RGL      HS      SNUP    LAI    MAXALB'
1       .12,    .70,   .950,  .55,    .70,   1,    125.,    30.,   47.35,   0.08,   6.40,   52.,     'Evergreen Needleleaf Forest'
2,      .12,    .70,   .950,  .55,    .95,   2,    150.,    30.,   41.69,   0.08,   6.48,   35.,     'Evergreen Broadleaf Forest'
3,      .14,    .70,   .940,  .55,    .70,   4,    150.,    30.,   47.35,   0.08,   5.16,   54.,     'Deciduous Needleleaf Forest'
4,      .16,    .70,   .930,  .55,    .80,   3,    100.,    30.,   54.53,   0.08,   3.31,   58.,     'Deciduous Broadleaf Forest'
5,      .13,    .70,   .940,  .55,    .80,   2,    125.,    30.,   51.93,   0.08,   5.50,   53.,     'Mixed Forests'
6,      .22,    .10,   .930,  .40,    .70,   4,    300.,   100.,   42.00,   0.03,   3.66,   60.,     'Closed Shrublands'
7,      .20,    .10,   .880,  .40,    .70,   4,    170.,   100.,   39.18,  0.035,   2.60,   65.,     'Open Shrublands'
8,      .20,    .15,   .930,  .40,    .70,   5,    300.,   100.,   42.00,   0.03,   3.66,   60.,     'Woody Savannas'
9,      .20,    .15,   .920,  .40,    .50,   5,     70.,    65.,   54.53,   0.04,   3.66,   50.,     'Savannas'
10,     .19,   .075,   .920,  .40,    .80,   5,     40.,   100.,   36.35,   0.04,   2.90,   70.,     'Grasslands'
11      .14,    .30,   .950,  .40,    .60,   4,     70.,    65.,   55.97   0.015    5.72,   59.,     'Permanent wetlands'
12,     .18,    .20,   .935,  .40,    .80,   7,     40.,   100.,   36.25,   0.04,   5.68,   66.,     'Croplands'
13,     .18,    1.0,   .880,  .40,    .10,   9,    200.,   999.,   999.0,   0.04,   1.00,   46.,     'Urban and Built-Up'
14      .16,    .20,   .920,  .40,    .80,   7,     40.,   100.,   36.25,   0.04,   4.29,   68.,     'cropland/natural vegetation mosaic'
15,     .55,   .011,   .980,  .00,    .00,   9,    999.,   999.,   999.0,   0.02,   0.01,   82.,     'Snow and Ice'
16,     .25,   .065,   .850,  .30,    .01,   5,    999.,   999.,   999.0,   0.02,   0.75,   75.,     'Barren or Sparsely Vegetated'
17,     .08,  .0001,   .980,  .00,    .00,   9,    100.,    30.,   51.75,   0.01,   0.01,   70.,     'Water'
18,     .15,    .15,   .930,  .40,    .60,   5,    150.,   100.,   42.00,  0.025,   3.35,   55.,     'Wooded Tundra'
19,     .15,    .10,   .920,  .40,    .60,   5,    150.,   100.,   42.00,  0.025,   3.35,   60.,     'Mixed Tundra'
20,     .15,    .06,   .900,  .30,    .30,   5,    200.,   100.,   42.00,   0.02,   3.35,   75.,     'Barren Tundra'
21,     .08,  .0001,   .980,  .00,    .00,   9,    100.,    30.,   51.75,   0.01,   0.01,   70.,     'Lakes'
```

Against `convert_to_pressure_levels.WRF_EMISS`, which was measured from the run by the
identity `eps = 1 - (LWUPB-LWUPBC)/(LWDNB-LWDNBC)`:

| cat | name | measured `WRF_EMISS` | `MODI-RUC` `LEMI` | Noah `EMISSMIN` | Noah `EMISSMAX` |
|---:|---|---:|---:|---:|---:|
| 1 | Evergreen Needleleaf | 0.950 | **.950** | .950 | .950 |
| 2 | Evergreen Broadleaf | 0.950 | **.950** | .950 | .950 |
| 3 | Deciduous Needleleaf | 0.940 | **.940** | .930 | .940 |
| 4 | Deciduous Broadleaf | 0.930 | **.930** | .930 | .930 |
| 5 | Mixed Forests | 0.940 | **.940** | .930 | .970 |
| 6 | Closed Shrublands | 0.930 | **.930** | .930 | .930 |
| 7 | Open Shrublands | 0.880 | **.880** | .930 | .950 |
| 8 | Woody Savannas | 0.930 | **.930** | .930 | .930 |
| 9 | Savannas | 0.920 | **.920** | .920 | .920 |
| 10 | Grasslands | 0.920 | **.920** | .920 | .960 |
| 11 | Permanent Wetlands | 0.950 *(not measured)* | **.950** | .950 | .950 |
| 12 | Croplands | 0.935 | **.935** | .920 | .985 |
| 13 | Urban and Built-Up | 0.880 | **.880** | .880 | .880 |
| 14 | Cropland/Natural Mosaic | 0.920 *(not measured)* | **.920** | .920 | .980 |
| 15 | Snow and Ice | 0.980 | **.980** | .950 | .950 |
| 16 | Barren or Sparsely Veg. | 0.850 | **.850** | .900 | .900 |
| 17 | Water | 0.980 | **.980** | .980 | .980 |
| 18 | Wooded Tundra | 0.930 | **.930** | .930 | .930 |
| 19 | Mixed Tundra | 0.920 *(not measured)* | **.920** | .920 | .920 |
| 20 | Barren Tundra | 0.900 *(not measured)* | **.900** | .900 | .900 |
| 21 | Lakes | 0.980 | **.980** | — (Noah section stops at 20) | — |

**21 out of 21 exact.** Including the five entries the converter marks NOT MEASURED and
filled with `EMISSMIN` as a guess — all five happen to be right, and are now confirmed
rather than guessed.

Two further points:

- The Noah `EMISSMAX` column does not explain it either: cat 3 (.940) and cat 5 (.940) sit at
  `EMISSMAX` while cat 10 (.920), cat 12 (.935), cat 14 (.920) and cat 15 (.980) do not. Only
  `LEMI` matches everywhere. This is the fourth and final refutation of the green-fraction
  blend `EMISSMIN + shdfac*(EMISSMAX-EMISSMIN)` that `CLAUDE.md` already records as refuted
  by measurement — it is now refuted by the table as well.
- The measured snow value, 0.980, is `MODI-RUC`'s own `LEMI` for cat 15, `Snow and Ice`. The
  snow *switch* (`CLAUDE.md`: flat 0.98 from `SNOWC >= 0.01`) is a rule in the RUC source,
  which is **not on disk** (§ below) — only the value it switches to is confirmed here.

**`LANDUSE.TBL` carries the identical numbers** in its `MODIS` section, column `SFEM`
(line 213 onward): `.95 .95 .94 .93 .94 .93 .88 .93 .92 .92 .95 .935 .88 .92 .98 .85 .98
.93 .92 .90` for cats 1–20 and `.98` for cat 21 `'Lakes'` — the same column, to the digit.
Its `MODIFIED_IGBP_MODIS_NOAH` section (line 101) gives the *different* Noah-flavoured values
(`.95 .95 .94 .93 .97 .93 .95 .93 .92 .96 .95 .985 .88 .98 .95 .90 .98 .93 .92 .90`) that
were compared against before.

So, precisely: the numbers live in the **RUC-flavoured section of both tables**
(`VEGPARM.TBL:MODI-RUC` / `LANDUSE.TBL:MODIS`), and the error was reading the
**Noah-flavoured section** (`MODIFIED_IGBP_MODIS_NOAH`) of a table whose Noah half this run
never touches.

**Which of the two files RUC actually opened is not settled by anything on disk.** The WRF
source tree is not present under `$WORK/CHAPTER` or anywhere else the pipeline reaches — only
the run-time tables and `README.namelist` were recovered, and neither states which module
reads which file. It does not matter for the result: the two columns are identical.

### What to change

`CLAUDE.md`'s claim that *"four do not, and RUC takes them from neither VEGPARM.TBL nor
LANDUSE.TBL"* should become: **RUC takes all twenty-one from `VEGPARM.TBL`, section
`MODI-RUC`, column `LEMI` (identically, `LANDUSE.TBL` section `MODIS`, column `SFEM`).** The
five NOT MEASURED markers can be dropped — every entry is now backed by the table the run
read. Nothing in the converter changes: `WRF_EMISS` is already correct in all 21 slots. What
changes is that a measured table becomes a cited one.

---

## 6. Options that render a wrfout field meaningless and are **not** in `CLAUDE.md`

This is the part of the ticket with the most left in it. All lines below are d02.

### a. `bucket_mm = -1`, `bucket_J = -1` — accumulation buckets off

```
 BUCKET_MM       =  -1.000000    ,
 BUCKET_J        =  -1.000000    ,
```

Not in `namelist.input`; these are the defaults. Confirms the `no I_RAINNC` assumption
(§4) and extends it: **no `I_AC*` counterpart exists for any radiation accumulator either**,
so all 19 accumulators in `accum_ref.ACCUMULATED_VARS` are monotone within a run by
configuration, not merely by observation.

### b. `topo_wind = 1` — the 10 m wind carries a terrain correction

```
topo_wind                = 1,1,1,
```

`README.namelist`:

```
 topo_wind (max_dom)                 = 0,  ! turn off, 
                                     = 1,    turn on topographic surface wind correction from Jimenez 
                                             (YSU PBL only, and require extra input from geogrid)
```

`U10` and `V10` are **not** the plain surface-layer log-law diagnostic: they carry the
Jiménez sub-grid topography correction, driven by geogrid's `VAR_SSO` (present in the
wrfout). `10u`, `10v`, `10si` and `10fg` all inherit it. This is a real difference from ERA5's
10 m wind and belongs in the documentation of those variables.

### c. `slope_rad = 0`, `topo_shading = 0` — no terrain effect on shortwave

```
 SLOPE_RAD       = 11*0,
 TOPO_SHADING    = 11*0,
```

`README.namelist`: `slope_rad ! slope effects for solar radiation (1=on, 0=off)`;
`topo_shading ! neighboring-point shadow effects for solar radiation`. Both are defaults, not
choices. `SWDOWN`, `ACSWDNB` and therefore `ssrd` are **flat-surface** fluxes: at 3 km over
the Alps and the Pyrenees neither slope aspect nor cast shadow is represented. A user
comparing `ssrd` against a station in a valley should know this.

### d. `swint_opt = 0` with `radt = 5` — shortwave is a 5-minute step function

```
 SWINT_OPT       =           0,
```

`README.namelist`: `swint_opt  Interpolation of short-wave radiation based on the updated
solar zenith angle between SW call / = 0, ! no interpolation`. With `radt = 5`, the
instantaneous SW fields hold whatever the last radiation call produced, up to 5 minutes
stale. Matters at sunrise/sunset and for the instantaneous (not accumulated) SW messages.

### e. `nwp_diagnostics = 1` — seven fields are per-hour maxima, by configuration

```
nwp_diagnostics               = 1,
```

`README.namelist`: `nwp_diagnostics = 0 ! set to = 1 to add 7 history-interval max
diagnostic fields`. The wrfout carries exactly seven:

```
WSPD10MAX    m s-1      WIND SPD MAX 10 M
W_UP_MAX     m s-1      MAX Z-WIND UPDRAFT
W_DN_MAX     m s-1      MAX Z-WIND DOWNDRAFT
UP_HELI_MAX  m2 s-2     MAX UPDRAFT HELICITY
REFD_MAX     dbZ        MAX DERIVED RADAR REFL
HAIL_MAX2D   m          MAX HAIL DIAMETER ENTIRE COLUMN
HAIL_MAXK1   m          MAX HAIL DIAMETER K=1
```

`CLAUDE.md` established for `WSPD10MAX` alone, by testing monotonicity across hours, that it
is reset at every history write. **That is now settled from the configuration, and it
generalises**: with `history_interval = 60`, all seven are 1-hour maxima. The `10fg`
encoding (reference time H-1, step `0-1`, `stepType=max`) is confirmed, and any future use of
the other six inherits the same window with no further testing.

`HAIL_MAX2D` / `HAIL_MAXK1` are **not** HAILCAST output — `hailcast_opt = 0` (§f) — and they
are non-zero on the sample file (max 1.79 cm and 0.68 cm), so they are alive.

### f. `hailcast_opt = 0` — HAILCAST off

```
hailcast_opt             = 0,        0,        0,
```

`README.namelist`: `1 = 1-D hail growth model which predicts 1st-5th rank-ordered hail
diameters, mean hail diameter and standard deviation`. None of those fields exists. Together
with `mp_physics = 6` (§m), which has no hail class, this is why `HAILNC` is identically
zero — `CLAUDE.md` lists it as dead without a reason.

### g. `sf_urban_physics = 0` — no urban canopy

```
sf_urban_physics         = 0,        0,        0,
```

`README.namelist`: `activate urban canopy model (in Noah and Noah-MP LSMs only)` — so with
RUC it would have been inert regardless. Urban is nothing but MODIS category 13
(`ISURBAN = 13` in the wrfout attributes) with its table row. `URBPARM.TBL` is not read; no
`TC_URB`/`TB_URB`/`FRC_URB2D`.

### h. `mosaic_lu = 0`, `mosaic_soil = 0`, `sf_surface_mosaic = 0` — dominant category only

```
 SF_SURFACE_MOSAIC       =           0,
 MOSAIC_LU       =           0,
 MOSAIC_SOIL     =           0,
```

`README.namelist`: `mosaic_lu = 0, ! default ; set to = 1 to use mosaic landuse categories
in RUC`. **This is the configuration line behind the whole geo_em story.** The run reduced
every cell to one dominant land-use and one dominant soil category and discarded the
fractions; `LANDUSEF` is absent from the wrfout. The 90.1 % average dominance and the 17.9 %
of land cells carrying both high and low vegetation, which `CLAUDE.md` reports from geo_em,
describe information the model itself never used. `cvl`/`cvh` from geo_em are therefore
*more* informative than anything in the hourly output, and correctly sourced there.

### i. `rdlai2d = .false.` — `LAI` in the wrfout is a table lookup

```
 RDLAI2D = F,
```

`README.namelist`: `rdlai2d = .false. ! use LAI from input; false means using values from
table`. The `LAI` field in the wrfout is `MODI-RUC`'s `LAI` column for the dominant
category, modulated by green fraction — not observed LAI. **This strengthens the decision not
to publish `lai_lv`/`lai_hv`**: `CLAUDE.md` gives the reason as "the model carries one LAI
per cell, ERA5 wants one per class", which is true; the sharper reason is that the one LAI
it carries is itself keyed on the same dominant category, so no split could recover
independent information. It is a table value wearing a field's clothes.

### j. `usemonalb = .false.`, `rdmaxalb = .true.` — where the albedo comes from

```
 USEMONALB       = F,
 RDMAXALB        = T,
```

`README.namelist`: `usemonalb ! use monthly albedo map instead of table value`;
`rdmaxalb = .true. ! use snow albedo from geogrid; false means using values from table`.
So `ALBBCK` is the `MODI-RUC` `ALBEDO` column by dominant category — **no seasonal cycle from
observation** — while `SNOALB` does come from geogrid. Bears directly on `al`, which the
archive writes in every message.

### k. `output_diagnostics = 0` — no min/max screen-level fields, so no `mx2t`/`mn2t`

```
 OUTPUT_DIAGNOSTICS      =           0,
```

`README.namelist`: `output_diagnostics = 0 ! set to = 1 to add 36 surface diagnostic arrays
(max/min/mean/std)`. There is no `T2MAX`/`T2MIN`, no `U10MAX`, no daily statistics of any
screen-level field. **ERA5's `mx2t` and `mn2t` cannot be produced from these wrfout**, and
this is a configuration fact, not a conversion limitation. It belongs in
`MISSING_VARIABLES.md`, which does not currently carry it. (The hourly maxima of §e are a
different, smaller set.)

### l. `p_top_requested = 5000` — the archive's top pressure level is the model lid

```
p_top_requested          = 5000,
```

and the wrfout confirms `P_TOP = 5000.0` Pa. The registry writes 13 pressure levels with
50 hPa at the top (`wrf_era5_comparison.PRESSURE_LEVELS`). **50 hPa is exactly the model
lid**: there is no model air above it, the topmost mass level sits just below it, and the
100 hPa level is the highest one with genuine model air on both sides.

Compounding it:

```
w_damping                = 0,
damp_opt                 = 0,
```

no upper-level damping of any kind, so vertically propagating gravity waves reflect off that
lid rather than being absorbed. The 50 hPa messages — and to a lesser extent 100 and
150 hPa — deserve a look before anyone trains on them. This is not in `CLAUDE.md` and is
arguably the most consequential item in this section.

### m. `mp_physics = 6` (WSM6) — the hydrometeor set is fixed by it

```
mp_physics               = 6,         6,         6,
```

Six species, single moment: `QVAPOR`, `QCLOUD`, `QRAIN`, `QICE`, `QSNOW`, `QGRAUP` and
nothing else. No hail class (hence `HAILNC` dead, §f), no number concentrations, so no
effective radii and no double-moment diagnostics. `CLAUDE.md`'s `clwc`/`ciwc`/`crwc`/`cswc`
set is exactly what WSM6 can offer; `QGRAUP` has no ERA5 counterpart, as recorded.

Also `MP_ZERO_OUT = 0` — negative moisture is not clipped, so small negative values can
survive in the `Q*` fields. Worth a guard in anything that divides by `1 + total water`.

### n. `gwd_opt = 0` — no gravity wave drag

```
 GWD_OPT =           0,
```

`VAR_SSO` is present in the wrfout but the run never used it for drag (only `topo_wind`
consumes sub-grid orography here, §b). Anything derived from `VAR`/`VAR_SSO` describes the
static dataset, not a process the model ran.

### o. `aer_opt = 0`, `o3input = 2` — clear-sky radiation has no aerosol

```
 AER_OPT =           0,
 O3INPUT =           2,
```

`README.namelist`: `aer_opt = 0, ! none`; `o3input = 2, ! using CAM ozone data
(ozone.formatted)`. RRTMG ran with a CAM ozone climatology and **no aerosol at all**. This
touches the `skt` inversion directly: `LWUPBC`/`LWDNBC` are clear-sky in the sense of
cloud-free, not aerosol-free, and the identity used to measure emissivity is unaffected —
but `ssrd`, `ssrdc` and their biases against observations are.

### p. `hybrid_opt = 2`, `etac = 0.2` — hybrid vertical coordinate

```
 HYBRID_OPT      =           2,
```

confirmed by the wrfout attributes `HYBRID_OPT = 2`, `ETAC = 0.2`. `README.namelist`:
`hybrid_opt = 2, ! default; Klemp cubic form with etac`. The vertical coordinate is **not**
terrain-following eta throughout: above `znw = 0.2` the surfaces become isobaric. Any
reconstruction of pressure from `ZNU`/`ZNW` alone is wrong; the `C1H`/`C2H`/`C1F`/`C2F`
coefficients in the wrfout are required. (wrf-python handles this via `P`+`PB`, so the
current converter is safe — this is a warning for anything new.)

### q. `diff_6th_opt = 2`, `diff_6th_factor = 0.12` — an explicit numerical filter

```
diff_6th_opt             = 2,        2,        0,
diff_6th_factor          = 0.12,     0.12,     0.12,
```

d02 runs the positive-definite 6th-order horizontal filter at 0.12. Every prognostic field
carries its damping; effective resolution is coarser than 3 km by more than advection alone
would give.

### r. `use_adaptive_time_step = .true.`, `adaptation_domain = 2`

```
use_adaptive_time_step   = .true.,
step_to_output_time      = .true.,
adaptation_domain             = 2
target_cfl                    =              1,             1,             1,
```

The timestep is adaptive and **driven by d02**, and `step_to_output_time = .true.` forces the
integration onto the exact history time. So accumulation windows are exactly hourly despite
the varying step — which is what makes §4's byte-level agreement possible.

### s. `ifsnow = 0` — a trap, not a finding

```
ifsnow                   = 0,
```

`README.namelist`: `ifsnow = 1, ! snow-cover effects (only works for sf_surface_physics = 1)`.
With RUC this is **inert**. Do not read it as "snow cover has no effect" — RUC handles snow
fully, and the measured snow emissivity switch (§5) is proof it does. Recorded here so the
next reader of the namelist does not draw the wrong conclusion.

### t. `isfflx = 1` — the surface fluxes exist, they are just not written

```
isfflx                   = 1,
```

`README.namelist`: `1 = with fluxes from the surface`. `HFX`, `LH`, `QFX` and `GRDFLX` are
computed every timestep. Their absence from the wrfout is an **output** matter, not a physics
one — see §u. `CLAUDE.md`'s "the run cannot give ... no `TSK`, `HFX`, `LH`" is true of the
delivered files but the reason it implies (the run did not produce them) is wrong.

### u. `IOFIELDS_FILENAME = NONE_SPECIFIED` — the missing fields are **not settled** by the configuration

```
1367: IOFIELDS_FILENAME       = NONE_SPECIFIED
1389: IGNORE_IOFIELDS_WARNING = T,
```

The namelist **does not restrict the history stream**: no `iofields_filename` was given, so
WRF wrote whatever its Registry marks for history. Yet the wrfout (200 variables) is missing
fields that a stock WRF 4.1.1 history stream carries — verified absent: `TSK`, `HFX`, `LH`,
`QFX`, `GRDFLX`, `EMISS`, `ALBEDO`, `PBLH`, `LANDUSEF`.

So the trimming happened **outside this namelist** — a modified Registry at build time, or a
post-run subsetting step. Which of the two, the configuration cannot say, and the WRF source
tree is not on disk. **This is the honest answer for every "why is field X missing" question:
not settled by the configuration.** It is also the single most valuable thing to ask the run's
producers, because if it was post-run subsetting, `TSK` may still exist upstream and the
entire `skt` inversion becomes a validation exercise rather than a reconstruction.

### v. `feedback = 1`, `smooth_option = 0`; `spec_bdy_width = 5`

```
feedback                 = 1,
smooth_option            = 0,
```

```
spec_bdy_width           = 5,
relax_zone               = 4,
nested                   = .false.,   .true.,   .true.,
```

Two-way nesting without smoothing of the feedback. d02's outer frame is driven from d01 over
the configured widths; the exact treatment at a nest boundary is WRF's nesting code, not
settled by these lines, but the outermost rows and columns of the 1353x1641 grid are not free
model solution and should not be trusted as such.

### w. `p_lev_diags = 1` — the run computed its own pressure-level fields, into a stream we do not receive

```
&diags
 p_lev_diags      = 1
 num_press_levels      = 11,
 press_levels      = 100000, 97500, 95000, 92500, 90000, 85000, 70000, 60000, 50000, 30000, 20000,
```

with

```
auxhist23_interval       = 60,       60,
io_form_auxhist23        = 2
```

WRF interpolated its **own** diagnostics to 11 pressure levels every hour, for d01 and d02,
and wrote them to `auxhist23_d<domain>_<date>`. No `auxhist23` file exists anywhere under
`$WORK`, and the wrfout carries no `P_PL`/`GHT_PL`, so we do not receive that stream.

Eight of those levels are ours too — 1000, 925, 850, 700, 600, 500, 300, 200 hPa. If the
`auxhist23` files still exist upstream they are an **independent check on our vertical
interpolation** on those eight levels, computed by the model itself on its own native grid.
Worth asking for.

### x. Sea ice, for the record

```
 FRACTIONAL_SEAICE       =           0,
 SEAICE_THRESHOLD        =   100.0000    ,
 SEAICE_ALBEDO_OPT       =           0,
 SEAICE_SNOWDEPTH_OPT    =           0,
```

`README.namelist` on `seaice_threshold`: *"tsk < seaice_threshold, if water point and 5-layer
slab scheme, set to land point and permanent ice ... The default value has changed from 271
to 100 K in v3.5.1 to avoid mixed-up use with fractional seaice input"*. At 100 K it never
fires. So the sea ice in this run comes **entirely from the input data**, is **binary per
cell** (`fractional_seaice = 0`), and has a constant albedo. This is consistent with — and
explains — `CLAUDE.md`'s finding that the land/sea mask varies in time: it varies because
each run is initialised with a fresh sea-ice field, not because the model reclassifies points
on a temperature test.

### y. Category codes, from the wrfout attributes

```
MMINLU = 'MODIFIED_IGBP_MODIS_NOAH'
NUM_LAND_CAT = 21
ISWATER = 17   ISLAKE = 21   ISICE = 15   ISURBAN = 13   ISOILWATER = 14
```

matching `num_land_cat = 21` in the namelist. Confirms every category code `CLAUDE.md` and
`static_ref.py` rely on.

### z. Soil initialisation

```
num_metgrid_soil_levels  = 4,
num_soil_layers          = 6,
```

RUC's 6-node soil column was initialised by interpolation from the driving data's 4 layers.
The deep column carries less independent information than its 6 nodes suggest — relevant to
`stl3`/`stl4` and `swvl3`/`swvl4`, which the archive publishes as exact ERA5 layer averages
of a profile whose deep structure is interpolated from 4 input layers.

---

## 7. Summary against `CLAUDE.md`

**Confirmed, now with a line from the file**

- `cu_physics = 0` on d02, and `shcu_physics = 0` besides — `RAINC`/`RAINSH`/`PREC_ACC_C`
  dead, `cp`/`csf` not producible
- `sf_ocean_physics = 0`, `sf_lake_physics = 0` (both inherited defaults, absent from
  `namelist.input`)
- `sst_update = 0` — SST constant per run; and `sst_skin = 0`, which is *why* `SSTSK` is dead
- `bl_pbl_physics = 1`, `km_opt = 4` — **no TKE**, by configuration
- `icloud = 1` = Xu–Randall — `CLDFRA` is fractional. The correction `CLAUDE.md` already made
  is confirmed; `icloud = 2` would have been the binary one
- `sf_surface_physics = 3` (RUC), 6 soil nodes at 0/5/20/40/160/300 cm exactly as stated
- no bucket reset — `bucket_mm = bucket_J = -1`, so *all* 19 accumulators are monotone within
  a run by configuration
- `WSPD10MAX` is a 1-hour maximum — `nwp_diagnostics = 1`, "7 history-interval max fields",
  and `history_interval = 60`
- `lightning_option = 3`, `do_radar_ref = 1`, `prec_acc_dt = 60`
- the spinup structure: `start_hour = 18`, `run_hours = 30`

**Corrected**

1. **The emissivity table is not RUC's own.** All 21 values are `VEGPARM.TBL` section
   `MODI-RUC`, column `LEMI` (equivalently `LANDUSE.TBL` section `MODIS`, column `SFEM`). The
   earlier comparison read the Noah section of a table whose Noah half this run never touches.
   The five NOT MEASURED entries are all correct and can be cited rather than guessed.
2. **`PBLH` is not a "the run cannot give" case.** YSU diagnoses a PBL height and WRF writes
   it; it is absent from the *delivered* wrfout for a reason outside the namelist (§6.u).
   Only the TKE half of that sentence is settled by the configuration.
3. **`HFX`/`LH`/`TSK` likewise.** `isfflx = 1`: they are computed. Their absence is an output
   matter, and the namelist does not restrict the output.
4. **`lightning_option = 3` is not a flash-rate scheme.** It is the Yair et al. (2010) LPI;
   `flashrate_factor` and `cellcount_method` are set but belong to options 1/2/11 and are
   inert here.
5. **`HAILNC` dead needs no mystery:** WSM6 has no hail class and `hailcast_opt = 0`.
6. **`ACHFX`/`ACLHF`/`ACGRDFLX`/`NOAHRES` dead needs no mystery either:** they are Noah
   accumulators and this run is RUC. Not a bucket artefact — `ACSWDNB`/`ACLWDNB` are alive on
   the same file with the same `bucket_J = -1`.

**Not settled by the configuration** — say so rather than inferring

- Why `TSK`, `HFX`, `LH`, `QFX`, `GRDFLX`, `EMISS`, `ALBEDO`, `PBLH` and `LANDUSEF` are
  missing from the wrfout. `IOFIELDS_FILENAME = NONE_SPECIFIED`, so the namelist did not
  trim them. Modified Registry or post-run subsetting — the files on disk cannot tell, and
  the WRF source is not here. **Worth asking the run's producers: if it was subsetting, `TSK`
  may exist upstream.**
- Which file RUC opened for `LEMI` (`VEGPARM.TBL` or `LANDUSE.TBL`) — identical values, so it
  does not matter
- The exact snow-emissivity switch in RUC — only the value it switches to (0.980,
  `MODI-RUC` cat 15) is confirmed here
- Whether this one namelist governs every year of the archive. It is one run's
  (`2022-12-31_18:00:00`); a per-year check was not part of this ticket

**New, and the highest-value items**

- **`p_top_requested = 5000`**: 50 hPa is the model lid, and it is the archive's topmost
  pressure level. With `damp_opt = 0` and `w_damping = 0` there is no upper damping either.
- **`output_diagnostics = 0`**: no `T2MAX`/`T2MIN`, so `mx2t`/`mn2t` are impossible. Belongs
  in `MISSING_VARIABLES.md`.
- **`topo_wind = 1`**: `U10`/`V10` carry the Jiménez terrain correction.
- **`slope_rad = 0`, `topo_shading = 0`**: `ssrd` is a flat-surface flux, in a 3 km domain
  full of mountains.
- **`mosaic_lu = 0`**: the configuration line behind the entire geo_em story.
- **`rdlai2d = .false.`**: the wrfout's `LAI` is a table value keyed on the dominant category
  — a sharper reason not to publish `lai_lv`/`lai_hv`.
- **`usemonalb = .false.`**: `ALBBCK` has no observed seasonal cycle.
- **`p_lev_diags = 1`**: the run produced its own pressure-level diagnostics on 11 levels into
  an `auxhist23` stream we never receive; 8 levels overlap ours and would validate our
  interpolation.
- **`PREC_ACC_NC` is the exact hourly `RAINNC` increment** (verified to 1.1e-4 mm over the
  whole domain): a per-file cross-check on `tp` that bypasses the 00Z sidecar entirely.
