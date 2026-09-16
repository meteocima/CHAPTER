# Handoff — nuove variabili nei GRIB CHAPTER

Scritto il 2026-09-16, aggiornato lo stesso giorno a lavoro di codice completato.

**Stato: lo schema è implementato e testato su singolo file. La campagna di ri-conversione
NON è partita e non deve partire senza via esplicito.**

---

## 1. Cosa è cambiato

Lo schema è passato da **21 variabili / 93 messaggi in GRIB1** a **62 variabili / 182 messaggi
in GRIB2**. Nessuna variabile precedente è stata tolta.

Il passaggio a GRIB2 non è estetico: `2r`, `tirf`, `mucape`, `mucin` e `wz` **non esistono in
GRIB1**, e GRIB1 non sa dichiarare la sfera su cui WRF integra (vedi §4).

Nuove: `tirf`, `2r`, `10fg`, `100u/100v`, `200u/200v`, `vwsh`, `hcc/mcc/lcc`, `mucape/mucin`,
`ssrd`, `tsr`, `r`, `clwc`, `ciwc`, `w` (ω) e `wz` sui livelli, `sst`, `ci`, e il land-surface
ERA5 (`swvl1-4`, `stl1-4`, `sd`, `rsn`, `sf`, `src`, `sro`, `ssro`, `cvl`, `lai_lv`, `tvl`,
`slt`, `zust`, `fsr`).

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

## 4. Costi misurati (1 core DCGP, 2024-07-01 14Z)

| | prima | ora |
|---|---|---|
| messaggi | 93 | **182** |
| dimensione | 388 MB | **~663 MB** |
| tempo | ~7,5 min | **~3 min** (`grid_ccsds` comprime meglio ed è molto più veloce di `grid_second_order`) |
| picco RAM | — | **18,2 GB** → `slurm.step_convert_mem` alzato a 32G (la RAM non è fatturata su DCGP) |

## 5. Come far ripartire la pipeline (SOLO dopo il via)

L'output va in un albero **nuovo**, `grib_v2/` (già impostato in `conf/pipeline.yaml`): la
re-entrancy di `convert_step.sh` si basa sull'esistenza del GRIB di output, quindi scrivere lo
schema nuovo dentro `grib/` salterebbe in silenzio ogni ora già convertita. `grib/` si cancella
a validazione finita.

Ordine consigliato:

1. **4056 ore già su disco** (`wrfout_share` 2019 + 2024) — solo CPU, nessun transfer.
   Si riusa `hpc/run_share_conversion.sh` (catene convert-only, `keep_wrfout=true`, gate 48).
2. **324 ore** di `wrfout_2024fill` (2024-03-18..03-31), mai convertite.
3. **8424 ore da ri-scaricare** (~77 TB, ~5 giorni di datamover) a blocchi mensili.
   **Prima serve uno scan/recall da nastro su LRZ** (`hpc/lrz/chapter_scan.sh`, poi
   `chapter_recall.sh` mese per mese): molti wrfout già cancellati sono tornati su tape.
4. Il resto mai iniziato (buco 2024, 2025 H2, 2019 completo) con `hpc/run_2024_fill.sh`.

Gli stop flag di `fill2024` sono tutti presenti: vanno rimossi solo al punto 4, e
`PHASES_ONLY` resta obbligatorio (vedi `CLAUDE.md`).

## 6. Decisioni ancora aperte

1. `MISSING_VARIABLES.pdf` è da sottoporre ai colleghi: ne possono uscire richieste nuove
   (in particolare i `geo_em_d02` da LRZ per il land-use frazionario, e se TKE è un requisito
   vero — nel qual caso serve rifare il run WRF, non riprocessarne l'output).
2. **Wind shear**: implementato come bulk 10 m → 100 m (`vwsh`, s⁻¹). Se serve un'altra
   definizione va cambiata **prima** della campagna.
3. `mucape`/`mucin`: i punti indefiniti sono scritti come 0 (non come mancanti) per tenere i
   campi densi. Da confermare con chi userà i dati.
4. `wrfout_share` sono 34 TB fermi per un collega: liberarli è l'unica leva di spazio reale, ma
   sono anche 4056 ore riconvertibili gratis. Decidere dopo il punto 1.
