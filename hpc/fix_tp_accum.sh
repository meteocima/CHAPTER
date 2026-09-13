#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=06:00:00
#SBATCH --partition=dcgp_usr_prod
#SBATCH --account=aifpt_ailamit_0
#SBATCH --job-name=fix_tp
#
# Refer tp of already-produced GRIBs to 00Z of the same day (hpc/fix_tp_accum.py),
# one month per array task. Re-entrant and idempotent: re-submitting is safe.
#
# Submit (months listed explicitly, one array index each):
#   MONTHS="2024-10 2024-11 2024-12 2025-01 2025-02 2025-03 2025-04 2025-05 2025-06"
#   sbatch --array=0-8%3 --export=ALL,MONTHS="$MONTHS",PROJECT_DIR=$PWD \
#          --output=/leonardo_work/AIFPT_AILAMIT/CHAPTER/logs/fix_tp_%A_%a.out hpc/fix_tp_accum.sh
#
# Extra args for fix_tp_accum.py can be passed via FIX_ARGS (e.g. "--dry-run").

set -euo pipefail

read -r -a MONTH_LIST <<< "${MONTHS:?MONTHS not set}"
MONTH="${MONTH_LIST[${SLURM_ARRAY_TASK_ID:-0}]}"

cd "${PROJECT_DIR:?PROJECT_DIR not set}"

# Load eccodes C library (built with gcc-12, needs matching runtime) -- as convert_step.sh
module load eccodes/2.34.0--gcc--12.2.0 2>/dev/null
GCC12_RT="/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/gcc-runtime-12.2.0-dqfwf7yjtbtdzllj66jx6suk34ir2ct3/lib"
ECCODES_LIB="/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/eccodes-2.34.0-msheephhj7zirdzmqcfdrf4jat5w545r/lib64"
export LD_PRELOAD="$GCC12_RT/libstdc++.so.6"
export LD_LIBRARY_PATH="$GCC12_RT:$ECCODES_LIB:${LD_LIBRARY_PATH:-}"

echo "=== fix_tp_accum ${MONTH} @ $(hostname) $(date -u +%FT%TZ) ==="
# shellcheck disable=SC2086
uv run python hpc/fix_tp_accum.py --month "${MONTH}" ${FIX_ARGS:-}
