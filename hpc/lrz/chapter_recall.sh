#!/bin/bash
# CHAPTER su LRZ: sottomette un job DSA di stage (recall da tape) per una finestra di date.
# Di default NON lancia nulla: stampa il comando. Serve --run per eseguirlo davvero
# (uno stage puo' valere decine di TB: non e' una cosa da far partire per sbaglio).
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/chapter_common.sh"

usage() {
    cat <<'EOF'
Uso: chapter_recall.sh -s <inizio> -e <fine> [-o <outdir>] [-l <stagelist>] [--all-window] [--run]

  -s, --start     data di inizio  (YYYY-MM-DD | DD/MM/YYYY | DD-MM-YYYY | DD.MM.YYYY)
  -e, --end       data di fine    (inclusa)
  -o, --outdir    cartella risultati (default: /dss/dsshome1/0B/di54coy/call_2019)
  -l, --list      usa questa stagelist invece dell'output dello scan
      --all-window  richiama TUTTA la finestra senza scan (rimette in coda anche
                    cio' che e' gia' su disco: usare solo se mmlsattr non e' disponibile)
      --run       sottomette davvero il job DSA (senza, e' un dry run)

Lo scan si fa UNA volta su una finestra larga, il recall si fa a pezzi: se non trova lo
scan con lo stesso identico intervallo, cerca in outdir lo scan piu' stretto che CONTIENE
la finestra chiesta e lo ritaglia da solo. Quindi:

  ./chapter_scan.sh   -s 2019-01-01 -e 2019-12-31      # una volta, tutto l'anno
  ./chapter_recall.sh -s 2019-01-01 -e 2019-01-31      # mese per mese, dry run
  ./chapter_recall.sh -s 2019-01-01 -e 2019-01-31 --run
EOF
}

parse_common_args "$@"

# Scan che COPRE [START,END] anche con un TAG diverso (tipicamente l'anno intero).
# Stampa il path del piu' stretto fra quelli che la contengono; niente = nessuno.
find_covering_scan() {
    local f b s e span best="" best_span=0 want_s want_e
    want_s=$(date -u -d "$START" +%s); want_e=$(date -u -d "$END" +%s)
    for f in "${OUTDIR}"/scan_*_offline.txt; do
        [ -f "$f" ] || continue
        b=$(basename "$f")
        # solo gli scan "a finestra": quelli fatti con -l hanno un TAG non-data
        [[ "$b" =~ ^scan_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{4}-[0-9]{2}-[0-9]{2})_offline\.txt$ ]] || continue
        s=$(date -u -d "${BASH_REMATCH[1]}" +%s); e=$(date -u -d "${BASH_REMATCH[2]}" +%s)
        { [ "$s" -le "$want_s" ] && [ "$e" -ge "$want_e" ]; } || continue
        span=$((e - s))
        if [ -z "$best" ] || [ "$span" -lt "$best_span" ]; then best="$f"; best_span="$span"; fi
    done
    # sempre exit 0: sotto `set -e` un return!=0 qui ucciderebbe lo script invece
    # di far scattare il messaggio d'errore piu' sotto.
    printf '%s' "$best"
}

# Tiene le righe la cui data TARGET (quella nel nome del wrfout, non la init-dir) e' in
# [START,END]. Le date YYYY-MM-DD si confrontano come stringhe, niente aritmetica.
filter_window() {
    awk -v s="$START" -v e="$END" '
        match($0, /wrfout_d02_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_/) {
            d = substr($0, RSTART + 11, 10)
            if (d >= s && d <= e) print
        }' "$1"
}

# La stagelist e' l'elenco OFFLINE prodotto dallo scan: solo cio' che serve davvero.
if [ -z "$LIST" ]; then
    if [ "$ALLWIN" -eq 1 ]; then
        LIST="${OUTDIR}/recall_${TAG}_allwindow.txt"
        expand_window "$START" "$END" > "$LIST"
        echo "--all-window: richiamo l'intera finestra (nessuno scan)."
    else
        LIST="${OUTDIR}/scan_${TAG}_offline.txt"
        if [ ! -f "$LIST" ]; then
            SRC=$(find_covering_scan)
            if [ -z "$SRC" ]; then
                echo "Nessuno scan che copra ${START}..${END} trovato in ${OUTDIR}." >&2
                echo "Esegui prima:  ./chapter_scan.sh -s ${START} -e ${END} -o ${OUTDIR}" >&2
                echo "(va bene anche una finestra piu' larga: viene ritagliata da sola)" >&2
                echo "oppure passa una lista con -l, oppure usa --all-window." >&2
                exit 1
            fi
            LIST="${OUTDIR}/recall_${TAG}_offline.txt"
            filter_window "$SRC" > "$LIST"
            echo "Scan esatto assente -> uso $(basename "$SRC") ritagliato su ${START}..${END}:"
            echo "  $(wc -l < "$LIST") file OFFLINE su $(wc -l < "$SRC") dello scan"
        fi
    fi
fi

[ -f "$LIST" ] || { echo "ERRORE: stagelist inesistente: $LIST" >&2; exit 1; }
N=$(wc -l < "$LIST")
[ "$N" -gt 0 ] || { echo "Stagelist vuota (${LIST}): nulla da richiamare, la finestra e' gia' tutta su disco."; exit 0; }

TB=$(awk -v n="$N" -v g="$GB_PER_FILE" 'BEGIN{printf "%.2f", n*g/1000}')
echo "Stagelist : ${LIST}"
echo "Container : ${DSA_CONTAINER}"
echo "File      : ${N}   (~${TB} TB da rimettere su disco)"

CMD=(dsacli stage job create --dsacontainer "$DSA_CONTAINER" -l "$LIST" -n)
if [ "$RUN" -eq 1 ]; then
    LOG="${OUTDIR}/recall_${TAG}_job.txt"
    echo "+ ${CMD[*]}"
    "${CMD[@]}" 2>&1 | tee "$LOG"
    echo
    echo "Output del job salvato in ${LOG}"
    echo "Segui con:  dsacli stage job list   |   dsacli stage job show <job_id>"
else
    echo
    echo "DRY RUN - non e' stato sottomesso nulla. Per lanciare:"
    echo "  ${CMD[*]}"
    echo "oppure rilancia questo script con --run"
fi
