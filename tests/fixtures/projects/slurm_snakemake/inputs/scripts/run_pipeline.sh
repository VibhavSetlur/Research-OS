#!/usr/bin/env bash
#SBATCH --job-name=brca_rnaseq
#SBATCH --partition=gpu-a100
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/snakemake.%j.out
#SBATCH --error=logs/snakemake.%j.err

# Driver script for TCGA-BRCA bulk RNA-seq pipeline.
# Submits the master Snakemake job; per-rule jobs are dispatched
# by the `slurm` profile under ~/.config/snakemake/slurm/.

set -euo pipefail
cd "$(dirname "$0")/.."

module purge
module load bwa/0.7.17
module load samtools/1.18
module load star/2.7.11a
module load subread/2.0.6
module load snakemake/8.5.3
module load r/4.3.2

mkdir -p logs workspace

snakemake \
    --snakefile inputs/data/Snakefile \
    --profile slurm \
    --use-conda \
    --conda-frontend mamba \
    --jobs 50 \
    --keep-going \
    --rerun-incomplete \
    --printshellcmds \
    --latency-wait 60 \
    --restart-times 2 \
    all
