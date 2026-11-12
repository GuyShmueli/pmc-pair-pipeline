# Inputs and outputs

## Inputs

| Input | Config key | Format |
|---|---|---|
| Regenerated PMC-Patients collection | `paths.pmc_patients` | CSV, JSON list or JSONL; fields `patient_uid` (e.g. `9899453-1`) and `similar_patients` (dict `{patient_uid: score}`, a Python/JSON literal in CSV files). Other columns are ignored. |
| PMC Open Access articles | `paths.pmc_source` | PMC Cloud Service URL (`https://pmc-oa-opendata.s3.amazonaws.com`) or a local folder with the same layout (`PMC<id>.<version>/PMC<id>.<version>.xml`, `.json`, figure files) |
| Label taxonomy (vocabulary and mapping rules) | `paths.label_rules` (default: `label_taxonomy.json` of this repository) | JSON, see `LABEL_RULES.md` |
| Split file | `paths.existing_split` (default: `image_splits.json` of this repository, the benchmark split; `null` draws a split) | JSON `{image_id: "train" / "val" / "test"}`; must have `split.expected_sha256`, fit the pairs and equal the regenerated split |
| OpenAI API key (only for model calls) | environment variable `OPENAI_API_KEY` | never stored in files |

## Work directory (`paths.work_dir`)

Every step writes its outputs and a `stats.json` with counts into its own folder. The
`.jsonl` files marked "checkpoint" are appended to while a step runs, so a step that is
interrupted continues where it stopped.

| Folder | Main files |
|---|---|
| `cases/` | `cases.jsonl` (`case_id`, `pmcid`), `case_pairs.jsonl` (`case_pair_id`, `case_ids`) |
| `articles/` | `PMC<id>/article.xml`, `metadata.json`, JPEG files; `download_log.jsonl` (checkpoint: status, version, licence per article) |
| `figures/` | `figures.jsonl` (`image_id`, `case_id`, `figure_index`, `figure_xml_id`, `image_file`, `caption`, …), `figure_issues.jsonl` |
| `image_filter/` | `image_filter.jsonl` (checkpoint: white ratio, OCR character count, `flagged`, `reason`, `settings_id` of the thresholds used) |
| `pairs/` | `articles.jsonl`, `candidate_status.jsonl` (first failed check of every candidate pair), `citation_pairs.jsonl` (pairs with a confirmed citation: titles, abstracts, citation passages), `annotation_ready.jsonl` (case descriptions and captions) |
| `llm/<stage>/` | `responses.jsonl` (cache, checkpoint), `outputs.jsonl` (answers of the current requests), `requests/` (batch input files), `batch_outputs/`, `batches.json`, `failures.jsonl` |
| `image_pairs/` | `image_pairs.jsonl` (validated pairs), `rejected_proposals.jsonl` (with reasons), `response_repairs.jsonl` (every attempted response repair; see below), `stats.json` |
| `labels/` | `image_labels.jsonl` (copied into the release), `phrase_mappings.json` (categories and matches of every distinct description), `unmatched_phrases.csv` (descriptions labelled `other`) |
| `split/` | `split.json` (the split used, in the format of `image_splits.json`), `stats.json` (images, pairs, groups, components and source articles per partition; integrity counts; warnings; SHA-256) |
| `pipeline.log` | log of all steps |

`image_pairs/response_repairs.jsonl` records every repair attempt, including attempts
that fail. Each record contains the raw response and its hash, repaired JSON or the
failure, details from the repair library, and counts of proposals kept, rejected and
discarded as duplicates. It is work-directory evidence; it does not replace the raw
responses in the language-model cache. Successfully parsing a repaired answer does not
mean every proposal passed the image-identifier and required-field checks.

The image-pair `stats.json` includes `outputs_repair_attempted`, `outputs_repaired` and
`outputs_repair_failed`, together with the proposal and rejection counts.
An empty array recovered from surrounding prose counts as a repaired response but adds
no proposed pairs.

Identifiers: case `9899453-1`; image `9899453_1_1` (article, case index, figure extraction
index = position of the `<fig>` element in the article XML); case pair
`4023003-1__9899453-1` (sorted case ids); model request `<stage>:<case_pair_id>`.

## Release (`paths.release_dir`)

File names are set in the configuration (`release.file_names`).

| File | Content |
|---|---|
| `image_pairs.json` | JSON array; per pair: `pair_id` (two image ids, sorted), `modality`, `anatomy`, `diagnosis` (free text), `captions` (two objects `{"image_id", "caption"}` in `pair_id` order) |
| `image_labels.jsonl` | one line per image: `{"image_id": ..., "labels": {"modality": [...], "anatomy": [...], "diagnosis": [...]}}` |
| `label_taxonomy.json` | the label taxonomy (vocabulary and mapping rules) used for the labels |
| `case_pair_citations.json` | JSON array; per annotation-ready case pair: `citing_case`, `cited_case` (`PMC…`), `extracted_citation` (the passages given to the model, paragraphs or table rows; empty if none), `citation_reason` (model output) |
| `image_splits.json` | `{image_id: "train" / "val" / "test"}`, article-disjoint; sorted keys, 2-space indent (byte-identical to the benchmark file when that is used) |
| `images_part_NNN.zip` | image files `images/<image_id>.jpg`, `release.images_per_zip` per archive |
| `CHECKS.json` | result of the release checks |
| `MANIFEST.json` | counts, SHA-256 of all files, inputs and prompt files, settings, model snapshots and response sources (`sync`, `batch`, `batch_file`, `import`) per stage, Tesseract version, statistics of every step, pipeline version and git commit (`null` unless the code runs from a checkout of its own Git repository) |

The release is written to `<release_dir>.incomplete` first and moved into place only when
all model outputs match the current inputs and every check passes; an existing
`release_dir` is replaced only if it holds a release (`MANIFEST.json`).

Text descriptions for retrieval can be rebuilt from a pair record with the template
`"{diagnosis} in the {anatomy} on {modality}."`.
