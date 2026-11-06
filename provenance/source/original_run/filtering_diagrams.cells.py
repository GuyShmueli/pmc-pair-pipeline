# --- cell 4 (image list)
# data_dir = '<DATA_ROOT>/pmc/pythonProject/data2'

# imgs_paths = [
#         data_dir+f"/{patient_uid}/{patient_uid[3:]}_1/{img_path}"
#         for patient_uid in os.listdir(data_dir)
#         if os.path.isdir(f"{data_dir}/{patient_uid}/{patient_uid[3:]}_1") 
#         for img_path in os.listdir(data_dir+f"/{patient_uid}/{patient_uid[3:]}_1")
#         if img_path.endswith('jpg')
#     ]

# imgs_paths = sorted(imgs_paths)

# --- cell 5 (image list)
# lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>'

# with open(lists_path + "/imgs_paths.json", 'w') as f:
#     json.dump(imgs_paths, f)

# --- cell 14 (keep list)
diagrams_paths_set = set(imgs_paths_diagrams)

# --- cell 15 (keep list)
non_diagrams_imgs_paths = [path for path in imgs_paths if path not in diagrams_paths_set]

# --- cell 19 (keep list)
compound_filtered_paths_list = list(filtered_df['image_path'])
prefix = '<DATA_ROOT>/pmc/pythonProject/data2/'
compound_filtered_paths_list = [os.path.join(prefix, suffix) for suffix in compound_filtered_paths_list]

# --- cell 20 (keep list)
diagrams_compound_filtered_paths_list = [path for path in compound_filtered_paths_list if path not in diagrams_paths_set]

# --- cell 23 (keep list)
# lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/'

# with open(lists_path + "diagrams_compound_filtered_paths_list.json", 'w') as f:
#     json.dump(diagrams_compound_filtered_paths_list, f)

# --- cell 38 (threshold function)
def calc_ratio_and_text_len_with(path, threshold=250):     
    with Image.open(path) as image:  # Ensure image is closed after use
        pixel_values = np.asarray(image)
 
        # Compute ratio early
        tot_pixels = pixel_values.size
        pixels_exceeding_threshold = (pixel_values >= threshold).sum()
        ratio = round(pixels_exceeding_threshold / tot_pixels, 2)

        # If ratio > 0.5, no need for OCR
        if ratio > 0.5:
            return ratio, 0  # Text len won't matter

        # Perform OCR while image is still open
        text = pytesseract.image_to_string(image, lang='eng')
        
    return ratio, len(text)

# --- cell 52 (diagram list write)
lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/'
with open(lists_path+'imgs_paths_diagrams.json', 'w') as f:
    json.dump(imgs_paths_diagrams, f)
