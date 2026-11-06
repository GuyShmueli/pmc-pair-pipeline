# --- lines 355-900 (citation verification and passages; updated-run passage gathering; updated-run citation records)
from __future__ import annotations

import os
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from lxml import etree


def fix_apostrophe_spacing(text: str) -> str:
    return re.sub(r"([A-Za-z0-9])'([A-Za-z0-9])", r"\1 ' \2", text or "")


def normalize_title_strict(text: str) -> str:
    text = fix_apostrophe_spacing(text or "")
    text = text.lower()
    text = re.sub(r"[-]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def titles_match_substring(
    citing_title: str,
    cited_title: str,
    *,
    min_cited_chars: int = 0,
    min_cited_tokens: int = 0,
) -> bool:
    norm_citing = normalize_title_strict(citing_title)
    norm_cited = normalize_title_strict(cited_title)

    if not norm_cited:
        return False
    if min_cited_chars and len(norm_cited) < min_cited_chars:
        return False
    if min_cited_tokens and len(norm_cited.split()) < min_cited_tokens:
        return False
    return norm_cited in norm_citing


def extract_title_from_mixed_citation(mixed_elem: etree._Element) -> str:
    sub_article_titles = mixed_elem.xpath('.//*[local-name()="article-title"]')
    if sub_article_titles:
        return " ".join(sub_article_titles[0].itertext()).strip()

    unwanted_tags = {
        "string-name",
        "person-group",
        "year",
        "volume",
        "issue",
        "fpage",
        "lpage",
        "pub-id",
        "edition",
        "conf-date",
        "name",
        "isbn",
        "editor",
    }

    def itertext_desired(root: etree._Element):
        for node in root.iter():
            if not isinstance(node, etree._Element):
                continue
            if not node.tag or not isinstance(node.tag, str):
                continue

            local_name = etree.QName(node).localname
            if local_name in unwanted_tags:
                continue

            if node.text:
                yield node.text
            if node.tail:
                yield node.tail

    parts = list(itertext_desired(mixed_elem))
    text = " ".join(part.strip() for part in parts if part and part.strip())
    return text.strip()


def _resolve_workers(workers: int | None) -> int:
    if workers is not None:
        return max(1, int(workers))

    env_value = os.environ.get("SLURM_CPUS_PER_TASK")
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            pass

    return os.cpu_count() or 1


def _chunksize(total_items: int, workers: int) -> int:
    return max(1, total_items // max(1, workers * 4))


def _build_reverse_reference_maps(
    references: dict[str, dict[str, str | None]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    reverse_doi: dict[str, str] = {}
    reverse_pmid: dict[str, str] = {}
    reverse_pmcid: dict[str, str] = {}

    for ref_id, ref_info in references.items():
        if ref_info.get("doi"):
            reverse_doi[ref_info["doi"]] = ref_id
        if ref_info.get("pmid"):
            reverse_pmid[ref_info["pmid"]] = ref_id
        if ref_info.get("pmcid"):
            reverse_pmcid[ref_info["pmcid"]] = ref_id

    return reverse_doi, reverse_pmid, reverse_pmcid


def _extract_doc_fields(root: etree._Element) -> dict[str, Any]:
    def get_article_id(id_type: str) -> str | None:
        elems = root.xpath(f'//*[local-name()="article-id"][@pub-id-type="{id_type}"]')
        if elems and elems[0].text:
            return elems[0].text.strip()
        return None

    paper_pmid = get_article_id("pmid")
    paper_doi = get_article_id("doi")
    paper_pmcid = get_article_id("pmc")

    title_elems = root.xpath('//*[local-name()="title-group"]//*[local-name()="article-title"]')
    if not title_elems:
        title_elems = root.xpath('//*[local-name()="article-title"]')
    paper_title = "".join(title_elems[0].itertext()).strip() if title_elems else ""

    abstract_elems = root.xpath('//*[local-name()="abstract"]')
    abs_texts: list[str] = []
    for abs_elem in abstract_elems:
        text = " ".join(abs_elem.itertext()).strip()
        if text:
            abs_texts.append(text)
    paper_abstract = " ".join(abs_texts).strip()

    references: dict[str, dict[str, str | None]] = {}
    ref_list = root.xpath('//*[local-name()="ref"]')
    for ref_node in ref_list:
        ref_id = ref_node.get("id")
        if not ref_id:
            continue

        doi_elems = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="doi"]')
        pmid_elems = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmid"]')
        pmcid_elems = ref_node.xpath('.//*[local-name()="pub-id"][@pub-id-type="pmc"]')

        cited_doi = doi_elems[0].text.strip() if doi_elems and doi_elems[0].text else None
        cited_pmid = pmid_elems[0].text.strip() if pmid_elems and pmid_elems[0].text else None
        cited_pmcid = pmcid_elems[0].text.strip() if pmcid_elems and pmcid_elems[0].text else None

        ec_title_elems = ref_node.xpath(
            './/*[local-name()="element-citation"]/*[local-name()="article-title"]'
        )
        if ec_title_elems:
            ref_title = " ".join(ec_title_elems[0].itertext()).strip()
        else:
            mixed_elems = ref_node.xpath('.//*[local-name()="mixed-citation"]')
            if mixed_elems:
                ref_title = extract_title_from_mixed_citation(mixed_elems[0])
            else:
                comment_elems = ref_node.xpath(
                    './/*[local-name()="element-citation"]/*[local-name()="comment"]'
                )
                if comment_elems:
                    ref_title = " ".join(comment_elems[0].itertext()).strip()
                else:
                    ref_title = ""

        references[ref_id] = {
            "doi": cited_doi,
            "pmid": cited_pmid,
            "pmcid": cited_pmcid,
            "title": ref_title,
        }

    reverse_doi, reverse_pmid, reverse_pmcid = _build_reverse_reference_maps(references)

    return {
        "pmid": paper_pmid,
        "doi": paper_doi,
        "pmcid": paper_pmcid,
        "title": paper_title,
        "abstract": paper_abstract,
        "references": references,
        "reverse_doi": reverse_doi,
        "reverse_pmid": reverse_pmid,
        "reverse_pmcid": reverse_pmcid,
    }


def parse_nxml(file_path: str | None) -> dict[str, Any] | None:
    if not file_path or not Path(file_path).is_file():
        return None

    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        tree = etree.parse(file_path, parser)
    except Exception:
        return None

    doc = _extract_doc_fields(tree.getroot())
    doc["tree"] = tree
    doc["file_path"] = file_path
    return doc


def parse_nxml_metadata(file_path: str | None) -> dict[str, Any] | None:
    if not file_path or not Path(file_path).is_file():
        return None

    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        tree = etree.parse(file_path, parser)
    except Exception:
        return None

    doc = _extract_doc_fields(tree.getroot())
    doc["file_path"] = file_path
    return doc


_DOC_CACHE: dict[str, dict[str, Any] | None] = {}
_DOC_METADATA_CACHE: dict[str, dict[str, Any] | None] = {}
_PARAGRAPH_CACHE: dict[tuple[str, str], list[str]] = {}


def get_doc(file_path: str | None) -> dict[str, Any] | None:
    if not file_path:
        return None
    if file_path not in _DOC_CACHE:
        _DOC_CACHE[file_path] = parse_nxml(file_path)
    return _DOC_CACHE[file_path]


def get_doc_metadata(file_path: str | None) -> dict[str, Any] | None:
    if not file_path:
        return None
    if file_path not in _DOC_METADATA_CACHE:
        _DOC_METADATA_CACHE[file_path] = parse_nxml_metadata(file_path)
    return _DOC_METADATA_CACHE[file_path]


def get_all_citation_paragraphs(tree: etree._ElementTree, ref_id: str) -> list[str]:
    xrefs = tree.xpath('.//*[local-name()="xref"][@ref-type="bibr" or @ref-type="ref"]')
    paragraphs: list[str] = []
    seen = set()

    for xref in xrefs:
        rid_attr = xref.get("rid", "") or ""
        rid_parts = rid_attr.split()
        if ref_id not in rid_parts:
            continue

        elem = xref
        while elem is not None:
            try:
                if etree.QName(elem).localname == "p":
                    break
            except Exception:
                pass
            elem = elem.getparent()

        if elem is None:
            continue

        paragraph_text = " ".join(elem.itertext()).strip()
        if paragraph_text and paragraph_text not in seen:
            paragraphs.append(paragraph_text)
            seen.add(paragraph_text)

    return paragraphs


def build_reference_maps(doc: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    reverse_doi = doc.get("reverse_doi")
    reverse_pmid = doc.get("reverse_pmid")
    reverse_pmcid = doc.get("reverse_pmcid")

    if isinstance(reverse_doi, dict) and isinstance(reverse_pmid, dict) and isinstance(reverse_pmcid, dict):
        return reverse_doi, reverse_pmid, reverse_pmcid

    return _build_reverse_reference_maps(doc.get("references", {}))


def find_citation_rid(
    citing_doc: dict[str, Any],
    cited_doc: dict[str, Any],
    *,
    title_fallback: bool = True,
    title_min_cited_chars: int = 0,
    title_min_cited_tokens: int = 0,
) -> tuple[str | None, str | None]:
    reverse_doi, reverse_pmid, reverse_pmcid = build_reference_maps(citing_doc)

    if cited_doc.get("doi") and cited_doc["doi"] in reverse_doi:
        return reverse_doi[cited_doc["doi"]], "doi"
    if cited_doc.get("pmid") and cited_doc["pmid"] in reverse_pmid:
        return reverse_pmid[cited_doc["pmid"]], "pmid"
    if cited_doc.get("pmcid") and cited_doc["pmcid"] in reverse_pmcid:
        return reverse_pmcid[cited_doc["pmcid"]], "pmcid"

    if title_fallback:
        cited_title = (cited_doc.get("title") or "").strip()
        if cited_title:
            for ref_id, ref_info in citing_doc["references"].items():
                if (
                    (ref_info.get("pmid") and ref_info["pmid"] == cited_doc.get("pmid"))
                    or (ref_info.get("doi") and ref_info["doi"] == cited_doc.get("doi"))
                    or (ref_info.get("pmcid") and ref_info["pmcid"] == cited_doc.get("pmcid"))
                ):
                    continue

                if titles_match_substring(
                    ref_info.get("title") or "",
                    cited_title,
                    min_cited_chars=title_min_cited_chars,
                    min_cited_tokens=title_min_cited_tokens,
                ):
                    return ref_id, "title_substring"

    return None, None


def _iter_unique_xml_paths(xml_pairs: list[list[str | None]]) -> list[str]:
    unique_paths: list[str] = []
    seen: set[str] = set()

    for pair in xml_pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        for path in pair:
            if not path:
                continue
            path_str = str(path)
            if path_str in seen:
                continue
            seen.add(path_str)
            unique_paths.append(path_str)

    return unique_paths


def _parse_doc_metadata_task(file_path: str) -> tuple[str, dict[str, Any] | None]:
    return file_path, parse_nxml_metadata(file_path)


def _populate_doc_metadata_cache(
    file_paths: list[str],
    workers: int | None = None,
) -> dict[str, dict[str, Any] | None]:
    if not file_paths:
        return {}

    unique_paths = [path for path in file_paths if path]
    missing_paths = [path for path in unique_paths if path not in _DOC_METADATA_CACHE]

    if missing_paths:
        resolved_workers = _resolve_workers(workers)
        if resolved_workers == 1 or len(missing_paths) == 1:
            for path in missing_paths:
                _DOC_METADATA_CACHE[path] = parse_nxml_metadata(path)
        else:
            with ProcessPoolExecutor(max_workers=resolved_workers) as executor:
                for path, doc in executor.map(
                    _parse_doc_metadata_task,
                    missing_paths,
                    chunksize=_chunksize(len(missing_paths), resolved_workers),
                ):
                    _DOC_METADATA_CACHE[path] = doc

    return {path: _DOC_METADATA_CACHE.get(path) for path in unique_paths}


def _extract_citation_paragraphs_for_file(
    task: tuple[str, tuple[str, ...]],
) -> tuple[str, dict[str, list[str]]]:
    file_path, ref_ids = task

    if not file_path or not Path(file_path).is_file():
        return file_path, {}

    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        tree = etree.parse(file_path, parser)
    except Exception:
        return file_path, {}

    paragraph_map: dict[str, list[str]] = {}
    for ref_id in ref_ids:
        paragraph_map[ref_id] = get_all_citation_paragraphs(tree, ref_id)

    return file_path, paragraph_map


def _populate_paragraph_cache(
    refs_by_file: dict[str, set[str]],
    workers: int | None = None,
) -> dict[tuple[str, str], list[str]]:
    tasks: list[tuple[str, tuple[str, ...]]] = []

    for file_path, ref_ids in refs_by_file.items():
        uncached_ref_ids = [
            ref_id for ref_id in sorted(ref_ids)
            if (file_path, ref_id) not in _PARAGRAPH_CACHE
        ]
        if uncached_ref_ids:
            tasks.append((file_path, tuple(uncached_ref_ids)))

    if not tasks:
        return _PARAGRAPH_CACHE

    resolved_workers = _resolve_workers(workers)

    if resolved_workers == 1 or len(tasks) == 1:
        results_iter = map(_extract_citation_paragraphs_for_file, tasks)
        for file_path, paragraph_map in results_iter:
            for ref_id, paragraphs in paragraph_map.items():
                _PARAGRAPH_CACHE[(file_path, ref_id)] = paragraphs
        return _PARAGRAPH_CACHE

    with ProcessPoolExecutor(max_workers=resolved_workers) as executor:
        results_iter = executor.map(
            _extract_citation_paragraphs_for_file,
            tasks,
            chunksize=_chunksize(len(tasks), resolved_workers),
        )
        for file_path, paragraph_map in results_iter:
            for ref_id, paragraphs in paragraph_map.items():
                _PARAGRAPH_CACHE[(file_path, ref_id)] = paragraphs

    return _PARAGRAPH_CACHE


def process_xml_pairs(
    xml_pairs: list[list[str | None]],
    *,
    pair_indices: list[int] | None = None,
    title_fallback: bool = True,
    title_min_cited_chars: int = 0,
    title_min_cited_tokens: int = 0,
    workers: int | None = None,
    verbose: bool = False,
) -> tuple[list[dict[str, Any]], list[int]]:
    if pair_indices is None:
        pair_indices = list(range(len(xml_pairs)))
    if len(pair_indices) != len(xml_pairs):
        raise ValueError("pair_indices must have the same length as xml_pairs")

    unique_paths = _iter_unique_xml_paths(xml_pairs)
    doc_cache = _populate_doc_metadata_cache(unique_paths, workers=workers)

    results: list[dict[str, Any]] = []
    valid_indices: list[int] = []
    refs_by_citing_file: dict[str, set[str]] = defaultdict(set)

    for xml_pair, original_index in zip(xml_pairs, pair_indices):
        if not isinstance(xml_pair, list) or len(xml_pair) != 2:
            continue

        xml_a, xml_b = xml_pair
        doc_a = doc_cache.get(str(xml_a)) if xml_a else None
        doc_b = doc_cache.get(str(xml_b)) if xml_b else None

        if not doc_a or not doc_b:
            if verbose:
                print(f"Skipping pair {original_index}: could not parse one or both NXML files.")
            continue

        rid, match_type = find_citation_rid(
            doc_a,
            doc_b,
            title_fallback=title_fallback,
            title_min_cited_chars=title_min_cited_chars,
            title_min_cited_tokens=title_min_cited_tokens,
        )
        if rid:
            results.append(
                {
                    "pair_index": original_index,
                    "citing_file": doc_a["file_path"],
                    "cited_file": doc_b["file_path"],
                    "match_type": match_type,
                    "match_ref_id": rid,
                    "citing_title": doc_a["title"],
                    "citing_abstract": doc_a["abstract"],
                    "citation_paragraphs": [],
                    "cited_title": doc_b["title"],
                    "cited_abstract": doc_b["abstract"],
                }
            )
            valid_indices.append(original_index)
            refs_by_citing_file[doc_a["file_path"]].add(rid)
            continue

        rid, match_type = find_citation_rid(
            doc_b,
            doc_a,
            title_fallback=title_fallback,
            title_min_cited_chars=title_min_cited_chars,
            title_min_cited_tokens=title_min_cited_tokens,
        )
        if rid:
            results.append(
                {
                    "pair_index": original_index,
                    "citing_file": doc_b["file_path"],
                    "cited_file": doc_a["file_path"],
                    "match_type": match_type,
                    "match_ref_id": rid,
                    "citing_title": doc_b["title"],
                    "citing_abstract": doc_b["abstract"],
                    "citation_paragraphs": [],
                    "cited_title": doc_a["title"],
                    "cited_abstract": doc_a["abstract"],
                }
            )
            valid_indices.append(original_index)
            refs_by_citing_file[doc_b["file_path"]].add(rid)

    _populate_paragraph_cache(refs_by_citing_file, workers=workers)

    for record in results:
        record["citation_paragraphs"] = _PARAGRAPH_CACHE.get(
            (record["citing_file"], record["match_ref_id"]),
            [],
        )

    return results, valid_indices


def find_common_indices(summary_valid_indices: list[int], citation_valid_indices: list[int]) -> list[int]:
    summary_set = set(summary_valid_indices)
    citation_set = set(citation_valid_indices)
    return [idx for idx in summary_valid_indices if idx in citation_set]
