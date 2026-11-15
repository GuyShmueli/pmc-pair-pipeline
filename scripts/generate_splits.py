#!/usr/bin/env python3
"""Regenerate the article-disjoint split from image pairs and compare it with image_splits.json.

    python scripts/generate_splits.py --pairs /path/to/zenodo-download/image_pairs.json

Procedure (pmc_pair/article_disjoint_split.py):
  1. Form the connected components of the image graph given by the positive pairs.
  2. Merge components that share a source article into groups.
  3. Sort the groups by their smallest image ID (string order) and shuffle them with
     random.Random(42).
  4. Assign whole groups by group count: the first int(0.8 * N) groups to train, the
     next int(0.1 * N) to val, the rest to test.

Checks (exit status 0 only if every check passes, 1 otherwise):
  * the pairs contain no repeated pair, no self-pair and no malformed image ID;
  * every image is assigned, and no source article and no pair crosses partitions;
  * the regenerated split equals the expected split image by image. The expected split
    is image_splits.json of this repository unless --expected names another file
    (or "none"). The packaged file must also have the SHA-256 listed in SHA256SUMS.

The computed counts are printed as JSON. --output writes the regenerated split (only if
every check passes) and --report writes the JSON summary; existing files are never
overwritten. Only the Python standard library is needed; the package does not have to be
installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:  # allows running from a checkout without installation
    sys.path.insert(0, str(REPOSITORY))

from pmc_pair.article_disjoint_split import (DEFAULT_FRACTIONS, DEFAULT_SEED, PARTITIONS,  # noqa: E402
                                             article_groups, assign_groups, check_fractions, check_seed,
                                             compare_splits, integrity_counts, pair_problems, read_pairs,
                                             read_split, sha256_file, split_problems, split_statistics,
                                             split_to_bytes, write_split)

PUBLISHED_SPLIT = REPOSITORY / "image_splits.json"


def non_negative_int(text):
    try:
        return check_seed(int(text))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", type=Path, required=True,
                        help="image_pairs.json of the release (or a JSON list of [image_id, image_id])")
    parser.add_argument("--expected", default=str(PUBLISHED_SPLIT),
                        help='split to compare with (default: image_splits.json of this repository); "none" skips it')
    parser.add_argument("--output", type=Path, help="write the regenerated split here (new file)")
    parser.add_argument("--report", type=Path, help="write the JSON summary here (new file)")
    parser.add_argument("--seed", type=non_negative_int, default=DEFAULT_SEED,
                        help=f"shuffle seed, a non-negative integer (default {DEFAULT_SEED})")
    parser.add_argument("--fractions", type=float, nargs=3, metavar=("TRAIN", "VAL", "TEST"),
                        default=[DEFAULT_FRACTIONS[name] for name in PARTITIONS],
                        help="share of article groups per partition (default 0.8 0.1 0.1)")
    args = parser.parse_args(argv)
    try:
        check_fractions(args.fractions)
    except ValueError as error:
        parser.error(str(error))
    outputs = [path for path in (args.output, args.report) if path is not None]
    if len(outputs) == 2 and outputs[0].resolve() == outputs[1].resolve():
        parser.error("--output and --report must be different files")
    for path in outputs:
        if os.path.lexists(path):
            parser.error(f"Refusing to overwrite {path}")
    return args


def published_checksum(path):
    """SHA-256 recorded in SHA256SUMS for a file of this repository, or None."""
    sums = REPOSITORY / "SHA256SUMS"
    if not sums.is_file():
        return None
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if (REPOSITORY / name).resolve() == path.resolve():
            return digest
    return None


def main(argv=None):
    args = parse_arguments(argv)
    pairs = read_pairs(args.pairs)
    problems = pair_problems(pairs)
    image_ids = sorted({image_id for pair in pairs for image_id in pair})
    fractions = dict(zip(PARTITIONS, args.fractions))
    if problems:
        summary = {"pairs_file": {"name": args.pairs.name, "records": len(pairs)}, "problems": problems,
                   "passed": False}
        print(json.dumps(summary, indent=2))
        print("FAILED: the pairs file cannot be split: " + "; ".join(problems), file=sys.stderr)
        return 1

    components, groups = article_groups(image_ids, pairs)
    regenerated = assign_groups(groups, args.seed, fractions)
    problems += split_problems(regenerated, image_ids, pairs)
    summary = {
        "pairs_file": {"name": args.pairs.name, "sha256": sha256_file(args.pairs), "records": len(pairs)},
        "seed": args.seed,
        "fractions": fractions,
        "procedure": "connected components of the pair graph, merged when they share a source article; "
                     "groups sorted by smallest image ID (string order), shuffled with random.Random(seed), "
                     "assigned whole by group count: int(f_train * N) train, int(f_val * N) val, rest test",
        **split_statistics(regenerated, pairs, groups, components),
        "integrity": integrity_counts(regenerated, image_ids, pairs),
        "regenerated_sha256": hashlib.sha256(split_to_bytes(regenerated)).hexdigest(),
        "comparison": None,
    }

    if args.expected.lower() != "none":
        expected_path = Path(args.expected)
        expected_sha256 = sha256_file(expected_path)
        recorded = published_checksum(expected_path)
        if recorded is not None and recorded != expected_sha256:
            problems.append(f"{expected_path.name} has SHA-256 {expected_sha256}, but SHA256SUMS lists {recorded}")
        try:
            expected = read_split(expected_path)
        except ValueError as error:
            problems.append(str(error))
            expected = {}
        comparison = compare_splits(expected, regenerated)
        comparison.update({"expected_file": expected_path.name, "expected_sha256": expected_sha256,
                           "byte_identical": expected_sha256 == summary["regenerated_sha256"],
                           "expected_file_problems": split_problems(expected, image_ids, pairs)})
        summary["comparison"] = comparison
        if not comparison["identical"]:
            problems.append(f"the regenerated split differs from {expected_path.name} for "
                            f"{comparison['differing_assignments']} images "
                            f"({comparison['only_in_expected']} only in the file, "
                            f"{comparison['only_in_actual']} only in the pairs)")
        problems += [f"{expected_path.name}: {message}" for message in comparison["expected_file_problems"]]
    summary["problems"] = problems
    summary["passed"] = not problems

    if args.output is not None and summary["passed"]:
        write_split(regenerated, args.output)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, indent=2)
            handle.write("\n")
    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        print("FAILED: " + "; ".join(problems), file=sys.stderr)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
