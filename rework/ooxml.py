"""Minimal helpers for reading, editing and writing .docx packages."""
import posixpath
import zipfile

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def rels_name(part: str) -> str:
    folder, base = posixpath.split(part)
    return posixpath.join(folder, "_rels", base + ".rels")


class Package:
    """A .docx file held in memory as {part name: bytes}."""

    def __init__(self, path: str):
        with zipfile.ZipFile(path) as z:
            self.parts = {name: z.read(name) for name in z.namelist()}

    def xml(self, name: str) -> etree._Element:
        return etree.fromstring(self.parts[name])

    def set_xml(self, name: str, root: etree._Element) -> None:
        self.parts[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def save(self, path: str) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in self.parts.items():
                z.writestr(name, data)


def style_names(styles: etree._Element) -> dict[str, str]:
    """styleId -> lower-case display name."""
    out = {}
    for s in styles.iter(w("style")):
        name = s.find(w("name"))
        out[s.get(w("styleId"))] = name.get(w("val")).lower() if name is not None else ""
    return out


def sections(body: etree._Element) -> list[tuple[list[etree._Element], etree._Element]]:
    """Split a document body into (elements, sectPr) per section, in order."""
    out, current = [], []
    for el in body:
        if el.tag == w("sectPr"):
            out.append((current, el))
            current = []
            continue
        current.append(el)
        sect = el.find(f"./{w('pPr')}/{w('sectPr')}")
        if sect is not None:
            out.append((current, sect))
            current = []
    return out


KNOWN_TYPES = {
    "ttf": "application/x-font-ttf",
    "otf": "application/x-font-opentype",
    "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "emf": "image/x-emf",
    "wmf": "image/x-wmf",
}


def register_content_types(pkg: Package, fallback: Package) -> None:
    """Give every part a content type. Word reports a file as corrupt when one is missing;
    pandoc leaves embedded template fonts without one."""
    types = pkg.xml("[Content_Types].xml")
    overrides = {o.get("PartName") for o in types if o.tag == f"{{{CT_NS}}}Override"}
    defaults = {d.get("Extension").lower() for d in types if d.tag == f"{{{CT_NS}}}Default"}
    known = dict(KNOWN_TYPES)
    for d in fallback.xml("[Content_Types].xml"):
        if d.tag == f"{{{CT_NS}}}Default":
            known[d.get("Extension").lower()] = d.get("ContentType")
    added = False
    for name in pkg.parts:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if name == "[Content_Types].xml" or "/" + name in overrides or ext in defaults or ext not in known:
            continue
        types.insert(0, etree.Element(f"{{{CT_NS}}}Default", Extension=ext, ContentType=known[ext]))
        defaults.add(ext)
        added = True
    if added:
        pkg.set_xml("[Content_Types].xml", types)


class Importer:
    """Copies parts referenced from a template into an output package, fixing relationships."""

    def __init__(self, src: Package, dst: Package):
        self.src, self.dst = src, dst
        self.copied: dict[str, str] = {}
        self.new_rids: dict[str, str] = {}
        self.src_doc_rels = {r.get("Id"): r for r in src.xml("word/_rels/document.xml.rels")}
        self.dst_doc_rels = dst.xml("word/_rels/document.xml.rels")
        self.dst_types = dst.xml("[Content_Types].xml")
        src_types = src.xml("[Content_Types].xml")
        self.src_overrides = {o.get("PartName"): o.get("ContentType")
                              for o in src_types if o.tag == f"{{{CT_NS}}}Override"}
        self.src_defaults = {d.get("Extension").lower(): d.get("ContentType")
                             for d in src_types if d.tag == f"{{{CT_NS}}}Default"}

    def remap(self, el: etree._Element) -> None:
        """Point every relationship id inside `el` at a copy of the template's target."""
        for node in el.iter():
            for key, value in list(node.attrib.items()):
                if key.startswith(f"{{{R_NS}}}") and value in self.src_doc_rels:
                    node.set(key, self._rid(value))

    def finish(self) -> None:
        self.dst.set_xml("word/_rels/document.xml.rels", self.dst_doc_rels)
        self.dst.set_xml("[Content_Types].xml", self.dst_types)

    def _rid(self, old: str) -> str:
        if old in self.new_rids:
            return self.new_rids[old]
        rel = self.src_doc_rels[old]
        new_id = f"rIdRework{len(self.new_rids) + 1}"
        copy = etree.SubElement(self.dst_doc_rels, f"{{{PKG_REL_NS}}}Relationship",
                                Id=new_id, Type=rel.get("Type"))
        if rel.get("TargetMode") == "External":
            copy.set("Target", rel.get("Target"))
            copy.set("TargetMode", "External")
        else:
            part = self._part(posixpath.normpath(posixpath.join("word", rel.get("Target"))))
            copy.set("Target", posixpath.relpath(part, "word"))
        self.new_rids[old] = new_id
        return new_id

    def _part(self, name: str) -> str:
        if name in self.copied:
            return self.copied[name]
        folder, base = posixpath.split(name)
        new = posixpath.join(folder, "tpl_" + base)
        self.copied[name] = new
        self.dst.parts[new] = self.src.parts[name]
        if rels_name(name) in self.src.parts:
            rels = self.src.xml(rels_name(name))
            for rel in rels:
                target = posixpath.normpath(posixpath.join(folder, rel.get("Target", "")))
                if rel.get("TargetMode") != "External" and target in self.src.parts:
                    rel.set("Target", posixpath.relpath(self._part(target), folder))
            self.dst.set_xml(rels_name(new), rels)
        self._content_type(name, new)
        return new

    def _content_type(self, old: str, new: str) -> None:
        if "/" + old in self.src_overrides:
            etree.SubElement(self.dst_types, f"{{{CT_NS}}}Override",
                             PartName="/" + new, ContentType=self.src_overrides["/" + old])
            return
        ext = new.rsplit(".", 1)[-1].lower()
        have = {d.get("Extension").lower() for d in self.dst_types if d.tag == f"{{{CT_NS}}}Default"}
        if ext not in have and ext in self.src_defaults:
            default = etree.Element(f"{{{CT_NS}}}Default", Extension=ext, ContentType=self.src_defaults[ext])
            self.dst_types.insert(0, default)
