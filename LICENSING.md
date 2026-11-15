# Licensing

Different terms apply to different files of this repository. Every file belongs to one class
below. The MIT license in [`LICENSE`](LICENSE) applies to the first class only.

| Class | Paths | Terms |
|---|---|---|
| Code, documentation and configuration | `pmc_pair/**`, `scripts/**`, `tests/*.py`, `docs/**`, `README.md`, `LICENSE`, `LICENSING.md`, `THIRD_PARTY_NOTICES.md`, `CITATION.cff`, `SHA256SUMS`, `config.example.yaml`, `pyproject.toml`, `requirements.txt`, `environment.yml`, `.gitattributes`, `.gitignore` | MIT license in `LICENSE` |
| Non-code files and examples | `image_splits.json`, `label_taxonomy.json`, `prompts/**`, `tests/label_examples.json`, `examples/**` | Not yet set |

A path that is not in this table is not covered by `LICENSE`.

## What `LICENSE` covers

`LICENSE` holds the standard MIT text. In this repository, its words "this software and
associated documentation files" mean the files of the first class and no others. It grants no
license for the other class. A wheel built from `pyproject.toml` holds only the `pmc_pair`
package, so all of its code is in the first class.

## Files with terms not yet set

The terms for the non-code files and the examples are not yet set. `LICENSE` grants no
license for them.

## Material outside this repository

The articles, images and captions that the pipeline reads or writes are not in this repository.
Images and captions keep the terms recorded for each image in `licenses.csv` of the PMC-PaIR
dataset. [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) points to the sources of the articles
and of PMC-Patients. The Python packages in `requirements.txt` are installed separately, under
their own terms.

## Quotations

Quoted text keeps the terms of its source wherever it appears, including the sentence from the
PMC-Patients README quoted in `README.md`.
