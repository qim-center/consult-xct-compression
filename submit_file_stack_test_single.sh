#BSUB -q hpc
###BSUB -J file_stack_test_jpegxl
#BSUB -J file_stack_tests
#BSUB -n 18
#BSUB -W 48:00
### Set specific host group for consistency
### Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpccascadelaker"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6226R && maxmem > 500GB]"
#BSUB -R "rusage[mem=5GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/file_stack_test_jpegxl.%J.%I.out
#BSUB -e logs/file_stack_test_jpegxl.%J.%I.err


export PYTHONUNBUFFERED=1
pixi run papermill \
    --log-output \
    -p is_papermill True \
    -p reverse_configs "${reverse_configs}" \
    -p target_configs "TIFFFILE_JPEGXL_LOSSY_CONFIGS" \
    -p "run_id" "2026-08-03" \
    projection_file_stack_compression.ipynb \
    output/projection_file_stack_compression_$(date '+%d-%m-%Y_%H%M%S').ipynb
