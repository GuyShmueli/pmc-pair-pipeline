"""
This file aims to create a 2D list of the form:
matching_uids = [['<CASE_ID>', '<CASE_ID>'], ['<CASE_ID>', '<CASE_ID>'], ...]
which contains positive pairs (based on the heuristic of PMC Patient's authors).
"""
import json
import pandas as pd

def creating_uids_pairs(df, rows_num):
    matching_uids = []
    checked_pairs = set()
    # Create a set of patient_uids present in the filtered DataFrame
    uids_in_df = set(df['patient_uid'])
    
    for index, row in df.head(rows_num).iterrows():
        patient_uid = row['patient_uid']
        
        # Ensure that patient_uid is in uids_in_df
        if patient_uid not in uids_in_df:
            continue  # This should not happen, but added for safety

        sim_patients = row['unique_articles_sim_patients']
    
        # Skip NaN values
        if pd.isna(sim_patients):
            continue
    
        # Clean the 'unique_articles_sim_patients' column
        sim_patients = sim_patients.strip("[]").replace("'", "")
        sim_patients_list = sim_patients.split(', ') if sim_patients else []
    
        for similar_uid in sim_patients_list:
            # Skip self-matching
            if similar_uid == patient_uid:
                continue

            # Check if similar_uid is in the filtered DataFrame
            if similar_uid not in uids_in_df:
                continue  # Skip if similar_uid not in the DataFrame

            # Create a sorted tuple to handle symmetry
            pair = tuple(sorted([patient_uid, similar_uid]))
    
            # Check if the pair was already added
            if pair not in checked_pairs:
                matching_uids.append([patient_uid, similar_uid])  # Add the pair
                checked_pairs.add(pair)  # Mark this pair as checked

    return matching_uids


# Uploading the filtered df
filtered_csv_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/filtered_df.csv'
filtered_df = pd.read_csv(filtered_csv_path)

# Creating matching_uids list
matching_uids = creating_uids_pairs(filtered_df, len(filtered_df))

# Saving the lists to a json file
lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/'
with open(lists_path + 'matching_uids.json', 'w') as f:
    json.dump(matching_uids, f)
