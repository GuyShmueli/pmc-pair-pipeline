# --- cell 1 (citation requests)
citation_records = load_json(base_path/'repro_positive_pairs_pipeline/outputs/03_citation_records.json')

# --- cell 3 (citation requests; updated-run citation request (passage key))

# pipeline_path = '<DATA_ROOT>/repro_positive_pairs_pipeline'

# developer_instructions = """You are a medical citation analysis assistant. You will read excerpts from a 'citing paper' referencing another 'cited paper,' each describing a single-patient case report. Your task is to produce four pieces of information:

# 1. Reason for Citation (a short phrase or sentence about why the authors mention the cited paper).
# 2. Possible Similarities (a brief mention of how these patients’ cases align, if at all).
# 3. Explanation (one to two sentences summarizing how the citation is used).

# ----
# Follow this exact output format:
# Reason for Citation: <short phrase or sentence>
# Possible Similarities: <brief mention>
# Explanation: <one to two sentences>
# ----
# Read the following excerpt(s) and generate your final answer in the required format. Unify your response if multiple citations are present. If no citations are specified, base your response on the articles' titles and abstracts.
# """

# out_path = os.path.join(pipeline_path, 'new_batch_reqs/citation_req.jsonl')

# with open(out_path, 'w', encoding='utf-8') as f:
#     for i, record in enumerate(citation_records, start=1):
#         user_content = (
#             f"Citing Title: {record.get('citing_title', '')}\n"
#             f"Citing Abstract: {record.get('citing_abstract', '')}\n"
#             f"Citation Paragraph: {record.get('citation_paragraph', '')}\n"
#             f"Cited Title: {record.get('cited_title', '')}\n"
#             f"Cited Abstract: {record.get('cited_abstract', '')}"
#         )

#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/responses",
#             "body": {
#                 "model": "gpt-5.4-mini",
#                 "reasoning": {"effort": "medium"},
#                 "instructions": developer_instructions,
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

# print(f"Wrote {out_path}")

# --- cell 12 (text from raw batch output)
# Read First Response

file_response = client.files.content(fir_final_output_id)
file_response_text = file_response.text
json_strings = [line for line in file_response_text.splitlines() if line.strip()]

# Parse each JSON string into a dictionary
response_dicts = [json.loads(line) for line in json_strings]

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

fir_citation_response = [extract_final_text(d) for d in response_dicts]
