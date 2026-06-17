# Confronto variabili: liste MeteoSwiss vs pipeline CHAPTER

Fonte liste: `Compare_list_vars_from_meteoswiss.ods`.
Fonte pipeline: `wrf_era5_comparison.py` (`WRF_TO_ECMWF_PARAMID`) + `convert_to_pressure_levels.py`.
Aggiornato: 2026-06.

## Le 4 colonne del foglio
| Col | Nome | Significato |
|---|---|---|
| A | `ERA5 dataset` | Lista ERA5/Anemoi completa di riferimento |
| B | `Training_Meteoswiss USED!` | Variabili **realmente usate** nel training MeteoSwiss → **lista di riferimento** |
| C | `COSMO_meteoswiss_recipe` | Variabili recipe COSMO (nomi Anemoi) |
| D | `COSMO_meteoswiss_recipe_orig_names` | Nomi nativi COSMO (U_10M, T_2M, FIS, OMEGA, …) |

Relazioni tra colonne:
- **B = A** meno `cp`, `sdor`, `slor`, `tcw` e **senza il livello 600 hPa** (B = 12 livelli, non 13). Niente `w`.
- **C** = B + `w` (13 liv.) + 600 hPa + `tqv`, `tcc`, `hsurf`.
- Forcings (`cos/sin_julian_day`, `_latitude`, `_local_time`, `_longitude`, `insolation`) presenti in A, B, C.

## Livelli di pressione
- CHAPTER: 13 livelli — 1000, 925, 850, 700, **600**, 500, 400, 300, 250, 200, 150, 100, 50 hPa.
- USED (B): 12 livelli (stessi **senza 600**). ERA5 (A) e COSMO (C): 13 livelli.

## Esito del confronto (riferimento = col. B "USED")

### 1. Richieste da B e già prodotte da CHAPTER ✓
Surface: `10u 10v 2d 2t lsm msl skt sp tp z(surf)`.
Livelli: `t u v q z`. **Tutta la fisica richiesta è presente** (CHAPTER su 13 liv., USED ne usa 12).

### 2. Extra prodotti da CHAPTER → DISABILITATI (commentati, non eliminati) 2026-06
Variabili che NON compaiono in **nessuna** colonna (A/B/C/D). Commentate in
`wrf_era5_comparison.py` (e `theta/rh/pvo` rimosse da `derived_3d` in `convert_to_pressure_levels.py`):

| WRF | shortName | paramId | Tipo | Motivo |
|---|---|---|---|---|
| CLDFRA | cc | 248 | livelli | cloud fraction per livello — diversa da `tcc`/CLCT (cloud cover) di col. C |
| ACLWDNB | strd | 175 | surface | radiazione LW down accumulata |
| ACSWDNB | ssrd | 169 | surface | radiazione SW down accumulata |
| ISLTYP | slt | 43 | surface | categoria suolo |
| SEAICE | ci | 31 | surface | flag ghiaccio marino |
| SST | sst | 34 | surface | temperatura superficie mare |
| Q2 | q@2m | 133 | 2 m | umidità specifica a 2 m (liste hanno `q` solo ai livelli) |
| theta | pt | 3 | livelli | temperatura potenziale |
| rh | r | 157 | livelli | umidità relativa |
| pvo | pv | 60 | livelli | vorticità potenziale |

Per riattivarle: togliere il `#` nel dict `WRF_TO_ECMWF_PARAMID` (e, per `theta/rh/pvo`,
rimetterle nella lista `derived_3d`).

### 3. Extra MANTENUTI (compaiono in almeno una colonna, quindi NON commentati)
| WRF | shortName | In colonna | Nota |
|---|---|---|---|
| W | w | C (COSMO) / D=OMEGA | non in A/B, ma richiesto da COSMO |
| VAR_SSO | sdor | A (ERA5) | non in B |
| slor | slor | A (ERA5) | non in B |
| tcw | tcw | A (ERA5) | non in B |
| livello 600 hPa (t/u/v/q/z) | — | A, C | non in B (che usa 12 livelli) |

## Variabili richieste da ≥1 colonna ma NON nei wrfout (non aggiungibili ai GRIB)

| Variabile | Richiesta da | Stato nei wrfout CHAPTER | Conclusione |
|---|---|---|---|
| `cp` (convective precip) | A (ERA5) | `RAINC` esiste ma con gli schemi convection-permitting a 3 km è ~0 / non significativo | **Non aggiungibile in modo sensato.** Non è in B/C → non serve per la lista USED |
| `cos/sin_julian_day`, `cos/sin_latitude`, `cos/sin_longitude`, `cos/sin_local_time` | A, B, C | non sono campi meteo dei wrfout | **Non vanno nei GRIB**: le genera Anemoi come *forcings* a build-time (vedi sotto) |
| `insolation` | A, B, C | non è un campo wrfout (≈ cos solar zenith angle) | come sopra: forcing Anemoi (`COSZEN` esiste nei wrfout ma la via standard è il forcing Anemoi) |

Variabili di colonna C derivate dai wrfout:
- `tqv` (TQV) → **IMPLEMENTATO 2026-06**: shortName `tcwv`, paramId 137. Integrale verticale di `QVAPOR`
  (mixing ratio, come `tcw`). Diverso da `tcw` (136 = vapore + idrometeore).
- `tcc` (CLCT) → **IMPLEMENTATO 2026-06**: shortName `tcc`, paramId 164. Da `CLDFRA` con overlap
  massimo-random (ECMWF/RRTMG). Diverso da `cc` (248 = cloud fraction per livello, disabilitato).
- `hsurf` (HSURF): = `HGT` → già encodato come `z` surface (paramId 129).

Nota naming: in GRIB `tqv` esce con shortName ECMWF `tcwv`; la recipe COSMO la chiama `tqv` →
eventuale `rename` nella recipe Anemoi se si vuole il nome COSMO.

## Nota Anemoi: i forcings si generano nella recipe, non nei GRIB
Verificato sulla doc anemoi-datasets (`building/sources/forcings`): i forcings dipendono solo
da posizione/tempo e si dichiarano nella sezione `input` della recipe con un `template` che
referenzia un'altra source. Vengono **generati a build-time del dataset**. Variabili disponibili:
`latitude, longitude, cos/sin_latitude, cos/sin_longitude, julian_day, cos/sin_julian_day,
local_time, cos/sin_local_time, insolation (= cos_solar_zenith_angle), toa_incident_solar_radiation`.

Esempio (da integrare in `wrf_anemoi_recipe.yaml`):
```yaml
input:
  join:
    - grib:
        path: /path/ailam-an-cima-3km-*-*.grib
    - forcings:
        template: ${input.join.0.grib}
        param:
          - cos_latitude
          - sin_latitude
          - cos_longitude
          - sin_longitude
          - cos_julian_day
          - sin_julian_day
          - cos_local_time
          - sin_local_time
          - insolation
```
La `grib` source accetta `param` e `levelist` (linguaggio MARS) per selezionare variabili/livelli
— utile per limitare i livelli (es. escludere 600 hPa) o i parametri direttamente in lettura.
Filtri `select`/`drop`/`rename` sono applicabili a valle via `pipe`.
```
