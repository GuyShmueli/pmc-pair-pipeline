"""
This script's objective is to filter out captions that describe more than one image (compound figures).
The reason for that, is that we expect the image encoder will do poorly on figures that include multiple images.
"""
import os
import pandas as pd
import re
from concurrent.futures import ThreadPoolExecutor

# Read captions into 'caption_text' column
# Uploading a csv file to a pandas DataFrame
def upload_csv(file_path):
    df = pd.read_csv(file_path)
    return df

# read_caption aims to create a 'caption_text' column to the DataFrame which extracts the captions from the txt file
# Done in parallel in order to speed up the process.
# max_workers refer to the number of threads, which can be two times bigger than the number of CPU cores
def read_caption(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def read_captions_parallel(paths, max_workers=8):
    captions = [None] * len(paths)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(read_caption, path): idx for idx, path in enumerate(paths)}
        for future in future_to_index:
            idx = future_to_index[future]
            try:
                captions[idx] = future.result()
            except Exception as e:
                print(f"Error reading caption at index {idx}: {e}")
                captions[idx] = ""
    return captions

# Checking whether a caption contains certain patterns
def is_containing_specified_patterns(caption, patterns):
    for pattern in patterns:
        if re.search(pattern, caption):
            return True
    return False

# Filtering out the specified patterns using Regex
def filter_out_using_regex(df, patterns, csv_path_and_name):
    # Applying the function to the 'caption_text' column
    df['contains_specified_patterns'] = df['caption_text'].apply(lambda caption 
                                                                    : is_containing_specified_patterns(caption, patterns))
    # Creating a new DataFrame that excludes rows with specified patterns
    df_filtered = df[~df['contains_specified_patterns']].reset_index(drop=True)

    # Dropping the 'contains_specified_patterns' column
    df_filtered = df_filtered.drop('contains_specified_patterns', axis='columns')
    
    # Add 'caption_id' of such form "<IMAGE_ID>, <IMAGE_ID>" to each caption
    # This will help us later in creating a dictionary mapping each patient_uid to all of its captions
    df_filtered['caption_id'] = df_filtered['caption_path'].apply(
        lambda x: os.path.splitext(os.path.basename(x))[0]
    )

    # Saving the filtered DataFrame as a CSV file
    df_filtered.to_csv(csv_path_and_name, index=False)

    # Returning the newly saved DataFrame from the CSV`
    return pd.read_csv(csv_path_and_name)

patterns = [
    r'\(B\)',    # Matches (B)
    r'\(b\)',    # Matches (b)
    r'B\)',      # Matches B)
    r'b\)',      # Matches b)
    r'B\.',      # Matches B.
    r'b\.',      # Matches b.
    r'b\s[A-Z]',   # Matches 'b' followed by a space and a capital letter
    r'B\s[A-Z]',   # Matches 'B' followed by a space and a capital letter
]


# Uploading the csv
file_path = '<DATA_ROOT>/pmc/pythonProject/data2/final_csv2.csv'
df = upload_csv(file_path)

# Reading captions into 'caption_text' column
data_path = '<DATA_ROOT>/pmc/pythonProject/data2/'
txt_paths = [data_path + elem for elem in df['caption_path'].tolist()]
df['caption_text'] = read_captions_parallel(txt_paths)

# Specifying the path where the filtered df will be saved
filtered_csv_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/filtered_df.csv'
filtered_df = filter_out_using_regex(df, patterns, filtered_csv_path)
