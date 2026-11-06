"""Map blank legacy merged citations to their original JATS reference IDs.

Read-only with respect to all source artifacts. This does not extract contexts
or modify the master citation file. It reproduces the original identifier
priority and title fallback; saved compound reference IDs take precedence for
compound-only rows. Every mapping is verified against the cited document.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
LEGACY_CODE = ROOT / "<DATA_ROOT>/scripts-final/extract_citations.py"
spec = importlib.util.spec_from_file_location("original_citation_extractor", LEGACY_CODE)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def load(relative):
    return json.loads((ROOT / relative).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pmcid(path):
    found = re.findall(r"(?:^|/)PMC(\d+)(?:/|$)", str(path))
    if len(found) != 1:
        raise ValueError(f"Expected one PMCID path component: {path}")
    return "PMC" + str(int(found[0]))


@lru_cache(maxsize=None)
def metadata(path):
    data = legacy.parse_nxml(path)
    if data is None:
        raise ValueError(f"Could not parse source XML: {path}")
    # Retain compact metadata, not thousands of XML trees.
    data.pop("tree")
    data["sha256"] = digest(path)
    if data["pmcid"]:
        declared = "PMC" + str(int(re.sub(r"^PMC", "", data["pmcid"], flags=re.I)))
        if declared != pmcid(path):
            raise ValueError(f"PMCID mismatch: {path}, XML declares {declared}")
    return data


def original_match(citing, cited):
    # Original extraction built reverse maps, so duplicate identifiers resolve
    # to the last reference. Preserve that exact historical choice.
    for kind in ("doi", "pmid", "pmcid"):
        reverse = {v[kind]: rid for rid, v in citing["references"].items() if v[kind]}
        if cited[kind] and cited[kind] in reverse:
            return reverse[cited[kind]], kind
    title = cited["title"].strip()
    if title:
        for rid, info in citing["references"].items():
            if any(info[kind] == cited[kind] for kind in ("pmid", "doi", "pmcid")):
                continue
            if legacy.titles_match_substring(info["title"], title):
                return rid, "title_substring"
    return None, None


def verify_reference(citing, cited, rid, kind):
    info = citing["references"].get(rid)
    if info is None:
        raise ValueError(f"Reference {rid} not present")
    if kind in ("doi", "pmid", "pmcid"):
        if not cited[kind] or info[kind] != cited[kind]:
            raise ValueError(f"Saved {kind} reference mismatch at {rid}")
    elif kind == "title_substring":
        if not cited["title"].strip() or not legacy.titles_match_substring(info["title"], cited["title"]):
            raise ValueError(f"Saved title reference mismatch at {rid}")
    else:
        raise ValueError(f"Unknown match type {kind}")
    matched_ids = {k: cited[k] for k in ("doi", "pmid", "pmcid") if cited[k] and info[k] == cited[k]}
    return {
        "reference_identifiers": {k: info[k] for k in ("doi", "pmid", "pmcid")},
        "cited_identifiers": {k: cited[k] for k in ("doi", "pmid", "pmcid")},
        "matching_identifiers": matched_ids,
        "reference_title": info["title"],
        "cited_title": cited["title"],
        "verified_by": kind,
    }


def main():
    master = load("<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations_all_runs_unique.json")
    newer = load("<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations.json")
    excluded = {(r["citing_case"], r["cited_case"]) for r in newer if not r["extracted_citation"].strip()}
    provenance = load("chipa_citation_merge_2026-10-14/merge_provenance.json")["records"]
    paths = load("<DATA_ROOT>/matching_uids_xml_paths.json")
    compound = load("<DATA_ROOT>/compound_citation_list.json")
    originals = load("chipa_citation_merge_2026-10-14/original_normalized_records.json")
    # Files reside on network storage. A bounded concurrent preload avoids
    # serial filesystem round trips while preserving deterministic matching.
    wanted_paths = set()
    for i, record in enumerate(master):
        if record["extracted_citation"].strip() or (record["citing_case"], record["cited_case"]) in excluded:
            continue
        sources = provenance[i]["sources"]
        original_sources = [s for s in sources if s["source"] == "original"]
        if original_sources:
            candidate = originals[original_sources[0]["source_index"]]["candidate_index"]
            wanted_paths.update(paths[candidate])
        else:
            saved = compound[next(s["source_index"] for s in sources if s["source"] == "compound")]
            wanted_paths.update((saved["citing_file"], saved["cited_file"]))
    preload_errors = {}
    print(f"Preloading {len(wanted_paths)} XML files with 8 threads", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(metadata, path): path for path in sorted(wanted_paths)}
        for count, future in enumerate(as_completed(pending), 1):
            try:
                future.result()
            except Exception as exc:
                preload_errors[pending[future]] = str(exc)
            if count % 1000 == 0 or count == len(pending):
                print(f"Preloaded {count}/{len(pending)} XML files; {len(preload_errors)} errors", flush=True)
    result = []
    stats = Counter()
    discrepancies = []
    assert len(master) == len(provenance)
    for i, record in enumerate(master):
        key = (record["citing_case"], record["cited_case"])
        p = provenance[i]
        assert p["output_index"] == i and (p["citing_case"], p["cited_case"]) == key
        if record["extracted_citation"].strip():
            continue
        if key in excluded:
            stats["excluded_newer_empty"] += 1
            continue
        row = {"master_index": i, "citing_case": key[0], "cited_case": key[1], "sources": p["sources"]}
        original_sources = [s for s in p["sources"] if s["source"] == "original"]
        compound_sources = [s for s in p["sources"] if s["source"] == "compound"]
        try:
            if original_sources:
                source = original_sources[0]
                norm = originals[source["source_index"]]
                assert (norm["citing_case"], norm["cited_case"]) == key
                candidates = paths[norm["candidate_index"]]
                citing_path = next(path for path in candidates if pmcid(path) == key[0])
                cited_path = next(path for path in candidates if pmcid(path) == key[1])
                a, b = metadata(citing_path), metadata(cited_path)
                rid, kind = original_match(a, b)
                if rid is None:
                    raise ValueError("Original matcher found no reference")
                row["mapping_source"] = "original_reproduced_match"
            else:
                assert len(compound_sources) == 1
                source = compound_sources[0]
                saved = compound[source["source_index"]]
                citing_path, cited_path = saved["citing_file"], saved["cited_file"]
                assert (pmcid(citing_path), pmcid(cited_path)) == key
                a, b = metadata(citing_path), metadata(cited_path)
                rid, kind = saved["match_ref_id"], saved["match_type"]
                row["mapping_source"] = "compound_saved_match"
            verification = verify_reference(a, b, rid, kind)
            row.update({"mapping_status": "mapped", "source_nxml_path": citing_path,
                        "cited_nxml_path": cited_path, "source_nxml_sha256": a["sha256"],
                        "cited_nxml_sha256": b["sha256"], "ref_id": rid, "match_type": kind,
                        "verification": verification})
            # A duplicate must agree on source paths, direction and reference ID.
            if original_sources and compound_sources:
                saved = compound[compound_sources[0]["source_index"]]
                if ((saved["citing_file"], saved["cited_file"], saved["match_ref_id"])
                        != (citing_path, cited_path, rid)):
                    discrepancies.append({"master_index": i, "original": [citing_path, cited_path, rid],
                                          "compound": [saved["citing_file"], saved["cited_file"], saved["match_ref_id"]]})
                else:
                    stats["duplicate_original_compound_agreement"] += 1
            stats["mapped"] += 1
            stats["match_type_" + kind] += 1
        except Exception as exc:
            row.update({"mapping_status": "unresolved", "ref_id": None, "match_type": None,
                        "error": f"{type(exc).__name__}: {exc}"})
            stats["unresolved"] += 1
        result.append(row)
        if len(result) % 500 == 0:
            print(f"Mapped {len(result)} target rows; {stats['unresolved']} unresolved", flush=True)
    report = {
        "target_rows": len(result), "counts": dict(stats),
        "unique_xml_files_parsed": metadata.cache_info().currsize,
        "legacy_matching_code": str(LEGACY_CODE),
        "legacy_matching_code_sha256": digest(LEGACY_CODE),
        "mapping_policy": "Original DOI, PMID, PMCID, then historical title-substring fallback; compound-only uses saved match_ref_id. Verify actual cited identifiers or saved title fallback.",
        "duplicate_mapping_discrepancies": discrepancies,
        "preload_errors": preload_errors,
        "unresolved": [r for r in result if r["mapping_status"] != "mapped"],
    }
    assert len(result) == 4323 and stats["excluded_newer_empty"] == 410
    (OUT / "mapped_rows.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (OUT / "mapping_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("unresolved", "duplicate_mapping_discrepancies")}, indent=2))
    print(f"Discrepancies: {len(discrepancies)}", flush=True)


if __name__ == "__main__":
    main()
