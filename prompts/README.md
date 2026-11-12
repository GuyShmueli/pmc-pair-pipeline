# Prompts

The prompts that this pipeline sends to the language models, one pair of files per stage:

- `<stage>.instructions.txt` — sent as the `instructions` of an OpenAI Responses API request,
- `<stage>.user.txt` — the user message; `{placeholders}` are filled in by `pmc_pair/chipa.py`.

Neither file ends with a line break (`.gitattributes` stops Git from changing the bytes).
Models and reasoning efforts are set in the configuration (`llm.stages`). The SHA-256 of every
file is written to the release `MANIFEST.json`. Editing a prompt makes the cached responses of
that stage (and of all later stages) stale: they are requested again, and `finalize-pairs` /
`export` refuse the stale outputs.

| Stage | Case pairs | Placeholders of `<stage>.user.txt` |
|---|---|---|
| `citation_analysis` | annotation-ready | `{citing_title}`, `{citing_abstract}`, `{citation_paragraph}` (all extracted passages, separated by blank lines; empty if none), `{cited_title}`, `{cited_abstract}` |
| `question_generation` | annotation-ready | `{case_a}` (citing case), `{case_b}` (cited case), `{citation_reason}` (citation-analysis output) |
| `answer_generation` | annotation-ready | `{case_a}`, `{case_b}`, `{citation_reason}`, `{questions}` |
| `pair_selection` | annotation-ready | `{questions}`, `{answers}`, `{captions_a}`, `{captions_b}` (JSON objects `{image_id: caption}`) |

[See the annotation provenance record for the code, prompts, and settings used to generate the deposited annotations.](../docs/ANNOTATION_PROVENANCE.md)
