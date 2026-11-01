"""
Answers to unanswered questions (mail plan 5.3, phase 4). The team writes the answer on Questions; it can go to everyone who asked and left an email,
and the team ticks who. `assist.record_gap` keeps who asked (QuestionAsker); a chat's email can come after the question, so it's looked up here. Each
person gets it once, through the usual queue, so an unsubscribe or a bounce stops it like any other email.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, require_manager
from backend.models import Bot, Contact, Conversation, KnowledgeGap, QuestionAsker
from database import get_db
from mail import small
from phone import extract_contact

router = APIRouter(prefix="/api/email", tags=["email"])


async def _owned(gap_id: str, ctx: AuthContext, db: AsyncSession) -> KnowledgeGap:
    gap = (await db.execute(select(KnowledgeGap).join(Bot, Bot.bot_id == KnowledgeGap.bot_id)
                            .where(KnowledgeGap.id == gap_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if gap is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return gap


async def _address(db: AsyncSession, row: QuestionAsker) -> tuple[Optional[str], Optional[str]]:
    """Their email and name, as far as anyone knows."""
    kind, _, value = row.who.partition(":")
    if kind == "email":
        contact = (await db.execute(select(Contact.name).where(Contact.bot_id == row.bot_id, Contact.email == value))).first()
        return value, contact[0] if contact else None
    if kind == "phone":
        contact = (await db.execute(select(Contact).where(Contact.bot_id == row.bot_id, Contact.e164 == value))).scalars().first()
        return (contact.email, contact.name) if contact else (None, None)
    conv = await db.get(Conversation, value) if kind == "chat" else None
    if conv is None:
        return None, None
    found = extract_contact(conv.captured_data or {})
    return found.get("email"), found.get("name")


async def _people(db: AsyncSession, gap: KnowledgeGap) -> list[tuple[QuestionAsker, Optional[str], Optional[str]]]:
    rows = (await db.execute(select(QuestionAsker).where(QuestionAsker.gap_id == gap.id).order_by(QuestionAsker.asked_at.desc()).limit(500))).scalars().all()
    return [(row, *await _address(db, row)) for row in rows]


@router.get("/questions/{gap_id}/people")
async def people_who_asked(gap_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    gap = await _owned(gap_id, ctx, db)
    people = await _people(db, gap)
    reachable = {}
    for row, address, name in people:  # one person asking on a chat and a call is one email
        reachable.setdefault((address or "").lower(), (row, address, name))
    reachable.pop("", None)
    return {"people": [{"id": row.id, "email": address, "name": name, "channel": row.channel, "asked_at": row.asked_at.isoformat() if row.asked_at else None,
                        "sent": bool(row.sent_at)} for row, address, name in reachable.values()],
            "without_email": sum(1 for _, address, _ in people if not address)}


class SendIn(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=500)


@router.post("/questions/{gap_id}/send")
async def send_answer(gap_id: str, data: SendIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    gap = await _owned(gap_id, ctx, db)
    if gap.status != "answered" or not gap.answer:
        raise HTTPException(status_code=400, detail="Write the answer first")
    await plans.require_feature(db, gap.bot_id, "email_alerts")
    chosen, question, answer = set(data.ids), gap.question, gap.answer
    wanted = [(row, address, name) for row, address, name in await _people(db, gap) if row.id in chosen and address and not row.sent_at]
    await db.commit()  # the queue writes in its own session
    sent = 0
    for row, address, name in wanted:
        if await small.queue(ctx.owner_id, gap.bot_id, "question_answer", row.id, address, {"name": name, "question": question, "answer": answer}):
            sent += 1
            row = await db.get(QuestionAsker, row.id)
            row.sent_at = datetime.utcnow()
            await db.commit()
    return {"sent": sent, "not_sent": len(wanted) - sent}
