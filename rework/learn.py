"""Work out a template's house style: which of its styles, sections and cover to use."""
import re
from collections import Counter

from .ooxml import R_NS, STYLE_KEYS, Package, sections, style_names, w

GUIDANCE = ("comment", "instruction", "guidance", "placeholder", "hint", "note to")
SKIP_NAMES = ("heading", "title", "subtitle", "toc", "caption", "list", "header", "footer", "footnote")


def _pstyle(p) -> str | None:
    ps = p.find(f"./{w('pPr')}/{w('pStyle')}")
    return ps.get(w("val")) if ps is not None else None


FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
PAGE_NUMBER = re.compile(r"^[\divxlcIVXLC_|\s.-]*$")  # "2", "iv", "_3_": field results, not placeholders


def _text(el, tabs: bool = False) -> str:
    """Visible text; Word stores each text box twice (a modern copy and a fallback), count it once."""
    return "".join(("\t" if n.tag != w("t") else n.text or "") for n in el.iter(w("t"), w("tab"), w("ptab"))
                   if (tabs or n.tag == w("t")) and not any(a.tag == FALLBACK for a in n.iterancestors()))


def _lines(elements) -> list[str]:
    """One entry per innermost paragraph, so text boxes aren't glued onto the paragraph holding them."""
    lines = []
    for el in elements:
        for p in el.iter(w("p")):
            # Tabs separate fields ("Title<tab>Study<tab>Number"); list each field on its own,
            # since that is the text a replace pair can match.
            text = _text(p, tabs=True) if p.find(f".//{w('p')}") is None else ""
            for part in (t.strip() for t in text.split("\t")):
                if part and part not in lines:
                    lines.append(part)
    return lines


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
    # The cover's own big heading ("Report title goes here") is not a chapter.
    after_cover = set(list(body)[_cover(list(body), names):])
    chapters = [sum(1 for el in elements if el in after_cover for p in el.iter(w("p"))
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
    # Template guidance ("Comment", "Instructions") fills sample cells but is not the house cell style.
    cell_styles = Counter(sid for sid in (_pstyle(p) or default for p in in_tables if _text(p).strip())
                          if not any(k in names.get(sid, "") for k in GUIDANCE))
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

    # Data tables, not layout ones (a one-row table placing an equation number, a borderless glossary
    # in the front matter): count tables with 2+ rows, in the body section when it has any.
    def data_tables(els):
        return [t for el in els for t in el.iter(w("tbl")) if len(t.findall(w("tr"))) >= 2]
    tables = data_tables(scope) or data_tables(body)
    table_styles = Counter(t.find(f"{w('tblPr')}/{w('tblStyle')}").get(w("val")) for t in tables
                           if t.find(f"{w('tblPr')}/{w('tblStyle')}") is not None
                           and names.get(t.find(f"{w('tblPr')}/{w('tblStyle')}").get(w("val"))) != "normal table")
    # A dedicated table-text style beats what the template's sample tables happen to use.
    table_text = next((sid for sid, name in names.items()
                       if name == "table" or ("table" in name and any(k in name for k in ("text", "contents", "body"))
                                              and "head" not in name)), None)
    style = {
        "body": body_chars.most_common(1)[0][0] if body_chars else default,
        "table": table_styles.most_common(1)[0][0] if table_styles else None,
        "table_cell": table_text or (cell_styles.most_common(1)[0][0] if cell_styles else None),
        "list": list_styles.most_common(1)[0][0] if list_styles else _by_name(names, "list paragraph"),
        **_captions(names, body),
        "quote": _by_name(names, "quote") or _by_name(names, "block text"),
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
    # Front matter often runs past the cover (title page, declarations, copyright): offer every
    # place it can be cut, up to where the body section's text starts.
    section_start = sum(len(els) for els, _ in secs[:body_section])
    front = max(section_start, _first_heading(elements, names, start=candidate), candidate)
    style["front_end"] = front
    later = sum(len(_text(e).strip()) for e in elements[style["cover"]:front])
    if style["cover"] and later:
        style["cover_note"] = ("The template's front matter continues after the cover (title page, declarations, "
                               "contents...). To copy more of it, set \"cover\" to a number from cover_choices.")
    if "cover_note" in style:
        style["cover_choices"] = _cover_choices(elements[:front])
    style["cover_lines"] = _lines(elements[:candidate])
    levels = sorted({int(n[8:]) for n in (names.get(_pstyle(p) or "", "") for el in scope for p in el.iter(w("p")))
                     if re.fullmatch(r"heading [1-9]", n)})
    numbered_by_hand = [p for el in scope for p in el.iter(w("p"))
                        if names.get(_pstyle(p) or "", "") == "heading 1"
                        and p.find(f"{w('pPr')}/{w('numPr')}") is not None]
    if numbered_by_hand:
        style["numbering_note"] = ("The template numbers its headings paragraph by paragraph, which is not copied. "
                                   "Pass -- --number-sections to number yours.")
    if levels and levels[0] > 1:
        style["heading_note"] = (f"The template's sections start at Heading {levels[0]}. Pass "
                                 f"-- --shift-heading-level-by={levels[0] - 1} so that # headings use it.")
    style["header_lines"] = _header_lines(pkg, secs[: style["body_section"] + 1])
    style["replace"] = []
    # Report display names, which people recognise ("摘要", "Body Text"), rather than ids ("af1").
    display = style_names(styles, lower=False)
    for key in STYLE_KEYS:
        if style.get(key):
            style[key] = display.get(style[key]) or style[key]
    return style


def _cover_choices(elements, limit: int = 60) -> dict[str, str]:
    """"cover" value -> the last thing it copies, so front matter can be cut at a chosen line or break."""
    choices = {}
    for i, el in enumerate(elements, 1):
        text = _text(el).strip()
        if is_toc(el):
            choices[str(i)] = "[sample table of contents: don't copy, use -- --toc]"
        elif el.find(f".//{w('sectPr')}") is not None:
            choices[str(i)] = (text[:40] + " " if text else "") + "[section break]"
        elif any(b.get(w("type")) == "page" for b in el.iter(w("br"))):
            choices[str(i)] = (text[:40] + " " if text else "") + "[page break]"
        elif text:
            choices[str(i)] = text[:60]
    return dict(list(choices.items())[:limit])


def _first_heading(elements, names, start: int = 0) -> int:
    return next((i for i, el in enumerate(elements) if i >= start and names.get(_pstyle(el) or "", "") == "heading 1"
                 and _text(el).strip()), len(elements))


def _captions(names: dict[str, str], body) -> dict:
    """The template's caption styles: the ones its own captions use, else the standard names."""
    used = Counter(_pstyle(p) for p in body.iter(w("p")) if "caption" in names.get(_pstyle(p) or "", ""))
    candidates = [sid for sid, _ in used.most_common()] + [sid for sid, n in names.items() if "caption" in n]

    def pick(*words):
        return next((sid for sid in candidates if any(k in names[sid] for k in words)), None)

    return {
        "caption": candidates[0] if candidates else None,
        "table_caption": _by_name(names, "table caption") or pick("table"),
        "figure_caption": _by_name(names, "image caption") or _by_name(names, "figure caption")
        or pick("figure", "image", "chart"),
    }


def _header_lines(pkg: Package, secs) -> list[str]:
    """Text in the headers and footers the body uses, where placeholders also hide."""
    rels = {r.get("Id"): r.get("Target") for r in pkg.xml("word/_rels/document.xml.rels")}
    lines = []
    for _, sect in secs:
        for ref in sect.iter(w("headerReference"), w("footerReference")):
            name = "word/" + rels.get(ref.get(f"{{{R_NS}}}id"), "")
            if name in pkg.parts:
                lines += [t for t in _lines([pkg.xml(name)]) if t not in lines and not PAGE_NUMBER.match(t)]
    return lines


COVER_MAX_CHARS = 400  # a cover is a short page; longer front matter is not copied


def _breaks_before(el) -> bool:
    return (el.find(f".//{w('pageBreakBefore')}") is not None
            or any(b.get(w("type")) == "page" for b in el.iter(w("br"))))


def is_toc(el) -> bool:
    gallery = el.find(f".//{w('docPartGallery')}")
    return el.tag == w("sdt") and gallery is not None and "contents" in (gallery.get(w("val")) or "").lower()


def _cover(elements: list, names: dict[str, str]) -> int:
    """Number of leading body elements that may form a cover page (0 if none).

    The candidate ends at the first page or section break, or just before a table of contents
    (and its "Contents" title). `_cover_ok` then checks it is short and has some text.
    """
    end = 0
    for i, el in enumerate(elements):
        if is_toc(el):
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
