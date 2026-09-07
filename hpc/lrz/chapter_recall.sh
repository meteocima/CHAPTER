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

Flusso normale:
  ./chapter_scan.sh   -s 17/06/2019 -e 06/09/2019         # trova cosa e' su tape
  ./chapter_recall.sh -s 17/06/2019 -e 06/09/2019         # mostra il comando
  ./chapter_recall.sh -s 17/06/2019 -e 06/09/2019 --run   # lo esegue
EOF
}

parse_common_args "$@"
TAG="${START}_${END}"

# La stagelist e' l'elenco OFFLINE prodotto dallo scan: solo cio' che serve davvero.
if [ -z "$LIST" ]; then
    if [ "$ALLWIN" -eq 1 ]; then
        LIST="${OUTDIR}/recall_${TAG}_allwindow.txt"
        expand_window "$START" "$END" > "$LIST"
        echo "--all-window: richiamo l'intera finestra (nessuno scan)."
    else
        LIST="${OUTDIR}/scan_${TAG}_offline.txt"
        if [ ! -f "$LIST" ]; then
            echo "Nessuno scan trovato in ${LIST}." >&2
            echo "Esegui prima:  ./chapter_scan.sh -s ${START} -e ${END} -o ${OUTDIR}" >&2
            echo "oppure passa una lista con -l, oppure usa --all-window." >&2
            exit 1
        fi
    fi
fi

[ -f "$LIST" ] || { echo "ERRORE: stagelist inesistente: $LIST" >&2; exit 1; }
N=$(wc -l < "$LIST")
[ "$N" -gt 0 ] || { echo "Stagelist vuota (${LIST}): nulla da richiamare."; exit 0; }

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
