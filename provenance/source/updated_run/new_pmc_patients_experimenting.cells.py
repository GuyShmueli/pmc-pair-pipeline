# --- cell 1 (delta against the older collection)
# Old PMC-Patients DataFrame
def upload_csv(file_path):
    df = pd.read_csv(file_path)
    return df

file_path = '<DATA_ROOT>/PMC-Patients.csv'
df = upload_csv(file_path)

len(df)

# --- cell 4 (delta against the older collection)
# New PMC-Patients DataFrame

new_file_path = '<DATA_ROOT>/PMC-patients_collection/datasets/PMC-Patients.csv'
new_df = upload_csv(new_file_path)

len(new_df)

# --- cell 5 (delta against the older collection)
before = len(new_df)
new_df = new_df[
    new_df["relevant_articles"].notna()
    & (new_df["relevant_articles"].astype(str).str.strip() != "{}")
].reset_index(drop=True)
after = len(new_df)

print("removed:", before - after)
print("remaining:", after)

# --- cell 8 (delta against the older collection)
# Create a new DF following these 2 rules:
# Rule 1: Keep rows whose patient_uid exists in new_df but not in df
# Rule 2: Keep rows whose patient_uid already exists in df, but they have at least one similar patient that is new

import ast
import json
import pandas as pd

def parse_similar_patients_dict(value):
    """
    Parse a similar_patients cell into a dict {patient_uid: score}.
    Supports:
      - dict objects
      - JSON strings
      - Python-literal dict strings
      - empty / NaN
    """
    if pd.isna(value):
        return {}

    if isinstance(value, dict):
        return {str(k).strip(): v for k, v in value.items()}

    if isinstance(value, str):
        s = value.strip()
        if not s or s == "{}":
            return {}

        for parser in (json.loads, ast.literal_eval):
            try:
                obj = parser(s)
                if isinstance(obj, dict):
                    return {str(k).strip(): v for k, v in obj.items()}
            except Exception:
                pass

    return {}


def serialize_similar_patients(filtered_dict, original_value):
    """
    Keep the output type consistent with the original cell:
      - if original was a dict -> return dict
      - otherwise -> return JSON string
    """
    if isinstance(original_value, dict):
        return filtered_dict
    return json.dumps(filtered_dict, ensure_ascii=False)


# Normalize patient_uid columns
result_base = new_df.copy()
result_base["patient_uid"] = result_base["patient_uid"].astype(str).str.strip()

old_uids = set(df["patient_uid"].astype(str).str.strip())
new_uids = set(result_base["patient_uid"])

# New patient_uids in new_df that do not exist in df
novel_uids = new_uids - old_uids

# Parse similar_patients once
result_base["_similar_dict"] = result_base["similar_patients"].apply(parse_similar_patients_dict)

# Rule 1:
# Keep rows whose patient_uid exists in new_df but not in df
rule1_mask = result_base["patient_uid"].isin(novel_uids)

# Rule 2:
# Keep rows whose patient_uid already exists in df,
# but they have at least one similar patient that is novel
rule2_mask = (
    result_base["patient_uid"].isin(old_uids)
    & result_base["_similar_dict"].apply(lambda d: len(set(d.keys()) & novel_uids) > 0)
)

# Build result
result_df = result_base[rule1_mask | rule2_mask].copy()

# For rule 2 rows only:
# filter similar_patients to keep only novel_uids
rule2_in_result = result_df["patient_uid"].isin(
    result_base.loc[rule2_mask, "patient_uid"]
)

result_df.loc[rule2_in_result, "similar_patients"] = result_df.loc[rule2_in_result].apply(
    lambda row: serialize_similar_patients(
        {uid: score for uid, score in row["_similar_dict"].items() if uid in novel_uids},
        row["similar_patients"]
    ),
    axis=1
)

# Clean up helper column
result_df = result_df.drop(columns=["_similar_dict"]).reset_index(drop=True)

print("rows from rule 1 (new patient_uid):", int(rule1_mask.sum()))
print("rows from rule 2 (existing uid linked to new uid):", int(rule2_mask.sum()))
print("total rows in result_df:", len(result_df))
