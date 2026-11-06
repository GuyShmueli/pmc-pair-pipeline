# --- cell 14 (intersection)
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

# --- cell 19 (intersection)
citation_valid_indices_dict = {citation_valid_indices[idx]: idx for idx in range(len(citation_valid_indices))}

# --- cell 46 (xml and pmid inputs)
import os

def get_xml_path(pmc_id: str):
    pmc_id = pmc_id[:-2]

    path = f'<DATA_ROOT>/pmc/pythonProject/data2/PMC{pmc_id}/{pmc_id}_1'

    for file_name in os.listdir(path):
        if file_name.endswith('.nxml'):
            return os.path.join(path, file_name)
    return None

get_xml_path('<CASE_ID>')

# --- cell 47 (xml and pmid inputs)
# matching_uids_xml_paths = [
#     [get_xml_path(uid) for uid in pair]
#     for pair in matching_uids
# ]

with open ('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/matching_uids_xml_paths.json', 'r') as f:
    matching_uids_xml_paths = json.load(f)

# --- cell 49 (citation verification)
#!/usr/bin/env python3

import os
import sys
import json
import re
import string
from lxml import etree

##############################################################################
# 1. parse_nxml: gather pmid, doi, pmcid, main title, abstract, references
##############################################################################

def parse_nxml(file_path):
    """
    Parses a JATS .nxml file to gather:
      - pmid, doi, pmcid
      - the main article title, abstract
      - references => { ref_id -> { "doi":..., "pmid":..., "pmcid":..., "title":... } }
      - the parsed lxml 'tree'

    If file not found or parse error => returns None.
    """
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return None

    parser = etree.XMLParser(recover=True)
    try:
        tree = etree.parse(file_path, parser)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

    root = tree.getroot()

    def _get_article_id(id_type):
        elem = root.find(f'.//article-id[@pub-id-type="{id_type}"]')
        return elem.text.strip() if elem is not None and elem.text else None

    paper_pmid  = _get_article_id("pmid")
    paper_doi   = _get_article_id("doi")
    paper_pmcid = _get_article_id("pmc")

    # Extract main article title
    title_elems = root.xpath('//*[local-name()="title-group"]//*[local-name()="article-title"]')
    if not title_elems:
        title_elems = root.xpath('//*[local-name()="article-title"]')
    paper_title = "".join(title_elems[0].itertext()).strip() if title_elems else ""

    # Extract abstract
    abstract_elems = root.xpath('//*[local-name()="abstract"]')
    abs_texts = []
    for abs_elem in abstract_elems:
        txt = " ".join(abs_elem.itertext()).strip()
        if txt:
            abs_texts.append(txt)
    paper_abstract = " ".join(abs_texts)

    # Extract references => store pmid, doi, pmcid, plus a "title" from <article-title> or fallback
    references = {}
    ref_list = root.xpath('//*[local-name()="ref"]')
    for ref_node in ref_list:
        r_id = ref_node.get('id')
        if not r_id:
            continue

        # gather pub-ids
        doi_elems   = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="doi"]')
        pmid_elems  = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmid"]')
        pmcid_elems = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmc"]')

        cited_doi   = doi_elems[0].text.strip()   if doi_elems   and doi_elems[0].text else None
        cited_pmid  = pmid_elems[0].text.strip()  if pmid_elems  and pmid_elems[0].text else None
        cited_pmcid = pmcid_elems[0].text.strip() if pmcid_elems and pmcid_elems[0].text else None

        # Attempt <article-title> in <element-citation>, else fallback <mixed-citation>, else <comment>
        ec_title_elems = ref_node.xpath('.//*[local-name()="element-citation"]/*[local-name()="article-title"]')
        if ec_title_elems:
            ref_title = " ".join(ec_title_elems[0].itertext()).strip()
        else:
            mixed_elems = ref_node.xpath('.//*[local-name()="mixed-citation"]')
            if mixed_elems:
                ref_title = extract_title_from_mixed_citation(mixed_elems[0])
            else:
                # final fallback => <comment>
                comment_elems = ref_node.xpath('.//*[local-name()="element-citation"]/*[local-name()="comment"]')
                if comment_elems:
                    ref_title = " ".join(comment_elems[0].itertext()).strip()
                else:
                    ref_title = ""

        references[r_id] = {
            "doi":   cited_doi,
            "pmid":  cited_pmid,
            "pmcid": cited_pmcid,
            "title": ref_title
        }

    return {
        "pmid": paper_pmid,
        "doi": paper_doi,
        "pmcid": paper_pmcid,
        "title": paper_title,
        "abstract": paper_abstract,
        "references": references,
        "tree": tree
    }

##############################################################################
# 2. Minimally parse <mixed-citation> to skip authors/year/vol tags
##############################################################################

def extract_title_from_mixed_citation(mixed_elem):
    sub_article_titles = mixed_elem.xpath('.//*[local-name()="article-title"]')
    if sub_article_titles:
        return " ".join(sub_article_titles[0].itertext()).strip()

    unwanted_tags = {
        "string-name", "person-group", "year", "volume",
        "issue", "fpage", "lpage", "pub-id", "edition",
        "conf-date", "name", "isbn", "editor",
    }

    def itertext_desired(root):
        from lxml import etree
        for node in root.iter():
            if not isinstance(node, etree._Element):
                continue
            if not node.tag or not isinstance(node.tag, str):
                continue

            local = etree.QName(node).localname
            if local in unwanted_tags:
                continue

            if node.text:
                yield node.text
            if node.tail:
                yield node.tail

    parts = list(itertext_desired(mixed_elem))
    text = " ".join(p.strip() for p in parts if p.strip())
    return text

##############################################################################
# 3. get_all_citation_paragraphs: gather ALL paragraphs referencing ref_id
##############################################################################

def get_all_citation_paragraphs(tree, ref_id):
    xrefs = tree.xpath(".//xref[(@ref-type='bibr' or @ref-type='ref')]")
    matched_paras = []
    for x in xrefs:
        rid_attr = x.get("rid", "")
        rid_parts = rid_attr.split()
        if ref_id in rid_parts:
            elem = x
            while elem is not None and elem.tag != 'p':
                elem = elem.getparent()
            if elem is not None:
                paragraph_text = " ".join(elem.itertext()).strip()
                matched_paras.append(paragraph_text)
    return matched_paras

##############################################################################
# 4. Fix minor apostrophe spacing
##############################################################################

def fix_apostrophe_spacing(txt):
    """
    Insert a space if we see something like "in'burned" => "in ' burned".
    This is limited so we don't handle bigger 'typos', but it catches the
    missing space around quotes or apostrophes next to letters.
    """
    txt = re.sub(r"([A-Za-z0-9])'([A-Za-z0-9])", r"\1 ' \2", txt)
    return txt

##############################################################################
# 5. Title Normalization
##############################################################################

def normalize_title_strict(txt):
    # fix missing space around apostrophes
    txt = fix_apostrophe_spacing(txt)
    txt = txt.lower()
    # hyphens => space
    txt = re.sub(r'[-]+', ' ', txt)
    # remove punctuation except spaces
    txt = re.sub(r'[^a-z0-9\s]+', '', txt)
    # collapse multiple spaces
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()

##############################################################################
# 6. Substring-based fallback matching approach
##############################################################################

def titles_match_substring(citing_title, cited_title):
    """
    Instead of exact equality, we check if cited_title is a substring
    of citing_title after normalizing punctuation/whitespace/hyphens.

    This helps when citing_title has extra text (authors, journal, year),
    but the actual 'paper title' is inside it.
    """
    norm_citing = normalize_title_strict(citing_title)
    norm_cited  = normalize_title_strict(cited_title)
    # Return True if norm_cited is contained in norm_citing
    return norm_cited in norm_citing

##############################################################################
# 7. Main process_pairs
##############################################################################

def process_pairs(matching_uids_xml_paths, matching_uids_pmid_list):
    """
    For each pair (xmlA, xmlB),(pmidA, pmidB):
      parse docA => dataA, docB => dataB
      check if A references B by:
        A) B's doi => revA_doi
        B) B's pmid => revA_pmid
        C) B's pmcid => revA_pmcid
        D) fallback => substring match
      if found => store paragraphs in "citation_paragraphs"
      else check B => A similarly

    We now also return indices_list, which tracks the i-th pair index
    for each found citation.
    """
    results = []
    indices_list = []

    for i, ((xmlA, xmlB), (pmidA, pmidB)) in enumerate(zip(matching_uids_xml_paths, matching_uids_pmid_list)):
        dataA = parse_nxml(xmlA)
        dataB = parse_nxml(xmlB)
        if not dataA or not dataB:
            continue

        # Quick check that dataA['pmid'] is among (pmidA, pmidB)
        if dataA['pmid'] and dataA['pmid'] not in (pmidA, pmidB):
            continue
        # Same for dataB
        if dataB['pmid'] and dataB['pmid'] not in (pmidA, pmidB):
            continue

        # Build references map for doc A
        citing_found = False
        revA_doi   = {}
        revA_pmid  = {}
        revA_pmcid = {}

        for r_id, r_info in dataA["references"].items():
            if r_info["doi"]:
                revA_doi[r_info["doi"]] = r_id
            if r_info["pmid"]:
                revA_pmid[r_info["pmid"]] = r_id
            if r_info["pmcid"]:
                revA_pmcid[r_info["pmcid"]] = r_id

        # A => B
        if dataB["doi"] and dataB["doi"] in revA_doi:
            rid = revA_doi[dataB["doi"]]
            paragraphs = get_all_citation_paragraphs(dataA["tree"], rid)
            results.append({
                "citing_title": dataA["title"],
                "citing_abstract": dataA["abstract"],
                "citation_paragraphs": paragraphs,
                "cited_title": dataB["title"],
                "cited_abstract": dataB["abstract"]
            })
            indices_list.append(i)
            citing_found = True
        elif dataB["pmid"] and dataB["pmid"] in revA_pmid:
            rid = revA_pmid[dataB["pmid"]]
            paragraphs = get_all_citation_paragraphs(dataA["tree"], rid)
            results.append({
                "citing_title": dataA["title"],
                "citing_abstract": dataA["abstract"],
                "citation_paragraphs": paragraphs,
                "cited_title": dataB["title"],
                "cited_abstract": dataB["abstract"]
            })
            indices_list.append(i)
            citing_found = True
        elif dataB["pmcid"] and dataB["pmcid"] in revA_pmcid:
            rid = revA_pmcid[dataB["pmcid"]]
            paragraphs = get_all_citation_paragraphs(dataA["tree"], rid)
            results.append({
                "citing_title": dataA["title"],
                "citing_abstract": dataA["abstract"],
                "citation_paragraphs": paragraphs,
                "cited_title": dataB["title"],
                "cited_abstract": dataB["abstract"]
            })
            indices_list.append(i)
            citing_found = True
        else:
            # fallback => substring matching for B's title
            b_title = dataB["title"].strip()
            if b_title:
                for (r_id, r_info) in dataA["references"].items():
                    # skip if r_info has the same pmid/doi/pmcid
                    if (r_info["pmid"]  == dataB["pmid"] or
                        r_info["doi"]   == dataB["doi"]  or
                        r_info["pmcid"] == dataB["pmcid"]):
                        continue
                    if titles_match_substring(r_info["title"], b_title):
                        paragraphs = get_all_citation_paragraphs(dataA["tree"], r_id)
                        results.append({
                            "citing_title": dataA["title"],
                            "citing_abstract": dataA["abstract"],
                            "citation_paragraphs": paragraphs,
                            "cited_title": dataB["title"],
                            "cited_abstract": dataB["abstract"]
                        })
                        indices_list.append(i)
                        citing_found = True
                        break

        # If not found, check B => A the same way
        if not citing_found:
            revB_doi   = {}
            revB_pmid  = {}
            revB_pmcid = {}

            for r_id, r_info in dataB["references"].items():
                if r_info["doi"]:
                    revB_doi[r_info["doi"]] = r_id
                if r_info["pmid"]:
                    revB_pmid[r_info["pmid"]] = r_id
                if r_info["pmcid"]:
                    revB_pmcid[r_info["pmcid"]] = r_id

            if dataA["doi"] and dataA["doi"] in revB_doi:
                rid = revB_doi[dataA["doi"]]
                paragraphs = get_all_citation_paragraphs(dataB["tree"], rid)
                results.append({
                    "citing_title": dataB["title"],
                    "citing_abstract": dataB["abstract"],
                    "citation_paragraphs": paragraphs,
                    "cited_title": dataA["title"],
                    "cited_abstract": dataA["abstract"]
                })
                indices_list.append(i)
            elif dataA["pmid"] and dataA["pmid"] in revB_pmid:
                rid = revB_pmid[dataA["pmid"]]
                paragraphs = get_all_citation_paragraphs(dataB["tree"], rid)
                results.append({
                    "citing_title": dataB["title"],
                    "citing_abstract": dataB["abstract"],
                    "citation_paragraphs": paragraphs,
                    "cited_title": dataA["title"],
                    "cited_abstract": dataA["abstract"]
                })
                indices_list.append(i)
            elif dataA["pmcid"] and dataA["pmcid"] in revB_pmcid:
                rid = revB_pmcid[dataA["pmcid"]]
                paragraphs = get_all_citation_paragraphs(dataB["tree"], rid)
                results.append({
                    "citing_title": dataB["title"],
                    "citing_abstract": dataB["abstract"],
                    "citation_paragraphs": paragraphs,
                    "cited_title": dataA["title"],
                    "cited_abstract": dataA["abstract"]
                })
                indices_list.append(i)
            else:
                # fallback => substring matching for A's title
                a_title = dataA["title"].strip()
                if a_title:
                    for (r_id, r_info) in dataB["references"].items():
                        if (r_info["pmid"]  == dataA["pmid"] or
                            r_info["doi"]   == dataA["doi"]  or
                            r_info["pmcid"] == dataA["pmcid"]):
                            continue
                        if titles_match_substring(r_info["title"], a_title):
                            paragraphs = get_all_citation_paragraphs(dataB["tree"], r_id)
                            results.append({
                                "citing_title": dataB["title"],
                                "citing_abstract": dataB["abstract"],
                                "citation_paragraphs": paragraphs,
                                "cited_title": dataA["title"],
                                "cited_abstract": dataA["abstract"]
                            })
                            indices_list.append(i)
                            break

    return results, indices_list


citation_list, citation_valid_indices = process_pairs(matching_uids_xml_paths, matching_uids_pmid_list)

# --- cell 57 (citation verification)
# with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/citation_extrac_list.json', 'w') as f:
#     json.dump(citation_list, f)

# --- cell 61 (citation request and output; first-pass citation request (passage key))
with open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/batch_requests.jsonl", "w", encoding="utf-8") as f:
    for i, record in enumerate(citation_list, start=1):
        user_content = (
            f"Citing Title: {record.get('citing_title', '')}\n"
            f"Citing Abstract: {record.get('citing_abstract', '')}\n"
            f"Citation Paragraph: {record.get('citation_paragraph', '')}\n"
            f"Cited Title: {record.get('cited_title', '')}\n"
            f"Cited Abstract: {record.get('cited_abstract', '')}"
        )

        request_obj = {
            "custom_id": f"request-{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "o3-mini",
                "reasoning_effort": "medium",
                "messages": [
                    {"role": "developer", "content": 
                        """You are a medical citation analysis assistant. You will read excerpts from a 'citing paper' referencing another 'cited paper,' each describing a single-patient case report. Your task is to produce four pieces of information:

                        1. Reason for Citation (a short phrase or sentence about why the authors mention the cited paper).
                        2. Possible Similarities (a brief mention of how these patients’ cases align, if at all).
                        3. Explanation (one to two sentences summarizing how the citation is used).
                        4. Confidence (High, Medium, or Low), based on the degree of similarity between the single-patient cases:
                        - High: The text explicitly states that the two patients share significant clinical or therapeutic similarities.
                        - Medium: Some parallels are hinted at but lack explicit detail or direct confirmation.
                        - Low: The citation is vague or does not clearly connect the patients’ key features.

                        ----
                        Follow this exact output format:
                        Reason for Citation: <short phrase or sentence>
                        Possible Similarities: <brief mention>
                        Explanation: <one to two sentences>
                        Confidence: <High/Medium/Low>

                        ----
                        Read the following excerpt(s) and generate your final answer in the required format. Unify your response if multiple citations are present. If no citations are specified, base your response on the articles' titles and abstracts.
                        """
                    },

                    {"role": "user", "content": user_content}
                ]
            }
        }
        # Write each object on a new line in the JSONL file
        f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 65 (citation request and output)
batch_input_file = client.files.create(
  file=open("<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/batch_requests.jsonl", "rb"),
  purpose="batch"
)

# --- cell 66 (citation request and output)
batch_input_file_id = batch_input_file.id

client.batches.create(
    input_file_id=batch_input_file_id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
    metadata={
      "description": "Citation Reason Extraction"
    }
)

# --- cell 69 (citation request and output)
file_response = client.files.content('<OPENAI_ID>')
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

o3_mini_response_list = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 70 (citation request and output)
# with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/o3_mini_response_list.json', 'w') as f:
#     json.dump(o3_mini_response_list, f)

with open('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/o3_mini_response_list.json', 'r') as f:
    o3_mini_response_list = json.load(f)

# --- cell 81 (xml and pmid inputs)
import os
import glob
from lxml import etree

def extract_pmids_from_nxml(file_path):
    """Return a list of PMIDs found in a single .nxml file."""
    tree = etree.parse(file_path)
    pmid_elements = tree.xpath('//article-id[@pub-id-type="pmid"]')
    pmids = [elem.text.strip() for elem in pmid_elements if elem.text]
    return pmids[0]

def find_and_extract_pmids(directory):
    """
    Look for the first .nxml file in 'directory' (non-recursive)
    and extract PMIDs from it.
    """
    # Search only *.nxml in this directory (no subfolders)
    nxml_files = glob.glob(os.path.join(directory, '*.nxml'))
    if not nxml_files:
        return None

    # Take the first .nxml file in the directory
    file_path = nxml_files[0]

    pmc_id = file_path[61:68] + '-1'  

    # Extract PMIDs
    pmids = extract_pmids_from_nxml(file_path)
    if pmids:
        return pmids
    return None


find_and_extract_pmids('<DATA_ROOT>/pmc/pythonProject/data2/<PMCID>/<ARTICLE_ID>_1')

# --- cell 82 (xml and pmid inputs)
prefix = '<DATA_ROOT>/pmc/pythonProject/data2'
matching_uids_paths_list = [
    [os.path.join(prefix, os.path.join(f'PMC{id[:-2]}', f'{id[:-2]}_1')) for id in pair]
    for pair in matching_uids
]

# --- cell 85 (xml and pmid inputs)
# matching_uids_pmid_list = [
#     [find_and_extract_pmids(path) for path in paths_pair]
#     for paths_pair in matching_uids_paths_list
# ]

with open ('<DATA_ROOT>/pmc/pythonProject/<DATA_ROOT>/matching_uids_pmid_list.json', 'r') as f:
    matching_uids_pmid_list = json.load(f)
