# --- lines 46-88 (OA package paths used for download)
import requests
import xml.etree.ElementTree as ET
import json

logger = open("new_log.txt", "w")
logger.write(f"started retrieving files info\n")

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
with open('new_unique_articles.json', 'r') as f:
    unique_articles_list = json.load(f)
files_info = []
failed_ids = []
total_amount = len(unique_articles_list)


for i, PMC_ID in enumerate(unique_articles_list):
    if i % 100 == 0:
        percent = i // total_amount * 100
        print(f"processed {i} out of {total_amount} values, {percent}%\n")
    try:
        url = f'https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={PMC_ID}'
        response = requests.get(url)
        root = ET.fromstring(response.content)
        link_element = root.find('.//link')
        href = link_element.get('href')
        local_filename = href.split('/')[-1]
        ftp_path = href.split(f'ftp://{FTP_SERVER}/')[1]
        files_info.append((PMC_ID, local_filename, ftp_path))
    except Exception as e:
        print(f"{e}\n")
        logger.write(f"failed retrieving file info for pmc_id: {PMC_ID}\n")
        logger.write(f"got error: {e}\n")
        failed_ids.append(PMC_ID)

with open('new_failed_ids.json', 'w') as f:
    json.dump(failed_ids, f)

with open('new_files_info.json', 'w') as f:
    json.dump(files_info, f)

logger.write(f"finished retrieving {len(files_info)} articles info\n")
logger.write(f"failed retrieving {len(failed_ids)} articles info. If failed, see failed_ids.json\n")
logger.close()
