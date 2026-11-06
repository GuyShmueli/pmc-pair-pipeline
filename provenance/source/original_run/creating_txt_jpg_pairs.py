"""
This file creates two 3D lists, each of the form:
pairs_text_list = [
                    [ [patient's_i_captions_paths], [patient's_j_captions_paths] ], [ [] ], ...
                  ]
"""

import os
import glob
import json
import pandas as pd

def creating_txt_jpg_pairs(matching_uids, file_path, patient_uid_to_captions):
    # Each list consists of pairs containing the aligned files for each patient_uid
    pairs_text_list = []
    pairs_image_list = []
    not_found_counter = 0

    # Iterating over the pairs
    for pair in matching_uids:
        uids = [pair[0][:-2], pair[1][:-2]]
    
        pair_aligned_txt_files = []
        pair_aligned_jpg_files = []
    
        # Iterating over each patient_uid within the pair
        for uid in uids:
            # Construct the full path using the base_path parameter
            path = os.path.join(file_path, f'PMC{uid}/{uid}_1')
    
            # Check if the path exists
            if not os.path.exists(path):
                # print(f"Directory {path} does not exist.")
                not_found_counter += 1
                continue
    
            # Get all txt and jpg files within a single patient_uid
            txt_files = glob.glob(os.path.join(path, '*.txt'))
            jpg_files = glob.glob(os.path.join(path, '*.jpg'))

            # Get valid caption IDs for this patient_uid
            valid_caption_ids = patient_uid_to_captions.get(uid+'-1', set())

            # Create mappings: '<IMAGE_ID>' -> '/path/to/<IMAGE_ID>.txt'
            txt_files_dict = {os.path.splitext(os.path.basename(f))[0]: f for f in txt_files}
            jpg_files_dict = {os.path.splitext(os.path.basename(f))[0]: f for f in jpg_files}

            # Find common keys that are in the valid captions for this uid
            common_keys = set(txt_files_dict.keys()) & set(jpg_files_dict.keys()) & valid_caption_ids

            # Sort the paths to align txt and jpg files
            sorted_keys = sorted(common_keys)

            # Align txt and jpg files (within the same patient_uid)
            aligned_txt_files = [txt_files_dict[key] for key in sorted_keys]
            aligned_jpg_files = [jpg_files_dict[key] for key in sorted_keys]

            # Append the aligned files for this patient_uid to the pair's list
            pair_aligned_txt_files.append(aligned_txt_files)
            pair_aligned_jpg_files.append(aligned_jpg_files)
    
        # After processing both patient_uids in the pair, append the pair to the main list
        if len(pair_aligned_txt_files) == 2:
            pairs_text_list.append(pair_aligned_txt_files)
            pairs_image_list.append(pair_aligned_jpg_files)
    
    return pairs_text_list, pairs_image_list, not_found_counter

# Uploading the matching_uids list
lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/'
with open(lists_path + 'matching_uids.json', 'r') as f:
    matching_uids = json.load(f)

# Uploading the filtered df
filtered_csv_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/filtered_df.csv'
filtered_df = pd.read_csv(filtered_csv_path)

# Create the mapping from 'patient_uid' to a set of 'caption_id's
patient_uid_to_captions = filtered_df.groupby('patient_uid')['caption_id'].apply(set).to_dict()

base_path = '<DATA_ROOT>/pmc/pythonProject/data2'
pairs_text_list, pairs_image_list, not_exist_num = creating_txt_jpg_pairs(matching_uids, base_path, patient_uid_to_captions)
