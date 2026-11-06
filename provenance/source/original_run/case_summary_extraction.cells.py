# --- cell 3 (case descriptions)
from lxml import etree
from multiprocessing import Pool

# Create an XPath expression that matches <sec> elements with a <title> containing any of the keywords.
# Using translate() ensures a case-insensitive search.
xpath_expr = (
    "//sec["
    "  contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case presentation') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case report') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case description') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case summary') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient presentation') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient report') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient description') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient summary') "
    "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case') "
    "or (normalize-space(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) = 'patient') "
    "]"
)


def process_file_list(file_list):
    """
    Given a list of file paths, parse each file, run the XPath,
    gather the text from <sec> paragraphs, return a dict { filepath: text }.
    """
    single_pair_case_summary = {}
    for file in file_list:
        tree = etree.parse(file)
        sections = tree.xpath(xpath_expr)
        for sec in sections:
            paragraphs = sec.xpath(".//p//text()")
            text = " ".join(paragraphs)
            single_pair_case_summary[file] = text
    return single_pair_case_summary

def multiprocess_case_summaries():
    with Pool() as pool:
        # Map each sub-list to a worker process
        case_summary_pairs_list = pool.map(process_file_list, matching_uids_xml_paths)

    return case_summary_pairs_list


case_summary_pairs_list = multiprocess_case_summaries()

# --- cell 4 (case descriptions)
case_summary_pairs_list = [list(case_summary_pairs_list[idx].values()) for idx in range(len(case_summary_pairs_list))]

# --- cell 5 (case descriptions)
def calc_indices_summaries_list(case_summary_pairs_list):
    """
    Returns two lists:
      - A list of indices corresponding to elements depicting both cases.
      - A list of indices corresponding to elements depicting less than 2 cases.
    """
    valid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) == 2]
    invalid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) != 2]

    return valid_indices, invalid_indices

# --- cell 9 (case descriptions)
# with open('<DATA_ROOT>/case_summary_pairs_list.json', 'w') as f:
#     json.dump(case_summary_pairs_list, f)

with open('<DATA_ROOT>/case_summary_pairs_list.json', 'r') as f:
    case_summary_pairs_list = json.load(f)
case_summary_pairs_list[0]
