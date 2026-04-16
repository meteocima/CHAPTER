#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --job-name=chapter_fetch
#
# Fetch all 24 hourly wrfout files for a single target date from SuperMUC.
#
# Required env vars (set via --export at submission):
#   TARGET_DATE   - target date in YYYY-MM-DD format
#   REMOTE_PATH   - full path to run folder on SuperMUC
#   LOCAL_DIR     - local directory to store wrfout files
#   SSH_SOCKET    - path to pre-activated SSH control socket
#   SUPERMUC_HOST - remote hostname (default: supermuc)

set -euo pipefail

SUPERMUC_HOST="${SUPERMUC_HOST:-supermuc}"

echo "=== CHAPTER fetch_day ==="
echo "Target date:  ${TARGET_DATE}"
echo "Remote path:  ${REMOTE_PATH}"
echo "Local dir:    ${LOCAL_DIR}"
echo "SSH socket:   ${SSH_SOCKET}"
echo ""

# Check SSH socket is alive
if ! ssh -S "${SSH_SOCKET}" -O check "${SUPERMUC_HOST}" 2>/dev/null; then
    echo "ERROR: SSH socket ${SSH_SOCKET} is not active."
    echo "Re-activate it in your tmux session:"
    echo "  ssh -fNM -S ${SSH_SOCKET} ${SUPERMUC_HOST}"
    exit 1
fi

mkdir -p "${LOCAL_DIR}"

echo "Fetching wrfout files for ${TARGET_DATE}..."
rsync -av --progress \
    -e "ssh -S ${SSH_SOCKET}" \
    --include="wrfout_d02_${TARGET_DATE}_*" \
    --exclude="*" \
    "${SUPERMUC_HOST}:${REMOTE_PATH}/" \
    "${LOCAL_DIR}/"

# Verify we got 24 files
FILE_COUNT=$(find "${LOCAL_DIR}" -name "wrfout_d02_${TARGET_DATE}_*" -type f | wc -l)
echo ""
echo "Files fetched: ${FILE_COUNT}/24"

if [ "${FILE_COUNT}" -ne 24 ]; then
    echo "ERROR: Expected 24 wrfout files, got ${FILE_COUNT}."
    echo "Missing hours:"
    for h in $(seq -w 0 23); do
        f="${LOCAL_DIR}/wrfout_d02_${TARGET_DATE}_${h}:00:00"
        [ ! -f "$f" ] && echo "  ${h}:00:00"
    done
    exit 1
fi

echo "Fetch completed successfully."
