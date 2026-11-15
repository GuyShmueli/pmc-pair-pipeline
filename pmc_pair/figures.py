"""Step 3 (extract-figures): one image record per article figure, with its caption.

For every <fig> of a downloaded article (document order = figure extraction index):
  * the figure needs a <graphic> reference and a non-empty <caption>,
  * the referenced image must exist as a JPEG file (.jpg / .jpeg).

PMC supplies most figures as a full-size JPEG plus a small GIF thumbnail with the same
base name; the JPEG is used. Figures without a JPEG file are skipped.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from .config import log, work_dir
from .ids import make_image_id
from .io_utils import read_jsonl, write_json, write_jsonl
from .jats import list_figures, parse_xml
from .pmc_download import downloaded_articles

KNOWN_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".gif", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def find_image_file(href, files_by_lower_name, image_extensions):
    """File in the article folder that holds the JPEG version of a <graphic> reference.

    The reference may or may not carry an extension; suffixes such as ".001" in
    "CRIC2020-4726529.001" are part of the name, not an extension.
    """
    name = os.path.basename(href.strip().replace("\\", "/").split("?")[0].split("#")[0])
    stem, extension = os.path.splitext(name)
    candidates = []
    if extension.lower() in image_extensions:
        candidates.append(name)
    base = stem if extension.lower() in KNOWN_IMAGE_EXTENSIONS else name
    candidates += [base + ext for ext in image_extensions]
    for candidate in candidates:
        if candidate.lower() in files_by_lower_name:
            return files_by_lower_name[candidate.lower()]
    return None


def extract_figures(cfg):
    image_extensions = [ext.lower() for ext in cfg["figures"]["image_extensions"]]
    articles_dir = work_dir(cfg, "articles")
    out_dir = work_dir(cfg, "figures")

    cases_by_article = {}
    for case in read_jsonl(work_dir(cfg, "cases") / "cases.jsonl"):
        cases_by_article.setdefault(case["pmcid"], []).append(case["case_id"])

    figures, issues = [], []
    articles = downloaded_articles(cfg)
    for pmcid in sorted(articles, key=int):
        article_dir = articles_dir / f"PMC{pmcid}"
        tree = parse_xml(article_dir / "article.xml")
        if tree is None:
            issues.append({"pmcid": pmcid, "reason": "unreadable_xml"})
            continue
        files_by_lower_name = {p.name.lower(): p.name for p in article_dir.iterdir() if p.is_file()}
        for case_id in cases_by_article.get(pmcid, []):  # one case per (single-patient) article
            for figure in list_figures(tree):
                image_id = make_image_id(case_id, figure["index"])
                if not figure["graphic_href"] or not figure["caption"]:
                    issues.append({"image_id": image_id, "reason": "missing_graphic_or_caption"})
                    continue
                image_file = find_image_file(figure["graphic_href"], files_by_lower_name, image_extensions)
                if image_file is None:
                    issues.append({"image_id": image_id, "reason": "no_jpeg_file",
                                   "graphic_href": figure["graphic_href"]})
                    continue
                figures.append({
                    "image_id": image_id,
                    "case_id": case_id,
                    "pmcid": pmcid,
                    "figure_index": figure["index"],
                    "figure_xml_id": figure["xml_id"],
                    "figure_label": figure["label"],
                    "graphic_href": figure["graphic_href"],
                    "image_file": (Path("articles") / f"PMC{pmcid}" / image_file).as_posix(),  # relative to work_dir
                    "caption": figure["caption"],
                })

    write_jsonl(figures, out_dir / "figures.jsonl")
    write_jsonl(issues, out_dir / "figure_issues.jsonl")
    stats = {
        "articles_read": len(articles),
        "figures_with_image_and_caption": len(figures),
        "skipped_figures": dict(Counter(issue["reason"] for issue in issues)),
    }
    write_json(stats, out_dir / "stats.json")
    log(cfg, f"extract-figures: {len(figures)} figures with a JPEG image and caption; skipped {stats['skipped_figures']}")
    return stats
