"""Malformed LLM responses are repaired without weakening pair validation."""

import hashlib
import json

import pytest

from pmc_pair import json_responses, pair_parsing
from pmc_pair.io_utils import read_jsonl, write_jsonl


PAIR = {"pair_id": ["1_1_1", "2_1_1"], "modality": "CT",
        "anatomy": "lung", "diagnosis": "mass"}
VALID = json.dumps([PAIR], separators=(",", ":"))


@pytest.mark.parametrize("text", [
    VALID,
    "```json\n" + VALID + "\n```",
    "  \n" + VALID + "\n  ",
    "[]",
    json.dumps([{**PAIR, "diagnosis": 'Crohn\'s disease, café; "lesion" [left]'}], ensure_ascii=False),
])
def test_valid_json_never_enters_repair(text, monkeypatch):
    def unexpected_repair(*args, **kwargs):
        pytest.fail("Valid JSON must not pass through the repair library")
    monkeypatch.setattr(json_responses, "repair_json", unexpected_repair)
    info = {}
    result = json_responses.parse_proposals(text, repair_info=info)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = json_responses.CODE_FENCE.sub("", cleaned).strip()
    assert result == json.loads(cleaned)
    assert info == {}


@pytest.mark.parametrize("text", [
    '[{pair_id: ["1_1_1", "2_1_1"], modality: CT, anatomy: lung, diagnosis: mass}]',
    VALID.replace('"1_1_1"', '1_1_1').replace('"2_1_1"', '2_1_1'),
    VALID.replace('"', "'"),
    VALID.replace('"2_1_1"]', '"2_1_1",]').replace('"mass"}', '"mass",}').replace('}]', '},]'),
    VALID.replace(',"anatomy"', ' "anatomy"'),
    VALID[:-1],  # only the closing array delimiter is missing
    VALID[:-2],  # closing object and array delimiters are missing
    VALID.replace('"mass"', 'mass"'),  # missing opening quotation mark
    VALID.replace('"mass"', '"mass'),  # missing closing quotation mark
    'Here are the positive matches:\n' + VALID + '\nOne pair was found.',
    'Here are the matches:\n```json\n' + VALID + '\n```\nDone.',
    'Results [for review]:\n' + VALID + '\nEnd.',
])
def test_repairs_common_formatting_errors(text):
    info = {}
    assert json_responses.parse_proposals(text, repair_info=info) == [PAIR]
    assert info["status"] == "repaired"
    assert info["original_text"] == text
    assert info["original_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert json.loads(info["repaired_json"]) == [PAIR]


def test_prose_around_empty_list_is_a_successful_empty_response():
    info = {}
    assert json_responses.parse_proposals("Here are the positive matches: []", repair_info=info) == []
    assert info["status"] == "repaired"


@pytest.mark.parametrize("text", [
    "nothing to extract", "", "42", '"not a list"',
    json.dumps(PAIR), json.dumps({"pairs": [PAIR]}),
    json.dumps([PAIR, 42]), json.dumps([[PAIR]]),
    '[[' + json.dumps(PAIR) + ',],]',
    VALID + '\n' + VALID,
    VALID + ' [1,2]',
    VALID + ' ["another"]',
    VALID + ' [[1]]',
    'First: [1,2]\nThen: ' + VALID,
    'First: ["another"]\nThen: ' + VALID,
    'First option: ' + VALID + '\nAlternative: ' + VALID,
    VALID.replace('"modality":"CT"', 'modality: MRI, modality: CT'),
    VALID[:-4],  # the clinical string is cut off, not merely a bracket
    VALID[:-7] + 'mass [left]',  # clinical brackets cannot stand in for JSON closers
    VALID[:-7] + 'mass {left}',
    VALID[:-1] + ', ...]',
    VALID[:-1] + ', …]',
    'Here is an object: {"pairs": ' + VALID + '}',
    '__import__("os").system("not executed")',
])
def test_unsupported_or_ambiguous_inputs_are_not_salvaged(text):
    assert json_responses.parse_proposals(text) is None


def test_repaired_text_preserves_clinical_punctuation():
    record = {**PAIR, "diagnosis": 'Crohn\'s disease, café; "lesion" [left]'}
    text = "Result:\n" + json.dumps([record], ensure_ascii=False) + "\nDone."
    assert json_responses.parse_proposals(text) == [record]


def test_finalize_repairs_then_validates_and_deduplicates(tmp_path, monkeypatch):
    cfg = {"paths": {"work_dir": str(tmp_path / "work")}}
    # This test isolates finalization; stale-cache checks have independent tests.
    monkeypatch.setattr(pair_parsing, "outdated_model_outputs", lambda *a, **k: [])
    ready = [{"case_pair_id": "a", "case_a_captions": {"1_1_1": "a", "1_1_2": "c"},
              "case_b_captions": {"2_1_1": "b", "2_1_2": "d"}},
             {"case_pair_id": "b", "case_a_captions": {"1_1_1": "a"},
              "case_b_captions": {"2_1_1": "b"}},
             {"case_pair_id": "c", "case_a_captions": {"1_1_1": "a"},
              "case_b_captions": {"2_1_1": "b"}}]
    monkeypatch.setattr(pair_parsing, "annotation_ready_pairs", lambda cfg: ready)
    proposals = [
        {**PAIR, "diagnosis": ""},  # invalid first proposal must not claim the pair
        PAIR,
        {**PAIR, "pair_id": list(reversed(PAIR["pair_id"])), "diagnosis": "different"},
        {**PAIR, "pair_id": ["1_1_1", "unknown"]},
        {**PAIR, "pair_id": ["1_1_1", "1_1_2"]},
        {**PAIR, "pair_id": ["1_1_2", "2_1_2"], "modality": 7},
        {"pair_id": ["1_1_2", "2_1_2"], "modality": "CT", "anatomy": "lung"},
        {**PAIR, "pair_id": ["1_1_2", "2_1_2"]},
    ]
    raw = "Here are the results:\n" + json.dumps(proposals) + "\nDone."
    outputs = tmp_path / "work" / "llm" / "pair_selection" / "outputs.jsonl"
    # Deliberately reverse response order: sorting by case-pair ID must win.
    write_jsonl([{"case_pair_id": "b", "output_text": json.dumps([{**PAIR, "diagnosis": "later"}])},
                 {"case_pair_id": "c", "output_text": "no JSON supplied"},
                 {"case_pair_id": "a", "output_text": raw}], outputs)
    before = outputs.read_bytes()
    stats = pair_parsing.finalize_pairs(cfg)
    folder = tmp_path / "work" / "image_pairs"
    kept = read_jsonl(folder / "image_pairs.jsonl")
    assert len(kept) == 2
    assert kept[0]["case_pair_id"] == "a"
    assert kept[0]["diagnosis"] == "mass"
    assert stats["duplicate_items"] == 2
    assert stats["rejected_items"] == {"missing_field": 3, "pair_id_not_in_case_captions": 2}
    assert stats["outputs_repair_attempted"] == 2
    assert stats["outputs_repaired"] == 1
    assert stats["outputs_repair_failed"] == 1
    repairs = read_jsonl(folder / "response_repairs.jsonl")
    assert repairs[0]["original_text"] == raw
    assert repairs[0]["kept_proposals"] == 2
    assert repairs[0]["rejected_proposals"] == 5
    assert repairs[0]["duplicate_proposals"] == 1
    assert repairs[1]["status"] == "failed"
    assert outputs.read_bytes() == before
    # Re-running overwrites evidence for this run instead of appending duplicates.
    pair_parsing.finalize_pairs(cfg)
    assert read_jsonl(folder / "response_repairs.jsonl") == repairs
    assert read_jsonl(folder / "image_pairs.jsonl") == kept
