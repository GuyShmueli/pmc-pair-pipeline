# --- cell 9 (compound table writer)
df['contains_specified_patterns'] = df['caption_text'].apply(lambda caption : is_containing_specified_patterns(caption, patterns))

# --- cell 10 (compound table writer)
compound_images_df = df[df['contains_specified_patterns'] == True]

# --- cell 16 (compound table writer)
compound_images_dict = compound_images_df.to_dict(orient='records')  # or 'index', 'split', etc.
with open(r'<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/compound_images_df.json', 'w') as f:
    json.dump(compound_images_dict, f, indent=2)

# --- cell 27 (first-route list writer)

# Add 'caption_id' and 'patient_uid' columns to 'filtered_df'
filtered_df['caption_id'] = filtered_df['caption_path'].apply(
    lambda x: os.path.splitext(os.path.basename(x))[0]
)

# Create the mapping from 'patient_uid' to a set of 'caption_id's
patient_uid_to_captions = filtered_df.groupby('patient_uid')['caption_id'].apply(set).to_dict()

# --- cell 50 (first-route list writer)
base_path = '<DATA_ROOT>/pmc/pythonProject/data2'
pairs_text_list, pairs_image_list, not_exist_num = creating_txt_jpg_pairs(matching_uids, base_path, patient_uid_to_captions)

# --- cell 51 (first-route list writer)
# Saving the lists to a json file
lists_path = r'<DATA_ROOT>/envs/pmc_project/'

with open(lists_path + 'matching_uids.json', 'w') as f:
    json.dump(matching_uids, f)

with open(lists_path + 'pairs_text_list.json', 'w') as g:
    json.dump(pairs_text_list, g)

with open(lists_path + 'pairs_image_list.json', 'w') as h:
    json.dump(pairs_image_list, h)
