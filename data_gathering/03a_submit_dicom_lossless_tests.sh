#!/bin/bash
### Submit from anywhere with
###   bash data_gathering/03a_submit_dicom_lossless_tests.sh [extra bsub options]
### e.g. `-J "dicom_lossless_tests[2-3]"` to rerun only some datasets. It hands
### this same file to bsub with the repo root as the job's working directory and
### absolute log paths (see the end of the #BSUB block). Run it with the same
### COMPTEST_RUN_ID as 03b_submit_zarr_lossless_tests.sh.
#BSUB -q hpc
### One array element per dataset, see DATASETS below.
#BSUB -J dicom_lossless_tests[1-3]
#BSUB -n 8
### Three configurations of well under a minute each, once the volume is read.
#BSUB -W 1:00
### Set specific host group for consistency: the same CPU model as the lossy runs
### and the OME-Zarr lossless tests, so their timings compare.
#BSUB -m "rhpcice"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6342 && maxmem > 500GB]"
### No SSIM, so no ~100 GB peak: the reference 2 GB + decoded 2 GB (both in shared
### memory) + the in-memory DICOM stack, about 2 GB for RLE + 8 workers.
#BSUB -R "rusage[mem=3GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/dicom_lossless_tests.%J.%I.out
#BSUB -e logs/dicom_lossless_tests.%J.%I.err

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
        -o "$REPO_DIR/logs/dicom_lossless_tests.%J.%I.out" \
        -e "$REPO_DIR/logs/dicom_lossless_tests.%J.%I.err" \
        "$@" \
        < "${BASH_SOURCE[0]}"
fi

### Inside LSF: the working directory is the repo root when submitted as above.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

export PYTHONUNBUFFERED=1

DATASETS=(Canislupus_CZM_712 Canislupus_BM_2600 Canislupus_UAM_18197)

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time. All array elements share COMPTEST_RUN_ID, so
### their results land side by side in output/dicom/lossless_<run_id>/<dataset>/.
export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-$(date +%Y-%m-%d)}"
export COMPTEST_IS_BATCH="${COMPTEST_IS_BATCH:-True}"
export COMPTEST_REVERSE_CONFIGS="${COMPTEST_REVERSE_CONFIGS:-False}"
### Space- or comma-separated config names; empty runs every config.
export COMPTEST_TARGET_CONFIGS="${COMPTEST_TARGET_CONFIGS:-}"
export COMPTEST_DATA_VARIANT="${COMPTEST_DATA_VARIANT:-u16_1000}"
export COMPTEST_DATASET="${COMPTEST_DATASET:-${DATASETS[$((LSB_JOBINDEX - 1))]}}"

### One worker process per core LSF actually gave the job, otherwise the
### timings are not comparable between runs.
export COMPTEST_N_WORKERS="${COMPTEST_N_WORKERS:-${LSB_DJOB_NUMPROC:-8}}"

### --frozen --no-install: use the environment exactly as installed at
### submission, never modify it from inside a job.
pixi run --frozen --no-install python data_gathering/03a_dicom_lossless_tests.py
