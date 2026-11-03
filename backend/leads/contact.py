"""
Whether something automatic may reach a lead now, and if not, why (instagram_plan.md 4.3 to 4.5, phase 4). Every automatic channel asks here just before it
sends: the lead's first email, call and WhatsApp message, Schedule's dialler, journeys and the email agent. A blocker always comes with a sentence a person can
read. One chase at a time: a reply, a person taking over, a meeting booked, an opt-out or a closed lead stops everything automatic that was waiting.

What allows a contact: for a call, their enquiry in the last seven days (TRAI Regulation 05 of 2026: an enquiry kept in writing), a call they asked for, or a
call they agreed to in the last seven days; for WhatsApp, their opt-in (a form's tick, their own message) or a message from them in the last 24 hours; for an
email about what they asked, an enquiry in the last month, and for offers their agreement (`Consent`). Their own refusal, the do-not-call list, an
unsubscribe or a bounce stops a channel whatever else says yes. A form submission doesn't open WhatsApp's 24-hour window: only their message does.
"""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import ChannelPermission, Contact, Conversation, EmailJob, LeadEvent, LeadTask, NotificationLog, PhoneNumber, User, WhatsAppChat
from phone import display

CHANNELS = ("call", "whatsapp", "email")
LABEL = {"call": "phone", "whatsapp": "WhatsApp", "email": "email"}
ENQUIRY = timedelta(days=7)          # TRAI: an enquiry kept in writing allows follow-up for seven days
SERVICE_EMAIL = timedelta(days=30)   # an email about what they asked; after this only offers they agreed to
CALL_CONSENT = timedelta(days=7)     # TRAI: explicit consent for a service call lasts seven days, and they can renew it
WORKING = timedelta(hours=24)        # a person's own try at them, or their task, this recent: nothing automatic chases meanwhile
QUIET = ("09:00", "20:00")           # when messages may go, in the business's time
# A meeting in words: a request isn't booked until the team approves it.
MEETING_STATE = {"confirmed": "a meeting booked", "requested": "a meeting request waiting for your answer", "proposed": "a new meeting time waiting for their answer"}


@dataclass
class Verdict:
    ok: bool
    reason: str = ""                       # why not, for a person to read
    code: str = ""                         # junk, no_number, no_email, dnc, email_blocked, refused, closed, person, plan, window, permission, hours, a2p
    wait_until: Optional[datetime] = None  # only a matter of time (quiet hours)
    cause: str = ""                        # what allows it, when it's allowed

    def json(self) -> dict:
        return {"ok": self.ok, "reason": self.reason, "code": self.code, "cause": self.cause, "wait_until": _iso(self.wait_until)}


def _iso(at: Optional[datetime]) -> Optional[str]:
    from voice.schedule import utc
    return utc(at).isoformat() if at else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def indian(e164: Optional[str]) -> bool:
    return bool(e164) and e164.startswith("+91")


def a2p_blocked(number: Optional[PhoneNumber]) -> Optional[str]:
    """Why this number mustn't place an automated call, or None. TRAI: from about 17 November 2026 an automated call from an undeclared Indian number is
    unsolicited commercial communication, and action can fall on the provider's and Nimmi's numbers. A2P_GATE=off turns it off (never on live)."""
    if number is None or not indian(number.e164) or number.a2p_declared_at or os.getenv("A2P_GATE", "on") == "off":
        return None
    return (f"{number.number or display(number.e164)} isn't declared for automated calls. TRAI requires it: declare the number with your phone provider, "
            "then mark it in Voice > Numbers.")


# ─── their own word ──────────────────────────────────────────────
async def permission(db, contact_id: str, channel: str, purpose: str = "service") -> Optional[ChannelPermission]:
    return (await db.execute(select(ChannelPermission).where(ChannelPermission.contact_id == contact_id, ChannelPermission.channel == channel,
                                                             ChannelPermission.purpose == purpose))).scalars().first()


def _expires(channel: str, state: str, at: datetime) -> Optional[datetime]:
    return at + CALL_CONSENT if channel == "call" and state == "granted" else None


async def record(db, contact: Contact, channel: str, state: str, source: str, words: Optional[str] = None, evidence: Optional[str] = None,
                 by: Optional[str] = None, purpose: str = "service") -> Optional[ChannelPermission]:
    """Their word, kept with where it came from (the caller commits). The team can't turn a refusal back into a yes: only the person can, by their own
    tick or message. None when it wasn't changed for that reason."""
    if channel not in CHANNELS or state not in ("granted", "refused"):
        raise ValueError(channel)
    at = _now()
    row = await permission(db, contact.id, channel, purpose)
    if row is not None and row.state == "refused" and state == "granted" and source == "team":
        return None
    if row is None:
        row = ChannelPermission(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, channel=channel, purpose=purpose)
        db.add(row)
    row.state, row.source, row.words, row.evidence, row.by = state, source, (words or "")[:500] or None, (evidence or "")[:80] or None, by
    row.given_at, row.expires_at = at.replace(tzinfo=None), (_expires(channel, state, at) or None)
    if row.expires_at is not None:
        row.expires_at = row.expires_at.replace(tzinfo=None)
    from leads import core
    verb = "agreed to" if state == "granted" else "asked not to be contacted by"
    db.add(core.event(contact, "permission", f"They {verb} {LABEL[channel]}{f': {words}' if words else ''}", by))
    return row


async def permissions_of(db, contact_id: str) -> list[dict]:
    rows = (await db.execute(select(ChannelPermission).where(ChannelPermission.contact_id == contact_id))).scalars().all()
    return [{"channel": r.channel, "purpose": r.purpose, "state": r.state, "source": r.source, "words": r.words, "given_at": _iso(r.given_at),
             "expires_at": _iso(r.expires_at)} for r in rows]


# ─── who's on it ─────────────────────────────────────────────────
async def person_on_it(db, contact: Contact, now: Optional[datetime] = None) -> Optional[str]:
    """A person on the team working this lead now, in words, or None: their chat taken over, a try of their own today, or a task they set for the next day."""
    now = now or _now()
    names = {}

    async def name(user_id: Optional[str]) -> str:
        if not user_id:
            return "Someone on your team"
        if user_id not in names:
            u = await db.get(User, user_id)
            names[user_id] = (u.name or u.email) if u else "Someone on your team"
        return names[user_id]
    taken = (await db.execute(select(Conversation.agent_id).where(Conversation.contact_id == contact.id, Conversation.handoff_status == "human"))).first()
    if taken:
        return f"{await name(taken[0])} took over their chat"
    if contact.e164:
        paused = (await db.execute(select(WhatsAppChat.ai_paused_until).where(WhatsAppChat.user_id == contact.user_id, WhatsAppChat.wa_id == contact.e164.lstrip("+"))
                                   .order_by(WhatsAppChat.ai_paused_until.desc().nulls_last()))).first()  # Postgres sorts empty first
        if paused and paused[0] and _aware(paused[0]) > now:
            return "Your team is handling their WhatsApp chat"
    tried = (await db.execute(select(LeadEvent.by).where(LeadEvent.contact_id == contact.id, LeadEvent.kind == "result", LeadEvent.by.isnot(None),
                                                         LeadEvent.at >= (now - WORKING).replace(tzinfo=None)).order_by(LeadEvent.at.desc()))).first()
    if tried:
        return f"{await name(tried[0])} tried them today"
    task = (await db.execute(select(LeadTask.title, LeadTask.created_by).where(LeadTask.contact_id == contact.id, LeadTask.status == "open", LeadTask.origin == "team",
                                                                               LeadTask.due_at <= (now + WORKING).replace(tzinfo=None)))).first()
    if task:
        return f"{await name(task[1])} plans to: {task[0]}"
    return None


# ─── the check ───────────────────────────────────────────────────
async def blockers(db, contact: Optional[Contact], channel: str, purpose: str = "service", *, now: Optional[datetime] = None, cause: Optional[str] = None,
                   since: Optional[datetime] = None, skip: tuple = (), requested: bool = False) -> Optional[Verdict]:
    """What stops a channel whatever else allows it: no way to reach them, their opt-out or refusal, a closed lead, a person on it. None when nothing does.
    `cause`: what they asked for themselves (a call-back, their meeting), which a closed lead or a person on it doesn't cancel. `since`: when they asked, so
    only a refusal after it counts. `skip`: codes that don't apply (a journey for lost leads isn't stopped by the lead being lost). `requested`: an email they
    asked for themselves (their meeting's confirmation), which an unsubscribe doesn't stop."""
    from leads import quality
    from mail import suppress
    from voice import schedule
    if contact is None:
        return Verdict(False, "They're not in your contacts any more", "gone")
    if contact.quality in ("junk", "wrong_number"):
        return Verdict(False, "Marked as junk" if contact.quality == "junk" else "Their number was wrong", "junk")
    if channel in ("call", "whatsapp"):
        if not contact.e164 or quality.impossible(contact.e164):
            return Verdict(False, "No phone number for them", "no_number")
        if await schedule.on_dnc(db, contact.user_id, contact.e164):
            return Verdict(False, "Their number is on your do-not-call list", "dnc")
    else:
        if not contact.email:
            return Verdict(False, "No email for them", "no_email")
        blocked = await suppress.why_blocked(db, contact.user_id, contact.email, marketing=purpose == "marketing", requested=requested)
        if blocked:
            return Verdict(False, blocked, "email_blocked")
    own = await permission(db, contact.id, channel, purpose)
    if own is not None and own.state == "refused" and (since is None or _aware(own.given_at) >= _aware(since)):
        return Verdict(False, f"They asked not to be contacted by {LABEL[channel]}", "refused")
    if cause:
        return None
    if "closed" not in skip and (contact.stage == "lost" or contact.lead_status == "not_interested"):
        return Verdict(False, "They said they're not interested" if contact.lead_status == "not_interested" else "The lead is closed as lost", "closed")
    if "meeting" not in skip and contact.e164:
        meeting = await schedule.upcoming_meeting(db, contact.bot_id, contact.e164)
        if meeting is not None:
            tz = schedule.zone(await schedule.settings_for(contact.bot_id, db))
            what = MEETING_STATE.get(meeting.status, "a meeting")
            return Verdict(False, f"They have {what} for {schedule.when_text(schedule.utc(meeting.starts_at), tz)}, so nothing automatic chases them meanwhile", "meeting")
    on_it = None if "person" in skip else await person_on_it(db, contact, now)
    if on_it:
        return Verdict(False, f"{on_it}, so nothing automatic goes meanwhile", "person")
    return None


def _quiet(now: datetime, tz) -> Optional[datetime]:
    """When a message may go, if not now (9 am to 8 pm in the business's time)."""
    from voice import schedule
    if schedule.allowed(now, list(QUIET), schedule.DAYS, tz):
        return None
    return schedule.next_allowed(now, list(QUIET), schedule.DAYS, tz)


async def can_contact(db, contact: Optional[Contact], channel: str, purpose: str = "service", *, now: Optional[datetime] = None, cause: Optional[str] = None,
                      hours: bool = True) -> Verdict:
    """Whether something automatic may reach them on this channel now. `cause`: they asked for it themselves. `hours`: also the time of day."""
    import plans
    from voice import schedule
    now = now or _now()
    stop = await blockers(db, contact, channel, purpose, now=now, cause=cause)
    if stop is not None:
        return stop
    included = await plans.includes(db, contact.bot_id)
    if channel == "call" and not included.schedule:
        return Verdict(False, "Calls from your assistant come with the Pro plan", "plan")
    if channel == "call":
        from voice import ai_models, metering
        from backend.models import VoiceAgent
        wallet = await metering.get_wallet(db, contact.user_id)
        model = (await db.execute(select(VoiceAgent.ai_model).where(VoiceAgent.bot_id == contact.bot_id))).scalar()
        if not metering.enough_for_a_call(metering.credits_left(wallet), ai_models.per_minute(ai_models.call_model(model))):
            return Verdict(False, "No voice credits left: buy credits in Billing", "credits")
    if channel == "whatsapp" and not included.whatsapp:
        return Verdict(False, "WhatsApp comes with the Growth plan", "plan")
    if channel == "email" and not (included.email_alerts or included.welcome_email):
        return Verdict(False, "Emails to leads come with the Starter plan", "plan")
    enquired = _aware(contact.last_enquiry_at)
    own = await permission(db, contact.id, channel, purpose)
    allowed = own is not None and own.state == "granted" and (own.expires_at is None or _aware(own.expires_at) > now)
    cause_text = ""
    if channel == "call":
        if cause:
            cause_text = cause
        elif allowed:
            cause_text = f"They agreed to a call ({own.words or own.source})"
        elif enquired and now - enquired < ENQUIRY:
            cause_text = f"Their enquiry on {enquired:%d %b} allows calls until {enquired + ENQUIRY:%d %b}"
        else:
            return Verdict(False, "Their enquiry is more than 7 days old and they haven't agreed to a call", "window")
    elif channel == "whatsapp":
        chat = (await db.execute(select(WhatsAppChat).where(WhatsAppChat.user_id == contact.user_id, WhatsAppChat.wa_id == contact.e164.lstrip("+"))
                                 .order_by(WhatsAppChat.last_inbound_at.desc().nulls_last()))).scalars().first()
        if chat is not None and chat.last_inbound_at and now - _aware(chat.last_inbound_at) < timedelta(hours=24):
            cause_text = "They wrote on WhatsApp in the last 24 hours"
        elif allowed:
            cause_text = f"They agreed to WhatsApp ({own.words or own.source})"
        elif chat is not None and chat.last_inbound_at:
            cause_text = "They started a WhatsApp chat with you"
        else:
            return Verdict(False, "They haven't agreed to WhatsApp messages: a form submission isn't an opt-in", "permission")
    else:
        from mail import consent
        if purpose == "marketing":
            if not await consent.has(db, contact.bot_id, contact.email):
                return Verdict(False, "They haven't agreed to offers and news", "permission")
            cause_text = "They agreed to offers and news"
        elif cause:
            cause_text = cause
        elif enquired and now - enquired < SERVICE_EMAIL:
            cause_text = "About the enquiry they made"
        else:
            return Verdict(False, "Their enquiry is over a month old, and they haven't agreed to offers and news", "window")
    if hours:
        settings = await schedule.settings_for(contact.bot_id, db)
        tz = schedule.zone(settings)
        if channel == "call":
            calling = settings["callbacks"]["hours"]
            if not schedule.allowed(now, calling, schedule.DAYS, tz):
                return Verdict(False, f"Outside your calling hours ({schedule.hours_text(calling)})", "hours",
                               wait_until=schedule.next_allowed(now, calling, schedule.DAYS, tz), cause=cause_text)
        else:
            later = _quiet(now, tz)
            if later is not None:
                return Verdict(False, "Messages go from 9 am to 8 pm", "hours", wait_until=later, cause=cause_text)
    return Verdict(True, cause=cause_text)


async def overview(db, contact: Contact) -> dict:
    """Each channel's answer, for the lead's page."""
    return {ch: (await can_contact(db, contact, ch)).json() for ch in CHANNELS}


async def claim(owner_id: str, key: str) -> bool:
    """One process, once: a unique row (NotificationLog). False when another got there first."""
    from database import async_session
    async with async_session() as db:
        db.add(NotificationLog(user_id=owner_id, kind="lead_first", ref_id=key[:200], status="sent"))
        try:
            await db.commit()
            return True
        except IntegrityError:
            return False


# ─── one chase at a time ─────────────────────────────────────────
async def stop_chase(db, contact: Optional[Contact], why: str) -> int:
    """Everything automatic waiting for this person stops: planned follow-up calls, journeys, the email agent's queued emails. What they asked for themselves
    (a call-back, their meeting's calls) and the team's own tasks stay. The caller commits. How many things stopped."""
    if contact is None:
        return 0
    from mail import journeys
    from voice import schedule
    count = await journeys.stop_for(db, contact.user_id, [contact.id], why)
    if contact.e164:
        count += await schedule.cancel_waiting(db, contact.bot_id, contact.e164, why, kinds=("follow_up",), statuses=("queued", "review"))
    agent = await db.execute(update(EmailJob).where(EmailJob.user_id == contact.user_id, EmailJob.automation == "agent", EmailJob.ref_id == contact.id,
                                                    EmailJob.status == "queued").values(status="cancelled", error=why[:300]).execution_options(synchronize_session=False))
    count += agent.rowcount or 0
    if count:
        from leads import core
        db.add(core.event(contact, "stopped", f"{why}: {count} automatic {'step' if count == 1 else 'steps'} stopped"))
    return count


async def stop_chase_for(db, owner_id: str, bot_id: Optional[str], e164: Optional[str] = None, email: Optional[str] = None, contact_id: Optional[str] = None,
                         why: str = "") -> int:
    """stop_chase for the lead a chat, a number or an address belongs to (the caller commits)."""
    from sqlalchemy import func
    q = select(Contact).where(Contact.user_id == owner_id)
    if contact_id:
        q = q.where(Contact.id == contact_id)
    elif e164:
        q = q.where(Contact.e164 == e164)
    elif email:
        q = q.where(func.lower(Contact.email) == email.lower())
    else:
        return 0
    if bot_id:
        q = q.where(Contact.bot_id == bot_id)
    count = 0
    for contact in (await db.execute(q)).scalars().all():
        count += await stop_chase(db, contact, why)
    return count


TOOK_OVER = "A person on your team took over the chat"
WROTE = "They wrote on WhatsApp"


async def stop_for_chat(conversation_id: Optional[str], why: str = TOOK_OVER) -> None:
    """A person took over a chat (live chat, the WhatsApp Inbox or the phone app), or they wrote: that lead's automatic steps stop. Never raises: the chat goes
    on without this."""
    import logging
    from database import async_session
    if not conversation_id:
        return
    try:
        async with async_session() as db:
            conv = await db.get(Conversation, conversation_id)
            if conv is None:
                return
            contact_id = conv.contact_id
            if not contact_id:
                from mail import journeys
                from phone import extract_contact
                found = extract_contact(conv.captured_data or {})
                session = conv.visitor_session_id or ""
                if session.startswith("wa:") and session[3:].isdigit():  # a WhatsApp chat: its number
                    found.setdefault("phone", "+" + session[3:])
                contact = await journeys.find_contact(db, conv.bot_id, found.get("phone"), found.get("email"))
                contact_id = contact.id if contact else None
            if contact_id:
                bot = conv.bot_id
                owner = (await db.execute(select(Contact.user_id).where(Contact.id == contact_id))).scalar_one_or_none()
                if owner:
                    await stop_chase_for(db, owner, bot, contact_id=contact_id, why=why)
                    await db.commit()
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning(f"Stopping the automatic steps for chat {conversation_id} failed: {e!r}")
