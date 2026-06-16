#!/bin/bash
# Fetch a range of daily wrfout files from SuperMUC via rsync.
# Each target date pulls from its own init folder (previous day at init_hour Z).
#
# Usage:
#   ./hpc/fetch_month.sh <start-date> <end-date>
#   ./hpc/fetch_month.sh 2025-04-01 2025-04-30
#
# Requires an active SSH ControlMaster to the supermuc host.

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <start-date YYYY-MM-DD> <end-date YYYY-MM-DD>"
    exit 1
fi

START="$1"
END="$2"

SUPERMUC_HOST="${SUPERMUC_HOST:-supermuc}"
SSH_SOCKET="${SSH_SOCKET:-/tmp/skt-di54coy}"
WORK_DIR="${WORK_DIR:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
BASE_2023="${BASE_2023:-/dss/dsafs01/0001/pn29co-dss-0000/CHAPTER-23-25}"
BASE_PRE2023="${BASE_PRE2023:-/dss/dsafs01/0001/pn29co-dss-0000/CHAPTER}"
INIT_HOUR="${INIT_HOUR:-18}"

# Verify SSH ControlMaster is active
if ! ssh -S "${SSH_SOCKET}" -O check "${SUPERMUC_HOST}" 2>/dev/null; then
    echo "ERROR: SSH ControlMaster socket not active at ${SSH_SOCKET}."
    echo "Activate it first (e.g. in tmux): ssh -fNM -S ${SSH_SOCKET} ${SUPERMUC_HOST}"
    exit 1
fi

CURRENT="$START"
while [[ "$CURRENT" < "$END" || "$CURRENT" == "$END" ]]; do
    YEAR=$(date -d "$CURRENT" +%Y)
    INIT=$(date -d "$CURRENT -1 day" +%Y%m%d)$(printf "%02d" "$INIT_HOUR")

    if [ "$YEAR" -ge 2023 ]; then
        BASE="$BASE_2023"
    else
        BASE="$BASE_PRE2023"
    fi

    LOCAL_DIR="${WORK_DIR}/wrfout/${CURRENT}"
    REMOTE_PATH="${BASE}/${INIT}"

    echo "=== ${CURRENT}  <-  ${SUPERMUC_HOST}:${REMOTE_PATH} ==="
    mkdir -p "$LOCAL_DIR"

    for h in 00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23; do
        FNAME="wrfout_d02_${CURRENT}_${h}:00:00"
        LOCAL_FILE="${LOCAL_DIR}/${FNAME}"

        if [ -s "$LOCAL_FILE" ]; then
            echo "  skip ${h}:00 (exists)"
            continue
        fi

        echo "  fetch ${h}:00"
        if ! rsync -avh --no-compress --progress \
                --partial --partial-dir=.rsync-partial \
                --timeout=120 \
                -e "ssh -S ${SSH_SOCKET}" \
                "${SUPERMUC_HOST}:${REMOTE_PATH}/${FNAME}" \
                "${LOCAL_FILE}"; then
            echo "  WARN: rsync failed for ${FNAME} (will retry on next run)"
        fi
    done

    COUNT=$(find "$LOCAL_DIR" -maxdepth 1 -name "wrfout_d02_${CURRENT}_*" -type f | wc -l)
    echo "  fetched: ${COUNT}/24"
    echo ""

    CURRENT=$(date -d "$CURRENT +1 day" +%Y-%m-%d)
done

echo "Done."
