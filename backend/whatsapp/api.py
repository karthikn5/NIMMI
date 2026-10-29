"""
The dashboard's WhatsApp section: connected numbers and how the assistant behaves on them (owners and admins), the
Inbox where the whole team reads and answers chats, the Files the assistant can send, and this month's figures.
"""
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, get_ctx, rate_limit, require_manager
from backend.models import (Bot, Conversation, IntegrationSettings, Message, TeamMember, User, WhatsAppChat, WhatsAppFile,
                            WhatsAppMessage, WhatsAppNumber)
from database import get_db
from phone import to_e164
from whatsapp import chats, graph, live, numbers, outbound, settings, storage

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

FREE_SERVICE_MESSAGES = 1000  # Meta: free replies inside the 24-hour window, per number per month (from Oct 2026)
CHATS_PAGE = 50
MESSAGES_SHOWN = 300
# What the business may upload for WhatsApp, by kind: (MIME types, largest size). Meta allows more for documents
# (100 MB); files pass through this server, so they're kept smaller.
FILE_TYPES = {
    "image": ({"image/jpeg", "image/png"}, 5 * 1024 * 1024),
    "video": ({"video/mp4", "video/3gpp"}, 16 * 1024 * 1024),
    "audio": ({"audio/mpeg", "audio/mp4", "audio/aac", "audio/ogg", "audio/amr"}, 16 * 1024 * 1024),
    "document": ({"application/pdf", "application/msword", "text/plain",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  "application/vnd.ms-powerpoint",
                  "application/vnd.openxmlformats-officedocument.presentationml.presentation"}, 30 * 1024 * 1024),
}
EXTENSIONS = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4", "3gp": "video/3gpp",
    "mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac", "ogg": "audio/ogg", "amr": "audio/amr",
    "pdf": "application/pdf", "doc": "application/msword", "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _backend_url() -> str:
    return (os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL", "http://localhost:8001")).rstrip("/")


def _iso(at) -> Optional[str]:
    at = chats.aware(at)
    return at.isoformat() if at else None


# ─── numbers ──────────────────────────────────────────────────────
def number_json(n: WhatsAppNumber, bot_name: Optional[str] = None) -> dict:
    return {
        "id": n.id, "phone_number_id": n.phone_number_id, "waba_id": n.waba_id or "", "display_number": n.display_number,
        "verified_name": n.verified_name, "bot_id": n.bot_id or "", "bot_name": bot_name, "ai_enabled": bool(n.ai_enabled),
        "settings": settings.clean(n.settings), "connection": n.connection, "status": n.status,
        "status_detail": n.status_detail, "quality_rating": n.quality_rating, "messaging_limit": n.messaging_limit,
        "has_token": bool(n.access_token), "has_app_secret": bool(n.app_secret) or bool(numbers.app_secret()),
        "verify_token": n.verify_token, "webhook_url": f"{_backend_url()}/api/integrations/whatsapp/webhook",
        "last_inbound_at": _iso(n.last_inbound_at), "created_at": _iso(n.created_at),
    }


async def _bot_names(db: AsyncSession, owner_id: str) -> dict:
    return dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all())


async def _number(db: AsyncSession, number_id: str, ctx: AuthContext) -> WhatsAppNumber:
    n = await db.get(WhatsAppNumber, number_id)
    if n is None or n.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Number not found")
    return n


async def _own_bot(db: AsyncSession, bot_id: Optional[str], ctx: AuthContext) -> Optional[str]:
    bot_id = (bot_id or "").strip()
    if not bot_id:
        return None
    if not (await db.execute(select(Bot.bot_id).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).first():
        raise HTTPException(status_code=400, detail="Choose one of your own assistants")
    return bot_id


async def _refresh(n: WhatsAppNumber) -> None:
    """Read the number's details from Meta; raises GraphError if the token or ID doesn't work."""
    info = await graph.number_info(n.phone_number_id, n.access_token)
    n.display_number = info.get("display_phone_number") or n.display_number
    n.verified_name = info.get("verified_name") or n.verified_name
    n.quality_rating = info.get("quality_rating") or n.quality_rating
    n.status, n.status_detail = "connected", None


@router.get("/numbers")
async def list_numbers(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    names = await _bot_names(db, ctx.owner_id)
    rows = (await db.execute(select(WhatsAppNumber).where(
        WhatsAppNumber.user_id == ctx.owner_id, WhatsAppNumber.status != "disconnected")
        .order_by(WhatsAppNumber.created_at))).scalars().all()
    out = [number_json(n, names.get(n.bot_id)) for n in rows]
    if ctx.role == "agent":  # the team sees which numbers there are, not how they're connected
        for n in out:
            n["verify_token"] = n["webhook_url"] = None
    return out


class ConnectIn(BaseModel):
    phone_number_id: str = Field(..., min_length=5, max_length=40)
    access_token: str = Field(..., min_length=20, max_length=2000)
    app_secret: str = Field("", max_length=200)
    waba_id: str = Field("", max_length=40)
    bot_id: Optional[str] = None


@router.post("/numbers")
async def connect_number(data: ConnectIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Connect a number from the business's own Meta app (until one-click connect, through Meta, is available)."""
    await plans.require(db, ctx.owner_id, "integrations")
    rate_limit(f"wa-connect:{ctx.owner_id}", 10, 600)
    pid, waba = data.phone_number_id.strip(), data.waba_id.strip()
    if not pid.isdigit() or (waba and not waba.isdigit()):
        raise HTTPException(status_code=400, detail="The phone number ID and WhatsApp account ID are long numbers from "
                                                    "API Setup in your Meta app.")
    bot_id = await _own_bot(db, data.bot_id, ctx)
    n = (await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.phone_number_id == pid))).scalars().first()
    if n is not None and n.user_id != ctx.owner_id and n.status != "disconnected":
        raise HTTPException(status_code=409, detail="That WhatsApp number is already connected to another workspace")
    if n is not None and n.user_id != ctx.owner_id:
        # A number another workspace disconnected: its chats stay theirs, but no longer get this number's messages.
        await db.execute(update(WhatsAppChat).where(WhatsAppChat.number_id == n.id).values(number_id=None, reply_due_at=None))
    if n is None:
        n = WhatsAppNumber(phone_number_id=pid, verify_token=numbers.new_verify_token(), settings={}, ai_enabled=True)
        db.add(n)
    n.user_id, n.connection, n.access_token = ctx.owner_id, "manual", data.access_token.strip()
    n.app_secret = data.app_secret.strip() or n.app_secret
    n.waba_id = waba or n.waba_id
    n.bot_id = bot_id or n.bot_id
    n.verify_token = n.verify_token or numbers.new_verify_token()
    try:
        await _refresh(n)
    except graph.GraphError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Meta didn't accept these details: {e}")
    if n.waba_id:
        try:
            await graph.subscribe_app(n.waba_id, n.access_token)
        except graph.GraphError as e:
            n.status_detail = f"Couldn't subscribe your app to the WhatsApp account: {e}"[:500]
    await db.commit()
    return number_json(n, (await _bot_names(db, ctx.owner_id)).get(n.bot_id))


class NumberUpdate(BaseModel):
    bot_id: Optional[str] = None
    ai_enabled: Optional[bool] = None
    settings: Optional[dict] = None
    access_token: Optional[str] = Field(None, max_length=2000)
    app_secret: Optional[str] = Field(None, max_length=200)


@router.patch("/numbers/{number_id}")
async def update_number(number_id: str, data: NumberUpdate, ctx: AuthContext = Depends(require_manager),
                        db: AsyncSession = Depends(get_db)):
    n = await _number(db, number_id, ctx)
    if data.bot_id is not None:
        n.bot_id = await _own_bot(db, data.bot_id, ctx)
    if data.ai_enabled is not None:
        n.ai_enabled = data.ai_enabled
    if data.settings is not None:
        n.settings = settings.clean({**settings.clean(n.settings), **data.settings})
    if data.app_secret:
        n.app_secret = data.app_secret.strip()
    if data.access_token:
        n.access_token = data.access_token.strip()
        try:
            await _refresh(n)
        except graph.GraphError as e:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Meta didn't accept the new token: {e}")
        if n.waba_id:  # as when connecting: Meta sends this WhatsApp account's messages to the app
            try:
                await graph.subscribe_app(n.waba_id, n.access_token)
            except graph.GraphError as e:
                n.status_detail = f"Couldn't subscribe your app to the WhatsApp account: {e}"[:500]
    await db.commit()
    return number_json(n, (await _bot_names(db, ctx.owner_id)).get(n.bot_id))


@router.post("/numbers/{number_id}/refresh")
async def refresh_number(number_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    n = await _number(db, number_id, ctx)
    try:
        await _refresh(n)
    except graph.GraphError as e:
        n.status, n.status_detail = "error", str(e)[:500]
    await db.commit()
    return number_json(n, (await _bot_names(db, ctx.owner_id)).get(n.bot_id))


@router.delete("/numbers/{number_id}")
async def disconnect_number(number_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Stop using the number. Its chats stay in the Inbox; its keys are forgotten."""
    n = await _number(db, number_id, ctx)
    n.status, n.access_token, n.app_secret, n.status_detail = "disconnected", None, None, None
    await db.execute(update(WhatsAppChat).where(WhatsAppChat.number_id == n.id).values(reply_due_at=None))
    await db.commit()
    return {"status": "disconnected"}


TEST_TEXT = "Hello from Nimmi AI. Your WhatsApp number is connected."


class TestIn(BaseModel):
    to: str = Field(..., max_length=30)
    text: str = Field(TEST_TEXT, max_length=1000)


@router.post("/numbers/{number_id}/test")
async def send_test(number_id: str, data: TestIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    n = await _number(db, number_id, ctx)
    rate_limit(f"wa-test:{ctx.owner_id}", 10, 600)
    to = to_e164(data.to)
    if not to:
        raise HTTPException(status_code=400, detail="Enter a mobile number with its country code, like +91 98765 43210")
    try:
        await graph.send_text(n.phone_number_id, n.access_token, to, data.text.strip() or TEST_TEXT)
    except graph.GraphError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "sent"}


# ─── Inbox ────────────────────────────────────────────────────────
async def _chat(db: AsyncSession, chat_id: str, ctx: AuthContext) -> WhatsAppChat:
    chat = await db.get(WhatsAppChat, chat_id)
    if chat is None or chat.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def _needs_person():
    """A chat for the team: a person was asked for or is handling it (never NULL, so "not" works too)."""
    return or_(func.coalesce(Conversation.handoff_status, "ai").in_(["pending", "human"]),
               and_(WhatsAppChat.ai_paused_until.isnot(None), WhatsAppChat.ai_paused_until > chats.now()))


@router.get("/chats")
async def list_chats(view: str = "open", q: str = Query("", max_length=80), number_id: str = "",
                     ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """view: open (everything not closed), ai (the assistant is handling), person (needs someone from the team),
    mine (assigned to me), closed."""
    query = (select(WhatsAppChat, Conversation.handoff_status)
             .outerjoin(Conversation, Conversation.conversation_id == WhatsAppChat.conversation_id)
             .where(WhatsAppChat.user_id == ctx.owner_id))
    if view == "closed":
        query = query.where(WhatsAppChat.status == "closed")
    else:
        query = query.where(WhatsAppChat.status != "closed")
        if view == "ai":
            query = query.where(~_needs_person())
        elif view == "person":
            query = query.where(_needs_person())
        elif view == "mine":
            query = query.where(WhatsAppChat.assigned_to == ctx.user_id)
    if number_id:
        query = query.where(WhatsAppChat.number_id == number_id)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        digits = re.sub(r"\D", "", q)
        query = query.where(or_(func.lower(WhatsAppChat.profile_name).like(like),
                                *([WhatsAppChat.wa_id.like(f"%{digits}%")] if len(digits) >= 3 else [])))
    rows = (await db.execute(query.order_by(WhatsAppChat.last_message_at.desc()).limit(CHATS_PAGE))).all()
    conv_ids = [c.conversation_id for c, _ in rows if c.conversation_id]
    last: dict = {}
    if conv_ids:
        ranked = (select(Message.conversation_id, Message.role, Message.content, Message.author_id,
                         func.row_number().over(partition_by=Message.conversation_id,
                                                order_by=Message.timestamp.desc()).label("n"))
                  .where(Message.conversation_id.in_(conv_ids), Message.role != "note").subquery())
        for conv_id, role, content, author_id, _ in (await db.execute(select(ranked).where(ranked.c.n == 1))).all():
            last[conv_id] = {"role": role, "text": (content or "")[:160],
                             "by": "customer" if role == "user" else "team" if author_id else "ai"}
    out = []
    for chat, handoff in rows:
        j = live.chat_json(chat, last.get(chat.conversation_id))
        j["handoff"] = handoff or "ai"
        out.append(j)
    return out


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    rows = (await db.execute(
        select(Message, WhatsAppMessage).outerjoin(WhatsAppMessage, WhatsAppMessage.message_id == Message.id)
        .where(Message.conversation_id == chat.conversation_id)
        .order_by(Message.timestamp.desc()).limit(MESSAGES_SHOWN))).all() if conv else []
    authors = dict((await db.execute(select(User.id, User.name).where(
        User.id.in_([m.author_id for m, _ in rows if m.author_id] or [""])))).all())
    n = await db.get(WhatsAppNumber, chat.number_id) if chat.number_id else None
    j = live.chat_json(chat)
    j.update(handoff=conv.handoff_status if conv else "ai", captured=(conv.captured_data or {}) if conv else {},
             number={"id": n.id, "display_number": n.display_number, "status": n.status} if n else None,
             summary=chat.summary)
    j["messages"] = [live.message_json(m, w, authors.get(m.author_id)) for m, w in reversed(rows)]
    return j


class SendIn(BaseModel):
    text: str = Field("", max_length=4096)
    file_id: Optional[str] = None
    caption: Optional[str] = Field(None, max_length=1024)


@router.post("/chats/{chat_id}/send")
async def send_in_chat(chat_id: str, data: SendIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A team member writes to the customer. The assistant then leaves the chat to the team for a while."""
    chat = await _chat(db, chat_id, ctx)
    n = await db.get(WhatsAppNumber, chat.number_id) if chat.number_id else None
    if n is None or n.status == "disconnected":
        raise HTTPException(status_code=409, detail="This chat's WhatsApp number isn't connected any more")
    if not chats.window_open(chat):
        raise HTTPException(status_code=409, detail="The 24-hour window has closed: WhatsApp only allows an approved "
                                                    "template until the customer writes again.")
    f = None
    if data.file_id:
        f = await db.get(WhatsAppFile, data.file_id)
        if f is None or f.user_id != ctx.owner_id:
            raise HTTPException(status_code=404, detail="File not found")
    elif not data.text.strip():
        raise HTTPException(status_code=400, detail="Write a message first")
    rate_limit(f"wa-send:{ctx.user_id}", 60, 60)
    # The team has it now: the assistant steps back, and what the customer said so far counts as answered.
    hours = settings.clean(n.settings)["pause_hours"]
    chat.ai_paused_until, chat.reply_due_at, chat.unread = chats.now() + timedelta(hours=hours), None, 0
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.agent_id = "human", ctx.user_id
    await db.execute(update(WhatsAppMessage).where(WhatsAppMessage.chat_id == chat.id, WhatsAppMessage.direction == "in",
                                                   WhatsAppMessage.handled.is_(False)).values(handled=True))
    await db.commit()
    if f is not None:
        w = await outbound.send_file(n, chat, f, sent_by="team", author_id=ctx.user_id, caption=data.caption)
    else:
        w = await outbound.send_text(n, chat, data.text.strip(), sent_by="team", author_id=ctx.user_id)
    m = await db.get(Message, w.message_id)
    author = (await db.get(User, ctx.user_id))
    return live.message_json(m, w, author.name if author else None)


class PauseIn(BaseModel):
    hours: Optional[int] = None


@router.post("/chats/{chat_id}/pause")
async def pause_ai(chat_id: str, data: PauseIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    n = await db.get(WhatsAppNumber, chat.number_id) if chat.number_id else None
    hours = data.hours if data.hours in settings.PAUSE_HOURS else settings.clean(n.settings if n else {})["pause_hours"]
    chat.ai_paused_until, chat.reply_due_at = chats.now() + timedelta(hours=hours), None
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.agent_id = "human", ctx.user_id
    await db.commit()
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


@router.post("/chats/{chat_id}/resume")
async def resume_ai(chat_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Hand the chat back to the assistant: it answers the customer's next message."""
    chat = await _chat(db, chat_id, ctx)
    chat.ai_paused_until = None
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.handoff_requested, conv.agent_id = "ai", False, None
    await db.commit()
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


class AssignIn(BaseModel):
    user_id: Optional[str] = None


async def _people(db: AsyncSession, owner_id: str) -> dict:
    owner = await db.get(User, owner_id)
    people = {owner_id: owner.name if owner else "Owner"}
    rows = (await db.execute(select(TeamMember.member_id, User.name).join(User, User.id == TeamMember.member_id).where(
        TeamMember.owner_id == owner_id, TeamMember.status == "active"))).all()
    people.update({mid: name for mid, name in rows if mid})
    return people


@router.get("/people")
async def list_people(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Who chats can be assigned to: the owner and active team members."""
    return [{"id": pid, "name": name or "Team member"} for pid, name in (await _people(db, ctx.owner_id)).items()]


@router.post("/chats/{chat_id}/assign")
async def assign_chat(chat_id: str, data: AssignIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    if data.user_id and data.user_id not in await _people(db, ctx.owner_id):
        raise HTTPException(status_code=400, detail="Choose someone in this workspace")
    chat.assigned_to = data.user_id or None
    await db.commit()
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


class StatusIn(BaseModel):
    status: str = Field(..., pattern="^(open|closed)$")


@router.post("/chats/{chat_id}/status")
async def set_chat_status(chat_id: str, data: StatusIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    chat.status = data.status
    if data.status == "closed":
        chat.unread = 0
    await db.commit()
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


@router.post("/chats/{chat_id}/read")
async def read_chat(chat_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The team opened the chat: nothing waiting for them, and the customer's last message shows as read."""
    chat = await _chat(db, chat_id, ctx)
    had = chat.unread or 0
    chat.unread = 0
    await db.commit()
    if had:
        last = (await db.execute(select(WhatsAppMessage.wamid).where(
            WhatsAppMessage.chat_id == chat.id, WhatsAppMessage.direction == "in")
            .order_by(WhatsAppMessage.created_at.desc()).limit(1))).scalar_one_or_none()
        n = await db.get(WhatsAppNumber, chat.number_id) if chat.number_id else None
        if last and n and n.status != "disconnected":
            await graph.mark_read(n.phone_number_id, n.access_token, last)
    return {"unread": 0}


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/chats/{chat_id}/notes")
async def add_note(chat_id: str, data: NoteIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A private note for the team: never sent to the customer, never read by the assistant."""
    chat = await _chat(db, chat_id, ctx)
    if not chat.conversation_id:
        raise HTTPException(status_code=409, detail="This chat has no messages yet")
    note = Message(conversation_id=chat.conversation_id, role="note", content=data.text.strip(), author_id=ctx.user_id,
                   timestamp=chats.now())
    db.add(note)
    await db.commit()
    author = await db.get(User, ctx.user_id)
    await live.message(ctx.owner_id, chat, note, None, author.name if author else None)
    return live.message_json(note, None, author.name if author else None)


@router.get("/media/{ref}")
async def media(ref: str, e: int = 0, s: str = "", db: AsyncSession = Depends(get_db)):
    """A file in a chat ("<message id>") or in WhatsApp > Files ("file:<id>"), through a signed link: <img> and
    <audio> tags can't send the sign-in header."""
    if not live.media_link_ok(ref, e, s):
        raise HTTPException(status_code=403, detail="This link has expired. Open the page again.")
    if ref.startswith("file:"):
        f = await db.get(WhatsAppFile, ref[5:])
        stored, mime, filename = (f.stored, f.mime, f.filename) if f else (None, None, None)
    else:
        w = await db.get(WhatsAppMessage, ref)
        info = (w.media or {}) if w else {}
        stored, mime, filename = info.get("stored"), info.get("mime"), info.get("filename")
    content = await storage.load(stored)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    name = re.sub(r'[^\w. -]', "_", filename or "file")
    return Response(content, media_type=mime or "application/octet-stream", headers={
        "Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


# ─── files ────────────────────────────────────────────────────────
def file_json(f: WhatsAppFile, bot_name: Optional[str] = None) -> dict:
    return {"id": f.id, "name": f.name, "when_to_send": f.when_to_send or "", "caption": f.caption or "", "kind": f.kind,
            "mime": f.mime, "filename": f.filename, "size": f.size, "bot_id": f.bot_id or "", "bot_name": bot_name,
            "sends": f.sends or 0, "created_at": _iso(f.created_at), "url": live.media_url(f"file:{f.id}")}


def _kind(mime: str) -> Optional[str]:
    return next((kind for kind, (types, _) in FILE_TYPES.items() if mime in types), None)


@router.get("/files")
async def list_files(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    names = await _bot_names(db, ctx.owner_id)
    rows = (await db.execute(select(WhatsAppFile).where(WhatsAppFile.user_id == ctx.owner_id)
                             .order_by(WhatsAppFile.created_at.desc()))).scalars().all()
    return [file_json(f, names.get(f.bot_id)) for f in rows]


@router.post("/files")
async def upload_file(file: UploadFile = File(...), name: str = Form(""), when_to_send: str = Form(""),
                      caption: str = Form(""), bot_id: str = Form(""), ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "integrations")
    rate_limit(f"wa-file:{ctx.owner_id}", 30, 600)
    filename = os.path.basename(file.filename or "file")[:240]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = EXTENSIONS.get(ext) or (file.content_type or "").split(";")[0].strip().lower()
    kind = _kind(mime)
    if kind is None:
        raise HTTPException(status_code=400, detail="WhatsApp can send JPG or PNG photos, MP4 videos, MP3/M4A/OGG audio, "
                                                    "and PDF, Word, Excel, PowerPoint or text documents.")
    limit = FILE_TYPES[kind][1]
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=400, detail=f"That {kind} is too big: WhatsApp takes up to {limit // (1024 * 1024)} MB.")
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty")
    f = WhatsAppFile(id=str(uuid.uuid4()), user_id=ctx.owner_id, bot_id=await _own_bot(db, bot_id, ctx),
                     name=(name.strip() or filename.rsplit(".", 1)[0])[:120], when_to_send=when_to_send.strip()[:500] or None,
                     caption=caption.strip()[:1024] or None, kind=kind, mime=mime, filename=filename, size=len(content),
                     stored="", sends=0, meta_media={})
    f.stored = await storage.save(f"{ctx.owner_id}/{f.id}.{ext or 'bin'}", content, mime)
    db.add(f)
    await db.commit()
    return file_json(f, (await _bot_names(db, ctx.owner_id)).get(f.bot_id))


class FileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    when_to_send: Optional[str] = Field(None, max_length=500)
    caption: Optional[str] = Field(None, max_length=1024)
    bot_id: Optional[str] = None


@router.patch("/files/{file_id}")
async def update_file(file_id: str, data: FileUpdate, ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    f = await db.get(WhatsAppFile, file_id)
    if f is None or f.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="File not found")
    if data.name is not None and data.name.strip():
        f.name = data.name.strip()
    if data.when_to_send is not None:
        f.when_to_send = data.when_to_send.strip() or None
    if data.caption is not None:
        f.caption = data.caption.strip() or None
    if data.bot_id is not None:
        f.bot_id = await _own_bot(db, data.bot_id, ctx)
    await db.commit()
    return file_json(f, (await _bot_names(db, ctx.owner_id)).get(f.bot_id))


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    f = await db.get(WhatsAppFile, file_id)
    if f is None or f.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="File not found")
    await storage.delete(f.stored)
    await db.delete(f)
    await db.commit()
    return {"status": "deleted"}


# ─── after phone calls ────────────────────────────────────────────
class ConfirmationsIn(BaseModel):
    enabled: bool = False
    template: str = Field("", max_length=120)
    language: str = Field("en", max_length=10)


def _confirmations_json(s: Optional[IntegrationSettings]) -> dict:
    return {"enabled": bool(s and s.whatsapp_enabled), "template": (s.whatsapp_template if s else None) or "",
            "language": (s.whatsapp_language if s else None) or "en"}


@router.get("/confirmations")
async def get_confirmations(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The approved template sent to a caller after a call that captured a lead (notify/events.py)."""
    return _confirmations_json((await db.execute(select(IntegrationSettings).where(
        IntegrationSettings.user_id == ctx.owner_id))).scalars().first())


@router.put("/confirmations")
async def set_confirmations(data: ConfirmationsIn, ctx: AuthContext = Depends(require_manager),
                            db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "integrations")
    template = data.template.strip()
    if data.enabled and not template:
        raise HTTPException(status_code=400, detail="Enter the name of your approved WhatsApp template")
    s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == ctx.owner_id))).scalars().first()
    if s is None:
        s = IntegrationSettings(user_id=ctx.owner_id, email_alerts=True)
        db.add(s)
    s.whatsapp_enabled, s.whatsapp_template, s.whatsapp_language = data.enabled, template or None, data.language or "en"
    await db.commit()
    return _confirmations_json(s)


# ─── overview ─────────────────────────────────────────────────────
@router.get("/overview")
async def overview(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """This month at a glance, and what's left to set up."""
    now = datetime.now(timezone.utc)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    names = await _bot_names(db, ctx.owner_id)
    nums = (await db.execute(select(WhatsAppNumber).where(
        WhatsAppNumber.user_id == ctx.owner_id, WhatsAppNumber.status != "disconnected")
        .order_by(WhatsAppNumber.created_at))).scalars().all()
    counts = dict((await db.execute(
        select(WhatsAppMessage.sent_by, func.count()).join(WhatsAppChat, WhatsAppChat.id == WhatsAppMessage.chat_id)
        .where(WhatsAppChat.user_id == ctx.owner_id, WhatsAppMessage.created_at >= month,
               or_(WhatsAppMessage.status.is_(None), WhatsAppMessage.status != "failed"))
        .group_by(WhatsAppMessage.sent_by))).all())
    per_number = dict((await db.execute(
        select(WhatsAppChat.number_id, func.count()).select_from(WhatsAppMessage)
        .join(WhatsAppChat, WhatsAppChat.id == WhatsAppMessage.chat_id)
        .where(WhatsAppChat.user_id == ctx.owner_id, WhatsAppMessage.created_at >= month,
               WhatsAppMessage.direction == "out", WhatsAppMessage.sent_by.in_(["ai", "team"]),
               WhatsAppMessage.kind != "template", WhatsAppMessage.status.in_(["sent", "delivered", "read"]))
        .group_by(WhatsAppChat.number_id))).all())
    chats_this_month = (await db.execute(select(func.count()).select_from(WhatsAppChat).where(
        WhatsAppChat.user_id == ctx.owner_id, WhatsAppChat.last_message_at >= month))).scalar_one()
    person = (await db.execute(select(func.count()).select_from(WhatsAppChat)
                               .outerjoin(Conversation, Conversation.conversation_id == WhatsAppChat.conversation_id)
                               .where(WhatsAppChat.user_id == ctx.owner_id, WhatsAppChat.status != "closed",
                                      _needs_person()))).scalar_one()
    files = (await db.execute(select(func.count()).select_from(WhatsAppFile).where(
        WhatsAppFile.user_id == ctx.owner_id))).scalar_one()
    out_numbers = []
    for n in nums:
        j = number_json(n, names.get(n.bot_id))
        if ctx.role == "agent":
            j["verify_token"] = j["webhook_url"] = None
        sent = per_number.get(n.id, 0)
        j["replies_this_month"], j["free_left"] = sent, max(0, FREE_SERVICE_MESSAGES - sent)
        out_numbers.append(j)
    return {
        "numbers": out_numbers,
        "month": {"chats": chats_this_month, "from_customers": counts.get("customer", 0), "by_ai": counts.get("ai", 0),
                  "by_team": counts.get("team", 0) + counts.get("phone", 0), "waiting_for_team": person},
        "setup": {"connected": bool(nums), "answering": any(n.ai_enabled for n in nums),
                  "app_secret": all(bool(n.app_secret) or bool(numbers.app_secret()) for n in nums) if nums else False,
                  "files": files, "first_message": any(n.last_inbound_at for n in nums),
                  "free_replies": FREE_SERVICE_MESSAGES},
    }
