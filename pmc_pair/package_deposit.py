"""Repack a PMC-PaIR deposit from verified loose images and captions.

Archive membership comes exclusively from file_manifest.csv.  Extra loose files
(including withheld images) are never selected.  ZIPs in the metadata directory
are not read.  The rebuilt ZIP bytes can differ from the published ZIPs, but each
selected member must retain its recorded bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile


_ARCHIVE = re.compile(r"images_captions_[0-9]{3}\.zip\Z")
_DIGEST = re.compile(r"[0-9a-fA-F]{64}\Z")
_MANIFEST_FIELDS = {
    "image_id", "archive", "image_path", "caption_path",
    "image_size_bytes", "caption_size_bytes", "image_sha256", "caption_sha256",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_object(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Release summary repeats a JSON key: {key!r}")
        result[key] = value
    return result


def _no_symlinks(path: Path) -> None:
    """Check the complete path before resolve() can hide a symbolic link."""
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symbolic links are not allowed: {component}")


def _input_directory(value: str | Path) -> Path:
    path = Path(value).absolute()
    _no_symlinks(path)
    if not path.is_dir():
        raise ValueError(f"Input directory does not exist: {path}")
    return path.resolve()


def _regular_file(path: Path) -> None:
    _no_symlinks(path)
    if not path.is_file():
        raise ValueError(f"Required regular file is missing: {path}")


def _read_checksums(path: Path) -> dict[str, str]:
    _regular_file(path)
    checksums = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            raise ValueError(f"Malformed checksum line {number} in {path.name}")
        digest, name = match.groups()
        if name != Path(name).name or name in {".", "..", "SHA256SUMS.txt"} or "\\" in name:
            raise ValueError(f"Checksum entries must be simple filenames: {name!r}")
        if name in checksums:
            raise ValueError(f"Duplicate checksum entry: {name}")
        checksums[name] = digest.lower()
    return checksums


def _read_manifest(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    image_ids, members = set(), set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not _MANIFEST_FIELDS <= set(reader.fieldnames or []):
            raise ValueError("file_manifest.csv is missing required columns")
        for row in reader:
            image_id, archive = row["image_id"], row["archive"]
            if not image_id or image_id in image_ids:
                raise ValueError(f"Empty or repeated manifest image identifier: {image_id!r}")
            if not _ARCHIVE.fullmatch(archive):
                raise ValueError(f"Invalid manifest archive name: {archive!r}")
            image_ids.add(image_id)
            for kind in ("image", "caption"):
                member = row[f"{kind}_path"]
                parts = PurePosixPath(member).parts
                if (len(parts) != 2 or parts[0] != f"{kind}s" or
                        parts[1] in {".", ".."} or "\\" in member or
                        str(PurePosixPath(member)) != member):
                    raise ValueError(f"Unsafe or unsupported manifest member path: {member!r}")
                if member in members:
                    raise ValueError(f"Repeated manifest member: {member}")
                members.add(member)
                if not _DIGEST.fullmatch(row[f"{kind}_sha256"]):
                    raise ValueError(f"Invalid manifest SHA256 for {member}")
                if int(row[f"{kind}_size_bytes"]) < 0:
                    raise ValueError(f"Invalid manifest size for {member}")
            grouped.setdefault(archive, []).append(row)
    if not grouped:
        raise ValueError("file_manifest.csv contains no images")
    return grouped


def _write_member(archive: zipfile.ZipFile, source: Path, member: str,
                  expected_size: int, expected_hash: str) -> None:
    _regular_file(source)
    info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    # ZipFile.open() uses this field for per-member compression settings.
    info._compresslevel = 6
    info.file_size = expected_size
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
            writer.write(block)
    if size != expected_size or digest.hexdigest() != expected_hash.lower():
        raise ValueError(f"Loose file does not match the final manifest: {source}")


def package_deposit(images_dir: str | Path, captions_dir: str | Path,
                    metadata_dir: str | Path, output_dir: str | Path) -> dict:
    """Create a verified deposit directory from loose files and deposit metadata.

    ``images_dir`` and ``captions_dir`` contain the files named below the
    manifest's ``images/`` and ``captions/`` prefixes.  Metadata must have a
    SHA256SUMS.txt that lists and matches every metadata file.  Entries for the
    published ZIPs are required, but the ZIP files themselves are not needed
    and are ignored if present.  Output must not exist or overlap any input.

    Returns the full verification report of the output.  Input/validation errors
    raise ValueError.  No partial output directory remains after a failed operation.
    """
    from .deposit import REQUIRED_METADATA, verify_deposit

    images = _input_directory(images_dir)
    captions = _input_directory(captions_dir)
    metadata = _input_directory(metadata_dir)
    output = Path(output_dir).absolute()
    _no_symlinks(output)
    if output.exists():
        raise ValueError(f"Output directory already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"Output parent directory must already exist: {output.parent}")
    output = output.resolve()
    for source in (images, captions, metadata):
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError(f"Output directory overlaps an input directory: {source}")

    checksums = _read_checksums(metadata / "SHA256SUMS.txt")
    for name in sorted(REQUIRED_METADATA):
        if name not in checksums:
            raise ValueError(f"Required metadata is absent from SHA256SUMS.txt: {name}")
    # Validate metadata before trusting its archive/member names.  The published
    # ZIPs need not be on disk and do not contribute to the rebuilt payloads.
    for name, expected in checksums.items():
        if _ARCHIVE.fullmatch(name):
            continue
        source = metadata / name
        _regular_file(source)
        if _sha256(source) != expected:
            raise ValueError(f"Metadata checksum mismatch: {name}")
    for source in metadata.iterdir():
        if source.name in {"images", "captions"} and source.is_dir():
            _no_symlinks(source)
            selected_source = images if source.name == "images" else captions
            if source.resolve() == selected_source:
                continue
        _regular_file(source)
        if source.name != "SHA256SUMS.txt" and source.name not in checksums:
            raise ValueError(f"Unlisted metadata file: {source.name}")
    grouped = _read_manifest(metadata / "file_manifest.csv")
    archive_names = {name for name in checksums if _ARCHIVE.fullmatch(name)}
    if archive_names != set(grouped):
        raise ValueError("Manifest archives differ from the SHA256SUMS.txt archive inventory")
    with (metadata / "release_summary.json").open(encoding="utf-8") as handle:
        summary = json.load(handle, object_pairs_hook=_unique_object)
    if _sha256(metadata / "release_summary.json") != checksums["release_summary.json"]:
        raise ValueError("Release summary changed during packaging")
    if (not isinstance(summary, dict) or
            {item["archive"] for item in summary.get("archives", [])} != set(grouped)):
        raise ValueError("Release summary archive inventory does not match the manifest")
    if len(summary["archives"]) != len(grouped):
        raise ValueError("Release summary repeats an archive")
    for item in summary["archives"]:
        name = item["archive"]
        if (item["sha256"] != checksums[name] or item["images"] != len(grouped[name]) or
                item["entries"] != 2 * len(grouped[name])):
            raise ValueError(f"Release summary disagrees with checksums or manifest: {name}")

    selected = {row["image_id"] for rows in grouped.values() for row in rows}
    included = (metadata / "included_image_ids.txt").read_text(encoding="utf-8").splitlines()
    withheld = (metadata / "withheld_image_ids.txt").read_text(encoding="utf-8").splitlines()
    if set(included) != selected or len(included) != len(selected):
        raise ValueError("Manifest images differ from included_image_ids.txt")
    if selected.intersection(withheld):
        raise ValueError("The manifest includes a withheld image")
    # Resolve all selected paths before writing anything.  Extra loose files
    # are deliberately allowed because a full source collection can contain
    # withheld or unselected images.
    for rows in grouped.values():
        for row in rows:
            for kind, directory in (("image", images), ("caption", captions)):
                source = directory / PurePosixPath(row[f"{kind}_path"]).name
                _regular_file(source)
                if source.stat().st_size != int(row[f"{kind}_size_bytes"]):
                    raise ValueError(f"Loose file size does not match the final manifest: {source}")

    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.repack-", dir=output.parent))
    try:
        for name, expected in checksums.items():
            if _ARCHIVE.fullmatch(name) or name == "release_summary.json":
                continue
            shutil.copyfile(metadata / name, stage / name)
            if _sha256(stage / name) != expected:
                raise ValueError(f"Metadata changed during packaging: {name}")
        rebuilt = []
        for name, rows in sorted(grouped.items()):
            destination = stage / name
            with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                for row in sorted(rows, key=lambda item: item["image_id"]):
                    for kind, directory in (("image", images), ("caption", captions)):
                        member = row[f"{kind}_path"]
                        _write_member(archive, directory / PurePosixPath(member).name,
                                      member, int(row[f"{kind}_size_bytes"]), row[f"{kind}_sha256"])
            rebuilt.append({"archive": name, "images": len(rows), "entries": 2 * len(rows),
                            "bytes": destination.stat().st_size, "sha256": _sha256(destination),
                            "operation": "repacked_from_manifest_verified_loose_files"})
        summary.update({"archives": rebuilt, "archive_count": len(rebuilt),
                        "archive_bytes": sum(item["bytes"] for item in rebuilt),
                        "zip_entries": sum(item["entries"] for item in rebuilt),
                        "original_file_bytes_preserved": True})
        (stage / "release_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "SHA256SUMS.txt").write_text("".join(
            f"{_sha256(path)}  {path.name}\n" for path in sorted(stage.iterdir())), encoding="utf-8")
        report = verify_deposit(stage)
        if not report.get("passed"):
            raise ValueError("Repacked deposit failed verification: " + json.dumps(report, ensure_ascii=False))
        if output.exists() or output.is_symlink():
            raise ValueError(f"Output appeared during packaging; refusing replacement: {output}")
        stage.chmod(0o755)
        # Reserve an empty destination, then atomically replace only our own
        # placeholder.  mkdir refuses any concurrently created destination.
        output.mkdir()
        try:
            os.replace(stage, output)
        except BaseException:
            output.rmdir()
            raise
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--images-dir", type=Path, required=True,
                        help="Loose image files (the contents of images/).")
    parser.add_argument("--captions-dir", type=Path, required=True,
                        help="Loose caption files (the contents of captions/).")
    parser.add_argument("--metadata-dir", type=Path, required=True,
                        help="Flat deposit metadata with a complete SHA256SUMS.txt. Listed ZIPs are not read.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory to create after full verification; its parent must exist.")


def run_cli(args: argparse.Namespace) -> int:
    try:
        report = package_deposit(args.images_dir, args.captions_dir, args.metadata_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Packaging failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
