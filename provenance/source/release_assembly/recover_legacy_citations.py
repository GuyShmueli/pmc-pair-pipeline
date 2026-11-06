"""Apply the existing citation recovery v1.0.0 to legacy empty rows only.

Writes a NEW four-field citation file and audit. The 410 originally unresolved
newer-run pairs are identified by directed PMC pair, never by row index.
Source files, populated passages, identifiers, ordering, and reasons remain
unchanged. No model is invoked and no recovery algorithm is reimplemented.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parent
PIPELINE = ROOT / "<DATA_ROOT>/repro_positive_pairs_pipeline"
sys.path.insert(0, str(PIPELINE / "02_case_pair_selection_pipeline"))
from case_pair_selection_pipeline import citation_recovery as recovery


def read_json(path):
    with path.open() as handle:
        return json.load(handle)


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_new(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".citation_recovery_", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def identity(record):
    return record["citing_case"], record["cited_case"]


def main():
    plan = read_json(AUDIT / "recovery_plan.json")
    source = Path(plan["source_manifest"]["combined"]["path"])
    destination = source.with_name("case_pair_citations_all_runs_unique_recovered.json")
    audit_destination = AUDIT / "recovery_audit.json"
    if destination.exists() or audit_destination.exists():
        raise FileExistsError("Recovery output or audit already exists; refusing to overwrite")
    records = read_json(source)
    expected_fields = {"citing_case", "cited_case", "extracted_citation", "citation_reason"}
    assert all(set(row) == expected_fields and all(isinstance(value, str) for value in row.values()) for row in records)
    assert len({identity(row) for row in records}) == len(records)
    excluded = {tuple(pair) for pair in plan["excluded_directed_pairs"]}
    assert len(excluded) == 410
    targets = {
        index for index, row in enumerate(records)
        if not row["extracted_citation"].strip() and identity(row) not in excluded
    }
    assert len(targets) == plan["legacy_empty_targets"] == 4323
    mappings = read_json(AUDIT / "mapped_rows.json")
    assert len(mappings) == len(targets)
    assert {row["master_index"] for row in mappings} == targets

    references_by_file = defaultdict(set)
    for row in mappings:
        assert identity(row) == identity(records[row["master_index"]])
        if row.get("mapping_status") == "unresolved":
            continue
        assert isinstance(row["ref_id"], str) and row["ref_id"]
        references_by_file[row["source_nxml_path"]].add(row["ref_id"])
    tasks = [(path, tuple(sorted(refs))) for path, refs in sorted(references_by_file.items())]
    recovered_files = {}
    source_hashes = {}
    errors = {}
    print(json.dumps({"targets": len(targets), "excluded_newer_pairs": len(excluded), "source_xml_files": len(tasks)}), flush=True)
    with ProcessPoolExecutor(max_workers=4) as executor:
        future_paths = {executor.submit(recovery._parse_worker, task): task[0] for task in tasks}
        for done, future in enumerate(as_completed(future_paths), 1):
            path = future_paths[future]
            try:
                parsed_path, xml_hash, results = future.result()
                assert parsed_path == path
                recovered_files[path] = results
                source_hashes[path] = xml_hash
            except Exception as error:
                errors[path] = {"type": type(error).__name__, "message": str(error)}
            if done % 250 == 0 or done == len(tasks):
                print(json.dumps({"parsed_files": done, "total_files": len(tasks), "errors": len(errors)}), flush=True)

    updated = [dict(row) for row in records]
    recovered_rows = []
    unrecovered_rows = []
    method_counts = Counter()
    for mapping in sorted(mappings, key=lambda row: row["master_index"]):
        index = mapping["master_index"]
        base = dict(mapping)
        if mapping.get("mapping_status") == "unresolved":
            unrecovered_rows.append({**base, "recovery_status": "mapping_unresolved"})
            continue
        path, ref_id = mapping["source_nxml_path"], mapping["ref_id"]
        if path in errors:
            unrecovered_rows.append({**base, "recovery_status": "source_parse_error", "error": errors[path]})
            continue
        assert source_hashes[path] == mapping["source_nxml_sha256"], f"XML changed after reference mapping: {path}"
        base["source_nxml_sha256"] = source_hashes[path]
        result = recovered_files[path][ref_id]
        if result.status != "recovered":
            unrecovered_rows.append({**base, "recovery_status": "no_reliable_intext_marker_found"})
            continue
        assert result.extracted_citation.strip()
        updated[index]["extracted_citation"] = result.extracted_citation
        method_counts[result.method] += 1
        recovered_rows.append({
            **base,
            "method": result.method,
            "context_count": len(result.contexts),
            "extracted_citation_sha256": hashlib.sha256(result.extracted_citation.encode()).hexdigest(),
            "evidence": [
                {"method": item.method, "container_type": item.container_type, "xpath": item.xpath, "details": item.details}
                for item in result.evidence
            ],
        })

    invariants = recovery._verify_only_extracted_changed(records, updated)
    changed = {index for index, (old, new) in enumerate(zip(records, updated)) if old != new}
    assert changed <= targets
    assert len(changed) == len(recovered_rows)
    assert len(recovered_rows) + len(unrecovered_rows) == len(targets)
    assert all(old == new for old, new in zip(records, updated) if identity(old) in excluded)
    assert all(old == new for old, new in zip(records, updated) if old["extracted_citation"].strip())
    counts = {
        "total_records": len(records),
        "before_empty": sum(not row["extracted_citation"].strip() for row in records),
        "legacy_empty_targets": len(targets),
        "excluded_newer_empty_unchanged": len(excluded),
        "recovered": len(recovered_rows),
        "legacy_still_empty": len(unrecovered_rows),
        "after_empty": sum(not row["extracted_citation"].strip() for row in updated),
        "after_nonempty": sum(bool(row["extracted_citation"].strip()) for row in updated),
        "recovery_methods": dict(sorted(method_counts.items())),
        "source_xml_files_attempted": len(tasks),
        "source_xml_files_parsed": len(recovered_files),
        "source_parse_errors": len(errors),
    }
    assert counts["after_empty"] == counts["before_empty"] - counts["recovered"]
    assert counts["after_empty"] == 410 + counts["legacy_still_empty"]
    for item in plan["source_manifest"].values():
        assert file_hash(item["path"]) == item["sha256"], f"Source changed: {item['path']}"
    write_new(destination, updated)
    reloaded = read_json(destination)
    assert reloaded == updated
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "recovery_version": recovery.RECOVERY_VERSION,
        "algorithm_file": str(Path(recovery.__file__).resolve()),
        "algorithm_sha256": file_hash(recovery.__file__),
        "input_file": str(source),
        "input_sha256": plan["source_manifest"]["combined"]["sha256"],
        "output_file": str(destination),
        "output_sha256": file_hash(destination),
        "mapping_file_sha256": file_hash(AUDIT / "mapped_rows.json"),
        "source_files_unchanged": True,
        "counts": counts,
        "invariants": {**invariants, "excluded_newer_rows_changed": 0, "row_order_changed": False},
        "protected_source_manifest": plan["source_manifest"],
        "excluded_directed_pairs": sorted(excluded),
        "recovered_rows": recovered_rows,
        "unrecovered_rows": unrecovered_rows,
    }
    write_new(audit_destination, report)
    print(json.dumps({"output_file": str(destination), "audit_file": str(audit_destination), "counts": counts, "invariants": report["invariants"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
