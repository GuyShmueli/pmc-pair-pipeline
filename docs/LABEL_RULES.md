# Label taxonomy

Image-level labels are produced by `pmc_pair/labels.py` (step `label-images`) from the
free-text `modality`, `anatomy` and `diagnosis` of each image pair and, for nuclear
medicine, from the caption of each image ([below](#nuclear-medicine-from-captions)). The vocabulary and the
mapping rules are data: `label_taxonomy.json` in this repository, the file released with
the dataset. `paths.label_rules` selects the file, and `export` copies it unchanged into
the release (its SHA-256 is recorded in `MANIFEST.json`).

## Contents of the file

| Key | Content |
|---|---|
| `categories` | per field, `{category: description}`: 12 modality, 20 anatomy and 40 diagnosis categories, each field with `other` |
| `normalization` | `replacements` (`{pattern, replacement}`, regular expressions for spelling variants and plurals, e.g. `tumou?rs?` → `tumor`, `\bhaem` → `hem`), `alias_regular_plurals`, and descriptions of both |
| `rules` | per field, a list of rules: `id`, `label` (a category), `kind` (`specific`, `fallback` or `generic`), `priority`, `aliases` (words and phrases) and `patterns` (regular expressions) |
| `matching` | regular expressions for vessel phrases (`anatomy_vessel_span`), diagnosis clause separators, negation, resolution, unresolved conditions, normal and postoperative reports, and the `priority_policy` as text |
| `expected_unique_images` | number of images of the released annotations (86,893); `label-images` reports it next to the number of images it labeled |
| `version` | version of the taxonomy |

## Procedure

For one description:

1. **Normalization.** Unicode and case folding (accents removed), dashes and punctuation
   replaced by spaces except "/", ",", ";" and decimal points ("X-ray" → "x ray", "H&E" →
   "h e", "PET/CT" → "pet/ct"), the `replacements` in order, single spaces. Aliases are
   normalized in the same way.
2. **Rule expressions.** Each rule is one regular expression, matched as whole words: its
   aliases in the order listed, then its patterns. With `alias_regular_plurals`, an alias
   ending in a consonant and "y" also matches "ies" ("artery", "arteries"), and an alias
   ending in another letter than "s" also matches with a final "s" ("nodule", "nodules").
3. **Overlapping matches.** The matches of all rules of the field are collected. Where
   matches overlap, the one whose rule has the higher priority is kept, then the longer
   one, then the one whose rule id sorts first; the others are dropped. "CT angiography"
   is therefore `ct` (priority 120) and not also `angiography_fluoroscopy` (priority 30).
4. **Modality:** the categories of the kept matches.
5. **Anatomy:** vessel phrases (`anatomy_vessel_span`: up to seven modifiers such as "left
   renal" followed by "artery", "vein", "aorta" or another vessel word) give
   `vasculature` and are masked before the rules are applied. Organ words inside them do
   not count ("left renal vein" is only `vasculature`); organs named elsewhere do
   ("hepatic artery and liver" is `hepatobiliary_pancreatic` and `vasculature`).
6. **Diagnosis:** the text is split into clauses at `diagnosis_clause_separator` (";",
   ",", "but", "however", "and", "with", "plus", "complicated by", "associated with",
   "due to"). In each clause:
   - **Kind.** If a `specific` rule matched, only the specific matches count; otherwise,
     if a `fallback` rule (named organ-family disorder) matched, only the fallback
     matches; otherwise the `generic` ones (unspecified mass or lesion). Thus "abscess
     lesion" is `infection_or_abscess`.
   - **Negation.** A counted match gives `normal_or_negative_report` if the text before
     it in the clause matches `negation_prefix` ("no", "without", "negative for", …) or
     the text after it matches `negation_suffix` ("… was excluded").
   - **Resolution.** Otherwise, it gives `postoperative_or_resolved_state` if the text
     before or after it matches `resolution_prefix` or `resolution_suffix` ("resolved",
     "resected", "… has resolved"), unless the clause matches `unresolved_context`
     ("partially resolved", "no resolution of").
   - **Category.** Otherwise, it gives the category of its rule.
   - **Clause without a match.** Such a clause gives `postoperative_or_resolved_state` if
     it matches `postoperative_report` ("postoperative changes"). Otherwise it gives
     `normal_or_negative_report` if it matches `normal_report` ("normal study").

   The categories of all clauses are combined. Negation and resolution apply within a
   clause: "no tumor but pleural effusion" is `normal_or_negative_report` and
   `edema_or_effusion`.
7. A description with no category receives `other`.

For one image: the union of the categories of every pair that contains the image, per
field, and `nuclear_medicine` if the image's caption names it (next section), deduplicated
and sorted; `other` is kept only when no other category remains. A compound figure is one
image, whose labels may describe different panels.

### Nuclear medicine from captions

A pair description names only the modality its two figures share. Nuclear-medicine
imaging shown beside CT or MRI in a compound figure, or a fused PET/CT image paired with a
plain CT image, is therefore often missing from it. The rule of the `nuclear_medicine`
category (its aliases and patterns, normalized and matched as whole words as in steps 1
and 2) is also applied to the caption of every image, and an image whose caption matches
receives `nuclear_medicine`. Because "pet" is also an ordinary word ("pet dog", "10% in
pet." for petrolatum in patch tests), the abbreviation PET counts in a caption only when
it is written in capitals. No other category is read from captions. The caption category
and the condition on PET are set in `labels.py` (`CAPTION_RULE`, `CAPITAL_PET`), not in
`label_taxonomy.json`. In the released labels, 2,811 images have a caption that names
nuclear-medicine imaging (2,808 of them have a caption file in the Zenodo deposit; the other
3 are withheld images that also have the category from a pair); for 873 of them the
category comes only from the caption. The captions are those of the released
`image_pairs.json` of a pipeline release, and the `captions/IMAGE_ID.txt` files in the
ZIP archives of the Zenodo deposit.

`label-images` also writes, in `<work_dir>/labels/`:
- `phrase_mappings.json`: every distinct description of each field, with its normalized
  text, its categories, the matches behind them and the number of pairs using it;
- `caption_matches.json`: the images whose caption names nuclear-medicine imaging, with
  the matched words and whether a pair description also gives the category;
- `unmatched_phrases.csv`: the descriptions that received `other`.

The following examples are checked by `tests/test_pipeline.py`, together with 96
further descriptions in `tests/label_examples.json`:

| Field | Description | Categories |
|---|---|---|
| modality | MRI | `mri` |
| anatomy | lumbar spine/paraspinal muscles/epidural space | `musculoskeletal`, `spine_spinal_cord` |
| diagnosis | paraspinal abscess with spinal epidural abscess | `infection_or_abscess` |
| diagnosis | hepatic abscess; liver abscess | `infection_or_abscess` |
| diagnosis | tumor; mass; unspecified lesion | `mass_or_lesion` |
| diagnosis | abscess lesion | `infection_or_abscess` |
| diagnosis | no abscess | `normal_or_negative_report` |
| diagnosis | resolved abscess | `postoperative_or_resolved_state` |

## Comparing with existing labels

For the output of a pipeline run, `python -m pmc_pair check --config config.yaml` recomputes
every image label from `image_pairs.json` (descriptions and captions) and `label_taxonomy.json`
of the release and reports the images whose labels in `image_labels.jsonl` differ. Use the
configuration of that run; `--release-dir FOLDER` names a release in another folder. The
deposit has another layout: check it with `verify-deposit` ([DEPOSIT.md](DEPOSIT.md)).

A comparison per field, for any folder that holds `image_pairs.json`, `image_labels.jsonl` and
`label_taxonomy.json`, including the Zenodo download with its ZIP archives extracted in place
(the captions are then in `captions/`). Run it from that folder with the package installed:

```python
import json
from pathlib import Path
from pmc_pair.labels import FIELDS, caption_categories, combine_image_labels, load_label_rules, pair_categories

rules = load_label_rules("label_taxonomy.json")
pairs = json.load(open("image_pairs.json", encoding="utf-8"))
released = {}
with open("image_labels.jsonl", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        released[record["image_id"]] = record["labels"]
# captions: in the records of a pipeline release; as captions/IMAGE_ID.txt in the Zenodo download
captions = {c["image_id"]: c["caption"] for pair in pairs for c in pair.get("captions", [])}
captions.update({path.stem: path.read_text(encoding="utf-8") for path in Path("captions").glob("*.txt")})

recomputed = {r["image_id"]: r["labels"] for r in combine_image_labels(
    pair_categories(pairs, rules), rules["other"], caption_categories(captions, rules))}
for field in FIELDS:
    different = [i for i in released if recomputed.get(i, {}).get(field) != released[i][field]]
    print(f"{field}: {len(different)} of {len(released)} images differ, e.g. {different[:3]}")
```

The 68 withheld images of the Zenodo deposit have no caption file; the caption rule changes
the labels of none of them.
