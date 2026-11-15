"""Step 1 (select-cases): single-patient case reports and their citation-linked case pairs.

Rules:
  * keep only articles associated with exactly one patient record,
  * keep only links connecting two retained cases, remove self links,
  * count each linked pair once regardless of citation direction,
  * discard cases without a remaining link.
"""

from __future__ import annotations

import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .config import log, work_dir
from .ids import article_of_case, make_case_pair_id, normalize_case_id
from .io_utils import read_json, read_jsonl, write_json, write_jsonl


def read_pmc_patients_table(path):
    """Read the regenerated PMC-Patients collection (CSV, JSON list or JSONL)."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))  # patient summaries can be long
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    if suffix == ".json":
        data = read_json(path)
        return data if isinstance(data, list) else list(data.values())
    if suffix == ".jsonl":
        return read_jsonl(path)
    raise ValueError(f"Unsupported PMC-Patients file type: {path} (use .csv, .json or .jsonl)")


def parse_similar_patients(value):
    """`similar_patients` is a dict {patient_uid: similarity}; in CSV files it is a text literal."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {item: None for item in value}
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {item: None for item in parsed}
    return {}


def select_cases(cfg):
    table_path = cfg["paths"]["pmc_patients"]
    if not table_path:
        raise SystemExit("Set paths.pmc_patients in the configuration file.")
    records = read_pmc_patients_table(table_path)
    log(cfg, f"select-cases: read {len(records)} patient records from {table_path}")

    # Standardize identifiers and collect the similarity links of every case.
    links_by_case = {}
    unreadable_ids = 0
    for record in records:
        case_id = normalize_case_id(record.get("patient_uid"))
        if case_id is None:
            unreadable_ids += 1
            continue
        linked = links_by_case.setdefault(case_id, set())
        for other in parse_similar_patients(record.get("similar_patients")):
            other_id = normalize_case_id(other)
            if other_id is not None:
                linked.add(other_id)

    # Figures belong to articles, not patients: keep articles with exactly one patient.
    patients_per_article = Counter(article_of_case(case_id) for case_id in links_by_case)
    single_patient_cases = {
        case_id for case_id in links_by_case if patients_per_article[article_of_case(case_id)] == 1
    }

    # Undirected links between two retained cases, without self links.
    pair_keys = set()
    self_links = 0
    for case_id in single_patient_cases:
        for other_id in links_by_case[case_id]:
            if other_id == case_id:
                self_links += 1
            elif other_id in single_patient_cases:
                pair_keys.add(tuple(sorted((case_id, other_id))))

    linked_cases = sorted({case_id for pair in pair_keys for case_id in pair})
    case_pairs = sorted(pair_keys)

    out_dir = work_dir(cfg, "cases")
    write_jsonl([{"case_id": c, "pmcid": article_of_case(c)} for c in linked_cases],
                out_dir / "cases.jsonl")
    write_jsonl([{"case_pair_id": make_case_pair_id(a, b), "case_ids": [a, b]} for a, b in case_pairs],
                out_dir / "case_pairs.jsonl")

    stats = {
        "patient_records_read": len(records),
        "unreadable_patient_ids": unreadable_ids,
        "distinct_cases": len(links_by_case),
        "articles": len(patients_per_article),
        "single_patient_articles": sum(1 for n in patients_per_article.values() if n == 1),
        "multi_patient_articles": sum(1 for n in patients_per_article.values() if n > 1),
        "self_links_removed": self_links,
        "selected_cases_with_links": len(linked_cases),
        "candidate_case_pairs": len(case_pairs),
    }
    write_json(stats, out_dir / "stats.json")
    log(cfg, f"select-cases: {len(linked_cases)} cases form {len(case_pairs)} candidate case pairs")
    return stats
