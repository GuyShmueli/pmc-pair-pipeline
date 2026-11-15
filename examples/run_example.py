"""Run the whole pipeline on the synthetic example, offline (under a minute).

    python examples/run_example.py

The model stages use the ready-made responses in examples/data/llm_responses/
(imported with --import-responses), so no API key is needed and nothing is paid.
Every command is printed before it runs, so this file doubles as a walkthrough.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = EXAMPLE_DIR.parent
CONFIG = EXAMPLE_DIR / "example_config.yaml"
RESPONSES = EXAMPLE_DIR / "data" / "llm_responses"


def run(*args):
    command = [sys.executable, *map(str, args)]
    print("\n$ " + " ".join(str(a) for a in args), flush=True)
    subprocess.run(command, check=True, cwd=REPOSITORY_DIR)


def main():
    # start from a clean example folder so the run is reproducible
    for folder in ("work", "release"):
        shutil.rmtree(EXAMPLE_DIR / "data" / folder, ignore_errors=True)
    run(EXAMPLE_DIR / "make_example_data.py")

    for step in ("select-cases", "download", "extract-figures", "filter-images", "prepare-pairs"):
        run("-m", "pmc_pair", step, "--config", CONFIG)

    for stage in ("citation-analysis", "question-generation", "answer-generation", "pair-selection"):
        responses = RESPONSES / f"{stage.replace('-', '_')}.jsonl"
        run("-m", "pmc_pair", "llm", stage, "--config", CONFIG, "--import-responses", responses)

    run("-m", "pmc_pair", "run-all", "--config", CONFIG, "--from", "finalize-pairs")
    run("-m", "pmc_pair", "check", "--config", CONFIG)
    print(f"\nDone. Release files: {EXAMPLE_DIR / 'data' / 'release'}")


if __name__ == "__main__":
    main()
