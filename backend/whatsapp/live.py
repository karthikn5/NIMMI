"""What the dashboard's WhatsApp Inbox is told as things happen (Socket.IO, to the workspace's own room), and how a
message looks to it. The Inbox also re-reads the open chat every few seconds, so nothing depends on a socket alone."""
import hashlib
import hmac
import os
import time
from typing import Optional

from backend.models import Message, WhatsAppChat, WhatsAppMessage
from realtime import notify_owner
from whatsapp import chats

MEDIA_LINK_SECONDS = 3600


def _iso(at) -> Optional[str]:
    at = chats.aware(at)
    return at.isoformat() if at else None


def _key() -> bytes:
    return (os.getenv("JWT_SECRET") or "dev-secret").encode()


def media_url(wa_message_id: str) -> str:
    """A link to a message's file for <img>/<audio> tags (which can't send the sign-in header), valid for an hour."""
    expires = int(time.time()) + MEDIA_LINK_SECONDS
    sig = hmac.new(_key(), f"{wa_message_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/whatsapp/media/{wa_message_id}?e={expires}&s={sig}"


def media_link_ok(wa_message_id: str, expires: int, sig: str) -> bool:
    if expires < time.time():
        return False
    expected = hmac.new(_key(), f"{wa_message_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, sig or "")


def message_json(m: Message, w: Optional[WhatsAppMessage], author: Optional[str] = None) -> dict:
    sent_by = w.sent_by if w and w.sent_by else (
        "customer" if m.role == "user" else "note" if m.role == "note" else "team" if m.author_id else "ai")
    media = None
    if w and w.media:
        media = {k: w.media.get(k) for k in ("mime", "filename", "caption", "size") if w.media.get(k)}
        if w.media.get("stored"):
            media["url"] = media_url(w.id)
    return {
        "id": m.id, "role": m.role, "text": m.content, "at": _iso(w.created_at if w else m.timestamp) or _iso(m.timestamp),
        "kind": w.kind if w else "text", "sent_by": sent_by, "author": author,
        "status": w.status if w else None, "error": w.error if w else None, "media": media,
        "wa_message_id": w.id if w else None,
    }


def chat_json(chat: WhatsAppChat, last: Optional[dict] = None) -> dict:
    ends = chats.window_ends(chat)
    return {
        "id": chat.id, "number_id": chat.number_id, "bot_id": chat.bot_id, "conversation_id": chat.conversation_id,
        "name": chats.label(chat), "profile_name": chat.profile_name,
        "phone": f"+{chat.wa_id}" if chat.wa_id else None, "status": chat.status, "unread": chat.unread or 0,
        "assigned_to": chat.assigned_to, "ai_paused_until": _iso(chat.ai_paused_until) if chats.ai_paused(chat) else None,
        "window_ends": _iso(ends) if ends and chats.window_open(chat) else None,
        "last_message_at": _iso(chat.last_message_at), "last": last,
    }


async def message(owner_id: str, chat: WhatsAppChat, m: Message, w: Optional[WhatsAppMessage], author: Optional[str] = None) -> None:
    await notify_owner(owner_id, "wa_message", {"chat": chat_json(chat), "message": message_json(m, w, author)})


async def status(owner_id: str, chat_id: str, w: WhatsAppMessage) -> None:
    await notify_owner(owner_id, "wa_status", {"chat_id": chat_id, "wa_message_id": w.id, "message_id": w.message_id,
                                               "status": w.status, "error": w.error})


async def chat_changed(owner_id: str, chat: WhatsAppChat) -> None:
    await notify_owner(owner_id, "wa_chat", {"chat": chat_json(chat)})
