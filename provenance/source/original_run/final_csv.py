import pandas as pd

img_captions_df = pd.read_csv('Images_Captions.csv')
img_captions_df['patient_uid'] = img_captions_df['patient_uid'].astype(str).map(lambda x: x.replace('_', '-'))

unique_articles_df = pd.read_csv('unique_articles.csv')

merged_df = pd.merge(img_captions_df, unique_articles_df[['patient_uid', 'unique_articles_sim_patients']], on='patient_uid', how='inner')

merged_df.to_csv('final_csv.csv', index=False)
