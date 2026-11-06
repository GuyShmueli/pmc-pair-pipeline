# --- cell 9 (answer requests)
from itertools import islice

citation_valid_indices = load_json(base_path/'repro_positive_pairs_pipeline/outputs/03_citation_valid_indices.json')
citation_valid_indices_dict = {citation_valid_indices[idx]: idx for idx in range(len(citation_valid_indices))}

first_50000 = dict(islice(citation_valid_indices_dict.items(), 50_000))
rest_items = list(islice(citation_valid_indices_dict.items(), 50_000, None))

# --- cell 10 (answer requests)
answering_prompt = """You will be given:
- Case A
- Case B
- Reason for Citation
- A numbered list of comparative questions

You are an expert clinician specializing in medical imaging.

Answer each question using only the provided case information.

Rules:
- Keep the exact numbering.
- Each line must follow this format exactly:
  <number>. <Yes|No|Partial|Unclear> — <brief reason>
- The brief reason must be short and evidence-based.
- Do not add any text before or after the numbered answers.
- Do not restate the questions.
- Do not use outside knowledge or speculation.
"""

# with open(pipeline_path / 'new_batch_reqs/fir_answers_nano_high.jsonl', "w", encoding="utf-8") as f:
#     for i, curr_index in enumerate(common_indices[:50_000]):
#         case1 = case_summary_pairs[curr_index][0]
#         case2 = case_summary_pairs[curr_index][1]
#         citation_reason = fir_citation_response[first_50000[curr_index]]
#         curr_questions = fir_ques[i]

#         answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

#         ---
#         Case A:
#         {case1}

#         Case B:
#         {case2}

#         Reason for Citation, Possible Similarities and Explanation:
#         {citation_reason}

#         Questions:
#         {curr_questions}
#         ---

#         Provide your answers now:
#         """

#         request_obj = {
#             "custom_id": f"request-{i+1}",
#             "method": "POST",
#             "url": "/v1/responses",
#             "body": {
#                 "model": "gpt-5.4-nano",
#                 "reasoning": {"effort": "high"},
#                 "instructions": answering_prompt,
#                 "input": [
#                     {
#                         "role": "user",
#                         "content": answering_user
#                     }
#                 ],
#                 "text": {
#                     "format": {
#                         "type": "text"
#                     }
#                 }
#             }
#         }

#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")


# with open(pipeline_path / 'new_batch_reqs/sec_answers_nano_high.jsonl', "w", encoding="utf-8") as f:
#     for local_idx, (curr_index, _) in enumerate(rest_items):
#         global_req_id = local_idx + 50_001

#         case1 = case_summary_pairs[curr_index][0]
#         case2 = case_summary_pairs[curr_index][1]
#         citation_reason = sec_citation_response[local_idx]
#         curr_questions = sec_ques[local_idx]

#         answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

#         ---
#         Case A:
#         {case1}

#         Case B:
#         {case2}

#         Reason for Citation, Possible Similarities and Explanation:
#         {citation_reason}

#         Questions:
#         {curr_questions}
#         ---

#         Provide your answers now:
#         """

#         request_obj = {
#             "custom_id": f"request-{global_req_id}",
#             "method": "POST",
#             "url": "/v1/responses",
#             "body": {
#                 "model": "gpt-5.4-nano",
#                 "reasoning": {"effort": "high"},
#                 "instructions": answering_prompt,
#                 "input": [
#                     {
#                         "role": "user",
#                         "content": answering_user
#                     }
#                 ],
#                 "text": {
#                     "format": {
#                         "type": "text"
#                     }
#                 }
#             }
#         }

#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 21 (single retry and merge)
# Re-run the failed request - step 2
from pathlib import Path
import json

def retry_unfinished_batch(batch_id: str, input_jsonl_path: Path):
    batch = client.batches.retrieve(batch_id)

    def load_remote_jsonl(file_id: str | None):
        if not file_id:
            return []
        text = client.files.content(file_id).text
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    # Read original input and index by custom_id
    input_by_custom_id = {}
    with open(input_jsonl_path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            cid = row["custom_id"]
            if cid in input_by_custom_id:
                raise ValueError(f"Duplicate custom_id in input file: {cid}")
            input_by_custom_id[cid] = {
                "line_no": line_no,
                "raw": raw,
                "row": row,
            }

    # Read successful + error outputs from OpenAI
    output_rows = load_remote_jsonl(batch.output_file_id)
    error_rows = load_remote_jsonl(batch.error_file_id)

    completed_ids = {row["custom_id"] for row in output_rows}
    error_ids = {row["custom_id"] for row in error_rows}

    # Requests specifically cancelled by expiration
    expired_ids = [
        row["custom_id"]
        for row in error_rows
        if (row.get("error") or {}).get("code") == "batch_expired"
    ]

    # Defensive check: anything missing from both files
    unmatched_ids = sorted(set(input_by_custom_id) - completed_ids - error_ids)

    # Retry expired first; also include any unmatched IDs just in case
    retry_ids = expired_ids + [cid for cid in unmatched_ids if cid not in expired_ids]

    if not retry_ids:
        return {
            "original_batch_id": batch.id,
            "original_status": batch.status,
            "retry_ids": [],
            "message": "Nothing to retry.",
        }

    retry_path = input_jsonl_path.with_name(f"{input_jsonl_path.stem}.retry.jsonl")
    with open(retry_path, "w", encoding="utf-8") as out:
        for cid in retry_ids:
            out.write(input_by_custom_id[cid]["raw"])

    with open(retry_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")

    retry_batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=batch.endpoint,          # e.g. "/v1/responses"
        completion_window="24h",
        metadata={"description": f"retry of {batch.id}"},
    )

    return {
        "original_batch_id": batch.id,
        "original_status": batch.status,
        "retry_ids": retry_ids,
        "retry_input_file": str(retry_path),
        "retry_file_id": uploaded.id,
        "retry_batch_id": retry_batch.id,
        "retry_batch_status": retry_batch.status,
        "retry_line_numbers": [input_by_custom_id[cid]["line_no"] for cid in retry_ids],
    }

result = retry_unfinished_batch(
    "<OPENAI_ID>",
    chunks_dir / "sec_answers_nano_high.part_003.jsonl",
)

# --- cell 24 (single retry and merge)
from pathlib import Path
import json

def _read_remote_jsonl(file_id: str | None):
    if not file_id:
        return []
    text = client.files.content(file_id).text
    return [json.loads(line) for line in text.splitlines() if line.strip()]

def _read_input_order(input_jsonl_path: Path):
    order = []
    seen = set()

    with open(input_jsonl_path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            cid = row["custom_id"]
            if cid in seen:
                raise ValueError(f"Duplicate custom_id in input file: {cid}")
            seen.add(cid)
            order.append((cid, line_no))

    return order

def merge_batch_outputs_for_part(
    input_jsonl_path: Path,
    original_batch_id: str,
    retry_batch_id: str,
    merged_output_path: Path | None = None,
):
    input_order = _read_input_order(input_jsonl_path)

    original_batch = client.batches.retrieve(original_batch_id)
    retry_batch = client.batches.retrieve(retry_batch_id)

    if not original_batch.output_file_id:
        raise ValueError(f"Original batch has no output_file_id: {original_batch_id}")

    if retry_batch.status != "completed":
        raise ValueError(
            f"Retry batch is not completed yet. status={retry_batch.status}"
        )

    if not retry_batch.output_file_id:
        raise ValueError(f"Retry batch has no output_file_id: {retry_batch_id}")

    original_rows = _read_remote_jsonl(original_batch.output_file_id)
    retry_rows = _read_remote_jsonl(retry_batch.output_file_id)

    merged_by_custom_id = {}
    source_by_custom_id = {}

    # Base: original successful rows
    for row in original_rows:
        cid = row["custom_id"]
        if cid in merged_by_custom_id:
            raise ValueError(f"Duplicate custom_id in original output: {cid}")
        merged_by_custom_id[cid] = row
        source_by_custom_id[cid] = "original"

    # Overlay: retry successful rows
    for row in retry_rows:
        cid = row["custom_id"]
        merged_by_custom_id[cid] = row
        source_by_custom_id[cid] = "retry"

    merged_rows = []
    missing_after_merge = []

    # Write rows in original input order
    for cid, line_no in input_order:
        row = merged_by_custom_id.get(cid)
        if row is None:
            missing_after_merge.append({"custom_id": cid, "line_no": line_no})
        else:
            merged_rows.append(row)

    if merged_output_path is None:
        merged_output_path = input_jsonl_path.with_name(
            f"{input_jsonl_path.stem}.merged_output.jsonl"
        )

    with open(merged_output_path, "w", encoding="utf-8") as out:
        for row in merged_rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "merged_output_path": str(merged_output_path),
        "input_requests": len(input_order),
        "original_successes": len(original_rows),
        "retry_successes": len(retry_rows),
        "merged_successes": len(merged_rows),
        "missing_after_merge": missing_after_merge,
        "sources_sample": dict(list(source_by_custom_id.items())[:5]),
    }


merge_info = merge_batch_outputs_for_part(
    input_jsonl_path=chunks_dir / "sec_answers_nano_high.part_003.jsonl",
    original_batch_id="<OPENAI_ID>",
    retry_batch_id="<OPENAI_ID>",
    merged_output_path=chunks_dir / "sec_answers_nano_high.part_003.output_merged.jsonl",
)

from pprint import pprint
pprint(merge_info)

# --- cell 25 (answer alignment)
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

# --- cell 44 (answer alignment)
from pathlib import Path
from collections import Counter
import json

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

pipeline_path = Path('<DATA_ROOT>/repro_positive_pairs_pipeline')
req_dir = pipeline_path / "new_batch_reqs"

# IMPORTANT:
# - Hosted OpenAI batch outputs should stay as file IDs, e.g. "file-..."
# - The repaired sec03 should be a LOCAL merged JSONL path
#   (change this if your merged file lives elsewhere)
sec_out_03 = req_dir / "sec_answers_chunks" / "sec_answers_nano_high.part_003.output_merged.jsonl"

chunk_specs = [
    {
        "name": "fir01",
        "input_path": req_dir / "fir_answers_chunks" / "fir_answers_nano_high.part_001.jsonl",
        "output_source": fir_out_01,
    },
    {
        "name": "fir02",
        "input_path": req_dir / "fir_answers_chunks" / "fir_answers_nano_high.part_002.jsonl",
        "output_source": fir_out_02,
    },
    {
        "name": "fir03",
        "input_path": req_dir / "fir_answers_chunks" / "fir_answers_nano_high.part_003.jsonl",
        "output_source": fir_out_03,
    },
    {
        "name": "fir04",
        "input_path": req_dir / "fir_answers_chunks" / "fir_answers_nano_high.part_004.jsonl",
        "output_source": fir_out_04,
    },
    {
        "name": "sec01",
        "input_path": req_dir / "sec_answers_chunks" / "sec_answers_nano_high.part_001.jsonl",
        "output_source": sec_out_01,
    },
    {
        "name": "sec02",
        "input_path": req_dir / "sec_answers_chunks" / "sec_answers_nano_high.part_002.jsonl",
        "output_source": sec_out_02,
    },
    {
        "name": "sec03",
        "input_path": req_dir / "sec_answers_chunks" / "sec_answers_nano_high.part_003.jsonl",
        "output_source": sec_out_03,   # local merged path
    },
]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def read_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def _normalize_custom_id(x):
    return str(x)

def _manifest_get(manifest, custom_id):
    """
    Safe lookup for manifest keyed by either str/int custom IDs.
    Returns None if no manifest entry exists.
    """
    if manifest is None:
        return None

    cid_str = str(custom_id)

    if isinstance(manifest, dict):
        if cid_str in manifest:
            return manifest[cid_str]
        try:
            cid_int = int(cid_str)
            if cid_int in manifest:
                return manifest[cid_int]
        except Exception:
            pass

    return None

def read_batch_output_source(source):
    """
    source can be:
      - OpenAI hosted file id, e.g. 'file-abc123'
      - local path as Path
      - local path as str
    """
    if isinstance(source, Path):
        txt = source.read_text(encoding="utf-8")
        return [json.loads(line) for line in txt.splitlines() if line.strip()]

    source = str(source).strip()
    if not source:
        raise ValueError("Empty output_source")

    if source.startswith("file-"):
        txt = client.files.content(source).text
        return [json.loads(line) for line in txt.splitlines() if line.strip()]

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Local output file does not exist: {path}")
    txt = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in txt.splitlines() if line.strip()]

def _extract_status_code(output_row):
    """
    Supports raw batch output rows:
      {
        "custom_id": "...",
        "response": {"status_code": 200, "body": ...},
        "error": null
      }
    and also any already-flattened rows that happen to contain status_code at top level.
    """
    if output_row is None:
        return None

    if "status_code" in output_row and output_row["status_code"] is not None:
        return output_row["status_code"]

    response = output_row.get("response")
    if isinstance(response, dict):
        return response.get("status_code")

    return None

def verify_input_file(input_path: Path, manifest):
    """
    Keeps the same fields your audit code expects.
    """
    reqs = read_jsonl(input_path)
    custom_ids = [_normalize_custom_id(r["custom_id"]) for r in reqs]

    duplicate_custom_ids = [cid for cid, cnt in Counter(custom_ids).items() if cnt > 1]

    contiguous_in_file_order = True
    min_custom_id = None
    max_custom_id = None

    numeric_ids = []
    for cid in custom_ids:
        try:
            numeric_ids.append(int(cid))
        except Exception:
            pass

    if numeric_ids:
        min_custom_id = min(numeric_ids)
        max_custom_id = max(numeric_ids)
        contiguous_in_file_order = numeric_ids == list(range(min_custom_id, max_custom_id + 1))
    else:
        contiguous_in_file_order = False

    # Manifest mismatch check:
    # if a manifest entry exists and stores custom_id, verify consistency.
    n_mismatches = 0
    for req in reqs:
        cid = _normalize_custom_id(req["custom_id"])
        m = _manifest_get(manifest, cid)
        if m is None:
            continue

        m_cid = m.get("custom_id")
        if m_cid is not None and _normalize_custom_id(m_cid) != cid:
            n_mismatches += 1

    return {
        "n_rows": len(reqs),
        "min_custom_id": min_custom_id,
        "max_custom_id": max_custom_id,
        "contiguous_in_file_order": contiguous_in_file_order,
        "duplicate_custom_ids": duplicate_custom_ids,
        "n_mismatches": n_mismatches,
    }

def align_output_to_input(input_path: Path, output_source, manifest):
    """
    Aligns output rows to input order using custom_id.
    Works with either:
      - hosted batch output file IDs
      - local merged JSONL files
    """
    reqs = read_jsonl(input_path)
    outs = read_batch_output_source(output_source)

    input_rows_by_id = {}
    input_ids_in_order = []
    for req in reqs:
        cid = _normalize_custom_id(req["custom_id"])
        input_ids_in_order.append(cid)
        input_rows_by_id[cid] = req

    output_rows_by_id = {}
    duplicate_output_custom_ids = []
    for out in outs:
        cid = _normalize_custom_id(out["custom_id"])
        if cid in output_rows_by_id:
            duplicate_output_custom_ids.append(cid)
            continue
        output_rows_by_id[cid] = out

    input_id_set = set(input_rows_by_id.keys())
    output_id_set = set(output_rows_by_id.keys())

    missing_custom_ids = [cid for cid in input_ids_in_order if cid not in output_id_set]
    extra_custom_ids = [cid for cid in output_rows_by_id.keys() if cid not in input_id_set]

    aligned = []
    for cid in input_ids_in_order:
        req = input_rows_by_id[cid]
        out = output_rows_by_id.get(cid)
        manifest_row = _manifest_get(manifest, cid)

        aligned.append({
            "custom_id": cid,
            "input_row": req,
            "output_row": out,
            "manifest_row": manifest_row,
            "status_code": _extract_status_code(out),
            "error": None if out is None else out.get("error"),
            "missing_output": out is None,
        })

    return {
        "input_rows": len(reqs),
        "output_rows": len(outs),
        "aligned": aligned,
        "missing_custom_ids": missing_custom_ids,
        "extra_custom_ids": extra_custom_ids,
        "duplicate_output_custom_ids": duplicate_output_custom_ids,
    }

def audit_chunk(name, input_path, output_source, manifest):
    vin = verify_input_file(input_path, manifest)
    aligned_obj = align_output_to_input(input_path, output_source, manifest)

    bad_status_rows = sum(x.get("status_code") != 200 for x in aligned_obj["aligned"])

    ok = (
        vin["n_mismatches"] == 0
        and len(vin["duplicate_custom_ids"]) == 0
        and len(aligned_obj["missing_custom_ids"]) == 0
        and len(aligned_obj["extra_custom_ids"]) == 0
        and len(aligned_obj["duplicate_output_custom_ids"]) == 0
        and bad_status_rows == 0
    )

    summary = {
        "name": name,
        "ok": ok,
        "input_path": str(input_path),
        "output_source": str(output_source),
        "input_rows": vin["n_rows"],
        "min_custom_id": vin["min_custom_id"],
        "max_custom_id": vin["max_custom_id"],
        "contiguous_in_file_order": vin["contiguous_in_file_order"],
        "duplicate_input_custom_ids": len(vin["duplicate_custom_ids"]),
        "prompt_mismatches": vin["n_mismatches"],
        "output_rows": aligned_obj["output_rows"],
        "missing_output_custom_ids": len(aligned_obj["missing_custom_ids"]),
        "extra_output_custom_ids": len(aligned_obj["extra_custom_ids"]),
        "duplicate_output_custom_ids": len(aligned_obj["duplicate_output_custom_ids"]),
        "bad_status_rows": bad_status_rows,
    }

    return summary, aligned_obj

# ------------------------------------------------------------------
# Run audit
# ------------------------------------------------------------------

manifest = build_answer_manifest()

all_chunk_summaries = []
all_chunk_aligned = {}

for spec in chunk_specs:
    summary, aligned_obj = audit_chunk(
        name=spec["name"],
        input_path=spec["input_path"],
        output_source=spec["output_source"],
        manifest=manifest,
    )
    all_chunk_summaries.append(summary)
    all_chunk_aligned[spec["name"]] = aligned_obj

for s in all_chunk_summaries:
    print(json.dumps(s, indent=2))

bad_chunks = [s["name"] for s in all_chunk_summaries if not s["ok"]]
print("\nBad chunks:", bad_chunks)

# --- cell 45 (answer alignment)
def get_aligned_final_texts(chunk_name):
    texts = []
    for i, x in enumerate(all_chunk_aligned[chunk_name]["aligned"]):
        out = x.get("output_row")
        if out is None:
            raise ValueError(f"{chunk_name}: missing output_row at aligned index {i}, custom_id={x.get('custom_id')}")
        texts.append(extract_final_text(out))
    return texts
    
# aligned answers lists for those chunks
fir_answ_01 = get_aligned_final_texts("fir01")
fir_answ_02 = get_aligned_final_texts("fir02")
fir_answ_03 = get_aligned_final_texts("fir03")
fir_answ_04 = get_aligned_final_texts("fir04")
sec_answ_01 = get_aligned_final_texts("sec01")
sec_answ_02 = get_aligned_final_texts("sec02")
sec_answ_03 = get_aligned_final_texts("sec03")

aligned_dir = pipeline_path / "outputs" / "aligned_answers"
aligned_dir.mkdir(parents=True, exist_ok=True)

all_answers = {
    "fir_answ_01": fir_answ_01,
    "fir_answ_02": fir_answ_02,
    "fir_answ_03": fir_answ_03,
    "fir_answ_04": fir_answ_04,
    "sec_answ_01": sec_answ_01,
    "sec_answ_02": sec_answ_02,
    "sec_answ_03": sec_answ_03,
}

for name, answers in all_answers.items():
    dump_json(aligned_dir / f"{name}.json", answers)
