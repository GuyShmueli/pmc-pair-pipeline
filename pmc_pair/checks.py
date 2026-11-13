"""Consistency checks on the release files.

Only errors that would make the dataset wrong or misaligned are checked:
  * image pairs: two valid, different image ids from two different cases; no duplicate
    undirected pair; captions aligned with pair_id; non-empty descriptions;
    one caption per image across records,
  * labels: exactly one record per paired image; categories from the released
    vocabulary; "other" never mixed with other categories; identical to the labels
    recomputed from the released pairs, their captions and the label taxonomy,
  * split: covers exactly the paired images, valid partition names, no source article
    and no pair across partitions; with split settings, identical to the split
    regenerated from the released pairs (article_disjoint_split.py),
  * citation records: one record per case pair, and every image pair has the
    citation record of its two articles,
  * image files (ZIP archives): exactly one per paired image,
  * files listed in MANIFEST.json (written by export after these checks): present and
    unchanged (SHA-256).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .article_disjoint_split import (article_groups, assign_groups, compare_splits, empty_partitions,
                                     read_split, split_problems)
from .ids import IMAGE_ID_PATTERN, case_of_image
from .io_utils import read_json, read_jsonl, sha256_file

PARTITIONS = {"train", "val", "test"}
PAIR_KEYS = {"pair_id", "modality", "anatomy", "diagnosis", "captions"}
CITATION_KEYS = {"citing_case", "cited_case", "extracted_citation", "citation_reason"}


def check_release(release_dir, names=None, expect_images=False, split_settings=None):
    """Check the release files; with expect_images, image files must be present for every image.

    names: {"image_pairs": file name, ...} as in release.file_names (default: built-in names).
    split_settings: {"seed": ..., "fractions": ...} (the split section of the configuration);
    when given, the split must equal the split regenerated from the released pairs.
    """
    from .config import DEFAULT_CONFIG
    from .labels import FIELDS, caption_categories, combine_image_labels, load_label_rules, pair_categories

    release_dir = Path(release_dir)
    names = {**DEFAULT_CONFIG["release"]["file_names"], **(names or {})}
    problems = []

    def problem(message):
        problems.append(message)

    # ---------------------------------------------------------- image pairs
    pairs = read_json(release_dir / names["image_pairs"])
    seen_pairs, caption_of = set(), {}
    for index, record in enumerate(pairs):
        where = f"image_pairs[{index}]"
        if set(record) != PAIR_KEYS:
            problem(f"{where}: fields {sorted(record)} differ from {sorted(PAIR_KEYS)}")
            continue
        pair_id = record["pair_id"]
        if (not isinstance(pair_id, list) or len(pair_id) != 2
                or not all(isinstance(i, str) and IMAGE_ID_PATTERN.match(i) for i in pair_id)):
            problem(f"{where}: malformed pair_id {pair_id}")
            continue
        if case_of_image(pair_id[0]) == case_of_image(pair_id[1]):
            problem(f"{where}: both images belong to case {case_of_image(pair_id[0])}")
        key = tuple(sorted(pair_id))
        if key in seen_pairs:
            problem(f"{where}: duplicate pair {key}")
        seen_pairs.add(key)
        for field in ("modality", "anatomy", "diagnosis"):
            if not isinstance(record[field], str) or not record[field].strip():
                problem(f"{where}: empty {field}")
        captions = record["captions"]
        if [c.get("image_id") for c in captions] != pair_id:
            problem(f"{where}: captions are not aligned with pair_id")
            continue
        for caption in captions:
            if not caption.get("caption"):
                problem(f"{where}: empty caption for {caption['image_id']}")
            if caption_of.setdefault(caption["image_id"], caption["caption"]) != caption["caption"]:
                problem(f"{where}: image {caption['image_id']} has different captions in different records")
    image_ids = {image_id for key in seen_pairs for image_id in key}

    # ---------------------------------------------------------- labels
    rules = load_label_rules(release_dir / names["label_rules"])
    labels = read_jsonl(release_dir / names["image_labels"])
    label_ids = [record.get("image_id") for record in labels]
    if len(label_ids) != len(set(label_ids)):
        problem("image_labels: duplicate image ids")
    if set(label_ids) != image_ids:
        problem(f"image_labels: {len(set(label_ids) - image_ids)} extra and "
                f"{len(image_ids - set(label_ids))} missing images compared with image_pairs")
    for record in labels:
        if set(record) != {"image_id", "labels"} or set(record["labels"]) != set(FIELDS):
            problem(f"image_labels {record.get('image_id')}: fields differ from image_id and labels {list(FIELDS)}")
            continue
        for field in FIELDS:
            values = record["labels"][field]
            vocabulary = rules["fields"][field]["categories"]
            if not values or values != sorted(set(values)):
                problem(f"image_labels {record['image_id']}: {field} labels empty, unsorted or repeated")
            elif any(value not in vocabulary for value in values):
                problem(f"image_labels {record['image_id']}: {field} label outside the vocabulary: {values}")
            elif rules["other"] in values and len(values) > 1:
                problem(f"image_labels {record['image_id']}: '{rules['other']}' combined with other {field} labels")
    recomputed = {r["image_id"]: r["labels"] for r in combine_image_labels(
        pair_categories([record for record in pairs if set(record) == PAIR_KEYS], rules), rules["other"],
        caption_categories({i: c for i, c in caption_of.items() if isinstance(c, str)}, rules))}  # empty ones reported above
    different = [record.get("image_id") for record in labels
                 if recomputed.get(record.get("image_id")) != record.get("labels")]
    if different:
        problem(f"image_labels: {len(different)} of {len(labels)} images differ from the labels recomputed "
                f"from image_pairs (descriptions and captions) and the label taxonomy, e.g. {different[:3]}")

    # ---------------------------------------------------------- split
    try:
        split = read_split(release_dir / names["split"])
    except ValueError as error:
        problem(f"split: {error}")
        split = {}
    for message in split_problems(split, image_ids, seen_pairs):
        problem(message)
    if split_settings is not None:
        try:
            _, groups = article_groups(image_ids, seen_pairs)
            regenerated = assign_groups(groups, split_settings["seed"], split_settings["fractions"])
        except ValueError as error:
            problem(f"split: cannot regenerate the split: {error}")
        else:
            comparison = compare_splits(split, regenerated)
            if not comparison["identical"]:
                problem(f"split: {comparison['differing_assignments']} images differ from the split regenerated "
                        f"with seed {split_settings['seed']!r} and fractions {split_settings['fractions']}, "
                        f"e.g. {comparison['examples']}")

    # ---------------------------------------------------------- citation records
    citations = read_json(release_dir / names["citation_records"])
    article_pairs = set()
    for index, record in enumerate(citations):
        if set(record) != CITATION_KEYS:
            problem(f"citation_records[{index}]: fields {sorted(record)} differ from {sorted(CITATION_KEYS)}")
            continue
        if record["citing_case"] == record["cited_case"]:
            problem(f"citation_records[{index}]: article cites itself")
        key = frozenset((record["citing_case"], record["cited_case"]))
        if key in article_pairs:
            problem(f"citation_records[{index}]: duplicate record for {sorted(key)}")
        article_pairs.add(key)
        if not record["citation_reason"].strip():
            problem(f"citation_records[{index}]: empty citation_reason")
    for key in seen_pairs:
        articles = frozenset(f"PMC{image_id.split('_')[0]}" for image_id in key)
        if articles not in article_pairs:
            problem(f"image pair {key} has no citation record for {sorted(articles)}")
            break

    # ---------------------------------------------------------- image files
    archived = []  # image ids of the files in the ZIP archives
    for zip_path in sorted(release_dir.glob("images_part_*.zip")):
        with zipfile.ZipFile(zip_path) as archive:
            archived += [Path(name).stem for name in archive.namelist() if name.endswith(".jpg")]
    if expect_images or archived:
        extra, missing = set(archived) - image_ids, image_ids - set(archived)
        repeated = len(archived) - len(set(archived))
        if extra or missing or repeated:
            problem(f"image files: {len(extra)} extra, {len(missing)} missing and {repeated} repeated")

    # ---------------------------------------------------------- files recorded in MANIFEST.json
    manifest_path = release_dir / "MANIFEST.json"
    if manifest_path.exists():
        for name, recorded in read_json(manifest_path)["files"].items():
            path = release_dir / name
            if not path.exists() or sha256_file(path) != recorded["sha256"]:
                problem(f"{name}: missing or different from the SHA-256 recorded in MANIFEST.json")

    return {
        "passed": not problems,
        "problems": problems[:200],
        "problem_count": len(problems),
        "split_regeneration_checked": split_settings is not None,
        "warnings": ([] if split_settings is not None else
                     ["split not compared with the split regenerated from the pairs (split.verify_regeneration is false)"])
                    + [f"partition {name} has no images" for name in empty_partitions(split)],
        "counts": {"image_pairs": len(pairs), "images": len(image_ids), "labelled_images": len(labels),
                   "citation_records": len(citations), "image_files": len(archived),
                   "split_images": {name: sum(1 for v in split.values() if v == name) for name in sorted(PARTITIONS)},
                   "split_pairs": {name: sum(1 for a, b in seen_pairs if split.get(a) == split.get(b) == name)
                                   for name in sorted(PARTITIONS)}},
    }
