"""
A business's look from its own website, for "create an agent for me" (agent/builder.py): its name, logo, colours and
font, read from the home page and its stylesheets with the public-only client (netsafe). No paid service.

Colours, strongest signal first: <meta name="theme-color">; CSS custom properties named like primary, brand, accent or
theme; the backgrounds of buttons and calls to action; then the saturated colours the stylesheets use most. Greys,
near-white and near-black are never a brand colour. The text on the brand colour is white or near-black, whichever
reads better (WCAG contrast). Sites that draw their look only with JavaScript give fewer signals: the colours list is
then shorter or empty, and the builder falls back to Nimmi's plum.
"""
import asyncio
import colorsys
import logging
import re
from collections import Counter
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
VARIABLE = re.compile(r"--([\w-]*?(?:primary|brand|accent|theme|main)[\w-]*)\s*:\s*([^;{}]+)", re.I)
BUTTONISH = re.compile(r"([^{}]*(?:\bbtn\b|button|\.cta|primary|navbar|header)[^{}]*)\{([^{}]*)\}", re.I)
BACKGROUND = re.compile(r"background(?:-color)?\s*:\s*([^;{}!]+)", re.I)
FONT_FAMILY = re.compile(r"(?:^|[;{\s])font-family\s*:\s*([^;{}]+)", re.I)
MAX_HTML, MAX_CSS, MAX_SHEETS = 3 * 1024 * 1024, 600 * 1024, 4
DEFAULT = "#550a64"  # Nimmi's plum, when a site gives nothing to go on


def to_hex(value: str) -> Optional[str]:
    value = (value or "").strip()
    m = HEX.search(value)
    if m:
        h = m.group(1)
        return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h).lower()
    m = RGB.search(value)
    if m and all(int(x) <= 255 for x in m.groups()):
        return "#" + "".join(f"{int(x):02x}" for x in m.groups())
    return None


def _hls(hex_: str) -> tuple[float, float, float]:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def usable(hex_: str) -> bool:
    """A colour that can be a brand colour: not grey, not near white or near black."""
    _, light, sat = _hls(hex_)
    return sat >= 0.2 and 0.12 <= light <= 0.9


def luminance(hex_: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(int(hex_[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(background: str) -> str:
    """White or near-black text on this colour, whichever reads better."""
    return "#ffffff" if contrast(background, "#ffffff") >= contrast(background, "#111827") else "#111827"


def _name(soup: BeautifulSoup, url: str) -> str:
    for attrs in ({"property": "og:site_name"}, {"name": "application-name"}, {"name": "apple-mobile-web-app-title"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()[:60]
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    if title:
        parts = [p.strip() for p in re.split(r"\s[|\-–—:·]\s|\s[|–—]\s?", title) if p.strip()]
        # "Home | Sri Dental Care" or "Sri Dental Care - Best dentist in Chennai": the shortest part that isn't "Home".
        parts = [p for p in parts if p.lower() not in ("home", "welcome", "home page", "official website")] or parts
        return min(parts, key=len)[:60] if parts else title[:60]
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title() if host else ""


def _logo(soup: BeautifulSoup, url: str) -> Optional[str]:
    candidates: list[tuple[int, str]] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        label = " ".join([src, img.get("alt", ""), " ".join(img.get("class", [])), img.get("id", "")]).lower()
        if src and "logo" in label and not src.startswith("data:"):
            candidates.append((3 if img.find_parent(["header", "nav"]) else 2, src))
    for link in soup.find_all("link", rel=True):
        rel = " ".join(link.get("rel")).lower()
        if ("apple-touch-icon" in rel or "icon" in rel) and link.get("href"):
            sizes = re.findall(r"(\d+)x\d+", link.get("sizes", ""))
            size = max(map(int, sizes), default=180 if "apple" in rel else 32)
            candidates.append((1 if size >= 120 else 0, link["href"]))
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        candidates.append((0, og["content"]))
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c[0])[1]
    return urljoin(url, best)


def _font(soup: BeautifulSoup, css: str) -> Optional[str]:
    """The builder's font that matches the site's main font, if it has one (agent/tools/changes.FONTS)."""
    from agent.tools.changes import FONTS
    families = [m.group(1) for m in FONT_FAMILY.finditer(css)]
    for link in soup.find_all("link", href=True):
        if "fonts.googleapis.com" in link["href"]:
            families += re.findall(r"family=([^:&]+)", link["href"])
    for family in families:
        first = family.split(",")[0].strip().strip("'\"").replace("+", " ").lower()
        for label in FONTS:
            if label.split(" (")[0].lower() == first:
                return label
    return None


def from_page(html: str, url: str, css: str = "") -> dict:
    """The look from a page's HTML and its stylesheets' text (no network here)."""
    soup = BeautifulSoup(html, "html.parser")
    inline = "\n".join(s.get_text() for s in soup.find_all("style"))
    styles = inline + "\n" + css
    scores: Counter = Counter()
    theme = soup.find("meta", attrs={"name": "theme-color"})
    if theme and (h := to_hex(theme.get("content", ""))) and usable(h):
        scores[h] += 50
    for name, value in VARIABLE.findall(styles):
        if (h := to_hex(value)) and usable(h):
            scores[h] += 30 if "primary" in name.lower() or "brand" in name.lower() else 15
    for selector, body in BUTTONISH.findall(styles):
        for value in BACKGROUND.findall(body):
            if (h := to_hex(value)) and usable(h):
                scores[h] += 6
    for m in HEX.finditer(styles):
        h = to_hex(m.group(0))
        if h and usable(h):
            scores[h] += 1
    for el in soup.find_all(style=True):  # colours set right on the page's elements
        for value in BACKGROUND.findall(el["style"]):
            if (h := to_hex(value)) and usable(h):
                scores[h] += 3
    colours: list[str] = []
    for h, _ in scores.most_common(12):  # distinct colours only: skip shades a step away from one already chosen
        hue, light, _sat = _hls(h)
        if all(abs(hue - _hls(c)[0]) > 0.04 or abs(light - _hls(c)[1]) > 0.15 for c in colours):
            colours.append(h)
        if len(colours) == 3:
            break
    primary = colours[0] if colours else DEFAULT
    return {"name": _name(soup, url), "logo": _logo(soup, url), "colours": colours, "primary": primary,
            "text_on_primary": text_on(primary), "font": _font(soup, styles), "found_colours": bool(colours)}


async def extract(url: str) -> dict:
    """The look of the website at `url`: its home page and up to MAX_SHEETS of its own stylesheets."""
    from crawler import _get
    from netsafe import safe_client
    async with safe_client(timeout=15.0, follow_redirects=True) as client:
        final_url, _ctype, body = await _get(client, url, MAX_HTML)
        html = body.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        host = (urlparse(final_url).hostname or "").removeprefix("www.")
        sheets = []
        for link in soup.find_all("link", href=True):
            if "stylesheet" in " ".join(link.get("rel") or []).lower():
                href = urljoin(final_url, link["href"])
                if (urlparse(href).hostname or "").removeprefix("www.").endswith(host):
                    sheets.append(href)

        async def fetch(href: str) -> str:
            try:
                return (await _get(client, href, MAX_CSS))[2].decode("utf-8", errors="replace")
            except Exception as e:  # a stylesheet that won't load: the others still count
                logger.info(f"brand: stylesheet {href} skipped: {e}")
                return ""
        css = "\n".join(await asyncio.gather(*(fetch(h) for h in sheets[:MAX_SHEETS])))
    asked = (urlparse(url).hostname or "").removeprefix("www.")
    moved = host if host and asked and host != asked and not host.endswith("." + asked) else None
    return {**from_page(html, final_url, css), "url": final_url, "moved_to": moved}  # moved_to: a different site answered
