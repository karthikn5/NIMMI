"""
The dashboard's Email section (/api/email): an overview, the business's own sending domains, who each assistant's
emails come from, the addresses it doesn't email, each assistant's emails and their designs, and the AI's after-call
emails waiting for the team (Drafts). Plus links in emails (public) and Resend's webhook (public, signed). History, bulk
email and the workspace's automations keep their routes (routers/email_center.py, routers/integrations.py).
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, rate_limit, require_manager
from backend.models import (Bot, EmailDomain, EmailJob, EmailLink, EmailSender, EmailSetup, EmailTemplate, EmailUnsubscribe,
                            IntegrationSettings, User, WhatsAppFile)
from database import get_db
from mail import address, after_call, compose, designs, domains, links, render, senders, setup, suppress, threads, webhooks
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
    from mail.broadcasts import complaint_rate
    from routers.email_center import _job_json
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
        "drafts": by_status.get("draft", 0),
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
    await plans.require_workspace_feature(db, ctx.owner_id, "team_alerts")
    if data.domain_id.strip():  # sending from their own domain: Growth
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
    await address.reply_address_works(reply_to)
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


# ─── an assistant's emails: which are on, and how each looks ─────
async def _own_bot(bot_id: str, ctx: AuthContext, db: AsyncSession) -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if bot is None:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return bot


@router.get("/setup/{bot_id}")
async def get_setup(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await _own_bot(bot_id, ctx, db)
    row = await db.get(EmailSetup, bot.bot_id)
    saved = {}
    for kind in designs.KINDS:
        saved[kind] = sorted({r for (r,) in (await db.execute(select(EmailTemplate.language).where(
            EmailTemplate.bot_id == bot.bot_id, EmailTemplate.kind == kind))).all()})
    return {"bot_id": bot.bot_id, "bot_name": bot.bot_name,
            "automations": await setup.automations_for(db, ctx.owner_id, bot.bot_id),
            "own_automations": bool(row is not None and row.automations),
            "settings": await setup.settings_for(db, bot.bot_id), "replies_on": threads.enabled(),
            "kinds": [{"kind": k, "label": v["label"], "about": v["about"], "placeholders": v["placeholders"],
                       "languages": list(v["designs"]), "saved": saved[k]} for k, v in designs.KINDS.items()],
            "languages": designs.LANGUAGES, "delays": list(automations.DELAYS)}


class SetupIn(BaseModel):
    automations: Optional[dict] = None  # {"chat_lead": {"enabled", "steps"}}: this assistant's own
    settings: Optional[dict] = None     # {"after_call": {...}, "welcome": {...}}


GROWTH_SETTINGS = {"after_call", "replies", "journeys", "question_answer", "consent", "during_call", "lead_email", "lead_call", "callback_booked", "voicemail", "missed_chat", "chat_copy"}


@router.put("/setup/{bot_id}")
async def save_setup(bot_id: str, data: SetupIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require_workspace_feature(db, ctx.owner_id, "team_alerts")
    bot = await _own_bot(bot_id, ctx, db)
    row = await db.get(EmailSetup, bot.bot_id)
    if data.automations is not None:
        try:
            given = automations.checked(data.automations)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        before = await setup.automations_for(db, ctx.owner_id, bot.bot_id)
        if automations.grows(before, {**before, **given}):  # beyond the one-email welcome: Growth
            await plans.require_feature(db, bot.bot_id, "email_alerts")
        if any(a["enabled"] for a in given.values()):
            sender = await senders.sender_for(db, ctx.owner_id, bot.bot_id)
            if not sender.reply_to:
                raise HTTPException(status_code=400, detail="Add where replies go (Email > Settings) so customers can answer you")
        if row is None:
            row = EmailSetup(bot_id=bot.bot_id, user_id=ctx.owner_id)
            db.add(row)
        row.automations = {**(row.automations or {}), **given}
    for kind, values in (data.settings or {}).items():
        if kind not in setup.SETTINGS or not isinstance(values, dict):
            raise HTTPException(status_code=400, detail="Unknown email setting")
        allowed = {k: v for k, v in values.items() if k in setup.SETTINGS[kind] and k not in ("approved", "approved_unchanged", "suggested")}
        turning_on = any(v not in (False, "off", 0, None, []) for k, v in allowed.items() if k in ("enabled", "inbound", "outbound", "mode"))
        if kind in GROWTH_SETTINGS and turning_on:
            await plans.require_feature(db, bot.bot_id, "email_alerts")
            if not (await senders.sender_for(db, ctx.owner_id, bot.bot_id)).reply_to:
                raise HTTPException(status_code=400, detail="Add where replies go (Email > Settings) so customers can answer you")
        if kind == "after_call" and any(allowed.get(d) not in (None, "off", "review", "auto") for d in ("inbound", "outbound")):
            raise HTTPException(status_code=400, detail="The after-call email is off, review first, or automatic")
        if kind == "consent" and "words" in allowed and not 5 <= len(str(allowed["words"] or "").strip()) <= 200:
            raise HTTPException(status_code=400, detail="Write the words next to the box, in 5 to 200 characters")
        if kind == "consent" and "ask" in allowed:
            allowed["ask"] = bool(allowed["ask"])
        if kind == "journeys" and not all(isinstance(allowed.get(k, 1), int) and 1 <= allowed.get(k, 1) <= 14 for k in ("per_day", "per_week")):
            raise HTTPException(status_code=400, detail="Choose between 1 and 14 emails")
        if kind == "replies" and allowed.get("mode") not in (None, "ai", "draft", "team"):
            raise HTTPException(status_code=400, detail="Replies are answered by the AI, drafted by it, or left to your team")
        await setup.save_settings(db, ctx.owner_id, bot.bot_id, kind, allowed)
    await db.commit()
    return await get_setup(bot.bot_id, ctx, db)


def _kind(kind: str) -> str:
    if kind not in designs.KINDS:
        raise HTTPException(status_code=404, detail="Unknown email")
    return kind


@router.get("/designs/{bot_id}/{kind}")
async def get_design(bot_id: str, kind: str, language: str = "en", ctx: AuthContext = Depends(require_manager),
                     db: AsyncSession = Depends(get_db)):
    bot = await _own_bot(bot_id, ctx, db)
    return await setup.design_for(db, ctx.owner_id, bot.bot_id, _kind(kind), language if language in designs.LANGUAGES else "en")


class DesignIn(BaseModel):
    language: str = Field("en", max_length=8)
    subject: str = Field(..., max_length=200)
    blocks: list = Field(default_factory=list)


@router.put("/designs/{bot_id}/{kind}")
async def save_design(bot_id: str, kind: str, data: DesignIn, ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    await plans.require_workspace_feature(db, ctx.owner_id, "team_alerts")
    bot = await _own_bot(bot_id, ctx, db)
    kind = _kind(kind)
    if data.language not in designs.LANGUAGES:
        raise HTTPException(status_code=400, detail="Unknown language")
    blocks = designs.clean(data.blocks)
    if not data.subject.strip() or not blocks:
        raise HTTPException(status_code=400, detail="Add a subject and at least one block")
    row = (await db.execute(select(EmailTemplate).where(EmailTemplate.bot_id == bot.bot_id, EmailTemplate.kind == kind,
                                                        EmailTemplate.language == data.language))).scalars().first()
    if row is None:
        row = EmailTemplate(user_id=ctx.owner_id, bot_id=bot.bot_id, kind=kind, language=data.language)
        db.add(row)
    row.subject, row.blocks, row.updated_by = data.subject.strip(), blocks, ctx.user_id
    await db.commit()
    return await setup.design_for(db, ctx.owner_id, bot.bot_id, kind, data.language)


@router.delete("/designs/{bot_id}/{kind}")
async def reset_design(bot_id: str, kind: str, language: str = "en", ctx: AuthContext = Depends(require_manager),
                       db: AsyncSession = Depends(get_db)):
    """Back to the ready-made design for that language."""
    bot = await _own_bot(bot_id, ctx, db)
    row = (await db.execute(select(EmailTemplate).where(EmailTemplate.bot_id == bot.bot_id, EmailTemplate.kind == _kind(kind),
                                                        EmailTemplate.language == language))).scalars().first()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return await setup.design_for(db, ctx.owner_id, bot.bot_id, kind, language)


SAMPLE = {
    "name": "Priya Sharma", "first_name": "Priya", "email": "priya@example.com", "phone": "+91 98765 43210",
    "details": "Interested in: 2BHK\nVisit: Saturday", "details_map": {"Interested in": "2BHK", "Visit": "Saturday"},
    "ai_note": "You asked about weekend site visits for a 2BHK; our team can show you the homes that are ready this Saturday.",
    "call": {"recap": ["You asked about 2BHK homes near Anna Nagar.", "We booked a site visit for Saturday at 11 am."],
             "answers": [{"q": "Is parking included?", "a": "Yes, every home has one covered parking space."}],
             "next_step": "Our team will meet you at the site on Saturday at 11 am."},
    "meeting": {"when": "Saturday 4 November, 11:00 am", "where": "Online (Google Meet)"},
    "meeting_subject": "Your meeting is confirmed", "meeting_text": "Hi Priya, your meeting with us is confirmed.",
    "callback_when": "today at 4 pm",
    "transcript": [{"who": "You", "text": "Do you have 2BHK homes?"}, {"who": "Assistant", "text": "Yes, three are ready to move in."}],
}


async def _sample(db: AsyncSession, ctx: AuthContext, bot: Bot, sender: senders.Sender) -> dict:
    files = (await db.execute(select(WhatsAppFile).where(WhatsAppFile.user_id == ctx.owner_id).order_by(
        WhatsAppFile.created_at.desc()).limit(2))).scalars().all()
    wa = await compose.whatsapp_link(db, ctx.owner_id, bot.bot_id)
    return {**SAMPLE, "business": sender.name, "assistant": bot.bot_name, "signature": sender.name,
            "files": [{"name": f.name, "url": "#", "size": compose._size(f.size)} for f in files] or
                     [{"name": "Brochure.pdf", "url": "#", "size": "1.2 MB"}],
            "actions": {"whatsapp": wa or "https://wa.me/919876543210", "book": "https://nimmiai.in", "call": "https://nimmiai.in", "join": "https://meet.google.com",
                        "change": "https://nimmiai.in", "cancel": "https://nimmiai.in"}}


async def _rendered(db: AsyncSession, ctx: AuthContext, bot_id: str, kind: str, data: DesignIn) -> tuple[render.Rendered, Bot, senders.Sender]:
    bot = await _own_bot(bot_id, ctx, db)
    sender = await senders.sender_for(db, ctx.owner_id, bot.bot_id)
    design = {"subject": data.subject, "blocks": designs.clean(data.blocks)}
    made = render.email(design, await _sample(db, ctx, bot, sender), render.brand_of(bot.visual_config, sender.name),
                        language=data.language if data.language in designs.LANGUAGES else "en",
                        unsubscribe_url="https://nimmiai.in" if kind != "chat_copy" else None, link=links.preview)
    return made, bot, sender


@router.post("/designs/{bot_id}/{kind}/preview")
async def preview_design(bot_id: str, kind: str, data: DesignIn, ctx: AuthContext = Depends(require_manager),
                         db: AsyncSession = Depends(get_db)):
    """The email with sample details (nothing is sent)."""
    made, _, sender = await _rendered(db, ctx, bot_id, _kind(kind), data)
    return {"subject": made.subject, "html": made.html, "text": made.text, "preheader": made.preheader,
            "from": f"{sender.name} <{sender.address}>", "reply_to": sender.reply_to,
            "too_big": len(made.html) > render.GMAIL_CLIPS}


@router.post("/designs/{bot_id}/{kind}/test")
async def test_design(bot_id: str, kind: str, data: DesignIn, ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    """The email with sample details, to the signed-in person's own address."""
    await plans.require_workspace_feature(db, ctx.owner_id, "team_alerts")
    rate_limit(f"email-test:{ctx.user_id}", 10, 3600)
    made, bot, sender = await _rendered(db, ctx, bot_id, _kind(kind), data)
    me = (await db.execute(select(User.email).where(User.id == ctx.user_id))).scalar_one_or_none()
    if not me:
        raise HTTPException(status_code=400, detail="Your account has no email address")
    sent = await email.deliver(me, f"[Test] {made.subject}", made.text, made.html, from_name=sender.name,
                               from_address=sender.address, api_key=sender.api_key, reply_to=sender.reply_to,
                               tags={"ws": ctx.owner_id, "kind": "test"})
    if not sent.ok:
        raise HTTPException(status_code=409, detail=sent.error or "The test email couldn't be sent")
    return {"to": me}


# ─── drafts: the AI's after-call emails waiting for the team ─────
def _draft_json(job: EmailJob, bot_name: Optional[str]) -> dict:
    data = job.merge_data or {}
    written = data.get("call") or {}
    return {"id": job.id, "to": job.to_email, "name": data.get("name"), "phone": data.get("phone"), "bot_id": job.bot_id,
            "bot_name": bot_name, "direction": data.get("direction"), "call_id": job.ref_id, "language": data.get("language") or "en",
            "created_at": _iso(job.created_at), "subject": data.get("subject") or "",
            "state": {"pending": "writing", "working": "writing", "failed": "failed"}.get(job.compose_state, "ready"),
            "note": job.error, "fixed": data.get("fixed"), "unanswered": data.get("unanswered") or [],
            "recap": written.get("recap") or [], "answers": written.get("answers") or [], "next_step": written.get("next_step") or "",
            "file_ids": data.get("file_ids") or []}


async def _own_draft(job_id: str, ctx: AuthContext, db: AsyncSession) -> EmailJob:
    job = (await db.execute(select(EmailJob).where(EmailJob.id == job_id, EmailJob.user_id == ctx.owner_id,
                                                   EmailJob.status == "draft"))).scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="This draft isn't waiting any more")
    return job


async def _suggestions(db: AsyncSession, owner_id: str) -> list[dict]:
    """Assistants whose team has approved enough emails to be offered automatic sending."""
    rows = (await db.execute(select(EmailSetup, Bot.bot_name).join(Bot, Bot.bot_id == EmailSetup.bot_id)
                             .where(EmailSetup.user_id == owner_id))).all()
    out = []
    for row, name in rows:
        prefs = {**setup.SETTINGS["after_call"], **((row.settings or {}).get("after_call") or {})}
        if (prefs["approved"] >= after_call.APPROVALS_BEFORE_ASKING and not prefs["suggested"]
                and "review" in (prefs["inbound"], prefs["outbound"])):
            out.append({"bot_id": row.bot_id, "bot_name": name, "approved": prefs["approved"], "unchanged": prefs["approved_unchanged"]})
    return out


@router.get("/drafts")
async def list_drafts(limit: int = 50, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    mine = [EmailJob.user_id == ctx.owner_id, EmailJob.status == "draft"]
    rows = (await db.execute(select(EmailJob).where(*mine).order_by(EmailJob.created_at.desc()).limit(min(max(limit, 1), 100)))).scalars().all()
    names = {b: n for b, n in (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all()}
    total = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine))).scalar_one()
    return {"items": [_draft_json(j, names.get(j.bot_id)) for j in rows], "total": total, "suggest": await _suggestions(db, ctx.owner_id)}


async def _draft_detail(db: AsyncSession, ctx: AuthContext, job: EmailJob) -> dict:
    bot = await db.get(Bot, job.bot_id)
    sender = await senders.sender_for(db, ctx.owner_id, job.bot_id)
    shown, _ = await after_call.made(db, job, sender, "https://nimmiai.in", link=links.preview)
    files = await compose._files(db, ctx.owner_id, job.bot_id)
    return {**_draft_json(job, bot.bot_name if bot else None), "html": shown.html, "text": shown.text, "shown_subject": shown.subject,
            "from": f"{sender.name} <{sender.address}>", "reply_to": sender.reply_to,
            "files_available": [{"id": f.id, "name": f.name, "size": compose._size(f.size)} for f in files]}


@router.get("/drafts/{job_id}")
async def get_draft(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    return await _draft_detail(db, ctx, await _own_draft(job_id, ctx, db))


class AnswerIn(BaseModel):
    q: str = Field(..., max_length=200)
    a: str = Field(..., max_length=800)


class DraftIn(BaseModel):
    to: str = Field(..., max_length=200)
    subject: str = Field("", max_length=200)
    recap: list[str] = Field(default_factory=list, max_length=6)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=10)
    next_step: str = Field("", max_length=800)
    file_ids: list[str] = Field(default_factory=list, max_length=6)


@router.put("/drafts/{job_id}")
async def save_draft(job_id: str, data: DraftIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The team's changes. They're saved as they type, and the preview comes back."""
    job = await _own_draft(job_id, ctx, db)
    if job.compose_state in ("pending", "working"):
        raise HTTPException(status_code=409, detail="The AI is still writing this email")
    to = data.to.strip()
    if not automations.EMAIL_RE.fullmatch(to):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    job.to_email = to
    call = {"recap": [p.strip()[:300] for p in data.recap if p.strip()],
            "answers": [{"q": a.q.strip(), "a": a.a.strip()} for a in data.answers if a.q.strip() and a.a.strip()],
            "next_step": data.next_step.strip()}
    job.merge_data = {**(job.merge_data or {}), "call": call, "subject": data.subject.strip(), "file_ids": data.file_ids}
    await db.commit()
    return await _draft_detail(db, ctx, job)


@router.post("/drafts/{job_id}/send")
async def send_draft(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The team approves it. It goes out on the next pass of the email loop, whatever the setting says by then."""
    job = await _own_draft(job_id, ctx, db)
    if job.compose_state in ("pending", "working"):
        raise HTTPException(status_code=409, detail="The AI is still writing this email")
    data = dict(job.merge_data or {})
    written = data.get("call") or {}
    design = await setup.design_for(db, ctx.owner_id, job.bot_id, "after_call", data.get("language") or "en")
    if any(b.get("type") == "call_summary" for b in design["blocks"]) and not written.get("recap"):
        raise HTTPException(status_code=400, detail="Add what you talked about first")
    why = await suppress.why_blocked(db, ctx.owner_id, job.to_email)
    if why:
        raise HTTPException(status_code=409, detail=f"This address isn't emailed: {why}")
    if not email.is_configured():
        raise HTTPException(status_code=409, detail="Email sending isn't set up on the server yet")
    original = data.get("original") or {}
    unchanged = (written == original.get("call") and (data.get("file_ids") or []) == (original.get("file_ids") or [])
                 and not data.get("subject"))
    data["approved_by"] = ctx.user_id
    claimed = await db.execute(update(EmailJob).where(EmailJob.id == job.id, EmailJob.status == "draft").values(
        status="queued", compose_state="done", error=None, send_at=datetime.utcnow(), merge_data=data)
        .execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise HTTPException(status_code=404, detail="This draft isn't waiting any more")
    prefs = (await setup.settings_for(db, job.bot_id))["after_call"]
    await setup.save_settings(db, ctx.owner_id, job.bot_id, "after_call", {
        "approved": prefs["approved"] + 1, "approved_unchanged": prefs["approved_unchanged"] + (1 if unchanged else 0)})
    await db.commit()
    return {"status": "sending"}


@router.post("/drafts/{job_id}/discard")
async def discard_draft(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    job = await _own_draft(job_id, ctx, db)
    job.status, job.error = "cancelled", "Discarded by your team"
    await db.commit()
    return {"status": "discarded"}


@router.post("/drafts/{job_id}/rewrite")
async def rewrite_draft(job_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The AI writes it again, from the call."""
    job = await _own_draft(job_id, ctx, db)
    if job.compose_state in ("pending", "working"):
        raise HTTPException(status_code=409, detail="The AI is still writing this email")
    rate_limit(f"email-rewrite:{ctx.owner_id}", 20, 600)
    job.compose_state, job.error, job.send_at = "pending", None, datetime.utcnow()
    await db.commit()
    return {"status": "writing"}


class SuggestionIn(BaseModel):
    bot_id: str = Field(..., max_length=36)
    accept: bool


@router.post("/drafts/suggestion")
async def answer_suggestion(data: SuggestionIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The offer to send after-call emails automatically: yes, or not now (it isn't made again)."""
    bot = await _own_bot(data.bot_id, ctx, db)
    prefs = (await setup.settings_for(db, bot.bot_id))["after_call"]
    values: dict = {"suggested": True}
    if data.accept:
        await plans.require_feature(db, bot.bot_id, "email_alerts")
        values.update({d: "auto" for d in ("inbound", "outbound") if prefs[d] == "review"})
    await setup.save_settings(db, ctx.owner_id, bot.bot_id, "after_call", values)
    await db.commit()
    return {"status": "saved"}


# ─── links in emails (public) ────────────────────────────────────
@router.get("/l/{token}")
async def open_link(token: str, db: AsyncSession = Depends(get_db)):
    """A link or a file from a customer email: counted, then opened (a redirect) or downloaded."""
    row = await db.get(EmailLink, token[:32])
    if row is None:
        return HTMLResponse("<!doctype html><title>Link not found</title><p style='font-family:sans-serif;margin:15vh auto;"
                            "max-width:420px'>This link isn't available any more.</p>", status_code=404)
    now = datetime.utcnow()
    row.clicks = (row.clicks or 0) + 1
    row.first_at = row.first_at or now
    row.last_at = now
    if row.job_id:
        job = await db.get(EmailJob, row.job_id)
        if job is not None:
            job.clicked_at = job.clicked_at or now
    await db.commit()
    if row.kind == "file" and row.target.startswith("file:"):
        f = await db.get(WhatsAppFile, row.target[len("file:"):])
        from whatsapp import storage
        content = await storage.load(f.stored) if f is not None and f.user_id == row.user_id else None
        if content is None:
            return HTMLResponse("<!doctype html><title>File not available</title><p style='font-family:sans-serif;margin:15vh auto;"
                                "max-width:420px'>This file isn't available any more. Reply to the email to ask for it.</p>",
                                status_code=404)
        safe = "".join(ch for ch in f.filename if ch.isalnum() or ch in "._- ")[:120] or "file"
        return Response(content, media_type=f.mime, headers={"Content-Disposition": f'attachment; filename="{safe}"',
                                                               "Cache-Control": "private, no-store"})
    if not row.target.startswith(("https://", "http://")):
        raise HTTPException(status_code=404, detail="Link not found")
    return RedirectResponse(row.target, status_code=302)


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
