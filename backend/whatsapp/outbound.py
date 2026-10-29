"""
Sending on WhatsApp, for the assistant and the team alike. Each message goes through Meta, then is kept (a Message in
the conversation, a WhatsAppMessage with Meta's id for delivery receipts) and shown in the Inbox. One Meta refuses is
kept too, marked failed with the reason, so the team sees what didn't go out. If Meta says the access token no longer
works, the number is marked as needing attention (WhatsApp > Overview).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.models import Message, User, WhatsAppChat, WhatsAppFile, WhatsAppMessage, WhatsAppNumber
from database import async_session
from whatsapp import chats, graph, live, storage

logger = logging.getLogger(__name__)

MEDIA_FRESH = timedelta(days=25)  # Meta keeps an uploaded file 30 days; upload again a little before


async def _keep(number: WhatsAppNumber, chat: WhatsAppChat, *, text: str, kind: str, sent_by: str,
                author_id: Optional[str], wamid: Optional[str], error: Optional[str], media: Optional[dict] = None,
                message_id: Optional[str] = None) -> WhatsAppMessage:
    at = chats.now()
    async with async_session() as db:
        m = await db.get(Message, message_id) if message_id else None
        if m is None:
            m = Message(conversation_id=chat.conversation_id, role="assistant", content=text, author_id=author_id, timestamp=at)
            db.add(m)
            await db.flush()
        w = WhatsAppMessage(chat_id=chat.id, message_id=m.id, wamid=wamid or None, direction="out", kind=kind,
                            sent_by=sent_by, author_id=author_id, media=media, status="failed" if error else "sent",
                            error=(error or None) and error[:500], handled=True, created_at=at)
        db.add(w)
        row = await db.get(WhatsAppChat, chat.id)
        row.last_message_at = at
        user = await db.get(User, author_id) if author_id else None
        author = user.name if user else None
        await db.commit()
    await live.message(number.user_id, row, m, w, author)
    return w


async def _trouble(number: WhatsAppNumber, e: graph.GraphError) -> None:
    if e.token_problem:
        async with async_session() as db:
            row = await db.get(WhatsAppNumber, number.id)
            row.status, row.status_detail = "error", str(e)[:500]
            await db.commit()


async def send_text(number: WhatsAppNumber, chat: WhatsAppChat, text: str, *, sent_by: str,
                    author_id: Optional[str] = None, reply_to: Optional[str] = None, buttons: Optional[list[str]] = None,
                    message_id: Optional[str] = None) -> WhatsAppMessage:
    """A text (with reply buttons, if given). `message_id`: the conversation already has this message (Live chat)."""
    wamid, error = None, None
    try:
        if buttons:
            wamid = await graph.send_buttons(number.phone_number_id, number.access_token, chats.address(chat), text,
                                             buttons, reply_to)
        else:
            wamid = await graph.send_text(number.phone_number_id, number.access_token, chats.address(chat), text, reply_to)
    except graph.GraphError as e:
        error = str(e)
        logger.warning(f"WhatsApp message to ...{chats.address(chat)[-4:]} not sent: {e}")
        await _trouble(number, e)
    shown = text + ("\n" + " | ".join(f"[{b}]" for b in buttons) if buttons else "")
    return await _keep(number, chat, text=shown, kind="choice" if buttons else "text", sent_by=sent_by,
                       author_id=author_id, wamid=wamid, error=error, message_id=message_id)


async def media_id(number: WhatsAppNumber, f: WhatsAppFile, fresh: bool = False) -> str:
    """The file's id at Meta for this number, uploading it when there's none (or it's getting old)."""
    known = (f.meta_media or {}).get(number.phone_number_id) or {}
    try:
        uploaded = datetime.fromisoformat(known["at"]) if known.get("at") else None
    except ValueError:
        uploaded = None
    if known.get("id") and uploaded and chats.aware(uploaded) > chats.now() - MEDIA_FRESH and not fresh:
        return known["id"]
    content = await storage.load(f.stored)
    if content is None:
        raise graph.GraphError("The file is missing from storage. Upload it again in WhatsApp > Files.")
    mid = await graph.upload_media(number.phone_number_id, number.access_token, content, f.mime, f.filename)
    async with async_session() as db:
        row = await db.get(WhatsAppFile, f.id)
        row.meta_media = {**(row.meta_media or {}), number.phone_number_id: {"id": mid, "at": chats.now().isoformat()}}
        await db.commit()
    return mid


async def send_file(number: WhatsAppNumber, chat: WhatsAppChat, f: WhatsAppFile, *, sent_by: str,
                    author_id: Optional[str] = None, caption: Optional[str] = None) -> WhatsAppMessage:
    caption = (caption if caption is not None else f.caption) or None
    wamid, error = None, None
    for attempt in range(2):
        try:
            mid = await media_id(number, f, fresh=attempt > 0)
            wamid = await graph.send_media(number.phone_number_id, number.access_token, chats.address(chat), f.kind, mid,
                                           caption=caption, filename=f.filename)
            error = None
            break
        except graph.GraphError as e:
            error = str(e)
            if e.code not in (131053, 100) or attempt:  # an old upload Meta no longer has: once more, freshly
                await _trouble(number, e)
                break
    if error:
        logger.warning(f"WhatsApp file to ...{chats.address(chat)[-4:]} not sent: {error}")
    else:
        async with async_session() as db:
            row = await db.get(WhatsAppFile, f.id)
            row.sends = (row.sends or 0) + 1
            await db.commit()
    media = {"file_id": f.id, "mime": f.mime, "filename": f.filename, "size": f.size, "stored": f.stored, "caption": caption}
    text = f'(sent the file "{f.name}")' + (f" {caption}" if caption else "")
    return await _keep(number, chat, text=text, kind=f.kind, sent_by=sent_by, author_id=author_id, wamid=wamid,
                       error=error, media=media)
