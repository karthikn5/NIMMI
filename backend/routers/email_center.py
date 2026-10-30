"""
Customer emails: what was sent (history), and bulk emails to leads.

History lists every automatic and bulk email with its status; a failed or cancelled email can be
sent again, a queued one cancelled, and a person can be stopped from getting any more emails.
Bulk email picks leads who shared an email in chat or on a call, skips anyone who unsubscribed,
and queues one email per address; the scheduler sends them in batches.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import assist
from auth import AuthContext, rate_limit, require_manager
from database import get_db
from backend.models import Bot, CallLog, Conversation, EmailBroadcast, EmailJob, EmailUnsubscribe, IntegrationSettings
from notify import automations, email
from phone import extract_contact
import plans

router = APIRouter(prefix="/api/integrations/email", tags=["integrations"])

MAX_RECIPIENTS = 2000
BROADCASTS_PER_DAY = 5
SCAN = 5000  # most recent chats / calls looked at when building an audience


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _job_json(j: EmailJob) -> dict:
    key = j.automation or ("broadcast" if j.broadcast_id else j.kind.split("#")[0])
    return {"id": j.id, "to": j.to_email, "subject": j.subject, "automation": key, "label": automations.LABELS.get(key, key),
            "step": j.step or 1, "status": j.status, "error": j.error, "broadcast_id": j.broadcast_id,
            "send_at": _iso(j.send_at), "sent_at": _iso(j.sent_at), "created_at": _iso(j.created_at)}


async def _own_job(job_id: str, ctx: AuthContext, db: AsyncSession) -> EmailJob:
    job = (await db.execute(select(EmailJob).where(EmailJob.id == job_id, EmailJob.user_id == ctx.owner_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Email not found")
    return job


# ─── history ─────────────────────────────────────────────────────
@router.get("/history")
async def history(status: str = "", automation: str = "", q: str = "", offset: int = 0, limit: int = 50,
                  ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    base = [EmailJob.user_id == ctx.owner_id]
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
            "counts": {k: counts.get(k, 0) for k in ("queued", "sent", "failed", "cancelled")},
            "total": counts.get(status, 0) if status else sum(counts.values())}


@router.get("/jobs/{job_id}")
async def job_detail(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    job = await _own_job(job_id, ctx, db)
    return {**_job_json(job), "body": job.body,
            "unsubscribed": await automations.is_unsubscribed(db, ctx.owner_id, job.to_email)}


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
    if not await automations.is_unsubscribed(db, ctx.owner_id, address):
        db.add(EmailUnsubscribe(user_id=ctx.owner_id, email=address))
    await db.commit()
    return {"cancelled": cancelled}


# ─── bulk email ──────────────────────────────────────────────────
class AudienceIn(BaseModel):
    source: str = "all"  # all, chat, calls
    days: int = Field(90, ge=0, le=3650)  # 0 = any time
    hot_only: bool = False


async def _audience(db: AsyncSession, owner_id: str, a: AudienceIn) -> tuple[list[dict], int]:
    """People who shared an email, newest first, one per address. Returns (people, unsubscribed skipped)."""
    if a.source not in ("all", "chat", "calls"):
        raise HTTPException(status_code=400, detail="Unknown audience")
    since = datetime.utcnow() - timedelta(days=a.days) if a.days else None
    found: list[tuple[datetime, dict]] = []

    if a.source in ("all", "chat"):
        q = select(Conversation).join(Bot, Bot.bot_id == Conversation.bot_id).where(Bot.user_id == owner_id)
        if since:
            q = q.where(Conversation.created_at >= since)
        for c in (await db.execute(q.order_by(Conversation.created_at.desc()).limit(SCAN))).scalars().all():
            contact = extract_contact(c.captured_data or {})
            if not contact.get("email"):
                continue
            if a.hot_only and assist.lead_score(c.captured_data, asked_for_person=bool(c.handoff_requested))["label"] != "hot":
                continue
            found.append((c.created_at, {**contact, "source": "chat"}))

    if a.source in ("all", "calls"):
        q = select(CallLog).where(CallLog.user_id == owner_id, CallLog.channel != "browser")
        if since:
            q = q.where(CallLog.started_at >= since)
        for c in (await db.execute(q.order_by(CallLog.started_at.desc()).limit(SCAN))).scalars().all():
            contact = extract_contact(c.captured or {})
            if not contact.get("email"):
                continue
            if a.hot_only and assist.lead_score(c.captured, successful=c.successful, sentiment=c.sentiment,
                                                outcome=c.outcome)["label"] != "hot":
                continue
            found.append((c.started_at, {**contact, "source": "call"}))

    found.sort(key=lambda x: x[0] or datetime.min, reverse=True)
    unsub = {e for (e,) in (await db.execute(select(EmailUnsubscribe.email).where(EmailUnsubscribe.user_id == owner_id))).all()}
    people, seen, skipped = [], set(), set()
    for when, p in found:
        key = p["email"].lower()
        if key in seen or key in skipped:
            continue
        if key in unsub:
            skipped.add(key)
            continue
        seen.add(key)
        people.append({"name": p.get("name") or "", "email": p["email"], "source": p["source"], "last_seen": _iso(when)})
    return people, len(skipped)


@router.post("/audience")
async def audience(data: AudienceIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    people, skipped = await _audience(db, ctx.owner_id, data)
    return {"count": len(people), "sample": people[:8], "unsubscribed": skipped, "limit": MAX_RECIPIENTS}


class BroadcastIn(AudienceIn):
    subject: str = Field(..., max_length=200)
    body: str = Field(..., max_length=10000)
    consent: bool = False  # "these people agreed to hear from us"


@router.post("/broadcasts")
async def send_broadcast(data: BroadcastIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require_workspace_feature(db, ctx.owner_id, "email_alerts")  # emails to customers: Growth
    if not (data.subject.strip() and data.body.strip()):
        raise HTTPException(status_code=400, detail="Add a subject and message")
    if not data.consent:
        raise HTTPException(status_code=400, detail="Confirm these people agreed to hear from you")
    if not email.is_configured():
        raise HTTPException(status_code=409, detail="Email sending isn't set up on the server yet")
    settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == ctx.owner_id))).scalars().first()
    if not (settings and settings.reply_to):
        raise HTTPException(status_code=400, detail="Add a reply-to address first, so people can answer you")
    today = (await db.execute(select(func.count()).select_from(EmailBroadcast).where(
        EmailBroadcast.user_id == ctx.owner_id, EmailBroadcast.created_at >= datetime.utcnow() - timedelta(days=1)))).scalar_one()
    if today >= BROADCASTS_PER_DAY:
        raise HTTPException(status_code=429, detail=f"You can send up to {BROADCASTS_PER_DAY} bulk emails a day")
    rate_limit(f"broadcast:{ctx.owner_id}", 3, 600)

    people, _ = await _audience(db, ctx.owner_id, data)
    if not people:
        raise HTTPException(status_code=400, detail="No one to send to with these filters")
    if len(people) > MAX_RECIPIENTS:
        raise HTTPException(status_code=400, detail=f"That's {len(people)} people. Narrow it to {MAX_RECIPIENTS} or fewer.")

    business = settings.sender_name or "Our team"
    b = EmailBroadcast(user_id=ctx.owner_id, subject=data.subject.strip(), body=data.body.strip(),
                       audience={"source": data.source, "days": data.days, "hot_only": data.hot_only}, recipients=len(people))
    db.add(b)
    await db.flush()
    now = datetime.utcnow()
    for p in people:
        values = {"name": (p["name"] or "there").split()[0] if p["name"] else "there", "email": p["email"], "business": business}
        db.add(EmailJob(user_id=ctx.owner_id, kind=f"broadcast:{b.id}", ref_id=automations.recipient_ref(p["email"]),
                        to_email=p["email"], automation="broadcast", step=1, broadcast_id=b.id,
                        subject=automations.render(b.subject, values)[:200], body=automations.render(b.body, values), send_at=now))
    await db.commit()
    return {"id": b.id, "recipients": len(people)}


@router.get("/broadcasts")
async def list_broadcasts(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EmailBroadcast).where(EmailBroadcast.user_id == ctx.owner_id)
                             .order_by(EmailBroadcast.created_at.desc()).limit(50))).scalars().all()
    counts: dict[str, dict] = {}
    if rows:
        for bid, status, n in (await db.execute(select(EmailJob.broadcast_id, EmailJob.status, func.count()).where(
                EmailJob.broadcast_id.in_([r.id for r in rows])).group_by(EmailJob.broadcast_id, EmailJob.status))).all():
            counts.setdefault(bid, {})[status] = n
    return [{"id": r.id, "subject": r.subject, "audience": r.audience or {}, "recipients": r.recipients or 0,
             "created_at": _iso(r.created_at),
             "counts": {k: counts.get(r.id, {}).get(k, 0) for k in ("queued", "sent", "failed", "cancelled")}} for r in rows]


@router.post("/broadcasts/{broadcast_id}/cancel")
async def cancel_broadcast(broadcast_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Stop the emails of a bulk send that haven't gone out yet."""
    jobs = (await db.execute(select(EmailJob).where(EmailJob.user_id == ctx.owner_id, EmailJob.broadcast_id == broadcast_id,
                                                    EmailJob.status == "queued"))).scalars().all()
    for j in jobs:
        j.status, j.error = "cancelled", "Cancelled by your team"
    await db.commit()
    return {"cancelled": len(jobs)}
