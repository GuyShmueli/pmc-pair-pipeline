#!/bin/bash
# Example SLURM job for the long, CPU-bound steps (download, image screening, parsing).
# Adjust the resources, partition and environment activation for your cluster, and set
# `workers` in config.yaml to the number of CPUs requested here.
# Submit it from the repository root: sbatch scripts/slurm_job.sh
# The log, slurm-pmc_pair-<job id>.out, is written to that folder.
#SBATCH --job-name=pmc_pair
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=4-00:00:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail
source .venv/bin/activate          # or: conda activate pmc-pair
export OMP_THREAD_LIMIT=1          # Tesseract: one thread per worker process

# Download and image screening resume where they stopped if the job is interrupted.
python -u -m pmc_pair select-cases    --config config.yaml
python -u -m pmc_pair download        --config config.yaml
python -u -m pmc_pair extract-figures --config config.yaml
python -u -m pmc_pair filter-images   --config config.yaml
python -u -m pmc_pair prepare-pairs   --config config.yaml
