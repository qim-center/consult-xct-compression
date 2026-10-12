#!/bin/bash
### Submit from anywhere with
###   bash data_gathering/02b_submit_zarr_tests.sh [extra bsub options]
### e.g. `-J "zarr_tests[3,13]"` to rerun only some elements (see JOBS below). It
### hands this same file to bsub with the repo root as the job's working
### directory and absolute log paths (see the end of the #BSUB block). A plain
### `bsub < data_gathering/02b_submit_zarr_tests.sh` also works, but only from
### the repo root: LSF resolves the relative -o/-e below against the submission
### directory, and #BSUB lines cannot expand variables to do better.
#BSUB -q hpc
### One array element per dataset x codec family group, see JOBS below.
#BSUB -J zarr_tests[1-30]
#BSUB -n 8
### SSIM + MS-SSIM take ~18 min per lossy config at 8 cores; the largest group
### (SZ3, 3D and per slice) has 14 lossy configs, JPEG-LS 11, JPEG-XL 9, the
### others 7.
#BSUB -W 6:00
### Set specific host group for consistency: the same CPU model as the DICOM
### tests, so their timings compare. Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpcice"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6342 && maxmem > 500GB]"
### Memory is dominated by the 3D SSIM, not by the codec under test: ~100 GB
### peak for a 1000^3 volume, on top of the reference (2 GB uint16 or 4 GB
### float32), the decoded volume and the in-memory array. MS-SSIM peaks at the
### same ~100 GB as SSIM.
### 8 x 17 GB = 136 GB leaves headroom; the host group has > 500 GB.
#BSUB -R "rusage[mem=17GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/zarr_tests.%J.%I.out
#BSUB -e logs/zarr_tests.%J.%I.err

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
        -o "$REPO_DIR/logs/zarr_tests.%J.%I.out" \
        -e "$REPO_DIR/logs/zarr_tests.%J.%I.err" \
        "$@" \
        < "${BASH_SOURCE[0]}"
fi

### Inside LSF: the working directory is the repo root when submitted as above.
### For a plain `bsub <` from elsewhere in the repo, find the root rather than
### fail on the relative path below.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

export PYTHONUNBUFFERED=1

DATASETS=(Canislupus_CZM_712 Canislupus_BM_2600 Canislupus_UAM_18197)
### Codec families run together in one element. Pcodec is lossless, so it skips
### the SSIM and takes seconds: it rides along with a 3D family of its dtype.
FAMILY_GROUPS=(
    "jpegls"
    "j2k"
    "htj2k"
    "jpegxl_u16"
    "jpegxl_f32"
    "lerc_slice"
    "lerc_3d pcodec_u16"
    "zfp pcodec_f32"
    "sz3 sz3_slice"
    "sperr"
)

### Element i (1-based) is dataset (i-1) / 10, family group (i-1) % 10:
### 1-10 are the first dataset, 11-20 the second, 21-30 the third.
JOB=$((LSB_JOBINDEX - 1))
N_GROUPS=${#FAMILY_GROUPS[@]}

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time, e.g.
###   COMPTEST_TARGET_CONFIGS="zarr_jpegls_near025" bash data_gathering/02b_submit_zarr_tests.sh
### All array elements share COMPTEST_RUN_ID, so their results land side by side
### in output/zarr/<category>_<run_id>/<dataset>/.
export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-$(date +%Y-%m-%d)}"
export COMPTEST_IS_BATCH="${COMPTEST_IS_BATCH:-True}"
export COMPTEST_REVERSE_CONFIGS="${COMPTEST_REVERSE_CONFIGS:-False}"
### Space- or comma-separated config names; empty runs every config of the group.
export COMPTEST_TARGET_CONFIGS="${COMPTEST_TARGET_CONFIGS:-}"
### The 3D SSIM and MS-SSIM, ~8 min each per config: "ssim ms_ssim" (empty, the
### default), one of them, or "none". PSNR and the maximum error always run.
export COMPTEST_METRICS="${COMPTEST_METRICS:-}"
export COMPTEST_U16_VARIANT="${COMPTEST_U16_VARIANT:-u16_1000}"
export COMPTEST_F32_VARIANT="${COMPTEST_F32_VARIANT:-f32_1000}"
export COMPTEST_DATASET="${COMPTEST_DATASET:-${DATASETS[$((JOB / N_GROUPS))]}}"
export COMPTEST_CODEC_FAMILIES="${COMPTEST_CODEC_FAMILIES:-${FAMILY_GROUPS[$((JOB % N_GROUPS))]}}"

### Keep the compressed array of each configuration, on the project scratch
### space rather than in the repo's output/ directory. Off by default.
export COMPTEST_STORE_ZARRS="${COMPTEST_STORE_ZARRS:-False}"
### Or only some configurations, by name, space- or comma-separated, e.g.
###   COMPTEST_STORE_CONFIGS="zarr_jpegxl_f32_d0.1_e7 zarr_jpegxl_f32_d1_e7"
### Empty uses the script's STORE_CONFIGS_DEFAULT; "none" stores none.
export COMPTEST_STORE_CONFIGS="${COMPTEST_STORE_CONFIGS:-}"
### Arrays land in <ZARRS_DIR>/<category>_<run_id>/<dataset>/<config name>.zarr.
### Empty uses the default, naturarv3d_compression_study/compression_tests/zarr_stores.
export COMPTEST_ZARRS_DIR="${COMPTEST_ZARRS_DIR:-}"

### One zarr codec thread per core LSF actually gave the job, otherwise the
### timings are not comparable between runs.
export COMPTEST_N_THREADS="${COMPTEST_N_THREADS:-${LSB_DJOB_NUMPROC:-8}}"

echo "Dataset: $COMPTEST_DATASET, families: $COMPTEST_CODEC_FAMILIES, run: $COMPTEST_RUN_ID"

### --frozen --no-install: use the environment exactly as installed at
### submission, never modify it from inside a job.
pixi run --frozen --no-install python data_gathering/02b_zarr_compression_tests.py
