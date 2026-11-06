# --- cell 19 (compound selection)
with open('<DATA_ROOT>/compound_images_df.json', 'r') as f:
    compound_images_dict = json.load(f)

compound_images_df = pd.DataFrame(compound_images_dict)

# --- cell 20 (compound selection)
# Add 'caption_id' of such form "<IMAGE_ID>, <IMAGE_ID>" to each caption
# This will help us later in creating a dictionary mapping each patient_uid to all of its captions
compound_images_df['caption_id'] = compound_images_df['caption_path'].apply(
    lambda x: os.path.splitext(os.path.basename(x))[0])

# --- cell 23 (compound selection)
def creating_uids_pairs(df, rows_num):
    matching_uids = []
    checked_pairs = set()
    # Create a set of patient_uids present in the filtered DataFrame
    uids_in_df = set(df['patient_uid'])
    
    for index, row in df.head(rows_num).iterrows():
        patient_uid = row['patient_uid']
        sim_patients = row['unique_articles_sim_patients']
    
        # Skip NaN values
        if pd.isna(sim_patients):
            continue
    
        # Clean the 'unique_articles_sim_patients' column
        sim_patients = sim_patients.strip("[]").replace("'", "")
        sim_patients_list = sim_patients.split(', ') if sim_patients else []
    
        for similar_uid in sim_patients_list:
            # Skip self-matching
            if similar_uid == patient_uid:
                continue

            # Check if similar_uid is in the filtered DataFrame
            if similar_uid not in uids_in_df:
                continue  # Skip if similar_uid not in the DataFrame

            # Create a sorted tuple to handle symmetry
            pair = tuple(sorted([patient_uid, similar_uid]))
    
            # Check if the pair was already added
            if pair not in checked_pairs:
                matching_uids.append([patient_uid, similar_uid])  # Add the pair
                checked_pairs.add(pair)  # Mark this pair as checked

    return matching_uids


# compound_m_uids = creating_uids_pairs(compound_images_df, len(compound_images_df))

# --- cell 25 (compound selection)
with open(os.path.join(jsons_path, 'imgs_paths_diagrams.json'), 'r') as f:
    imgs_paths_diagrams = json.load(f)


l = [x.split('data2/')[1] for x in imgs_paths_diagrams]
g = list(compound_images_df['image_path'])
h = pd.Series(list(set(g) - set(l)))
compound_images_df = compound_images_df.loc[compound_images_df["image_path"].isin(h)]
compound_m_uids = creating_uids_pairs(compound_images_df, len(compound_images_df))

print(len(compound_m_uids))

# --- cell 28 (compound selection)
def creating_txt_jpg_pairs(matching_uids, file_path, patient_uid_to_captions):
    # Each list consists of pairs containing the aligned files for each patient_uid
    pairs_text_list = []
    pairs_image_list = []
    not_found_counter = 0

    # Iterating over the pairs
    for pair in matching_uids:
        uids = [pair[0][:-2], pair[1][:-2]]
    
        pair_aligned_txt_files = []
        pair_aligned_jpg_files = []
    
        # Iterating over each patient_uid within the pair
        for uid in uids:
            # Construct the full path using the base_path parameter
            path = os.path.join(file_path, f'PMC{uid}/{uid}_1')
    
            # Check if the path exists
            if not os.path.exists(path):
                # print(f"Directory {path} does not exist.")
                not_found_counter += 1
                continue
    
            # Get all txt and jpg files within a single patient_uid
            txt_files = glob.glob(os.path.join(path, '*.txt'))
            jpg_files = glob.glob(os.path.join(path, '*.jpg'))

            # Get valid caption IDs for this patient_uid
            valid_caption_ids = patient_uid_to_captions.get(uid+'-1', set())

            # Create mappings: '<IMAGE_ID>' -> '/path/to/<IMAGE_ID>.txt'
            txt_files_dict = {os.path.splitext(os.path.basename(f))[0]: f for f in txt_files}
            jpg_files_dict = {os.path.splitext(os.path.basename(f))[0]: f for f in jpg_files}

            # Find common keys that are in the valid captions for this uid
            common_keys = set(txt_files_dict.keys()) & set(jpg_files_dict.keys()) & valid_caption_ids

            # Sort the paths to align txt and jpg files
            sorted_keys = sorted(common_keys)

            # Align txt and jpg files (within the same patient_uid)
            aligned_txt_files = [txt_files_dict[key] for key in sorted_keys]
            aligned_jpg_files = [jpg_files_dict[key] for key in sorted_keys]

            # Append the aligned files for this patient_uid to the pair's list
            pair_aligned_txt_files.append(aligned_txt_files)
            pair_aligned_jpg_files.append(aligned_jpg_files)
    
        # After processing both patient_uids in the pair, append the pair to the main list
        if len(pair_aligned_txt_files) == 2:
            pairs_text_list.append(pair_aligned_txt_files)
            pairs_image_list.append(pair_aligned_jpg_files)
    
    return pairs_text_list, pairs_image_list, not_found_counter


# # Create the mapping from 'patient_uid' to a set of 'caption_id's
# patient_uid_to_captions = compound_images_df.groupby('patient_uid')['caption_id'].apply(set).to_dict()

# # Build the two 3D lists
# pairs_text_list, pairs_image_list, missing = \
#     creating_txt_jpg_pairs(compound_m_uids, data_path, patient_uid_to_captions)

# --- cell 29 (compound selection)
    # # Save the pairs to JSON files
    # with open(os.path.join(jsons_path, 'compound_text_list.json'), 'w') as f:
    #     json.dump(pairs_text_list, f)

    # with open(os.path.join(jsons_path, 'compound_image_list.json'), 'w') as f:
    #     json.dump(pairs_image_list, f)

    with open(os.path.join(jsons_path, 'compound_text_list.json'), 'r') as f:
        compound_text_list = json.load(f)

    with open(os.path.join(jsons_path, 'compound_image_list.json'), 'r') as f:
        compound_image_list = json.load(f)

# --- cell 31 (compound selection)
# import os
# import json
# from pathlib import Path
# from functools import lru_cache

# DATA2_BASE = Path("<DATA_ROOT>/data2")

# def strip_dash_suffix(uid: str) -> str:
#     """
#     '<CASE_ID>' -> '<ARTICLE_ID>'
#     If there's no '-', returns the whole string.
#     """
#     return uid.split("-", 1)[0]

# @lru_cache(maxsize=None)
# def pmc_id_to_nxml_path(pmc_id: str) -> str | None:
#     """
#     Returns the selected .nxml file path for a given PMC numeric id (no 'PMC' prefix),
#     or None if not found.

#     If multiple .nxml files exist, picks the largest by file size (usually the main article).
#     """
#     dir_path = DATA2_BASE / f"PMC{pmc_id}" / f"{pmc_id}_1"
#     if not dir_path.is_dir():
#         return None

#     candidates = list(dir_path.glob("*.nxml"))
#     if not candidates:
#         return None

#     if len(candidates) == 1:
#         return str(candidates[0])

#     # Multiple .nxml files: pick largest (often most complete)
#     candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
#     return str(candidates[0])

# def build_compound_uids_xml_paths(compound_m_uids: list[list[str]]):
#     """
#     Returns:
#       compound_uids_xml_paths: list of [path1, path2] (paths are strings or None)
#       valid_indices: indices where both paths were found
#       missing: list of (idx, uid1, uid2, path1, path2) for debugging
#     """
#     compound_uids_xml_paths = []
#     missing = []

#     for idx, (uid1, uid2) in enumerate(compound_m_uids):
#         pmc1 = strip_dash_suffix(uid1)
#         pmc2 = strip_dash_suffix(uid2)

#         path1 = pmc_id_to_nxml_path(pmc1)
#         path2 = pmc_id_to_nxml_path(pmc2)

#         compound_uids_xml_paths.append([path1, path2])

#         if path1 is None or path2 is None:
#             missing.append((idx, uid1, uid2, path1, path2))

#     valid_indices = [
#         i for i, (p1, p2) in enumerate(compound_uids_xml_paths)
#         if (p1 is not None and p2 is not None)
#     ]

#     return compound_uids_xml_paths, valid_indices, missing


# compound_uids_xml_paths, valid_indices, missing = build_compound_uids_xml_paths(compound_m_uids)

# print(f"Total pairs: {len(compound_m_uids)}")
# print(f"Pairs with both .nxml found: {len(valid_indices)}")
# print(f"Pairs missing at least one .nxml: {len(missing)}")

# # Show a few missing examples (if any)
# for row in missing[:5]:
#     print("MISSING:", row)


# with open(os.path.join(jsons_path, "compound_uids_xml_paths.json"), "w") as f:
#     json.dump(compound_uids_xml_paths, f)
# with open(os.path.join(jsons_path, "compound_valid_indices.json"), "w") as f:
#     json.dump(valid_indices, f)

# --- cell 34 (compound selection)
# """
# Objective:
#   Extract “case…” sections (e.g. Case Presentation, Case Report, Patient Summary, etc.) 
#   from a list of PMC .nxml files so you can later compute diagnosis similarity via generated queries.

# Usage:
#   python extract_case_summaries.py \
#     --jsons_path <DATA_ROOT>
# """
# import os
# import json
# import argparse
# from lxml import etree
# from multiprocessing import Pool


# def process_file_list(file_list):
#     """
#     Given a list of file paths, parse each file, run the XPath,
#     gather the text from <sec> paragraphs, return a dict { filepath: text }.
#     """
#     # Create an XPath expression that matches <sec> elements with a <title> containing any of the keywords.
#     # Using translate() ensures a case-insensitive search.
#     xpath_expr = (
#         "//sec["
#         "  contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case presentation') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case report') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case description') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case summary') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient presentation') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient report') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient description') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'patient summary') "
#         "or contains(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'case') "
#         "or (normalize-space(translate(title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) = 'patient') "
#         "]"
#     )
#     single_pair_case_summary = {}
#     for file in file_list:
#         tree = etree.parse(file)
#         sections = tree.xpath(xpath_expr)
#         for sec in sections:
#             paragraphs = sec.xpath(".//p//text()")
#             text = " ".join(paragraphs)
#             single_pair_case_summary[file] = text
#     return single_pair_case_summary


# def multiprocess_case_summaries(matching_uids_xml_paths):
#     with Pool() as pool:
#         # Map each sub-list to a worker process
#         case_summary_pairs_list = pool.map(process_file_list, matching_uids_xml_paths)

#     return case_summary_pairs_list


# def calc_indices_summaries_list(case_summary_pairs_list):
#     """
#     Returns two lists:
#       - A list of indices corresponding to elements depicting both cases.
#       - A list of indices corresponding to elements depicting less than 2 cases.
#     """
#     valid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) == 2]
#     invalid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) != 2]
#     return valid_indices, invalid_indices


# with open (os.path.join(jsons_path, 'compound_uids_xml_paths.json'), 'r') as f:
#     compound_uids_xml_paths = json.load(f)

# case_summary_pairs_list = multiprocess_case_summaries(compound_uids_xml_paths)
# case_summary_pairs_list = [list(case_summary_pairs_list[idx].values()) for idx in range(len(case_summary_pairs_list))]

# summaries_valid_indices, summaries_invalid_indices = calc_indices_summaries_list(case_summary_pairs_list)

# print(f"Extracted {len(summaries_valid_indices)} valid case summaries.")
# print(f"There are {len(summaries_invalid_indices)} missing case summaries.")

# --- cell 35 (compound selection)
# with open (os.path.join(jsons_path, 'compound_case_summary_pairs_list.json'), 'w') as f:
#     json.dump(case_summary_pairs_list, f)

# with open(os.path.join(jsons_path, 'compound_summaries_valid_indices.json'), 'w') as f:
#     json.dump(summaries_valid_indices, f)

# # with open (os.path.join(jsons_path, 'compound_valid_indices.json'), 'r') as f:
# #     valid_indices = json.load(f)

# --- cell 39 (compound citation)
# # --- Text cleanup / title matching ---

# def fix_apostrophe_spacing(txt: str) -> str:
#     """Fix cases like: in'burned -> in ' burned"""
#     return re.sub(r"([A-Za-z0-9])'([A-Za-z0-9])", r"\1 ' \2", txt)

# def normalize_title_strict(txt: str) -> str:
#     txt = fix_apostrophe_spacing(txt or "")
#     txt = txt.lower()
#     txt = re.sub(r"[-]+", " ", txt)          # hyphens => spaces
#     txt = re.sub(r"[^a-z0-9\s]+", "", txt)  # drop punctuation
#     txt = re.sub(r"\s+", " ", txt).strip()  # collapse whitespace
#     return txt

# def titles_match_substring(
#     citing_title: str,
#     cited_title: str,
#     *,
#     min_cited_chars: int = 0,
#     min_cited_tokens: int = 0,
# ) -> bool:
#     """Return True if normalized(cited_title) is a substring of normalized(citing_title)."""
#     norm_citing = normalize_title_strict(citing_title)
#     norm_cited  = normalize_title_strict(cited_title)
#     if not norm_cited:
#         return False
#     if min_cited_chars and len(norm_cited) < min_cited_chars:
#         return False
#     if min_cited_tokens and len(norm_cited.split()) < min_cited_tokens:
#         return False
#     return norm_cited in norm_citing

# # --- Minimal parsing of <mixed-citation> to recover a title ---

# def extract_title_from_mixed_citation(mixed_elem: etree._Element) -> str:
#     # Best case: an explicit <article-title> inside mixed-citation
#     sub_article_titles = mixed_elem.xpath('.//*[local-name()="article-title"]')
#     if sub_article_titles:
#         return " ".join(sub_article_titles[0].itertext()).strip()

#     # Otherwise: collect text while skipping common metadata tags
#     unwanted_tags = {
#         "string-name", "person-group", "year", "volume",
#         "issue", "fpage", "lpage", "pub-id", "edition",
#         "conf-date", "name", "isbn", "editor",
#     }

#     def itertext_desired(root: etree._Element):
#         for node in root.iter():
#             if not isinstance(node, etree._Element):
#                 continue
#             if not node.tag or not isinstance(node.tag, str):
#                 continue
#             local = etree.QName(node).localname
#             if local in unwanted_tags:
#                 continue
#             if node.text:
#                 yield node.text
#             if node.tail:
#                 yield node.tail

#     parts = list(itertext_desired(mixed_elem))
#     text = " ".join(p.strip() for p in parts if p.strip())
#     return text.strip()


# # --- Parse JATS (.nxml) into metadata + references + the lxml tree ---

# def parse_nxml(file_path: str) -> Optional[Dict[str, Any]]:
#     """
#     Parse a JATS .nxml and return:
#       pmid, doi, pmcid, title, abstract,
#       references: {ref_id: {doi, pmid, pmcid, title}},
#       tree: lxml parsed tree

#     Returns None on missing file or parse error.
#     """
#     if not file_path or not os.path.isfile(file_path):
#         return None

#     parser = etree.XMLParser(recover=True, huge_tree=True)
#     try:
#         tree = etree.parse(file_path, parser)
#     except Exception:
#         return None

#     root = tree.getroot()

#     def _get_article_id(id_type: str) -> Optional[str]:
#         elems = root.xpath(f'//*[local-name()="article-id"][@pub-id-type="{id_type}"]')
#         if elems and elems[0].text:
#             return elems[0].text.strip()
#         return None

#     paper_pmid  = _get_article_id("pmid")
#     paper_doi   = _get_article_id("doi")
#     paper_pmcid = _get_article_id("pmc")

#     # Title
#     title_elems = root.xpath('//*[local-name()="title-group"]//*[local-name()="article-title"]')
#     if not title_elems:
#         title_elems = root.xpath('//*[local-name()="article-title"]')
#     paper_title = "".join(title_elems[0].itertext()).strip() if title_elems else ""

#     # Abstract (concatenate all <abstract> blocks)
#     abstract_elems = root.xpath('//*[local-name()="abstract"]')
#     abs_texts = []
#     for abs_elem in abstract_elems:
#         txt = " ".join(abs_elem.itertext()).strip()
#         if txt:
#             abs_texts.append(txt)
#     paper_abstract = " ".join(abs_texts).strip()

#     # References
#     references: Dict[str, Dict[str, Optional[str]]] = {}
#     ref_list = root.xpath('//*[local-name()="ref"]')
#     for ref_node in ref_list:
#         r_id = ref_node.get("id")
#         if not r_id:
#             continue

#         doi_elems   = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="doi"]')
#         pmid_elems  = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmid"]')
#         pmcid_elems = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmc"]')

#         cited_doi   = doi_elems[0].text.strip()   if doi_elems   and doi_elems[0].text else None
#         cited_pmid  = pmid_elems[0].text.strip()  if pmid_elems  and pmid_elems[0].text else None
#         cited_pmcid = pmcid_elems[0].text.strip() if pmcid_elems and pmcid_elems[0].text else None

#         # Prefer <element-citation>/<article-title>, else <mixed-citation>, else <comment>
#         ec_title_elems = ref_node.xpath('.//*[local-name()="element-citation"]/*[local-name()="article-title"]')
#         if ec_title_elems:
#             ref_title = " ".join(ec_title_elems[0].itertext()).strip()
#         else:
#             mixed_elems = ref_node.xpath('.//*[local-name()="mixed-citation"]')
#             if mixed_elems:
#                 ref_title = extract_title_from_mixed_citation(mixed_elems[0])
#             else:
#                 comment_elems = ref_node.xpath('.//*[local-name()="element-citation"]/*[local-name()="comment"]')
#                 if comment_elems:
#                     ref_title = " ".join(comment_elems[0].itertext()).strip()
#                 else:
#                     ref_title = ""

#         references[r_id] = {
#             "doi": cited_doi,
#             "pmid": cited_pmid,
#             "pmcid": cited_pmcid,
#             "title": ref_title
#         }

#     return {
#         "pmid": paper_pmid,
#         "doi": paper_doi,
#         "pmcid": paper_pmcid,
#         "title": paper_title,
#         "abstract": paper_abstract,
#         "references": references,
#         "tree": tree,
#         "file_path": file_path,
#     }


# # --- Extract all paragraphs that cite a given reference id (rid) ---

# def get_all_citation_paragraphs(tree: etree._ElementTree, ref_id: str) -> List[str]:
#     # Match <xref ref-type="bibr" rid="R1"> or <xref ref-type="ref" ...>
#     xrefs = tree.xpath('.//*[local-name()="xref"][@ref-type="bibr" or @ref-type="ref"]')
#     paras: List[str] = []
#     seen = set()

#     for x in xrefs:
#         rid_attr = x.get("rid", "") or ""
#         rid_parts = rid_attr.split()
#         if ref_id not in rid_parts:
#             continue

#         elem = x
#         while elem is not None:
#             try:
#                 if etree.QName(elem).localname == "p":
#                     break
#             except Exception:
#                 pass
#             elem = elem.getparent()

#         if elem is not None:
#             paragraph_text = " ".join(elem.itertext()).strip()
#             if paragraph_text and paragraph_text not in seen:
#                 paras.append(paragraph_text)
#                 seen.add(paragraph_text)

#     return paras

# # --- In-memory caching to avoid reparsing the same .nxml many times ---

# _DOC_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}

# def get_doc(file_path: str) -> Optional[Dict[str, Any]]:
#     if file_path not in _DOC_CACHE:
#         _DOC_CACHE[file_path] = parse_nxml(file_path)
#     return _DOC_CACHE[file_path]

# def _build_reference_maps(doc: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
#     """Return (doi->ref_id, pmid->ref_id, pmcid->ref_id)"""
#     rev_doi: Dict[str, str] = {}
#     rev_pmid: Dict[str, str] = {}
#     rev_pmcid: Dict[str, str] = {}

#     for r_id, r_info in doc["references"].items():
#         if r_info.get("doi"):
#             rev_doi[r_info["doi"]] = r_id
#         if r_info.get("pmid"):
#             rev_pmid[r_info["pmid"]] = r_id
#         if r_info.get("pmcid"):
#             rev_pmcid[r_info["pmcid"]] = r_id

#     return rev_doi, rev_pmid, rev_pmcid


# def _find_citation_rid(
#     citing_doc: Dict[str, Any],
#     cited_doc: Dict[str, Any],
#     *,
#     title_fallback: bool = True,
#     title_min_cited_chars: int = 0,
#     title_min_cited_tokens: int = 0,
# ) -> Tuple[Optional[str], Optional[str]]:
#     """Return (ref_id, match_type) in citing_doc referencing cited_doc, else (None, None)."""
#     rev_doi, rev_pmid, rev_pmcid = _build_reference_maps(citing_doc)

#     if cited_doc.get("doi") and cited_doc["doi"] in rev_doi:
#         return rev_doi[cited_doc["doi"]], "doi"
#     if cited_doc.get("pmid") and cited_doc["pmid"] in rev_pmid:
#         return rev_pmid[cited_doc["pmid"]], "pmid"
#     if cited_doc.get("pmcid") and cited_doc["pmcid"] in rev_pmcid:
#         return rev_pmcid[cited_doc["pmcid"]], "pmcid"

#     if title_fallback:
#         cited_title = (cited_doc.get("title") or "").strip()
#         if cited_title:
#             for r_id, r_info in citing_doc["references"].items():
#                 # Skip if IDs already match (avoid "double matching" when IDs exist)
#                 if (
#                     (r_info.get("pmid")  and r_info["pmid"]  == cited_doc.get("pmid")) or
#                     (r_info.get("doi")   and r_info["doi"]   == cited_doc.get("doi"))  or
#                     (r_info.get("pmcid") and r_info["pmcid"] == cited_doc.get("pmcid"))
#                 ):
#                     continue

#                 if titles_match_substring(
#                     r_info.get("title") or "",
#                     cited_title,
#                     min_cited_chars=title_min_cited_chars,
#                     min_cited_tokens=title_min_cited_tokens,
#                 ):
#                     return r_id, "title_substring"

#     return None, None


# def process_pairs(
#     xml_pairs: List[List[str]],
#     *,
#     pair_indices: Optional[List[int]] = None,
#     title_fallback: bool = True,
#     title_min_cited_chars: int = 0,
#     title_min_cited_tokens: int = 0,
#     verbose: bool = False,
# ) -> Tuple[List[Dict[str, Any]], List[int]]:
#     """
#     For each pair (xmlA, xmlB):
#       - parse both
#       - check A cites B; else check B cites A
#       - if found, collect all paragraphs that cite the matching ref_id

#     pair_indices:
#       - if provided, must align with xml_pairs (same length)
#       - used to report indices relative to the *original* dataset

#     Returns (results, indices).
#     """
#     if pair_indices is None:
#         pair_indices = list(range(len(xml_pairs)))

#     results: List[Dict[str, Any]] = []
#     indices_list: List[int] = []

#     for local_i, (pair, original_i) in enumerate(zip(xml_pairs, pair_indices)):
#         if not pair or len(pair) != 2:
#             continue
#         xmlA, xmlB = pair

#         docA = get_doc(xmlA)
#         docB = get_doc(xmlB)
#         if not docA or not docB:
#             if verbose:
#                 print(f"Skipping pair idx={original_i}: parse failed")
#             continue

#         # A -> B
#         rid, match_type = _find_citation_rid(
#             docA, docB,
#             title_fallback=title_fallback,
#             title_min_cited_chars=title_min_cited_chars,
#             title_min_cited_tokens=title_min_cited_tokens,
#         )
#         if rid:
#             paras = get_all_citation_paragraphs(docA["tree"], rid)
#             results.append({
#                 "pair_index": original_i,
#                 "citing_file": docA["file_path"],
#                 "cited_file": docB["file_path"],
#                 "match_type": match_type,
#                 "match_ref_id": rid,
#                 "citing_title": docA["title"],
#                 "citing_abstract": docA["abstract"],
#                 "citation_paragraphs": paras,
#                 "cited_title": docB["title"],
#                 "cited_abstract": docB["abstract"],
#             })
#             indices_list.append(original_i)
#             continue

#         # B -> A
#         rid, match_type = _find_citation_rid(
#             docB, docA,
#             title_fallback=title_fallback,
#             title_min_cited_chars=title_min_cited_chars,
#             title_min_cited_tokens=title_min_cited_tokens,
#         )
#         if rid:
#             paras = get_all_citation_paragraphs(docB["tree"], rid)
#             results.append({
#                 "pair_index": original_i,
#                 "citing_file": docB["file_path"],
#                 "cited_file": docA["file_path"],
#                 "match_type": match_type,
#                 "match_ref_id": rid,
#                 "citing_title": docB["title"],
#                 "citing_abstract": docB["abstract"],
#                 "citation_paragraphs": paras,
#                 "cited_title": docA["title"],
#                 "cited_abstract": docA["abstract"],
#             })
#             indices_list.append(original_i)

#     return results, indices_list


# # Choose which indices to process
# if "compound_summaries_valid_indices" in globals() and compound_summaries_valid_indices:
#     indices_to_process = list(compound_summaries_valid_indices)
# else:
#     indices_to_process = list(range(len(compound_uids_xml_paths)))

# xml_pairs_to_process = [compound_uids_xml_paths[i] for i in indices_to_process]

# citation_list, citation_valid_indices = process_pairs(
#     xml_pairs_to_process,
#     pair_indices=indices_to_process,  # keeps original indices
#     title_fallback=True,
#     title_min_cited_chars=0,          # set e.g. 30 to reduce false positives
#     title_min_cited_tokens=0,         # set e.g. 5  to reduce false positives
#     verbose=False,
# )

# print(f"Found {len(citation_valid_indices)} citing pairs out of {len(indices_to_process)} processed pairs.")

# --- cell 40 (compound citation)
# with open(os.path.join(jsons_path, 'compound_citation_list.json'), 'w') as f:
#     json.dump(citation_list, f)

# with open(os.path.join(jsons_path, 'compound_citation_valid_indices.json'), 'w') as f:
#     json.dump(citation_valid_indices, f)

# --- cell 46 (compound citation)
# with open(os.path.join(jsons_path, 'compound_batch_reqs/compound_citation_req.jsonl'), 'w', encoding="utf-8") as f:
#     for i, record in enumerate(compound_citation_list, start=1):
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
#             "url": "/v1/chat/completions",
#             "body": {
#                 "model": "o3-mini",
#                 "reasoning_effort": "medium",
#                 "messages": [
#                     {"role": "developer", "content": 
#                         """You are a medical citation analysis assistant. You will read excerpts from a 'citing paper' referencing another 'cited paper,' each describing a single-patient case report. Your task is to produce four pieces of information:

#                         1. Reason for Citation (a short phrase or sentence about why the authors mention the cited paper).
#                         2. Possible Similarities (a brief mention of how these patients’ cases align, if at all).
#                         3. Explanation (one to two sentences summarizing how the citation is used).

#                         ----
#                         Follow this exact output format:
#                         Reason for Citation: <short phrase or sentence>
#                         Possible Similarities: <brief mention>
#                         Explanation: <one to two sentences>
#                         ----
#                         Read the following excerpt(s) and generate your final answer in the required format. Unify your response if multiple citations are present. If no citations are specified, base your response on the articles' titles and abstracts.
#                         """
#                     },

#                     {"role": "user", "content": user_content}
#                 ]
#             }
#         }
#         # Write each object on a new line in the JSONL file
#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 47 (compound citation)
# # 1) Upload
# batch_input_file = client.files.create(
#     file=open(os.path.join(jsons_path, 'compound_batch_reqs/compound_citation_req.jsonl'), "rb"),
#     purpose="batch",
# )

# # 2) Create batch
# batch = client.batches.create(
#     input_file_id=batch_input_file.id,
#     endpoint="/v1/chat/completions",
#     completion_window="24h",
#     metadata={"description": "Citation Reason Extraction"},
# )

# --- cell 49 (compound citation)
# file_response = client.files.content("<OPENAI_ID>")
# file_response_text = file_response.text

# json_strings = file_response_text.strip().splitlines()

# # Parse each JSON string into a dictionary and store in a list
# response_dicts = [json.loads(line) for line in json_strings]

# compound_citation_response = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 50 (compound citation)
# with open(os.path.join(jsons_path, 'compound_batch_resps/compound_citation_reponse.jsonl'), 'w') as f:
#     json.dump(compound_citation_response, f)

with open(os.path.join(jsons_path, 'compound_batch_resps/compound_citation_reponse.jsonl'), 'r') as f:
    compound_citation_response = json.load(f)

# --- cell 52 (compound questions)
def calc_indices_summaries_list(case_summary_pairs_list):
    """
    Returns two lists:
      - A list of indices corresponding to elements depicting both cases.
      - A list of indices corresponding to elements depicting less than 2 cases.
    """
    valid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) == 2]
    invalid_indices = [idx for idx in range(len(case_summary_pairs_list)) if len(case_summary_pairs_list[idx]) != 2]

    return valid_indices, invalid_indices

# --- cell 55 (compound questions)
def find_common_indices(summaries_valid_indices, citation_valid_indices):
    """
    Find the common indices between summaries_valid_indices and citation_valid_indices:
      - summaries_valid_indices - represents the indices corresponding to successfully extracted case summaries (0-31,691) 
      - citation_valid_indices - represents the indices corresponding to successfully cited-citing pairs (0-31,691)
    """
    summaries_valid_indices_set = set(summaries_valid_indices)
    citation_valid_indices_set = set(citation_valid_indices)
    common_indices = []

    for i in range(len(compound_m_uids)):
        if i in summaries_valid_indices_set and i in citation_valid_indices_set:
            common_indices.append(i)
    
    return common_indices


common_indices = find_common_indices(summaries_valid_indices, compound_citation_valid_indices)

# --- cell 57 (compound questions)
citation_valid_indices_dict = {compound_citation_valid_indices[idx]: idx for idx in range(len(compound_citation_valid_indices))}

# --- cell 59 (compound questions)
# question_generating_prompt = """
# You are an experienced clinician specializing in medical imaging. You will be given two cases and the reason for citation between the two (one case report cites the other), and asked to generate a set of comparative, clinically relevant questions that highlight both similarities and differences, helping differentiate potential diagnoses. Your questions should:

# 1. **Focus on Diagnostic Clues and Clinical Significance:**
#    - Avoid trivial or purely technical details (like minor differences in image orientation).
#    - Emphasize findings that inform diagnosis (e.g., presence of lesions, pattern of abnormalities, symptoms).

# 2. **Use a Comparative Framing:**
#    - Explicitly compare Case A and Case B.
#    - Aim for questions that probe both common ground and distinguishing features.
#    - If possible, try asking mostly yes/no questions.

# 3. **Follow a Hierarchical Reasoning Approach:**
#    - **Level 1 (Broad Context)**: Are both cases the same modality/organ system?
#    - **Level 2 (General Diagnosis Category)**: Are they both infectious, both neoplastic, etc.?
#    - **Level 3 (Specific Features & Findings)**: Detailed imaging findings (e.g., cavitation, consolidation, nodules), clinical presentation, organism type, etc.

# 4. **Consider Step-by-Step Reasoning:**
#    - You may first silently analyze the diagnoses and imaging findings for each case.
#    - Then generate questions that a clinician would naturally ask to tease out whether the two cases have the same underlying pathology or different pathologies.

# 5. **Provide a subtitle specifying the level (1/2/3) of the current set of questions.**
# """

# question_generating_user = f"""
# Below are two cases and the reason for citation between the two. Read them carefully, then generate a concise list of question prompts (in numbered format) that compare these cases on clinically meaningful aspects.

# ---
# Case A:
# %s

# Case B:
# %s

# Reason for Citation, Possible Similarities and Explanation:
# %s
# ---

# Now, **generate the list of comparative, clinically relevant questions** that a radiologist or physician might ask to determine whether these two cases share a diagnosis or differ in key features. 

# Remember:
# - Maintain clinical depth: mention imaging findings, pathophysiology, or hallmark symptoms.
# - Emphasize similarities/differences that impact diagnosis.
# - Keep the questions focused and direct, as if you are performing a differential diagnosis.
# - Avoid vague or generic questions; ensure each question contributes to understanding diagnostic overlap or divergence.
# - Start with broad-level questions (anatomy, broad diagnosis similarity), then proceed to more specific questions about the nature of the condition, causative agents, imaging signs, etc.
# - Adhere to yes/no questions, if possible.
# - Provide a subtitle specifying the level (1/2/3) of each set of questions.

# Provide your final list of questions now.
# """


# with open(os.path.join(jsons_path, 'compound_batch_reqs/compound_questions_req.jsonl'), "w", encoding="utf-8") as f:
#     for i, curr_index in enumerate(common_indices, start=1):

#         case1 = compound_case_summary_pairs_list[curr_index][0]
#         case2 = compound_case_summary_pairs_list[curr_index][1]
#         citation_reason = compound_citation_response[citation_valid_indices_dict[curr_index]]


#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/chat/completions",
#             "body": {
#                 "model": "o4-mini",
#                 "reasoning_effort": "low",
#                 "messages": [
#                     {"role": "developer", "content": question_generating_prompt},
#                     {"role": "user", "content": question_generating_user % (case1, case2, citation_reason)}
#                 ]
#             }
#         }
#         # Write each object on a new line in the JSONL file
#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 65 (compound questions)
# file_response = client.files.content("file-")
# file_response_text = file_response.text

# json_strings = file_response_text.strip().splitlines()

# # Parse each JSON string into a dictionary and store in a list
# response_dicts = [json.loads(line) for line in json_strings]

# compound_questions_response = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 66 (compound questions)
# with open(os.path.join(jsons_path, 'compound_batch_resps/compound_questions_response.jsonl'), 'w') as f:
#     json.dump(compound_questions_response, f)

with open(os.path.join(jsons_path, 'compound_batch_resps/compound_questions_response.jsonl'), 'r') as f:
    compound_questions_response = json.load(f)

# --- cell 69 (compound answers)
# answering_prompt = """You will be given case details for Case A, Case B, Reason for Citation (one case cites the other), along with a list of questions.
# You are an experienced clinician specializing in medical imaging. Previously, a list of comparative, clinically oriented questions was generated for the two cases.
# Now, your task is to answer those questions in a way that highlights the diagnostic similarities and differences between the two cases.
# DO NOT provide any additional information or context outside of the answers to the questions.
# """


# with open(os.path.join(jsons_path, 'compound_batch_reqs/compound_answers_req.jsonl'), "w", encoding="utf-8") as f:
#     for idx in range(len(common_indices)):
#         common_index = common_indices[idx]
#         case1 = compound_case_summary_pairs_list[common_index][0]
#         case2 = compound_case_summary_pairs_list[common_index][1]
#         citation_reason = compound_citation_response[citation_valid_indices_dict[common_index]]
#         curr_questions = compound_questions_response[idx]

#         answering_user = f"""Below are the two case descriptions and the set of questions to be answered.

#         ---
#         Case A:
#         {case1}

#         Case B:
#         {case2}

#         Reason for Citation, Possible Similarities and Explanation:
#         {citation_reason}

#         Questions:
#         {curr_questions}
#         ---

#         Provide your answers now:
#         """

#         request_obj = {
#             "custom_id": f"request-{idx+1}",
#             "method": "POST",
#             "url": "/v1/chat/completions",
#             "body": {
#                     "model": "gpt-5-mini",
#                     "messages": [
#                         {
#                             "role": "developer",
#                             "content": f"{answering_prompt}"
#                         },
#                         {
#                             "role": "user",
#                             "content": f"{answering_user}"
#                         }
#                     ],
#             }
#         }
#         # Write each object on a new line in the JSONL file
#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 79 (compound answers)
file_response = client.files.content("<OPENAI_ID>")
file_response_text = file_response.text

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

compound_answers_response = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 82 (compound answers)
# with open(os.path.join(jsons_path, 'compound_batch_resps/compound_answers_response.jsonl'), 'w') as f:
#     json.dump(aligned_answers, f)

with open(os.path.join(jsons_path, 'compound_batch_resps/compound_answers_response.jsonl'), 'r') as f:
    compound_answers_response = json.load(f)

# --- cell 86 (compound labeling)
# compound_pairs_text = [
#     [ [open(p, encoding="utf-8").read().strip() for p in patient_group]
#       for patient_group in pair ]
#     for pair in compound_text_list
# ]

# --- cell 87 (compound labeling)
# with open(os.path.join(jsons_path, 'compound_pairs_text.json'), 'w') as f:
#     json.dump(compound_pairs_text, f)

with open(os.path.join(jsons_path, 'compound_pairs_text.json'), 'r') as f:
    compound_pairs_text = json.load(f)

# --- cell 91 (compound labeling)
from pathlib import Path

stems_3d = [
    [
        [Path(p).stem for p in sin_patient]   # 3rd level: every path in one patient
        for sin_patient in pair              # 2nd level: both patients in the pair
    ]
    for pair in compound_text_list              # 1st level: all pairs
]

stems_3d[0:1]

# --- cell 92 (compound labeling)
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

stem_caption_list = build_stem_caption_3d(compound_pairs_text, stems_3d)

# --- cell 100 (compound labeling)
compound_stem_caption_list = [
    [
        {k: v for k, v in d.items() if k in compound_stems_set}      # keep only wanted keys
        for d in inner                                   # loop over inner dicts
        if any(k in compound_stems_set for k in d)                  # …and drop empty dicts
    ]
    for inner in stem_caption_list                       # loop over outer groups
]

# --- cell 103 (compound labeling)
# The invalid caption-pairs rise when all the captions in patient1 or patient2 are filtered out (diagrams)
invalid_pairs_indices = [i for i, inner in enumerate(compound_stem_caption_list) if len(inner) < 2]
invalid_pairs_indices_set = set(invalid_pairs_indices)

# --- cell 108 (compound labeling)
prompt = "You are a medical-AI expert. " \
"Your job is to classify *pairs* of medical-image captions as " \
"**positive** if they share the same diagnosis & modality.\n" \
"\n" \
"### MATCHING RULES ###\n" \
"1. **Same Modality**: Match at the modality-family level (e.g., CT, MRI, Ultrasound, X-Ray). " \
"For example, a CT-CT pair is a positive match even if one caption says 'axial' and the other says 'sagittal'. " \
"Ignore differences in planes, views, or sequences.\n" \
"2. **Same Diagnosis**: Match if they share the same pathology family within the same organ system.\n" \
"   - IGNORE 'decorators' (such as acuity, severity, laterality, or exact anatomical slice/level).\n" \
"   - DO NOT collapse different pathophysiologies just because they look visually similar " \
"(e.g., do not match a tumor with an abscess/infection).\n" \
"\n" \
"NOTE: Classify **only inter-case pairs** (the two caption-IDs come from different cases).\n" \
"Output **only** valid JSON matching this schema (no markdown). For example:\n" \
"{\n" \
'  "pair_id": "<label_1, label_2>",\n' \
'  "reasoning": "<short explanation why it is positive>",\n' \
'  "modality": "<the shared modality-family>",\n' \
'  "anatomy": "<the shared organ system>",\n' \
'  "diagnosis": "<the shared pathology-family>"\n' \
"}\n" \
"DON'T classify (return nothing) if one of the following is true:\n" \
"1. They are negatives (they fail the modality or diagnosis criteria).\n" \
"2. If either caption describes a diagram/illustration.\n" \
"\n" \
"FINAL SANITY CHECK (before you output):\n" \
"✓ Inter-case pair?\n" \
"✓ Same modality-family (ignoring plane/view)?\n" \
"✓ Same pathology-family & organ system (ignoring decorators, strictly respecting pathophysiology)?\n" \
"✓ No diagram/illustration words?\n" \
"If every answer is YES → produce the JSON object.\n" \
"Otherwise → output {}."

# --- cell 109 (compound labeling)
# prompts = []
# for idx, common_index in enumerate(common_indices):
    
#     if common_index in invalid_pairs_indices_set:
#         continue

#     # ---------- collect the data we need for this pair ----------
#     captions1      = compound_stem_caption_list[common_index][0]
#     captions2      = compound_stem_caption_list[common_index][1]
#     curr_questions = compound_questions_response[idx]
#     curr_answers   = compound_answers_response[idx]

#     # ---------- build the message list after the assignments ----------
#     messages = [
#         {   # 1) System role
#             "role": "developer",
#             "content": (
#                 prompt
#             )
            
#         },
#         {   # 2) User role
#             "role": "user",
#             "content": f"""\
# ### PATIENT-CONTEXT QUERIES & ANSWERS
# {curr_questions}

# {curr_answers}

# ### IMAGE CAPTIONS (MULTIPLE PAIRS)
# {captions1}

# {captions2}
# """
#         }
#     ]

#     prompts.append(messages)


prompts = []
for idx, common_index in enumerate(common_indices):
    
    if common_index in invalid_pairs_indices_set:
        continue

    # ---------- collect the data we need for this pair ----------
    captions1      = compound_stem_caption_list[common_index][0]
    captions2      = compound_stem_caption_list[common_index][1]
    curr_questions = compound_questions_response[idx]
    curr_answers   = compound_answers_response[idx]

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


print(len(prompts))

# --- cell 112 (compound labeling)
# with open(os.path.join(jsons_path, 'compound_batch_reqs/compound_positives_req.jsonl'), "w", encoding="utf-8") as f:
#     for i, messages in enumerate(prompts, start=1):
#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/chat/completions",
#             "body": {
#                 "model": "gpt-5-mini", 
#                 "messages": messages
#             }
#         }

#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# --- cell 113 (compound labeling)
# positives_request_file = client.files.create(
#   file=open(os.path.join(jsons_path, 'compound_batch_reqs/compound_positives_req.jsonl'), "rb"),
#   purpose="batch"
# )

# batch = client.batches.create(
#     input_file_id=positives_request_file.id,
#     endpoint="/v1/chat/completions",
#     completion_window="24h",
#     metadata={"description": "Compound Positive Image Pairs"},
# )

# --- cell 117 (compound labeling)
file_response = client.files.content("<OPENAI_ID>")
file_response_text = file_response.text 

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

compound_pairs = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 118 (compound labeling)
# with open(os.path.join(jsons_path, 'compound_batch_resps/compound_pairs.jsonl'), 'w') as f:
#     json.dump(compound_pairs, f)

with open(os.path.join(jsons_path, 'compound_batch_resps/compound_pairs.jsonl'), 'r') as f:
    compound_pairs = json.load(f)

# --- cell 131 (relabel requests)
### Re-running Positive Pairs on the old pairs ###

from pathlib import Path


with open(jsons_path + "/diagrams_compound_filtered_paths_list.json", 'r') as f:
    diagrams_filtered_paths_list = json.load(f)

# diagrams_filtered_paths_list = list(new_df['image_path'])
# prefix = '<DATA_ROOT>/data2'
# diagrams_filtered_paths_list = [os.path.join(prefix, suffix) for suffix in diagrams_filtered_paths_list]

with open(jsons_path + '/generated_questions.json', 'r') as f:
    generated_questions = json.load(f)

with open(jsons_path + '/generated_answers.json', 'r') as f:
    generated_answers = json.load(f)

with open(os.path.join(jsons_path, "common_indices.json"), "r") as f:
    common_indices = json.load(f)
    
diagrams_filtered_stems = [Path(p).stem for p in diagrams_filtered_paths_list]

diagrams_filtered_stems_set = set(diagrams_filtered_stems)

with open(os.path.join(jsons_path, 'pairs_text.json'), 'r') as f:
    pairs_text = json.load(f)

with open(os.path.join(jsons_path, 'stems_3d.json'), 'r') as f:
    stems_3d = json.load(f)

stem_caption_list = build_stem_caption_3d(pairs_text, stems_3d)

filtered_stem_caption_list = [
    [
        {k: v for k, v in d.items() if k in diagrams_filtered_stems_set}      # keep only wanted keys
        for d in inner                                   # loop over inner dicts
        if any(k in diagrams_filtered_stems_set for k in d)                  # …and drop empty dicts
    ]
    for inner in stem_caption_list                       # loop over outer groups
]



invalid_pairs_indices = [i for i, inner in enumerate(filtered_stem_caption_list) if len(inner) < 2]
invalid_pairs_indices_set = set(invalid_pairs_indices)

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

# --- cell 135 (relabel requests)
# with open(os.path.join(jsons_path, 'compound_batch_reqs/new_positives_req.jsonl'), "w", encoding="utf-8") as f:
#     for i, messages in enumerate(prompts, start=1):
#         request_obj = {
#             "custom_id": f"request-{i}",
#             "method": "POST",
#             "url": "/v1/chat/completions",
#             "body": {
#                 "model": "gpt-5-mini", 
#                 "messages": messages
#             }
#         }

#         f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

# positives_request_file = client.files.create(
#   file=open(os.path.join(jsons_path, 'compound_batch_reqs/new_positives_req.jsonl'), "rb"),
#   purpose="batch"
# )

# batch = client.batches.create(
#     input_file_id=positives_request_file.id,
#     endpoint="/v1/chat/completions",
#     completion_window="24h",
#     metadata={"description": "New Positive Image Pairs"},
# )

# --- cell 140 (relabel requests)
file_response = client.files.content("<OPENAI_ID>")
file_response_text = file_response.text 

json_strings = file_response_text.strip().splitlines()

# Parse each JSON string into a dictionary and store in a list
response_dicts = [json.loads(line) for line in json_strings]

new_pairs = [response_dicts[i]['response']['body']['choices'][0]['message']['content'] for i in range(len(response_dicts))]

# --- cell 142 (post-processing)
### Combine new pairs with the previously generated compound pairs ###

import json
import re
import ast
import os
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------
# Config
# --------------------------------------------------

RADIOLOGY_PATH = "<DATA_ROOT>/radiology_pairs_combined.json"

# Match previous notebook behavior:
# False  -> ['a','b'] and ['b','a'] are considered different pairs
# True   -> they are considered the same pair for dedupe/merge
ORDER_INSENSITIVE_DEDUPE = False

OUT_DIR = os.path.dirname(RADIOLOGY_PATH)
NEW_LABELED_PATH = os.path.join(OUT_DIR, "new_radiology_labeled_pairs.json")
NEW_CLEAN_PATH   = os.path.join(OUT_DIR, "new_radiology_pairs_clean.json")
NEW_ONLY_PATH    = os.path.join(OUT_DIR, "new_radiology_pairs_only_to_add.json")
MERGED_PATH      = os.path.join(OUT_DIR, "radiology_pairs_combined_merged.json")
BAD_PATH         = os.path.join(OUT_DIR, "new_pairs_bad_rows.json")

# --------------------------------------------------
# Helpers
# --------------------------------------------------

_PAIR_ID_CLEAN_RE = re.compile(r"[^0-9_,]")

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def parse_model_item_to_dict(x: Any) -> Optional[Dict[str, Any]]:
    """
    Accepts:
      - dict
      - JSON string
      - string containing JSON inside fences / surrounding text
      - python-literal dict string with single quotes
    Returns dict or None.
    """
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if not isinstance(x, str):
        return None

    s = _strip_code_fences(x)
    if not s:
        return None

    if s == "{}":
        return {}

    # strict JSON
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # try first {...} block
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = s[first:last+1]

        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

        try:
            obj = ast.literal_eval(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    # last try: literal eval on full string
    try:
        obj = ast.literal_eval(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def normalize_pair_id(pair_id_val: Any) -> Optional[List[str]]:
    """
    Keeps only digits, '_' and ',' from the input,
    then splits on comma. Returns [id1, id2] or None.
    """
    if pair_id_val is None:
        return None

    if isinstance(pair_id_val, (list, tuple)):
        s = ",".join(str(x) for x in pair_id_val)
    else:
        s = str(pair_id_val)

    cleaned = _PAIR_ID_CLEAN_RE.sub("", s)
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

def modality_bucket(modality: str) -> str:
    m = (modality or "").strip().lower()

    radiology_keywords = [
        "ct", "computed tomography", "mri", "magnetic resonance",
        "radiograph", "x-ray", "xray", "ultrasound", "sonograph", "sonography",
        "pet", "spect", "angiograph", "angiography", "fluoroscopy",
        "mammograph", "mammography", "tomograph", "tomography",
    ]
    pathology_keywords = [
        "histolog", "patholog", "microscop", "immunohistochem", "ihc",
        "hematoxylin", "eosin", "h&e", "stain", "biopsy", "slide",
    ]
    ophtho_keywords = [
        "fundus", "oct", "optical coherence", "slit lamp",
        "fluorescein", "indocyanine", "retinal", "ophthalm",
    ]
    endoscopy_keywords = [
        "endoscop", "colonoscopy", "gastroscopy", "bronchoscopy",
        "laparoscopy", "hysteroscopy", "arthroscopy",
    ]
    cardiology_keywords = [
        "ecg", "ekg", "electrocardi", "echocardi", "echo",
    ]

    if any(k in m for k in radiology_keywords):
        return "radiology"
    if any(k in m for k in pathology_keywords):
        return "pathology_microscopy"
    if any(k in m for k in ophtho_keywords):
        return "ophthalmology"
    if any(k in m for k in endoscopy_keywords):
        return "endoscopy"
    if any(k in m for k in cardiology_keywords):
        return "cardiology"
    return "other"

def pair_key(pid: List[str], order_insensitive: bool = False) -> Tuple[str, str]:
    return tuple(sorted(pid)) if order_insensitive else tuple(pid)

def load_jsonish_file(path: str) -> Any:
    """
    Loads either valid JSON or a Python-literal file
    like [['a','b'], ['c','d']].
    """
    with open(path, "r") as f:
        s = f.read()

    s = _strip_code_fences(s)

    try:
        return json.loads(s)
    except Exception:
        pass

    try:
        return ast.literal_eval(s)
    except Exception as e:
        raise ValueError(f"Could not parse file: {path}") from e

def clean_pair_list(raw_pairs: Any, order_insensitive: bool = False) -> Tuple[List[List[str]], List[Dict[str, Any]]]:
    """
    Cleans a list like:
      [['<IMAGE_ID>', '<IMAGE_ID>'], ...]
    and dedupes it.
    """
    if not isinstance(raw_pairs, list):
        raise ValueError("Expected a list of pairs")

    clean = []
    bad = []
    seen = set()

    for idx, item in enumerate(raw_pairs):
        candidate = item.get("pair_id") if isinstance(item, dict) else item
        pid = normalize_pair_id(candidate)

        if not pid or len(pid) != 2:
            bad.append({
                "idx": idx,
                "reason": "bad_pair_id_in_existing_file",
                "raw": item
            })
            continue

        k = pair_key(pid, order_insensitive=order_insensitive)
        if k in seen:
            continue

        seen.add(k)
        clean.append(pid)

    return clean, bad

def process_new_radiology_pairs(
    new_pairs: List[Any],
    order_insensitive: bool = False,
) -> Tuple[List[Dict[str, Any]], List[List[str]], List[Dict[str, Any]], int]:
    """
    Parses Batch API outputs, keeps only radiology, normalizes pair_id, dedupes.
    Returns:
      - labeled radiology records
      - clean radiology pair list
      - bad rows diagnostics
      - count skipped because non-radiology
    """
    labeled = []
    pairs_clean = []
    bad = []
    skipped_non_radiology = 0
    seen = set()

    for idx, raw in enumerate(new_pairs):
        obj = parse_model_item_to_dict(raw)

        if obj is None:
            bad.append({
                "idx": idx,
                "reason": "unparseable",
                "raw_preview": str(raw)[:300]
            })
            continue

        if obj == {}:
            # model returned empty object
            continue

        pid = normalize_pair_id(obj.get("pair_id"))
        if not pid or len(pid) != 2:
            bad.append({
                "idx": idx,
                "reason": "bad_pair_id",
                "pair_id": obj.get("pair_id"),
                "raw_preview": str(raw)[:300]
            })
            continue

        if modality_bucket(str(obj.get("modality", ""))) != "radiology":
            skipped_non_radiology += 1
            continue

        k = pair_key(pid, order_insensitive=order_insensitive)
        if k in seen:
            continue

        seen.add(k)

        obj = dict(obj)
        obj["pair_id"] = pid

        labeled.append(obj)
        pairs_clean.append(pid)

    return labeled, pairs_clean, bad, skipped_non_radiology

# --------------------------------------------------
# Main
# --------------------------------------------------

# Assumes `new_pairs` already exists in memory
# new_pairs = [response_dicts[i]['response']['body']['choices'][0]['message']['content']
#              for i in range(len(response_dicts))]

# 1) Load and clean the existing radiology pairs file
radiology_pairs_combined_raw = load_jsonish_file(RADIOLOGY_PATH)
radiology_pairs_combined, radiology_pairs_combined_bad = clean_pair_list(
    radiology_pairs_combined_raw,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
)

# 2) Parse the Batch API outputs, keep only radiology
new_radiology_labeled_pairs, new_radiology_pairs_clean, new_pairs_bad, skipped_non_radiology = process_new_radiology_pairs(
    new_pairs,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
)

# 3) Keep only truly new pairs to add
existing_seen = {pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE) for pid in radiology_pairs_combined}

new_radiology_pairs_only_to_add = []
for pid in new_radiology_pairs_clean:
    k = pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE)
    if k not in existing_seen:
        existing_seen.add(k)
        new_radiology_pairs_only_to_add.append(pid)

# 4) Merge old + new without repetitions
radiology_pairs_combined_merged = radiology_pairs_combined + new_radiology_pairs_only_to_add

# --------------------------------------------------
# Save outputs as valid JSON
# --------------------------------------------------

with open(NEW_LABELED_PATH, "w") as f:
    json.dump(new_radiology_labeled_pairs, f, indent=2)

with open(NEW_CLEAN_PATH, "w") as f:
    json.dump(new_radiology_pairs_clean, f, indent=2)

with open(NEW_ONLY_PATH, "w") as f:
    json.dump(new_radiology_pairs_only_to_add, f, indent=2)

with open(MERGED_PATH, "w") as f:
    json.dump(radiology_pairs_combined_merged, f, indent=2)

with open(BAD_PATH, "w") as f:
    json.dump({
        "new_pairs_bad_rows": new_pairs_bad,
        "existing_radiology_pairs_bad_rows": radiology_pairs_combined_bad,
    }, f, indent=2)

# --------------------------------------------------
# Summary
# --------------------------------------------------

print("Existing radiology pairs loaded:", len(radiology_pairs_combined))
print("New radiology labeled pairs:", len(new_radiology_labeled_pairs))
print("New radiology clean pairs:", len(new_radiology_pairs_clean))
print("New radiology pairs actually added:", len(new_radiology_pairs_only_to_add))
print("Merged radiology pairs total:", len(radiology_pairs_combined_merged))
print("Skipped non-radiology rows from new_pairs:", skipped_non_radiology)
print("Bad/unparseable rows in new_pairs:", len(new_pairs_bad))
print("Bad rows in existing radiology file:", len(radiology_pairs_combined_bad))
print("Saved:")
print(" -", NEW_LABELED_PATH)
print(" -", NEW_CLEAN_PATH)
print(" -", NEW_ONLY_PATH)
print(" -", MERGED_PATH)
print(" -", BAD_PATH)

# --- cell 145 (post-processing; relabel pass recovery and unordered dedup)
### Recover missing radiology pairs from new_pairs and merge with aligned texts ###

import json
import re
import ast
import os
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------
# Config
# --------------------------------------------------

RADIOLOGY_PATH = "<DATA_ROOT>/radiology_pairs_combined.json"
RADIOLOGY_TEXTS_PATH = "<DATA_ROOT>/text_pairs_radiology_combined.json"

# Match previous notebook behavior:
# False  -> ['a','b'] and ['b','a'] are considered different pairs
# True   -> they are considered the same pair for dedupe/merge
ORDER_INSENSITIVE_DEDUPE = False

# IMPORTANT:
# True  -> preserves your OLD bucket behavior exactly
#         (e.g. OCT may count as "radiology" because of "tomography")
# False -> stricter bucket order, where ophthalmology/endoscopy/etc. are checked first
PRESERVE_OLD_RADIOLOGY_BUCKET_BEHAVIOR = True

# Try a conservative regex salvage on rows that still fail robust parsing.
# This can recover some extra pair_ids from malformed outputs.
SALVAGE_REMAINING_BAD_ROWS = True

OUT_DIR = os.path.dirname(RADIOLOGY_PATH)

NEW_LABELED_PATH              = os.path.join(OUT_DIR, "new_radiology_labeled_pairs_recovered.json")
NEW_CLEAN_PATH                = os.path.join(OUT_DIR, "new_radiology_pairs_clean_recovered.json")
NEW_TEXT_PATH                 = os.path.join(OUT_DIR, "new_radiology_text_pairs_recovered.json")

NEW_ONLY_PATH                 = os.path.join(OUT_DIR, "new_radiology_pairs_only_to_add_recovered.json")
NEW_ONLY_TEXT_PATH            = os.path.join(OUT_DIR, "new_radiology_text_pairs_only_to_add_recovered.json")

RECOVERED_VS_OLD_PATH         = os.path.join(OUT_DIR, "new_radiology_pairs_recovered_vs_old_logic.json")
RECOVERED_VS_OLD_TEXT_PATH    = os.path.join(OUT_DIR, "new_radiology_text_pairs_recovered_vs_old_logic.json")
RECOVERED_VS_OLD_LABELED_PATH = os.path.join(OUT_DIR, "new_radiology_labeled_pairs_recovered_vs_old_logic.json")

MERGED_PATH                   = os.path.join(OUT_DIR, "radiology_pairs_combined_merged_recovered.json")
MERGED_TEXT_PATH              = os.path.join(OUT_DIR, "radiology_text_pairs_merged_recovered.json")
MISSING_TEXT_PATH             = os.path.join(OUT_DIR, "radiology_text_pairs_missing_pairs_recovered.json")

BAD_PATH                      = os.path.join(OUT_DIR, "new_radiology_bad_rows_recovered.json")
DIAG_PATH                     = os.path.join(OUT_DIR, "radiology_recovery_diagnostics.json")

# --------------------------------------------------
# Helpers
# --------------------------------------------------

_PAIR_ID_CLEAN_RE = re.compile(r"[^0-9_,]")
_ID_RE = re.compile(r"\d+_\d+_\d+")
_OBJECT_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.S)

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def load_jsonish_file(path: str) -> Any:
    with open(path, "r") as f:
        s = f.read()

    s = _strip_code_fences(s)

    try:
        return json.loads(s)
    except Exception:
        pass

    try:
        return ast.literal_eval(s)
    except Exception as e:
        raise ValueError(f"Could not parse file: {path}") from e

def normalize_pair_id(pair_id_val: Any) -> Optional[List[str]]:
    """
    Keeps only digits, '_' and ',' from the input,
    then splits on comma. Returns [id1, id2] or None.
    """
    if pair_id_val is None:
        return None

    if isinstance(pair_id_val, (list, tuple)):
        s = ",".join(str(x) for x in pair_id_val)
    else:
        s = str(pair_id_val)

    cleaned = _PAIR_ID_CLEAN_RE.sub("", s)
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

def pair_key(pid: List[str], order_insensitive: bool = False) -> Tuple[str, str]:
    return tuple(sorted(pid)) if order_insensitive else (pid[0], pid[1])

def normalize_text_pair_item(x: Any) -> List[str]:
    """
    Normalizes a text_pairs item into list[str].
    Accepts:
      - ["caption"]
      - "caption"
      - []
      - None
    """
    if x is None:
        return []
    if isinstance(x, list):
        return [str(t).strip() for t in x if str(t).strip()]
    s = str(x).strip()
    return [s] if s else []

def build_short_caption_from_record(obj: Dict[str, Any]) -> List[str]:
    diagnosis = str(obj.get("diagnosis", "")).strip()
    anatomy = str(obj.get("anatomy", "")).strip()
    modality = str(obj.get("modality", "")).strip()

    parts = []
    if diagnosis:
        parts.append(diagnosis)
    if anatomy:
        parts.append(f"in the {anatomy}")
    if modality:
        parts.append(f"on {modality}")

    cap = " ".join(parts).strip()
    if cap and not cap.endswith("."):
        cap += "."
    return [cap] if cap else []

def modality_bucket(modality: str, preserve_old_behavior: bool = True) -> str:
    m = (modality or "").strip().lower()

    radiology_keywords = [
        "ct", "computed tomography", "mri", "magnetic resonance",
        "radiograph", "x-ray", "xray", "ultrasound", "sonograph", "sonography",
        "pet", "spect", "angiograph", "angiography", "fluoroscopy",
        "mammograph", "mammography", "tomograph", "tomography",
    ]
    pathology_keywords = [
        "histolog", "patholog", "microscop", "immunohistochem", "ihc",
        "hematoxylin", "eosin", "h&e", "stain", "biopsy", "slide",
    ]
    ophtho_keywords = [
        "fundus", "oct", "optical coherence", "slit lamp",
        "fluorescein", "indocyanine", "retinal", "ophthalm",
    ]
    endoscopy_keywords = [
        "endoscop", "colonoscopy", "gastroscopy", "bronchoscopy",
        "laparoscopy", "hysteroscopy", "arthroscopy",
    ]
    cardiology_keywords = [
        "ecg", "ekg", "electrocardi", "echocardi", "echo",
    ]

    if preserve_old_behavior:
        # This matches your old notebook behavior.
        if any(k in m for k in radiology_keywords):
            return "radiology"
        if any(k in m for k in pathology_keywords):
            return "pathology_microscopy"
        if any(k in m for k in ophtho_keywords):
            return "ophthalmology"
        if any(k in m for k in endoscopy_keywords):
            return "endoscopy"
        if any(k in m for k in cardiology_keywords):
            return "cardiology"
        return "other"

    # Stricter classification: check specialty buckets before generic radiology words like "tomography".
    if any(k in m for k in pathology_keywords):
        return "pathology_microscopy"
    if any(k in m for k in ophtho_keywords):
        return "ophthalmology"
    if any(k in m for k in endoscopy_keywords):
        return "endoscopy"
    if any(k in m for k in cardiology_keywords):
        return "cardiology"
    if any(k in m for k in radiology_keywords):
        return "radiology"
    return "other"

def clean_pair_list_with_texts(
    raw_pairs: Any,
    raw_text_pairs: Any,
    order_insensitive: bool = False,
):
    """
    Cleans/dedupes an existing pair list while keeping text_pairs aligned.
    """
    if not isinstance(raw_pairs, list):
        raise ValueError("raw_pairs must be a list")
    if not isinstance(raw_text_pairs, list):
        raise ValueError("raw_text_pairs must be a list")
    if len(raw_pairs) != len(raw_text_pairs):
        raise ValueError(
            f"Length mismatch: raw_pairs has {len(raw_pairs)} items, "
            f"raw_text_pairs has {len(raw_text_pairs)} items"
        )

    clean_pairs = []
    clean_texts = []
    bad = []
    seen = set()

    for idx, (pair_item, text_item) in enumerate(zip(raw_pairs, raw_text_pairs)):
        candidate = pair_item.get("pair_id") if isinstance(pair_item, dict) else pair_item
        pid = normalize_pair_id(candidate)

        if not pid or len(pid) != 2:
            bad.append({
                "idx": idx,
                "reason": "bad_pair_id_in_existing_pairs_with_texts",
                "raw_pair": pair_item,
            })
            continue

        k = pair_key(pid, order_insensitive=order_insensitive)
        if k in seen:
            continue

        seen.add(k)
        clean_pairs.append(pid)
        clean_texts.append(normalize_text_pair_item(text_item))

    return clean_pairs, clean_texts, bad

def merge_pairs_and_texts(
    base_pairs: List[List[str]],
    base_texts: List[Any],
    add_pairs: List[List[str]],
    add_texts: List[Any],
    *,
    order_insensitive: bool = False,
):
    """
    Merges while preserving exact pair/text alignment.
    If a pair already exists and its old text is empty, fill it from the new text.
    """
    if len(base_pairs) != len(base_texts):
        raise ValueError("base_pairs and base_texts must have the same length")
    if len(add_pairs) != len(add_texts):
        raise ValueError("add_pairs and add_texts must have the same length")

    merged_pairs = [list(pid) for pid in base_pairs]
    merged_texts = [normalize_text_pair_item(t) for t in base_texts]

    index = {
        pair_key(pid, order_insensitive=order_insensitive): i
        for i, pid in enumerate(merged_pairs)
    }

    added_count = 0
    filled_missing_text_count = 0
    conflicting_nonempty_text_count = 0
    conflicts_preview = []

    for pid, txt in zip(add_pairs, add_texts):
        txt_norm = normalize_text_pair_item(txt)
        k = pair_key(pid, order_insensitive=order_insensitive)

        if k in index:
            i = index[k]
            if (not merged_texts[i]) and txt_norm:
                merged_texts[i] = txt_norm
                filled_missing_text_count += 1
            elif merged_texts[i] and txt_norm and merged_texts[i] != txt_norm:
                conflicting_nonempty_text_count += 1
                if len(conflicts_preview) < 50:
                    conflicts_preview.append({
                        "pair_id": pid,
                        "existing_text": merged_texts[i],
                        "incoming_text": txt_norm,
                    })
        else:
            index[k] = len(merged_pairs)
            merged_pairs.append(list(pid))
            merged_texts.append(txt_norm)
            added_count += 1

    return merged_pairs, merged_texts, {
        "added_count": added_count,
        "filled_missing_text_count": filled_missing_text_count,
        "conflicting_nonempty_text_count": conflicting_nonempty_text_count,
        "conflicts_preview": conflicts_preview,
    }

# --------------------------------------------------
# Legacy parser (your old behavior) for comparison
# --------------------------------------------------

def parse_model_item_to_dict_legacy(x: Any) -> Optional[Dict[str, Any]]:
    """
    Your old behavior:
      - accepts dict
      - accepts string that parses to dict
      - rejects list-of-dicts
    """
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if not isinstance(x, str):
        return None

    s = _strip_code_fences(x)
    if not s:
        return None

    if s == "{}":
        return {}

    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = s[first:last+1]

        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

        try:
            obj = ast.literal_eval(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    try:
        obj = ast.literal_eval(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def process_new_radiology_pairs_legacy_like(
    new_pairs: List[Any],
    order_insensitive: bool = False,
    preserve_old_bucket_behavior: bool = True,
):
    labeled = []
    pairs_clean = []
    text_pairs = []
    bad = []
    skipped_non_radiology = 0
    seen = set()

    for idx, raw in enumerate(new_pairs):
        obj = parse_model_item_to_dict_legacy(raw)

        if obj is None:
            bad.append({
                "idx": idx,
                "reason": "unparseable",
                "raw_preview": str(raw)[:300],
            })
            continue

        if obj == {}:
            continue

        pid = normalize_pair_id(obj.get("pair_id"))
        if not pid or len(pid) != 2:
            bad.append({
                "idx": idx,
                "reason": "bad_pair_id",
                "pair_id": obj.get("pair_id"),
                "raw_preview": str(raw)[:300],
            })
            continue

        if modality_bucket(
            str(obj.get("modality", "")),
            preserve_old_behavior=preserve_old_bucket_behavior,
        ) != "radiology":
            skipped_non_radiology += 1
            continue

        k = pair_key(pid, order_insensitive=order_insensitive)
        if k in seen:
            continue

        seen.add(k)

        obj2 = dict(obj)
        obj2["pair_id"] = pid

        labeled.append(obj2)
        pairs_clean.append(pid)
        text_pairs.append(build_short_caption_from_record(obj2))

    return labeled, pairs_clean, text_pairs, bad, skipped_non_radiology

# --------------------------------------------------
# Robust parsing helpers
# --------------------------------------------------

def _parse_jsonish_obj(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None

    s = _strip_code_fences(raw)
    if not s:
        return None

    candidates = [s]

    first_arr = s.find("[")
    last_arr = s.rfind("]")
    if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
        candidates.append(s[first_arr:last_arr + 1])

    first_obj = s.find("{")
    last_obj = s.rfind("}")
    if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
        candidates.append(s[first_obj:last_obj + 1])

    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)

        try:
            return json.loads(cand)
        except Exception:
            pass

        try:
            return ast.literal_eval(cand)
        except Exception:
            pass

    return None

def _flatten_dict_records(obj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def _rec(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, dict):
            if x != {}:
                out.append(x)
            return
        if isinstance(x, list):
            for item in x:
                _rec(item)

    _rec(obj)
    return out

def parse_jsonish_to_records(raw: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Returns:
      None -> unparseable
      []   -> parseable but empty / {}
      [...] -> one or more dict records
    """
    obj = _parse_jsonish_obj(raw)
    if obj is None:
        return None
    return _flatten_dict_records(obj)

# --------------------------------------------------
# Conservative salvage for remaining bad rows
# --------------------------------------------------

def _extract_field_from_text(s: str, field: str) -> Optional[str]:
    patterns = [
        rf'"{re.escape(field)}"\s*:\s*"([^"]*)"',
        rf"'{re.escape(field)}'\s*:\s*'([^']*)'",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.S)
        if m:
            return m.group(1).strip()
    return None

def salvage_records_from_raw_text(raw: Any) -> List[Dict[str, Any]]:
    """
    Conservative salvage:
      - split into flat {...} blocks if possible
      - recover pair_id and any modality/anatomy/diagnosis fields we can find
    """
    s = _strip_code_fences(str(raw))
    if not s:
        return []

    candidate_blocks = _OBJECT_BLOCK_RE.findall(s)
    if not candidate_blocks:
        candidate_blocks = [s]

    recovered = []
    seen = set()

    for block in candidate_blocks:
        obj = _parse_jsonish_obj(block)
        if isinstance(obj, dict) and obj:
            pid = normalize_pair_id(obj.get("pair_id"))
            if pid and len(pid) == 2:
                obj2 = dict(obj)
                obj2["pair_id"] = pid
                k = tuple(pid)
                if k not in seen:
                    seen.add(k)
                    recovered.append(obj2)
                continue

        pair_val = _extract_field_from_text(block, "pair_id")
        pid = normalize_pair_id(pair_val)

        if (not pid or len(pid) != 2):
            ids = _ID_RE.findall(block)
            if len(ids) >= 2:
                pid = [ids[0], ids[1]]

        if not pid or len(pid) != 2:
            continue

        rec = {
            "pair_id": pid,
            "modality": _extract_field_from_text(block, "modality") or "",
            "anatomy": _extract_field_from_text(block, "anatomy") or "",
            "diagnosis": _extract_field_from_text(block, "diagnosis") or "",
            "reasoning": _extract_field_from_text(block, "reasoning") or "",
        }

        k = tuple(pid)
        if k not in seen:
            seen.add(k)
            recovered.append(rec)

    return recovered

# --------------------------------------------------
# Robust radiology processor
# --------------------------------------------------

def process_new_radiology_pairs_robust(
    new_pairs: List[Any],
    order_insensitive: bool = False,
    preserve_old_bucket_behavior: bool = True,
    salvage_remaining_bad_rows: bool = True,
):
    """
    Parses Batch API outputs, keeps only radiology, handles:
      - dict
      - JSON dict string
      - JSON list-of-dicts string
      - python-literal versions of the above
    Returns aligned:
      - labeled radiology records
      - clean radiology pair list
      - radiology text_pairs
      - remaining bad rows diagnostics
      - skipped_non_radiology_records
      - raw_empty_items
      - multi_record_raw_items
      - regex_salvaged_kept_records
    """
    labeled = []
    pairs_clean = []
    text_pairs = []
    bad = []

    skipped_non_radiology_records = 0
    raw_empty_items = 0
    multi_record_raw_items = 0
    regex_salvaged_kept_records = 0

    seen = set()

    for idx, raw in enumerate(new_pairs):
        records = parse_jsonish_to_records(raw)
        source_type = "parsed"

        if records is None or len(records) == 0:
            if salvage_remaining_bad_rows:
                salvaged = salvage_records_from_raw_text(raw)
                if salvaged:
                    records = salvaged
                    source_type = "regex_salvaged"

        if records is None:
            bad.append({
                "idx": idx,
                "reason": "unparseable",
                "raw_preview": str(raw)[:500],
            })
            continue

        if len(records) == 0:
            raw_empty_items += 1
            continue

        if len(records) > 1:
            multi_record_raw_items += 1

        for subidx, obj in enumerate(records):
            pid = normalize_pair_id(obj.get("pair_id"))
            if not pid or len(pid) != 2:
                bad.append({
                    "idx": idx,
                    "subidx": subidx,
                    "reason": "bad_pair_id",
                    "pair_id": obj.get("pair_id"),
                    "raw_preview": str(raw)[:500],
                    "source_type": source_type,
                })
                continue

            if modality_bucket(
                str(obj.get("modality", "")),
                preserve_old_behavior=preserve_old_bucket_behavior,
            ) != "radiology":
                skipped_non_radiology_records += 1
                continue

            k = pair_key(pid, order_insensitive=order_insensitive)
            if k in seen:
                continue

            seen.add(k)

            obj2 = dict(obj)
            obj2["pair_id"] = pid

            labeled.append(obj2)
            pairs_clean.append(pid)
            text_pairs.append(build_short_caption_from_record(obj2))

            if source_type == "regex_salvaged":
                regex_salvaged_kept_records += 1

    return (
        labeled,
        pairs_clean,
        text_pairs,
        bad,
        skipped_non_radiology_records,
        raw_empty_items,
        multi_record_raw_items,
        regex_salvaged_kept_records,
    )

# --------------------------------------------------
# Main
# --------------------------------------------------

# Assumes `new_pairs` already exists in memory
if "new_pairs" not in globals():
    raise ValueError("new_pairs must already exist in memory")

# Existing aligned radiology baseline
radiology_pairs_combined_raw = load_jsonish_file(RADIOLOGY_PATH)

if "text_pairs_radiology_combined" in globals():
    radiology_text_pairs_combined_raw = text_pairs_radiology_combined
else:
    radiology_text_pairs_combined_raw = load_jsonish_file(RADIOLOGY_TEXTS_PATH)

radiology_pairs_combined, radiology_text_pairs_combined, existing_radiology_bad = clean_pair_list_with_texts(
    radiology_pairs_combined_raw,
    radiology_text_pairs_combined_raw,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
)

# 1) Recompute your OLD logic for comparison
legacy_labeled, legacy_pairs_clean, legacy_text_pairs, legacy_bad, legacy_skipped_non_radiology = process_new_radiology_pairs_legacy_like(
    new_pairs,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
    preserve_old_bucket_behavior=PRESERVE_OLD_RADIOLOGY_BUCKET_BEHAVIOR,
)

# 2) Robust recovery pass
(
    new_radiology_labeled_pairs,
    new_radiology_pairs_clean,
    new_radiology_text_pairs,
    new_pairs_bad,
    skipped_non_radiology_records,
    raw_empty_items,
    multi_record_raw_items,
    regex_salvaged_kept_records,
) = process_new_radiology_pairs_robust(
    new_pairs,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
    preserve_old_bucket_behavior=PRESERVE_OLD_RADIOLOGY_BUCKET_BEHAVIOR,
    salvage_remaining_bad_rows=SALVAGE_REMAINING_BAD_ROWS,
)

# 3) Which radiology pairs were recovered vs your old logic?
legacy_seen = {pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE) for pid in legacy_pairs_clean}
recovered_vs_old_pairs = []
recovered_vs_old_texts = []
recovered_vs_old_labeled = []

for rec, pid, txt in zip(new_radiology_labeled_pairs, new_radiology_pairs_clean, new_radiology_text_pairs):
    k = pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE)
    if k not in legacy_seen:
        recovered_vs_old_labeled.append(rec)
        recovered_vs_old_pairs.append(pid)
        recovered_vs_old_texts.append(txt)

# 4) Keep only truly new radiology pairs to add on top of existing baseline
existing_seen = {pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE) for pid in radiology_pairs_combined}
new_radiology_pairs_only_to_add = []
new_radiology_text_pairs_only_to_add = []

for pid, txt in zip(new_radiology_pairs_clean, new_radiology_text_pairs):
    k = pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE)
    if k not in existing_seen:
        existing_seen.add(k)
        new_radiology_pairs_only_to_add.append(pid)
        new_radiology_text_pairs_only_to_add.append(txt)

# 5) Merge old + recovered-new while keeping texts aligned
radiology_pairs_combined_merged, radiology_text_pairs_merged, merge_stats = merge_pairs_and_texts(
    radiology_pairs_combined,
    radiology_text_pairs_combined,
    new_radiology_pairs_clean,
    new_radiology_text_pairs,
    order_insensitive=ORDER_INSENSITIVE_DEDUPE,
)

assert len(radiology_pairs_combined_merged) == len(radiology_text_pairs_merged), (
    f"Alignment error: "
    f"{len(radiology_pairs_combined_merged)} merged pairs vs "
    f"{len(radiology_text_pairs_merged)} merged texts"
)

missing_text_pairs = [
    pid
    for pid, txt in zip(radiology_pairs_combined_merged, radiology_text_pairs_merged)
    if not normalize_text_pair_item(txt)
]

# --------------------------------------------------
# Save outputs
# --------------------------------------------------

with open(NEW_LABELED_PATH, "w") as f:
    json.dump(new_radiology_labeled_pairs, f, indent=2)

with open(NEW_CLEAN_PATH, "w") as f:
    json.dump(new_radiology_pairs_clean, f, indent=2)

with open(NEW_TEXT_PATH, "w") as f:
    json.dump(new_radiology_text_pairs, f, indent=2)

with open(NEW_ONLY_PATH, "w") as f:
    json.dump(new_radiology_pairs_only_to_add, f, indent=2)

with open(NEW_ONLY_TEXT_PATH, "w") as f:
    json.dump(new_radiology_text_pairs_only_to_add, f, indent=2)

with open(RECOVERED_VS_OLD_PATH, "w") as f:
    json.dump(recovered_vs_old_pairs, f, indent=2)

with open(RECOVERED_VS_OLD_TEXT_PATH, "w") as f:
    json.dump(recovered_vs_old_texts, f, indent=2)

with open(RECOVERED_VS_OLD_LABELED_PATH, "w") as f:
    json.dump(recovered_vs_old_labeled, f, indent=2)

with open(MERGED_PATH, "w") as f:
    json.dump(radiology_pairs_combined_merged, f, indent=2)

with open(MERGED_TEXT_PATH, "w") as f:
    json.dump(radiology_text_pairs_merged, f, indent=2)

with open(MISSING_TEXT_PATH, "w") as f:
    json.dump(missing_text_pairs, f, indent=2)

with open(BAD_PATH, "w") as f:
    json.dump({
        "remaining_bad_rows_after_recovery": new_pairs_bad,
        "legacy_bad_rows": legacy_bad,
        "existing_radiology_pairs_bad_rows": existing_radiology_bad,
    }, f, indent=2)

with open(DIAG_PATH, "w") as f:
    json.dump({
        "order_insensitive_dedupe": ORDER_INSENSITIVE_DEDUPE,
        "preserve_old_radiology_bucket_behavior": PRESERVE_OLD_RADIOLOGY_BUCKET_BEHAVIOR,
        "salvage_remaining_bad_rows": SALVAGE_REMAINING_BAD_ROWS,

        "existing_radiology_pairs_loaded": len(radiology_pairs_combined),
        "existing_radiology_texts_loaded": len(radiology_text_pairs_combined),

        "legacy_radiology_pairs_from_new_pairs": len(legacy_pairs_clean),
        "legacy_skipped_non_radiology_rows": legacy_skipped_non_radiology,
        "legacy_bad_rows": len(legacy_bad),

        "recovered_radiology_pairs_from_new_pairs": len(new_radiology_pairs_clean),
        "recovered_radiology_text_pairs_from_new_pairs": len(new_radiology_text_pairs),
        "recovered_vs_old_logic_count": len(recovered_vs_old_pairs),

        "new_radiology_pairs_actually_added": len(new_radiology_pairs_only_to_add),
        "merged_radiology_pairs_total": len(radiology_pairs_combined_merged),
        "merged_radiology_text_pairs_total": len(radiology_text_pairs_merged),

        "skipped_non_radiology_records_after_robust_parsing": skipped_non_radiology_records,
        "raw_empty_items": raw_empty_items,
        "raw_items_with_multiple_records": multi_record_raw_items,
        "regex_salvaged_kept_records": regex_salvaged_kept_records,
        "remaining_bad_rows_after_recovery": len(new_pairs_bad),
        "existing_radiology_bad_rows": len(existing_radiology_bad),

        "missing_text_pairs_count": len(missing_text_pairs),

        "merge_stats": merge_stats,
    }, f, indent=2)

# --------------------------------------------------
# Summary
# --------------------------------------------------

print("Existing radiology pairs loaded:", len(radiology_pairs_combined))
print("Existing radiology text pairs loaded:", len(radiology_text_pairs_combined))
print()

print("OLD logic radiology pairs from new_pairs:", len(legacy_pairs_clean))
print("ROBUST recovered radiology pairs from new_pairs:", len(new_radiology_pairs_clean))
print("Extra radiology pairs recovered vs old logic:", len(recovered_vs_old_pairs))
print()

print("New radiology pairs actually added:", len(new_radiology_pairs_only_to_add))
print("Merged radiology pairs total:", len(radiology_pairs_combined_merged))
print("Merged radiology texts total:", len(radiology_text_pairs_merged))
print("Missing text pairs after merge:", len(missing_text_pairs))
print()

print("Skipped non-radiology rows under OLD logic:", legacy_skipped_non_radiology)
print("Skipped non-radiology records under ROBUST logic:", skipped_non_radiology_records)
print("Raw empty items:", raw_empty_items)
print("Raw items with multiple records:", multi_record_raw_items)
print("Regex-salvaged kept records:", regex_salvaged_kept_records)
print("Remaining bad rows after recovery:", len(new_pairs_bad))
print("Bad rows in existing radiology baseline:", len(existing_radiology_bad))
print()

print("Saved:")
print(" -", NEW_LABELED_PATH)
print(" -", NEW_CLEAN_PATH)
print(" -", NEW_TEXT_PATH)
print(" -", NEW_ONLY_PATH)
print(" -", NEW_ONLY_TEXT_PATH)
print(" -", RECOVERED_VS_OLD_PATH)
print(" -", RECOVERED_VS_OLD_TEXT_PATH)
print(" -", RECOVERED_VS_OLD_LABELED_PATH)
print(" -", MERGED_PATH)
print(" -", MERGED_TEXT_PATH)
print(" -", MISSING_TEXT_PATH)
print(" -", BAD_PATH)
print(" -", DIAG_PATH)

# --- cell 146 (post-processing)
def unordered_key(pid):
    return tuple(sorted(pid))

def count_unordered_dupes(pairs):
    total = len(pairs)
    uniq_unordered = len({unordered_key(pid) for pid in pairs})
    return {
        "total": total,
        "unique_unordered": uniq_unordered,
        "unordered_duplicates": total - uniq_unordered,
    }

print("existing baseline:", count_unordered_dupes(radiology_pairs_combined))
print("new robust radiology:", count_unordered_dupes(new_radiology_pairs_clean))
print("new_only_to_add:", count_unordered_dupes(new_radiology_pairs_only_to_add))
print("merged:", count_unordered_dupes(radiology_pairs_combined_merged))

# --- cell 147 (post-processing)
existing_unordered = {tuple(sorted(pid)) for pid in radiology_pairs_combined}
false_new_due_to_order = [
    pid for pid in new_radiology_pairs_only_to_add
    if tuple(sorted(pid)) in existing_unordered
]

print("False new pairs due only to reversed order:", len(false_new_due_to_order))
print(false_new_due_to_order[:10])

# --- cell 148 (post-processing; relabel pass recovery and unordered dedup)
import json

PAIRS_IN = "<DATA_ROOT>/radiology_pairs_combined_merged_recovered.json"
TEXTS_IN = "<DATA_ROOT>/radiology_text_pairs_merged_recovered.json"

PAIRS_OUT = "<DATA_ROOT>/radiology_pairs_combined_merged_recovered_unordered_dedup.json"
TEXTS_OUT = "<DATA_ROOT>/radiology_text_pairs_merged_recovered_unordered_dedup.json"
CONFLICTS_OUT = "<DATA_ROOT>/radiology_unordered_dedup_conflicts.json"

def normalize_text_pair_item(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [str(t).strip() for t in x if str(t).strip()]
    s = str(x).strip()
    return [s] if s else []

with open(PAIRS_IN, "r") as f:
    pairs = json.load(f)

with open(TEXTS_IN, "r") as f:
    texts = json.load(f)

assert len(pairs) == len(texts), (len(pairs), len(texts))

dedup_pairs = []
dedup_texts = []
index = {}
conflicts = []

for pid, txt in zip(pairs, texts):
    pid = list(pid)
    txt = normalize_text_pair_item(txt)

    key = tuple(sorted(pid))   # unordered dedupe
    canonical_pid = list(key)  # save in canonical sorted order

    if key not in index:
        index[key] = len(dedup_pairs)
        dedup_pairs.append(canonical_pid)
        dedup_texts.append(txt)
    else:
        i = index[key]
        if (not dedup_texts[i]) and txt:
            dedup_texts[i] = txt
        elif dedup_texts[i] and txt and dedup_texts[i] != txt:
            conflicts.append({
                "pair_id_existing": dedup_pairs[i],
                "existing_text": dedup_texts[i],
                "incoming_text": txt,
            })

with open(PAIRS_OUT, "w") as f:
    json.dump(dedup_pairs, f, indent=2)

with open(TEXTS_OUT, "w") as f:
    json.dump(dedup_texts, f, indent=2)

with open(CONFLICTS_OUT, "w") as f:
    json.dump(conflicts, f, indent=2)

print("original pairs:", len(pairs))
print("deduped unordered pairs:", len(dedup_pairs))
print("removed as unordered duplicates:", len(pairs) - len(dedup_pairs))
print("text conflicts:", len(conflicts))
print("saved:", PAIRS_OUT)
print("saved:", TEXTS_OUT)
print("saved:", CONFLICTS_OUT)

# --- cell 174 (post-processing; compound pass: parse, salvage, radiology filter, aligned text)
### Processing the new image-pairs ###

import json
import re
import ast
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

# ---------------------------
# 1) Robust parsing helpers
# ---------------------------

_PAIR_ID_CLEAN_RE = re.compile(r"[^0-9_,]")

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # remove leading ```json / ``` and trailing ```
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def parse_model_item_to_dict(x: Any) -> Optional[Dict[str, Any]]:
    """
    Accepts either:
      - dict (returns as-is)
      - JSON string (tries json.loads)
      - string containing JSON inside fences / surrounding text
      - python-literal dict with single quotes (tries ast.literal_eval)
    Returns dict or None.
    """
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if not isinstance(x, str):
        # unexpected type
        return None

    s = _strip_code_fences(x)
    if not s:
        return None

    # treat exact {} as "no output"
    if s == "{}":
        return {}

    # Try strict JSON first
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # Try extracting the first {...} block
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = s[first:last+1]
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

        # Try python literal eval (handles single quotes)
        try:
            obj = ast.literal_eval(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    # Last try: literal eval on full string
    try:
        obj = ast.literal_eval(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def normalize_pair_id(pair_id_val: Any) -> Optional[List[str]]:
    """
    Replicates your notebook logic:
      cleaned = re.sub(r'[^0-9_,]', '', pair_id)
      parts = cleaned.split(',') filtered
    Returns list[str] or None.
    """
    if pair_id_val is None:
        return None

    # If it's already a list/tuple, join to a string and normalize the same way
    if isinstance(pair_id_val, (list, tuple)):
        s = ",".join(str(x) for x in pair_id_val)
    else:
        s = str(pair_id_val)

    cleaned = _PAIR_ID_CLEAN_RE.sub("", s)  # keep only digits, '_' and ','
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

# ---------------------------
# 2) Modality bucketing
#    (Notebook did not contain the split code, so this recreates it.)
# ---------------------------

def modality_bucket(modality: str) -> str:
    m = (modality or "").strip().lower()

    # Radiology-ish / imaging modalities
    radiology_keywords = [
        "ct", "computed tomography", "mri", "magnetic resonance",
        "radiograph", "x-ray", "xray", "ultrasound", "sonograph", "sonography",
        "pet", "spect", "angiograph", "angiography", "fluoroscopy",
        "mammograph", "mammography", "tomograph", "tomography",
    ]

    pathology_keywords = [
        "histolog", "patholog", "microscop", "immunohistochem", "ihc",
        "hematoxylin", "eosin", "h&e", "stain", "biopsy", "slide",
    ]

    ophtho_keywords = [
        "fundus", "oct", "optical coherence", "slit lamp",
        "fluorescein", "indocyanine", "retinal", "ophthalm",
    ]

    endoscopy_keywords = [
        "endoscop", "colonoscopy", "gastroscopy", "bronchoscopy",
        "laparoscopy", "hysteroscopy", "arthroscopy",
    ]

    cardiology_keywords = [
        "ecg", "ekg", "electrocardi", "echocardi", "echo",
    ]

    if any(k in m for k in radiology_keywords):
        return "radiology"
    if any(k in m for k in pathology_keywords):
        return "pathology_microscopy"
    if any(k in m for k in ophtho_keywords):
        return "ophthalmology"
    if any(k in m for k in endoscopy_keywords):
        return "endoscopy"
    if any(k in m for k in cardiology_keywords):
        return "cardiology"
    return "other"

# ---------------------------
# 3) Main processing function
# ---------------------------

def process_compound_positive_pairs(
    compound_positive_pairs: List[Any],
    base_pairs: Optional[List[List[str]]] = None,
    *,
    allow_swapped_order: bool = False,   # NOTE: your notebook effectively used False
    dedupe: bool = True,
) -> Dict[str, Any]:
    """
    Returns:
      labeled_all: list[dict] (pair_id normalized)
      pairs_clean_all: list[[id1,id2]]
      text_pairs_all: list[list[str]]  (short captions like notebook)
      by_bucket: dict[bucket]->dict with same three lists
      bad: list[dict] diagnostics for items we couldn't parse/keep
    """

    base_set = None
    base_set_swapped = None
    if base_pairs is not None:
        # Convert to tuple set for O(1) membership tests
        base_set = {tuple(p) for p in base_pairs if isinstance(p, (list, tuple)) and len(p) == 2}
        if allow_swapped_order:
            base_set_swapped = { (b,a) for (a,b) in base_set }

    labeled_all: List[Dict[str, Any]] = []
    pairs_clean_all: List[List[str]] = []
    text_pairs_all: List[List[str]] = []
    bad: List[Dict[str, Any]] = []

    seen = set()

    for idx, raw in enumerate(compound_positive_pairs):
        obj = parse_model_item_to_dict(raw)
        if obj is None:
            bad.append({"idx": idx, "reason": "unparseable", "raw_preview": str(raw)[:200]})
            continue

        # skip empty dict outputs
        if obj == {}:
            continue

        pid = normalize_pair_id(obj.get("pair_id"))
        if not pid or len(pid) != 2:
            bad.append({"idx": idx, "reason": "bad_pair_id", "pair_id": obj.get("pair_id")})
            continue

        # Filter to base pairs list (like your notebook)
        pid_t = tuple(pid)
        if base_set is not None:
            ok = (pid_t in base_set) or (allow_swapped_order and base_set_swapped is not None and pid_t in base_set_swapped)
            if not ok:
                bad.append({"idx": idx, "reason": "not_in_base_pairs", "pair_id_norm": pid})
                continue

        # Dedupe by (id1,id2)
        if dedupe:
            if pid_t in seen:
                continue
            seen.add(pid_t)

        # normalize in object
        obj = dict(obj)          # copy
        obj["pair_id"] = pid

        labeled_all.append(obj)
        pairs_clean_all.append(pid)

        # Build the same short caption your notebook created
        modality = str(obj.get("modality", "")).strip()
        anatomy  = str(obj.get("anatomy", "")).strip()
        diagnosis = str(obj.get("diagnosis", "")).strip()

        parts = []
        if diagnosis:
            parts.append(diagnosis)
        if anatomy:
            parts.append(f"in the {anatomy}")
        if modality:
            parts.append(f"on {modality}")

        cap = " ".join(parts).strip()
        if cap and not cap.endswith("."):
            cap += "."
        text_pairs_all.append([cap] if cap else [])

    # Split into buckets
    by_bucket = defaultdict(lambda: {"labeled": [], "pairs_clean": [], "text_pairs": []})
    for rec, pid, caps in zip(labeled_all, pairs_clean_all, text_pairs_all):
        bucket = modality_bucket(rec.get("modality", ""))
        by_bucket[bucket]["labeled"].append(rec)
        by_bucket[bucket]["pairs_clean"].append(pid)
        by_bucket[bucket]["text_pairs"].append(caps)

    return {
        "labeled_all": labeled_all,
        "pairs_clean_all": pairs_clean_all,
        "text_pairs_all": text_pairs_all,
        "by_bucket": dict(by_bucket),
        "bad": bad,
    }

# ---------------------------
# 4) Example usage (edit names as needed)
# ---------------------------

# base_pairs should be whatever you used analogously to `pos_pairs` in the notebook.
# If you already have it in memory, skip loading.
#
# with open("/path/to/pos_pairs.json", "r") as f:
#     base_pairs = json.load(f)

# Run processing:
res = process_compound_positive_pairs(
    compound_positive_pairs=compound_pairs,
    base_pairs=pos_pairs if "pos_pairs" in globals() else None,  # adjust if your base list is named differently
    allow_swapped_order=False,  # match notebook behavior
    dedupe=True,
)

compound_labeled_pos_pairs = res["labeled_all"]
compound_pos_pairs_clean   = res["pairs_clean_all"]
compound_text_pairs        = res["text_pairs_all"]
compound_by_bucket         = res["by_bucket"]
compound_bad               = res["bad"]

print("Kept labeled:", len(compound_labeled_pos_pairs))
print("Kept pairs_clean:", len(compound_pos_pairs_clean))
print("Bad/filtered diagnostics:", len(compound_bad))
print("Bucket sizes:", {k: len(v["labeled"]) for k, v in compound_by_bucket.items()})

# If you want radiology subset like your old radiology_pos_pairs.json:
compound_radiology_pos_pairs = compound_by_bucket.get("radiology", {}).get("labeled", [])
print("Radiology labeled:", len(compound_radiology_pos_pairs))

# Optional: save outputs
# with open("compound_labeled_pos_pairs.json", "w") as f:
#     json.dump(compound_labeled_pos_pairs, f)
# with open("compound_pos_pairs_clean.json", "w") as f:
#     json.dump(compound_pos_pairs_clean, f)
# with open("compound_text_pairs.json", "w") as f:
#     json.dump(compound_text_pairs, f)
# with open("compound_radiology_pos_pairs.json", "w") as f:
#     json.dump(compound_radiology_pos_pairs, f)
# with open("compound_bad_rows.json", "w") as f:
#     json.dump(compound_bad, f)

# --- cell 176 (post-processing; compound pass: parse, salvage, radiology filter, aligned text)
import json
import re
import ast
from typing import Any, Dict, List, Optional, Tuple

_ID_RE = re.compile(r"\d+_\d+_\d+")         # matches ids like <IMAGE_ID>
_KEEP_CHARS_RE = re.compile(r"[^0-9_,]")    # for cleaning pair_id strings

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _normalize_pair_id(val: Any) -> Optional[List[str]]:
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        s = ",".join(str(x) for x in val)
    else:
        s = str(val)
    cleaned = _KEEP_CHARS_RE.sub("", s)
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

def _parse_jsonish_to_records(raw: Any) -> List[Dict[str, Any]]:
    """
    Returns a list of dict records parsed from raw output.
    Handles:
      - dict
      - JSON string -> dict or list[dict]
      - python-literal string -> dict or list[dict]
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        # already a list (unlikely here, but handle)
        return [x for x in raw if isinstance(x, dict)]

    if not isinstance(raw, str):
        return []

    s = _strip_code_fences(raw)
    if not s:
        return []

    # try json.loads directly
    try:
        obj = json.loads(s)
    except Exception:
        obj = None

    # if json failed, try extracting {...} or [...] block
    if obj is None:
        first_brace = min([i for i in [s.find("{"), s.find("[")] if i != -1], default=-1)
        last_brace = max(s.rfind("}"), s.rfind("]"))
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cand = s[first_brace:last_brace+1]
            try:
                obj = json.loads(cand)
            except Exception:
                try:
                    obj = ast.literal_eval(cand)
                except Exception:
                    obj = None
        else:
            # last resort literal eval on whole string
            try:
                obj = ast.literal_eval(s)
            except Exception:
                obj = None

    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []

def salvage_pairs_from_compound_bad(
    compound_positive_pairs: List[Any],
    compound_bad: List[Dict[str, Any]],
    *,
    base_pairs: Optional[List[List[str]]] = None,  # if you want to restrict to candidates
    allow_swapped_order: bool = True,              # if base filtering enabled
) -> Tuple[List[List[str]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns:
      recovered_pairs_clean: list[[id1,id2]]
      recovered_records: list[dict] (with normalized pair_id)
      still_bad: diagnostics that could not yield a valid pair
    """
    base_set = None
    base_set_swapped = None
    if base_pairs is not None:
        base_set = {tuple(p) for p in base_pairs if isinstance(p, (list,tuple)) and len(p) == 2}
        if allow_swapped_order:
            base_set_swapped = {(b,a) for (a,b) in base_set}

    recovered_pairs_clean: List[List[str]] = []
    recovered_records: List[Dict[str, Any]] = []
    still_bad: List[Dict[str, Any]] = []

    seen = set()

    for d in compound_bad:
        idx = d.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < len(compound_positive_pairs)):
            still_bad.append({**d, "reason2": "bad_idx"})
            continue

        raw = compound_positive_pairs[idx]
        recs = _parse_jsonish_to_records(raw)

        # If parsing gave nothing, fallback to regex extraction of IDs
        if not recs:
            if isinstance(raw, str):
                ids = _ID_RE.findall(raw)
                ids = [x for x in ids if x]
                if len(ids) >= 2:
                    pid = [ids[0], ids[1]]
                    recs = [{"pair_id": pid}]
                else:
                    still_bad.append({**d, "reason2": "no_ids_found"})
                    continue
            else:
                still_bad.append({**d, "reason2": "unhandled_raw_type"})
                continue

        # Each rec could yield a pair; keep those that validate
        kept_any = False
        for rec in recs:
            pid = _normalize_pair_id(rec.get("pair_id"))
            if not pid or len(pid) != 2:
                continue

            pid_t = tuple(pid)
            # optional candidate filter (like your earlier pipeline)
            if base_set is not None:
                ok = (pid_t in base_set) or (allow_swapped_order and base_set_swapped is not None and pid_t in base_set_swapped)
                if not ok:
                    continue

            # dedupe (by exact order of pid; you can also canonicalize if you prefer)
            if pid_t in seen:
                continue
            seen.add(pid_t)

            rec2 = dict(rec)
            rec2["pair_id"] = pid
            recovered_records.append(rec2)
            recovered_pairs_clean.append(pid)
            kept_any = True

        if not kept_any:
            still_bad.append({**d, "reason2": "parsed_but_no_valid_pair"})

    return recovered_pairs_clean, recovered_records, still_bad


recovered_pairs, recovered_records, still_bad = salvage_pairs_from_compound_bad(
    compound_positive_pairs=compound_pairs,
    compound_bad=compound_bad,
    base_pairs=None,              # optional: restrict to your candidate list
    allow_swapped_order=True,
)

print("Recovered pairs:", len(recovered_pairs))
print("Still bad:", len(still_bad))
print("Example recovered:", recovered_pairs[:5])
print("Example still_bad:", still_bad[:3])

# --- cell 178 (post-processing; compound pass: parse, salvage, radiology filter, aligned text)
import json
import re
from typing import Any, Dict, List, Tuple, Optional

# ---------- helpers ----------
_KEEP_CHARS_RE = re.compile(r"[^0-9_,]")

def normalize_pair_id(val: Any) -> Optional[List[str]]:
    """Return ['id1','id2'] from list/tuple or a string; None if not recoverable."""
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        s = ",".join(str(x) for x in val)
    else:
        s = str(val)
    cleaned = _KEEP_CHARS_RE.sub("", s)         # keep only digits, '_' and ','
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

def canon_pair(pid2: List[str]) -> Tuple[str, str]:
    a, b = str(pid2[0]).strip(), str(pid2[1]).strip()
    return (a, b) if a < b else (b, a)

def modality_bucket(modality: str) -> str:
    m = (modality or "").strip().lower()
    radiology_keywords = [
        "ct", "computed tomography", "mri", "magnetic resonance",
        "radiograph", "x-ray", "xray", "ultrasound", "sonograph", "sonography",
        "pet", "spect", "angiograph", "angiography", "fluoroscopy",
        "mammograph", "mammography", "tomograph", "tomography",
    ]
    if any(k in m for k in radiology_keywords):
        return "radiology"
    return "other"

def is_radiology_record(rec: Dict[str, Any]) -> bool:
    # Primary signal: modality field (best)
    if modality_bucket(str(rec.get("modality", ""))) == "radiology":
        return True

    # Optional fallback: sometimes modality is missing, but reasoning mentions imaging type
    # (comment this out if you want STRICT modality-only)
    r = (str(rec.get("reasoning", "")) + " " + str(rec.get("anatomy", "")) + " " + str(rec.get("diagnosis", ""))).lower()
    if any(k in r for k in ["x-ray", "xray", "radiograph", "mri", "ct", "ultrasound", "sonograph", "tomography", "fluoroscopy", "angiography", "mammography", "pet", "spect"]):
        return True

    return False

def dedupe_pairs(pairs: List[Any]) -> List[List[str]]:
    seen = set()
    out: List[List[str]] = []
    for p in pairs:
        pid = normalize_pair_id(p)
        if not pid or len(pid) != 2:
            continue
        u, v = canon_pair(pid)
        if (u, v) in seen:
            continue
        seen.add((u, v))
        out.append([u, v])
    return out

# ---------- inputs you must have in memory ----------
# recovered_records : from salvage_pairs_from_compound_bad(...)
# compound_by_bucket (or compound_labeled_pos_pairs) : from process_compound_positive_pairs(...)
assert "recovered_records" in globals(), "Need recovered_records from the salvage step."
# compound_by_bucket is preferred, but we can fall back to compound_labeled_pos_pairs
assert ("compound_by_bucket" in globals()) or ("compound_labeled_pos_pairs" in globals()), \
       "Need compound_by_bucket (preferred) or compound_labeled_pos_pairs from the earlier processing step."

# ---------- 1) NEW radiology pairs from kept compound results ----------
new_rad_pairs_kept: List[Any] = []
if "compound_by_bucket" in globals() and isinstance(compound_by_bucket, dict):
    new_rad_pairs_kept = compound_by_bucket.get("radiology", {}).get("pairs_clean", []) or []
else:
    # fallback: filter compound_labeled_pos_pairs by modality
    new_rad_pairs_kept = []
    for rec in compound_labeled_pos_pairs:
        if not isinstance(rec, dict):
            continue
        if modality_bucket(str(rec.get("modality", ""))) == "radiology":
            pid = normalize_pair_id(rec.get("pair_id"))
            if pid and len(pid) == 2:
                new_rad_pairs_kept.append(pid)

new_rad_pairs_kept = dedupe_pairs(new_rad_pairs_kept)

# ---------- 2) NEW radiology pairs from salvaged records ----------
new_rad_pairs_salvaged: List[Any] = []
for rec in recovered_records:
    if not isinstance(rec, dict):
        continue
    if not is_radiology_record(rec):
        continue
    pid = normalize_pair_id(rec.get("pair_id"))
    if pid and len(pid) == 2:
        new_rad_pairs_salvaged.append(pid)

new_rad_pairs_salvaged = dedupe_pairs(new_rad_pairs_salvaged)

# ---------- 3) OLD good radiology pairs (plain list of pairs) ----------
# Set this to wherever your "earlier good radiology pairs" live.
# If your old pos_pairs_clean.json is already radiology-only (as you implied), use that.
OLD_RADIOLOGY_PAIRS_PATH = "<DATA_ROOT>/pos_pairs_clean.json"

with open(OLD_RADIOLOGY_PAIRS_PATH, "r", encoding="utf-8") as f:
    old_rad_pairs = json.load(f)

old_rad_pairs = dedupe_pairs(old_rad_pairs)

# ---------- 4) Combine + dedupe ----------
combined_radiology_pairs = dedupe_pairs(old_rad_pairs + new_rad_pairs_kept + new_rad_pairs_salvaged)

print("Old radiology pairs:", len(old_rad_pairs))
print("New radiology (kept):", len(new_rad_pairs_kept))
print("New radiology (salvaged):", len(new_rad_pairs_salvaged))
print("Combined radiology unique pairs:", len(combined_radiology_pairs))

# ---------- 5) Save ----------
OUT_PATH = "<DATA_ROOT>/radiology_pairs_combined.json"
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(combined_radiology_pairs, f)

print("Wrote:", OUT_PATH)

# --- cell 182 (post-processing; compound pass: parse, salvage, radiology filter, aligned text)
import json
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Optional

# ---------------------------
# Helpers
# ---------------------------

def canon_pair(p: Any) -> Tuple[str, str]:
    """Canonical key (u,v) with u < v, regardless of input order."""
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise ValueError(f"Bad pair (expected len=2 list/tuple): {p}")
    a = str(p[0]).strip()
    b = str(p[1]).strip()
    if not a or not b:
        raise ValueError(f"Empty id in pair: {p}")
    return (a, b) if a < b else (b, a)

def norm_caps(caps: Any) -> List[str]:
    """Normalize captions into a flat list[str]."""
    if caps is None:
        return []
    if isinstance(caps, str):
        s = caps.strip()
        return [s] if s else []
    if isinstance(caps, (list, tuple)):
        # handle list containing a single list (your trainer guards for this too)
        if len(caps) == 1 and isinstance(caps[0], list):
            caps = caps[0]
        out = []
        for c in caps:
            if c is None:
                continue
            s = str(c).strip()
            if s:
                out.append(s)
        return out
    s = str(caps).strip()
    return [s] if s else []

def caption_from_record(rec: Dict[str, Any]) -> Optional[str]:
    """Make the same style of short caption you used earlier."""
    diagnosis = str(rec.get("diagnosis", "")).strip()
    anatomy   = str(rec.get("anatomy", "")).strip()
    modality  = str(rec.get("modality", "")).strip()

    parts = []
    if diagnosis:
        parts.append(diagnosis)
    if anatomy:
        parts.append(f"in the {anatomy}")
    if modality:
        parts.append(f"on {modality}")

    cap = " ".join(parts).strip()
    if not cap:
        return None
    if not cap.endswith("."):
        cap += "."
    return cap

def add_pairs_texts_to_map(pair2caps: Dict[Tuple[str, str], set], pairs: List[Any], texts: List[Any]):
    if len(pairs) != len(texts):
        raise ValueError(f"pairs/texts length mismatch: {len(pairs)} vs {len(texts)}")
    for p, caps in zip(pairs, texts):
        key = canon_pair(p)
        for c in norm_caps(caps):
            pair2caps[key].add(c)

def build_aligned_texts_for_existing_pairs(
    combined_pairs: List[Any],
    pair2caps: Dict[Tuple[str, str], set],
    *,
    keep_pairs_with_no_text: bool = True,
) -> List[List[str]]:
    aligned: List[List[str]] = []
    missing = 0
    for p in combined_pairs:
        key = canon_pair(p)  # lookup is canonical even if file contains non-canonical order
        caps = sorted(pair2caps.get(key, set()))
        if not caps and not keep_pairs_with_no_text:
            # If you drop, you would break alignment. So default is keep.
            raise ValueError("keep_pairs_with_no_text=False would break alignment. Use True.")
        if not caps:
            missing += 1
        aligned.append(caps)
    print(f"Pairs with 0 captions: {missing} / {len(combined_pairs)}")
    return aligned

# ---------------------------
# CONFIG: choose your combined pairs file
# ---------------------------

# If you want radiology-only:
COMBINED_PAIRS_PATH = "<DATA_ROOT>/radiology_pairs_combined.json"
OUT_TEXTS_PATH      = "<DATA_ROOT>/text_pairs_radiology_combined.json"

# If instead you want the unified-all-modalities dataset, switch to:
# COMBINED_PAIRS_PATH = "<DATA_ROOT>/pos_pairs_clean_unified.json"
# OUT_TEXTS_PATH      = "<DATA_ROOT>/text_pairs_unified.json"

# Old dataset (your existing training files)
OLD_PAIRS_PATH = "<DATA_ROOT>/pos_pairs_clean.json"
OLD_TEXTS_PATH = "<DATA_ROOT>/text_pairs.json"

# New kept LLM outputs (must exist in memory OR load from disk)
assert "compound_pos_pairs_clean" in globals(), "Need compound_pos_pairs_clean in memory."
assert "compound_text_pairs" in globals(), "Need compound_text_pairs in memory."

# Salvaged LLM records (optional but recommended, since you recovered lots)
USE_SALVAGED = True
if USE_SALVAGED:
    assert "recovered_records" in globals(), "Need recovered_records in memory if USE_SALVAGED=True."

# ---------------------------
# LOAD combined pairs
# ---------------------------

with open(COMBINED_PAIRS_PATH, "r", encoding="utf-8") as f:
    combined_pairs = json.load(f)

print("Loaded combined pairs:", len(combined_pairs))

# ---------------------------
# Build pair -> captions map from all sources
# ---------------------------

pair2caps: Dict[Tuple[str, str], set] = defaultdict(set)

# 1) Old captions
with open(OLD_PAIRS_PATH, "r", encoding="utf-8") as f:
    old_pairs = json.load(f)
with open(OLD_TEXTS_PATH, "r", encoding="utf-8") as f:
    old_texts = json.load(f)

add_pairs_texts_to_map(pair2caps, old_pairs, old_texts)

# 2) New "kept" captions from your processed compound results
add_pairs_texts_to_map(pair2caps, compound_pos_pairs_clean, compound_text_pairs)

# 3) New "salvaged" captions from recovered_records (generated)
if USE_SALVAGED:
    n_added_caps = 0
    for rec in recovered_records:
        if not isinstance(rec, dict):
            continue
        pid = rec.get("pair_id")
        if not isinstance(pid, (list, tuple)) or len(pid) != 2:
            continue
        key = canon_pair(pid)
        cap = caption_from_record(rec)
        if cap:
            if cap not in pair2caps[key]:
                n_added_caps += 1
            pair2caps[key].add(cap)
    print("Added generated captions from salvaged records:", n_added_caps)

# ---------------------------
# Build aligned texts for the existing combined pairs list
# ---------------------------

combined_texts = build_aligned_texts_for_existing_pairs(
    combined_pairs=combined_pairs,
    pair2caps=pair2caps,
    keep_pairs_with_no_text=True,
)

# ---------------------------
# Save ONLY the texts file (no pairs file written)
# ---------------------------

with open(OUT_TEXTS_PATH, "w", encoding="utf-8") as f:
    json.dump(combined_texts, f)

print("Wrote:", OUT_TEXTS_PATH)
print("len(texts) == len(pairs)?", len(combined_texts) == len(combined_pairs))

# --- cell 191 (compound answers)
# import json
# from openai import OpenAI

# def load_json_records_from_file_id(file_id: str):
#     content = client.files.content(file_id)
#     text = content.text  # full file content as string

#     text_stripped = text.lstrip()

#     # Case 1 — JSON array
#     if text_stripped.startswith("["):
#         return json.loads(text)

#     # Case 2 — JSONL (fast path)
#     try:
#         return [json.loads(line) for line in text.splitlines() if line.strip()]
#     except json.JSONDecodeError:
#         pass  # fall through to streaming parser

#     # Case 3 — Stream of JSON objects (robust fallback)
#     decoder = json.JSONDecoder()
#     idx = 0
#     length = len(text)
#     records = []

#     while idx < length:
#         # Skip whitespace
#         while idx < length and text[idx].isspace():
#             idx += 1
#         if idx >= length:
#             break

#         obj, next_idx = decoder.raw_decode(text, idx)
#         records.append(obj)
#         idx = next_idx

#     return records

# # ---- Your IDs from the Batch object ----
# input_file_id  = "<OPENAI_ID>"
# output_file_id = "<OPENAI_ID>"
# error_file_id  = "<OPENAI_ID>"

# # 1) Load input, output, error
# input_lines  = load_json_records_from_file_id(input_file_id)
# output_lines = load_json_records_from_file_id(output_file_id)
# error_lines  = load_json_records_from_file_id(error_file_id)

# # 2) Build mapping: custom_id -> input index
# cid_to_idx = {}
# for idx, req in enumerate(input_lines):
#     cid = req.get("custom_id")
#     if cid is None:
#         raise ValueError(f"Input line {idx} missing custom_id")
#     if cid in cid_to_idx:
#         raise ValueError(f"Duplicate custom_id in input file: {cid}")
#     cid_to_idx[cid] = idx

# N = len(input_lines)

# # 3) Allocate aligned outputs
# aligned_answers = [None] * N          # answer text (or None if failed)
# aligned_raw     = [None] * N          # full underlying response body (optional)
# aligned_error   = [None] * N          # error object/details (optional)

# # 4) Fill successes
# for row in output_lines:
#     cid = row["custom_id"]
#     i = cid_to_idx[cid]

#     # row["response"]["body"] is the actual Chat Completions response payload
#     body = row["response"]["body"]
#     aligned_raw[i] = body

#     # Typical chat.completions extraction:
#     # (adjust if you requested multiple choices / different structure)
#     aligned_answers[i] = body["choices"][0]["message"]["content"]

# # 5) Fill failures
# failed_indices = []
# for row in error_lines:
#     cid = row["custom_id"]
#     i = cid_to_idx[cid]
#     failed_indices.append(i)

#     # Error rows often look like: {"response": null, "error": {...}}
#     # but sometimes you may also get a response with a non-200 status_code
#     aligned_error[i] = row.get("error") or row.get("response") or row

# # ---- Results you can use ----
# print("N questions:", N)
# print("Succeeded:", sum(a is not None for a in aligned_answers))
# print("Failed:", len(failed_indices))

# # failed_indices are the "indices in your original question list" that failed
# # aligned_answers[i] is the answer for compound_questions_response[i] (or None if failed)

# --- cell 193 (compound answers)
# import os
# import time
# import tempfile

# def _wait_for_batch_terminal(batch_id: str, poll_s: int = 30):
#     """Poll batch until it reaches a terminal status; returns the final batch object."""
#     while True:
#         b = client.batches.retrieve(batch_id)
#         if b.status in ("validating", "in_progress", "finalizing", "cancelling"):
#             time.sleep(poll_s)
#             continue
#         return b

# def retry_failed_requests_and_fill(
#     *,
#     input_lines,
#     cid_to_idx,
#     aligned_answers,
#     aligned_raw=None,
#     aligned_error=None,
#     failed_indices=None,
#     endpoint=None,
#     completion_window="24h",
#     poll_s=30,
#     metadata=None,
# ):
#     """
#     Retries failed batch requests (by indices into `input_lines`) via a NEW Batch job,
#     then fills `aligned_answers` (and optionally `aligned_raw`/`aligned_error`) IN PLACE.

#     Returns a dict summary, including remaining failures (if any).
#     """
#     N = len(input_lines)

#     if aligned_raw is None:
#         aligned_raw = [None] * N
#     if aligned_error is None:
#         aligned_error = [None] * N

#     # Default: retry anything still missing an answer
#     if failed_indices is None:
#         failed_indices = [i for i, ans in enumerate(aligned_answers) if ans is None]

#     # Only retry indices that are still missing + valid
#     failed_indices = sorted({i for i in failed_indices if 0 <= i < N and aligned_answers[i] is None})
#     if not failed_indices:
#         return {
#             "retried": 0,
#             "filled": 0,
#             "still_failed": 0,
#             "still_failed_indices": [],
#             "batch_id": None,
#         }

#     retry_tasks = [input_lines[i] for i in failed_indices]

#     # Infer endpoint from the task "url" if not provided
#     if endpoint is None:
#         endpoint = retry_tasks[0].get("url")
#     if not endpoint:
#         raise ValueError("Could not infer `endpoint` (missing url in tasks). Pass endpoint explicitly.")

#     # Sanity check: Batch endpoint must match all task urls
#     offenders = [t.get("custom_id") for t in retry_tasks if t.get("url") != endpoint]
#     if offenders:
#         raise ValueError(
#             f"Retry tasks contain mixed urls; expected url={endpoint}. "
#             f"Offenders (first 10 custom_id): {offenders[:10]}"
#         )

#     tmp_path = None
#     try:
#         # 1) Write strict JSONL retry file (1 JSON object per line)
#         with tempfile.NamedTemporaryFile("w", delete=False, suffix=".jsonl", encoding="utf-8") as tmp:
#             tmp_path = tmp.name
#             for obj in retry_tasks:
#                 tmp.write(json.dumps(obj, ensure_ascii=False) + "\n")

#         # 2) Upload with purpose="batch" and create a new batch job
#         # (Official flow: upload JSONL with purpose 'batch', then batches.create) :contentReference[oaicite:1]{index=1}
#         with open(tmp_path, "rb") as f:
#             retry_file = client.files.create(file=f, purpose="batch")

#         retry_batch = client.batches.create(
#             input_file_id=retry_file.id,
#             endpoint=endpoint,
#             completion_window=completion_window,
#             metadata=metadata,
#         )

#         # 3) Wait until terminal
#         retry_batch = _wait_for_batch_terminal(retry_batch.id, poll_s=poll_s)

#         # If not completed, return diagnostic info (no in-place fill beyond this point)
#         if retry_batch.status != "completed":
#             return {
#                 "retried": len(retry_tasks),
#                 "filled": 0,
#                 "still_failed": len(failed_indices),
#                 "still_failed_indices": failed_indices,
#                 "batch_id": retry_batch.id,
#                 "batch_status": retry_batch.status,
#                 "batch_file_id": retry_file.id,
#                 "batch": retry_batch,
#             }

#         filled = 0
#         still_failed_indices = set()

#         # 4) Apply successes (by custom_id -> original index)
#         if retry_batch.output_file_id:
#             out_rows = load_json_records_from_file_id(retry_batch.output_file_id)
#             for row in out_rows:
#                 cid = row["custom_id"]
#                 i = cid_to_idx[cid]
#                 body = row["response"]["body"]

#                 # Fill only if still missing (safe if you re-run)
#                 if aligned_answers[i] is None:
#                     aligned_answers[i] = body["choices"][0]["message"]["content"]
#                     filled += 1

#                 aligned_raw[i] = body
#                 aligned_error[i] = None

#         # 5) Apply remaining failures
#         if retry_batch.error_file_id:
#             err_rows = load_json_records_from_file_id(retry_batch.error_file_id)
#             for row in err_rows:
#                 cid = row["custom_id"]
#                 i = cid_to_idx[cid]
#                 aligned_error[i] = row.get("error") or row.get("response") or row
#                 still_failed_indices.add(i)

#         return {
#             "retried": len(retry_tasks),
#             "filled": filled,
#             "still_failed": len(still_failed_indices),
#             "still_failed_indices": sorted(still_failed_indices),
#             "batch_id": retry_batch.id,
#             "batch_file_id": retry_file.id,
#             "batch": retry_batch,
#         }

#     finally:
#         if tmp_path:
#             try:
#                 os.remove(tmp_path)
#             except OSError:
#                 pass

# --- cell 194 (compound answers)
# retry_summary = retry_failed_requests_and_fill(
#     input_lines=input_lines,
#     cid_to_idx=cid_to_idx,
#     aligned_answers=aligned_answers,
#     aligned_raw=aligned_raw,
#     aligned_error=aligned_error,
#     failed_indices=failed_indices,  # or omit to retry all None slots
#     metadata={"description": "Retry failed requests (round 1)"},
# )

# print("retried:", retry_summary["retried"])
# print("filled:", retry_summary["filled"])
# print("still_failed:", retry_summary["still_failed"])
# print("still_failed_indices (first 20):", retry_summary["still_failed_indices"][:20])

# --- cell 202 (compound descriptor source; writer of the compound descriptor file)
import json
import re
import ast
import os
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, Counter

# --------------------------------------------------
# Config
# --------------------------------------------------

BASE_DIR = "<DATA_ROOT>"

# Existing canonical baseline (NOT the compound list)
CANONICAL_POS_PAIRS_PATH = os.path.join(BASE_DIR, "canonical_pos_pairs.json")

# Optional:
# Set this only if you already saved the old canonical text list to disk.
# Otherwise the code uses `text_pairs` from memory if it exists, and if not,
# rebuilds the captions from canonical_pairs / canonical_pos_pairs.json.
CANONICAL_TEXT_PAIRS_PATH = None

# Match previous notebook behavior:
# False -> ['a','b'] and ['b','a'] are different pairs
# True  -> they are treated as the same pair for dedupe/merge
ORDER_INSENSITIVE_DEDUPE = False

# Optional candidate filter for compound_pairs.
# Set to None to keep every positive pair emitted by compound_pairs.
COMPOUND_BASE_PAIRS = pos_pairs if "pos_pairs" in globals() else None
COMPOUND_ALLOW_SWAPPED_ORDER_FOR_BASE_FILTER = False

# Recover extra compound pairs from compound_bad using regex on IDs when needed.
SALVAGE_COMPOUND_BAD = True

# --------------------------------------------------
# Output paths
# --------------------------------------------------

NEW_CANONICAL_LABELED_PATH   = os.path.join(BASE_DIR, "new_canonical_labeled_pairs.json")
NEW_CANONICAL_CLEAN_PATH     = os.path.join(BASE_DIR, "new_canonical_pairs_clean.json")
NEW_CANONICAL_TEXT_PATH      = os.path.join(BASE_DIR, "new_canonical_text_pairs.json")
NEW_CANONICAL_ONLY_PATH      = os.path.join(BASE_DIR, "new_canonical_pairs_only_to_add.json")

CANONICAL_MERGED_PAIRS_PATH  = os.path.join(BASE_DIR, "canonical_pairs_merged_with_new.json")
CANONICAL_MERGED_TEXTS_PATH  = os.path.join(BASE_DIR, "canonical_text_pairs_merged_with_new.json")

COMPOUND_CLEAN_PATH          = os.path.join(BASE_DIR, "compound_canonical_pairs_clean.json")
COMPOUND_TEXTS_PATH          = os.path.join(BASE_DIR, "compound_canonical_text_pairs.json")
COMPOUND_LABELED_PATH        = os.path.join(BASE_DIR, "compound_canonical_labeled_pairs.json")
COMPOUND_ONLY_PATH           = os.path.join(BASE_DIR, "compound_canonical_pairs_only_to_add.json")
COMPOUND_RECOVERED_PATH      = os.path.join(BASE_DIR, "compound_canonical_recovered_pairs.json")
COMPOUND_STILL_BAD_PATH      = os.path.join(BASE_DIR, "compound_canonical_still_bad.json")

FINAL_MERGED_PAIRS_PATH      = os.path.join(BASE_DIR, "canonical_compound_pairs_merged.json")
FINAL_MERGED_TEXTS_PATH      = os.path.join(BASE_DIR, "canonical_compound_text_pairs_merged.json")
FINAL_MISSING_TEXT_PATH      = os.path.join(BASE_DIR, "canonical_compound_missing_text_pairs.json")
DIAG_PATH                    = os.path.join(BASE_DIR, "canonical_compound_diagnostics.json")

# --------------------------------------------------
# Helpers
# --------------------------------------------------

_PAIR_ID_CLEAN_RE = re.compile(r"[^0-9_,]")
_ID_RE = re.compile(r"\d+_\d+_\d+")

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def load_jsonish_file(path: str) -> Any:
    with open(path, "r") as f:
        s = f.read()

    s = _strip_code_fences(s)

    try:
        return json.loads(s)
    except Exception:
        pass

    try:
        return ast.literal_eval(s)
    except Exception as e:
        raise ValueError(f"Could not parse file: {path}") from e

def _parse_jsonish_obj(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None

    s = _strip_code_fences(raw)
    if not s:
        return None

    candidates = [s]

    first_arr = s.find("[")
    last_arr = s.rfind("]")
    if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
        candidates.append(s[first_arr:last_arr + 1])

    first_obj = s.find("{")
    last_obj = s.rfind("}")
    if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
        candidates.append(s[first_obj:last_obj + 1])

    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)

        try:
            return json.loads(cand)
        except Exception:
            pass

        try:
            return ast.literal_eval(cand)
        except Exception:
            pass

    return None

def _flatten_dict_records(obj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def _rec(x: Any) -> None:
        if isinstance(x, dict):
            if x != {}:
                out.append(x)
            return
        if isinstance(x, list):
            for item in x:
                _rec(item)

    _rec(obj)
    return out

def parse_jsonish_to_records(raw: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Returns:
      None -> unparseable
      []   -> parseable but empty (e.g. {})
      [...] -> one or more dict records
    """
    obj = _parse_jsonish_obj(raw)
    if obj is None:
        return None
    return _flatten_dict_records(obj)

def normalize_pair_id(pair_id_val: Any) -> Optional[List[str]]:
    if pair_id_val is None:
        return None

    if isinstance(pair_id_val, (list, tuple)):
        s = ",".join(str(x) for x in pair_id_val)
    else:
        s = str(pair_id_val)

    cleaned = _PAIR_ID_CLEAN_RE.sub("", s)
    parts = [p for p in cleaned.split(",") if p]
    return parts if parts else None

def pair_key(pid: List[str], order_insensitive: bool = False) -> Tuple[str, str]:
    return tuple(sorted(pid)) if order_insensitive else (pid[0], pid[1])

def normalize_text_pair_item(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(t).strip() for t in x if str(t).strip()]
    s = str(x).strip()
    return [s] if s else []

def build_short_caption_from_record(obj: Dict[str, Any]) -> List[str]:
    diagnosis = str(obj.get("diagnosis", "")).strip()
    anatomy = str(obj.get("anatomy", "")).strip()
    modality = str(obj.get("modality", "")).strip()

    parts = []
    if diagnosis:
        parts.append(diagnosis)
    if anatomy:
        parts.append(f"in the {anatomy}")
    if modality:
        parts.append(f"on {modality}")

    cap = " ".join(parts).strip()
    if cap and not cap.endswith("."):
        cap += "."
    return [cap] if cap else []

def modality_bucket(modality: str) -> str:
    m = (modality or "").strip().lower()

    radiology_keywords = [
        "ct", "computed tomography", "mri", "magnetic resonance",
        "radiograph", "x-ray", "xray", "ultrasound", "sonograph", "sonography",
        "pet", "spect", "angiograph", "angiography", "fluoroscopy",
        "mammograph", "mammography", "tomograph", "tomography",
    ]
    pathology_keywords = [
        "histolog", "patholog", "microscop", "immunohistochem", "ihc",
        "hematoxylin", "eosin", "h&e", "stain", "biopsy", "slide",
    ]
    ophtho_keywords = [
        "fundus", "oct", "optical coherence", "slit lamp",
        "fluorescein", "indocyanine", "retinal", "ophthalm",
    ]
    endoscopy_keywords = [
        "endoscop", "colonoscopy", "gastroscopy", "bronchoscopy",
        "laparoscopy", "hysteroscopy", "arthroscopy",
    ]
    cardiology_keywords = [
        "ecg", "ekg", "electrocardi", "echocardi", "echo",
    ]

    # Check more specific buckets before generic radiology/tomography,
    # otherwise OCT gets swallowed by "tomography".
    if any(k in m for k in pathology_keywords):
        return "pathology_microscopy"
    if any(k in m for k in ophtho_keywords):
        return "ophthalmology"
    if any(k in m for k in endoscopy_keywords):
        return "endoscopy"
    if any(k in m for k in cardiology_keywords):
        return "cardiology"
    if any(k in m for k in radiology_keywords):
        return "radiology"
    return "other"

def bucket_counts(by_bucket: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    return {k: len(v.get("pairs_clean", [])) for k, v in by_bucket.items()}

def normalize_pair_list_input(raw_pairs: Optional[List[Any]]) -> List[List[str]]:
    if raw_pairs is None:
        return []

    clean: List[List[str]] = []
    seen = set()

    for item in raw_pairs:
        candidate = item.get("pair_id") if isinstance(item, dict) else item
        pid = normalize_pair_id(candidate)
        if not pid or len(pid) != 2:
            continue

        k = pair_key(pid, order_insensitive=ORDER_INSENSITIVE_DEDUPE)
        if k in seen:
            continue

        seen.add(k)
        clean.append(pid)

    return clean

def process_positive_pair_outputs(
    raw_outputs: List[Any],
    *,
    base_pairs: Optional[List[Any]] = None,
    allow_swapped_order: bool = False,
    dedupe: bool = True,
    order_insensitive_dedupe: bool = False,
) -> Dict[str, Any]:
    """
    Keeps ALL modalities.
    Handles each raw item being:
      - one dict
      - one JSON-stringified dict
      - one JSON-stringified list of dicts
      - {}
    """
    base_clean = normalize_pair_list_input(base_pairs)
    base_set = {tuple(p) for p in base_clean}
    base_set_swapped = {(b, a) for (a, b) in base_set} if allow_swapped_order else set()

    labeled_all: List[Dict[str, Any]] = []
    pairs_clean_all: List[List[str]] = []
    text_pairs_all: List[List[str]] = []
    bad: List[Dict[str, Any]] = []

    by_bucket = defaultdict(lambda: {"labeled": [], "pairs_clean": [], "text_pairs": []})
    modality_counts = Counter()

    seen = set()
    raw_empty_items = 0
    multi_record_raw_items = 0

    for idx, raw in enumerate(raw_outputs):
        records = parse_jsonish_to_records(raw)

        if records is None:
            bad.append({
                "idx": idx,
                "reason": "unparseable",
                "raw_preview": str(raw)[:500],
            })
            continue

        if len(records) == 0:
            raw_empty_items += 1
            continue

        if len(records) > 1:
            multi_record_raw_items += 1

        for subidx, obj in enumerate(records):
            pid = normalize_pair_id(obj.get("pair_id"))
            if not pid or len(pid) != 2:
                bad.append({
                    "idx": idx,
                    "subidx": subidx,
                    "reason": "bad_pair_id",
                    "pair_id": obj.get("pair_id"),
                    "raw_preview": str(raw)[:500],
                })
                continue

            pid_t = tuple(pid)
            if base_pairs is not None:
                ok = (pid_t in base_set) or (allow_swapped_order and pid_t in base_set_swapped)
                if not ok:
                    bad.append({
                        "idx": idx,
                        "subidx": subidx,
                        "reason": "not_in_base_pairs",
                        "pair_id_norm": pid,
                    })
                    continue

            k = pair_key(pid, order_insensitive=order_insensitive_dedupe)
            if dedupe and k in seen:
                continue
            seen.add(k)

            obj2 = dict(obj)
            obj2["pair_id"] = pid

            caps = build_short_caption_from_record(obj2)
            bucket = modality_bucket(str(obj2.get("modality", "")))
            modality = str(obj2.get("modality", "")).strip() or "UNKNOWN"

            labeled_all.append(obj2)
            pairs_clean_all.append(pid)
            text_pairs_all.append(caps)

            by_bucket[bucket]["labeled"].append(obj2)
            by_bucket[bucket]["pairs_clean"].append(pid)
            by_bucket[bucket]["text_pairs"].append(caps)

            modality_counts[modality] += 1

    return {
        "labeled_all": labeled_all,
        "pairs_clean_all": pairs_clean_all,
        "text_pairs_all": text_pairs_all,
        "by_bucket": dict(by_bucket),
        "bad": bad,
        "raw_empty_items": raw_empty_items,
        "multi_record_raw_items": multi_record_raw_items,
        "modality_counts": dict(modality_counts),
    }

def salvage_pairs_from_bad_rows(
    raw_outputs: List[Any],
    bad_rows: List[Dict[str, Any]],
    *,
    base_pairs: Optional[List[Any]] = None,
    allow_swapped_order: bool = True,
    order_insensitive_dedupe: bool = False,
) -> Tuple[List[List[str]], List[List[str]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns:
      recovered_pairs_clean
      recovered_text_pairs
      recovered_records
      still_bad
    """
    base_clean = normalize_pair_list_input(base_pairs)
    base_set = {tuple(p) for p in base_clean}
    base_set_swapped = {(b, a) for (a, b) in base_set} if allow_swapped_order else set()

    recovered_pairs_clean: List[List[str]] = []
    recovered_text_pairs: List[List[str]] = []
    recovered_records: List[Dict[str, Any]] = []
    still_bad: List[Dict[str, Any]] = []

    seen = set()

    for d in bad_rows:
        idx = d.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < len(raw_outputs)):
            still_bad.append({**d, "reason2": "bad_idx"})
            continue

        raw = raw_outputs[idx]
        records = parse_jsonish_to_records(raw)

        if records is None or len(records) == 0:
            ids = _ID_RE.findall(str(raw))
            if len(ids) >= 2:
                records = [{"pair_id": [ids[0], ids[1]]}]
            else:
                still_bad.append({**d, "reason2": "no_ids_found"})
                continue

        kept_any = False
        for rec in records:
            pid = normalize_pair_id(rec.get("pair_id"))
            if not pid or len(pid) != 2:
                continue

            pid_t = tuple(pid)
            if base_pairs is not None:
                ok = (pid_t in base_set) or (allow_swapped_order and pid_t in base_set_swapped)
                if not ok:
                    continue

            k = pair_key(pid, order_insensitive=order_insensitive_dedupe)
            if k in seen:
                continue
            seen.add(k)

            rec2 = dict(rec)
            rec2["pair_id"] = pid

            recovered_records.append(rec2)
            recovered_pairs_clean.append(pid)
            recovered_text_pairs.append(build_short_caption_from_record(rec2))
            kept_any = True

        if not kept_any:
            still_bad.append({**d, "reason2": "parsed_but_no_valid_pair"})

    return recovered_pairs_clean, recovered_text_pairs, recovered_records, still_bad

def clean_existing_canonical_records_with_texts(
    raw_records: List[Any],
    raw_text_pairs: Optional[List[Any]] = None,
    *,
    order_insensitive_dedupe: bool = False,
):
    if not isinstance(raw_records, list):
        raise ValueError("Expected the canonical baseline to be a list")

    if raw_text_pairs is not None:
        if not isinstance(raw_text_pairs, list):
            raise ValueError("raw_text_pairs must be a list")
        if len(raw_records) != len(raw_text_pairs):
            raise ValueError(
                f"Length mismatch: raw_records has {len(raw_records)} items, "
                f"raw_text_pairs has {len(raw_text_pairs)} items"
            )

    clean_records: List[Dict[str, Any]] = []
    clean_pairs: List[List[str]] = []
    clean_texts: List[List[str]] = []
    bad: List[Dict[str, Any]] = []
    seen = set()

    for idx, item in enumerate(raw_records):
        if isinstance(item, dict):
            obj = item
        else:
            records = parse_jsonish_to_records(item)
            if records is None:
                bad.append({
                    "idx": idx,
                    "reason": "unparseable_existing_record",
                    "raw_preview": str(item)[:500],
                })
                continue
            if len(records) == 0:
                continue
            if len(records) > 1:
                bad.append({
                    "idx": idx,
                    "reason": "multiple_records_in_existing_item",
                    "count": len(records),
                })
            obj = records[0]

        pid = normalize_pair_id(obj.get("pair_id"))
        if not pid or len(pid) != 2:
            bad.append({
                "idx": idx,
                "reason": "bad_pair_id_in_existing_record",
                "pair_id": obj.get("pair_id"),
            })
            continue

        k = pair_key(pid, order_insensitive=order_insensitive_dedupe)
        if k in seen:
            continue
        seen.add(k)

        obj2 = dict(obj)
        obj2["pair_id"] = pid

        txt = normalize_text_pair_item(raw_text_pairs[idx]) if raw_text_pairs is not None else []
        if not txt:
            txt = build_short_caption_from_record(obj2)

        clean_records.append(obj2)
        clean_pairs.append(pid)
        clean_texts.append(txt)

    return clean_records, clean_pairs, clean_texts, bad

def merge_pairs_and_texts(
    base_pairs: List[List[str]],
    base_texts: List[Any],
    add_pairs: List[List[str]],
    add_texts: List[Any],
    *,
    order_insensitive_dedupe: bool = False,
):
    if len(base_pairs) != len(base_texts):
        raise ValueError("base_pairs and base_texts must have the same length")
    if len(add_pairs) != len(add_texts):
        raise ValueError("add_pairs and add_texts must have the same length")

    merged_pairs = [list(pid) for pid in base_pairs]
    merged_texts = [normalize_text_pair_item(txt) for txt in base_texts]

    index = {
        pair_key(pid, order_insensitive=order_insensitive_dedupe): i
        for i, pid in enumerate(merged_pairs)
    }

    added_count = 0
    filled_missing_text_count = 0
    conflict_count = 0
    conflicts_preview = []

    for pid, txt in zip(add_pairs, add_texts):
        txt_norm = normalize_text_pair_item(txt)
        k = pair_key(pid, order_insensitive=order_insensitive_dedupe)

        if k in index:
            i = index[k]
            if (not merged_texts[i]) and txt_norm:
                merged_texts[i] = txt_norm
                filled_missing_text_count += 1
            elif merged_texts[i] and txt_norm and merged_texts[i] != txt_norm:
                conflict_count += 1
                if len(conflicts_preview) < 50:
                    conflicts_preview.append({
                        "pair_id": pid,
                        "existing_text": merged_texts[i],
                        "incoming_text": txt_norm,
                    })
        else:
            index[k] = len(merged_pairs)
            merged_pairs.append(list(pid))
            merged_texts.append(txt_norm)
            added_count += 1

    return merged_pairs, merged_texts, {
        "added_count": added_count,
        "filled_missing_text_count": filled_missing_text_count,
        "conflict_count": conflict_count,
        "conflicts_preview": conflicts_preview,
    }

def get_only_new_pairs(
    base_pairs: List[List[str]],
    candidate_pairs: List[List[str]],
    *,
    order_insensitive_dedupe: bool = False,
) -> List[List[str]]:
    seen = {pair_key(pid, order_insensitive=order_insensitive_dedupe) for pid in base_pairs}
    out: List[List[str]] = []

    for pid in candidate_pairs:
        k = pair_key(pid, order_insensitive=order_insensitive_dedupe)
        if k in seen:
            continue
        seen.add(k)
        out.append(list(pid))

    return out

def dedupe_records_by_pair(
    records: List[Dict[str, Any]],
    *,
    order_insensitive_dedupe: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()

    for rec in records:
        pid = normalize_pair_id(rec.get("pair_id"))
        if not pid or len(pid) != 2:
            continue

        k = pair_key(pid, order_insensitive=order_insensitive_dedupe)
        if k in seen:
            continue
        seen.add(k)

        rec2 = dict(rec)
        rec2["pair_id"] = pid
        out.append(rec2)

    return out

# --------------------------------------------------
# Main
# --------------------------------------------------

if "new_pairs" not in globals():
    raise ValueError("new_pairs must already exist in memory")
if "compound_pairs" not in globals():
    raise ValueError("compound_pairs must already exist in memory")

# 1) Load the existing canonical baseline (NOT the compound list)
if "canonical_pairs" in globals():
    canonical_pairs_raw = canonical_pairs
else:
    canonical_pairs_raw = load_jsonish_file(CANONICAL_POS_PAIRS_PATH)

if CANONICAL_TEXT_PAIRS_PATH is not None:
    canonical_text_pairs_raw = load_jsonish_file(CANONICAL_TEXT_PAIRS_PATH)
elif "text_pairs" in globals():
    canonical_text_pairs_raw = text_pairs
else:
    canonical_text_pairs_raw = None

existing_canonical_records, existing_canonical_pairs_clean, existing_canonical_text_pairs, existing_canonical_bad = (
    clean_existing_canonical_records_with_texts(
        canonical_pairs_raw,
        raw_text_pairs=canonical_text_pairs_raw,
        order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
    )
)

# 2) Process new_pairs across ALL modalities
res_new = process_positive_pair_outputs(
    new_pairs,
    base_pairs=None,
    allow_swapped_order=False,
    dedupe=True,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

new_canonical_labeled_pairs = res_new["labeled_all"]
new_canonical_pairs_clean = res_new["pairs_clean_all"]
new_canonical_text_pairs = res_new["text_pairs_all"]
new_canonical_bad = res_new["bad"]
new_canonical_by_bucket = res_new["by_bucket"]

new_canonical_pairs_only_to_add = get_only_new_pairs(
    existing_canonical_pairs_clean,
    new_canonical_pairs_clean,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

canonical_pairs_merged, canonical_text_pairs_merged, canonical_merge_stats = merge_pairs_and_texts(
    existing_canonical_pairs_clean,
    existing_canonical_text_pairs,
    new_canonical_pairs_clean,
    new_canonical_text_pairs,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

# 3) Process compound_pairs across ALL modalities
res_compound = process_positive_pair_outputs(
    compound_pairs,
    base_pairs=COMPOUND_BASE_PAIRS,
    allow_swapped_order=COMPOUND_ALLOW_SWAPPED_ORDER_FOR_BASE_FILTER,
    dedupe=True,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

compound_pairs_clean_main = res_compound["pairs_clean_all"]
compound_text_pairs_main = res_compound["text_pairs_all"]
compound_labeled_pairs_main = res_compound["labeled_all"]
compound_bad_main = res_compound["bad"]
compound_by_bucket = res_compound["by_bucket"]

compound_recovered_pairs = []
compound_recovered_texts = []
compound_recovered_records = []
compound_still_bad = list(compound_bad_main)

if SALVAGE_COMPOUND_BAD and compound_bad_main:
    (
        compound_recovered_pairs,
        compound_recovered_texts,
        compound_recovered_records,
        compound_still_bad,
    ) = salvage_pairs_from_bad_rows(
        compound_pairs,
        compound_bad_main,
        base_pairs=COMPOUND_BASE_PAIRS,
        allow_swapped_order=COMPOUND_ALLOW_SWAPPED_ORDER_FOR_BASE_FILTER,
        order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
    )

compound_canonical_labeled_pairs = dedupe_records_by_pair(
    compound_labeled_pairs_main + compound_recovered_records,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

compound_canonical_pairs_clean, compound_canonical_text_pairs, compound_internal_merge_stats = merge_pairs_and_texts(
    compound_pairs_clean_main,
    compound_text_pairs_main,
    compound_recovered_pairs,
    compound_recovered_texts,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

# 4) Merge canonical baseline+new_pairs with compound canonical pairs/texts
compound_pairs_only_to_add = get_only_new_pairs(
    canonical_pairs_merged,
    compound_canonical_pairs_clean,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

canonical_compound_pairs_merged, canonical_compound_text_pairs_merged, final_merge_stats = merge_pairs_and_texts(
    canonical_pairs_merged,
    canonical_text_pairs_merged,
    compound_canonical_pairs_clean,
    compound_canonical_text_pairs,
    order_insensitive_dedupe=ORDER_INSENSITIVE_DEDUPE,
)

missing_text_pairs = [
    pid
    for pid, txt in zip(canonical_compound_pairs_merged, canonical_compound_text_pairs_merged)
    if not normalize_text_pair_item(txt)
]

# --------------------------------------------------
# Save
# --------------------------------------------------

with open(NEW_CANONICAL_LABELED_PATH, "w") as f:
    json.dump(new_canonical_labeled_pairs, f, indent=2)

with open(NEW_CANONICAL_CLEAN_PATH, "w") as f:
    json.dump(new_canonical_pairs_clean, f, indent=2)

with open(NEW_CANONICAL_TEXT_PATH, "w") as f:
    json.dump(new_canonical_text_pairs, f, indent=2)

with open(NEW_CANONICAL_ONLY_PATH, "w") as f:
    json.dump(new_canonical_pairs_only_to_add, f, indent=2)

with open(CANONICAL_MERGED_PAIRS_PATH, "w") as f:
    json.dump(canonical_pairs_merged, f, indent=2)

with open(CANONICAL_MERGED_TEXTS_PATH, "w") as f:
    json.dump(canonical_text_pairs_merged, f, indent=2)

with open(COMPOUND_CLEAN_PATH, "w") as f:
    json.dump(compound_canonical_pairs_clean, f, indent=2)

with open(COMPOUND_TEXTS_PATH, "w") as f:
    json.dump(compound_canonical_text_pairs, f, indent=2)

with open(COMPOUND_LABELED_PATH, "w") as f:
    json.dump(compound_canonical_labeled_pairs, f, indent=2)

with open(COMPOUND_ONLY_PATH, "w") as f:
    json.dump(compound_pairs_only_to_add, f, indent=2)

with open(COMPOUND_RECOVERED_PATH, "w") as f:
    json.dump({
        "recovered_pairs": compound_recovered_pairs,
        "recovered_texts": compound_recovered_texts,
        "recovered_records": compound_recovered_records,
    }, f, indent=2)

with open(COMPOUND_STILL_BAD_PATH, "w") as f:
    json.dump(compound_still_bad, f, indent=2)

with open(FINAL_MERGED_PAIRS_PATH, "w") as f:
    json.dump(canonical_compound_pairs_merged, f, indent=2)

with open(FINAL_MERGED_TEXTS_PATH, "w") as f:
    json.dump(canonical_compound_text_pairs_merged, f, indent=2)

with open(FINAL_MISSING_TEXT_PATH, "w") as f:
    json.dump(missing_text_pairs, f, indent=2)

with open(DIAG_PATH, "w") as f:
    json.dump({
        "order_insensitive_dedupe": ORDER_INSENSITIVE_DEDUPE,
        "compound_base_pairs_used": COMPOUND_BASE_PAIRS is not None,
        "compound_allow_swapped_order_for_base_filter": COMPOUND_ALLOW_SWAPPED_ORDER_FOR_BASE_FILTER,
        "salvage_compound_bad": SALVAGE_COMPOUND_BAD,

        "existing_canonical_count": len(existing_canonical_pairs_clean),
        "new_canonical_count": len(new_canonical_pairs_clean),
        "canonical_merged_count": len(canonical_pairs_merged),

        "compound_main_count": len(compound_pairs_clean_main),
        "compound_recovered_count": len(compound_recovered_pairs),
        "compound_final_count": len(compound_canonical_pairs_clean),

        "final_merged_count": len(canonical_compound_pairs_merged),
        "final_missing_text_pairs_count": len(missing_text_pairs),

        "existing_canonical_bad_rows": existing_canonical_bad,
        "new_pairs_bad_rows": new_canonical_bad,
        "compound_bad_rows_main": compound_bad_main,
        "compound_still_bad_after_salvage": compound_still_bad,

        "new_pairs_raw_empty_items": res_new["raw_empty_items"],
        "new_pairs_raw_items_with_multiple_records": res_new["multi_record_raw_items"],
        "compound_raw_empty_items": res_compound["raw_empty_items"],
        "compound_raw_items_with_multiple_records": res_compound["multi_record_raw_items"],

        "new_pairs_modality_counts": res_new["modality_counts"],
        "compound_modality_counts": res_compound["modality_counts"],

        "new_pairs_bucket_counts": bucket_counts(new_canonical_by_bucket),
        "compound_bucket_counts": bucket_counts(compound_by_bucket),

        "canonical_merge_stats": canonical_merge_stats,
        "compound_internal_merge_stats": compound_internal_merge_stats,
        "final_merge_stats": final_merge_stats,
    }, f, indent=2)

# --------------------------------------------------
# Summary
# --------------------------------------------------

print("Existing canonical baseline:", len(existing_canonical_pairs_clean))
print("New canonical pairs from new_pairs:", len(new_canonical_pairs_clean))
print("New canonical pairs actually added:", len(new_canonical_pairs_only_to_add))
print("Canonical merged total:", len(canonical_pairs_merged))
print()

print("Compound main pairs:", len(compound_pairs_clean_main))
print("Compound recovered pairs:", len(compound_recovered_pairs))
print("Compound final total:", len(compound_canonical_pairs_clean))
print("Compound pairs actually added on top of canonical:", len(compound_pairs_only_to_add))
print()

print("Final canonical+compound merged pairs:", len(canonical_compound_pairs_merged))
print("Final canonical+compound merged texts:", len(canonical_compound_text_pairs_merged))
print("Missing text pairs:", len(missing_text_pairs))
print()

print("Bad existing canonical rows:", len(existing_canonical_bad))
print("Bad rows in new_pairs:", len(new_canonical_bad))
print("Bad rows in compound main:", len(compound_bad_main))
print("Still bad after compound salvage:", len(compound_still_bad))
print()

print("Saved:")
print(" -", NEW_CANONICAL_LABELED_PATH)
print(" -", NEW_CANONICAL_CLEAN_PATH)
print(" -", NEW_CANONICAL_TEXT_PATH)
print(" -", NEW_CANONICAL_ONLY_PATH)
print(" -", CANONICAL_MERGED_PAIRS_PATH)
print(" -", CANONICAL_MERGED_TEXTS_PATH)
print(" -", COMPOUND_CLEAN_PATH)
print(" -", COMPOUND_TEXTS_PATH)
print(" -", COMPOUND_LABELED_PATH)
print(" -", COMPOUND_ONLY_PATH)
print(" -", COMPOUND_RECOVERED_PATH)
print(" -", COMPOUND_STILL_BAD_PATH)
print(" -", FINAL_MERGED_PAIRS_PATH)
print(" -", FINAL_MERGED_TEXTS_PATH)
print(" -", FINAL_MISSING_TEXT_PATH)
print(" -", DIAG_PATH)
