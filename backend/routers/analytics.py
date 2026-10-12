"""Workspace analytics from real data: conversations, messages, leads, handoffs and calls."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx
from database import get_db
from backend.models import Bot, CallLog, Conversation, Message
from phone import extract_contact

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
async def analytics(days: int = 30, bot_id: Optional[str] = None, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    days = max(7, min(days, 90))
    since = (datetime.utcnow() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    bots = (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all()
    names = {b: n for b, n in bots}
    ids = [bot_id] if bot_id in names else list(names)
    empty = {"days": days, "totals": {"conversations": 0, "messages": 0, "leads": 0, "handoffs": 0, "calls": 0, "call_leads": 0},
             "by_day": [], "by_bot": [], "previous": {"conversations": 0, "leads": 0}}
    if not ids:
        return empty

    convs = (await db.execute(select(Conversation).where(Conversation.bot_id.in_(ids), Conversation.created_at >= since))).scalars().all()
    prev_since = since - timedelta(days=days)
    prev = (await db.execute(select(Conversation).where(Conversation.bot_id.in_(ids), Conversation.created_at >= prev_since,
                                                        Conversation.created_at < since))).scalars().all()
    msg_counts = dict((await db.execute(
        select(Message.conversation_id, func.count()).where(Message.conversation_id.in_([c.conversation_id for c in convs]))
        .group_by(Message.conversation_id)
    )).all()) if convs else {}
    calls = (await db.execute(select(CallLog).where(CallLog.user_id == ctx.owner_id, CallLog.channel == "phone",
                                                    CallLog.bot_id.in_(ids), CallLog.started_at >= since))).scalars().all()

    def is_lead(c: Conversation) -> bool:
        contact = extract_contact(c.captured_data)
        return bool(contact.get("phone") or contact.get("email"))

    day_keys = [(since + timedelta(days=i)).date() for i in range(days)]
    per_day = {d: {"conversations": 0, "leads": 0, "calls": 0} for d in day_keys}
    per_bot = defaultdict(lambda: {"conversations": 0, "leads": 0, "handoffs": 0, "calls": 0})
    for c in convs:
        d = c.created_at.replace(tzinfo=None).date()
        if d in per_day:
            per_day[d]["conversations"] += 1
            per_day[d]["leads"] += int(is_lead(c))
        b = per_bot[c.bot_id]
        b["conversations"] += 1
        b["leads"] += int(is_lead(c))
        b["handoffs"] += int(bool(c.handoff_requested))
    for call in calls:
        d = call.started_at.replace(tzinfo=None).date()
        if d in per_day:
            per_day[d]["calls"] += 1
        per_bot[call.bot_id]["calls"] += 1

    return {
        "days": days,
        "totals": {
            "conversations": len(convs),
            "messages": sum(msg_counts.values()),
            "leads": sum(1 for c in convs if is_lead(c)),
            "handoffs": sum(1 for c in convs if c.handoff_requested),
            "calls": len(calls),
            "call_leads": sum(1 for c in calls if c.outcome == "lead_captured"),
        },
        "previous": {"conversations": len(prev), "leads": sum(1 for c in prev if is_lead(c))},
        "by_day": [{"date": d.isoformat(), **v} for d, v in per_day.items()],
        "by_bot": sorted(
            [{"bot_id": b, "bot_name": names.get(b, "Deleted assistant"), **v} for b, v in per_bot.items() if b in names],
            key=lambda r: r["conversations"], reverse=True,
        ),
    }
