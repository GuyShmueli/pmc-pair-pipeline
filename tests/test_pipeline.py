"""Tests for the errors that matter most: misaligned records, duplicate pairs, inconsistent
labels and splits, stale cached responses, and accidental API calls.

The synthetic example (examples/make_example_data.py) is built and run once (offline,
about 10 seconds); Tesseract OCR must be installed for that part.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from lxml import etree

from pmc_pair import cases, checks, chipa, export, figures, image_filter, jats, labels, llm, pair_parsing
from pmc_pair import pmc_download, prepare_pairs, splits
from pmc_pair.config import load_config
from pmc_pair.io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl

REPOSITORY = Path(__file__).resolve().parents[1]
TAXONOMY = REPOSITORY / "label_taxonomy.json"
sys.path.insert(0, str(REPOSITORY / "examples"))
import make_example_data  # noqa: E402


def run_example(root):
    make_example_data.main(root / "data")
    config = {
        "paths": {"pmc_patients": "data/pmc_patients_example.csv", "pmc_source": "data/pmc_mirror",
                  "work_dir": "data/work", "release_dir": "data/release", "existing_split": None},
        "workers": 2, "download": {"workers": 2},
        "split": {"seed": 42, "fractions": {"train": 0.4, "val": 0.4, "test": 0.2}},  # as examples/example_config.yaml
        "release": {"images_per_zip": 4},
    }
    (root / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    cfg = load_config(root / "config.yaml")
    for step in (cases.select_cases, pmc_download.download_articles, figures.extract_figures,
                 image_filter.filter_images, prepare_pairs.prepare_pairs):
        step(cfg)
    for stage in llm.STAGES:
        chipa.run_stage(cfg, stage, action="import-responses",
                        import_file=root / "data" / "llm_responses" / f"{stage}.jsonl")
    for step in (pair_parsing.finalize_pairs, labels.label_images, splits.make_split, export.export_release):
        step(cfg)
    return cfg


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    if shutil.which("tesseract") is None:
        pytest.skip("Tesseract OCR is not installed")
    return run_example(tmp_path_factory.mktemp("example"))


def copy_of_work(cfg, tmp_path):
    """Configuration that points to a private copy of the example work directory."""
    new_cfg = json.loads(json.dumps(cfg))
    new_cfg["paths"]["work_dir"] = str(tmp_path / "work")
    shutil.copytree(cfg["paths"]["work_dir"], new_cfg["paths"]["work_dir"])
    return new_cfg


# ---------------------------------------------------------------- end to end

def test_example_run_gives_expected_release(example):
    work, release = Path(example["paths"]["work_dir"]), Path(example["paths"]["release_dir"])
    assert checks.check_release(release)["passed"]

    # each filter removed exactly the case it was built to catch
    case_stats = read_json(work / "cases" / "stats.json")
    assert (case_stats["multi_patient_articles"], case_stats["self_links_removed"],
            case_stats["candidate_case_pairs"]) == (1, 1, 11)
    pair_checks = read_json(work / "pairs" / "stats.json")
    assert pair_checks["status_counts"] == {
        "ready": 5, "animal_case": 1, "citation_not_confirmed": 1, "no_retained_figure": 1,
        "missing_case_description": 1, "article_unavailable": 2}
    assert (pair_checks["citation_confirmed_pairs"], pair_checks["annotation_ready_pairs"]) == (7, 5)
    pair_stats = read_json(work / "image_pairs" / "stats.json")
    assert pair_stats["rejected_items"] == {"pair_id_not_in_case_captions": 2, "missing_field": 1}
    assert (pair_stats["duplicate_items"], pair_stats.get("outputs_not_a_json_array", 0)) == (1, 0)
    assert pair_stats["outputs_repaired"] == 1

    pairs = read_json(release / "image_pairs.json")
    assert [p["pair_id"] for p in pairs] == [["99000001_1_1", "99000002_1_1"], ["99000001_1_3", "99000002_1_3"],
                                             ["99000010_1_1", "99000011_1_1"], ["99000012_1_1", "99000013_1_1"],
                                             ["99000012_1_2", "99000013_1_2"]]  # a histology pair: any shared modality family
    # the first examples of the table in docs/LABEL_RULES.md
    image_labels = {r["image_id"]: r["labels"] for r in read_jsonl(release / "image_labels.jsonl")}
    assert image_labels["99000001_1_1"] == {"modality": ["mri"], "anatomy": ["musculoskeletal", "spine_spinal_cord"],
                                           "diagnosis": ["infection_or_abscess"]}
    # the published version is preferred over the author manuscript
    assert pmc_download.downloaded_articles(example)["99000002"]["version"] == "PMC99000002.2"
    # citation records for the annotation-ready pairs only (5 of the 7 confirmed citations)
    records = {(r["citing_case"], r["cited_case"]): r for r in read_json(release / "case_pair_citations.json")}
    assert len(records) == 5
    assert records[("PMC99000003", "PMC99000002")]["extracted_citation"].endswith(
        "Paraspinal muscle abscess 2 | MRI | Lumbar paraspinal muscles")  # citation in a table row
    assert records[("PMC99000013", "PMC99000012")]["extracted_citation"] == ""  # plain-text citation, no <xref>
    assert len(list(release.glob("images_part_*.zip"))) == 3  # 10 images, 4 per archive


# ---------------------------------------------------------------- language-model bookkeeping

def test_batch_output_is_matched_by_custom_id_not_line_order(example, tmp_path):
    cfg = copy_of_work(example, tmp_path)
    shutil.rmtree(Path(cfg["paths"]["work_dir"]) / "llm" / "citation_analysis")
    assert chipa.run_stage(cfg, "citation_analysis")["pending"] == 5
    request_file = Path(cfg["paths"]["work_dir"]) / "llm" / "citation_analysis" / "requests" / "pending_part_001.jsonl"
    request_ids = [line["custom_id"] for line in read_jsonl(request_file)]

    # Batch output in reverse order, with one failed request and one unknown id
    output = [{"custom_id": "citation_analysis:unknown", "response": {"status_code": 200, "body": {}}}]
    for custom_id in reversed(request_ids):
        if custom_id == request_ids[0]:
            output.append({"custom_id": custom_id, "response": {"status_code": 500, "body": None},
                           "error": {"message": "server error"}})
            continue
        body = {"status": "completed", "model": "gpt-5.4-mini-2026-03-17",
                "output": [{"type": "reasoning", "summary": []},
                           {"type": "message", "content": [{"type": "output_text", "text": f"answer for {custom_id}"}]}]}
        output.append({"custom_id": custom_id, "response": {"status_code": 200, "body": body}})
    output_file = tmp_path / "batch_output.jsonl"
    write_jsonl(output, output_file)

    result = chipa.run_stage(cfg, "citation_analysis", action="import-batch-output",
                             import_file=output_file, request_file=request_file)
    assert (result["answered"], result["pending"]) == (4, 1)
    outputs = read_jsonl(Path(cfg["paths"]["work_dir"]) / "llm" / "citation_analysis" / "outputs.jsonl")
    assert all(line["output_text"] == f"answer for {line['request_id']}" for line in outputs)
    assert request_ids[0] not in {line["request_id"] for line in outputs}


def test_changed_prompt_makes_cached_responses_stale(example, tmp_path):
    cfg = copy_of_work(example, tmp_path)
    prompts = tmp_path / "prompts"
    shutil.copytree(cfg["paths"]["prompts_dir"], prompts)
    cfg["paths"]["prompts_dir"] = str(prompts)
    instructions = prompts / "question_generation.instructions.txt"
    original = instructions.read_text(encoding="utf-8")

    assert chipa.run_stage(cfg, "question_generation")["pending"] == 0
    instructions.write_text(original + "\nBe brief.", encoding="utf-8")
    with pytest.raises(SystemExit):  # saved outputs do not match the changed prompt: later steps refuse them
        pair_parsing.finalize_pairs(cfg)
    assert chipa.run_stage(cfg, "question_generation")["answered"] == 0  # and the cache is not reused
    instructions.write_text(original, encoding="utf-8")
    assert chipa.run_stage(cfg, "question_generation")["answered"] == 5


def test_api_is_only_contacted_when_allowed(example, tmp_path, monkeypatch):
    cfg = copy_of_work(example, tmp_path)
    shutil.rmtree(Path(cfg["paths"]["work_dir"]) / "llm" / "pair_selection")
    with pytest.raises(SystemExit):
        chipa.run_stage(cfg, "pair_selection", action="sync")  # no --allow-api-calls

    class FakeClient:  # stands in for openai.OpenAI(); returns Responses-API-shaped objects
        def __init__(self):
            self.batch_requests = []
            self.responses = SimpleNamespace(create=self.create)
            self.files = SimpleNamespace(create=self.upload, content=self.content)
            self.batches = SimpleNamespace(create=self.create_batch, retrieve=self.retrieve)

        def create(self, **body):
            text = "[]"
            return SimpleNamespace(model_dump=lambda: {"id": "resp_1", "status": "completed", "model": body["model"],
                                                       "output": [{"type": "message", "content": [
                                                           {"type": "output_text", "text": text}]}]})

        def upload(self, file, purpose):
            self.batch_requests = [json.loads(line) for line in file.read().decode("utf-8").splitlines()]
            return SimpleNamespace(id="file_in")

        def create_batch(self, **kwargs):
            return SimpleNamespace(id="batch_1", status="validating")

        def retrieve(self, batch_id):
            return SimpleNamespace(status="completed", output_file_id="file_out", error_file_id=None)

        def content(self, file_id):
            lines = [json.dumps({"custom_id": r["custom_id"], "response": {"status_code": 200, "body": {
                "status": "completed", "model": "fake", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "[]"}]}]}}}) for r in reversed(self.batch_requests)]
            return SimpleNamespace(text="\n".join(lines))

    fake = FakeClient()
    monkeypatch.setattr(llm, "openai_client", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")

    result = chipa.run_stage(cfg, "pair_selection", action="submit-batch", allow_api_calls=True, limit=2)
    assert result["pending"] == 2 and len(fake.batch_requests) == 2
    with pytest.raises(SystemExit):  # a second submission before collecting would pay twice
        chipa.run_stage(cfg, "pair_selection", action="submit-batch", allow_api_calls=True)
    result = chipa.run_stage(cfg, "pair_selection", action="collect-batch", allow_api_calls=True)
    assert (result["answered"], result["pending"]) == (5 - 3, 3)
    result = chipa.run_stage(cfg, "pair_selection", action="sync", allow_api_calls=True)
    assert (result["answered"], result["pending"]) == (5, 0)


# ---------------------------------------------------------------- release checks

def corrupt_and_check(example, tmp_path, file_name, corrupt):
    release = tmp_path / "release"
    shutil.copytree(example["paths"]["release_dir"], release)
    path = release / file_name
    data = read_jsonl(path) if path.suffix == ".jsonl" else read_json(path)
    corrupt(data)
    write_jsonl(data, path) if path.suffix == ".jsonl" else write_json(data, path)
    return " | ".join(checks.check_release(release)["problems"])


def test_release_check_compares_the_split_with_its_regeneration(example, tmp_path):
    release = tmp_path / "release"
    shutil.copytree(example["paths"]["release_dir"], release)
    assert checks.check_release(release, split_settings=example["split"])["passed"]
    split = read_json(release / "image_splits.json")
    swap = {"train": "val", "val": "train", "test": "test"}  # whole groups move: still article-disjoint
    write_json({image_id: swap[name] for image_id, name in split.items()}, release / "image_splits.json")
    problems = " | ".join(checks.check_release(release, split_settings=example["split"])["problems"])
    assert "differ from the split regenerated" in problems and "cross partitions" not in problems


def test_release_checks_detect_consequential_errors(example, tmp_path):
    def duplicate_reversed_pair(pairs):
        pairs.append({**pairs[0], "pair_id": pairs[0]["pair_id"][::-1], "captions": pairs[0]["captions"][::-1]})

    def misalign_captions(pairs):
        pairs[1]["captions"] = pairs[1]["captions"][::-1]

    def split_a_pair(split):
        split["99000001_1_1"] = "test" if split["99000002_1_1"] != "test" else "train"

    def change_a_label(image_labels):
        image_labels[0]["labels"]["modality"] = ["ct"]

    def name_pet_in_a_caption(pairs):  # the labels then lack nuclear_medicine for that image
        pairs[0]["captions"][0]["caption"] += " PET/CT shows uptake."

    def empty_a_caption(pairs):
        pairs[0]["captions"][0]["caption"] = None

    assert "duplicate pair" in corrupt_and_check(example, tmp_path / "a", "image_pairs.json",
                                                 duplicate_reversed_pair)
    assert "not aligned" in corrupt_and_check(example, tmp_path / "b", "image_pairs.json", misalign_captions)
    assert "cross partitions" in corrupt_and_check(example, tmp_path / "c", "image_splits.json", split_a_pair)
    assert "recomputed" in corrupt_and_check(example, tmp_path / "d", "image_labels.jsonl", change_a_label)
    assert "recomputed" in corrupt_and_check(example, tmp_path / "f", "image_pairs.json", name_pet_in_a_caption)
    assert "empty caption" in corrupt_and_check(example, tmp_path / "g", "image_pairs.json", empty_a_caption)

    release = tmp_path / "e" / "release"  # two image files swapped inside an archive after export
    shutil.copytree(example["paths"]["release_dir"], release)
    archive_path = sorted(release.glob("images_part_*.zip"))[0]
    with zipfile.ZipFile(archive_path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    first, second = sorted(entries)[:2]
    entries[first], entries[second] = entries[second], entries[first]
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    assert "MANIFEST.json" in " | ".join(checks.check_release(release)["problems"])


def test_checkpoint_survives_a_crash_while_writing(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    append_jsonl({"id": 1}, path)
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"id": 2, "unfini')  # process killed in the middle of a line
    append_jsonl({"id": 3}, path)  # the resumed run appends the next record
    assert [record["id"] for record in read_jsonl(path)] == [1, 3]


# ---------------------------------------------------------------- method details

def test_figure_index_counts_every_fig_element():
    """Image ids use the position of <fig> in the XML, counting figures that are skipped later."""
    xml = (b'<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>'
           b'<fig id="ga"><graphic xlink:href="ga1"/></fig>'  # no caption: skipped, but counted
           b'<fig id="f1"><label>Figure 1</label><caption><p>MRI <italic>T2</italic> image.</p></caption>'
           b'<graphic xlink:href="g1"/></fig>'
           b'<fig-group><fig id="f2a"><caption><p>CT.</p></caption><graphic xlink:href="g2a"/></fig>'
           b'<fig id="f2b"><caption><p>US.</p></caption><graphic xlink:href="g2b"/></fig></fig-group></body>'
           b'<floats-group><fig id="f3"><caption><p>X-ray.</p></caption><graphic xlink:href="g3.gif"/></fig>'
           b'</floats-group></article>')
    found = jats.list_figures(etree.ElementTree(etree.fromstring(xml)))
    assert [(f["index"], f["xml_id"]) for f in found] == [(1, "ga"), (2, "f1"), (3, "f2a"), (4, "f2b"), (5, "f3")]
    assert (found[0]["caption"], found[1]["caption"]) == ("", "MRI T2 image.")

    files = {"g1.jpg": "g1.jpg", "g3.jpg": "g3.jpg", "cric2020-4726529.001.jpg": "CRIC2020-4726529.001.jpg"}
    jpeg = [".jpg", ".jpeg"]
    assert figures.find_image_file("g1", files, jpeg) == "g1.jpg"  # no extension in the XML
    assert figures.find_image_file("g3.gif", files, jpeg) == "g3.jpg"  # JPEG preferred over the GIF thumbnail
    assert figures.find_image_file("CRIC2020-4726529.001", files, jpeg) == "CRIC2020-4726529.001.jpg"
    assert figures.find_image_file("g2a", files, jpeg) is None


def test_case_description_reads_case_report_sections():
    xml = (b'<article><body>'
           b'<sec><title>Case presentation</title><p>A 7-year-old boy had fever.</p>'
           b'<sec><title>Case history</title><p>He had no prior illness.</p></sec>'  # read once, with its parent
           b'<fig id="f1"><caption><p>MRI of the spine.</p></caption></fig></sec>'  # caption left out
           b'<sec><title>Review of previously reported cases</title><p>Ten other patients.</p></sec>'
           b'<sec><title>Showcase</title><p>Not a case-report heading.</p></sec></body></article>')
    text = jats.case_description(etree.ElementTree(etree.fromstring(xml)))
    assert text == "A 7-year-old boy had fever. He had no prior illness."


def test_label_mapping_reproduces_the_paper_and_known_examples():
    rules = labels.load_label_rules(TAXONOMY)

    def mapped(text, field="diagnosis"):
        return labels.map_description(text, field, rules)

    # the examples of the table in docs/LABEL_RULES.md
    assert mapped("MRI", "modality") == ["mri"]
    assert mapped("lumbar spine/paraspinal muscles/epidural space", "anatomy") == ["musculoskeletal",
                                                                                   "spine_spinal_cord"]
    assert mapped("paraspinal abscess with spinal epidural abscess") == ["infection_or_abscess"]
    assert mapped("hepatic abscess") == mapped("liver abscess") == ["infection_or_abscess"]
    assert mapped("tumor") == mapped("mass") == mapped("unspecified lesion") == ["mass_or_lesion"]
    assert mapped("abscess lesion") == ["infection_or_abscess"]  # specific condition before generic lesion term
    assert mapped("no abscess") == ["normal_or_negative_report"]
    assert mapped("resolved abscess") == ["postoperative_or_resolved_state"]

    # 96 further descriptions with known categories
    examples = read_json(REPOSITORY / "tests" / "label_examples.json")["examples"]
    wrong = [(field, text, expected, mapped(text, field)) for field, items in examples.items()
             for text, expected in items if mapped(text, field) != expected]
    assert not wrong, wrong

    # a compound figure: union over its pairs, "other" only without a known category, and
    # no labels for images that share no pair
    pairs = [{"pair_id": ["a_1_1", "b_1_1"], "modality": "CT", "anatomy": "liver", "diagnosis": "tumor"},
             {"pair_id": ["a_1_1", "c_1_1"], "modality": "MRI", "anatomy": "spinal cord", "diagnosis": "abscess"},
             {"pair_id": ["a_1_1", "d_1_1"], "modality": "unknown modality", "anatomy": "unknown anatomy",
              "diagnosis": "unknown diagnosis"}]
    by_image = {r["image_id"]: r["labels"]
                for r in labels.combine_image_labels(labels.pair_categories(pairs, rules), "other")}
    assert by_image["a_1_1"] == {"modality": ["ct", "mri"], "anatomy": ["hepatobiliary_pancreatic", "spine_spinal_cord"],
                                 "diagnosis": ["infection_or_abscess", "mass_or_lesion"]}
    assert by_image["d_1_1"] == {field: ["other"] for field in labels.FIELDS}
    assert (by_image["b_1_1"]["diagnosis"], by_image["c_1_1"]["diagnosis"]) == (["mass_or_lesion"],
                                                                              ["infection_or_abscess"])


def test_nuclear_medicine_is_also_read_from_the_image_caption():
    rules = labels.load_label_rules(TAXONOMY)
    found = labels.caption_categories({
        "a_1_1": "(A) Contrast-enhanced CT shows a mass. (B) 18F-FDG PET/CT shows intense uptake.",
        "b_1_1": "Whole-body bone scintigraphy with 99mTc-MDP.",
        "c_1_1": "Chest X ray of the patient's pet dog.",                        # the ordinary word
        "d_1_1": "Patch test with levocetirizine (10% in Pet.) was positive.",  # petrolatum
        "e_1_1": "Axial CT of the abdomen.",
        "f_1_1": "Positron emission tomography.",
        "g_1_1": "Coronal PET/CT of the chest.",                                 # the abbreviation alone
    }, rules)
    assert found == {"a_1_1": ["fdg", "pet"], "b_1_1": ["scintigraphy"], "f_1_1": ["positron emission tomography"],
                     "g_1_1": ["pet"]}

    # the category joins the pair categories; "other" goes when it is the only other category;
    # images that share no pair still receive no labels
    pairs = [{"pair_id": ["a_1_1", "e_1_1"], "modality": "CT", "anatomy": "liver", "diagnosis": "tumor"},
             {"pair_id": ["f_1_1", "c_1_1"], "modality": "unknown modality", "anatomy": "liver", "diagnosis": "tumor"}]
    by_image = {r["image_id"]: r["labels"]["modality"]
                for r in labels.combine_image_labels(labels.pair_categories(pairs, rules), "other", found)}
    assert by_image == {"a_1_1": ["ct", "nuclear_medicine"], "c_1_1": ["other"], "e_1_1": ["ct"],
                        "f_1_1": ["nuclear_medicine"]}


def test_label_images_reads_the_captions_of_the_annotation_ready_pairs(tmp_path):
    work = tmp_path / "work"
    cfg = {"paths": {"work_dir": str(work), "label_rules": str(TAXONOMY)}}
    write_jsonl([{"pair_id": ["a_1_1", "b_1_1"], "modality": "CT", "anatomy": "liver", "diagnosis": "tumor"}],
                work / "image_pairs" / "image_pairs.jsonl")
    write_jsonl([{"case_a_captions": {"a_1_1": "(A) Contrast-enhanced CT. (B) PET/CT shows uptake."},
                  "case_b_captions": {"b_1_1": "Axial CT of the liver."}}], work / "pairs" / "annotation_ready.jsonl")
    stats = labels.label_images(cfg)
    by_image = {r["image_id"]: r["labels"]["modality"] for r in read_jsonl(work / "labels" / "image_labels.jsonl")}
    assert by_image == {"a_1_1": ["ct", "nuclear_medicine"], "b_1_1": ["ct"]}
    assert read_json(work / "labels" / "caption_matches.json") == {
        "a_1_1": {"words": ["pet"], "also_from_pair_descriptions": False}}
    assert stats["caption_rule"]["images_with_the_category_only_from_the_caption"] == 1


def test_pmc_cloud_listing_and_version_choice():
    listing = (b'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
               b'<Name>pmc-oa-opendata</Name><IsTruncated>true</IsTruncated><NextContinuationToken>abc</NextContinuationToken>'
               b'<Contents><Key>PMC11370360.2/PMC11370360.2.xml</Key><Size>51234</Size></Contents>'
               b'<CommonPrefixes><Prefix>PMC11370360.1/</Prefix></CommonPrefixes>'
               b'<CommonPrefixes><Prefix>PMC11370360.2/</Prefix></CommonPrefixes></ListBucketResult>')
    prefixes, keys, truncated, token = pmc_download.parse_s3_listing(listing)
    assert prefixes == ["PMC11370360.1/", "PMC11370360.2/"]
    assert keys == {"PMC11370360.2/PMC11370360.2.xml": 51234} and truncated and token == "abc"

    settings = {"require_open_access": True, "prefer_non_manuscript": True}
    candidates = [("PMC1.1", {"is_pmc_openaccess": True, "is_manuscript": False}),
                  ("PMC1.2", {"is_pmc_openaccess": True, "is_manuscript": True}),
                  ("PMC1.3", {"is_pmc_openaccess": False, "is_manuscript": False})]
    assert pmc_download.choose_version(candidates, settings)[0] == "PMC1.1"
    assert pmc_download.choose_version(candidates[2:], settings) == (None, None)
