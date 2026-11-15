"""Step 12 (split): article-disjoint train / val / test partitions.

The procedure is in article_disjoint_split.py. Connected components of the image graph
that share a source article are merged into groups. The groups are sorted by their
smallest image identifier (string order), shuffled with split.seed (42) and assigned
whole, 80/10/10 by group count (split.fractions; rounded down, test takes the rest).

paths.existing_split names a split file to use instead of a newly drawn one. By default
it is image_splits.json of this repository, the PMC-PaIR benchmark split. The file must:
  * have the SHA-256 in split.expected_sha256 (when that is set),
  * cover exactly the paired images, with no source article and no pair across
    partitions,
  * equal, image by image, the split regenerated from the pairs with split.seed and
    split.fractions (when split.verify_regeneration is true; a warning is recorded
    otherwise).
Set paths.existing_split to null to draw the split for another set of pairs.
"""

from __future__ import annotations

from pathlib import Path

from .article_disjoint_split import (article_groups, assign_groups, check_fractions, check_seed, compare_splits,
                                     empty_partitions, integrity_counts, pair_problems, read_pairs, read_split,
                                     sha256_file, split_problems, split_statistics, write_split)
from .config import log, work_dir
from .io_utils import write_json


def split_settings(cfg):
    """split.seed and split.fractions, checked; stop with an explanation if they are invalid."""
    try:
        check_seed(cfg["split"]["seed"])
        check_fractions(cfg["split"]["fractions"])
    except ValueError as error:
        raise SystemExit(f"Configuration: {error}.") from None
    return cfg["split"]["seed"], cfg["split"]["fractions"]


def regenerate(image_ids, pairs, cfg):
    """Groups, components and the split drawn with the configured seed and fractions."""
    seed, fractions = split_settings(cfg)
    try:
        components, groups = article_groups(image_ids, pairs)
    except ValueError as error:
        raise SystemExit(f"split: {error}") from None
    return assign_groups(groups, seed, fractions), groups, components


def load_existing_split(path, image_ids, pairs, regenerated, cfg):
    """Read a split file and check it; stop with an explanation if any check fails."""
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"paths.existing_split: {path} is not a file. Set it to null to draw a new split.")
    actual_sha256 = sha256_file(path)
    expected_sha256 = cfg["split"].get("expected_sha256")
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise SystemExit(f"{path} has SHA-256 {actual_sha256}, but split.expected_sha256 is {expected_sha256}. "
                         f"Use the repository's image_splits.json, or set split.expected_sha256 for another file.")
    try:
        split = read_split(path)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    problems = split_problems(split, image_ids, pairs)
    if problems:
        raise SystemExit(f"{path} does not fit the image pairs of this run:\n  " + "\n  ".join(problems)
                         + "\nSet paths.existing_split to null to draw a split for these pairs.")
    comparison = compare_splits(split, regenerated)
    warnings = []
    if cfg["split"].get("verify_regeneration", True):
        if not comparison["identical"]:
            raise SystemExit(f"{path} differs from the split regenerated with seed {cfg['split']['seed']!r} and "
                             f"fractions {cfg['split']['fractions']}: {comparison['differing_assignments']} images "
                             f"are assigned differently, e.g. {comparison['examples']}.")
    else:
        warnings.append("split.verify_regeneration is false: the split file was not required to equal the "
                        f"regenerated split ({comparison['differing_assignments']} images differ)")
    return split, {"method": "existing_split_file", "file": path.name, "sha256": actual_sha256,
                   "identical_to_regenerated": comparison["identical"]}, warnings


def make_split(cfg):
    pairs_path = work_dir(cfg, "image_pairs") / "image_pairs.jsonl"
    try:
        pairs = read_pairs(pairs_path)
    except ValueError as error:
        raise SystemExit(f"split: {error}") from None
    problems = pair_problems(pairs)
    if problems:
        raise SystemExit(f"split: {pairs_path} cannot be split:\n  " + "\n  ".join(problems))
    image_ids = sorted({image_id for pair in pairs for image_id in pair})
    regenerated, groups, components = regenerate(image_ids, pairs, cfg)

    existing = cfg["paths"].get("existing_split")
    warnings = []
    if existing:
        split, source, warnings = load_existing_split(existing, image_ids, pairs, regenerated, cfg)
    else:
        split, source = regenerated, {"method": "article_groups"}
    problems = split_problems(split, image_ids, pairs)
    if problems:  # cannot happen after the checks above; kept as a last guard
        raise SystemExit("split: " + "; ".join(problems))
    warnings += [f"partition {name} has no images" for name in empty_partitions(split)]

    out_dir = work_dir(cfg, "split")
    write_split(split, out_dir / "split.json", overwrite=True)
    stats = {
        **source,
        "seed": cfg["split"]["seed"],
        "fractions": cfg["split"]["fractions"],
        "unit": "article groups (connected components merged when they share a source article)",
        **split_statistics(split, pairs, groups, components),
        "integrity": integrity_counts(split, image_ids, pairs),
        "warnings": warnings,
        "split_sha256": sha256_file(out_dir / "split.json"),
    }
    write_json(stats, out_dir / "stats.json")
    counts = {name: (values["images"], values["pairs"]) for name, values in stats["partitions"].items()}
    log(cfg, f"split ({source['method']}): {stats['totals']['groups']} article groups; "
             f"(images, pairs) per partition {counts}")
    for warning in warnings:
        log(cfg, f"split: WARNING {warning}")
    return stats
