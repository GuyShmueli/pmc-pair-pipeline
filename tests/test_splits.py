"""Tests of the article-disjoint split: the procedure, the checks, the file format, the
split step, scripts/generate_splits.py and the benchmark image_splits.json.

With PMC_PAIR_RELEASE_PAIRS set to the released image_pairs.json, the benchmark split is
also regenerated from the released pairs and compared image by image.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from pmc_pair import article_disjoint_split as ads
from pmc_pair import splits
from pmc_pair.config import DEFAULT_CONFIG, PUBLISHED_SPLIT_SHA256, load_config
from pmc_pair.io_utils import write_jsonl

REPOSITORY = Path(__file__).resolve().parents[1]
PUBLISHED = REPOSITORY / "image_splits.json"
SCRIPT = REPOSITORY / "scripts" / "generate_splits.py"
SMALL = {"train": 0.5, "val": 0.25, "test": 0.25}

# Ten components; article 1 links the first two and article 5 the next two, giving 8 groups.
PAIRS = [("1_1_1", "2_1_1"), ("1_1_2", "3_1_1"), ("4_1_1", "5_1_1"), ("5_1_2", "6_1_1"),
         ("7_1_1", "8_1_1"), ("9_1_1", "10_1_1"), ("11_1_1", "12_1_1"), ("13_1_1", "14_1_1"),
         ("15_1_1", "16_1_1"), ("17_1_1", "18_1_1")]
IMAGES = sorted({image_id for pair in PAIRS for image_id in pair})


def test_components_that_share_an_article_are_merged():
    components, groups = ads.article_groups(IMAGES, PAIRS)
    assert len(components) == 10 and len(groups) == 8
    assert ["1_1_1", "1_1_2", "2_1_1", "3_1_1"] in groups      # through article PMC1
    assert ["4_1_1", "5_1_1", "5_1_2", "6_1_1"] in groups      # through article PMC5
    assert groups == sorted(groups, key=lambda group: group[0])


def test_assignment_follows_the_documented_procedure():
    _, groups = ads.article_groups(IMAGES, PAIRS)
    order = sorted(groups, key=min)
    random.Random(42).shuffle(order)
    n_train, n_val = int(0.5 * len(order)), int(0.25 * len(order))
    expected = {image_id: ("train" if k < n_train else "val" if k < n_train + n_val else "test")
                for k, group in enumerate(order) for image_id in group}
    split = ads.generate_split(IMAGES, PAIRS, 42, SMALL)
    assert split == expected
    assert ads.group_counts(13371) == {"train": 10696, "val": 1337, "test": 1338}
    # the result does not depend on the order or orientation of the inputs
    reordered = [(b, a) for a, b in reversed(PAIRS)]
    assert ads.generate_split(list(reversed(IMAGES)), reordered, 42, SMALL) == split


def test_split_problems_are_detected():
    split = ads.generate_split(IMAGES, PAIRS, 42, SMALL)
    assert ads.split_problems(split, IMAGES, PAIRS) == []
    assert set(ads.integrity_counts(split, IMAGES, PAIRS).values()) == {0}

    def problems_after(change):
        changed = dict(split)
        change(changed)
        return " | ".join(ads.split_problems(changed, IMAGES, PAIRS))

    other = {"train": "val", "val": "test", "test": "train"}
    assert "have no partition" in problems_after(lambda s: s.pop("7_1_1"))
    assert "not in the image pairs" in problems_after(lambda s: s.update({"99_1_1": "train"}))
    assert "unknown partition names" in problems_after(lambda s: s.update({"7_1_1": "dev"}))
    one_image = problems_after(lambda s: s.update({"1_1_2": other[s["1_1_2"]]}))
    assert "source articles span partitions" in one_image and "pairs cross partitions" in one_image
    # the pair 5_1_2-6_1_1 moves together, but article PMC5 is left in two partitions
    moved = problems_after(lambda s: s.update({"5_1_2": other[s["5_1_2"]], "6_1_1": other[s["6_1_1"]]}))
    assert "source articles span partitions" in moved and "pairs cross partitions" not in moved
    with pytest.raises(ads.SplitError):
        ads.validate_split({**split, "7_1_1": "dev"}, IMAGES, PAIRS)


def test_settings_identifiers_and_files_are_checked(tmp_path):
    _, groups = ads.article_groups(IMAGES, PAIRS)
    for seed in ("42", -42, None, True, 4.2):  # random.Random would accept these silently
        with pytest.raises(ValueError, match="non-negative integer"):
            ads.assign_groups(groups, seed, SMALL)
    with pytest.raises(ValueError, match="fractions"):
        ads.assign_groups(groups, 42, {"train": 0.9, "val": 0.2, "test": 0.1})
    with pytest.raises(SystemExit, match="non-negative integer"):
        splits.make_split(make_config(tmp_path / "a", seed="42"))
    for image_id in ("0123_1_1", "123_1_1\n", "123_1", "PMC123_1_1", "\u0661\u0662_1_1", 123):
        with pytest.raises(ValueError):
            ads.source_article(image_id)
    problems = " | ".join(ads.pair_problems([("1_1_1", "1_1_1"), ("2_1_1", "3_1_1"), ("3_1_1", "2_1_1")]))
    assert "with itself" in problems and "more than once" in problems
    repeated_key = tmp_path / "repeated_key.json"
    repeated_key.write_text('{"1_1_1": "train", "1_1_1": "test"}', encoding="utf-8")
    with pytest.raises(ValueError, match="repeated keys"):
        ads.read_split(repeated_key)


def test_split_step_records_warnings(tmp_path):
    stats = splits.make_split(make_config(tmp_path / "a", fractions={"train": 0.8, "val": 0.1, "test": 0.1}))
    assert "partition val has no images" in stats["warnings"]  # 8 groups: int(0.1 * 8) = 0

    published = tmp_path / "published.json"
    split = ads.generate_split(IMAGES, PAIRS, 42, SMALL)
    split.update({image_id: "val" if split["7_1_1"] != "val" else "test" for image_id in ("7_1_1", "8_1_1")})
    ads.write_split(split, published)  # valid, but not the regenerated split
    cfg = make_config(tmp_path / "b", existing_split=str(published), expected_sha256=None, verify_regeneration=False)
    stats = splits.make_split(cfg)
    assert not stats["identical_to_regenerated"]
    assert any("verify_regeneration is false" in warning for warning in stats["warnings"])


def test_split_file_format(tmp_path):
    split = ads.generate_split(IMAGES, PAIRS, 42, SMALL)
    path = tmp_path / "image_splits.json"
    ads.write_split(split, path)
    assert ads.read_split(path) == split
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "10_1_1": ') and text.endswith('"\n}\n')  # sorted keys, indent 2
    with pytest.raises(FileExistsError):
        ads.write_split(split, path)


def make_config(tmp_path, **split_settings):
    pairs_file = tmp_path / "work" / "image_pairs" / "image_pairs.jsonl"
    write_jsonl([{"pair_id": list(pair)} for pair in PAIRS], pairs_file)
    config = {"paths": {"pmc_patients": "unused.csv", "work_dir": "work",
                        "existing_split": split_settings.pop("existing_split", None)},
              "split": {"seed": 42, "fractions": SMALL, **split_settings}}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return load_config(tmp_path / "config.yaml")


def test_split_step_uses_and_checks_a_split_file(tmp_path):
    drawn = make_config(tmp_path / "a", expected_sha256=None)
    assert splits.make_split(drawn)["method"] == "article_groups"

    published = tmp_path / "published.json"
    ads.write_split(ads.generate_split(IMAGES, PAIRS, 42, SMALL), published)
    cfg = make_config(tmp_path / "b", existing_split=str(published), expected_sha256=ads.sha256_file(published))
    stats = splits.make_split(cfg)
    assert stats["method"] == "existing_split_file" and stats["identical_to_regenerated"]
    assert (tmp_path / "b" / "work" / "split" / "split.json").read_bytes() == published.read_bytes()
    assert set(stats["integrity"].values()) == {0} and stats["totals"]["groups"] == 8

    with pytest.raises(SystemExit, match="SHA-256"):
        splits.make_split(make_config(tmp_path / "c", existing_split=str(published), expected_sha256="0" * 64))

    regrouped = ads.read_split(published)  # a valid split, but not the one the procedure draws
    group = ["7_1_1", "8_1_1"]
    target = next(name for name in ads.PARTITIONS if name != regrouped[group[0]])
    regrouped.update({image_id: target for image_id in group})
    altered = tmp_path / "altered.json"
    ads.write_split(regrouped, altered)
    with pytest.raises(SystemExit, match="differs from the split regenerated"):
        splits.make_split(make_config(tmp_path / "d", existing_split=str(altered), expected_sha256=None))


def run_script(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, cwd=REPOSITORY)


def test_generate_splits_script(tmp_path):
    pairs_file = tmp_path / "image_pairs.json"
    pairs_file.write_text(json.dumps([{"pair_id": list(pair)} for pair in PAIRS]), encoding="utf-8")
    expected = tmp_path / "expected.json"
    ads.write_split(ads.generate_split(IMAGES, PAIRS, 42, SMALL), expected)
    fractions = ["--fractions", "0.5", "0.25", "0.25"]

    result = run_script("--pairs", pairs_file, "--expected", expected, "--output", tmp_path / "out.json", *fractions)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["passed"] and summary["comparison"]["identical"] and summary["comparison"]["byte_identical"]
    assert summary["totals"]["groups"] == 8 and set(summary["integrity"].values()) == {0}
    assert (tmp_path / "out.json").read_bytes() == expected.read_bytes()

    again = run_script("--pairs", pairs_file, "--expected", expected, "--output", tmp_path / "out.json", *fractions)
    assert again.returncode != 0 and "Refusing to overwrite" in again.stderr
    same = run_script("--pairs", pairs_file, "--output", tmp_path / "x.json", "--report", tmp_path / "x.json")
    assert same.returncode != 0 and "must be different files" in same.stderr
    negative = run_script("--pairs", pairs_file, "--seed", "-42")
    assert negative.returncode != 0 and "non-negative integer" in negative.stderr
    doubled = tmp_path / "doubled.json"
    doubled.write_text(json.dumps([{"pair_id": list(pair)} for pair in PAIRS + PAIRS[:1]]), encoding="utf-8")
    repeated = run_script("--pairs", doubled, "--expected", expected, *fractions)
    assert repeated.returncode == 1 and "more than once" in repeated.stderr

    regrouped = ads.read_split(expected)  # valid, but one group in another partition
    regrouped.update({image_id: "val" if regrouped["7_1_1"] != "val" else "test" for image_id in ("7_1_1", "8_1_1")})
    ads.write_split(regrouped, tmp_path / "regrouped.json")
    different = run_script("--pairs", pairs_file, "--expected", tmp_path / "regrouped.json", *fractions)
    assert different.returncode == 1
    comparison = json.loads(different.stdout)["comparison"]
    assert comparison["differing_assignments"] == 2 and not comparison["identical"]


def test_published_split_file():
    assert DEFAULT_CONFIG["paths"]["existing_split"] == str(PUBLISHED)
    assert DEFAULT_CONFIG["split"]["seed"] == ads.DEFAULT_SEED == 42
    assert DEFAULT_CONFIG["split"]["fractions"] == ads.DEFAULT_FRACTIONS
    assert ads.sha256_file(PUBLISHED) == PUBLISHED_SPLIT_SHA256 == DEFAULT_CONFIG["split"]["expected_sha256"]
    for line in (REPOSITORY / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        assert ads.sha256_file(REPOSITORY / name) == digest, name
    split = ads.read_split(PUBLISHED)
    assert ads.split_to_bytes(split) == PUBLISHED.read_bytes()
    assert set(split.values()) == set(ads.PARTITIONS)
    assert ads.integrity_counts(split, split, [])["source_articles_across_partitions"] == 0


@pytest.mark.skipif(not os.environ.get("PMC_PAIR_RELEASE_PAIRS"),
                    reason="set PMC_PAIR_RELEASE_PAIRS to the released image_pairs.json")
def test_published_split_regenerates_from_released_pairs():
    pairs = ads.read_pairs(os.environ["PMC_PAIR_RELEASE_PAIRS"])
    image_ids = sorted({image_id for pair in pairs for image_id in pair})
    split = ads.generate_split(image_ids, pairs)
    assert ads.split_to_bytes(split) == PUBLISHED.read_bytes()
    stats = ads.split_statistics(split, pairs)
    assert stats["totals"]["groups"] == 13371 and stats["totals"]["images"] == len(image_ids)
    assert {name: (values["images"], values["pairs"]) for name, values in stats["partitions"].items()} == {
        "train": (70741, 70492), "val": (8442, 8186), "test": (7922, 7638)}
    assert set(ads.integrity_counts(split, image_ids, pairs).values()) == {0}
