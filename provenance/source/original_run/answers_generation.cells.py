# --- cell 5 (answer requests)
idx = 101
common_index = common_indices[idx]

case1 = case_summary_pairs_list[common_index][0]

case2 = case_summary_pairs_list[common_index][1]

citation_reason = o3_mini_response_list[citation_valid_indices_dict[common_index]]

curr_questions = generated_questions[idx]

answering_prompt = """You will be given case details for Case A, Case B, Reason for Citation (one case cites the other), along with a list of questions.
You are an experienced clinician specializing in medical imaging. Previously, a list of comparative, clinically oriented questions was generated for the two cases.
Now, your task is to answer those questions in a way that highlights the diagnostic similarities and differences between the two cases.
DO NOT provide any additional information or context outside of the answers to the questions.
"""
# Instructions for answering:

# 1. **Refer to Both Cases**  
#    - You will be given the same case details for Case A, Case B, Reason for Citation, along with the full list of questions.
#    - Answer each question by explicitly referencing the relevant details from Case A and Case B that support your conclusion.

# 2. **Structure of Answers**  
#    - For yes/no questions, begin your response with a clear “Yes” or “No,” then provide a brief rationale.
#    - For open-ended or more detailed comparative questions, give a concise yet clinically thorough answer.
#    - If you need to highlight differences in imaging findings, symptoms, or etiologies, do so clearly and directly.
#    - Split each answer to 'In case A, ...' and 'In case B, ...'

# 3. **Clinical Depth & Relevance**  
#    - Focus on the clinical significance of each answer, referencing imaging features, pathophysiology, or typical clinical presentation.
#    - Avoid tangential or purely theoretical discussion; make sure each answer directly relates to the question and helps differentiate or confirm diagnoses.

# 4. **Accuracy & Clarity**  
#    - Base your answers on standard radiological and clinical knowledge, ensuring that any assertions are consistent with typical findings and established practice.
#    - If you must make an assumption (e.g., missing data), state it explicitly and provide your best inference based on standard clinical reasoning.

# 5. **Format**  
#    - Number your answers to match the questions.
#    - Keep them concise, but complete enough to stand as a definitive answer.
# """

answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

---
Case A:
{case1}

Case B:
{case2}

Reason for Citation, Possible Similarities and Explanation:
{citation_reason}

Questions:
{curr_questions}
---

Provide your answers now:
"""

# --- cell 8 (answer requests)
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/batch_requests_answer_gen_part1.jsonl", "w", encoding="utf-8") as f:
    for idx in range(len(common_indices))[:len(common_indices)//2]:
        common_index = common_indices[idx]
        case1 = case_summary_pairs_list[common_index][0]
        case2 = case_summary_pairs_list[common_index][1]
        citation_reason = o3_mini_response_list[citation_valid_indices_dict[common_index]]
        curr_questions = generated_questions[idx]

        answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

        ---
        Case A:
        {case1}

        Case B:
        {case2}

        Reason for Citation, Possible Similarities and Explanation:
        {citation_reason}

        Questions:
        {curr_questions}
        ---

        Provide your answers now:
        """

        request_obj = {
            "custom_id": f"request-{idx+1}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {
                            "role": "developer",
                            "content": f"{answering_prompt}"
                        },
                        {
                            "role": "user",
                            "content": f"{answering_user}"
                        }
                    ],
            }
        }
        # Write each object on a new line in the JSONL file
        f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 9 (answer requests)
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/batch_requests_answer_gen_part2.jsonl", "w", encoding="utf-8") as f:
    for idx in range(len(common_indices))[len(common_indices)//2:]:
        common_index = common_indices[idx]
        case1 = case_summary_pairs_list[common_index][0]
        case2 = case_summary_pairs_list[common_index][1]
        citation_reason = o3_mini_response_list[citation_valid_indices_dict[common_index]]
        curr_questions = generated_questions[idx]

        answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

        ---
        Case A:
        {case1}

        Case B:
        {case2}

        Reason for Citation, Possible Similarities and Explanation:
        {citation_reason}

        Questions:
        {curr_questions}
        ---

        Provide your answers now:
        """

        request_obj = {
            "custom_id": f"request-{idx+1}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {
                            "role": "developer",
                            "content": f"{answering_prompt}"
                        },
                        {
                            "role": "user",
                            "content": f"{answering_user}"
                        }
                    ],
            }
        }
        # Write each object on a new line in the JSONL file
        f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 14 (answer outputs)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

generated_answers_part1 = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 20 (answer outputs)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

generated_answers_part2 = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 22 (answer outputs)
generated_answers = generated_answers_part1 + generated_answers_part2
len(generated_answers)

# --- cell 23 (answer outputs)
with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/generated_answers.json', 'w') as f:
    json.dump(generated_answers, f)
