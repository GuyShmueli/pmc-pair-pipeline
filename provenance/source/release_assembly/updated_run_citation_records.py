from pathlib import Path
import json
import os
import re
import tempfile

outdir = Path('<DATA_ROOT>/repro_positive_pairs_pipeline/outputs')
records_path = outdir / '03_citation_records.json'
first_path = outdir / 'fir_citation_response.json'
second_path = outdir / 'sec_citation_response.json'
target = outdir / 'case_pair_citations.json'

if target.exists():
    raise FileExistsError(f'Refusing to overwrite existing output: {target}')

with records_path.open('r', encoding='utf-8') as f:
    records = json.load(f)
with first_path.open('r', encoding='utf-8') as f:
    reasons_first = json.load(f)
with second_path.open('r', encoding='utf-8') as f:
    reasons_second = json.load(f)

reasons = reasons_first + reasons_second
if len(records) != len(reasons):
    raise ValueError(f'Length mismatch: {len(records)} citation records vs {len(reasons)} reasons')

pmcid_pattern = re.compile(r'(?:^|/)PMC(\d+)(?:/|$)')

def extract_pmcid(path_value, *, row, field):
    match = pmcid_pattern.search(str(path_value))
    if not match:
        raise ValueError(f'Row {row}: cannot extract PMCID from {field}={path_value!r}')
    return f'PMC{match.group(1)}'

fd, temp_name = tempfile.mkstemp(
    dir=outdir,
    prefix='.case_pair_citations.',
    suffix='.tmp',
    text=True,
)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        out.write('[\n')
        for position, (record, reason) in enumerate(zip(records, reasons)):
            paragraphs = record.get('citation_paragraphs', [])
            if paragraphs is None:
                paragraphs = []
            if not isinstance(paragraphs, list) or not all(isinstance(p, str) for p in paragraphs):
                raise TypeError(f'Row {position}: citation_paragraphs must be list[str]')
            if not isinstance(reason, str) or not reason.strip():
                raise TypeError(f'Row {position}: citation_reason must be a nonempty string')

            item = {
                'citing_case': extract_pmcid(record.get('citing_file'), row=position, field='citing_file'),
                'cited_case': extract_pmcid(record.get('cited_file'), row=position, field='cited_file'),
                'extracted_citation': '\n\n'.join(p.strip() for p in paragraphs if p.strip()),
                'citation_reason': reason,
            }
            if position:
                out.write(',\n')
            json.dump(item, out, ensure_ascii=False, indent=2)
        out.write('\n]\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp_name, target)
except Exception:
    try:
        os.unlink(temp_name)
    except FileNotFoundError:
        pass
    raise

print(target)
print(f'rows={len(records)}')
print(f'bytes={target.stat().st_size}')
