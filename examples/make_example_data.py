"""Create a small synthetic example for an offline end-to-end run.

Everything written here is invented: articles, patients, images and model responses.
The PMC ids (PMC99000001, ...) are far above the ids in use and do not refer to real
articles. The files mimic the real inputs:

  data/pmc_patients_example.csv   regenerated PMC-Patients table (patient_uid, similar_patients, ...)
  data/pmc_mirror/                folder with the layout of the PMC Cloud Service bucket
  data/llm_responses/*.jsonl      ready-made model outputs, keyed by request id

The cases are chosen so that every filter of the pipeline removes something:
multi-patient article, self link, animal case, missing citation, missing case
section, diagram-only figures, unavailable and non-open-access articles, author
manuscript vs. published version, GIF thumbnails, PNG-only figure, text-heavy figure.
Citations appear in paragraphs, in a table row and as plain text without a link.

Usage:  python examples/make_example_data.py [output folder, default examples/data]
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFilter, ImageFont

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"


# ------------------------------------------------------------------ images

def scan_image(seed, kind):
    """Dark, scan-like grayscale picture (passes the diagram screen)."""
    rng = random.Random(seed)
    image = Image.new("L", (512, 512), 18)
    draw = ImageDraw.Draw(image)
    if kind == "chest":
        draw.ellipse((70, 60, 240, 460), fill=55)
        draw.ellipse((272, 60, 442, 460), fill=55)
        draw.ellipse((300, 240, 400, 380), fill=150)  # consolidation
    elif kind == "brain":
        draw.ellipse((80, 60, 432, 460), fill=95)
        draw.ellipse((260, 150, 360, 260), fill=190, outline=230, width=6)  # rim-enhancing mass
    else:  # spine / abdomen
        draw.ellipse((120, 90, 392, 420), fill=85)
        for y in range(110, 400, 48):
            draw.rectangle((235, y, 285, y + 34), fill=160)  # vertebrae
        draw.ellipse((300, 200, 380, 300), fill=210)  # collection
    noise = Image.effect_noise((512, 512), 18 + rng.randint(0, 6))
    image = Image.blend(image, noise, 0.15).filter(ImageFilter.GaussianBlur(1))
    return image.convert("RGB")


def diagram_image():
    """White-background schematic (flagged by the white-background screen)."""
    image = Image.new("RGB", (512, 384), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    for i, label in enumerate(["Presentation", "Imaging", "Drainage", "Recovery"]):
        x = 20 + i * 122
        draw.rectangle((x, 160, x + 105, 220), outline="black", width=3)
        draw.text((x + 6, 178), label[:9], fill="black", font=font)
        if i < 3:
            draw.line((x + 105, 190, x + 122, 190), fill="black", width=3)
    return image


def histology_image(seed):
    rng = random.Random(seed)
    image = Image.new("RGB", (512, 512), (226, 170, 196))
    draw = ImageDraw.Draw(image)
    for _ in range(260):
        x, y, r = rng.randint(0, 512), rng.randint(0, 512), rng.randint(4, 11)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(110, 50, 140))
    return image


def text_heavy_image():
    """Dark table-like picture with plenty of readable text (flagged by OCR)."""
    image = Image.new("RGB", (900, 700), (35, 35, 35))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    lines = ["Laboratory results on admission", "White cell count 18.2 high",
             "C reactive protein 210 mg per litre", "Erythrocyte sedimentation rate 95",
             "Blood culture Staphylococcus aureus", "Procalcitonin 4.1 nanogram per mL",
             "Creatinine 0.6 mg per decilitre", "Lactate 1.1 millimol per litre",
             "Antibiotic flucloxacillin intravenous", "Duration of therapy six weeks"]
    for i, line in enumerate(lines):
        draw.text((30, 30 + i * 64), line, fill=(240, 240, 240), font=font)
    return image


# ------------------------------------------------------------------ articles

def reference_xml(ref):
    ids = "".join(f'<pub-id pub-id-type="{kind}">{escape(value)}</pub-id>'
                  for kind, value in ref.get("ids", {}).items())
    return (f'<ref id="{ref["id"]}"><element-citation publication-type="journal">'
            f'<person-group person-group-type="author"><name><surname>Author</surname>'
            f'<given-names>A</given-names></name></person-group>'
            f'<article-title>{escape(ref["title"])}</article-title><source>Example J</source>'
            f'<year>2024</year>{ids}</element-citation></ref>')


def figure_xml(number, fig):
    return (f'<fig id="f{number}" position="float"><label>Figure {number}</label>'
            f'<caption><p>{escape(fig["caption"])}</p></caption>'
            f'<graphic xlink:href="{fig["href"]}"/></fig>')


def article_xml(article):
    sections = []
    for title, paragraphs in article["sections"]:
        body = "".join(p if p.startswith("<table-wrap") else f"<p>{p}</p>" for p in paragraphs)
        if title == article.get("figures_in"):
            body += "".join(figure_xml(i, fig) for i, fig in enumerate(article["figures"], start=1))
        sections.append(f"<sec><title>{escape(title)}</title>{body}</sec>")
    refs = "".join(reference_xml(ref) for ref in article.get("references", []))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink" article-type="case-report">
<front>
<journal-meta><journal-title-group><journal-title>{escape(article.get("journal", "Journal of Example Case Reports"))}</journal-title></journal-title-group></journal-meta>
<article-meta>
<article-id pub-id-type="pmc">{article["pmcid"]}</article-id>
<article-id pub-id-type="pmid">{article["pmid"]}</article-id>
<article-id pub-id-type="doi">{article["doi"]}</article-id>
<title-group><article-title>{escape(article["title"])}</article-title></title-group>
<contrib-group><contrib contrib-type="author"><name><surname>Example</surname><given-names>Ada</given-names></name></contrib>
<contrib contrib-type="author"><name><surname>Synthetic</surname><given-names>Ben</given-names></name></contrib></contrib-group>
<permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>Synthetic example, CC BY 4.0.</license-p></license></permissions>
<abstract><p>{escape(article["abstract"])}</p></abstract>
</article-meta>
</front>
<body>{"".join(sections)}</body>
<back><ref-list>{refs}</ref-list></back>
</article>
"""


def doi(n):
    return f"10.99999/example.{n:04d}"


def pmid(n):
    return str(99100000 + n)


def article(n, title, abstract, case_text, figures, references=(), extra_sections=(), case_heading="Case presentation",
            versions=(("1", False),), open_access=True):
    pmcid = str(99000000 + n)
    sections = [("Introduction", [f"Background on {title.lower()}."])]
    if case_heading:
        sections.append((case_heading, case_text))
    sections += list(extra_sections)
    return {"n": n, "pmcid": pmcid, "pmid": pmid(n), "doi": doi(n), "title": title, "abstract": abstract,
            "sections": sections, "figures_in": case_heading or "Introduction", "figures": list(figures),
            "references": list(references), "versions": versions, "open_access": open_access}


def fig(href, caption, picture, extensions=(".jpg", ".gif")):
    return {"href": href, "caption": caption, "picture": picture, "extensions": extensions}


def build_articles():
    xref = '<xref ref-type="bibr" rid="{rid}">{n}</xref>'
    return [
        article(1, "Paraspinal abscess with epidural extension in a child: a case report",
                "We report a child with a lumbar paraspinal abscess extending into the epidural space.",
                ["A 7-year-old boy presented with fever and back pain. MRI showed a paraspinal abscess "
                 "with epidural extension. Staphylococcus aureus grew from the drained pus."],
                [fig("ex-0001-g001", "Sagittal T2-weighted MRI of the lumbar spine showing a paraspinal "
                                     "abscess with epidural extension.", ("scan", "spine")),
                 fig("ex-0001-g002", "Diagram of the treatment timeline.", ("diagram",)),
                 fig("ex-0001-g003", "Histopathology (H&E) of the abscess wall with neutrophils.", ("histology",)),
                 fig("ex-0001-g004", "Photograph of the drained material.", ("scan", "abdomen"), extensions=(".png",))]),
        article(2, "Paraspinal muscle abscess complicated by spinal epidural abscess",
                "A case of pyomyositis of the paraspinal muscles with spinal epidural abscess.",
                ["A 9-year-old girl had fever and refused to walk. Contrast-enhanced MRI demonstrated "
                 "paraspinal collections with thick enhancing walls extending into the spinal canal."],
                [fig("ex-0002-g001", "Contrast-enhanced T1-weighted MRI showing paraspinal collections "
                                     "with thick enhancing walls and extension into the spinal canal.", ("scan", "spine")),
                 fig("ex-0002-g002", "Axial CT of the lumbar region showing a low-density paraspinal collection.",
                     ("scan", "spine")),
                 fig("ex-0002-g003", "Gram stain and histology of the aspirate.", ("histology",)),
                 fig("ex-0002-g004", "Laboratory results on admission.", ("text",))],
                references=[{"id": "B1", "title": "Paraspinal abscess with epidural extension in a child: a case report",
                             "ids": {"doi": doi(1)}}],
                extra_sections=[("Discussion", ["A similar paediatric case was described previously "
                                                + xref.format(rid="B1", n=1) + "."])],
                versions=(("1", True), ("2", False))),
        article(3, "Pyogenic liver abscess after spinal infection",
                "A liver abscess developed after a spinal infection.",
                ["A 45-year-old man developed fever and right upper quadrant pain. CT showed a multiloculated "
                 "liver abscess."],
                [fig("ex-0003-g001", "Contrast-enhanced CT of the abdomen showing a multiloculated liver abscess.",
                     ("scan", "abdomen")),
                 fig("ex-0003-g002", "Ultrasound of the liver showing a hypoechoic collection.", ("scan", "abdomen"))],
                references=[{"id": "R1", "title": "Paraspinal Abscess With Epidural Extension in a Child - A Case Report",
                             "ids": {}},  # no identifiers: confirmed by title matching
                            {"id": "R2", "title": "Paraspinal muscle abscess complicated by spinal epidural abscess",
                             "ids": {"pmid": pmid(2)}}],
                extra_sections=[("Discussion", ["Spinal infections can seed distant abscesses "
                                                + xref.format(rid="R1", n=1) + ", " + xref.format(rid="R2", n=2) + ".",
                                                '<table-wrap id="t1"><label>Table 1</label><caption><p>Earlier reports of '
                                                'spinal abscess.</p></caption><table><thead><tr><th>Earlier report</th>'
                                                '<th>Imaging</th><th>Site</th></tr></thead><tbody><tr><td>Paraspinal muscle '
                                                'abscess ' + xref.format(rid="R2", n=2) + '</td><td>MRI</td><td>Lumbar '
                                                'paraspinal muscles</td></tr></tbody></table></table-wrap>'])]),
        article(4, "Two siblings with paraspinal abscess",
                "Two patients from one family.", ["Patient 1 ... Patient 2 ..."],
                [fig("ex-0004-g001", "MRI of patient 1.", ("scan", "spine"))]),
        article(5, "Paraspinal abscess in a dog: a case report",
                "A 6-year-old Labrador retriever was presented with back pain.",
                ["The dog presented with fever and lumbar pain; MRI showed a paraspinal abscess."],
                [fig("ex-0005-g001", "MRI of the lumbar spine of the dog.", ("scan", "spine"))],
                references=[{"id": "B1", "title": "Paraspinal abscess with epidural extension in a child",
                             "ids": {"doi": doi(1)}}],
                ),
        article(6, "Lumbar discitis in an adult",
                "Discitis without abscess.", ["A 60-year-old woman had back pain; MRI showed discitis."],
                [fig("ex-0006-g001", "Sagittal MRI showing L4-L5 discitis.", ("scan", "spine"))],
                references=[{"id": "B1", "title": "An unrelated report", "ids": {"doi": "10.99999/unrelated"}}]),
        article(7, "Imaging of hepatic abscesses", "A short imaging note.", [],
                [fig("ex-0007-g001", "CT of a hepatic abscess.", ("scan", "abdomen"))],
                references=[{"id": "B1", "title": "Pyogenic liver abscess after spinal infection",
                             "ids": {"doi": doi(3)}}],
                case_heading=None,
                extra_sections=[("Clinical findings", ["A hepatic abscess was drained."])]),
        # article 8 is linked in PMC-Patients but missing from the mirror (not available)
        article(9, "Epidural abscess management pathway", "A management pathway illustrated with schematics.",
                ["A 50-year-old man with an epidural abscess was managed following the pathway."],
                [fig("ex-0009-g001", "Flowchart of the management pathway.", ("diagram",)),
                 fig("ex-0009-g002", "Schematic of surgical approaches.", ("diagram",))],
                references=[{"id": "B1", "title": "Paraspinal muscle abscess complicated by spinal epidural abscess",
                             "ids": {"doi": doi(2)}}]),
        article(10, "Right lower lobe pneumonia in a young adult", "Community-acquired pneumonia.",
                ["A 25-year-old man had cough and fever. Chest radiograph showed right lower lobe consolidation."],
                [fig("ex-0010-g001", "Frontal chest radiograph showing right lower lobe consolidation.", ("scan", "chest"))]),
        article(11, "Lobar pneumonia with parapneumonic effusion", "Pneumonia complicated by effusion.",
                ["A 31-year-old woman had pleuritic pain. Chest X-ray showed lobar consolidation; "
                 "CT confirmed a small effusion."],
                [fig("ex-0011-g001", "Chest X-ray showing right lobar consolidation.", ("scan", "chest")),
                 fig("ex-0011-g002", "Axial chest CT showing consolidation and a small effusion.", ("scan", "chest"))],
                references=[{"id": "B1", "title": "Right lower lobe pneumonia in a young adult",
                             "ids": {"pmc": "PMC99000010"}}],  # PMCID written with the PMC prefix
                extra_sections=[("Discussion", ["Consolidation patterns were comparable "
                                                + xref.format(rid="B1", n=1) + "."])]),
        article(12, "Glioblastoma presenting with seizures", "A glioblastoma case.",
                ["A 58-year-old man had a first seizure. MRI showed a rim-enhancing right temporal mass; "
                 "CT showed a hypodense mass with mass effect."],
                [fig("ex-0012-g001", "Contrast-enhanced T1-weighted brain MRI showing a rim-enhancing mass.", ("scan", "brain")),
                 fig("ex-0012-g002", "Non-contrast head CT showing a hypodense temporal mass.", ("scan", "brain"))]),
        article(13, "Glioblastoma in an older adult", "Another glioblastoma case.",
                ["A 70-year-old woman had headaches. MRI demonstrated a ring-enhancing frontal mass; CT showed "
                 "vasogenic oedema around a mass."],
                [fig("ex-0013-g001", "Brain MRI with contrast showing a ring-enhancing frontal mass.", ("scan", "brain")),
                 fig("ex-0013-g002", "Head CT showing a mass with surrounding oedema.", ("scan", "brain"))],
                references=[{"id": "B1", "title": "Glioblastoma presenting with seizures", "ids": {"doi": doi(12)}}],
                # cited only as plain author-year text: no <xref>, so no passage can be extracted
                extra_sections=[("Discussion", ["Seizures were also the first sign in an earlier report (Example 2024)."])]),
        article(15, "Pneumonia in a restricted-license article", "Not in the open access subset.",
                ["Chest radiograph showed consolidation."],
                [fig("ex-0015-g001", "Chest radiograph.", ("scan", "chest"))],
                open_access=False),
    ]


def picture(spec, seed):
    kind = spec[0]
    if kind == "scan":
        return scan_image(seed, spec[1])
    if kind == "diagram":
        return diagram_image()
    if kind == "histology":
        return histology_image(seed)
    return text_heavy_image()


def write_mirror(articles, mirror):
    shutil.rmtree(mirror, ignore_errors=True)
    for art in articles:
        for version, is_manuscript in art["versions"]:
            prefix = f"PMC{art['pmcid']}.{version}"
            folder = mirror / prefix
            folder.mkdir(parents=True)
            (folder / f"{prefix}.xml").write_text(article_xml(art), encoding="utf-8")
            media = []
            for i, figure in enumerate(art["figures"], start=1):
                image = picture(figure["picture"], seed=art["n"] * 10 + i)
                for extension in figure["extensions"]:
                    path = folder / f"{figure['href']}{extension}"
                    if extension == ".gif":
                        image.resize((100, 100)).save(path)  # PMC-style thumbnail
                    else:
                        image.save(path, quality=90) if extension == ".jpg" else image.save(path)
                    media.append(path.name)
            metadata = {"pmcid": f"PMC{art['pmcid']}", "version": int(version), "pmid": art["pmid"],
                        "doi": art["doi"], "title": art["title"], "is_pmc_openaccess": art["open_access"],
                        "is_manuscript": is_manuscript, "license_code": "CC BY" if art["open_access"] else None,
                        "media_urls": [f"s3://pmc-oa-opendata/{prefix}/{name}" for name in media]}
            (folder / f"{prefix}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def write_pmc_patients_table(data_dir):
    links = {
        "99000001-1": ["99000002-1", "99000003-1", "99000005-1", "99000004-1", "99000001-1"],  # incl. self link
        "99000002-1": ["99000001-1", "99000003-1", "99000006-1", "99000009-1", "99000004-2"],
        "99000003-1": ["99000001-1", "99000002-1", "99000007-1", "99000008-1"],
        "99000004-1": ["99000001-1", "99000004-2"], "99000004-2": ["99000002-1", "99000004-1"],
        "99000005-1": ["99000001-1"], "99000006-1": ["99000002-1"], "99000007-1": ["99000003-1"],
        "99000008-1": ["99000003-1"], "99000009-1": ["99000002-1"],
        "99000010-1": ["99000011-1", "99000015-1"], "99000011-1": ["99000010-1"],
        "99000012-1": ["99000013-1"], "99000013-1": ["99000012-1"],
        "99000014-1": [], "99000015-1": ["99000010-1"],
    }
    path = data_dir / "pmc_patients_example.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["patient_id", "patient_uid", "PMID", "title", "patient", "similar_patients"])
        writer.writeheader()
        for i, (uid, others) in enumerate(links.items()):
            similar = {other: (2 if other.split("-")[0] == uid.split("-")[0] else 1) for other in others}
            writer.writerow({"patient_id": i, "patient_uid": uid, "PMID": pmid(int(uid[2:8])),
                             "title": f"Synthetic article {uid.split('-')[0]}", "patient": "Synthetic summary.",
                             "similar_patients": repr(similar)})


def write_llm_responses(data_dir):
    p12, p13, p23 = "99000001-1__99000002-1", "99000001-1__99000003-1", "99000002-1__99000003-1"
    p1011, p1213 = "99000010-1__99000011-1", "99000012-1__99000013-1"
    ready = (p12, p13, p23, p1011, p1213)
    citation = {
        p12: "Reason for Citation: To cite a previous paediatric paraspinal abscess with epidural extension.\n"
             "Possible Similarities: Both are children with paraspinal abscess extending into the epidural space.\n"
             "Explanation: The citing report compares its MRI findings with the earlier case.",
        p13: "Reason for Citation: To show that spinal infections can seed distant abscesses.\n"
             "Possible Similarities: Both involve pyogenic abscesses.\n"
             "Explanation: The cited case is background on spinal infection, not on liver involvement.",
        p23: "Reason for Citation: Background on spinal epidural abscess.\n"
             "Possible Similarities: Both involve pyogenic abscesses at different sites.\n"
             "Explanation: Cited as an example of spinal infection preceding a liver abscess.",
        p1011: "Reason for Citation: Comparison of consolidation patterns.\n"
               "Possible Similarities: Both are young adults with lobar pneumonia on chest radiographs.\n"
               "Explanation: The citing authors compare radiographic findings.",
        p1213: "Reason for Citation: Seizure as the presenting sign of glioblastoma.\n"
               "Possible Similarities: Both are adults with ring-enhancing glioblastoma.\n"
               "Explanation: Cited to support the presentation (no citation passage was available).",
    }
    questions = {pair: "Level 1 - modality / organ system\n1. Both imaged with MRI or CT of the same region?\n"
                       "2. Same organ system involved?\nLevel 2 - broad diagnostic category\n"
                       "3. Same disease category (infectious vs neoplastic)?\nLevel 3 - specific imaging and clinical features\n"
                       "4. Same hallmark imaging finding?" for pair in ready}
    answers = {pair: "1. Yes — both describe cross-sectional imaging of the involved region.\n"
                     "2. Yes — same organ system.\n3. Yes — same disease category.\n4. Partial — similar findings."
               for pair in (p12, p1011, p1213)}
    answers[p13] = "1. No — spine MRI vs abdominal CT.\n2. No — spine vs liver.\n3. Yes — both infections.\n4. No — different sites."
    answers[p23] = answers[p13]
    pairs = {
        # valid MRI pair + histology pair + the MRI pair repeated in reverse (kept once)
        p12: "```json\n" + json.dumps([
            {"pair_id": ["99000002_1_1", "99000001_1_1"], "modality": "MRI",
             "anatomy": "lumbar spine/paraspinal muscles/epidural space",
             "diagnosis": "paraspinal abscess with spinal epidural abscess"},
            {"pair_id": ["99000002_1_3", "99000001_1_3"], "modality": "Histopathology (H&E)",
             "anatomy": "paraspinal soft tissue", "diagnosis": "abscess"},
            {"pair_id": ["99000001_1_1", "99000002_1_1"], "modality": "MRI", "anatomy": "lumbar spine",
             "diagnosis": "paraspinal abscess"}], indent=1) + "\n```",
        p13: "Here are the positive matches: []",  # prose is removed; a valid empty list remains
        p23: json.dumps([{"pair_id": ["99000003_1_1", "99000002_1_9"], "modality": "CT", "anatomy": "abdomen",
                          "diagnosis": "abscess"}]),  # 99000002_1_9 does not exist: rejected
        p1011: json.dumps([{"pair_id": ["99000011_1_1", "99000010_1_1"], "modality": "X-ray",
                            "anatomy": "chest/lungs", "diagnosis": "lobar pneumonia"},
                           {"pair_id": ["99000011_1_2", "99000010_1_1"], "modality": "CT",
                            "anatomy": "chest"}]),  # missing diagnosis: rejected
        p1213: json.dumps([{"pair_id": ["99000013_1_1", "99000012_1_1"], "modality": "MRI", "anatomy": "brain",
                            "diagnosis": "glioblastoma"},
                           {"pair_id": ["PMC99000013_1_1", "99000012_1_2"], "modality": "MRI",  # not the exact id
                            "anatomy": "brain", "diagnosis": "glioblastoma"},
                           {"pair_id": ["99000013_1_2", "99000012_1_2"], "modality": "CT",
                            "anatomy": "brain/intracranial", "diagnosis": "enhancing mass lesion"}]),
    }
    folder = data_dir / "llm_responses"
    folder.mkdir(parents=True, exist_ok=True)
    for stage, texts in (("citation_analysis", citation), ("question_generation", questions),
                         ("answer_generation", answers), ("pair_selection", pairs)):
        with open(folder / f"{stage}.jsonl", "w", encoding="utf-8") as f:
            for pair_id, text in texts.items():
                f.write(json.dumps({"request_id": f"{stage}:{pair_id}", "output_text": text,
                                    "model": "synthetic-example"}) + "\n")


def main(data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    write_mirror(build_articles(), data_dir / "pmc_mirror")
    write_pmc_patients_table(data_dir)
    write_llm_responses(data_dir)
    print(f"Synthetic example written to {data_dir}")


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:2])
