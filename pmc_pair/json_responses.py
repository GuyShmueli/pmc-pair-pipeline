"""Parse pair proposals, repairing syntax locally before normal validation.

Already valid JSON is never passed through the repair parser. Repair does not
wrap objects into lists, populate schema fields or bypass proposal validation.
"""

from __future__ import annotations

import hashlib
import json
import re

from json_repair import repair_json


CODE_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", re.S)
ARRAY_START = re.compile(r"\[\s*(?=[{\]])")
OTHER_ARRAY = re.compile(r'''\[\s*(?=[\[\]{"'0-9-]|true\b|false\b|null\b)''')
IMAGE_ID_TOKEN = re.compile(r"[0-9]+_[0-9]+_[0-9]+")
REPAIR_VERSION = "0.64.0"


def _is_proposal_list(value):
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _array_payload(text):
    """Remove surrounding prose, without choosing between competing JSON arrays.

    Scan balanced brackets while respecting quoted strings, so brackets in a
    clinical description do not end the payload. Incomplete closing delimiters
    are left to json-repair, but a visibly cut-off quoted value is rejected.
    """
    if text.startswith("{"):
        raise ValueError("Expected a list of pair records, not a single object")
    if text.startswith("["):
        start = 0
    else:
        match = ARRAY_START.search(text)
        if match is None:
            raise ValueError("No list of pair records found")
        start = match.start()
    prefix = text[:start]
    if "{" in prefix or "}" in prefix or OTHER_ARRAY.search(prefix):
        raise ValueError("Cannot extract a list from another JSON object")

    depth, quote, escaped, end = 0, None, False, None
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        # Do not turn a response ending halfway through a description into an
        # apparently complete clinical annotation. Missing closing quotes before
        # explicit object/list delimiters remain repairable.
        if quote is not None and re.search(r"}\s*]\s*$", text) is None:
            raise ValueError("Response ends inside an incomplete quoted value")
        end = len(text)
    suffix = text[end:]
    if "[" in suffix or "{" in suffix or "}" in suffix:
        raise ValueError("Multiple JSON payloads or ambiguous surrounding text")
    return text[start:end].strip(), bool(prefix.strip() or suffix.strip())


def _quote_image_identifiers(payload):
    """Keep bare 123_1_2 tokens as exact strings, not Python-style numbers.

    Only entire unquoted values are touched; quoted text is copied verbatim.
    These strings must still match the retained caption identifiers later.
    """
    output, index, quote, escaped, previous, changed = [], 0, None, False, "", False
    while index < len(payload):
        char = payload[index]
        if quote is None and (payload.startswith("...", index) or char == "…"):
            raise ValueError("Response contains an unquoted omission marker")
        if quote is None and previous in ("[", ",", ":"):
            match = IMAGE_ID_TOKEN.match(payload, index)
            if match is not None and payload[match.end():].lstrip()[:1] in (",", "]", "}"):
                output.append(json.dumps(match.group()))
                index, previous, changed = match.end(), '"', True
                continue
        output.append(char)
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        if not char.isspace():
            previous = char
        index += 1
    return "".join(output), changed


def parse_proposals(text, *, repair_info=None):
    """Return a list of proposal objects or None; optionally record repair evidence.

    A caller-provided dict is populated only when syntax repair is attempted.
    Correct JSON with the wrong structure is rejected, not reshaped. Required
    fields and allowed image IDs are checked by finalize_pairs after this step.
    """
    if repair_info is not None:
        repair_info.clear()
    original = text or ""
    cleaned = original.strip()
    if cleaned.startswith("```"):
        cleaned = CODE_FENCE.sub("", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except ValueError:
        pass
    else:
        return parsed if _is_proposal_list(parsed) else None

    info = repair_info if repair_info is not None else {}
    info.update({
        "status": "failed",
        "original_text": original,
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "repair_library": "json-repair",
        "repair_version": REPAIR_VERSION,
        "repair_details": [],
        "repaired_json": None,
    })
    try:
        payload, extracted = _array_payload(cleaned)
        info["surrounding_text_removed"] = extracted
        # Even after extracting a payload, preserve valid JSON exactly. In
        # particular, do not reinterpret escaped quotes or clinical punctuation.
        try:
            parsed = json.loads(payload)
        except ValueError:
            payload, identifiers_quoted = _quote_image_identifiers(payload)
            info["unquoted_image_identifiers_quoted"] = identifiers_quoted
            parsed, details = repair_json(
                payload, return_objects=True, skip_json_loads=True,
                logging=True, strict=True,
            )
            info["repair_details"] = details
        info["repaired_json"] = json.dumps(parsed, ensure_ascii=False)
        if not _is_proposal_list(parsed):
            raise ValueError("Repaired response is not a JSON list of pair records")
    except (ValueError, IndexError, RecursionError) as exc:
        info["error"] = str(exc)
        return None
    info["status"] = "repaired"
    return parsed
