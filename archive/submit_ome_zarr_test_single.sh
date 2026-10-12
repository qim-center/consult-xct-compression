#BSUB -q hpc
#BSUB -J ome_zarr_tests
#BSUB -n 18
#BSUB -W 12:00
### Set specific host group for consistency
### Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpccascadelaker"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6226R && maxmem > 500GB]"
### Memory is dominated by the 3D SSIM, not by the codec under test. picax
### computes it in float64 over the whole volume, and measurements at 25M, 50M
### and 75M voxels scale linearly to ~102 GB peak for a 1000^3 volume, on top of
### the reference volume 2 GB + decoded volume 2 GB + in-memory store ~2 GB.
### 18 x 7 GB = 126 GB leaves headroom; the host group has > 500 GB.
#BSUB -R "rusage[mem=7GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/ome_zarr_tests.%J.%I.out
#BSUB -e logs/ome_zarr_tests.%J.%I.err


export PYTHONUNBUFFERED=1

### This is a jupytext script, not an .ipynb, so it takes its parameters from
### the environment rather than from papermill. Everything below can be
### overridden at submission time, e.g.
###   COMPTEST_TARGET_SERIALIZERS="jpegls_nll_008 jpegls_nll_016" \
###       bsub < submit_ome_zarr_test_single.sh
export COMPTEST_RUN_ID="${COMPTEST_RUN_ID:-2026-09-01}"
export COMPTEST_IS_BATCH="${COMPTEST_IS_BATCH:-True}"
export COMPTEST_REVERSE_CONFIGS="${COMPTEST_REVERSE_CONFIGS:-False}"
### Space- or comma-separated serializer names; empty runs every store found.
export COMPTEST_TARGET_SERIALIZERS="${COMPTEST_TARGET_SERIALIZERS:-}"
export COMPTEST_OUTPUT_ID="${COMPTEST_OUTPUT_ID:-OME-Zarr_quality}"
export COMPTEST_DATASET="${COMPTEST_DATASET:-Canislupus_CZM_712}"

### Keep the decompressed volume each configuration produced, for viewing and
### differencing after the fact. One volume per configuration, so a full run of
### 20 configurations writes on the order of 20-40 GB: these go to the project
### scratch space, not to the repo's output/ directory. Set to False to skip.
export COMPTEST_STORE_VOLUMES="${COMPTEST_STORE_VOLUMES:-True}"
### Volumes land in <VOLUMES_DIR>/<category>_<timestamp>_<host>_<run_id>/<dataset>/
### <config name>.zarr - the same run/dataset coordinates as the JSON results.
### Empty uses the default, compression_tests/decompressed_volumes on scratch.
export COMPTEST_VOLUMES_DIR="${COMPTEST_VOLUMES_DIR:-}"

### Pin zarr's codec threads to the cores LSF actually gave the job, otherwise
### it uses the whole node's CPU count and the timings are not comparable.
export COMPTEST_N_THREADS="${COMPTEST_N_THREADS:-${LSB_DJOB_NUMPROC:-18}}"

### The script resolves its own paths, so it can be run from the submission
### directory. Results land in output/ome-zarr/<category>_<timestamp>_<host>_<run_id>/.
pixi run python notebooks/2026-09-01_ome_zarr_compression_tests.py
