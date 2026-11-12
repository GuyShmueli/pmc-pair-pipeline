"""Step 5 (prepare-pairs): check every candidate case pair and gather the model inputs.

Each candidate pair is checked in this order; the first failed check is recorded:
  1. article_unavailable        an article could not be downloaded or read
  2. animal_case                an article reports an animal case (see animal_filter.py)
  3. citation_not_confirmed     neither reference list contains the other article
  4. missing_case_description   no text under a case-report heading in one article
  5. no_retained_figure         a case has no captioned figure left after screening
Pairs that pass every check are annotation-ready.

Two files feed the language-model stages, which run on the annotation-ready pairs:
  citation_pairs.jsonl    every pair whose citation is confirmed (checks 1-3): titles,
                          abstracts and citation passages. The entries of annotation-ready
                          pairs are the input of the citation analysis and the source of
                          the exported citation records.
  annotation_ready.jsonl  pairs that pass all checks: case descriptions and captions.
                          Input of question generation, answer generation and pair
                          selection.

Case A is the citing case and Case B the cited case in all prompts.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

from .animal_filter import is_animal_case
from .citations import verify_citation
from .config import log, work_dir
from .ids import article_of_case
from .image_filter import screening_results
from .io_utils import read_jsonl, write_json
from .jats import article_metadata, case_description, citation_passages, normalize_whitespace, parse_xml
from .pmc_download import downloaded_articles


@lru_cache(maxsize=32)
def load_article(xml_path, strict_non_human):
    """Parse one article and extract what the pair checks need.

    Pairs are processed sorted by case id, so consecutive pairs often share an article;
    a small cache per worker process avoids parsing it again.
    """
    tree = parse_xml(xml_path)
    if tree is None:
        return None
    meta = article_metadata(tree)
    flagged, reasons = is_animal_case(meta["title_spaced"], normalize_whitespace(meta["abstract"]),
                                      meta["journal_title"], strict_non_human)
    return {**meta, "case_description": case_description(tree),
            "animal_case": flagged, "animal_case_reasons": reasons, "tree": tree}


def article_summary(pmcid, info):
    if info is None:
        return {"pmcid": pmcid, "readable": False}
    return {"pmcid": pmcid, "readable": True, "title": info["title"], "doi": info["doi"],
            "pmid": info["pmid"], "journal_title": info["journal_title"],
            "has_case_description": bool(info["case_description"]),
            "references": len(info["references"]),
            "animal_case": info["animal_case"], "animal_case_reasons": info["animal_case_reasons"]}


def evaluate_pair(task):
    """Checks 1-4 for one candidate pair (runs in a worker process); check 5 follows in prepare_pairs."""
    case_pair_id, case_a, case_b, xml_a, xml_b, strict_non_human, title_fallback = task
    info = {case_a: load_article(xml_a, strict_non_human) if xml_a else None,
            case_b: load_article(xml_b, strict_non_human) if xml_b else None}
    result = {"case_pair_id": case_pair_id,
              "articles": [article_summary(article_of_case(c), info[c]) for c in (case_a, case_b)]}

    if info[case_a] is None or info[case_b] is None:
        return {**result, "status": "article_unavailable"}
    if info[case_a]["animal_case"] or info[case_b]["animal_case"]:
        return {**result, "status": "animal_case"}
    link = verify_citation(case_a, info[case_a], case_b, info[case_b], title_fallback)
    if link is None:
        return {**result, "status": "citation_not_confirmed"}

    citing, cited = info[link["citing_case"]], info[link["cited_case"]]
    result["citation"] = {
        "case_pair_id": case_pair_id,
        "citing_case": link["citing_case"], "cited_case": link["cited_case"],
        "citing_pmcid": article_of_case(link["citing_case"]), "cited_pmcid": article_of_case(link["cited_case"]),
        "match_type": link["match_type"], "ref_id": link["ref_id"],
        "citing_title": citing["title"], "citing_abstract": citing["abstract"],
        "cited_title": cited["title"], "cited_abstract": cited["abstract"],
        "citation_passages": citation_passages(citing["tree"], link["ref_id"]),
    }
    if not citing["case_description"] or not cited["case_description"]:
        return {**result, "status": "missing_case_description"}
    result["descriptions"] = {"case_a_description": citing["case_description"],
                              "case_b_description": cited["case_description"]}
    return {**result, "status": "passed_text_checks"}


def retained_captions_by_case(cfg):
    """{case_id: {image_id: caption}} for captioned figures that passed the image screen."""
    screening = screening_results(cfg)
    captions = {}
    for figure in read_jsonl(work_dir(cfg, "figures") / "figures.jsonl"):
        result = screening.get(figure["image_id"])
        if result is None:
            raise SystemExit(f"Figure {figure['image_id']} has not been screened; run filter-images first.")
        if not result["flagged"]:
            captions.setdefault(figure["case_id"], {})[figure["image_id"]] = figure["caption"]
    return captions


def prepare_pairs(cfg):
    out_dir = work_dir(cfg, "pairs")
    articles_dir = work_dir(cfg, "articles")
    available = downloaded_articles(cfg)
    captions = retained_captions_by_case(cfg)
    strict = bool(cfg["animal_filter"]["strict_non_human"])
    title_fallback = bool(cfg["citations"]["title_fallback"])

    def xml_path(case_id):
        pmcid = article_of_case(case_id)
        return str(articles_dir / f"PMC{pmcid}" / "article.xml") if pmcid in available else None

    case_pairs = read_jsonl(work_dir(cfg, "cases") / "case_pairs.jsonl")
    tasks = [(p["case_pair_id"], p["case_ids"][0], p["case_ids"][1],
              xml_path(p["case_ids"][0]), xml_path(p["case_ids"][1]), strict, title_fallback)
             for p in case_pairs]
    log(cfg, f"prepare-pairs: checking {len(tasks)} candidate case pairs")

    status_counts, match_types, passage_counts = Counter(), Counter(), Counter()
    seen_articles = set()
    names = ("articles", "candidate_status", "citation_pairs", "annotation_ready")
    paths = {name: out_dir / f"{name}.jsonl" for name in names}
    files = {name: open(str(path) + ".tmp", "w", encoding="utf-8", newline="\n") for name, path in paths.items()}
    try:
        with ProcessPoolExecutor(max_workers=int(cfg["workers"])) as pool:
            for result in pool.map(evaluate_pair, tasks, chunksize=64):
                for summary in result["articles"]:
                    if summary["pmcid"] not in seen_articles:
                        seen_articles.add(summary["pmcid"])
                        files["articles"].write(_json_line(summary))

                status, citation = result["status"], result.get("citation")
                if citation:
                    match_types[citation["match_type"]] += 1
                    passage_counts["with_passage" if citation["citation_passages"] else "without_passage"] += 1
                    files["citation_pairs"].write(_json_line(citation))
                if status == "passed_text_checks":
                    case_a, case_b = citation["citing_case"], citation["cited_case"]
                    if captions.get(case_a) and captions.get(case_b):
                        status = "ready"
                        files["annotation_ready"].write(_json_line({
                            "case_pair_id": result["case_pair_id"],
                            "citing_case": case_a, "cited_case": case_b,
                            **result["descriptions"],
                            "case_a_captions": dict(sorted(captions[case_a].items())),
                            "case_b_captions": dict(sorted(captions[case_b].items())),
                        }))
                    else:
                        status = "no_retained_figure"
                status_counts[status] += 1
                files["candidate_status"].write(_json_line(
                    {"case_pair_id": result["case_pair_id"], "status": status,
                     **({"citing_case": citation["citing_case"], "match_type": citation["match_type"]}
                        if citation else {})}))
    finally:
        for f in files.values():
            f.close()
    for name, path in paths.items():
        os.replace(str(path) + ".tmp", path)

    stats = {
        "candidate_case_pairs": len(tasks),
        "status_counts": dict(status_counts),
        "citation_confirmed_pairs": sum(match_types.values()),
        "annotation_ready_pairs": status_counts["ready"],
        "confirmed_citation_match_types": dict(match_types),
        "citation_passages": dict(passage_counts),
    }
    write_json(stats, out_dir / "stats.json")
    log(cfg, f"prepare-pairs: {stats['citation_confirmed_pairs']} pairs with a confirmed citation, "
             f"{stats['annotation_ready_pairs']} annotation-ready; {dict(status_counts)}")
    return stats


def _json_line(record):
    return json.dumps(record, ensure_ascii=False) + "\n"


def citation_pairs(cfg):
    """Case pairs with a confirmed citation: titles, abstracts and citation passages."""
    return read_jsonl(Path(cfg["paths"]["work_dir"]) / "pairs" / "citation_pairs.jsonl")


def annotation_ready_pairs(cfg):
    """Annotation-ready case pairs (input of all language-model stages): case descriptions and captions."""
    return read_jsonl(Path(cfg["paths"]["work_dir"]) / "pairs" / "annotation_ready.jsonl")
