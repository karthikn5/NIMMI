"""
A design (mail/designs.py) made into an email: HTML that mail apps show well (tables, inline styles, 560 px wide, the
business's colour on its buttons) and the same in plain text. Placeholders take a fallback: {{first_name|there}}. A
block with nothing to show (no files, no AI note, a button without its address) is left out. Links can be tracked:
`link(url, kind, label)` returns the address to put in the email (mail/links.py).
"""
import html
import re
from dataclasses import dataclass
from typing import Callable, Optional

from mail.designs import WORDS

DEFAULT_COLOR = "#550a64"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
INK, MUTED, LINE = "#1c1719", "#78716c", "#e8e5e0"
GMAIL_CLIPS = 100_000  # Gmail shows "message clipped" past about 102 KB of HTML
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*(?:\|([^}]*))?\}\}")
_URL = re.compile(r"https?://[^\s<>\"')\]]+")


@dataclass
class Brand:
    name: str                   # the business, as the email is signed
    color: str = DEFAULT_COLOR
    logo: Optional[str] = None  # a PNG or JPEG address; mail apps don't show SVG or data: images


@dataclass
class Rendered:
    subject: str
    html: str
    text: str
    preheader: str


def brand_of(visual: Optional[dict], name: str) -> Brand:
    visual = visual or {}
    color = str(visual.get("color") or visual.get("primaryColor") or "")
    if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}){1,2}", color):
        color = DEFAULT_COLOR
    logo = str(visual.get("logo_url") or visual.get("botLogo") or "")
    usable = logo.startswith("https://") and not re.search(r"\.svg(\?|$)", logo, re.I)
    return Brand(name=name, color=color, logo=logo if usable else None)


def fill(template: str, values: dict) -> str:
    """Placeholders filled in; an empty one takes its fallback ({{first_name|there}}) or nothing."""
    def sub(m):
        value = values.get(m.group(1).lower())
        value = str(value).strip() if value not in (None, "") else ""
        return value or (m.group(2) or "")
    out = _PLACEHOLDER.sub(sub, template or "")
    out = re.sub(r"[ \t]+([,.!?])", r"\1", out)  # "Hi ," when there was no name
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _on(color: str) -> str:
    """Text colour readable on the business's colour."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#ffffff" if lum < 0.6 else INK


def email(design: dict, values: dict, brand: Brand, *, language: str = "en", unsubscribe_url: Optional[str] = None,
          link: Optional[Callable[[str, str, str], str]] = None) -> Rendered:
    link = link or (lambda url, kind, label: url)
    words = WORDS.get(language) or WORDS["en"]
    actions = values.get("actions") or {}
    parts_html: list[str] = []
    parts_text: list[str] = []
    preheader = ""
    p_style = f"margin:0 0 14px;font-family:{FONT};font-size:15px;line-height:1.6;color:{INK}"

    def paragraphs(text: str) -> tuple[str, str]:
        blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
        out = []
        for b in blocks:
            safe = html.escape(b)
            safe = _URL.sub(lambda m: f'<a href="{html.escape(link(html.unescape(m.group(0)), "link", ""))}" style="color:{brand.color}">'
                                      f'{m.group(0)}</a>', safe)
            out.append(f'<p style="{p_style}">{safe.replace(chr(10), "<br>")}</p>')
        return "".join(out), "\n\n".join(b.strip() for b in blocks)

    def button(label: str, url: str) -> tuple[str, str]:
        return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 16px"><tr>'
                f'<td style="border-radius:6px;background:{brand.color}"><a href="{html.escape(url)}" '
                f'style="display:inline-block;padding:11px 20px;font-family:{FONT};font-size:15px;font-weight:600;'
                f'color:{_on(brand.color)};text-decoration:none;border-radius:6px">{html.escape(label)}</a></td></tr></table>',
                f"{label}: {url}")

    def heading(text: str) -> tuple[str, str]:
        return (f'<p style="margin:20px 0 8px;font-family:{FONT};font-size:13px;font-weight:600;letter-spacing:.02em;'
                f'text-transform:uppercase;color:{MUTED}">{html.escape(text)}</p>', text.upper())

    for block in design.get("blocks") or []:
        kind = block.get("type")
        h = t = ""
        if kind == "text":
            h, t = paragraphs(fill(block.get("text", ""), values))
            preheader = preheader or t
        elif kind == "heading":
            text = fill(block.get("text", ""), values)
            if text:
                h, t = (f'<p style="margin:6px 0 12px;font-family:{FONT};font-size:18px;font-weight:600;color:{INK}">'
                        f'{html.escape(text)}</p>', text)
        elif kind == "ai_note":
            note = str(values.get("ai_note") or "").strip()
            if note:
                h, t = paragraphs(note)
                preheader = note
        elif kind == "call_summary":
            call = values.get("call") or {}
            hs, ts = [], []
            recap = [str(x).strip() for x in call.get("recap") or [] if str(x).strip()]
            if recap:
                a, b = heading(words["talked"])
                hs.append(a + '<ul style="margin:0 0 14px;padding-left:20px">' + "".join(
                    f'<li style="{p_style};margin-bottom:6px">{html.escape(x)}</li>' for x in recap) + "</ul>")
                ts.append(b + "\n" + "\n".join(f"- {x}" for x in recap))
            answers = [a for a in call.get("answers") or [] if str(a.get("q", "")).strip() and str(a.get("a", "")).strip()]
            if answers:
                a, b = heading(words["answers"])
                hs.append(a + "".join(f'<p style="{p_style}"><strong>{html.escape(str(x["q"]))}</strong><br>{html.escape(str(x["a"]))}</p>'
                                      for x in answers))
                ts.append(b + "\n" + "\n\n".join(f"{x['q']}\n{x['a']}" for x in answers))
            next_step = str(call.get("next_step") or "").strip()
            if next_step:
                a, b = heading(words["next"])
                hs.append(a + f'<p style="{p_style}">{html.escape(next_step)}</p>')
                ts.append(f"{b}\n{next_step}")
            h, t = "".join(hs), "\n\n".join(ts)
        elif kind == "meeting":
            m = values.get("meeting") or {}
            rows = [(words["when"], m.get("when")), (words["where"], m.get("where"))]
            rows = [(k, str(v)) for k, v in rows if v]
            if rows:
                h = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 16px;'
                     f'border:1px solid {LINE};border-radius:8px"><tr><td style="padding:14px 16px">' + "".join(
                         f'<p style="margin:0 0 6px;font-family:{FONT};font-size:14px;color:{INK}"><span style="color:{MUTED}">'
                         f'{html.escape(k)}</span><br>{html.escape(v)}</p>' for k, v in rows) + "</td></tr></table>")
                t = "\n".join(f"{k}: {v}" for k, v in rows)
        elif kind == "files":
            files = values.get("files") or []
            if files:
                cards = []
                for f in files:
                    url = link(f["url"], "file", f["name"]) if f.get("url") else ""
                    size = f" ({f['size']})" if f.get("size") else ""
                    action = (f' &middot; <a href="{html.escape(url)}" style="color:{brand.color};font-weight:600">'
                              f'{html.escape(words["download"])}</a>') if url else ""
                    cards.append(f'<tr><td style="padding:10px 14px;border-top:1px solid {LINE};font-family:{FONT};font-size:14px;'
                                 f'color:{INK}">{html.escape(f["name"])}<span style="color:{MUTED}">{html.escape(size)}</span>{action}</td></tr>')
                h = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 16px;'
                     f'border:1px solid {LINE};border-radius:8px;border-collapse:separate"><tr><td style="padding:10px 14px;'
                     f'font-family:{FONT};font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.02em">'
                     f'{html.escape(words["files"])}</td></tr>' + "".join(cards) + "</table>")
                t = "\n".join(f"{f['name']}: {f['url']}" if f.get("url") else f["name"] for f in files)
        elif kind == "button":
            action = block.get("action") or "link"
            url = block.get("url") if action == "link" else actions.get(action)
            label = fill(block.get("label") or "", values)
            if url and label and str(url).startswith(("https://", "http://", "mailto:", "tel:")):
                h, t = button(label, link(str(url), action, label))
        elif kind == "details":
            details = {k: v for k, v in (values.get("details_map") or {}).items() if str(v).strip()}
            if details:
                a, b = heading(words["details"])
                h = a + "".join(f'<p style="margin:0 0 6px;font-family:{FONT};font-size:14px;color:{INK}">'
                                f'<span style="color:{MUTED}">{html.escape(str(k))}:</span> {html.escape(str(v))}</p>'
                                for k, v in details.items())
                t = b + "\n" + "\n".join(f"{k}: {v}" for k, v in details.items())
        elif kind == "transcript":
            lines = values.get("transcript") or []
            if lines:
                h = "".join(f'<p style="{p_style}"><span style="color:{MUTED}">{html.escape(str(x["who"]))}</span><br>'
                            f'{html.escape(str(x["text"]))}</p>' for x in lines)
                t = "\n\n".join(f"{x['who']}: {x['text']}" for x in lines)
        elif kind == "signature":
            who = str(values.get("signature") or brand.name).strip()
            h = f'<p style="{p_style};margin-top:6px">{html.escape(who).replace(chr(10), "<br>")}</p>'
            t = who
        elif kind == "divider":
            h, t = f'<hr style="border:0;border-top:1px solid {LINE};margin:18px 0">', "----"
        elif kind == "image":
            url = str(block.get("url") or "")
            if url.startswith("https://") and not re.search(r"\.svg(\?|$)", url, re.I):
                h = (f'<img src="{html.escape(url)}" alt="{html.escape(str(block.get("alt") or ""))}" width="504" '
                     f'style="display:block;width:100%;max-width:504px;height:auto;border:0;border-radius:6px;margin:4px 0 16px">')
                t = str(block.get("alt") or "")
        if h:
            parts_html.append(h)
        if t:
            parts_text.append(t)

    header = (f'<img src="{html.escape(brand.logo)}" alt="{html.escape(brand.name)}" height="40" style="display:block;height:40px;'
              f'width:auto;border:0">' if brand.logo else
              f'<span style="font-family:{FONT};font-size:17px;font-weight:600;color:{brand.color}">{html.escape(brand.name)}</span>')
    footer = html.escape(brand.name) + (f' &middot; <a href="{html.escape(unsubscribe_url)}" style="color:{MUTED}">Unsubscribe</a>'
                                        if unsubscribe_url else "")
    preheader = re.sub(r"\s+", " ", preheader).strip()[:140]
    body = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light"><title>{html.escape(fill(design.get("subject", ""), values))}</title></head>'
            f'<body style="margin:0;padding:0;background:#f6f5f3">'
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{html.escape(preheader)}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f5f3"><tr>'
            f'<td align="center" style="padding:24px 12px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;'
            f'border:1px solid {LINE};border-radius:8px"><tr><td style="padding:24px 28px 4px">{header}</td></tr>'
            f'<tr><td style="padding:16px 28px 10px">{"".join(parts_html)}</td></tr></table>'
            f'<p style="max-width:560px;margin:14px auto 0;font-family:{FONT};font-size:12px;color:{MUTED};text-align:center">'
            f'{footer}</p></td></tr></table></body></html>')
    text = "\n\n".join(parts_text) + (f"\n\n--\n{brand.name}\nUnsubscribe: {unsubscribe_url}" if unsubscribe_url else f"\n\n--\n{brand.name}")
    return Rendered(subject=fill(design.get("subject", ""), values)[:200], html=body, text=text, preheader=preheader)
