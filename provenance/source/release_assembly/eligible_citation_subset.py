import ast
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

base = Path('<DATA_ROOT>')
output = base / 'zenodo_dataset/case_pair_citations_eligible.json'
manifest_path = output.with_suffix('.manifest.json')
assert not output.exists(), f'Output already exists: {output}'
assert not manifest_path.exists(), f'Manifest already exists: {manifest_path}'
paths = {
    'source': base / 'zenodo_dataset/case_pair_citations.json',
    'original_matching_pairs': base / '<DATA_ROOT>/matching_uids.json',
    'original_citation_indices': base / '<DATA_ROOT>/citation_valid_indices_dict.json',
    'original_description_ready_indices': base / '<DATA_ROOT>/common_indices.json',
    'original_saved_requests': base / '<DATA_ROOT>/generate_positives.jsonl',
    'compound_saved_requests': base / '<DATA_ROOT>/compound_batch_reqs/compound_positives_req.jsonl',
    'compound_xml_path_pairs': base / '<DATA_ROOT>/compound_uids_xml_paths.json',
    'compound_citation_indices': base / '<DATA_ROOT>/compound_citation_valid_indices.json',
    'compound_summary_indices': base / '<DATA_ROOT>/compound_summaries_valid_indices.json',
    'newer_citation_records': base / '<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/case_pair_citations.json',
    'saved_animal_image_pair_exclusions': base / '<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/postprocessed/positive_pairs_pet_filtered_out.json',
}

def file_info(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'path': str(p), 'size_bytes': p.stat().st_size, 'sha256': h.hexdigest()}

before = {name: file_info(p) for name, p in paths.items()}

def read(name):
    with paths[name].open(encoding='utf-8') as stream:
        return json.load(stream)

def canonical(pair):
    assert len(pair) == 2 and pair[0] != pair[1], pair
    assert all(re.fullmatch(r'[0-9]+-1', uid) for uid in pair), pair
    return tuple(sorted(pair))

def record_key(record):
    pair = []
    for field in ('citing_case', 'cited_case'):
        m = re.fullmatch(r'PMC([0-9]+)', record[field])
        assert m, (field, record[field])
        pair.append(m.group(1) + '-1')
    return canonical(pair)

def image_case(image_id):
    m = re.fullmatch(r'([0-9]+)_([0-9]+)_(.+)', image_id)
    assert m, image_id
    assert m.group(2) == '1', image_id
    return m.group(1) + '-' + m.group(2)

def request_keys(name):
    result = set()
    n = 0
    with paths[name].open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            contents = [message['content'] for message in row['body']['messages']
                        if message['role'] == 'user' and '### IMAGE CAPTIONS (MULTIPLE PAIRS)' in message['content']]
            assert len(contents) == 1
            tail = contents[0].split('### IMAGE CAPTIONS (MULTIPLE PAIRS)', 1)[1].strip()
            nodes = ast.parse(tail, mode='exec').body
            assert len(nodes) == 2 and all(isinstance(node, ast.Expr) for node in nodes)
            endpoints = []
            for node in nodes:
                captions = ast.literal_eval(node.value)
                assert isinstance(captions, dict) and captions
                assert all(isinstance(v, str) and v.strip() for v in captions.values())
                uids = {image_case(image_id) for image_id in captions}
                assert len(uids) == 1
                endpoints.append(next(iter(uids)))
            key = canonical(endpoints)
            assert key not in result, (name, key)
            result.add(key)
            n += 1
    assert len(result) == n
    return result

def key_hash(keys):
    serialized = ''.join('|'.join(key) + '\n' for key in sorted(keys))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

records = read('source')
assert isinstance(records, list) and len(records) == 125083
keys = [record_key(record) for record in records]
source_keys = set(keys)
assert len(source_keys) == 125083
assert all(set(record) == {'citing_case', 'cited_case', 'extracted_citation', 'citation_reason'} for record in records)
assert all(isinstance(value, str) for record in records for value in record.values())

matching = read('original_matching_pairs')
citation_indices = read('original_citation_indices')
common = read('original_description_ready_indices')
original_citations = {canonical(matching[int(i)]) for i in citation_indices}
original_ready = {canonical(matching[i]) for i in common}
assert len(original_citations) == 31080 and len(original_ready) == 31002
assert original_ready <= original_citations
original_requests = request_keys('original_saved_requests')
compound_requests = request_keys('compound_saved_requests')
assert len(original_requests) == 27519 and len(compound_requests) == 13445
assert original_requests <= original_ready

compound_paths = read('compound_xml_path_pairs')
compound_indices = read('compound_citation_indices')
assert set(compound_indices) <= set(read('compound_summary_indices'))
compound_citations = {canonical([Path(p).parent.name.replace('_', '-') for p in compound_paths[i]]) for i in compound_indices}
assert compound_citations == compound_requests
assert len(original_citations & compound_citations) == 5672
assert len(original_requests & compound_requests) == 4829
newer_records = read('newer_citation_records')
newer_keys = {record_key(record) for record in newer_records}
assert len(newer_records) == len(newer_keys) == 86230
assert not (newer_keys & (original_citations | compound_citations))
assert source_keys == original_citations | compound_citations | newer_keys
del newer_records

figure = original_ready - original_requests - compound_requests - newer_keys
description = original_citations - original_ready - compound_citations - newer_keys
animal_rows = read('saved_animal_image_pair_exclusions')['filtered_pairs']
assert len(animal_rows) == 774
animal = {canonical([image_case(image_id) for image_id in row['pair']]) for row in animal_rows}
groups = {'figure_screening': figure, 'known_animal_association': animal, 'incomplete_case_description': description}
assert [len(group) for group in groups.values()] == [2640, 416, 78]
assert all(group <= source_keys for group in groups.values())
assert not (figure & animal or figure & description or animal & description)
assert len((original_ready - original_requests) & compound_requests) == 843
excluded = figure | animal | description
eligible = source_keys - excluded
assert len(excluded) == 3134 and len(eligible) == 121949
assert eligible == (original_requests | compound_requests | newer_keys) - animal
expected_hashes = {
    'source': 'f33ae98cd277505576a95e6209c8cc656618562a42c49fa4ad2645caf0adae1b',
    'figure_screening': '02134bbb4adf9067631feb54d4db713e6d47e49ca0f1a0b13304bec126553390',
    'known_animal_association': 'dce91dbabeca3b3af976d0793d2202467c858998c68bf9f06699bc8552a23922',
    'incomplete_case_description': '2ab0117d773ea6bc51e9191b049ca4c76927be7d38985b892a8de174832a67ad',
    'eligible': '456cf0df88571c3fcf4ecc75b56f7c6e890b7e9c76deaec165a6c8c488425b17',
}
assert key_hash(source_keys) == expected_hashes['source']
assert key_hash(eligible) == expected_hashes['eligible']
assert all(key_hash(group) == expected_hashes[name] for name, group in groups.items())
retained = [record for record, key in zip(records, keys) if key in eligible]
assert len(retained) == 121949
assert sum(not record['extracted_citation'].strip() for record in records) == 887
assert sum(not record['extracted_citation'].strip() for record in retained) == 863
print(json.dumps({'verified_counts': {name: len(group) for name, group in groups.items()}, 'retained': len(retained), 'retained_empty_passages': 863, 'independent_key_hash_match': True}), flush=True)

# Create only the requested derived file and its audit manifest; never overwrite inputs.
with output.open('x', encoding='utf-8') as stream:
    json.dump(retained, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
with output.open(encoding='utf-8') as stream:
    read_back = json.load(stream)
assert read_back == retained
assert [record_key(record) for record in read_back] == [key for key in keys if key in eligible]
assert len({record_key(record) for record in read_back}) == 121949
output_info = file_info(output)
del read_back
assert before == {name: file_info(p) for name, p in paths.items()}, 'An input changed during export'

reason_by_key = {key: name for name, group in groups.items() for key in group}
manifest = {
    'created_at': datetime.now(ZoneInfo('Asia/Jerusalem')).isoformat(),
    'purpose': 'Exact subset of the user-specified citation source corresponding to the reconstructed 121,949 eligible unique case-record pairs.',
    'source': before['source'],
    'output': output_info,
    'counts': {'input_records': 125083, 'input_unique_unordered_case_pairs': 125083,
               'figure_screening_excluded': 2640, 'after_figure_screening': 122443,
               'known_animal_association_excluded': 416, 'after_animal_exclusion': 122027,
               'incomplete_case_description_excluded': 78, 'total_excluded': 3134,
               'retained_records': 121949, 'retained_unique_unordered_case_pairs': 121949,
               'input_empty_citation_passages': 887, 'retained_empty_citation_passages': 863},
    'preservation': 'Every retained record preserves all source fields, values, citation direction and relative list order. No identifier or content is rewritten.',
    'pair_matching': 'For set membership only, map PMC<n> to case UID <n>-1 and sort the two endpoint UIDs lexicographically. Saved case and image identifiers used in the joins all have case index 1. This does not establish that each article describes only one actual patient.',
    'derivation': {
        'original_citation_pairs': 'matching_uids[int(index)] for keys of citation_valid_indices_dict: 31,080 unique pairs.',
        'original_description_ready_pairs': 'matching_uids[index] for common_indices: 31,002 unique pairs.',
        'saved_request_pairs': 'Parse the two literal caption dictionaries following the IMAGE CAPTIONS heading in each saved request; derive one case UID per dictionary from its image IDs. The request custom_id is not used as a candidate index.',
        'figure_screening': '31,002 original description-ready pairs minus 27,519 original saved request pairs leaves 3,483; 843 are covered by compound requests, leaving 2,640 net exclusions. No overlap with the newer route.',
        'known_animal_association': 'Project the 774 saved animal-associated image-pair exclusions to 416 unique unordered case pairs. Apply only this known exclusion set, without rerunning a classifier.',
        'incomplete_case_description': '31,080 original citation-covered pairs minus 31,002 original description-ready pairs: 78, with no rescue by compound or newer records.',
        'cross_check': 'Source keys equal the union of 31,080 original, 13,445 compound and 86,230 newer pairs, with 5,672 original/compound overlaps. Final keys also equal (27,519 original requests union 13,445 compound requests union 86,230 newer pairs) minus 416 animal-associated pairs.'
    },
    'notes': [
        'The 34,305 candidate pairs absent from the 125,083-record citation resource are already absent from this input; they are not subtracted again.',
        'An empty extracted_citation field is not an exclusion criterion. Of the 887 such source records, 23 belong to the figure-screening exclusions, 1 to the animal-associated exclusions, and 863 are retained.',
        'Counts reconstruct saved outcomes under the requested case-level animal-exclusion interpretation. The known blacklist does not establish comprehensive human/animal screening.',
        'Only saved files were read. No image, citation, annotation or classification pipeline was rerun; no API or network calls were made.'
    ],
    'input_files': before,
    'canonical_pair_key_hash_encoding': "Lexicographically sorted unordered UID pairs, id1|id2 per line, UTF-8, including final newline.",
    'canonical_pair_key_sha256': expected_hashes,
    'verification': {'all_exclusions_in_source': True, 'exclusion_groups_mutually_disjoint': True,
                     'independent_reconstruction_key_hashes_match': True,
                     'read_back_equals_exact_source_subset': True, 'source_order_and_all_fields_preserved': True,
                     'all_input_sha256_hashes_unchanged': True},
    'excluded_records': [{'source_index_zero_based': i, 'citing_case': record['citing_case'],
                          'cited_case': record['cited_case'], 'case_pair_key': list(key),
                          'reason': reason_by_key[key]}
                         for i, (record, key) in enumerate(zip(records, keys)) if key in excluded],
}
assert sum(not record['extracted_citation'].strip() for record, key in zip(records, keys) if key in figure) == 23
assert sum(not record['extracted_citation'].strip() for record, key in zip(records, keys) if key in animal) == 1
with manifest_path.open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
with manifest_path.open(encoding='utf-8') as stream:
    assert json.load(stream) == manifest
print(json.dumps({'created': output_info, 'manifest': str(manifest_path), 'source_unchanged': True, 'all_checks_passed': True}, indent=2), flush=True)
