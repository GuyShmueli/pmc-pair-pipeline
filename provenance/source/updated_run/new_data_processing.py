import pandas as pd
import ast
import json

logger = open("new_logger.txt", "w")
logger.write("started processing data\n")


def get_pmcid_clean(value):
    return str(value).split('-', 1)[0]


def get_pmcid(value):
    return f'PMC{value}'


def parse_sim_patients_dict(dictionary_str):
    try:
        if pd.isna(dictionary_str):
            return {}
        dictionary = ast.literal_eval(str(dictionary_str))
        return dictionary if isinstance(dictionary, dict) else {}
    except (SyntaxError, ValueError, TypeError):
        return {}


def get_sim_patients_list(dictionary_str):
    dictionary = parse_sim_patients_dict(dictionary_str)
    return list(dictionary.keys())


def filter_patients(patients, values):
    return [patient for patient in patients if patient.split('-', 1)[0] in values]


def filter_sim_patients_dict(dictionary_str, allowed_article_ids):
    """
    Keep only similar_patients whose article ID (part before '-')
    belongs to the set of single-patient articles.
    Return as a JSON string with double quotes.
    """
    dictionary = parse_sim_patients_dict(dictionary_str)
    filtered = {
        patient_id: score
        for patient_id, score in dictionary.items()
        if isinstance(patient_id, str) and patient_id.split('-', 1)[0] in allowed_article_ids
    }
    return json.dumps(filtered, ensure_ascii=False)


def read_csv():
    try:
        df = pd.read_csv("<DATA_ROOT>/result_df.csv")
    except pd.errors.ParserError as e:
        logger.write(f"Error reading CSV file: {e}\n")
        raise

    logger.write(f"finished reading csv, read {len(df)} rows out of result_df.csv\n")

    new_df = df[df['similar_patients'] != '{}'].copy()
    n_empty_sim_patients = len(df) - len(new_df)
    logger.write(
        f"removed {n_empty_sim_patients} rows from df (with empty similar_patients), left with {len(new_df)}\n"
    )

    return new_df


def create_new_columns(df):
    df = df.copy()
    df['pmc_id_clean'] = df['patient_uid'].apply(get_pmcid_clean)
    df['pmc_id'] = df['pmc_id_clean'].apply(get_pmcid)
    df['similar_patients_list'] = df['similar_patients'].apply(get_sim_patients_list)
    return df


def get_unique_articles_pmcid(df):
    pmc_values_counts = df['pmc_id_clean'].value_counts()
    recurring_clean_values = set(pmc_values_counts[pmc_values_counts > 1].index)
    unique_clean_values = set(pmc_values_counts[pmc_values_counts == 1].index)

    logger.write(f"found {len(recurring_clean_values)} articles which contain more than one patient\n")
    logger.write(f"found {len(unique_clean_values)} articles which contain just one patient\n")

    return unique_clean_values


def filter_unique_articles_patients(df, unique_articles):
    unique_df = df[df['pmc_id_clean'].isin(unique_articles)].copy()
    n_not_unique = len(df) - len(unique_df)
    logger.write(
        f"removed {n_not_unique} patients that do not appear in a unique article, left with {len(unique_df)}\n"
    )

    # Overwrite similar_patients itself with the filtered dict string
    unique_df['similar_patients'] = unique_df['similar_patients'].apply(
        lambda s: filter_sim_patients_dict(s, unique_articles)
    )

    # Rebuild similar_patients_list from the filtered dict
    unique_df['similar_patients_list'] = unique_df['similar_patients'].apply(get_sim_patients_list)

    # Keep the list column too, for downstream convenience
    unique_df['unique_articles_sim_patients'] = unique_df['similar_patients_list']

    unique_df.to_csv('temp_new_unique_articles_2.csv', index=False)

    unique_sim_patients_df = unique_df[
        unique_df['unique_articles_sim_patients'].apply(lambda x: len(x) != 0)
    ].copy()

    n_empty_unique_sim_patients = len(unique_df) - len(unique_sim_patients_df)
    logger.write(
        f"removed {n_empty_unique_sim_patients} patients that didn't have similar patients "
        f"which appear in a unique article, left with {len(unique_sim_patients_df)}\n"
    )

    return unique_sim_patients_df


def save_results(unique_df):
    unique_df.to_csv('new_unique_articles_2.csv', index=False)

    # Save only the articles that actually survived the final filtering
    surviving_articles = sorted(unique_df['pmc_id_clean'].unique().tolist())
    with open('new_unique_articles_2.json', 'w') as f:
        json.dump(surviving_articles, f)


df = read_csv()
df = create_new_columns(df)
unique_articles = get_unique_articles_pmcid(df)
unique_df = filter_unique_articles_patients(df, unique_articles)
save_results(unique_df)

logger.write(f"finished processing data, left with {len(unique_df)} patients\n")
logger.close()
