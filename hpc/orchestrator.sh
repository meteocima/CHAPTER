#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --job-name=chapter_orch
#
# Orchestrator SLURM wrapper: submits fetch + convert jobs for all dates.
# Invoked by submit_pipeline.py in entry mode.
#
# Required env vars:
#   PROJECT_DIR     - path to CHAPTER repo
#   HYDRA_OVERRIDES - Hydra CLI overrides to pass through

set -euo pipefail

cd "${PROJECT_DIR}"

echo "=== CHAPTER Orchestrator ==="
echo "Project dir:     ${PROJECT_DIR}"
echo "Hydra overrides: ${HYDRA_OVERRIDES:-none}"
echo ""

# Run the pipeline in worker mode
uv run python hpc/submit_pipeline.py --worker ${HYDRA_OVERRIDES:-}
