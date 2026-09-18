# Handoff — le variabili recuperate da geo_em.d02

Scritto il 2026-09-16, riscritto il 2026-09-17, **riscritto il 2026-09-18** quando il file
statico `geo_em.d02` è arrivato da LRZ.

> **Stato: il codice è finito e verificato. La campagna è FERMA e NON va fatta ripartire
> senza un via esplicito dell'utente.**

---

## 1. Cosa è successo

`geo_em.d02` — dichiarato irrecuperabile in `CLAUDE.md`, nel registry, in `MISSING_VARIABLES.md`
e nella versione precedente di questo file — è stato ottenuto da LRZ. Sta in
`/leonardo_work/AIFPT_AILAMIT/CHAPTER/geo_em/` (fuori da HOME e fuori dal worktree git), con
`wrfinput_d02`, `wrfbdy_d01`, `namelist.input` e `namelist.wps`.

**È il file dei run, verificato e non assunto:**

| controllo | esito |
|---|---|
| `XLAT_M`/`XLONG_M` contro un wrfout | differenza massima **0.0** |
| `LU_INDEX` contro `IVGTYP` (escluso il recode dei laghi) | **100.00 %** su 2019-08 e 2024-07, 99.95 % su 2024-03 (la differenza è il ghiaccio marino) |
| `SCT_DOM` contro `ISLTYP` | 98.5 % (la differenza è acqua/ghiaccio) |
| `HGT_M` contro `HGT` | rms 8.24 m, il ritocco di `real.exe` |

L'unica differenza sistematica è categoria 21 (lago) → 17 (acqua): `sf_lake_physics=0`. È
esattamente il motivo per cui `cl` è informazione nuova — **19 309 celle che la maschera terra/mare
chiama terra contengono un lago sub-griglia**, e il modello quella classe l'ha buttata a runtime.

## 2. Lo schema: 231 → 246 messaggi

75 → **90 voci**, +15 messaggi, tutti a livello singolo. **Puramente additivo, verificato**:
rileggendo un GRIB vecchio e uno nuovo dello stesso timestep, i 231 messaggi preesistenti sono
identici byte a byte, 15 aggiunti, 0 modificati.

| campo | paramId | da dove |
|---|---|---|
| `cvl`, `cvh` | 27, 28 | somma di `LANDUSEF` sulle classi MODIS basse / alte |
| `tvl`, `tvh` | 29, 30 | classe dominante bassa / alta tradotta in code table 4.234 |
| `slt` | 43 | soglie FAO di ECMWF su `CLAYFRAC`/`SANDFRAC` — nessun crosswalk di categorie |
| `cl`, `dl` | 26, 228007 | `LANDUSEF[21]` e `LAKE_DEPTH` (`dl` su `entireLake`) |
| `swvl1-4` | 39-42 | medie di strato ERA5 del profilo RUC (`SMOIS`) |
| `stl1-4` | 139, 170, 183, 236 | idem (`TSLB`) |

**Il blocco suolo è integrato, non rietichettato.** RUC ha 6 nodi a 0/5/20/40/160/300 cm e un
profilo lineare fra loro; gli strati ERA5 (0-7, 7-28, 28-100, 100-289 cm) stanno **tutti dentro**
quei nodi, quindi ogni strato è l'integrale esatto del profilo del modello e non si estrapola
niente. In pratica una matrice 4×6 costante (`convert_to_pressure_levels.SOIL_LAYER_WEIGHTS`).
Questo è ciò che è cambiato rispetto al 2026-09-17: l'obiezione era contro lo scrivere i valori
puntuali, non contro l'integrarli.

**`tvl` è mascherato dove domina lo shrubland** (124 672 celle, 15.8 % di quelle con `cvl>0`,
Iberia e margine nordafricano): MODIS non porta la fenologia degli arbusti mentre la 4.234 separa
sempreverdi (16) da caducifogli (17), e si è scelto di non inventare. `cvl` dà comunque la
copertura. **`dl` è mascherato fuori dai laghi**: `LAKE_DEPTH` vale 10.0 m su **99.56 %** del
dominio, che è il riempimento di default di WPS.

Non pubblicati: `lai_lv`/`lai_hv` (il modello porta un solo LAI per cella) e `anor`/`isor`
(`OA`/`OL` non sono l'angolo e l'anisotropia di ECMWF).

## 3. `skt` NON è stato toccato — questione chiusa per misura

L'emissività che WRF ha usato è stata **ricavata dai dati**, non scelta. La relazione
`LWUPB − GLW = eps·(σT⁴ − GLW)` è una retta per l'origine la cui pendenza *è* l'emissività;
adattata cella per cella su un ciclo diurno completo (12 istanti, luglio e marzo) risulta una
**costante per categoria**: dispersione interna IQR 0.0005–0.0014, e luglio e marzo concordano a
0.0005. Il controllo è esatto: sull'acqua, dove `TSK` è nota perché è la SST, lo stesso fit
restituisce **0.97999** contro 0.980, R² = 1.000000.

Due candidati sono stati **respinti**:

| ipotesi | perché cade |
|---|---|
| mix pesato su `LANDUSEF` | porta `max\|skt−SST\|` sul mare aperto da 0.0015 K a **0.98 K**. Con `sf_surface_physics=3` WRF non vede mai `LANDUSEF` a runtime |
| `EMISSMIN + shdfac·(EMISSMAX−EMISSMIN)`, la formula con cui WRF stesso inizializza `EMISS` | l'eps adattata è **piatta** rispetto a VEGFRA (< 0.001 su tutto l'intervallo) dove quella formula imporrebbe +0.04…0.065. Il caso più pulito è il prato a luglio: 0.9202 adattato, 0.920 `EMISSMIN`, 0.96 se avesse usato la tabella estiva |

Quindi `EMISSMIN[IVGTYP]` — quello che il converter già fa — è giusto. Contro il livello di suolo
a 0 cm su terra senza neve:

| superficie | notte | giorno |
|---|---|---|
| foreste, savana, prato, urbano (7 classi) | 0.03–0.11 K RMSE | 0.09–0.22 K |
| foresta mista, colture | 0.12–0.19 K | 0.21–0.30 K |
| **arbusteto aperto** | 0.72 K (bias −0.68) | 1.22 K (bias −1.15) |
| **suolo nudo / rado** | 0.75 K (bias −0.74) | 1.54 K (bias −1.52) |

Sulle due classi aride `skt` corre 1–1.5 K più freddo del suolo. Lì il fit vorrebbe un'emissività
vicina a **0.85**, che chiuderebbe lo scarto — ma 0.85 sta **sotto ogni emissività di ogni
tabella WRF** (il minimo assoluto è 0.88, l'urbano), quindi non può essere ciò che il modello ha
usato, e adottarla significherebbe mettere un numero inventato sotto un nome ERA5. **Non
"sistemare" questo scarto con un fit.**

Nota per chi rilegge le versioni precedenti: una misura intermedia usava `SOILT1` come
riferimento e dava 7 K di RMSE con +6 K di bias. Era il campo sbagliato — `SOILT1` è la
temperatura *dentro la neve*, non la pelle.

## 4. Costo misurato

| | 231 messaggi | 246 messaggi |
|---|---|---|
| file orario | 710.4 MB | **749.6 MB** (+39.2 MB, +5.5 %) |
| giorno | 17.0 GB | **17.9 GB** |
| anno | 6.20 TB | **6.55 TB** |
| tempo / RAM su 1 core DCGP | ~5 min / 19.0 GB | **~6 min / 19.9 GB** |

L'aggiunta è piatta nel tempo (sette campi costanti, otto che variano poco). `step_convert_mem:
32G` resta giusto. Misure su tre file reali: 749.6 MB (luglio 14Z), 650.3 MB (00Z), 772.4 MB
(marzo 12Z).

## 5. Verifiche fatte

Tutte passate, seguendo i quattro passi di `CLAUDE.md`:

- `--debug-vars` sui 15 campi: la cache 3D viene saltata (fix di `flat_only`, prima ogni campo
  derivato di superficie leggeva 2.6 GB inutilmente);
- tre conversioni complete come job SLURM: **246 messaggi** ciascuna, luglio 14Z / 00Z / marzo;
- `check_grib_sanity.py`: `checked=3 bad=0`;
- suolo ricalcolato indipendentemente in numpy: concordanza relativa **1.5e-8**;
- maschera del suolo == terra della `lsm` **oraria**, e si muove davvero: 1 304 109 punti a luglio,
  1 306 578 a marzo, differenza **2469** — esattamente i punti di ghiaccio marino documentati;
- statiche **identiche byte a byte** fra un file di luglio e uno di marzo, mentre `lsm` no;
- `cvl+cvh+(classi né l'una né l'altra) == 1` a 1.9e-7; `dl` presente su esattamente 88 785 celle;
- 00Z: accumulazioni ancora esattamente zero;
- additività: 231 messaggi preesistenti invariati.

Un dettaglio trovato strada facendo: `CLAYFRAC` ha un picco esattamente su 0.35 che in float64
legge 34.999999 e cadeva dal lato sbagliato della soglia FAO dei 35 %, spostando 3922 celle da
*fine* a *medium*. Risolto arrotondando a 1e-4 punti percentuali, più fine della spaziatura del
dato stesso (~4e-4).

## 6. Cosa c'è di nuovo nel repo

- **`static_ref.py`** — legge `geo_em.d02` una volta e scrive `static_v1/chapter_static_d02.npz`
  (1.8 MB). **Tutte le decisioni di mapping stanno qui**, non nel converter. `--check-wrfout`
  testa l'assunzione e si rifiuta di scrivere se le griglie differiscono.
- **`hpc/grib_schema_ok.py`** — conta i messaggi camminando sulle intestazioni GRIB, senza
  eccodes né numpy (i tool `grib_*` non esistono in questa installazione spack). Serve allo
  **skip sensibile al contenuto**: i job di convert ora saltano un output solo se ha
  `EXPECTED_MESSAGES` messaggi, quindi un cambio di schema si auto-ripara e non serve più un
  albero nuovo ogni volta.
- Registry, converter, `convert_step.sh`/`convert_day.sh`, `fetch_step.sh`,
  `submit_step_pipeline.py`, `conf/pipeline.yaml` (`grib_dir` → **`grib_v3`**, nuovo
  `static_ref_dir`), `check_grib_sanity.py` (`STATIC` esteso), e la documentazione
  (`CHAPTER_VARIABLES.md` §8 con le tabelle di traduzione, `MISSING_VARIABLES.md`, `CLAUDE.md`).

**`accum_ref_v2` non è stato rinominato** e non va rinominato: non si aggiunge nessun
accumulatore, i 223 sidecar restano validi, e passare a `_v3` costringerebbe a riscaricare
wrfout 00Z che non esistono più. La versione del sidecar insegue `ACCUMULATED_VARS`, quella
dell'albero insegue lo schema dei messaggi.

## 7. Stato operativo e ordine di ripartenza

**Fermato il 2026-09-18 alle 17:15**, prima di toccare il repo (lezione dei null byte, commit
`de63194`): stop flag `rebuild_r24_02_cv.stop`, `rebuild_r24_03_dl.stop`,
`rebuild_sequence.stop`; coda `conv_` scesa a 0 e driver tutti morti prima della prima modifica.
Gli stop flag di `fill2024` sono rimasti dove erano.

Cosa c'era a quel punto: **5291 file in `grib_v2`** a 231 messaggi (2019-06/09, 2024-01/02/03 e
06/09), `wrfout_rebuild` con ~600 wrfout staged, quota a 55 TB su 100.

**Ordine di ripartenza — nessuno di questi passi è stato eseguito:**

1. **`wrfout_rebuild`, ~600 ore, gratis.** Già a disco. Convertirle per prime in `grib_v3` con
   `keep_wrfout=true`: validazione end-to-end su scala, zero datamover.
2. **Le ~4392 ore a disco, zero download.** `hpc/run_share_conversion.sh`: `wrfout_share`
   (2019-06-17..09-06 e 2024-06-18..09-12) e `wrfout_2024fill` (2024-03-18..03-31).
   `keep_wrfout=true`, gate 48. ~370 core-ora. **Non si cancella niente.**
3. **Le ~900 ore i cui wrfout sono spariti** (2019-09-07..09, 2024-01, parte di 2024-02):
   riscarico, ~8 TB dal relay. La lista si ricostruisce da `logs/freeze_staged.txt` e dal ledger
   `rebuild_r24_02_cv_status.log`, **non** dai confini di fase. `PHASES_ONLY` obbligatorio.
4. **Il resto** (resto di 2019 e 2024, 2025-H1) su `hpc/run_year_rebuild.sh`.

`grib_v2` si cancella **solo** quando `grib_v3` ha passato `check_grib_sanity` sullo stesso
insieme di file: è l'unica copia di quelle ~900 ore i cui wrfout non esistono più.

## 8. Decisioni aperte

1. `MISSING_VARIABLES.pdf` e `CHAPTER_VARIABLES.pdf` sono da sottoporre ai colleghi; il §6.1 del
   primo chiede conferma proprio sulla lista land-surface, che ora è quasi completa.
2. `mucape`/`mucin`: i punti indefiniti sono scritti come 0, non come mancanti. Da confermare.
3. Il geo_em è datato 2022-12-31 18Z e l'archivio arriva al 2025: **ripetere `--check-wrfout` sul
   primo wrfout 2025 disponibile** prima di fidarsi delle statiche per quell'anno.
