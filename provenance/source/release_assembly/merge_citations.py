"""Combine three saved citation runs without modifying any source file.

The release uses the newer run's four-string-field schema. A unique record
is a directed (citing PMC article, cited PMC article) pair. Exact extraction
paragraph duplicates are removed within legacy rows. Duplicate pair records
retain the first source in newer/original/compound order, unless a subsequent
source supplies a missing passage. All conflicting variants are preserved in
the provenance file. No citation text or interpretation is generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from original_normalizer import load_original_records


FIELDS = ("citing_case", "cited_case", "extracted_citation", "citation_reason")


def read_json(path):
    with path.open() as handle:
        return json.load(handle)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(block)
    return {"size_bytes": path.stat().st_size, "sha256": result.hexdigest()}


def write_new_json(path, value):
    """Publish a complete JSON file exclusively; never overwrite a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".citation_merge_", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_name, path)
    finally:
        os.unlink(temp_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-normalized", action="store_true")
    args = parser.parse_args()
    audit = Path(__file__).resolve().parent
    root = audit.parent
    output = root / "<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations_all_runs_unique.json"
    if output.exists():
        raise FileExistsError(output)
    manifest_path = audit / "source_manifest_before.json"
    source_manifest = read_json(manifest_path)

    if args.reuse_normalized:
        original = read_json(audit / "original_normalized_records.json")
        original_report = read_json(audit / "original_normalization_report.json")
    else:
        original, original_report = load_original_records(root)

    source_paths = {
        "newer": "<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations.json",
        "original": "<DATA_ROOT>/citation_extrac_list.json",
        "compound": "<DATA_ROOT>/compound_citation_list.json",
    }
    newer = read_json(root / source_paths["newer"])
    compound_input = read_json(root / source_paths["compound"])
    compound_reasons = read_json(root / "<DATA_ROOT>/compound_batch_resps/compound_citation_reponse.jsonl")
    assert len(compound_input) == len(compound_reasons)
    compound = []
    for index, record in enumerate(compound_input):
        ids = []
        for field in ("citing_file", "cited_file"):
            matches = set(re.findall(r"PMC\d+", record[field]))
            assert len(matches) == 1, (index, field)
            ids.append(matches.pop())
        paragraphs = record["citation_paragraphs"]
        assert isinstance(paragraphs, list)
        assert all(isinstance(paragraph, str) for paragraph in paragraphs)
        compound.append({
            "citing_case": ids[0],
            "cited_case": ids[1],
            "extracted_citation": "\n\n".join(dict.fromkeys(p for p in paragraphs if p.strip())),
            "citation_reason": compound_reasons[index],
        })

    merged = {}
    provenance = {}
    source_statistics = {}
    duplicate_statistics = Counter()
    for source, rows in (("newer", newer), ("original", original), ("compound", compound)):
        keys = set()
        empty = 0
        for index, row in enumerate(rows):
            record = {field: row[field] for field in FIELDS}
            assert all(isinstance(value, str) for value in record.values())
            key = record["citing_case"], record["cited_case"]
            assert all(re.fullmatch(r"PMC\d+", value) for value in key)
            keys.add(key)
            empty += not record["extracted_citation"].strip()
            reference = {"source": source, "source_index": index}
            if source == "original":
                assert row["source_index"] == index
                reference["candidate_index"] = row["candidate_index"]
            if key not in merged:
                merged[key] = record
                provenance[key] = {"selected_source": reference, "sources": [reference], "alternative_records": []}
                continue
            duplicate_statistics["duplicate_pair_rows_removed"] += 1
            prior = merged[key]
            provenance[key]["sources"].append(reference)
            if record == prior:
                duplicate_statistics["identical_normalized_records"] += 1
                continue
            duplicate_statistics["different_normalized_records"] += 1
            if record["extracted_citation"] == prior["extracted_citation"]:
                duplicate_statistics["duplicates_with_identical_passage"] += 1
            else:
                duplicate_statistics["duplicates_with_different_passage"] += 1
                # Do not silently discard distinct extracted evidence.
                assert not record["extracted_citation"].strip() or not prior["extracted_citation"].strip(), key
            if record["extracted_citation"].strip() and not prior["extracted_citation"].strip():
                provenance[key]["alternative_records"].append({**provenance[key]["selected_source"], "record": prior})
                provenance[key]["selected_source"] = reference
                merged[key] = record
            else:
                provenance[key]["alternative_records"].append({**reference, "record": record})
        assert len(keys) == len(rows), (source, "unexpected within-source duplicate pair")
        source_statistics[source] = {"records": len(rows), "empty_extracted_citation": empty}

    ordered_keys = sorted(merged, key=lambda pair: tuple(int(value[3:]) for value in pair))
    records = [merged[key] for key in ordered_keys]
    empty_count = sum(not record["extracted_citation"].strip() for record in records)
    total_rows = sum(stats["records"] for stats in source_statistics.values())
    assert len(records) == total_rows - duplicate_statistics["duplicate_pair_rows_removed"]
    assert len(set(tuple(sorted(key)) for key in merged)) == len(merged), "Reverse-direction pairs found"
    assert all(record["citation_reason"].strip() for record in records)
    provenance_records = [
        {"output_index": index, "citing_case": key[0], "cited_case": key[1], **provenance[key]}
        for index, key in enumerate(ordered_keys)
    ]
    for source, rows in (("newer", newer), ("original", original), ("compound", compound)):
        for row in rows:
            key = row["citing_case"], row["cited_case"]
            assert key in merged
            if row["extracted_citation"].strip():
                assert row["extracted_citation"] == merged[key]["extracted_citation"], (source, key)

    after = {name: digest(root / name) for name in source_manifest}
    assert after == source_manifest, "A source or mapping file changed during processing"
    write_new_json(output, records)
    saved = read_json(output)
    assert saved == records
    write_new_json(audit / "merge_provenance.json", {
        "source_paths": source_paths,
        "selection_policy": "First source in newer, original, compound order; prefer a nonempty passage if needed. All differing records preserved below.",
        "records": provenance_records,
    })
    report = {
        "output_file": str(output),
        "output_schema": list(FIELDS),
        "unique_key": ["citing_case", "cited_case"],
        "identifier_level": "PMC article; citation direction resolved from saved citing/cited metadata",
        "records": len(records),
        "empty_extracted_citation": empty_count,
        "nonempty_extracted_citation": len(records) - empty_count,
        "empty_definition": "extracted_citation.strip() == ''",
        "empty_citation_reason": sum(not record["citation_reason"].strip() for record in records),
        "source_statistics": source_statistics,
        "raw_input_records": total_rows,
        "duplicate_statistics": dict(duplicate_statistics),
        "source_files_unchanged": True,
        "source_manifest": source_manifest,
        "normalized_original_artifact": digest(audit / "original_normalized_records.json") if args.reuse_normalized else None,
        "original_normalization": original_report,
        "output_digest": digest(output),
        "provenance_file": str(audit / "merge_provenance.json"),
        "verification": "Read-back equals written records; every source pair covered; all nonempty normalized citation passages retained exactly; no missing fields; directed and unordered uniqueness; source SHA-256 hashes unchanged.",
    }
    write_new_json(audit / "merge_report.json", report)
    print(json.dumps({key: report[key] for key in ("output_file", "records", "empty_extracted_citation", "nonempty_extracted_citation", "source_statistics", "duplicate_statistics", "source_files_unchanged")}, indent=2))


if __name__ == "__main__":
    main()
