"""Article-disjoint train / validation / test split of the PMC-PaIR image graph.

Images are nodes and positive image pairs are edges. The split is drawn in three steps:

1. Connected components of the image graph are found.
2. Components that contain images from the same source article are merged, transitively,
   into article groups. The source article of an image is the PMC article number at the
   start of its identifier (``9899453_1_1`` belongs to PMC9899453).
3. The groups are sorted by their smallest image identifier, compared as strings, and
   shuffled with ``random.Random(seed)``. They are then assigned whole, by group count:
   the first ``int(0.8 * N)`` groups go to train, the next ``int(0.1 * N)`` to val and
   the remaining groups to test, where N is the number of groups. Both products are
   rounded down; test receives the remainder.

Every image therefore receives one partition, and no positive pair and no source article
spans two partitions. Pairs and article links only decide which images stay together; they
add no pairs and change no annotation.

This module uses only the Python standard library, so the split can be regenerated and
checked without the rest of the pipeline (``scripts/generate_splits.py``).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

PARTITIONS = ("train", "val", "test")
DEFAULT_SEED = 42
DEFAULT_FRACTIONS = {"train": 0.8, "val": 0.1, "test": 0.1}

# <PMC article number>_<case index>_<figure index>, ASCII digits, article number without leading zero
IMAGE_ID = re.compile(r"([1-9][0-9]*)_[0-9]+_[0-9]+")


class SplitError(ValueError):
    """A split that does not satisfy the requirements; ``problems`` lists every failure."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems[:5]) + (" ..." if len(self.problems) > 5 else ""))


# ---------------------------------------------------------------- identifiers and pairs

def source_article(image_id):
    """PMC identifier of the article an image comes from: ``9899453_1_1`` -> ``PMC9899453``."""
    match = IMAGE_ID.fullmatch(image_id) if isinstance(image_id, str) else None
    if not match:
        raise ValueError(f"Not a PMC-PaIR image identifier: {image_id!r}")
    return f"PMC{match.group(1)}"


def normalize_pairs(pairs):
    """Unordered, de-duplicated pairs as sorted tuples, in sorted order."""
    unique = set()
    for first, second in pairs:
        unique.add((first, second) if first <= second else (second, first))
    return sorted(unique)


def pair_problems(pairs, max_examples=3):
    """Pair records that a released set of positive pairs must not contain."""
    problems = []
    self_pairs = [pair for pair in pairs if pair[0] == pair[1]]
    if self_pairs:
        problems.append(f"pairs: {len(self_pairs)} pairs join an image with itself, e.g. {self_pairs[:max_examples]}")
    repeated = [pair for pair, count in Counter(tuple(sorted(p)) for p in pairs).items() if count > 1]
    if repeated:
        problems.append(f"pairs: {len(repeated)} pairs occur more than once, e.g. {sorted(repeated)[:max_examples]}")
    malformed = sorted({image_id for pair in pairs for image_id in pair
                        if not (isinstance(image_id, str) and IMAGE_ID.fullmatch(image_id))})
    if malformed:
        problems.append(f"pairs: {len(malformed)} malformed image identifiers, e.g. {malformed[:max_examples]}")
    return problems


# ---------------------------------------------------------------- groups

class _UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first, second):
        first, second = self.find(first), self.find(second)
        if first != second:
            self.parent[max(first, second)] = min(first, second)

    def groups(self):
        members = defaultdict(list)
        for item in sorted(self.parent):
            members[self.find(item)].append(item)
        # every group is sorted, and the groups are ordered by their smallest image id
        return sorted(members.values(), key=lambda group: group[0])


def article_groups(image_ids, pairs):
    """Return (components, groups) as lists of sorted image-id lists, each ordered by smallest id.

    components: connected components of the pair graph;
    groups: components merged transitively when they share a source article.
    """
    images = sorted(set(image_ids))
    union_find = _UnionFind(images)
    for first, second in normalize_pairs(pairs):
        if first not in union_find.parent or second not in union_find.parent:
            raise ValueError(f"Pair endpoint outside the image set: {(first, second)!r}")
        union_find.union(first, second)
    components = union_find.groups()
    first_image_of_article = {}
    for image_id in images:
        article = source_article(image_id)
        if article in first_image_of_article:
            union_find.union(first_image_of_article[article], image_id)
        else:
            first_image_of_article[article] = image_id
    return components, union_find.groups()


# ---------------------------------------------------------------- drawing the split

def check_seed(seed):
    """The seed must be a non-negative integer (random.Random would accept None, strings or
    negative numbers, which give an irreproducible or a different split)."""
    if type(seed) is not int or seed < 0:
        raise ValueError(f"The split seed must be a non-negative integer, got {seed!r}")
    return seed


def check_fractions(fractions):
    """(train, val, test) shares of article groups: three non-negative numbers summing to 1."""
    if isinstance(fractions, dict):
        if set(fractions) != set(PARTITIONS):
            raise ValueError(f"The split fractions must give {PARTITIONS}, got {sorted(fractions)}")
        fractions = [fractions[name] for name in PARTITIONS]
    values = tuple(fractions)
    if (len(values) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)
            or any(not math.isfinite(v) or v < 0 for v in values) or not math.isclose(sum(values), 1.0)):
        raise ValueError(f"The split fractions must be three non-negative numbers summing to 1, got {fractions!r}")
    return tuple(float(v) for v in values)


def group_counts(n_groups, fractions=DEFAULT_FRACTIONS):
    """Groups per partition: int(f_train * N) and int(f_val * N), rounded down; test gets the rest."""
    train, val, _ = check_fractions(fractions)
    n_train, n_val = int(train * n_groups), int(val * n_groups)
    return {"train": n_train, "val": n_val, "test": n_groups - n_train - n_val}


def assign_groups(groups, seed=DEFAULT_SEED, fractions=DEFAULT_FRACTIONS):
    """Shuffle the groups with random.Random(seed) and assign them whole, by group count."""
    order = sorted((sorted(group) for group in groups), key=lambda group: group[0])
    random.Random(check_seed(seed)).shuffle(order)
    counts = group_counts(len(order), fractions)
    split = {}
    for index, group in enumerate(order):
        name = ("train" if index < counts["train"]
                else "val" if index < counts["train"] + counts["val"] else "test")
        for image_id in group:
            split[image_id] = name
    return dict(sorted(split.items()))


def generate_split(image_ids, pairs, seed=DEFAULT_SEED, fractions=DEFAULT_FRACTIONS):
    """The article-disjoint split of the given images and pairs (see the module docstring)."""
    _, groups = article_groups(image_ids, pairs)
    split = assign_groups(groups, seed, fractions)
    validate_split(split, image_ids, pairs)
    return split


# ---------------------------------------------------------------- checking a split

def split_problems(split, image_ids, pairs, max_examples=3):
    """Every way in which `split` fails the requirements, as messages (empty list: valid).

    Requirements: exactly the given images, one known partition each, every pair endpoint
    among them, and no source article and no positive pair across partitions.
    """
    problems = []
    images = set(image_ids)
    missing, extra = sorted(images - split.keys()), sorted(split.keys() - images)
    if missing:
        problems.append(f"split: {len(missing)} images have no partition, e.g. {missing[:max_examples]}")
    if extra:
        problems.append(f"split: {len(extra)} images are not in the image pairs, e.g. {extra[:max_examples]}")
    unknown = sorted({str(value) for value in split.values() if value not in PARTITIONS})
    if unknown:
        problems.append(f"split: unknown partition names {unknown}")

    partitions_of_article, malformed = defaultdict(set), []
    for image_id, name in split.items():
        try:
            partitions_of_article[source_article(image_id)].add(name)
        except ValueError:
            malformed.append(image_id)
    if malformed:
        problems.append(f"split: {len(malformed)} malformed image identifiers, e.g. {sorted(map(str, malformed))[:max_examples]}")
    spanning = sorted(article for article, names in partitions_of_article.items() if len(names) > 1)
    if spanning:
        problems.append(f"split: {len(spanning)} source articles span partitions, e.g. {spanning[:max_examples]}")

    unique_pairs = normalize_pairs(pairs)
    outside = [pair for pair in unique_pairs if pair[0] not in images or pair[1] not in images]
    if outside:
        problems.append(f"split: {len(outside)} pair endpoints are outside the image set, e.g. {outside[:max_examples]}")
    crossing = [pair for pair in unique_pairs if pair[0] in split and pair[1] in split
                and split[pair[0]] != split[pair[1]]]
    if crossing:
        problems.append(f"split: {len(crossing)} pairs cross partitions, e.g. {crossing[:max_examples]}")
    return problems


def integrity_counts(split, image_ids, pairs):
    """Counts behind the requirements of split_problems (all zero for a valid split)."""
    images = set(image_ids)
    partitions_of_article, malformed = defaultdict(set), 0
    for image_id, name in split.items():
        try:
            partitions_of_article[source_article(image_id)].add(name)
        except ValueError:
            malformed += 1
    unique_pairs = normalize_pairs(pairs)
    return {
        "images_without_partition": len(images - split.keys()),
        "partitioned_images_not_in_pairs": len(split.keys() - images),
        "unknown_partition_names": sum(1 for name in split.values() if name not in PARTITIONS),
        "malformed_image_identifiers": malformed,
        "source_articles_across_partitions": sum(1 for names in partitions_of_article.values() if len(names) > 1),
        "pairs_across_partitions": sum(1 for a, b in unique_pairs
                                       if a in split and b in split and split[a] != split[b]),
    }


def empty_partitions(split):
    """Partitions without images (possible for very few groups, e.g. val when 0.1 * N < 1)."""
    present = set(split.values())
    return [name for name in PARTITIONS if name not in present]


def validate_split(split, image_ids, pairs):
    """Raise SplitError if the split fails any requirement of split_problems; return it otherwise."""
    problems = split_problems(split, image_ids, pairs)
    if problems:
        raise SplitError(problems)
    return split


def compare_splits(expected, actual, max_examples=3):
    """Image-by-image comparison of two splits."""
    common = expected.keys() & actual.keys()
    differing = sorted(image_id for image_id in common if expected[image_id] != actual[image_id])
    return {
        "identical": expected == actual,
        "differing_assignments": len(differing),
        "only_in_expected": len(expected.keys() - actual.keys()),
        "only_in_actual": len(actual.keys() - expected.keys()),
        "examples": differing[:max_examples],
    }


def split_statistics(split, pairs, groups=None, components=None):
    """Images, pairs, groups, components and source articles per partition (computed)."""
    unique_pairs = normalize_pairs(pairs)
    if groups is None or components is None:
        components, groups = article_groups(split, unique_pairs)

    def per_partition(units):
        return dict(Counter(split[unit[0]] for unit in units))

    articles = {}
    for image_id, name in split.items():
        articles.setdefault(source_article(image_id), name)
    pair_partitions = Counter(split[a] for a, b in unique_pairs if a in split and b in split and split[a] == split[b])
    stats = {name: {"images": 0, "pairs": 0, "groups": 0, "components": 0, "source_articles": 0}
             for name in PARTITIONS}
    for key, values in (("images", Counter(split.values())), ("pairs", pair_partitions),
                        ("groups", per_partition(groups)), ("components", per_partition(components)),
                        ("source_articles", Counter(articles.values()))):
        for name, count in values.items():
            stats[name][key] = count
    totals = {"images": len(split), "pairs": len(unique_pairs), "groups": len(groups),
              "components": len(components), "source_articles": len(articles)}
    return {"partitions": stats, "totals": totals}


# ---------------------------------------------------------------- files

def split_to_bytes(split):
    """The file format of image_splits.json: sorted keys, 2-space indent, final newline."""
    return (json.dumps(split, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_split(split, path, overwrite=False):
    """Write a split file; without overwrite, the file is created exclusively (never replaced)."""
    path = Path(path)
    data = split_to_bytes(split)
    if not overwrite:
        if os.path.lexists(path):
            raise FileExistsError(f"Refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as handle:
            handle.write(data)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _object_without_repeated_keys(items):
    keys = [key for key, _ in items]
    repeated = sorted(key for key, count in Counter(keys).items() if count > 1)
    if repeated:
        raise ValueError(f"repeated keys {repeated[:3]}")
    return dict(items)


def read_split(path):
    """A split file {image_id: "train" | "val" | "test"}; repeated keys are an error."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            split = json.load(handle, object_pairs_hook=_object_without_repeated_keys)
    except ValueError as error:
        raise ValueError(f"{path}: not a valid split file ({error})") from None
    if not isinstance(split, dict):
        raise ValueError(f"{path}: expected a JSON object image_id -> partition")
    return split


def read_pairs(path):
    """Positive pairs from image_pairs.json (records with "pair_id"), a JSON list of
    two-element lists, or a JSONL file of records with "pair_id" (every line must parse)."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as handle:
        if path.suffix == ".jsonl":
            records = []
            for number, line in enumerate(handle, 1):
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        raise ValueError(f"{path}: line {number} is not valid JSON") from None
        else:
            records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected a list of pair records")
    pairs = []
    for index, record in enumerate(records):
        pair = record.get("pair_id") if isinstance(record, dict) else record
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(i, str) for i in pair):
            raise ValueError(f"{path}: record {index} has no pair_id of two image identifiers")
        pairs.append((pair[0], pair[1]))
    return pairs


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
