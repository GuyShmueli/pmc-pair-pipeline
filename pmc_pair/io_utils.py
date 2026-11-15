"""Small helpers for reading and writing JSON / JSONL files.

Whole-file writes are atomic (write to a temporary file, then rename), so an
interrupted run never leaves a half-written output that a later step would read.
JSONL files that act as checkpoints are appended to one record at a time.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(data, path, indent=2, sort_keys=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:  # same bytes on every OS
        json.dump(data, f, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
        f.write("\n")
    os.replace(tmp_path, path)


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A crash while appending can leave a truncated last line.
                print(f"WARNING: skipping unreadable line {line_number} in {path}")


def read_jsonl(path):
    return list(iter_jsonl(path))


def write_jsonl(records, path, compact=False):
    """compact: no spaces after "," and ":" (the format of image_labels.jsonl)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    separators = (",", ":") if compact else None
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, separators=separators) + "\n")
    os.replace(tmp_path, path)


def append_jsonl(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":  # last line was cut off by a crash: start a new line
                f.write(b"\n")
        f.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))


def stable_json(data):
    """JSON text with sorted keys, used for hashing request bodies."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
