"""Exclusion of animal case reports.

Animal case reports are recognized with keyword rules on the title, abstract and journal
title. With `strict_non_human: false` (default) the rules target dog and cat case
reports. Exclusion phrases for human contexts ("dog bite", "CAT scan", "canine teeth")
cancel only the signals listed in EXCLUSIONS_FOR; "dog bite" does not cancel the
"from a dog" pattern, so the title "Infection from a dog bite" is flagged.
`strict_non_human: true` also flags horses, cattle, sheep, goats, pigs, rabbits, ferrets
and birds; it then also matches human reports that mention, for example, "calf pain",
"bird's beak sign" or "rabbit antithymocyte globulin".

Decision rule for one article:
  * any animal signal in the title, or
  * a signal in the abstract together with veterinary or case-report context, or
  * two or more different signals in the abstract.
"""

from __future__ import annotations

import re

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
PET_PATTERNS = {
    "dogs_plural": re.compile(r"\bdogs\b", re.I),
    "dog_phrase": re.compile(
        r"\b(?:in|of|from|with|on)\s+(?:(?:a|an|the|one|two|\d+)\s+)?(?:\w+\s+){0,3}dog\b", re.I),
    "dog_subject": re.compile(
        r"\bdog\s+(?:with|present(?:ed|ing)?|underwent|had|was|were|showed|showing|diagnosed|treated|suffering)\b",
        re.I),
    "puppy": re.compile(r"\bpupp(?:y|ies)\b", re.I),
    "canine": re.compile(r"\bcanines?\b", re.I),
    "cats_plural": re.compile(r"\bcats\b", re.I),
    "cat_phrase": re.compile(
        r"\b(?:in|of|from|with|on)\s+(?:(?:a|an|the|one|two|\d+)\s+)?(?:\w+\s+){0,3}cat\b", re.I),
    "cat_subject": re.compile(
        r"\bcat\s+(?:with|present(?:ed|ing)?|underwent|had|was|were|showed|showing|diagnosed|treated|suffering)\b",
        re.I),
    "feline": re.compile(r"\bfelines?\b", re.I),
    "kitten": re.compile(r"\bkittens?\b", re.I),
    "domestic_cat": re.compile(r"\bdomestic\s+(short|long)hair\b|\bdomestic\s+cat\b", re.I),
    "breed": re.compile(
        r"\b(labrador|retriever|bulldog|beagle|poodle|terrier|dachshund|rottweiler|"
        r"doberman|boxer|german shepherd|shih tzu|persian|siamese|maine coon)\b", re.I),
}
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

# Signals that are ignored when an exclusion phrase is present (e.g. "dog bite", "CAT scan").
EXCLUSIONS_FOR = {
    "dog_subject": DOG_EXCLUSIONS,
    "canine": CANINE_EXCLUSIONS,
    "cat_phrase": CAT_EXCLUSIONS,
    "cat_subject": CAT_EXCLUSIONS,
}


def _signals(text, strict_non_human):
    hits = []
    for name, pattern in PET_PATTERNS.items():
        exclusions = EXCLUSIONS_FOR.get(name, [])
        if pattern.search(text) and not any(e.search(text) for e in exclusions):
            hits.append(name)
    if strict_non_human:
        hits += [name for name, pattern in NON_HUMAN_EXTRA_PATTERNS.items() if pattern.search(text)]
    return hits


def is_animal_case(title, abstract, journal_title, strict_non_human=False):
    """Return (flagged, reasons) for one article."""
    title = (title or "").lower()
    abstract = (abstract or "").lower()
    journal = (journal_title or "").lower()

    title_hits = [f"title:{name}" for name in _signals(title, strict_non_human)]
    abstract_hits = [f"abstract:{name}" for name in _signals(abstract, strict_non_human)]
    context_hits = [f"title_or_abstract:{name}" for name, pattern in VET_CONTEXT_PATTERNS.items()
                    if pattern.search(f"{title} {abstract}")]
    if "veterinary" in journal:
        context_hits.append("journal:veterinary")

    flagged = bool(title_hits) or (bool(abstract_hits) and bool(context_hits)) or len(abstract_hits) >= 2
    return flagged, sorted(set(title_hits + abstract_hits + context_hits))
