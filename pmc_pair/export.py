"""Step 13 (export): write the release files.

image_pairs        JSON array, one object per image pair: pair_id, modality, anatomy,
                   diagnosis, captions (one {"image_id", "caption"} per image, pair_id order)
image_labels       JSONL, one {"image_id", "labels": {modality, anatomy, diagnosis}} per line
label_rules        the vocabulary and mapping rules used for the labels
citation_records   JSON array, one record per annotation-ready case pair:
                   citing_case, cited_case, extracted_citation, citation_reason
split              {image_id: "train" | "val" | "test"}, article-disjoint (the file format of
                   image_splits.json: sorted keys, 2-space indent)
images_part_NNN.zip   the image files, images/<image_id>.jpg, release.images_per_zip per archive
CHECKS.json, MANIFEST.json   check results; counts, checksums, settings, prompt hashes, models

File names are set in the configuration (release.file_names). The release is first
written to "<release_dir>.incomplete" and moved into place only if every model output
matches the current inputs and all release checks pass.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

from . import __version__
from .article_disjoint_split import write_split
from .checks import check_release
from .chipa import outdated_model_outputs, stage_pairs
from .config import REPOSITORY_DIR, log, work_dir
from .io_utils import iter_jsonl, read_json, sha256_file, utc_now, write_json
from .llm import STAGES, prompt_files, stage_dir
from .prepare_pairs import annotation_ready_pairs


def git_commit():
    """HEAD of the pipeline's own Git repository, or None.

    The repository is the pipeline's own only if its root is the code's folder and its HEAD
    contains this file. A copy inside another repository, or unpacked at the root of one,
    must not record that repository's commit.
    """
    # Variables such as GIT_DIR would make Git read another repository.
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    try:
        # The final -- stops Git from reading the arguments as file names. The output is read as bytes
        # because Git writes the path in UTF-8, whatever the text encoding of this process.
        result = subprocess.run(["git", "rev-parse", "--show-toplevel", "HEAD", "HEAD:pmc_pair/export.py", "--"],
                                cwd=REPOSITORY_DIR, env=env, capture_output=True, timeout=10)
        if result.returncode != 0:
            return None
        toplevel, commit, *_ = result.stdout.split(b"\n")
        return commit.decode("ascii") if Path(os.fsdecode(toplevel)).samefile(REPOSITORY_DIR) else None
    except Exception:
        return None


def copy_images(cfg, release_dir, image_ids, figures):
    """Image files in ZIP archives of release.images_per_zip images each."""
    work_root = Path(cfg["paths"]["work_dir"])
    per_zip = int(cfg["release"]["images_per_zip"])
    if per_zip <= 0:
        raise SystemExit("release.images_per_zip must be a positive number of images per ZIP archive")
    for part, start in enumerate(range(0, len(image_ids), per_zip), start=1):
        zip_path = release_dir / f"images_part_{part:03d}.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            for image_id in image_ids[start:start + per_zip]:
                # fixed time stamp and attributes: the same images give the same archive bytes on every run
                entry = zipfile.ZipInfo(f"images/{image_id}.jpg", date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system, entry.external_attr = 3, 0o644 << 16
                data = (work_root / figures[image_id]["image_file"]).read_bytes()
                archive.writestr(entry, data, compress_type=zipfile.ZIP_STORED)  # JPEGs are compressed already


def export_release(cfg):
    problems = outdated_model_outputs(cfg, require_complete=True)
    if problems:
        raise SystemExit("Cannot export: the model outputs do not cover the current inputs:\n  "
                         + "\n  ".join(problems))

    release_dir = Path(cfg["paths"]["release_dir"])
    if release_dir.exists() and any(release_dir.iterdir()) and not (release_dir / "MANIFEST.json").exists():
        raise SystemExit(f"{release_dir} is not empty and is not an earlier release; choose another release_dir.")
    staging = release_dir.with_name(release_dir.name + ".incomplete")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    names = cfg["release"]["file_names"]

    captions = {}  # the captions exactly as the pair-selection model received them
    for pair in annotation_ready_pairs(cfg):
        captions.update(pair["case_a_captions"])
        captions.update(pair["case_b_captions"])
    figures = {f["image_id"]: f for f in iter_jsonl(work_dir(cfg, "figures") / "figures.jsonl")}
    pairs = list(iter_jsonl(work_dir(cfg, "image_pairs") / "image_pairs.jsonl"))
    split = read_json(work_dir(cfg, "split") / "split.json")
    image_ids = sorted({image_id for pair in pairs for image_id in pair["pair_id"]})

    # 1. image pairs, with captions in the same order as pair_id
    write_json([{
        "pair_id": pair["pair_id"],
        "modality": pair["modality"],
        "anatomy": pair["anatomy"],
        "diagnosis": pair["diagnosis"],
        "captions": [{"image_id": image_id, "caption": captions[image_id]} for image_id in pair["pair_id"]],
    } for pair in pairs], staging / names["image_pairs"])

    # 2-3. image-level labels (as written by label-images) and the rules that produced them
    shutil.copyfile(work_dir(cfg, "labels") / "image_labels.jsonl", staging / names["image_labels"])
    shutil.copyfile(cfg["paths"]["label_rules"], staging / names["label_rules"])

    # 4. citation records: the case pairs of the citation analysis (chipa.stage_pairs)
    analyses = {line["case_pair_id"]: line["output_text"]
                for line in iter_jsonl(stage_dir(cfg, "citation_analysis") / "outputs.jsonl")}
    citation_records = sorted(({
        "citing_case": f"PMC{pair['citing_pmcid']}",
        "cited_case": f"PMC{pair['cited_pmcid']}",
        "extracted_citation": "\n\n".join(p.strip() for p in pair["citation_passages"] if p.strip()),
        "citation_reason": analyses[pair["case_pair_id"]],
    } for pair in stage_pairs(cfg, "citation_analysis")), key=lambda record: (record["citing_case"], record["cited_case"]))
    write_json(citation_records, staging / names["citation_records"])

    # 5. benchmark partitions, in the format of image_splits.json (byte-identical when the
    #    benchmark split is used)
    write_split({image_id: split[image_id] for image_id in image_ids}, staging / names["split"])

    # 6. the image files
    if cfg["release"]["copy_images"]:
        copy_images(cfg, staging, image_ids, figures)

    checks = check_release(staging, names, expect_images=cfg["release"]["copy_images"],
                           split_settings=cfg["split"] if cfg["split"].get("verify_regeneration", True) else None)
    write_json(checks, staging / "CHECKS.json")
    write_json(build_manifest(cfg, staging, pairs, image_ids, citation_records, checks), staging / "MANIFEST.json")
    if not checks["passed"]:
        raise SystemExit(f"Release checks failed; the files are kept for inspection in {staging}:\n  "
                         + "\n  ".join(checks["problems"][:20]))

    shutil.rmtree(release_dir, ignore_errors=True)  # output of an earlier export (checked above)
    os.replace(staging, release_dir)
    log(cfg, f"export: {len(pairs)} image pairs, {len(image_ids)} images, {len(citation_records)} citation "
             f"records written to {release_dir}; checks passed")
    for warning in checks["warnings"]:
        log(cfg, f"export: WARNING {warning}")
    return checks


def build_manifest(cfg, release_dir, pairs, image_ids, citation_records, checks):
    prompts, models_used, response_sources = {}, {}, {}
    for stage in STAGES:
        instructions_file, user_file = prompt_files(cfg, stage)
        prompts[stage] = {"instructions_sha256": sha256_file(instructions_file),
                          "user_template_sha256": sha256_file(user_file)}
        outputs = list(iter_jsonl(stage_dir(cfg, stage) / "outputs.jsonl"))
        models_used[stage] = dict(Counter(str(line.get("response_model")) for line in outputs))
        # "sync" / "batch" = obtained by this pipeline, "batch_file" = --import-batch-output,
        # "import" = texts attached with --import-responses
        response_sources[stage] = dict(Counter(line["source"].split(":")[0] for line in outputs))

    inputs = {}
    for key in ("pmc_patients", "label_rules", "existing_split"):
        path = cfg["paths"].get(key)
        if path and Path(path).exists():
            inputs[key] = {"file_name": Path(path).name, "sha256": sha256_file(path)}

    step_stats = {}
    for step in ("cases", "articles", "figures", "image_filter", "pairs", "image_pairs", "labels", "split"):
        stats_path = Path(cfg["paths"]["work_dir"]) / step / "stats.json"
        if stats_path.exists():
            step_stats[step] = read_json(stats_path)
    for stage in STAGES:
        stats_path = stage_dir(cfg, stage) / "stats.json"
        if stats_path.exists():
            step_stats[f"llm_{stage}"] = read_json(stats_path)

    files = {}
    for path in sorted(release_dir.iterdir()):
        if path.is_file() and path.name != "MANIFEST.json":
            files[path.name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}

    settings = {key: cfg[key] for key in ("download", "figures", "image_filter", "animal_filter", "citations",
                                          "llm", "split", "release")}
    settings["image_filter"] = {**settings["image_filter"],
                                "tesseract_cmd": "set" if cfg["image_filter"].get("tesseract_cmd") else None}
    return {
        "dataset": "PMC-PaIR",
        "created_at": utc_now(),
        "pipeline_version": __version__,
        "git_commit": git_commit(),
        "counts": {"image_pairs": len(pairs), "images": len(image_ids),
                   "citation_records": len(citation_records),
                   "citation_records_without_passage": sum(1 for r in citation_records if not r["extracted_citation"])},
        "checks_passed": checks["passed"],
        "inputs": inputs,
        "settings": settings,
        "prompt_file_sha256": prompts,
        "response_models": models_used,
        "response_sources": response_sources,
        "step_statistics": step_stats,
        "files": files,
    }
