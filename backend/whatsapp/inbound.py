"""
What Meta's webhooks bring, kept before Meta is told "received" (so a crash means Meta sends it again, never a lost
message):

- a customer's message: saved in their chat (each Meta message id once, whichever server process gets it), shown in
  the Inbox, and the assistant's answer is made due (replies.py);
- delivery receipts: sent, delivered, read or failed (with Meta's reason), shown on the message;
- messages the business sent from the WhatsApp Business app on the same number (coexistence): kept in the chat, and
  the assistant leaves that chat to them for a while;
- a customer changing their number or WhatsApp user id: their chat follows them.
"""
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import Message, WhatsAppChat, WhatsAppMessage, WhatsAppNumber
from database import async_session
from notify.events import fire_and_forget, lead_captured
from realtime import notify_owner
from whatsapp import chats, graph, live, numbers, settings

logger = logging.getLogger(__name__)

MEDIA_KINDS = ("image", "video", "document", "audio", "sticker")
PLACEHOLDER = {"image": "(photo)", "video": "(video)", "audio": "(audio)", "voice": "(voice note)", "sticker": "(sticker)"}
STATUS_ORDER = {"received": 0, "sent": 1, "delivered": 2, "read": 3}


def describe(msg: dict) -> tuple[str, str, Optional[dict], Optional[str]]:
    """(kind, text for the conversation, file details, id of the message it replies to). Files are only described
    here; replies.py fetches and understands them when it answers."""
    kind = msg.get("type") or "unsupported"
    context = (msg.get("context") or {}).get("id")
    if kind == "text":
        return "text", ((msg.get("text") or {}).get("body") or "").strip() or "(empty message)", None, context
    if kind == "button":  # a quick-reply button on a template
        b = msg.get("button") or {}
        return "choice", (b.get("text") or b.get("payload") or "(tapped a button)").strip(), None, context
    if kind == "interactive":
        i = msg.get("interactive") or {}
        reply = i.get("button_reply") or i.get("list_reply") or {}
        text = (reply.get("title") or "").strip()
        if reply.get("description"):
            text += f" ({reply['description'].strip()})"
        return "choice", text or "(sent a form)", None, context
    if kind in MEDIA_KINDS:
        body = msg.get(kind) or {}
        if kind == "audio" and body.get("voice"):
            kind = "voice"
        caption = (body.get("caption") or "").strip()
        media = {k: v for k, v in {"id": body.get("id"), "mime": body.get("mime_type"), "caption": caption or None,
                                   "filename": body.get("filename"), "sha256": body.get("sha256")}.items() if v}
        label = f"(document: {body['filename']})" if kind == "document" and body.get("filename") else (
            PLACEHOLDER.get(kind) or "(document)")
        return kind, f"{label} {caption}".strip(), media, context
    if kind == "location":
        loc = msg.get("location") or {}
        place = ", ".join(p for p in (loc.get("name"), loc.get("address")) if p)
        return "location", "(location) " + (f"{place} " if place else "") + f"({loc.get('latitude')}, {loc.get('longitude')})", None, context
    if kind == "contacts":
        people = []
        for c in msg.get("contacts") or []:
            name = (c.get("name") or {}).get("formatted_name") or ""
            phones = ", ".join(p.get("phone", "") for p in c.get("phones") or [] if p.get("phone"))
            people.append(f"{name} {phones}".strip())
        return "contacts", "(shared a contact) " + "; ".join(p for p in people if p), None, context
    if kind == "reaction":
        r = msg.get("reaction") or {}
        text = f"(reacted {r['emoji']} to a message)" if r.get("emoji") else "(removed a reaction)"
        return "reaction", text, None, r.get("message_id") or context
    if kind == "order":
        return "order", "(sent an order from the catalogue)", None, context
    if kind == "request_welcome":
        return "text", "(opened the chat)", None, context
    return "unsupported", "(a kind of message WhatsApp can't show here)", None, context


def _sender(msg: dict, contacts: list[dict]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(Meta's user id, phone digits, profile name) of who sent a message."""
    phone, bsuid = msg.get("from"), msg.get("from_user_id")
    contact = next((c for c in contacts if (phone and c.get("wa_id") == phone) or (bsuid and c.get("user_id") == bsuid)),
                   contacts[0] if len(contacts) == 1 else {})
    return (bsuid or contact.get("user_id") or None, phone or contact.get("wa_id") or None,
            ((contact.get("profile") or {}).get("name") or "").strip() or None)


async def message(number: WhatsAppNumber, msg: dict, contacts: list[dict]) -> Optional[str]:
    """Keep a customer's message. Returns its chat's id when it was new, None for a repeat or one with no sender."""
    wamid = msg.get("id")
    if not wamid:
        return None
    if msg.get("type") == "system":
        await _system(number, msg)
        return None
    async with async_session() as db:
        if (await db.execute(select(WhatsAppMessage.id).where(WhatsAppMessage.wamid == wamid))).first():
            return None  # Meta sent it again
    bsuid, phone, name = _sender(msg, contacts)
    if not (bsuid or phone):
        return None
    kind, text, media, context = describe(msg)
    chat = await chats.find_or_create(number, bsuid, phone, name)
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat.id)
        number = await db.get(WhatsAppNumber, number.id)
        bot = await numbers.assistant(db, number)
        if bot is None:
            logger.warning(f"WhatsApp number {number.phone_number_id} has no assistant to answer")
            return None
        conv, new = await chats.conversation(db, chat, bot)
        at = chats.now()
        m = Message(conversation_id=conv.conversation_id, role="user", content=text, timestamp=at)
        db.add(m)
        await db.flush()
        w = WhatsAppMessage(chat_id=chat.id, message_id=m.id, wamid=wamid, direction="in", kind=kind, sent_by="customer",
                            media=media, context_wamid=context, status="received", handled=kind == "reaction", created_at=at)
        db.add(w)
        chat.last_inbound_at = chat.last_message_at = at
        chat.unread = (chat.unread or 0) + (0 if kind == "reaction" else 1)
        chat.status = "open"
        number.last_inbound_at = at
        due = None
        if (kind != "reaction" and number.ai_enabled and not chats.ai_paused(chat) and conv.handoff_status != "human"):
            due = at + timedelta(seconds=settings.clean(number.settings)["wait_seconds"])
            chat.reply_due_at = due
        try:
            await db.commit()
        except IntegrityError:  # the same message, kept a moment ago by another server process
            await db.rollback()
            return None
    if new and chat.wa_id:
        fire_and_forget(lead_captured(conv.conversation_id))  # a WhatsApp chat comes with a number to reach them
    await live.message(number.user_id, chat, m, w)
    # Live chat shows the conversation's messages too (old event name, kept for it).
    await notify_owner(number.user_id, "new_message", {
        "conversation_id": conv.conversation_id, "bot_id": bot.bot_id, "session_id": conv.visitor_session_id,
        "role": "user", "message": text, "created_at": at.timestamp()})
    if due is not None:
        from whatsapp import replies
        replies.schedule(chat.id, due)
    return chat.id


async def _system(number: WhatsAppNumber, msg: dict) -> None:
    """A customer changed their number or their WhatsApp user id: the chat moves with them."""
    system = msg.get("system") or {}
    old_user = system.get("previous_user_id") or msg.get("from_user_id")
    async with async_session() as db:
        chat = None
        if old_user:
            chat = (await db.execute(select(WhatsAppChat).where(
                WhatsAppChat.number_id == number.id, WhatsAppChat.wa_user == old_user))).scalars().first()
        if chat is None and msg.get("from"):
            chat = (await db.execute(select(WhatsAppChat).where(
                WhatsAppChat.number_id == number.id, WhatsAppChat.wa_id == msg["from"]))).scalars().first()
        if chat is None:
            return
        if system.get("user_id") or system.get("new_user_id"):
            chat.wa_user = system.get("user_id") or system.get("new_user_id")
        if system.get("wa_id") or system.get("new_wa_id"):
            chat.wa_id = system.get("wa_id") or system.get("new_wa_id")
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()


async def status(number: WhatsAppNumber, st: dict) -> None:
    """Sent, delivered, read or failed: shown on the message (never moving backwards, e.g. read back to delivered)."""
    wamid, state = st.get("id"), st.get("status")
    if not wamid or state not in ("sent", "delivered", "read", "failed"):
        return
    async with async_session() as db:
        w = (await db.execute(select(WhatsAppMessage).where(WhatsAppMessage.wamid == wamid))).scalars().first()
        if w is None:
            return
        chat = await db.get(WhatsAppChat, w.chat_id)
        if chat is None or chat.number_id != number.id:
            return
        if state == "failed":
            err = (st.get("errors") or [{}])[0]
            w.status = "failed"
            w.error = (graph.ERRORS.get(err.get("code")) or err.get("title") or "Not delivered")[:500]
            logger.warning(f"WhatsApp message to ...{(chat.wa_id or chat.wa_user)[-4:]} failed: {err.get('code')} {err.get('title')}"
                           f" {(err.get('error_data') or {}).get('details') or err.get('message') or ''}".rstrip())
        elif STATUS_ORDER.get(state, 0) > STATUS_ORDER.get(w.status or "received", 0) and w.status != "failed":
            w.status = state
        else:
            return
        await db.commit()
    await live.status(number.user_id, chat.id, w)


async def echo(number: WhatsAppNumber, e: dict) -> None:
    """A message the business sent from the WhatsApp Business app on this number: kept, and the assistant steps back."""
    wamid = e.get("id")
    if not wamid:
        return
    async with async_session() as db:
        if (await db.execute(select(WhatsAppMessage.id).where(WhatsAppMessage.wamid == wamid))).first():
            return
    kind, text, media, context = describe(e)
    chat = await chats.find_or_create(number, e.get("to_user_id"), e.get("to"), None)
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat.id)
        number = await db.get(WhatsAppNumber, number.id)
        bot = await numbers.assistant(db, number)
        if bot is None:
            return
        conv, _ = await chats.conversation(db, chat, bot)
        at = chats.now()
        m = Message(conversation_id=conv.conversation_id, role="assistant", content=text, timestamp=at)
        db.add(m)
        await db.flush()
        w = WhatsAppMessage(chat_id=chat.id, message_id=m.id, wamid=wamid, direction="out", kind=kind, sent_by="phone",
                            media=media, context_wamid=context, status="sent", handled=True, created_at=at)
        db.add(w)
        chat.last_message_at = at
        chat.ai_paused_until = at + timedelta(hours=settings.clean(number.settings)["pause_hours"])
        chat.reply_due_at = None
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return
    await live.message(number.user_id, chat, m, w)


async def number_update(number: WhatsAppNumber, field: str, value: dict) -> None:
    """Meta's news about the number itself, e.g. its sending limit."""
    limit = value.get("current_limit") or value.get("messaging_limit")
    if field == "phone_number_quality_update" and limit:
        async with async_session() as db:
            row = await db.get(WhatsAppNumber, number.id)
            row.messaging_limit = str(limit)[:40]
            await db.commit()
    elif value.get("event"):
        logger.info(f"WhatsApp {field} for {number.phone_number_id}: {value.get('event')}")
