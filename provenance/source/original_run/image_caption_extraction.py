import pandas as pd
from bs4 import BeautifulSoup
import time
import ftplib
import gzip
import io
import tarfile
import os
import json

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
CASE_NUMBER = 1  ## For unique patient per PMC id

images_info_for_df = []
tar_extraction_failed_pmc_ids = []
graphic_caption_failed_pmc_ids = []
image_convertion_failed_pmc_ids = []

def save_info():
    try:
        with open('tar_extraction_failed_pmc_ids.json', 'w') as f:
            json.dump(tar_extraction_failed_pmc_ids, f)

        with open('graphic_caption_failed_pmc_ids.json', 'w') as f:
            json.dump(graphic_caption_failed_pmc_ids, f)

        with open('image_convertion_failed_pmc_ids.json', 'w') as f:
            json.dump(image_convertion_failed_pmc_ids, f)

    except Exception as e:
        print(f"Failed to write failed PMC IDs to JSON files, error: {e}\n")


def connect_ftp():
    try:
        ftp = ftplib.FTP(FTP_SERVER, timeout=600)
        ftp.set_pasv(True)
        ftp.login()
        return ftp
    except Exception as e:
        print(f"Failed to connect FTP, error: {e}\n")
        save_info()
        raise e


def extract_jpg_nxml(ftp, ftp_path, PMC_ID):
    with io.BytesIO() as gz_data:
        ftp.retrbinary(f"RETR {ftp_path}", gz_data.write)
        gz_data.seek(0)

        with gzip.open(gz_data, 'rb') as gz_file:
            with tarfile.open(fileobj=gz_file) as tar:
                for member in tar.getmembers():
                    if member.name.endswith('.jpg') or member.name.endswith('.nxml'):
                        tar.extract(member, path=PMC_ID)

ftp = connect_ftp()

with open('files_info.json', 'r') as f:
    files_info = json.load(f)

for num, (pmc_id_clean, local_filename, ftp_path) in enumerate(files_info):

    PMC_ID = "PMC" + pmc_id_clean
    article_path = "https://ncbi.nlm.nih.gov/pmc/articles/" + PMC_ID

    try:
        extract_jpg_nxml(ftp, ftp_path, PMC_ID)
    except IOError as e:
        print(f"Failed first attempt to retrieve the files of the {num}th article, PMC_ID: {PMC_ID}, error: {e}\n")
        ftp = connect_ftp()
        try:
            extract_jpg_nxml(ftp, ftp_path, PMC_ID)
        except Exception as e:
            print(f"Failed to retrieve the files of the {num}th article, PMC_ID: {PMC_ID}, error: {e}\n")
            ftp = connect_ftp()
            tar_extraction_failed_pmc_ids.append(pmc_id_clean)
            continue
    except Exception as e:
        print(f"Failed to retrieve the files of the {num}th article, PMC_ID: {PMC_ID}, error: {e}\n")
        ftp = connect_ftp()
        tar_extraction_failed_pmc_ids.append(pmc_id_clean)
        continue

    # Get the path of the extracted .nxml file
    nxml_path = None
    try:
        for root, _, files in os.walk(PMC_ID):
            for file in files:
                if file.endswith('.nxml'):
                    nxml_path = os.path.join(root, file)
                    break
    except Exception as e:
        print(f"Failed during directory traversal for PMC_ID: {PMC_ID}, error: {e}\n")
        tar_extraction_failed_pmc_ids.append(pmc_id_clean)
        continue

    if nxml_path:
        try:
            with open(nxml_path, 'r', encoding='utf-8') as file:
                content = file.read()
                soup = BeautifulSoup(content, 'xml')
        except Exception as e:
            print(f"Failed to read the .nxml file at {nxml_path} for PMC_ID: {PMC_ID}, error: {e}\n")
            tar_extraction_failed_pmc_ids.append(pmc_id_clean)
            continue

        figures = soup.find_all('fig')

        for i, fig in enumerate(figures):

            caption = fig.find('caption')
            graphic = fig.find('graphic')

            if graphic and caption:

                img_url = graphic['xlink:href']
                caption_text = caption.get_text()

                if img_url and caption_text:

                    patient_uid = f"{pmc_id_clean}_{CASE_NUMBER}"
                    patient_folder = f"{PMC_ID}/{patient_uid}"
                    if not os.path.exists(patient_folder):
                        try:
                            os.rename(f"{PMC_ID}/{PMC_ID}", patient_folder)
                        except Exception as e:
                            print(f"Failed to rename {PMC_ID}/{PMC_ID} to {patient_folder} for PMC_ID: {PMC_ID}, error: {e}\n")
                            graphic_caption_failed_pmc_ids.append((pmc_id_clean, fig))
                            continue

                    fig_title = f"{pmc_id_clean}_{CASE_NUMBER}_{i + 1}"

                    image_path = f"{patient_folder}/{img_url}.jpg"
                    new_image_path = f"{patient_folder}/{fig_title}.jpg"
                    try:
                        os.rename(image_path, new_image_path)
                    except Exception as e:
                        print(f"Failed to find or rename the {i}th image ({image_path}) for PMC_ID: {PMC_ID}, error: {e}\n")
                        image_convertion_failed_pmc_ids.append((pmc_id_clean, fig))
                        continue

                    try:
                        caption_path = f"{patient_folder}/{fig_title}.txt"
                        with open(caption_path, 'w') as file:
                            file.write(caption_text)
                    except Exception as e:
                        print(f"Failed to write caption text to {caption_path} for PMC_ID: {PMC_ID}, error: {e}\n")
                        graphic_caption_failed_pmc_ids.append((pmc_id_clean, fig))

                    images_info_for_df.append([new_image_path, caption_path, patient_uid, pmc_id_clean, article_path])
                else:
                    graphic_caption_failed_pmc_ids.append((pmc_id_clean, fig))

            else:
                graphic_caption_failed_pmc_ids.append((pmc_id_clean, fig))
    else:
        print(f"Failed to find the .nxml file for PMC_ID: {PMC_ID}\n")
        tar_extraction_failed_pmc_ids.append(pmc_id_clean)

try:
    images_info_df = pd.DataFrame(images_info_for_df,
                                  columns=["image_path", "caption_path", "patient_uid", "pmc_id", "article_path"])
    images_info_df.to_csv('Images_Captions.csv', index=False)
except Exception as e:
    print(f"Failed to create DataFrame or write to CSV, error: {e}\n")

save_info()
