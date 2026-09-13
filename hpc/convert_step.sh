#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --job-name=chapter_conv_step
#
# Convert a single hourly wrfout to GRIB1 format (single timestep, non-array).
# Submitted by hpc/fetch_step.sh once the wrfout for the timestep has been fetched.
# Runs on a compute node (e.g. dcgp_usr_prod); no network access required.
#
# Required env vars (set via --export at submission):
#   TARGET_DATE   - target date in YYYY-MM-DD format
#   HOUR          - hour of the timestep, zero-padded (00-23)
#   WRFOUT_DIR    - directory containing the wrfout file for this timestep
#   GRIB_DIR      - output directory for GRIB files
#   PROJECT_DIR   - path to CHAPTER repo (for convert_to_pressure_levels.py)
#   GRIB_TEMPLATE - output filename template (Python .format() style)
#   ACCUM_REF_DIR - (optional) 00Z reference sidecars for accumulated fields
#                   (accum_ref.py); default: <GRIB_DIR>/../accum_ref

set -euo pipefail

HOUR=$(printf "%02d" "$((10#${HOUR}))")
DATE_COMPACT=$(echo "${TARGET_DATE}" | tr -d '-')

INPUT="${WRFOUT_DIR}/wrfout_d02_${TARGET_DATE}_${HOUR}:00:00"

# Output goes under a YYYY/MM tree below GRIB_DIR
YEAR="${TARGET_DATE:0:4}"
MONTH="${TARGET_DATE:5:2}"
OUTPUT="${GRIB_DIR}/${YEAR}/${MONTH}/${GRIB_TEMPLATE}"

# Expand template variables in output filename
OUTPUT=$(echo "${OUTPUT}" | sed "s/{year}/${YEAR}/g; s/{date_compact}/${DATE_COMPACT}/g; s/{hour:02d}/${HOUR}/g")
mkdir -p "$(dirname "${OUTPUT}")"
# tp is referred to 00Z of the same day: the 00Z fields live in this sidecar
ACCUM_REF_DIR="${ACCUM_REF_DIR:-$(dirname "${GRIB_DIR%/}")/accum_ref}"
ACCUM_REF="${ACCUM_REF_DIR}/${YEAR}/${MONTH}/accum_ref_${DATE_COMPACT}.npz"
TMPOUT="${OUTPUT}.tmp"

# Clean up partial output on failure
trap 'rm -f "${TMPOUT}"' EXIT

echo "=== CHAPTER convert_step ==="
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

# Load eccodes C library (built with gcc-12, needs matching runtime)
module load eccodes/2.34.0--gcc--12.2.0 2>/dev/null
GCC12_RT="/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/gcc-runtime-12.2.0-dqfwf7yjtbtdzllj66jx6suk34ir2ct3/lib"
ECCODES_LIB="/leonardo/prod/spack/06/install/0.22/linux-rhel8-icelake/gcc-12.2.0/eccodes-2.34.0-msheephhj7zirdzmqcfdrf4jat5w545r/lib64"
export LD_PRELOAD="$GCC12_RT/libstdc++.so.6"
export LD_LIBRARY_PATH="$GCC12_RT:$ECCODES_LIB:${LD_LIBRARY_PATH:-}"

uv run python convert_to_pressure_levels.py \
    --input "${INPUT}" \
    --output "${TMPOUT}" \
    --accum-ref-dir "${ACCUM_REF_DIR}"

# Atomic rename on success
mv "${TMPOUT}" "${OUTPUT}"

echo ""
# Convert jobs of the same day run independently and in any order, and every
# non-00Z hour needs the 00Z fields: never delete the 00Z wrfout unless its
# sidecar exists (the converter writes it when the input is 00Z).
if [ "${HOUR}" = "00" ] && [ ! -s "${ACCUM_REF}" ]; then
    echo "ERROR: 00Z reference sidecar missing (${ACCUM_REF}); keeping ${INPUT}"
    exit 1
fi
echo "Conversion successful. Cleaning up wrfout..."
timeout 60 rm -f "${INPUT}"
echo "Deleted: ${INPUT}"
