# --- cell 44 (GIF to JPEG path repair)
"""
Run after final_csv.py.
Some figures in 'img_captions_df' have a '.gif' suffix.
This script's goal is to find whether there is a corresponding '.jpg' format
in the patient's directory, and replace the '.gif' with it.
"""
import os
import pandas as pd
from bs4 import BeautifulSoup

JPEG_EXTS = (".jpg", ".jpeg")


def find_nxml_path(pmc_dir):
    for root, _, files in os.walk(pmc_dir):
        for file in files:
            if file.lower().endswith(".nxml"):
                return os.path.join(root, file)
    return None


def get_graphic_href(graphic):
    if graphic is None:
        return None

    for key in ("xlink:href", "href"):
        value = graphic.get(key)
        if value:
            return value

    for key, value in graphic.attrs.items():
        key_lower = str(key).lower()
        if key_lower == "href" or key_lower.endswith(":href"):
            return value

    return None


def load_graphic_hrefs_from_nxml(pmc_dir):
    nxml_path = find_nxml_path(pmc_dir)
    if not nxml_path:
        return None

    with open(nxml_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "xml")

    hrefs = []
    for fig in soup.find_all("fig"):
        hrefs.append(get_graphic_href(fig.find("graphic")))

    return hrefs


def find_matching_jpeg(search_root, graphic_href, prefer_dir=None):
    graphic_href = str(graphic_href).strip()
    href_basename = os.path.basename(graphic_href)

    candidates = set()

    for seed in {graphic_href, href_basename}:
        seed = seed.strip()
        base, ext = os.path.splitext(seed)
        ext = ext.lower()

        if ext in JPEG_EXTS:
            candidates.add(seed)
            candidates.add(seed.lower())
        else:
            seed_no_ext = base if ext else seed
            for jpg_ext in JPEG_EXTS:
                candidates.add(seed_no_ext + jpg_ext)
                candidates.add((seed_no_ext + jpg_ext).lower())

    matches = []
    for root, _, files in os.walk(search_root):
        for file in files:
            if file in candidates or file.lower() in candidates:
                matches.append(os.path.join(root, file))

    if not matches:
        return None

    def sort_key(path):
        same_prefer_dir = 1 if (prefer_dir and os.path.dirname(path) == prefer_dir) else 0
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        return (-same_prefer_dir, -size, path.lower())

    matches.sort(key=sort_key)
    return matches[0]


def replace_gif_paths_with_jpg(merged_df, image_col="image_path", remove_old_gif=False):
    df = merged_df.copy()

    gif_mask = df[image_col].astype(str).str.lower().str.endswith(".gif")
    nxml_cache = {}
    path_cache = {}
    changed_rows = []
    unresolved_rows = []

    for row_idx, gif_path in df.loc[gif_mask, image_col].items():
        gif_path = os.path.normpath(str(gif_path))

        if gif_path in path_cache:
            cached_new_path = path_cache[gif_path]
            if cached_new_path is not None:
                df.at[row_idx, image_col] = cached_new_path
                changed_rows.append({
                    "row_index": row_idx,
                    "old_path": gif_path,
                    "new_path": cached_new_path,
                    "source_jpg": None,
                    "action": "updated_from_cache",
                })
            else:
                unresolved_rows.append({
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "reason": "previously unresolved",
                })
            continue

        gif_name = os.path.basename(gif_path)
        stem, _ = os.path.splitext(gif_name)
        parts = stem.rsplit("_", 2)

        if len(parts) != 3:
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": "unexpected standardized filename format",
            })
            continue

        pmc_id_clean, case_number, figure_number_text = parts

        try:
            figure_number = int(figure_number_text)
        except ValueError:
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": "could not parse figure number",
            })
            continue

        patient_dir = os.path.dirname(gif_path)
        pmc_dir = os.path.dirname(patient_dir)
        target_jpg_path = os.path.normpath(
            os.path.join(patient_dir, f"{pmc_id_clean}_{case_number}_{figure_number}.jpg")
        )

        if os.path.exists(target_jpg_path):
            df.at[row_idx, image_col] = target_jpg_path
            path_cache[gif_path] = target_jpg_path
            changed_rows.append({
                "row_index": row_idx,
                "old_path": gif_path,
                "new_path": target_jpg_path,
                "source_jpg": target_jpg_path,
                "action": "target_already_exists",
            })

            if remove_old_gif and os.path.exists(gif_path):
                try:
                    os.remove(gif_path)
                except OSError:
                    pass

            continue

        if pmc_dir not in nxml_cache:
            nxml_cache[pmc_dir] = load_graphic_hrefs_from_nxml(pmc_dir)

        graphic_hrefs = nxml_cache[pmc_dir]
        if not graphic_hrefs:
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": "nxml not found or no figures in nxml",
            })
            continue

        if figure_number < 1 or figure_number > len(graphic_hrefs):
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": f"figure index {figure_number} out of range",
            })
            continue

        graphic_href = graphic_hrefs[figure_number - 1]
        if not graphic_href:
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": "graphic href missing in nxml",
            })
            continue

        src_jpg_path = find_matching_jpeg(pmc_dir, graphic_href, prefer_dir=patient_dir)
        if src_jpg_path is None:
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": f"no matching jpg/jpeg found for graphic href {graphic_href}",
            })
            continue

        src_jpg_path = os.path.normpath(src_jpg_path)

        if os.path.abspath(src_jpg_path) != os.path.abspath(target_jpg_path):
            os.makedirs(patient_dir, exist_ok=True)
            if not os.path.exists(target_jpg_path):
                os.replace(src_jpg_path, target_jpg_path)

        df.at[row_idx, image_col] = target_jpg_path
        path_cache[gif_path] = target_jpg_path

        changed_rows.append({
            "row_index": row_idx,
            "old_path": gif_path,
            "new_path": target_jpg_path,
            "source_jpg": src_jpg_path,
            "action": "renamed_jpg_and_updated_df",
        })

        if remove_old_gif and os.path.exists(gif_path):
            try:
                os.remove(gif_path)
            except OSError:
                pass

    return df, pd.DataFrame(changed_rows), pd.DataFrame(unresolved_rows)


merged_df, changed_rows_df, unresolved_rows_df = replace_gif_paths_with_jpg(
    merged_df,
    image_col="image_path",
    remove_old_gif=False,   # set True only if you also want to delete the old .gif files
)

print("updated rows:", len(changed_rows_df))
print("unresolved rows:", len(unresolved_rows_df))

changed_rows_df.head()
unresolved_rows_df.head()

# --- cell 46 (GIF to JPEG path repair)
import os
import re
import shutil
import pandas as pd
from bs4 import BeautifulSoup

JPEG_EXTS = (".jpg", ".jpeg")
KNOWN_IMAGE_EXTS = {".jpg", ".jpeg", ".gif", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def find_nxml_path(pmc_dir):
    for root, _, files in os.walk(pmc_dir):
        for file in files:
            if file.lower().endswith(".nxml"):
                return os.path.join(root, file)
    return None


def get_graphic_href(graphic):
    if graphic is None:
        return None

    for key in ("xlink:href", "href"):
        value = graphic.get(key)
        if value:
            return value

    for key, value in graphic.attrs.items():
        key_lower = str(key).lower()
        if key_lower == "href" or key_lower.endswith(":href"):
            return value

    return None


def normalize_graphic_ref(value):
    if value is None:
        return None

    value = str(value).strip().strip('"').strip("'")
    if not value:
        return None

    value = value.replace("\\", "/")
    value = value.split("?", 1)[0].split("#", 1)[0]
    return value or None


FIG_LABEL_RE = re.compile(r"\b(?:figure|fig\.?)\s*(\d+)\b", flags=re.IGNORECASE)
TRAILING_INT_RE = re.compile(r"(\d+)$")


def extract_label_figure_number(fig):
    label = fig.find("label")
    if label is not None:
        label_text = " ".join(label.stripped_strings)

        m = FIG_LABEL_RE.search(label_text)
        if m:
            return int(m.group(1))

        m = re.fullmatch(r"\s*(\d+)\s*", label_text)
        if m:
            return int(m.group(1))

    fig_id = (fig.get("id") or fig.get("xml:id") or "").strip()
    if fig_id:
        m = TRAILING_INT_RE.search(fig_id)
        if m:
            return int(m.group(1))

    return None


def load_graphics_from_nxml(pmc_dir):
    nxml_path = find_nxml_path(pmc_dir)
    if not nxml_path:
        return None

    with open(nxml_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "xml")

    graphics = []
    for position, fig in enumerate(soup.find_all("fig"), start=1):
        graphics.append(
            {
                "position": position,
                "label_number": extract_label_figure_number(fig),
                "href": normalize_graphic_ref(get_graphic_href(fig.find("graphic"))),
            }
        )

    return graphics


def resolve_graphic_href(graphics, figure_number):
    if not graphics:
        return None, "no_graphics"

    # Prefer an explicit label match, e.g. <label>Figure 1</label>
    label_matches = [
        item["href"]
        for item in graphics
        if item.get("href") and item.get("label_number") == figure_number
    ]
    if len(label_matches) == 1:
        return label_matches[0], "matched_by_label"
    if len(label_matches) > 1:
        return label_matches[0], "multiple_label_matches_used_first"

    # Fallback: original positional behavior
    if 1 <= figure_number <= len(graphics):
        href = graphics[figure_number - 1].get("href")
        if href:
            return href, "matched_by_position"
        return None, "graphic_href_missing_at_position"

    return None, "figure_number_out_of_range"


def build_jpeg_index(search_root):
    index = {}
    for root, _, files in os.walk(search_root):
        for file in files:
            if file.lower().endswith(JPEG_EXTS):
                index.setdefault(file.lower(), []).append(os.path.join(root, file))
    return index


def build_jpeg_candidate_names(graphic_href):
    """
    Convert a graphic href into the JPEG filenames we should try to match.

    Important fix:
    If href is 'CRIC2020-4726529.001', we must NOT treat '.001' as a real extension.
    We should look for 'CRIC2020-4726529.001.jpg', not 'CRIC2020-4726529.jpg'.
    """
    graphic_href = normalize_graphic_ref(graphic_href)
    if not graphic_href:
        return set()

    candidates = set()
    seeds = {
        graphic_href,
        os.path.basename(graphic_href),
    }

    for seed in seeds:
        seed = normalize_graphic_ref(seed)
        if not seed:
            continue

        seed = os.path.basename(seed)
        root, ext = os.path.splitext(seed)
        ext = ext.lower()

        # Strip only real image extensions.
        # If ext is something like '.001', keep it as part of the base name.
        if ext in KNOWN_IMAGE_EXTS:
            base_for_jpeg = root
        else:
            base_for_jpeg = seed

        for jpg_ext in JPEG_EXTS:
            candidates.add(base_for_jpeg + jpg_ext)
            candidates.add((base_for_jpeg + jpg_ext).lower())

    return candidates


def sort_match_paths(paths, prefer_dir=None):
    unique_paths = list(dict.fromkeys(paths))

    def sort_key(path):
        same_prefer_dir = 1 if (prefer_dir and os.path.dirname(path) == prefer_dir) else 0
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        return (-same_prefer_dir, -size, path.lower())

    unique_paths.sort(key=sort_key)
    return unique_paths


def find_matching_jpeg(search_root, graphic_href, prefer_dir=None, jpeg_index_cache=None):
    candidates = build_jpeg_candidate_names(graphic_href)
    if not candidates:
        return None

    if jpeg_index_cache is None:
        jpeg_index = build_jpeg_index(search_root)
    else:
        if search_root not in jpeg_index_cache:
            jpeg_index_cache[search_root] = build_jpeg_index(search_root)
        jpeg_index = jpeg_index_cache[search_root]

    matches = []
    for candidate in candidates:
        matches.extend(jpeg_index.get(candidate.lower(), []))

    if not matches:
        return None

    return sort_match_paths(matches, prefer_dir=prefer_dir)[0]


def materialize_target_jpg(src_jpg_path, target_jpg_path, move_src_jpg_to_target=True):
    src_jpg_path = os.path.normpath(src_jpg_path)
    target_jpg_path = os.path.normpath(target_jpg_path)

    os.makedirs(os.path.dirname(target_jpg_path), exist_ok=True)

    if os.path.abspath(src_jpg_path) == os.path.abspath(target_jpg_path):
        return "already_at_target"

    if os.path.exists(target_jpg_path):
        return "target_already_exists"

    if not os.path.exists(src_jpg_path):
        return "source_missing"

    if move_src_jpg_to_target:
        os.replace(src_jpg_path, target_jpg_path)
        return "moved"
    else:
        shutil.copy2(src_jpg_path, target_jpg_path)
        return "copied"


def replace_gif_paths_with_jpg(
    merged_df,
    image_col="image_path",
    remove_old_gif=False,
    move_src_jpg_to_target=True,  # keep True to preserve old behavior
):
    df = merged_df.copy()

    gif_mask = (
        df[image_col].notna()
        & df[image_col].astype(str).str.lower().str.endswith(".gif")
    )

    nxml_cache = {}
    jpeg_index_cache = {}
    path_cache = {}

    changed_rows = []
    unresolved_rows = []

    for row_idx, gif_path in df.loc[gif_mask, image_col].items():
        gif_path = os.path.normpath(str(gif_path))

        if gif_path in path_cache:
            cached_new_path = path_cache[gif_path]
            if cached_new_path is not None:
                df.at[row_idx, image_col] = cached_new_path
                changed_rows.append(
                    {
                        "row_index": row_idx,
                        "old_path": gif_path,
                        "new_path": cached_new_path,
                        "source_jpg": None,
                        "graphic_href": None,
                        "href_resolution": "cache",
                        "action": "updated_from_cache",
                    }
                )
            else:
                unresolved_rows.append(
                    {
                        "row_index": row_idx,
                        "gif_path": gif_path,
                        "graphic_href": None,
                        "href_resolution": "cache",
                        "reason": "previously unresolved",
                    }
                )
            continue

        gif_name = os.path.basename(gif_path)
        stem, _ = os.path.splitext(gif_name)
        parts = stem.rsplit("_", 2)

        if len(parts) != 3:
            path_cache[gif_path] = None
            unresolved_rows.append(
                {
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "graphic_href": None,
                    "href_resolution": None,
                    "reason": "unexpected standardized filename format",
                }
            )
            continue

        pmc_id_clean, case_number, figure_number_text = parts

        try:
            figure_number = int(figure_number_text)
        except ValueError:
            path_cache[gif_path] = None
            unresolved_rows.append(
                {
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "graphic_href": None,
                    "href_resolution": None,
                    "reason": "could not parse figure number",
                }
            )
            continue

        patient_dir = os.path.dirname(gif_path)
        pmc_dir = os.path.dirname(patient_dir)

        target_jpg_path = os.path.normpath(
            os.path.join(patient_dir, f"{pmc_id_clean}_{case_number}_{figure_number}.jpg")
        )

        if os.path.exists(target_jpg_path):
            df.at[row_idx, image_col] = target_jpg_path
            path_cache[gif_path] = target_jpg_path

            changed_rows.append(
                {
                    "row_index": row_idx,
                    "old_path": gif_path,
                    "new_path": target_jpg_path,
                    "source_jpg": target_jpg_path,
                    "graphic_href": None,
                    "href_resolution": "target_exists",
                    "action": "target_already_exists",
                }
            )

            if remove_old_gif and os.path.exists(gif_path):
                try:
                    os.remove(gif_path)
                except OSError:
                    pass

            continue

        if pmc_dir not in nxml_cache:
            nxml_cache[pmc_dir] = load_graphics_from_nxml(pmc_dir)

        graphics = nxml_cache[pmc_dir]
        if not graphics:
            path_cache[gif_path] = None
            unresolved_rows.append(
                {
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "graphic_href": None,
                    "href_resolution": None,
                    "reason": "nxml not found or no figures in nxml",
                }
            )
            continue

        graphic_href, href_resolution = resolve_graphic_href(graphics, figure_number)
        if not graphic_href:
            path_cache[gif_path] = None
            unresolved_rows.append(
                {
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "graphic_href": None,
                    "href_resolution": href_resolution,
                    "reason": f"could not resolve figure {figure_number} to a graphic href",
                }
            )
            continue

        src_jpg_path = find_matching_jpeg(
            pmc_dir,
            graphic_href,
            prefer_dir=patient_dir,
            jpeg_index_cache=jpeg_index_cache,
        )

        if src_jpg_path is None:
            path_cache[gif_path] = None
            unresolved_rows.append(
                {
                    "row_index": row_idx,
                    "gif_path": gif_path,
                    "graphic_href": graphic_href,
                    "href_resolution": href_resolution,
                    "reason": f"no matching jpg/jpeg found for graphic href {graphic_href}",
                }
            )
            continue

        src_jpg_path = os.path.normpath(src_jpg_path)

        materialize_status = materialize_target_jpg(
            src_jpg_path,
            target_jpg_path,
            move_src_jpg_to_target=move_src_jpg_to_target,
        )

        if materialize_status == "source_missing":
            path_cache[gif_path] = None
            unresolved_rows.append({
                "row_index": row_idx,
                "gif_path": gif_path,
                "reason": f"source jpg missing at materialization time: {src_jpg_path}",
            })
            continue

        df.at[row_idx, image_col] = target_jpg_path
        path_cache[gif_path] = target_jpg_path

        changed_rows.append({
            "row_index": row_idx,
            "old_path": gif_path,
            "new_path": target_jpg_path,
            "source_jpg": src_jpg_path,
            "action": f"materialized_{materialize_status}_and_updated_df",
        })

        if remove_old_gif and os.path.exists(gif_path):
            try:
                os.remove(gif_path)
            except OSError:
                pass

    return df, pd.DataFrame(changed_rows), pd.DataFrame(unresolved_rows)

# --- cell 47 (GIF to JPEG path repair)
unresolved_idx = unresolved_rows_df["row_index"].unique()

subset_df = merged_df.loc[unresolved_idx].copy()

# --- cell 49 (GIF to JPEG path repair)
subset_updated_df, changed_rows_retry_df, unresolved_rows_retry_df = replace_gif_paths_with_jpg(
    subset_df,
    image_col="image_path",
    remove_old_gif=False,
    move_src_jpg_to_target=True,
)

# --- cell 52 (GIF to JPEG path repair)
# merged_df here = the full dataframe returned by the FIRST run
full_pass1_df = merged_df.copy()

# subset_updated_df here = the dataframe returned by the RETRY run on subset_df
unified_df = full_pass1_df.copy()

# Since your function really only changes image_path, update just that column
unified_df.loc[subset_updated_df.index, "image_path"] = subset_updated_df["image_path"]

# --- cell 53 (GIF to JPEG path repair)
unified_df.to_csv('merged_csv2.csv', index=False)

# --- cell 56 (GIF to JPEG path repair)
unified_df["image_path"] = (
    "<DATA_ROOT>/" + unified_df["image_path"]
)

# --- cell 57 (GIF to JPEG path repair)
unified_df['image_path'].to_json('new_img_paths.json')

# --- cell 59 (GIF to JPEG path repair)
new_img_paths_list = list(new_img_paths.values())

# --- cell 60 (GIF to JPEG path repair)
with open('new_img_paths.json', 'w') as f:
    json.dump(new_img_paths_list, f)
