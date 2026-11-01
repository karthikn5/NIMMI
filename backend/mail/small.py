"""
The smaller emails (mail plan, phase 1), each with its own switch per assistant, from its design (mail/designs.py), and sent through
the usual queue, so what stops other emails stops these:

  callback_booked  a call-back was booked for them: when we'll call
  voicemail        we called and reached their voicemail
  missed_chat      they asked for a person in the chat and nobody came in time
  chat_copy        they asked for a copy of their chat (a button in the widget)
  lead_email       a lead came in from a portal or a form (mail/intake.py): on when lead sources are
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import Bot, CallbackJob, CallLog, Contact, Conversation, EmailJob, EmailSetup, Message
from database import async_session
from mail import compose, links, render, setup, suppress
from phone import display, extract_contact

logger = logging.getLogger(__name__)

KINDS = ("callback_booked", "voicemail", "missed_chat", "chat_copy", "lead_email")
WHO = {"user": "You", "assistant": "Assistant"}


async def queue(owner_id: str, bot_id: str, kind: str, ref_id: str, to: Optional[str], values: dict, stamp: str = "") -> bool:
    """One email of this kind for this ref (and `stamp`, when the same ref can have another). False when it's off or can't go."""
    import plans
    from notify import automations
    to = (to or "").strip()
    if not to or not automations.EMAIL_RE.fullmatch(to):
        return False
    async with async_session() as db:
        if not (await setup.settings_for(db, bot_id))[kind]["enabled"] or not (await plans.includes(db, bot_id)).email_alerts:
            return False
        if await suppress.why_blocked(db, owner_id, to) or await automations._looks_abusive(db, owner_id, kind, to, per_day=5):
            return False
        db.add(EmailJob(user_id=owner_id, bot_id=bot_id, kind=f"{kind}#{stamp}" if stamp else kind, ref_id=ref_id, to_email=to, automation=kind, step=1,
                        subject="", body="", send_at=datetime.utcnow(), merge_data=values))
        try:
            await db.commit()
        except IntegrityError:
            return False
    return True


async def hold_back(db, job: EmailJob) -> Optional[str]:
    """Just before it's sent: a reason to cancel it, or None."""
    import plans
    if job.bot_id is None or not (await plans.includes(db, job.bot_id)).email_alerts:
        return "The plan no longer includes it"
    return None if (await setup.settings_for(db, job.bot_id))[job.automation]["enabled"] else "Automation turned off"


async def made(db, job: EmailJob, sender, unsubscribe_url: Optional[str]) -> tuple[render.Rendered, list]:
    data = job.merge_data or {}
    bot = await db.get(Bot, job.bot_id)
    design = await setup.design_for(db, job.user_id, job.bot_id, job.automation, "en")
    values = {**data, "first_name": compose._first_name(data.get("name")), "business": sender.name, "signature": sender.name,
              "actions": await links.actions_for(db, job.user_id, job.bot_id, job.to_email)}
    tracker = links.Tracker(job.user_id, job.id)
    rendered = render.email(design, values, render.brand_of(bot.visual_config if bot else None, sender.name), unsubscribe_url=unsubscribe_url,
                            link=lambda url, kind, label: tracker(url, kind, label))
    return rendered, tracker.rows()


async def callback_booked(job_id: str) -> None:
    """Best effort; never raises."""
    from mail import after_call
    from voice import schedule
    try:
        async with async_session() as db:
            job = await db.get(CallbackJob, job_id)
            if job is None or not job.next_attempt_at:
                return
            contact = (await db.execute(select(Contact).where(Contact.bot_id == job.bot_id, Contact.e164 == job.e164))).scalars().first()
            at = schedule.utc(job.next_attempt_at)
            tz = schedule.zone(await schedule.settings_for(job.bot_id, db))
            owner, bot_id, phone = job.user_id, job.bot_id, display(job.e164)
            name = job.name or (contact.name if contact else None)
            to = contact.email if contact else None
        await queue(owner, bot_id, "callback_booked", job_id, to, {"name": name, "phone": phone, "callback_when": after_call._when(at, tz)}, stamp=str(int(at.timestamp())))
    except Exception as e:
        logger.warning(f"The call-back email for {job_id} failed: {e}")


async def voicemail(call_id: str) -> None:
    """We reached their voicemail. Best effort; never raises."""
    from mail import after_call
    try:
        async with async_session() as db:
            call = await db.get(CallLog, call_id)
            if call is None or call.outcome != "voicemail" or not call.bot_id or call.channel != "phone":
                return
            to, name = await after_call._reach(db, call)
            owner, bot_id, phone = call.user_id, call.bot_id, display(call.caller_e164) if call.caller_e164 else ""
        await queue(owner, bot_id, "voicemail", call_id, to, {"name": name, "phone": phone})
    except Exception as e:
        logger.warning(f"The voicemail email for {call_id} failed: {e}")


async def missed_chats() -> None:
    """Scheduler: someone asked for a person, who hasn't come after the assistant's minutes. Each chat once."""
    now = datetime.utcnow()
    async with async_session() as db:
        rows = (await db.execute(select(EmailSetup).where(EmailSetup.settings.isnot(None)))).scalars().all()
        due = []
        for row in rows:
            prefs = (row.settings or {}).get("missed_chat") or {}
            if not prefs.get("enabled"):
                continue
            wait = timedelta(minutes=int(prefs.get("minutes") or 10))
            chats = (await db.execute(select(Conversation).where(
                Conversation.bot_id == row.bot_id, Conversation.handoff_status == "pending", Conversation.handoff_at < now - wait,
                Conversation.handoff_at > now - timedelta(days=1)))).scalars().all()
            due += [(row.user_id, row.bot_id, c) for c in chats if not (c.visitor_session_id or "").startswith("wa:")]
    for owner, bot_id, conv in due:
        found = extract_contact(conv.captured_data or {})
        await queue(owner, bot_id, "missed_chat", conv.conversation_id, found.get("email"), {"name": found.get("name")})


async def chat_copy(bot: Bot, conv: Conversation) -> str:
    """They pressed Email me this chat. It goes only to the address they gave in this chat. Returns what to tell them."""
    found = extract_contact(conv.captured_data or {})
    if not found.get("email"):
        return "no_address"
    async with async_session() as db:
        rows = (await db.execute(select(Message).where(Message.conversation_id == conv.conversation_id, Message.role.in_(("user", "assistant")))
                                 .order_by(Message.timestamp).limit(200))).scalars().all()
    lines = [{"who": WHO[m.role], "text": m.content[:2000]} for m in rows]
    if not lines:
        return "nothing"
    done = await queue(bot.user_id, bot.bot_id, "chat_copy", conv.conversation_id, found["email"], {"name": found.get("name"), "transcript": lines}, stamp=str(len(lines)))
    return "sent" if done else "not_sent"
