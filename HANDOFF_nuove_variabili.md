# Handoff — aggiungere variabili al converter CHAPTER

Scritto il 2026-09-16. Da leggere nella chat in cui si implementano le nuove variabili.
La pipeline di download/conversione del 2024 è **ferma apposta** in attesa di questo lavoro:
finché non si sa quali variabili servono, ogni GRIB prodotto andrebbe rifatto.

---

## 1. Perché la pipeline è ferma

I GRIB si producono da wrfout da ~9,14 GB l'uno, scaricati da LRZ attraverso il datamover
CINECA a ~71 file/h. Un wrfout convertito veniva cancellato subito: il GRIB pesa 410 MB
contro 9 GB, e la quota di progetto è 100 TB condivisi.

Il 2026-09-16 è emerso che potrebbero servire **più variabili** di quelle prodotte ora.
Da quel momento `KEEP_WRFOUT=true` (commit `0b00dd9`): i wrfout restano su disco. Ma le
fasi già completate avevano già cancellato i loro, e sono le ore elencate sotto come
"da ri-scaricare".

**La cosa importante da capire prima di progettare qualsiasi cosa: il collo di bottiglia
non è la CPU, è il transfer.** Riconvertire da un wrfout già su disco costa ~5 minuti di
1 core DCGP. Riconvertire da un wrfout da ri-scaricare costa ~50 minuti di datamover.
Quindi: **decidere TUTTE le variabili in una volta sola** e fare una sola passata.

---

## 2. Stato dei dati al 2026-09-16

### GRIB già prodotti (tutti con lo schema di variabili attuale)

```
2019   1968 / 8760    (solo 2019-06-17..09-06)
2024   6168 / 8784    (mancano marzo, aprile, maggio, 1-17 giugno)
2025   4344 / 8760    (gennaio-giugno)
```

Tutti verificati con `hpc/check_grib_sanity.py`: `bad=0`.

### wrfout grezzi ancora su disco (la materia prima disponibile *senza* ri-scaricare)

```
wrfout_share/     2019-06-17..09-06     1968 ore   18,0 TB
wrfout_share/     2024-06-18..09-12     2088 ore   19,1 TB
wrfout_2024fill/  2024-03-01..03-18     ~330 ore    3,0 TB   (parziale, download interrotto)
```

`wrfout_share` era stato messo da parte per un collega; i file sono di sola lettura ma
integri e già validati. **Non cancellarli**: sono 4056 ore riconvertibili a costo quasi zero.

### wrfout da ri-scaricare (cancellati o mai presi)

```
2024-01-01..02-29            1440 ore   13,2 TB   cancellati (conversione già fatta)
2024-09-13..10-25            1032 ore    9,4 TB   cancellati (conversione già fatta)
2024-10-26..12-31            1608 ore   14,7 TB   cancellati (run precedenti)
2024-03-18..06-17            ~2280 ore  20,8 TB   mai scaricati
2025-01-01..06-30            4344 ore   39,7 TB   cancellati (run precedenti)
2019 fuori dalla finestra    6792 ore   62,1 TB   mai scaricati
```

### Vincolo di quota (decisivo)

Quota progetto: **100 TB**, oggi ~46 TB usati (34 dei quali sono `wrfout_share`).
Un anno intero di wrfout sono **~80 TB**. Non è possibile tenere in linea più di
~5000-6000 ore per volta. Qualunque piano che assuma "tengo tutti i wrfout di 2019+2024
e poi riconverto con calma" **non sta nella quota**: va fatto a blocchi mensili,
scarica → converti → cancella, con lo schema di variabili già definitivo.

---

## 3. Dove si aggiungono le variabili

Due file, sempre entrambi.

### `wrf_era5_comparison.py` — il dizionario `WRF_TO_ECMWF_PARAMID` (riga 36)

È la lista di cosa finisce nel GRIB. Chiave = nome WRF nativo (`T2`, `U`, `RAINNC`) oppure
nome di una variabile derivata (`tk`, `q`, `slp`, `tcw`, `slor`, `skt`, `tqv`, `tcc`).

```python
'T2': {'shortName': '2t', 'paramId': 167, 'long_name': '2m Temperature', 'units': 'K'},
```

**Buona notizia**: molte variabili sono già scritte e solo **commentate**, disattivate nel
2026-06 perché non richieste da nessuna colonna MeteoSwiss. Se servono, spesso basta
togliere il `#`:

| WRF | shortName | paramId | tipo | nota |
|---|---|---|---|---|
| `CLDFRA` | cc | 248 | livelli | cloud fraction per livello |
| `ACLWDNB` | strd | 175 | surface | LW down accumulata — **vedi §5, è accumulata** |
| `ACSWDNB` | ssrd | 169 | surface | SW down accumulata — **idem** |
| `SST` | sst | 34 | surface | c'è già il codice di mascheramento oceano |
| `SEAICE` | ci | 31 | surface | |
| `ISLTYP` / `IVGTYP` | slt / tvl | 43 / 29 | surface | categorie |
| `Q2` | q | 133 | 2 m | conversione mixing ratio → specifica già scritta |
| `QCLOUD/QICE/QRAIN/QSNOW` | clwc/ciwc/crwc/cswc | 246/247/75/76 | livelli | |
| `SMOIS` / `TSLB` | swvl1 / stl1 | 39 / 139 | suolo | **attenzione: hanno dimensione `soil_layers_stag`, non gestita** |
| `SNOW` / `SNOWH` | sf / sd | 228144 / 228141 | surface | |
| `theta` | pt | 3 | livelli | derivata — va anche rimessa in `derived_3d` |
| `rh` | r | 157 | livelli | derivata — idem |
| `pvo` | pv | 60 | livelli | derivata — idem |

Il contesto delle richieste è in `meteoswiss_variable_comparison.md` (le 4 colonne
ERA5 / Training MeteoSwiss / recipe COSMO). Vale la pena rileggerlo prima di scegliere:
dice quale lista è il riferimento e cosa manca a ciascuna.

### `convert_to_pressure_levels.py` — come la variabile viene calcolata

Tre percorsi distinti:

**a) Variabile WRF nativa** — nessun codice da scrivere. Il loop alla riga 164 itera su
`ncfile.variables`, e se il nome è nel dizionario la prende. Decide da solo:
- ha `bottom_top` / `bottom_top_stag` → destaggering (riga 186) + `wrf.vinterp` sui 13
  livelli di pressione (riga 197);
- altrimenti → copia 2D diretta.

**b) Variabile nativa con conversione di unità** — un `elif` nel blocco alle righe 214-243.
Esempi già presenti: `HGT` × g → geopotenziale, `VAR_SSO` → radice → deviazione standard,
`Q2` mixing ratio → umidità specifica, `RAINNC` → tp riferita alle 00Z.

**c) Variabile derivata** — due liste più i blocchi ad hoc:
- `derived_3d = ['tk', 'z']` (riga 254): nomi che `wrf.getvar` sa calcolare, interpolati
  sui livelli di pressione;
- `derived_2d = ['td2', 'slp']` (riga 285);
- calcoli su misura più sotto: `q` (riga ~341), `tcw` (~367), `tqv` (~398), `tcc` (~413),
  `skt` da `LWUPB` (~440), `slor` da `HGT` (~452). Il pattern è sempre lo stesso: calcola
  e assegna `output_vars['nome'] = array`.

L'encoding GRIB (riga ~487 in poi) è **generico**: guarda `len(shape)` e decide se scrivere
13 messaggi isobarici (`indicatorOfTypeOfLevel=100`) o un solo messaggio surface. Non serve
toccarlo per aggiungere una variabile, **a meno che** non serva un tipo di livello nuovo
(suolo, altezza fissa diversa da 2/10 m): in quel caso è lì che va messo il ramo.

---

## 4. Come si testa

C'è un wrfout locale su cui provare senza toccare niente:

```bash
cd /leonardo/home/userexternal/lmonaco0/CHAPTER
W=/leonardo_work/AIFPT_AILAMIT/CHAPTER
uv run python convert_to_pressure_levels.py \
  --input $W/wrfout_share/2024-07-01/wrfout_d02_2024-07-01_12:00:00 \
  --output /tmp/test.grib \
  --debug-vars <NOME_VAR>
```

`--debug-vars` limita la conversione alle variabili elencate: gira in ~5 s invece di ~5 min,
ed è il modo giusto per iterare. Senza, il file completo sono 149 messaggi / ~410 MB.

Per ispezionare il risultato servono i `grib_*`, che non sono sul PATH:
```bash
module load eccodes/2.34.0--gcc--12.2.0
grib_ls /tmp/test.grib
grib_dump -p shortName,paramId,level,indicatorOfTypeOfLevel /tmp/test.grib | head -40
```

Non esiste una suite di test: la verifica è questa, più `hpc/check_grib_sanity.py`.

---

## 5. Regole del dominio da non violare

- **Livelli**: 13 isobarici, `PRESSURE_LEVELS` a riga 27 (1000→50 hPa). Cambiarli invalida
  tutti i GRIB già prodotti: se serve un livello in più, va rifatto **tutto**.
- **GRIB1 tabella 128**, `indicatorOfParameter` = il paramId ECMWF. Attenzione: i paramId a
  6 cifre (`228143`, `228144`, `500014`) **non entrano** in un campo GRIB1 a 8 bit. Le voci
  del dizionario che li hanno sono commentate anche per questo: se una di quelle serve
  davvero, il problema va risolto (paramId alternativo o passaggio a GRIB2), non ignorato.
- **Campi accumulati**: WRF accumula dall'init del run (18Z del giorno prima, 6 h di spinup).
  La convenzione CHAPTER è **riferire tutto alle 00Z dello stesso giorno**. Se si riattiva
  una variabile accumulata (`ACSWDNB`, `ACLWDNB`, `ACHFX`, `ACLHF`) va aggiunta a
  `accum_ref.ACCUMULATED_VARS` **e** al sidecar, altrimenti esce un campo riferito all'init
  e silenziosamente sbagliato. I sidecar esistenti (`accum_ref/YYYY/MM/*.npz`) contengono
  solo le variabili attive al momento in cui sono stati scritti: **aggiungerne una obbliga a
  rigenerare i sidecar dal wrfout 00Z**, quindi serve il 00Z di ogni giorno su disco.
- **La tp corretta ha `generatingProcessIdentifier=128`** (127 = vecchia, riferita all'init).
  `check_grib_sanity.py` lo verifica, e verifica anche che tp sia esattamente 0 alle 00Z.
- **Mascheramento oceano**: `SST` e sea-ice usano `LANDMASK` (già caricata, riga 105).
- Il `check_grib_sanity.py` controlla che i campi statici `lsm z sdor slor skt` non siano
  tutti a zero: se si aggiungono altri campi statici conviene estendere quel set.

---

## 6. Quando le variabili sono pronte: far ripartire la pipeline

Lo stato è congelato con degli stop flag. Per ripartire:

```bash
W=/leonardo_work/AIFPT_AILAMIT/CHAPTER
rm -f $W/logs/fill2024_sequence.stop $W/logs/fill2024_*_dl.stop $W/logs/fill2024_*_cv.stop
cd /leonardo/home/userexternal/lmonaco0/CHAPTER
PHASES_ONLY="p3_mar p4_apr p5_may p6_jun" bash hpc/run_2024_fill.sh
```

**`PHASES_ONLY` non è opzionale.** La re-entrancy del download si basa sul wrfout in
staging (`SKIP_RAW_EXISTS`), non sul GRIB: le fasi `p0_sepoct`, `p1_jan`, `p2_feb` hanno già
cancellato i loro wrfout, quindi senza il filtro verrebbero ri-scaricate per intero
(2472 file, 22,6 TB) senza che nessuno se ne accorga.

Da eseguire **da un login node normale** (il datamover non è raggiungibile da
`lrd_all_serial`), e la catena vive su quel nodo: la liveness si controlla con
`find <driver_log> -mmin +25`, **mai** con `pgrep`.

Il resto del contesto operativo (log, ledger, stop, cosa fare se una catena muore) è in
`logs/fill2024_HANDOFF.md`. Le regole generali della pipeline sono in `CLAUDE.md`.

---

## 7. Decisioni ancora aperte

1. **Quali variabili** — è il blocco vero. Serve la lista definitiva prima di riprendere.
2. **Riconvertire i GRIB già fatti?** Le 6168 ore del 2024 + 4344 del 2025 + 1968 del 2019
   hanno lo schema vecchio. Se le nuove variabili servono su tutto l'archivio, vanno rifatte:
   4056 di quelle ore hanno il wrfout su disco (costo: solo CPU), le altre vanno ri-scaricate.
3. **`wrfout_share` si può liberare?** Sono 34 TB fermi lì per un collega. Liberarli è
   l'unica leva realistica per avere spazio di manovra — ma sono anche 4056 ore
   riconvertibili gratis. Da decidere *dopo* aver fissato le variabili, non prima.
4. **Il 2019 e il resto del 2025** non sono nemmeno iniziati: 62 TB e 39 TB di transfer.
   Vale la pena pianificarli con lo schema nuovo già a posto, non prima.
