"""
A business's own sending domain (Email > Settings), through Resend's Domains API: Nimmi adds the domain to its Resend
account, shows the DNS records to add at the business's DNS provider, checks until Resend has verified them, then
makes a Resend key that can send only from that domain (Resend's advice for platforms like Nimmi). Open and click
tracking stay off on these domains: they would need one more DNS record, and mail apps open emails by themselves.

A newly verified domain warms up: its bulk email starts small and doubles every day (section 5.1 of mail_plan.md).
"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import EmailDomain, EmailSender, IntegrationSettings
from database import async_session
from notify import email

logger = logging.getLogger(__name__)

DOMAIN_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# Addresses people have at a mail provider can't be sent from by anyone else (only a domain's owner controls its DNS).
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "ymail.com", "hotmail.com",
             "outlook.com", "outlook.in", "live.com", "live.in", "msn.com", "icloud.com", "me.com", "mac.com",
             "rediffmail.com", "aol.com", "protonmail.com", "proton.me", "zoho.com", "zohomail.in", "mail.com",
             "gmx.com", "gmx.net", "yandex.com"}
MAX_PER_WORKSPACE = 5
WARM_START, WARM_DAYS = 100, 7  # bulk emails a day from a new domain: 100, 200, 400 ... no limit after a week
CHECK_FOR = timedelta(days=4)   # Resend gives up on records it can't find after 72 hours


class DomainError(Exception):
    pass


class _NotFound(DomainError):
    pass


async def _call(method: str, path: str, json: Optional[dict] = None) -> dict:
    key = os.getenv("RESEND_API_KEY")
    if not key:
        raise DomainError("Email sending isn't set up on the server yet")
    try:
        async with email.resend_client() as client:
            resp = await client.request(method, f"{email.resend_url()}{path}", json=json,
                                        headers={"Authorization": f"Bearer {key}"})
    except Exception as e:
        logger.warning(f"Resend {method} {path} failed: {e}")
        raise DomainError("Couldn't reach Resend. Please try again in a minute.")
    if resp.status_code == 404:
        raise _NotFound("Resend doesn't have this domain")
    if resp.status_code >= 300:
        raise DomainError(email._resend_reason(resp.status_code, resp.text))
    return resp.json() if resp.content else {}


def clean_name(value: str) -> str:
    name = (value or "").strip().lower()
    name = re.sub(r"^[a-z]+://", "", name).split("/")[0].lstrip("@").rstrip(".")
    return name[4:] if name.startswith("www.") else name


def _reserved(name: str) -> bool:
    ours = {email.address_of(email.customer_sender()).split("@")[-1], email.address_of(email._sender()).split("@")[-1],
            "nimmiai.in"}
    return any(name == d or name.endswith(f".{d}") for d in ours if d)


def records(raw: Optional[list], domain: str) -> list[dict]:
    """The DNS records to add, as the business types them: the host relative to the domain (most DNS providers add the
    domain themselves), TXT values without the quotes some providers add. Tracking records are left out."""
    out = []
    for r in raw or []:
        if (r.get("record") or "").lower() == "tracking":
            continue
        host = (r.get("name") or "").rstrip(".")
        if host == domain:
            host = "@"
        elif host.endswith(f".{domain}"):
            host = host[: -len(domain) - 1]
        value = str(r.get("value") or "")
        if len(value) > 1 and value[0] == value[-1] == '"':
            value = value[1:-1]
        out.append({"purpose": r.get("record") or "", "type": r.get("type") or "", "host": host or "@",
                    "full_name": domain if host in ("", "@") else f"{host}.{domain}", "value": value,
                    "priority": r.get("priority"), "status": r.get("status") or "not_started"})
    return out


async def add(db, owner_id: str, name: str) -> EmailDomain:
    name = clean_name(name)
    if not DOMAIN_RE.fullmatch(name):
        raise DomainError("Enter a domain like sunrisehomes.in")
    if name in FREE_MAIL:
        raise DomainError(f"Nobody can send as @{name} except {name} itself. Use your business's own domain; until "
                          "then, emails go from Nimmi's sending address under your business's name.")
    if _reserved(name):
        raise DomainError("That domain belongs to Nimmi")
    existing = (await db.execute(select(EmailDomain).where(EmailDomain.name == name))).scalars().first()
    if existing is not None:
        if existing.user_id == owner_id:
            return existing
        raise DomainError("This domain is already connected to another Nimmi account. Write to support.nimmi@gmail.com "
                          "if it's yours.")
    count = len((await db.execute(select(EmailDomain.id).where(EmailDomain.user_id == owner_id))).all())
    if count >= MAX_PER_WORKSPACE:
        raise DomainError(f"A workspace can have up to {MAX_PER_WORKSPACE} sending domains")

    created = await _call("POST", "/domains", {"name": name})
    try:  # tracking needs one more record; Nimmi keeps it off on customer domains
        await _call("PATCH", f"/domains/{created['id']}", {"open_tracking": False, "click_tracking": False})
    except DomainError as e:
        logger.info(f"Turning tracking off on {name}: {e}")
    domain = EmailDomain(user_id=owner_id, name=name, resend_id=created.get("id"), region=created.get("region"),
                         status=created.get("status") or "not_started", records=records(created.get("records"), name),
                         checked_at=datetime.utcnow())
    db.add(domain)
    await db.commit()
    return domain


async def refresh(db, domain: EmailDomain) -> EmailDomain:
    """Read the domain's status from Resend; once verified, give it its own sending key."""
    data = await _call("GET", f"/domains/{domain.resend_id}")
    domain.status = data.get("status") or domain.status
    found = records(data.get("records"), domain.name)
    if found:
        domain.records = found
    domain.checked_at = datetime.utcnow()
    if domain.status == "verified":
        domain.verified_at = domain.verified_at or datetime.utcnow()
        if not domain.sending_key:
            await _make_key(domain)
    await db.commit()
    return domain


async def verify(db, domain: EmailDomain) -> EmailDomain:
    """Ask Resend to look for the records now (it also keeps looking on its own for 72 hours)."""
    await _call("POST", f"/domains/{domain.resend_id}/verify")
    return await refresh(db, domain)


async def _make_key(domain: EmailDomain) -> None:
    try:
        key = await _call("POST", "/api-keys", {"name": f"Nimmi {domain.name}"[:50], "permission": "sending_access",
                                                "domain_id": domain.resend_id})
        domain.sending_key, domain.sending_key_id = key.get("token"), key.get("id")
    except DomainError as e:  # Nimmi's own key still sends from the domain
        logger.warning(f"No sending key for {domain.name}: {e}")


async def remove(db, domain: EmailDomain) -> None:
    if domain.sending_key_id:
        try:
            await _call("DELETE", f"/api-keys/{domain.sending_key_id}")
        except DomainError as e:
            logger.warning(f"Removing the sending key of {domain.name}: {e}")
    if domain.resend_id:
        try:
            await _call("DELETE", f"/domains/{domain.resend_id}")
        except _NotFound:
            pass
    await db.execute(update(EmailSender).where(EmailSender.domain_id == domain.id).values(domain_id=None))
    await db.execute(update(IntegrationSettings).where(IntegrationSettings.sender_domain_id == domain.id)
                     .values(sender_domain_id=None))
    await db.delete(domain)
    await db.commit()


def bulk_allowance(domain: Optional[EmailDomain], now: Optional[datetime] = None) -> Optional[int]:
    """Bulk emails a domain may send today while it warms up; None = no limit (Nimmi's address, or a week on)."""
    if domain is None:
        return None
    if domain.status != "verified" or not domain.verified_at:
        return 0
    days = ((now or datetime.utcnow()) - domain.verified_at.replace(tzinfo=None)).days
    return None if days >= WARM_DAYS else WARM_START * 2 ** max(days, 0)


async def check_pending() -> None:
    """Scheduler, every 10 minutes: domains waiting for their records, and a daily look at verified ones (a record
    removed later makes Resend stop sending)."""
    if not os.getenv("RESEND_API_KEY"):
        return
    now = datetime.utcnow()
    async with async_session() as db:
        rows = (await db.execute(select(EmailDomain))).scalars().all()
        for domain in rows:
            created = domain.created_at.replace(tzinfo=None) if domain.created_at else now
            checked = domain.checked_at.replace(tzinfo=None) if domain.checked_at else None
            waiting = domain.status != "verified" and now - created < CHECK_FOR
            stale = domain.status == "verified" and (checked is None or now - checked > timedelta(days=1))
            if not (waiting or stale) or not domain.resend_id:
                continue
            try:
                await refresh(db, domain)
            except DomainError as e:
                logger.info(f"Checking {domain.name}: {e}")
