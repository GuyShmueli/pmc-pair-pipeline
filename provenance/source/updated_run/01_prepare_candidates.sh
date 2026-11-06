# --- lines 25-30 (stage 01 command)
python -u scripts/01_prepare_candidates.py \
  --dataset-csv "$ROOT/merged_csv2.csv" \
  --diagram-paths-json "$ROOT/new_imgs_paths_diagrams_4.json" \
  --data-dir "$ROOT/new_data" \
  --output-dir "$OUTPUT_DIR" \
  --workers "${SLURM_CPUS_PER_TASK}"
