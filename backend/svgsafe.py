"""
SVG uploads made safe. An SVG is a document, not only a picture: it can carry scripts, event handlers,
links, animations that rewrite links, and whole web pages (foreignObject). Logos and chat backgrounds
are shown on customers' websites and anyone can open the file from its link. Supabase storage serves SVGs
as downloads under a sandbox policy (seen Oct 2026) and /static is sandboxed too, but the file must be
harmless wherever it ends up, so an uploaded SVG is never stored as sent.

clean() reads it and writes a new file with only the drawing elements and attributes listed below.
Everything else goes: scripts, foreignObject, animation, links (what they draw stays), anything in
another namespace (XHTML, editor data), event handlers, references outside the file (only "#id" and
embedded PNG/JPEG/GIF/WebP pictures stay), @import and outside url() in CSS, comments, processing
instructions and the DTD. Simple entities, which Illustrator writes, are expanded first; anything else
in a DTD makes the file unreadable rather than risky.

Shown through <img> or CSS, as everywhere in Nimmi, an SVG never runs scripts anyway: this protects
the file itself.
"""
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

MAX_BYTES = 1024 * 1024
MAX_ELEMENTS = 20_000
MAX_DEPTH = 100

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

KEEP = {
    "svg", "g", "defs", "symbol", "use", "switch", "title", "desc", "style",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "image", "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "pattern", "clipPath", "mask", "marker", "filter",
    "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite", "feConvolveMatrix", "feDiffuseLighting",
    "feDisplacementMap", "feDistantLight", "feDropShadow", "feFlood", "feFuncA", "feFuncB", "feFuncG", "feFuncR",
    "feGaussianBlur", "feMerge", "feMergeNode", "feMorphology", "feOffset", "fePointLight", "feSpecularLighting",
    "feSpotLight", "feTile", "feTurbulence",
}
UNWRAP = {"a"}  # a link can't be followed from a picture: what it draws stays, the link goes
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
TEXT = {"text", "tspan", "textPath"}

NOT_SVG = "Upload a PNG, JPG, WebP, GIF or SVG image"
TOO_BIG = "SVG images must be 1 MB or smaller."
UNREADABLE = "This SVG couldn't be read. Export it again as SVG, or upload a PNG."
TOO_DETAILED = "This SVG is too detailed. Simplify it, or upload a PNG."
NOTHING_LEFT = "This SVG has nothing to show once scripts and links are taken out. Upload a plain SVG or a PNG."

_ATTR = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_LOCAL_REF = re.compile(r"#[A-Za-z_][\w.:-]*")
_PICTURE = re.compile(r"data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+", re.I)
_SIZE = re.compile(r"\s*(\d+(?:\.\d+)?|\.\d+)\s*(?:px)?\s*")
_IMPORT = re.compile(r"@import[^;]*;?", re.I)
_URL = re.compile(r"url\(\s*([\"']?)(.*?)\1\s*\)", re.I | re.S)
_CSS_RISKY = re.compile(r"url\(|image-set\(|image\(|cross-fade\(|element\(|expression\(|javascript:|vbscript:|"
                        r"-moz-binding|behavior\s*:|\\|<", re.I)
_SCHEMES = ("javascript:", "vbscript:", "data:")
_ENCODING = re.compile(rb"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']")
_DECLARATION = re.compile(r"^﻿?\s*<\?xml[^>]*\?>")
_DOCTYPE = re.compile(r"<!DOCTYPE\s[^\[>]*(?:\[(.*?)\])?\s*>", re.I | re.S)
_ENTITY = re.compile(r"<!ENTITY\s+([A-Za-z_][\w.-]*)\s+([\"'])([^\"'&%<]{0,500})\2\s*>")
_ENTITY_REF = re.compile(r"&([A-Za-z_][\w.-]*);")
_PREDEFINED = {"amp", "lt", "gt", "quot", "apos"}


class SvgError(ValueError):
    pass


def looks_like_svg(data: bytes) -> bool:
    """Starts like a markup file and has an <svg> element near the top. clean() decides for sure."""
    head = data[:65536]
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        head = head.decode("utf-16", "ignore").encode()
    head = head.removeprefix(b"\xef\xbb\xbf").lstrip()
    return head.startswith(b"<") and re.search(rb"<svg[\s>/]", head) is not None


def clean(data: bytes) -> bytes:
    """The SVG rebuilt from its safe parts (UTF-8). Raises SvgError with a message for the person uploading."""
    if len(data) > MAX_BYTES:
        raise SvgError(TOO_BIG)
    root = _parse(_without_dtd(_decode(data)))
    if _split(root.tag, SVG_NS) != (SVG_NS, "svg"):  # an <svg> written without its namespace is read as one
        raise SvgError(NOT_SVG)
    writer = _Writer(SVG_NS if root.tag == "svg" else None)
    writer.element(root, 0)
    if not writer.drawn:
        raise SvgError(NOTHING_LEFT)
    return "".join(writer.out).encode("utf-8")


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    else:
        declared = _ENCODING.match(data)
        encoding = declared.group(1).decode() if declared else "utf-8"
        if encoding.lower() in ("utf-8", "utf8"):
            encoding = "utf-8-sig"
    try:
        return data.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        raise SvgError(UNREADABLE)


def _without_dtd(text: str) -> str:
    """The text without its XML declaration and DTD; the DTD's simple entities are expanded in place."""
    text = _DECLARATION.sub("", text, count=1)
    entities = {}
    doctype = _DOCTYPE.search(text)
    if doctype:
        for name, _, value in _ENTITY.findall(doctype.group(1) or ""):
            if name not in _PREDEFINED and len(entities) < 50:
                entities[name] = value
        text = text[:doctype.start()] + text[doctype.end():]
    if re.search(r"<!(?:DOCTYPE|ENTITY)", text, re.I):
        raise SvgError(UNREADABLE)
    if entities:
        text = _ENTITY_REF.sub(lambda ref: entities.get(ref.group(1), ref.group(0)), text)
        if len(text) > 2 * MAX_BYTES:
            raise SvgError(TOO_DETAILED)
    return text


class _Counting(ET.TreeBuilder):
    """Stops a file with too many elements before it's all in memory."""

    def __init__(self):
        super().__init__()
        self.elements = 0

    def start(self, tag, attrs):
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise SvgError(TOO_DETAILED)
        return super().start(tag, attrs)


def _parse(text: str) -> ET.Element:
    parser = ET.XMLParser(target=_Counting())
    try:
        parser.feed(text)
        return parser.close()
    except ET.ParseError:
        raise SvgError(UNREADABLE)


def _split(tag: str, default):
    if tag[:1] == "{":
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return default, tag


def _css(text: str) -> str:
    """CSS without @import and with url() only to "#id" in this file; "" if anything else could load or run."""
    text = _IMPORT.sub("", text)
    text = _URL.sub(lambda m: f"url({m.group(2).strip()})" if _LOCAL_REF.fullmatch(m.group(2).strip()) else "none", text)
    return "" if _CSS_RISKY.search(_URL.sub("", text)) else text


def _value(element: str, name: str, value: str):
    """What to keep of an attribute's value, or None to drop the attribute."""
    if name in ("href", "xlink:href"):
        ref = value.strip()
        return ref if _LOCAL_REF.fullmatch(ref) or (element == "image" and _PICTURE.fullmatch(ref)) else None
    if name == "style" or "url(" in value.lower():
        return _css(value) or None
    compact = re.sub(r"[\s\x00-\x1f]+", "", value).lower()
    return None if any(s in compact for s in _SCHEMES) else value


def _attributes(element: str, attrib: dict) -> list:
    kept = []
    for key, value in attrib.items():
        ns, local = _split(key, None)
        if ns is None and _ATTR.fullmatch(local) and not local.lower().startswith("on"):
            name = local
        elif (ns, local) == (XLINK_NS, "href"):
            name = "xlink:href"
        elif ns == XML_NS and local in ("space", "lang"):
            name = f"xml:{local}"
        else:
            continue
        value = _value(element, name, value)
        if value is not None:
            kept.append((name, value))
    return kept


class _Writer:
    def __init__(self, default_ns):
        self.default_ns = default_ns
        self.out = []
        self.drawn = False

    def element(self, el: ET.Element, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise SvgError(TOO_DETAILED)
        ns, local = _split(el.tag, self.default_ns)
        if ns == SVG_NS and local in UNWRAP:
            self.content(el, depth)
        elif ns == SVG_NS and local == "style":
            css = _css("".join(el.itertext()))
            if css.strip():
                self.out.append(f"<style>{escape(css)}</style>")
        elif ns == SVG_NS and local in KEEP:
            attrs = _attributes(local, el.attrib)
            if depth == 0:
                attrs = [("xmlns", SVG_NS), ("xmlns:xlink", XLINK_NS)] + _with_view_box(attrs)
            names = {name for name, _ in attrs}
            if local in SHAPES or (local in ("image", "use") and names & {"href", "xlink:href"}) \
                    or (local in TEXT and "".join(el.itertext()).strip()):
                self.drawn = True
            start = "<" + local + "".join(f" {name}={quoteattr(value)}" for name, value in attrs)
            if el.text or len(el):
                self.out.append(start + ">")
                self.content(el, depth)
                self.out.append(f"</{local}>")
            else:
                self.out.append(start + "/>")
        if el.tail and depth:
            self.out.append(escape(el.tail))

    def content(self, el: ET.Element, depth: int) -> None:
        if el.text:
            self.out.append(escape(el.text))
        for child in el:
            self.element(child, depth + 1)


def _with_view_box(attrs: list) -> list:
    """Without a viewBox, a picture drawn smaller than its width and height is cut off instead of scaled."""
    given = dict(attrs)
    width, height = _SIZE.fullmatch(given.get("width", "")), _SIZE.fullmatch(given.get("height", ""))
    if "viewBox" in given or not (width and height):
        return attrs
    return attrs + [("viewBox", f"0 0 {width.group(1)} {height.group(1)}")]
