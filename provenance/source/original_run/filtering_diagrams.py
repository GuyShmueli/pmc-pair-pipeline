"""
This script filters diagrams based on a pixel value threshold and OCR text length.
"""

import os
from PIL import Image
import numpy as np
import json
import pytesseract  # for OCR
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

lists_path = '<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>'

with open(os.path.join(lists_path, 'imgs_paths.json'), 'r') as g:
    imgs_paths = json.load(g)

def calc_ratio_and_text_len(path, threshold=250):     
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


imgs_paths_diagrams = []

def process_path(path):
    try:
        ratio, text_len = calc_ratio_and_text_len(path)
        condition1 = ratio > 0.5
        condition2 = text_len > 100
        return path if condition1 or condition2 else None
    except Exception as e:
        print(f"Error processing {path}: {e}")
        return None

# --- Use ProcessPoolExecutor for CPU-bound tasks ---
num_workers = max(1, multiprocessing.cpu_count() - 2)  # Leave 2 cores free for other tasks
with ProcessPoolExecutor(max_workers=num_workers) as executor: 
    futures = [executor.submit(process_path, path) for path in imgs_paths]

    for future in as_completed(futures):
        result = future.result()
        if result:
            imgs_paths_diagrams.append(result)

print(f"Total images retained: {len(imgs_paths_diagrams)}")
with open(os.path.join(lists_path, 'imgs_paths_diagrams_new.json'), 'w') as f:
    json.dump(imgs_paths_diagrams, f)
