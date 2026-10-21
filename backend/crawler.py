"""
Reading a business's website into the assistant's knowledge.

crawl_site() reads a whole site the way a careful new employee would:
  - finds pages from the sitemap (and robots.txt) as well as by following links, several levels deep;
  - reads the important pages first (about, services, products, pricing, contact, FAQ, policies);
  - reads documents the site links to (PDF brochures, price lists, menus);
  - keeps each page's main content, and the header/footer (address, phone, hours) only once;
  - collects contact details it finds anywhere: phone and WhatsApp links, emails, social profiles.
Everything goes through the public-only HTTP client (netsafe), so it can't reach private networks.
"""
import asyncio
import io
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NimmiAIBot/1.0; +https://nimmiai.in) AppleWebKit/537.36 Chrome/120 Safari/537.36",
           "Accept-Language": "en-IN,en;q=0.9"}
SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|ico|zip|rar|mp4|mp3|wav|avi|mov|css|js|json|xml|woff2?|ttf|eot|exe|dmg|apk)$", re.I)
DOC_EXT = re.compile(r"\.pdf$", re.I)
SKIP_PATH = re.compile(r"/(wp-admin|wp-login|cart|checkout|my-account|login|signin|signup|register|logout|search|tag|author|feed)(/|$)|[?&](replytocom|add-to-cart)=", re.I)
IMPORTANT = re.compile(r"about|service|product|pric|plan|package|menu|contact|faq|help|support|policy|refund|shipping|"
                       r"location|branch|team|course|fee|offer|solution|feature|portfolio|project|gallery|book|appointment|career", re.I)
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_DOCS = 10
TIME_BUDGET = 120  # seconds for one whole crawl


def _tidy(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _clean_text(soup: BeautifulSoup) -> str:
    """Kept for callers that read a single page: all visible text without scripts, menus and footers."""
    for tag in soup(["script", "style", "header", "footer", "nav", "noscript", "svg", "form", "iframe"]):
        tag.decompose()
    return _tidy(soup.get_text("\n"))


def _page_parts(html: str, url: str) -> dict:
    """Title, main text, site-wide text (header/footer), links and contact details of one page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")[:150]
    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = meta["content"].strip()[:300]

    links, contacts = [], {"phones": set(), "emails": set(), "whatsapp": set(), "social": set()}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("tel:"):
            contacts["phones"].add(unquote(href[4:]).strip())
        elif low.startswith("mailto:"):
            contacts["emails"].add(unquote(href[7:].split("?")[0]).strip())
        elif "wa.me/" in low or "api.whatsapp.com" in low:
            contacts["whatsapp"].add(href)
        elif any(s in low for s in ("facebook.com/", "instagram.com/", "linkedin.com/", "youtube.com/", "x.com/", "twitter.com/")):
            contacts["social"].add(href.split("?")[0])
        else:
            links.append(urljoin(url, href))

    chrome = []
    for tag in soup.find_all(["header", "footer"]):
        chrome.append(tag.get_text("\n"))
        tag.decompose()
    for tag in soup.find_all(["nav", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return {"title": title, "description": description, "text": _tidy(main.get_text("\n")),
            "chrome": _tidy("\n".join(chrome)), "links": links, "contacts": contacts}


async def _get(client: httpx.AsyncClient, url: str, limit: int) -> tuple[str, str, bytes]:
    """(final url, content type, body up to `limit` bytes)."""
    async with client.stream("GET", url, headers=HEADERS) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                break
        return str(response.url), response.headers.get("content-type", ""), bytes(body)


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, list[str]]:
    """Page text and the links on it (used for a single page)."""
    final_url, ctype, body = await _get(client, url, MAX_PAGE_BYTES)
    if "html" not in (ctype or "html"):
        return "", []
    parts = _page_parts(body.decode("utf-8", errors="replace"), final_url)
    text = "\n".join(p for p in (parts["title"], parts["description"], parts["text"], parts["chrome"]) if p)
    return text, parts["links"]


async def extract_text_from_url(url: str) -> str:
    """One page's text."""
    try:
        from netsafe import safe_client
        async with safe_client(timeout=15.0, follow_redirects=True) as client:
            text, _ = await _fetch(client, url)
            return text
    except Exception as e:
        logger.error(f"Scraping Error for {url}: {e}")
        return f"Error crawling URL: {str(e)}"


def _same_site(url: str, hosts: set[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() in hosts


def _normal(url: str) -> str:
    url = urldefrag(url)[0]
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    query = "&".join(q for q in parsed.query.split("&") if q and not q.lower().startswith(("utm_", "fbclid", "gclid")))
    return f"{parsed.scheme}://{(parsed.hostname or '').lower()}{path}" + (f"?{query}" if query else "")


async def _sitemap_urls(client: httpx.AsyncClient, origin: str, hosts: set[str], cap: int) -> list[str]:
    """Page URLs listed in the site's sitemap(s), important-looking ones first."""
    candidates = [f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"]
    try:
        _, _, robots = await _get(client, f"{origin}/robots.txt", 200_000)
        candidates = [line.split(":", 1)[1].strip() for line in robots.decode("utf-8", "replace").splitlines()
                      if line.lower().startswith("sitemap:")] + candidates
    except Exception:
        pass
    found, seen_maps = [], set()
    queue = [c for c in candidates if _same_site(c, hosts)]
    while queue and len(seen_maps) < 8 and len(found) < cap * 4:
        sitemap = queue.pop(0)
        if sitemap in seen_maps:
            continue
        seen_maps.add(sitemap)
        try:
            _, _, body = await _get(client, sitemap, 5_000_000)
            root = ET.fromstring(body)
        except Exception:
            continue
        for loc in root.iter():
            if not loc.tag.endswith("loc") or not (loc.text or "").strip():
                continue
            u = loc.text.strip()
            if not _same_site(u, hosts):
                continue
            (queue if u.lower().endswith(".xml") else found).append(u)
    found.sort(key=lambda u: (not IMPORTANT.search(urlparse(u).path), urlparse(u).path.count("/"), len(u)))
    return found


def _pdf_text(body: bytes) -> str:
    from utils import extract_text_from_pdf
    text = extract_text_from_pdf(io.BytesIO(body))
    return "" if text == "Error" else _tidy(text)


async def crawl_site(url: str, max_pages: int = 25) -> list[tuple[str, str]]:
    """
    Up to `max_pages` pages of the website at `url`, plus documents it links to.
    Returns [(page url, text)]; the first block is the page at `url`, and site-wide details
    (header/footer, contact details) come last. Pages that fail or have no text are skipped.
    """
    from netsafe import safe_client

    start = _normal(url)
    parsed = urlparse(start)
    host = (parsed.hostname or "").lower()
    hosts = {host, host[4:] if host.startswith("www.") else f"www.{host}"}
    origin = f"{parsed.scheme}://{host}"
    deadline = time.monotonic() + TIME_BUDGET

    pages: dict[str, tuple[str, str]] = {}
    docs: list[tuple[str, str]] = []
    chrome_seen: dict[str, int] = {}
    contacts = {"phones": set(), "emails": set(), "whatsapp": set(), "social": set()}
    seen: set[str] = {start}
    doc_links: list[str] = []
    order: list[str] = []

    async with safe_client(timeout=15.0, follow_redirects=True) as client:
        # The start page must work: it's the one the business gave us.
        final_url, ctype, body = await _get(client, start, MAX_PAGE_BYTES)
        if DOC_EXT.search(urlparse(final_url).path) or "pdf" in ctype:
            text = _pdf_text(body)
            return [(start, text)] if text else []
        queue: list[tuple[int, str]] = []

        def consider(link: str, depth: int) -> None:
            n = _normal(link)
            if n in seen or not _same_site(n, hosts):
                return
            path = urlparse(n).path
            if DOC_EXT.search(path):
                seen.add(n)
                doc_links.append(n)
                return
            if SKIP_EXT.search(path) or SKIP_PATH.search(n):
                return
            seen.add(n)
            queue.append((depth, n))

        def absorb(page_url: str, html: str, depth: int) -> None:
            parts = _page_parts(html, page_url)
            for key in contacts:
                contacts[key] |= parts["contacts"][key]
            if parts["chrome"]:
                chrome_seen[parts["chrome"]] = chrome_seen.get(parts["chrome"], 0) + 1
            header = parts["title"] + (f"\n{parts['description']}" if parts["description"] else "")
            text = "\n".join(p for p in (header, parts["text"]) if p.strip())
            if len(parts["text"]) >= 40:
                pages[page_url] = (page_url, text)
                order.append(page_url)
            for link in parts["links"]:
                consider(link, depth + 1)

        if "html" in (ctype or "html"):
            absorb(_normal(final_url), body.decode("utf-8", errors="replace"), 0)
        for u in await _sitemap_urls(client, origin, hosts, max_pages):
            consider(u, 1)

        limit = asyncio.Semaphore(5)

        async def visit(page_url: str, depth: int):
            async with limit:
                if time.monotonic() > deadline:
                    return
                try:
                    final, kind, raw = await _get(client, page_url, MAX_PAGE_BYTES)
                    if "html" in (kind or "html"):
                        absorb(_normal(final), raw.decode("utf-8", errors="replace"), depth)
                except Exception as e:
                    logger.info(f"Skipped {page_url}: {e}")

        while queue and len(pages) < max_pages and time.monotonic() < deadline:
            # Important pages first, then shallow ones.
            queue.sort(key=lambda item: (not IMPORTANT.search(urlparse(item[1]).path), item[0]))
            take = min(10, max_pages - len(pages))
            batch, queue = queue[:take], queue[take:]
            await asyncio.gather(*(visit(u, d) for d, u in batch if d <= 4))

        async def read_doc(doc_url: str):
            async with limit:
                if time.monotonic() > deadline:
                    return
                try:
                    _, _, raw = await _get(client, doc_url, MAX_DOC_BYTES)
                    text = _pdf_text(raw)
                    if len(text) >= 40:
                        docs.append((doc_url, text))
                except Exception as e:
                    logger.info(f"Skipped document {doc_url}: {e}")
        await asyncio.gather(*(read_doc(d) for d in doc_links[:MAX_DOCS]))

    out = [pages[u] for u in order if u in pages][:max_pages] + docs
    site_wide = [block for block, _ in sorted(chrome_seen.items(), key=lambda kv: -kv[1])][:2]
    found = []
    if contacts["phones"]:
        found.append("Phone: " + ", ".join(sorted(contacts["phones"])[:6]))
    if contacts["emails"]:
        found.append("Email: " + ", ".join(sorted(contacts["emails"])[:6]))
    if contacts["whatsapp"]:
        found.append("WhatsApp: " + ", ".join(sorted(contacts["whatsapp"])[:3]))
    if contacts["social"]:
        found.append("Social: " + ", ".join(sorted(contacts["social"])[:8]))
    extra = "\n\n".join(p for p in ("\n".join(found), *site_wide) if p.strip())
    if extra:
        out.append((f"{origin} (site-wide details)", "Contact details and information shown on every page:\n" + extra))
    return out


async def extract_youtube_transcript(video_id_or_url: str) -> str:
    """
    Extracts transcript from a YouTube video.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Extract video ID
        video_id = video_id_or_url
        if "youtube.com" in video_id_or_url or "youtu.be" in video_id_or_url:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_id_or_url)
            if match:
                video_id = match.group(1)

        # Run the blocking call in a thread
        transcript_list = await asyncio.to_thread(YouTubeTranscriptApi.get_transcript, video_id)
        transcript = " ".join([item['text'] for item in transcript_list])
        return transcript

    except Exception as e:
        logger.error(f"YouTube Transcript Error: {e}")
        return f"Error extracting YouTube transcript: {str(e)}"
