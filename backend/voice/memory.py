"""
What an assistant remembers about the people it talks to on the phone, by their number (Voice > Contacts).

After every phone call the caller's contact is brought up to date from what the call collected. At the start of the
next call, incoming or outgoing, the agent gets their name, what they told it, the team's notes and what earlier calls
were about, so it greets them by name and picks up where they left off. Calls from before contacts existed count too.
Each assistant keeps its own contacts: one account can run assistants for different businesses.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import CallLog, Contact
from database import async_session
from phone import extract_contact

logger = logging.getLogger(__name__)

RECENT_CALLS = 5       # earlier calls the agent hears about
SUMMARY_CHARS = 300
DETAIL_KEYS = 30       # collected details kept per contact
# Calls with nothing to remember: nobody answered, a machine did, or the call never got going.
NOTHING_SAID = ("no_answer", "voicemail", "in_progress")
IST = timezone(timedelta(hours=5, minutes=30))


def _day(at: Optional[datetime], now: Optional[datetime] = None) -> str:
    """When a call or chat was, as the business sees it: "today at 4:10 pm", "yesterday at 6 pm", else "28 Oct" (stored
    in UTC; SQLite keeps it without a zone). Oct 2026, live: given only "30 Oct", the agent told someone who had called an
    hour before that they'd asked "yesterday"."""
    if at is None:
        return ""
    local = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(IST)
    today = (now or datetime.now(timezone.utc)).astimezone(IST).date()
    if local.date() in (today, today - timedelta(days=1)):
        clock = f"{local.hour % 12 or 12}{f':{local.minute:02d}' if local.minute else ''} {'am' if local.hour < 12 else 'pm'}"
        return f"{'today' if local.date() == today else 'yesterday'} at {clock}"
    return local.strftime("%d %b").lstrip("0")


def first_name(name: Optional[str]) -> Optional[str]:
    """'K. Karthik Raja' -> 'Karthik': how the agent greets them."""
    for word in re.split(r"[\s,]+", (name or "").strip()):
        word = word.strip(".")
        if len(word) > 1 and any(ch.isalpha() for ch in word):  # never "123" or a WhatsApp name of only symbols
            return word[:30]
    return None


async def remember_call(call_id: str) -> None:
    """After a phone call: the caller's contact, made or brought up to date. Best effort; never raises."""
    try:
        for _ in range(2):  # two calls from one number ending at once, on different servers: the second retries
            try:
                await _remember(call_id)
                return
            except IntegrityError:
                continue
    except Exception as e:
        logger.warning(f"Remembering call {call_id} failed: {e}")


async def _remember(call_id: str) -> None:
    async with async_session() as db:
        call = (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()
        if (not call or call.channel != "phone" or not call.caller_e164 or not call.bot_id
                or call.outcome in NOTHING_SAID or (call.outcome == "failed" and not call.captured)):
            return
        contact = (await db.execute(select(Contact).where(
            Contact.bot_id == call.bot_id, Contact.e164 == call.caller_e164))).scalars().first()
        if contact is None:
            contact = Contact(user_id=call.user_id, bot_id=call.bot_id, e164=call.caller_e164, details={}, calls=0)
            db.add(contact)
        captured = call.captured or {}
        found = extract_contact(captured)
        name = (found.get("name") or "").strip()[:80]
        if name and not (contact.name and name.lower() in contact.name.lower()):  # "Arjun" doesn't replace "Arjun Kumar"
            contact.name = name
        if found.get("email"):
            contact.email = found["email"][:120]
        details = dict(contact.details or {})
        for key, value in captured.items():
            if value in (None, "", []) or str(key).lower() in ("name", "email", "phone"):
                continue
            if found.get("name") == value or found.get("email") == value or found.get("phone") == value:
                continue  # already kept as name, email or the number itself
            details[str(key)[:40]] = str(value)[:200]
        contact.details = dict(list(details.items())[-DETAIL_KEYS:])
        contact.calls = (contact.calls or 0) + 1
        when = call.started_at or datetime.utcnow()
        contact.first_call_at = contact.first_call_at or when
        contact.last_call_at = when
        await db.commit()


async def context_for(bot_id: str, e164: Optional[str]) -> Optional[dict]:
    """What the agent knows about a number when a call starts, or None if it hasn't spoken to them (or was told to
    forget them)."""
    if not e164:
        return None
    async with async_session() as db:
        contact = (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalars().first()
        query = select(CallLog).where(CallLog.bot_id == bot_id, CallLog.caller_e164 == e164, CallLog.channel == "phone",
                                      CallLog.outcome.notin_(NOTHING_SAID))
        if contact is not None and contact.remember_from is not None:
            query = query.where(CallLog.started_at >= contact.remember_from)
        calls = (await db.execute(query.order_by(CallLog.started_at.desc()).limit(RECENT_CALLS))).scalars().all()
    name = contact.name if contact else None
    email = contact.email if contact else None
    if not name or not email:  # calls from before contacts existed
        for call in calls:
            found = extract_contact(call.captured or {})
            name, email = name or found.get("name"), email or found.get("email")
    history = [{"when": _day(c.started_at), "direction": c.direction,
                "summary": (c.summary or "").strip()[:SUMMARY_CHARS]} for c in calls if (c.summary or "").strip()]
    details = dict((contact.details or {}) if contact else {})
    notes = (contact.notes or "").strip() if contact else ""
    chats = await _whatsapp_chats(bot_id, e164, contact.remember_from if contact else None)
    if not (name or history or details or notes or chats):
        return None
    return {"name": name, "first_name": first_name(name), "has_email": bool(email), "details": details,
            "notes": notes[:1000], "calls": history, "chats": chats,
            "language": calls[0].language if calls else None}  # where their last call ended up


async def _whatsapp_chats(bot_id: str, e164: str, since: Optional[datetime]) -> list[dict]:
    """What their WhatsApp chats with this assistant were about (summaries, written once a chat goes quiet)."""
    from backend.models import WhatsAppChat
    async with async_session() as db:
        query = select(WhatsAppChat).where(WhatsAppChat.bot_id == bot_id, WhatsAppChat.wa_id == e164.lstrip("+"),
                                           WhatsAppChat.summary.isnot(None))
        if since is not None:
            query = query.where(WhatsAppChat.last_message_at >= since)
        rows = (await db.execute(query.order_by(WhatsAppChat.last_message_at.desc()).limit(2))).scalars().all()
    return [{"when": _day(c.last_message_at), "summary": c.summary.strip()[:SUMMARY_CHARS]} for c in rows if c.summary.strip()]
