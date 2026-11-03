"""
Instagram chats: one per connected account and person. A person is known by Meta's id for them with that account (IGSID); their username and name
are read once they've written, as Meta allows only then. What's said lives in the assistant's usual Conversation (session "ig:<IGSID>"), so Live
chat, leads, questions and analytics treat Instagram like website chat.

Instagram's windows (Meta's messaging pages, read 3 November 2026): anything may be sent within 24 hours of their last message, or up to 7 days after
a first message from a Click-to-Direct ad; after that only a person's reply, tagged HUMAN_AGENT, within 7 days of their last message. Nothing is sent
to someone who hasn't written. The assistant answers only inside the first window, never with the tag.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, Conversation, InstagramAccount, InstagramChat
from database import async_session

WINDOW = timedelta(hours=24)
HUMAN_WINDOW = timedelta(days=7)
AD_WINDOW = timedelta(days=7)
CLOSED = "It's more than 7 days since their last message, so Instagram doesn't allow a reply until they write again."


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(at: Optional[datetime]) -> Optional[datetime]:
    """SQLite gives times back without a zone; they're stored in UTC."""
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def window_ends(chat: InstagramChat) -> Optional[datetime]:
    """When the window for anything (the assistant included) closes: 24 hours after their last message, or the 7 days an ad's first message gives."""
    last = aware(chat.last_inbound_at)
    ends = last + WINDOW if last else None
    ad = aware(chat.ad_window_until)
    if ad and (ends is None or ad > ends):
        ends = ad
    return ends


def window_open(chat: InstagramChat, at: Optional[datetime] = None) -> bool:
    ends = window_ends(chat)
    return bool(ends and ends > (at or now()))


def human_window_ends(chat: InstagramChat) -> Optional[datetime]:
    last = aware(chat.last_inbound_at)
    return last + HUMAN_WINDOW if last else None


def reply_route(chat: InstagramChat, at: Optional[datetime] = None) -> str:
    """How a person's reply may go now: "open" (as usual), "human_agent" (with the tag: after 24 hours, within 7 days), or "closed"."""
    at = at or now()
    if window_open(chat, at):
        return "open"
    ends = human_window_ends(chat)
    return "human_agent" if ends and ends > at else "closed"


def ai_paused(chat: InstagramChat) -> bool:
    until = aware(chat.ai_paused_until)
    return bool(until and until > now())


def label(chat: InstagramChat) -> str:
    return f"@{chat.username}" if chat.username else (chat.name or "Instagram user")


async def find_or_create(account: InstagramAccount, igsid: str) -> InstagramChat:
    for _ in range(2):  # the same new person's first messages on two server processes at once: the second finds the first's chat
        async with async_session() as db:
            chat = (await db.execute(select(InstagramChat).where(InstagramChat.account_id == account.id, InstagramChat.igsid == igsid))).scalars().first()
            if chat is not None:
                return chat
            chat = InstagramChat(account_id=account.id, user_id=account.user_id, bot_id=account.bot_id, igsid=igsid[:64], unread=0, status="open")
            db.add(chat)
            try:
                await db.commit()
                return chat
            except IntegrityError:
                await db.rollback()
    raise RuntimeError("Couldn't save the Instagram chat")


async def conversation(db: AsyncSession, chat: InstagramChat, bot: Bot) -> tuple[Conversation, bool]:
    """The chat's conversation with its assistant, and whether it's new (the caller commits)."""
    if chat.conversation_id:
        conv = await db.get(Conversation, chat.conversation_id)
        if conv is not None and conv.bot_id == bot.bot_id:
            return conv, False
    captured = {"channel": "instagram"}
    if chat.name:
        captured["name"] = chat.name
    if chat.username:
        captured["instagram"] = f"@{chat.username}"
    conv = Conversation(bot_id=bot.bot_id, visitor_session_id=f"ig:{chat.igsid}", captured_data=captured, contact_id=chat.contact_id)
    db.add(conv)
    await db.flush()
    chat.conversation_id, chat.bot_id = conv.conversation_id, bot.bot_id
    return conv, True


async def for_conversation(db: AsyncSession, conversation_id: str) -> Optional[InstagramChat]:
    return (await db.execute(select(InstagramChat).where(InstagramChat.conversation_id == conversation_id))).scalars().first()
