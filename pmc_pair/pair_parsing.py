"""Step 10 (finalize-pairs): validate the image pairs proposed in the pair-selection stage.

Output format (as the prompt requires): a JSON array of objects. Formatting errors
are repaired locally when possible (see json_responses.py), with separate evidence.
Unrecoverable responses and wrong structures are rejected. For every object:
  * `pair_id` must be a list of two strings, each exactly the identifier of a retained
    caption (surrounding spaces ignored), one from each case of the pair, in either order,
  * `modality`, `anatomy` and `diagnosis` must be non-empty strings (other keys are ignored),
  * the same undirected pair is kept once.
"""

from __future__ import annotations

from collections import Counter

from .chipa import outdated_model_outputs
from .config import log, work_dir
from .io_utils import iter_jsonl, write_json, write_jsonl
from .json_responses import parse_proposals
from .llm import stage_dir
from .prepare_pairs import annotation_ready_pairs

REQUIRED_FIELDS = ("modality", "anatomy", "diagnosis")


def pair_id_strings(value):
    """The two identifiers of a well-formed pair_id, or None."""
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value):
        return value[0].strip(), value[1].strip()
    return None


def finalize_pairs(cfg):
    problems = outdated_model_outputs(cfg, require_complete=False)
    if problems:
        raise SystemExit("Model outputs do not match the current inputs:\n  " + "\n  ".join(problems))
    ready = {pair["case_pair_id"]: pair for pair in annotation_ready_pairs(cfg)}
    outputs_path = stage_dir(cfg, "pair_selection") / "outputs.jsonl"
    outputs = sorted(iter_jsonl(outputs_path), key=lambda line: line["case_pair_id"])

    kept, rejected, seen, repairs = [], [], set(), []
    counts = Counter()
    for output in outputs:
        case_pair_id = output["case_pair_id"]
        pair = ready[case_pair_id]
        ids_a, ids_b = set(pair["case_a_captions"]), set(pair["case_b_captions"])
        repair_info = {}
        items = parse_proposals(output["output_text"], repair_info=repair_info)
        if repair_info:
            counts["outputs_repair_attempted"] += 1
            counts["outputs_repaired" if items is not None else "outputs_repair_failed"] += 1
            repair_info.update({"case_pair_id": case_pair_id, "kept_proposals": 0,
                                "rejected_proposals": 0, "duplicate_proposals": 0})
            repairs.append(repair_info)
        if items is None:
            counts["outputs_not_a_json_array"] += 1
            rejected.append({"case_pair_id": case_pair_id, "reason": "output_not_a_json_array",
                             "output_preview": output["output_text"][:500]})
            continue
        counts["outputs_with_proposals" if items else "empty_outputs"] += 1

        before_kept, before_rejected = len(kept), len(rejected)
        before_duplicates = counts["duplicate_items"]
        for item in items:
            counts["proposed_items"] += 1
            ids = pair_id_strings(item.get("pair_id"))
            if ids is None:
                rejected.append({"case_pair_id": case_pair_id, "reason": "bad_pair_id", "item": item})
                continue
            first, second = ids
            if first in ids_a and second in ids_b:
                image_a, image_b = first, second
            elif first in ids_b and second in ids_a:
                image_a, image_b = second, first
            else:
                rejected.append({"case_pair_id": case_pair_id, "reason": "pair_id_not_in_case_captions",
                                 "item": item})
                continue
            if not all(isinstance(item.get(f), str) and item[f].strip() for f in REQUIRED_FIELDS):
                rejected.append({"case_pair_id": case_pair_id, "reason": "missing_field", "item": item})
                continue
            key = tuple(sorted((image_a, image_b)))
            if key in seen:
                counts["duplicate_items"] += 1
                continue
            seen.add(key)
            kept.append({"pair_id": list(key), "case_pair_id": case_pair_id,
                         "modality": item["modality"].strip(), "anatomy": item["anatomy"].strip(),
                         "diagnosis": item["diagnosis"].strip()})

        if repair_info:
            repair_info.update({"kept_proposals": len(kept) - before_kept,
                                "rejected_proposals": len(rejected) - before_rejected,
                                "duplicate_proposals": counts["duplicate_items"] - before_duplicates})

    kept.sort(key=lambda record: record["pair_id"])
    out_dir = work_dir(cfg, "image_pairs")
    write_jsonl(kept, out_dir / "image_pairs.jsonl")
    write_jsonl(rejected, out_dir / "rejected_proposals.jsonl")
    write_jsonl(repairs, out_dir / "response_repairs.jsonl")
    stats = {
        "pair_selection_outputs": len(outputs),
        **dict(counts),
        "rejected_items": dict(Counter(r["reason"] for r in rejected if r["reason"] != "output_not_a_json_array")),
        "image_pairs_kept": len(kept),
        "outputs_repair_attempted": counts["outputs_repair_attempted"],
        "outputs_repaired": counts["outputs_repaired"],
        "outputs_repair_failed": counts["outputs_repair_failed"],
    }
    write_json(stats, out_dir / "stats.json")
    log(cfg, f"finalize-pairs: kept {len(kept)} image pairs; rejected {stats['rejected_items']}")
    return stats
