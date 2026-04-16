#!/bin/bash
#SBATCH --array=0-23
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --job-name=chapter_conv
#
# Convert a single hourly wrfout to GRIB1 format.
# SLURM_ARRAY_TASK_ID (0-23) maps to the hour.
#
# Required env vars (set via --export at submission):
#   TARGET_DATE   - target date in YYYY-MM-DD format
#   WRFOUT_DIR    - directory containing wrfout files for this date
#   GRIB_DIR      - output directory for GRIB files
#   PROJECT_DIR   - path to CHAPTER repo (for convert_to_pressure_levels.py)
#   GRIB_TEMPLATE - output filename template (Python .format() style)

set -euo pipefail

HOUR=$(printf "%02d" "${SLURM_ARRAY_TASK_ID}")
DATE_COMPACT=$(echo "${TARGET_DATE}" | tr -d '-')

INPUT="${WRFOUT_DIR}/wrfout_d02_${TARGET_DATE}_${HOUR}:00:00"
OUTPUT="${GRIB_DIR}/${GRIB_TEMPLATE}"

# Expand template variables in output filename
YEAR="${TARGET_DATE:0:4}"
OUTPUT=$(echo "${OUTPUT}" | sed "s/{year}/${YEAR}/g; s/{date_compact}/${DATE_COMPACT}/g; s/{hour:02d}/${HOUR}/g")

echo "=== CHAPTER convert_day ==="
echo "Date:   ${TARGET_DATE}"
echo "Hour:   ${HOUR}"
echo "Input:  ${INPUT}"
echo "Output: ${OUTPUT}"
echo ""

# Re-entrancy: skip if output already exists
if [ -f "${OUTPUT}" ]; then
    echo "Output GRIB already exists, skipping."
    exit 0
fi

# Check input exists
if [ ! -f "${INPUT}" ]; then
    echo "ERROR: Input wrfout not found: ${INPUT}"
    exit 1
fi

cd "${PROJECT_DIR}"

uv run python convert_to_pressure_levels.py \
    --input "${INPUT}" \
    --output "${OUTPUT}"

EXITCODE=$?

if [ ${EXITCODE} -eq 0 ]; then
    echo ""
    echo "Conversion successful. Cleaning up wrfout..."
    rm -f "${INPUT}"
    echo "Deleted: ${INPUT}"
else
    echo ""
    echo "ERROR: Conversion failed with exit code ${EXITCODE}"
    exit ${EXITCODE}
fi
