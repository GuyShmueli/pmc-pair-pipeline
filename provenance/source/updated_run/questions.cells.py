# --- cell 1 (question requests)
citation_valid_indices = load_json(base_path/'repro_positive_pairs_pipeline/outputs/03_citation_valid_indices.json')
citation_valid_indices_dict = {citation_valid_indices[idx]: idx for idx in range(len(citation_valid_indices))}

# --- cell 2 (question requests)
# Load responses from stage 01
case_summary_pairs = load_json(base_path/'repro_positive_pairs_pipeline/outputs/02_case_summary_pairs.json')
common_indices = load_json(base_path/'repro_positive_pairs_pipeline/outputs/03_common_indices.json')

# --- cell 3 (question requests)
question_generating_prompt = """You are a clinician specializing in medical imaging. Given two cited cases and the citation reason, generate at most 9 numbered comparative questions that operationalize the citation reason and help determine both:
(1) what shared diagnostic lesson the two cases illustrate, and
(2) whether they share a diagnosis or differ in clinically important ways.

Requirements:
- Focus on diagnostically meaningful imaging findings, clinical presentation, pathophysiology, and hallmark symptoms.
- Avoid trivial or purely technical details.
- Compare Case A and Case B explicitly; prefer yes/no questions when natural.
- Group the questions under subtitles:
  Level 1 - modality / organ system
  Level 2 - broad diagnostic category
  Level 3 - specific imaging and clinical features
- Do not add any introduction, decoration, note, or follow-up suggestion."""

question_generating_user = """Read the two cases and the citation reason, then generate the comparative questions.

Case A:
%s

Case B:
%s

Citation reason:
%s"""

# --- cell 4 (question requests)
first_50000 = dict(islice(citation_valid_indices_dict.items(), 50_000))
rest_items = list(islice(citation_valid_indices_dict.items(), 50_000, None))

# --- cell 6 (question requests)
with open(Path(pipeline_path) / "outputs/fir_citation_response.json", 'r') as f:
    fir_citation_response = json.load(f)

with open(Path(pipeline_path) / "outputs/sec_citation_response.json", 'r') as g:
    sec_citation_response = json.load(g)

# --- cell 8 (question requests)
# with open(os.path.join(pipeline_path, 'new_batch_reqs/fir_questions_nano_high.jsonl'), "w", encoding="utf-8") as f:
#     for i, curr_index in enumerate(common_indices[:50_000], start=1):

#         case1 = case_summary_pairs[curr_index][0]
#         case2 = case_summary_pairs[curr_index][1]
#         citation_reason = fir_citation_response[first_50000[curr_index]]

#         user_content = question_generating_user % (case1, case2, citation_reason)

#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/responses",
#             "body": {
#                 "model": "gpt-5.4-nano",
#                 "reasoning": {"effort": "high"},
#                 "instructions": question_generating_prompt,
#                 "input": [
#                     {
#                         "role": "user",
#                         "content": user_content
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

# --- cell 9 (question requests)
# with open(os.path.join(pipeline_path, 'new_batch_reqs/sec_questions_nano_high.jsonl'), "w", encoding="utf-8") as f:
#     for local_idx, (curr_index, _) in enumerate(rest_items):
#         global_req_id = local_idx + 50_001

#         case1 = case_summary_pairs[curr_index][0]
#         case2 = case_summary_pairs[curr_index][1]
#         citation_reason = sec_citation_response[local_idx]

#         user_content = question_generating_user % (case1, case2, citation_reason)

#         request_obj = {
#             "custom_id": f"request-{global_req_id}",
#             "method": "POST",
#             "url": "/v1/responses",
#             "body": {
#                 "model": "gpt-5.4-nano",
#                 "reasoning": {"effort": "high"},
#                 "instructions": question_generating_prompt,
#                 "input": [
#                     {
#                         "role": "user",
#                         "content": user_content
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

# --- cell 15 (question alignment by custom_id)
# Read first Responses (01-03)
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

file_response = client.files.content(fir_out_01)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

fir_ques_01 = [extract_final_text(d) for d in response_dicts]

# --- cell 30 (question alignment by custom_id)
import json
import re
import hashlib
from collections import Counter
from pathlib import Path

pipeline_path = Path('<DATA_ROOT>/repro_positive_pairs_pipeline')
req_dir = pipeline_path / "new_batch_reqs"

CID_RE = re.compile(r"request-(\d+)$")

def cid_num(custom_id: str) -> int:
    m = CID_RE.fullmatch(custom_id)
    if not m:
        raise ValueError(f"Bad custom_id: {custom_id}")
    return int(m.group(1))

def read_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def read_batch_output_file(file_id: str):
    txt = client.files.content(file_id).text
    return [json.loads(line) for line in txt.splitlines() if line.strip()]

def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

# Rebuild the exact mapping implied by YOUR generation code.
# This checks against what you actually submitted, not what you may have intended.
def build_manifest():
    manifest = {}

    # fir: request-1 ... request-50000
    for i, curr_index in enumerate(common_indices[:50_000], start=1):
        case1, case2 = case_summary_pairs[curr_index]
        citation_idx = first_50000[curr_index]
        citation_reason = fir_citation_response[citation_idx]
        user_content = question_generating_user % (case1, case2, citation_reason)

        manifest[f"request-{i}"] = {
            "split": "fir",
            "curr_index": curr_index,
            "citation_source_idx": citation_idx,
            "user_hash": sha16(user_content),
        }

    # sec: request-50001 ...
    for local_idx, (curr_index, _) in enumerate(rest_items):
        global_req_id = local_idx + 50_001
        case1, case2 = case_summary_pairs[curr_index]
        citation_reason = sec_citation_response[local_idx]
        user_content = question_generating_user % (case1, case2, citation_reason)

        manifest[f"request-{global_req_id}"] = {
            "split": "sec",
            "curr_index": curr_index,
            "citation_source_idx": local_idx,
            "user_hash": sha16(user_content),
        }

    return manifest

def materialize_expected(custom_id: str, manifest):
    meta = manifest[custom_id]
    curr_index = meta["curr_index"]
    case1, case2 = case_summary_pairs[curr_index]

    if meta["split"] == "fir":
        citation_reason = fir_citation_response[meta["citation_source_idx"]]
    else:
        citation_reason = sec_citation_response[meta["citation_source_idx"]]

    user_content = question_generating_user % (case1, case2, citation_reason)

    return {
        "custom_id": custom_id,
        "split": meta["split"],
        "curr_index": curr_index,
        "citation_source_idx": meta["citation_source_idx"],
        "case1": case1,
        "case2": case2,
        "citation_reason": citation_reason,
        "user_content": user_content,
    }

def verify_input_file(input_path: Path, manifest):
    reqs = read_jsonl(input_path)
    ids = [r["custom_id"] for r in reqs]
    dup_ids = [cid for cid, c in Counter(ids).items() if c > 1]

    mismatches = []
    for line_no, req in enumerate(reqs, start=1):
        cid = req["custom_id"]

        if cid not in manifest:
            mismatches.append({
                "kind": "unknown_custom_id",
                "line_no": line_no,
                "custom_id": cid,
            })
            continue

        got_content = req["body"]["input"][0]["content"]
        got_hash = sha16(got_content)

        if got_hash != manifest[cid]["user_hash"]:
            mismatches.append({
                "kind": "prompt_mismatch",
                "line_no": line_no,
                "custom_id": cid,
            })

    nums = [cid_num(cid) for cid in ids]
    contiguous = nums == list(range(min(nums), max(nums) + 1)) if nums else True

    return {
        "path": str(input_path),
        "n_rows": len(reqs),
        "min_custom_id": min(nums) if nums else None,
        "max_custom_id": max(nums) if nums else None,
        "contiguous_in_file_order": contiguous,
        "duplicate_custom_ids": dup_ids,
        "n_mismatches": len(mismatches),
        "sample_mismatches": mismatches[:10],
    }

def align_output_to_input(input_path: Path, output_file_id: str, manifest):
    reqs = read_jsonl(input_path)
    outs = read_batch_output_file(output_file_id)

    in_ids = [r["custom_id"] for r in reqs]
    out_ids = [r["custom_id"] for r in outs]

    dup_out_ids = [cid for cid, c in Counter(out_ids).items() if c > 1]
    out_by_id = {r["custom_id"]: r for r in outs}

    missing = sorted(set(in_ids) - set(out_ids), key=cid_num)
    extra = sorted(set(out_ids) - set(in_ids), key=cid_num)

    aligned = []
    for local_pos, req in enumerate(reqs):
        cid = req["custom_id"]
        meta = manifest[cid]
        out_row = out_by_id.get(cid)

        aligned.append({
            "local_pos": local_pos,              # index within this chunk
            "custom_id": cid,                    # the true join key
            "global_req_num": cid_num(cid),      # request number across all chunks
            "split": meta["split"],
            "curr_index": meta["curr_index"],
            "citation_source_idx": meta["citation_source_idx"],
            "status_code": None if out_row is None else out_row["response"]["status_code"],
            "final_text": None if out_row is None else extract_final_text(out_row),
            "raw_output": out_row,
        })

    return {
        "input_rows": len(reqs),
        "output_rows": len(outs),
        "missing_custom_ids": missing,
        "extra_custom_ids": extra,
        "duplicate_output_custom_ids": dup_out_ids,
        "aligned": aligned,
    }

# --- cell 31 (question alignment by custom_id)
import json
from pathlib import Path

# Reuse:
# - manifest = build_manifest()
# - verify_input_file(...)
# - align_output_to_input(...)
# - materialize_expected(...)
# - extract_final_text(...)

pipeline_path = Path('<DATA_ROOT>/repro_positive_pairs_pipeline')
req_dir = pipeline_path / "new_batch_reqs"

chunk_specs = [
    {
        "name": "fir01",
        "input_path": req_dir / "fir_questions_chunks" / "fir_questions_nano_high.part_001.jsonl",
        "output_file_id": "<OPENAI_ID>",
    },
    {
        "name": "fir02",
        "input_path": req_dir / "fir_questions_chunks" / "fir_questions_nano_high.part_002.jsonl",
        "output_file_id": "<OPENAI_ID>",
    },
    {
        "name": "fir03",
        "input_path": req_dir / "fir_questions_chunks" / "fir_questions_nano_high.part_003.jsonl",
        "output_file_id": "<OPENAI_ID>",
    },
    {
        "name": "sec01",
        "input_path": req_dir / "sec_questions_chunks" / "sec_questions_nano_high.part_001.jsonl",
        "output_file_id": "<OPENAI_ID>",
    },
    {
        "name": "sec02",
        "input_path": req_dir / "sec_questions_chunks" / "sec_questions_nano_high.part_002.jsonl",
        "output_file_id": "<OPENAI_ID>",
    },
]

def audit_chunk(name, input_path, output_file_id, manifest):
    vin = verify_input_file(input_path, manifest)
    aligned_obj = align_output_to_input(input_path, output_file_id, manifest)

    bad_status_rows = sum(x["status_code"] != 200 for x in aligned_obj["aligned"])

    ok = (
        vin["n_mismatches"] == 0
        and len(vin["duplicate_custom_ids"]) == 0
        and vin["contiguous_in_file_order"]
        and len(aligned_obj["missing_custom_ids"]) == 0
        and len(aligned_obj["extra_custom_ids"]) == 0
        and len(aligned_obj["duplicate_output_custom_ids"]) == 0
        and bad_status_rows == 0
    )

    summary = {
        "name": name,
        "ok": ok,
        "input_path": str(input_path),
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

manifest = build_manifest()

all_chunk_summaries = []
all_chunk_aligned = {}

for spec in chunk_specs:
    summary, aligned_obj = audit_chunk(
        name=spec["name"],
        input_path=spec["input_path"],
        output_file_id=spec["output_file_id"],
        manifest=manifest,
    )
    all_chunk_summaries.append(summary)
    all_chunk_aligned[spec["name"]] = aligned_obj

for s in all_chunk_summaries:
    print(json.dumps(s, indent=2))

# Optional hard fail if anything is wrong
bad_chunks = [s["name"] for s in all_chunk_summaries if not s["ok"]]
print("\nBad chunks:", bad_chunks)

# --- cell 32 (question alignment by custom_id)
# aligned question lists for those chunks
fir_ques_01 = [x["final_text"] for x in all_chunk_aligned["fir01"]["aligned"]]
fir_ques_02 = [x["final_text"] for x in all_chunk_aligned["fir02"]["aligned"]]
fir_ques_03 = [x["final_text"] for x in all_chunk_aligned["fir03"]["aligned"]]
sec_ques_01 = [x["final_text"] for x in all_chunk_aligned["sec01"]["aligned"]]
sec_ques_02 = [x["final_text"] for x in all_chunk_aligned["sec02"]["aligned"]]

aligned_dir = pipeline_path / "outputs" / "aligned_questions"
aligned_dir.mkdir(parents=True, exist_ok=True)

all_questions = {
    "fir_ques_01": fir_ques_01,
    "fir_ques_02": fir_ques_02,
    "fir_ques_03": fir_ques_03,
    "sec_ques_01": sec_ques_01,
    "sec_ques_02": sec_ques_02,
}

for name, questions in all_questions.items():
    dump_json(aligned_dir / f"{name}.json", questions)
