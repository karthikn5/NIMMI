"""
Outbound campaigns (call a list of people who agreed to be called) and the
"Collected data" view: what each agent found out on its calls, as a table.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import assist
from auth import AuthContext, get_owned_bot, rate_limit, require_manager
from database import get_db
from backend.models import Bot, CallbackJob, CallLog, Campaign, DncEntry, PhoneNumber, VoiceAgent
from phone import callable_destination, display, to_e164
import plans

router = APIRouter(prefix="/api/voice", tags=["voice-campaigns"])

MAX_CONTACTS = 2000
TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ─── Collected data ───────────────────────────────────────────────
@router.get("/data")
async def collected_data(bot_id: str, days: int = 30, campaign_id: str = "", include_tests: bool = False,
                         ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """One row per call with the agent's fields as columns, plus success and sentiment."""
    bot = await get_owned_bot(bot_id, ctx, db)
    agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == bot.bot_id))).scalars().first()
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    query = select(CallLog).where(CallLog.user_id == ctx.owner_id, CallLog.bot_id == bot.bot_id, CallLog.started_at >= since,
                                  CallLog.outcome != "in_progress")
    if campaign_id:
        query = query.where(CallLog.campaign_id == campaign_id)
    if not include_tests:
        query = query.where(CallLog.channel == "phone")
    calls = (await db.execute(query.order_by(CallLog.started_at.desc()).limit(2000))).scalars().all()

    columns = [f["label"] for f in ((agent.collect_fields if agent else None) or []) if f.get("label")]
    extra: list[str] = []
    for c in calls:  # older calls may hold fields that aren't configured any more
        for key in (c.captured or {}):
            if key not in columns and key not in extra:
                extra.append(key)
    return {
        "columns": columns + extra,
        "configured": bool(columns),
        "rows": [{
            "call_id": c.id, "started_at": _iso(c.started_at), "direction": c.direction, "channel": c.channel,
            "caller": "Browser test" if c.channel == "browser" else display(c.caller_e164),
            "outcome": c.outcome, "successful": c.successful, "sentiment": c.sentiment, "summary": c.summary or "",
            "duration_sec": c.duration_sec or 0, "values": c.captured or {}, "campaign_id": c.campaign_id,
            "lead": assist.lead_score({**(c.captured or {}), **({"phone": c.caller_e164} if c.caller_e164 else {})},
                                      successful=c.successful, sentiment=c.sentiment, outcome=c.outcome),
        } for c in calls],
    }


# ─── Campaigns ────────────────────────────────────────────────────
class Contact(BaseModel):
    phone: str = Field(..., max_length=40)
    name: str = Field("", max_length=80)
    variables: dict[str, str] = {}


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    bot_id: str
    from_number_id: str
    purpose: str = Field(..., min_length=5, max_length=600)
    contacts: list[Contact]
    window_start: str = Field("10:00", pattern=TIME_RE)
    window_end: str = Field("19:00", pattern=TIME_RE)
    max_attempts: int = Field(2, ge=1, le=3)
    concurrency: int = Field(1, ge=1, le=5)
    start_at: Optional[datetime] = None
    consent: bool


async def _counts(db: AsyncSession, campaign_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {cid: {"total": 0, "queued": 0, "calling": 0, "done": 0, "failed": 0, "cancelled": 0}
                            for cid in campaign_ids}
    if not campaign_ids:
        return out
    rows = (await db.execute(select(CallbackJob.campaign_id, CallbackJob.status, func.count())
                             .where(CallbackJob.campaign_id.in_(campaign_ids))
                             .group_by(CallbackJob.campaign_id, CallbackJob.status))).all()
    for cid, status, n in rows:
        out[cid][status] = out[cid].get(status, 0) + n
        out[cid]["total"] += n
    success = dict((await db.execute(select(CallLog.campaign_id, func.count())
                                     .where(CallLog.campaign_id.in_(campaign_ids), CallLog.successful.is_(True))
                                     .group_by(CallLog.campaign_id))).all())
    for cid in campaign_ids:
        out[cid]["successful"] = success.get(cid, 0)
    return out


def _campaign_json(c: Campaign, counts: dict, bot_names: dict, numbers: dict) -> dict:
    return {
        "id": c.id, "name": c.name, "bot_id": c.bot_id, "bot_name": bot_names.get(c.bot_id, "Deleted assistant"),
        "purpose": c.purpose, "status": c.status, "from_number": numbers.get(c.from_number_id),
        "window_start": c.window_start, "window_end": c.window_end, "max_attempts": c.max_attempts,
        "concurrency": c.concurrency, "created_at": _iso(c.created_at), "completed_at": _iso(c.completed_at),
        "counts": counts,
    }


async def _lookups(db: AsyncSession, owner_id: str) -> tuple[dict, dict]:
    bots = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all())
    numbers = dict((await db.execute(select(PhoneNumber.id, PhoneNumber.number).where(PhoneNumber.user_id == owner_id))).all())
    return bots, numbers


@router.get("/campaigns")
async def list_campaigns(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    campaigns = (await db.execute(select(Campaign).where(Campaign.user_id == ctx.owner_id)
                                  .order_by(Campaign.created_at.desc()).limit(100))).scalars().all()
    counts = await _counts(db, [c.id for c in campaigns])
    bots, numbers = await _lookups(db, ctx.owner_id)
    return [_campaign_json(c, counts[c.id], bots, numbers) for c in campaigns]


@router.post("/campaigns")
async def create_campaign(data: CampaignCreate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "voice")
    rate_limit(f"campaign:{ctx.owner_id}", 10, 3600)
    if not data.consent:
        raise HTTPException(status_code=400, detail="Confirm that everyone on the list agreed to be called")
    bot = await get_owned_bot(data.bot_id, ctx, db)
    agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == bot.bot_id))).scalars().first()
    if not agent or not agent.voice_id:
        raise HTTPException(status_code=400, detail="Set up this assistant's voice first (Voice, then Agents)")
    number = (await db.execute(select(PhoneNumber).where(
        PhoneNumber.id == data.from_number_id, PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active"
    ))).scalars().first()
    if not number:
        raise HTTPException(status_code=400, detail="Choose an active number to call from")
    if not data.contacts:
        raise HTTPException(status_code=400, detail="The list is empty")
    if len(data.contacts) > MAX_CONTACTS:
        raise HTTPException(status_code=400, detail=f"A campaign can have up to {MAX_CONTACTS} people")

    blocked = set((await db.execute(select(DncEntry.e164).where(DncEntry.user_id == ctx.owner_id))).scalars().all())
    seen: set[str] = set()
    invalid = duplicates = skipped_dnc = 0
    clean: list[tuple[str, Contact]] = []
    for contact in data.contacts:
        e164 = to_e164(contact.phone)
        if not e164 or not callable_destination(e164):
            invalid += 1
        elif e164 in seen:
            duplicates += 1
        elif e164 in blocked:
            skipped_dnc += 1
        else:
            seen.add(e164)
            clean.append((e164, contact))
    if not clean:
        raise HTTPException(status_code=400, detail="None of the numbers can be called (invalid, in a country we don't call, repeated or on your do-not-call list)")

    start = data.start_at.astimezone(timezone.utc).replace(tzinfo=None) if data.start_at and data.start_at.tzinfo else data.start_at
    start = max(start or datetime.utcnow(), datetime.utcnow())
    campaign = Campaign(user_id=ctx.owner_id, bot_id=bot.bot_id, name=data.name.strip(), purpose=data.purpose.strip(),
                        status="running", from_number_id=number.id, window_start=data.window_start, window_end=data.window_end,
                        max_attempts=data.max_attempts, concurrency=data.concurrency,
                        consent_note=f"Consent confirmed by user {ctx.user_id} on {datetime.utcnow():%d %b %Y %H:%M} UTC")
    db.add(campaign)
    await db.flush()
    consent = f"On the '{campaign.name}' calling list (consent confirmed when uploaded)"
    for e164, contact in clean:
        variables = {str(k).strip()[:40]: str(v).strip()[:200] for k, v in list(contact.variables.items())[:20] if str(k).strip()}
        name = contact.name.strip() or variables.get("name", "")
        if name:
            variables["name"] = name
        db.add(CallbackJob(user_id=ctx.owner_id, bot_id=bot.bot_id, e164=e164, name=name or None, consent_source=consent,
                           next_attempt_at=start, campaign_id=campaign.id, variables=variables))
    await db.commit()
    counts = await _counts(db, [campaign.id])
    bots, numbers = await _lookups(db, ctx.owner_id)
    return {**_campaign_json(campaign, counts[campaign.id], bots, numbers),
            "skipped": {"invalid": invalid, "duplicates": duplicates, "do_not_call": skipped_dnc}}


async def _owned_campaign(campaign_id: str, ctx: AuthContext, db: AsyncSession) -> Campaign:
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == ctx.owner_id))).scalars().first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    campaign = await _owned_campaign(campaign_id, ctx, db)
    jobs = (await db.execute(select(CallbackJob).where(CallbackJob.campaign_id == campaign.id)
                             .order_by(CallbackJob.created_at))).scalars().all()
    calls = {c.id: c for c in (await db.execute(select(CallLog).where(CallLog.campaign_id == campaign.id))).scalars().all()}
    latest_by_number: dict[str, CallLog] = {}
    for c in sorted(calls.values(), key=lambda c: c.started_at or datetime.min):
        latest_by_number[c.caller_e164] = c  # unanswered attempts aren't linked to the job, so match by number
    counts = await _counts(db, [campaign.id])
    bots, numbers = await _lookups(db, ctx.owner_id)
    agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == campaign.bot_id))).scalars().first()
    contacts = []
    for j in jobs:
        call = calls.get(j.call_id) if j.call_id else latest_by_number.get(j.e164)
        contacts.append({
            "id": j.id, "phone": display(j.e164), "name": j.name, "variables": j.variables or {}, "status": j.status,
            "attempts": j.attempts, "last_error": j.last_error, "next_attempt_at": _iso(j.next_attempt_at),
            "call_id": call.id if call else None, "outcome": call.outcome if call else None,
            "successful": call.successful if call else None, "sentiment": call.sentiment if call else None,
            "summary": call.summary if call else None, "values": (call.captured or {}) if call else {},
        })
    return {**_campaign_json(campaign, counts[campaign.id], bots, numbers),
            "fields": [f["label"] for f in ((agent.collect_fields if agent else None) or []) if f.get("label")],
            "contacts": contacts}


@router.post("/campaigns/{campaign_id}/{action}")
async def campaign_action(campaign_id: str, action: str, ctx: AuthContext = Depends(require_manager),
                          db: AsyncSession = Depends(get_db)):
    campaign = await _owned_campaign(campaign_id, ctx, db)
    if action == "pause" and campaign.status == "running":
        campaign.status = "paused"
    elif action == "resume" and campaign.status == "paused":
        campaign.status = "running"
    elif action == "cancel" and campaign.status in ("running", "paused"):
        campaign.status, campaign.completed_at = "cancelled", datetime.utcnow()
        for job in (await db.execute(select(CallbackJob).where(
            CallbackJob.campaign_id == campaign.id, CallbackJob.status == "queued"
        ))).scalars().all():
            job.status, job.last_error = "cancelled", "Campaign stopped"
    else:
        raise HTTPException(status_code=400, detail=f"Can't {action} a {campaign.status} campaign")
    await db.commit()
    counts = await _counts(db, [campaign.id])
    bots, numbers = await _lookups(db, ctx.owner_id)
    return _campaign_json(campaign, counts[campaign.id], bots, numbers)
