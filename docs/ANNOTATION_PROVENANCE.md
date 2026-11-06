# Annotation provenance

This record states how the annotations in the PMC-PaIR deposit were generated, as far as the
saved records of the work establish it. It covers the deposited `image_pairs.json` (86,316 pairs),
`image_labels.jsonl` and `case_pair_citations_eligible.json`, and the benchmark split
`image_splits.json` of this repository. Anything the records do not show is marked "not
established".

The dataset's DOI is 10.5281/zenodo.23439169. The record has not been published yet, so the DOI
does not resolve.

The deposited image pairs come from two annotation runs, not from one run of the `pmc_pair`
package in this repository:

- The **original run** processed a fixed PMC-Patients table. Its cohort has three passes: a
  **first pass**, a **relabeling** pass over the same case pairs, and a **compound-figure
  extension**.
- The **updated run** processed case pairs from a PMC-Patients table regenerated in March 2026.

Section 8 explains how `pmc_pair` relates to these runs.

## Where to find each item

Paths are relative to the repository root. Section 2 gives the model, reasoning effort and request
count of each stage, and `provenance/MANIFEST.json` gives them for each template file.

| Run or pass | Prompts sent | Request and parsing code |
|---|---|---|
| First pass | `provenance/templates/original_run_first_pass/` | `provenance/source/original_run/`: `citation_extraction.cells.py`, `questions_generation.cells.py`, `answers_generation.cells.py`, `generating_pairs.cells.py`, `positives_experimenting.cells.py` |
| Relabeling | `provenance/templates/original_run_relabeling/` | `provenance/source/original_run/repeat_pipeline_compound.cells.py`, cells whose `# --- cell` comment names `relabel` |
| Compound-figure extension | `provenance/templates/original_run_compound_figures/` | the same file, cells whose comment names `compound`; cells named only `post-processing` combine the two passes |
| Updated run | `provenance/templates/updated_run/` | `provenance/source/updated_run/`: `citation_reason.cells.py`, `questions.cells.py`, `answers.cells.py`, `pos_pairs.cells.py` |

| Other material | Location |
|---|---|
| Steps before the language-model stages | `provenance/source/original_run/` and `provenance/source/updated_run/`, listed by step in section 7 |
| Release assembly | `provenance/source/release_assembly/`, described in sections 6 and 7 |
| Image labels, benchmark split | `pmc_pair/labels.py`, `pmc_pair/article_disjoint_split.py` and `scripts/generate_splits.py`, which give the same bytes (section 9) |
| Checking and repackaging the deposit | `pmc_pair/deposit.py`, `pmc_pair/package_deposit.py` and `docs/DEPOSIT.md` |
| Prompts and code for new runs | `prompts/` and `pmc_pair/` (sections 3 and 8) |

These materials are not in this repository:

- the locally modified PMC-Patients construction code and the regenerated table it produced
  (sections 5 and 7);
- the saved request files and response text, which hold case text, and the batch records (sections
  2 and 9);
- the notebook cells and script lines outside the extracts (section 7);
- the scripts that wrote the deposited `image_labels.jsonl`;
- other private working files named in this record, such as `final_csv2.csv`, `pos_pairs.json` and
  `compound_citation_req.jsonl`;
- the code of the deposit's licence review and withholding decisions, and the code that wrote its
  metadata files and ZIP archives.

## 1. The deposited annotations by cohort

| | Original run | Updated run | Deposit |
|---|---:|---:|---:|
| Candidate case pairs (the two sets do not overlap) | 54,979 | 104,409 | 159,388 |
| Case pairs that reached pair selection, the last language-model stage | 36,135 | 86,230 | 122,365 |
| Citation records in `case_pair_citations_eligible.json` | 36,135 | 85,814 | 121,949 |
| Released image pairs | 24,596 | 61,720 | 86,316 |
| Images (8,090 occur in both cohorts) | 30,701 | 64,494 | 87,105 |
| Source articles (6,953 occur in both cohorts) | 20,789 | 42,321 | 56,157 |

38,853 original-run case pairs entered citation analysis. The 24,596 pairs split by the pass whose
response supplied the retained descriptors: first pass 7,406, relabeling 8,560 and compound-figure
extension 8,630. The source files of the cohorts and the `selected_source` column of the private
assembly table agree on the membership of every released pair.

## 2. Models and settings

| Pass | Stage | Model | Reasoning effort | Requests |
|---|---|---|---|---:|
| First pass | citation analysis | `o3-mini` | medium | 31,080 |
| | question generation | `o3-mini` | low | 31,002 |
| | answer generation | `gpt-4.1-mini` | not set in the request | 31,002 |
| | pair selection | `o4-mini` | low | 27,519 |
| Relabeling | pair selection | `gpt-5-mini` | not set in the request | 27,519 |
| Compound-figure extension | citation analysis | `o4-mini` | medium | 13,445 |
| | question generation | `o4-mini` | low | 13,445 |
| | answer generation | `gpt-5-mini` | not set in the request | 13,445 |
| | pair selection | `gpt-5-mini` | not set in the request | 13,445 |
| Updated run | citation analysis | `gpt-5.4-mini` | medium | 86,230 |
| | question generation | `gpt-5.4-nano` | high | 86,230 |
| | answer generation | `gpt-5.4-nano` | high | 86,230 |
| | pair selection | `gpt-5.4-mini` | low | 86,230 |

These values come from a scan of every saved production request. The original-run passes used
`/v1/chat/completions` with a developer and a user message. The updated run used `/v1/responses`
with `instructions` and one user input. No request sets a JSON schema, `temperature`, `top_p`, a
token limit or a seed.

The relabeling pass reused the first-pass questions and answers: its 27,519 user messages are
byte-identical to those of the first-pass pair selection. It did not repeat the citation analyses.

Batch records name the snapshots `o4-mini-2025-04-16` (compound-figure citation analysis and
questions) and `gpt-5-mini-2025-08-07` (compound-figure answers and pairs, relabeling). Raw
responses survive for 5,932 updated-run answers, all with status 200 and the snapshot
`gpt-5.4-nano-2026-03-17`. The snapshots of the other stages are not established, and neither is
the effective reasoning effort of the `gpt-5-mini` requests. The batch records report 62 failed
relabeling requests and 2 failed compound-figure pair requests with no located retry.

## 3. Prompt templates

**Templates supplied for running CHIPA** are in [`prompts/`](../prompts/). `pmc_pair/chipa.py`
sends them with the models in `config.example.yaml`. They did not generate the deposited
annotations. Of the instruction files, only citation analysis matches a saved production request,
the compound-figure extension's, apart from whitespace. `citation_analysis.user.txt` is
byte-identical to the production templates, and `pair_selection.user.txt` matches them apart from
whitespace.

**Templates documented as having generated the deposited annotations** are in
[`provenance/templates/`](../provenance/templates/), one folder per pass:
`original_run_first_pass`, `original_run_relabeling`, `original_run_compound_figures` and
`updated_run`. `<stage>.instructions.txt` holds the exact bytes of the static instructions.
`<stage>.user_template.txt` holds the user message with named placeholders such as `{case_a}`
in place of case-specific content. The first-pass question stage has two wordings: part A
("in bullet or numbered format") for 16,000 requests and part B ("in numbered format") for
15,002. [`provenance/MANIFEST.json`](../provenance/MANIFEST.json) gives the SHA-256, model, effort and
request count of each file.

Every saved production request was checked against these files: the instructions are byte-identical
in all 546,822 requests, and every user message is an instance of its template. The saved requests
show what was submitted; section 2 lists the evidence of what was returned.

Differences that affect the annotations:

| Feature | First pass | Relabeling, compound-figure | Updated run | `prompts/` |
|---|---|---|---|---|
| Radiology-only pre-filter | absent | absent | **present** | absent |
| Pairing criterion | same diagnosis and modality | same modality family; same pathology family and organ system | same modality family; same pathology family and anatomy or organ system | as updated run, without the pre-filter |
| Compound-figure exclusion in the prompt | present | absent | absent | absent |
| Pair output | one JSON object per pair, string `pair_id`, `reasoning`; `{}` if none | same | JSON array, two-element `pair_id`, no `reasoning`; `[]` if none | as updated run |
| Citation-analysis output | adds a `Confidence` line | no `Confidence` line (compound-figure) | no `Confidence` line; the text says "four pieces" and lists three | no `Confidence` line |
| Question count | not limited | not limited | at most 9 | about three per level |
| Case A and Case B | candidate order, not citation direction | candidate order | candidate order | Case A is the citing case |
| Captions in the request | Python `dict` text | Python `dict` text | Python `dict` text | JSON |

The updated-run pre-filter tells the model to keep only captions of radiology modalities and to
ignore clinical photographs, pathology, endoscopy, ECG, ophthalmic imaging and diagrams. It lists
"CT / OCT" as valid and also excludes ophthalmic OCT; the template preserves this as sent.

## 4. Citation evidence the models received

`extracted_citation` in the deposit is the passage extracted for a case pair. In most cases it is
not what the citation-analysis model saw:

- The request writers of the first pass and the updated run read the key `citation_paragraph`,
  while the records hold `citation_paragraphs`. The `Citation Paragraph` field is therefore empty
  in all 31,080 first-pass and all 86,230 updated-run requests. The instructions then direct the
  model to the titles and abstracts.
- The compound-figure requests carry the passage list as text in 11,801 of 13,445 requests and the
  literal `[]` in the others.

Of the 121,949 deposited citation records, 6,857 (5.6%) have a reason whose request contained a
passage, all from the compound-figure extension. Among released pairs, this applies to 0 of 61,720
updated-run pairs and 5,148 of the 24,576 original-run pairs that join two articles. 7,632 released
pairs came through a compound-figure chain whose citation request held a passage. For 2,832
compound-figure pairs the deposited reason is the first-pass record, not the analysis behind their
questions. The question stage receives the citation analysis, not the passages.

Passages were also completed after the model stages: 13,410 deposited passages come from a later
recovery that reads table rows and numeric citation ranges in the source XML. That recovery changed
no `citation_reason`. 863 deposited records have an empty passage.

`citation_reason` has three formats, by the source of the kept record:

| Kept record | In the eligible file | Format |
|---|---:|---|
| First pass (`o3-mini`) | 28,362 | `Reason for Citation:` label and three further lines, including `Confidence:` in nearly all records |
| Compound-figure extension (`o4-mini`) | 7,773 | label, `Possible Similarities:` and `Explanation:` |
| Updated run (`gpt-5.4-mini`) | 85,814 | same, with the `Reason for Citation:` label removed after the run |

## 5. Selection and filtering rules

| Step | Original run | Updated run |
|---|---|---|
| Source table | `PMC-Patients.csv` of the [PMC-Patients dataset](https://huggingface.co/datasets/zhengyun21/PMC-Patients) on Hugging Face, 167,034 rows. The saved table has the size and SHA-256 (`97f41501…`) of that file in revision `e5fbe020` of 2023-11-06. | PMC-Patients regenerated from Open Access Subset files dated up to 2026-03-13 and PubMed files dated 2026-01-29, 319,939 rows, with a locally modified copy of the PMC-Patients construction code. The PMC reference file was empty, so the citation graph used PubMed reference lists only. |
| Case selection | Drop rows without similar patients (104,464 remain); keep articles with exactly one remaining row (63,384); keep cases linked to another kept article: 59,567 cases, 54,979 pairs. | Drop rows with empty `relevant_articles` (4,863, all absent from the older table, 1,099 with similar-patient links). Then keep cases absent from the older table, or older cases with a new similar case, with links cut to new cases (212,065 rows); then the same single-case rule: 106,389 cases, 104,409 pairs, each with a new endpoint. |
| Article files | PMC packages, JPEG and XML files: 61,901 of 63,384 articles. 53 had no package link and 1,430 extractions failed, 1,427 of them for lack of disk space, which removed 2,438 candidate pairs. | The same PMC Open Access packages, all image extensions; a later step repointed 166,174 `.gif` rows to JPEG files at the figure's standard name, moving files where needed, leaving 24. |
| Caption routes | Case-sensitive regular expressions for a label B on the caption text split captions into non-compound and compound (no image inspection). The first pass and relabeling use non-compound captions, and the extension compound captions, so a request never mixes them. 7,811 candidate pairs with figures left after screening in both cases had no route. | No split: a request holds all retained captions. |
| Figure screening | White threshold 250 on the unconverted array, listed if the ratio rounded to two decimals exceeds 0.5, otherwise if OCR returns more than 100 characters. The list that went forward has 20,675 images. Its building loop is not saved; this rule is inferred from the saved code and fits all tested images (see section 10). | Thumbnail of at most 384 pixels, grey level ≥ 250, listed if the ratio exceeds 0.5, otherwise if Tesseract (`--oem 1 --psm 11 -c tessedit_do_invert=0`, English, 2-second timeout) returns more than 200 characters: 54,827 listed. 101 images whose OCR timed out stayed in. |
| Case descriptions | Sections whose title contains `case`, `patient presentation`, `patient report`, `patient description` or `patient summary`, or equals `patient`; all paragraph text of the section, including captions inside it; **the last matching section wins**. | Same heading test and paragraph text; **all matching sections**, with identical texts removed. |
| Citation verification | DOI, PMID, PMCID, then the cited title as a substring of a reference title, in either direction. First pass 10,468 / 16,536 / 0 / 4,076, none 612. Extension 5,475 / 6,805 / 0 / 1,165, none 147. | Same order: 32,761 / 37,912 / 0 / 15,557 on 86,230 pairs; 1,390 had no match. Run only on pairs with descriptions (263 lost before it). |
| Eligibility | First pass: both cases with a description, a citation and a caption left after screening: 31,692 to 31,002 to 27,519. Extension: 13,629 to 13,592 to 13,445. 4,829 pairs are in both routes. | 87,883 candidates to 87,620 to 86,230. |
| Animal cases | **No screen in production.** Applied afterwards to this cohort, the rule flags 172 of the 24,596 released pairs. The precision of the rule is not established. | The rule ran **after the language-model stages** on proposed image pairs: 774 of 62,520 pairs removed, which is 416 case pairs (86,230 − 416 = 85,814). It flags 1,293 of the 86,230 requested case pairs; the other 877 had no proposed pair and remain among the 85,814 records. |
| Modality | Keyword filter applied to the responses (section 6). | Pre-filter in the prompt, then keyword buckets (section 6). |

## 6. From model responses to released pairs

### Original-run cohort

No parser here uses `json-repair`. The first pass parses each response with `json.loads`; 381 of
27,519 responses needed concatenated objects joined into a list first. 426 released pairs keep
descriptors from such responses, and 111 have no other route into the release. The compound-figure
and relabeling parsers accept objects and lists; no released pair from them needed more than
whole-string JSON parsing.

A keyword filter then keeps "radiology" records, with a different rule per pass:

| Pass | Rule | Records in, out |
|---|---|---:|
| First pass | word-boundary regular expressions `RADIOLOGY_MODALITIES` on `modality` | 14,623 to 7,408, then 7,406 after identifier cleanup |
| Compound-figure, single-object responses | substring keywords on `modality` | 5,666 to 3,224 |
| Compound-figure, list responses | same keywords on `modality`, then a fallback over `reasoning`, `anatomy` and `diagnosis` | 7,570 to 5,413 |
| Relabeling | substring keywords on `modality` | 28,967 to 14,431 |

The substring keywords are `ct, computed tomography, mri, magnetic resonance, radiograph, x-ray,
xray, ultrasound, sonograph, sonography, pet, spect, angiograph, angiography, fluoroscopy,
mammograph, mammography, tomograph, tomography`. Because `ct` matches inside other words, `oct`,
`electrocardiogram` and `electron microscopy` pass, and in the fallback so does any text with words
such as "infection". This leaves non-radiology descriptors in the release:

- 1,250 released pairs passed only through the fallback. Their deposited `modality` fails the
  substring keywords, though 24, such as echocardiography, pass the word-boundary rule: pathology or
  microscopy 822, other 265, endoscopy 96, ophthalmology 44, cardiology 23.
- 662 further released pairs have a `modality` that fails the word-boundary rule and passes only
  through `ct`, `pet` or `spect`. They include OCT and ECG strings as well as 17 real cone-beam CT
  strings.

The passes were merged in order, first pass, then compound-figure, then relabeling:
7,406 + 3,224 + 5,413 = 16,043; adding 11,479 relabeling pairs gives 27,522; removing 2,897
reversed duplicates gives 24,625. When a pair recurs, the text of the earlier pass stays. After
their modality filters, first pass and relabeling overlap in 5,849 pairs (11,288 before them) and
disagree on the text of 5,567 of them.

`prepare_pairmed_inputs.py` then removes 29 pairs whose identifiers resolve to no file: 27 have
truncated identifiers, and 2 have well-formed identifiers with no image, giving 24,596.

Two rules stated elsewhere for pipeline output do not hold for this cohort. 20 released pairs join
two images of one article (compound-figure 15, relabeling 4, first pass 1), and `verify-deposit`
reports them as a warning. 4 released pairs have an endpoint that the proposing pass did not offer.
No saved parser here compares returned identifiers with the offered captions.

### Updated-run cohort

No parser here uses `json-repair`. All 86,230 responses are strict JSON arrays (52,020 empty), so
the fence stripping and regular-expression salvage in the parser never fired. Of 62,630 records,
78 have identifiers outside the offered captions and 32 are duplicates, giving 62,520 pairs.

Keyword buckets on `modality` (pathology, ophthalmology, endoscopy and cardiology before
radiology) sort these pairs. `prepare_pairmed_inputs.py` keeps radiology, cardiology, ophthalmology
and other, removing 13 + 13 = 26 pairs. The 13 "pathology" records are ultrasound biomicroscopy,
matched by the keyword `microscop`. Of the 13 "endoscopy" records, 8 name ultrasound or
fluoroscopy and 5 an endoscopic procedure. The animal rule then removes 774 pairs:
62,520 − 26 − 774 = 61,720.

The bucket exclusion and the animal rule applied only to updated-run outputs, and the two cohorts
share no image pair. With the exclusion's bucket order, 1,117 original-run pairs stay in the
pathology and endoscopy buckets (pathology 987, endoscopy 130); with the original-run
radiology-first order, 918.

### Assembly of the deposited files

`prepare_pairmed_inputs.py` unions the cohorts and `pets_filtering` removes the listed pairs, giving
86,316. `build_pair_derived_image_annotations.py` recovers each pair's modality, anatomy and
diagnosis from the saved records whose regenerated text equals the retained text, and records the
source in `selected_source`. `build_pairs_no_pets_categories.py` writes the file that is deposited
as `image_pairs.json`, byte for byte.

Citation records: 86,230 updated-run + 31,080 first-pass + 13,445 compound-figure − 5,672 overlap =
125,083. The eligible file removes 2,640 for figure screening, 78 for incomplete descriptions and
416 for the animal rule, giving 121,949. This filter was reconstructed from saved files after the
annotation stages. It did not run before them.

Image labels and the split are derived from the released pairs (section 9).

## 7. Code

Everything cited here is in [`provenance/source/`](../provenance/source/). Extracts hold the
production code as saved: selected code cells from notebooks, never outputs, and whole scripts or
selected line ranges. The notebook extracts hold 193 of the 1,225 non-empty code cells of their 16
notebooks, and 14 script extracts hold part of a file. Private paths, account
identifiers and literal case identifiers are replaced by tokens such as `<DATA_ROOT>`, and
`provenance/MANIFEST.json` records the counts and the SHA-256 of each private source file. The
extracts depend on notebook state and private inputs, so they are a record and are not meant to be
run. Their article downloads call the PMC OA Web Service and the PMC FTP article packages, which
NCBI ended in August 2026 ([`METHOD.md`](METHOD.md#references), R2 and R3). A line extract can join
separate ranges of a file and then does not parse as a whole: `build_pair_derived_image_annotations.py`
is one.

`provenance/MANIFEST.json` lists the cells or line ranges of each extract. A line that starts with
`# --- cell` or `# --- lines` is added for this record and names the range and its purpose. All
other text, including comments, docstrings, messages, file names and identifiers, is the saved
production text apart from the tokens above. The authors listed in [`CITATION.cff`](../CITATION.cff) wrote
it during the work, and it stays unedited so that the extracts remain a record of the saved code.
Who wrote the code is a separate matter from the terms for these files: see
[`LICENSING.md`](../LICENSING.md).

That text relates runs and passes in its own terms and can use a word differently from this
document. In `original_run/`, `old` usually means the first pass, and `new` the relabeling or
compound-figure pass. In `updated_run/`, `new` usually means the updated run, and `old` the older
PMC-Patients table. In `release_assembly/`, `old` and `legacy` usually mean the original-run cohort,
`original` its first pass and `compound` its compound-figure pass, and `new`, `newer` and `repro`
the updated run. These words also occur with their ordinary meaning. Comments can state what their
authors assumed: `prepare_pairmed_inputs.py` calls the original-run pairs a "radiology-only merged
source", while section 6 lists non-radiology descriptors among them. Where an extract's wording and
this document differ, this document states what the checks established.

| Step | Original run (`original_run/`) | Updated run (`updated_run/`) |
|---|---|---|
| Case selection | `data_processing.py` | `new_pmc_patients_experimenting.cells.py`, `repeat_pipeline_compound.cells.py`, `data_processing.py`, `new_data_processing.py` |
| Article files and figures | `files_info_retrieve.py`, `image_caption_extraction.py`, `final_csv.py` | `files_info_retrieve.py`, `new_image_caption_extraction.py`, `new_final_csv.py`, `pipeline_experimenting.cells.py` |
| Caption routes, candidates | `creating_filtered_df.py`, `initial_project.cells.py`, `creating_uids_pairs.py`, `creating_txt_jpg_pairs.py` | `01_prepare_candidates.py`, `.sh`, `data_prep.py` |
| Figure screening | `filtering_diagrams.py`, `filtering_diagrams.cells.py` | `00_filter_diagrams_2.py`, `.sh` |
| Descriptions | `case_summary_extraction.cells.py`, `repeat_pipeline_compound.cells.py` | `02_extract_case_summaries.py`, `.sh`, `case_summaries.py` |
| Citation verification, passages | `citation_extraction.cells.py`, `extract_citations.py`, `repeat_pipeline_compound.cells.py` | `03_extract_citations.py`, `.sh`, `citations.py`, with the helpers `artifacts.py` and `io_utils.py` |
| Requests and batches | `citation_extraction.cells.py`, `questions_generation.cells.py`, `answers_generation.cells.py`, `generating_pairs.cells.py`, `repeat_pipeline_compound.cells.py` | `citation_reason.cells.py`, `questions.cells.py`, `answers.cells.py`, `pos_pairs.cells.py` |
| Parsing, modality rules | `positives_experimenting.cells.py`, `generating_pairs.cells.py`, `repeat_pipeline_compound.cells.py` | `pos_pairs.cells.py` |

`release_assembly/` holds the steps after the cohorts: `prepare_pairmed_inputs.py`,
`pets_filtering.cells.py`, `build_pair_derived_image_annotations.py`,
`build_pairs_no_pets_categories.py`, and for citation records `updated_run_citation_records.py`,
`updated_run_citation_reason_label_strip.py`, `original_normalizer.py`, `merge_citations.py`,
`citation_recovery.py`, `recover_case_pair_citations.py`, `map_legacy_empty_citations.py`,
`recover_legacy_citations.py` and `eligible_citation_subset.py`. Three of these
(`updated_run_citation_records.py`, `updated_run_citation_reason_label_strip.py`,
`eligible_citation_subset.py`) had no saved script and were recovered from session records. In
sequence, the first two give the SHA-256 in the recovery audit and, after recovery, the saved file
byte for byte. `eligible_citation_subset.py` reproduces its output byte for byte.

**Shared implementation.** One execution of `prepare_pairmed_inputs.py` and of the blacklist step
handled both cohorts. The description heading test, the title normalisation and matching helpers,
and the candidate-pair construction (the first-pass function gives the same 87,883 pairs in the
same order on the updated-run rows) are the same logic in both runs. Image labels and the split
are derived from all released pairs together, with no per-cohort configuration;
`pmc_pair/labels.py` and `pmc_pair/article_disjoint_split.py` reproduce them byte for byte.

**Materially different implementation.** Article download, figure screening, description text
(the two extractors differ for 351 of 1,500 sampled articles), citation lookup details, prompts,
parsers and modality rules; the animal rule ran only in the updated run. These are the extracts
listed in the two columns above.

**Not included.** The regenerated PMC-Patients table was built with a locally modified copy of the
[PMC-Patients construction code](https://github.com/zhao-zy15/PMC-Patients). That copy is not
distributed here, and neither is a patch of it, because the terms that apply to it are not
established. [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) points to the upstream sources.

The table compares the copy with upstream commit `20cba9b`. The seven commits back to `dc43d57`
hold the same versions of these files, and no record names the commit that was copied. Paths are
under `code/PMC-Patients_collection/`, and line counts include the comment blocks.

| File | Lines added, removed | Difference |
|---|---:|---|
| `PMC_OA_utils/PMC_OA_meta.py` | 2, 2 | Data path, final newline. |
| `PMC_OA_utils/extract_PMC_cites.py` | 2, 2 | Data path, final newline. |
| `pubmed_extractors/extract_cites.py` | 115, 34 | Upstream code kept as a 47-line comment block. Reads only `.xml` and `.xml.gz` files, skips records without a PMID, reports failed files and continues, and writes to `pubmed_citations`, the folder `annotate.py` reads. |
| `pubmed_extractors/extract_title_abstract.py` | 134, 45 | Upstream code kept as a 63-line comment block. Same file handling. |
| `PMC-Patients_collection/extractor.py` | 419, 95 | Unpacks XML from Open Access `.tar.gz` packages, accepts `comm` and `oa_comm` folder names, tolerates a missing `article-type` or `article-meta`, has no debugger stop, and collects results with `imap_unordered`, not `map`. |
| `PMC-Patients_collection/filters.py` | 453, 79 | Upstream code kept as a 269-line comment block. Has no debugger stop, numbers notes per PMCID, not per run of adjacent records, normalises file paths and PMIDs, and sorts the PMID list. |
| `PMC-Patients_collection/annotate.py` | 336, 127 | Upstream code kept as a 152-line comment block. Same relations, with normalised PMIDs and sorted lists. |
| `PMC-Patients_collection/add_annotations.py` | 5, 5 | Paths: reads `meta_data/PMC-Patients.json` and writes `datasets/PMC-Patients.json`. |
| `PMC-Patients_collection/add_citation.py` | 2, 2 | Paths. The job did not complete and its output was not used. |
| `PMC-Patients_collection/json_to_csv.py` | 41, 0 | Not in upstream. Writes `datasets/PMC-Patients.csv`. |
| `xml_utils.py` | 0, 0 | Byte-identical, copied into `PMC-Patients_collection/` and `pubmed_extractors/`. |

The extraction expressions, the licence list, the demographic expressions, the filter order and
the relation definitions are the same as upstream. `extract_PMC_cites.py` keeps the upstream logic,
so the empty PMC reference file (section 5) does not come from a change to that script. With
`imap_unordered`, `patient_id` and the row order depend on worker scheduling, as does which article
keeps a note text found in several articles (18 texts, 37 candidates). On the saved table, the
upstream numbering rule gives the same `patient_uid` for all 319,939 rows. Each saved file is dated
before its output, except `add_annotations.py`, whose logic reproduces `datasets/PMC-Patients.json`
byte for byte. These statements come from comparing the code and the saved files. The unmodified
upstream code was not run on these inputs.

## 8. How `pmc_pair` relates to these runs

`pmc_pair` is a single implementation of the workflow, written after these runs. It uses the
updated-run models and screening settings as defaults. It reproduces some production steps and
differs in others:

| Step | Result of comparing `pmc_pair` with production |
|---|---|
| Image labels (`label-images`) | byte-identical `image_labels.jsonl` |
| Split (`scripts/generate_splits.py`) | byte-identical `image_splits.json` |
| Pair checks | a strict rule of the same kind gives the same 62,520 updated-run pairs on the same text |
| Animal rule | same regular expressions; same decision on 90,916 of 90,916 articles given the same metadata. `pmc_pair` runs it before the model stages, so it would exclude every candidate with a flagged article. |
| Citation decisions | same on 1,500 of 1,500 sampled updated-run pairs; same match type on 1,477 of 1,486 |
| Description text | identical for 802 of 3,000 sampled articles. `pmc_pair` leaves out figure captions and matches headings on word boundaries. |
| Citation passages | identical for 1,248 of 1,486 sampled pairs |
| Passages in the citation-analysis request | `pmc_pair` sends them |
| Response repair | `pmc_pair` uses `json-repair`. No production parser did. Re-finalizing production responses with it could change pair counts. |
| Prompts | section 3 |

## 9. Reproducibility by stage

Each row says what was run on 2026-11-04 and what the result establishes. Readers can repeat the
label and split rows with the deposit, using the commands below the table. The other replays used
private working files that hold case text and are not distributed.

| Stage | What was run | Result | What this does not establish |
|---|---|---|---|
| Image labels | `label-images` on the deposited `image_pairs.json` (sha256 `10feb3a9…`) and `label_taxonomy.json` (sha256 `5f73225d…`) | **Byte-identical** to the deposited `image_labels.jsonl` (sha256 `e74b32b4…`, 87,105 records) | The step is a deterministic mapping of the descriptor text. It says nothing about whether a descriptor is correct or how it was produced. |
| Benchmark split | `scripts/generate_splits.py` on the deposited `image_pairs.json` | **Byte-identical** to `image_splits.json` (sha256 `bdad427e…`) and to `data/article_disjoint_split.json` of `pmc-pair-retrieval` | The script reads only `pair_id`. It checks the procedure and the integrity of the partitions, not the annotations. |
| Merge to `image_pairs.json` | Saved code on the saved cohort files, labeled records, blacklist and image tree | **Byte-identical** to the deposited file | Takes the cohort outputs as given. Uses the image files as they stood at the check. |
| Parsing and filters | Saved code on the saved response text | Updated run: 9 of 9 output files byte-identical, and the later pair and text files. Original run: every intermediate file equal up to the 24,625 pairs, the last step byte-identical | Starts from text lists, not raw API output. Execution order of the notebooks is not recoverable. |
| Requests | Saved cells on saved inputs, no API | Updated run: 7 of 7 files byte-identical. First pass, relabeling, compound-figure: identical except two files that need the variant recorded in section 10 | Shows what was submitted, not that every request completed. |
| **Model responses** | Not run: no model was called | **Not regenerated.** The requests set no seed, and OpenAI shut down `o3-mini` and `o4-mini` on 23 October 2026 and lists `gpt-5-mini` for removal on 11 December 2026, `gpt-4.1-mini` on 14 January 2027 and `gpt-5.4-nano` on 1 April 2027 ([deprecations](https://developers.openai.com/api/docs/deprecations), read 2026-11-05). Raw output survives for 5,932 answers; all other stages survive as extracted text only. | None of these replays regenerates a response: they cover the steps before and after the responses. Regenerating the pair annotations themselves has not been shown. |
| Case descriptions, citations | Saved functions on the saved XML | Updated run: byte-identical files. Original run: 31,080 of 31,080 and 13,445 of 13,445 citation records equal, and all description lists | Shows that this code gives the saved lists, not that a match is a true citation: 4,742 original-run and 15,557 updated-run links rest on title text alone. |
| Figure screening | Decisions recomputed on images | Updated run: the saved list reproduces the filtered rows byte for byte, and sample decisions agree (2,000 of 2,000 on ratio, 292 of 292 on finished OCR). Original run: see section 10 | A 2-second OCR limit makes the updated-run list load-dependent at the margin. |
| Case selection | Saved code on the source tables | Updated run: rows and links equal from the regenerated table onward. Original run: byte-identical candidate table | Article download and the `.gif` step changed files and were not replayed. |
| Citation records | Saved code on saved files | Each step byte-identical, up to the eligible file | Takes model responses as given. |

To repeat the label and split checks, install `requirements.txt`, then run from the repository root:

```bash
export DATA=/path/to/zenodo-download WORK=/path/to/new-folder
mkdir -p "$WORK/image_pairs"
python - <<'PY'
import json, os
pairs = json.load(open(os.environ["DATA"] + "/image_pairs.json", encoding="utf-8"))
with open(os.environ["WORK"] + "/image_pairs/image_pairs.jsonl", "w", encoding="utf-8") as f:
    f.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs)
PY
printf 'paths:\n  pmc_patients: unused.csv\n  work_dir: %s\n  release_dir: %s/release\n  label_rules: %s/label_taxonomy.json\n' \
    "$WORK" "$WORK" "$DATA" > "$WORK/labels.yaml"
python -m pmc_pair label-images --config "$WORK/labels.yaml"
cmp "$WORK/labels/image_labels.jsonl" "$DATA/image_labels.jsonl"
python scripts/generate_splits.py --pairs "$DATA/image_pairs.json"
```

## 10. What the records do not establish

- **Original-run source table.** No download record for the 167,034-row table was located. Its
  upstream source rests on the size and SHA-256 match in section 5.
- **Original-run figure list.** The loop that built the 20,675-image list is not saved. The rule in
  section 5 fits everything tested: at white threshold 250, 16,872 listed images exceed ratio 0.5
  and none of the 175,188 unlisted images does; all 3,803 other listed images return more than 100
  OCR characters (minimum 101); none of 2,200 sampled unlisted images does (maximum 99). OCR of
  the remaining unlisted images was not run, and the OCR version used in production is not established.
- **Saved cells that differ from what ran.** `compound_citation_req.jsonl` was written with the
  plural passage key and the saved prompt, while the saved notebook cell shows an earlier key, model
  and wording. Part A of the first-pass question requests uses the wording kept in another cell.
  The private `final_csv2.csv` table is reproduced by the saved join with `how='left'`, while the
  saved code says `how='inner'`. `pos_pairs.json` has no saved writer; it decides that two first-pass records with
  damaged identifiers are dropped.
- **Response alignment.** Without raw output, responses are matched to requests by position. The
  saved compound-figure and relabeling lists are 2 and 62 responses shorter than the requests.
- **Upstream PMC-Patients.** No record names the upstream commit that was copied, and the unmodified
  upstream code was not run on these inputs (section 7). The exact effect of the empty PMC reference
  file is not established. A sample suggests about 1,500 missing candidate pairs against 104,409.
- **Quality of filters.** The precision of the compound-caption expressions, the animal rule and the
  title-only citation matches has not been measured, and neither text has been adjudicated for the
  5,567 pairs on which the first pass and relabeling disagree.
