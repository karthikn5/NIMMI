"""
Understanding what people send in Instagram DMs besides text, through the same steps as WhatsApp (whatsapp/understand.py): voice messages written
out (Sarvam, then Gemini), photos described with any text or amounts copied exactly, PDFs summarised. The file comes from Meta's own address in the
webhook; a copy is kept for the Inbox (those addresses expire). What's understood replaces the "(photo)" placeholder in the conversation, so the team
and later replies see it too. Videos, shared posts and reels can't be opened here: their placeholders stay.
"""
import asyncio
import logging

import ai
from backend.models import InstagramAccount, InstagramMessage, Message
from database import async_session
from instagram import graph
from whatsapp import storage
from whatsapp.understand import _ext, _hear

logger = logging.getLogger(__name__)

KINDS = ("image", "audio", "file")
MAX_DOWNLOAD = 20 * 1024 * 1024
KEEP = 16 * 1024 * 1024

PHOTO = ("A customer sent this image to a business in an Instagram message. In one or two sentences, say what it shows that matters for helping them "
         "(a product, a problem, a document, a payment screenshot...). Copy any important text, numbers or amounts exactly. No preamble.")
PDF = ("A customer sent this PDF to a business in an Instagram message. Say what it is and its key details (names, dates, amounts, items) in at most 5 "
       "short lines. No preamble.")


async def message(account: InstagramAccount, w: InstagramMessage, m: Message) -> str:
    """Fetch, keep and understand one file. Returns the message's text for the assistant."""
    media, text = dict(w.media or {}), m.content
    content, mime = None, ""
    try:
        content, mime = await graph.download(media.get("url") or "", MAX_DOWNLOAD)
    except graph.IGError as e:
        logger.warning(f"Couldn't fetch a {w.kind} someone sent on Instagram: {e}")
    if content is not None:
        mime = mime.split(";")[0].strip().lower()
        media.update(mime=mime, size=len(content))
        if len(content) <= KEEP:
            media["stored"] = await storage.save(f"instagram/{account.user_id}/{w.id}{_ext(mime)}", content, mime)
        try:
            if w.kind == "audio":
                heard = (await _hear(content, mime)).strip()
                text = f"(voice message) {heard}" if heard else "(voice message: couldn't make out the words)"
            elif w.kind == "image":
                seen = await asyncio.to_thread(ai.look, PHOTO, content, mime, 300)
                text = f"(photo: {seen})"
            elif w.kind == "file" and mime == "application/pdf":
                read = await asyncio.to_thread(ai.look, PDF, content, mime, 500)
                text = f"(PDF: {read})"
        except ai.AIError as e:
            logger.warning(f"Couldn't understand a {w.kind} someone sent on Instagram: {e}")
    media["understood"] = True
    async with async_session() as db:
        row, msg = await db.get(InstagramMessage, w.id), await db.get(Message, m.id)
        row.media = media
        msg.content = text[:8000]
        await db.commit()
    return text
