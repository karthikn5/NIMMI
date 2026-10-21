"""
Site addresses: the free <slug>.<SITES_DOMAIN> address, and custom domains (paid plans).

Custom domains (e.g. www.mybusiness.in bought on GoDaddy):
1. The owner adds two DNS records: a TXT record proving the domain is theirs, and a CNAME
   pointing it at CUSTOM_DOMAIN_TARGET.
2. We check both over DNS-over-HTTPS, then register the domain with Cloudflare for SaaS
   (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID), which issues and renews its HTTPS certificate
   and forwards visits to us (see ops/sites_edge_worker.js).
A bare domain (mybusiness.in) can't hold a CNAME at most registrars, so we ask for www and show
how to forward the bare domain to it.
"""
import ipaddress
import logging
import os
import re
from typing import Optional

import httpx

from security import is_production

logger = logging.getLogger(__name__)

RESERVED_SLUGS = {
    "www", "api", "app", "apps", "admin", "administrator", "root", "mail", "email", "smtp", "imap", "pop", "ftp", "ns1", "ns2",
    "dashboard", "console", "status", "docs", "help", "support", "blog", "cdn", "static", "assets", "media", "files",
    "login", "signin", "signup", "auth", "account", "accounts", "billing", "pay", "payment", "payments", "secure",
    "nimmi", "nimmiai", "official", "team", "staff", "test", "demo", "preview", "cname", "domains", "origin", "edge",
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
# Common two-part endings, so "www" is found as the host in www.shop.co.in.
TWO_PART = {"co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in", "ac.in", "edu.in", "res.in", "gov.in",
            "co.uk", "org.uk", "me.uk", "ac.uk", "com.au", "net.au", "org.au", "co.nz", "com.sg", "com.my",
            "co.za", "com.br", "co.jp", "com.cn", "com.hk", "com.ph", "com.pk", "com.bd", "com.np", "com.lk", "co.ae"}
LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


# ─── the free address ─────────────────────────────────────────────
def sites_domain() -> Optional[str]:
    """The domain sites are published under, e.g. nimmi.site. Locally: <slug>.localhost:<port>."""
    configured = os.getenv("SITES_DOMAIN", "").strip().lower().strip(".")
    if configured:
        return configured
    return None if is_production() else f"localhost:{os.getenv('PORT', '8000')}"


def _scheme() -> str:
    return "https" if os.getenv("SITES_DOMAIN") else "http"


def site_url(slug: str) -> Optional[str]:
    domain = sites_domain()
    return f"{_scheme()}://{slug}.{domain}" if domain else None


def preview_url(slug: str, deploy_id: str) -> Optional[str]:
    """Every deploy keeps its own address (slug--abcd1234), so an older version can be looked at."""
    domain = sites_domain()
    return f"{_scheme()}://{slug}--{deploy_id[:8]}.{domain}" if domain else None


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:40].strip("-")
    return slug


def slug_problem(slug: str) -> Optional[str]:
    if not SLUG.match(slug or ""):
        return "Use 3 to 40 letters, numbers or hyphens, starting and ending with a letter or number"
    if "--" in slug:
        return "Use single hyphens only"
    if slug in RESERVED_SLUGS:
        return "That address is reserved"
    return None


# ─── custom domains ───────────────────────────────────────────────
def custom_target() -> Optional[str]:
    """What customers point their CNAME at (the Cloudflare for SaaS hostname)."""
    target = os.getenv("CUSTOM_DOMAIN_TARGET", "").strip().lower().strip(".")
    if target:
        return target
    domain = os.getenv("SITES_DOMAIN", "").strip().lower().strip(".")
    return f"cname.{domain}" if domain else (None if is_production() else "cname.localhost")


def cloudflare() -> Optional[tuple[str, str]]:
    token, zone = os.getenv("CLOUDFLARE_API_TOKEN", ""), os.getenv("CLOUDFLARE_ZONE_ID", "")
    return (token, zone) if token and zone else None


def custom_domains_available() -> bool:
    """Production needs Cloudflare for SaaS for certificates; locally the DNS checks alone are enough."""
    return bool(cloudflare() and custom_target()) or not is_production()


def normalize(raw: str) -> str:
    """mybusiness.in, https://www.MyBusiness.in/ -> www.mybusiness.in-style lowercase host, or ValueError."""
    host = (raw or "").strip().lower()
    host = re.sub(r"^[a-z]+://", "", host).split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].strip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("That isn't a valid domain")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Enter a domain name, not an IP address")
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or not all(LABEL.match(label) for label in labels) or labels[-1].isdigit():
        raise ValueError("That isn't a valid domain")
    own = [d for d in (os.getenv("SITES_DOMAIN", ""), "nimmiai.in", "railway.app", "up.railway.app", "localhost") if d]
    if any(host == d.split(":")[0] or host.endswith("." + d.split(":")[0]) for d in own):
        raise ValueError("Use a domain you own")
    return host


def apex(host: str) -> str:
    labels = host.split(".")
    n = 3 if ".".join(labels[-2:]) in TWO_PART and len(labels) >= 3 else 2
    return ".".join(labels[-n:])


def is_apex(host: str) -> bool:
    return apex(host) == host


def dns_host(name: str) -> str:
    """The "Host"/"Name" a registrar like GoDaddy wants: the part before the domain, or @."""
    root = apex(name)
    return "@" if name == root else name[: -len(root) - 1]


def verify_name(host: str) -> str:
    return f"_nimmi-verify.{host}"


def records(host: str, token: str) -> list[dict]:
    """The DNS records the owner adds, in the form registrars show them."""
    return [
        {"type": "CNAME", "host": dns_host(host), "name": host, "value": custom_target() or ""},
        {"type": "TXT", "host": dns_host(verify_name(host)), "name": verify_name(host), "value": f"nimmi-verify={token}"},
    ]


async def lookup(name: str, rtype: str) -> list[str]:
    """DNS answers over HTTPS (Cloudflare, then Google), without trusting the server's own resolver."""
    for url in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(url, params={"name": name, "type": rtype}, headers={"Accept": "application/dns-json"})
            if r.status_code == 200:
                return [str(a.get("data", "")).strip().strip('"').rstrip(".").lower()
                        for a in (r.json().get("Answer") or []) if a.get("data")]
        except (httpx.HTTPError, ValueError):
            continue
    return []


async def dns_status(host: str, token: str) -> tuple[bool, bool]:
    """(TXT record proves ownership, CNAME points at us)."""
    txt = await lookup(verify_name(host), "TXT")
    owned = any(t.replace('" "', "") == f"nimmi-verify={token}" for t in txt)
    target = custom_target() or ""
    pointed = bool(target) and target in await lookup(host, "CNAME")
    return owned, pointed


# ─── Cloudflare for SaaS (certificates and routing for custom domains) ──
CF_API = "https://api.cloudflare.com/client/v4"


async def _cf(method: str, path: str, json: Optional[dict] = None) -> dict:
    token, zone = cloudflare()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.request(method, f"{CF_API}/zones/{zone}{path}", json=json, headers={"Authorization": f"Bearer {token}"})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("success"):
        errors = "; ".join(e.get("message", "") for e in data.get("errors") or []) or f"HTTP {r.status_code}"
        raise RuntimeError(errors)
    return data.get("result") or {}


async def cf_create(host: str) -> str:
    """Register a custom hostname; Cloudflare validates it over HTTP once the CNAME points at us."""
    result = await _cf("POST", "/custom_hostnames", {"hostname": host, "ssl": {
        "method": "http", "type": "dv", "settings": {"min_tls_version": "1.2", "http2": "on"}}})
    return result["id"]


async def cf_status(provider_id: str) -> tuple[bool, Optional[str]]:
    """(ready to serve over HTTPS, a problem worth showing)."""
    result = await _cf("GET", f"/custom_hostnames/{provider_id}")
    ssl = result.get("ssl") or {}
    ready = result.get("status") == "active" and ssl.get("status") == "active"
    problems = [e.get("message") for e in (result.get("verification_errors") or []) + (ssl.get("validation_errors") or [])
                if isinstance(e, dict) and e.get("message")] + [e for e in result.get("verification_errors") or [] if isinstance(e, str)]
    return ready, (problems[0][:300] if problems and not ready else None)


async def cf_delete(provider_id: str) -> None:
    try:
        await _cf("DELETE", f"/custom_hostnames/{provider_id}")
    except Exception as e:  # already gone, or Cloudflare unreachable: nothing to undo for the customer
        logger.warning(f"Removing custom hostname {provider_id} failed: {e}")
