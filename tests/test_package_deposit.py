"""Repacking preserves selected payloads and cannot replace inputs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pmc_pair.package_deposit import main, package_deposit
from test_deposit import create_deposit


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(path.relative_to(root)): digest(path)
            for path in root.rglob("*") if path.is_file()}


class TestPackageDeposit(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.metadata = self.root / "metadata"
        create_deposit(self.metadata)
        self.source = self.root / "loose"
        self.source.mkdir()
        for path in self.metadata.glob("images_captions_*.zip"):
            with zipfile.ZipFile(path) as archive:
                archive.extractall(self.source)
            path.unlink()
        self.images = self.source / "images"
        self.captions = self.source / "captions"
        self.output = self.root / "rebuilt"

    def package(self, **kwargs):
        options = dict(images_dir=self.images, captions_dir=self.captions,
                       metadata_dir=self.metadata, output_dir=self.output)
        options.update(kwargs)
        return package_deposit(**options)

    def assertNoPartialOutput(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".rebuilt.repack-*")))

    def test_rebuild_without_old_archives_preserves_members_and_metadata(self):
        original = snapshot(self.root)
        old_summary = json.loads((self.metadata / "release_summary.json").read_text())
        self.assertTrue(self.package()["passed"])
        self.assertEqual(snapshot(self.metadata), {key.removeprefix("metadata/"): value
                         for key, value in original.items() if key.startswith("metadata/")})
        self.assertEqual(snapshot(self.source), {key.removeprefix("loose/"): value
                         for key, value in original.items() if key.startswith("loose/")})
        for path in self.metadata.iterdir():
            if path.name not in {"release_summary.json", "SHA256SUMS.txt"}:
                self.assertEqual(path.read_bytes(), (self.output / path.name).read_bytes())
        with (self.metadata / "file_manifest.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        for name in {row["archive"] for row in rows}:
            expected = {row[kind + "_path"] for row in rows if row["archive"] == name
                        for kind in ("image", "caption")}
            with zipfile.ZipFile(self.output / name) as archive:
                self.assertEqual(set(archive.namelist()), expected)
                for member in archive.infolist():
                    self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(archive.read(member), (self.source / member.filename).read_bytes())
        new_summary = json.loads((self.output / "release_summary.json").read_text())
        self.assertEqual(new_summary["included_images"], old_summary["included_images"])
        self.assertEqual(new_summary["archive_bytes"], sum(
            path.stat().st_size for path in self.output.glob("images_captions_*.zip")))
        for record in new_summary["archives"]:
            self.assertEqual(record["sha256"], digest(self.output / record["archive"]))
            self.assertEqual(record["operation"], "repacked_from_manifest_verified_loose_files")
        self.assertNotEqual(new_summary["archives"], old_summary["archives"])

    def test_repeat_is_deterministic_and_ignores_unselected_loose_files(self):
        withheld = (self.metadata / "withheld_image_ids.txt").read_text().splitlines()
        for image_id in withheld:
            (self.images / (image_id + ".jpg")).write_bytes(b"must not distribute")
            (self.captions / (image_id + ".txt")).write_bytes(b"must not distribute")
        (self.images / "unselected.jpg").write_bytes(b"unselected")
        self.package()
        second = self.root / "rebuilt-again"
        self.package(output_dir=second)
        self.assertEqual(snapshot(self.output), snapshot(second))
        for path in self.output.glob("images_captions_*.zip"):
            with zipfile.ZipFile(path) as archive:
                self.assertNotIn("images/unselected.jpg", archive.namelist())
                for image_id in withheld:
                    self.assertNotIn("images/" + image_id + ".jpg", archive.namelist())

    def test_existing_output_is_never_replaced_even_if_empty(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.package()
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_overlapping_output_is_rejected(self):
        for source in (self.images, self.captions, self.metadata):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "overlaps"):
                self.package(output_dir=source / "new-output")

    def test_symbolic_source_directory_is_rejected(self):
        linked = self.root / "linked-images"
        linked.symlink_to(self.images, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            self.package(images_dir=linked)
        self.assertNoPartialOutput()

    def test_symbolic_source_file_is_rejected(self):
        source = next(self.images.iterdir())
        target = self.root / "real-source"
        source.rename(target)
        source.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            self.package()
        self.assertNoPartialOutput()

    def test_dangling_output_symlink_is_rejected(self):
        self.output.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            self.package()
        self.assertTrue(self.output.is_symlink())

    def test_metadata_checksum_tamper_fails_before_writing(self):
        (self.metadata / "README.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Metadata checksum mismatch"):
            self.package()
        self.assertNoPartialOutput()

    def test_unlisted_metadata_fails_before_writing(self):
        (self.metadata / "unexpected.txt").write_text("untracked")
        with self.assertRaisesRegex(ValueError, "Unlisted metadata"):
            self.package()
        self.assertNoPartialOutput()

    def test_missing_metadata_fails_before_writing(self):
        (self.metadata / "label_taxonomy.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.package()
        self.assertNoPartialOutput()

    def test_same_size_image_tamper_removes_partial_archive(self):
        image = next(self.images.iterdir())
        data = image.read_bytes()
        image.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        with self.assertRaisesRegex(ValueError, "does not match the final manifest"):
            self.package()
        self.assertNoPartialOutput()

    def test_final_verification_failure_removes_stage(self):
        with patch("pmc_pair.deposit.verify_deposit", return_value={
                "passed": False, "problems": ["bad metadata"]}) as validator:
            with self.assertRaisesRegex(ValueError, "failed verification"):
                self.package()
        validator.assert_called_once()
        self.assertNoPartialOutput()

    def test_extracted_sources_can_be_inside_download_directory(self):
        inside_images, inside_captions = self.metadata / "images", self.metadata / "captions"
        self.images.rename(inside_images)
        self.captions.rename(inside_captions)
        self.assertTrue(self.package(images_dir=inside_images, captions_dir=inside_captions)["passed"])

    def test_summary_duplicate_keys_are_rejected_even_with_matching_checksum(self):
        path = self.metadata / "release_summary.json"
        text = path.read_text()
        # Duplicate an existing key without otherwise changing the JSON object.
        duplicate = '"archive_count": 0,'
        path.write_text(text.replace("{", "{" + duplicate, 1))
        checksum_path = self.metadata / "SHA256SUMS.txt"
        lines = checksum_path.read_text().splitlines()
        checksum_path.write_text("\n".join(
            f"{digest(path)}  release_summary.json" if line.endswith("  release_summary.json") else line
            for line in lines) + "\n")
        with self.assertRaisesRegex(ValueError, "repeats a JSON key"):
            self.package()
        self.assertNoPartialOutput()

    def test_cli_reports_failure_without_traceback(self):
        self.output.mkdir()
        error = io.StringIO()
        with patch("sys.stderr", error):
            status = main(["--images-dir", str(self.images), "--captions-dir", str(self.captions),
                           "--metadata-dir", str(self.metadata), "--output-dir", str(self.output)])
        self.assertEqual(status, 1)
        self.assertIn("already exists", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
