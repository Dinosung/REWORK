import shutil
import zipfile

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Pt
from lxml import etree

from rework.cli import build, main
from rework.learn import learn
from rework.ooxml import style_names, w

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="needs pandoc")

MARKDOWN = """---
title: Bridge Deck Assessment
author: Example Consulting
date: October 2026
---

# Introduction

This report summarises the condition of the deck.

- first point
- second point

| Core | Chloride |
|------|----------|
| C1   | 0.12     |

Table: Chloride by core
"""


def make_template(path):
    """A small house template: cover section, a custom body style, a table style, a header."""
    doc = Document()
    body = doc.styles.add_style("House Body", WD_STYLE_TYPE.PARAGRAPH)
    body.font.name = "Georgia"
    body.font.size = Pt(11)
    doc.add_paragraph("ACME Engineering", style="Title")
    doc.add_paragraph("Report title goes here")
    doc.add_paragraph("Prepared for: Client name")
    second = doc.add_section(WD_SECTION.NEW_PAGE)
    second.header.is_linked_to_previous = False
    second.header.paragraphs[0].text = "ACME Confidential"
    doc.add_heading("Background", level=1)
    for _ in range(3):
        doc.add_paragraph("House body text " * 10, style="House Body")
    table = doc.add_table(rows=2, cols=2)
    table.style = "Light Grid Accent 1"
    table.cell(0, 0).text = "a"
    doc.save(path)


def read(path, part):
    return etree.fromstring(zipfile.ZipFile(path).read(part))


@pytest.fixture
def files(tmp_path):
    tpl, md = tmp_path / "house.docx", tmp_path / "report.md"
    make_template(tpl)
    md.write_text(MARKDOWN)
    return tpl, md, tmp_path / "out.docx"


def test_learn_finds_house_style(files):
    tpl, _, _ = files
    style = learn(str(tpl))
    assert style["body"] == "HouseBody"
    assert style["table"] == "LightGrid-Accent1"
    assert style["cover"] == 4  # three lines plus the section break
    assert style["body_section"] == 1
    assert "Report title goes here" in style["cover_lines"]


def test_build_applies_house_style(files):
    tpl, md, out = files
    style = learn(str(tpl))
    style["replace"] = [["Report title goes here", "{title}"], ["Client name", "{client}"]]
    missing = build(str(md), str(tpl), str(out), style, {"client": "City of Springfield"})
    assert missing == []

    doc = read(out, "word/document.xml")
    texts = ["".join(t.text or "" for t in p.iter(w("t"))) for p in doc.iter(w("p"))]
    assert texts[:3] == ["ACME Engineering", "Bridge Deck Assessment", "Prepared for: City of Springfield"]
    assert "Example Consulting" not in texts  # pandoc's title block was replaced by the cover

    used = {p.get(w("val")) for p in doc.iter(w("pStyle"))}
    assert "HouseBody" in used and "FirstParagraph" not in used and "BodyText" not in used
    assert {t.get(w("val")) for t in doc.iter(w("tblStyle"))} == {"LightGrid-Accent1"}

    # Every style the document uses is defined.
    defined = set(style_names(read(out, "word/styles.xml")))
    used_all = {e.get(w("val")) for tag in ("pStyle", "rStyle", "tblStyle") for e in doc.iter(w(tag))}
    assert used_all <= defined

    # The body section carries the template's main-section header.
    headers = [n for n in zipfile.ZipFile(out).namelist() if n.startswith("word/tpl_header")]
    assert any(b"ACME Confidential" in zipfile.ZipFile(out).read(h) for h in headers)


def test_template_is_not_modified(files):
    tpl, md, out = files
    before = tpl.read_bytes()
    build(str(md), str(tpl), str(out))
    assert tpl.read_bytes() == before


def test_cli_learn_and_build(files, capsys, tmp_path):
    tpl, md, out = files
    assert main(["learn", str(tpl)]) == 0
    style_file = tmp_path / "style.json"
    style_file.write_text(capsys.readouterr().out)
    assert main(["build", str(md), "-t", str(tpl), "-s", str(style_file), "-o", str(out)]) == 0
    assert zipfile.is_zipfile(out)


def test_parts_without_a_content_type_are_registered(files, tmp_path):
    from rework.ooxml import Package, register_content_types

    tpl, _, _ = files
    pkg = Package(str(tpl))
    pkg.parts["word/fonts/House-Bold.ttf"] = b"font bytes"
    register_content_types(pkg, pkg)
    types = pkg.parts["[Content_Types].xml"].decode()
    assert 'Extension="ttf"' in types
    path = tmp_path / "fixed.docx"
    pkg.save(str(path))
    Document(str(path))  # python-docx refuses parts without a content type


def test_cover_may_use_a_heading_style(tmp_path):
    doc = Document()
    doc.add_heading("ACME LTD", level=1)  # some templates style the firm's name as a heading
    doc.add_paragraph("[Report name]")
    doc.add_page_break()
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("Body " * 200)
    path = tmp_path / "t.docx"
    doc.save(path)
    style = learn(str(path))
    assert style["cover"] == 3
    assert style["cover_lines"] == ["ACME LTD", "[Report name]"]


def test_long_front_matter_is_only_suggested(tmp_path):
    doc = Document()
    doc.add_paragraph("Statement " * 100)
    doc.add_page_break()
    doc.add_heading("Introduction", level=1)
    path = tmp_path / "t.docx"
    doc.save(path)
    style = learn(str(path))
    assert style["cover"] == 0 and "cover_note" in style
