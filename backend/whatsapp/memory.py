"""
What the assistant remembers about a WhatsApp customer, shared with phone calls: one contact per assistant and phone
number (Voice > Contacts). Its WhatsApp replies know their name, what they told it, the team's notes and what their
phone calls were about; a phone call knows what their WhatsApp chat was about (the chat's summary, written once the
chat has been quiet for a while). Email addresses and numbers are never put in front of the AI.
"""
import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

import ai
from backend.models import Contact, Conversation, Message, WhatsAppChat
from database import async_session
from phone import extract_contact
from voice import memory as voice_memory
from whatsapp import chats

logger = logging.getLogger(__name__)

QUIET = timedelta(minutes=30)     # a chat this quiet gets its summary (re)written
RECENT = timedelta(days=7)        # older chats aren't summarised again
SUMMARY_CHARS = 300
DETAIL_KEYS = voice_memory.DETAIL_KEYS
SUMMARY_PROMPT = ("Summarise this WhatsApp chat between a customer and a business in one or two short sentences: what "
                  "the customer wanted, what they were told or sent, and anything left to do. Plain text, no names of "
                  "the business's staff, never phone numbers or email addresses.")


async def about(bot_id: str, chat: WhatsAppChat, long_chat: bool) -> list[str]:
    """Lines for the assistant about this customer (none for someone new)."""
    lines = []
    ctx = await voice_memory.context_for(bot_id, f"+{chat.wa_id}") if chat.wa_id else None
    if ctx:
        if ctx.get("name"):
            lines.append(f"- Name: {ctx['name']}")
        if ctx.get("details"):
            lines.append("- What they've told us: " + "; ".join(f"{k}: {v}" for k, v in ctx["details"].items()))
        if ctx.get("notes"):
            lines.append(f"- Notes from the team: {ctx['notes']}")
        for call in ctx.get("calls") or []:
            who = "they called" if call.get("direction") == "inbound" else "we called them"
            lines.append(f"- Phone call, {call['when']} ({who}): {call['summary']}")
    if long_chat and chat.summary:
        lines.append(f"- Earlier in this WhatsApp chat: {chat.summary}")
    return lines


async def noted(chat_id: str) -> None:
    """Bring the customer's contact up to date after a WhatsApp exchange. Best effort; never raises."""
    try:
        for _ in range(2):  # their contact made at the same moment by a phone call: the second try updates it
            try:
                await _note(chat_id)
                return
            except IntegrityError:
                continue
    except Exception as e:
        logger.warning(f"Remembering WhatsApp chat {chat_id} failed: {e}")


async def _note(chat_id: str) -> None:
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat_id)
        if not chat or not chat.wa_id or not chat.bot_id:
            return
        e164 = f"+{chat.wa_id}"
        contact = (await db.execute(select(Contact).where(Contact.bot_id == chat.bot_id, Contact.e164 == e164))).scalars().first()
        if contact is None:
            contact = Contact(user_id=chat.user_id, bot_id=chat.bot_id, e164=e164, details={}, calls=0)
            db.add(contact)
        conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
        captured = (conv.captured_data or {}) if conv else {}
        found = extract_contact(captured)
        name = (found.get("name") or "").strip()[:80]
        if name and any(ch.isalpha() for ch in name) and not (contact.name and name.lower() in contact.name.lower()):
            contact.name = name
        if found.get("email") and not contact.email:
            contact.email = found["email"][:120]
        details = dict(contact.details or {})
        for key, value in captured.items():
            if value in (None, "", []) or str(key).lower() in ("name", "email", "phone", "channel"):
                continue
            details[str(key)[:40]] = str(value)[:200]
        contact.details = dict(list(details.items())[-DETAIL_KEYS:])
        contact.chats = (await db.execute(select(func.count()).select_from(WhatsAppChat).where(
            WhatsAppChat.bot_id == chat.bot_id, WhatsAppChat.wa_id == chat.wa_id))).scalar_one()
        contact.last_chat_at = chat.last_message_at or chats.now()
        await db.commit()


async def summarise_quiet() -> None:
    """Write the summary of chats that have gone quiet since it was last written (for later chats and calls)."""
    now = chats.now()
    async with async_session() as db:
        ids = (await db.execute(select(WhatsAppChat.id).where(
            WhatsAppChat.last_message_at < now - QUIET, WhatsAppChat.last_message_at > now - RECENT,
            WhatsAppChat.conversation_id.isnot(None),
            (WhatsAppChat.summary_at.is_(None)) | (WhatsAppChat.summary_at < WhatsAppChat.last_message_at),
        ).limit(10))).scalars().all()
    for chat_id in ids:
        await _summarise(chat_id, now)


async def _summarise(chat_id: str, now) -> Optional[str]:
    async with async_session() as db:
        # Claimed first: every server process runs the scheduler, and one summary is enough.
        claimed = await db.execute(update(WhatsAppChat).where(
            WhatsAppChat.id == chat_id,
            (WhatsAppChat.summary_at.is_(None)) | (WhatsAppChat.summary_at < WhatsAppChat.last_message_at),
        ).values(summary_at=now))
        await db.commit()
        if claimed.rowcount != 1:
            return None
        chat = await db.get(WhatsAppChat, chat_id)
        rows = (await db.execute(select(Message).where(
            Message.conversation_id == chat.conversation_id, Message.role.in_(["user", "assistant"]))
            .order_by(Message.timestamp.desc()).limit(40))).scalars().all()
    if not rows:
        return None
    transcript = "\n".join(f"{'Customer' if m.role == 'user' else 'Business'}: {m.content[:400]}" for m in reversed(rows))
    try:
        summary = await asyncio.to_thread(ai.chat, SUMMARY_PROMPT, [{"role": "user", "content": transcript}],
                                          max_tokens=200, temperature=0.2, fast=True)
    except ai.AIError as e:
        logger.info(f"WhatsApp chat summary skipped: {e}")
        return None
    async with async_session() as db:
        row = await db.get(WhatsAppChat, chat_id)
        row.summary = summary.strip()[:SUMMARY_CHARS]
        await db.commit()
    return row.summary
