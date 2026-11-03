#!/bin/bash
### Submit from anywhere with
###   bash data_gathering/03b_submit_zarr_lossless_tests.sh [extra bsub options]
### e.g. `-J "zarr_lossless_tests[3,13]"` to rerun only some elements (see JOBS
### below). It hands this same file to bsub with the repo root as the job's
### working directory and absolute log paths (see the end of the #BSUB block). Run
### it with the same COMPTEST_RUN_ID as 03a_submit_dicom_lossless_tests.sh.
#BSUB -q hpc
### One array element per dataset x codec family group, see JOBS below.
#BSUB -J zarr_lossless_tests[1-27]
#BSUB -n 8
### Estimated at under 15 min per group on 8 cores, from one slab of one dataset.
#BSUB -W 2:00
### Set specific host group for consistency: the same CPU model as the lossy runs
### and the DICOM lossless tests, so their timings compare.
#BSUB -m "rhpcice"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6342 && maxmem > 500GB]"
### No SSIM, so no ~100 GB peak: the reference (2 GB uint16 or 4 GB float32), the
### decoded volume and the in-memory array, which is about the volume's size for
### RLE on float32. 8 x 3 GB = 24 GB leaves headroom.
#BSUB -R "rusage[mem=3GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/zarr_lossless_tests.%J.%I.out
#BSUB -e logs/zarr_lossless_tests.%J.%I.err

set -euo pipefail

### Outside LSF: submit this file. Command-line options override the #BSUB
### ones above, and the job inherits this environment, COMPTEST_* included.
if [[ -z "${LSB_JOBID:-}" ]]; then
    REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    mkdir -p "$REPO_DIR/logs"

    # Bring the environment up to date once, here. Array elements that start
    # together would otherwise each try to update it and collide.
    (cd "$REPO_DIR" && pixi install)

    # Fixed here rather than in each element, so they all share one run
    # directory even if they start on different days.
    export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-$(date +%Y-%m-%d)}"
    echo "COMPTEST_RUN_ID=$COMPTEST_RUN_ID"

    # -env all: this cluster's LSF does not hand the submitting environment to
    # the job otherwise, and COMPTEST_* overrides would silently not apply.
    exec bsub \
        -env "all" \
        -cwd "$REPO_DIR" \
        -o "$REPO_DIR/logs/zarr_lossless_tests.%J.%I.out" \
        -e "$REPO_DIR/logs/zarr_lossless_tests.%J.%I.err" \
        "$@" \
        < "${BASH_SOURCE[0]}"
fi

### Inside LSF: the working directory is the repo root when submitted as above.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

export PYTHONUNBUFFERED=1

DATASETS=(Canislupus_CZM_712 Canislupus_BM_2600 Canislupus_UAM_18197)
### Codec families run together in one element, split so that no element is much
### longer than the others.
FAMILY_GROUPS=(
    "jpegxl_u16"
    "jpegxl_f32"
    "lzma_u16"
    "lzma_f32"
    "zstd_u16 deflate_u16 lzw_u16 rle_u16"
    "zstd_f32 deflate_f32 lzw_f32 rle_f32"
    "jpegls j2k htj2k jpegxr jpeg png"
    "lerc_u16 pcodec_u16"
    "lerc_f32 pcodec_f32 zfp sz3"
)

### Element i (1-based) is dataset (i-1) / 9, family group (i-1) % 9:
### 1-9 are the first dataset, 10-18 the second, 19-27 the third.
JOB=$((LSB_JOBINDEX - 1))
N_GROUPS=${#FAMILY_GROUPS[@]}

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time, e.g.
###   COMPTEST_TARGET_CONFIGS="zarr_png_l9" bash data_gathering/03b_submit_zarr_lossless_tests.sh
### All array elements share COMPTEST_RUN_ID, so their results land side by side
### in output/zarr/lossless_<run_id>/<dataset>/.
export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-$(date +%Y-%m-%d)}"
export COMPTEST_IS_BATCH="${COMPTEST_IS_BATCH:-True}"
export COMPTEST_REVERSE_CONFIGS="${COMPTEST_REVERSE_CONFIGS:-False}"
### Space- or comma-separated config names; empty runs every config of the group.
export COMPTEST_TARGET_CONFIGS="${COMPTEST_TARGET_CONFIGS:-}"
export COMPTEST_U16_VARIANT="${COMPTEST_U16_VARIANT:-u16_1000}"
export COMPTEST_F32_VARIANT="${COMPTEST_F32_VARIANT:-f32_1000}"
export COMPTEST_DATASET="${COMPTEST_DATASET:-${DATASETS[$((JOB / N_GROUPS))]}}"
export COMPTEST_CODEC_FAMILIES="${COMPTEST_CODEC_FAMILIES:-${FAMILY_GROUPS[$((JOB % N_GROUPS))]}}"

### One zarr codec thread per core LSF actually gave the job, otherwise the
### timings are not comparable between runs.
export COMPTEST_N_THREADS="${COMPTEST_N_THREADS:-${LSB_DJOB_NUMPROC:-8}}"

echo "Dataset: $COMPTEST_DATASET, families: $COMPTEST_CODEC_FAMILIES, run: $COMPTEST_RUN_ID"

### --frozen --no-install: use the environment exactly as installed at
### submission, never modify it from inside a job.
pixi run --frozen --no-install python data_gathering/03b_zarr_lossless_tests.py
