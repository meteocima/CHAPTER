#!/bin/bash
#
# Detached sequence that converts every wrfout still on local disk to GRIB:
# wrfout_share 2024, then wrfout_share 2019, then the March 2024 block staged in
# wrfout_2024fill (4380 hours in all). It KEEPS every wrfout -- wrfout_share is
# still to be copied by a colleague, and nothing is deleted until asked -- and
# never queues more than 48 convert jobs (two days of reanalysis) at a time.
#
# Per phase (the "chain name" is the first field of PHASES and prefixes every
# per-chain file: <name>_conv_status.log, <name>_conv_driver.log, <name>_conv.stop):
#   1. launch the step pipeline (hpc/submit_step_pipeline.py) with keep_wrfout and the
#      queue gate -- unless a chain for that phase is already alive (then just wait)
#   2. wait for "Window complete" in its driver log and an empty conv_* queue;
#      a driver log silent for > DEAD_MINUTES without completion -> CHAIN_DEAD, stop
#   3. write the read-only report and submit a 1-core check_grib_sanity job
#
# RUN ON A REGULAR LOGIN NODE:  bash hpc/run_share_conversion.sh
# It snapshots itself and re-execs detached (setsid), so the terminal / chat can be
# closed and edits to the repo copy do not touch the running sequence. Re-entrant:
# re-running skips existing GRIBs. Stop: touch ${W}/logs/share_conv_sequence.stop
# (plus the per-phase share<year>_conv.stop to stop the driver itself).

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/leonardo/home/userexternal/lmonaco0/CHAPTER}"
W="${W:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
LOG_DIR="${W}/logs"
SEQ_LOG="${LOG_DIR}/share_conv_sequence.log"
SEQ_STOP="${LOG_DIR}/share_conv_sequence.stop"
UV="${UV:-${HOME}/.local/bin/uv}"
MAX_QUEUED=48
DEAD_MINUTES=60
POLL_SECONDS=300
SANITY_ACCOUNT=aifpt_ailamit_0

# chain-name  start_date  end_date  months-for-sanity  wrfout-subdir
# The chain name is only an identifier for the per-phase ledger/driver/stop
# triplet; it must not collide with an older chain, whose stop flag would kill
# this one on sight (that is why March is share2024mar, not fill2024_p3_mar).
PHASES=(
    "share2024    2024-06-18 2024-09-12 2024-06,2024-07,2024-08,2024-09 wrfout_share"
    "share2019    2019-06-17 2019-09-06 2019-06,2019-07,2019-08,2019-09 wrfout_share"
    "share2024mar 2024-03-18 2024-03-31 2024-03                         wrfout_2024fill"
)

# ---- self-detach from a snapshot --------------------------------------------
if [ -z "${SEQ_DETACHED:-}" ]; then
    mkdir -p "$LOG_DIR"
    snap="${LOG_DIR}/.share_conv_sequence_$(date +%Y%m%d%H%M%S).sh"
    cp "$0" "${snap}.tmp" && mv "${snap}.tmp" "$snap"
    SEQ_DETACHED=1 setsid bash "$snap" >> "$SEQ_LOG" 2>&1 < /dev/null &
    echo "Sequence detached on $(hostname) (pid $!), snapshot ${snap}"
    echo "Log: ${SEQ_LOG}    Stop: touch ${SEQ_STOP}"
    exit 0
fi

log() { echo "$(date -u +%FT%TZ) | $*"; }

queued_converts() {
    local out
    out=$(timeout 60 squeue -h -u "${USER}" -o %j 2>/dev/null) || return 1
    printf '%s\n' "$out" | awk '/^conv_/ {n++} END {print n+0}'
}

check_stop() {
    if [ -e "$SEQ_STOP" ]; then
        log "STOPPED | ${SEQ_STOP} present; exiting."
        exit 0
    fi
}

pipeline_args() {
    local y="$1" start="$2" end="$3" wdir="$4"
    echo "window.start_date=${start} window.start_hour=0 window.end_date=${end} window.end_hour=23" \
         "paths.wrfout_dir=${W}/${wdir} pipeline.keep_wrfout=true" \
         "batch.size=${MAX_QUEUED} batch.max_queued_converts=${MAX_QUEUED}" \
         "paths.status_log=${LOG_DIR}/${y}_conv_status.log" \
         "paths.driver_log=${LOG_DIR}/${y}_conv_driver.log" \
         "paths.stop_flag=${LOG_DIR}/${y}_conv.stop"
}

log "START | sequence on $(hostname), pid $$"
cd "$PROJECT_DIR" || { log "FATAL | cannot cd ${PROJECT_DIR}"; exit 1; }

for ph in "${PHASES[@]}"; do
    read -r y start end months wdir <<<"$ph"
    check_stop
    dlog="${LOG_DIR}/${y}_conv_driver.log"
    ystop="${LOG_DIR}/${y}_conv.stop"
    if [ -e "$ystop" ]; then
        log "STOPPED | ${ystop} present; not launching ${y}, exiting."
        exit 0
    fi
    # shellcheck disable=SC2046
    args=( $(pipeline_args "$y" "$start" "$end" "$wdir") )

    # Only the driver-log bytes written after this point count as "this run".
    touch "$dlog"
    offset=$(( $(stat -c%s "$dlog") + 1 ))

    if [ -n "$(find "$dlog" -mmin -25 -size +0)" ] && ! tail -n 3 "$dlog" | grep -q "Window complete\|STOP flag"; then
        log "WAIT | ${y}: a chain is already alive (driver log fresh); not launching a second one"
        offset=1
    else
        log "LAUNCH | ${y}: ${start}..${end} from ${wdir}, keep_wrfout, <=${MAX_QUEUED} queued"
        if ! "$UV" run python hpc/submit_step_pipeline.py "${args[@]}"; then
            log "FATAL | ${y}: launcher failed; exiting (re-run this script to retry)"
            exit 1
        fi
    fi

    # 2. wait for this phase's chain to finish
    while :; do
        sleep "$POLL_SECONDS"
        check_stop
        if tail -c "+${offset}" "$dlog" | grep -q "Window complete"; then
            log "WINDOW_COMPLETE | ${y}"
            break
        fi
        if tail -c "+${offset}" "$dlog" | grep -q "STOP flag present"; then
            log "STOPPED | ${y}: driver stopped by its stop flag; exiting."
            exit 0
        fi
        if [ -z "$(find "$dlog" -mmin "-${DEAD_MINUTES}")" ]; then
            log "CHAIN_DEAD | ${y}: driver log silent > ${DEAD_MINUTES} min without Window complete; exiting (re-run this script, it is re-entrant)"
            exit 1
        fi
    done
    while :; do
        check_stop
        if nq=$(queued_converts) && [ "$nq" -eq 0 ]; then break; fi
        sleep "$POLL_SECONDS"
    done
    log "QUEUE_EMPTY | ${y}: all converts left the queue"

    # 3. report + sanity
    "$UV" run python hpc/submit_step_pipeline.py "${args[@]}" report=true \
        > "${LOG_DIR}/${y}_conv_report.txt" 2>&1
    log "REPORT | ${y}: $(grep '^# summary' "${LOG_DIR}/${y}_conv_report.txt")"
    log "WRFOUT_COUNT | ${y}: $(find "${W}/${wdir}" -name "wrfout_d02_${start:0:4}-*" | wc -l) files left in ${wdir}"

    month_args=""
    for m in ${months//,/ }; do month_args+=" --month ${m}"; done
    jid=$(sbatch --parsable --partition dcgp_usr_prod --account "$SANITY_ACCOUNT" \
        --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 8G --time 06:00:00 \
        --job-name "sanity_${y}" --output "${LOG_DIR}/${y}_sanity_%j.out" \
        --wrap "cd ${PROJECT_DIR}
module load eccodes/2.34.0--gcc--12.2.0 2>/dev/null
GCC12_RT=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/gcc-runtime-12.2.0-dqfwf7yjtbtdzllj66jx6suk34ir2ct3/lib
ECCODES_LIB=/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/eccodes-2.34.0-msheephhj7zirdzmqcfdrf4jat5w545r/lib64
export LD_PRELOAD=\$GCC12_RT/libstdc++.so.6
export LD_LIBRARY_PATH=\$GCC12_RT:\$ECCODES_LIB:\${LD_LIBRARY_PATH:-}
${UV} run python hpc/check_grib_sanity.py${month_args}")
    log "SANITY_SUBMITTED | ${y}: job ${jid:-FAILED} -> ${LOG_DIR}/${y}_sanity_${jid}.out"
done

log "DONE | all phases processed"
