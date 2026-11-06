from pathlib import Path
import hashlib
import json
import os
import re
import tempfile

path = Path('<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations.json')
if not path.is_file():
    raise FileNotFoundError(path)

before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
with path.open('r', encoding='utf-8') as f:
    rows = json.load(f)

pattern = re.compile(r'^Reason for Citation:[ \t]*')
changed = 0
for i, row in enumerate(rows):
    reason = row.get('citation_reason')
    if not isinstance(reason, str):
        raise TypeError(f'Row {i}: citation_reason is not a string')
    updated, count = pattern.subn('', reason, count=1)
    if count != 1:
        raise ValueError(f'Row {i}: expected prefix not found')
    if not updated:
        raise ValueError(f'Row {i}: removing prefix produced an empty reason')
    row['citation_reason'] = updated
    changed += 1

fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix='.case_pair_citations.', suffix='.tmp', text=True)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(rows, out, ensure_ascii=False, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp_name, path)
except Exception:
    try:
        os.unlink(temp_name)
    except FileNotFoundError:
        pass
    raise

after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
print(f'rows_updated={changed}')
print(f'before_sha256={before_hash}')
print(f'after_sha256={after_hash}')
print(f'bytes={path.stat().st_size}')
