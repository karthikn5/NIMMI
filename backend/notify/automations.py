"""
Automatic emails to customers: a thank-you after a chat lead, a follow-up after a call.

A trigger queues one EmailJob per (kind, conversation/call); the scheduler sends it
when due. Every email carries the business's name, replies go to the business,
and there's an unsubscribe link that's honoured before each send.
"""
import html
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import async_session
from backend.models import EmailJob, EmailUnsubscribe, IntegrationSettings
from notify import email

logger = logging.getLogger(__name__)

DELAYS = {"now": 0, "1h": 3600, "1d": 86400}
PLACEHOLDERS = ["name", "business", "assistant", "email", "phone", "summary"]
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}")

DEFAULTS: dict[str, dict] = {
    "chat_lead": {
        "enabled": False, "delay": "now",
        "subject": "Thanks for reaching out to {{business}}",
        "body": ("Hi {{name}},\n\nThanks for chatting with us. We have your details, and someone from our team "
                 "will get back to you shortly.\n\nIf there's anything else you'd like us to know, just reply to this email.\n\n"
                 "Regards,\n{{business}}"),
    },
    "call_lead": {
        "enabled": False, "delay": "now",
        "subject": "Following up on your call with {{business}}",
        "body": ("Hi {{name}},\n\nThank you for speaking with us. Here's a short summary of the call:\n\n{{summary}}\n\n"
                 "Reply to this email if anything needs correcting or you have more questions.\n\nRegards,\n{{business}}"),
    },
}


def automations(settings: Optional[IntegrationSettings]) -> dict[str, dict]:
    saved = (settings.email_automations if settings else None) or {}
    return {k: {**v, **{f: saved.get(k, {}).get(f) for f in v if saved.get(k, {}).get(f) is not None}} for k, v in DEFAULTS.items()}


def render(template: str, values: dict) -> str:
    def sub(m):
        return str(values.get(m.group(1).strip().lower()) or "")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, template or "").strip()


def html_email(body: str, business: str, unsubscribe_url: Optional[str]) -> str:
    paragraphs = "".join(
        f'<p style="margin:0 0 14px">{"<br>".join(html.escape(line) for line in block.splitlines())}</p>'
        for block in re.split(r"\n\s*\n", body) if block.strip()
    )
    footer = (f'{html.escape(business)}' +
              (f' &middot; <a href="{html.escape(unsubscribe_url)}" style="color:#78716c">Unsubscribe</a>' if unsubscribe_url else ""))
    return ('<div style="background:#faf9f7;padding:24px 12px">'
            '<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e8e5e0;border-radius:8px;'
            'padding:28px 28px 12px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.6;color:#1c1719">'
            f'{paragraphs}</div>'
            f'<p style="max-width:560px;margin:14px auto 0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
            f'font-size:12px;color:#78716c;text-align:center">{footer}</p></div>')


def unsubscribe_url(owner_id: str, to: str) -> str:
    from auth import issue_scoped_token
    token = issue_scoped_token(f"{owner_id}|{to.lower()}", "email_unsub", 365 * 24 * 3600)
    base = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL", "http://localhost:8000")
    return f"{base.rstrip('/')}/api/integrations/email/unsubscribe?token={token}"


async def is_unsubscribed(db, owner_id: str, to: str) -> bool:
    return (await db.execute(select(EmailUnsubscribe.id).where(
        EmailUnsubscribe.user_id == owner_id, EmailUnsubscribe.email == to.lower()))).first() is not None


async def schedule(owner_id: str, kind: str, ref_id: str, to: Optional[str], values: dict) -> bool:
    """Queue this automation for one customer, if it's on. Returns True if queued (once per kind + ref)."""
    to = (to or "").strip()
    if not to or not EMAIL_RE.fullmatch(to):
        return False
    async with async_session() as db:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        auto = automations(settings).get(kind)
        if not auto or not auto["enabled"] or await is_unsubscribed(db, owner_id, to):
            return False
        values = {**values, "name": values.get("name") or "there"}
        db.add(EmailJob(user_id=owner_id, kind=kind, ref_id=ref_id, to_email=to,
                        subject=render(auto["subject"], values)[:200], body=render(auto["body"], values),
                        send_at=datetime.utcnow() + timedelta(seconds=DELAYS.get(auto["delay"], 0))))
        try:
            await db.commit()
        except IntegrityError:
            return False  # already queued for this lead
    return True


async def process_due() -> None:
    """Send queued customer emails whose time has come (called by the background loop)."""
    from notify.events import _once  # the delivery log, one row per (kind, ref)
    now = datetime.utcnow()
    async with async_session() as db:
        jobs = (await db.execute(select(EmailJob).where(EmailJob.status == "queued", EmailJob.send_at <= now)
                                 .order_by(EmailJob.send_at).limit(20))).scalars().all()
        for job in jobs:
            settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == job.user_id))).scalars().first()
            if await is_unsubscribed(db, job.user_id, job.to_email) or not automations(settings)[job.kind]["enabled"]:
                job.status, job.error = "cancelled", "Unsubscribed or automation turned off"
                continue
            business = (settings.sender_name if settings else None) or "Our team"
            link = unsubscribe_url(job.user_id, job.to_email)
            text = f"{job.body}\n\n--\n{business}\nUnsubscribe: {link}"
            result: dict = {}

            async def send(job=job, text=text, business=business, link=link, result=result):
                ok = await email.send_email(job.to_email, job.subject, text, html_email(job.body, business, link),
                                            reply_to=settings.reply_to if settings else None, from_name=business)
                result["ok"] = ok
                return None if ok else "email not configured"
            await _once(job.user_id, f"auto_{job.kind}", job.ref_id, send)
            job.status = "sent" if result.get("ok") else "failed"
            job.error = None if result.get("ok") else "Email provider not configured or rejected the message"
        await db.commit()


async def unsubscribe(owner_id: str, to: str) -> None:
    async with async_session() as db:
        if not await is_unsubscribed(db, owner_id, to):
            db.add(EmailUnsubscribe(user_id=owner_id, email=to.lower()))
        for job in (await db.execute(select(EmailJob).where(
            EmailJob.user_id == owner_id, func.lower(EmailJob.to_email) == to.lower(), EmailJob.status == "queued"))).scalars().all():
            job.status, job.error = "cancelled", "Unsubscribed"
        try:
            await db.commit()
        except IntegrityError:
            pass
