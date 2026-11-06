"""
Objective:
  For each pair of PMC IDs and their directories, this script will:
    1. Locate the corresponding JATS .nxml file.
    2. Extract its PMID.
    3. Parse out metadata (PMID, DOI, PMCID, title, abstract, references).
    4. Compare document pairs and collect any citation paragraphs
       (by DOI, PMID, PMCID or fallback substring-match on titles).

Usage:
 FIRST TIME:
  python process_pmc_citations.py \
    --data_path /path/to/data2 \
    --jsons_path /path/to/jsons \
    --bootstrap
 
  NEXT TIMES:
  python process_pmc_citations.py \
    --data_path /path/to/data2 \
    --jsons_path /path/to/jsons
"""
import os
import glob
import re
import json
import argparse
from lxml import etree

def get_xml_path(pmc_id: str, base_path):
    """ Locate and return the first `.nxml` file for a given PMC ID. """
    # strip the trailing version (e.g. “01”) off 'pmc_id'
    pmc_num = pmc_id[:-2]

    # build the full path by joining the base path with your two sub-dirs
    xml_dir = os.path.join(base_path, f'PMC{pmc_num}', f'{pmc_num}_1')

    # scan for the .nxml file
    for fname in os.listdir(xml_dir):
        if fname.endswith('.nxml'):
            return os.path.join(xml_dir, fname)

    return None

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



# --- 1. parse_nxml: gather pmid, doi, pmcid, main title, abstract, references ---

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

# --- 2. Minimally parse <mixed-citation> to skip authors/year/vol tags ---

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

# --- 3. get_all_citation_paragraphs: gather ALL paragraphs referencing ref_id ---

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

# 4. --- Fix minor apostrophe spacing ---

def fix_apostrophe_spacing(txt):
    """
    Insert a space if we see something like "in'burned" => "in ' burned".
    This is limited so we don't handle bigger 'typos', but it catches the
    missing space around quotes or apostrophes next to letters.
    """
    txt = re.sub(r"([A-Za-z0-9])'([A-Za-z0-9])", r"\1 ' \2", txt)
    return txt

# 5. --- Title Normalization ---

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

# 6. --- Substring-based fallback matching approach ---

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


# 7. --- Main process_pairs ---

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


def bootstrap_precompute(data_path, jsons_path):
    """
    Read matching_uids.json, run find_and_extract_pmids and get_xml_path on each pair,
    then dump matching_uids_pmid_list.json and matching_uids_xml_paths.json.
    """
    # load the raw pairs
    with open(os.path.join(jsons_path, 'matching_uids.json'), 'r') as f:
        matching_uids = json.load(f)

    # build directories and PMIDs
    matching_uids_paths = [
        [ os.path.join(data_path, f'PMC{uid[:-2]}', f'{uid[:-2]}_1')
          for uid in pair ]
        for pair in matching_uids
    ]
    matching_uids_pmid_list = [
        [ find_and_extract_pmids(d) for d in paths ]
        for paths in matching_uids_paths
    ]

    # locate the XML files
    matching_uids_xml_paths = [
        [ get_xml_path(uid, data_path) for uid in pair ]
        for pair in matching_uids
    ]

    # write out
    with open(os.path.join(jsons_path, 'matching_uids_pmid_list.json'), 'w') as f:
        json.dump(matching_uids_pmid_list, f)
    with open(os.path.join(jsons_path, 'matching_uids_xml_paths.json'), 'w') as f:
        json.dump(matching_uids_xml_paths, f)

    print("Bootstrap complete: generated matching_uids_pmid_list.json and matching_uids_xml_paths.json")


DATA_PATH = '<DATA_ROOT>/data2'
JSONS_PATH = '<DATA_ROOT>'

def main(data_path, jsons_path):
    # load the precomputed JSONs
    with open(os.path.join(jsons_path, 'matching_uids_pmid_list.json'), 'r') as f:
        pmid_list = json.load(f)
    with open(os.path.join(jsons_path, 'matching_uids_xml_paths.json'), 'r') as f:
        xml_list  = json.load(f)

    citation_list, valid_indices = process_pairs(xml_list, pmid_list)

    # write outputs
    with open(os.path.join(jsons_path, 'citation_list.json'), 'w') as f:
        json.dump(citation_list, f)
    with open(os.path.join(jsons_path, 'citation_valid_indices.json'), 'w') as f:
        json.dump(valid_indices, f)

    print(f"Processed {len(valid_indices)} citation pairs; results saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Locate JATS .nxml files, extract PMIDs/DOIs/PMCIDs, " \
        "parse metadata and compare citation pairs.")
    
    parser.add_argument(
        "--data_path",
        "-d",                # -d is a short option for data paths
        default=DATA_PATH,
        help="root directory where PMC folders live (default: %(default)s)")
    
    parser.add_argument(
        "--jsons_path",
        "-j",                # -j is a short option for JSONs paths
        default=JSONS_PATH,
        help="directory where matching_uids_*.json are stored (default: %(default)s)")
    
    parser.add_argument(
    "--bootstrap",
    "-b",                    # -b is a short option for bootstrap
    action="store_true",     # sets to Boolean, init with False
    help="(Re)generate the matching_uids_* JSON files before running")

    args = parser.parse_args()

    # If true, run the bootstrap step to precompute PMIDs and XML paths
    if args.bootstrap:
        bootstrap_precompute(args.data_path, args.jsons_path)
    # Run main()
    main(args.data_path, args.jsons_path)
