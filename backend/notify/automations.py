"""
Automatic emails to customers.

Triggers (each can be a short sequence of up to three emails):
  chat_lead     someone shares their email in chat or on WhatsApp
  call_lead     a caller gives their email on a call
  goal_met      a call reached the agent's goal (e.g. a booking); replaces call_lead for that call
  call_missed   we called (call-back or campaign) and never reached them
  handoff_done  a person from the team finished helping them in Live chat

A trigger queues one EmailJob per step; the scheduler sends each when due. Follow-up steps stop
when the customer unsubscribes, when a later call with them reaches its goal, or when the business
stops them. Every email carries the business's name, replies go to the business, and there's an
unsubscribe link that's honoured before each send. Bulk emails (broadcasts) use the same queue.
"""
import hashlib
import html
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import async_session
from backend.models import CallLog, EmailJob, EmailUnsubscribe, IntegrationSettings, NotificationLog
from notify import email

logger = logging.getLogger(__name__)

# How long after the trigger each email goes out.
DELAYS = {"now": 0, "1h": 3600, "1d": 86400, "2d": 2 * 86400, "3d": 3 * 86400, "5d": 5 * 86400, "7d": 7 * 86400, "14d": 14 * 86400}
MAX_STEPS = 3
PLACEHOLDERS = ["name", "business", "assistant", "email", "phone", "summary", "details"]
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}")
BATCH = 50  # emails sent per scheduler pass (about every 20 seconds)


def _step(delay: str, subject: str, body: str) -> dict:
    return {"delay": delay, "subject": subject, "body": body}


DEFAULTS: dict[str, dict] = {
    "chat_lead": {"enabled": False, "steps": [_step(
        "now", "Thanks for reaching out to {{business}}",
        "Hi {{name}},\n\nThanks for chatting with us. We have your details, and someone from our team "
        "will get back to you shortly.\n\nIf there's anything else you'd like us to know, just reply to this email.\n\n"
        "Regards,\n{{business}}")]},
    "call_lead": {"enabled": False, "steps": [_step(
        "now", "Following up on your call with {{business}}",
        "Hi {{name}},\n\nThank you for speaking with us. Here's a short summary of the call:\n\n{{summary}}\n\n"
        "Reply to this email if anything needs correcting or you have more questions.\n\nRegards,\n{{business}}")]},
    "goal_met": {"enabled": False, "steps": [_step(
        "now", "Confirmed: your details with {{business}}",
        "Hi {{name}},\n\nThanks for speaking with us. Here's what we noted:\n\n{{details}}\n\n{{summary}}\n\n"
        "If anything needs changing, just reply to this email.\n\nRegards,\n{{business}}")]},
    "call_missed": {"enabled": False, "steps": [_step(
        "now", "We tried to call you",
        "Hi {{name}},\n\nWe tried calling you on {{phone}} but couldn't get through. "
        "Reply to this email with a good time to call, or any questions you have.\n\nRegards,\n{{business}}")]},
    "handoff_done": {"enabled": False, "steps": [_step(
        "now", "Thanks for chatting with {{business}}",
        "Hi {{name}},\n\nThanks for chatting with our team today. If there's anything else we can help with, "
        "just reply to this email.\n\nRegards,\n{{business}}")]},
}

LABELS = {"chat_lead": "After a chat", "call_lead": "After a call", "goal_met": "Goal met on a call",
          "call_missed": "Couldn't reach them", "handoff_done": "After your team helps", "broadcast": "Bulk email"}


def _normalize(saved: Optional[dict], default: dict) -> dict:
    """Saved settings over the defaults. Older saves had one email: {enabled, delay, subject, body}."""
    saved = saved or {}
    steps = saved.get("steps")
    if steps is None and saved.get("subject") is not None:
        steps = [_step(saved.get("delay") or "now", saved.get("subject") or "", saved.get("body") or "")]
    return {"enabled": bool(saved.get("enabled", default["enabled"])), "steps": steps or default["steps"]}


def automations(settings: Optional[IntegrationSettings]) -> dict[str, dict]:
    saved = (settings.email_automations if settings else None) or {}
    return {k: _normalize(saved.get(k), v) for k, v in DEFAULTS.items()}


def render(template: str, values: dict) -> str:
    def sub(m):
        return str(values.get(m.group(1).strip().lower()) or "")
    out = re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, template or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()  # an empty placeholder shouldn't leave a gap


def field_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")


def details_text(fields: Optional[dict]) -> str:
    """Collected details as lines ("Visit date: Sunday, 10 AM") for {{details}}."""
    return "\n".join(f"{k}: {v}" for k, v in (fields or {}).items() if str(v).strip())


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


def job_kind(automation: str, step: int) -> str:
    return automation if step == 1 else f"{automation}#{step}"


async def schedule(owner_id: str, kind: str, ref_id: str, to: Optional[str], values: dict) -> bool:
    """Queue this automation's emails for one customer, if it's on. True if queued (once per kind + ref)."""
    to = (to or "").strip()
    if not to or not EMAIL_RE.fullmatch(to):
        return False
    async with async_session() as db:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        auto = automations(settings).get(kind)
        if not auto or not auto["enabled"] or await is_unsubscribed(db, owner_id, to):
            return False
        if await _looks_abusive(db, owner_id, kind, to):
            return False
        values = {**values, "name": values.get("name") or "there"}
        now = datetime.utcnow()
        for i, step in enumerate(auto["steps"][:MAX_STEPS], start=1):
            db.add(EmailJob(user_id=owner_id, kind=job_kind(kind, i), ref_id=ref_id, to_email=to, automation=kind, step=i,
                            subject=render(step["subject"], values)[:200], body=render(step["body"], values),
                            send_at=now + timedelta(seconds=DELAYS.get(step["delay"], 0))))
        try:
            await db.commit()
        except IntegrityError:
            return False  # already queued for this lead
    return True


DAILY_CAP = int(os.getenv("AUTOMATION_DAILY_CAP", "500"))  # automatic emails one workspace can queue per day


async def _looks_abusive(db, owner_id: str, kind: str, to: str) -> bool:
    """
    Chat details are typed by website visitors, so anyone could enter a stranger's address over and over
    to make us email them. Each address gets a given automation at most once a day, and a workspace has
    a daily ceiling, which protects people's inboxes and our sending reputation.
    """
    since = datetime.utcnow() - timedelta(days=1)
    again = (await db.execute(select(EmailJob.id).where(
        EmailJob.user_id == owner_id, EmailJob.automation == kind, func.lower(EmailJob.to_email) == to.lower(),
        EmailJob.created_at >= since).limit(1))).first()
    if again:
        return True
    today = (await db.execute(select(func.count()).select_from(EmailJob).where(
        EmailJob.user_id == owner_id, EmailJob.broadcast_id.is_(None), EmailJob.created_at >= since))).scalar_one()
    if today >= DAILY_CAP:
        logger.warning(f"Automatic email cap reached for workspace {owner_id[:8]}; not queuing more today")
        return True
    return False


async def _reached_goal_since(db, job: EmailJob) -> bool:
    """Did a later call with this person reach the agent's goal (e.g. they booked)? Then stop follow-ups."""
    calls = (await db.execute(select(CallLog.captured).where(
        CallLog.user_id == job.user_id, CallLog.successful.is_(True), CallLog.started_at > job.created_at,
    ).order_by(CallLog.started_at.desc()).limit(200))).scalars().all()
    target = job.to_email.lower()
    return any(target in str(v).lower() for captured in calls for v in (captured or {}).values())


async def process_due() -> None:
    """Send queued customer emails whose time has come (called by the background loop)."""
    from notify.events import _once  # the delivery log, one row per (kind, ref)
    now = datetime.utcnow()
    async with async_session() as db:
        jobs = (await db.execute(select(EmailJob).where(EmailJob.status == "queued", EmailJob.send_at <= now)
                                 .order_by(EmailJob.send_at).limit(BATCH))).scalars().all()
        for job in jobs:
            settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == job.user_id))).scalars().first()
            if await is_unsubscribed(db, job.user_id, job.to_email):
                job.status, job.error = "cancelled", "They unsubscribed"
                continue
            if not job.broadcast_id:
                key = job.automation or job.kind.split("#")[0]
                auto = automations(settings).get(key)
                if not auto or not auto["enabled"]:
                    job.status, job.error = "cancelled", "Automation turned off"
                    continue
                if (job.step or 1) > len(auto["steps"]):
                    job.status, job.error = "cancelled", "Follow-up removed"
                    continue
                if (job.step or 1) > 1 and await _reached_goal_since(db, job):
                    job.status, job.error = "cancelled", "Stopped: a later call reached its goal"
                    continue
            business = (settings.sender_name if settings else None) or "Our team"
            link = unsubscribe_url(job.user_id, job.to_email)
            text = f"{job.body}\n\n--\n{business}\nUnsubscribe: {link}"
            result: dict = {}

            async def send(job=job, text=text, business=business, link=link, result=result):
                ok = await email.send_email(job.to_email, job.subject, text, html_email(job.body, business, link),
                                            reply_to=settings.reply_to if settings else None, from_name=business,
                                            unsubscribe_url=link)
                result["ok"], result["error"] = ok, email.last_error()
                return None if ok else (result["error"] or "email not configured")
            await db.commit()  # _once writes in its own session; SQLite allows one writer at a time
            await _once(job.user_id, f"auto_{job.kind}", job.ref_id, send)
            if result.get("ok"):
                job.status, job.error, job.sent_at = "sent", None, datetime.utcnow()
            else:
                job.status, job.error = "failed", result.get("error") or "Email provider not configured or rejected the message"
        await db.commit()


async def requeue(job: EmailJob, db) -> None:
    """Send a failed or cancelled email again, now."""
    await db.execute(delete(NotificationLog).where(NotificationLog.kind == f"auto_{job.kind}", NotificationLog.ref_id == job.ref_id))
    job.status, job.error, job.send_at, job.sent_at = "queued", None, datetime.utcnow(), None


async def stop_for(db, owner_id: str, to: str, reason: str) -> int:
    """Cancel everything still queued for this address. Returns how many."""
    jobs = (await db.execute(select(EmailJob).where(
        EmailJob.user_id == owner_id, func.lower(EmailJob.to_email) == to.lower(), EmailJob.status == "queued"))).scalars().all()
    for job in jobs:
        job.status, job.error = "cancelled", reason
    return len(jobs)


async def unsubscribe(owner_id: str, to: str) -> None:
    async with async_session() as db:
        if not await is_unsubscribed(db, owner_id, to):
            db.add(EmailUnsubscribe(user_id=owner_id, email=to.lower()))
        await stop_for(db, owner_id, to, "They unsubscribed")
        try:
            await db.commit()
        except IntegrityError:
            pass


def recipient_ref(address: str) -> str:
    """A stable 32-character id per address, so a bulk email reaches each person once."""
    return hashlib.sha256(address.lower().encode()).hexdigest()[:32]
