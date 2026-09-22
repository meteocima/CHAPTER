#!/bin/bash
# Measure the whole audit sample with the harness, and keep at it until it is
# complete. Detached: launch it and log out.
#
#     bash tools/audit/run_harness_campaign.sh          # detach and return
#     bash tools/audit/run_harness_campaign.sh --fg     # run in the foreground
#     touch $WORK/CHAPTER/logs/audit_harness_campaign.stop   # ask it to stop
#
# WHY A CAMPAIGN AND NOT ONE sbatch. Two failures were met on 2026-09-21 and
# neither is ours: seventeen of thirty-four tasks died at launch with
# "container_p_join: open failed for /nvme/tmpfs/.../.ns", and for ninety minutes
# slurmctld refused every submission -- a one-line echo job included -- with
# "Invalid account or account/partition combination specified" while the budget
# and the associations were fine. A single submission survives neither. This
# loop resubmits exactly the timesteps that are still missing, and waits out a
# controller that is refusing.
#
# THE ONLY SOURCE OF TRUTH IS THE ROWS ON DISK. Not the queue, not sacct -- both
# lied on 2026-09-21, squeue reporting an empty queue while sacct still called
# sixteen tasks RUNNING. A timestep is done when its file holds 246 rows with
# 246 distinct (variable, level) keys and one timestep. Anything else is redone.
#
# IT NEVER DELETES A COMPLETE FILE. The previous run deleted the whole measured
# set before confirming the replacement could even be submitted, and left the
# families with nothing while the controller was down. Files are only ever
# rewritten by the task that owns them.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${WORK_DIR:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
ROWS="${WORK}/audit_rows"
LOGS="${WORK}/logs"
LOG="${LOGS}/audit_harness_campaign.log"
STOP="${LOGS}/audit_harness_campaign.stop"
MAX_ROUNDS=12

mkdir -p "${ROWS}" "${LOGS}"

# Run from a snapshot of itself, so the repo is free to be edited while this
# lives. A script edited while running is re-read from a shifted byte offset and
# dies; that killed a staging run after 22 of 2088 files in September.
if [ -z "${HARNESS_CAMPAIGN_SNAPSHOT:-}" ]; then
    SNAP="${LOGS}/.harness_campaign_$(date -u +%Y%m%dT%H%M%S)_$$.sh"
    cp "${BASH_SOURCE[0]}" "${SNAP}"
    if [ "${1:-}" = "--fg" ]; then
        HARNESS_CAMPAIGN_SNAPSHOT="${SNAP}" PROJECT_DIR="${PROJECT_DIR}" \
            exec bash "${SNAP}" --fg
    fi
    rm -f "${STOP}"
    HARNESS_CAMPAIGN_SNAPSHOT="${SNAP}" PROJECT_DIR="${PROJECT_DIR}" \
        setsid nohup bash "${SNAP}" --fg >>"${LOG}" 2>&1 </dev/null &
    disown || true
    sleep 2
    echo "detached. log ${LOG}"
    echo "stop with: touch ${STOP}"
    echo "check with: bash tools/audit/run_harness_campaign.sh --status"
    exit 0
fi

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

cd "${PROJECT_DIR}"
# shellcheck disable=SC1091
source tools/eccodes_env.sh >/dev/null 2>&1 || true

"${HOME}/.local/bin/uv" run python -c "
import sys; sys.path.insert(0, 'tools/audit')
from harness import sample_timesteps
print('\n'.join(sample_timesteps()))
" > "${ROWS}/timesteps.txt"
N=$(wc -l < "${ROWS}/timesteps.txt")
say "campaign starting: ${N} timesteps, 246 rows each"

missing_indices() {
    "${HOME}/.local/bin/uv" run --no-project python - "${ROWS}" <<'PY'
import collections, json, os, sys
rows = sys.argv[1]
steps = [l.strip() for l in open(os.path.join(rows, 'timesteps.txt')) if l.strip()]
bad = []
for i, step in enumerate(steps):
    path = os.path.join(rows, f'rows_{step}.jsonl')
    if not os.path.exists(path):
        bad.append(str(i)); continue
    keys, stamps = [], set()
    try:
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            keys.append((row['variable'], row['level']))
            stamps.add(row['timestep'])
    except Exception:
        bad.append(str(i)); continue
    counts = collections.Counter(keys)
    if len(keys) != 246 or any(v > 1 for v in counts.values()) or len(stamps) != 1:
        bad.append(str(i))
print(','.join(bad))
PY
}

submit_array() {
    local spec="$1" out
    for attempt in $(seq 1 60); do
        [ -e "${STOP}" ] && { say "STOP flag while submitting"; return 1; }
        out=$(sbatch --parsable \
            --job-name audit_harness \
            --partition dcgp_usr_prod --account aifpt_ailamit_0 \
            --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 8G --time 01:00:00 \
            --array "${spec}%8" \
            --output "${LOGS}/audit_harness_%A_%a.out" \
            --wrap "set -euo pipefail
cd '${PROJECT_DIR}'
source tools/eccodes_env.sh
STEP=\$(sed -n \"\$((SLURM_ARRAY_TASK_ID+1))p\" '${ROWS}/timesteps.txt')
echo \"timestep \${STEP}\"
\${HOME}/.local/bin/uv run python tools/audit/harness.py compare \
    --timestep \"\${STEP}\" --out '${ROWS}/rows_'\"\${STEP}\"'.jsonl'" 2>/dev/null) || out=""
        # stdout only: --parsable prints the id there and warns on stderr, and a
        # loop that captured both never recognised its own success and submitted
        # ten duplicate arrays.
        if [[ "${out}" =~ ^[0-9]+$ ]]; then
            printf '%s' "${out}"
            return 0
        fi
        sleep 60
    done
    return 1
}

for round in $(seq 1 "${MAX_ROUNDS}"); do
    [ -e "${STOP}" ] && { say "STOP flag present; stopping."; exit 0; }
    SPEC=$(missing_indices)
    if [ -z "${SPEC}" ]; then
        say "COMPLETE: all ${N} timesteps hold 246 unique rows"
        "${HOME}/.local/bin/uv" run --no-project python - "${ROWS}" <<'PY'
import collections, glob, json, os, sys
rows = sys.argv[1]
total = 0
fails = collections.Counter()
for path in glob.glob(os.path.join(rows, 'rows_*.jsonl')):
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        total += 1
        for failure in row['leg_a']['failures']:
            fails[(row['variable'], failure[:60])] += 1
print(f'{total} rows on disk')
print(f'leg A failures: {sum(fails.values())}')
for (var, text), n in fails.most_common():
    print(f'   {var}: {text} x{n}')
PY
        exit 0
    fi
    COUNT=$(awk -F, '{print NF}' <<<"${SPEC}")
    say "round ${round}: ${COUNT} timestep(s) still missing -> ${SPEC}"
    JOB=$(submit_array "${SPEC}") || { say "sbatch refused for an hour; stopping."; exit 1; }
    say "round ${round}: array ${JOB} submitted"
    while :; do
        [ -e "${STOP}" ] && { say "STOP flag; leaving array ${JOB} to finish."; exit 0; }
        sleep 60
        Q=$(squeue -u "${USER}" -h -j "${JOB}" 2>/dev/null | wc -l)
        [ "${Q}" -eq 0 ] && break
    done
    say "round ${round}: array ${JOB} drained"
done
say "gave up after ${MAX_ROUNDS} rounds; $(missing_indices) still missing"
exit 1
