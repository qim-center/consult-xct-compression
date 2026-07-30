#BSUB -q hpc
###BSUB -q qimalma94
#BSUB -J file_stack_tests
#BSUB -n 18
#BSUB -W 48:00
#BSUB -R "rusage[mem=3GB]"
#BSUB -R "span[hosts=1]"
#BSUB -R "select[avx512 && model == XeonGold6226R]"
#BSUB -o logs/file_stack_tests.%J.%I.out
#BSUB -e logs/file_stack_tests.%J.%I.err

export PYTHONUNBUFFERED=1
pixi run papermill --log-output projection_file_stack_compression.ipynb output/projection_file_stack_compression_$(date '+%d-%m-%Y_%H%M%S').ipynb
