"""Read-only normalization of the original CHIPA citation extraction output.

The original file contains titles, abstracts and paragraph lists, but no IDs.
The index mapping links each extraction row back to the candidate UID/XML pair.
Candidate order is NOT citation direction: direction is resolved from the
saved citing/cited titles, with original XML title+abstract fallback.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as etree


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def load_original_records(root):
    """Return (normalized_rows, report), without writing or modifying sources.

    Rows contain the four common citation fields plus source_index and
    candidate_index for downstream provenance. IDs are article-level PMC IDs,
    matching the newer output's citing_case/cited_case convention.
    """
    root = Path(root)
    folder = root / "<DATA_ROOT>"
    records = json.loads((folder / "citation_extrac_list.json").read_text())
    indices = json.loads((folder / "citation_valid_indices_dict.json").read_text())
    pairs = json.loads((folder / "matching_uids.json").read_text())
    xml_paths = json.loads((folder / "matching_uids_xml_paths.json").read_text())
    reasons = json.loads((folder / "o3_mini_response_list.json").read_text())
    assert len(records) == len(indices) == len(reasons)
    assert sorted(indices.values()) == list(range(len(records)))

    # This title column is authoritative original release metadata. It need
    # not exactly reproduce JATS typography, hence the XML fallback below.
    csv.field_size_limit(100_000_000)
    titles = {}
    with (root / "<DATA_ROOT>/PMC-Patients.csv").open(newline="") as handle:
        for record in csv.DictReader(handle):
            titles[record["patient_uid"]] = record["title"]

    @lru_cache(maxsize=None)
    def xml_metadata(path):
        tree = etree.parse(path)
        local = lambda element: element.tag.rsplit("}", 1)[-1]
        title_elements = [
            element
            for group in tree.iter() if local(group) == "title-group"
            for element in group.iter() if local(element) == "article-title"
        ]
        if not title_elements:
            title_elements = [e for e in tree.iter() if local(e) == "article-title"]
        title = "".join(title_elements[0].itertext()).strip() if title_elements else ""
        abstract_parts = []
        for element in tree.iter():
            if local(element) != "abstract":
                continue
            text = " ".join(element.itertext()).strip()
            if text:
                abstract_parts.append(text)
        return title, " ".join(abstract_parts)

    stats = Counter()
    result = [None] * len(records)
    for candidate_index_string, source_index in indices.items():
        candidate_index = int(candidate_index_string)
        a, b = pairs[candidate_index]
        record = records[source_index]
        citing_title = _norm(record["citing_title"])
        cited_title = _norm(record["cited_title"])
        ta, tb = _norm(titles[a]), _norm(titles[b])
        forward = ta == citing_title and tb == cited_title
        reverse = tb == citing_title and ta == cited_title
        method = "original_csv_titles"

        if forward == reverse:
            (ta, aa), (tb, ab) = map(xml_metadata, xml_paths[candidate_index])
            ta, tb = _norm(ta), _norm(tb)
            forward = ta == citing_title and tb == cited_title
            reverse = tb == citing_title and ta == cited_title
            method = "xml_titles"
            if forward == reverse:
                sa = _norm(record["citing_abstract"])
                sb = _norm(record["cited_abstract"])
                forward = forward and _norm(aa) == sa and _norm(ab) == sb
                reverse = reverse and _norm(ab) == sa and _norm(aa) == sb
                method = "xml_titles_and_abstracts"
        if forward == reverse:
            raise ValueError(
                f"Unresolved original citation direction: source {source_index}, "
                f"candidate {candidate_index}, IDs {a}, {b}"
            )
        citing_uid, cited_uid = (a, b) if forward else (b, a)
        stats[method] += 1
        stats["forward" if forward else "reverse"] += 1
        paragraphs = record["citation_paragraphs"]
        assert isinstance(paragraphs, list)
        unique_paragraphs = []
        for paragraph in paragraphs:
            assert isinstance(paragraph, str)
            if paragraph.strip() and paragraph not in unique_paragraphs:
                unique_paragraphs.append(paragraph)
        stats["duplicate_paragraphs_removed"] += len(
            [p for p in paragraphs if p.strip()]
        ) - len(unique_paragraphs)
        passage = "\n\n".join(unique_paragraphs)
        reason = reasons[source_index]
        assert isinstance(reason, str)
        stats["empty_extracted_citation"] += not passage.strip()
        stats["empty_citation_reason"] += not reason.strip()
        result[source_index] = {
            "citing_case": "PMC" + citing_uid.split("-", 1)[0],
            "cited_case": "PMC" + cited_uid.split("-", 1)[0],
            "extracted_citation": passage,
            "citation_reason": reason,
            "source_index": source_index,
            "candidate_index": candidate_index,
        }
    assert all(record is not None for record in result)
    report = dict(stats)
    report["records"] = len(result)
    report["xml_files_used"] = xml_metadata.cache_info().currsize
    report["direction_resolution"] = (
        "Match both saved citing/cited titles to original CSV titles; when "
        "needed, match original XML titles and abstracts. Fail if unresolved."
    )
    return result, report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows, report = load_original_records(args.root)
    if args.output:
        args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, indent=2))
