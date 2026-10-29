"""
Understanding what customers send besides text, so the assistant can answer it the way a person would:

- voice notes are written out: Sarvam first (Indian languages, and Tamil/Hindi mixed with English), Gemini when
  Sarvam can't (no key, or a note longer than its 30 seconds);
- photos and stickers are described, with any text or amounts in them copied exactly;
- PDFs are summarised.

A copy of the file is kept for the Inbox (Meta deletes it after 30 days). What's understood replaces the "(voice
note)" placeholder in the conversation, so the team and later replies see it too.
"""
import asyncio
import logging
import mimetypes

import ai
from backend.models import Message, WhatsAppMessage, WhatsAppNumber
from database import async_session
from voice import sarvam
from whatsapp import graph, storage

logger = logging.getLogger(__name__)

KINDS = ("voice", "audio", "image", "sticker", "document")
MAX_DOWNLOAD = 20 * 1024 * 1024
KEEP = 16 * 1024 * 1024  # bigger files are understood but not kept

PHOTO = ("A customer sent this image to a business on WhatsApp. In one or two sentences, say what it shows that matters "
         "for helping them (a product, a problem, a document, a payment screenshot...). Copy any important text, numbers "
         "or amounts exactly. No preamble.")
PDF = ("A customer sent this PDF to a business on WhatsApp. Say what it is and its key details (names, dates, amounts, "
       "items) in at most 5 short lines. No preamble.")
HEAR = ("Write out exactly what is said in this voice message, in the language and script it's spoken in (Tamil, Hindi "
        "or other languages mixed with English stay mixed, as spoken). Only the words, nothing else.")


def _ext(mime: str, filename: str = "") -> str:
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[1][:8].lower()
    return {"audio/ogg": ".ogg", "image/webp": ".webp", "image/jpeg": ".jpg"}.get(mime) or mimetypes.guess_extension(mime) or ""


async def _hear(content: bytes, mime: str) -> str:
    if sarvam.configured():
        try:
            heard = await sarvam.transcribe(content, "voice" + _ext(mime), mime)
            if heard:
                return heard
        except Exception as e:
            logger.info(f"Sarvam couldn't write out a voice note ({e}); trying Gemini")
    try:
        return await asyncio.to_thread(ai.look, HEAR, content, mime, 600)
    except ai.AIError as e:
        logger.warning(f"Voice note couldn't be written out: {e}")
        return ""


async def message(number: WhatsAppNumber, w: WhatsAppMessage, m: Message) -> str:
    """Fetch, keep and understand one file a customer sent. Returns the message's text for the assistant."""
    media, text = dict(w.media or {}), m.content
    caption = media.get("caption") or ""
    try:
        content, mime = await graph.download_media(number.access_token, media.get("id") or "", MAX_DOWNLOAD)
    except graph.GraphError as e:
        logger.warning(f"Couldn't fetch a {w.kind} a customer sent: {e}")
        content, mime = None, ""
    if content is not None:
        mime = mime.split(";")[0].strip().lower()
        media.update(mime=mime, size=len(content))
        if len(content) <= KEEP:
            media["stored"] = await storage.save(f"{number.user_id}/{w.id}{_ext(mime, media.get('filename', ''))}", content, mime)
        try:
            if w.kind in ("voice", "audio"):
                heard = (await _hear(content, mime)).strip()
                text = f"({'voice note' if w.kind == 'voice' else 'audio'}) {heard}" if heard else (
                    "(voice note: couldn't make out the words)")
            elif w.kind in ("image", "sticker"):
                seen = await asyncio.to_thread(ai.look, PHOTO, content, mime, 300)
                text = f"({'photo' if w.kind == 'image' else 'sticker'}: {seen})" + (f" {caption}" if caption else "")
            elif w.kind == "document" and mime == "application/pdf":
                read = await asyncio.to_thread(ai.look, PDF, content, mime, 500)
                name = media.get("filename") or "PDF"
                text = f"(document {name}: {read})" + (f" {caption}" if caption else "")
        except ai.AIError as e:
            logger.warning(f"Couldn't understand a {w.kind} a customer sent: {e}")
    media["understood"] = True
    async with async_session() as db:
        row, msg = await db.get(WhatsAppMessage, w.id), await db.get(Message, m.id)
        row.media = media
        msg.content = text[:8000]
        await db.commit()
    return text
