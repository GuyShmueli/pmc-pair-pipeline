"""Citation verification between the two articles of a case pair.

A citation link is confirmed when one article's reference list contains the other
article: DOI, PMID and PMCID are checked in this order, then the normalised title as a
substring of a reference title. A match in either direction confirms the link.
"""

from __future__ import annotations

import re


def fix_apostrophe_spacing(text):
    return re.sub(r"([A-Za-z0-9])'([A-Za-z0-9])", r"\1 ' \2", text or "")


def normalize_title(text):
    text = fix_apostrophe_spacing(text or "").lower()
    text = re.sub(r"[-]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def title_contains(reference_title, cited_title):
    """True if the normalized title of the cited article occurs inside the reference title."""
    cited = normalize_title(cited_title)
    return bool(cited) and cited in normalize_title(reference_title)


def find_citation(citing, cited, title_fallback=True):
    """(reference id, match type) if `citing` lists `cited` in its references, else (None, None).

    `citing` and `cited` are article metadata dicts from jats.article_metadata().
    """
    references = citing["references"]
    for kind in ("doi", "pmid", "pmcid"):
        # When two references share an identifier, the last one wins.
        reverse = {ref[kind]: ref_id for ref_id, ref in references.items() if ref.get(kind)}
        if cited.get(kind) and cited[kind] in reverse:
            return reverse[cited[kind]], kind

    if title_fallback and (cited.get("title") or "").strip():
        for ref_id, ref in references.items():
            if any(ref.get(kind) and ref[kind] == cited.get(kind) for kind in ("pmid", "doi", "pmcid")):
                continue
            if title_contains(ref.get("title") or "", cited["title"]):
                return ref_id, "title_substring"
    return None, None


def verify_citation(case_a, meta_a, case_b, meta_b, title_fallback=True):
    """Check A -> B first, then B -> A. Returns the citing/cited cases or None."""
    for citing_case, citing, cited_case, cited in ((case_a, meta_a, case_b, meta_b),
                                                   (case_b, meta_b, case_a, meta_a)):
        ref_id, match_type = find_citation(citing, cited, title_fallback)
        if ref_id:
            return {"citing_case": citing_case, "cited_case": cited_case,
                    "match_type": match_type, "ref_id": ref_id}
    return None
