import json
import os
import io
import time
import tarfile
import ftplib

import pandas as pd
from bs4 import BeautifulSoup

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
CASE_NUMBER = 1
INPUT_FILES_INFO = "new_files_info.json"
RESUME_FROM = 0
OUTPUT_ROOT = "new_data"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".bmp", ".webp")

RETRIES = 3
PROGRESS_EVERY = 100
CHECKPOINT_EVERY = 100

IMAGES_CSV = "Images_Captions.csv"
TAR_FAIL_JSON = "new_tar_extraction_failed_pmc_ids.json"
FIG_FAIL_JSON = "new_graphic_caption_failed_pmc_ids.json"


def connect_ftp():
    ftp = ftplib.FTP(FTP_SERVER, timeout=600)
    ftp.set_pasv(True)
    ftp.login()
    return ftp


def normalize_pmc_id_clean(value):
    value = str(value).strip()
    if value.startswith("PMC"):
        return value[3:]
    return value


def normalize_ftp_path(path):
    path = str(path).strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def is_target_member(member_name):
    lower_name = member_name.lower()
    return lower_name.endswith(".nxml") or lower_name.endswith(IMAGE_EXTS)


def is_safe_extract_path(base_dir, member_name):
    base_dir_real = os.path.realpath(base_dir)
    target_real = os.path.realpath(os.path.join(base_dir, member_name))
    return target_real == base_dir_real or target_real.startswith(base_dir_real + os.sep)


def extract_assets_once(ftp, ftp_path, pmc_dir):
    ftp_path = normalize_ftp_path(ftp_path)
    os.makedirs(pmc_dir, exist_ok=True)

    with io.BytesIO() as gz_data:
        ftp.retrbinary(f"RETR {ftp_path}", gz_data.write)
        gz_data.seek(0)

        with tarfile.open(fileobj=gz_data, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                if not is_target_member(member.name):
                    continue
                if not is_safe_extract_path(pmc_dir, member.name):
                    continue
                tar.extract(member, path=pmc_dir)


def extract_assets_with_retry(ftp, ftp_path, pmc_dir, pmc_id, retries=RETRIES):
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            extract_assets_once(ftp, ftp_path, pmc_dir)
            return ftp
        except ftplib.all_errors + (EOFError, tarfile.TarError, OSError) as e:
            last_exc = e
            print(f"{pmc_id} attempt {attempt}/{retries} failed: {type(e).__name__}: {e!r}")

            try:
                ftp.quit()
            except Exception:
                pass

            time.sleep(min(5 * attempt, 15))
            ftp = connect_ftp()

    raise last_exc


def find_nxml_path(pmc_dir):
    for root, _, files in os.walk(pmc_dir):
        for file in files:
            if file.lower().endswith(".nxml"):
                return os.path.join(root, file)
    return None


def ensure_patient_folder(pmc_dir, patient_uid):
    patient_folder = os.path.join(pmc_dir, patient_uid)
    legacy_folder = os.path.join(pmc_dir, os.path.basename(pmc_dir))

    if os.path.isdir(patient_folder):
        return patient_folder

    if os.path.isdir(legacy_folder):
        os.rename(legacy_folder, patient_folder)
        return patient_folder

    os.makedirs(patient_folder, exist_ok=True)
    return patient_folder


def get_graphic_href(graphic):
    for key in ("xlink:href", "href"):
        value = graphic.get(key)
        if value:
            return value

    for key, value in graphic.attrs.items():
        key_lower = str(key).lower()
        if key_lower == "href" or key_lower.endswith(":href"):
            return value

    return None


# def find_graphic_file(search_root, graphic_href):
#     graphic_href = str(graphic_href).strip()
#     href_basename = os.path.basename(graphic_href)

#     candidates = set()

#     for seed in {graphic_href, href_basename}:
#         base, ext = os.path.splitext(seed)
#         if ext:
#             candidates.add(seed)
#             candidates.add(seed.lower())
#         else:
#             for image_ext in IMAGE_EXTS:
#                 candidates.add(seed + image_ext)
#                 candidates.add((seed + image_ext).lower())

#     for root, _, files in os.walk(search_root):
#         for file in files:
#             if file in candidates or file.lower() in candidates:
#                 return os.path.join(root, file)

#     return None

def find_graphic_file(search_root, graphic_href):
    graphic_href = str(graphic_href).strip()
    href_basename = os.path.basename(graphic_href)

    candidates = set()

    for seed in {graphic_href, href_basename}:
        seed = seed.strip()
        _, ext = os.path.splitext(seed)
        ext = ext.lower()

        # Only treat it as a "real extension" if it is one of the supported image extensions.
        # This avoids misclassifying names like "...001" as already having an image extension.
        if ext in IMAGE_EXTS:
            candidates.add(seed)
            candidates.add(seed.lower())
        else:
            candidates.add(seed)
            candidates.add(seed.lower())
            for image_ext in IMAGE_EXTS:
                candidates.add(seed + image_ext)
                candidates.add((seed + image_ext).lower())

    for root, _, files in os.walk(search_root):
        for file in files:
            if file in candidates or file.lower() in candidates:
                return os.path.join(root, file)

    return None

def save_outputs(images_info_for_df, tar_extraction_failed_pmc_ids, graphic_caption_failed_pmc_ids):
    images_info_df = pd.DataFrame(
        images_info_for_df,
        columns=["image_path", "caption_path", "patient_uid", "pmc_id", "article_path"],
    )
    images_info_df.to_csv(IMAGES_CSV, index=False)

    with open(TAR_FAIL_JSON, "w") as f:
        json.dump(tar_extraction_failed_pmc_ids, f, indent=2)

    with open(FIG_FAIL_JSON, "w") as f:
        json.dump(graphic_caption_failed_pmc_ids, f, indent=2)


def load_existing_state():
    images_info_for_df = []
    seen_image_paths = set()
    tar_extraction_failed_pmc_ids = []
    graphic_caption_failed_pmc_ids = []

    if RESUME_FROM > 0:
        if os.path.exists(IMAGES_CSV):
            existing_df = pd.read_csv(IMAGES_CSV)
            if not existing_df.empty:
                images_info_for_df = existing_df[
                    ["image_path", "caption_path", "patient_uid", "pmc_id", "article_path"]
                ].values.tolist()
                seen_image_paths = set(existing_df["image_path"].astype(str))

        if os.path.exists(TAR_FAIL_JSON):
            with open(TAR_FAIL_JSON, "r") as f:
                tar_extraction_failed_pmc_ids = json.load(f)

        if os.path.exists(FIG_FAIL_JSON):
            with open(FIG_FAIL_JSON, "r") as f:
                graphic_caption_failed_pmc_ids = json.load(f)

    return (
        images_info_for_df,
        seen_image_paths,
        tar_extraction_failed_pmc_ids,
        graphic_caption_failed_pmc_ids,
    )


def main():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    (
        images_info_for_df,
        seen_image_paths,
        tar_extraction_failed_pmc_ids,
        graphic_caption_failed_pmc_ids,
    ) = load_existing_state()

    ftp = connect_ftp()

    with open(INPUT_FILES_INFO, "r") as f:
        files_info = json.load(f)

    files_info = files_info[RESUME_FROM:]

    for num, entry in enumerate(files_info, start=RESUME_FROM):
        try:
            pmc_id_clean, local_filename, ftp_path = entry
        except ValueError:
            tar_extraction_failed_pmc_ids.append(
                {"entry": entry, "reason": "malformed files_info entry"}
            )
            continue

        pmc_id_clean = normalize_pmc_id_clean(pmc_id_clean)
        pmc_id = "PMC" + pmc_id_clean
        pmc_dir = os.path.join(OUTPUT_ROOT, pmc_id)
        article_path = "https://ncbi.nlm.nih.gov/pmc/articles/" + pmc_id

        try:
            ftp = extract_assets_with_retry(ftp, ftp_path, pmc_dir, pmc_id)
        except Exception as e:
            print(f"Failed to retrieve files for {pmc_id}: {type(e).__name__}: {e!r}")
            try:
                ftp.quit()
            except Exception:
                pass
            ftp = connect_ftp()
            tar_extraction_failed_pmc_ids.append(
                {"pmc_id": pmc_id_clean, "reason": f"{type(e).__name__}: {e!r}"}
            )
            continue

        nxml_path = find_nxml_path(pmc_dir)
        if not nxml_path:
            tar_extraction_failed_pmc_ids.append(
                {"pmc_id": pmc_id_clean, "reason": "nxml not found after extraction"}
            )
            continue

        try:
            with open(nxml_path, "r", encoding="utf-8") as file:
                content = file.read()
            soup = BeautifulSoup(content, "xml")
        except Exception as e:
            tar_extraction_failed_pmc_ids.append(
                {"pmc_id": pmc_id_clean, "reason": f"failed reading/parsing nxml: {type(e).__name__}: {e!r}"}
            )
            continue

        figures = soup.find_all("fig")
        patient_uid = f"{pmc_id_clean}_{CASE_NUMBER}"
        patient_folder = ensure_patient_folder(pmc_dir, patient_uid)

        for i, fig in enumerate(figures, start=1):
            caption = fig.find("caption")
            graphic = fig.find("graphic")

            if not (graphic and caption):
                graphic_caption_failed_pmc_ids.append(
                    {
                        "pmc_id": pmc_id_clean,
                        "figure_index": i,
                        "reason": "missing graphic or caption",
                    }
                )
                continue

            graphic_href = get_graphic_href(graphic)
            caption_text = caption.get_text(" ", strip=True)

            if not graphic_href or not caption_text:
                graphic_caption_failed_pmc_ids.append(
                    {
                        "pmc_id": pmc_id_clean,
                        "figure_index": i,
                        "reason": "empty graphic href or empty caption text",
                    }
                )
                continue

            src_image_path = find_graphic_file(patient_folder, graphic_href)
            if src_image_path is None:
                src_image_path = find_graphic_file(pmc_dir, graphic_href)

            if src_image_path is None:
                graphic_caption_failed_pmc_ids.append(
                    {
                        "pmc_id": pmc_id_clean,
                        "figure_index": i,
                        "reason": f"image file not found for graphic href {graphic_href}",
                    }
                )
                continue

            image_ext = os.path.splitext(src_image_path)[1] or ".jpg"
            fig_title = f"{pmc_id_clean}_{CASE_NUMBER}_{i}"
            new_image_path = os.path.join(patient_folder, fig_title + image_ext)
            caption_path = os.path.join(patient_folder, fig_title + ".txt")

            try:
                if os.path.abspath(src_image_path) != os.path.abspath(new_image_path):
                    if not os.path.exists(new_image_path):
                        os.replace(src_image_path, new_image_path)

                if not os.path.exists(caption_path):
                    with open(caption_path, "w", encoding="utf-8") as file:
                        file.write(caption_text)

                if new_image_path not in seen_image_paths:
                    images_info_for_df.append(
                        [new_image_path, caption_path, patient_uid, pmc_id_clean, article_path]
                    )
                    seen_image_paths.add(new_image_path)

            except Exception as e:
                graphic_caption_failed_pmc_ids.append(
                    {
                        "pmc_id": pmc_id_clean,
                        "figure_index": i,
                        "reason": f"{type(e).__name__}: {e!r}",
                    }
                )

        processed = num + 1

        if processed % PROGRESS_EVERY == 0:
            print(
                f"processed {processed} entries | "
                f"success rows={len(images_info_for_df)} | "
                f"tar_failures={len(tar_extraction_failed_pmc_ids)} | "
                f"figure_failures={len(graphic_caption_failed_pmc_ids)}"
            )

        if processed % CHECKPOINT_EVERY == 0:
            save_outputs(
                images_info_for_df,
                tar_extraction_failed_pmc_ids,
                graphic_caption_failed_pmc_ids,
            )

    save_outputs(
        images_info_for_df,
        tar_extraction_failed_pmc_ids,
        graphic_caption_failed_pmc_ids,
    )

    try:
        ftp.quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
