"""Small public-layout fixtures and failure tests; no external files or network."""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from pmc_pair.deposit import verify_deposit, run_cli
from pmc_pair.article_disjoint_split import generate_split


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_csv(path, rows, fields=None):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_checksums(root):
    (root / "SHA256SUMS.txt").write_text("".join(
        f"{sha256(path)}  {path.name}\n" for path in sorted(root.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.txt"), encoding="utf-8")


def refresh_archive_metadata(root, name):
    summary = json.loads((root / "release_summary.json").read_text())
    for entry in summary["archives"]:
        if entry["archive"] == name:
            entry["sha256"] = sha256(root / name)
            entry["bytes"] = (root / name).stat().st_size
    summary["archive_bytes"] = sum(entry["bytes"] for entry in summary["archives"])
    write_json(root / "release_summary.json", summary)
    refresh_checksums(root)


def create_deposit(root, *, image_ids=None):
    """Create six tiny archives with six included images and one withheld image.

    Returns the root Path. Image payloads are arbitrary bytes: validation checks byte
    integrity, not image decoding or medical contents. Captions are valid UTF-8.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    images = list(image_ids) if image_ids is not None else [f"{100 + i}_1_1" for i in range(7)]
    included, withheld = images[:6], images[6:]
    pairs = [{"pair_id": [images[a], images[b]], "modality": "CT", "anatomy": "brain", "diagnosis": "mass"}
             for a, b in ((0, 1), (2, 3), (4, 5), (0, 6))]
    write_json(root / "image_pairs.json", pairs)
    matching_names = ["anatomy_vessel_span", "negation_prefix", "negation_suffix", "unresolved_context",
                      "resolution_prefix", "resolution_suffix", "postoperative_report", "normal_report"]
    matching = {name: r"(?!)" for name in matching_names}
    matching["diagnosis_clause_separator"] = r";"
    categories = {"modality": {"ct": "CT", "other": "Other"},
                  "anatomy": {"brain": "Brain", "other": "Other", "vasculature": "Vessels"},
                  "diagnosis": {"mass": "Mass", "other": "Other", "normal_or_negative_report": "Normal",
                                "postoperative_or_resolved_state": "Resolved"}}
    rules = {field: [{"id": field + "_rule", "label": label, "priority": 1, "aliases": [alias]}]
             for field, label, alias in (("modality", "ct", "CT"), ("anatomy", "brain", "brain"),
                                         ("diagnosis", "mass", "mass"))}
    write_json(root / "label_taxonomy.json", {"categories": categories, "expected_unique_images": len(images),
               "normalization": {"replacements": []}, "matching": matching, "rules": rules, "version": 1})
    with (root / "image_labels.jsonl").open("w", encoding="utf-8") as handle:
        for image in images:
            handle.write(json.dumps({"image_id": image, "labels": {"modality": ["ct"], "anatomy": ["brain"], "diagnosis": ["mass"]}}) + "\n")
    citations = []
    for row in pairs:
        first, second = ["PMC" + image.split("_")[0] for image in row["pair_id"]]
        if first != second:
            citations.append({"citing_case": first, "cited_case": second,
                              "extracted_citation": "A cited case.", "citation_reason": "Comparison of cases."})
    write_json(root / "case_pair_citations_eligible.json", citations)
    (root / "included_image_ids.txt").write_text("\n".join(included) + "\n")
    (root / "withheld_image_ids.txt").write_text("\n".join(withheld) + "\n")
    (root / "README.txt").write_text("Test public release.\n")
    (root / "LICENSE.txt").write_text("Test metadata license.\n")
    manifest, licenses, archives = [], [], []
    for index, image in enumerate(images):
        pmcid = "PMC" + image.split("_")[0]
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        license_row = {"image_id": image, "pmcid": pmcid, "source_article_url": url, "figure_xml_id": "f1",
                       "file_redistribution_status": "included" if image in included else "withheld_privacy_review",
                       "image_license": "CC BY 4.0", "caption_license": "CC BY 4.0",
                       "image_license_components": '[{"license":"CC BY 4.0"}]',
                       "caption_license_components": '[{"license":"CC BY 4.0"}]',
                       "image_commercial_use_under_recorded_license": "permitted",
                       "caption_commercial_use_under_recorded_license": "permitted",
                       "archive": "", "image_member": "", "caption_member": "",
                       "attribution": "Test Author. Test article. Source and terms supplied.",
                       "article_authors": "Test Author", "article_title": "Test article"}
        if image in included:
            name = f"images_captions_{index + 1:03d}.zip"
            image_path, caption_path = f"images/{image}.jpg", f"captions/{image}.txt"
            image_data, caption_data = f"Image bytes {image}".encode(), f"Caption {image}, café.".encode()
            with zipfile.ZipFile(root / name, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(image_path, image_data)
                archive.writestr(caption_path, caption_data)
            manifest.append({"image_id": image, "archive": name, "image_path": image_path, "caption_path": caption_path,
                             "image_size_bytes": len(image_data), "caption_size_bytes": len(caption_data),
                             "image_sha256": hashlib.sha256(image_data).hexdigest(),
                             "caption_sha256": hashlib.sha256(caption_data).hexdigest(), "pmcid": pmcid,
                             "figure_xml_id": "f1", "source_article_url": url})
            archives.append({"archive": name, "images": 1, "entries": 2, "bytes": (root / name).stat().st_size,
                             "sha256": sha256(root / name), "operation": "copied_byte_identically" if index == 5 else "rewritten"})
            license_row.update(archive=name, image_member=image_path, caption_member=caption_path)
        licenses.append(license_row)
    write_csv(root / "file_manifest.csv", manifest)
    write_csv(root / "licenses.csv", licenses)
    write_csv(root / "withheld.csv", [{"image_id": withheld[0], "status": "withheld_privacy_review",
              "reason": "Requires review", "source_article_url": licenses[-1]["source_article_url"], "additional_source_urls": "[]"}])
    availability = []
    for index, pair in enumerate(pairs):
        first, second = pair["pair_id"]
        availability.append({"pair_index": index, "image_id_1": first, "image_id_2": second,
            "image_1_available": first in included, "image_2_available": second in included,
            "both_images_available": first in included and second in included})
    write_csv(root / "pair_availability.csv", availability)
    summary = {"annotation_image_ids": 7, "annotation_pairs": 4, "included_images": 6, "included_captions": 6,
               "withheld_images": 1, "withheld_by_status": {"withheld_privacy_review": 1},
               "complete_pairs": 3, "affected_pairs": 1,
               "included_source_articles": len({i.split("_")[0] for i in included}),
               "all_source_articles": len({i.split("_")[0] for i in images}), "archives": archives,
               "archive_count": 6, "archive_bytes": sum(a["bytes"] for a in archives), "zip_entries": 12}
    for kind in ("image", "caption"):
        summary[f"primary_{kind}_license_counts"] = {"CC BY 4.0": 6}
        summary[f"{kind}_component_license_combinations"] = {"CC BY 4.0": 6}
        summary[f"{kind}_commercial_use_counts"] = {"permitted": 6}
    write_json(root / "release_summary.json", summary)
    refresh_checksums(root)
    return root


class DepositTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = create_deposit(Path(self.temp.name) / "deposit")

    def assertFails(self, text):
        result = verify_deposit(self.root)
        self.assertFalse(result["passed"], result)
        self.assertIn(text, " ".join(result["problems"]))
        return result

    def test_complete_deposit_needs_no_historical_release_or_split(self):
        result = verify_deposit(self.root)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["counts"]["verified_zip_members"], 12)
        self.assertFalse(result["split_checked"])
        self.assertEqual(result["counts"]["withheld_images"], 1)

    def test_outer_tamper_stops_before_reading_zip_payloads(self):
        (self.root / "README.txt").write_text("Changed")
        with patch("pmc_pair.deposit.zipfile.ZipFile", side_effect=AssertionError("should stop before ZIP")):
            self.assertFails("SHA-256 mismatch")

    def test_missing_required_metadata_is_not_silently_skipped(self):
        (self.root / "withheld.csv").unlink()
        refresh_checksums(self.root)
        self.assertFails("missing required files")

    def test_unlisted_file_and_missing_listed_file_fail(self):
        (self.root / "untracked.txt").write_text("unexpected")
        self.assertFails("unlisted")
        (self.root / "untracked.txt").unlink()
        (self.root / "README.txt").unlink()
        self.assertFails("missing")

    def test_checksum_duplicate_and_traversal_fail(self):
        path = self.root / "SHA256SUMS.txt"
        original = path.read_text()
        path.write_text(original + original.splitlines()[0] + "\n")
        self.assertFails("repeated filename")
        path.write_text(original + "0" * 64 + "  ../outside.txt\n")
        self.assertFails("unsafe")

    def test_final_archive_payload_is_verified_even_when_marked_copied(self):
        name = "images_captions_006.zip"
        with zipfile.ZipFile(self.root / name) as archive:
            payloads = {item.filename: archive.read(item) for item in archive.infolist()}
        caption = next(n for n in payloads if n.startswith("captions/"))
        payloads[caption] = b"X" + payloads[caption][1:]
        with zipfile.ZipFile(self.root / name, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, payload in payloads.items():
                archive.writestr(member, payload)
        refresh_archive_metadata(self.root, name)
        self.assertFails("payload size or SHA-256 differs")

    def test_duplicate_zip_member_is_rejected(self):
        name = "images_captions_006.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.root / name, "a") as archive:
                archive.writestr("images/105_1_1.jpg", b"repeated image")
        refresh_archive_metadata(self.root, name)
        self.assertFails("duplicate member")

    def test_withheld_payload_is_rejected(self):
        name = "images_captions_006.zip"
        with zipfile.ZipFile(self.root / name, "a") as archive:
            archive.writestr("images/106_1_1.jpg", b"withheld")
        refresh_archive_metadata(self.root, name)
        self.assertFails("unexpected member")

    def test_malformed_pairs_are_a_failed_report(self):
        write_json(self.root / "image_pairs.json", [{"pair_id": 3}])
        refresh_checksums(self.root)
        self.assertFails("expected pair_id")

    def test_pair_duplication_is_rejected(self):
        pairs = json.loads((self.root / "image_pairs.json").read_text())
        pairs.append({**pairs[0], "pair_id": list(reversed(pairs[0]["pair_id"]))})
        write_json(self.root / "image_pairs.json", pairs)
        refresh_checksums(self.root)
        self.assertFails("duplicate undirected pair")

    def test_distinct_images_are_accepted_without_warnings(self):
        images = [f"{100 + i}_1_1" for i in range(7)]
        images[1] = "100_1_2"
        other = create_deposit(Path(self.temp.name) / "distinct-images", image_ids=images)
        result = verify_deposit(other)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["counts"]["image_pairs"], 4)
        self.assertEqual(result["counts"]["annotation_images"], 7)
        self.assertEqual(result["warnings"], [])

    def test_labels_recomputed_from_taxonomy(self):
        path = self.root / "image_labels.jsonl"
        path.write_text(path.read_text().replace('"ct"', '"other"', 1))
        refresh_checksums(self.root)
        self.assertFails("differ from recomputed")

    def test_availability_and_summary_are_recomputed(self):
        path = self.root / "pair_availability.csv"
        path.write_text(path.read_text().replace("True,True,True", "False,True,True", 1))
        refresh_checksums(self.root)
        self.assertFails("incorrect image_1_available")

    def test_license_attribution_and_component_policy(self):
        path = self.root / "licenses.csv"
        rows = list(csv.DictReader(path.open()))
        rows[0]["attribution"] = ""
        write_csv(path, rows)
        refresh_checksums(self.root)
        self.assertFails("missing attribution")
        rows[0]["attribution"] = "Test attribution"
        rows[0]["image_license_components"] = '[{"license":"CC BY-ND 4.0"}]'
        write_csv(path, rows)
        refresh_checksums(self.root)
        self.assertFails("invalid image license components")
        rows[0]["image_license_components"] = '[{"license":"Unresolved"}]'
        write_csv(path, rows)
        refresh_checksums(self.root)
        self.assertFails("invalid image license components")

    def test_zip_traversal_fails(self):
        name = "images_captions_006.zip"
        with zipfile.ZipFile(self.root / name, "a") as archive:
            archive.writestr("../outside.txt", b"outside")
        refresh_archive_metadata(self.root, name)
        self.assertFails("unsafe or unexpected member")

    def test_zip_symlink_is_rejected(self):
        name = "images_captions_006.zip"
        info = zipfile.ZipInfo("images/link.jpg")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.root / name, "a") as archive:
            archive.writestr(info, "outside")
        refresh_archive_metadata(self.root, name)
        self.assertFails("symbolic-link member")

    def test_citation_coverage_and_case_normalization(self):
        path = self.root / "case_pair_citations_eligible.json"
        rows = json.loads(path.read_text())
        for row in rows:
            row["citing_case"] = row["citing_case"][3:] + "-1"
            row["cited_case"] = row["cited_case"][3:] + "-1"
        write_json(path, rows)
        refresh_checksums(self.root)
        self.assertTrue(verify_deposit(self.root)["passed"])
        write_json(path, rows[1:])
        refresh_checksums(self.root)
        self.assertFails("has no citation record")

    def test_optional_split_compared_to_regenerated_assignments(self):
        pairs = [r["pair_id"] for r in json.loads((self.root / "image_pairs.json").read_text())]
        images = {i for pair in pairs for i in pair}
        split = generate_split(images, pairs)
        path = Path(self.temp.name) / "split.json"
        write_json(path, split)
        result = verify_deposit(self.root, path)
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["split_checked"])
        write_json(path, {i: "test" if s == "train" else "train" for i, s in split.items()})
        result = verify_deposit(self.root, path)
        self.assertFalse(result["passed"])
        self.assertIn("regeneration", result["problems"][0])

    def test_cli_report_must_be_new_and_outside_deposit(self):
        args = argparse.Namespace(data_dir=self.root, split_file=None, report_file=self.root / "report.json")
        with self.assertRaises(SystemExit):
            run_cli(args)
        args.report_file = Path(self.temp.name) / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_cli(args), 0)
        self.assertTrue(json.loads(args.report_file.read_text())["passed"])
        with self.assertRaises(SystemExit):
            run_cli(args)


if __name__ == "__main__":
    unittest.main()
