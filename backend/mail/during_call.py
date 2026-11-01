"""
Email during a phone call (mail plan, phase 1): the agent's send_email function, so "email me the price list" arrives while
they're still talking. It goes straight out, not through the queue. Each assistant switches it on (settings "during_call").

It goes to the address on file, which the agent knows exists but is never told: someone else may be using the phone. Or to an
address they give on the call, spelt back first. They asked for it, so it reaches someone who unsubscribed, never an address that
bounced or reported spam. A test call in the browser sends nothing.
"""
import asyncio
import logging
import re
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.future import select

from backend.models import Bot, CallLog, Contact, EmailJob
from database import async_session
from mail import address as mail_address, compose, designs, links, render, senders, setup, suppress, threads
from notify import automations, email

logger = logging.getLogger(__name__)

PER_CALL = 3
PER_DAY = 6
ADDRESS_SECONDS = 3   # the check of a new address is skipped if it would keep the caller waiting


async def offer(db, owner_id: str, bot_id: str, e164: Optional[str]) -> Optional[dict]:
    """What the agent can send on this call, or None when it's off. Never holds the address itself."""
    import plans
    if not (await setup.settings_for(db, bot_id))["during_call"]["enabled"] or not (await plans.includes(db, bot_id)).email_alerts:
        return None
    contact = (await db.execute(select(Contact.email).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalar_one_or_none() if e164 else None
    return {"on_file": bool(contact), "files": [{"id": f.id, "name": f.name, "when": f.when_to_send} for f in await compose._files(db, owner_id, bot_id)]}


def spec(emails: dict) -> dict:
    listed = "; ".join(f"{f['name']}" + (f" (send when: {f['when']})" if f["when"] else "") for f in emails["files"]) or "none"
    where = ("Their email is on file, so you don't need to ask for it." if emails["on_file"] else
             "You don't have their email: ask for it, spell it back letter by letter, and send only when they say it's right.")
    return {"name": "send_email", "description": (
        f"Email this caller while you talk: one of the business's files, or a short note, when they ask for it or agree to it. {where} "
        f"Files: {listed}."),
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string", "description": "The file's name exactly as listed, if it's a file"},
            "note": {"type": "string", "description": "One sentence on what you're sending, in their language"},
            "address": {"type": "string", "description": "Only an address they gave on this call and confirmed when you spelt it back"}}}}


def rules(emails: dict) -> str:
    return ("- Never read out the email address on file, or say what it is: someone else may be using this phone. Say the email is on its way."
            if emails["on_file"] else "- Before send_email, spell their email back letter by letter and wait for them to say it's right.")


async def send(owner_id: str, bot_id: str, e164: Optional[str], call_id: Optional[str], name: Optional[str], args: dict, sent_so_far: int) -> str:
    """Never raises. What comes back is for the model to read."""
    if sent_so_far >= PER_CALL:
        return "You've sent enough on this call. Tell them the team can send anything else."
    given = str(args.get("address") or "").strip()
    wanted = str(args.get("file") or "").strip().lower()
    note = str(args.get("note") or "").strip()[:300]
    async with async_session() as db:
        bot = await db.get(Bot, bot_id)
        contact = (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalars().first() if e164 else None
        to = given or (contact.email if contact else None)
        if not to or not automations.EMAIL_RE.fullmatch(to):
            return "You don't have an address for them. Ask for it and spell it back before sending."
        files = await compose._files(db, owner_id, bot_id)
        file = next((f for f in files if f.name.lower() == wanted), None) or next((f for f in files if wanted and wanted in f.name.lower()), None)
        if wanted and file is None:
            return "That file isn't in the list. Tell them the team will send it."
        why = await suppress.why_blocked(db, owner_id, to, requested=True)
        if why:
            return "That address can't be emailed. Tell them the team will follow up another way."
        if await automations._looks_abusive(db, owner_id, "during_call", to, per_day=PER_DAY):
            return "Enough has gone to that address today. Tell them the team will follow up."
        sender = await senders.sender_for(db, owner_id, bot_id)
        design = await setup.design_for(db, owner_id, bot_id, "during_call", designs.language_of(note))
        thread = await threads.thread_for(db, owner_id, bot_id, to, name, design["subject"]) if threads.enabled() else None
        job = EmailJob(user_id=owner_id, bot_id=bot_id, kind=f"during_call#{secrets.token_hex(4)}", ref_id=call_id or secrets.token_hex(16)[:36],
                       to_email=to, automation="during_call", step=1, subject="", body="", status="queued", send_at=datetime.utcnow(), merge_data={"note": note})
        db.add(job)
        await db.flush()
        tracker = links.Tracker(owner_id, job.id)
        link = automations.unsubscribe_url(owner_id, to, bot_id)
        values = {"name": name, "first_name": compose._first_name(name), "business": sender.name, "signature": sender.name,
                  "ai_note": compose.keep_known_numbers(note, f"{bot.knowledge_base or ''}\n{file.name if file else ''}"),
                  "files": [{"name": file.name, "url": file.id, "size": compose._size(file.size)}] if file else []}
        made = render.email(design, values, render.brand_of(bot.visual_config, sender.name), language=design.get("language", "en"), unsubscribe_url=link,
                            link=lambda url, kind, label: tracker(url if kind != "file" else f"file:{url}", kind, label))
        db.add_all(tracker.rows())
        job.subject, job.body = made.subject, made.text.split("\n\n--\n")[0]
        reply_to = threads.address(thread) if thread else sender.reply_to
        if given and contact is not None and not contact.email:
            contact.email = given[:120]
        if thread:
            threads.note_sent(db, thread, job)
        await db.commit()
        job_id = job.id
    if given:  # a DNS lookup: outside the session, and only as long as a caller can wait
        try:
            verdict = await asyncio.wait_for(mail_address.check(given), timeout=ADDRESS_SECONDS)
            if not verdict.ok:
                await _settle(job_id, "cancelled", verdict.reason, None)
                return "That address doesn't look right. Ask them to spell it again."
        except asyncio.TimeoutError:
            pass
    sent = await email.deliver(to, made.subject, made.text, made.html, reply_to=reply_to, from_name=sender.name, from_address=sender.address,
                               api_key=sender.api_key, unsubscribe_url=link, tags={"ws": owner_id, "job": job_id, "kind": "customer"},
                               idempotency_key=f"email-{job_id}-1")
    await _settle(job_id, "sent" if sent.ok else "failed", None if sent.ok else sent.error, sent.id)
    if not sent.ok:
        return "The email didn't go. Tell them the team will send it."
    return "Sent. Tell them it's on its way to their email, and don't read the address out."


async def _settle(job_id: str, status: str, error: Optional[str], provider_id: Optional[str]) -> None:
    async with async_session() as db:
        job = await db.get(EmailJob, job_id)
        job.status, job.error, job.provider_id, job.attempts = status, error, provider_id, 1
        job.sent_at = datetime.utcnow() if status == "sent" else None
        await db.commit()
