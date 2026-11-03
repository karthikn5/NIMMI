"""What the dashboard's Instagram Inbox is told as things happen (Socket.IO, to the workspace's own room), and how a message looks to it. The Inbox also
re-reads the open chat every few seconds, so nothing depends on a socket alone."""
import hashlib
import hmac
import os
import time
from typing import Optional

from backend.models import InstagramChat, InstagramMessage, Message
from instagram import chats
from realtime import notify_owner

MEDIA_LINK_SECONDS = 3600


def _iso(at) -> Optional[str]:
    at = chats.aware(at)
    return at.isoformat() if at else None


def _key() -> bytes:
    return (os.getenv("JWT_SECRET") or "dev-secret").encode()


def media_url(ig_message_id: str) -> str:
    """A link to a message's kept file for <img>/<audio> tags (which can't send the sign-in header), valid for an hour."""
    expires = int(time.time()) + MEDIA_LINK_SECONDS
    sig = hmac.new(_key(), f"ig:{ig_message_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/instagram/media/{ig_message_id}?e={expires}&s={sig}"


def media_link_ok(ig_message_id: str, expires: int, sig: str) -> bool:
    if expires < time.time():
        return False
    expected = hmac.new(_key(), f"ig:{ig_message_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, sig or "")


def message_json(m: Message, w: Optional[InstagramMessage], author: Optional[str] = None) -> dict:
    sent_by = w.sent_by if w and w.sent_by else ("customer" if m.role == "user" else "note" if m.role == "note" else "team" if m.author_id else "ai")
    media = None
    if w and w.media:
        media = {k: w.media.get(k) for k in ("type", "mime") if w.media.get(k)}
        if w.media.get("stored"):
            media["url"] = media_url(w.id)
    return {"id": m.id, "role": m.role, "text": m.content, "at": _iso(w.created_at if w else m.timestamp) or _iso(m.timestamp), "kind": w.kind if w else "text",
            "sent_by": sent_by, "author": author, "status": w.status if w else None, "error": w.error if w else None, "media": media,
            "tag": w.tag if w else None, "ig_message_id": w.id if w else None}


def chat_json(chat: InstagramChat, last: Optional[dict] = None) -> dict:
    ends, human = chats.window_ends(chat), chats.human_window_ends(chat)
    return {"id": chat.id, "account_id": chat.account_id, "bot_id": chat.bot_id, "conversation_id": chat.conversation_id, "contact_id": chat.contact_id,
            "name": chats.label(chat), "username": chat.username, "full_name": chat.name, "status": chat.status, "unread": chat.unread or 0,
            "assigned_to": chat.assigned_to, "ai_paused_until": _iso(chat.ai_paused_until) if chats.ai_paused(chat) else None,
            "window_ends": _iso(ends) if chats.window_open(chat) else None, "human_window_ends": _iso(human) if chats.reply_route(chat) != "closed" else None,
            "reply": chats.reply_route(chat), "last_message_at": _iso(chat.last_message_at), "last": last}


async def message(owner_id: str, chat: InstagramChat, m: Message, w: Optional[InstagramMessage], author: Optional[str] = None) -> None:
    await notify_owner(owner_id, "ig_message", {"chat": chat_json(chat), "message": message_json(m, w, author)})


async def status(owner_id: str, chat_id: str, w: InstagramMessage) -> None:
    await notify_owner(owner_id, "ig_status", {"chat_id": chat_id, "ig_message_id": w.id, "message_id": w.message_id, "status": w.status, "error": w.error})


async def chat_changed(owner_id: str, chat: InstagramChat) -> None:
    await notify_owner(owner_id, "ig_chat", {"chat": chat_json(chat)})
