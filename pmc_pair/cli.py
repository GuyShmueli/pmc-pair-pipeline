"""Command line: python -m pmc_pair <step> --config config.yaml

Steps in order (each one reads the outputs of the previous ones from the work directory):

  select-cases      single-patient case reports and citation-linked case pairs
  download          article XML, metadata and JPEG figures from the PMC Cloud Service
  extract-figures   figure images with captions
  filter-images     flag diagrams / text-heavy figures (white background, OCR)
  prepare-pairs     animal cases, citation check, passages, case descriptions, figures
                    -> annotation-ready pairs
  llm STAGE         language-model stages on the annotation-ready pairs: citation-analysis,
                    question-generation, answer-generation, pair-selection
  finalize-pairs    validate the proposed image pairs
  label-images      image-level labels from the pair descriptions (nuclear medicine also from captions)
  split             article-disjoint train / val / test (the benchmark split, or drawn with seed 42)
  export            release files + checks + MANIFEST.json

  run-all           all steps in order, using cached model responses only (never calls the API)
  check             re-run the release checks
  verify-deposit    verify the downloaded Zenodo files
  package-deposit   package verified loose images and captions using deposit metadata
  status            progress summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cases import select_cases
from .checks import check_release
from .chipa import run_stage
from .config import load_config, log
from .export import export_release
from .figures import extract_figures
from .image_filter import filter_images
from .labels import label_images
from .llm import STAGES, stage_dir
from .pair_parsing import finalize_pairs
from .pmc_download import download_articles
from .prepare_pairs import prepare_pairs
from .splits import make_split

STEP_HELP = {
    "select-cases": "single-patient case reports and citation-linked case pairs",
    "download": "article XML, metadata and JPEG figures from the PMC Cloud Service",
    "extract-figures": "figure images with captions",
    "filter-images": "flag diagrams and text-heavy figures",
    "prepare-pairs": "check case pairs and gather the model inputs",
    "finalize-pairs": "validate the proposed image pairs",
    "label-images": "image-level labels from the pair descriptions (nuclear medicine also from captions)",
    "split": "article-disjoint train / val / test (benchmark split or seed 42)",
    "export": "write release files, checks and MANIFEST.json",
}
BEFORE_LLM = [("select-cases", select_cases), ("download", download_articles),
              ("extract-figures", extract_figures), ("filter-images", filter_images),
              ("prepare-pairs", prepare_pairs)]
AFTER_LLM = [("finalize-pairs", finalize_pairs), ("label-images", label_images),
             ("split", make_split), ("export", export_release)]
ALL_STEP_NAMES = [n for n, _ in BEFORE_LLM] + [s.replace("_", "-") for s in STAGES] + [n for n, _ in AFTER_LLM]


def run_all(cfg, start_step=None):
    """Run every step in order. Stops (exit code 3) when model responses are missing."""
    started = start_step is None
    for name in ALL_STEP_NAMES:
        started = started or name == start_step
        if not started:
            continue
        stage = name.replace("-", "_")
        if stage in STAGES:
            result = run_stage(cfg, stage)
            if result["pending"] or result["waiting_for_earlier_stages"]:
                log(cfg, f"run-all stopped at {name}: {result['pending']} requests have no cached response. "
                         f"Obtain them with `python -m pmc_pair llm {name} --submit-batch --allow-api-calls` "
                         f"(paid; then --collect-batch) or import existing responses, then run "
                         f"`python -m pmc_pair run-all --from {name}`.")
                return 3
        else:
            dict(BEFORE_LLM + AFTER_LLM)[name](cfg)
    return 0


def show_status(cfg):
    work = Path(cfg["paths"]["work_dir"])
    for folder, label in (("cases", "select-cases"), ("articles", "download"), ("figures", "extract-figures"),
                          ("image_filter", "filter-images"), ("pairs", "prepare-pairs")):
        path = work / folder / "stats.json"
        print(f"{label:18s} " + (path.read_text(encoding="utf-8").strip().replace("\n", " ")[:300]
                                 if path.exists() else "not run"))
    for stage in STAGES:
        path = stage_dir(cfg, stage) / "stats.json"
        print(f"{stage.replace('_', '-'):18s} " + (json.dumps(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else "not run"))
    for folder, label in (("image_pairs", "finalize-pairs"), ("labels", "label-images"), ("split", "split")):
        path = work / folder / "stats.json"
        print(f"{label:18s} " + (path.read_text(encoding="utf-8").strip().replace("\n", " ")[:300]
                                 if path.exists() else "not run"))


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m pmc_pair", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, help_text):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--config", default="config.yaml", help="configuration file (default: config.yaml)")
        return command

    for name, _ in BEFORE_LLM + AFTER_LLM:
        command = add(name, STEP_HELP[name])
        if name == "download":
            command.add_argument("--retry-permanent-failures", action="store_true",
                                 help="also retry articles recorded as missing or not open access")

    llm = add("llm", "run one language-model stage")
    llm.add_argument("stage", choices=[s.replace("_", "-") for s in STAGES])
    action = llm.add_mutually_exclusive_group()
    action.add_argument("--sync", action="store_true", help="send pending requests now, one by one (paid)")
    action.add_argument("--submit-batch", action="store_true", help="submit pending requests to the Batch API (paid)")
    action.add_argument("--collect-batch", action="store_true", help="download finished batches")
    action.add_argument("--import-responses", metavar="JSONL", help='import {"request_id", "output_text"} lines')
    action.add_argument("--import-batch-output", metavar="JSONL", help="import a downloaded Batch API output file")
    llm.add_argument("--request-file", help="batch input file that belongs to --import-batch-output")
    llm.add_argument("--allow-api-calls", action="store_true", help="confirm that the OpenAI API may be contacted")
    llm.add_argument("--limit", type=int, help="only the first N case pairs (for trial runs)")

    run = add("run-all", "run all steps using cached model responses only")
    run.add_argument("--from", dest="start_step", choices=ALL_STEP_NAMES, help="start at this step")

    check = add("check", "check the release files")
    check.add_argument("--release-dir", help="release folder (default: paths.release_dir)")
    from . import deposit, package_deposit
    deposit.add_arguments(commands.add_parser(
        "verify-deposit", help="verify the downloaded Zenodo files"))
    package_deposit.add_arguments(commands.add_parser(
        "package-deposit", help="package loose images and captions using public deposit metadata"))
    add("status", "show progress of every step")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "verify-deposit":
        from .deposit import run_cli
        return run_cli(args)
    if args.command == "package-deposit":
        from .package_deposit import run_cli
        return run_cli(args)
    cfg = load_config(args.config)

    if args.command == "llm":
        action = ("sync" if args.sync else "submit-batch" if args.submit_batch else
                  "collect-batch" if args.collect_batch else
                  "import-responses" if args.import_responses else
                  "import-batch-output" if args.import_batch_output else None)
        result = run_stage(cfg, args.stage.replace("-", "_"), action=action, allow_api_calls=args.allow_api_calls,
                           limit=args.limit, import_file=args.import_responses or args.import_batch_output,
                           request_file=args.request_file)
        # exit code 3: the stage still has requests without a response
        return 3 if result["pending"] or result["waiting_for_earlier_stages"] else 0
    if args.command == "run-all":
        return run_all(cfg, args.start_step)
    if args.command == "check":
        result = check_release(args.release_dir or cfg["paths"]["release_dir"], cfg["release"]["file_names"],
                               expect_images=bool(cfg["release"]["copy_images"]) and not args.release_dir,
                               split_settings=cfg["split"] if cfg["split"].get("verify_regeneration", True) else None)
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if args.command == "status":
        show_status(cfg)
        return 0
    if args.command == "download":
        download_articles(cfg, retry_permanent_failures=args.retry_permanent_failures)
        return 0
    dict(BEFORE_LLM + AFTER_LLM)[args.command](cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
