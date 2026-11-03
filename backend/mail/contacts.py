"""
A website chat lead as a contact of its assistant (mail plan, phase 0): found by phone number, else by email, made if
new, with the name and the details they gave. The same contact then holds their calls, WhatsApp chats and emails, so
a lead who calls later is greeted by name. WhatsApp chats keep their own contacts (whatsapp/memory.py); "Remember
callers" off on the assistant's voice agent means no contacts are kept from chats either.
"""
import logging

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import Bot, Contact, Conversation, VoiceAgent
from database import async_session
from phone import extract_contact

logger = logging.getLogger(__name__)

DETAIL_KEYS = 30


CONSENT_KEY = "Offers and news"  # the chat's tick box, as the widget saves it: words the team and the person can read


async def remember_lead(conversation_id: str) -> None:
    """Best effort; never raises."""
    try:
        for _ in range(2):  # the phone and the email arriving at once, on different processes: the second retries
            try:
                await _remember(conversation_id)
                return
            except IntegrityError:
                continue
    except Exception as e:
        logger.warning(f"Keeping chat lead {conversation_id} as a contact failed: {e}")


async def _remember(conversation_id: str) -> None:
    async with async_session() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or (conv.visitor_session_id or "").startswith(("wa:", "ig:")):  # their own channels keep their contacts
            return
        bot = await db.get(Bot, conv.bot_id)
        if bot is None:
            return
        remember = (await db.execute(select(VoiceAgent.remember_callers).where(VoiceAgent.bot_id == bot.bot_id))).scalar_one_or_none()
        if remember is False:
            return
        captured = conv.captured_data or {}
        found = extract_contact(captured)
        phone, address = found.get("phone"), (found.get("email") or "").strip()
        if not (phone or address):
            return
        contact = None
        if phone:
            contact = (await db.execute(select(Contact).where(Contact.bot_id == bot.bot_id, Contact.e164 == phone))).scalars().first()
        if contact is None and address:
            contact = (await db.execute(select(Contact).where(
                Contact.bot_id == bot.bot_id, func.lower(Contact.email) == address.lower())
                .order_by(Contact.created_at))).scalars().first()
        if contact is None:
            contact = Contact(user_id=bot.user_id, bot_id=bot.bot_id, e164=phone, details={}, calls=0, source="chat")
            db.add(contact)
        elif phone and not contact.e164:
            contact.e164 = phone  # an email-only contact now has a number too
        name = (found.get("name") or "").strip()[:80]
        if name and not (contact.name and name.lower() in contact.name.lower()):  # "Arjun" doesn't replace "Arjun Kumar"
            contact.name = name
        if address and not contact.email:
            contact.email = address[:120]
        details = dict(contact.details or {})
        for key, value in captured.items():
            if value in (None, "", []) or str(key).lower() in ("name", "email", "phone") or key == CONSENT_KEY:
                continue
            if value in (found.get("name"), found.get("email"), found.get("phone")):
                continue  # already kept as the name, email or number
            details[str(key)[:40]] = str(value)[:200]
        contact.details = dict(list(details.items())[-DETAIL_KEYS:])
        if str(captured.get(CONSENT_KEY) or "").lower() == "yes" and contact.email:  # the tick box under the chat's email question
            from mail import consent, setup
            await consent.give(db, bot.user_id, bot.bot_id, contact.email, "chat", (await setup.settings_for(db, bot.bot_id))["consent"]["words"])
        await db.commit()
