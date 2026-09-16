#!/bin/bash
#
# Detached sequence that closes the 2024 gap: 5088 missing hourly timesteps
# (2024-09-13..10-25 and 2024-01-01..06-17), fetched from LRZ and converted to GRIB,
# with the wrfout deleted as soon as its GRIB exists.
#
# Why phases: downloading all 46.5 TB before converting would peak at ~88 TB of the
# project's 100 TB quota. Instead the window is cut into ~monthly phases and, as soon
# as a phase finishes downloading, its conversion is launched IN THE BACKGROUND while
# the next phase is already downloading. The convert chain only ever sees local files,
# so it never touches the datamover and the download is never slowed down. At most two
# phases sit on disk at a time -> peak ~58 TB.
#
# Per phase:
#   1. wait until the project quota is below QUOTA_STOP_TB
#   2. launch a DOWNLOAD-ONLY chain (no convert, wrfout kept) and wait for "Window complete"
#   3. launch the CONVERT chain for that same phase and DO NOT wait for it
# KEEP_WRFOUT=true (the default) keeps the staged wrfout after conversion; PHASES_ONLY
# restricts the run to a subset of phase labels when resuming a stopped sequence.
# At the end: wait for every convert chain, drain the queue, write the per-phase reports
# and submit one check_grib_sanity job over all the affected months.
#
# RUN ON A REGULAR LOGIN NODE:  bash hpc/run_2024_fill.sh
# It snapshots itself and re-execs detached (setsid), so the terminal / chat can be
# closed and edits to the repo copy do not touch the running sequence. Re-entrant:
# re-running skips staged wrfout (download) and existing GRIBs (convert).
# Stop: touch ${W}/logs/fill2024_sequence.stop  (plus the per-chain fill2024_<label>_{dl,cv}.stop
# to stop a driver itself).

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/leonardo/home/userexternal/lmonaco0/CHAPTER}"
W="${W:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
LOG_DIR="${W}/logs"
FILL_DIR="${FILL_DIR:-${W}/wrfout_2024fill}"   # dedicated staging dir (never wrfout/ or wrfout_share/)
SEQ_LOG="${LOG_DIR}/fill2024_sequence.log"
SEQ_STOP="${LOG_DIR}/fill2024_sequence.stop"
UV="${UV:-${HOME}/.local/bin/uv}"
MAX_QUEUED=48          # convert chain: batch.size and batch.max_queued_converts
FETCH_PARALLEL=3       # download chain: concurrent sftp streams through the datamover
DEAD_MINUTES=60        # a driver log silent this long without completing is dead
POLL_SECONDS=300
PROJECT_QUOTA_ID=20148120        # lfs project id of /leonardo_work/AIFPT_AILAMIT
QUOTA_STOP_TB=85                 # hold new downloads above this
SANITY_ACCOUNT=aifpt_ailamit_0
SANITY_MONTHS="2024-01,2024-02,2024-03,2024-04,2024-05,2024-06,2024-09,2024-10"
# Keep the staged wrfout after a successful convert. Default true: more variables may have
# to be extracted from these years later, and re-fetching a wrfout costs 9 GB over the LRZ
# relay. NB with KEEP=true nothing frees space, so a QUOTA_HOLD can no longer resolve
# itself -- size the phases so the projected peak stays under QUOTA_STOP_TB.
KEEP_WRFOUT="${KEEP_WRFOUT:-true}"
# Restrict the run to these phase labels (space separated), e.g. to resume a stopped
# sequence without re-downloading phases whose wrfout are already gone. Empty = all.
PHASES_ONLY="${PHASES_ONLY:-}"
export KEEP_WRFOUT PHASES_ONLY

# label  start_date  end_date   (the small block first: it doubles as an end-to-end shakedown)
PHASES=(
    "p0_sepoct 2024-09-13 2024-10-25"
    "p1_jan    2024-01-01 2024-01-31"
    "p2_feb    2024-02-01 2024-02-29"
    "p3_mar    2024-03-01 2024-03-31"
    "p4_apr    2024-04-01 2024-04-30"
    "p5_may    2024-05-01 2024-05-31"
    "p6_jun    2024-06-01 2024-06-17"
)

# ---- self-detach from a snapshot --------------------------------------------
if [ -z "${SEQ_DETACHED:-}" ]; then
    mkdir -p "$LOG_DIR"
    snap="${LOG_DIR}/.fill2024_sequence_$(date +%Y%m%d%H%M%S).sh"
    cp "$0" "${snap}.tmp" && mv "${snap}.tmp" "$snap"
    SEQ_DETACHED=1 setsid bash "$snap" >> "$SEQ_LOG" 2>&1 < /dev/null &
    echo "Sequence detached on $(hostname) (pid $!), snapshot ${snap}"
    echo "Log: ${SEQ_LOG}    Stop: touch ${SEQ_STOP}"
    exit 0
fi

log() { echo "$(date -u +%FT%TZ) | $*" >&2; }

check_stop() {
    if [ -e "$SEQ_STOP" ]; then
        log "STOPPED | ${SEQ_STOP} present; exiting."
        exit 0
    fi
}

queued_converts() {
    local out
    out=$(timeout 60 squeue -h -u "${USER}" -o %j 2>/dev/null) || return 1
    printf '%s\n' "$out" | awk '/^conv_/ {n++} END {print n+0}'
}

# Project usage in TB, or empty if lfs did not answer (never guess: a missing
# reading must not be read as "plenty of room").
used_tb() {
    timeout 60 lfs quota -p "$PROJECT_QUOTA_ID" /leonardo_work 2>/dev/null \
        | awk '/leonardo_work/ {gsub(/\*/,"",$2); printf "%.2f", $2/1024/1024/1024}'
}

# Hold here while the quota is above the threshold: the convert chain of the previous
# phase is deleting wrfout as it goes, so this resolves itself instead of aborting.
wait_for_quota() {
    local label="$1" tb warned=0
    while :; do
        check_stop
        tb=$(used_tb)
        if [ -z "$tb" ]; then
            log "QUOTA_UNKNOWN | ${label}: lfs quota did not answer; waiting ${POLL_SECONDS}s"
            sleep "$POLL_SECONDS"; continue
        fi
        if awk -v u="$tb" -v m="$QUOTA_STOP_TB" 'BEGIN{exit !(u < m)}'; then
            log "QUOTA_OK | ${label}: ${tb} TB used (< ${QUOTA_STOP_TB} TB)"
            return 0
        fi
        if [ "$warned" -eq 0 ]; then
            if [ "$KEEP_WRFOUT" = "true" ]; then
                log "QUOTA_HOLD | ${label}: ${tb} TB used >= ${QUOTA_STOP_TB} TB and KEEP_WRFOUT=true, so nothing will free space on its own: move or delete data, or raise QUOTA_STOP_TB"
            else
                log "QUOTA_HOLD | ${label}: ${tb} TB used >= ${QUOTA_STOP_TB} TB; waiting for converts to free space"
            fi
        fi
        warned=1
        sleep "$POLL_SECONDS"
    done
}

dl_args() {
    local label="$1" start="$2" end="$3"
    echo "window.start_date=${start} window.start_hour=0 window.end_date=${end} window.end_hour=23" \
         "pipeline.download_only=true paths.wrfout_dir=${FILL_DIR}" \
         "batch.fetch_parallel=${FETCH_PARALLEL} batch.size=${MAX_QUEUED} batch.max_queued_converts=0" \
         "paths.status_log=${LOG_DIR}/fill2024_${label}_dl_status.log" \
         "paths.driver_log=${LOG_DIR}/fill2024_${label}_dl_driver.log" \
         "paths.stop_flag=${LOG_DIR}/fill2024_${label}_dl.stop"
}

cv_args() {
    local label="$1" start="$2" end="$3"
    # KEEP_WRFOUT=false lets convert_step.sh delete each wrfout once its GRIB is in place
    # (it still refuses to delete a 00Z whose accum_ref sidecar is missing); true keeps them.
    echo "window.start_date=${start} window.start_hour=0 window.end_date=${end} window.end_hour=23" \
         "paths.wrfout_dir=${FILL_DIR} pipeline.keep_wrfout=${KEEP_WRFOUT}" \
         "batch.fetch_parallel=${FETCH_PARALLEL} batch.size=${MAX_QUEUED} batch.max_queued_converts=${MAX_QUEUED}" \
         "paths.status_log=${LOG_DIR}/fill2024_${label}_cv_status.log" \
         "paths.driver_log=${LOG_DIR}/fill2024_${label}_cv_driver.log" \
         "paths.stop_flag=${LOG_DIR}/fill2024_${label}_cv.stop"
}

# Launch a chain unless one is already alive on that driver log. Echoes the byte offset
# from which the driver log belongs to this run (1 = an existing chain we are adopting).
launch_chain() {
    local kind="$1" label="$2" dlog="$3"; shift 3
    local offset alive=""
    # sample freshness before touching, otherwise our own touch makes a stale log look alive
    [ -f "$dlog" ] && alive=$(find "$dlog" -mmin -25 -size +0)
    touch "$dlog"
    offset=$(( $(stat -c%s "$dlog") + 1 ))
    if [ -n "$alive" ] && ! tail -n 3 "$dlog" | grep -q "Window complete\|STOP flag"; then
        log "WAIT | ${label} ${kind}: a chain is already alive (driver log fresh); adopting it"
        echo 1; return 0
    fi
    log "LAUNCH | ${label} ${kind}"
    if ! "$UV" run python hpc/submit_step_pipeline.py "$@" >&2; then
        log "FATAL | ${label} ${kind}: launcher failed"
        echo ""; return 1
    fi
    echo "$offset"
}

# Poll a driver log until it reports the window done. 0 = complete, 1 = dead, 2 = stopped.
wait_chain() {
    local kind="$1" label="$2" dlog="$3" offset="$4"
    while :; do
        sleep "$POLL_SECONDS"
        check_stop
        if tail -c "+${offset}" "$dlog" | grep -q "Window complete"; then
            log "WINDOW_COMPLETE | ${label} ${kind}"
            return 0
        fi
        if tail -c "+${offset}" "$dlog" | grep -q "STOP flag present"; then
            log "STOPPED | ${label} ${kind}: driver stopped by its stop flag"
            return 2
        fi
        if [ -z "$(find "$dlog" -mmin "-${DEAD_MINUTES}")" ]; then
            log "CHAIN_DEAD | ${label} ${kind}: driver log silent > ${DEAD_MINUTES} min without Window complete"
            return 1
        fi
    done
}

case "$FILL_DIR" in
    */wrfout|*/wrfout_share)
        log "FATAL | FILL_DIR must be a dedicated staging dir, not ${FILL_DIR}"; exit 1 ;;
esac

log "START | sequence on $(hostname), pid $$, staging ${FILL_DIR}"
cd "$PROJECT_DIR" || { log "FATAL | cannot cd ${PROJECT_DIR}"; exit 1; }
mkdir -p "$FILL_DIR"

CV_PENDING=()   # "label start end offset" of the convert chains still to be waited on

for ph in "${PHASES[@]}"; do
    read -r label start end <<<"$ph"
    check_stop
    if [ -n "$PHASES_ONLY" ] && ! printf '%s\n' $PHASES_ONLY | grep -qx "$label"; then
        log "SKIP_PHASE | ${label}: not in PHASES_ONLY"
        continue
    fi
    wait_for_quota "$label"

    dl_log="${LOG_DIR}/fill2024_${label}_dl_driver.log"
    # shellcheck disable=SC2046
    dargs=( $(dl_args "$label" "$start" "$end") )
    if ! off=$(launch_chain download "$label" "$dl_log" "${dargs[@]}") || [ -z "$off" ]; then
        log "FATAL | ${label}: download launcher failed; exiting (re-run this script, it is re-entrant)"
        exit 1
    fi
    wait_chain download "$label" "$dl_log" "$off"; rc=$?
    [ "$rc" -eq 2 ] && exit 0
    if [ "$rc" -ne 0 ]; then
        log "FATAL | ${label}: download chain died; exiting (re-run this script, it is re-entrant)"
        exit 1
    fi
    log "STAGED | ${label}: $(find "${FILL_DIR}" -name 'wrfout_d02_*' -type f | wc -l) wrfout on disk, $(used_tb) TB used"

    # Convert this phase in the background (local files only, no datamover) while the
    # next phase downloads. Its wrfout are deleted one by one as the GRIBs appear.
    cv_log="${LOG_DIR}/fill2024_${label}_cv_driver.log"
    # shellcheck disable=SC2046
    cargs=( $(cv_args "$label" "$start" "$end") )
    if ! off=$(launch_chain convert "$label" "$cv_log" "${cargs[@]}") || [ -z "$off" ]; then
        log "FATAL | ${label}: convert launcher failed; exiting (re-run this script, it is re-entrant)"
        exit 1
    fi
    CV_PENDING+=("${label} ${start} ${end} ${off}")
done

log "ALL_DOWNLOADS_DONE | waiting for ${#CV_PENDING[@]} convert chain(s)"

for pend in "${CV_PENDING[@]}"; do
    read -r label start end off <<<"$pend"
    cv_log="${LOG_DIR}/fill2024_${label}_cv_driver.log"
    wait_chain convert "$label" "$cv_log" "$off"; rc=$?
    [ "$rc" -eq 2 ] && exit 0
    [ "$rc" -ne 0 ] && log "WARN | ${label} convert: chain died; its report below will show what is missing"
done

while :; do
    check_stop
    if nq=$(queued_converts) && [ "$nq" -eq 0 ]; then break; fi
    sleep "$POLL_SECONDS"
done
log "QUEUE_EMPTY | all converts left the queue"

for pend in "${CV_PENDING[@]}"; do
    read -r label start end off <<<"$pend"
    # shellcheck disable=SC2046
    cargs=( $(cv_args "$label" "$start" "$end") )
    rep="${LOG_DIR}/fill2024_${label}_report.txt"
    "$UV" run python hpc/submit_step_pipeline.py "${cargs[@]}" report=true > "$rep" 2>&1
    log "REPORT | ${label}: $(grep '^# summary' "$rep")"
done
log "GRIB_COUNT | 2024: $(find "${W}/grib/2024" -name '*.grib' | wc -l) / 8784"
log "STAGING_LEFT | $(find "${FILL_DIR}" -name 'wrfout_d02_*' -type f | wc -l) wrfout still in ${FILL_DIR}, $(used_tb) TB used"

month_args=""
for m in ${SANITY_MONTHS//,/ }; do month_args+=" --month ${m}"; done
jid=$(sbatch --parsable --partition dcgp_usr_prod --account "$SANITY_ACCOUNT" \
    --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 8G --time 06:00:00 \
    --job-name "sanity_fill2024" --output "${LOG_DIR}/fill2024_sanity_%j.out" \
    --wrap "cd ${PROJECT_DIR}
module load eccodes/2.34.0--gcc--12.2.0 2>/dev/null
GCC12_RT=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/gcc-runtime-12.2.0-dqfwf7yjtbtdzllj66jx6suk34ir2ct3/lib
ECCODES_LIB=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/eccodes-2.34.0-msheephhj7zirdzmqcfdrf4jat5w545r/lib64
export LD_PRELOAD=\$GCC12_RT/libstdc++.so.6
export LD_LIBRARY_PATH=\$GCC12_RT:\$ECCODES_LIB:\${LD_LIBRARY_PATH:-}
${UV} run python hpc/check_grib_sanity.py${month_args}")
log "SANITY_SUBMITTED | job ${jid:-FAILED} -> ${LOG_DIR}/fill2024_sanity_${jid}.out"

log "DONE | all phases processed"
