#!/bin/bash
#
# Detached sequence that rebuilds the CHAPTER archive in GRIB2 (246 messages) for the
# hours whose wrfout are NOT on local disk: 17 496 timesteps over 2019 (full year),
# 2024 (full year) and 2025 (01-01..06-30). Each one is fetched from the LRZ relay,
# converted, and its wrfout deleted as soon as the GRIB exists.
#
# Companion of hpc/run_share_conversion.sh, which converts the 4392 hours already
# staged in wrfout_share/ and wrfout_2024fill/ and never deletes them. The two run in
# parallel: this one is datamover-bound, that one is CPU-bound, and they only meet in
# the conv_* queue gate. The PHASES below are the exact complement of what that script
# covers, so nothing is fetched twice:
#
#   on disk (run_share_conversion): 2019-06-17..09-06, 2024-03-18..03-31, 2024-06-18..09-12
#   here:                           everything else in 2019, 2024 and 2025-H1
#
# Why phases: a year of wrfout is ~80 TB against a 100 TB quota. The window is cut into
# ~monthly phases and, as soon as a phase finishes downloading, its conversion starts IN
# THE BACKGROUND while the next phase downloads. The convert chain only sees local files,
# so it never competes for the datamover. With KEEP_WRFOUT=false each converted wrfout is
# deleted at once, so at most ~2 phases sit on disk (~14 TB).
#
# Per phase:
#   1. wait until the project quota is below QUOTA_STOP_TB
#   2. launch a DOWNLOAD-ONLY chain (no convert, wrfout kept) and wait for "Window complete"
#   3. launch the CONVERT chain for that same phase and DO NOT wait for it
# At the end: wait for every convert chain, drain the queue, write the per-phase reports
# and submit one check_grib_sanity job over every month touched.
#
# RUN ON A REGULAR LOGIN NODE:  bash hpc/run_year_rebuild.sh
# It snapshots itself and re-execs detached (setsid), so the terminal / chat can be closed
# and edits to the repo copy do not touch the running sequence. Re-entrant: re-running
# skips staged wrfout (download) and existing GRIBs (convert).
# Stop: touch ${W}/logs/rebuild_sequence.stop  (plus the per-chain
# rebuild_<label>_{dl,cv}.stop to stop a driver itself).
# Resume after a stop: PHASES_ONLY="<labels>" is REQUIRED for phases whose wrfout were
# already deleted -- the download side keys on the staged file, so they would otherwise
# be fetched again in full.

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/leonardo/home/userexternal/lmonaco0/CHAPTER}"
W="${W:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
LOG_DIR="${W}/logs"
STAGING_DIR="${STAGING_DIR:-${W}/wrfout_rebuild}"   # this sequence's own staging slot;
                                                    # KEEP_WRFOUT decides if its wrfout survive
SEQ_LOG="${LOG_DIR}/rebuild_sequence.log"
SEQ_STOP="${LOG_DIR}/rebuild_sequence.stop"
UV="${UV:-${HOME}/.local/bin/uv}"
MAX_QUEUED=48          # convert chain: batch.size and batch.max_queued_converts
FETCH_PARALLEL=3       # download chain: concurrent sftp streams through the datamover
DEAD_MINUTES=60        # a driver log silent this long without completing is dead
POLL_SECONDS=300
PROJECT_QUOTA_ID=20148120        # lfs project id of /leonardo_work/AIFPT_AILAMIT
QUOTA_STOP_TB=85                 # hold new downloads above this
SANITY_ACCOUNT=aifpt_ailamit_0
# Delete each staged wrfout once its GRIB is in place. The schema is closed at 246
# messages, so there is no longer a reason to keep them, and it is the only way this
# campaign fits in the quota. convert_step.sh still refuses to delete a 00Z whose
# accum_ref sidecar is missing.
KEEP_WRFOUT="${KEEP_WRFOUT:-false}"
# Restrict the run to these phase labels (space separated). Empty = all.
PHASES_ONLY="${PHASES_ONLY:-}"
export KEEP_WRFOUT PHASES_ONLY

# label  start_date start_hour  end_date end_hour
# The first phase is a 72 h shakedown: an end-to-end failure shows up in ~2 h instead of
# after a full month. It is a real slice of 2019-09, not a duplicate of any other phase.
PHASES=(
    "r19_09a 2019-09-07 0 2019-09-09 23"
    "r24_01  2024-01-01 0 2024-01-31 23"
    "r24_02  2024-02-01 0 2024-02-29 23"
    "r24_03  2024-03-01 0 2024-03-17 23"
    "r24_04  2024-04-01 0 2024-04-30 23"
    "r24_05  2024-05-01 0 2024-05-31 23"
    "r24_06  2024-06-01 0 2024-06-17 23"
    "r24_09  2024-09-13 0 2024-09-30 23"
    "r24_10  2024-10-01 0 2024-10-31 23"
    "r24_11  2024-11-01 0 2024-11-30 23"
    "r24_12  2024-12-01 0 2024-12-31 23"
    "r19_01  2019-01-01 0 2019-01-31 23"
    "r19_02  2019-02-01 0 2019-02-28 23"
    "r19_03  2019-03-01 0 2019-03-31 23"
    "r19_04  2019-04-01 0 2019-04-30 23"
    "r19_05  2019-05-01 0 2019-05-31 23"
    "r19_06  2019-06-01 0 2019-06-16 23"
    "r19_09b 2019-09-10 0 2019-09-30 23"
    "r19_10  2019-10-01 0 2019-10-31 23"
    "r19_11  2019-11-01 0 2019-11-30 23"
    "r19_12  2019-12-01 0 2019-12-31 23"
    "r25_01  2025-01-01 0 2025-01-31 23"
    "r25_02  2025-02-01 0 2025-02-28 23"
    "r25_03  2025-03-01 0 2025-03-31 23"
    "r25_04  2025-04-01 0 2025-04-30 23"
    "r25_05  2025-05-01 0 2025-05-31 23"
    "r25_06  2025-06-01 0 2025-06-30 23"
)

# ---- self-detach from a snapshot --------------------------------------------
if [ -z "${SEQ_DETACHED:-}" ]; then
    mkdir -p "$LOG_DIR"
    snap="${LOG_DIR}/.rebuild_sequence_$(date +%Y%m%d%H%M%S).sh"
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
    local label="$1" sd="$2" sh="$3" ed="$4" eh="$5"
    echo "window.start_date=${sd} window.start_hour=${sh} window.end_date=${ed} window.end_hour=${eh}" \
         "pipeline.download_only=true paths.wrfout_dir=${STAGING_DIR}" \
         "batch.fetch_parallel=${FETCH_PARALLEL} batch.size=${MAX_QUEUED} batch.max_queued_converts=0" \
         "paths.status_log=${LOG_DIR}/rebuild_${label}_dl_status.log" \
         "paths.driver_log=${LOG_DIR}/rebuild_${label}_dl_driver.log" \
         "paths.stop_flag=${LOG_DIR}/rebuild_${label}_dl.stop"
}

cv_args() {
    local label="$1" sd="$2" sh="$3" ed="$4" eh="$5"
    echo "window.start_date=${sd} window.start_hour=${sh} window.end_date=${ed} window.end_hour=${eh}" \
         "paths.wrfout_dir=${STAGING_DIR} pipeline.keep_wrfout=${KEEP_WRFOUT}" \
         "batch.fetch_parallel=${FETCH_PARALLEL} batch.size=${MAX_QUEUED} batch.max_queued_converts=${MAX_QUEUED}" \
         "paths.status_log=${LOG_DIR}/rebuild_${label}_cv_status.log" \
         "paths.driver_log=${LOG_DIR}/rebuild_${label}_cv_driver.log" \
         "paths.stop_flag=${LOG_DIR}/rebuild_${label}_cv.stop"
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

# The staging slot belongs to this sequence alone: never a shared tree, never
# another campaign's slot. With KEEP_WRFOUT=false its wrfout are deleted as they
# convert, so pointing it at one of those would destroy someone else's data.
case "$STAGING_DIR" in
    */wrfout|*/wrfout_share|*/wrfout_2024fill)
        log "FATAL | STAGING_DIR must be this sequence's own staging slot, not ${STAGING_DIR}"; exit 1 ;;
esac

log "START | sequence on $(hostname), pid $$, staging ${STAGING_DIR}, keep_wrfout=${KEEP_WRFOUT}"
cd "$PROJECT_DIR" || { log "FATAL | cannot cd ${PROJECT_DIR}"; exit 1; }
mkdir -p "$STAGING_DIR"

CV_PENDING=()   # "label sd sh ed eh offset" of the convert chains still to be waited on
MONTHS=""       # distinct YYYY-MM touched, for the final sanity job

for ph in "${PHASES[@]}"; do
    read -r label sd sh ed eh <<<"$ph"
    check_stop
    if [ -n "$PHASES_ONLY" ] && ! printf '%s\n' $PHASES_ONLY | grep -qx "$label"; then
        log "SKIP_PHASE | ${label}: not in PHASES_ONLY"
        continue
    fi
    case ",${MONTHS}," in *",${sd:0:7},"*) ;; *) MONTHS="${MONTHS:+${MONTHS},}${sd:0:7}" ;; esac
    wait_for_quota "$label"

    dl_log="${LOG_DIR}/rebuild_${label}_dl_driver.log"
    # shellcheck disable=SC2046
    dargs=( $(dl_args "$label" "$sd" "$sh" "$ed" "$eh") )
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
    log "STAGED | ${label}: $(find "${STAGING_DIR}" -name 'wrfout_d02_*' -type f | wc -l) wrfout on disk, $(used_tb) TB used"

    # Convert this phase in the background (local files only, no datamover) while the
    # next phase downloads. Its wrfout are deleted one by one as the GRIBs appear.
    cv_log="${LOG_DIR}/rebuild_${label}_cv_driver.log"
    # shellcheck disable=SC2046
    cargs=( $(cv_args "$label" "$sd" "$sh" "$ed" "$eh") )
    if ! off=$(launch_chain convert "$label" "$cv_log" "${cargs[@]}") || [ -z "$off" ]; then
        log "FATAL | ${label}: convert launcher failed; exiting (re-run this script, it is re-entrant)"
        exit 1
    fi
    CV_PENDING+=("${label} ${sd} ${sh} ${ed} ${eh} ${off}")
done

log "ALL_DOWNLOADS_DONE | waiting for ${#CV_PENDING[@]} convert chain(s)"

for pend in "${CV_PENDING[@]}"; do
    read -r label sd sh ed eh off <<<"$pend"
    cv_log="${LOG_DIR}/rebuild_${label}_cv_driver.log"
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
    read -r label sd sh ed eh off <<<"$pend"
    # shellcheck disable=SC2046
    cargs=( $(cv_args "$label" "$sd" "$sh" "$ed" "$eh") )
    rep="${LOG_DIR}/rebuild_${label}_report.txt"
    "$UV" run python hpc/submit_step_pipeline.py "${cargs[@]}" report=true > "$rep" 2>&1
    log "REPORT | ${label}: $(grep '^# summary' "$rep")"
done
for y in 2019 2024 2025; do
    log "GRIB_COUNT | ${y}: $(find "${W}/grib_v3/${y}" -name '*.grib' 2>/dev/null | wc -l)"
done
log "STAGING_LEFT | $(find "${STAGING_DIR}" -name 'wrfout_d02_*' -type f | wc -l) wrfout still in ${STAGING_DIR}, $(used_tb) TB used"

month_args=""
for m in ${MONTHS//,/ }; do month_args+=" --month ${m}"; done
jid=$(sbatch --parsable --partition dcgp_usr_prod --account "$SANITY_ACCOUNT" \
    --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 8G --time 12:00:00 \
    --job-name "sanity_rebuild" --output "${LOG_DIR}/rebuild_sanity_%j.out" \
    --wrap "cd ${PROJECT_DIR}
module load eccodes/2.34.0--gcc--12.2.0 2>/dev/null
GCC12_RT=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/gcc-runtime-12.2.0-dqfwf7yjtbtdzllj66jx6suk34ir2ct3/lib
ECCODES_LIB=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/eccodes-2.34.0-msheephhj7zirdzmqcfdrf4jat5w545r/lib64
export LD_PRELOAD=\$GCC12_RT/libstdc++.so.6
export LD_LIBRARY_PATH=\$GCC12_RT:\$ECCODES_LIB:\${LD_LIBRARY_PATH:-}
${UV} run python hpc/check_grib_sanity.py${month_args}")
log "SANITY_SUBMITTED | job ${jid:-FAILED} -> ${LOG_DIR}/rebuild_sanity_${jid}.out"

log "DONE | all phases processed"
