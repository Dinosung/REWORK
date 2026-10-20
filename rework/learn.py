"""Work out a template's house style: which of its styles, sections and cover to use."""
from collections import Counter

from .ooxml import Package, sections, style_names, w

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

    in_tables = {p for tbl in body.iter(w("tbl")) for p in tbl.iter(w("p"))}
    body_chars, cell_styles, list_styles = Counter(), Counter(), Counter()
    for p in body.iter(w("p")):
        sid = _pstyle(p) or default
        text = _text(p).strip()
        if not text:
            continue
        if p in in_tables:
            cell_styles[sid] += 1
        elif p.find(f"./{w('pPr')}/{w('numPr')}") is not None and not _is_heading(sid, names):
            list_styles[sid] += 1
        elif not names.get(sid, "").startswith(SKIP_NAMES):
            body_chars[sid] += len(text)

    table_styles = Counter(t.get(w("val")) for t in body.iter(w("tblStyle")))
    style = {
        "body": body_chars.most_common(1)[0][0] if body_chars else default,
        "table": table_styles.most_common(1)[0][0] if table_styles else None,
        "table_cell": cell_styles.most_common(1)[0][0] if cell_styles else None,
        "list": list_styles.most_common(1)[0][0] if list_styles else _by_name(names, "list paragraph"),
        "caption": _by_name(names, "caption"),
    }

    # The body section is the one holding the most text; earlier sections are front matter.
    secs = sections(body)
    sizes = [sum(len(_text(el)) for el in elements) for elements, _ in secs]
    style["body_section"] = max(range(len(secs)), key=lambda i: sizes[i]) if secs else 0

    style["cover"] = _cover(list(body), names)
    # Cover fields need judgement (which line is the title, the client, the date), so learn
    # lists the cover's lines; a person or an agent writes `replace` as [regex, "{title}"] pairs.
    style["cover_lines"] = [t for t in (_text(p).strip() for el in list(body)[:style["cover"]]
                                        for p in el.iter(w("p"))) if t]
    style["replace"] = []
    return style


def _cover(elements: list, names: dict[str, str]) -> int:
    """Number of leading body elements that form a cover page, or 0 if there is none.

    A cover is everything before the first section or page break, as long as that break
    comes before the first heading and the part before it has some text.
    """
    for i, el in enumerate(elements):
        # A cover may use the Title style; a real heading means the body has started.
        if el.tag == w("p") and names.get(_pstyle(el) or "", "").startswith("heading"):
            return 0
        breaks_page = (el.find(f"./{w('pPr')}/{w('sectPr')}") is not None
                       or any(b.get(w("type")) == "page" for b in el.iter(w("br"))))
        if breaks_page:
            has_text = any(_text(e).strip() for e in elements[:i + 1])
            return i + 1 if has_text else 0
    return 0
