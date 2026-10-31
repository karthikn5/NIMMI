"""
The dashboard's Email section (/api/email): an overview, the business's own sending domains, who each assistant's
emails come from, and the addresses it doesn't email. Plus Resend's webhook (public, signed). History, bulk email and
the automations keep their routes (routers/email_center.py, routers/integrations.py).
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, rate_limit, require_manager
from backend.models import Bot, EmailDomain, EmailJob, EmailSender, EmailUnsubscribe, IntegrationSettings
from database import get_db
from mail import domains, senders, suppress, webhooks
from notify import automations, email

router = APIRouter(prefix="/api/email", tags=["email"])

STATUS_LABEL = {
    "not_started": "Waiting for the DNS records", "pending": "Checking the DNS records",
    "verified": "Verified", "partially_verified": "Partly verified", "partially_failed": "Partly verified",
    "failed": "Records not found", "temporary_failure": "Records missing: check them",
}


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


# ─── overview ────────────────────────────────────────────────────
@router.get("/overview")
async def overview(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    mine = [EmailJob.user_id == ctx.owner_id, EmailJob.created_at >= since]
    by_status = dict((await db.execute(select(EmailJob.status, func.count()).where(*mine).group_by(EmailJob.status))).all())
    counted = {}
    for name, column in (("delivered", EmailJob.delivered_at), ("bounced", EmailJob.bounced_at),
                         ("complained", EmailJob.complained_at), ("opened", EmailJob.opened_at),
                         ("clicked", EmailJob.clicked_at)):
        counted[name] = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine, column.isnot(None)))).scalar_one()
    problems = (await db.execute(select(EmailJob).where(
        EmailJob.user_id == ctx.owner_id, EmailJob.created_at >= since,
        (EmailJob.status == "failed") | EmailJob.bounced_at.isnot(None) | EmailJob.complained_at.isnot(None))
        .order_by(EmailJob.created_at.desc()).limit(5))).scalars().all()
    settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == ctx.owner_id))).scalars().first()
    own = (await db.execute(select(EmailDomain).where(EmailDomain.user_id == ctx.owner_id).order_by(EmailDomain.created_at))).scalars().all()
    stopped = (await db.execute(select(func.count()).select_from(EmailUnsubscribe).where(
        EmailUnsubscribe.user_id == ctx.owner_id))).scalar_one()
    from routers.email_center import _job_json, complaint_rate
    return {
        "server": {"email": email.is_configured(), "resend": bool(os.getenv("RESEND_API_KEY")),
                   "events": bool(os.getenv("RESEND_WEBHOOK_SECRET")),
                   "sending_address": email.address_of(email.customer_sender())},
        "last_30_days": {**{k: by_status.get(k, 0) for k in ("queued", "sent", "failed", "cancelled")}, **counted},
        "automations": [{"key": k, "label": automations.LABELS[k], "enabled": a["enabled"], "emails": len(a["steps"])}
                        for k, a in automations.automations(settings).items()],
        "domains": [{"id": d.id, "name": d.name, "status": d.status, "status_label": STATUS_LABEL.get(d.status, d.status)}
                    for d in own],
        "stopped": stopped,
        "complaint_rate": await complaint_rate(db, ctx.owner_id),
        "problems": [_job_json(j) for j in problems],
    }


# ─── sending domains ─────────────────────────────────────────────
def _domain_json(d: EmailDomain) -> dict:
    allowance = domains.bulk_allowance(d) if d.status == "verified" else None
    return {"id": d.id, "name": d.name, "status": d.status, "status_label": STATUS_LABEL.get(d.status, d.status),
            "verified": d.status == "verified", "records": d.records or [], "own_key": bool(d.sending_key),
            "bulk_today": allowance, "created_at": _iso(d.created_at), "checked_at": _iso(d.checked_at),
            "verified_at": _iso(d.verified_at)}


async def _own_domain(domain_id: str, ctx: AuthContext, db: AsyncSession) -> EmailDomain:
    d = (await db.execute(select(EmailDomain).where(EmailDomain.id == domain_id, EmailDomain.user_id == ctx.owner_id))).scalars().first()
    if d is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return d


@router.get("/domains")
async def list_domains(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EmailDomain).where(EmailDomain.user_id == ctx.owner_id).order_by(EmailDomain.created_at))).scalars().all()
    return [_domain_json(d) for d in rows]


class DomainIn(BaseModel):
    name: str = Field(..., max_length=253)


@router.post("/domains")
async def add_domain(data: DomainIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require_workspace_feature(db, ctx.owner_id, "email_alerts")  # emails to customers: Growth
    rate_limit(f"email-domain:{ctx.owner_id}", 10, 3600)
    try:
        return _domain_json(await domains.add(db, ctx.owner_id, data.name))
    except domains.DomainError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/domains/{domain_id}/verify")
async def verify_domain(domain_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    d = await _own_domain(domain_id, ctx, db)
    rate_limit(f"email-verify:{d.id}", 12, 600)
    try:
        return _domain_json(await domains.verify(db, d))
    except domains.DomainError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/domains/{domain_id}")
async def remove_domain(domain_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    d = await _own_domain(domain_id, ctx, db)
    try:
        await domains.remove(db, d)
    except domains.DomainError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "removed"}


# ─── who emails come from ────────────────────────────────────────
def _sender_json(s: senders.Sender) -> dict:
    return {"name": s.name, "address": s.address, "reply_to": s.reply_to, "domain": s.domain}


@router.get("/senders")
async def list_senders(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == ctx.owner_id))).scalars().first()
    bots = (await db.execute(select(Bot).where(Bot.user_id == ctx.owner_id).order_by(Bot.created_at))).scalars().all()
    rows = {r.bot_id: r for r in (await db.execute(select(EmailSender).where(EmailSender.user_id == ctx.owner_id))).scalars().all()}
    own = (await db.execute(select(EmailDomain).where(EmailDomain.user_id == ctx.owner_id).order_by(EmailDomain.created_at))).scalars().all()
    assistants = []
    for b in bots:
        r = rows.get(b.bot_id)
        assistants.append({"bot_id": b.bot_id, "bot_name": b.bot_name, "from_name": (r.from_name if r else None) or "",
                           "local_part": (r.local_part if r else None) or "", "domain_id": (r.domain_id if r else None) or "",
                           "reply_to": (r.reply_to if r else None) or "",
                           "sends_as": _sender_json(await senders.sender_for(db, ctx.owner_id, b.bot_id, settings))})
    return {
        "default": {"from_name": (settings.sender_name if settings else None) or "",
                    "local_part": (settings.sender_local if settings else None) or "",
                    "domain_id": (settings.sender_domain_id if settings else None) or "",
                    "reply_to": (settings.reply_to if settings else None) or "",
                    "sends_as": _sender_json(await senders.sender_for(db, ctx.owner_id, None, settings))},
        "assistants": assistants,
        "domains": [{"id": d.id, "name": d.name, "verified": d.status == "verified"} for d in own],
        "nimmi_address": email.address_of(email.customer_sender()),
    }


class SenderIn(BaseModel):
    from_name: str = Field("", max_length=60)
    local_part: str = Field("", max_length=64)
    domain_id: str = Field("", max_length=36)
    reply_to: str = Field("", max_length=200)


@router.put("/senders/{bot_id}")
async def save_sender(bot_id: str, data: SenderIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """`bot_id` "default": the workspace's own settings, which every assistant uses for what it leaves empty."""
    await plans.require_workspace_feature(db, ctx.owner_id, "email_alerts")
    name = "".join(ch for ch in data.from_name if ch not in '<>"\r\n').strip()
    local = None
    if data.local_part.strip():
        local = senders.clean_local(data.local_part)
        if not local:
            raise HTTPException(status_code=400, detail="The part before the @ can have letters, numbers, dots, dashes and underscores")
    reply_to = data.reply_to.strip()
    if reply_to and not automations.EMAIL_RE.fullmatch(reply_to):
        raise HTTPException(status_code=400, detail="Enter a valid reply-to email address")
    domain_id = data.domain_id.strip() or None
    if domain_id:
        await _own_domain(domain_id, ctx, db)

    if bot_id == "default":
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == ctx.owner_id))).scalars().first()
        if settings is None:
            settings = IntegrationSettings(user_id=ctx.owner_id, email_alerts=True, whatsapp_language="en")
            db.add(settings)
        settings.sender_name, settings.sender_local = name or None, local
        settings.sender_domain_id, settings.reply_to = domain_id, reply_to or None
    else:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
        if bot is None:
            raise HTTPException(status_code=404, detail="Assistant not found")
        row = await db.get(EmailSender, bot_id)
        if row is None:
            row = EmailSender(bot_id=bot_id, user_id=ctx.owner_id)
            db.add(row)
        row.from_name, row.local_part, row.domain_id, row.reply_to = name or None, local, domain_id, reply_to or None
    await db.commit()
    return await list_senders(ctx, db)


# ─── addresses not emailed ───────────────────────────────────────
@router.get("/suppressions")
async def list_suppressions(q: str = "", reason: str = "", offset: int = 0, limit: int = 50,
                            ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    base = [EmailUnsubscribe.user_id == ctx.owner_id]
    if q.strip():
        base.append(func.lower(EmailUnsubscribe.email).like(f"%{q.strip().lower()}%"))
    counts = dict((await db.execute(select(func.coalesce(EmailUnsubscribe.reason, "unsubscribed"), func.count())
                                    .where(*base).group_by(func.coalesce(EmailUnsubscribe.reason, "unsubscribed")))).all())
    where = base + ([func.coalesce(EmailUnsubscribe.reason, "unsubscribed") == reason] if reason else [])
    rows = (await db.execute(select(EmailUnsubscribe).where(*where).order_by(EmailUnsubscribe.created_at.desc())
                             .offset(max(0, offset)).limit(min(max(limit, 1), 100)))).scalars().all()
    names = {b: n for b, n in (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all()}

    def text(r: EmailUnsubscribe) -> str:
        why = r.reason or "unsubscribed"
        return suppress.TEXT["marketing"] if why == "unsubscribed" and (r.scope or "all") == "marketing" else suppress.TEXT.get(why, why)
    return {"items": [{"id": r.id, "email": r.email, "reason": r.reason or "unsubscribed", "text": text(r),
                       "only_marketing": (r.scope or "all") == "marketing", "bot_name": names.get(r.bot_id) if r.bot_id else None,
                       "created_at": _iso(r.created_at), "removable": r.reason == "team"} for r in rows],
            "counts": counts, "total": sum(counts.values()) if not reason else counts.get(reason, 0)}


@router.delete("/suppressions/{row_id}")
async def remove_suppression(row_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(EmailUnsubscribe).where(EmailUnsubscribe.id == row_id, EmailUnsubscribe.user_id == ctx.owner_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if row.reason != "team":
        raise HTTPException(status_code=409, detail=(
            "Only addresses your team stopped can be emailed again from here. People who unsubscribed can resubscribe "
            "from the link in any email; spam reports and bounced addresses stay stopped."))
    await db.delete(row)
    await db.commit()
    return {"status": "removed"}


# ─── Resend's events (public, signed) ────────────────────────────
@router.post("/webhooks/resend")
async def resend_webhook(request: Request):
    secret = os.getenv("RESEND_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="RESEND_WEBHOOK_SECRET isn't set on the server")
    body = await request.body()
    headers = request.headers
    event_id = headers.get("svix-id", "")
    if not webhooks.signature_ok(secret, event_id, headers.get("svix-timestamp", ""), headers.get("svix-signature", ""), body):
        raise HTTPException(status_code=401, detail="The signature doesn't match")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    if isinstance(payload, dict):
        await webhooks.handle(event_id, payload)
    return {"ok": True}
