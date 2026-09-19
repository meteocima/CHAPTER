#!/bin/bash
#
# Stage the audit sample -- ticket "Stage the audit sample" (#13) of the
# variable-audit map (#11).
#
# 34 timesteps on three axes, fetched into a staging directory of their own,
# converted at the current 246-message schema into a GRIB tree of their own, and
# left on disk as the audit's fixture. Every other ticket of the map measures
# these files, so that two results are comparable.
#
# WHY IT OWNS EVERY PATH IT TOUCHES. The 2024-fill campaign is paused, not
# finished: its staging dir, ledger, driver log and stop flag all still exist, and
# two chains sharing any one of them collide -- a stop request meant for one kills
# the other, and their ledgers interleave into an unreadable record. Hence:
#     wrfout   $WORK/wrfout_audit      (never wrfout_share / _rebuild / _2024fill)
#     GRIB     $WORK/grib_audit        (never grib_v3)
#     ledger   $LOGS/audit_sample_status.log
#     driver   $LOGS/audit_sample_driver.log
#     stop     $LOGS/audit_sample.stop
#
# And why NOT grib_v3 in particular: convert_step.sh keys its re-entrancy on the
# MESSAGE COUNT of an existing output (hpc/grib_schema_ok.py), not on its values. A
# sample file whose count is 246 but whose values are wrong would be skipped
# forever by the rebuild campaign. Finding exactly that is what this audit is for,
# so its output must not sit in the archive's own tree.
#
# Phases, in order; each is re-entrant and can be re-run:
#   link      symlink the timesteps already on local disk into the staging dir
#   fetch     pull the rest from the LRZ relay via the CINECA datamover
#   convert   sbatch one convert per timestep, 00Z first (it writes the day's
#             accumulation sidecar, which every other hour of that day needs)
#   verify    hpc/check_grib_sanity.py on every GRIB produced
#   report    print what is staged, converted and missing
#
# The fetch MUST run on a regular login node: the datamover is unreachable from
# lrd_all_serial and from compute nodes. The convert is always SLURM.
#
set -euo pipefail

# Honour an inherited value: the snapshot re-exec below runs the script from the
# log directory, where deriving the repo root from BASH_SOURCE would be wrong.
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PROJECT_DIR}"

# ---- the sample ------------------------------------------------------------
#
# date hour axis
#
# seasonal    the 15th of each month of 2024 at 00Z and 12Z: separates a dead
#             field from a seasonally-zero one, and carries snow, sea ice and the
#             whole radiation range.
# interannual 2019 summer against its 2024 twin, 2025 winter against its 2024
#             twin: separates a physical signal from a code artefact.
# diurnal     one summer day also at 06Z and 18Z: radiation, accumulations and
#             the skt / 2t cycle.
#
# 00Z is never optional: accumulated fields are referred to 00Z of the same day,
# so every 12Z in the sample needs its day's 00Z anyway.
SAMPLE="
2024-01-15 00 seasonal
2024-01-15 12 seasonal
2024-02-15 00 seasonal
2024-02-15 12 seasonal
2024-03-15 00 seasonal
2024-03-15 12 seasonal
2024-04-15 00 seasonal
2024-04-15 12 seasonal
2024-05-15 00 seasonal
2024-05-15 12 seasonal
2024-06-15 00 seasonal
2024-06-15 12 seasonal
2024-07-15 00 seasonal
2024-07-15 06 diurnal
2024-07-15 12 seasonal
2024-07-15 18 diurnal
2024-08-15 00 seasonal
2024-08-15 12 seasonal
2024-09-15 00 seasonal
2024-09-15 12 seasonal
2024-10-15 00 seasonal
2024-10-15 12 seasonal
2024-11-15 00 seasonal
2024-11-15 12 seasonal
2024-12-15 00 seasonal
2024-12-15 12 seasonal
2019-07-15 00 interannual
2019-07-15 12 interannual
2019-08-15 00 interannual
2019-08-15 12 interannual
2025-01-15 00 interannual
2025-01-15 12 interannual
2025-02-15 00 interannual
2025-02-15 12 interannual
"

# Directories already holding CHAPTER wrfout on this filesystem, searched in this
# order by the link phase. They belong to other efforts: read, never write.
SOURCE_DIRS="wrfout_share wrfout_rebuild wrfout_2024fill wrfout"

# ---- configuration ---------------------------------------------------------
# Read from conf/pipeline.yaml rather than duplicated here: the datamover paths
# and the relay's key move, and a second copy would rot.
eval "$(~/.local/bin/uv run python - <<'PY'
from omegaconf import OmegaConf
c = OmegaConf.to_container(OmegaConf.load("conf/pipeline.yaml"), resolve=True)
p, d, s, g = c["paths"], c["datamover"], c["slurm"], c["grib"]
out = {
    "WORK_DIR": p["work_dir"], "LOG_DIR": p["log_dir"],
    "ACCUM_REF_DIR": p["accum_ref_dir"], "STATIC_REF_DIR": p["static_ref_dir"],
    "GRIB_TEMPLATE": g["name_template"],
    "DATAMOVER_HOST": d["host"], "REMOTE_HOST": d["remote_host"],
    "IDENTITY_FILE": d["identity_file"], "SFTP_OPTS": d["sftp_opts"],
    "BASE_2023": d["base_2023"], "BASE_PRE2023": d["base_pre2023"],
    "INIT_HOUR": str(d["init_hour"]),
    "FETCH_TIMEOUT": str(d["fetch_timeout"]), "FETCH_RETRIES": str(d["fetch_retries"]),
    "CONVERT_PARTITION": s["step_convert_partition"],
    "CONVERT_WALLTIME": s["step_convert_walltime"],
    "CONVERT_MEM": s["step_convert_mem"],
    "CONVERT_ACCOUNT": s["step_convert_account"],
}
for k, v in out.items():
    print(f"{k}={v!r}".replace("'", '"'))
PY
)"

# Audit-owned paths: none of these is shared with a campaign chain.
WRFOUT_DIR="${WORK_DIR}/wrfout_audit"
GRIB_DIR="${WORK_DIR}/grib_audit"
STATUS_LOG="${LOG_DIR}/audit_sample_status.log"
DRIVER_LOG="${LOG_DIR}/audit_sample_driver.log"
STOP_FLAG="${LOG_DIR}/audit_sample.stop"
# Concurrent sftp streams through the datamover. 3 is the measured ceiling that
# still scales linearly (~60 MB/s each); 4 was never tested.
FETCH_PARALLEL="${FETCH_PARALLEL:-3}"
MIN_BYTES=1073741824   # 1 GiB: below this a "successful" transfer is a stub

mkdir -p "${WRFOUT_DIR}" "${GRIB_DIR}" "${LOG_DIR}"

wrfout_name() { echo "wrfout_d02_$1_$2:00:00"; }
staged_path()  { echo "${WRFOUT_DIR}/$1/$(wrfout_name "$1" "$2")"; }
grib_file()    {
    local d="$1" h="$2" n="${GRIB_TEMPLATE}"
    n="${n//\{year\}/${d:0:4}}"; n="${n//\{date_compact\}/${d//-/}}"; n="${n//\{hour:02d\}/$h}"
    echo "${GRIB_DIR}/${d:0:4}/${d:5:2}/${n}"
}
big_enough()   { [ -f "$1" ] && [ "$(stat -Lc%s "$1" 2>/dev/null || echo 0)" -ge "${MIN_BYTES}" ]; }
sidecar()      { echo "${ACCUM_REF_DIR}/${1:0:4}/${1:5:2}/accum_ref_${1//-/}.npz"; }

each_sample() { echo "${SAMPLE}" | awk 'NF'; }

# ---- phases ----------------------------------------------------------------

phase_link() {
    echo "=== link: timesteps already on local disk ==="
    local d h axis src found n_link=0 n_have=0 n_miss=0
    while read -r d h axis; do
        local dest; dest="$(staged_path "$d" "$h")"
        if big_enough "${dest}"; then n_have=$((n_have+1)); continue; fi
        found=""
        for base in ${SOURCE_DIRS}; do
            src="${WORK_DIR}/${base}/${d}/$(wrfout_name "$d" "$h")"
            if big_enough "${src}"; then found="${src}"; break; fi
        done
        if [ -n "${found}" ]; then
            mkdir -p "$(dirname "${dest}")"
            ln -sfn "${found}" "${dest}"
            echo "  ${d}T${h}  -> ${found#${WORK_DIR}/}"
            n_link=$((n_link+1))
        else
            n_miss=$((n_miss+1))
        fi
    done < <(each_sample)
    echo "linked ${n_link}, already staged ${n_have}, to fetch ${n_miss}"
}

# One timestep through the tested transfer path: hpc/fetch_step.sh with a window
# of exactly one hour, download-only. It fetches, validates the NetCDF, appends to
# our ledger and exits without respawning (the window is exhausted after one step).
fetch_one() {
    local d="$1" h="$2"
    START_DT="${d}T${h}" END_DT="${d}T${h}" CURRENT_DT="${d}T${h}" \
    DIRECTION=forward BATCH_SIZE=1 DRIVER_MAX_SECONDS=3600 FETCH_PARALLEL=1 \
    FETCH_TIMEOUT="${FETCH_TIMEOUT}" FETCH_RETRIES="${FETCH_RETRIES}" \
    DOWNLOAD_ONLY=1 KEEP_WRFOUT=1 MAX_QUEUED_CONVERTS=0 DRY_RUN="${DRY_RUN:-0}" \
    WRFOUT_DIR="${WRFOUT_DIR}" GRIB_DIR="${GRIB_DIR}" GRIB_TEMPLATE="${GRIB_TEMPLATE}" \
    PROJECT_DIR="${PROJECT_DIR}" ACCUM_REF_DIR="${ACCUM_REF_DIR}" \
    STATIC_REF_DIR="${STATIC_REF_DIR}" \
    DATAMOVER_HOST="${DATAMOVER_HOST}" REMOTE_HOST="${REMOTE_HOST}" \
    IDENTITY_FILE="${IDENTITY_FILE}" SFTP_OPTS="${SFTP_OPTS}" \
    BASE_2023="${BASE_2023}" BASE_PRE2023="${BASE_PRE2023}" INIT_HOUR="${INIT_HOUR}" \
    LOG_DIR="${LOG_DIR}" STATUS_LOG="${STATUS_LOG}" DRIVER_LOG="${DRIVER_LOG}" \
    STOP_FLAG="${STOP_FLAG}" DRIVER_SCRIPT="${PROJECT_DIR}/hpc/fetch_step.sh" \
    CONVERT_SCRIPT="${PROJECT_DIR}/hpc/convert_step.sh" \
    CONVERT_PARTITION="${CONVERT_PARTITION}" CONVERT_WALLTIME="${CONVERT_WALLTIME}" \
    CONVERT_MEM="${CONVERT_MEM}" CONVERT_ACCOUNT="${CONVERT_ACCOUNT}" \
        bash "${PROJECT_DIR}/hpc/fetch_step.sh" 2>&1 | sed "s/^/[${d}T${h}] /"
}

phase_fetch() {
    echo "=== fetch: the rest, from the relay via the datamover ==="
    if ! timeout 15 bash -c "cat </dev/null >/dev/tcp/${DATAMOVER_HOST}/22" 2>/dev/null; then
        echo "FATAL: datamover unreachable from $(hostname). Run this on a regular login node."
        exit 1
    fi
    # Collect the pending timesteps FIRST, then walk the array.
    #
    # Not a `while read` over a process substitution, and the fetch is launched with
    # its stdin closed. hpc/fetch_step.sh runs `ssh -xT` with neither -n nor a stdin
    # redirect: backgrounded inside a read loop, ssh inherits fd 0 and DRAINS the
    # loop's own input, so the loop ends after exactly FETCH_PARALLEL iterations.
    # That is what silently cut this phase to 3 of 21 files, twice.
    local d h axis
    local -a pending=()
    while read -r d h axis; do
        big_enough "$(staged_path "$d" "$h")" && continue
        pending+=("${d} ${h}")
    done < <(each_sample)
    echo "${#pending[@]} timesteps to fetch, ${FETCH_PARALLEL} at a time"

    local running=0 spec
    for spec in "${pending[@]}"; do
        [ -e "${STOP_FLAG}" ] && { echo "STOP flag present; stopping."; break; }
        fetch_one ${spec} < /dev/null &
        running=$((running+1))
        if [ "${running}" -ge "${FETCH_PARALLEL}" ]; then wait -n || true; running=$((running-1)); fi
    done
    wait || true

    local left=0
    while read -r d h axis; do
        big_enough "$(staged_path "$d" "$h")" || left=$((left+1))
    done < <(each_sample)
    echo "fetch phase done: ${#pending[@]} attempted, ${left} still missing"
}

phase_convert() {
    echo "=== convert: one SLURM job per timestep, 00Z first ==="
    local d h axis dep jobid n=0 did00
    local -a hours
    # Group by date. The 00Z of a day writes that day's accumulation sidecar, and
    # every other hour of the day fails without it, so 00Z goes first and the rest
    # wait on it. Where the sidecar already exists, nothing has to wait.
    for d in $(each_sample | awk '{print $1}' | sort -u); do
        dep=""; did00=0
        if [ ! -s "$(sidecar "$d")" ]; then
            if ! big_enough "$(staged_path "$d" 00)"; then
                echo "  WARN ${d}: no sidecar and no staged 00Z -- every hour of this day would fail; skipping the day"
                continue
            fi
            if [ -f "$(grib_file "$d" 00)" ]; then
                echo "  WARN ${d}: 00Z GRIB exists but the sidecar does not; reconverting 00Z"
                rm -f "$(grib_file "$d" 00)"
            fi
            jobid=$(submit_convert "$d" 00 "" </dev/null)
            echo "  ${d}T00  job ${jobid}  (writes the day's sidecar)"
            dep="--dependency=afterok:${jobid}"
            did00=1; n=$((n+1))
        fi
        local -a hours=()
        while read -r _ h axis; do hours+=("$h"); done < <(each_sample | awk -v D="$d" '$1==D')
        for h in "${hours[@]}"; do
            [ "$h" = "00" ] && [ "$did00" = "1" ] && continue
            if ! big_enough "$(staged_path "$d" "$h")"; then
                echo "  skip ${d}T${h}: not staged"; continue
            fi
            if [ -f "$(grib_file "$d" "$h")" ]; then
                echo "  skip ${d}T${h}: GRIB exists"; continue
            fi
            jobid=$(submit_convert "$d" "$h" "${dep}" </dev/null)
            echo "  ${d}T${h}  job ${jobid}${dep:+  (after ${dep#*:})}"
            n=$((n+1))
        done
    done
    echo "submitted ${n} convert jobs"
}

submit_convert() {
    local d="$1" h="$2" dep="${3:-}"
    local dc="${d//-/}"
    sbatch --parsable \
        --partition "${CONVERT_PARTITION}" --account "${CONVERT_ACCOUNT}" \
        --time "${CONVERT_WALLTIME}" --mem "${CONVERT_MEM}" \
        --job-name "audit_${dc}${h}" \
        --output "${LOG_DIR}/audit_conv_${dc}${h}_%j.out" \
        ${dep} \
        --export "TARGET_DATE=${d},HOUR=${h},WRFOUT_DIR=${WRFOUT_DIR}/${d},GRIB_DIR=${GRIB_DIR},PROJECT_DIR=${PROJECT_DIR},GRIB_TEMPLATE=${GRIB_TEMPLATE},ACCUM_REF_DIR=${ACCUM_REF_DIR},STATIC_REF_DIR=${STATIC_REF_DIR},KEEP_WRFOUT=1" \
        "${PROJECT_DIR}/hpc/convert_step.sh"
}

phase_verify() {
    echo "=== verify: check_grib_sanity over the whole sample in one pass ==="
    # One invocation for all of them: the eccodes import dominates a single-file
    # run, and the checker already reports per file and exits 1 if any is BAD.
    local d h axis f files=() missing=0
    while read -r d h axis; do
        f="$(grib_file "$d" "$h")"
        if [ -f "$f" ]; then files+=("$f"); else echo "  MISSING  ${d}T${h}"; missing=$((missing+1)); fi
    done < <(each_sample)
    echo "present ${#files[@]}, missing ${missing}"
    [ "${#files[@]}" -eq 0 ] && return 1
    source tools/eccodes_env.sh
    ~/.local/bin/uv run python hpc/check_grib_sanity.py "${files[@]}"
}

phase_report() {
    printf '%-12s %-4s %-12s %-10s %-10s\n' DATE HOUR AXIS WRFOUT GRIB
    local d h axis w g
    while read -r d h axis; do
        big_enough "$(staged_path "$d" "$h")" && w=staged || w=--
        [ -L "$(staged_path "$d" "$h")" ] && [ "$w" = staged ] && w=linked
        g="$(grib_file "$d" "$h")"
        if [ -f "$g" ]; then g="$(( $(stat -c%s "$g") / 1048576 ))MB"; else g=--; fi
        printf '%-12s %-4s %-12s %-10s %-10s\n' "$d" "$h" "$axis" "$w" "$g"
    done < <(each_sample)
}

# ---- run from a snapshot ---------------------------------------------------
# Bash reads a script incrementally from disk: editing this file while a long
# phase is running shifts every byte after the read offset and the running shell
# dies on a syntax error mid-loop. That is not hypothetical -- it happened to this
# script on its first fetch, and to hpc/fetch_step.sh before it (which is why the
# step pipeline snapshots its driver). So the long phases re-exec themselves from
# a copy, and the working tree is free to move under them.
if [ -z "${AUDIT_SNAPSHOT:-}" ]; then
    case "${1:-report}" in
        fetch|all|convert)
            SNAP="${LOG_DIR}/.audit_stage_$(date -u +%Y%m%dT%H%M%S)_$$.sh"
            cp "${BASH_SOURCE[0]}" "${SNAP}"
            echo "Running from snapshot ${SNAP} (the working copy is free to be edited)."
            AUDIT_SNAPSHOT="${SNAP}" PROJECT_DIR="${PROJECT_DIR}" exec bash "${SNAP}" "$@"
            ;;
    esac
fi

case "${1:-report}" in
    link)    phase_link ;;
    fetch)   phase_fetch ;;
    convert) phase_convert ;;
    verify)  phase_verify ;;
    report)  phase_report ;;
    all)     phase_link; phase_fetch; phase_link; phase_convert ;;
    *) echo "usage: $0 {link|fetch|convert|verify|report|all}"; exit 2 ;;
esac
