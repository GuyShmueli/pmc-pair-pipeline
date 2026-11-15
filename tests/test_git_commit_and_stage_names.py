"""Tests for which Git commit an export records, and for stage names shown to the user."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pmc_pair import cli, export, llm

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def run_git(folder, *arguments):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    result = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                             "-c", "commit.gpgsign=false", *arguments],
                            cwd=folder, env=environment, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def repository(folder, *files):
    """A new repository in ``folder`` with one commit holding ``files``; returns its HEAD."""
    folder.mkdir(parents=True, exist_ok=True)
    run_git(folder, "init", "-q")
    for name in files:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    run_git(folder, "add", "-A")
    run_git(folder, "commit", "-q", "--allow-empty", "-m", "test")
    return run_git(folder, "rev-parse", "HEAD")


@needs_git
@pytest.mark.parametrize("name", ["pipeline", "pipeline with space", "piplin-é-中"])
def test_own_repository_records_its_commit(tmp_path, monkeypatch, name):
    try:
        os.fsencode(name)
    except UnicodeEncodeError:
        pytest.skip("this file system encoding cannot hold the folder name")
    root = tmp_path / name
    head = repository(root, "pmc_pair/export.py")
    monkeypatch.setattr(export, "REPOSITORY_DIR", root)
    assert export.git_commit() == head


@needs_git
def test_git_variables_do_not_redirect_the_lookup(tmp_path, monkeypatch):
    own = tmp_path / "own"
    head = repository(own, "pmc_pair/export.py")
    other = tmp_path / "other"
    repository(other, "pmc_pair/export.py")
    monkeypatch.setattr(export, "REPOSITORY_DIR", own)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert export.git_commit() == head


def test_no_repository_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "REPOSITORY_DIR", tmp_path)
    assert export.git_commit() is None


@needs_git
def test_copy_inside_another_repository_records_nothing(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    repository(outer, "vendored/pmc_pair/export.py")
    monkeypatch.setattr(export, "REPOSITORY_DIR", outer / "vendored")
    assert export.git_commit() is None


@needs_git
def test_unpacked_at_the_root_of_another_repository_records_nothing(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    repository(outer, "unrelated.txt")
    (outer / "pmc_pair").mkdir()
    (outer / "pmc_pair" / "export.py").write_text("# unpacked, not committed\n", encoding="utf-8")
    monkeypatch.setattr(export, "REPOSITORY_DIR", outer)
    assert export.git_commit() is None


@needs_git
def test_repository_without_a_commit_records_nothing(tmp_path, monkeypatch):
    run_git(tmp_path, "init", "-q")
    monkeypatch.setattr(export, "REPOSITORY_DIR", tmp_path)
    assert export.git_commit() is None


@needs_git
@pytest.mark.skipif(os.name == "nt", reason="':' cannot occur in a Windows file name")
def test_file_name_that_looks_like_a_revision_is_not_followed(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    repository(outer, "unrelated.txt")
    crafted = outer / "HEAD:pmc_pair"
    crafted.mkdir()
    (crafted / "export.py").write_text("# crafted\n", encoding="utf-8")
    monkeypatch.setattr(export, "REPOSITORY_DIR", outer)
    assert export.git_commit() is None


@pytest.mark.parametrize("stage", llm.STAGES)
def test_missing_stage_suggests_a_name_the_command_line_accepts(tmp_path, stage):
    with pytest.raises(SystemExit) as caught:
        llm.stage_outputs({"paths": {"work_dir": str(tmp_path)}}, stage)
    suggested = re.search(r"python -m pmc_pair llm (\S+)` first", str(caught.value)).group(1)
    assert cli.build_parser().parse_args(["llm", suggested]).stage == suggested


def test_status_shows_stage_names_the_command_line_accepts(tmp_path, capsys):
    cli.show_status({"paths": {"work_dir": str(tmp_path)}})
    shown = capsys.readouterr().out
    for stage in llm.STAGES:
        assert stage not in shown
        assert stage.replace("_", "-") in shown
