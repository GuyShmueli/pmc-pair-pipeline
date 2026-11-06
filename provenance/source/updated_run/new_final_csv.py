# --- lines 3-17 (figure table join, as run)
# img_captions_df = pd.read_csv('Images_Captions.csv')
# unique_articles_df = pd.read_csv('new_unique_articles.csv')

# # Make sure they both share the same 'patient_uid' format
# unique_articles_df['patient_uid'] = unique_articles_df['patient_uid'].str.replace('_', '-', regex=False)
# img_captions_df['patient_uid'] = img_captions_df['patient_uid'].str.replace('_', '-', regex=False)

# merged_df = pd.merge(
#     img_captions_df,
#     unique_articles_df[['patient_uid', 'unique_articles_sim_patients']],
#     on='patient_uid',
#     how='inner'
# )

# merged_df.to_csv('new_final_csv.csv', index=False)
