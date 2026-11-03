"""
Someone who writes to the account is a lead (instagram_plan.md phase 5): a Contact for them with this assistant, known by Instagram's id for them and
their @name, without a phone number or email, and a lead in Leads like any other. Their name comes from Instagram's profile, which Meta lets the
account read once they've written.

A number or email they type in a DM (brain.learn_details, then notify/events.lead_captured) joins them up: their own contact takes it, or, if another
contact of this assistant already has it, the two become one (leads.core.merge). Only on what they typed: never by name or photo.
"""
import logging
from typing import Optional

from sqlalchemy import delete, func
from sqlalchemy.future import select

from backend.models import Contact, Conversation, InstagramAccount, InstagramChat, VoiceAgent
from database import async_session
from instagram import accounts, chats, graph

logger = logging.getLogger(__name__)


async def first_dm(chat_id: str) -> None:
    """A new person wrote: their profile, their contact, their lead. Never raises: the chat goes on without this."""
    try:
        async with async_session() as db:
            chat = await db.get(InstagramChat, chat_id)
            account = await db.get(InstagramAccount, chat.account_id) if chat else None
            if chat is None or account is None or not account.access_token:
                return
            token, igsid = account.access_token, chat.igsid
        try:
            found = await graph.profile(igsid, token)
        except graph.IGError as e:
            logger.info(f"Instagram profile not read: {e}")
            found = {}
        async with async_session() as db:
            chat = await db.get(InstagramChat, chat_id)
            account = await db.get(InstagramAccount, chat.account_id)
            if found:
                chat.username = (str(found.get("username") or "")[:120] or chat.username)
                chat.name = (str(found.get("name") or "")[:200] or chat.name)
                chat.profile_at = chats.now()
            conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
            if conv is not None:
                captured = dict(conv.captured_data or {})
                if chat.name and not captured.get("name"):
                    captured["name"] = chat.name
                if chat.username:
                    captured["instagram"] = f"@{chat.username}"
                conv.captured_data = captured
            bot = await accounts.assistant(db, account)
            remember = (await db.execute(select(VoiceAgent.remember_callers).where(VoiceAgent.bot_id == bot.bot_id))).scalar_one_or_none() if bot else False
            contact = None
            if bot is not None and remember is not False:  # "Remember callers" off keeps no contacts (as for calls and WhatsApp)
                contact = (await db.execute(select(Contact).where(Contact.bot_id == bot.bot_id, Contact.instagram_id == igsid))).scalars().first()
                if contact is None:
                    contact = Contact(user_id=account.user_id, bot_id=bot.bot_id, e164=None, email=None, name=chat.name or (f"@{chat.username}" if chat.username else None),
                                      instagram_id=igsid, instagram_username=chat.username, details={}, calls=0, source="instagram")
                    db.add(contact)
                    await db.flush()
                elif chat.username and contact.instagram_username != chat.username:
                    contact.instagram_username = chat.username
                chat.contact_id = contact.id
                if conv is not None:
                    conv.contact_id = contact.id
            await db.commit()
            owner_id, contact_id, answered = account.user_id, contact.id if contact else None, bool(account.ai_enabled)
            origin = conv.origin if conv is not None else None
            conv_id = conv.conversation_id if conv is not None else chat_id
            bot_id = bot.bot_id if bot is not None else None
        if contact_id:
            from leads import core as leads, origin as lead_origin
            from mail import journeys
            # The assistant answers DMs, so it's an enquiry already answered (no first task), as for a call; with it off, the team gets one.
            await leads.came_in(owner_id, contact_id, "Instagram", conv_id, origin=origin, first_step=not answered, answered=answered)
            # A journey for Instagram leads starts as soon as they write (phase 7), not only once they type a number or email: its steps that need one
            # wait or are skipped, and telling the team works for everyone.
            await journeys.fire(owner_id, bot_id, "new_lead", contact_id, ("instagram", *(("any_ad",) if lead_origin.from_ad(origin) else ())))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Making an Instagram lead for chat {chat_id} failed: {e!r}")


async def link_details(conversation_id: str, phone: Optional[str], email: Optional[str], name: Optional[str]) -> Optional[str]:
    """They typed a number or email in a DM: their contact takes it, or joins the contact that has it. Returns the contact's id."""
    from leads import core as leads, quality
    if phone and quality.impossible(phone):
        phone = None  # nobody's number: never kept, so strangers who typed it aren't joined together
    if not (phone or email):
        return None
    async with async_session() as db:
        conv = await db.get(Conversation, conversation_id)
        chat = await chats.for_conversation(db, conversation_id)
        if conv is None or chat is None:
            return None
        mine = await db.get(Contact, chat.contact_id or conv.contact_id) if (chat.contact_id or conv.contact_id) else None
        other = None
        if phone:
            other = (await db.execute(select(Contact).where(Contact.bot_id == conv.bot_id, Contact.e164 == phone))).scalars().first()
        if other is None and email:
            other = (await db.execute(select(Contact).where(Contact.bot_id == conv.bot_id, func.lower(Contact.email) == email.lower())
                                      .order_by(Contact.created_at))).scalars().first()
        if mine is None:
            if other is None:
                return None  # no contact kept for them (Remember callers off): the usual chat lead handling makes one
            target = other
        elif other is None or other.id == mine.id:
            target = mine
            if phone and not mine.e164:
                mine.e164 = phone
            if email and not mine.email:
                mine.email = email[:120]
        else:
            how = "the number" if phone and other.e164 == phone else "the email"
            await leads.merge(db, mine, other, f"they gave {how} in an Instagram DM")
            target = other
        if name and (not target.name or target.name.startswith("@")):
            target.name = name[:80]
        if not target.instagram_id:
            target.instagram_id, target.instagram_username = chat.igsid, chat.username
        chat.contact_id = conv.contact_id = target.id
        await db.commit()
        return target.id


async def erase(db, owner_id: str, contact_ids: list[str]) -> int:
    """Compliance > Erase: their Instagram chats go with them, conversations and messages included (the caller commits). How many chats."""
    if not contact_ids:
        return 0
    found = (await db.execute(select(InstagramChat).where(InstagramChat.user_id == owner_id, InstagramChat.contact_id.in_(contact_ids)))).scalars().all()
    conv_ids = [c.conversation_id for c in found if c.conversation_id]
    if conv_ids:
        await db.execute(delete(Conversation).where(Conversation.conversation_id.in_(conv_ids)))
    await db.execute(delete(InstagramChat).where(InstagramChat.id.in_([c.id for c in found])))
    return len(found)
