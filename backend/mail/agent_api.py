"""
The email agent's side of Email > Drafts and its activity (/api/email/agent/...): the emails it wrote that wait for the team, which they can change, send or drop,
one at a time or all of a morning's at once; what it did for each lead. Its level is the assistant's setting "agent" (PUT /api/email/setup/{bot_id}).
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, rate_limit, require_manager
from backend.models import Bot, Contact, EmailAgentAction, EmailJob
from database import get_db
from mail import agent

router = APIRouter(prefix="/api/email/agent", tags=["email"])


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _draft_json(j: EmailJob, bot_name: Optional[str]) -> dict:
    data = j.merge_data or {}
    return {"id": j.id, "bot_id": j.bot_id, "bot_name": bot_name, "to": j.to_email, "name": data.get("name"), "subject": j.subject, "body": j.body,
            "why": data.get("why"), "note": data.get("note"), "level": data.get("level"), "language": data.get("language"), "created_at": _iso(j.created_at)}


async def _own(job_id: str, ctx: AuthContext, db: AsyncSession) -> EmailJob:
    j = (await db.execute(select(EmailJob).where(EmailJob.id == job_id, EmailJob.user_id == ctx.owner_id, EmailJob.automation == "agent"))).scalars().first()
    if j is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if j.status != "draft":
        raise HTTPException(status_code=409, detail="This email has already gone or been dropped")
    return j


@router.get("/drafts")
async def drafts(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EmailJob).where(EmailJob.user_id == ctx.owner_id, EmailJob.automation == "agent", EmailJob.status == "draft")
                             .order_by(EmailJob.created_at.desc()).limit(100))).scalars().all()
    names = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all())
    return {"items": [_draft_json(j, names.get(j.bot_id)) for j in rows], "total": len(rows)}


class EditIn(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)


@router.put("/drafts/{job_id}")
async def edit(job_id: str, data: EditIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    j = await _own(job_id, ctx, db)
    j.subject, j.body = data.subject.strip(), data.body.strip()
    await db.commit()
    return _draft_json(j, None)


async def _approve(j: EmailJob, ctx: AuthContext) -> None:
    j.status, j.send_at, j.error = "queued", datetime.utcnow(), None
    j.merge_data = {**(j.merge_data or {}), "approved_by": ctx.user_id}


@router.post("/drafts/{job_id}/send")
async def send(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await _approve(await _own(job_id, ctx, db), ctx)
    await db.commit()
    return {"status": "queued"}


@router.post("/drafts/{job_id}/discard")
async def discard(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    j = await _own(job_id, ctx, db)
    j.status, j.error = "cancelled", "Dropped by your team"
    await db.commit()
    return {"status": "cancelled"}


class AllIn(BaseModel):
    bot_id: Optional[str] = Field(None, max_length=36)


@router.post("/drafts/send-all")
async def send_all(data: AllIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A morning's queue at once. Emails a check held for a person aren't in it: each of those needs its own look."""
    where = [EmailJob.user_id == ctx.owner_id, EmailJob.automation == "agent", EmailJob.status == "draft"] + ([EmailJob.bot_id == data.bot_id] if data.bot_id else [])
    rows = [j for j in (await db.execute(select(EmailJob).where(*where))).scalars().all() if not (j.merge_data or {}).get("note")]
    for j in rows:
        await _approve(j, ctx)
    await db.commit()
    return {"queued": len(rows)}


@router.get("/{bot_id}/activity")
async def activity(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """What the agent decided lately, lead by lead."""
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if bot is None:
        raise HTTPException(status_code=404, detail="Assistant not found")
    rows = (await db.execute(select(EmailAgentAction, Contact.name, Contact.email).join(Contact, Contact.id == EmailAgentAction.contact_id, isouter=True)
                             .where(EmailAgentAction.bot_id == bot_id, EmailAgentAction.created_at >= datetime.utcnow() - timedelta(days=30))
                             .order_by(EmailAgentAction.created_at.desc()).limit(100))).all()
    return [{"id": a.id, "action": a.action, "why": a.why, "name": name, "email": email, "at": _iso(a.created_at), "job_id": a.job_id} for a, name, email in rows]


@router.post("/{bot_id}/run")
async def run_now(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Look at the leads now, at the assistant's level, instead of waiting for its hour. A few at a time."""
    import plans
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if bot is None:
        raise HTTPException(status_code=404, detail="Assistant not found")
    await plans.require_feature(db, bot_id, "email_alerts")
    if (await agent.settings_of(db, bot_id))["level"] == "off":
        raise HTTPException(status_code=409, detail="Turn the email agent on first")
    rate_limit(f"email-agent-run:{ctx.owner_id}", 6, 3600)
    await db.commit()  # models write next: no connection waits on them
    done = await agent.run_for(bot_id, limit=5)
    return {"looked_at": len(done), "actions": [{k: d.get(k) for k in ("contact_id", "action", "why", "held")} for d in done]}
