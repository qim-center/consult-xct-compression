#BSUB -q hpc
###BSUB -q qimalma94
#BSUB -J file_stack_tests_variability[1-4]
#BSUB -n 18
#BSUB -W 48:00
### Set specific host group for consistency
### Found using `bmgroup -w -r` and `nodestat -F`
#BSUB -m "rhpccascadelaker"
## These are redundant given hostgroup, but good to have for extra
#BSUB -R "select[avx512 && model == XeonGold6226R && maxmem > 500GB]"
#BSUB -R "rusage[mem=3GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o logs/file_stack_tests.%J.%I.out
#BSUB -e logs/file_stack_tests.%J.%I.err

export PYTHONUNBUFFERED=1
if [[ "${LSB_JOBINDEX}" == "2" ]]; then
    reverse_configs=True
else
    reverse_configs=False
fi
pixi run papermill \
    --log-output \
    -p is_papermill True \
    -p reverse_configs "${reverse_configs}" \
    -p target_configs "CONFIGS_VARIABILITY" \
    -p run_id "variability" \
    projection_file_stack_compression.ipynb \
    output/projection_file_stack_compression_$(date '+%d-%m-%Y_%H%M%S').ipynb
