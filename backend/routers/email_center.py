"""
Customer emails: what was sent (history).

History lists every automatic and bulk email with its status; a failed or cancelled email can be
sent again, a queued one cancelled, and a person can be stopped from getting any more emails.
Bulk email itself is mail/broadcasts.py.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, require_manager
from database import get_db
from backend.models import EmailJob
from mail import suppress
from notify import automations, email

router = APIRouter(prefix="/api/integrations/email", tags=["integrations"])


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _job_json(j: EmailJob) -> dict:
    key = j.automation or ("broadcast" if j.broadcast_id else j.kind.split("#")[0])
    return {"id": j.id, "to": j.to_email, "subject": j.subject, "automation": key, "label": automations.LABELS.get(key, key),
            "step": j.step or 1, "status": j.status, "error": j.error, "broadcast_id": j.broadcast_id,
            "send_at": _iso(j.send_at), "sent_at": _iso(j.sent_at), "created_at": _iso(j.created_at),
            # What Resend reported after sending (mail/webhooks.py). Opens are a hint: mail apps open emails by themselves.
            "event": j.event, "event_detail": j.event_detail, "delivered_at": _iso(j.delivered_at),
            "bounced_at": _iso(j.bounced_at), "complained_at": _iso(j.complained_at), "opened_at": _iso(j.opened_at),
            "clicked_at": _iso(j.clicked_at)}


async def _own_job(job_id: str, ctx: AuthContext, db: AsyncSession) -> EmailJob:
    job = (await db.execute(select(EmailJob).where(EmailJob.id == job_id, EmailJob.user_id == ctx.owner_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Email not found")
    return job


# ─── history ─────────────────────────────────────────────────────
@router.get("/history")
async def history(status: str = "", automation: str = "", q: str = "", offset: int = 0, limit: int = 50,
                  ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    base = [EmailJob.user_id == ctx.owner_id, EmailJob.status != "draft"]  # drafts have their own page
    if automation == "broadcast":
        base.append(EmailJob.broadcast_id.isnot(None))
    elif automation:
        base.append(EmailJob.automation == automation)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        base.append(func.lower(EmailJob.to_email).like(like) | func.lower(EmailJob.subject).like(like))
    counts = dict((await db.execute(select(EmailJob.status, func.count()).where(*base).group_by(EmailJob.status))).all())
    where = base + ([EmailJob.status == status] if status else [])
    rows = (await db.execute(select(EmailJob).where(*where).order_by(EmailJob.send_at.desc())
                             .offset(max(0, offset)).limit(min(max(limit, 1), 100)))).scalars().all()
    return {"items": [_job_json(j) for j in rows],
            "counts": {k: counts.get(k, 0) for k in ("queued", "held", "sent", "failed", "cancelled")},
            "total": counts.get(status, 0) if status else sum(counts.values())}


@router.get("/jobs/{job_id}")
async def job_detail(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    job = await _own_job(job_id, ctx, db)
    why = await suppress.why_blocked(db, ctx.owner_id, job.to_email)
    return {**_job_json(job), "body": job.body, "unsubscribed": why is not None, "stopped_because": why}


@router.post("/jobs/{job_id}/resend")
async def resend(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    job = await _own_job(job_id, ctx, db)
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail="Only failed or cancelled emails can be sent again")
    if await automations.is_unsubscribed(db, ctx.owner_id, job.to_email):
        raise HTTPException(status_code=409, detail="This person unsubscribed, so we can't email them")
    if not email.is_configured():
        raise HTTPException(status_code=409, detail="Email sending isn't set up on the server yet")
    await automations.requeue(job, db)
    await db.commit()
    return _job_json(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    job = await _own_job(job_id, ctx, db)
    if job.status != "queued":
        raise HTTPException(status_code=409, detail="This email isn't waiting to be sent")
    job.status, job.error = "cancelled", "Cancelled by your team"
    await db.commit()
    return _job_json(job)


class StopIn(BaseModel):
    email: str = Field(..., max_length=200)


@router.post("/stop")
async def stop_person(data: StopIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Never email this person again: cancel what's queued and add them to the unsubscribed list."""
    address = data.email.strip().lower()
    if not automations.EMAIL_RE.fullmatch(address):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    cancelled = await automations.stop_for(db, ctx.owner_id, address, "Stopped by your team")
    await suppress.add(db, ctx.owner_id, address, "team")
    await suppress.commit_quietly(db)
    return {"cancelled": cancelled}
