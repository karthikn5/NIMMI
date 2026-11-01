"""
Is an email address worth sending to? Its format, a typo in a common provider ("gmial.com"), a throwaway inbox, and
whether its domain receives mail at all (MX records, looked up once a day per domain). Checked before the first
automatic email to someone: a bounce hurts the sending reputation of every business on Nimmi.
"""
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from disposable_email_domains import allowlist, blocklist

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")

# Providers most people in India use: a domain one or two letters away from one of these is probably a typo.
COMMON = ("gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "ymail.com", "hotmail.com", "outlook.com",
          "live.com", "msn.com", "icloud.com", "me.com", "rediffmail.com", "aol.com", "protonmail.com", "proton.me",
          "zoho.com", "zohomail.in")
# Real providers that look like typos of the ones above: never "corrected".
REAL = set(COMMON) | {"mail.com", "gmx.com", "gmx.net", "yandex.com", "live.in", "hotmail.co.in", "outlook.in", "mac.com"}

_CACHE_SECONDS = 24 * 3600
_cache: dict[str, tuple[float, bool]] = {}


@dataclass
class Verdict:
    ok: bool                          # worth sending to
    reason: Optional[str] = None      # why not, in plain words
    suggestion: Optional[str] = None  # "karthi@gmail.com" for "karthi@gmial.com"
    throwaway: bool = False           # a temporary inbox (mailinator and the like)


def _distance(a: str, b: str) -> int:
    """Letters added, removed, changed or swapped to turn a into b (optimal string alignment)."""
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            row[j] = min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                row[j] = min(row[j], rows[-2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower().rstrip(".")


def suggestion(address: str) -> Optional[str]:
    """The address with a mistyped common provider corrected, or None."""
    address = (address or "").strip()
    if "@" not in address:
        return None
    local, domain = address.rsplit("@", 1)[0], domain_of(address)
    if not local or domain in REAL:
        return None
    best, best_d = None, 3
    for candidate in COMMON:
        d = _distance(domain, candidate)
        if d < best_d:
            best, best_d = candidate, d
    limit = 1 if len(domain) <= 7 else 2
    return f"{local}@{best}" if best and best_d <= limit else None


def throwaway(domain: str) -> bool:
    """A temporary inbox provider (the community list in disposable-email-domains), including its subdomains."""
    parts = domain.lower().split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in allowlist:
            return False
        if candidate in blocklist:
            return True
    return False


async def _lookup(domain: str) -> Optional[bool]:
    """True: the domain takes mail (an MX record, or an address of its own); False: it doesn't; None: couldn't tell."""
    try:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver
        resolver = dns.asyncresolver.Resolver()
        resolver.timeout, resolver.lifetime = 2.0, 4.0
    except Exception as e:  # no resolver configured on this machine
        logger.debug(f"No DNS resolver: {e}")
        return None
    try:
        answer = await resolver.resolve(domain, "MX")
        # A "null MX" ("." as the host, RFC 7505) says the domain takes no mail.
        return any(r.exchange.to_text().rstrip(".") for r in answer)
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        try:  # no MX: mail goes to the domain's own address, if it has one (RFC 5321)
            await resolver.resolve(domain, "A")
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return False
        except Exception:
            return None
    except Exception:  # time-outs, servers that don't answer
        return None


async def receives_mail(domain: str) -> Optional[bool]:
    domain = domain.lower().strip().rstrip(".")
    if domain in REAL:
        return True
    hit = _cache.get(domain)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    found = await _lookup(domain)
    if found is not None:  # "couldn't tell" is asked again next time
        if len(_cache) > 5000:
            _cache.clear()
        _cache[domain] = (time.monotonic() + _CACHE_SECONDS, found)
    return found


async def check(address: str) -> Verdict:
    address = (address or "").strip()
    if not EMAIL_RE.fullmatch(address):
        return Verdict(False, "That isn't a complete email address")
    fix = suggestion(address)
    domain = domain_of(address)
    if await receives_mail(domain) is False:
        return Verdict(False, f"{domain} doesn't receive email", fix)
    return Verdict(True, suggestion=fix, throwaway=throwaway(domain))


async def reply_address_works(address: str) -> None:
    """Where a business's replies go has to take mail, or every reply is lost without anyone knowing. Nov 2026, on live:
    admin@nimmai.in was saved, a domain that doesn't exist. Raises what to tell them. An empty address is fine here."""
    from fastapi import HTTPException
    if not (address or "").strip():
        return
    verdict = await check(address)
    if not verdict.ok:
        raise HTTPException(status_code=400, detail=f"Replies couldn't reach {address}: {verdict.reason}."
                                                    + (f" Did you mean {verdict.suggestion}?" if verdict.suggestion else ""))

