#!/bin/bash
#
# Recursive, time-budgeted fetch driver for the step-by-step pipeline.
#
# RUNS ON A LOGIN NODE (NOT via SLURM). The CINECA datamover
# (data.leonardo.cineca.it) is reachable only from regular login nodes -- NOT from
# lrd_all_serial (login08/13 are firewalled off) nor compute nodes. So the fetch
# cannot be a SLURM job. The launcher starts this script detached on the login
# node; it scp's each wrfout via the datamover and submits the (heavy) convert to
# dcgp_usr_prod via sbatch.
#
# Login-node processes are killed past ~30 min, so the driver works to a wall-time
# budget (DRIVER_MAX_SECONDS) and then RE-SPAWNS ITSELF detached (setsid) for the
# next batch -- each process stays well under the limit. The convert jobs are the
# only SLURM jobs.
#
# Per timestep it:
#   1. skips it if the output GRIB already exists (re-entrancy)
#   2. fetches the wrfout via:  ssh -xT <datamover> "scp -F <cfg> <vm>:<remote> <local>/"
#      wrapped in `timeout` (cuts tape-recall hangs) with a few retries
#   3. checks the file is a readable NetCDF (catches tape stubs / truncation)
#   4. submits a convert_step.sh job (dcgp_usr_prod) for that timestep (async)
# Every outcome is appended to STATUS_LOG (single writer = this driver chain).
# Missing / on-tape / unreadable files are logged and SKIPPED, never fatal.
#
# Required env vars (set by hpc/submit_step_pipeline.py):
#   START_DT, END_DT, CURRENT_DT   - "YYYY-MM-DDTHH"; START=oldest, END=newest edge
#   DIRECTION                      - "backward" (newest->oldest, default) or "forward"
#   BATCH_SIZE                     - max timesteps per process (time budget usually cuts first)
#   DRIVER_MAX_SECONDS             - wall-time budget per process before re-spawning
#   FETCH_PARALLEL                 - concurrent scp transfers
#   FETCH_TIMEOUT, FETCH_RETRIES   - per-scp timeout (s) and retry count
#   WRFOUT_DIR, GRIB_DIR, GRIB_TEMPLATE, PROJECT_DIR
#   DATAMOVER_HOST, SSH_CONFIG, REMOTE_HOST, BASE_2023, BASE_PRE2023, INIT_HOUR
#   LOG_DIR, STATUS_LOG, DRIVER_LOG, DRIVER_SCRIPT, CONVERT_SCRIPT
#   CONVERT_PARTITION, CONVERT_WALLTIME, CONVERT_MEM, CONVERT_ACCOUNT
#   DRY_RUN                        - "1" to print commands instead of running them

set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
DIRECTION="${DIRECTION:-backward}"
INIT_HOUR=$(printf "%02d" "$((10#${INIT_HOUR:-18}))")
FETCH_PARALLEL="${FETCH_PARALLEL:-2}"
BATCH_SIZE="${BATCH_SIZE:-24}"
DRIVER_MAX_SECONDS="${DRIVER_MAX_SECONDS:-1080}"
FETCH_TIMEOUT="${FETCH_TIMEOUT:-600}"
FETCH_RETRIES="${FETCH_RETRIES:-2}"
STATUS_LOG="${STATUS_LOG:-${LOG_DIR}/step_pipeline_status.log}"
DRIVER_LOG="${DRIVER_LOG:-${LOG_DIR}/fetch_step_driver.log}"
# A genuine wrfout is ~8.6G; far below this after a "successful" scp is a tape
# stub or a truncated transfer.
MIN_BYTES="${MIN_WRFOUT_BYTES:-1073741824}"  # 1 GiB
DRIVER_START=$(date +%s)

# ---- helpers ---------------------------------------------------------------

# Append a step outcome to the status ledger (single-writer chain).
#   $1 = target timestep "YYYY-MM-DDTHH"   $2 = STATUS   $3 = detail
log_status() {
    local ts
    ts=$(TZ=UTC date -u +%Y-%m-%dT%H:%M:%SZ)
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [LOG] ${ts} | $1 | $2 | ${3:-}"
    else
        printf '%s | %s | %s | %s\n' "$ts" "$1" "$2" "${3:-}" >> "${STATUS_LOG}"
    fi
}

# Is the datamover reachable from this node? (TCP :22; the restricted shell
# rejects probe commands, so test the socket directly.)
datamover_reachable() {
    timeout 15 bash -c "cat < /dev/null > /dev/tcp/${DATAMOVER_HOST}/22" 2>/dev/null
}

# Remote wrfout path on the VM for a given target date/hour.
remote_path() {
    local d="$1" h="$2" year init base
    year="${d:0:4}"
    init="$(TZ=UTC date -d "${d} -1 day" +%Y%m%d)${INIT_HOUR}"
    if [ "$year" -ge 2023 ]; then base="${BASE_2023}"; else base="${BASE_PRE2023}"; fi
    echo "${base}/${init}/wrfout_d02_${d}_${h}:00:00"
}

# Expanded output GRIB path for a given target date/hour (under a YYYY/MM tree).
grib_path() {
    local d="$1" h="$2" out year month dcompact
    year="${d:0:4}"
    month="${d:5:2}"
    dcompact="${d//-/}"
    out="${GRIB_DIR}/${year}/${month}/${GRIB_TEMPLATE}"
    out="${out//\{year\}/$year}"
    out="${out//\{date_compact\}/$dcompact}"
    out="${out//\{hour:02d\}/$h}"
    echo "$out"
}

# Submit a convert job for one timestep. Real mode echoes ONLY the job id
# (--parsable); dry mode prints the command.
submit_convert() {
    local d="$1" h="$2" dcompact local_dir convert_env
    dcompact="${d//-/}"
    local_dir="${WRFOUT_DIR}/${d}"
    convert_env="TARGET_DATE=${d},HOUR=${h},WRFOUT_DIR=${local_dir},GRIB_DIR=${GRIB_DIR},PROJECT_DIR=${PROJECT_DIR},GRIB_TEMPLATE=${GRIB_TEMPLATE}"

    local acct_args=()
    [ -n "${CONVERT_ACCOUNT:-}" ] && acct_args=(--account "${CONVERT_ACCOUNT}")

    local args=(
        --partition "${CONVERT_PARTITION}"
        --time "${CONVERT_WALLTIME}"
        --mem "${CONVERT_MEM}"
        --job-name "conv_${dcompact}${h}"
        --output "${LOG_DIR}/convert_${dcompact}${h}_%j.out"
        --export "${convert_env}"
        "${acct_args[@]}"
        "${CONVERT_SCRIPT}"
    )
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [DRY] sbatch ${args[*]}"
    else
        sbatch --parsable "${args[@]}"
    fi
}

# Fetch one timestep via the datamover, validate it, then submit its convert job.
# Records the outcome in STATUS_LOG with a grep-able tag; never aborts the driver.
process_one() {
    local d="$1" h="$2"
    local dt="${d}T${h}"
    local local_dir remote fname dest
    local_dir="${WRFOUT_DIR}/${d}"
    remote="$(remote_path "$d" "$h")"
    fname="wrfout_d02_${d}_${h}:00:00"
    dest="${local_dir}/${fname}"
    mkdir -p "$local_dir"

    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [DRY] ssh -xT ${DATAMOVER_HOST} \"scp -F ${SSH_CONFIG} ${REMOTE_HOST}:${remote} ${local_dir}/\""
        log_status "$dt" "FETCH_OK" "(dry-run)"
        submit_convert "$d" "$h"
        log_status "$dt" "CONVERT_SUBMITTED" "(dry-run)"
        return 0
    fi

    if [ -s "$dest" ]; then
        echo "  [${dt}] wrfout already present locally."
    else
        local attempt rc errf snippet max_attempts
        max_attempts=$((FETCH_RETRIES + 1))
        errf=$(mktemp)
        rc=1
        for attempt in $(seq 1 "$max_attempts"); do
            echo "  [${dt}] fetch attempt ${attempt}/${max_attempts} via datamover..."
            if timeout "${FETCH_TIMEOUT}" ssh -xT "${DATAMOVER_HOST}" \
                 "scp -F ${SSH_CONFIG} ${REMOTE_HOST}:${remote} ${local_dir}/" 2>"$errf"; then
                rc=0; break
            else
                rc=$?
            fi
            # tape-recall hang (timeout) or missing source -> no point retrying
            if [ "$rc" -eq 124 ]; then break; fi
            if grep -qiE 'No such file|not a regular file' "$errf"; then break; fi
            sleep 5
        done

        if [ "$rc" -ne 0 ]; then
            snippet=$(tr '\n' ' ' <"$errf" | tr -s ' ' | cut -c1-200)
            rm -f "$errf"; timeout 30 rm -f "$dest" 2>/dev/null || true
            if [ "$rc" -eq 124 ]; then
                echo "  WARN [${dt}] TAPE_TIMEOUT (scp > ${FETCH_TIMEOUT}s)"
                log_status "$dt" "TAPE_TIMEOUT" "scp exceeded ${FETCH_TIMEOUT}s; file likely migrated to tape -> ask LRZ to recall"
            elif echo "$snippet" | grep -qiE 'No such file|not a regular file'; then
                echo "  WARN [${dt}] MISSING_ON_LRZ"
                log_status "$dt" "MISSING_ON_LRZ" "$snippet"
            else
                echo "  WARN [${dt}] FETCH_ERROR rc=${rc}"
                log_status "$dt" "FETCH_ERROR" "rc=${rc} ${snippet}"
            fi
            return 1
        fi
        rm -f "$errf"
    fi

    # Integrity check: size sanity + NetCDF header open. A tape stub copied as a
    # placeholder, or a truncated transfer, fails here -> flag for recall.
    local size
    size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
    if [ "$size" -lt "$MIN_BYTES" ] || \
       ! ( cd "$PROJECT_DIR" && uv run python -c "import sys,netCDF4; netCDF4.Dataset(sys.argv[1]).close()" "$dest" ) >/dev/null 2>&1; then
        echo "  WARN [${dt}] UNREADABLE_TAPE (size=${size}B)"
        log_status "$dt" "UNREADABLE_TAPE" "size=${size}B not a readable NetCDF; likely tape stub/truncated -> ask LRZ to recall"
        timeout 30 rm -f "$dest" 2>/dev/null || true
        return 1
    fi

    log_status "$dt" "FETCH_OK" "size=${size}B"
    local jobid
    jobid=$(submit_convert "$d" "$h")
    echo "  [${dt}] convert submitted (job ${jobid})"
    log_status "$dt" "CONVERT_SUBMITTED" "job=${jobid}"
}

# Re-spawn this driver detached for the next timestep (fresh login-node clock).
respawn() {
    local next_dt="$1"
    if [ "${DRY_RUN}" = "1" ]; then
        echo "[DRY] setsid bash ${DRIVER_SCRIPT}   (CURRENT_DT=${next_dt})"
    else
        CURRENT_DT="${next_dt}" setsid bash "${DRIVER_SCRIPT}" >> "${DRIVER_LOG}" 2>&1 < /dev/null &
        echo "Respawned driver (pid $!) for ${next_dt}."
    fi
}

# ---- main ------------------------------------------------------------------

if [ "${DIRECTION}" = "forward" ]; then STEP=3600; else STEP=-3600; DIRECTION="backward"; fi

echo "=== CHAPTER fetch_step @ $(hostname) $(date -u +%FT%TZ) ==="
echo "Window:    ${START_DT} (oldest)  ..  ${END_DT} (newest)"
echo "Direction: ${DIRECTION}    Current: ${CURRENT_DT}"
echo "Budget:    ${DRIVER_MAX_SECONDS}s wall, batch<=${BATCH_SIZE}, ${FETCH_PARALLEL} parallel, fetch timeout ${FETCH_TIMEOUT}s"
echo "Datamover: ${DATAMOVER_HOST}  (vm: ${REMOTE_HOST})"
echo "StatusLog: ${STATUS_LOG}"
echo "Dry run:   ${DRY_RUN}"
echo ""

mkdir -p "${LOG_DIR}" "$(dirname "${STATUS_LOG}")"

# Refuse to run where the datamover is unreachable (e.g. lrd_all_serial / compute).
if [ "${DRY_RUN}" != "1" ] && ! datamover_reachable; then
    echo "FATAL: datamover ${DATAMOVER_HOST}:22 unreachable from $(hostname)."
    echo "       Launch the pipeline from a regular login node (NOT lrd_all_serial)."
    log_status "DRIVER@$(hostname)" "DATAMOVER_UNREACHABLE" "datamover unreachable; run from a regular login node"
    exit 1
fi

# All timestamp arithmetic is done in UTC (WRF timesteps are UTC) via epoch
# seconds, to avoid local-timezone/DST artifacts in hour labels.
CUR_DATE="${CURRENT_DT%T*}"; CUR_HOUR="${CURRENT_DT#*T}"
CUR_EPOCH=$(TZ=UTC date -d "${CUR_DATE} $((10#${CUR_HOUR})):00:00" +%s)
START_EPOCH=$(TZ=UTC date -d "${START_DT%T*} $((10#${START_DT#*T})):00:00" +%s)
END_EPOCH=$(TZ=UTC date -d "${END_DT%T*} $((10#${END_DT#*T})):00:00" +%s)

# A timestep is in scope if it lies within [oldest, newest], regardless of direction.
within_window() { [ "$1" -ge "$START_EPOCH" ] && [ "$1" -le "$END_EPOCH" ]; }

processed=0
running=0
budget_hit=0
while [ "$processed" -lt "$BATCH_SIZE" ] && within_window "$CUR_EPOCH"; do
    if [ "$(( $(date +%s) - DRIVER_START ))" -ge "$DRIVER_MAX_SECONDS" ]; then
        echo "Time budget (${DRIVER_MAX_SECONDS}s) reached; will respawn for the rest of the window."
        budget_hit=1
        break
    fi

    d=$(TZ=UTC date -d "@${CUR_EPOCH}" +%Y-%m-%d)
    h=$(TZ=UTC date -d "@${CUR_EPOCH}" +%H)
    dt="${d}T${h}"

    if [ -f "$(grib_path "$d" "$h")" ]; then
        echo "  [${dt}] GRIB already exists, skipping."
        log_status "$dt" "SKIP_GRIB_EXISTS" ""
    elif [ "${DRY_RUN}" = "1" ] || [ "${FETCH_PARALLEL}" -le 1 ]; then
        process_one "$d" "$h" || true
    else
        process_one "$d" "$h" &
        running=$((running + 1))
        if [ "$running" -ge "$FETCH_PARALLEL" ]; then
            wait -n || true
            running=$((running - 1))
        fi
    fi

    CUR_EPOCH=$((CUR_EPOCH + STEP))
    processed=$((processed + 1))
done

# Wait for any in-flight background fetch+convert dispatches
wait || true

# Re-spawn for the next timestep if the window is not exhausted
if within_window "$CUR_EPOCH"; then
    NEXT_DT=$(TZ=UTC date -d "@${CUR_EPOCH}" +%Y-%m-%dT%H)
    echo ""
    [ "$budget_hit" -eq 1 ] && echo "Batch stopped on time budget." || echo "Batch done (${processed} timesteps)."
    echo "Continuing from ${NEXT_DT} (${DIRECTION})..."
    respawn "${NEXT_DT}"
else
    echo ""
    echo "Window complete (reached ${DIRECTION} edge). No further respawn."
fi
