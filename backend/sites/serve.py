"""
Serving published sites to visitors.

SitesMiddleware sits in front of the API. A request is for a site when its host is
<slug>.<SITES_DOMAIN> (or <slug>--<deploy>.<SITES_DOMAIN> for an older version), or an active
custom domain. Requests forwarded by our Cloudflare edge worker carry the visitor's host in
X-Nimmi-Site-Host, trusted only with the shared SITES_EDGE_KEY. Everything else goes on to the API.

Lookups are cached in memory (site rows briefly, deploy file lists and file contents for good,
since a deploy never changes), so a page view costs at most one small query.
"""
import asyncio
import gzip
import hmac
import mimetypes
import os
import posixpath
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

from sqlalchemy.future import select

from database import async_session
from backend.models import Site, SiteDeploy
from security import is_production
from sites import domains, storage

SITE_TTL = 10.0
DOMAINS_TTL = 30.0
FILE_CACHE_BYTES = 64 * 1024 * 1024
CACHEABLE_FILE = 2 * 1024 * 1024
HASHED = re.compile(r"[.-][0-9a-zA-Z_-]{8,}\.(?:js|mjs|css|woff2?|ttf|png|jpe?g|webp|avif|gif|svg|ico|wasm|map)$")
TEXT_TYPES = ("text/", "application/javascript", "application/json", "application/manifest+json", "image/svg+xml", "application/xml")
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".webmanifest": "application/manifest+json",
         ".wasm": "application/wasm", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
         ".ttf": "font/ttf", ".otf": "font/otf", ".webp": "image/webp", ".avif": "image/avif", ".txt": "text/plain",
         ".md": "text/plain", ".xml": "application/xml", ".csv": "text/csv", ".pdf": "application/pdf", ".mp4": "video/mp4",
         ".webm": "video/webm", ".mp3": "audio/mpeg", ".html": "text/html", ".htm": "text/html", ".css": "text/css"}


@dataclass
class Live:
    site_id: str
    slug: str
    status: str
    deploy_id: Optional[str]
    bot_id: Optional[str]
    spa_setting: str
    preview: bool = False


_sites: dict[str, tuple[float, Optional[Live]]] = {}
_domains: tuple[float, dict[str, str]] = (0.0, {})
_domains_lock = asyncio.Lock()
_manifests: "OrderedDict[str, tuple[dict, bool]]" = OrderedDict()
_files: "OrderedDict[tuple[str, str], bytes]" = OrderedDict()
_files_size = 0


def forget(slug: Optional[str] = None) -> None:
    """Drop cached site rows after a change in this process (other processes catch up within SITE_TTL)."""
    global _domains
    if slug:
        for key in [k for k in _sites if k == slug or k.startswith(slug + "--")]:
            _sites.pop(key, None)
    else:
        _sites.clear()
    _domains = (0.0, {})


async def _custom_domains() -> dict[str, str]:
    global _domains
    if time.monotonic() < _domains[0]:
        return _domains[1]
    async with _domains_lock:
        if time.monotonic() < _domains[0]:
            return _domains[1]
        try:
            async with async_session() as db:
                rows = (await db.execute(select(Site.custom_domain, Site.slug).where(
                    Site.domain_status == "active", Site.custom_domain.is_not(None), Site.deleted_at.is_(None)))).all()
            _domains = (time.monotonic() + DOMAINS_TTL, {d: s for d, s in rows})
        except Exception:
            _domains = (time.monotonic() + 5.0, _domains[1])
    return _domains[1]


async def _live(label: str) -> Optional[Live]:
    """The site (and deploy) behind "<slug>" or "<slug>--<deploy prefix>"."""
    hit = _sites.get(label)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    slug, _, prefix = label.partition("--")
    live = None
    async with async_session() as db:
        site = (await db.execute(select(Site).where(Site.slug == slug, Site.deleted_at.is_(None)))).scalars().first()
        if site:
            live = Live(site.id, site.slug, site.status, site.current_deploy_id, site.bot_id, site.spa or "auto")
            if prefix:
                deploy = None
                if re.fullmatch(r"[0-9a-f]{8}", prefix):
                    deploy = (await db.execute(select(SiteDeploy.id).where(
                        SiteDeploy.site_id == site.id, SiteDeploy.id.like(f"{prefix}%"), SiteDeploy.status == "ready"))).scalars().first()
                live.deploy_id, live.preview = deploy, True
    _sites[label] = (time.monotonic() + SITE_TTL, live)
    return live


def _request_host(scope) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-nimmi-site-host")
    key = os.getenv("SITES_EDGE_KEY", "")
    if forwarded and key and hmac.compare_digest(headers.get(b"x-nimmi-edge-key", b"").decode("latin-1"), key):
        return forwarded.decode("latin-1").strip().lower().rstrip(".")
    return headers.get(b"host", b"").decode("latin-1").strip().lower().rstrip(".")


async def resolve(host: str) -> tuple[bool, Optional[Live]]:
    """(this host is a site address, the site if one is published there)."""
    if not host:
        return False, None
    base = domains.sites_domain()
    if base and host.endswith("." + base):
        label = host[: -len(base) - 1]
        if label and "." not in label:
            return True, await _live(label)
        return False, None
    bare = host.split(":", 1)[0]
    if "." not in bare or bare.endswith(("nimmiai.in", ".railway.app", ".trycloudflare.com")):
        return False, None  # the API's own addresses: never a database lookup
    slug = (await _custom_domains()).get(bare)
    return (True, await _live(slug)) if slug else (False, None)


async def _manifest(deploy_id: str) -> Optional[tuple[dict, bool]]:
    hit = _manifests.get(deploy_id)
    if hit:
        _manifests.move_to_end(deploy_id)
        return hit
    async with async_session() as db:
        row = (await db.execute(select(SiteDeploy.files, SiteDeploy.spa).where(
            SiteDeploy.id == deploy_id, SiteDeploy.status == "ready"))).first()
    if not row:
        return None
    _manifests[deploy_id] = (row[0] or {}, bool(row[1]))
    while len(_manifests) > 256:
        _manifests.popitem(last=False)
    return _manifests[deploy_id]


async def _file(site_id: str, sha: str) -> Optional[bytes]:
    global _files_size
    key = (site_id, sha)
    data = _files.get(key)
    if data is not None:
        _files.move_to_end(key)
        return data
    data = await storage.get(site_id, sha)
    if data is not None and len(data) <= CACHEABLE_FILE:
        _files[key] = data
        _files_size += len(data)
        while _files_size > FILE_CACHE_BYTES and _files:
            _, old = _files.popitem(last=False)
            _files_size -= len(old)
    return data


def _content_type(path: str) -> str:
    ext = posixpath.splitext(path)[1].lower()
    kind = TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    return f"{kind}; charset=utf-8" if kind.startswith(TEXT_TYPES) and "charset" not in kind else kind


def _find(files: dict, path: str, spa: bool) -> tuple[Optional[str], int, Optional[str]]:
    """(file to send, status, redirect location) for a request path."""
    if path in files:
        return path, 200, None
    base = path.rstrip("/")
    if path == "" or path.endswith("/"):
        index = f"{base}/index.html" if base else "index.html"
        if index in files:
            return index, 200, None
    else:
        if f"{path}.html" in files:
            return f"{path}.html", 200, None
        if f"{path}/index.html" in files:
            return None, 308, f"/{path}/"  # so the page's relative links resolve inside its folder
    if spa and "." not in posixpath.basename(base) and "index.html" in files:
        return "index.html", 200, None
    if "404.html" in files:
        return "404.html", 404, None
    return None, 404, None


def _assistant_tag(bot_id: str) -> bytes:
    api = os.getenv("PUBLIC_BACKEND_URL", "").rstrip("/") or "https://api.nimmiai.in"
    dashboard = os.getenv("DASHBOARD_URL", "").rstrip("/") or "https://nimmiai.in"
    return (f'<script src="{api}/static/nimmi-widget.js" data-bot-id="{bot_id}" data-api-url="{api}" '
            f'data-dashboard-url="{dashboard}" async></script>').encode()


def with_assistant(html: bytes, bot_id: str) -> bytes:
    """Add the assistant's chat widget to a page (unless the page already has one)."""
    if b"nimmi-widget.js" in html:
        return html
    at = html.lower().rfind(b"</body>")
    tag = _assistant_tag(bot_id)
    return html[:at] + tag + html[at:] if at >= 0 else html + tag


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="robots" content="noindex"><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#faf9f7;color:#1c1719;font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:420px;padding:24px;text-align:center}}h1{{font-size:20px;margin:0 0 6px}}p{{margin:0;color:#57534e}}
a{{color:#550a64}}small{{display:block;margin-top:28px;color:#a8a29e;font-size:12px}}</style></head>
<body><main><h1>{title}</h1><p>{body}</p><small>Hosted on <a href="https://nimmiai.in">Nimmi AI</a></small></main></body></html>"""


async def _send(send, status: int, headers: list, body: bytes, head: bool) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(k.encode(), v.encode()) for k, v in headers] + [(b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": b"" if head else body})


def _base_headers(live: Optional[Live], on_sites_domain: bool) -> list:
    headers = [("x-content-type-options", "nosniff"), ("referrer-policy", "strict-origin-when-cross-origin")]
    if on_sites_domain and is_production():
        headers.append(("strict-transport-security", "max-age=31536000"))
    if live and live.preview:
        headers.append(("x-robots-tag", "noindex"))  # older versions shouldn't compete with the live site in search
    return headers


async def _page(send, status: int, title: str, body: str, head: bool, base: list) -> None:
    html = PAGE.format(title=title, body=body).encode()
    await _send(send, status, base + [("content-type", "text/html; charset=utf-8"), ("cache-control", "no-store")], html, head)


async def serve(scope, send, live: Optional[Live], on_sites_domain: bool) -> None:
    head = scope["method"] == "HEAD"
    base = _base_headers(live, on_sites_domain)
    if scope["method"] not in ("GET", "HEAD"):
        return await _send(send, 405, base + [("allow", "GET, HEAD"), ("content-type", "text/plain")], b"Method not allowed", head)
    if live is None:
        return await _page(send, 404, "There's no site here", "Check the address and try again.", head, base)
    if live.status == "blocked":
        return await _page(send, 451, "This site is unavailable", "It was taken down for breaking our terms of use.", head, base)
    found = await _manifest(live.deploy_id) if live.deploy_id else None
    if not found:
        return await _page(send, 404, "Nothing published yet", "This site doesn't have a published version yet.", head, base)
    files, detected_spa = found
    spa = detected_spa if live.spa_setting == "auto" else live.spa_setting == "on"

    raw = unquote(scope.get("path") or "/")
    if "\x00" in raw or any(seg == ".." for seg in raw.split("/")):
        return await _page(send, 400, "Bad request", "That address isn't valid.", head, base)
    path = raw.lstrip("/")
    target, status, location = _find(files, path, spa)
    if location:
        query = scope.get("query_string", b"").decode("latin-1")
        return await _send(send, 308, base + [("location", location + (f"?{query}" if query else ""))], b"", head)
    if target is None:
        return await _page(send, 404, "Page not found", "This page doesn't exist on the site.", head, base)

    sha = files[target][0]
    html = target.lower().endswith((".html", ".htm"))
    inject = html and live.bot_id
    etag = f'"{sha[:20]}{"-" + live.bot_id[:8] if inject else ""}"'
    if html:
        cache = "public, max-age=0, must-revalidate"
    elif HASHED.search(target):
        cache = "public, max-age=31536000, immutable"
    else:
        cache = "public, max-age=3600"
    headers = base + [("content-type", _content_type(target)), ("cache-control", cache), ("etag", etag),
                      ("vary", "Accept-Encoding")]
    request_headers = dict(scope.get("headers") or [])
    if status == 200 and request_headers.get(b"if-none-match", b"").decode("latin-1") == etag:
        return await _send(send, 304, headers, b"", True)

    data = await _file(live.site_id, sha)
    if data is None:
        return await _page(send, 503, "Temporarily unavailable", "This page couldn't be loaded. Try again in a moment.", head, base)
    if inject:
        data = with_assistant(data, live.bot_id)
    if len(data) > 1024 and _content_type(target).startswith(TEXT_TYPES) and b"gzip" in request_headers.get(b"accept-encoding", b""):
        data = gzip.compress(data, compresslevel=6)
        headers.append(("content-encoding", "gzip"))
    await _send(send, status, headers, data, head)


class SitesMiddleware:
    """Outermost: requests for a site's address are answered here; all others go to the API."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            host = _request_host(scope)
            is_site, live = await resolve(host)
            if is_site:
                base = domains.sites_domain()
                return await serve(scope, send, live, bool(base) and host.endswith("." + base))
        await self.app(scope, receive, send)
