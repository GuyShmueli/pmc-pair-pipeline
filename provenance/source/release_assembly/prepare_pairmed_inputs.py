from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


# ============================================================
# EDIT THESE PATHS
# ============================================================

# Existing radiology-only merged source
OLD_RAD_PAIRS = Path(
    "<DATA_ROOT>/radiology_pairs_combined_merged_recovered_unordered_dedup.json"
)
OLD_RAD_TEXTS = Path(
    "<DATA_ROOT>/radiology_text_pairs_merged_recovered_unordered_dedup.json"
)

# New post-processing outputs
# Use the by-bucket file if you want flexible bucket inclusion/exclusion
NEW_BY_BUCKET = Path(
   "<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/postprocessed/positive_pairs_by_bucket.json"
)

# Optional: if you also have explicit new radiology-only files and want to merge them directly
NEW_RAD_PAIRS = None  # Path("/path/to/radiology_pairs_clean.json")
NEW_RAD_TEXTS = None  # Path("/path/to/radiology_text_pairs.json")

# Search order matters: first hit wins if an ID exists in both roots
IMAGE_ROOTS = [
    Path("<DATA_ROOT>/new_data"),
    Path("<DATA_ROOT>/data2"),
]

OUT_ROOT = Path("<DATA_ROOT>/prepared_pairmed_inputs")


# ============================================================
# HELPERS
# ============================================================

EXTS = ["jpg", "png", "jpeg", "JPG", "PNG", "JPEG"]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _coerce_top_level(obj: Any) -> list:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ["pairs", "edges", "data", "examples", "items"]:
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    raise ValueError("Unsupported JSON: expected a list or a dict containing a list-like key.")


def canonical_pair(pair: Any) -> tuple[str, str]:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError(f"Bad pair: {pair}")
    a = str(pair[0]).strip()
    b = str(pair[1]).strip()
    return tuple(sorted((a, b)))


def normalize_texts(caps: Any) -> list[str]:
    if caps is None:
        return []
    if isinstance(caps, str):
        caps = [caps]
    elif isinstance(caps, list) and len(caps) == 1 and isinstance(caps[0], list):
        caps = caps[0]
    elif not isinstance(caps, list):
        caps = [str(caps)]

    out = []
    seen = set()
    for c in caps:
        s = str(c).strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def article_id(image_id: str) -> str:
    return str(image_id).split("_", 1)[0]


def resolve_path_from_roots(roots: list[Path], image_id: str) -> str | None:
    pmc = article_id(image_id)
    for root in roots:
        for ext in EXTS:
            cand = root / f"PMC{pmc}" / f"{pmc}_1" / f"{image_id}.{ext}"
            if cand.exists():
                return str(cand)
    return None


def add_pair_text_filepair(
    pair_path: Path,
    text_path: Path,
    pair_to_texts: dict[tuple[str, str], set[str]],
) -> None:
    pairs = _coerce_top_level(load_json(pair_path))
    texts = _coerce_top_level(load_json(text_path))
    if len(pairs) != len(texts):
        raise ValueError(
            f"Length mismatch for {pair_path} vs {text_path}: "
            f"{len(pairs)} != {len(texts)}"
        )

    for pair, caps in zip(pairs, texts):
        key = canonical_pair(pair)
        pair_to_texts[key].update(normalize_texts(caps))


def add_bucket_source(
    by_bucket_path: Path,
    include_buckets: set[str],
    pair_to_texts: dict[tuple[str, str], set[str]],
) -> None:
    obj = load_json(by_bucket_path)
    if not isinstance(obj, dict):
        raise ValueError(f"{by_bucket_path} must be a dict of buckets")

    for bucket in include_buckets:
        payload = obj.get(bucket, {})
        if not isinstance(payload, dict):
            continue

        pairs = payload.get("pairs_clean", [])
        texts = payload.get("text_pairs", [])

        if len(pairs) != len(texts):
            raise ValueError(
                f"Bucket '{bucket}' in {by_bucket_path} has length mismatch: "
                f"{len(pairs)} != {len(texts)}"
            )

        for pair, caps in zip(pairs, texts):
            key = canonical_pair(pair)
            pair_to_texts[key].update(normalize_texts(caps))


def build_id2path_map(image_ids: set[str], roots: list[Path]) -> tuple[dict[str, str], list[str]]:
    id2path = {}
    missing = []
    for iid in sorted(image_ids):
        p = resolve_path_from_roots(roots, iid)
        if p is None:
            missing.append(iid)
        else:
            id2path[iid] = p
    return id2path, missing


def save_id2path_csv(path: Path, id2path: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "path"])
        writer.writeheader()
        for iid in sorted(id2path):
            writer.writerow({"id": iid, "path": id2path[iid]})


def prepare_dataset(
    dataset_name: str,
    include_old_radiology: bool,
    include_new_bucket_source: bool,
    include_buckets: set[str],
    include_new_explicit_radiology: bool = False,
) -> Path:
    outdir = OUT_ROOT / dataset_name
    outdir.mkdir(parents=True, exist_ok=True)

    pair_to_texts: dict[tuple[str, str], set[str]] = defaultdict(set)

    # Existing radiology source
    if include_old_radiology:
        add_pair_text_filepair(OLD_RAD_PAIRS, OLD_RAD_TEXTS, pair_to_texts)

    # New bucketed source
    if include_new_bucket_source:
        add_bucket_source(NEW_BY_BUCKET, include_buckets, pair_to_texts)

    # Optional explicit new radiology source
    if include_new_explicit_radiology:
        if NEW_RAD_PAIRS is None or NEW_RAD_TEXTS is None:
            raise ValueError("NEW_RAD_PAIRS / NEW_RAD_TEXTS are not set")
        add_pair_text_filepair(NEW_RAD_PAIRS, NEW_RAD_TEXTS, pair_to_texts)

    # Resolve images across both roots
    all_ids = {iid for pair in pair_to_texts.keys() for iid in pair}
    id2path, missing_ids = build_id2path_map(all_ids, IMAGE_ROOTS)
    available_ids = set(id2path.keys())

    # Drop pairs whose image(s) are missing
    kept_pairs = []
    kept_texts = []
    dropped_missing_pair_count = 0
    for pair in sorted(pair_to_texts.keys()):
        a, b = pair
        if a not in available_ids or b not in available_ids:
            dropped_missing_pair_count += 1
            continue
        kept_pairs.append([a, b])
        kept_texts.append(sorted(pair_to_texts[pair]))

    save_json(outdir / "pairs.json", kept_pairs)
    save_json(outdir / "texts.json", kept_texts)
    save_json(outdir / "missing_ids.json", missing_ids)
    save_id2path_csv(outdir / "id2path.csv", id2path)

    stats = {
        "dataset_name": dataset_name,
        "include_buckets": sorted(include_buckets),
        "num_unique_pairs_before_image_filter": len(pair_to_texts),
        "num_pairs_after_image_filter": len(kept_pairs),
        "num_unique_ids_before_image_filter": len(all_ids),
        "num_resolved_ids": len(id2path),
        "num_missing_ids": len(missing_ids),
        "num_pairs_dropped_due_to_missing_images": dropped_missing_pair_count,
    }
    save_json(outdir / "prep_stats.json", stats)

    print(f"\nPrepared: {dataset_name}")
    print(json.dumps(stats, indent=2))
    print(f"pairs-json:   {outdir / 'pairs.json'}")
    print(f"texts-json:   {outdir / 'texts.json'}")
    print(f"id2path-csv:  {outdir / 'id2path.csv'}")

    return outdir


if __name__ == "__main__":
    # 1) radiology only
    prepare_dataset(
        dataset_name="radiology_only",
        include_old_radiology=True,
        include_new_bucket_source=True,
        include_buckets={"radiology"},
        include_new_explicit_radiology=False,
    )

    # 2) broader version: radiology + cardiology + ophthalmology + other
    #    excluding pathology_microscopy and endoscopy
    prepare_dataset(
        dataset_name="broad_no_path_endo",
        include_old_radiology=True,
        include_new_bucket_source=True,
        include_buckets={"radiology", "cardiology", "ophthalmology", "other"},
        include_new_explicit_radiology=False,
    )
