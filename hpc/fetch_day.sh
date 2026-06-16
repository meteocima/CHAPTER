#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --job-name=chapter_fetch
#
# Fetch all 24 hourly wrfout files for a single target date from SuperMUC.
# Opens its own SSH ControlMaster and closes it on exit (job-local socket).
#
# Required env vars (set via --export at submission):
#   TARGET_DATE   - target date in YYYY-MM-DD format
#   REMOTE_PATH   - full path to run folder on SuperMUC
#   LOCAL_DIR     - local directory to store wrfout files
#   SUPERMUC_HOST - remote hostname (default: supermuc)

set -euo pipefail

SUPERMUC_HOST="${SUPERMUC_HOST:-supermuc}"
SSH_SOCKET="${TMPDIR:-/tmp}/skt-fetch-${SLURM_JOB_ID:-$$}"

echo "=== CHAPTER fetch_day ==="
echo "Target date:  ${TARGET_DATE}"
echo "Remote path:  ${REMOTE_PATH}"
echo "Local dir:    ${LOCAL_DIR}"
echo "SSH socket:   ${SSH_SOCKET}"
echo ""

# Close SSH master on any exit
cleanup_ssh() {
    if ssh -S "${SSH_SOCKET}" -O check "${SUPERMUC_HOST}" 2>/dev/null; then
        echo "Closing SSH master..."
        ssh -S "${SSH_SOCKET}" -O exit "${SUPERMUC_HOST}" 2>/dev/null || true
    fi
}
trap cleanup_ssh EXIT

# Open SSH ControlMaster (with retry)
MAX_RETRIES=3
RETRY_DELAY=10
for attempt in $(seq 1 $MAX_RETRIES); do
    if ssh -fNM -S "${SSH_SOCKET}" "${SUPERMUC_HOST}" 2>/dev/null; then
        break
    fi
    if [ "$attempt" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: failed to open SSH master to ${SUPERMUC_HOST} after ${MAX_RETRIES} attempts."
        exit 1
    fi
    echo "SSH master open failed, retrying in ${RETRY_DELAY}s (attempt ${attempt}/${MAX_RETRIES})..."
    sleep ${RETRY_DELAY}
done

# Verify the master is reachable
if ! ssh -S "${SSH_SOCKET}" -O check "${SUPERMUC_HOST}" 2>/dev/null; then
    echo "ERROR: SSH master opened but check failed."
    exit 1
fi
echo "SSH master open."

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
