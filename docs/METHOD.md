# Method implementation

How each step of the pipeline is implemented, with its default parameters
(`config.example.yaml`). All case pairs of a run are processed with one configuration.

## 1. Data source and case selection (`cases.py`, step `select-cases`)

The regenerated PMC-Patients collection is read from one table (`paths.pmc_patients`).
Patient records are counted per article over the whole table, and only articles with
exactly one patient record are kept. Patient identifiers are standardized to
`<pmcid>-<index>`. Links between two retained cases are kept without self links and
counted once regardless of citation direction; cases without a remaining link are
removed. PMC-Patients itself is regenerated outside this pipeline, with the PMC-Patients code
([locations](../README.md#inputs-and-outputs)).

## 2. Figure download and filtering (`pmc_download.py`, `figures.py`, `image_filter.py`, `animal_filter.py`)

- **Articles** are read from the PMC Cloud Service, which distributes the PMC Open Access
  collection as individual files [R1, R3, R4], or from a local mirror of it. NCBI ended the
  PMC OA Web Service and removed the article packages from the PMC FTP site in August 2026
  [R2, R3]. Only Open Access versions are used; a published version is preferred to an
  author manuscript, otherwise the highest version; the version used is logged.
- **Figures:** every `<fig>` element in document order defines the figure extraction
  index of the image identifier, so the identifiers of one article can have gaps where a
  figure is not kept. A figure needs a caption and a JPEG file (`.jpg`/`.jpeg`); a figure
  stored as several image files uses the first one.
- **Screening:** gray level ≥ 250 on a 384-pixel thumbnail; an image is flagged if more
  than half of its pixels are white. Otherwise Tesseract OCR (`--oem 1 --psm 11 -c
  tessedit_do_invert=0`, English, 2-second timeout) is applied, and an image is flagged
  above 200 recognized characters. Images whose OCR times out are kept; images whose OCR
  fails with an error are excluded and screened again on the next run. The Tesseract
  version is recorded in `MANIFEST.json`.
- **Animal cases:** keyword rules for dog and cat case reports on the title, abstract and
  journal title. Exceptions for human contexts such as "dog bite", "CAT scan" and "canine
  teeth" apply to the signals listed in `animal_filter.py`, so a human report that mentions
  a dog or a breed through another signal can still be flagged.

## 3. Case descriptions and citation evidence (`jats.py`, `citations.py`)

- **Case descriptions:** the paragraph text of sections whose title contains the word
  "case" (for example "Case presentation", "Case report"), "patient presentation",
  "patient report", "patient description" or "patient summary", or is "patient".
  Captions and footnotes of figures and tables are left out, and a matching subsection is
  read once, as part of its matching parent.
- **Citation verification:** DOI, PMID and PMCID in this order, then the normalized title
  (lower case, punctuation removed) of the cited article as a substring of a reference
  title. The reference lists of both articles are searched, so either article can be the
  citing one. Identifiers are compared without case, URL prefix or "PMC" prefix. If both
  articles cite each other, the first case in sorted order is the citing case.
- **Citation passages:** for every `<xref>` link to the matched reference, its table row
  (cells separated by " | ") if the citation is in a table, otherwise its paragraph.
  Passages are joined with blank lines (`extracted_citation`). Author–year citations
  without an `<xref>` link give no passage.

## 4. Case pairs processed by each stage (`prepare_pairs.py`, `chipa.py`)

Every candidate pair is checked in this order: both articles available, no animal case,
citation confirmed, both case descriptions non-empty, and at least one retained figure
with a caption for each case (`candidate_status.jsonl` records the first failed check).
The pairs that pass all checks are annotation-ready. All four language-model stages run
on these pairs, and each of them has one record in `case_pair_citations.json`.

## 5. Language-model stages (`chipa.py`, `llm.py`, `prompts/`)

- **Prompts:** `prompts/` holds the four prompts of this pipeline. Each is split into the
  instructions (sent as the `instructions` of an OpenAI Responses API request) and the
  user template (the user message, with `{placeholders}` filled in). Case A is the citing
  case and Case B the cited case.
- **Inputs:** titles, abstracts and citation passages (citation analysis); both case
  descriptions and the citation analysis (question generation); the same plus the
  questions (answer generation); questions, answers and the captions of both cases as
  JSON objects `{image_id: caption}` (pair selection).
- **Models:** `llm.stages`, with the reasoning effort always set explicitly [R5, R6]; the
  model snapshot returned by the API is stored with every response.
- **Requests** are sent through the Batch API (or one by one with `--sync`). The request
  id `<stage>:<case_pair_id>` is the Batch `custom_id`; responses are matched by id and
  cached with the SHA-256 of the full request body.

## 6. Response repair and validation (`pair_parsing.py`, step `finalize-pairs`)

An answer must contain a JSON array of objects. After removing surrounding whitespace
and code-block markers, the standard JSON parser is tried first. Answers it can already
parse are not repaired; a valid JSON value with the wrong structure is still rejected.

If parsing fails, the code looks for one array in the answer, allowing explanatory text
or code-block markers around it. Malformed syntax is repaired locally with
`json-repair==0.64.0` in strict mode. This can recover missing quotation marks, trailing
commas and missing closing delimiters. Competing arrays and ambiguous malformed input,
including repeated object keys encountered during repair, are rejected. Repair does
not use a language model, execute the response as code, or obtain identifiers or
descriptions from another source. It does not fill in missing clinical content: closing
an incomplete structure cannot establish what an unfinished description meant.
Bare image identifiers such as `123_1_2` are quoted without changing their characters,
so the repair library cannot interpret their underscores as numeric separators.
Clearly unfinished quoted values and unquoted omission markers (`...` or `…`) are rejected.

Arrays parsed directly and repaired arrays pass the same proposal checks. In every object,
`pair_id` must be two strings that exactly identify retained captions, one from each
case, and `modality`, `anatomy` and `diagnosis` must be non-empty strings. An answer that
cannot be recovered as an array of objects is rejected in full. Within such an array,
an invalid proposal is rejected individually, with its reason recorded in
`rejected_proposals.jsonl`. No validation failure automatically triggers another model
request.

Pairs are unordered: A--B and B--A are duplicates. Responses are processed by sorted
case-pair identifier, and proposals in their order within each response. The first valid
proposal supplies all three retained descriptions; later duplicate proposals do not
replace or contribute descriptions. The stored `pair_id` is sorted.

Every attempted repair is recorded in `image_pairs/response_repairs.jsonl`, including
the raw response and its hash, repaired JSON or failure, repair details, and the numbers
of proposals kept, rejected and discarded as duplicates. The raw response cache is not
changed. The step's `stats.json` adds `outputs_repair_attempted`, `outputs_repaired` and
`outputs_repair_failed`; a syntactically repaired response may still contain no valid
proposals after the normal checks.

## 7. Image-level labels (`labels.py`, step `label-images`)

Each free-text description is mapped to the controlled vocabulary of
`label_taxonomy.json` (`LABEL_RULES.md`). After text normalization, each rule (aliases
and regular expressions) is matched as whole words; where matches overlap, the one of
higher priority counts, then the longer one. In anatomy, vessel phrases are vasculature
and are masked before the other rules are applied. A diagnosis description is split into
clauses. In each clause, specific rules count before organ-family fallback rules, which
count before generic lesion terms. A counted term with a negation cue in its clause gives
`normal_or_negative_report`, and a resolved term gives `postoperative_or_resolved_state`.
A clause without a term can be an explicit postoperative or normal report. A description
that no rule recognizes receives `other`. An image receives the union of the categories
of all pairs that contain it, deduplicated and sorted, with `other` kept only when no
other category remains. Because a pair description names only the modality both figures
share, the rule of `nuclear_medicine` is also applied to the caption of every image: an
image whose caption names nuclear-medicine imaging (the abbreviation PET only in
capitals) receives `nuclear_medicine` as well.

## 8. Partitions (`article_disjoint_split.py`, `splits.py`, step `split`)

- **Groups:** images are nodes and image pairs are edges. Connected components that
  contain images of the same source article are merged, transitively, into article groups.
  The source article of an image is the PMC number at the start of its identifier.
- **Assignment:** the groups are sorted by their smallest image identifier (string order),
  shuffled with `random.Random(split.seed)` (42; a non-negative integer) and assigned whole,
  by group count
  (`split.fractions`: 0.8 / 0.1 / 0.1). The first `int(0.8 * N)` groups go to train, the
  next `int(0.1 * N)` to val and the rest to test, where N is the number of groups.
  Pairs and article links only decide which images stay together; they add no pairs.
- **Benchmark split:** `paths.existing_split` defaults to `image_splits.json` of this
  repository, the benchmark split. The step checks:
  - its SHA-256 (`split.expected_sha256`);
  - that it covers exactly the paired images, with no source article and no pair across
    partitions;
  - that it equals, image by image, the split regenerated from the pairs
    (`split.verify_regeneration`).

  With `paths.existing_split: null` the step draws the split for the pairs of the run.
  `scripts/generate_splits.py` regenerates the split from a release's `image_pairs.json`
  and compares it with the packaged file, using only the standard library.
- **Statistics:** images, pairs, article groups, components and source articles per
  partition, and the integrity counts, in `<work_dir>/split/stats.json` and `MANIFEST.json`.
  Warnings are recorded there for an empty partition and when `split.verify_regeneration`
  is off.

## 9. Release (`export.py`, `checks.py`, step `export`)

The files and their fields are described in `OUTPUTS.md`. `image_splits.json` is written
with sorted keys and a 2-space indent, so a release made with the benchmark split contains
it byte for byte. The release checks repeat the coverage, integrity and regeneration checks
of section 8 on the released pairs (the SHA-256 check concerns the input file only), and
`CHECKS.json` records whether the regeneration check ran. The images are stored as
`images/<image_id>.jpg` in `images_part_NNN.zip`, 10,000 per archive, with fixed entry
timestamps so that the same images give the same archives. The release is written only
when all model outputs match the current inputs and all checks pass.

## 10. Reproducibility

- Language-model outputs are not deterministic, and model snapshots are retired over time
  [R6, R7]. OpenAI lists `gpt-5.4-nano`, the default of the question and answer stages,
  for removal from its API on 1 April 2027 [R7]; after that date those stages need another
  model. A repeat run can produce different annotations; rebuilding a release exactly
  requires its archived responses (`<work_dir>/llm/`) or Batch files and the matching
  pipeline version, dependencies, inputs and configuration.
- Pair counts, labels and the fit of an existing split depend on the response parser, because
  response repair decides which proposals can be read. Check them before using `finalize-pairs`
  output as a dataset release, even when the cached model responses are unchanged.
- PMC articles receive new versions and corrections; the version used is logged for
  every article. OCR results depend on the Tesseract version.

## References

- [R1] NCBI Insights, "Changes to PMC Article Dataset Distribution Services Coming in 2026"
  (12 February 2026): https://ncbiinsights.ncbi.nlm.nih.gov/2026/02/12/pmc-article-dataset-distribution-services/
- [R2] PMC OA Web Service: https://pmc.ncbi.nlm.nih.gov/tools/oa-service
- [R3] PMC, Accessing PMC Article Datasets using AWS: https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/
- [R4] PMC Cloud Service bucket README: https://pmc-oa-opendata.s3.amazonaws.com/README.txt
- [R5] OpenAI, GPT-5.4 mini: https://developers.openai.com/api/docs/models/gpt-5.4-mini
- [R6] OpenAI, GPT-5.4 nano: https://developers.openai.com/api/docs/models/gpt-5.4-nano
- [R7] OpenAI, Deprecations: https://developers.openai.com/api/docs/deprecations
