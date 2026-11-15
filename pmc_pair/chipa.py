"""Steps 6-9: the four CHIPA language-model stages, each run on the annotation-ready case pairs.

  citation_analysis    why the citing article cites the cited one (titles, abstracts and
                       extracted citation passages)
  question_generation  comparative clinical questions at three levels (both case
                       descriptions + citation analysis)
  answer_generation    answers to the questions using only the supplied evidence
  pair_selection       positive image pairs from the captions of both cases, with the
                       questions and answers as clinical context

A stage only builds requests for pairs whose earlier stages are answered. Prompts are
read from prompts/, models and reasoning efforts from the configuration (llm.stages).
"""

from __future__ import annotations

import json

from .config import log
from .io_utils import iter_jsonl
from .llm import (STAGES, build_request, collect_batches, fill_template, import_batch_output,
                  import_responses, load_prompt, run_sync, split_cached, stage_dir, stage_outputs,
                  submit_batches, write_request_files, write_stage_outputs)
from .prepare_pairs import annotation_ready_pairs, citation_pairs


def stage_pairs(cfg, stage):
    """The annotation-ready case pairs, with the fields the stage needs: titles, abstracts
    and citation passages (citation_pairs.jsonl) for the citation analysis, case
    descriptions and captions (annotation_ready.jsonl) for the other stages."""
    ready = annotation_ready_pairs(cfg)
    if stage != "citation_analysis":
        return ready
    ready_ids = {pair["case_pair_id"] for pair in ready}
    return [pair for pair in citation_pairs(cfg) if pair["case_pair_id"] in ready_ids]


def citation_passage_text(passages):
    """All extracted passages for the citation, separated by blank lines ("" if none)."""
    return "\n\n".join(p.strip() for p in passages if p.strip())


def captions_text(captions):
    """Caption dictionary {image_id: caption} as JSON for the pair-selection prompt."""
    return json.dumps(captions, ensure_ascii=False, indent=2, sort_keys=True)


def stage_values(stage, pair, upstream):
    """Values for the {placeholders} of the stage's user template (None if an earlier stage is missing)."""
    if stage == "citation_analysis":
        return {"citing_title": pair["citing_title"], "citing_abstract": pair["citing_abstract"],
                "citation_paragraph": citation_passage_text(pair["citation_passages"]),
                "cited_title": pair["cited_title"], "cited_abstract": pair["cited_abstract"]}

    pair_id = pair["case_pair_id"]
    analysis = upstream["citation_analysis"].get(pair_id)
    if analysis is None:
        return None
    if stage == "question_generation":
        return {"case_a": pair["case_a_description"], "case_b": pair["case_b_description"],
                "citation_reason": analysis}

    questions = upstream["question_generation"].get(pair_id)
    if questions is None:
        return None
    if stage == "answer_generation":
        return {"case_a": pair["case_a_description"], "case_b": pair["case_b_description"],
                "citation_reason": analysis, "questions": questions}

    answers = upstream["answer_generation"].get(pair_id)
    if answers is None:
        return None
    return {"questions": questions, "answers": answers,
            "captions_a": captions_text(pair["case_a_captions"]),
            "captions_b": captions_text(pair["case_b_captions"])}


def build_stage_requests(cfg, stage):
    instructions, template = load_prompt(cfg, stage)
    settings = cfg["llm"]["stages"][stage]
    upstream = {earlier: stage_outputs(cfg, earlier) for earlier in STAGES[:STAGES.index(stage)]}
    requests, waiting_for_upstream = [], 0
    for pair in stage_pairs(cfg, stage):
        values = stage_values(stage, pair, upstream)
        if values is None:
            waiting_for_upstream += 1
            continue
        requests.append(build_request(stage, pair["case_pair_id"], settings, instructions,
                                      fill_template(template, values)))
    return requests, waiting_for_upstream


def outdated_model_outputs(cfg, require_complete):
    """Problems that make the saved stage outputs unfit for the current inputs ([] if none).

    Every stage's requests are rebuilt from the current case pairs, prompts and settings;
    an output whose request hash differs was produced for something else. With
    require_complete, every case pair of every stage must also have an output.
    """
    problems = []
    for stage in STAGES:
        command = f"python -m pmc_pair llm {stage.replace('_', '-')}"
        outputs_path = stage_dir(cfg, stage) / "outputs.jsonl"
        if not outputs_path.exists():
            problems.append(f"{stage}: no outputs yet (run `{command}`)")
            break  # later stages cannot be rebuilt without this one
        requests, waiting = build_stage_requests(cfg, stage)
        current = {request["case_pair_id"]: request["sha256"] for request in requests}
        outputs = list(iter_jsonl(outputs_path))
        stale = sum(1 for line in outputs if current.get(line["case_pair_id"]) != line["request_sha256"])
        missing = len(set(current) - {line["case_pair_id"] for line in outputs}) + waiting
        if stale:
            problems.append(f"{stage}: {stale} outputs belong to other inputs, prompts or settings "
                            f"(re-run `{command}`)")
        if require_complete and missing:
            problems.append(f"{stage}: {missing} case pairs have no output")
    return problems


def run_stage(cfg, stage, action=None, allow_api_calls=False, limit=None,
              import_file=None, request_file=None):
    """Build the stage's requests, optionally obtain responses, and write outputs.jsonl.

    action: None             reuse cached responses only; write pending requests to
                             llm/<stage>/requests/pending_part_*.jsonl for inspection
            "sync"           call the API request by request (needs allow_api_calls)
            "submit-batch"   submit pending requests to the Batch API (needs allow_api_calls)
            "collect-batch"  download finished batches (needs allow_api_calls)
            "import-responses"     import {"request_id", "output_text"} lines from import_file
            "import-batch-output"  import a downloaded batch output file (needs request_file)
    """
    requests, waiting = build_stage_requests(cfg, stage)
    if limit:
        requests = requests[:limit]
    _, pending = split_cached(cfg, stage, requests)

    if action == "sync":
        run_sync(cfg, stage, pending, allow_api_calls)
    elif action == "submit-batch":
        submit_batches(cfg, stage, pending, allow_api_calls)
    elif action == "collect-batch":
        collect_batches(cfg, stage, allow_api_calls)
    elif action == "import-responses":
        import_responses(cfg, stage, requests, import_file)
    elif action == "import-batch-output":
        if not request_file:
            raise SystemExit("--import-batch-output needs --request-file (the batch input file that was submitted)")
        import_batch_output(cfg, stage, request_file, import_file)
    elif action is not None:
        raise ValueError(f"Unknown action {action}")

    answered, pending = write_stage_outputs(cfg, stage, requests)
    if action is None:
        files = write_request_files(cfg, stage, pending, prefix="pending")  # also removes stale pending files
        if files:
            log(cfg, f"{stage}: wrote {len(pending)} pending requests to {len(files)} file(s) in "
                     f"{files[0].parent} (not sent anywhere)")
    log(cfg, f"{stage}: {len(answered)}/{len(requests)} requests answered, {len(pending)} pending"
             + (f", {waiting} pairs waiting for earlier stages" if waiting else ""))
    return {"requests": len(requests), "answered": len(answered), "pending": len(pending),
            "waiting_for_earlier_stages": waiting}
