#BSUB -q hpc
### This should be 1 to {the numnber returned by --num-indices}
#BSUB -J lossless_projection_tests[1-7]
#BSUB -n 16
#BSUB -W 01:00
#BSUB -R "rusage[mem=2GB]"
#BSUB -R "span[hosts=1]"
#BSUB -R "select[avx512 && model == XeonGold6342]"
#BSUB -o logs/lossless_projection_tests.%J.%I.out
#BSUB -e logs/lossless_projection_tests.%J.%I.err

index=$((LSB_JOBINDEX - 1))
pixi run comptest \
    lossless_curated \
    $index \
    --dataset-path /dtu/3d-imaging-center/projects/2026_DANFIX_201/analysis/compression/datasets/Canislupus_CZM_712 \
    --run-id "2026-07-27T10:43:35+02:00"
