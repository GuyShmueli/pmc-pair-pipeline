# --- lines 27-31 (screening command)
python -u 00_filter_diagrams_2.py \
  --workers "${SLURM_CPUS_PER_TASK:-8}" \
  --chunksize 64 \
  --tmpdir "$TMPDIR" \
  --log-every 5000 \
