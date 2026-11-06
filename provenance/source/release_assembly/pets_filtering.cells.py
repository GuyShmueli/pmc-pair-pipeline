# --- cell 0 (animal heuristic over updated-run pairs)
from pathlib import Path
from functools import lru_cache
import copy
import json
import re

from lxml import etree

try:
    from tqdm.auto import tqdm
except Exception:
    def tqdm(x, **kwargs):
        return x

# --- cell 1 (animal rule and screen; animal heuristic over updated-run pairs)
def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


output_dir = Path("<DATA_ROOT>/repro_positive_pairs_pipeline/outputs/postprocessed")

positive_pairs_by_bucket = load_json(output_dir / "positive_pairs_by_bucket.json")

BASE_DIR = Path("<DATA_ROOT>/new_data")

# --- cell 2 (animal heuristic; animal rule and screen; animal heuristic over updated-run pairs)
output_dir = Path(output_dir)
output_dir.mkdir(parents=True, exist_ok=True)

# False = dogs/cats-focused veterinary filter
# True  = broader non-human veterinary filter (horse/rabbit/bovine/etc.)
STRICT_NON_HUMAN = False

# --------------------------
# Regex configuration
# --------------------------

DOG_EXCLUSIONS = [
    re.compile(r"\bdog[- ]ear(s)?\b", re.I),
    re.compile(r"\bdog\s+bite(s)?\b", re.I),
    re.compile(r"\bdog\s+attack(s|ed)?\b", re.I),
]

CANINE_EXCLUSIONS = [
    re.compile(r"\bcanine\s+(fossa|space|eminence|tooth|teeth|root|roots|retraction|guidance)\b", re.I),
    re.compile(r"\b(maxillary|mandibular|impacted)\s+canine\b", re.I),
    re.compile(r"\bcanine\s+to\s+canine\b", re.I),
]

CAT_EXCLUSIONS = [
    re.compile(r"\bcat\s+scan\b", re.I),
    re.compile(r"\bcomputed\s+axial\s+tomography\b", re.I),
]

# Companion-animal signals
PET_PATTERNS = {
    # dog / canine
    "dogs_plural": re.compile(r"\bdogs\b", re.I),
    "dog_phrase": re.compile(
        r"\b(?:in|of|from|with|on)\s+(?:(?:a|an|the|one|two|\d+)\s+)?(?:\w+\s+){0,3}dog\b",
        re.I,
    ),
    "dog_subject": re.compile(
        r"\bdog\s+(?:with|present(?:ed|ing)?|underwent|had|was|were|showed|showing|diagnosed|treated|suffering)\b",
        re.I,
    ),
    "puppy": re.compile(r"\bpupp(?:y|ies)\b", re.I),
    "canine": re.compile(r"\bcanines?\b", re.I),

    # cat / feline
    "cats_plural": re.compile(r"\bcats\b", re.I),
    "cat_phrase": re.compile(
        r"\b(?:in|of|from|with|on)\s+(?:(?:a|an|the|one|two|\d+)\s+)?(?:\w+\s+){0,3}cat\b",
        re.I,
    ),
    "cat_subject": re.compile(
        r"\bcat\s+(?:with|present(?:ed|ing)?|underwent|had|was|were|showed|showing|diagnosed|treated|suffering)\b",
        re.I,
    ),
    "feline": re.compile(r"\bfelines?\b", re.I),
    "kitten": re.compile(r"\bkittens?\b", re.I),
    "domestic_cat": re.compile(r"\bdomestic\s+(short|long)hair\b|\bdomestic\s+cat\b", re.I),

    # common pet breed names
    "breed": re.compile(
        r"\b(labrador|retriever|bulldog|beagle|poodle|terrier|dachshund|rottweiler|"
        r"doberman|boxer|german shepherd|shih tzu|persian|siamese|maine coon)\b",
        re.I,
    ),
}

# Optional broader non-human filter
NON_HUMAN_EXTRA_PATTERNS = {
    "equine": re.compile(r"\bequine\b|\bhorses?\b|\bpony\b|\bfoal\b|\bmare\b|\bstallion\b", re.I),
    "bovine": re.compile(r"\bbovine\b|\bcattle\b|\bcows?\b|\bcalf\b|\bcalves\b", re.I),
    "ovine": re.compile(r"\bovine\b|\bsheep\b|\blamb\b", re.I),
    "caprine": re.compile(r"\bcaprine\b|\bgoats?\b", re.I),
    "porcine": re.compile(r"\bporcine\b|\bpigs?\b|\bswine\b", re.I),
    "rabbit": re.compile(r"\brabbits?\b", re.I),
    "ferret": re.compile(r"\bferrets?\b", re.I),
    "avian": re.compile(r"\bavian\b|\bbirds?\b|\bparrots?\b", re.I),
}

VET_CONTEXT_PATTERNS = {
    "veterinary": re.compile(r"\bveterinar(?:y|ian)\b", re.I),
    "case_report": re.compile(r"\bcase\s+report\b|\bcase\s+series\b", re.I),
}

def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def _matches_any(pattern_dict, text: str) -> list[str]:
    hits = []
    for name, pat in pattern_dict.items():
        if pat.search(text):
            hits.append(name)
    return hits

def _has_any(exclusion_patterns, text: str) -> bool:
    return any(p.search(text) for p in exclusion_patterns)

# --------------------------
# XML parsing
# --------------------------

@lru_cache(maxsize=None)
def uid_to_nxml_path_cached(uid: str, base_dir_str: str) -> str:
    base_dir = Path(base_dir_str)
    puid = uid.split("_")[0]  # "<ARTICLE_ID>" from "<ARTICLE_ID>_xxx"
    dir_path = base_dir / f"PMC{puid}" / f"{puid}_1"

    if not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    nxml_files = sorted(dir_path.glob("*.nxml"))
    if not nxml_files:
        nxml_files = sorted(dir_path.rglob("*.nxml"))

    if not nxml_files:
        raise FileNotFoundError(f"No .nxml files found under: {dir_path}")

    return str(nxml_files[0])

@lru_cache(maxsize=None)
def parse_article_meta(uid: str, base_dir_str: str) -> dict:
    nxml_path = uid_to_nxml_path_cached(uid, base_dir_str)

    parser = etree.XMLParser(recover=True)
    tree = etree.parse(nxml_path, parser)
    root = tree.getroot()

    def first_text(xpath_expr: str) -> str | None:
        elems = root.xpath(xpath_expr)
        if not elems:
            return None
        elem = elems[0]
        txt = " ".join(elem.itertext()).strip() if hasattr(elem, "itertext") else str(elem).strip()
        return txt or None

    pmid_elems = root.xpath('//*[local-name()="article-id"][@pub-id-type="pmid"]')
    pmid = pmid_elems[0].text.strip() if pmid_elems and pmid_elems[0].text else None

    title = first_text('//*[local-name()="title-group"]//*[local-name()="article-title"]')
    if not title:
        title = first_text('//*[local-name()="article-title"]')
    title = _normalize_ws(title or "")

    abstract_elems = root.xpath('//*[local-name()="abstract"]')
    abstract = _normalize_ws(
        " ".join(" ".join(elem.itertext()).strip() for elem in abstract_elems if elem is not None)
    )

    journal_title = first_text('//*[local-name()="journal-title"]') or ""
    journal_title = _normalize_ws(journal_title)

    return {
        "uid": uid,
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "journal_title": journal_title,
        "nxml_path": nxml_path,
    }

# --------------------------
# Heuristic filter
# --------------------------

def detect_pet_or_vet_case(meta: dict, strict_non_human: bool = False) -> tuple[bool, list[str]]:
    """
    Heuristic:
      - Any strong pet/vet signal in the title => filter
      - Pet signal in abstract + vet context/journal => filter
      - Multiple pet signals in abstract => filter
    """
    title = (meta.get("title") or "").lower()
    abstract = (meta.get("abstract") or "").lower()
    journal = (meta.get("journal_title") or "").lower()

    title_hits = []
    abstract_hits = []
    context_hits = []

    # ---- title hits ----
    if PET_PATTERNS["dogs_plural"].search(title):
        title_hits.append("title:dogs_plural")
    if PET_PATTERNS["dog_phrase"].search(title):
        title_hits.append("title:dog_phrase")
    if PET_PATTERNS["dog_subject"].search(title) and not _has_any(DOG_EXCLUSIONS, title):
        title_hits.append("title:dog_subject")
    if PET_PATTERNS["puppy"].search(title):
        title_hits.append("title:puppy")
    if PET_PATTERNS["canine"].search(title) and not _has_any(CANINE_EXCLUSIONS, title):
        title_hits.append("title:canine")

    if PET_PATTERNS["cats_plural"].search(title):
        title_hits.append("title:cats_plural")
    if PET_PATTERNS["cat_phrase"].search(title) and not _has_any(CAT_EXCLUSIONS, title):
        title_hits.append("title:cat_phrase")
    if PET_PATTERNS["cat_subject"].search(title) and not _has_any(CAT_EXCLUSIONS, title):
        title_hits.append("title:cat_subject")
    if PET_PATTERNS["feline"].search(title):
        title_hits.append("title:feline")
    if PET_PATTERNS["kitten"].search(title):
        title_hits.append("title:kitten")
    if PET_PATTERNS["domestic_cat"].search(title):
        title_hits.append("title:domestic_cat")
    if PET_PATTERNS["breed"].search(title):
        title_hits.append("title:breed")

    # ---- abstract hits ----
    if PET_PATTERNS["dogs_plural"].search(abstract):
        abstract_hits.append("abstract:dogs_plural")
    if PET_PATTERNS["dog_phrase"].search(abstract):
        abstract_hits.append("abstract:dog_phrase")
    if PET_PATTERNS["dog_subject"].search(abstract) and not _has_any(DOG_EXCLUSIONS, abstract):
        abstract_hits.append("abstract:dog_subject")
    if PET_PATTERNS["puppy"].search(abstract):
        abstract_hits.append("abstract:puppy")
    if PET_PATTERNS["canine"].search(abstract) and not _has_any(CANINE_EXCLUSIONS, abstract):
        abstract_hits.append("abstract:canine")

    if PET_PATTERNS["cats_plural"].search(abstract):
        abstract_hits.append("abstract:cats_plural")
    if PET_PATTERNS["cat_phrase"].search(abstract) and not _has_any(CAT_EXCLUSIONS, abstract):
        abstract_hits.append("abstract:cat_phrase")
    if PET_PATTERNS["cat_subject"].search(abstract) and not _has_any(CAT_EXCLUSIONS, abstract):
        abstract_hits.append("abstract:cat_subject")
    if PET_PATTERNS["feline"].search(abstract):
        abstract_hits.append("abstract:feline")
    if PET_PATTERNS["kitten"].search(abstract):
        abstract_hits.append("abstract:kitten")
    if PET_PATTERNS["domestic_cat"].search(abstract):
        abstract_hits.append("abstract:domestic_cat")
    if PET_PATTERNS["breed"].search(abstract):
        abstract_hits.append("abstract:breed")

    # ---- optional broader non-human filter ----
    if strict_non_human:
        title_hits.extend([f"title:{x}" for x in _matches_any(NON_HUMAN_EXTRA_PATTERNS, title)])
        abstract_hits.extend([f"abstract:{x}" for x in _matches_any(NON_HUMAN_EXTRA_PATTERNS, abstract)])

    # ---- context hits ----
    merged = f"{title} {abstract}"
    context_hits.extend([f"title_or_abstract:{x}" for x in _matches_any(VET_CONTEXT_PATTERNS, merged)])
    if "veterinary" in journal:
        context_hits.append("journal:veterinary")

    reasons = sorted(set(title_hits + context_hits + abstract_hits))

    should_filter = (
        bool(title_hits) or
        (bool(abstract_hits) and bool(context_hits)) or
        (len(abstract_hits) >= 2)
    )

    return should_filter, reasons

def save_json(obj, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --------------------------
# Main pass over buckets
# --------------------------

filtered_out_records = []
kept_pairs_by_bucket = copy.deepcopy(positive_pairs_by_bucket)

summary = {
    "strict_non_human": STRICT_NON_HUMAN,
    "total_pairs_seen": 0,
    "total_pairs_filtered_out": 0,
    "total_pairs_kept": 0,
    "errors": [],
    "by_bucket": {},
}

for bucket_name in tqdm(list(positive_pairs_by_bucket.keys()), desc="Filtering buckets"):
    bucket_payload = positive_pairs_by_bucket[bucket_name]
    pairs_clean = bucket_payload.get("pairs_clean", [])

    kept_pairs = []
    filtered_here = 0
    kept_here = 0

    for pair_idx, pair in enumerate(tqdm(pairs_clean, desc=f"  {bucket_name}", leave=False)):
        summary["total_pairs_seen"] += 1

        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            kept_pairs.append(pair)
            kept_here += 1
            summary["total_pairs_kept"] += 1
            summary["errors"].append({
                "bucket": bucket_name,
                "pair_index": pair_idx,
                "pair": pair,
                "error": "Malformed pair; expected length-2 list/tuple",
            })
            continue

        uidA, uidB = pair[0], pair[1]

        try:
            metaA = parse_article_meta(str(uidA), str(BASE_DIR))
            metaB = parse_article_meta(str(uidB), str(BASE_DIR))
        except Exception as e:
            kept_pairs.append(pair)
            kept_here += 1
            summary["total_pairs_kept"] += 1
            summary["errors"].append({
                "bucket": bucket_name,
                "pair_index": pair_idx,
                "pair": list(pair),
                "error": repr(e),
            })
            continue

        filterA, reasonsA = detect_pet_or_vet_case(metaA, strict_non_human=STRICT_NON_HUMAN)
        filterB, reasonsB = detect_pet_or_vet_case(metaB, strict_non_human=STRICT_NON_HUMAN)

        if filterA or filterB:
            filtered_here += 1
            summary["total_pairs_filtered_out"] += 1

            filtered_out_records.append({
                "bucket": bucket_name,
                "pair_index_in_bucket": pair_idx,
                "pair": list(pair),
                "flagged_by": "both" if (filterA and filterB) else ("A" if filterA else "B"),
                "docA": {
                    "uid": uidA,
                    "pmid": metaA.get("pmid"),
                    "title": metaA.get("title"),
                    "journal_title": metaA.get("journal_title"),
                    "reasons": reasonsA,
                    "nxml_path": metaA.get("nxml_path"),
                },
                "docB": {
                    "uid": uidB,
                    "pmid": metaB.get("pmid"),
                    "title": metaB.get("title"),
                    "journal_title": metaB.get("journal_title"),
                    "reasons": reasonsB,
                    "nxml_path": metaB.get("nxml_path"),
                },
            })
        else:
            kept_pairs.append(pair)
            kept_here += 1
            summary["total_pairs_kept"] += 1

    kept_pairs_by_bucket[bucket_name]["pairs_clean"] = kept_pairs
    summary["by_bucket"][bucket_name] = {
        "original_pairs": len(pairs_clean),
        "filtered_out": filtered_here,
        "kept": kept_here,
    }

filtered_out_json = {
    "summary": summary,
    "filtered_pairs": filtered_out_records,
}

filtered_out_path = output_dir / "positive_pairs_pet_filtered_out.json"
kept_pairs_path = output_dir / "positive_pairs_by_bucket_no_pets.json"

save_json(filtered_out_json, filtered_out_path)
save_json(kept_pairs_by_bucket, kept_pairs_path)

print("Done.")
print(f"Filtered-out JSON: {filtered_out_path}")
print(f"Kept-pairs JSON : {kept_pairs_path}")
print()
print(json.dumps(summary["by_bucket"], indent=2))
print()
print(f"Total seen       : {summary['total_pairs_seen']}")
print(f"Filtered out     : {summary['total_pairs_filtered_out']}")
print(f"Kept             : {summary['total_pairs_kept']}")
print(f"Errors kept-as-is: {len(summary['errors'])}")

# Preview a few filtered examples
for rec in filtered_out_records[:10]:
    print("-" * 100)
    print(f"[{rec['bucket']}] pair={rec['pair']} flagged_by={rec['flagged_by']}")
    print("A:", rec["docA"]["title"])
    print("   reasons:", rec["docA"]["reasons"])
    print("B:", rec["docB"]["title"])
    print("   reasons:", rec["docB"]["reasons"])

# --- cell 6 (apply blacklist)
filtered_out_path = output_dir / "positive_pairs_pet_filtered_out.json"

f = load_json(filtered_out_path)

# --- cell 11 (blacklist application)
import json

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# Your filtered-out pairs
f_list = [p["pair"] for p in f["filtered_pairs"]]

# All pairs
pairs2 = load_json("<DATA_ROOT>/prepared_pairmed_inputs/broad_no_path_endo/pairs.json")

f_set = {tuple(sorted(pair)) for pair in f_list}
pairs2_no_pets = [pair for pair in pairs2 if tuple(sorted(pair)) not in f_set]

# Save
out_path = "<DATA_ROOT>/prepared_pairmed_inputs/broad_no_path_endo/pairs_no_pets.json"
save_json(pairs2_no_pets, out_path)

print(f"Original pairs2: {len(pairs2)}")
print(f"Filtered out:    {len(pairs2) - len(pairs2_no_pets)}")
print(f"Remaining:       {len(pairs2_no_pets)}")
print(f"Saved to:        {out_path}")

# --- cell 12 (blacklist application; apply blacklist)
import json
from pathlib import Path

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def canon_pair(pair):
    # Makes [A,B] and [B,A] identical
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError(f"Expected a pair of length 2, got: {pair}")
    return tuple(sorted(pair))

# Filtered-out pairs from your audit JSON
f_list = [p["pair"] for p in f["filtered_pairs"]]
f_set = {canon_pair(pair) for pair in f_list}

# Original aligned files
pairs_path = Path("<DATA_ROOT>/prepared_pairmed_inputs/broad_no_path_endo/pairs.json")
texts_path = Path("<DATA_ROOT>/prepared_pairmed_inputs/broad_no_path_endo/texts.json")

pairs2 = load_json(pairs_path)
texts2 = load_json(texts_path)

if len(pairs2) != len(texts2):
    raise ValueError(
        f"Length mismatch: len(pairs2)={len(pairs2)} but len(texts2)={len(texts2)}"
    )

pairs2_no_pets = []
texts2_no_pets = []

pairs2_removed = []
texts2_removed = []

for pair, txt in zip(pairs2, texts2):
    if canon_pair(pair) in f_set:
        pairs2_removed.append(pair)
        texts2_removed.append(txt)
    else:
        pairs2_no_pets.append(pair)
        texts2_no_pets.append(txt)

# Save kept
pairs_out_path = pairs_path.with_name("pairs_no_pets.json")
texts_out_path = texts_path.with_name("texts_no_pets.json")

save_json(pairs2_no_pets, pairs_out_path)
save_json(texts2_no_pets, texts_out_path)

# Optional: save removed too, for auditing
pairs_removed_path = pairs_path.with_name("pairs_removed_pets.json")
texts_removed_path = texts_path.with_name("texts_removed_pets.json")

save_json(pairs2_removed, pairs_removed_path)
save_json(texts2_removed, texts_removed_path)

print(f"Original pairs:   {len(pairs2)}")
print(f"Original texts:   {len(texts2)}")
print(f"Removed pairs:    {len(pairs2_removed)}")
print(f"Removed texts:    {len(texts2_removed)}")
print(f"Remaining pairs:  {len(pairs2_no_pets)}")
print(f"Remaining texts:  {len(texts2_no_pets)}")
print(f"Saved pairs to:   {pairs_out_path}")
print(f"Saved texts to:   {texts_out_path}")
print(f"Saved removed pairs to: {pairs_removed_path}")
print(f"Saved removed texts to: {texts_removed_path}")
