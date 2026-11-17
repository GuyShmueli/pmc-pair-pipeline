# Licensing

Different terms apply to different files of this repository. Every file belongs to one class
below.

| Class | Paths | Terms |
|---|---|---|
| Code, documentation, configuration, prompts, examples and tests | `pmc_pair/**`, `scripts/**`, `prompts/**`, `examples/**`, `tests/**`, `docs/**`, `README.md`, `LICENSE`, `LICENSING.md`, `THIRD_PARTY_NOTICES.md`, `CITATION.cff`, `SHA256SUMS`, `config.example.yaml`, `pyproject.toml`, `requirements.txt`, `environment.yml`, `.gitattributes`, `.gitignore` | MIT license in [`LICENSE`](LICENSE) |
| Data | `image_splits.json`, `label_taxonomy.json` | [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) (CC BY 4.0) |

A path that is not in this table is covered by neither license.

## What `LICENSE` covers

`LICENSE` holds the standard MIT text. In this repository, its words "this software and
associated documentation files" mean the files of the first class and no others. A wheel built
from `pyproject.toml` holds only the `pmc_pair` package, so all of its code is in the first class.

## Data files

`image_splits.json` (the article-disjoint benchmark split) and `label_taxonomy.json` (the label
vocabularies and the rules that map pair descriptions to labels) are released under the
Creative Commons Attribution 4.0 International license, to the extent that the authors hold
copyright or similar rights in them. Legal code:
https://creativecommons.org/licenses/by/4.0/legalcode

Attribute the PMC-PaIR dataset and its authors as listed in [`CITATION.cff`](CITATION.cff), and
indicate any modifications, as the license requires. The same terms apply to the copies of these
files elsewhere: `label_taxonomy.json` in the PMC-PaIR dataset (see its `LICENSE.txt`) and
`data/article_disjoint_split.json` in the `pmc-pair-retrieval` repository, which is identical to
`image_splits.json`.

## Material outside this repository

The articles, images and captions that the pipeline reads or writes are not in this repository.
Images and captions keep the terms recorded for each image in `licenses.csv` of the PMC-PaIR
dataset. [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) points to the sources of the articles
and of PMC-Patients. The Python packages in `requirements.txt` are installed separately, under
their own terms.

## Quotations

Quoted text keeps the terms of its source wherever it appears, including the sentence from the
PMC-Patients README quoted in `README.md`.
