#!/bin/bash
# The dead-field census over the whole audit sample: one SLURM task per timestep.
#
#     bash tools/audit/submit_census.sh [--after <jobid>]
#
# Every one of the 200 variables in every one of the 34 wrfout, because the
# census has to be complete rather than a re-check of the sixteen fields already
# suspected. That means reading each file whole -- 8.51 GiB of variables per
# timestep, ~290 GiB over the sample -- which is why it is an array and not a
# loop, and why it asks for 16 GB: the largest single variable is 423 MiB and
# several are read back to back.
#
# Read-only: it opens the wrfout and writes JSON into its own directory.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${WORK_DIR:-/leonardo_work/AIFPT_AILAMIT/CHAPTER}"
CENSUS="${WORK}/audit_census"
LOGS="${WORK}/logs"

mkdir -p "${CENSUS}" "${LOGS}"

DEP=""
if [ "${1:-}" = "--after" ] && [ -n "${2:-}" ]; then
    DEP="--dependency=afterany:$2"
    echo "will start after job $2"
fi

mapfile -t STEPS < <(cd "${PROJECT_DIR}" && "${HOME}/.local/bin/uv" run python -c "
import sys; sys.path.insert(0, 'tools/audit')
from dead_fields import sample_timesteps
print('\n'.join(sample_timesteps()))
" 2>/dev/null)
N=${#STEPS[@]}
[ "${N}" -gt 0 ] || { echo "no timesteps read from the sample" >&2; exit 1; }
printf '%s\n' "${STEPS[@]}" > "${CENSUS}/timesteps.txt"

JOB=$(sbatch --parsable ${DEP} \
    --job-name audit_census \
    --partition dcgp_usr_prod --account aifpt_ailamit_0 \
    --nodes 1 --ntasks 1 --cpus-per-task 1 --mem 16G --time 02:00:00 \
    --array "0-$((N-1))%17" \
    --output "${LOGS}/audit_census_%A_%a.out" \
    --wrap "set -euo pipefail
cd '${PROJECT_DIR}'
STEP=\$(sed -n \"\$((SLURM_ARRAY_TASK_ID+1))p\" '${CENSUS}/timesteps.txt')
/usr/bin/time -v \${HOME}/.local/bin/uv run python tools/audit/dead_fields.py scan \
    --timestep \"\${STEP}\" --out '${CENSUS}/census_'\"\${STEP}\"'.json'")

echo "submitted array ${JOB} over ${N} timesteps"
echo "  census ${CENSUS}/census_<timestep>.json"
echo "  then   uv run python tools/audit/dead_fields.py aggregate --dir ${CENSUS}"
