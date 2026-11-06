"""Reading PMC article XML (JATS).

  * figures: every <fig> in document order, with its first <caption> and <graphic>,
  * case descriptions: sections whose title contains a case-report heading,
  * titles, abstracts, identifiers and reference lists,
  * citation passages: the paragraph or table row around each <xref> to a reference.
"""

from __future__ import annotations

import re

from lxml import etree

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def parse_xml(path):
    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        return etree.parse(str(path), parser)
    except Exception:
        return None


def node_text(element, separator=" "):
    """Text of an element: stripped text pieces joined by `separator`."""
    if element is None:
        return ""
    return separator.join(piece.strip() for piece in element.itertext() if piece.strip())


def normalize_whitespace(text):
    return re.sub(r"\s+", " ", text or "").strip()


def first_descendant(element, name):
    found = element.xpath(f'.//*[local-name()="{name}"]')
    return found[0] if found else None


# ---------------------------------------------------------------- figures

def graphic_href(graphic):
    for key in (XLINK_HREF, "href"):
        if graphic.get(key):
            return graphic.get(key)
    for key, value in graphic.attrib.items():
        if key.lower().endswith(("}href", ":href")) and value:
            return value
    return None


def list_figures(tree):
    """All <fig> elements in document order. `index` is the figure extraction index."""
    figures = []
    for index, fig in enumerate(tree.xpath('//*[local-name()="fig"]'), start=1):
        caption = first_descendant(fig, "caption")
        graphic = first_descendant(fig, "graphic")
        label = fig.xpath('./*[local-name()="label"]')
        figures.append({
            "index": index,
            "xml_id": (fig.get("id") or "").strip(),
            "label": node_text(label[0]) if label else "",
            "caption": node_text(caption) if caption is not None else "",
            "graphic_href": graphic_href(graphic) if graphic is not None else None,
        })
    return figures


# ---------------------------------------------------------------- case description

# Case-report headings: a section title with the word "case" (not "cases" or "showcase"),
# "patient presentation/report/description/summary", or the title "patient".
CASE_HEADING = re.compile(r"\bcase\b|\bpatient (?:presentation|report|description|summary)\b|^patient$")
# paragraph text, leaving out captions and footnotes of figures and tables
NARRATIVE_TEXT_XPATH = ('.//*[local-name()="p"]//text()'
                        '[not(ancestor::*[local-name()="fig" or local-name()="table-wrap"])]')


def section_title(section):
    titles = section.xpath('./*[local-name()="title"]')
    return normalize_whitespace(" ".join(titles[0].itertext())).lower() if titles else ""


def case_description(tree):
    """Paragraph text of the sections with a case-report heading, joined by blank lines.

    A matching section inside another matching section is read only once, as part of its
    parent. Captions are left out: the models receive them separately.
    """
    sections = [s for s in tree.xpath('//*[local-name()="sec"]') if CASE_HEADING.search(section_title(s))]
    selected = set(sections)
    texts, seen = [], set()
    for section in sections:
        if any(ancestor in selected for ancestor in section.iterancestors()):
            continue
        text = normalize_whitespace(" ".join(section.xpath(NARRATIVE_TEXT_XPATH)))
        if text and text not in seen:
            texts.append(text)
            seen.add(text)
    return "\n\n".join(texts)


# ---------------------------------------------------------------- metadata and references

def normalize_identifier(kind, value):
    """Comparable form of a DOI / PMID / PMCID (case, URL prefix and "PMC" prefix removed)."""
    if not value:
        return None
    value = value.strip()
    if kind == "doi":
        value = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.IGNORECASE).lower()
    elif kind == "pmcid":
        value = re.sub(r"^pmc", "", value, flags=re.IGNORECASE)
    return value or None


def _mixed_citation_title(mixed):
    titles = mixed.xpath('.//*[local-name()="article-title"]')
    if titles:
        return " ".join(titles[0].itertext()).strip()
    unwanted = {"string-name", "person-group", "year", "volume", "issue", "fpage", "lpage",
                "pub-id", "edition", "conf-date", "name", "isbn", "editor"}
    parts = []
    for node in mixed.iter():
        if not isinstance(node.tag, str) or etree.QName(node).localname in unwanted:
            continue
        for piece in (node.text, node.tail):
            if piece and piece.strip():
                parts.append(piece.strip())
    return " ".join(parts).strip()


def _reference_title(ref):
    titles = ref.xpath('.//*[local-name()="element-citation"]/*[local-name()="article-title"]')
    if titles:
        return " ".join(titles[0].itertext()).strip()
    mixed = ref.xpath('.//*[local-name()="mixed-citation"]')
    if mixed:
        return _mixed_citation_title(mixed[0])
    comments = ref.xpath('.//*[local-name()="element-citation"]/*[local-name()="comment"]')
    return " ".join(comments[0].itertext()).strip() if comments else ""


def article_metadata(tree):
    root = tree.getroot()

    def article_id(*id_types):
        for id_type in id_types:
            found = root.xpath(f'//*[local-name()="article-id"][@pub-id-type="{id_type}"]')
            if found and found[0].text:
                return found[0].text.strip()
        return None

    titles = root.xpath('//*[local-name()="title-group"]//*[local-name()="article-title"]')
    if not titles:
        titles = root.xpath('//*[local-name()="article-title"]')
    title = "".join(titles[0].itertext()).strip() if titles else ""
    # the animal filter reads the title with its pieces joined by spaces
    title_spaced =normalize_whitespace(" ".join(titles[0].itertext())) if titles else ""

    abstract_parts = [" ".join(a.itertext()).strip() for a in root.xpath('//*[local-name()="abstract"]')]
    abstract = " ".join(part for part in abstract_parts if part).strip()

    journal = root.xpath('//*[local-name()="journal-title"]')

    references = {}
    for ref in root.xpath('//*[local-name()="ref"]'):
        ref_id = ref.get("id")
        if not ref_id:
            continue
        ids = {}
        for kind, id_type in (("doi", "doi"), ("pmid", "pmid"), ("pmcid", "pmc")):
            found = ref.xpath(f'.//*[local-name()="pub-id"][@pub-id-type="{id_type}"]')
            ids[kind] = normalize_identifier(kind, found[0].text) if found and found[0].text else None
        references[ref_id] = {**ids, "title": _reference_title(ref)}

    return {
        "pmid": normalize_identifier("pmid", article_id("pmid")),
        "doi": normalize_identifier("doi", article_id("doi")),
        "pmcid": normalize_identifier("pmcid", article_id("pmc", "pmcid")),
        "title": title,
        "title_spaced": title_spaced,
        "abstract": abstract,
        "journal_title": normalize_whitespace(" ".join(journal[0].itertext())) if journal else "",
        "references": references,
    }


def enclosing(element, name):
    """Nearest ancestor of `element` with the given local name (None if there is none)."""
    element = element.getparent()
    while element is not None and not (isinstance(element.tag, str) and etree.QName(element).localname == name):
        element = element.getparent()
    return element


def citation_passages(tree, ref_id):
    """Passages that cite the reference `ref_id`, in document order, without repeats.

    Passages are found through the <xref> links to the reference. A citation inside a
    table gives its table row (cells separated by " | "), any other citation the
    paragraph that contains it. Citations written as plain text (no <xref>) give no passage.
    """
    passages, seen = [], set()
    for xref in tree.xpath('//*[local-name()="xref"][@ref-type="bibr" or @ref-type="ref"]'):
        if ref_id not in (xref.get("rid") or "").split():
            continue
        row = enclosing(xref, "tr")
        if row is not None:
            cells = row.xpath('./*[local-name()="td" or local-name()="th"]')
            text = " | ".join(normalize_whitespace(node_text(cell)) for cell in cells)
        else:
            paragraph = enclosing(xref, "p")
            if paragraph is None:
                continue
            text = " ".join(paragraph.itertext()).strip()
        if text and text not in seen:
            passages.append(text)
            seen.add(text)
    return passages
