"""Language-model requests with stable identifiers and a response cache.

Request id    "<stage>:<case_pair_id>", e.g. "citation_analysis:4023003-1__9899453-1".
              It is also the OpenAI Batch `custom_id`, so responses are matched to
              requests by id, never by line order (batch output order is not guaranteed).
Request hash  SHA-256 of the complete request body (model, reasoning effort,
              instructions and filled-in user message).
Cache         <work_dir>/llm/<stage>/responses.jsonl, one line per received response.
              A response is reused only if it was produced for a request with the same
              hash, so changing a prompt, a model setting or an upstream output makes
              exactly the affected requests pending again.

Nothing in this module contacts the API unless the caller passes allow_api_calls=True
(command-line flag --allow-api-calls). Model calls are paid and their outputs are not
deterministic: a fresh run can give different answers than the cached ones.
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .config import log, work_dir
from .io_utils import (append_jsonl, iter_jsonl, read_json, sha256_text, stable_json,
                       utc_now, write_json, write_jsonl)

STAGES = ["citation_analysis", "question_generation", "answer_generation", "pair_selection"]
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
FINISHED_BATCH_STATES = {"completed", "failed", "expired", "cancelled"}


def stage_dir(cfg, stage, *parts):
    return work_dir(cfg, "llm", stage, *parts)


# ---------------------------------------------------------------- building requests

def prompt_files(cfg, stage):
    folder = Path(cfg["paths"]["prompts_dir"])
    return folder / f"{stage}.instructions.txt", folder / f"{stage}.user.txt"


def load_prompt(cfg, stage):
    """(instructions, user-message template), exactly as stored in prompts/<stage>.*.txt"""
    instructions_file, user_file = prompt_files(cfg, stage)
    with open(instructions_file, "r", encoding="utf-8", newline="") as f:  # keep the exact bytes
        instructions = f.read()
    with open(user_file, "r", encoding="utf-8", newline="") as f:
        user_template = f.read()
    return instructions, user_template


def fill_template(template, values):
    """Replace {name} placeholders in one pass (text inside the values is never re-read)."""
    names = set(PLACEHOLDER.findall(template))
    if names != set(values):
        raise ValueError(f"Template placeholders {sorted(names)} do not match values {sorted(values)}")
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def build_request(stage, case_pair_id, settings, instructions, user_text):
    """One request in the format of the OpenAI Responses API (also used inside batch files)."""
    body = {"model": settings["model"]}
    if settings.get("reasoning_effort"):
        body["reasoning"] = {"effort": settings["reasoning_effort"]}
    body["instructions"] = instructions
    body["input"] = [{"role": "user", "content": user_text}]
    body["text"] = {"format": {"type": "text"}}
    return {"request_id": f"{stage}:{case_pair_id}", "case_pair_id": case_pair_id,
            "body": body, "sha256": request_hash(body)}


def request_hash(body):
    return sha256_text(stable_json(body))


# ---------------------------------------------------------------- reading responses

def output_text_from_response(body):
    """Final assistant text of a Responses API result (None if missing or not completed)."""
    if not isinstance(body, dict) or body.get("status") not in (None, "completed"):
        return None
    messages = [item for item in body.get("output") or [] if item.get("type") == "message"]
    final = [m for m in messages if m.get("phase") == "final_answer"]
    chosen = final[0] if final else (messages[-1] if messages else None)
    if chosen is None:
        return None
    text = "\n".join(part.get("text", "") for part in chosen.get("content") or []
                     if part.get("type") == "output_text")
    return text if text.strip() else None


# ---------------------------------------------------------------- cache

def load_cache(cfg, stage):
    """{(request_id, request_sha256): cache entry}"""
    path = stage_dir(cfg, stage) / "responses.jsonl"
    cache = {}
    if path.exists():
        for entry in iter_jsonl(path):
            cache[(entry["request_id"], entry["request_sha256"])] = entry
    return cache


def store_response(cfg, stage, request_id, request_sha256, body, source):
    """Add a successful response to the cache; record a failure otherwise. Returns True on success."""
    text = output_text_from_response(body)
    if text is None:
        append_jsonl({"request_id": request_id, "request_sha256": request_sha256, "source": source,
                      "status": (body or {}).get("status"), "error": (body or {}).get("error"),
                      "recorded_at": utc_now()}, stage_dir(cfg, stage) / "failures.jsonl")
        return False
    append_jsonl({"request_id": request_id, "request_sha256": request_sha256, "output_text": text,
                  "response_id": body.get("id"), "response_model": body.get("model"),
                  "usage": body.get("usage"), "source": source, "received_at": utc_now()},
                 stage_dir(cfg, stage) / "responses.jsonl")
    return True


def split_cached(cfg, stage, requests):
    """(answered, pending): answered = [(request, cache entry)], pending = [request]"""
    cache = load_cache(cfg, stage)
    answered, pending = [], []
    for request in requests:
        entry = cache.get((request["request_id"], request["sha256"]))
        if entry:
            answered.append((request, entry))
        else:
            pending.append(request)
    return answered, pending


def import_responses(cfg, stage, requests, responses_path):
    """Import ready-made outputs: JSONL lines {"request_id": ..., "output_text": ...}.

    The texts are attached to the requests as built at import time (same request id); this
    pipeline cannot check that a text was produced from exactly these inputs, so imported
    responses are marked with the source "import:<file>" and counted in MANIFEST.json.
    Used for the bundled example and for outputs of a run whose request files are lost.
    """
    by_id = {request["request_id"]: request for request in requests}
    imported, unknown = 0, 0
    source = f"import:{Path(responses_path).name}"
    for line in iter_jsonl(responses_path):
        request = by_id.get(line.get("request_id"))
        if request is None:
            unknown += 1
            continue
        body = {"status": "completed", "model": line.get("model"),
                "output": [{"type": "message", "content": [{"type": "output_text",
                                                             "text": line.get("output_text") or ""}]}]}
        imported += store_response(cfg, stage, request["request_id"], request["sha256"], body, source)
    log(cfg, f"{stage}: imported {imported} responses from {responses_path} ({unknown} unknown request ids)")
    if unknown and not imported:
        log(cfg, f"WARNING: none of the request ids in {responses_path} belongs to a current {stage} request. "
                 f"Ids must have the form '{stage}:<case_pair_id>'.")


# ---------------------------------------------------------------- API calls

def require_api_permission(allow_api_calls, n_items, what):
    """Stop unless the user explicitly allowed contacting the (paid) OpenAI API."""
    if n_items == 0:
        return
    if not allow_api_calls:
        raise SystemExit(f"This step would contact the OpenAI API ({n_items} {what}). Model requests are "
                         f"paid. Re-run with --allow-api-calls to confirm.")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set the OPENAI_API_KEY environment variable (never write keys into files).")


def openai_client():
    from openai import OpenAI  # imported here so that offline steps do not need the package
    return OpenAI()


def run_sync(cfg, stage, pending, allow_api_calls):
    """Send pending requests one by one (several in parallel); every response is cached at once."""
    require_api_permission(allow_api_calls, len(pending), f"{stage} requests")
    if not pending:
        return
    client = openai_client()
    raw_path = stage_dir(cfg, stage) / "raw_sync_responses.jsonl"

    def call(request):
        last_error = None
        for attempt in range(1, 4):
            try:
                return request, client.responses.create(**request["body"]).model_dump(), None
            except Exception as error:  # rate limits, network problems, server errors
                last_error = f"{type(error).__name__}: {error}"
                time.sleep(5 * attempt)
        return request, None, last_error

    log(cfg, f"{stage}: sending {len(pending)} requests (synchronous mode)")
    succeeded = 0
    with ThreadPoolExecutor(max_workers=int(cfg["llm"]["sync_workers"])) as pool:
        futures = [pool.submit(call, request) for request in pending]
        for future in as_completed(futures):
            request, body, error = future.result()
            if body is not None:
                append_jsonl({"request_id": request["request_id"], "request_sha256": request["sha256"],
                              "response": body}, raw_path)
            else:
                body = {"status": "request_error", "error": error}
            succeeded += store_response(cfg, stage, request["request_id"], request["sha256"], body, "sync")
    log(cfg, f"{stage}: {succeeded}/{len(pending)} requests answered")


def write_request_files(cfg, stage, requests, prefix):
    """Batch input files (JSONL), split to respect the Batch API size limits."""
    batch_settings = cfg["llm"]["batch"]
    folder = stage_dir(cfg, stage, "requests")
    for old_file in folder.glob(f"{prefix}_part_*.jsonl"):
        old_file.unlink()
    files, lines, size = [], [], 0

    def flush():
        path = folder / f"{prefix}_part_{len(files) + 1:03d}.jsonl"
        path.write_text("".join(lines), encoding="utf-8", newline="\n")
        files.append(path)

    for request in requests:
        line = stable_json({"custom_id": request["request_id"], "method": "POST",
                            "url": batch_settings["endpoint"], "body": request["body"]}) + "\n"
        line_size = len(line.encode("utf-8"))
        if lines and (len(lines) >= batch_settings["max_requests_per_file"]
                      or size + line_size > batch_settings["max_bytes_per_file"]):
            flush()
            lines, size = [], 0
        lines.append(line)
        size += line_size
    if lines:
        flush()
    return files


def batches_record_path(cfg, stage):
    return stage_dir(cfg, stage) / "batches.json"


def submit_batches(cfg, stage, pending, allow_api_calls):
    """Write pending requests to new batch files and submit them to the OpenAI Batch API."""
    require_api_permission(allow_api_calls, len(pending), f"{stage} requests in a batch")
    if not pending:
        return
    record_path = batches_record_path(cfg, stage)
    batches = read_json(record_path) if record_path.exists() else []
    in_flight = [b for b in batches if not b.get("imported")]
    if in_flight:
        raise SystemExit(f"{stage}: {len(in_flight)} submitted batches have not been collected yet. "
                         f"Run with --collect-batch first (or delete {record_path} to forget them).")

    client = openai_client()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for path in write_request_files(cfg, stage, pending, prefix=f"batch_{stamp}"):
        with open(path, "rb") as f:
            uploaded = client.files.create(file=f, purpose="batch")
        # Record the upload before creating the batch: if the program stops in between,
        # collect_batches can still find the batch, and nothing is submitted (and paid) twice.
        record = {"request_file": path.name, "input_file_id": uploaded.id, "batch_id": None,
                  "status": "uploaded", "submitted_at": utc_now(), "imported": False}
        batches.append(record)
        write_json(batches, record_path)
        batch = client.batches.create(input_file_id=uploaded.id, endpoint=cfg["llm"]["batch"]["endpoint"],
                                      completion_window=cfg["llm"]["batch"]["completion_window"],
                                      metadata={"stage": stage, "request_file": path.name})
        record.update(batch_id=batch.id, status=batch.status)
        write_json(batches, record_path)
        log(cfg, f"{stage}: submitted {path.name} as batch {batch.id}")


def collect_batches(cfg, stage, allow_api_calls):
    """Download finished batches and import their outputs (matched by custom_id)."""
    record_path = batches_record_path(cfg, stage)
    batches = read_json(record_path) if record_path.exists() else []
    waiting = [b for b in batches if not b.get("imported")]
    require_api_permission(allow_api_calls, len(waiting), f"{stage} batches to check and download")
    if not waiting:
        log(cfg, f"{stage}: no submitted batches waiting to be collected")
        return
    client = openai_client()
    for record in waiting:
        if not record.get("batch_id"):  # submission was interrupted after the upload
            found = [b for b in client.batches.list() if b.input_file_id == record["input_file_id"]]
            if not found:
                log(cfg, f"{stage}: no batch exists for {record['request_file']}; delete this entry from "
                         f"{record_path} and submit again")
                continue
            record["batch_id"] = found[0].id
            write_json(batches, record_path)
        batch = client.batches.retrieve(record["batch_id"])
        record["status"] = batch.status
        if batch.status not in FINISHED_BATCH_STATES:
            log(cfg, f"{stage}: batch {record['batch_id']} is {batch.status}; try again later")
            continue
        outputs_folder = stage_dir(cfg, stage, "batch_outputs")
        for kind, file_id in (("output", batch.output_file_id), ("errors", batch.error_file_id)):
            if file_id:
                path = outputs_folder / f"{record['batch_id']}_{kind}.jsonl"
                path.write_text(client.files.content(file_id).text, encoding="utf-8", newline="\n")
                import_batch_output(cfg, stage, stage_dir(cfg, stage, "requests") / record["request_file"],
                                    path, source=f"batch:{record['batch_id']}")
        record["imported"] = True
        write_json(batches, record_path)
    write_json(batches, record_path)


def import_batch_output(cfg, stage, request_file, output_file, source=None):
    """Import a Batch API output (or error) file using the request file that was submitted."""
    requests = {}
    for line in iter_jsonl(request_file):
        requests[line["custom_id"]] = request_hash(line["body"])
    source = source or f"batch_file:{Path(output_file).name}"
    seen, succeeded, unknown = set(), 0, 0
    for line in iter_jsonl(output_file):
        custom_id = line.get("custom_id")
        if custom_id not in requests:
            unknown += 1
            continue
        seen.add(custom_id)
        response = line.get("response") or {}
        body = response.get("body") if response.get("status_code") == 200 else None
        if body is None:
            body = {"status": f"http_{response.get('status_code')}", "error": line.get("error")}
        succeeded += store_response(cfg, stage, custom_id, requests[custom_id], body, source)
    log(cfg, f"{stage}: {Path(output_file).name}: {succeeded} answered, {len(seen) - succeeded} failed, "
             f"{len(requests) - len(seen)} not in this file, {unknown} unknown ids")


# ---------------------------------------------------------------- stage outputs

def write_stage_outputs(cfg, stage, requests):
    """outputs.jsonl: the cached answer of every current request (in request order)."""
    answered, pending = split_cached(cfg, stage, requests)
    write_jsonl([{"case_pair_id": request["case_pair_id"], "request_id": request["request_id"],
                  "request_sha256": request["sha256"], "output_text": entry["output_text"],
                  "response_model": entry.get("response_model"), "source": entry["source"]}
                 for request, entry in answered], stage_dir(cfg, stage) / "outputs.jsonl")
    write_json({"requests": len(requests), "answered": len(answered), "pending": len(pending)},
               stage_dir(cfg, stage) / "stats.json")
    return answered, pending


def stage_outputs(cfg, stage):
    """{case_pair_id: output_text} of a finished stage."""
    path = stage_dir(cfg, stage) / "outputs.jsonl"
    if not path.exists():
        raise SystemExit(f"No outputs for stage {stage}; run `python -m pmc_pair llm {stage.replace('_', '-')}` first.")
    return {line["case_pair_id"]: line["output_text"] for line in iter_jsonl(path)}
