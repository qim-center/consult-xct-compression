#BSUB -q hpc
### One array element per dataset, see DATASETS below.
#BSUB -J dicom_tests[1-3]
#BSUB -n 18
#BSUB -W 12:00
### Set specific host group for consistency
### Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpccascadelaker"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6226R && maxmem > 500GB]"
### Memory is dominated by the 3D SSIM, not by the codec under test: ~102 GB
### peak for a 1000^3 volume (see submit_ome_zarr_test_single.sh), on top of the
### reference 2 GB + decoded 2 GB (both in shared memory) + the in-memory DICOM
### stack <= 2 GB + 18 workers holding one batch of slices each.
### 18 x 7 GB = 126 GB leaves headroom; the host group has > 500 GB.
#BSUB -R "rusage[mem=7GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/dicom_tests.%J.%I.out
#BSUB -e logs/dicom_tests.%J.%I.err


export PYTHONUNBUFFERED=1

DATASETS=(Canislupus_CZM_712 Canislupus_BM_2600 Canislupus_UAM_18197)

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time, e.g.
###   COMPTEST_TARGET_CONFIGS="dicom_jpegls_near025 dicom_j2k_cr008" \
###       bsub < data_gathering/02a_submit_dicom_tests.sh
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
export COMPTEST_N_WORKERS="${COMPTEST_N_WORKERS:-${LSB_DJOB_NUMPROC:-18}}"

### Submit from the repo root: logs/ above and the path below are relative to
### it. The script itself resolves its own paths.
pixi run python data_gathering/02a_dicom_compression_tests.py
