"""
WhatsApp chats: one per connected number and customer.

A customer is known by Meta's user id for them (BSUID: sent with every message since April 2026, and the only id for
people who use a WhatsApp username), plus their phone number when Meta shares it. Chats that began before Meta sent
user ids are found by number and take the user id from then on.

What's said lives in the assistant's usual Conversation (visitor session "wa:<number or user id>"), so Live chat,
leads, questions and analytics treat WhatsApp like website chat. Chats from before this module reuse that
conversation; a chat whose number now has a different assistant starts a new one with it.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, Conversation, WhatsAppChat, WhatsAppNumber
from database import async_session

WINDOW = timedelta(hours=24)  # after a customer's message, anything may be sent; after that only templates


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(at: Optional[datetime]) -> Optional[datetime]:
    """SQLite gives times back without a zone; they're stored in UTC."""
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def window_ends(chat: WhatsAppChat) -> Optional[datetime]:
    last = aware(chat.last_inbound_at)
    return last + WINDOW if last else None


def window_open(chat: WhatsAppChat) -> bool:
    ends = window_ends(chat)
    return bool(ends and ends > now())


def ai_paused(chat: WhatsAppChat) -> bool:
    until = aware(chat.ai_paused_until)
    return bool(until and until > now())


def address(chat: WhatsAppChat) -> str:
    """Where messages to them go: their number when known, else Meta's user id."""
    return chat.wa_id or chat.wa_user


def label(chat: WhatsAppChat) -> str:
    return chat.profile_name or (f"+{chat.wa_id}" if chat.wa_id else "WhatsApp user")


async def find_or_create(number: WhatsAppNumber, bsuid: Optional[str], phone: Optional[str],
                         name: Optional[str]) -> WhatsAppChat:
    phone = "".join(ch for ch in (phone or "") if ch.isdigit()) or None
    for _ in range(2):  # the same new customer's first messages, on two server processes at once: the second retries
        async with async_session() as db:
            chat = None
            mine = (WhatsAppChat.number_id == number.id, WhatsAppChat.user_id == number.user_id)
            if bsuid:
                chat = (await db.execute(select(WhatsAppChat).where(*mine, WhatsAppChat.wa_user == bsuid))).scalars().first()
            if chat is None and phone:
                chat = (await db.execute(select(WhatsAppChat).where(*mine, WhatsAppChat.wa_id == phone)
                                         .order_by(WhatsAppChat.created_at))).scalars().first()
            if chat is not None:
                if bsuid and chat.wa_user != bsuid and chat.wa_user.startswith("+"):
                    chat.wa_user = bsuid
                if phone and not chat.wa_id:
                    chat.wa_id = phone
                if name and name != chat.profile_name:
                    chat.profile_name = name[:120]
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                return chat
            if not (bsuid or phone):
                raise ValueError("A WhatsApp message without a sender")
            chat = WhatsAppChat(number_id=number.id, user_id=number.user_id, bot_id=number.bot_id,
                                wa_user=bsuid or f"+{phone}", wa_id=phone, profile_name=(name or "")[:120] or None,
                                unread=0, status="open")
            db.add(chat)
            try:
                await db.commit()
                return chat
            except IntegrityError:
                await db.rollback()
    raise RuntimeError("Couldn't save the WhatsApp chat")


async def conversation(db: AsyncSession, chat: WhatsAppChat, bot: Bot) -> tuple[Conversation, bool]:
    """The chat's conversation with its assistant, and whether it's new (caller commits)."""
    conv = None
    if chat.conversation_id:
        conv = (await db.execute(select(Conversation).where(
            Conversation.conversation_id == chat.conversation_id))).scalars().first()
        if conv is not None and conv.bot_id == bot.bot_id:
            return conv, False
        conv = None
    session = f"wa:{chat.wa_id or chat.wa_user}"
    if chat.wa_id:  # a chat from before WhatsApp chats were kept
        conv = (await db.execute(select(Conversation).where(
            Conversation.bot_id == bot.bot_id, Conversation.visitor_session_id == session)
            .order_by(Conversation.created_at.desc()))).scalars().first()
    new = conv is None
    if new:
        captured = {"channel": "whatsapp"}
        if chat.profile_name:
            captured["name"] = chat.profile_name
        if chat.wa_id:
            captured["phone"] = f"+{chat.wa_id}"
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=session, captured_data=captured)
        db.add(conv)
        await db.flush()
    chat.conversation_id, chat.bot_id = conv.conversation_id, bot.bot_id
    return conv, new


async def for_conversation(db: AsyncSession, conversation_id: str) -> Optional[WhatsAppChat]:
    return (await db.execute(select(WhatsAppChat).where(
        WhatsAppChat.conversation_id == conversation_id))).scalars().first()
