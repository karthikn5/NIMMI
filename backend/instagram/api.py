"""
The dashboard's Instagram section: connecting an account and how the assistant behaves on it (owners and admins), and the Inbox where the whole team
reads and answers DMs. A person's reply follows Instagram's windows: as usual within 24 hours of their last message (7 days after an ad's first
message), with Instagram's human agent tag up to 7 days, and not at all after that.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, get_ctx, rate_limit, require_manager
from backend.models import Bot, Conversation, InstagramAccount, InstagramChat, InstagramComment, InstagramMessage, InstagramRule, Message, TeamMember, User
from database import get_db
from instagram import accounts, chats, comments, graph, live, outbound, settings
from notify.events import fire_and_forget
from whatsapp import storage

router = APIRouter(prefix="/api/instagram", tags=["instagram"])

CHATS_PAGE = 50
MESSAGES_SHOWN = 300


def _iso(at) -> Optional[str]:
    at = chats.aware(at)
    return at.isoformat() if at else None


def account_json(a: InstagramAccount, bot_name: Optional[str] = None) -> dict:
    return {"id": a.id, "ig_id": a.ig_id, "username": a.username, "name": a.name, "bot_id": a.bot_id or "", "bot_name": bot_name,
            "comments_allowed": graph.COMMENTS_SCOPE in (a.scopes or []), "profile": a.profile or {"ice_breakers": [], "menu": []},
            "ai_enabled": bool(a.ai_enabled), "settings": settings.clean(a.settings), "status": a.status, "status_detail": a.status_detail,
            "subscribed": bool(a.subscribed), "token_expires_at": _iso(a.token_expires_at), "last_inbound_at": _iso(a.last_inbound_at),
            "created_at": _iso(a.created_at)}


async def _bot_names(db: AsyncSession, owner_id: str) -> dict:
    return dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all())


async def _account(db: AsyncSession, account_id: str, ctx: AuthContext) -> InstagramAccount:
    a = await db.get(InstagramAccount, account_id)
    if a is None or a.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Account not found")
    return a


async def _chat(db: AsyncSession, chat_id: str, ctx: AuthContext) -> InstagramChat:
    chat = await db.get(InstagramChat, chat_id)
    if chat is None or chat.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


# ─── accounts ─────────────────────────────────────────────────────
@router.get("")
async def overview(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What's connected, and this month's DMs: chats, the assistant's answers, and chats waiting for the team."""
    rows = (await db.execute(select(InstagramAccount).where(InstagramAccount.user_id == ctx.owner_id, InstagramAccount.status != "disconnected")
                             .order_by(InstagramAccount.created_at))).scalars().all()
    names = await _bot_names(db, ctx.owner_id)
    month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mine = select(InstagramChat.id).where(InstagramChat.user_id == ctx.owner_id)
    chats_month = (await db.execute(select(func.count()).select_from(InstagramChat).where(InstagramChat.user_id == ctx.owner_id,
                                                                                         InstagramChat.last_message_at >= month))).scalar_one()
    answered = (await db.execute(select(func.count()).select_from(InstagramMessage).where(InstagramMessage.chat_id.in_(mine), InstagramMessage.sent_by == "ai",
                                                                                         InstagramMessage.status.in_(("sent", "read")),
                                                                                         InstagramMessage.created_at >= month))).scalar_one()
    waiting = (await db.execute(select(func.count()).select_from(InstagramChat).outerjoin(Conversation, Conversation.conversation_id == InstagramChat.conversation_id)
                                .where(InstagramChat.user_id == ctx.owner_id, InstagramChat.status != "closed", _needs_person()))).scalar_one()
    return {"available": graph.available(), "accounts": [account_json(a, names.get(a.bot_id)) for a in rows],
            "month": {"chats": chats_month, "answered": answered, "waiting": waiting}}


@router.post("/connect")
async def connect(ctx: AuthContext = Depends(require_manager)):
    if not graph.available():
        raise HTTPException(status_code=503, detail="Instagram isn't set up on this server yet")
    return {"url": accounts.start_url(ctx.owner_id, ctx.user_id)}


class FinishIn(BaseModel):
    code: str = Field(..., max_length=2000)
    state: str = Field(..., max_length=2000)


@router.post("/connect/finish")
async def connect_finish(data: FinishIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Back from Instagram: only the person who started it, in the same workspace, can finish it."""
    who = accounts.read_state(data.state)
    if who != (ctx.owner_id, ctx.user_id):
        raise HTTPException(status_code=403, detail="This sign-in was started by someone else, or has expired. Connect again.")
    try:
        account_id, missing = await accounts.finish(data.code, ctx.owner_id, ctx.user_id)
    except accounts.Taken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except graph.IGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    a = await db.get(InstagramAccount, account_id)
    await db.refresh(a)
    return {**account_json(a, (await _bot_names(db, ctx.owner_id)).get(a.bot_id)), "missing": missing}


class AccountIn(BaseModel):
    bot_id: Optional[str] = Field(None, max_length=36)
    ai_enabled: Optional[bool] = None
    settings: Optional[dict] = None


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, data: AccountIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    a = await _account(db, account_id, ctx)
    if data.bot_id is not None:
        bot_id = data.bot_id.strip() or None
        if bot_id and not (await db.execute(select(Bot.bot_id).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).first():
            raise HTTPException(status_code=400, detail="Choose one of your own assistants")
        if bot_id and not (await plans.includes(db, bot_id)).instagram:
            bot = await db.get(Bot, bot_id)
            raise plans.plan_needed("instagram", bot.bot_name if bot else None)
        a.bot_id = bot_id
    if data.ai_enabled is not None:
        a.ai_enabled = data.ai_enabled
    if data.settings is not None:
        a.settings = settings.clean({**settings.clean(a.settings), **data.settings})
    await db.commit()
    return account_json(a, (await _bot_names(db, ctx.owner_id)).get(a.bot_id))


@router.delete("/accounts/{account_id}")
async def disconnect(account_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await _account(db, account_id, ctx)
    await accounts.disconnect(ctx.owner_id, account_id)
    return {"status": "disconnected"}


# ─── the Inbox ────────────────────────────────────────────────────
def _needs_person():
    """A chat for the team: a person was asked for or is handling it (never NULL, so "not" works too)."""
    return or_(func.coalesce(Conversation.handoff_status, "ai").in_(["pending", "human"]),
               and_(InstagramChat.ai_paused_until.isnot(None), InstagramChat.ai_paused_until > chats.now()))


@router.get("/chats")
async def list_chats(view: str = "open", q: str = Query("", max_length=80), account_id: str = "", ctx: AuthContext = Depends(get_ctx),
                     db: AsyncSession = Depends(get_db)):
    """view: open, ai (the assistant is handling), person (needs someone from the team), mine (assigned to me), closed."""
    query = (select(InstagramChat, Conversation.handoff_status).outerjoin(Conversation, Conversation.conversation_id == InstagramChat.conversation_id)
             .where(InstagramChat.user_id == ctx.owner_id))
    if view == "closed":
        query = query.where(InstagramChat.status == "closed")
    else:
        query = query.where(InstagramChat.status != "closed")
        if view == "ai":
            query = query.where(~_needs_person())
        elif view == "person":
            query = query.where(_needs_person())
        elif view == "mine":
            query = query.where(InstagramChat.assigned_to == ctx.user_id)
    if account_id:
        query = query.where(InstagramChat.account_id == account_id)
    if q.strip():
        like = f"%{q.strip().lower().lstrip('@')}%"
        query = query.where(or_(func.lower(InstagramChat.username).like(like), func.lower(InstagramChat.name).like(like)))
    rows = (await db.execute(query.order_by(InstagramChat.last_message_at.desc()).limit(CHATS_PAGE))).all()
    conv_ids = [c.conversation_id for c, _ in rows if c.conversation_id]
    last: dict = {}
    if conv_ids:
        ranked = (select(Message.conversation_id, Message.role, Message.content, Message.author_id, InstagramMessage.sent_by,
                         func.row_number().over(partition_by=Message.conversation_id, order_by=Message.timestamp.desc()).label("n"))
                  .outerjoin(InstagramMessage, InstagramMessage.message_id == Message.id)
                  .where(Message.conversation_id.in_(conv_ids), Message.role != "note").subquery())
        for conv_id, role, content, author_id, sent_by, _ in (await db.execute(select(ranked).where(ranked.c.n == 1))).all():
            by = "customer" if role == "user" else "ai" if sent_by == "ai" or (sent_by is None and not author_id) else "team"  # the Instagram app's are the team's
            last[conv_id] = {"role": role, "text": (content or "")[:160], "by": by}
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
        select(Message, InstagramMessage).outerjoin(InstagramMessage, InstagramMessage.message_id == Message.id)
        .where(Message.conversation_id == chat.conversation_id).order_by(Message.timestamp.desc()).limit(MESSAGES_SHOWN))).all() if conv else []
    authors = dict((await db.execute(select(User.id, User.name).where(User.id.in_([m.author_id for m, _ in rows if m.author_id] or [""])))).all())
    a = await db.get(InstagramAccount, chat.account_id) if chat.account_id else None
    j = live.chat_json(chat)
    j.update(handoff=conv.handoff_status if conv else "ai", captured=(conv.captured_data or {}) if conv else {},
             account={"id": a.id, "username": a.username, "status": a.status} if a else None)
    j["messages"] = [live.message_json(m, w, authors.get(m.author_id)) for m, w in reversed(rows)]
    return j


class SendIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


async def team_reply(db: AsyncSession, chat: InstagramChat, account: Optional[InstagramAccount], text: str, user_id: str,
                     message_id: Optional[str] = None) -> InstagramMessage:
    """A person on the team writes to them, inside Instagram's windows. The assistant then leaves the chat to the team for a while.
    Raises HTTPException with what's wrong (the Inbox shows it as is)."""
    if account is None or account.status == "disconnected":
        raise HTTPException(status_code=409, detail="This chat's Instagram account isn't connected any more")
    route = chats.reply_route(chat)
    if route == "closed":
        raise HTTPException(status_code=409, detail=chats.CLOSED)
    if len(text.encode("utf-8")) > graph.TEXT_BYTES:
        raise HTTPException(status_code=400, detail="Instagram takes up to 1,000 characters in a message (fewer in Tamil and Hindi). Make it shorter.")
    hours = settings.clean(account.settings)["pause_hours"]
    chat.ai_paused_until, chat.reply_due_at, chat.unread = chats.now() + timedelta(hours=hours), None, 0
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.agent_id = "human", user_id
    await db.execute(update(InstagramMessage).where(InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "in",
                                                    InstagramMessage.handled.is_(False)).values(handled=True))
    await db.commit()
    if conv is not None:
        from leads.contact import stop_for_chat
        fire_and_forget(stop_for_chat(conv.conversation_id))  # one chase at a time: the team has them now
    return await outbound.send_text(account, chat, text, sent_by="team", author_id=user_id, message_id=message_id, human_agent=route == "human_agent")


@router.post("/chats/{chat_id}/send")
async def send_in_chat(chat_id: str, data: SendIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    account = await db.get(InstagramAccount, chat.account_id) if chat.account_id else None
    rate_limit(f"ig-send:{ctx.user_id}", 60, 60)
    w = await team_reply(db, chat, account, data.text.strip(), ctx.user_id)
    m = await db.get(Message, w.message_id)
    author = await db.get(User, ctx.user_id)
    return live.message_json(m, w, author.name if author else None)


class PauseIn(BaseModel):
    hours: Optional[int] = None


@router.post("/chats/{chat_id}/pause")
async def pause_ai(chat_id: str, data: PauseIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    chat = await _chat(db, chat_id, ctx)
    a = await db.get(InstagramAccount, chat.account_id) if chat.account_id else None
    hours = data.hours if data.hours in settings.PAUSE_HOURS else settings.clean(a.settings if a else {})["pause_hours"]
    chat.ai_paused_until, chat.reply_due_at = chats.now() + timedelta(hours=hours), None
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.agent_id = "human", ctx.user_id
    await db.commit()
    if conv is not None:
        from leads.contact import stop_for_chat
        fire_and_forget(stop_for_chat(conv.conversation_id))
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


@router.post("/chats/{chat_id}/resume")
async def resume_ai(chat_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Hand the chat back to the assistant: it answers their next message (inside Instagram's 24 hours)."""
    chat = await _chat(db, chat_id, ctx)
    chat.ai_paused_until = None
    conv = await db.get(Conversation, chat.conversation_id) if chat.conversation_id else None
    if conv is not None:
        conv.handoff_status, conv.handoff_requested, conv.agent_id = "ai", False, None
    await db.commit()
    await live.chat_changed(ctx.owner_id, chat)
    return live.chat_json(chat)


async def _people(db: AsyncSession, owner_id: str) -> dict:
    owner = await db.get(User, owner_id)
    people = {owner_id: owner.name if owner else "Owner"}
    rows = (await db.execute(select(TeamMember.member_id, User.name).join(User, User.id == TeamMember.member_id).where(
        TeamMember.owner_id == owner_id, TeamMember.status == "active"))).all()
    people.update({mid: name for mid, name in rows if mid})
    return people


@router.get("/people")
async def list_people(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return [{"id": pid, "name": name or "Team member"} for pid, name in (await _people(db, ctx.owner_id)).items()]


class AssignIn(BaseModel):
    user_id: Optional[str] = None


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
    """The team opened the chat: nothing waiting for them, and their last message shows as seen (only while Instagram's window is open)."""
    chat = await _chat(db, chat_id, ctx)
    had = chat.unread or 0
    chat.unread = 0
    await db.commit()
    a = await db.get(InstagramAccount, chat.account_id) if chat.account_id else None
    if had and a is not None and a.status == "connected" and chats.window_open(chat):
        await graph.action(a.ig_id, a.access_token, chat.igsid, "mark_seen")
    return {"unread": 0}


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/chats/{chat_id}/notes")
async def add_note(chat_id: str, data: NoteIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A private note for the team: never sent to them, never read by the assistant."""
    chat = await _chat(db, chat_id, ctx)
    if not chat.conversation_id:
        raise HTTPException(status_code=409, detail="This chat has no messages yet")
    note = Message(conversation_id=chat.conversation_id, role="note", content=data.text.strip(), author_id=ctx.user_id, timestamp=chats.now())
    db.add(note)
    await db.commit()
    author = await db.get(User, ctx.user_id)
    await live.message(ctx.owner_id, chat, note, None, author.name if author else None)
    return live.message_json(note, None, author.name if author else None)


@router.get("/media/{ref}")
async def media(ref: str, e: int = 0, s: str = "", db: AsyncSession = Depends(get_db)):
    """A file someone sent, kept when it was understood, through a signed link: <img> and <audio> tags can't send the sign-in header."""
    if not live.media_link_ok(ref, e, s):
        raise HTTPException(status_code=403, detail="This link has expired. Open the page again.")
    w = await db.get(InstagramMessage, ref)
    info = (w.media or {}) if w else {}
    content = await storage.load(info.get("stored"))
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=content, media_type=info.get("mime") or "application/octet-stream", headers={"Cache-Control": "private, max-age=3600"})


# ─── comments (phase 6) ──────────────────────────────────────────
@router.get("/accounts/{account_id}/media")
async def list_media(account_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The account's latest posts and reels, for choosing which a rule watches."""
    a = await _account(db, account_id, ctx)
    if a.status == "disconnected" or not a.access_token:
        raise HTTPException(status_code=409, detail="This account isn't connected any more")
    try:
        found = await graph.media(a.ig_id, a.access_token)
    except graph.IGError as e:
        await accounts.trouble(a.id, e)
        raise HTTPException(status_code=400, detail=str(e))
    return [{"id": m["id"], "caption": (m.get("caption") or "")[:200], "type": m.get("media_type"), "permalink": m.get("permalink"),
             "picture": m.get("thumbnail_url") or m.get("media_url"), "at": m.get("timestamp")} for m in found]


class RuleIn(BaseModel):
    account_id: str = Field(..., max_length=36)
    name: str = Field(..., min_length=1, max_length=120)
    media_ids: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    private_reply: str = Field(..., min_length=1, max_length=2000)
    public_replies: list[str] = Field(default_factory=list, max_length=5)
    enabled: bool = False


def rule_json(r: InstagramRule, numbers: Optional[dict] = None) -> dict:
    return {"id": r.id, "account_id": r.account_id, "name": r.name, "media_ids": r.media_ids or [], "keywords": r.keywords or [], "private_reply": r.private_reply,
            "public_replies": r.public_replies or [], "enabled": bool(r.enabled), "last_error": r.last_error, "last_error_at": _iso(r.last_error_at),
            "report": numbers or {"comments": 0, "private_replies": 0, "public_replies": 0, "conversations": 0, "leads": 0, "sales": 0, "value": 0.0},
            "created_at": _iso(r.created_at)}


async def _clean_rule(db: AsyncSession, data: RuleIn, ctx: AuthContext) -> InstagramAccount:
    a = await _account(db, data.account_id, ctx)
    if len(data.private_reply.encode("utf-8")) > graph.TEXT_BYTES:
        raise HTTPException(status_code=400, detail="Instagram takes up to 1,000 characters in a message (fewer in Tamil and Hindi). Make the private reply shorter.")
    if any(len(p) > 300 for p in data.public_replies) or any(len(k) > 60 for k in data.keywords):
        raise HTTPException(status_code=400, detail="Keep public replies under 300 characters and words under 60")
    if data.enabled:
        bot = await accounts.assistant(db, a)
        if bot is None or not (await plans.includes(db, bot.bot_id)).instagram:
            raise plans.plan_needed("instagram", bot.bot_name if bot else None)
    return a


@router.get("/rules")
async def list_rules(account_id: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    q = select(InstagramRule).where(InstagramRule.user_id == ctx.owner_id)
    if account_id:
        q = q.where(InstagramRule.account_id == account_id)
    rows = (await db.execute(q.order_by(InstagramRule.created_at))).scalars().all()
    numbers = await comments.report(db, ctx.owner_id, account_id or None)
    return [rule_json(r, numbers.get(r.id)) for r in rows]


@router.post("/rules")
async def create_rule(data: RuleIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    a = await _clean_rule(db, data, ctx)
    r = InstagramRule(user_id=ctx.owner_id, account_id=a.id, name=data.name.strip(), media_ids=[m.strip()[:64] for m in data.media_ids if m.strip()] or None,
                      keywords=[k.strip() for k in data.keywords if k.strip()] or None, private_reply=data.private_reply.strip(),
                      public_replies=[p.strip() for p in data.public_replies if p.strip()] or None, enabled=data.enabled)
    db.add(r)
    await db.commit()
    return rule_json(r)


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, data: RuleIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    r = await db.get(InstagramRule, rule_id)
    if r is None or r.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    a = await _clean_rule(db, data, ctx)
    r.account_id, r.name = a.id, data.name.strip()
    r.media_ids = [m.strip()[:64] for m in data.media_ids if m.strip()] or None
    r.keywords = [k.strip() for k in data.keywords if k.strip()] or None
    r.private_reply = data.private_reply.strip()
    r.public_replies = [p.strip() for p in data.public_replies if p.strip()] or None
    if data.enabled and not r.enabled:
        r.last_error, r.last_error_at = None, None
    r.enabled = data.enabled
    await db.commit()
    return rule_json(r, (await comments.report(db, ctx.owner_id, a.id)).get(r.id))


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    r = await db.get(InstagramRule, rule_id)
    if r is None or r.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(r)
    await db.commit()
    return {"status": "deleted"}


@router.get("/comments")
async def list_comments(account_id: str = "", rule_id: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The latest comments and what happened to each: replied, waiting, skipped (and why) or failed."""
    q = select(InstagramComment).where(InstagramComment.user_id == ctx.owner_id)
    if account_id:
        q = q.where(InstagramComment.account_id == account_id)
    if rule_id:
        q = q.where(InstagramComment.rule_id == rule_id)
    rows = (await db.execute(q.order_by(InstagramComment.created_at.desc()).limit(50))).scalars().all()
    return [{"id": c.id, "username": c.from_username, "text": c.text, "media_id": c.media_id, "rule_id": c.rule_id, "status": c.status, "why": c.why,
             "public": bool(c.public_reply_id), "at": _iso(c.commented_at or c.created_at)} for c in rows]


class ProfileIn(BaseModel):
    ice_breakers: list[str] = Field(default_factory=list, max_length=4)
    menu: list[dict] = Field(default_factory=list, max_length=5)


@router.put("/accounts/{account_id}/profile")
async def save_profile(account_id: str, data: ProfileIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Ice breakers (up to 4 questions people can tap to start a chat; an ig.me link's ref needs them) and the menu in the chat."""
    a = await _account(db, account_id, ctx)
    if a.status == "disconnected" or not a.access_token:
        raise HTTPException(status_code=409, detail="This account isn't connected any more")
    questions = [q.strip()[:80] for q in data.ice_breakers if isinstance(q, str) and q.strip()]
    menu = []
    for item in data.menu:
        title = str(item.get("title") or "").strip()[:30]
        url = str(item.get("url") or "").strip()
        if not title:
            continue
        if url and not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="A menu link must start with https://")
        menu.append({"title": title, **({"url": url[:500]} if url else {})})
    try:
        await graph.set_profile(a.access_token, questions, menu)
        a.profile = {"ice_breakers": questions, "menu": menu, "error": None}
    except graph.IGError as e:
        await accounts.trouble(a.id, e)
        a.profile = {**(a.profile or {}), "error": str(e)[:300]}
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return account_json(a, (await _bot_names(db, ctx.owner_id)).get(a.bot_id))
