#!/bin/bash
# Measure the whole audit sample with the harness: one SLURM task per timestep.
#
#     bash tools/audit/submit_harness.sh            # submit the array
#     bash tools/audit/submit_harness.sh --dry-run  # print the plan only
#
# WHY ONE TASK PER TIMESTEP AND ALL 90 VARIABLES AT ONCE, rather than one run per
# family. The cost is reading and unpacking the GRIB, not the arithmetic --
# measured 350.9 s of system time against 22.8 s of user on a pressure-level
# family -- so a single streaming pass over each 703 MB file covers all 246
# messages for barely more than one family costs alone. Eight family tickets then
# start from rows already on disk, all produced by the same pass, instead of each
# session recomputing its own and the numbers drifting apart.
#
# WHY IT IS A JOB AND NOT A LOGIN-NODE LOOP. One timestep is ~450 s of CPU against
# the login node's 600 s per process. One would fit; thirty-four would be killed.
#
# Read-only against the archive: it opens GRIB and wrfout and writes only JSONL
# into its own directory.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${WORK_DIR:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
ROWS="${WORK}/audit_rows"
LOGS="${WORK}/logs"
ACCOUNT="aifpt_ailamit_0"
PARTITION="dcgp_usr_prod"

mkdir -p "${ROWS}" "${LOGS}"

# The sample list comes from docs/audit/sample.md through the harness itself, so
# there is no second copy of it to drift.
mapfile -t STEPS < <(cd "${PROJECT_DIR}" && "${HOME}/.local/bin/uv" run python -c "
import sys; sys.path.insert(0, 'tools/audit')
from harness import sample_timesteps
print('\n'.join(sample_timesteps()))
" 2>/dev/null)

N=${#STEPS[@]}
if [ "${N}" -eq 0 ]; then
    echo "could not read the sample timesteps; is the eccodes env available?" >&2
    exit 1
fi
printf '%s\n' "${STEPS[@]}" > "${ROWS}/timesteps.txt"
echo "${N} timesteps -> ${ROWS}"

if [ "${1:-}" = "--dry-run" ]; then
    echo "would submit: array 0-$((N-1)) on ${PARTITION}, account ${ACCOUNT}"
    printf '  %s\n' "${STEPS[@]}" | head -5
    echo "  ..."
    exit 0
fi

JOB=$(sbatch --parsable \
    --job-name audit_harness \
    --partition "${PARTITION}" --account "${ACCOUNT}" \
    --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 8G --time 01:00:00 \
    --array "0-$((N-1))%17" \
    --output "${LOGS}/audit_harness_%A_%a.out" \
    --wrap "set -euo pipefail
cd '${PROJECT_DIR}'
source tools/eccodes_env.sh
STEP=\$(sed -n \"\$((SLURM_ARRAY_TASK_ID+1))p\" '${ROWS}/timesteps.txt')
echo \"timestep \${STEP}\"
/usr/bin/time -v \${HOME}/.local/bin/uv run python tools/audit/harness.py compare \
    --timestep \"\${STEP}\" --out '${ROWS}/rows_'\"\${STEP}\"'.jsonl'")

echo "submitted array ${JOB} (0-$((N-1)), 17 at a time)"
echo "  rows   ${ROWS}/rows_<timestep>.jsonl"
echo "  logs   ${LOGS}/audit_harness_${JOB}_*.out"
echo
echo "when it is done, check completeness before believing it:"
echo "  grep -h 'expected rows' ${LOGS}/audit_harness_${JOB}_*.out | sort | uniq -c"
