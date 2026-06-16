#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --job-name=chapter_fetch_step
#
# Recursive, batch-based fetch driver for the step-by-step pipeline.
# Runs on a partition with outbound connectivity (lrd_all_serial): it triggers
# scp transfers on the CINECA datamover (data.leonardo.cineca.it), which reaches
# the chapteradmin VM (supermuc-vm). Compute nodes have no network, so the fetch
# MUST run here, not in the convert job.
#
# For each hourly timestep in the current batch it:
#   1. skips the timestep if its output GRIB already exists (re-entrancy)
#   2. fetches the wrfout via:  ssh -xT <datamover> "scp -F <cfg> <vm>:<remote> <local>/"
#   3. submits a convert_step.sh job (dcgp_usr_prod) for that timestep (async)
# After BATCH_SIZE timesteps it resubmits ITSELF for the next timestep until END_DT.
#
# Required env vars (set by hpc/submit_step_pipeline.py via --export):
#   START_DT, END_DT, CURRENT_DT   - "YYYY-MM-DDTHH" (CURRENT_DT advances each resubmission)
#   BATCH_SIZE                     - timesteps handled before resubmitting self
#   FETCH_PARALLEL                 - concurrent scp transfers within a batch
#   WRFOUT_DIR                     - base local dir; per-date subfolder is created
#   GRIB_DIR, GRIB_TEMPLATE        - output GRIB dir + Python .format() template
#   PROJECT_DIR                    - path to CHAPTER repo
#   DATAMOVER_HOST                 - e.g. data.leonardo.cineca.it
#   SSH_CONFIG                     - ssh config used by the datamover scp (-F)
#   REMOTE_HOST                    - ssh host alias for the VM (e.g. supermuc-vm)
#   BASE_2023, BASE_PRE2023        - remote base paths (VM view), selected by year
#   INIT_HOUR                      - run init hour (previous day), default 18
#   LOG_DIR                        - SLURM log directory
#   DRIVER_SCRIPT, CONVERT_SCRIPT  - absolute paths to this script and convert_step.sh
#   DRIVER_PARTITION, DRIVER_WALLTIME, DRIVER_ACCOUNT   - SLURM cfg for self-resubmission
#   CONVERT_PARTITION, CONVERT_WALLTIME, CONVERT_MEM, CONVERT_ACCOUNT - SLURM cfg for convert
#   DRY_RUN                        - "1" to print commands instead of running them

set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
INIT_HOUR=$(printf "%02d" "$((10#${INIT_HOUR:-18}))")
FETCH_PARALLEL="${FETCH_PARALLEL:-4}"
BATCH_SIZE="${BATCH_SIZE:-24}"

# ---- helpers ---------------------------------------------------------------

# Remote wrfout path on the VM for a given target date/hour.
remote_path() {
    local d="$1" h="$2" year init base
    year="${d:0:4}"
    init="$(TZ=UTC date -d "${d} -1 day" +%Y%m%d)${INIT_HOUR}"
    if [ "$year" -ge 2023 ]; then base="${BASE_2023}"; else base="${BASE_PRE2023}"; fi
    echo "${base}/${init}/wrfout_d02_${d}_${h}:00:00"
}

# Expanded output GRIB path for a given target date/hour.
grib_path() {
    local d="$1" h="$2" out year dcompact
    year="${d:0:4}"
    dcompact="${d//-/}"
    out="${GRIB_DIR}/${GRIB_TEMPLATE}"
    out="${out//\{year\}/$year}"
    out="${out//\{date_compact\}/$dcompact}"
    out="${out//\{hour:02d\}/$h}"
    echo "$out"
}

# Submit a convert job for one timestep (or print it in dry-run mode).
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
        sbatch "${args[@]}"
    fi
}

# Fetch one timestep via the datamover, then submit its convert job.
# Returns non-zero (without aborting the driver) if the fetch fails.
process_one() {
    local d="$1" h="$2" local_dir remote fname dest scp_cmd
    local_dir="${WRFOUT_DIR}/${d}"
    remote="$(remote_path "$d" "$h")"
    fname="wrfout_d02_${d}_${h}:00:00"
    dest="${local_dir}/${fname}"
    scp_cmd="scp -F ${SSH_CONFIG} ${REMOTE_HOST}:${remote} ${local_dir}/"

    mkdir -p "$local_dir"

    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [DRY] ssh -xT ${DATAMOVER_HOST} \"${scp_cmd}\""
        submit_convert "$d" "$h"
        return 0
    fi

    if [ -s "$dest" ]; then
        echo "  [${d} ${h}:00] wrfout already present, skipping fetch."
    else
        echo "  [${d} ${h}:00] fetching via datamover..."
        if ! ssh -xT "${DATAMOVER_HOST}" "${scp_cmd}"; then
            echo "  WARN: fetch failed for ${fname} (will retry next run); skipping convert."
            return 1
        fi
    fi
    submit_convert "$d" "$h"
}

# ---- main ------------------------------------------------------------------

echo "=== CHAPTER fetch_step ==="
echo "Window:    ${START_DT}  ->  ${END_DT}"
echo "Current:   ${CURRENT_DT}"
echo "Batch:     ${BATCH_SIZE} timesteps, ${FETCH_PARALLEL} parallel fetches"
echo "Datamover: ${DATAMOVER_HOST}  (vm: ${REMOTE_HOST})"
echo "Dry run:   ${DRY_RUN}"
echo ""

mkdir -p "${LOG_DIR}"

# All timestamp arithmetic is done in UTC (WRF timesteps are UTC) via epoch
# seconds, to avoid local-timezone/DST artifacts in hour labels.
CUR_DATE="${CURRENT_DT%T*}"
CUR_HOUR="${CURRENT_DT#*T}"
CUR_EPOCH=$(TZ=UTC date -d "${CUR_DATE} $((10#${CUR_HOUR})):00:00" +%s)

END_DATE="${END_DT%T*}"
END_HOUR="${END_DT#*T}"
END_EPOCH=$(TZ=UTC date -d "${END_DATE} $((10#${END_HOUR})):00:00" +%s)

processed=0
running=0
while [ "$processed" -lt "$BATCH_SIZE" ] && [ "$CUR_EPOCH" -le "$END_EPOCH" ]; do
    d=$(TZ=UTC date -d "@${CUR_EPOCH}" +%Y-%m-%d)
    h=$(TZ=UTC date -d "@${CUR_EPOCH}" +%H)

    if [ -f "$(grib_path "$d" "$h")" ]; then
        echo "  [${d} ${h}:00] GRIB already exists, skipping."
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

    CUR_EPOCH=$((CUR_EPOCH + 3600))
    processed=$((processed + 1))
done

# Wait for any in-flight background fetch+convert dispatches
wait || true

# Recurse: resubmit self for the next timestep if the window is not exhausted
if [ "$CUR_EPOCH" -le "$END_EPOCH" ]; then
    NEXT_DT=$(TZ=UTC date -d "@${CUR_EPOCH}" +%Y-%m-%dT%H)
    echo ""
    echo "Batch done (${processed} timesteps). Resubmitting driver for ${NEXT_DT}..."

    acct_args=()
    [ -n "${DRIVER_ACCOUNT:-}" ] && acct_args=(--account "${DRIVER_ACCOUNT}")
    args=(
        --partition "${DRIVER_PARTITION}"
        --time "${DRIVER_WALLTIME}"
        --job-name "fetch_step_${NEXT_DT//[-:T]/}"
        --output "${LOG_DIR}/fetch_step_${NEXT_DT//[-:T]/}_%j.out"
        --export "ALL,CURRENT_DT=${NEXT_DT}"
        "${acct_args[@]}"
        "${DRIVER_SCRIPT}"
    )
    if [ "${DRY_RUN}" = "1" ]; then
        echo "[DRY] sbatch ${args[*]}"
    else
        sbatch "${args[@]}"
    fi
else
    echo ""
    echo "Window complete: processed through ${END_DT}. No further resubmission."
fi
