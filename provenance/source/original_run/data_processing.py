# --- lines 1-89 (case selection rule)
# import pandas as pd
# import ast
# import json

# logger = open("logger.txt", "w")
# logger.write(f"started processing data\n")


# def get_pmcid_clean(value):
#     return value.split('-')[0]


# def get_pmcid(value):
#     return f'PMC{value}'


# def get_sim_patients_list(dictionary_str):
#     try:
#         dictionary = ast.literal_eval(dictionary_str)
#         return list(dictionary.keys())
#     except (SyntaxError, ValueError):
#         return []


# def filter_patients(patients, values):
#     return [patient for patient in patients if patient.split('-')[0] in values]


# def read_csv():
#     try:
#         df = pd.read_csv('PMC-Patients.csv', on_bad_lines='skip', engine='python')
#     except pd.errors.ParserError as e:
#         logger.write(f"Error reading CSV file: {e}\n")

#     logger.write(f"finished reading csv, read {len(df)} rows out of PMC-Patients.csv\n")

#     new_df = df[df['similar_patients'] != '{}']
#     n_empty_sim_patients = len(df) - len(new_df)
#     logger.write(
#         f"removed {n_empty_sim_patients} rows from df (with empty similar_patients), left with {len(new_df)}\n")

#     return new_df


# def create_new_columns(df):
#     df['pmc_id_clean'] = df['patient_uid'].apply(get_pmcid_clean)
#     df['pmc_id'] = df['pmc_id_clean'].apply(get_pmcid)
#     df.loc[:, 'similar_patients_list'] = df['similar_patients'].apply(get_sim_patients_list)
#     return df


# def get_unique_articles_pmcid(df):
#     pmc_values_counts = df['pmc_id_clean'].value_counts()
#     recurring_clean_values = set(pmc_values_counts[pmc_values_counts > 1].index)
#     unique_clean_values = set(pmc_values_counts[pmc_values_counts == 1].index)

#     logger.write(f"found {len(recurring_clean_values)} articles which contains more than one patient\n")
#     logger.write(f"found {len(unique_clean_values)} articles which contains just one patient\n")

#     return unique_clean_values


# def filter_unique_articles_patients(df, unique_articles):
#     unique_df = df[df['pmc_id_clean'].isin(unique_articles)]
#     n_not_unique = len(df) - len(unique_df)
#     logger.write(f"removed {n_not_unique} patients that does not appear in a unique article, left with {len(unique_df)}\n")
#     unique_df.to_csv('temp_unique_articles.csv', index=False)

#     unique_df['unique_articles_sim_patients'] = unique_df['similar_patients_list'].apply(lambda patients: filter_patients(patients, unique_articles))
#     unique_sim_patients_df = unique_df[unique_df['unique_articles_sim_patients'].apply(lambda x: len(x) != 0)]
#     n_empty_unique_sim_patients = len(unique_df) - len(unique_sim_patients_df)
#     logger.write(f"removed {n_empty_unique_sim_patients} patients that didn't have similar patients which appears in a unique article, left with {len(unique_sim_patients_df)}\n")
#     return unique_sim_patients_df

# def save_results(unique_df, unique_articles):
#     unique_df.to_csv('unique_articles.csv', index=False)
#     with open('unique_articles.json', 'w') as f:
#         json.dump(list(unique_articles), f)


# df = read_csv()
# df = create_new_columns(df)
# unique_articles = get_unique_articles_pmcid(df)
# unique_df = filter_unique_articles_patients(df, unique_articles)
# save_results(unique_df, unique_articles)

# logger.write(f"finished processing data, left with {len(unique_df)} patients")

# logger.close()
