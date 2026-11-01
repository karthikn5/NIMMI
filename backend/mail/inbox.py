"""
Email > Inbox (/api/email/inbox): the conversations people answered, with what the AI wrote or did about each. The team reads
them, answers, sends or drops the AI's draft, asks it to write one, assigns a conversation and keeps notes. Attachments stay at
Resend: opening one gets a fresh link (they last an hour).
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, rate_limit, require_manager
from backend.models import Bot, CallLog, Contact, EmailThread, ThreadMessage
from database import get_db
from mail import replies, setup, threads
from notify import email
from notify.events import fire_and_forget

router = APIRouter(prefix="/api/email/inbox", tags=["email"])

SHOWN = ("open", "answered", "closed")


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _thread_json(t: EmailThread, bots: dict, last: Optional[str] = None, draft: bool = False) -> dict:
    return {"id": t.id, "email": t.email, "name": t.name, "subject": t.subject, "status": t.status, "kind": t.kind, "unread": t.unread or 0,
            "assigned_to": t.assigned_to, "bot_id": t.bot_id, "bot_name": bots.get(t.bot_id), "last_at": _iso(t.last_at), "last": last, "draft": draft}


def _message_json(m: ThreadMessage) -> dict:
    return {"id": m.id, "direction": m.direction, "who": m.who, "status": m.status, "subject": m.subject, "text": m.text, "kind": m.kind,
            "note": m.note, "sender": m.sender, "attachments": m.attachments or [], "automatic": bool(m.automatic), "by": m.by,
            "action": m.action, "created_at": _iso(m.created_at)}


async def _own(thread_id: str, ctx: AuthContext, db: AsyncSession) -> EmailThread:
    thread = (await db.execute(select(EmailThread).where(EmailThread.id == thread_id, EmailThread.user_id == ctx.owner_id))).scalars().first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return thread


async def _own_message(thread: EmailThread, message_id: str, db: AsyncSession) -> ThreadMessage:
    row = (await db.execute(select(ThreadMessage).where(ThreadMessage.id == message_id, ThreadMessage.thread_id == thread.id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return row


@router.get("")
async def list_threads(status: str = "open", q: str = "", mine: bool = False, limit: int = 50, ctx: AuthContext = Depends(require_manager),
                       db: AsyncSession = Depends(get_db)):
    base = [EmailThread.user_id == ctx.owner_id, EmailThread.status.in_(SHOWN)]
    if q.strip():
        like = f"%{q.strip().lower()}%"
        base.append(or_(EmailThread.email.like(like), func.lower(EmailThread.name).like(like), func.lower(EmailThread.subject).like(like)))
    if mine:
        base.append(EmailThread.assigned_to == ctx.user_id)
    counts = dict((await db.execute(select(EmailThread.status, func.count()).where(*base).group_by(EmailThread.status))).all())
    where = base + ([EmailThread.status == status] if status in SHOWN else [])
    rows = (await db.execute(select(EmailThread).where(*where).order_by(EmailThread.last_at.desc()).limit(min(max(limit, 1), 100)))).scalars().all()
    bots = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all())
    items = []
    for t in rows:
        last = (await db.execute(select(ThreadMessage.text).where(ThreadMessage.thread_id == t.id, ThreadMessage.direction == "in")
                                 .order_by(ThreadMessage.created_at.desc()).limit(1))).scalar()
        draft = (await db.execute(select(ThreadMessage.id).where(ThreadMessage.thread_id == t.id, ThreadMessage.status == "draft").limit(1))).first()
        items.append(_thread_json(t, bots, (last or "")[:160], bool(draft)))
    unread = (await db.execute(select(func.coalesce(func.sum(EmailThread.unread), 0)).where(EmailThread.user_id == ctx.owner_id))).scalar()
    return {"items": items, "counts": {k: counts.get(k, 0) for k in SHOWN}, "unread": unread or 0, "enabled": threads.enabled()}


async def thread_detail(t: EmailThread, ctx: AuthContext, db: AsyncSession) -> dict:
    """A conversation, with the person's details and their calls."""
    rows = (await db.execute(select(ThreadMessage).where(ThreadMessage.thread_id == t.id, ThreadMessage.status.notin_(("new", "working", "discarded")))
                             .order_by(ThreadMessage.created_at).limit(200))).scalars().all()
    contact = (await db.execute(select(Contact).where(Contact.bot_id == t.bot_id, func.lower(Contact.email) == t.email)
                                .order_by(Contact.created_at))).scalars().first() if t.bot_id else None
    calls = []
    if contact is not None and contact.e164:
        calls = [{"id": c.id, "at": _iso(c.started_at), "summary": c.summary, "direction": c.direction} for c in (await db.execute(
            select(CallLog).where(CallLog.bot_id == t.bot_id, CallLog.caller_e164 == contact.e164, CallLog.channel == "phone")
            .order_by(CallLog.started_at.desc()).limit(5))).scalars().all()]
    bots = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all())
    return {**_thread_json(t, bots), "notes": t.notes or "", "messages": [_message_json(m) for m in rows],
            "contact": {"name": contact.name, "phone": contact.e164, "lead_status": contact.lead_status, "details": contact.details or {}} if contact else None,
            "calls": calls, "mode": (await setup.settings_for(db, t.bot_id))["replies"]["mode"] if t.bot_id else "team"}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Opening a conversation marks it read."""
    t = await _own(thread_id, ctx, db)
    shown = await thread_detail(t, ctx, db)
    t.unread = 0
    await db.commit()
    return {**shown, "unread": 0}


class ThreadIn(BaseModel):
    status: Optional[str] = Field(None, max_length=12)
    assigned_to: Optional[str] = Field(None, max_length=36)
    notes: Optional[str] = Field(None, max_length=4000)


@router.put("/{thread_id}")
async def update_thread(thread_id: str, data: ThreadIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    t = await _own(thread_id, ctx, db)
    if data.status is not None:
        if data.status not in SHOWN:
            raise HTTPException(status_code=400, detail="Unknown status")
        t.status = data.status
    if data.assigned_to is not None:
        t.assigned_to = data.assigned_to or None
    if data.notes is not None:
        t.notes = data.notes.strip() or None
    await db.commit()
    return await thread_detail(t, ctx, db)


class ReplyIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


@router.post("/{thread_id}/reply")
async def team_reply(thread_id: str, data: ReplyIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    t = await _own(thread_id, ctx, db)
    await plans.require_feature(db, t.bot_id, "email_alerts") if t.bot_id else await plans.require_workspace_feature(db, ctx.owner_id, "email_alerts")
    rate_limit(f"email-reply:{ctx.owner_id}", 60, 3600)
    why = await replies.send_text(t.id, data.text, "team", by=ctx.user_id)
    if why:
        raise HTTPException(status_code=409, detail=why)
    db.expire_all()  # sending saved it in a session of its own
    return await thread_detail(await _own(thread_id, ctx, db), ctx, db)


@router.post("/{thread_id}/drafts/{message_id}/send")
async def send_draft(thread_id: str, message_id: str, data: ReplyIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The team sends the AI's draft, changed or not. Its booking, if it has one, is made first."""
    t = await _own(thread_id, ctx, db)
    row = await _own_message(t, message_id, db)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="This draft has gone already")
    why = await replies.send_draft(row.id, data.text, ctx.user_id)
    if why:
        raise HTTPException(status_code=409, detail=why)
    db.expire_all()  # sending saved it in a session of its own
    return await thread_detail(await _own(thread_id, ctx, db), ctx, db)


@router.delete("/{thread_id}/drafts/{message_id}")
async def drop_draft(thread_id: str, message_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    t = await _own(thread_id, ctx, db)
    row = await _own_message(t, message_id, db)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="This draft has gone already")
    row.status = "discarded"
    await db.commit()
    return await thread_detail(t, ctx, db)


@router.post("/{thread_id}/write")
async def write_with_ai(thread_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Write with AI: a draft answering their latest email. It comes in by itself; the page looks again."""
    t = await _own(thread_id, ctx, db)
    if t.bot_id is None:
        raise HTTPException(status_code=400, detail="This email wasn't from an assistant, so the AI has no knowledge to answer from")
    await plans.require_feature(db, t.bot_id, "email_alerts")
    rate_limit(f"email-write:{ctx.owner_id}", 20, 600)
    last = (await db.execute(select(ThreadMessage.id).where(ThreadMessage.thread_id == t.id, ThreadMessage.direction == "in", ThreadMessage.status == "received",
                                                            ThreadMessage.automatic.isnot(True)).order_by(ThreadMessage.created_at.desc()).limit(1))).scalar()
    if last is None:
        raise HTTPException(status_code=409, detail="They haven't written anything to answer yet")
    fire_and_forget(replies.answer(last, asked=True))
    return {"status": "writing"}


@router.get("/{thread_id}/attachments/{message_id}/{attachment_id}")
async def open_attachment(thread_id: str, message_id: str, attachment_id: str, ctx: AuthContext = Depends(require_manager),
                          db: AsyncSession = Depends(get_db)):
    """A fresh link from Resend, for one attachment of an email in this conversation. The page opens it."""
    t = await _own(thread_id, ctx, db)
    row = await _own_message(t, message_id, db)
    if not any(a.get("id") == attachment_id for a in row.attachments or []) or not row.provider_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    async with email.resend_client() as client:
        resp = await client.get(f"{email.resend_url()}/emails/receiving/{row.provider_id}/attachments/{attachment_id}",
                                headers={"Authorization": f"Bearer {os.getenv('RESEND_API_KEY', '')}"})
    url = resp.json().get("download_url") if resp.status_code < 300 else None
    if not url:
        raise HTTPException(status_code=404, detail="Resend doesn't have this attachment any more")
    return {"url": url}
