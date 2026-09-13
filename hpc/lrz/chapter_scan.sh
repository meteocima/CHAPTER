#!/bin/bash
# CHAPTER su LRZ: scansiona una finestra di date e classifica ogni timestep in
#   ONLINE   file su disco, scaricabile subito
#   OFFLINE  migrato su tape -> va richiamato con chapter_recall.sh
#   ASSENTE  non esiste alla sorgente: NON e' un caso di tape, serve un ticket LRZ
# Sola lettura: non richiama e non modifica nulla.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/chapter_common.sh"

usage() {
    cat <<'EOF'
Uso: chapter_scan.sh -s <inizio> -e <fine> [-o <outdir>]
     chapter_scan.sh -l <lista_path_wrfout> [-o <outdir>]

  -s, --start   data di inizio  (YYYY-MM-DD | DD/MM/YYYY | DD-MM-YYYY | DD.MM.YYYY)
  -e, --end     data di fine    (inclusa)
  -o, --outdir  cartella risultati (default: /dss/dsshome1/0B/di54coy/call_2019)
  -l, --list    scansiona questi file (un path wrfout per riga) invece di una finestra

Esempio:  ./chapter_scan.sh -s 17/06/2019 -e 06/09/2019
EOF
}

parse_common_args "$@"
[ -n "$MMLSATTR" ] || {
    echo "ERRORE: mmlsattr non trovato; senza non si distingue OFFLINE da ONLINE." >&2
    echo "        Esegui su un nodo LRZ dove il container DSS e' montato." >&2
    exit 1
}

ALL="${OUTDIR}/scan_${TAG}_all.txt"
OFF="${OUTDIR}/scan_${TAG}_offline.txt"     # <- e' gia' la stagelist per dsacli -l
ABS="${OUTDIR}/scan_${TAG}_absent.txt"
ON="${OUTDIR}/scan_${TAG}_online.txt"
REP="${OUTDIR}/scan_${TAG}_report.tsv"
SUM="${OUTDIR}/scan_${TAG}_summary.txt"

if [ -n "$LIST" ] && [ -z "$START" ]; then
    grep -v '^\s*\(#\|$\)' "$LIST" > "$ALL"
    TOT=$(wc -l < "$ALL")
    echo "Lista ${LIST}  ->  ${TOT} file"
else
    expand_window "$START" "$END" > "$ALL"
    TOT=$(wc -l < "$ALL")
    echo "Finestra ${START} .. ${END}  ->  ${TOT} timestep"
fi
echo "Scansione in corso (mmlsattr su ogni file, puo' richiedere qualche minuto)..."

: > "$OFF"; : > "$ABS"; : > "$ON"
printf 'stato\tbytes\tpath\n' > "$REP"

n=0
while IFS= read -r f; do
    n=$((n + 1))
    if [ ! -e "$f" ]; then
        echo "$f" >> "$ABS"; printf 'ASSENTE\t0\t%s\n' "$f" >> "$REP"
    else
        sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
        if "$MMLSATTR" -L "$f" 2>/dev/null | grep -q 'OFFLINE'; then
            echo "$f" >> "$OFF"; printf 'OFFLINE\t%s\t%s\n' "$sz" "$f" >> "$REP"
        else
            echo "$f" >> "$ON";  printf 'ONLINE\t%s\t%s\n'  "$sz" "$f" >> "$REP"
        fi
    fi
    [ $((n % 100)) -eq 0 ] && echo "  ... $n/$TOT" >&2
done < "$ALL"

nOFF=$(wc -l < "$OFF"); nABS=$(wc -l < "$ABS"); nON=$(wc -l < "$ON")
TB=$(awk -v n="$nOFF" -v g="$GB_PER_FILE" 'BEGIN{printf "%.2f", n*g/1000}')
{
    echo "CHAPTER scan  ${START:-lista} .. ${END:-${TAG}}   ($(date -u +%FT%TZ))"
    echo "totale timestep : ${TOT}"
    echo "ONLINE          : ${nON}    (gia' su disco, scaricabili subito)"
    echo "OFFLINE         : ${nOFF}   (su tape, ~${TB} TB -> chapter_recall.sh)"
    echo "ASSENTI         : ${nABS}   (non esistono: NON e' tape, serve ticket LRZ)"
    echo
    echo "stagelist per il recall : ${OFF}"
    echo "elenco assenti          : ${ABS}"
    echo "dettaglio per file      : ${REP}"
} | tee "$SUM"
