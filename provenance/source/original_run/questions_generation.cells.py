# --- cell 3 (question requests)
def calc_indices_summaries_list(case_summary_pairs_list):
    """
    Returns two lists:
      - A list of indices corresponding to elements depicting both cases.
      - A list of indices corresponding to elements depicting less than 2 cases.
    """
    valid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) == 2]
    invalid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) != 2]

    return valid_indices, invalid_indices

# --- cell 7 (question requests)
def find_common_indices(summaries_valid_indices, citation_valid_indices):
    """
    Find the common indices between summaries_valid_indices and citation_valid_indices:
      - summaries_valid_indices - represents the indices corresponding to successfully extracted case summaries (0-31,691) 
      - citation_valid_indices - represents the indices corresponding to successfully cited-citing pairs (0-31,691)
    """
    summaries_valid_indices_set = set(summaries_valid_indices)
    citation_valid_indices_set = set(citation_valid_indices)
    common_indices = []

    for i in range(len(matching_uids_pmid_list)):
        if i in summaries_valid_indices_set and i in citation_valid_indices_set:
            common_indices.append(i)
    
    return common_indices


common_indices = find_common_indices(summaries_valid_indices, citation_valid_indices)

# --- cell 9 (question requests)
citation_valid_indices_dict = {citation_valid_indices[idx]: idx for idx in range(len(citation_valid_indices))}

# --- cell 13 (question requests)
curr_index = common_indices[6663]

case1 = case_summary_pairs_list[curr_index][0]

case2 = case_summary_pairs_list[curr_index][1]

citation_reason = o3_mini_response_list[citation_valid_indices_dict[curr_index]]

question_generating_prompt = """
You are an experienced clinician specializing in medical imaging. You will be given two cases and the reason for citation between the two (one case report cites the other), and asked to generate a set of comparative, clinically relevant questions that highlight both similarities and differences, helping differentiate potential diagnoses. Your questions should:

1. **Focus on Diagnostic Clues and Clinical Significance:**
   - Avoid trivial or purely technical details (like minor differences in image orientation).
   - Emphasize findings that inform diagnosis (e.g., presence of lesions, pattern of abnormalities, symptoms).

2. **Use a Comparative Framing:**
   - Explicitly compare Case A and Case B.
   - Aim for questions that probe both common ground and distinguishing features.
   - If possible, try asking mostly yes/no questions.

3. **Follow a Hierarchical Reasoning Approach:**
   - **Level 1 (Broad Context)**: Are both cases the same modality/organ system?
   - **Level 2 (General Diagnosis Category)**: Are they both infectious, both neoplastic, etc.?
   - **Level 3 (Specific Features & Findings)**: Detailed imaging findings (e.g., cavitation, consolidation, nodules), clinical presentation, organism type, etc.

4. **Consider Step-by-Step Reasoning:**
   - You may first silently analyze the diagnoses and imaging findings for each case.
   - Then generate questions that a clinician would naturally ask to tease out whether the two cases have the same underlying pathology or different pathologies.

5. **Provide a subtitle specifying the level (1/2/3) of the current set of questions.**
"""

question_generating_user = f"""
Below are two cases and the reason for citation between the two. Read them carefully, then generate a concise list of question prompts (in bullet or numbered format) that compare these cases on clinically meaningful aspects.

---
Case A:
{case1}

Case B:
{case2}

Reason for Citation, Possible Similarities and Explanation:
{citation_reason}
---

Now, **generate the list of comparative, clinically relevant questions** that a radiologist or physician might ask to determine whether these two cases share a diagnosis or differ in key features. 

Remember:
- Maintain clinical depth: mention imaging findings, pathophysiology, or hallmark symptoms.
- Emphasize similarities/differences that impact diagnosis.
- Keep the questions focused and direct, as if you are performing a differential diagnosis.
- Avoid vague or generic questions; ensure each question contributes to understanding diagnostic overlap or divergence.
- Start with broad-level questions (anatomy, broad diagnosis similarity), then proceed to more specific questions about the nature of the condition, causative agents, imaging signs, etc.
- Adhere to yes/no questions, if possible.
- Provide a subtitle specifying the level (1/2/3) of each set of questions.

Provide your final list of questions now.
"""

# --- cell 18 (question requests)
question_generating_prompt = """
You are an experienced clinician specializing in medical imaging. You will be given two cases and the reason for citation between the two (one case report cites the other), and asked to generate a set of comparative, clinically relevant questions that highlight both similarities and differences, helping differentiate potential diagnoses. Your questions should:

1. **Focus on Diagnostic Clues and Clinical Significance:**
   - Avoid trivial or purely technical details (like minor differences in image orientation).
   - Emphasize findings that inform diagnosis (e.g., presence of lesions, pattern of abnormalities, symptoms).

2. **Use a Comparative Framing:**
   - Explicitly compare Case A and Case B.
   - Aim for questions that probe both common ground and distinguishing features.
   - If possible, try asking mostly yes/no questions.

3. **Follow a Hierarchical Reasoning Approach:**
   - **Level 1 (Broad Context)**: Are both cases the same modality/organ system?
   - **Level 2 (General Diagnosis Category)**: Are they both infectious, both neoplastic, etc.?
   - **Level 3 (Specific Features & Findings)**: Detailed imaging findings (e.g., cavitation, consolidation, nodules), clinical presentation, organism type, etc.

4. **Consider Step-by-Step Reasoning:**
   - You may first silently analyze the diagnoses and imaging findings for each case.
   - Then generate questions that a clinician would naturally ask to tease out whether the two cases have the same underlying pathology or different pathologies.

5. **Provide a subtitle specifying the level (1/2/3) of the current set of questions.**
"""

question_generating_user = f"""
Below are two cases and the reason for citation between the two. Read them carefully, then generate a concise list of question prompts (in numbered format) that compare these cases on clinically meaningful aspects.

---
Case A:
%s

Case B:
%s

Reason for Citation, Possible Similarities and Explanation:
%s
---

Now, **generate the list of comparative, clinically relevant questions** that a radiologist or physician might ask to determine whether these two cases share a diagnosis or differ in key features. 

Remember:
- Maintain clinical depth: mention imaging findings, pathophysiology, or hallmark symptoms.
- Emphasize similarities/differences that impact diagnosis.
- Keep the questions focused and direct, as if you are performing a differential diagnosis.
- Avoid vague or generic questions; ensure each question contributes to understanding diagnostic overlap or divergence.
- Start with broad-level questions (anatomy, broad diagnosis similarity), then proceed to more specific questions about the nature of the condition, causative agents, imaging signs, etc.
- Adhere to yes/no questions, if possible.
- Provide a subtitle specifying the level (1/2/3) of each set of questions.

Provide your final list of questions now.
"""

# --- cell 20 (question requests)
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/questions_batch_requests_A.jsonl", "w", encoding="utf-8") as f:
    for i, curr_index in enumerate(common_indices[:16000], start=1):

        case1 = case_summary_pairs_list[curr_index][0]
        case2 = case_summary_pairs_list[curr_index][1]
        citation_reason = o3_mini_response_list[citation_valid_indices_dict[curr_index]]


        request_obj = {
            "custom_id": f"request-{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "o3-mini",
                "reasoning_effort": "low",
                "messages": [
                    {"role": "developer", "content": question_generating_prompt},
                    {"role": "user", "content": question_generating_user % (case1, case2, citation_reason)}
                ]
            }
        }
        # Write each object on a new line in the JSONL file
        f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 26 (question outputs)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts_A = [json.loads(line) for line in json_strings]

generated_questions_A = [response_dicts_A[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts_A))]

# --- cell 30 (question requests)
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/questions_batch_requests_B.jsonl", "w", encoding="utf-8") as f:
    for i, curr_index in enumerate(common_indices[16000:], start=16001):

        case1 = case_summary_pairs_list[curr_index][0]
        case2 = case_summary_pairs_list[curr_index][1]
        citation_reason = o3_mini_response_list[citation_valid_indices_dict[curr_index]]


        request_obj = {
            "custom_id": f"request-{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "o3-mini",
                "reasoning_effort": "low",
                "messages": [
                    {"role": "developer", "content": question_generating_prompt},
                    {"role": "user", "content": question_generating_user % (case1, case2, citation_reason)}
                ]
            }
        }
        # Write each object on a new line in the JSONL file
        f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 35 (question outputs)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts_B = [json.loads(line) for line in json_strings]

generated_questions_B = [response_dicts_B[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts_B))]

# --- cell 38 (question outputs)
# Combining the two lists into a single list
generated_questions = generated_questions_A + generated_questions_B
