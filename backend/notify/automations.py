"""
Automatic emails to customers.

Triggers (each can be a short sequence of up to three emails):
  chat_lead     someone shares their email in chat or on WhatsApp
  call_lead     a caller gives their email on a call
  goal_met      a call reached the agent's goal (e.g. a booking); replaces call_lead for that call
  call_missed   we called (call-back or campaign) and never reached them
  handoff_done  a person from the team finished helping them in Live chat
The AI's own email after a call replaces call_lead and goal_met where it's on (mail/after_call.py).

A trigger queues one EmailJob per step; the scheduler sends each when due. The text is filled in when it's sent, from
the chat or call as it is then (a name given after the email address still makes it in). Follow-up steps stop when the
customer unsubscribes, reports spam, the address bounces, a later call with them reaches its goal, or the business
stops them. Every email comes from the assistant's sender (mail/senders.py), replies go to the business, and there's
an unsubscribe link that's honoured before each send. Bulk emails (broadcasts) use the same queue.
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
from backend.models import CallLog, Conversation, EmailJob, IntegrationSettings, NotificationLog
from mail import address as mail_address, senders, setup, suppress, threads
from notify import email
from phone import display, extract_contact

logger = logging.getLogger(__name__)

# How long after the trigger each email goes out.
DELAYS = {"now": 0, "1h": 3600, "1d": 86400, "2d": 2 * 86400, "3d": 3 * 86400, "5d": 5 * 86400, "7d": 7 * 86400, "14d": 14 * 86400}
MAX_STEPS = 3
QUIET = int(os.getenv("EMAIL_QUIET_SECONDS", "120"))  # the welcome email waits until the chat has been quiet this long
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
          "call_missed": "Couldn't reach them", "handoff_done": "After your team helps", "broadcast": "Bulk email",
          "after_call": "After a call, by the AI", "during_call": "Sent during a call", "callback_booked": "Call-back booked",
          "voicemail": "Voicemail left", "missed_chat": "Missed live chat", "chat_copy": "Copy of the chat", "lead_email": "New lead from another place", "journey": "A journey", "question_answer": "The answer to their question", "rsvp_reminder": "Event reminder"}


def _normalize(saved: Optional[dict], default: dict) -> dict:
    """Saved settings over the defaults. Older saves had one email: {enabled, delay, subject, body}."""
    saved = saved or {}
    steps = saved.get("steps")
    if steps is None and saved.get("subject") is not None:
        steps = [_step(saved.get("delay") or "now", saved.get("subject") or "", saved.get("body") or "")]
    return {"enabled": bool(saved.get("enabled", default["enabled"])), "steps": steps or default["steps"]}


def checked(given: dict) -> dict[str, dict]:
    """Automations as saved from the dashboard ({key: {"enabled", "steps": [{"delay", "subject", "body"}]}}), checked:
    known kinds and delays, at most MAX_STEPS emails each later than the one before, text in every email that's on.
    Raises ValueError with what to fix."""
    out = {}
    for key, a in (given or {}).items():
        steps = a.get("steps") or []
        if key not in DEFAULTS or not steps or any(st.get("delay") not in DELAYS for st in steps):
            raise ValueError("Unknown email automation")
        if len(steps) > MAX_STEPS:
            raise ValueError(f"A sequence can have up to {MAX_STEPS} emails")
        offsets = [DELAYS[st["delay"]] for st in steps]
        if any(later <= earlier for earlier, later in zip(offsets, offsets[1:])):
            raise ValueError("Each follow-up has to go out after the one before it")
        on = bool(a.get("enabled"))
        if on and not all(str(st.get("subject") or "").strip() and str(st.get("body") or "").strip() for st in steps):
            raise ValueError("Add a subject and message to every email before turning it on")
        out[key] = {"enabled": on, "steps": [{"delay": st["delay"], "subject": str(st.get("subject") or "").strip()[:200],
                                              "body": str(st.get("body") or "").strip()[:5000]} for st in steps]}
    return out


def grows(before: dict, after: dict) -> list[str]:
    """Automations newly on, or with more emails than before: beyond the one-email welcome, those need Growth."""
    return [k for k, a in after.items() if a["enabled"] and (not before[k]["enabled"] or len(a["steps"]) > len(before[k]["steps"]))
            and not (k == "chat_lead" and len(a["steps"]) == 1)]


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


def _with_links(line: str) -> str:
    """A line for an email: escaped, with its web addresses as links."""
    return re.sub(r"https?://(?:[^\s<>&]|&amp;)+", lambda m: f'<a href="{m.group(0)}" style="color:#5b1f6a">{m.group(0)}</a>', html.escape(line))


def html_email(body: str, business: str, unsubscribe_url: Optional[str]) -> str:
    paragraphs = "".join(
        f'<p style="margin:0 0 14px">{"<br>".join(_with_links(line) for line in block.splitlines())}</p>'
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


def unsubscribe_url(owner_id: str, to: str, bot_id: Optional[str] = None) -> str:
    from auth import issue_scoped_token
    subject = f"{owner_id}|{to.lower()}" + (f"|{bot_id}" if bot_id else "")
    token = issue_scoped_token(subject, "email_unsub", 365 * 24 * 3600)
    base = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL", "http://localhost:8000")
    return f"{base.rstrip('/')}/api/integrations/email/unsubscribe?token={token}"


async def is_unsubscribed(db, owner_id: str, to: str) -> bool:
    """Whether this workspace mustn't email them at all (unsubscribed, spam report, bounce, stopped by the team)."""
    return await suppress.why_blocked(db, owner_id, to) is not None


def job_kind(automation: str, step: int) -> str:
    return automation if step == 1 else f"{automation}#{step}"


async def schedule(owner_id: str, kind: str, ref_id: str, to: Optional[str], values: dict,
                   bot_id: Optional[str] = None, first_only: bool = False) -> bool:
    """Queue this automation's emails for one customer, if it's on. True if queued (once per kind + ref).
    An address whose domain takes no mail gets its first email as "cancelled", with the reason, so History shows it.
    `first_only`: no follow-ups (the plan includes only the welcome email)."""
    to = (to or "").strip()
    if not to or not EMAIL_RE.fullmatch(to):
        return False
    async with async_session() as db:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        auto = automations(settings).get(kind)
        auto = (await setup.automations_for(db, owner_id, bot_id, settings)).get(kind)
        if not auto or not auto["enabled"] or await is_unsubscribed(db, owner_id, to):
            return False
        if await _looks_abusive(db, owner_id, kind, to):
            return False
    verdict = await mail_address.check(to)  # a DNS lookup: outside the session, so no connection waits on it
    values = {**values, "name": values.get("name") or "there"}
    now = datetime.utcnow()
    from mail import compose
    async with async_session() as db:
        auto = (await setup.automations_for(db, owner_id, bot_id)).get(kind) or auto  # the assistant's own, if it has them
        for i, step in enumerate(auto["steps"][:1 if first_only else MAX_STEPS], start=1):
            welcome = kind == "chat_lead" and i == 1  # the designed welcome email (mail/compose.py)
            job = EmailJob(user_id=owner_id, bot_id=bot_id, kind=job_kind(kind, i), ref_id=ref_id, to_email=to,
                           automation=kind, step=i, subject=render(step["subject"], values)[:200],
                           body=render(step["body"], values), subject_tpl=step["subject"], body_tpl=step["body"],
                           merge_data=_json_safe(values),
                           compose_state="pending" if welcome and not first_only and compose.needs_writing(kind) else None,
                           send_at=now + timedelta(seconds=DELAYS.get(step["delay"], 0) + (QUIET if welcome else 0)))
            if not verdict.ok:
                job.status = "cancelled"
                job.error = verdict.reason + (f". Did they mean {verdict.suggestion}?" if verdict.suggestion else "")
                db.add(job)
                break
            db.add(job)
        try:
            await db.commit()
        except IntegrityError:
            return False  # already queued for this lead
    return verdict.ok


def _json_safe(values: dict) -> dict:
    return {str(k): (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)) for k, v in values.items()}


async def _fresh_values(db, job: EmailJob) -> tuple[dict, Optional[str]]:
    """The placeholder values as the chat or call is now, over the ones saved when it was queued; and its assistant."""
    values = dict(job.merge_data or {})
    bot_id = job.bot_id
    captured, summary = None, None
    if job.automation in ("chat_lead", "handoff_done"):
        conv = await db.get(Conversation, job.ref_id)
        if conv is not None:
            captured, bot_id = conv.captured_data or {}, bot_id or conv.bot_id
    elif job.automation in ("call_lead", "goal_met"):
        call = await db.get(CallLog, job.ref_id)
        if call is not None:
            captured, summary, bot_id = call.captured or {}, call.summary, bot_id or call.bot_id
    if captured is not None:
        found = extract_contact(captured)
        fresh = {field_key(k): v for k, v in captured.items() if v not in (None, "")}
        fresh.update({k: v for k, v in (("name", found.get("name")), ("email", found.get("email")),
                                        ("phone", display(found["phone"]) if found.get("phone") else None),
                                        ("details", details_text(captured)), ("summary", summary)) if v})
        values.update(fresh)
    values["name"] = values.get("name") or "there"
    return values, bot_id


DAILY_CAP = int(os.getenv("AUTOMATION_DAILY_CAP", "500"))  # automatic emails one workspace can queue per day


async def _looks_abusive(db, owner_id: str, kind: str, to: str, per_day: int = 1) -> bool:
    """
    Chat details are typed by website visitors, so anyone could enter a stranger's address over and over
    to make us email them. Each address gets a given automation at most `per_day` times a day, and a workspace
    has a daily ceiling, which protects people's inboxes and our sending reputation.
    """
    since = datetime.utcnow() - timedelta(days=1)
    again = (await db.execute(select(func.count()).select_from(EmailJob).where(
        EmailJob.user_id == owner_id, EmailJob.automation == kind, func.lower(EmailJob.to_email) == to.lower(),
        EmailJob.status.notin_(("failed", "cancelled")), EmailJob.created_at >= since))).scalar_one()  # those never reached them
    if again >= per_day:
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
    from mail import after_call, broadcasts, compose, consent, journeys, outbox, small
    now = datetime.utcnow()
    async with async_session() as db:
        jobs = (await db.execute(select(EmailJob).where(EmailJob.status == "queued", EmailJob.send_at <= now)  # bulk email after everything else
                                 .order_by(EmailJob.broadcast_id.isnot(None), EmailJob.send_at).limit(BATCH))).scalars().all()
        for job in jobs:
            settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == job.user_id))).scalars().first()
            why = await suppress.why_blocked(db, job.user_id, job.to_email, marketing=bool(job.broadcast_id) or job.automation == "journey")
            if why:
                job.status, job.error = "cancelled", why
                continue
            bot_id = job.bot_id
            if compose.waiting(job):
                continue  # the AI is still writing part of it: it goes on a later pass
            if job.automation == "after_call":
                stop = await after_call.hold_back(db, job)
                if stop == "wait":
                    continue
                if stop:
                    job.status, job.error = "cancelled", stop
                    continue
            elif job.automation in small.KINDS:
                stop = await small.hold_back(db, job)
                if stop:
                    job.status, job.error = "cancelled", stop
                    continue
            elif job.automation == "journey":
                stop = await journeys.hold_back(db, job)
                if stop:
                    job.status, job.error = "cancelled", stop
                    continue
            elif job.broadcast_id and job.bot_id:
                if not await consent.has(db, job.bot_id, job.to_email):
                    job.status, job.error = "cancelled", "They no longer agree to offers and news"
                    continue
            elif job.automation != "rsvp_reminder" and not job.broadcast_id:
                key = job.automation or job.kind.split("#")[0]
                auto = (await setup.automations_for(db, job.user_id, bot_id, settings)).get(key)
                if not auto or not auto["enabled"]:
                    job.status, job.error = "cancelled", "Automation turned off"
                    continue
                if (job.step or 1) > len(auto["steps"]):
                    job.status, job.error = "cancelled", "Follow-up removed"
                    continue
                if (job.step or 1) > 1 and await _reached_goal_since(db, job):
                    job.status, job.error = "cancelled", "Stopped: a later call reached its goal"
                    continue
            values = None
            if not job.broadcast_id and job.subject_tpl is not None:  # queued since Nov 2026: filled in now
                values, bot_id = await _fresh_values(db, job)
                job.bot_id = bot_id
            sender = await senders.sender_for(db, job.user_id, bot_id, settings)
            if values is not None:  # from the chat or call as it is now, under the assistant's own sender name
                values["business"] = sender.name
                job.subject = render(job.subject_tpl, values)[:200] or job.subject
                job.body = render(job.body_tpl or "", values) or job.body
            link = unsubscribe_url(job.user_id, job.to_email, bot_id)
            thread = await threads.thread_for(db, job.user_id, bot_id, job.to_email, (job.merge_data or {}).get("name"), job.subject) \
                if threads.enabled() else None
            reply_to = threads.address(thread) if thread else sender.reply_to  # a reply comes back to Nimmi, when that's set up
            designed = job.automation == "after_call" or job.automation in small.KINDS or (
                values is not None and job.automation == "chat_lead" and (job.step or 1) == 1)
            if designed:  # from the assistant's design
                made, tracked = await (after_call.made(db, job, sender, link) if job.automation == "after_call"
                                       else small.made(db, job, sender, link) if job.automation in small.KINDS
                                       else compose.welcome(db, job, values, sender, link))
                job.subject, job.body = made.subject, made.text.split("\n\n--\n")[0]
                text, html_body = made.text, made.html
                db.add_all(tracked)
            else:
                plain = job.body
                if job.automation in ("journey", "broadcast"):  # so it can tell who clicked
                    plain, tracked = journeys.with_tracked_links(job)
                    db.add_all(tracked)
                text = f"{plain}\n\n--\n{sender.name}\nUnsubscribe: {link}"
                html_body = html_email(plain, sender.name, link)
            job.attempts = (job.attempts or 0) + 1
            result: dict = {}

            async def send(job=job, text=text, html_body=html_body, sender=sender, link=link, result=result, reply_to=reply_to):
                result["called"] = True
                sent = await email.deliver(
                    job.to_email, job.subject, text, html_body, reply_to=reply_to,
                    from_name=sender.name, from_address=broadcasts.bulk_address(sender) if job.broadcast_id else sender.address, api_key=sender.api_key, unsubscribe_url=link,
                    tags={"ws": job.user_id, "job": job.id, "kind": "customer"},
                    idempotency_key=f"email-{job.id}-{job.attempts}")  # a retry of this send is a no-op at Resend
                result["sent"] = sent
                return None if sent.ok else (sent.error or "email not configured")
            await db.commit()  # _once writes in its own session; SQLite allows one writer at a time
            await _once(job.user_id, f"auto_{job.kind}", job.ref_id, send)
            sent = result.get("sent")
            if sent is not None and sent.ok:
                job.status, job.error, job.sent_at, job.provider_id = "sent", None, datetime.utcnow(), sent.id
                if thread:
                    threads.note_sent(db, thread, job)
                await outbox.emit(db, job.user_id, "email.sent", {"email_id": job.id, "to": job.to_email, "subject": job.subject, "kind": job.automation or job.kind,
                                                                 "assistant_id": job.bot_id, "broadcast_id": job.broadcast_id, "at": job.sent_at.isoformat()})
            elif result.get("called"):
                job.status, job.error = "failed", (sent.error if sent else None) or "Email provider not configured or rejected the message"
            else:  # another process sent it already (its claim was there first)
                job.status, job.error = "sent", None
        await db.commit()


async def requeue(job: EmailJob, db) -> None:
    """Send a failed or cancelled email again, now."""
    await db.execute(delete(NotificationLog).where(NotificationLog.kind == f"auto_{job.kind}", NotificationLog.ref_id == job.ref_id))
    job.status, job.error, job.send_at, job.sent_at = "queued", None, datetime.utcnow(), None


async def stop_for(db, owner_id: str, to: str, reason: str) -> int:
    """Cancel everything still queued for this address. Returns how many."""
    jobs = (await db.execute(select(EmailJob).where(
        EmailJob.user_id == owner_id, func.lower(EmailJob.to_email) == to.lower(), EmailJob.status.in_(("queued", "held", "draft"))))).scalars().all()
    for job in jobs:
        job.status, job.error = "cancelled", reason
    return len(jobs)


async def unsubscribe(owner_id: str, to: str, scope: str = "all", bot_id: Optional[str] = None) -> None:
    """From the link in an email: "all" stops every email from this workspace, "marketing" only bulk email."""
    async with async_session() as db:
        await suppress.add(db, owner_id, to, "unsubscribed", scope=scope, bot_id=bot_id)
        if scope == "all":
            await stop_for(db, owner_id, to, "They unsubscribed")
        else:
            await suppress.cancel_queued_bulk(db, owner_id, to)
        from mail import outbox
        await outbox.emit(db, owner_id, "email.unsubscribed", {"to": to, "lead": to, "assistant_id": bot_id, "scope": scope, "reason": "unsubscribed",
                                                               "at": datetime.utcnow().isoformat(), "detail": "Only offers and news" if scope == "marketing" else "All emails"})
        await suppress.commit_quietly(db)


def recipient_ref(address: str) -> str:
    """A stable 32-character id per address, so a bulk email reaches each person once."""
    return hashlib.sha256(address.lower().encode()).hexdigest()[:32]
