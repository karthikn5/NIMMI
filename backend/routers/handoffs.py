"""Live chat: the agent side of human handoff, scoped to the caller's workspace."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx
from database import get_db
from pydantic import BaseModel, Field

import assist
from backend.models import Bot, Conversation, Message, User
from realtime import emit, notify_owner, relay_to_whatsapp, socket_room

router = APIRouter(prefix="/api/handoffs", tags=["live chat"])


async def _owned_conversation(conversation_id: str, ctx: AuthContext, db: AsyncSession) -> tuple[Conversation, Bot]:
    conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
    bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first() if conv else None
    if not conv or not bot or bot.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv, bot


@router.get("/pending")
async def pending_handoffs(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Conversation, Bot.bot_name)
        .join(Bot, Bot.bot_id == Conversation.bot_id)
        .where(Bot.user_id == ctx.owner_id, Conversation.handoff_status.in_(["pending", "human"]))
        .order_by(Conversation.created_at.desc())
    )).all()
    return [
        {
            "conversation_id": conv.conversation_id,
            "bot_id": conv.bot_id,
            "bot_name": bot_name,
            "session_id": conv.visitor_session_id,
            "status": conv.handoff_status,
            "agent_id": conv.agent_id,
            "created_at": conv.created_at,
            "captured_data": conv.captured_data,
            "channel": "whatsapp" if (conv.visitor_session_id or "").startswith("wa:") else "web",
            "lead": assist.lead_score(conv.captured_data, asked_for_person=True),
        }
        for conv, bot_name in rows
    ]


@router.post("/{conversation_id}/accept")
async def accept_handoff(conversation_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    conv, _ = await _owned_conversation(conversation_id, ctx, db)
    if conv.handoff_status == "human" and conv.agent_id and conv.agent_id != ctx.user_id:
        raise HTTPException(status_code=409, detail="A teammate is already handling this chat")
    conv.handoff_status, conv.agent_id = "human", ctx.user_id
    await db.commit()
    await emit("agent_joined", {"conversation_id": conversation_id, "agent_id": ctx.user_id}, room=conv.visitor_session_id)
    return {"status": "success", "message": "Handoff accepted"}


@router.post("/{conversation_id}/close")
async def close_handoff(conversation_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Agent is done: the assistant takes over again."""
    conv, _ = await _owned_conversation(conversation_id, ctx, db)
    conv.handoff_status, conv.handoff_requested = "ai", False
    db.add(Message(conversation_id=conv.conversation_id, role="assistant",
                   content="The agent has left the chat. The assistant is here to help."))
    await db.commit()
    await emit("agent_left", {"conversation_id": conversation_id}, room=conv.visitor_session_id)
    from notify import events
    events.fire_and_forget(events.handoff_closed(conv.conversation_id))
    return {"status": "success"}


@router.get("/{conversation_id}/messages")
async def handoff_messages(conversation_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    conv, _ = await _owned_conversation(conversation_id, ctx, db)
    messages = (await db.execute(
        select(Message).where(Message.conversation_id == conv.conversation_id).order_by(Message.timestamp.asc())
    )).scalars().all()
    authors = dict((await db.execute(select(User.id, User.name).where(
        User.id.in_([m.author_id for m in messages if m.author_id] or [""])))).all())
    return [
        {"id": m.id, "role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat() if m.timestamp else None,
         "author": authors.get(m.author_id) if m.author_id else None}
        for m in messages
    ]


class ReplyIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@router.post("/{conversation_id}/reply")
async def reply(conversation_id: str, data: ReplyIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A team member's reply to the customer. Sent over HTTP, not the agent's socket: it's saved and delivered
    even if that socket reconnected, or is connected to another server process than the visitor's."""
    conv, _ = await _owned_conversation(conversation_id, ctx, db)
    if conv.handoff_status == "human" and conv.agent_id and conv.agent_id != ctx.user_id:
        raise HTTPException(status_code=409, detail="A teammate is already handling this chat")
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write a message first")
    conv.handoff_status, conv.agent_id = "human", ctx.user_id
    message = Message(conversation_id=conv.conversation_id, role="assistant", content=text, author_id=ctx.user_id)
    db.add(message)
    await db.commit()
    room = conv.visitor_session_id
    payload = {"room": room, "message": text, "sender": "agent", "id": message.id, "conversation_id": conversation_id}
    if room.startswith("wa:"):
        await relay_to_whatsapp(db, conv, text, message_id=message.id, author_id=ctx.user_id)
    await emit("message", payload, room=socket_room(room, conv.bot_id))
    return payload


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/{conversation_id}/notes")
async def add_note(conversation_id: str, data: NoteIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A private note for the team. Never sent to the customer or to the AI."""
    conv, bot = await _owned_conversation(conversation_id, ctx, db)
    note = Message(conversation_id=conv.conversation_id, role="note", content=data.text.strip(), author_id=ctx.user_id)
    db.add(note)
    await db.commit()
    author = (await db.execute(select(User.name).where(User.id == ctx.user_id))).scalar_one_or_none()
    payload = {"conversation_id": conversation_id, "id": note.id, "content": note.content, "author": author,
               "timestamp": note.timestamp.isoformat() if note.timestamp else None}
    await notify_owner(bot.user_id, "note_added", payload)  # teammates' dashboards only, never the visitor's room
    return payload
