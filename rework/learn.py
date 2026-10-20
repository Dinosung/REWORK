"""Work out a template's house style: which of its styles, sections and cover to use."""
from collections import Counter

from .ooxml import R_NS, STYLE_KEYS, Package, sections, style_names, w

SKIP_NAMES = ("heading", "title", "subtitle", "toc", "caption", "list", "header", "footer", "footnote")


def _pstyle(p) -> str | None:
    ps = p.find(f"./{w('pPr')}/{w('pStyle')}")
    return ps.get(w("val")) if ps is not None else None


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(w("t")))


def _default_paragraph_style(styles) -> str:
    for s in styles.iter(w("style")):
        if s.get(w("type")) == "paragraph" and s.get(w("default")) in ("1", "true"):
            return s.get(w("styleId"))
    return "Normal"


def _by_name(names: dict[str, str], wanted: str) -> str | None:
    return next((sid for sid, name in names.items() if name == wanted), None)


def _is_heading(sid: str | None, names: dict[str, str]) -> bool:
    return bool(sid) and names.get(sid, "").startswith(("heading", "title"))


def learn(template_path: str) -> dict:
    """Return a style dict for `rework build`. Every field can be edited by hand."""
    pkg = Package(template_path)
    styles = pkg.xml("word/styles.xml")
    names = style_names(styles)
    body = pkg.xml("word/document.xml").find(w("body"))
    default = _default_paragraph_style(styles)

    # The body section is where the chapters are: the one with the most Heading 1 paragraphs
    # (the earliest on a tie), else the one with the most text. Front matter and appendices
    # usually have their own sections. Checked against 6 hand-labelled templates.
    secs = sections(body)
    chapters = [sum(1 for el in elements for p in el.iter(w("p"))
                    if names.get(_pstyle(p) or "") == "heading 1" and _text(p).strip())
                for elements, _ in secs]
    sizes = [sum(len(_text(el)) for el in elements) for elements, _ in secs]
    score = chapters if any(chapters) else sizes
    body_section = max(range(len(secs)), key=lambda i: (score[i], -i)) if secs else 0

    # Styles are counted in the body section, so an abstract or reference list in the front or
    # back matter isn't mistaken for body text or lists.
    scope = [el for el in secs[body_section][0]] if secs else list(body)
    paragraphs = [p for el in scope for p in el.iter(w("p"))]
    in_tables = {p for tbl in body.iter(w("tbl")) for p in tbl.iter(w("p"))}
    # Sample tables can sit anywhere, so table cells are counted across the whole template.
    cell_styles = Counter(_pstyle(p) or default for p in in_tables if _text(p).strip())
    body_chars, list_styles = Counter(), Counter()
    for p in paragraphs:
        sid = _pstyle(p) or default
        text = _text(p).strip()
        if not text or p in in_tables:
            continue
        if p.find(f"./{w('pPr')}/{w('numPr')}") is not None and not _is_heading(sid, names):
            list_styles[sid] += 1
        elif not names.get(sid, "").startswith(SKIP_NAMES):
            body_chars[sid] += len(text)

    table_styles = Counter(t.get(w("val")) for t in body.iter(w("tblStyle")))
    # A dedicated table-text style beats what the template's sample tables happen to use.
    table_text = next((sid for sid, name in names.items()
                       if "table" in name and any(k in name for k in ("text", "contents", "body"))
                       and "head" not in name), None)
    style = {
        "body": body_chars.most_common(1)[0][0] if body_chars else default,
        "table": table_styles.most_common(1)[0][0] if table_styles else None,
        "table_cell": table_text or (cell_styles.most_common(1)[0][0] if cell_styles else None),
        "list": list_styles.most_common(1)[0][0] if list_styles else _by_name(names, "list paragraph"),
        "caption": _by_name(names, "caption"),
        # pandoc's own caption style names; a template that defines them has captions styled its way.
        "table_caption": _by_name(names, "table caption"),
        "figure_caption": _by_name(names, "image caption") or _by_name(names, "figure caption"),
        # Templates that number captions do it with SEQ fields; then rework asks pandoc for them too.
        "number_captions": any("SEQ " in (n.get(w("instr")) or n.text or "")
                               for n in body.iter(w("fldSimple"), w("instrText"))),
        "body_section": body_section,
    }

    elements = list(body)
    candidate = _cover(elements, names)
    style["cover"] = candidate if _cover_ok(elements, candidate) else 0
    if candidate and not style["cover"]:
        style["cover_note"] = (f"The first {candidate} elements look like front matter but are too long to be "
                               f"sure they are a cover. Set \"cover\" to a number from cover_choices to "
                               f"copy the template up to that line ({candidate} copies all of it).")
        style["cover_choices"] = _cover_choices(elements[:candidate])
    # Cover fields need judgement (which line is the title, the client, the date), so learn
    # lists the cover's lines; a person or an agent writes `replace` as [regex, "{title}"] pairs.
    style["cover_lines"] = [t for t in (_text(p).strip() for el in elements[:candidate]
                                        for p in el.iter(w("p"))) if t]
    style["header_lines"] = _header_lines(pkg, secs[: style["body_section"] + 1])
    style["replace"] = []
    # Report display names, which people recognise ("摘要", "Body Text"), rather than ids ("af1").
    display = style_names(styles, lower=False)
    for key in STYLE_KEYS:
        if style.get(key):
            style[key] = display.get(style[key]) or style[key]
    return style


def _cover_choices(elements, limit: int = 40) -> dict[str, str]:
    """"cover" value -> the last line it copies, so a long front matter can be cut at a chosen line."""
    choices = {}
    for i, el in enumerate(elements, 1):
        text = _text(el).strip()
        if text:
            choices[str(i)] = text[:60]
    return dict(list(choices.items())[:limit])


def _header_lines(pkg: Package, secs) -> list[str]:
    """Text in the headers and footers the body uses, where placeholders also hide."""
    rels = {r.get("Id"): r.get("Target") for r in pkg.xml("word/_rels/document.xml.rels")}
    lines = []
    for _, sect in secs:
        for ref in sect.iter(w("headerReference"), w("footerReference")):
            name = "word/" + rels.get(ref.get(f"{{{R_NS}}}id"), "")
            if name in pkg.parts:
                for p in pkg.xml(name).iter(w("p")):
                    text = _text(p).strip()
                    if text and text not in lines:
                        lines.append(text)
    return lines


COVER_MAX_CHARS = 400  # a cover is a short page; longer front matter is not copied


def _breaks_before(el) -> bool:
    return (el.find(f".//{w('pageBreakBefore')}") is not None
            or any(b.get(w("type")) == "page" for b in el.iter(w("br"))))


def _is_toc(el) -> bool:
    gallery = el.find(f".//{w('docPartGallery')}")
    return el.tag == w("sdt") and gallery is not None and "contents" in (gallery.get(w("val")) or "").lower()


def _cover(elements: list, names: dict[str, str]) -> int:
    """Number of leading body elements that may form a cover page (0 if none).

    The candidate ends at the first page or section break, or just before a table of contents
    (and its "Contents" title). `_cover_ok` then checks it is short and has some text.
    """
    end = 0
    for i, el in enumerate(elements):
        if _is_toc(el):
            end = i
            if i and "contents" in _text(elements[i - 1]).lower():
                end = i - 1
            break
        if el.find(f"./{w('pPr')}/{w('sectPr')}") is not None:
            end = i + 1
            break
        if _breaks_before(el):
            # A break inside a heading starts the body on a new page; elsewhere it ends the cover.
            heading = names.get(_pstyle(el) or "", "").startswith("heading")
            end = i if heading else i + 1
            break
    return end


def _cover_ok(elements: list, end: int) -> bool:
    chars = sum(len(_text(e).strip()) for e in elements[:end])
    return 0 < chars <= COVER_MAX_CHARS
