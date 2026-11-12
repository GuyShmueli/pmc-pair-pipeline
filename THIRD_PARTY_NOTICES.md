# Third-party notices

This file points to the third-party sources that this repository builds on. It sets no terms for
any file. [`LICENSING.md`](LICENSING.md) gives the terms for each path of this repository.

## PMC-Patients

The pipeline reads a PMC-Patients table (`paths.pmc_patients`). This repository does not contain
that table, the PMC-Patients code or the locally modified copy of that code.

Upstream sources:

- Code: <https://github.com/zhao-zy15/PMC-Patients>. The upstream commit used for the
  locally modified copy is not established by the available records.
- Dataset: <https://huggingface.co/datasets/zhengyun21/PMC-Patients> and
  <https://doi.org/10.6084/m9.figshare.c.6723465>
- Article: Zhao et al. A large-scale dataset of patient summaries for retrieval-based clinical
  decision support systems. *Scientific Data* 10, 909 (2023).
  <https://doi.org/10.1038/s41597-023-02814-8>

Each of these sources states its own terms. This repository makes no statement about which of
them applies to any use of PMC-Patients.

## Articles, images and captions

The articles that a pipeline run downloads come from the U.S. National Library of Medicine (NLM):
NIH NLM NCBI PubMed Central (PMC) Article Datasets - Full-Text Biomedical and Life Sciences Journal
Articles on AWS, <https://registry.opendata.aws/ncbi-pmc>. The
[bucket README](https://pmc-oa-opendata.s3.amazonaws.com/README.txt) states the terms of use of
these data, and each article keeps its own terms.

The images and captions of the PMC-PaIR dataset keep the terms recorded for each image in
`licenses.csv` of the dataset.

## Python packages

The packages in `requirements.txt` are not in this repository. They are installed separately, and
each has its own licence.
