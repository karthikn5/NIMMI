"""
What Resend reports after an email is sent (POST /api/email/webhooks/resend). Each event is signed (Svix: svix-id,
svix-timestamp, svix-signature, with the endpoint's whsec_ secret in RESEND_WEBHOOK_SECRET) and may come more than
once, so it's kept once by its svix-id.

- delivered / delayed: shown on the email in History.
- bounced: a permanent bounce means the address doesn't exist: nobody on Nimmi emails it again, and what's queued for
  it is cancelled. A temporary one is only shown.
- complained (marked as spam): this business never emails the address again.
- failed / suppressed: Resend didn't send it; History says why.
- opened / clicked: kept as hints (mail apps open emails by themselves).
- received: someone replied (mail/inbound.py).

Emails are found by the job tag Nimmi puts on every customer email (or Resend's email id); the workspace by the ws tag.
"""
import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import EmailDomain, EmailEvent, EmailJob
from database import async_session
from mail import suppress

logger = logging.getLogger(__name__)

TOLERANCE = 5 * 60  # seconds a signed event stays valid (Svix's own default)
FAILED = {
    "reached_daily_quota": "Resend's sending allowance for the day was used up",
    "reached_monthly_quota": "Resend's sending allowance for the month was used up",
}


def signature_ok(secret: str, event_id: str, timestamp: str, signatures: str, body: bytes,
                 now: Optional[float] = None) -> bool:
    """Svix's scheme: base64(HMAC-SHA256(key, "<id>.<timestamp>.<body>")), the key being the secret after "whsec_",
    base64-decoded; the header lists "v1,<signature>" entries separated by spaces."""
    if not (secret and event_id and timestamp and signatures):
        return False
    try:
        if abs((now or time.time()) - int(timestamp)) > TOLERANCE:
            return False
        key = base64.b64decode(secret[len("whsec_"):] if secret.startswith("whsec_") else secret)
    except (ValueError, TypeError):
        return False
    signed = f"{event_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(version == "v1" and hmac.compare_digest(sig, expected)
               for version, _, sig in (part.partition(",") for part in signatures.split()))


def _tags(data: dict) -> dict:
    """Resend sends tags as an object; older events listed {name, value} pairs."""
    tags = data.get("tags") or {}
    if isinstance(tags, list):
        return {str(t.get("name")): str(t.get("value")) for t in tags if isinstance(t, dict)}
    return {str(k): str(v) for k, v in tags.items()} if isinstance(tags, dict) else {}


def _small(data: dict) -> dict:
    keep = {k: data[k] for k in ("bounce", "failed", "suppressed") if isinstance(data.get(k), dict)}
    if isinstance(data.get("click"), dict):
        keep["click"] = {"link": str(data["click"].get("link") or "")[:300]}
    return keep


async def handle(event_id: str, payload: dict) -> None:
    kind = str(payload.get("type") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if kind.startswith("domain."):
        await _domain_changed(data)
        return
    if not kind.startswith("email."):
        return
    tags = _tags(data)
    provider_id = data.get("email_id")
    to = data.get("to")
    to = (to[0] if isinstance(to, list) and to else to) or None
    async with async_session() as db:
        job = None
        if tags.get("job"):
            job = await db.get(EmailJob, tags["job"])
        if job is None and provider_id:
            job = (await db.execute(select(EmailJob).where(EmailJob.provider_id == provider_id))).scalars().first()
        owner = (job.user_id if job else None) or tags.get("ws") or None
        to = to or (job.to_email if job else None)
        db.add(EmailEvent(event_id=event_id, type=kind, provider_id=provider_id, user_id=owner,
                          job_id=job.id if job else None, to_email=to, detail=_small(data) or None))
        try:
            await db.commit()
        except IntegrityError:
            return  # Resend sent this event before: done then
        if kind == "email.received":
            from mail import inbound
            return await inbound.received(data)

        now = datetime.utcnow()
        customer = tags.get("kind") in ("customer", None) and owner is not None
        if kind == "email.delivered" and job:
            job.delivered_at = job.delivered_at or now
            if job.event in (None, "delayed"):
                job.event, job.event_detail = "delivered", None
        elif kind == "email.delivery_delayed" and job and job.event is None:
            job.event, job.event_detail = "delayed", "The receiving server is slow to accept it; Resend keeps trying"
        elif kind == "email.bounced":
            bounce = data.get("bounce") if isinstance(data.get("bounce"), dict) else {}
            hard = str(bounce.get("type") or "").lower() == "permanent"
            detail = str(bounce.get("message") or "")[:300] or None
            if job:
                job.bounced_at = job.bounced_at or now
                job.event, job.event_detail = "bounced", detail or ("The address doesn't exist" if hard else "It bounced")
            if hard and to:
                await suppress.add_bounce(db, to, "bounce", detail)
                if customer:  # shown on the business's own list too
                    await suppress.add(db, owner, to, "bounce", bot_id=job.bot_id if job else None)
                await suppress.cancel_queued(db, to, suppress.TEXT["bounce"])
        elif kind == "email.complained":
            if job:
                job.complained_at = job.complained_at or now
                job.event, job.event_detail = "complained", "They reported it as spam"
            if customer and to:
                await suppress.add(db, owner, to, "complaint", bot_id=job.bot_id if job else None)
                await suppress.cancel_queued(db, to, suppress.TEXT["complaint"], owner)
        elif kind == "email.failed":
            reason = str((data.get("failed") or {}).get("reason") or "") if isinstance(data.get("failed"), dict) else ""
            if job:
                job.status, job.event = "failed", "failed"
                job.error = FAILED.get(reason) or f"Resend couldn't send it{f' ({reason})' if reason else ''}"
        elif kind == "email.suppressed":
            if job:
                job.status, job.event, job.error = "failed", "suppressed", suppress.TEXT["suppressed"]
            if to:
                await suppress.add_bounce(db, to, "suppressed", str((data.get("suppressed") or {}).get("message") or "")
                                          if isinstance(data.get("suppressed"), dict) else None)
        elif kind == "email.opened" and job:
            job.opened_at = job.opened_at or now
        elif kind == "email.clicked" and job:
            job.clicked_at = job.clicked_at or now
        await suppress.commit_quietly(db)


async def _domain_changed(data: dict) -> None:
    """Resend changed a domain's status (a check passed or failed): read it again."""
    from mail import domains
    resend_id = data.get("id")
    if not resend_id:
        return
    async with async_session() as db:
        domain = (await db.execute(select(EmailDomain).where(EmailDomain.resend_id == resend_id))).scalars().first()
        if domain is None:
            return
        try:
            await domains.refresh(db, domain)
        except domains.DomainError as e:
            logger.info(f"Reading {domain.name} after Resend's event: {e}")
