"""Verify the downloaded public PMC-PaIR deposit.

This layout has separate image/caption ZIPs, licensing and availability metadata, and
annotation files. The check is deliberately separate from ``checks.check_release``, which
checks exported pipeline outputs with captions embedded in pair records.

All top-level files except SHA256SUMS.txt must be listed in that checksum file.
Additional checksummed flat files are integrity checked but not interpreted. Extracted
``images/`` and ``captions/`` directories may coexist with the download and are ignored:
this command verifies the archived payloads, not those extracted copies. No validation
report is written into the deposit. Checks establish internal integrity against the
supplied metadata, not authenticity, source provenance or legal clearance.
"""
from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import json
import re
import stat
import zipfile
import zlib
from collections import Counter
from pathlib import Path, PurePosixPath

from .article_disjoint_split import generate_split, read_split, split_problems

REQUIRED_METADATA = frozenset({
    "image_pairs.json", "image_labels.jsonl", "label_taxonomy.json",
    "case_pair_citations_eligible.json", "file_manifest.csv", "licenses.csv",
    "withheld.csv", "pair_availability.csv", "release_summary.json",
    "included_image_ids.txt", "withheld_image_ids.txt", "README.txt", "LICENSE.txt",
})
FIELDS = ("modality", "anatomy", "diagnosis")
IMAGE_ID = re.compile(r"([1-9][0-9]*)_([1-9][0-9]*)_([1-9][0-9]*)\Z")
CASE_ID = re.compile(r"(?:PMC)?([1-9][0-9]*)(?:-([1-9][0-9]*))?\Z")
ARCHIVE_NAME = re.compile(r"images_captions_[0-9]{3}\.zip\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SCOPE = ("Integrity of final downloaded files, archived image/caption bytes and annotation "
         "consistency. Historical construction/provenance and legal clearance are not verified. "
         "Extracted images/ and captions/ directories, if present, are not verified.")


class DepositError(ValueError):
    """A malformed or inconsistent deposited file."""


def _require(condition, message):
    if not condition:
        raise DepositError(message)


def _object(items):
    value = {}
    for key, item in items:
        _require(key not in value, f"JSON object repeats key {key!r}")
        value[key] = item
    return value


def _json(path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as error:
        raise DepositError(f"{path.name}: {error}") from None


def _rows(path, required):
    """Stream CSV rows, rejecting repeated/missing columns and malformed rows."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames or []
        _require(len(names) == len(set(names)), f"{path.name}: repeated CSV column names")
        _require(set(required) <= set(names),
                 f"{path.name}: missing columns {sorted(set(required) - set(names))}")
        for index, row in enumerate(reader, 2):
            _require(None not in row and all(value is not None for value in row.values()),
                     f"{path.name}:{index}: malformed CSV row")
            yield row


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _flat_name(name):
    return (isinstance(name, str) and name not in ("", ".", "..")
            and "/" not in name and "\\" not in name and "\x00" not in name
            and not any(ord(c) < 32 for c in name))


def _checksums(root):
    inventory = {}
    for line_number, line in enumerate((root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        _require(match is not None, f"SHA256SUMS.txt:{line_number}: malformed checksum line")
        digest, name = match.groups()
        _require(_flat_name(name) and name != "SHA256SUMS.txt",
                 f"SHA256SUMS.txt:{line_number}: unsafe or self-referential filename {name!r}")
        _require(name not in inventory, f"SHA256SUMS.txt: repeated filename {name!r}")
        inventory[name] = digest
    _require(REQUIRED_METADATA <= inventory.keys(),
             f"SHA256SUMS.txt: missing required files {sorted(REQUIRED_METADATA - inventory.keys())}")
    actual = set()
    for path in root.iterdir():
        _require(not path.is_symlink(), f"deposit contains a symbolic link: {path.name}")
        if path.is_dir():
            _require(path.name in {"images", "captions"}, f"unexpected directory in deposit: {path.name}")
        else:
            _require(path.is_file(), f"not a regular deposit file: {path.name}")
            if path.name != "SHA256SUMS.txt":
                actual.add(path.name)
    _require(actual == inventory.keys(),
             f"checksum inventory differs from files: missing {sorted(inventory.keys() - actual)[:10]}, "
             f"unlisted {sorted(actual - inventory.keys())[:10]}")
    # Stop before parsing metadata or decompressing ZIPs if an outer checksum differs.
    for name, expected in inventory.items():
        _require(_sha256_file(root / name) == expected, f"SHA-256 mismatch: {name}")
    return inventory


def _image_id(value, where):
    _require(isinstance(value, str) and IMAGE_ID.fullmatch(value),
             f"{where}: invalid image identifier {value!r}")
    return value


def _article(image_id):
    return "PMC" + image_id.split("_")[0]


def _case(image_id):
    article, case, _ = image_id.split("_")
    return article, case


def _citation_case(value, where):
    match = CASE_ID.fullmatch(value) if isinstance(value, str) else None
    _require(match, f"{where}: invalid citation case identifier {value!r}")
    return match.group(1), match.group(2) or "1"


def _ids(path):
    result = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = _image_id(line, f"{path.name}:{number}")
        _require(value not in result, f"{path.name}: repeated image {value}")
        result.add(value)
    return result


def _pairs(root, counts):
    records = _json(root / "image_pairs.json")
    _require(isinstance(records, list) and records, "image_pairs.json: expected a nonempty list")
    pairs, images = set(), set()
    for index, row in enumerate(records):
        where = f"image_pairs.json[{index}]"
        _require(isinstance(row, dict) and set(row) == {"pair_id", *FIELDS},
                 f"{where}: expected pair_id, modality, anatomy and diagnosis")
        pair = row["pair_id"]
        _require(isinstance(pair, list) and len(pair) == 2, f"{where}: pair_id must contain two images")
        first, second = [_image_id(value, where) for value in pair]
        _require(first != second, f"{where}: an image is paired with itself")
        key = tuple(sorted(pair))
        _require(key not in pairs, f"{where}: duplicate undirected pair {key}")
        for field in FIELDS:
            _require(isinstance(row[field], str) and row[field].strip(), f"{where}: empty or invalid {field}")
        pairs.add(key)
        images.update(pair)
    counts.update(image_pairs=len(records), annotation_images=len(images))
    return records, pairs, images


def _citations(root, pairs, counts):
    records = _json(root / "case_pair_citations_eligible.json")
    _require(isinstance(records, list), "case_pair_citations_eligible.json: expected a list")
    seen, passages = set(), 0
    for index, row in enumerate(records):
        where = f"case_pair_citations_eligible.json[{index}]"
        _require(isinstance(row, dict) and set(row) == {
            "citing_case", "cited_case", "extracted_citation", "citation_reason"}, f"{where}: invalid fields")
        first = _citation_case(row["citing_case"], where)
        second = _citation_case(row["cited_case"], where)
        _require(first != second, f"{where}: a case cites itself")
        key = tuple(sorted((first, second)))
        _require(key not in seen, f"{where}: repeated case pair {key}")
        seen.add(key)
        _require(isinstance(row["extracted_citation"], str), f"{where}: extracted_citation must be text")
        _require(isinstance(row["citation_reason"], str) and row["citation_reason"].strip(),
                 f"{where}: citation_reason must be nonempty text")
        passages += bool(row["extracted_citation"].strip())
    for first, second in pairs:
        if _article(first) != _article(second):
            key = tuple(sorted((_case(first), _case(second))))
            _require(key in seen, f"image pair {(first, second)} has no citation record for its cases")
    counts.update(citation_records=len(records), citation_records_with_passages=passages)


def _labels(root, records, images, counts):
    from .labels import combine_image_labels, load_label_rules, pair_categories

    # Parse strictly before the rule loader reads the same file.
    taxonomy = _json(root / "label_taxonomy.json")
    _require(isinstance(taxonomy, dict), "label_taxonomy.json: expected an object")
    rules = load_label_rules(root / "label_taxonomy.json")
    expected_count = rules.get("expected_unique_images")
    if expected_count is not None:
        _require(type(expected_count) is int and expected_count == len(images),
                 "label_taxonomy.json: expected_unique_images differs from paired images")
    expected = {r["image_id"]: r["labels"] for r in combine_image_labels(pair_categories(records, rules), rules["other"])}
    seen = set()
    with (root / "image_labels.jsonl").open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, 1):
            where = f"image_labels.jsonl:{index}"
            _require(line.strip(), f"{where}: empty line")
            row = json.loads(line, object_pairs_hook=_object)
            _require(isinstance(row, dict) and set(row) == {"image_id", "labels"}, f"{where}: invalid fields")
            image = _image_id(row["image_id"], where)
            _require(image not in seen, f"{where}: repeated image {image}")
            _require(isinstance(row["labels"], dict) and set(row["labels"]) == set(FIELDS),
                     f"{where}: invalid label groups")
            for field in FIELDS:
                values = row["labels"][field]
                _require(isinstance(values, list) and values and all(isinstance(v, str) for v in values),
                         f"{where}: invalid {field} labels")
                _require(values == sorted(set(values)), f"{where}: unsorted or repeated {field} labels")
                _require(set(values) <= set(rules["fields"][field]["categories"]), f"{where}: unknown {field} category")
            _require(row["labels"] == expected.get(image),
                     f"{where}: labels for {image} differ from recomputed taxonomy mapping")
            seen.add(image)
    _require(seen == images, "image_labels.jsonl: image coverage differs from image_pairs.json")
    counts["labelled_images"] = len(seen)


def _integer(value, where):
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise DepositError(f"{where}: expected a nonnegative integer") from None
    _require(str(number) == str(value) and number >= 0, f"{where}: expected a nonnegative integer")
    return number


def _compatible_license(value):
    """Release policy: no unresolved or no-derivatives grants."""
    return (bool(value.strip()) and "unresolved" not in value.lower()
            and "ND" not in value.upper() and "noderiv" not in value.lower())


def _metadata(root, records, images, summary, inventory, counts):
    included, withheld = _ids(root / "included_image_ids.txt"), _ids(root / "withheld_image_ids.txt")
    _require(not included & withheld, "included and withheld image identifiers overlap")
    _require(included | withheld == images, "included/withheld identifiers do not partition the annotated images")
    archives = summary.get("archives")
    _require(isinstance(archives, list) and archives, "release_summary.json: archives must be a nonempty list")
    archive_records = {}
    for row in archives:
        _require(isinstance(row, dict), "release_summary.json: invalid archive record")
        name = row.get("archive")
        _require(isinstance(name, str) and ARCHIVE_NAME.fullmatch(name), f"release_summary.json: invalid archive name {name!r}")
        _require(name not in archive_records, f"release_summary.json: duplicate archive {name}")
        _require(name in inventory and row.get("sha256") == inventory[name], f"release_summary.json: checksum differs for {name}")
        _require(type(row.get("bytes")) is int and row["bytes"] == (root / name).stat().st_size,
                 f"release_summary.json: size differs for {name}")
        archive_records[name] = row
    _require(set(archive_records) == {name for name in inventory if name.endswith(".zip")},
             "release_summary.json: archive inventory differs from deposited ZIP files")

    manifest, expected_members = {}, {name: {} for name in archive_records}
    manifest_fields = {"image_id", "archive", "image_path", "caption_path", "image_size_bytes", "caption_size_bytes",
                       "image_sha256", "caption_sha256", "pmcid", "figure_xml_id", "source_article_url"}
    for row in _rows(root / "file_manifest.csv", manifest_fields):
        image = _image_id(row["image_id"], "file_manifest.csv")
        _require(image not in manifest, f"file_manifest.csv: duplicate image {image}")
        _require(image in included, f"file_manifest.csv: image is not included: {image}")
        _require(row["archive"] in archive_records, f"file_manifest.csv: unknown archive for {image}")
        _require(row["pmcid"] == _article(image), f"file_manifest.csv: article differs for {image}")
        _require(row["figure_xml_id"] and row["source_article_url"], f"file_manifest.csv: missing source metadata for {image}")
        for kind, suffix in (("image", ".jpg"), ("caption", ".txt")):
            member = row[f"{kind}_path"]
            _require(member == f"{kind}s/{image}{suffix}", f"file_manifest.csv: unexpected {kind} path for {image}")
            digest = row[f"{kind}_sha256"]
            _require(SHA256.fullmatch(digest), f"file_manifest.csv: invalid {kind} SHA-256 for {image}")
            size = _integer(row[f"{kind}_size_bytes"], f"file_manifest.csv: {kind} size for {image}")
            _require(size > 0, f"file_manifest.csv: empty {kind} for {image}")
            members = expected_members[row["archive"]]
            _require(member not in members, f"file_manifest.csv: repeated member {member}")
            members[member] = (size, digest, kind)
        manifest[image] = row
    _require(set(manifest) == included, "file_manifest.csv: image coverage differs from included_image_ids.txt")

    withheld_rows, statuses = {}, Counter()
    for row in _rows(root / "withheld.csv", {"image_id", "status", "reason", "source_article_url"}):
        image = _image_id(row["image_id"], "withheld.csv")
        _require(image not in withheld_rows, f"withheld.csv: duplicate image {image}")
        _require(row["status"].startswith("withheld_") and row["reason"].strip(), f"withheld.csv: missing status/reason for {image}")
        withheld_rows[image] = row
        statuses[row["status"]] += 1
    _require(set(withheld_rows) == withheld, "withheld.csv: coverage differs from withheld_image_ids.txt")

    license_seen = set()
    distributions = {key: Counter() for key in (
        "primary_image_license_counts", "primary_caption_license_counts", "image_component_license_combinations",
        "caption_component_license_combinations", "image_commercial_use_counts", "caption_commercial_use_counts")}
    license_fields = {"image_id", "pmcid", "source_article_url", "figure_xml_id", "file_redistribution_status",
                      "image_license", "caption_license", "image_license_components", "caption_license_components",
                      "image_commercial_use_under_recorded_license", "caption_commercial_use_under_recorded_license",
                      "archive", "image_member", "caption_member", "attribution", "article_authors", "article_title"}
    for row in _rows(root / "licenses.csv", license_fields):
        image = _image_id(row["image_id"], "licenses.csv")
        _require(image not in license_seen, f"licenses.csv: duplicate image {image}")
        _require(image in images and row["pmcid"] == _article(image), f"licenses.csv: unknown image or wrong article for {image}")
        license_seen.add(image)
        for field in ("attribution", "article_authors", "article_title"):
            _require(row[field].strip(), f"licenses.csv: missing {field} for {image}")
        if image in included:
            entry = manifest[image]
            _require(row["file_redistribution_status"] == "included", f"licenses.csv: wrong included status for {image}")
            for key, manifest_key in (("archive", "archive"), ("image_member", "image_path"), ("caption_member", "caption_path"),
                                      ("source_article_url", "source_article_url"), ("figure_xml_id", "figure_xml_id")):
                _require(row[key] == entry[manifest_key], f"licenses.csv: {key} differs from manifest for {image}")
            for kind in ("image", "caption"):
                _require(_compatible_license(row[f"{kind}_license"]),
                         f"licenses.csv: unresolved or incompatible {kind} license for {image}")
                components = json.loads(row[f"{kind}_license_components"], object_pairs_hook=_object)
                _require(isinstance(components, list) and components and all(isinstance(c, dict) and isinstance(c.get("license"), str)
                         and _compatible_license(c["license"]) for c in components), f"licenses.csv: invalid {kind} license components for {image}")
                commercial = row[f"{kind}_commercial_use_under_recorded_license"]
                _require(commercial in {"permitted", "not_permitted"}, f"licenses.csv: invalid commercial-use flag for {image}")
                distributions[f"primary_{kind}_license_counts"][row[f"{kind}_license"]] += 1
                distributions[f"{kind}_component_license_combinations"][" + ".join(sorted({c["license"] for c in components}))] += 1
                distributions[f"{kind}_commercial_use_counts"][commercial] += 1
        else:
            _require(row["file_redistribution_status"] == withheld_rows[image]["status"], f"licenses.csv: withheld status differs for {image}")
            _require(not any(row[k] for k in ("archive", "image_member", "caption_member")), f"licenses.csv: withheld image has file locations: {image}")
    _require(license_seen == images, "licenses.csv: coverage differs from annotated images")

    indices, complete = set(), 0
    for row in _rows(root / "pair_availability.csv", {"pair_index", "image_id_1", "image_id_2", "image_1_available",
                                                    "image_2_available", "both_images_available"}):
        index = _integer(row["pair_index"], "pair_availability.csv: pair_index")
        _require(index < len(records) and index not in indices, f"pair_availability.csv: invalid or repeated pair index {index}")
        first, second = records[index]["pair_id"]
        _require((row["image_id_1"], row["image_id_2"]) == (first, second), f"pair_availability.csv: pair {index} differs from image_pairs.json")
        expected = {"image_1_available": first in included, "image_2_available": second in included,
                    "both_images_available": first in included and second in included}
        for key, value in expected.items():
            _require(row[key] == str(value), f"pair_availability.csv: incorrect {key} for pair {index}")
        complete += expected["both_images_available"]
        indices.add(index)
    _require(len(indices) == len(records), "pair_availability.csv: missing pairs")

    expected_summary = {
        "annotation_image_ids": len(images), "annotation_pairs": len(records), "included_images": len(included),
        "included_captions": len(included), "withheld_images": len(withheld), "complete_pairs": complete,
        "affected_pairs": len(records) - complete, "included_source_articles": len({_article(i) for i in included}),
        "all_source_articles": len({_article(i) for i in images}), "archive_count": len(archive_records),
        "archive_bytes": sum(row["bytes"] for row in archive_records.values()), "zip_entries": 2 * len(included),
        "withheld_by_status": dict(statuses),
    }
    expected_summary.update({key: dict(value) for key, value in distributions.items()})
    for key, value in expected_summary.items():
        _require(key in summary and type(summary[key]) is type(value) and summary[key] == value, f"release_summary.json: {key} differs from calculated value {value!r}")
    counts.update(included_images=len(included), withheld_images=len(withheld), complete_pairs=complete,
                  affected_pairs=len(records) - complete, licensed_images=len(license_seen))
    return archive_records, expected_members


def _archives(root, archive_records, expected_members, counts):
    total, payload_bytes = 0, 0
    for name, record in archive_records.items():
        expected = expected_members[name]
        with zipfile.ZipFile(root / name) as archive:
            infos, seen = archive.infolist(), set()
            for info in infos:
                member = info.filename
                path = PurePosixPath(member)
                _require(not path.is_absolute() and ".." not in path.parts and "\\" not in member
                         and member == str(path) and "\x00" not in member and not info.is_dir(),
                         f"{name}: unsafe or unexpected member {member!r}")
                _require(not stat.S_ISLNK(info.external_attr >> 16), f"{name}: symbolic-link member {member!r}")
                _require(not info.flag_bits & 1, f"{name}: encrypted member {member!r}")
                _require(member not in seen, f"{name}: duplicate member {member}")
                seen.add(member)
                _require(member in expected, f"{name}: unexpected member {member}")
                size, digest, kind = expected[member]
                _require(info.file_size == size, f"{name}/{member}: size differs from file_manifest.csv")
                actual_digest, actual_size = hashlib.sha256(), 0
                decoder = codecs.getincrementaldecoder("utf-8")() if kind == "caption" else None
                caption_has_text = False
                # Streaming through EOF makes zipfile check the CRC as well as our SHA-256.
                with archive.open(info) as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        actual_digest.update(block)
                        actual_size += len(block)
                        if decoder is not None:
                            caption_has_text |= bool(decoder.decode(block).strip())
                if decoder is not None:
                    caption_has_text |= bool(decoder.decode(b"", final=True).strip())
                    _require(caption_has_text, f"{name}/{member}: caption is empty or whitespace only")
                _require(actual_size == size and actual_digest.hexdigest() == digest,
                         f"{name}/{member}: payload size or SHA-256 differs from file_manifest.csv")
                payload_bytes += actual_size
            _require(seen == expected.keys(), f"{name}: missing manifest members {sorted(expected.keys() - seen)[:5]}")
            _require(type(record.get("entries")) is int and record["entries"] == len(seen), f"release_summary.json: entries differs for {name}")
            image_count = sum(kind == "image" for _, _, kind in expected.values())
            _require(type(record.get("images")) is int and record["images"] == image_count, f"release_summary.json: images differs for {name}")
            total += len(seen)
    counts.update(archives=len(archive_records), verified_zip_members=total, verified_payload_bytes=payload_bytes)


def verify_deposit(data_dir, split_file=None):
    """Return an integrity report; malformed inputs return ``passed=False``, never success.

    Verification stops at the first malformed/inconsistent input to keep diagnostics
    bounded and avoid processing untrusted data after a failed checksum or schema check.
    A separate split is optional. If supplied, its assignments must match regeneration
    with seed 42 and article-group fractions 0.8/0.1/0.1, in addition to integrity checks.
    """
    root = Path(data_dir)
    result = {"passed": False, "problems": [], "problem_count": 0, "counts": {},
              "split_checked": False, "scope": SCOPE, "warnings": []}
    try:
        _require(root.is_dir(), f"not a deposit directory: {root}")
        _require((root / "SHA256SUMS.txt").is_file(), "missing SHA256SUMS.txt")
        inventory = _checksums(root)
        result["counts"]["verified_top_level_files"] = len(inventory)
        result["additional_integrity_only_files"] = sorted(
            name for name in inventory if name not in REQUIRED_METADATA and not ARCHIVE_NAME.fullmatch(name))
        records, pairs, images = _pairs(root, result["counts"])
        _citations(root, pairs, result["counts"])
        _labels(root, records, images, result["counts"])
        summary = _json(root / "release_summary.json")
        _require(isinstance(summary, dict), "release_summary.json: expected an object")
        archive_records, expected_members = _metadata(root, records, images, summary, inventory, result["counts"])
        _archives(root, archive_records, expected_members, result["counts"])
        if split_file is not None:
            split = read_split(split_file)
            problems = split_problems(split, images, pairs)
            _require(not problems, "split: " + "; ".join(problems[:5]))
            regenerated = generate_split(images, pairs)
            _require(split == regenerated, "split: assignments differ from seed-42 article-group regeneration (0.8/0.1/0.1)")
            result["split_checked"] = True
            result["counts"]["split_images"] = dict(Counter(split.values()))
        result["passed"] = True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, csv.Error, zipfile.BadZipFile,
            RuntimeError, NotImplementedError, zlib.error, re.error) as error:
        result["problems"] = [str(error)[:2000] or type(error).__name__]
        result["problem_count"] = 1
    return result


def add_arguments(parser):
    parser.add_argument("--data-dir", required=True, type=Path, help="Directory containing the downloaded Zenodo files")
    parser.add_argument("--split-file", type=Path, help="Optional split from the code repository, checked against seed-42 regeneration")
    parser.add_argument("--report-file", type=Path, help="New JSON report outside the data directory; existing files are never overwritten")
    return parser


def run_cli(args):
    if args.report_file is not None:
        source, target = args.data_dir.resolve(), args.report_file.resolve()
        if target == source or source in target.parents:
            raise SystemExit("--report-file must be outside --data-dir")
        if args.report_file.exists() or args.report_file.is_symlink():
            raise SystemExit(f"Refusing to overwrite report: {args.report_file}")
    result = verify_deposit(args.data_dir, args.split_file)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report_file is not None:
        # Exclusive creation also protects against a file appearing during verification.
        with args.report_file.open("x", encoding="utf-8") as handle:
            handle.write(text)
    print(text, end="")
    return 0 if result["passed"] else 1


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser(description=__doc__))
    return run_cli(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
