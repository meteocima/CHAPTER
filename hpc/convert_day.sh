#!/bin/bash
#SBATCH --array=0-23
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --job-name=chapter_conv
#
# Convert a single hourly wrfout to GRIB2 format.
# SLURM_ARRAY_TASK_ID (0-23) maps to the hour.
#
# Required env vars (set via --export at submission):
#   TARGET_DATE   - target date in YYYY-MM-DD format
#   WRFOUT_DIR    - directory containing wrfout files for this date
#   GRIB_DIR      - output directory for GRIB files
#   PROJECT_DIR   - path to CHAPTER repo (for convert_to_pressure_levels.py)
#   GRIB_TEMPLATE - output filename template (Python .format() style)
#   STATIC_REF_DIR- (optional) geo_em sidecar for the static land fields
#                   (static_ref.py); default: <GRIB_DIR>/../static_v1
#   ACCUM_REF_DIR - (optional) 00Z reference sidecars for accumulated fields
#                   (accum_ref.py); default: <GRIB_DIR>/../accum_ref

set -euo pipefail

HOUR=$(printf "%02d" "${SLURM_ARRAY_TASK_ID}")
DATE_COMPACT=$(echo "${TARGET_DATE}" | tr -d '-')

INPUT="${WRFOUT_DIR}/wrfout_d02_${TARGET_DATE}_${HOUR}:00:00"
OUTPUT="${GRIB_DIR}/${GRIB_TEMPLATE}"

# Expand template variables in output filename
YEAR="${TARGET_DATE:0:4}"
OUTPUT=$(echo "${OUTPUT}" | sed "s/{year}/${YEAR}/g; s/{date_compact}/${DATE_COMPACT}/g; s/{hour:02d}/${HOUR}/g")
TMPOUT="${OUTPUT}.tmp"
# tp is referred to 00Z of the same day: the 00Z fields live in this sidecar
ACCUM_REF_DIR="${ACCUM_REF_DIR:-$(dirname "${GRIB_DIR%/}")/accum_ref}"
ACCUM_REF="${ACCUM_REF_DIR}/${YEAR}/${TARGET_DATE:5:2}/accum_ref_${DATE_COMPACT}.npz"
# cvl/cvh/tvl/tvh/slt/cl/dl come from geo_em, read once into this sidecar
STATIC_REF_DIR="${STATIC_REF_DIR:-$(dirname "${GRIB_DIR%/}")/static_v1}"

# Clean up partial output on failure
trap 'rm -f "${TMPOUT}"' EXIT

echo "=== CHAPTER convert_day ==="
echo "Date:   ${TARGET_DATE}"
echo "Hour:   ${HOUR}"
echo "Input:  ${INPUT}"
echo "Output: ${OUTPUT}"
echo ""

# Re-entrancy: skip only if the existing output is at the CURRENT schema.
# Keying the skip on the file merely EXISTING is what forced a new output tree
# at every schema change (grib -> grib_v2 -> grib_v3), because a wider schema
# written into the old tree silently skipped every hour already converted at
# the narrower one. Counting the messages makes a re-run self-healing instead.
if [ -f "${OUTPUT}" ]; then
    if SCHEMA=$(python3 "${PROJECT_DIR}/hpc/grib_schema_ok.py" "${OUTPUT}"); then
        echo "Output GRIB already exists at the current schema (${SCHEMA}), skipping."
        exit 0
    fi
    echo "SCHEMA_MISMATCH: ${OUTPUT} is ${SCHEMA} messages; reconverting."
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
    --accum-ref-dir "${ACCUM_REF_DIR}" \
    --static-ref-dir "${STATIC_REF_DIR}"

# Atomic rename on success
mv "${TMPOUT}" "${OUTPUT}"

echo ""
# Array tasks run in any order and every non-00Z hour needs the 00Z fields:
# never delete the 00Z wrfout unless its sidecar exists.
if [ "${HOUR}" = "00" ] && [ ! -s "${ACCUM_REF}" ]; then
    echo "ERROR: 00Z reference sidecar missing (${ACCUM_REF}); keeping ${INPUT}"
    exit 1
fi
echo "Conversion successful. Cleaning up wrfout..."
rm -f "${INPUT}"
echo "Deleted: ${INPUT}"
