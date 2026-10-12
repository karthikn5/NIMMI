"""
Workspace-level settings and tools: business hours and escalation, saved replies for
Live chat, and the Questions page (what assistants couldn't answer, and the answers).
"""
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import assist
from auth import AuthContext, get_ctx, get_owned_bot, require_manager
from database import get_db
from backend.models import Bot, KnowledgeGap, SavedReply, WorkspaceSettings

router = APIRouter(prefix="/api", tags=["workspace"])
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ─── Business hours and escalation ────────────────────────────────
async def _settings(owner_id: str, db: AsyncSession) -> WorkspaceSettings:
    s = (await db.execute(select(WorkspaceSettings).where(WorkspaceSettings.user_id == owner_id))).scalars().first()
    return s or WorkspaceSettings(user_id=owner_id)


def _settings_json(s: WorkspaceSettings) -> dict:
    hours = assist.hours_config(s)
    open_now = assist.is_open(hours)
    return {"business_hours": hours, "escalate_upset": s.escalate_upset is not False,
            "open_now": open_now, "next_open": None if open_now else assist.next_open(hours)}


class DayHours(BaseModel):
    open: bool
    start: str = Field("09:00", alias="from")
    to: str = "18:00"


class HoursIn(BaseModel):
    enabled: bool = False
    days: dict[str, DayHours]
    holidays: list[str] = []
    away_message: str = Field("", max_length=400)


class SettingsIn(BaseModel):
    business_hours: HoursIn
    escalate_upset: bool = True


@router.get("/workspace/settings")
async def get_settings(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return _settings_json(await _settings(ctx.owner_id, db))


@router.put("/workspace/settings")
async def update_settings(data: SettingsIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    days = {}
    for name in assist.DAYS:
        d = data.business_hours.days.get(name)
        if not d:
            raise HTTPException(status_code=400, detail="Set hours for every day of the week")
        if not (TIME_RE.match(d.start) and TIME_RE.match(d.to)):
            raise HTTPException(status_code=400, detail="Use 24-hour times like 09:00")
        if d.open and d.start >= d.to:
            raise HTTPException(status_code=400, detail=f"{name.title()}: closing time must be after opening time")
        days[name] = {"open": d.open, "from": d.start, "to": d.to}
    holidays = sorted({h for h in data.business_hours.holidays if DATE_RE.match(h)})[:60]
    if data.business_hours.enabled and not any(d["open"] for d in days.values()):
        raise HTTPException(status_code=400, detail="Open at least one day a week")
    s = await _settings(ctx.owner_id, db)
    s.business_hours = {"enabled": data.business_hours.enabled, "days": days, "holidays": holidays,
                        "away_message": data.business_hours.away_message.strip() or assist.DEFAULT_HOURS["away_message"]}
    s.escalate_upset = data.escalate_upset
    db.add(s)
    await db.commit()
    return _settings_json(s)


# ─── Saved replies ────────────────────────────────────────────────
class ReplyIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    body: str = Field(..., min_length=1, max_length=2000)


def _reply_json(r: SavedReply) -> dict:
    return {"id": r.id, "title": r.title, "body": r.body}


@router.get("/workspace/replies")
async def list_replies(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SavedReply).where(SavedReply.user_id == ctx.owner_id).order_by(SavedReply.title))).scalars().all()
    return [_reply_json(r) for r in rows]


@router.post("/workspace/replies")
async def add_reply(data: ReplyIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    count = (await db.execute(select(func.count()).select_from(SavedReply).where(SavedReply.user_id == ctx.owner_id))).scalar()
    if count >= 100:
        raise HTTPException(status_code=400, detail="You can keep up to 100 saved replies")
    r = SavedReply(user_id=ctx.owner_id, title=data.title.strip(), body=data.body.strip())
    db.add(r)
    await db.commit()
    return _reply_json(r)


async def _owned_reply(reply_id: str, ctx: AuthContext, db: AsyncSession) -> SavedReply:
    r = (await db.execute(select(SavedReply).where(SavedReply.id == reply_id, SavedReply.user_id == ctx.owner_id))).scalars().first()
    if not r:
        raise HTTPException(status_code=404, detail="Saved reply not found")
    return r


@router.put("/workspace/replies/{reply_id}")
async def edit_reply(reply_id: str, data: ReplyIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    r = await _owned_reply(reply_id, ctx, db)
    r.title, r.body = data.title.strip(), data.body.strip()
    await db.commit()
    return _reply_json(r)


@router.delete("/workspace/replies/{reply_id}")
async def delete_reply(reply_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await db.delete(await _owned_reply(reply_id, ctx, db))
    await db.commit()
    return {"status": "deleted"}


# ─── Questions: what assistants couldn't answer ───────────────────
def _gap_json(g: KnowledgeGap, bot_names: dict) -> dict:
    return {"id": g.id, "bot_id": g.bot_id, "bot_name": bot_names.get(g.bot_id, ""), "question": g.question,
            "answer": g.answer or "", "status": g.status, "count": g.count or 0, "channel": g.channel,
            "conversation_id": g.last_conversation_id,
            "last_asked_at": g.last_asked_at.isoformat() if g.last_asked_at else None}


@router.get("/questions")
async def list_questions(status: str = "open", bot_id: Optional[str] = None, ctx: AuthContext = Depends(require_manager),
                         db: AsyncSession = Depends(get_db)):
    bots = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all())
    query = select(KnowledgeGap).where(KnowledgeGap.bot_id.in_(list(bots) or [""]), KnowledgeGap.status == status)
    if bot_id:
        query = query.where(KnowledgeGap.bot_id == bot_id)
    order = (KnowledgeGap.count.desc(), KnowledgeGap.last_asked_at.desc()) if status == "open" else (KnowledgeGap.last_asked_at.desc(),)
    rows = (await db.execute(query.order_by(*order).limit(300))).scalars().all()
    counts = dict((await db.execute(select(KnowledgeGap.status, func.count()).where(
        KnowledgeGap.bot_id.in_(list(bots) or [""])).group_by(KnowledgeGap.status))).all())
    return {"items": [_gap_json(g, bots) for g in rows],
            "counts": {k: counts.get(k, 0) for k in ("open", "answered", "dismissed")}}


async def _owned_gap(gap_id: str, ctx: AuthContext, db: AsyncSession) -> KnowledgeGap:
    g = (await db.execute(select(KnowledgeGap).join(Bot, Bot.bot_id == KnowledgeGap.bot_id)
                          .where(KnowledgeGap.id == gap_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if not g:
        raise HTTPException(status_code=404, detail="Question not found")
    return g


class AnswerIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=2000)
    question: Optional[str] = Field(None, max_length=1000)  # optional rewording


@router.post("/questions/{gap_id}/answer")
async def answer_question(gap_id: str, data: AnswerIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    g = await _owned_gap(gap_id, ctx, db)
    if data.question and data.question.strip():
        g.question = data.question.strip()
    g.answer, g.status = data.answer.strip(), "answered"
    await db.commit()
    assist.forget_answers(g.bot_id)
    return {"status": "answered"}


@router.post("/questions/{gap_id}/{action}")
async def question_action(gap_id: str, action: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    g = await _owned_gap(gap_id, ctx, db)
    if action == "dismiss":
        g.status = "dismissed"
    elif action == "reopen":
        g.status = "open"
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    await db.commit()
    assist.forget_answers(g.bot_id)
    return {"status": g.status}


class ManualAnswer(BaseModel):
    bot_id: str
    question: str = Field(..., min_length=3, max_length=1000)
    answer: str = Field(..., min_length=1, max_length=2000)


@router.post("/questions")
async def add_answer(data: ManualAnswer, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Teach an answer before anyone asks."""
    bot = await get_owned_bot(data.bot_id, ctx, db)
    norm = assist.normalize(data.question)
    g = (await db.execute(select(KnowledgeGap).where(KnowledgeGap.bot_id == bot.bot_id, KnowledgeGap.normalized == norm))).scalars().first()
    if not g:
        g = KnowledgeGap(bot_id=bot.bot_id, question=data.question.strip(), normalized=norm, channel="manual", count=0)
        db.add(g)
    g.answer, g.status, g.last_asked_at = data.answer.strip(), "answered", datetime.utcnow()
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="That question already has an answer")
    assist.forget_answers(bot.bot_id)
    return {"id": g.id, "status": "answered"}


@router.delete("/questions/{gap_id}")
async def delete_question(gap_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    g = await _owned_gap(gap_id, ctx, db)
    bot_id = g.bot_id
    await db.delete(g)
    await db.commit()
    assist.forget_answers(bot_id)
    return {"status": "deleted"}
