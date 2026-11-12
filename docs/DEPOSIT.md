# Checking and repackaging the Zenodo deposit

The dataset deposit, *PMC-PaIR: Clinically similar medical image pairs from PubMed Central
case reports*, can be checked using only its downloaded files and this repository. These
commands do not run CHIPA or change the annotations.

The dataset's DOI is 10.5281/zenodo.23439169. The record has not been published yet, so
the DOI does not resolve.

## Downloaded files

Download all files from the same dataset record into one new directory. Check the
download before extraction. The checker also permits extracted `images/` and `captions/`
directories, but checks the archived contents, not those loose copies. Keep reports and
other working files outside the download directory. The expected layout is:

```text
zenodo-download/
  image_pairs.json
  image_labels.jsonl
  label_taxonomy.json
  case_pair_citations_eligible.json
  images_captions_001.zip
  images_captions_002.zip
  images_captions_003.zip
  images_captions_004.zip
  file_manifest.csv
  included_image_ids.txt
  withheld_image_ids.txt
  withheld.csv
  licenses.csv
  pair_availability.csv
  release_summary.json
  README.txt
  LICENSE.txt
  SHA256SUMS.txt
```

The split is supplied with the code as `image_splits.json`. It is not a required file
in the dataset download. The `pmc-pair-retrieval` repository supplies the same assignments
in `data/article_disjoint_split.json`.

## Verify the downloaded release

After installing the pipeline's dependencies, run from the repository root:

```bash
python -m pmc_pair verify-deposit --data-dir /path/to/zenodo-download
```

The checker reads all four ZIPs directly, without extracting them. It checks:

- the deposited file inventory and SHA-256 checksums against `SHA256SUMS.txt`;
- each archived image and caption against the filename, size and hash recorded in
  `file_manifest.csv`;
- agreement between archive contents and the included image identifiers, with withheld
  images excluded;
- consistency of pairs, captions, citation records, labels, taxonomy, licensing and
  availability records, and the release counts.

`SHA256SUMS.txt` must list every deposited file except itself, including the taxonomy and
citation records. A failed check should be resolved with the matching release files or
corrected release metadata before use. The report lists 19 within-case image pairs under
`warnings`; they are part of the deposited annotations and do not fail the check.

To include the repository's split in the checks and write a report:

```bash
python -m pmc_pair verify-deposit \
  --data-dir /path/to/zenodo-download \
  --split-file image_splits.json \
  --report-file /path/to/reports/deposit-check.json
```

The report path must be outside the downloaded directory and must not already exist.
Its parent directory must already exist. Verification leaves the downloaded files
unchanged. No model downloads, API calls, image inference or GPU are needed.

A passing check establishes consistency of this deposit. It does not regenerate the
citation, annotation or licensing decisions.

## Repackage from image and caption files

To obtain the exact deposited ZIPs, download them from the dataset record. To build
new ZIPs from loose files, supply the deposit metadata and the image and caption
locations explicitly:

```bash
python -m pmc_pair package-deposit \
  --images-dir /path/to/images \
  --captions-dir /path/to/captions \
  --metadata-dir /path/to/deposit-metadata \
  --output-dir /path/to/new-deposit
```

`--images-dir` contains `<image_id>.jpg` files and `--captions-dir` contains
`<image_id>.txt` files. Both must provide the files selected by the manifest.
Images alone are insufficient because captions are also part of the release. The
metadata directory supplies the non-ZIP files listed above. Its `SHA256SUMS.txt`
must cover all metadata files and keep the checksum entries of the deposited ZIPs,
consistent with `release_summary.json`, even when those ZIPs are absent. Existing ZIPs in
that directory are ignored when rebuilding.

The metadata directory may also contain `images/` and `captions/` when those are exactly
the directories supplied through `--images-dir` and `--captions-dir`. Other working
directories should be kept outside it. Extra loose images or captions are not selected
unless they occur in the manifest.

No path component of these directories may be a symbolic link.

The output directory must not already exist, its parent must already exist, and it
must be separate from the input directories. The command checks the selected image
and caption contents against the manifest, packages those files, and regenerates
archive metadata and the checksum list. It verifies the staged deposit before moving
it into the output directory. Source files are not modified, and withheld images are
not distributed. You can repeat `verify-deposit` on the output before uploading it as
a new deposit.

Repacking preserves image and caption contents. The ZIP bytes and their checksums can
differ from those of the deposited archives because archive metadata or compression
can differ. Use the regenerated summary and checksum list together with the rebuilt
archives.

## Relationship to the other commands

`export` and `check` operate on the output of a pipeline run, whose format is
specified in [OUTPUTS.md](OUTPUTS.md). That format includes `MANIFEST.json`,
`CHECKS.json`, `case_pair_citations.json`, `image_splits.json` and
`images_part_NNN.zip`. Those commands are strict about their own layout.

`verify-deposit` and `package-deposit` operate on the Zenodo layout shown here.

For retrieval, the public deposit contains 86,825 images and withholds 68 of the
86,893 identifiers retained in the annotations. Checking or repackaging the public
files does not restore those images. Follow the instructions of the `pmc-pair-retrieval`
repository for `--allow-missing-images`; training and image evaluation on the public subset
need not reproduce the numbers computed with all 86,893 images. Its saved-result reporting
commands do not require the withheld image files.
