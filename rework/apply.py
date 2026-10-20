"""Make a pandoc --reference-doc output follow the template's house style.

pandoc keeps the template's style definitions but writes its own style names (Compact, Table,
First Paragraph...), keeps the header and footer of the template's first section, and drops
the cover. This module fixes those after the fact. The template is only read.
"""
import copy
import re
import subprocess

from lxml import etree

from .ooxml import Importer, Package, R_NS, sections, style_names, w

TITLE_BLOCK = ("title", "subtitle", "author", "date", "abstract")


def _pstyle(p):
    return p.find(f"./{w('pPr')}/{w('pStyle')}")


def apply(template_path: str, pandoc_out: str, style: dict, dst: str, values: dict | None = None) -> list[str]:
    """Write `dst`. Returns styles still undefined after the fix (ideally none)."""
    tpl, out = Package(template_path), Package(pandoc_out)
    importer = Importer(tpl, out)
    doc = out.xml("word/document.xml")
    body = doc.find(w("body"))
    tpl_body = tpl.xml("word/document.xml").find(w("body"))

    names = style_names(out.xml("word/styles.xml"))
    meta = _take_title_block(body, names) if style.get("cover") else {}
    cover = _insert_cover(body, tpl_body, style, importer, {**meta, **(values or {})})
    _use_body_section(body, tpl_body, style, importer)
    _map_styles(body, style, skip=cover)
    out.set_xml("word/document.xml", doc)
    missing = _define_missing_styles(out)
    importer.finish()
    out.save(dst)
    return missing


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


def _insert_cover(body, tpl_body, style, importer, values) -> set:
    count = style.get("cover") or 0
    if not count:
        return set()
    cover = [copy.deepcopy(el) for el in list(tpl_body)[:count]]
    for el in cover:
        importer.remap(el)
        for p in el.iter(w("p")):
            _replace_text(p, style.get("replace", []), values)
    for i, el in enumerate(cover):
        body.insert(i, el)
    return {node for el in cover for node in el.iter()}


def _replace_text(p, pairs, values):
    runs = list(p.iter(w("t")))
    if not runs:
        return
    text = "".join(t.text or "" for t in runs)
    for pattern, replacement in pairs:
        if re.search(pattern, text):
            text = re.sub(pattern, lambda m: replacement.format_map(_Blank(values)), text, count=1)
            runs[0].text = text
            runs[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for t in runs[1:]:
                t.text = ""


class _Blank(dict):
    """format_map helper: unknown {fields} become empty instead of raising."""

    def __missing__(self, key):
        return ""


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
    for i, ((tag, kind), rid) in enumerate(sorted(refs.items())):
        el = etree.Element(tag)
        el.set(w("type"), kind)
        el.set(f"{{{R_NS}}}id", rid)
        new.insert(i, el)
    importer.remap(new)
    old = body.find(w("sectPr"))
    if old is not None:
        body.replace(old, new)
    else:
        body.append(new)


def _map_styles(body, style, skip: set):
    in_tables = {p for tbl in body.iter(w("tbl")) for p in tbl.iter(w("p"))}
    renames = {"FirstParagraph": style.get("body"), "BodyText": style.get("body"),
               "TableCaption": style.get("caption"), "ImageCaption": style.get("caption")}
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
    roots = [out.xml(n) for n in ("word/document.xml", "word/footnotes.xml") if n in out.parts]

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
    for name, root in zip(("word/document.xml", "word/footnotes.xml"), roots):
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
