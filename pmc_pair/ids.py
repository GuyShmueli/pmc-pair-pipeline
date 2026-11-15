"""Identifier conventions used throughout the pipeline.

case id       "9899453-1"     numeric PMC article id + "-" + patient index (PMC-Patients style)
image id      "9899453_1_1"   numeric PMC article id, case index, figure extraction index
case pair id  "4023003-1__9899453-1"   the two case ids, sorted, joined by "__"

The figure extraction index counts every <fig> element of the article XML in
document order (starting at 1), including figures that are later skipped, so
image ids of one article can have gaps.
"""

from __future__ import annotations

import re

CASE_ID_PATTERN = re.compile(r"^(\d+)-(\d+)$")
IMAGE_ID_PATTERN = re.compile(r"^(\d+)_(\d+)_(\d+)$")


def normalize_case_id(raw):
    """Return the standard case id ("123-1") or None if the value cannot be read.

    Accepts the spellings found in PMC-Patients files: "123-1", "123_1", "PMC123-1".
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if text.upper().startswith("PMC"):
        text = text[3:]
    text = text.replace("_", "-")
    return text if CASE_ID_PATTERN.match(text) else None


def article_of_case(case_id):
    return case_id.split("-")[0]


def make_image_id(case_id, figure_index):
    pmcid, case_index = case_id.split("-")
    return f"{pmcid}_{case_index}_{figure_index}"


def case_of_image(image_id):
    pmcid, case_index, _ = image_id.split("_")
    return f"{pmcid}-{case_index}"


def make_case_pair_id(case_id_1, case_id_2):
    first, second = sorted((case_id_1, case_id_2))
    return f"{first}__{second}"
