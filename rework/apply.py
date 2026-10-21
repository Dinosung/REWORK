"""Make a pandoc --reference-doc output follow the template's house style.

pandoc keeps the template's style definitions but writes its own style names (Compact, Table,
First Paragraph...), keeps the header and footer of the template's first section, and drops
the cover. This module fixes those after the fact. The template is only read.
"""
import copy
import re
import subprocess

from lxml import etree

from .fill import Filler
from .learn import is_toc
from .ooxml import (
    R_NS,
    W_NS,
    Importer,
    Package,
    register_content_types,
    rels_name,
    resolve_styles,
    sections,
    style_names,
    w,
)

TITLE_BLOCK = ("title", "subtitle", "author", "date")  # the cover replaces these; the abstract is content
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
HEADER_REL, FOOTER_REL = R_NS + "/header", R_NS + "/footer"


def _pstyle(p):
    return p.find(f"./{w('pPr')}/{w('pStyle')}")


def apply(template_path: str, pandoc_out: str, style: dict, dst: str, values: dict | None = None) -> list[str]:
    """Write `dst`. Returns warnings for the user (ideally none)."""
    tpl, out = Package(template_path), Package(pandoc_out)
    importer = Importer(tpl, out)
    doc = out.xml("word/document.xml")
    body = doc.find(w("body"))
    tpl_body = tpl.xml("word/document.xml").find(w("body"))

    names = style_names(out.xml("word/styles.xml"))
    style = resolve_styles(style, out.xml("word/styles.xml"))
    meta = _take_title_block(body, names) if style.get("cover") else {}
    filler = Filler(style.get("replace", []), {**meta, **(values or {})})
    links: list = []
    cover = _insert_cover(body, tpl_body, style, importer, filler, links)
    _use_body_section(body, tpl_body, style, importer)
    _map_styles(body, style, skip=cover)
    _unnumber(body)
    missing = _define_missing_styles(out)
    styles = out.xml("word/styles.xml")
    _never_number(styles, ("TOCHeading", "AbstractTitle"))
    out.set_xml("word/styles.xml", styles)
    warnings = _visible_body(body, styles, skip=cover)
    out.set_xml("word/document.xml", doc)
    importer.finish()
    _fill_headers(out, doc, filler)
    warnings += _fix_links(out, links, [t for t, v in filler.filled.items() if not v])
    _drop_unused_parts(out, doc)
    register_content_types(out, tpl)
    out.save(dst)
    warnings += _left_behind(tpl_body, style)
    warnings += _borrowed_headings(doc, tpl.xml("word/styles.xml"), style_names(out.xml("word/styles.xml")))
    template_text = _text(tpl_body)
    for t in filler.unused():
        where = (f"it is in the template but outside the copied cover (\"cover\": {style.get('cover') or 0}); "
                 "raise cover to include it" if t in template_text else "not found in the cover, header or footer")
        warnings.append(f"text to replace {t!r}: {where}")
    if missing:
        warnings.append(f"styles still undefined: {', '.join(missing)}")
    return warnings


def _take_title_block(body, names) -> dict:
    """Remove pandoc's title block (the template's cover replaces it) and return its text.

    pandoc applies the template's own Title/Author/Date styles, matched by name, so the
    style ids differ from template to template.
    """
    meta = {}
    for el in list(body):
        ps = _pstyle(el) if el.tag == w("p") else None
        sid = ps.get(w("val")) if ps is not None else ""
        name = names.get(sid, sid.lower())  # undefined in the template: pandoc's own id
        if name not in TITLE_BLOCK:
            break
        meta[name] = "".join(t.text or "" for t in el.iter(w("t")))
        body.remove(el)
    return meta


def _insert_cover(body, tpl_body, style, importer, filler, links) -> set:
    count = style.get("cover") or 0
    if not count:
        return set()
    cover = []
    for el in list(tpl_body)[:count]:
        el = copy.deepcopy(el)
        importer.remap(el)
        before = {h: _text(h) for h in el.iter(w("hyperlink")) if h.get(f"{{{R_NS}}}id")}
        changed = [p for p in el.iter(w("p")) if filler.paragraph(p)]
        for p in changed:
            _drop_empty_lines(p)
        links += [(h, text) for h, text in before.items() if _text(h) != text]
        # A placeholder line replaced by nothing is dropped, not left as an empty line.
        if el.tag == w("p") and el in changed and not _text(el).strip() and not _has_drawing(el):
            continue
        cover.append(el)
    for i, el in enumerate(cover):
        body.insert(i, el)
    if cover:
        # The first paragraph or table after the cover (pandoc 3.1 puts bookmark markers in between).
        first = next((el for el in list(body)[len(cover):] if el.tag in (w("p"), w("tbl"))), None)
        _new_page_after(cover[-1], first, body)
    return {node for el in cover for node in el.iter()}


def _new_page_after(last, first, body) -> None:
    """The body starts on a new page, even when the template's page break came after the copied part.

    If the cover ends in a section break, the body section is made to start on a new page (see
    _use_body_section); otherwise the body's first paragraph gets "page break before" (a separate
    break paragraph can spill onto a page of its own after a full-page cover).
    """
    if _ends_page(last):
        return
    if first is not None and first.tag == w("p"):
        ppr = first.find(w("pPr"))
        if ppr is None:
            ppr = etree.Element(w("pPr"))
            first.insert(0, ppr)
        if ppr.find(w("pageBreakBefore")) is None:
            before = [c for c in ppr if etree.QName(c).localname in ("pStyle", "keepNext", "keepLines")]
            ppr.insert(ppr.index(before[-1]) + 1 if before else 0, etree.Element(w("pageBreakBefore")))
    else:
        body.insert(body.index(last) + 1,
                    etree.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:br w:type="page"/></w:r></w:p>'))


def _borrowed_headings(doc, tpl_styles, names) -> list[str]:
    """Heading levels the template doesn't define come in with pandoc's look; say so."""
    own = set(style_names(tpl_styles).values())
    used = {names.get(ps.get(w("val")), "") for ps in doc.iter(w("pStyle"))}
    lacking = sorted(n for n in used if n.startswith("heading ") and n not in own)
    if not lacking:
        return []
    return [f"the template has no {', '.join(n.title() for n in lacking)} style, so pandoc's default look was "
            "used; use fewer heading levels, or pass -- --shift-heading-level-by if the levels are offset"]


def _left_behind(tpl_body, style) -> list[str]:
    """What the template has that the output doesn't, so a clean build isn't mistaken for a finished one."""
    notes = []
    elements, cover = list(tpl_body), style.get("cover") or 0
    front = elements[cover:style.get("front_end") or cover]
    # A sample table of contents lists the template's headings, not yours: never suggest copying it.
    rest = [t for t in (_text(el).strip() for el in front if not is_toc(el)) if t]
    if cover and rest:
        notes.append(f"the template's front matter continues after the cover ({len(rest)} more lines, from "
                     f"{rest[0][:40]!r}); raise \"cover\" to a value from cover_choices (rework learn) to copy it")
    if any(is_toc(el) for el in front):
        notes.append("the template has a table of contents after the cover; pass -- --toc for one listing your "
                     "headings (Word fills it in when fields are updated)")
    tables = [t for t in tpl_body.iter(w("tbl")) if len(t.findall(w("tr"))) >= 2]
    if tables and not style.get("table"):
        notes.append("the template's tables have no table style (they are formatted by hand), "
                     "so yours use pandoc's plain table look")
    return notes


def _ends_page(el) -> bool:
    return (el.find(f".//{w('sectPr')}") is not None
            or any(b.get(w("type")) == "page" for b in el.iter(w("br"))))


def _never_number(styles, ids) -> None:
    """pandoc's contents and abstract headings are based on Heading 1; keep them out of its numbering."""
    for s in styles.iter(w("style")):
        if s.get(w("styleId")) in ids:
            ppr = s.find(w("pPr"))
            if ppr is None:
                ppr = etree.SubElement(s, w("pPr"))
            if ppr.find(w("numPr")) is None:
                num = etree.Element(w("numPr"))
                etree.SubElement(num, w("numId")).set(w("val"), "0")
                # Schema order: numPr follows these, if present.
                before = [c for c in ppr if etree.QName(c).localname in NUMPR_AFTER]
                ppr.insert(ppr.index(before[-1]) + 1 if before else 0, num)


NUMPR_AFTER = ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl")
COLOR_AFTER = ("rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
               "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden")
WHITE = {"FFFFFF", "WHITE"}


def _visible_body(body, styles, skip: set) -> list[str]:
    """Some templates make a base style white for a dark cover and recolour body text by hand.

    Give runs in white-styled body paragraphs automatic colour, as the template's own pages do.
    """
    by_id = {s.get(w("styleId")): s for s in styles.iter(w("style"))}
    default = next((s.get(w("styleId")) for s in styles.iter(w("style"))
                    if s.get(w("type")) == "paragraph" and s.get(w("default")) in ("1", "true")), None)

    def find(sid, path, seen=()):
        s = by_id.get(sid)
        if s is None or sid in seen:
            return None
        found = s.find(path)
        if found is not None:
            return found
        based = s.find(w("basedOn"))
        return find(based.get(w("val")), path, (*seen, sid)) if based is not None else None

    def color(sid):
        c = find(sid, f"{w('rPr')}/{w('color')}")
        return (c.get(w("val")) or "").upper() if c is not None else None

    def on_band(sid):  # white text on a coloured paragraph fill (a heading bar) is meant to be white
        shd = find(sid, f"{w('pPr')}/{w('shd')}")
        return shd is not None and (shd.get(w("fill")) or "auto").upper() not in ("AUTO", "FFFFFF")

    fixed = set()
    for p in body.iter(w("p")):
        if p in skip:
            continue
        ps = _pstyle(p)
        sid = ps.get(w("val")) if ps is not None else default
        if color(sid) not in WHITE or on_band(sid):
            continue
        for r in p.iter(w("r")):
            rpr = r.find(w("rPr"))
            if rpr is None:
                rpr = etree.Element(w("rPr"))
                r.insert(0, rpr)
            run_style = rpr.find(w("rStyle"))
            if rpr.find(w("color")) is None and (run_style is None or color(run_style.get(w("val"))) is None):
                auto = etree.Element(w("color"))
                auto.set(w("val"), "auto")
                before = [c for c in rpr if etree.QName(c).localname in COLOR_AFTER]
                rpr.insert(rpr.index(before[-1]) + 1 if before else 0, auto)
        fixed.add(sid)
    return [f"the template's {', '.join(sorted(fixed))} style is white text (probably for a dark cover); "
            "body text was given automatic colour, as on the template's own pages"] if fixed else []


def _drop_empty_lines(p) -> None:
    """Remove line breaks left around a line that a replacement emptied ("Phone: ...<br/>" -> "")."""
    pending, seen_text = [], False
    for node in list(p.iter(w("t"), w("br"))):
        if node.tag == w("t"):
            if node.text:
                pending, seen_text = [], True
            continue
        if node.get(w("type")) not in (None, "textWrapping"):
            continue  # page and column breaks stay
        if not seen_text or pending:
            node.getparent().remove(node)  # a break before any text, or right after another break
        else:
            pending.append(node)
    for node in pending:
        node.getparent().remove(node)  # trailing breaks


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(w("t")))


def _has_drawing(el) -> bool:
    return any(n.tag in (w("drawing"), w("pict"), w("object")) for n in el.iter())


def _fill_headers(out: Package, doc, filler) -> None:
    """Fill placeholders in the headers and footers the document uses."""
    rels = {r.get("Id"): r.get("Target") for r in out.xml("word/_rels/document.xml.rels")}
    for ref in doc.iter(w("headerReference"), w("footerReference")):
        name = "word/" + rels.get(ref.get(f"{{{R_NS}}}id"), "")
        if name in out.parts:
            part = out.xml(name)
            if [p for p in part.iter(w("p")) if filler.paragraph(p)]:
                out.set_xml(name, part)


def _fix_links(out: Package, links, deleted: list[str]) -> list[str]:
    """Cover links whose text was filled in: a new email address gets a matching mailto target."""
    rels = out.xml("word/_rels/document.xml.rels")
    by_id = {r.get("Id"): r for r in rels}
    warnings = []
    for link, before in links:
        rel = by_id.get(link.get(f"{{{R_NS}}}id"))
        text = _text(link).strip()
        if not text:
            link.getparent().remove(link)
            if not any(before.strip() and before.strip() in gone for gone in deleted):  # deleting it was the point
                warnings.append(f"the link on {before!r} was removed because a replacement covered its text; "
                                "replace only the text outside the link")
        elif rel is None or rel.get("TargetMode") != "External":
            continue
        elif rel.get("Target", "").startswith("mailto:") and EMAIL.fullmatch(text):
            rel.set("Target", "mailto:" + text)
        else:
            warnings.append(f"the cover link now reads {text!r} but still points to {rel.get('Target')}; "
                            "use one replace pair per email address, or edit the link")
    out.set_xml("word/_rels/document.xml.rels", rels)
    return warnings


def _drop_unused_parts(out: Package, doc) -> None:
    """Remove pandoc's own headers and footers, which the template's section replaced."""
    used = {n.get(f"{{{R_NS}}}id") for n in doc.iter() if n.get(f"{{{R_NS}}}id")}
    rels = out.xml("word/_rels/document.xml.rels")
    kinds = (HEADER_REL, FOOTER_REL)
    for rel in list(rels):
        if rel.get("Type") in kinds and rel.get("Id") not in used:
            rels.remove(rel)
            name = "word/" + rel.get("Target")
            out.parts.pop(name, None)
            out.parts.pop(rels_name(name), None)
    out.set_xml("word/_rels/document.xml.rels", rels)
    types = out.xml("[Content_Types].xml")
    for o in list(types):
        if o.get("PartName") and o.get("PartName")[1:] not in out.parts:
            types.remove(o)
    out.set_xml("[Content_Types].xml", types)


def _use_body_section(body, tpl_body, style, importer):
    """Give the body the page setup, header and footer of the template's main section."""
    secs = sections(tpl_body)
    index = style.get("body_section", len(secs) - 1)
    if not secs or index >= len(secs):
        return
    # Word inherits header/footer references from earlier sections; resolve them.
    refs = {}
    for _, sect in secs[:index + 1]:
        for ref in sect:
            if ref.tag in (w("headerReference"), w("footerReference")):
                refs[(ref.tag, ref.get(w("type")))] = ref.get(f"{{{R_NS}}}id")
    new = copy.deepcopy(secs[index][1])
    for ref in list(new):
        if ref.tag in (w("headerReference"), w("footerReference")):
            new.remove(ref)
    # Headers before footers: LibreOffice misreads a first-page header listed after the footers.
    order = sorted(refs.items(), key=lambda item: (item[0][0] != w("headerReference"), item[0][1]))
    for i, ((tag, kind), rid) in enumerate(order):
        el = etree.Element(tag)
        el.set(w("type"), kind)
        el.set(f"{{{R_NS}}}id", rid)
        new.insert(i, el)
    # After a cover, the body section starts on a new page, not "continuous" on the cover's page.
    kind = new.find(w("type"))
    if style.get("cover") and kind is not None and kind.get(w("val")) == "continuous":
        kind.set(w("val"), "nextPage")
    # A past deliverable may restart page numbers mid-thesis ("start at 26"); start at 1 instead.
    pg = new.find(w("pgNumType"))
    if pg is not None and pg.get(w("start")) not in (None, "0", "1"):
        del pg.attrib[w("start")]
    importer.remap(new)
    old = body.find(w("sectPr"))
    if old is not None:
        body.replace(old, new)
    else:
        body.append(new)


UNNUMBERED = "ReworkUnnumbered"  # the character style the CLI's Lua filter puts on such headings


def _unnumber(body) -> None:
    """Headings marked {.unnumbered} in the source skip the template's heading numbering."""
    for p in body.iter(w("p")):
        marks = [r for r in p.iter(w("rStyle")) if r.get(w("val")) == UNNUMBERED]
        if not marks:
            continue
        for mark in marks:
            mark.getparent().remove(mark)
        ppr = p.find(w("pPr"))
        if ppr is None:
            ppr = etree.Element(w("pPr"))
            p.insert(0, ppr)
        num = ppr.find(w("numPr"))
        if num is None:
            num = etree.Element(w("numPr"))
            ppr.insert(1 if ppr.find(w("pStyle")) is not None else 0, num)
        for child in list(num):
            num.remove(child)
        etree.SubElement(num, w("numId")).set(w("val"), "0")


def _map_styles(body, style, skip: set):
    in_tables = {p for tbl in body.iter(w("tbl")) for p in tbl.iter(w("p"))}
    renames = {"FirstParagraph": style.get("body"), "BodyText": style.get("body"),
               "BlockText": style.get("quote"),
               "TableCaption": style.get("table_caption") or style.get("caption"),
               "ImageCaption": style.get("figure_caption") or style.get("caption")}
    for p in body.iter(w("p")):
        ps = _pstyle(p)
        if p in skip or ps is None:
            continue
        sid = ps.get(w("val"))
        if sid == "Compact" and p in in_tables and style.get("table_cell"):
            ps.set(w("val"), style["table_cell"])
        elif sid == "Compact" and p.find(f"./{w('pPr')}/{w('numPr')}") is not None and style.get("list"):
            ps.set(w("val"), style["list"])
        elif renames.get(sid):
            ps.set(w("val"), renames[sid])
        if sid == "TableCaption" and ps.getparent().find(w("keepNext")) is None:
            ps.addnext(etree.Element(w("keepNext")))  # keep a table's caption on the table's page
    if style.get("table"):
        for t in body.iter(w("tblStyle")):
            if t not in skip:
                t.set(w("val"), style["table"])


def _define_missing_styles(out: Package) -> list[str]:
    """Styles pandoc refers to but the template lacks: match by name, else copy pandoc's own."""
    styles = out.xml("word/styles.xml")
    defaults = etree.fromstring(_pandoc_default_styles())
    default_by_id = {s.get(w("styleId")): s for s in defaults.iter(w("style"))}
    default_names = style_names(defaults)
    parts = {n: out.xml(n) for n in ("word/document.xml", "word/footnotes.xml") if n in out.parts}
    roots = list(parts.values())

    def defined():
        return set(style_names(styles))

    renamed = {}

    def resolve(sid):
        if sid in defined():
            return sid
        by_name = {name: i for i, name in style_names(styles).items()}
        if default_names.get(sid) in by_name:
            renamed[sid] = by_name[default_names[sid]]
            return renamed[sid]
        if sid not in default_by_id:
            return sid
        definition = copy.deepcopy(default_by_id[sid])
        styles.append(definition)
        based = definition.find(w("basedOn"))
        if based is not None:
            based.set(w("val"), resolve(based.get(w("val"))))
        for tag in ("next", "link"):
            el = definition.find(w(tag))
            if el is not None and el.get(w("val")) not in defined() | set(default_by_id):
                definition.remove(el)
        return sid

    tags = ("pStyle", "rStyle", "tblStyle")
    used = {e.get(w("val")) for r in roots for t in tags for e in r.iter(w(t))}
    for sid in sorted(used):
        resolve(sid)
    for name, root in parts.items():
        for t in tags:
            for e in root.iter(w(t)):
                if e.get(w("val")) in renamed:
                    e.set(w("val"), renamed[e.get(w("val"))])
        out.set_xml(name, root)
    out.set_xml("word/styles.xml", styles)
    used = {e.get(w("val")) for r in roots for t in tags for e in r.iter(w(t))}
    return sorted(used - defined())


def _pandoc_default_styles() -> bytes:
    import io
    import zipfile
    ref = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
                         check=True, capture_output=True).stdout
    with zipfile.ZipFile(io.BytesIO(ref)) as z:
        return z.read("word/styles.xml")
