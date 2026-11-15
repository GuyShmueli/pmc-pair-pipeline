"""Step 11 (label-images): image-level labels from the pair descriptions and, for nuclear
medicine, from the image captions.

The free-text modality, anatomy and diagnosis of every image pair are mapped to the
controlled vocabulary of the label taxonomy (paths.label_rules, released as
label_taxonomy.json) with its predefined rules; docs/LABEL_RULES.md describes the
procedure. The categories of a pair are assigned to both of its images. A pair
description names only the modality its two figures share, so nuclear-medicine imaging
shown beside CT or MRI in a compound figure, or a fused PET/CT image paired with a CT
image, is often missing from it; the taxonomy's nuclear_medicine rule is therefore also
applied to the caption of every image (CAPTION_RULE). Every image receives the union of
the categories of all pairs that contain it and of its caption, sorted, with "other"
only when no other category remains. A compound figure is one image, whose labels may
come from different panels.

Outputs in <work_dir>/labels/:
  image_labels.jsonl      one {"image_id", "labels": {modality, anatomy, diagnosis}} per image
  phrase_mappings.json    every distinct description per field: normalized text,
                          categories, the matches behind them, number of pairs using it
  caption_matches.json    images whose caption names nuclear-medicine imaging: the matched
                          words and whether a pair description also gives the category
  unmatched_phrases.csv   descriptions that no rule recognizes (category "other")
  stats.json              category counts per field
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .config import log, work_dir
from .io_utils import iter_jsonl, read_json, write_json, write_jsonl

FIELDS = ("modality", "anatomy", "diagnosis")
OTHER = "other"
NEGATIVE = "normal_or_negative_report"        # "no abscess", "normal study"
RESOLVED = "postoperative_or_resolved_state"  # "resolved abscess", "postoperative changes"
VASCULATURE = "vasculature"                   # anatomy category of vessel phrases
# The category that is also read from each image's own caption, with the taxonomy rules of
# that category. Lower-case "pet" is also an ordinary word ("pet dog", "10% in pet." for
# petrolatum in patch tests), so the abbreviation PET counts in a caption only in capitals.
CAPTION_RULE = ("modality", "nuclear_medicine")
CAPITAL_PET = re.compile(r"\bPETs?\b")


def normalize(text, replacements):
    """Unicode and case folding, dashes and punctuation to spaces (keeping "/", ",", ";"
    and decimal points), the taxonomy's spelling and plural replacements, single spaces."""
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[‐‑‒–—−-]", " ", text)
    text = re.sub(r"[^\w\s/,;.]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    text = text.replace("_", " ")
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def alias_pattern(alias, replacements, regular_plurals):
    """Regular expression for one alias, normalized like the descriptions. With regular
    plurals, a final consonant + "y" also matches "ies" ("artery", "arteries") and other
    aliases ending in a letter other than "s" also match with a final "s"."""
    normalized = normalize(alias, replacements)
    pattern = re.escape(normalized)
    if regular_plurals:
        if re.search(r"[bcdfghjklmnpqrstvwxz]y$", normalized):
            pattern = pattern[:-1] + "(?:y|ies)"
        elif re.search(r"[a-z]$", normalized) and not normalized.endswith("s"):
            pattern += "s?"
    return pattern


def load_label_rules(path):
    """Read the label taxonomy and compile one regular expression per rule: its aliases,
    then its patterns, as whole words."""
    if not path:
        raise SystemExit("Set paths.label_rules to the label taxonomy file (see docs/LABEL_RULES.md).")
    taxonomy = read_json(path)
    replacements = [(re.compile(r["pattern"]), r["replacement"]) for r in taxonomy["normalization"]["replacements"]]
    regular_plurals = taxonomy["normalization"].get("alias_regular_plurals", False)
    fields = {}
    for field in FIELDS:
        categories = sorted(taxonomy["categories"][field])
        rules = []
        for rule in taxonomy["rules"][field]:
            alternatives = [alias_pattern(a, replacements, regular_plurals) for a in rule.get("aliases", [])]
            alternatives += rule.get("patterns", [])
            if rule["label"] not in categories or not alternatives:
                raise ValueError(f"{path}: rule {rule['id']} needs a {field} category and at least one "
                                 f"alias or pattern")
            rules.append({"id": rule["id"], "label": rule["label"], "priority": rule["priority"],
                          "kind": rule.get("kind", "specific"),
                          "regex": re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)")})
        fields[field] = {"categories": categories, "rules": rules}
    for field, needed in (("modality", [OTHER]), ("anatomy", [OTHER, VASCULATURE]),
                          ("diagnosis", [OTHER, NEGATIVE, RESOLVED])):
        missing = [name for name in needed if name not in fields[field]["categories"]]
        if missing:
            raise ValueError(f"{path}: the {field} categories must include {missing}")
    matching = {key: re.compile(value) for key, value in taxonomy["matching"].items() if key != "priority_policy"}
    return {"other": OTHER, "replacements": replacements, "matching": matching, "fields": fields,
            "version": taxonomy.get("version"), "expected_unique_images": taxonomy.get("expected_unique_images")}


def find_matches(text, rules):
    """Rule matches in the text. Where matches overlap, the one of higher priority is kept,
    then the longer one, then the one whose rule id sorts first."""
    hits = []
    for rule in rules:
        for match in rule["regex"].finditer(text):
            hits.append({"label": rule["label"], "rule": rule["id"], "priority": rule["priority"],
                         "kind": rule["kind"], "start": match.start(), "end": match.end(), "text": match.group()})
    kept = []
    for hit in sorted(hits, key=lambda h: (-h["priority"], -(h["end"] - h["start"]), h["rule"], h["start"])):
        if not any(hit["start"] < k["end"] and k["start"] < hit["end"] for k in kept):
            kept.append(hit)
    return kept


def classify(text, field, rules):
    """{"normalized", "labels", "matches"} for one description; "labels" is the sorted list
    of categories (["other"] if no rule recognizes the description)."""
    matching, field_rules = rules["matching"], rules["fields"][field]["rules"]
    text = normalize(text, rules["replacements"])
    labels, evidence = set(), []
    if field == "anatomy":
        # Vessel phrases ("left renal vein") are vasculature. They are masked before the
        # organ and tissue rules are applied; organs named elsewhere in the text still count.
        masked = list(text)
        for m in matching["anatomy_vessel_span"].finditer(text):
            labels.add(VASCULATURE)
            evidence.append({"rule": "anatomy_vessel_span", "text": m.group(), "label": VASCULATURE})
            masked[m.start():m.end()] = " " * (m.end() - m.start())
        hits = find_matches("".join(masked), field_rules)
        labels.update(h["label"] for h in hits)
        evidence.extend(hits)
    elif field == "modality":
        hits = find_matches(text, field_rules)
        labels.update(h["label"] for h in hits)
        evidence.extend(hits)
    else:
        for clause in filter(None, (c.strip() for c in matching["diagnosis_clause_separator"].split(text))):
            hits = find_matches(clause, field_rules)
            # specific conditions before named organ-family fallbacks, before generic lesion terms
            specific = [h for h in hits if h["kind"] == "specific"]
            if specific:
                hits = specific
            elif any(h["kind"] == "fallback" for h in hits):
                hits = [h for h in hits if h["kind"] == "fallback"]
            for hit in hits:
                before, after = clause[:hit["start"]], clause[hit["end"]:]
                label, state = hit["label"], "reported"
                if matching["negation_prefix"].search(before) or matching["negation_suffix"].search(after):
                    label, state = NEGATIVE, "negated"
                elif not matching["unresolved_context"].search(clause) and (
                        matching["resolution_prefix"].search(before) or matching["resolution_suffix"].search(after)):
                    label, state = RESOLVED, "resolved"
                labels.add(label)
                evidence.append({**hit, "label": label, "state": state, "clause": clause})
            if not hits:  # no condition named: an explicit postoperative or normal report
                if matching["postoperative_report"].search(clause):
                    labels.add(RESOLVED)
                    evidence.append({"rule": "postoperative_report", "label": RESOLVED, "clause": clause})
                elif matching["normal_report"].search(clause):
                    labels.add(NEGATIVE)
                    evidence.append({"rule": "normal_report", "label": NEGATIVE, "clause": clause})
    return {"normalized": text, "labels": sorted(labels or {OTHER}),
            "matches": sorted(evidence, key=lambda h: (h.get("clause", ""), h.get("start", -1), h["rule"]))}


def map_description(text, field, rules):
    """Sorted categories of one free-text description (["other"] if nothing is recognized)."""
    return classify(text, field, rules)["labels"]


def pair_categories(pairs, rules):
    """Categories of the three descriptions of every pair; repeated descriptions are mapped once."""
    cache = {}

    def categories(text, field):
        if (field, text) not in cache:
            cache[(field, text)] = map_description(text, field, rules)
        return cache[(field, text)]

    return [{"pair_id": pair["pair_id"], "labels": {field: categories(pair[field], field) for field in FIELDS}}
            for pair in pairs]


def caption_categories(captions, rules):
    """{image_id: matched words} for the images whose caption ({image_id: caption}) names
    the category of CAPTION_RULE, found with that category's taxonomy rules in the
    normalized caption."""
    field, label = CAPTION_RULE
    category_rules = [rule for rule in rules["fields"][field]["rules"] if rule["label"] == label]
    found = {}
    for image_id, caption in captions.items():
        words = sorted({hit["text"] for hit in find_matches(normalize(caption, rules["replacements"]), category_rules)})
        if set(words) - {"pet", "pets"} or (words and CAPITAL_PET.search(caption)):
            found[image_id] = words
    return found


def combine_image_labels(pair_labels, other, caption_found=()):
    """Union of the pair categories per image, plus the category of CAPTION_RULE for the
    images in caption_found (caption_categories), sorted by image id; "other" only if
    nothing else remains."""
    collected = defaultdict(lambda: {field: set() for field in FIELDS})
    for record in pair_labels:
        for image_id in record["pair_id"]:
            for field in FIELDS:
                collected[image_id][field].update(record["labels"][field])
    field, label = CAPTION_RULE
    for image_id in caption_found:
        if image_id in collected:  # images that share no pair receive no labels
            collected[image_id][field].add(label)
    image_labels = []
    for image_id in sorted(collected):
        labels = {}
        for field in FIELDS:
            recognised = collected[image_id][field] - {other}
            labels[field] = sorted(recognised) if recognised else [other]
        image_labels.append({"image_id": image_id, "labels": labels})
    return image_labels


def label_images(cfg):
    from .prepare_pairs import annotation_ready_pairs

    rules = load_label_rules(cfg["paths"]["label_rules"])
    pairs = list(iter_jsonl(work_dir(cfg, "image_pairs") / "image_pairs.jsonl"))
    captions = {}  # the captions exactly as the pair-selection model received them (as in export)
    for pair in annotation_ready_pairs(cfg):
        captions.update(pair["case_a_captions"])
        captions.update(pair["case_b_captions"])

    # every distinct description is mapped once
    mappings = {field: {} for field in FIELDS}
    for field in FIELDS:
        for phrase, count in sorted(Counter(pair[field] for pair in pairs).items()):
            mappings[field][phrase] = {**classify(phrase, field, rules), "pair_frequency": count}
    pair_labels = [{"pair_id": pair["pair_id"], "labels": {f: mappings[f][pair[f]]["labels"] for f in FIELDS}}
                   for pair in pairs]
    paired = sorted({image_id for pair in pairs for image_id in pair["pair_id"]})
    caption_found = caption_categories({image_id: captions[image_id] for image_id in paired}, rules)
    image_labels = combine_image_labels(pair_labels, rules["other"], caption_found)

    out_dir = work_dir(cfg, "labels")
    write_jsonl(image_labels, out_dir / "image_labels.jsonl", compact=True)
    write_json(mappings, out_dir / "phrase_mappings.json", sort_keys=True)
    caption_field, caption_label = CAPTION_RULE
    from_pairs = {image_id for record in pair_labels if caption_label in record["labels"][caption_field]
                  for image_id in record["pair_id"]}
    write_json({image_id: {"words": words, "also_from_pair_descriptions": image_id in from_pairs}
                for image_id, words in caption_found.items()}, out_dir / "caption_matches.json", sort_keys=True)
    with open(out_dir / "unmatched_phrases.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "phrase", "normalized", "pair_frequency"])
        for field in FIELDS:
            for phrase, value in sorted(mappings[field].items(), key=lambda pv: (-pv[1]["pair_frequency"], pv[0])):
                if value["labels"] == [rules["other"]]:
                    writer.writerow([field, phrase, value["normalized"], value["pair_frequency"]])

    stats = {"label_rules_file": Path(cfg["paths"]["label_rules"]).name, "taxonomy_version": rules["version"],
             "pairs": len(pairs), "images": len(image_labels),
             "taxonomy_expected_unique_images": rules["expected_unique_images"],  # images of the released annotations
             "caption_rule": {"field": caption_field, "category": caption_label,
                              "images_with_matching_caption": len(caption_found),
                              "images_with_the_category_only_from_the_caption":
                                  sum(image_id not in from_pairs for image_id in caption_found)},
             "fields": {}}
    for field in FIELDS:
        counts = Counter(label for record in image_labels for label in record["labels"][field])
        unmatched = [value for value in mappings[field].values() if value["labels"] == [rules["other"]]]
        stats["fields"][field] = {
            "declared_categories": len(rules["fields"][field]["categories"]),
            "observed_categories": len(counts),
            "category_image_counts": dict(sorted(counts.items())),
            "other_images": counts[rules["other"]],
            "distinct_input_phrases": len(mappings[field]),
            "unmatched_distinct_phrases": len(unmatched),
            "unmatched_pair_descriptions": sum(value["pair_frequency"] for value in unmatched),
            "multilabel_images": sum(len(record["labels"][field]) > 1 for record in image_labels),
        }
    write_json(stats, out_dir / "stats.json")
    published = rules["expected_unique_images"]
    log(cfg, f"label-images: {len(image_labels)} images labeled"
             + (f" (the taxonomy file states {published} for the published release)" if published else "")
             + "; 'other' per field " + str({f: stats["fields"][f]["other_images"] for f in FIELDS})
             + f"; {caption_label} from captions: {len(caption_found)} images, "
               f"{stats['caption_rule']['images_with_the_category_only_from_the_caption']} of them not from a pair")
    return stats
