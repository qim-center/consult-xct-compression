#!/bin/bash
### Submit from anywhere with
###   bash data_gathering/02a_submit_dicom_tests.sh [extra bsub options]
### e.g. `-J "dicom_tests[2-3]"` to rerun only some datasets. It hands this same file to bsub with the repo root as the job's working
### directory and absolute log paths (see the end of the #BSUB block). A plain
### `bsub < data_gathering/02a_submit_dicom_tests.sh` also works, but only from
### the repo root: LSF resolves the relative -o/-e below against the submission
### directory, and #BSUB lines cannot expand variables to do better.
#BSUB -q hpc
### One array element per dataset, see DATASETS below.
#BSUB -J dicom_tests[1-3]
#BSUB -n 8
### SSIM + MS-SSIM take ~25 min per lossy config at 8 cores, 17 lossy configs.
#BSUB -W 16:00
### Set specific host group for consistency: every dataset, and the OME-Zarr
### reruns, on the same CPU model so their timings compare. rhpcice (4 nodes,
### 48 cores, 503 GB) has far more free cores than rhpccascadelaker.
### Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpcice"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6342 && maxmem > 500GB]"
### Memory is dominated by the 3D SSIM, not by the codec under test: ~102 GB
### peak for a 1000^3 volume (see submit_ome_zarr_test_single.sh), on top of the
### reference 2 GB + decoded 2 GB (both in shared memory) + the in-memory DICOM
### stack <= 2 GB + 8 workers holding one batch of slices each. MS-SSIM peaks
### at the same ~100 GB as SSIM.
### 8 x 17 GB = 136 GB leaves headroom; the host group has > 500 GB.
#BSUB -R "rusage[mem=17GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/dicom_tests.%J.%I.out
#BSUB -e logs/dicom_tests.%J.%I.err

set -euo pipefail

### Outside LSF: submit this file. Command-line options override the #BSUB
### ones above, and the job inherits this environment, COMPTEST_* included.
if [[ -z "${LSB_JOBID:-}" ]]; then
    REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    mkdir -p "$REPO_DIR/logs"

    # Bring the environment up to date once, here. Array elements that start
    # together would otherwise each try to update it and collide.
    (cd "$REPO_DIR" && pixi install)

    # -env all: this cluster's LSF does not hand the submitting environment to
    # the job otherwise, and COMPTEST_* overrides would silently not apply.
    exec bsub \
        -env "all" \
        -cwd "$REPO_DIR" \
        -o "$REPO_DIR/logs/dicom_tests.%J.%I.out" \
        -e "$REPO_DIR/logs/dicom_tests.%J.%I.err" \
        "$@" \
        < "${BASH_SOURCE[0]}"
fi

### Inside LSF: the working directory is the repo root when submitted as above.
### For a plain `bsub <` from elsewhere in the repo, find the root rather than
### fail on the relative path below.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

export PYTHONUNBUFFERED=1

DATASETS=(Canislupus_CZM_712 Canislupus_BM_2600 Canislupus_UAM_18197)

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time, e.g.
###   COMPTEST_TARGET_CONFIGS="dicom_jpegls_near025 dicom_j2k_cr008" \
###       bash data_gathering/02a_submit_dicom_tests.sh
### All array elements share COMPTEST_RUN_ID, so their results land side by side
### in output/dicom/<category>_<run_id>/<dataset>/.
export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-2026-10-05}"
export COMPTEST_IS_BATCH="${COMPTEST_IS_BATCH:-True}"
export COMPTEST_REVERSE_CONFIGS="${COMPTEST_REVERSE_CONFIGS:-False}"
### Space- or comma-separated config names; empty runs every config.
export COMPTEST_TARGET_CONFIGS="${COMPTEST_TARGET_CONFIGS:-}"
export COMPTEST_DATA_VARIANT="${COMPTEST_DATA_VARIANT:-u16_1000}"
export COMPTEST_DATASET="${COMPTEST_DATASET:-${DATASETS[$((LSB_JOBINDEX - 1))]}}"

### Keep the compressed DICOM stack of each configuration. These are the files
### themselves, so a full run is on the order of the volume size per lossless
### configuration and less for the lossy ones, per dataset. They go to the
### project scratch space, not to the repo's output/ directory.
export COMPTEST_STORE_DICOMS="${COMPTEST_STORE_DICOMS:-True}"
### Stacks land in <DICOMS_DIR>/<category>_<run_id>/<dataset>/<config name>/.
### Empty uses the default, naturarv3d_compression_study/compression_tests/dicom_stacks.
export COMPTEST_DICOMS_DIR="${COMPTEST_DICOMS_DIR:-}"

### One worker process per core LSF actually gave the job, otherwise the
### timings are not comparable between runs.
export COMPTEST_N_WORKERS="${COMPTEST_N_WORKERS:-${LSB_DJOB_NUMPROC:-8}}"

### --frozen --no-install: use the environment exactly as installed at
### submission, never modify it from inside a job.
pixi run --frozen --no-install python data_gathering/02a_dicom_compression_tests.py
