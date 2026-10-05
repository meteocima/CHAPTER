#!/bin/bash
# Submit tests/test_anemoi_dataset.py as a SLURM job: the dataset build is far past the
# login node's 600 s CPU limit. Extra arguments go to pytest (e.g. -k grid).
# Runs in the anemoi/ environment, not the conversion one (see anemoi/pyproject.toml).
# CHAPTER_ANEMOI_REBUILD=1 forces the dataset to be rebuilt even if nothing changed.
set -euo pipefail
cd "$(dirname "$0")/.."
TEST_DIR=/leonardo_work/AIFPT_AILAMIT/CHAPTER/anemoi_test
mkdir -p "$TEST_DIR"
PYTEST_ARGS=""
[ $# -gt 0 ] && PYTEST_ARGS=$(printf '%q ' "$@")
sbatch --partition dcgp_usr_prod --account aifpt_ailamit_0 --nodes 1 --ntasks 1 \
  --cpus-per-task 1 --mem 64G --time 02:00:00 --job-name anemoi_test \
  --output "$TEST_DIR/anemoi_test_%j.out" \
  --export "ALL,CHAPTER_ANEMOI_REBUILD=${CHAPTER_ANEMOI_REBUILD:-0}" \
  --wrap "cd $PWD
source tools/eccodes_env.sh
export CHAPTER_ANEMOI_TEST_DIR=$TEST_DIR
/usr/bin/time -v \$HOME/.local/bin/uv run --project anemoi pytest -v -rs tests/test_anemoi_dataset.py $PYTEST_ARGS"
