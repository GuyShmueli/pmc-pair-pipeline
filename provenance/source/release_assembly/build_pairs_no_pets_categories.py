from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path


ANNOTATION_DIR = Path(__file__).resolve().parent
DATASET_DIR = ANNOTATION_DIR.parent

PAIRS_PATH = DATASET_DIR / "pairs_no_pets.json"
PAIR_ANNOTATIONS_PATH = ANNOTATION_DIR / "image_pair_annotations.csv"
OUTPUT_PATH = DATASET_DIR / "pairs_no_pets_categories.json"


def pair_key(pair: list[str] | tuple[str, str]) -> tuple[str, str]:
    if len(pair) != 2:
        raise ValueError(f"Expected exactly two image IDs, got {pair!r}")
    left, right = str(pair[0]), str(pair[1])
    if not left or not right or left == right:
        raise ValueError(f"Invalid pair: {pair!r}")
    return tuple(sorted((left, right)))


def load_pair_categories() -> dict[tuple[str, str], dict[str, str]]:
    categories_by_pair: dict[tuple[str, str], dict[str, str]] = {}

    with PAIR_ANNOTATIONS_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required_columns = {
            "source_pair_left",
            "source_pair_right",
            "modality",
            "anatomy",
            "diagnosis",
        }
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "Missing columns in image_pair_annotations.csv: "
                f"{sorted(missing_columns)}"
            )

        for row_number, row in enumerate(reader, start=2):
            key = pair_key((row["source_pair_left"], row["source_pair_right"]))
            categories = {
                "modality": row["modality"].strip(),
                "anatomy": row["anatomy"].strip(),
                "diagnosis": row["diagnosis"].strip(),
            }
            empty_fields = [name for name, value in categories.items() if not value]
            if empty_fields:
                raise ValueError(
                    f"Empty category fields at CSV row {row_number}: {empty_fields}"
                )

            previous = categories_by_pair.setdefault(key, categories)
            if previous != categories:
                raise ValueError(
                    f"Inconsistent categories for pair {key}: "
                    f"{previous!r} versus {categories!r}"
                )

    return categories_by_pair


def main() -> None:
    with PAIRS_PATH.open(encoding="utf-8") as handle:
        pairs = json.load(handle)

    if not isinstance(pairs, list):
        raise TypeError("pairs_no_pets.json must contain a JSON array")

    categories_by_pair = load_pair_categories()
    pair_keys = [pair_key(pair) for pair in pairs]

    if len(pair_keys) != len(set(pair_keys)):
        raise ValueError("pairs_no_pets.json contains duplicate unordered pairs")

    missing = set(pair_keys).difference(categories_by_pair)
    extra = set(categories_by_pair).difference(pair_keys)
    if missing or extra:
        raise ValueError(
            "Pair/category key mismatch: "
            f"missing_categories={len(missing)}, extra_categories={len(extra)}"
        )

    output_records = []
    for pair, key in zip(pairs, pair_keys, strict=True):
        output_records.append(
            {
                "pair_id": [str(pair[0]), str(pair[1])],
                **categories_by_pair[key],
            }
        )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=OUTPUT_PATH.parent,
        prefix=f".{OUTPUT_PATH.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(output_records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    os.replace(temp_path, OUTPUT_PATH)
    OUTPUT_PATH.chmod(0o644)

    digest = hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest()
    print(f"records={len(output_records)}")
    print(f"output={OUTPUT_PATH}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
