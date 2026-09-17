# Handoff — nuove variabili nei GRIB CHAPTER

Scritto il 2026-09-16, riscritto il 2026-09-17 dopo il secondo giro di variabili.

**Stato: lo schema a 246 messaggi è implementato e testato su tre file reali. La campagna di
ri-conversione NON è partita.**

---

## 1. Cosa è cambiato

Lo schema è passato da **21 variabili / 93 messaggi in GRIB1** a **90 variabili / 246 messaggi
in GRIB2**, in due tappe: prima 62/182 (commit `c1f8a2f`), poi altre 28 voci trovate rileggendo
per intero le 200 variabili del wrfout. Nessuna variabile precedente è stata tolta.

Il passaggio a GRIB2 non è estetico: `2r`, `tirf`, `mucape`, `mucin` e `wz` **non esistono in
GRIB1**, e GRIB1 non sa dichiarare la sfera su cui WRF integra (vedi §4).

Prima tappa: `tirf`, `2r`, `10fg`, `100u/100v`, `200u/200v`, `vwsh`, `hcc/mcc/lcc`,
`mucape/mucin`, `ssrd`, `tsr`, `r`, `clwc`, `ciwc`, `w` (ω) e `wz` sui livelli, `sst`, `ci`, e il
land-surface ERA5 (`swvl1-4`, `stl1-4`, `sd`, `rsn`, `sf`, `src`, `sro`, `ssro`, `cvl`, `lai_lv`,
`tvl`, `slt`, `zust`, `fsr`).

Seconda tappa (28 voci, 64 messaggi):

| gruppo | variabili |
|---|---|
| livelli di pressione (+39 msg) | `cc` (frazione di nube), `crwc` (pioggia), `cswc` (neve) |
| integrali di colonna | `tclw`, `tciw`, `tcrw`, `tcsw` |
| radiazione, il bilancio completo | `strd`, `ssrdc`, `strdc`, `tisr` (nativi) · `ssr`, `str`, `ssrc`, `strc`, `tsrc`, `ttr`, `ttrc` (netti) |
| idrologia e neve | `ro`, `snowc`, `tsn` |
| albedo | `al` (background senza neve), `fal` (reale, con bitmap di notte) |
| vegetazione alta | `cvh`, `tvh`, `lai_hv` — e `cvl`/`tvl`/`lai_lv` **ridefinite** alla sola vegetazione bassa |
| sforzo superficiale | `iews`, `inss` |

La separazione alta/bassa usa `ZTOPV` di `VEGPARM.TBL` (sezione `MODIFIED_IGBP_MODIS_NOAH`,
lo schema del run): categorie 1-5 e 18 sono alta (19,6 % della terra), 6-12/14/19/20 bassa
(50,5 %); urbano, nudo, ghiaccio e acqua non sono né l'una né l'altra. **Questa ridefinizione è
l'unico contenuto che cambia** rispetto ai 182 messaggi: prima `cvl`/`tvl`/`lai_lv` contenevano
tutto indistintamente, il che era una mappatura sbagliata su ERA5.

La lista autorevole è il dict `WRF_TO_ECMWF_PARAMID` in `wrf_era5_comparison.py`; quello che
**non** si può produrre, e perché, è in `MISSING_VARIABLES.md` (+ `.pdf`, da sottoporre ai
colleghi).

## 2. Bug trovati e corretti per strada

| | |
|---|---|
| `W` era scritto con `paramId=40` in tabella 128, che eccodes rilegge come **`swvl2`** (umidità del suolo) | ora `wz` = 260238, più `w` = 135 (ω in Pa/s) |
| `2d` era scritto in **gradi Celsius** sotto un paramId che ECMWF definisce in kelvin | ora si chiede `getvar('td2', units='K')`. **L'archivio GRIB1 esistente ha questo errore**: chi lo usa deve sommare 273.15 |
| La griglia era geolocalizzata con un errore fino a **~1,1 km** al bordo nord | ora `shapeOfTheEarth=1` con raggio 6370 km (quello di WRF): errore ~2 m |
| Una variabile che falliva veniva stampata e ignorata, il file usciva incompleto | ora la conversione **aborta**, e `check_grib_sanity.py` verifica l'inventario completo dei messaggi |
| `CLDFRA` era documentata come **binaria 0/1**: falso. `ICLOUD=1` è Xu-Randall, il campo è continuo (solo il 18-22 % dei punti nuvolosi sta esattamente a 1) | corretto in `CLAUDE.md` e `MISSING_VARIABLES.md`; `cc` è ora pubblicata anche sui livelli |
| `cp`/`csf` stavano per essere pubblicate come "zeri fisicamente corretti" | no: `CU_PHYSICS=0` le rende **campi morti**, e un campo sempre zero resta un campo morto qualunque sia la ragione. Fuori |

## 3. Vincoli scoperti, da non violare

- **I campi accumulati in GRIB2 richiedono il product definition template 8.** Le loro
  definizioni ECMWF impongono `typeOfStatisticalProcessing`, che nel template istantaneo non
  esiste: `codes_set(paramId)` su un messaggio PDT 0 fallisce con "Key/value not found". Sono
  scritti con reference time = 00Z del giorno e step `0-H`; `validityDate`/`validityTime`
  risolvono comunque al timestep. **Un file mescola reference time diversi di proposito:
  indicizzare sulla validità, mai su `dataTime`.**
- **`10fg` è l'unica eccezione**: `WSPD10MAX` viene azzerata da WRF a ogni scrittura (verificato:
  non è monotona fra ore consecutive), quindi è un massimo orario, scritto con reference time
  H-1 e step `0-1`.
- **`ACSNOM` non è un accumulatore monotono** (punti che si riazzerano dentro il run, misurato
  -7,26 mm contro le 00Z): per questo `smlt` non viene prodotta.
- **Aggiungere un nome a `accum_ref.ACCUMULATED_VARS` rende incompleti tutti i sidecar già
  scritti** (`load_ref` solleva `KeyError`): quei giorni vanno ri-estratti dal wrfout 00Z. È già
  successo con questo schema, quindi i sidecar vanno rigenerati insieme ai GRIB.

## 4. Costi misurati (1 core DCGP)

| | GRIB1 | 182 msg | **246 msg** |
|---|---|---|---|
| messaggi | 93 | 182 | **246** |
| dimensione | 388 MB | 663 MB | **761 MB** (14Z estivo) · 661 MB (00Z) · 784 MB (marzo) |
| media pesata sul giorno | — | ~673 MB | **~767 MB → 19 GB/giorno, ~7,0 TB/anno** |
| tempo | ~7,5 min | ~2:47 | **~5:15** |
| picco RAM | — | 18,2 GB | **19,0 GB** (`slurm.step_convert_mem: 32G`, la RAM non è fatturata) |

Misurato il 2026-09-17 su `wrfout_share/2024-07-01` (00Z e 14Z) e `wrfout_2024fill/2024-03-20`
(12Z). Le 4380 ore già su disco costano quindi ~3,4 TB e ~380 core-ora.

**Livelli di pressione: restano 13.** I 37 livelli ERA5 sono stati valutati e scartati: 8 sono
sopra il tetto del modello (`P_TOP` = 50 hPa, livello di massa più alto 51,9 hPa) e quindi
impossibili, e i 29 fattibili porterebbero il file orario a ~1,45 GB e l'anno a 18,1 TB.

## 5. Come far ripartire la pipeline (SOLO dopo il via)

L'output va in un albero **nuovo**, `grib_v2/` (già impostato in `conf/pipeline.yaml`): la
re-entrancy di `convert_step.sh` si basa sull'esistenza del GRIB di output, quindi scrivere lo
schema nuovo dentro `grib/` salterebbe in silenzio ogni ora già convertita. `grib/` si cancella
a validazione finita.

Ordine consigliato:

1. **Le 4380 ore già su disco**, in un colpo solo: `bash hpc/run_share_conversion.sh` da un
   **nodo di login normale** copre ora tutte e tre le finestre (`wrfout_share` 2024, poi
   `wrfout_share` 2019, poi `wrfout_2024fill` 2024-03-18..03-31), ciascuna con la propria
   directory di wrfout nella tabella `WINDOWS`. `keep_wrfout=true`, gate 48, nessuna
   cancellazione. Unico accorgimento: 2024-03-18 non ha il suo 00Z su disco, quindi `ensure_ref`
   se lo scarica dal relay (un file, ~9 GB).
   I sidecar vanno nel tree **nuovo** `accum_ref_v2` (già in `conf/pipeline.yaml`): i 520 vecchi
   contengono 6 variabili contro le 19 che servono ora, e `ensure_ref` si fida di qualunque
   sidecar non vuoto trovi.
2. **8424 ore da ri-scaricare** (~77 TB, ~5 giorni di datamover) a blocchi mensili.
   **Prima serve uno scan/recall da nastro su LRZ** (`hpc/lrz/chapter_scan.sh`, poi
   `chapter_recall.sh` mese per mese): molti wrfout già cancellati sono tornati su tape.
4. Il resto mai iniziato (buco 2024, 2025 H2, 2019 completo) con `hpc/run_2024_fill.sh`.

Gli stop flag di `fill2024` sono tutti presenti: vanno rimossi solo al punto 4, e
`PHASES_ONLY` resta obbligatorio (vedi `CLAUDE.md`).

## 6. Decisioni chiuse e ancora aperte

Chiuse in questa sessione: 13 livelli di pressione; `10efg`/`10nfg` e TKE fuori; `cp`/`csf`
fuori perché morte; vegetazione separata alta/bassa; `fal` con bitmap di notte; `cvl`/`cvh` da
`VEGFRA` orario; wind shear bulk 10→100 m. **`geo_em_d02` è irrecuperabile** (già chiesto a
LRZ): il land cover frazionario esce definitivamente dalle cose ottenibili.

Ancora aperte:

1. `MISSING_VARIABLES.pdf` è da sottoporre ai colleghi.
2. `mucape`/`mucin`: i punti indefiniti sono scritti come 0 (non come mancanti) per tenere i
   campi densi. Da confermare con chi userà i dati.
3. `tsn` è mascherata dove la neve copre più di metà cella (`SNOWC > 0.5`). Con la soglia più
   larga `SNOW > 0` un quarto dei punti restituiva la temperatura del suolo, non della neve.
4. **Nessun wrfout va cancellato** finché l'utente non lo dice: `wrfout_share` deve ancora essere
   copiato dal collega, e la cancellazione di `wrfout_2024fill` è sospesa. Sono 37 TB.
