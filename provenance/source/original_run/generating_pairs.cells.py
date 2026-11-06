# --- cell 18 (pair_id cleanup and pos_pairs_clean; first-pass ids, labeled records, short text)
import re

for item in radiology_pos_pairs:
    cleaned = re.sub(r'[^0-9_,]', '', item['pair_id'])  # keep only digits, '_' and ','
    item['pair_id'] = [s for s in cleaned.split(',') if s]

# --- cell 21 (pair_id cleanup and pos_pairs_clean; first-pass ids, labeled records, short text)
labeled_pos_pairs = []
pos_pairs_clean = []
for pair in radiology_pos_pairs:
    if pair['pair_id'] in pos_pairs:
        labeled_pos_pairs.append(pair)
        pos_pairs_clean.append(pair['pair_id'])

    

# --- cell 27 (pair_id cleanup and pos_pairs_clean; first-pass ids, labeled records, short text)
with open('<DATA_ROOT>/labeled_pos_pairs.json', 'w') as f:
    json.dump(labeled_pos_pairs, f)
with open('<DATA_ROOT>/text_pairs.json', 'w') as f:
    json.dump(text_pairs, f)
with open('<DATA_ROOT>/pos_pairs_clean.json', 'w') as f:
    json.dump(pos_pairs_clean, f)

# --- cell 30 (pair_id cleanup and pos_pairs_clean; first-pass ids, labeled records, short text)
text_pairs = []
for rec in labeled_pos_pairs:
    modality = str(rec.get("modality", "")).strip()
    anatomy = str(rec.get("anatomy", "")).strip()
    reasoning = str(rec.get("reasoning", "")).strip()
    diagnosis = str(rec.get("diagnosis", "")).strip()
    caps = []

    # Short diagnosis caption
    short_parts = []
    if diagnosis:
        short_parts.append(diagnosis)
    if anatomy:
        short_parts.append(f"in the {anatomy}")
    if modality:
        short_parts.append(f"on {modality}")
    if short_parts:
        s = " ".join(short_parts).strip()
        if not s.endswith("."):
            s += "."
        caps.append(s)
    text_pairs.append(caps)

# --- cell 57 (first-pass caption dicts and requests)
# pairs_text = [
#     [ [open(p, encoding="utf-8").read().strip() for p in patient_group]
#       for patient_group in pair ]
#     for pair in pairs_text_list
# ]

with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/pairs_text.json', 'r') as f:
    pairs_text = json.load(f)

# --- cell 62 (first-pass caption dicts and requests)
stems_3d = [
    [
        [Path(p).stem for p in sin_patient]   # 3rd level: every path in one patient
        for sin_patient in pair              # 2nd level: both patients in the pair
    ]
    for pair in pairs_text_list              # 1st level: all pairs
]

stems_3d[0:1]

# --- cell 77 (first-pass caption dicts and requests)
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

# --- cell 78 (first-pass caption dicts and requests)
stem_caption_list = build_stem_caption_3d(pairs_text, stems_3d)

# --- cell 81 (first-pass caption dicts and requests)
from pathlib import Path
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/" + "diagrams_compound_filtered_paths_list.json", 'r') as f:
    diagrams_compound_filtered_paths_list = json.load(f)

diagrams_compound_filtered_stems = [Path(p).stem for p in diagrams_compound_filtered_paths_list]

# --- cell 82 (first-pass caption dicts and requests)
diagrams_compound_filtered_stems_set = set(diagrams_compound_filtered_stems)

# --- cell 83 (first-pass caption dicts and requests)
filtered_stem_caption_list = [
    [
        {k: v for k, v in d.items() if k in diagrams_compound_filtered_stems_set}      # keep only wanted keys
        for d in inner                                   # loop over inner dicts
        if any(k in diagrams_compound_filtered_stems_set for k in d)                  # …and drop empty dicts
    ]
    for inner in stem_caption_list                       # loop over outer groups
]

# --- cell 87 (first-pass caption dicts and requests)
# The invalid caption-pairs rise when all the captions in patient1 or patient2 are filtered out (diagrams)
invalid_pairs_indices = [i for i, inner in enumerate(filtered_stem_caption_list) if len(inner) < 2]
invalid_pairs_indices_set = set(invalid_pairs_indices)

# --- cell 89 (first-pass caption dicts and requests)
prompt ="You are a medical-AI expert. " \
"Your job is to classify *pairs* of medical-image captions as " \
"**positive** if they share same diagnosis & modality.\n" \
"NOTE: Classify **only inter-case pairs** (the two caption-IDs come from different cases).\n" \
"Output **only** valid JSON matching this schema (no markdown). For example:\n" \
"{\n" \
'  "pair_id": "<label_1, label_2>",\n' \
'  "reasoning": "<short explanation why it is positive>",\n' \
'  "modality": "<the shared modality>",\n' \
'  "anatomy": "<the anatomy>",\n' \
'  "diagnosis": "<the shared diagnosis you found>",\n' \
"}\n" \
"DON'T classify (return nothing) if one of the following is true:\n" \
"1. They are negatives.\n" \
"2. If either caption describes a diagram/illustration.\n" \
"3. If either appears to be a caption describing a compound figure (has labels such as 'A', 'A-C', '(b) etc.)\n" \
"\n" \
"FINAL SANITY CHECK (before you output):\n" \
"✓ Inter-case pair?\n"  \
"✓ Same diagnosis **and** modality?\n"  \
"✓ No diagram/illustration words?\n"  \
"✓ No compound-figure cues listed above?\n"  \
"If every answer is YES → produce the JSON object.\n"  \
"Otherwise → output {}."

# --- cell 90 (first-pass caption dicts and requests)
prompts = []
for idx, common_index in enumerate(common_indices):
    
    if common_index in invalid_pairs_indices_set:
        continue

    # ---------- collect the data we need for this pair ----------
    # captions1      = stem_caption_list[common_index][0]
    # captions2      = stem_caption_list[common_index][1]
    captions1      = filtered_stem_caption_list[common_index][0]
    captions2      = filtered_stem_caption_list[common_index][1]
    curr_questions = generated_questions[idx]
    curr_answers   = generated_answers[idx]

    # ---------- build the message list after the assignments ----------
    messages = [
        {   # 1) System role
            "role": "developer",
            "content": (
                prompt
            )
            
        },
        {   # 2) User role
            "role": "user",
            "content": f"""\
### PATIENT-CONTEXT QUERIES & ANSWERS
{curr_questions}

{curr_answers}

### IMAGE CAPTIONS (MULTIPLE PAIRS)
{captions1}

{captions2}
"""
        }
    ]

    prompts.append(messages)

# --- cell 159 (first-pass caption dicts and requests)
# INPUT_FILE = "<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/generate_positives.jsonl"

# with open(INPUT_FILE, "w", encoding="utf-8") as f:
#     for i, messages in enumerate(prompts, start=1):
#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/chat/completions",
#             "body": {
#                 "model": "o4-mini", 
#                 "reasoning_effort": "low",
#                 "messages": messages
#             }
#         }

#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# with open(INPUT_FILE, 'r') as g:
#     positives_request = [json.loads(line) for line in g]

# --- cell 160 (first-pass caption dicts and requests)
# positives_request_file = client.files.create(
#   file=open(INPUT_FILE, "rb"),
#   purpose="batch"
# )

# --- cell 161 (first-pass caption dicts and requests)
# client.batches.create(
#     input_file_id=positives_request_file.id,
#     endpoint="/v1/chat/completions",
#     completion_window="24h",
#     metadata={
#       "description": "Generating captions positive pairs"
#     }
# )

# --- cell 163 (first-pass caption dicts and requests)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

generated_pos_pairs = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 164 (first-pass caption dicts and requests)
with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/generated_pos_pairs.json', 'w') as f:
    json.dump(generated_pos_pairs, f)
