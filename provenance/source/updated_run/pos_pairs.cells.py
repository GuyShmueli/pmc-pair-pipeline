# --- cell 5 (pair requests)
common_indices = load_json(base_path/'repro_positive_pairs_pipeline/outputs/03_common_indices.json')

# --- cell 7 (pair requests)
filtered_pair_image_paths = [pair_image_paths[i] for i in common_indices]

# --- cell 8 (pair requests)
filtered_pair_text_paths = [pair_text_paths[i] for i in common_indices]

# --- cell 16 (pair requests)
stems_3d = [
    [
        [Path(p).stem for p in sin_patient]   # 3rd level: every path in one patient
        for sin_patient in pair              # 2nd level: both patients in the pair
    ]
    for pair in filtered_pair_text_paths              # 1st level: all pairs
]

stems_3d[0:1]

# --- cell 18 (pair requests)
def build_stem_caption_3d(pairs_text, stems_3d):
    """
    Return a 3-D list with the same nesting as `pairs_text`
    [
        [                                # each pair
            {stem: caption, …},         # patient-0  (dict of every caption)
            {stem: caption, …}          # patient-1
        ],
        ...
    ]
    """
    return [
        [
            {stem: cap                                     # <-- inner dict
             for stem, cap in zip(stems_patient, caps_patient)}
            for stems_patient, caps_patient                # iterate over the
            in zip(stems_pair, caps_pair)                  # two patients
        ]
        for stems_pair, caps_pair                          # iterate over pairs
        in zip(stems_3d, pairs_text)
    ]

stem_caption_list = build_stem_caption_3d(filtered_pair_text_paths, stems_3d)

# --- cell 20 (pair requests)
# The invalid caption-pairs rise when all the captions in patient1 or patient2 are filtered out (diagrams)
invalid_pairs_indices = [i for i, inner in enumerate(stem_caption_list) if len(inner) < 2]
invalid_pairs_indices_set = set(invalid_pairs_indices)

# --- cell 23 (pair requests)
# Load responses from stage 02
all_questions = [
    "fir_ques_01",
    "fir_ques_02",
    "fir_ques_03",
    "sec_ques_01",
    "sec_ques_02",
]

loaded_questions = {
    name: load_json(quest_dir / f"{name}.json")
    for name in all_questions
}


fir_ques_01 = loaded_questions['fir_ques_01']
fir_ques_02 = loaded_questions['fir_ques_02']
fir_ques_03 = loaded_questions['fir_ques_03']
sec_ques_01 = loaded_questions['sec_ques_01']
sec_ques_02 = loaded_questions['sec_ques_02']


questions_response = fir_ques_01 + fir_ques_02 + fir_ques_03 + sec_ques_01 + sec_ques_02

# --- cell 25 (pair requests)
# Load responses from stage 03
all_answers = [
    "fir_answ_01",
    "fir_answ_02",
    "fir_answ_03",
    "fir_answ_04",
    "sec_answ_01",
    "sec_answ_02",
    "sec_answ_03"
]

loaded_answers = {
    name: load_json(answ_dir / f"{name}.json")
    for name in all_answers
}


fir_answ_01 = loaded_answers['fir_answ_01']
fir_answ_02 = loaded_answers['fir_answ_02']
fir_answ_03 = loaded_answers['fir_answ_03']
fir_answ_04 = loaded_answers['fir_answ_04']
sec_answ_01 = loaded_answers['sec_answ_01']
sec_answ_02 = loaded_answers['sec_answ_02']
sec_answ_03 = loaded_answers['sec_answ_03']


answers_response = fir_answ_01 + fir_answ_02 + fir_answ_03 + fir_answ_04 + sec_answ_01 + sec_answ_02 + sec_answ_03

# --- cell 27 (pair requests)
pair_caption_dicts = load_json('<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/01_pair_caption_dicts.json')

# --- cell 30 (pair requests)
filtered_pair_caption_dicts = [pair_caption_dicts[i] for i in common_indices]

# --- cell 41 (text from raw batch output)
def extract_final_text(d):
    output = d.get("response", {}).get("body", {}).get("output", [])

    # Prefer the final assistant message if tagged that way
    for item in output:
        if item.get("type") == "message" and item.get("phase") == "final_answer":
            texts = [
                c["text"]
                for c in item.get("content", [])
                if c.get("type") == "output_text" and "text" in c
            ]
            return "\n".join(texts) if texts else None

    # Fallback: take the last message item
    for item in reversed(output):
        if item.get("type") == "message":
            texts = [
                c["text"]
                for c in item.get("content", [])
                if c.get("type") == "output_text" and "text" in c
            ]
            return "\n".join(texts) if texts else None

    return None

# --- cell 65 (pair requests)
POSITIVE_PAIR_PROMPT = """You are a medical-AI expert.

You will receive:
1. Patient-context questions and answers for a case pair.
2. A dictionary of caption_id -> caption for Case A.
3. A dictionary of caption_id -> caption for Case B.

Your task is to evaluate every inter-case caption pair (one caption from Case A and one caption from Case B) and return only the POSITIVE matches.

IMPORTANT PRE-FILTER: RADIOLOGY IMAGES ONLY
Before forming any pairs, keep only captions that describe radiology imaging modalities.
Valid radiology modality families include:
- CT / OCT
- MRI
- X-ray / radiograph
- Fluoroscopy
- Mammography
- Ultrasound / sonography
- Angiography
- Nuclear medicine / hybrid imaging such as PET, SPECT, PET/CT, PET/MR

Ignore any caption that is NOT radiology imaging, including:
- clinical photographs or gross inspection images
- dermatology / operative / specimen photos
- pathology / histology / cytology / microscopy / IHC stains
- endoscopy / colonoscopy / bronchoscopy / EGD
- ECG / EKG / EEG
- ophthalmic photography / fundus imaging / OCT / OCTA / FA / ICG
- diagrams / illustrations / schematics
- any other non-radiology image

A pair is POSITIVE only if:
1. It is inter-case.
2. Both captions pass the radiology-only filter above.
3. The two captions describe the same modality family, ignoring view/plane/sequence details.
4. The two captions describe the same pathology family within the same anatomy / organ system.
5. You ignore decorators such as acuity, severity, laterality, exact slice, or exact level.

Output rules:
- Output valid JSON only, with no markdown and no prose.
- Output a JSON array.
- Each item must have exactly these keys:
  {
    "pair_id": ["caption_id_from_case_a", "caption_id_from_case_b"],
    "modality": "<shared modality family>",
    "anatomy": "<shared anatomy or organ system>",
    "diagnosis": "<shared pathology family>"
  }
- Use caption IDs exactly as they appear in the provided dictionaries.
- Do not output pairs involving any filtered-out caption.
- If there are no positive matches, output []."""

# --- cell 66 (pair requests)
batch_size = 50_000
model_name = "gpt-5.4-mini"
reasoning_effort = "low"

output_dir = pipeline_path / "new_batch_reqs"
output_dir.mkdir(parents=True, exist_ok=True)

# Build valid items while preserving:
# - original_idx: position in enumerate(common_indices)
# - valid_idx: position among non-invalid pairs
# - common_index: original pair index / id
valid_items = []
for original_idx, common_index in enumerate(common_indices):
    if common_index in invalid_pairs_indices_set:
        continue
    valid_idx = len(valid_items)
    valid_items.append((valid_idx, original_idx, common_index))

first_50000 = valid_items[:batch_size]
rest_items = valid_items[batch_size:]


def build_request_obj(request_id, valid_idx, original_idx, common_index):
    # CAPTIONS:
    # Use valid_idx if filtered_pair_caption_dicts is aligned to the filtered valid-pair order.
    captions1 = filtered_pair_caption_dicts[valid_idx][0]
    captions2 = filtered_pair_caption_dicts[valid_idx][1]

    # Q/A:
    # Keep original_idx because that matches your original code logic.
    curr_questions = questions_response[original_idx]
    curr_answers = answers_response[original_idx]

    user_content = f"""### PATIENT-CONTEXT QUERIES & ANSWERS
{curr_questions}

{curr_answers}

### IMAGE CAPTIONS (MULTIPLE PAIRS)
{captions1}

{captions2}
"""

    return {
        "custom_id": f"request-{request_id}",
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "model": model_name,
            "reasoning": {"effort": reasoning_effort},
            "instructions": POSITIVE_PAIR_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "text": {
                "format": {
                    "type": "text"
                }
            }
        }
    }


def write_batch_jsonl(file_path, items, start_request_id):
    with open(file_path, "w", encoding="utf-8") as f:
        for offset, (valid_idx, original_idx, common_index) in enumerate(items):
            request_obj = build_request_obj(
                request_id=start_request_id + offset,
                valid_idx=valid_idx,
                original_idx=original_idx,
                common_index=common_index,
            )
            f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")


write_batch_jsonl(
    output_dir / "fir_pos_pairs_mini_low.jsonl",
    first_50000,
    start_request_id=1,
)

if rest_items:
    write_batch_jsonl(
        output_dir / "sec_pos_pairs_mini_low.jsonl",
        rest_items,
        start_request_id=len(first_50000) + 1,
    )

print(f"Part 1 requests: {len(first_50000)}")
print(f"Part 2 requests: {len(rest_items)}")
print(f"Total valid requests: {len(valid_items)}")

# --- cell 67 (batch splitting)
# Batch sub-files

MAX_REQUESTS_PER_BATCH = 50_000
MAX_FILE_BYTES = 190 * 1024 * 1024  # keep headroom under the 200 MB limit

def split_jsonl_for_batches(input_path: Path,
                            out_dir: Path,
                            max_requests: int = MAX_REQUESTS_PER_BATCH,
                            max_bytes: int = MAX_FILE_BYTES):
    chunk_infos = []
    part_idx = 1
    chunk_lines = 0
    chunk_bytes = 0

    current_path = out_dir / f"{input_path.stem}.part_{part_idx:03d}.jsonl"
    current_file = open(current_path, "w", encoding="utf-8")

    with open(input_path, "r", encoding="utf-8") as src:
        for raw_line in src:
            if not raw_line.strip():
                continue

            raw_size = len(raw_line.encode("utf-8"))

            # Start a new chunk before writing this line if it would exceed limits.
            if chunk_lines > 0 and (
                chunk_lines >= max_requests or
                (chunk_bytes + raw_size) > max_bytes
            ):
                current_file.close()
                chunk_infos.append({
                    "path": current_path,
                    "requests": chunk_lines,
                    "bytes": chunk_bytes,
                })

                part_idx += 1
                current_path = out_dir / f"{input_path.stem}.part_{part_idx:03d}.jsonl"
                current_file = open(current_path, "w", encoding="utf-8")
                chunk_lines = 0
                chunk_bytes = 0

            current_file.write(raw_line)
            chunk_lines += 1
            chunk_bytes += raw_size

    current_file.close()

    if chunk_lines > 0:
        chunk_infos.append({
            "path": current_path,
            "requests": chunk_lines,
            "bytes": chunk_bytes,
        })

    return chunk_infos


def submit_batch_file(jsonl_path: Path, description: str):
    with open(jsonl_path, "rb") as f:
        uploaded = client.files.create(
            file=f,
            purpose="batch",
        )

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"description": description},
    )

    return {
        "file_name": jsonl_path.name,
        "file_id": uploaded.id,
        "batch_id": batch.id,
        "status": batch.status,
    }

# --- cell 70 (text from raw batch output)
fir_out_01 = "<OPENAI_ID>"
file_response = client.files.content(fir_out_01)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

fir_pairs_01 = [extract_final_text(d) for d in response_dicts]

# --- cell 71 (text from raw batch output)
fir_out_02 = "<OPENAI_ID>"
file_response = client.files.content(fir_out_02)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

fir_pairs_02 = [extract_final_text(d) for d in response_dicts]

# --- cell 72 (text from raw batch output)
fir_out_03 = "<OPENAI_ID>"
file_response = client.files.content(fir_out_03)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

fir_pairs_03 = [extract_final_text(d) for d in response_dicts]

# --- cell 76 (text from raw batch output)
sec_out_01 = "<OPENAI_ID>"
file_response = client.files.content(sec_out_01)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

sec_pairs_01 = [extract_final_text(d) for d in response_dicts]

# --- cell 77 (text from raw batch output)
sec_out_02 = "<OPENAI_ID>"
file_response = client.files.content(sec_out_02)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

sec_pairs_02 = [extract_final_text(d) for d in response_dicts]

# --- cell 79 (text from raw batch output)
pos_pairs = fir_pairs_01 + fir_pairs_02 + fir_pairs_03 + sec_pairs_01 + sec_pairs_02

# --- cell 80 (text from raw batch output)
dump_json("<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/updated_pos_pairs.json", pos_pairs)

# --- cell 89 (parser, buckets and saved outputs; updated-run bucket assignment and by-bucket file)
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

try:
    from tqdm.auto import tqdm
except Exception:
    def tqdm(x, **kwargs):
        return x


# ----------------------------
# helpers
# ----------------------------

_PAIR_ID_CLEAN_RE = re.compile(r"[^0-9_,]")
_ID_RE = re.compile(r"\d+_\d+_\d+")
_OBJECT_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.S)


def strip_code_fences(text):
    if text is None:
        return ""
    text = str(text).strip()
    if not text:
        return ""
    text = re.sub(r"^\s*```(?:[A-Za-z0-9_+-]+)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def normalize_text_pair_item(item):
    if item is None:
        return []
    if isinstance(item, str):
        s = item.strip()
        return [s] if s else []
    if isinstance(item, (list, tuple)):
        out = []
        for x in item:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    s = str(item).strip()
    return [s] if s else []


def normalize_pair_id(pair_id_val):
    if pair_id_val is None:
        return None

    if isinstance(pair_id_val, (list, tuple)):
        text = ",".join(str(item) for item in pair_id_val)
    else:
        text = str(pair_id_val)

    cleaned = _PAIR_ID_CLEAN_RE.sub("", text)
    parts = [part for part in cleaned.split(",") if part]
    return parts if parts else None


def canonical_pair_key(pair_id):
    a, b = str(pair_id[0]).strip(), str(pair_id[1]).strip()
    return tuple(sorted((a, b)))


def build_short_caption_from_record(obj):
    diagnosis = str(obj.get("diagnosis", "")).strip()
    anatomy = str(obj.get("anatomy", "")).strip()
    modality = str(obj.get("modality", "")).strip()

    parts = []
    if diagnosis:
        parts.append(diagnosis)
    if anatomy:
        parts.append(f"in the {anatomy}")
    if modality:
        parts.append(f"on {modality}")

    caption = " ".join(parts).strip()
    if caption and not caption.endswith("."):
        caption += "."
    return [caption] if caption else []


def modality_bucket(modality, legacy_order=False):
    value = (modality or "").strip().lower()

    radiology_keywords = [
        "ct",
        "computed tomography",
        "mri",
        "magnetic resonance",
        "radiograph",
        "x-ray",
        "xray",
        "ultrasound",
        "sonograph",
        "sonography",
        "pet",
        "spect",
        "angiograph",
        "angiography",
        "fluoroscopy",
        "mammograph",
        "mammography",
        "tomograph",
        "tomography",
    ]
    pathology_keywords = [
        "histolog",
        "patholog",
        "microscop",
        "immunohistochem",
        "ihc",
        "hematoxylin",
        "eosin",
        "h&e",
        "stain",
        "biopsy",
        "slide",
    ]
    ophtho_keywords = [
        "fundus",
        "oct",
        "optical coherence",
        "slit lamp",
        "fluorescein",
        "indocyanine",
        "retinal",
        "ophthalm",
    ]
    endoscopy_keywords = [
        "endoscop",
        "colonoscopy",
        "gastroscopy",
        "bronchoscopy",
        "laparoscopy",
        "hysteroscopy",
        "arthroscopy",
    ]
    cardiology_keywords = [
        "ecg",
        "ekg",
        "electrocardi",
        "echocardi",
        "echo",
    ]

    if legacy_order:
        if any(keyword in value for keyword in radiology_keywords):
            return "radiology"
        if any(keyword in value for keyword in pathology_keywords):
            return "pathology_microscopy"
        if any(keyword in value for keyword in ophtho_keywords):
            return "ophthalmology"
        if any(keyword in value for keyword in endoscopy_keywords):
            return "endoscopy"
        if any(keyword in value for keyword in cardiology_keywords):
            return "cardiology"
        return "other"

    if any(keyword in value for keyword in pathology_keywords):
        return "pathology_microscopy"
    if any(keyword in value for keyword in ophtho_keywords):
        return "ophthalmology"
    if any(keyword in value for keyword in endoscopy_keywords):
        return "endoscopy"
    if any(keyword in value for keyword in cardiology_keywords):
        return "cardiology"
    if any(keyword in value for keyword in radiology_keywords):
        return "radiology"
    return "other"


def parse_jsonish_obj(raw):
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None

    text = strip_code_fences(raw)
    if not text:
        return []

    candidates = [text]

    first_arr = text.find("[")
    last_arr = text.rfind("]")
    if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
        candidates.append(text[first_arr:last_arr + 1])

    first_obj = text.find("{")
    last_obj = text.rfind("}")
    if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
        candidates.append(text[first_obj:last_obj + 1])

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)

        try:
            return json.loads(candidate)
        except Exception:
            pass

        try:
            return ast.literal_eval(candidate)
        except Exception:
            pass

    return None


def flatten_dict_records(obj):
    records = []

    def recurse(value):
        if value is None:
            return
        if isinstance(value, dict):
            if value != {}:
                records.append(value)
            return
        if isinstance(value, list):
            for item in value:
                recurse(item)

    recurse(obj)
    return records


def parse_jsonish_to_records(raw):
    obj = parse_jsonish_obj(raw)
    if obj is None:
        return None
    return flatten_dict_records(obj)


def _extract_field_from_text(text, field):
    patterns = [
        rf'"{re.escape(field)}"\s*:\s*"([^"]*)"',
        rf"'{re.escape(field)}'\s*:\s*'([^']*)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.S)
        if match:
            return match.group(1).strip()
    return None


def salvage_records_from_raw_text(raw):
    text = strip_code_fences(str(raw))
    if not text:
        return []

    candidate_blocks = _OBJECT_BLOCK_RE.findall(text)
    if not candidate_blocks:
        candidate_blocks = [text]

    recovered = []
    seen = set()

    for block in candidate_blocks:
        obj = parse_jsonish_obj(block)
        if isinstance(obj, dict) and obj:
            pair_id = normalize_pair_id(obj.get("pair_id"))
            if pair_id and len(pair_id) == 2:
                obj2 = dict(obj)
                obj2["pair_id"] = pair_id
                key = tuple(pair_id)
                if key not in seen:
                    seen.add(key)
                    recovered.append(obj2)
                continue

        pair_val = _extract_field_from_text(block, "pair_id")
        pair_id = normalize_pair_id(pair_val)

        if not pair_id or len(pair_id) != 2:
            ids = _ID_RE.findall(block)
            if len(ids) >= 2:
                pair_id = [ids[0], ids[1]]

        if not pair_id or len(pair_id) != 2:
            continue

        rec = {
            "pair_id": pair_id,
            "modality": _extract_field_from_text(block, "modality") or "",
            "anatomy": _extract_field_from_text(block, "anatomy") or "",
            "diagnosis": _extract_field_from_text(block, "diagnosis") or "",
            "reasoning": _extract_field_from_text(block, "reasoning") or "",
        }

        key = tuple(pair_id)
        if key not in seen:
            seen.add(key)
            recovered.append(rec)

    return recovered


def _validate_inter_case_pair(pair_id, case_a_ids, case_b_ids):
    if len(pair_id) != 2:
        return None

    left, right = pair_id[0], pair_id[1]
    if left in case_a_ids and right in case_b_ids:
        return [left, right]
    if left in case_b_ids and right in case_a_ids:
        return [right, left]
    return None


def process_positive_responses(
    response_texts,
    request_indices,
    pair_caption_dicts,
    legacy_modality_bucket=False,
    show_progress=True,
):
    if len(response_texts) != len(request_indices):
        raise ValueError(
            f"Length mismatch: len(response_texts)={len(response_texts)} vs "
            f"len(request_indices)={len(request_indices)}"
        )

    labeled_all = []
    pairs_clean_all = []
    text_pairs_all = []
    bad_rows = []

    by_bucket = defaultdict(lambda: {"labeled": [], "pairs_clean": [], "text_pairs": []})
    seen_pairs = set()

    empty_outputs = 0
    parse_failures = 0
    regex_salvaged_outputs = 0
    invalid_pair_ids = 0
    duplicate_pairs = 0
    multi_record_outputs = 0

    iterator = zip(response_texts, request_indices)
    if show_progress:
        iterator = tqdm(iterator, total=len(response_texts), desc="Post-processing positive pairs")

    for request_position, (raw, original_pair_index) in enumerate(iterator):
        pair_caption_group = pair_caption_dicts[original_pair_index]

        if not isinstance(pair_caption_group, list) or len(pair_caption_group) != 2:
            bad_rows.append(
                {
                    "request_position": request_position,
                    "pair_index": original_pair_index,
                    "reason": "missing_caption_group",
                }
            )
            continue

        case_a_captions = pair_caption_group[0] or {}
        case_b_captions = pair_caption_group[1] or {}
        case_a_ids = set(case_a_captions.keys())
        case_b_ids = set(case_b_captions.keys())

        records = parse_jsonish_to_records(raw)
        source_type = "parsed"

        if records is None or len(records) == 0:
            salvaged = salvage_records_from_raw_text(raw)
            if salvaged:
                records = salvaged
                source_type = "regex_salvaged"
                regex_salvaged_outputs += 1

        if records is None:
            parse_failures += 1
            bad_rows.append(
                {
                    "request_position": request_position,
                    "pair_index": original_pair_index,
                    "reason": "unparseable",
                    "raw_preview": str(raw)[:500],
                }
            )
            continue

        if len(records) == 0:
            empty_outputs += 1
            continue

        if len(records) > 1:
            multi_record_outputs += 1

        for subidx, obj in enumerate(records):
            pair_id = normalize_pair_id(obj.get("pair_id"))
            if not pair_id or len(pair_id) != 2:
                invalid_pair_ids += 1
                bad_rows.append(
                    {
                        "request_position": request_position,
                        "pair_index": original_pair_index,
                        "subidx": subidx,
                        "reason": "bad_pair_id",
                        "pair_id": obj.get("pair_id"),
                        "raw_preview": str(raw)[:500],
                        "source_type": source_type,
                    }
                )
                continue

            validated_pair = _validate_inter_case_pair(pair_id, case_a_ids, case_b_ids)
            if validated_pair is None:
                invalid_pair_ids += 1
                bad_rows.append(
                    {
                        "request_position": request_position,
                        "pair_index": original_pair_index,
                        "subidx": subidx,
                        "reason": "pair_id_not_in_case_caption_dicts",
                        "pair_id": pair_id,
                        "allowed_case_a_ids": sorted(case_a_ids),
                        "allowed_case_b_ids": sorted(case_b_ids),
                        "source_type": source_type,
                    }
                )
                continue

            canonical_key = canonical_pair_key(validated_pair)
            if canonical_key in seen_pairs:
                duplicate_pairs += 1
                continue

            seen_pairs.add(canonical_key)

            record = dict(obj)
            record["pair_id"] = list(canonical_key)
            record["source_pair_index"] = original_pair_index
            record["request_position"] = request_position
            record["source_type"] = source_type

            bucket = modality_bucket(
                str(record.get("modality", "")),
                legacy_order=legacy_modality_bucket,
            )
            record["modality_bucket"] = bucket

            caption = build_short_caption_from_record(record)

            labeled_all.append(record)
            pairs_clean_all.append(list(canonical_key))
            text_pairs_all.append(caption)

            by_bucket[bucket]["labeled"].append(record)
            by_bucket[bucket]["pairs_clean"].append(list(canonical_key))
            by_bucket[bucket]["text_pairs"].append(caption)

    stats = {
        "requests_processed": len(response_texts),
        "labeled_pairs_kept": len(labeled_all),
        "empty_outputs": empty_outputs,
        "parse_failures": parse_failures,
        "regex_salvaged_outputs": regex_salvaged_outputs,
        "invalid_pair_ids": invalid_pair_ids,
        "duplicate_pairs_removed": duplicate_pairs,
        "multi_record_outputs": multi_record_outputs,
        "bucket_sizes": {
            bucket: len(payload["pairs_clean"])
            for bucket, payload in by_bucket.items()
        },
        "radiology_pairs_kept": len(by_bucket.get("radiology", {}).get("pairs_clean", [])),
    }

    return {
        "labeled_all": labeled_all,
        "pairs_clean_all": pairs_clean_all,
        "text_pairs_all": [normalize_text_pair_item(item) for item in text_pairs_all],
        "by_bucket": dict(by_bucket),
        "bad_rows": bad_rows,
        "stats": stats,
    }


def save_json(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --- cell 90 (parser, buckets and saved outputs; updated-run bucket assignment and by-bucket file)
assert len(pos_pairs) == len(common_indices)
assert max(common_indices) < len(pair_caption_dicts)

# common_indices is the same thing the original script called request_indices
result = process_positive_responses(
    response_texts=pos_pairs,
    request_indices=common_indices,
    pair_caption_dicts=pair_caption_dicts,
    legacy_modality_bucket=False,   # set True only if you want the notebook's old bucket precedence
    show_progress=True,
)

radiology_bucket = result["by_bucket"].get(
    "radiology",
    {"labeled": [], "pairs_clean": [], "text_pairs": []},
)

print(result["stats"])
print("All positive pairs kept:", len(result["pairs_clean_all"]))
print("Radiology positive pairs kept:", len(radiology_bucket["pairs_clean"]))
print("Bad rows logged:", len(result["bad_rows"]))

# --- cell 92 (parser, buckets and saved outputs; updated-run bucket assignment and by-bucket file)
output_dir = Path("<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/postprocessed")

save_json(result["labeled_all"], output_dir / "labeled_positive_pairs.json")
save_json(result["pairs_clean_all"], output_dir / "positive_pairs_clean.json")
save_json(result["text_pairs_all"], output_dir / "text_pairs.json")
save_json(result["by_bucket"], output_dir / "positive_pairs_by_bucket.json")
save_json(radiology_bucket["labeled"], output_dir / "radiology_labeled_positive_pairs.json")
save_json(radiology_bucket["pairs_clean"], output_dir / "radiology_pairs_clean.json")
save_json(radiology_bucket["text_pairs"], output_dir / "radiology_text_pairs.json")
save_json(result["bad_rows"], output_dir / "bad_rows.json")
save_json(result["stats"], output_dir / "final_stats.json")

print("Saved to:", output_dir)
