#!/bin/bash
# Helper condivisi per gli script CHAPTER su LRZ. Va "source"-ato, non eseguito.
#
# Copiare l'intera cartella su LRZ (di norma /dss/dsshome1/0B/di54coy/call_scripts):
#   chapter_common.sh  chapter_scan.sh  chapter_recall.sh
# Bash puro: su LRZ non c'e' modo di crearsi un env python.

BASE_2023="${BASE_2023:-/dss/dsafs01/0001/pn29co-dss-0000/CHAPTER-23-25}"
BASE_PRE2023="${BASE_PRE2023:-/dss/dsafs01/0001/pn29co-dss-0000/CHAPTER}"
DSA_CONTAINER="${DSA_CONTAINER:-pn29co-dss-0000}"   # nome DSS, NON il fileset pn29co-dsa-0000
INIT_HOUR="${INIT_HOUR:-18}"
OUTDIR="${OUTDIR:-/dss/dsshome1/0B/di54coy/call_2019}"

# ~9.14 GB per wrfout CHAPTER (misurato): serve solo a stimare il volume di uno stage.
GB_PER_FILE="${GB_PER_FILE:-9.139353544}"

# mmlsattr non e' sempre sul PATH
MMLSATTR=""
for _c in /usr/lpp/mmfs/bin/mmlsattr mmlsattr; do
    command -v "$_c" >/dev/null 2>&1 && { MMLSATTR="$_c"; break; }
done

# Accetta YYYY-MM-DD | DD/MM/YYYY | DD-MM-YYYY | DD.MM.YYYY -> stampa YYYY-MM-DD.
# Discrimina sul primo campo: 4 cifre = anno in testa, altrimenti giorno in testa.
norm_date() {
    local s="${1//\//-}"; s="${s//./-}"
    local a b c
    IFS='-' read -r a b c <<< "$s"
    if [ -z "${c:-}" ]; then
        echo "ERRORE: data non riconosciuta: $1  (usa YYYY-MM-DD o DD/MM/YYYY)" >&2; return 1
    fi
    local out
    if [ ${#a} -eq 4 ]; then
        out=$(printf '%04d-%02d-%02d' "$((10#$a))" "$((10#$b))" "$((10#$c))")
    else
        out=$(printf '%04d-%02d-%02d' "$((10#$c))" "$((10#$b))" "$((10#$a))")
    fi
    # date -d accetta "2019-02-31" normalizzandola a marzo: confronto per rifiutarla.
    if [ "$(date -u -d "$out" +%Y-%m-%d 2>/dev/null)" != "$out" ]; then
        echo "ERRORE: data inesistente: $1 (letta come $out)" >&2; return 1
    fi
    echo "$out"
}

# Base DSS corretta per l'anno del giorno TARGET (non dell'init).
# Caso limite: 2023-01-01 sta in CHAPTER-23-25 ma nella init-dir 2022123118.
base_for_day() { [ "${1:0:4}" -ge 2023 ] && echo "$BASE_2023" || echo "$BASE_PRE2023"; }

# Espande [start,end] in path assoluti DSS, 24 timestep per giorno, uno per riga.
# Il run WRF si inizializza alle INIT_HOUR Z del giorno PRECEDENTE: 2019-06-17 -> 2019061618.
# Aritmetica in epoch UTC: "date -d '<data> +1 hour'" verrebbe mal interpretata (+1 letto come TZ).
expand_window() {
    local cur end d base init h
    cur=$(date -u -d "$1" +%s); end=$(date -u -d "$2" +%s)
    while [ "$cur" -le "$end" ]; do
        d=$(date -u -d "@$cur" +%Y-%m-%d)
        base=$(base_for_day "$d")
        init=$(date -u -d "@$((cur - 86400))" +%Y%m%d)$(printf '%02d' "$((10#$INIT_HOUR))")
        for h in $(seq -w 0 23); do
            echo "${base}/${init}/wrfout_d02_${d}_${h}:00:00"
        done
        cur=$((cur + 86400))
    done
}

# Parsing comune. Popola START END OUTDIR RUN LIST ALLWIN.
START=""; END=""; RUN=0; LIST=""; ALLWIN=0
parse_common_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -s|--start)   START=$(norm_date "$2") || exit 1; shift 2 ;;
            -e|--end)     END=$(norm_date "$2")   || exit 1; shift 2 ;;
            -o|--outdir)  OUTDIR="$2"; shift 2 ;;
            -l|--list)    LIST="$2"; shift 2 ;;
            --run)        RUN=1; shift ;;
            --all-window) ALLWIN=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *) echo "Opzione sconosciuta: $1" >&2; usage; exit 1 ;;
        esac
    done
    # Con -l la lista stessa definisce i file: -s/-e diventano facoltativi.
    if [ -n "$LIST" ] && [ -z "$START" ] && [ -z "$END" ]; then
        [ -f "$LIST" ] || { echo "ERRORE: lista inesistente: $LIST" >&2; exit 1; }
        TAG="$(basename "$LIST" .txt)"
        mkdir -p "$OUTDIR"
        return 0
    fi
    if [ -z "$START" ] || [ -z "$END" ]; then
        echo "ERRORE: servono -s <inizio> e -e <fine> (oppure -l <lista>)." >&2; usage; exit 1
    fi
    TAG="${START}_${END}"
    if [ "$(date -u -d "$START" +%s)" -gt "$(date -u -d "$END" +%s)" ]; then
        echo "ERRORE: inizio ($START) successivo alla fine ($END)." >&2; exit 1
    fi
    mkdir -p "$OUTDIR"
}
