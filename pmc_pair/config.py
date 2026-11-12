"""Load the YAML configuration and provide the work-directory layout.

Relative paths in the configuration file are resolved against the folder that
contains the configuration file, so the same config works from any directory.
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import yaml

REPOSITORY_DIR = Path(__file__).resolve().parents[1]
# SHA-256 of image_splits.json of this repository (the article-disjoint benchmark split; also in SHA256SUMS)
PUBLISHED_SPLIT_SHA256 = "b0b7be4be1597fa4e557fa4c5a51d0148361c2f253a604cf3df4a95a277c30eb"

# Built-in defaults; config.example.yaml lists the same values with short explanations.
DEFAULT_CONFIG = {
    "paths": {
        "pmc_patients": None,  # regenerated PMC-Patients table (required)
        "pmc_source": "https://pmc-oa-opendata.s3.amazonaws.com",  # PMC Cloud Service or a local mirror folder
        "work_dir": "data/work",
        "release_dir": "data/release",
        "prompts_dir": str(REPOSITORY_DIR / "prompts"),
        "label_rules": str(REPOSITORY_DIR / "label_taxonomy.json"),  # label vocabulary and mapping rules
        # split file to use instead of drawing one (default: the benchmark split); null draws a new split
        "existing_split": str(REPOSITORY_DIR / "image_splits.json"),
    },
    "workers": 4,
    "download": {
        "workers": 8,
        "timeout_seconds": 60,
        "retries": 3,
        "require_open_access": True,
        "prefer_non_manuscript": True,
        "max_articles": None,  # set a small number for a trial run
    },
    "figures": {
        "image_extensions": [".jpg", ".jpeg"],  # JPEG figure files only
    },
    "image_filter": {  # white-background screen, then Tesseract OCR
        "white_threshold": 250,
        "white_ratio_threshold": 0.5,
        "thumbnail_size": 384,
        "ocr_text_length_threshold": 200,
        "ocr_language": "eng",
        "ocr_config": "--oem 1 --psm 11 -c tessedit_do_invert=0",
        "ocr_timeout_seconds": 2.0,
        "tesseract_cmd": None,  # path to the tesseract program if it is not on PATH (e.g. on Windows)
    },
    "animal_filter": {
        "strict_non_human": False,  # dog and cat case reports (see animal_filter.py)
    },
    "citations": {
        "title_fallback": True,  # normalised title substring match after DOI, PMID and PMCID
    },
    "llm": {
        "sync_workers": 4,
        "stages": {  # model and reasoning effort per stage
            "citation_analysis": {"model": "gpt-5.4-mini", "reasoning_effort": "medium"},
            "question_generation": {"model": "gpt-5.4-nano", "reasoning_effort": "high"},
            "answer_generation": {"model": "gpt-5.4-nano", "reasoning_effort": "high"},
            "pair_selection": {"model": "gpt-5.4-mini", "reasoning_effort": "low"},
        },
        "batch": {
            "endpoint": "/v1/responses",
            "completion_window": "24h",
            "max_requests_per_file": 50000,
            "max_bytes_per_file": 190000000,
        },
    },
    "split": {  # article-disjoint split, see article_disjoint_split.py
        "seed": 42,  # random.Random(seed) shuffles the article groups
        "fractions": {"train": 0.8, "val": 0.1, "test": 0.1},  # share of article groups per partition
        "expected_sha256": PUBLISHED_SPLIT_SHA256,  # required SHA-256 of paths.existing_split (null: not checked)
        "verify_regeneration": True,  # paths.existing_split must equal the split regenerated from the pairs
    },
    "release": {
        "file_names": {
            "image_pairs": "image_pairs.json",
            "image_labels": "image_labels.jsonl",
            "label_rules": "label_taxonomy.json",
            "citation_records": "case_pair_citations.json",
            "split": "image_splits.json",
        },
        "copy_images": True,  # image files in ZIP archives
        "images_per_zip": 10000,
    },
}

PATH_KEYS = ["pmc_patients", "pmc_source", "work_dir", "release_dir", "prompts_dir",
             "label_rules", "existing_split"]


def _merge(defaults, overrides):
    merged = copy.deepcopy(defaults)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULT_CONFIG, user_config)

    base_dir = config_path.parent
    for key in PATH_KEYS:
        value = cfg["paths"].get(key)
        if value is not None and not str(value).strip():
            cfg["paths"][key] = value = None  # an empty path means "not set"
        if value is None or str(value).startswith(("http://", "https://")):
            continue
        path = Path(value).expanduser()
        cfg["paths"][key] = str(path if path.is_absolute() else (base_dir / path).resolve())

    cfg["config_path"] = str(config_path)
    return cfg


def work_dir(cfg, *parts):
    """Folder inside the work directory (created if needed)."""
    path = Path(cfg["paths"]["work_dir"]).joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log(cfg, message):
    """Print a progress message and keep a copy in <work_dir>/pipeline.log."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    log_path = Path(cfg["paths"]["work_dir"]) / "pipeline.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
