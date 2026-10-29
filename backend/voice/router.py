"""HTTP and WebSocket API for voice. Shapes match dashboard/src/lib/voice/types.ts."""
import asyncio
import hmac
import logging
import os
import re
import statistics
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import (AuthContext, client_ip, decode_scoped_token, get_ctx, get_owned_bot, issue_scoped_token,
                  rate_limit, require_manager, require_owner)
from security import is_production, local_dev
from database import async_session, get_db
from backend.models import (Bot, CallbackJob, CallbackSettings, CallLog, Campaign, ComplianceSettings, Contact, Conversation,
                            DncEntry, Meeting, PhoneNumber, VoiceAgent, VoiceScript)
from notify.email import send_email
from notify.events import fire_and_forget
from phone import callable_destination, display, extract_contact, mask, to_e164
import assist
from voice import (accounts, ai_models, ambience, catalog, exotel, functions, llm, memory, metering, recording, sarvam,
                   schedule, scheduler, scripts, twilio)
from voice.pipeline import CallSession, CallSetup, prepare_opening
from voice.transports import BrowserTransport, ExotelTransport, TwilioTransport
import plans

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["voice"])


# ─── helpers ──────────────────────────────────────────────────────
def _agent_defaults(bot: Bot, owner_id: str) -> VoiceAgent:
    return VoiceAgent(
        bot_id=bot.bot_id, user_id=owner_id, enabled=False, language="en-IN", understand_code_mixed=True,
        voice_id=None, speaking_rate=1.0, assistant_name="Nimmi", company_name=bot.bot_name or "", greeting="How can I help you today?",
        allow_interruptions=True, silence_timeout_sec=8, max_call_minutes=10, transfer_enabled=False,
        transfer_number="", transfer_when="The caller asks to speak to a person.", end_call_phrases=["that's all", "bye"],
    )


async def _agent_for(bot: Bot, owner_id: str, db: AsyncSession) -> tuple[VoiceAgent, bool]:
    agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == bot.bot_id))).scalars().first()
    return (agent, True) if agent else (_agent_defaults(bot, owner_id), False)


def _direction(value: Optional[str]) -> str:
    """Which agent a request is about. None (the dashboard before incoming and outgoing agents) means outgoing: those
    were the only settings, and the incoming agent follows them until it's edited."""
    if value in (None, ""):
        return "outbound"
    if value not in scripts.DIRECTIONS:
        raise HTTPException(status_code=400, detail="Unknown kind of calls")
    return value


def _agent_json(agent: VoiceAgent, bot: Bot, direction: str = "outbound") -> dict:
    return {
        "bot_id": bot.bot_id, "bot_name": bot.bot_name, "direction": direction,
        "enabled": bool(agent.enabled), "language": agent.language,
        "understand_code_mixed": bool(agent.understand_code_mixed), "voice_id": agent.voice_id,
        "follow_caller_language": agent.follow_caller_language is not False,
        "switch_languages": agent.switch_languages or [],
        "remember_callers": agent.remember_callers is not False,
        "speaking_rate": agent.speaking_rate or 1.0, "assistant_name": agent.assistant_name or "",
        "company_name": agent.company_name or "", "greeting": agent.greeting or "",
        "allow_interruptions": bool(agent.allow_interruptions), "silence_timeout_sec": agent.silence_timeout_sec or 8,
        "max_call_minutes": agent.max_call_minutes or 10, "transfer_enabled": bool(agent.transfer_enabled),
        "transfer_number": agent.transfer_number or "", "transfer_when": agent.transfer_when or "",
        "end_call_phrases": agent.end_call_phrases or [],
        "call_goal": agent.call_goal or "", "collect_fields": agent.collect_fields or [],
        "ambience": agent.ambience or "none", "ambience_volume": agent.ambience_volume or "medium",
        "silence_reminders": 1 if agent.silence_reminders is None else agent.silence_reminders,
        "pronunciations": agent.pronunciations or [],
        "voicemail_action": agent.voicemail_action or "off", "voicemail_message": agent.voicemail_message or "",
        "transfer_mode": agent.transfer_mode or "cold", "ai_model": ai_models.ai_model(agent.ai_model).id,
        "functions": functions.public(agent.functions),
    }


class CollectField(BaseModel):
    key: str = Field("", max_length=60)
    label: str = Field("", max_length=100)
    type: str = "text"
    description: str = Field("", max_length=200)
    choices: list[str] = []
    required: bool = False


class Pronunciation(BaseModel):
    word: str = Field(..., min_length=1, max_length=40)
    say: str = Field(..., min_length=1, max_length=80)


def _clean_fields(fields: list[CollectField]) -> list[dict]:
    out, seen = [], set()
    for f in fields[:20]:
        label = (f.label or "").strip()
        if not label or label.lower() in seen:
            continue
        if f.type not in llm.FIELD_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown field type for {label}")
        choices = [c.strip()[:40] for c in f.choices if c.strip()][:12]
        if f.type == "choice" and len(choices) < 2:
            raise HTTPException(status_code=400, detail=f"Give {label} at least two choices")
        seen.add(label.lower())
        key = re.sub(r"[^\w]+", "_", (f.key or label).lower()).strip("_")[:40] or f"field_{len(out) + 1}"
        out.append({"key": key, "label": label, "type": f.type, "description": f.description.strip(),
                    "choices": choices if f.type == "choice" else [], "required": f.required})
    return out


async def _compliance(owner_id: str, db: AsyncSession) -> ComplianceSettings:
    c = (await db.execute(select(ComplianceSettings).where(ComplianceSettings.user_id == owner_id))).scalars().first()
    return c or ComplianceSettings(user_id=owner_id, record_calls=True, retention_days=90,
                                   opt_out_phrases=["don't call me", "do not call", "stop calling", "remove my number"])


async def _callbacks(owner_id: str, db: AsyncSession) -> CallbackSettings:
    c = (await db.execute(select(CallbackSettings).where(CallbackSettings.user_id == owner_id))).scalars().first()
    return c or CallbackSettings(user_id=owner_id, enabled=False, delay="1m", window_start="09:00",
                                 window_end="21:00", max_attempts=2, from_number_id=None)


def _call_json(c: CallLog, bot_names: dict, full: bool = False) -> dict:
    caller = "Browser test" if c.channel == "browser" else (display(c.caller_e164) if full else mask(c.caller_e164))
    data = {
        "id": c.id, "started_at": c.started_at.isoformat() if c.started_at else None, "direction": c.direction,
        "channel": c.channel, "caller": caller, "bot_id": c.bot_id, "bot_name": bot_names.get(c.bot_id, "Deleted assistant"),
        "duration_sec": c.duration_sec or 0, "outcome": c.outcome if c.outcome != "in_progress" else "answered",
        "in_progress": c.outcome == "in_progress", "language": c.language, "summary": c.summary,
        "captured": c.captured or {}, "consent_source": c.consent_source,
        "successful": c.successful, "sentiment": c.sentiment, "campaign_id": c.campaign_id,
        "credits_used": c.credits_used, "ai_model": ai_models.ai_model(c.ai_model).name if c.ai_model else None,
        "reply_sec": round(c.reply_ms / 1000, 2) if c.reply_ms else None,
    }
    if full:
        data["transcript"] = c.transcript or []
    return data


async def _bot_names(owner_id: str, db: AsyncSession) -> dict:
    rows = (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all()
    return {r[0]: r[1] for r in rows}


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ─── overview ─────────────────────────────────────────────────────
@router.get("/overview")
async def overview(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    this_month = _month_start(now)
    last_month = _month_start(this_month - timedelta(days=1))
    phone_calls = select(CallLog).where(CallLog.user_id == ctx.owner_id, CallLog.channel == "phone")

    month_calls = (await db.execute(phone_calls.where(CallLog.started_at >= this_month))).scalars().all()
    last_count = (await db.execute(
        select(func.count()).select_from(CallLog).where(CallLog.user_id == ctx.owner_id, CallLog.channel == "phone",
                                                        CallLog.started_at >= last_month, CallLog.started_at < this_month)
    )).scalar_one()
    connected = [c for c in month_calls if c.outcome not in ("no_answer", "in_progress", "failed")]
    resolved = [c for c in connected if c.outcome in ("answered", "lead_captured")]

    since = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    recent = (await db.execute(phone_calls.where(CallLog.started_at >= since))).scalars().all()
    by_day = {(since + timedelta(days=i)).date(): 0 for i in range(14)}
    for c in recent:
        d = c.started_at.replace(tzinfo=None).date()
        if d in by_day:
            by_day[d] += 1

    wallet = await metering.get_wallet(db, ctx.owner_id)
    agents = (await db.execute(select(VoiceAgent).where(VoiceAgent.user_id == ctx.owner_id))).scalars().all()
    active_number = (await db.execute(
        select(PhoneNumber.id).where(PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active")
    )).first()
    cb = await _callbacks(ctx.owner_id, db)
    return {
        "credits_left": metering.credits_left(wallet), "credits_included": wallet.plan_credits or 0,
        "credits_used": wallet.plan_credits_used or 0, "credits_bought": max(wallet.credits or 0, 0),
        "cycle_ends": wallet.cycle_end.isoformat() if wallet.cycle_end else None,
        "calls_this_month": len(month_calls), "calls_last_month": last_count,
        "ai_resolved_pct": round(100 * len(resolved) / len(connected)) if connected else 0,
        "avg_duration_sec": round(sum(c.duration_sec or 0 for c in connected) / len(connected)) if connected else 0,
        "leads_captured": sum(1 for c in month_calls if c.outcome == "lead_captured"),
        "calls_by_day": [{"date": datetime.combine(d, datetime.min.time()).isoformat(), "count": n} for d, n in by_day.items()],
        "setup": {
            "voice_chosen": any(a.voice_id for a in agents),
            "tested_in_browser": any(a.tested_at for a in agents),
            "number_active": active_number is not None,
            "callbacks_on": bool(cb.enabled),
        },
        "engine_ready": sarvam.configured(),
        "phone_ready": exotel.configured() or twilio.configured() or bool(active_number and active_number.account_id),
    }


# ─── agents & voices ──────────────────────────────────────────────
@router.get("/agents")
async def list_agents(direction: Optional[str] = None, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    is_local = local_dev()
    if is_local:
        bots = (await db.execute(select(Bot).order_by(Bot.created_at.desc()))).scalars().all()
        agents = {a.bot_id: a for a in (await db.execute(select(VoiceAgent))).scalars().all()}
        numbers = (await db.execute(select(PhoneNumber).where(PhoneNumber.status == "active"))).scalars().all()
    else:
        bots = (await db.execute(select(Bot).where(Bot.user_id == ctx.owner_id).order_by(Bot.created_at.desc()))).scalars().all()
        agents = {a.bot_id: a for a in (await db.execute(select(VoiceAgent).where(VoiceAgent.user_id == ctx.owner_id))).scalars().all()}
        numbers = (await db.execute(
            select(PhoneNumber).where(PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active")
        )).scalars().all()

    since = datetime.utcnow() - timedelta(days=30)
    counting = select(CallLog.bot_id, func.count()).where(CallLog.channel == "phone", CallLog.started_at >= since)
    if not is_local:
        counting = counting.where(CallLog.user_id == ctx.owner_id)
    if direction:
        counting = counting.where(CallLog.direction == _direction(direction))
    counts = dict((await db.execute(counting.group_by(CallLog.bot_id))).all())
    out = []
    for bot in bots:
        agent = agents.get(bot.bot_id) or _agent_defaults(bot, bot.user_id or ctx.owner_id)
        agent = scripts.for_direction(agent, _direction(direction))
        number = next((n.number for n in numbers if n.bot_id == bot.bot_id), None)
        out.append({"bot_id": bot.bot_id, "bot_name": bot.bot_name, "enabled": bool(agent.enabled), "language": agent.language,
                    "voice_id": agent.voice_id, "phone_number": number, "calls_30d": counts.get(bot.bot_id, 0)})
    return out


@router.get("/agents/{bot_id}")
async def get_agent(bot_id: str, direction: Optional[str] = None, ctx: AuthContext = Depends(get_ctx),
                    db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    direction = _direction(direction)
    return _agent_json(scripts.for_direction(agent, direction), bot, direction)


class AgentUpdate(BaseModel):
    enabled: bool
    language: str
    understand_code_mixed: bool
    follow_caller_language: bool = True
    switch_languages: list[str] = Field(default_factory=list, max_length=12)
    remember_callers: bool = True
    voice_id: Optional[str] = None
    speaking_rate: float = Field(1.0, ge=0.7, le=1.3)
    assistant_name: str = Field("", max_length=40)
    company_name: str = Field("", max_length=120)
    # What it says: on the Knowledge page now (voice_scripts). Sent only by the dashboard from before that page.
    greeting: Optional[str] = Field(None, max_length=300)
    allow_interruptions: bool = True
    silence_timeout_sec: int = Field(8, ge=3, le=60)
    max_call_minutes: int = Field(10, ge=1, le=60)
    transfer_enabled: bool = False
    transfer_number: str = ""
    transfer_when: str = Field("", max_length=500)
    end_call_phrases: list[str] = []
    call_goal: Optional[str] = Field(None, max_length=500)
    collect_fields: Optional[list[CollectField]] = None
    ambience: str = "none"
    ambience_volume: str = "medium"
    silence_reminders: int = Field(1, ge=0, le=3)
    pronunciations: list[Pronunciation] = []
    voicemail_action: str = "off"
    voicemail_message: str = Field("", max_length=500)
    transfer_mode: str = "cold"
    ai_model: Optional[str] = Field(None, max_length=40)  # voice/ai_models.py id ("auto": the default); None = unchanged
    functions: Optional[list[dict]] = Field(None, max_length=functions.MAX_FUNCTIONS + 1)  # None = unchanged


@router.put("/agents/{bot_id}")
async def update_agent(bot_id: str, data: AgentUpdate, direction: Optional[str] = None,
                       ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    direction = _direction(direction)
    if data.enabled:
        await plans.require(db, ctx.owner_id, "voice")
    bot = await get_owned_bot(bot_id, ctx, db)
    if data.language not in catalog.LANGUAGES or any(code not in catalog.LANGUAGES for code in data.switch_languages):
        raise HTTPException(status_code=400, detail="Unsupported language")
    if data.voice_id and data.voice_id not in catalog.VOICE_IDS:
        raise HTTPException(status_code=400, detail="Unknown voice")
    if data.enabled and not data.voice_id:
        raise HTTPException(status_code=400, detail="Choose a voice before turning on calls")
    if data.transfer_enabled and not to_e164(data.transfer_number):
        raise HTTPException(status_code=400, detail="Enter a valid number to transfer to")
    if data.ambience not in ambience.KINDS or data.ambience_volume not in ambience.VOLUMES:
        raise HTTPException(status_code=400, detail="Unknown background sound")
    if data.voicemail_action not in ("off", "hangup", "leave_message") or data.transfer_mode not in ("cold", "warm"):
        raise HTTPException(status_code=400, detail="Unknown option")
    agent, exists = await _agent_for(bot, ctx.owner_id, db)
    if data.ai_model is not None:
        data.ai_model = ai_models.DEFAULT if data.ai_model == "auto" else data.ai_model
        chosen = ai_models.AI_MODELS_BY_ID.get(data.ai_model)
        if not chosen:
            raise HTTPException(status_code=400, detail="Unknown AI model")
        # One that's no longer set up can stay while other settings are saved; calls use the default meanwhile.
        if not ai_models.available(chosen) and chosen.id != ai_models.ai_model(scripts.for_direction(agent, direction).ai_model).id:
            raise HTTPException(status_code=400, detail=f"{chosen.name} isn't available yet. Choose another model.")
    cleaned_functions = None
    if data.functions is not None:
        try:
            cleaned_functions = functions.clean(data.functions, scripts.for_direction(agent, direction).functions)
        except functions.FunctionError as e:
            raise HTTPException(status_code=400, detail=str(e))
    inbound = dict(agent.inbound or {})
    for field, value in data.model_dump().items():
        if value is None:
            continue  # what it says: not sent (it's on the Knowledge page)
        if field == "end_call_phrases":
            value = [p.strip().lower()[:60] for p in value if p.strip()][:20]
        elif field == "switch_languages":
            value = list(dict.fromkeys(value))
        elif field == "collect_fields":
            value = _clean_fields(data.collect_fields)
        elif field == "pronunciations":
            value = [{"word": p["word"].strip(), "say": p["say"].strip()} for p in value][:40]
        elif field == "functions":
            value = cleaned_functions
        if direction == "inbound" and field in scripts.PER_DIRECTION:
            inbound[field] = value
        elif direction == "inbound" and field in ("greeting", "call_goal", "collect_fields", "voicemail_action",
                                                  "voicemail_message"):
            continue  # the outgoing agent's
        else:
            setattr(agent, field, value)
    if direction == "inbound":
        # All of them, so later changes to the outgoing agent don't change this one.
        agent.inbound = {f: inbound.get(f, getattr(agent, f)) for f in scripts.PER_DIRECTION}
    if not exists:
        db.add(agent)
    await db.commit()
    await _prepare_openings(bot, agent, ctx.owner_id, db, direction)
    return _agent_json(scripts.for_direction(agent, direction), bot, direction)


async def _prepare_openings(bot: Bot, agent: VoiceAgent, owner_id: str, db: AsyncSession, *directions: str) -> None:
    """The opening for the next call coming in or going out, made now so it plays at once (best effort)."""
    recorded = bool((await _compliance(owner_id, db)).record_calls)
    for direction in directions:
        call_agent = scripts.for_direction(agent, direction)
        if call_agent.enabled and call_agent.voice_id:
            script, _ = await scripts.script_for(db, agent, direction)
            scripts.apply(call_agent, script, None)
            prepare_opening(call_agent, {}, recorded)


# ─── scripts: what the agents say (Knowledge) ──────────────────────
class ScriptAnswer(BaseModel):
    question: str = Field(..., max_length=200)
    answer: str = Field("", max_length=1000)


class ScriptUpdate(BaseModel):
    greeting: str = Field("", max_length=scripts.GREETING_CHARS)
    greeting_known: str = Field("", max_length=scripts.GREETING_CHARS)
    personality: str = Field("", max_length=scripts.PERSONALITY_CHARS)
    instructions: str = Field("", max_length=scripts.INSTRUCTIONS_CHARS)
    call_goal: str = Field("", max_length=scripts.GOAL_CHARS)
    collect_fields: list[CollectField] = []
    answers: list[ScriptAnswer] = Field(default_factory=list, max_length=15)


class DraftRequest(BaseModel):
    answers: list[ScriptAnswer] = Field(default_factory=list, max_length=15)


async def _script_reply(db: AsyncSession, bot: Bot, agent: VoiceAgent, direction: str) -> dict:
    script, saved = await scripts.script_for(db, agent, direction)
    return {**scripts.script_json(script, saved), "bot_id": bot.bot_id, "bot_name": bot.bot_name,
            "language": scripts.for_direction(agent, direction).language, "assistant_name": agent.assistant_name or "",
            "company_name": agent.company_name or bot.bot_name or ""}


@router.get("/scripts/{bot_id}/{direction}")
async def get_script(bot_id: str, direction: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    return await _script_reply(db, bot, agent, _direction(direction))


@router.put("/scripts/{bot_id}/{direction}")
async def update_script(bot_id: str, direction: str, data: ScriptUpdate, ctx: AuthContext = Depends(require_manager),
                        db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    direction = _direction(direction)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    row = (await db.execute(select(VoiceScript).where(
        VoiceScript.bot_id == bot.bot_id, VoiceScript.direction == direction))).scalars().first()
    if row is None:
        row = VoiceScript(bot_id=bot.bot_id, direction=direction, user_id=ctx.owner_id)
        db.add(row)
    row.greeting = data.greeting.strip()
    row.greeting_known = data.greeting_known.strip()
    row.personality = data.personality.strip()
    row.instructions = data.instructions.strip()
    row.call_goal = data.call_goal.strip()
    row.collect_fields = _clean_fields(data.collect_fields)
    row.answers = [a.model_dump() for a in data.answers if a.answer.strip()]
    await db.commit()
    await _prepare_openings(bot, agent, ctx.owner_id, db, direction)
    return await _script_reply(db, bot, agent, direction)


@router.post("/scripts/{bot_id}/{direction}/draft")
async def draft_script(bot_id: str, direction: str, data: DraftRequest, ctx: AuthContext = Depends(require_manager),
                       db: AsyncSession = Depends(get_db)):
    """Write with AI: a script from the owner's answers and the assistant's knowledge. Not saved: they review it."""
    bot = await get_owned_bot(bot_id, ctx, db)
    direction = _direction(direction)
    rate_limit(f"script-draft:{ctx.owner_id}", 20, 3600)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    try:
        knowledge = await llm.call_knowledge(bot)
        return await scripts.draft(bot, scripts.for_direction(agent, direction), direction,
                                   [a.model_dump() for a in data.answers], knowledge)
    except Exception as e:
        logger.warning(f"Writing a {direction} script for {bot.bot_id} failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't write the script just now. Please try again in a minute.")


# ─── contacts: who each assistant remembers ──────────────────────────
class ContactUpdate(BaseModel):
    name: str = Field("", max_length=80)
    email: str = Field("", max_length=120)
    notes: str = Field("", max_length=1000)


def _contact_json(c: Contact, bot_names: dict, full: bool = False) -> dict:
    data = {
        "id": c.id, "bot_id": c.bot_id, "bot_name": bot_names.get(c.bot_id, "Deleted assistant"),
        "number": display(c.e164) if full else mask(c.e164), "name": c.name or "", "calls": c.calls or 0,
        "last_call_at": c.last_call_at.isoformat() if c.last_call_at else None, "notes": c.notes or "",
        "lead_status": c.lead_status, "lead_reason": c.lead_reason or "", "lead_set_by_team": bool(c.lead_set_by),
        "follow_ups": c.follow_ups or 0, "follow_ups_off": bool(c.follow_ups_off),
    }
    if full:
        data.update({"email": c.email or "", "details": c.details or {},
                     "first_call_at": c.first_call_at.isoformat() if c.first_call_at else None,
                     "remember_from": c.remember_from.isoformat() if c.remember_from else None})
    return data


async def _owned_contact(contact_id: str, ctx: AuthContext, db: AsyncSession) -> Contact:
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == ctx.owner_id))).scalars().first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.get("/contacts")
async def list_contacts(bot_id: Optional[str] = None, q: str = "", ctx: AuthContext = Depends(get_ctx),
                        db: AsyncSession = Depends(get_db)):
    query = select(Contact).where(Contact.user_id == ctx.owner_id, or_(Contact.calls > 0, Contact.notes.is_not(None)))
    if bot_id:
        query = query.where(Contact.bot_id == bot_id)
    rows = (await db.execute(query.order_by(Contact.last_call_at.desc()).limit(500))).scalars().all()
    words = q.strip().lower()
    digits = re.sub(r"\D", "", words)
    if words:
        rows = [c for c in rows if words in (c.name or "").lower() or (digits and digits in (c.e164 or ""))]
    names = await _bot_names(ctx.owner_id, db)
    return [_contact_json(c, names) for c in rows]


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    contact = await _owned_contact(contact_id, ctx, db)
    calls = (await db.execute(select(CallLog).where(
        CallLog.user_id == ctx.owner_id, CallLog.bot_id == contact.bot_id, CallLog.caller_e164 == contact.e164,
    ).order_by(CallLog.started_at.desc()).limit(20))).scalars().all()
    names = await _bot_names(ctx.owner_id, db)
    return {**_contact_json(contact, names, full=True), "history": [
        {"id": c.id, "started_at": c.started_at.isoformat() if c.started_at else None, "direction": c.direction,
         "outcome": c.outcome, "summary": c.summary or "",
         "remembered": not (contact.remember_from and c.started_at and c.started_at < contact.remember_from)}
        for c in calls]}


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, data: ContactUpdate, ctx: AuthContext = Depends(require_manager),
                         db: AsyncSession = Depends(get_db)):
    contact = await _owned_contact(contact_id, ctx, db)
    contact.name = data.name.strip() or None
    contact.email = data.email.strip() or None
    contact.notes = data.notes.strip() or None
    await db.commit()
    return _contact_json(contact, await _bot_names(ctx.owner_id, db), full=True)


@router.post("/contacts/{contact_id}/forget")
async def forget_contact(contact_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The assistant forgets them: name, details, notes and earlier calls are no longer used (the calls stay in Calls;
    Compliance > Erase removes those too)."""
    contact = await _owned_contact(contact_id, ctx, db)
    contact.name = contact.email = contact.notes = None
    contact.details, contact.calls = {}, 0
    contact.remember_from = datetime.utcnow()
    await db.commit()
    return {"status": "forgotten"}


@router.get("/ambience")
async def ambience_kinds():
    return [{"id": k, "label": v} for k, v in ambience.KINDS.items()]


@router.get("/ambience/{kind}/sample")
async def ambience_sample(kind: str, volume: str = "medium"):
    if kind not in ambience.KINDS or volume not in ambience.VOLUMES:
        raise HTTPException(status_code=404, detail="Unknown background sound")
    wav = await asyncio.to_thread(ambience.preview_wav, kind, volume)
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/voices")
async def voices():
    return [{**v, "tone": "", "sample_url": f"/api/voice/voices/{v['id']}/sample"} for v in catalog.VOICES]


@router.get("/voices/{voice_id}/sample")
async def voice_sample(voice_id: str, request: Request, language: str = "en-IN"):
    if voice_id not in catalog.VOICE_IDS:
        raise HTTPException(status_code=404, detail="Unknown voice")
    if not sarvam.configured():
        raise HTTPException(status_code=503, detail="Voice samples need SARVAM_API_KEY on the server")
    rate_limit(f"sample:{client_ip(request)}", 30, 60)
    try:
        wav = await sarvam.voice_sample(voice_id, language)
    except sarvam.SarvamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


# ─── browser test calls ───────────────────────────────────────────
class SessionRequest(BaseModel):
    bot_id: str
    direction: str = "inbound"  # which agent to talk to: incoming or outgoing


@router.post("/session")
async def create_session(req: SessionRequest, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "voice")
    bot = await get_owned_bot(req.bot_id, ctx, db)
    if not sarvam.configured():
        raise HTTPException(status_code=503, detail="The voice engine needs SARVAM_API_KEY on the server")
    token = issue_scoped_token(f"{ctx.owner_id}:{bot.bot_id}:{_direction(req.direction)}", "voice_test", 120)
    return {"ws_path": "/api/voice/ws/browser", "token": token}


@router.websocket("/ws/browser")
async def browser_call(ws: WebSocket, token: str = ""):
    subject = decode_scoped_token(token, "voice_test")
    if not subject:
        await ws.close(code=4401)
        return
    _, bot_id, *rest = subject.split(":")
    direction = rest[0] if rest and rest[0] in scripts.DIRECTIONS else "inbound"
    async with async_session() as db:
        # The signed token is only issued after /session checked access to this bot, so trust it,
        # and run the call in the bot's own workspace (its credits, compliance and logs).
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        if not bot:
            await ws.close(code=4404)
            return
        owner_id = bot.user_id
        agent, _ = await _agent_for(bot, owner_id, db)
        script_row = (await db.execute(select(VoiceScript).where(
            VoiceScript.bot_id == bot.bot_id, VoiceScript.direction == direction))).scalars().first()
        compliance = await _compliance(owner_id, db)
    await ws.accept()
    agent, script = _for_call(agent, script_row, None, direction, {})
    setup = CallSetup(owner_id=owner_id, bot=bot, agent=agent, direction=direction, channel="browser",
                      record=bool(compliance.record_calls), opt_out_phrases=compliance.opt_out_phrases or [],
                      script=scripts.style(script), tools=await schedule.tools_for(owner_id, bot.bot_id, None, None, test=True))
    await CallSession(setup, BrowserTransport(ws)).run()
    try:
        await ws.close()
    except Exception:
        pass


# ─── Exotel phone calls ───────────────────────────────────────────
async def _exotel_scope(secret: str):
    """Nimmi's own Exotel (accounts.NIMMI) or the customer's connected account the token belongs to."""
    async with async_session() as db:
        scope = await accounts.by_hook(db, "exotel", secret)
    if scope is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    return scope


def _owner_of(scope) -> Optional[str]:
    return None if scope == accounts.NIMMI else scope.user_id


TEST_CALL = "Test call requested from the dashboard"


async def _first(query):
    """One lookup on its own connection, so a call's lookups can run side by side."""
    async with async_session() as db:
        return (await db.execute(query)).scalars().first()


async def _compliance_for(owner_id: str) -> ComplianceSettings:
    async with async_session() as db:
        return await _compliance(owner_id, db)


async def _nothing():
    return None


def _for_call(agent: VoiceAgent, script_row: Optional[VoiceScript], caller: Optional[dict], direction: str,
              variables: dict) -> tuple[VoiceAgent, VoiceScript]:
    """The agent as it is for one call: its direction's settings and script. Someone it knows is greeted by name."""
    call_agent = scripts.for_direction(agent, direction)
    script = script_row or scripts.default_script(call_agent, direction)
    known = (caller or {}).get("first_name")
    if known:
        variables.setdefault("name", known)
    scripts.apply(call_agent, script, known)
    return call_agent, script


def _job_variables(job: CallbackJob) -> dict:
    """A call's {{placeholders}}: a campaign's columns (a Schedule call's own notes aren't facts about the person)."""
    variables = {} if job.kind in schedule.KINDS else dict(job.variables or {})
    if job.name:
        variables.setdefault("name", job.name)
    return variables


async def prepare_job_opening(job: CallbackJob) -> None:
    """An outgoing call's opening, made while the phone rings, exactly as the call will say it (its direction's agent
    and script, the person's name, a Schedule call's own opening), so it plays the moment they answer."""
    try:
        scheduled = job.kind in schedule.CALL_KINDS
        bot, agent, script_row, caller_memory, compliance, inputs = await asyncio.gather(
            _first(select(Bot).where(Bot.bot_id == job.bot_id)),
            _first(select(VoiceAgent).where(VoiceAgent.bot_id == job.bot_id)),
            _first(select(VoiceScript).where(VoiceScript.bot_id == job.bot_id, VoiceScript.direction == "outbound")),
            memory.context_for(job.bot_id, job.e164),
            _compliance_for(job.user_id),
            schedule.plan_inputs(job) if scheduled else _nothing())
        if not (bot and agent):
            return
        if agent.remember_callers is False:
            caller_memory = None
        variables = _job_variables(job)
        call_agent, _ = _for_call(agent, script_row, caller_memory, "outbound", variables)
        if scheduled:
            schedule.apply_plan(call_agent, schedule.plan_for(job, *inputs, call_agent, caller_memory,
                                                              call_agent.company_name or bot.bot_name))
        prepare_opening(call_agent, variables, bool(compliance.record_calls))
    except Exception as e:
        logger.warning(f"Preparing call {job.id}'s opening ahead failed (the call will make it): {e}")


async def _prepare_known_opening(bot_id: str, caller: Optional[str]) -> None:
    """Someone the assistant knows is calling in. Their opening ("Hello Karthik, ...") can't be made ahead like the
    usual one, so it's made while the phone rings, before the call connects."""
    try:
        caller_memory = await memory.context_for(bot_id, caller)
        if not (caller_memory and caller_memory.get("first_name")):
            return  # the usual opening, made when the agent was saved
        agent, script_row = await asyncio.gather(
            _first(select(VoiceAgent).where(VoiceAgent.bot_id == bot_id)),
            _first(select(VoiceScript).where(VoiceScript.bot_id == bot_id, VoiceScript.direction == "inbound")))
        if agent and agent.remember_callers is not False:
            variables: dict = {}
            call_agent, _ = _for_call(agent, script_row, caller_memory, "inbound", variables)
            prepare_opening(call_agent, variables, bool((await _compliance_for(agent.user_id)).record_calls))
    except Exception as e:
        logger.warning(f"Preparing a known caller's opening failed (the call will make it): {e}")


async def _route_and_run(transport, call_sid: Optional[str], from_raw: Optional[str], to_raw: Optional[str],
                         job_id: Optional[str] = None, voicemail: bool = False, scope=accounts.NIMMI) -> None:
    """
    Work out who a phone call belongs to (callback job or the called number), then run it.
    `scope` is the account the call came in on: a customer's account only reaches its own numbers and calls.
    """
    owner = _owner_of(scope)
    async with async_session() as db:
        job = None
        if job_id:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.id == job_id))).scalars().first()
        if not job and call_sid:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.provider_call_id == call_sid))).scalars().first()
        if job and owner and job.user_id != owner:
            job = None
        variables, number_id = {}, None
        if job:
            owner_id, bot_id, caller, direction, consent = job.user_id, job.bot_id, job.e164, "outbound", job.consent_source
            variables, number_id = _job_variables(job), job.from_number_id
        else:
            called = to_e164(to_raw)
            number = (await db.execute(select(PhoneNumber).where(
                PhoneNumber.e164 == called, PhoneNumber.status == "active",
                PhoneNumber.account_id.is_(None) if owner is None else PhoneNumber.account_id == scope.id,
            ))).scalars().first() if called else None
            if not number or not number.bot_id:
                logger.warning(f"Call to unrouted number {to_raw}")
                await transport.hangup("done")
                return
            owner_id, bot_id, caller, direction, consent = number.user_id, number.bot_id, to_e164(from_raw), "inbound", None
            number_id = number.id

    # Everything else the call needs, fetched side by side on separate connections: the caller is
    # waiting in silence, and each lookup is a round trip to the database.
    campaign_id = job.campaign_id if job else None
    scheduled = job is not None and job.kind in schedule.CALL_KINDS  # a call-back, follow-up or meeting call
    bot, agent, campaign, compliance, settings, script_row, caller_memory, tools, inputs = await asyncio.gather(
        _first(select(Bot).where(Bot.bot_id == bot_id)),
        _first(select(VoiceAgent).where(VoiceAgent.bot_id == bot_id)),
        _first(select(Campaign).where(Campaign.id == campaign_id)) if campaign_id else _nothing(),
        _compliance_for(owner_id),
        assist.workspace(owner_id),
        _first(select(VoiceScript).where(VoiceScript.bot_id == bot_id, VoiceScript.direction == direction)),
        memory.context_for(bot_id, caller),
        schedule.tools_for(owner_id, bot_id, caller, number_id, name=job.name if job else None),
        schedule.plan_inputs(job) if scheduled else _nothing(),
    )
    purpose = campaign.purpose if campaign else None
    if campaign and not number_id:
        number_id = campaign.from_number_id
    if bot and not agent and job and (job.consent_source or "").startswith(TEST_CALL):
        agent = _agent_defaults(bot, owner_id)  # test calls work before voice is switched on
    is_test = bool(job and (job.consent_source or "").startswith(TEST_CALL))
    script = None
    if agent:
        if agent.remember_callers is False:
            caller_memory = None  # switched off: every call starts fresh
        agent, script = _for_call(agent, script_row, caller_memory, direction, variables)
    if not bot or not agent or not (agent.enabled or is_test):
        await transport.hangup("done")
        return
    if scheduled:  # what it's for, its own opening, and the language they spoke last time
        plan = schedule.plan_for(job, *inputs, agent, caller_memory, agent.company_name or bot.bot_name)
        schedule.apply_plan(agent, plan)
        purpose = plan.purpose
    if tools is not None and caller_memory and caller_memory.get("name"):
        tools.name = caller_memory["name"]

    hours = assist.hours_config(settings)
    setup = CallSetup(owner_id=owner_id, bot=bot, agent=agent, direction=direction, channel="phone", caller_e164=caller,
                      consent_source=consent, provider_call_id=call_sid, callback_job_id=job.id if job else None,
                      record=bool(compliance.record_calls), opt_out_phrases=compliance.opt_out_phrases or [],
                      variables=variables, purpose=purpose, campaign_id=job.campaign_id if job else None,
                      voicemail=voicemail, after_hours=None if assist.is_open(hours) else assist.next_open(hours),
                      script=scripts.style(script), caller=caller_memory, number_id=number_id, tools=tools)
    await CallSession(setup, transport).run()


async def _log_unanswered(db: AsyncSession, sid: Optional[str], job_id: Optional[str], status: str, provider: str,
                          owner: Optional[str] = None) -> None:
    """Outbound call that never connected: log it and schedule a retry (or give up)."""
    status = (status or "").lower()
    job = (await db.execute(select(CallbackJob).where(
        or_(CallbackJob.provider_call_id == sid, CallbackJob.id == job_id)
    ))).scalars().first() if (sid or job_id) else None
    if not job or (owner and job.user_id != owner):
        return
    if status == "completed":
        # Twilio reports "completed" the moment the caller hangs up, often before the session has
        # written its log. Only treat it as a non-connect if no session ever started for this call.
        started = (await db.execute(select(CallLog.id).where(CallLog.provider_call_id == sid))).first() if sid else None
        if started or job.call_id:
            return
        # Picked up, but the assistant never connected (e.g. a Twilio trial prompt that wasn't accepted).
        status = "ended before the assistant connected"
    elif status not in ("busy", "no-answer", "failed", "canceled"):
        return
    db.add(CallLog(user_id=job.user_id, bot_id=job.bot_id, direction="outbound", channel="phone", caller_e164=job.e164,
                   outcome="no_answer", consent_source=job.consent_source, provider_call_id=sid, campaign_id=job.campaign_id,
                   summary=f"Call {status.replace('-', ' ')}. Attempt {job.attempts}.", ended_at=datetime.utcnow()))
    if (job.consent_source or "").startswith(TEST_CALL):
        job.status, job.last_error = "failed", f"{provider}: {status}"
    else:
        await scheduler.retry_later(db, job, f"{provider}: {status}")
    await db.commit()
    _email_if_gave_up(job)


def _email_if_gave_up(job: CallbackJob) -> None:
    """No more attempts left: the "couldn't reach them" email, if they gave an email and it's on (calls they asked for:
    not follow-ups or meeting calls)."""
    if job.status == "failed" and not (job.consent_source or "").startswith(TEST_CALL) and job.kind in (None, "callback"):
        from notify import events
        events.fire_and_forget(events.call_missed(job.user_id, job.id, job.e164, {**(job.variables or {}), **({"name": job.name} if job.name else {})}, job.bot_id))


@router.websocket("/ws/exotel/{secret}")
async def exotel_call(ws: WebSocket, secret: str):
    async with async_session() as db:
        scope = await accounts.by_hook(db, "exotel", secret)
    if scope is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    transport = ExotelTransport(ws)
    if not await transport.wait_for_start():
        return
    await _route_and_run(transport, transport.call_sid, transport.from_number, transport.to_number, scope=scope)


@router.get("/exotel/after-bot")
async def exotel_after_bot(secret: str = "", CallSid: str = ""):
    """Exotel Passthru: 200 = transfer (next applet dials), anything else = hang up."""
    await _exotel_scope(secret)
    if CallSid in scheduler.pending_transfers:
        return PlainTextResponse("transfer")
    return Response(status_code=302)


@router.get("/exotel/transfer-target")
async def exotel_transfer_target(secret: str = "", CallSid: str = ""):
    """Exotel Connect applet 'dial number from URL'."""
    await _exotel_scope(secret)
    number = scheduler.pending_transfers.pop(CallSid, None)
    e164 = to_e164(number) if number else None
    if not e164:
        raise HTTPException(status_code=404, detail="No transfer pending")
    return PlainTextResponse(e164)


@router.api_route("/exotel/status", methods=["GET", "POST"])
async def exotel_status(request: Request, secret: str = "", db: AsyncSession = Depends(get_db)):
    """Outbound call status: on busy / no-answer / failed, log it and schedule a retry."""
    scope = await _exotel_scope(secret)
    params = dict(request.query_params)
    if request.method == "POST":
        params.update({k: str(v) for k, v in (await request.form()).items()})
    await _log_unanswered(db, params.get("CallSid"), params.get("CustomField"), params.get("Status") or "", "Exotel",
                          owner=_owner_of(scope))
    return {"status": "ok"}


# ─── Twilio phone calls (testing, and customers outside India) ───
async def _twilio_scope(secret: str, request: Request, form) -> object:
    """
    Which account a Twilio webhook belongs to. For a customer's own account, the request must
    also carry a valid X-Twilio-Signature made with that account's auth token.
    """
    async with async_session() as db:
        scope = await accounts.by_hook(db, "twilio", secret)
    if scope is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    if scope != accounts.NIMMI:
        _, token = accounts.twilio_creds(scope)
    else:
        # Nimmi's own account: the secret in the URL plus Twilio's signature, so a leaked URL alone isn't enough.
        token = os.getenv("TWILIO_AUTH_TOKEN") if os.getenv("TWILIO_VERIFY_SIGNATURES", "true").lower() != "false" else None
    if token:
        url = twilio.public_base() + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        params = {k: str(v) for k, v in form.items()}
        if not twilio.valid_signature(token, url, params, request.headers.get("X-Twilio-Signature", "")):
            logger.warning("Rejected a Twilio webhook with a missing or invalid signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
    return scope


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


@router.post("/twilio/incoming/{secret}")
async def twilio_incoming(secret: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The Twilio number's 'A call comes in' webhook."""
    form = await request.form()
    scope = await _twilio_scope(secret, request, form)
    owner = _owner_of(scope)
    called = to_e164(str(form.get("To") or ""))
    number = (await db.execute(select(PhoneNumber).where(
        PhoneNumber.e164 == called, PhoneNumber.status == "active",
        PhoneNumber.account_id.is_(None) if owner is None else PhoneNumber.account_id == scope.id,
    ))).scalars().first() if called else None
    if not number or not number.bot_id:
        return _xml(twilio.say_and_hangup("Sorry, this number isn't set up yet. Goodbye."))
    fire_and_forget(_prepare_known_opening(number.bot_id, to_e164(str(form.get("From") or ""))))
    return _xml(twilio.connect_twiml({"from": str(form.get("From") or ""), "to": str(form.get("To") or ""),
                                      "direction": "inbound"}, hook=secret))


@router.websocket("/ws/twilio/{secret}")
async def twilio_call(ws: WebSocket, secret: str):
    async with async_session() as db:
        scope = await accounts.by_hook(db, "twilio", secret)
    if scope is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    transport = TwilioTransport(ws)
    if not await transport.wait_for_start():
        return
    p = transport.params
    await _route_and_run(transport, transport.call_sid, p.get("from"), p.get("to"), job_id=p.get("job"),
                         voicemail=p.get("voicemail") == "1", scope=scope)


@router.post("/twilio/outbound/{secret}")
async def twilio_outbound(secret: str, request: Request, job: str = "", db: AsyncSession = Depends(get_db)):
    """Outbound call answered (voicemail detection on): a person gets the assistant; a machine gets the agent's choice."""
    form = await request.form()
    scope = await _twilio_scope(secret, request, form)
    answered_by = str(form.get("AnsweredBy") or "")
    if answered_by not in scheduler.MACHINE:
        return _xml(twilio.connect_twiml({"job": job, "direction": "outbound"}, hook=secret))
    cb = (await db.execute(select(CallbackJob).where(CallbackJob.id == job))).scalars().first() if job else None
    if cb and _owner_of(scope) and cb.user_id != _owner_of(scope):
        cb = None
    agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == cb.bot_id))).scalars().first() if cb else None
    if agent and agent.voicemail_action == "leave_message":
        return _xml(twilio.connect_twiml({"job": job, "direction": "outbound", "voicemail": "1"}, hook=secret))
    if cb:  # hang up and try again later
        db.add(CallLog(user_id=cb.user_id, bot_id=cb.bot_id, direction="outbound", channel="phone", caller_e164=cb.e164,
                       outcome="voicemail", consent_source=cb.consent_source, provider_call_id=str(form.get("CallSid") or ""),
                       campaign_id=cb.campaign_id, summary=f"Reached voicemail. Hung up without a message. Attempt {cb.attempts}.",
                       ended_at=datetime.utcnow()))
        await scheduler.retry_later(db, cb, "Reached voicemail")
        await db.commit()
        _email_if_gave_up(cb)
    return _xml(twilio.hangup_twiml())


@router.post("/twilio/whisper/{secret}")
async def twilio_whisper(secret: str, request: Request, call: str = ""):
    """Played to the person taking a warm transfer, before the caller is connected."""
    await _twilio_scope(secret, request, await request.form())
    brief = scheduler.pending_whispers.pop(call, "") if call else ""
    return _xml(twilio.whisper_twiml(brief or "The caller is being connected now."))


@router.post("/twilio/after/{secret}")
async def twilio_after(secret: str, request: Request):
    """<Connect action>: the stream ended. Transfer if the assistant asked to, otherwise hang up."""
    form = await request.form()
    await _twilio_scope(secret, request, form)
    sid = str(form.get("CallSid") or "")
    number = scheduler.pending_transfers.pop(sid, None)
    e164 = to_e164(number) if number else None
    if not e164:
        return _xml(twilio.hangup_twiml())
    return _xml(twilio.dial_twiml(e164, whisper_call=sid if sid in scheduler.pending_whispers else "", hook=secret))


@router.post("/twilio/status/{secret}")
async def twilio_status(secret: str, request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    scope = await _twilio_scope(secret, request, form)
    await _log_unanswered(db, str(form.get("CallSid") or ""), None, str(form.get("CallStatus") or ""), "Twilio",
                          owner=_owner_of(scope))
    return {"status": "ok"}


async def _place(db: AsyncSession, number: PhoneNumber, to: str, job_id: str) -> str:
    return await accounts.dial(db, number, to, job_id)


async def _publicly_reachable() -> bool:
    """Twilio/Exotel fetch the call's instructions from PUBLIC_BACKEND_URL when it's answered; if that address is
    dead (an expired tunnel), the call drops a second or two after pick-up with nothing said."""
    base = twilio.public_base()
    if os.getenv("VOICE_CHECK_PUBLIC_URL", "true").lower() == "false":
        return True  # the test suite (its public URL is a placeholder)
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            return (await client.get(f"{base}/")).status_code < 500
    except httpx.HTTPError:
        return False


class TestCallRequest(BaseModel):
    bot_id: str
    phone: str


@router.post("/test-call")
async def test_call(req: TestCallRequest, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Ring your own phone from one of your numbers and talk to the assistant (uses credits)."""
    await plans.require(db, ctx.owner_id, "voice")
    rate_limit(f"testcall-try:{ctx.owner_id}", 20, 600)
    bot = await get_owned_bot(req.bot_id, ctx, db)
    e164 = to_e164(req.phone)
    if not e164:
        raise HTTPException(status_code=400, detail="Enter a valid phone number, with the country code for non-Indian numbers")
    if not callable_destination(e164):
        raise HTTPException(status_code=400, detail="We can't place calls to that country")
    numbers = (await db.execute(select(PhoneNumber).where(
        PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active", PhoneNumber.e164.is_not(None)
    ))).scalars().all()
    number = None
    for n in numbers:
        if accounts.usable(n, await accounts.account_of(db, n)):
            number = n
            break
    if not number:
        raise HTTPException(status_code=400, detail="You need an active phone number to place a test call")
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    wallet = await metering.get_wallet(db, ctx.owner_id)
    if not metering.enough_for_a_call(metering.credits_left(wallet), ai_models.per_minute(ai_models.call_model(agent.ai_model))):
        raise HTTPException(status_code=402, detail="You're out of voice credits. Buy credits on the Voice page to keep testing.")
    if not await _publicly_reachable():
        raise HTTPException(status_code=503, detail="The phone company can't reach this server right now, so the call would "
                                                    "drop as soon as you answer. Check PUBLIC_BACKEND_URL (or restart the tunnel) and try again.")
    # Only calls actually placed count here: one that couldn't be (no tunnel, no number) mustn't lock you out
    # while you fix it.
    rate_limit(f"testcall:{ctx.owner_id}", 5, 600)
    # Make the opening while the phone rings, so the assistant speaks the moment it's answered.
    script_row = (await db.execute(select(VoiceScript).where(
        VoiceScript.bot_id == bot.bot_id, VoiceScript.direction == "outbound"))).scalars().first()
    variables: dict = {}
    known = await memory.context_for(bot.bot_id, e164) if agent.remember_callers is not False else None
    call_agent, _ = _for_call(agent, script_row, known, "outbound", variables)
    prepare_opening(call_agent, variables, bool((await _compliance(ctx.owner_id, db)).record_calls))
    job = CallbackJob(user_id=ctx.owner_id, bot_id=bot.bot_id, e164=e164, consent_source=f"{TEST_CALL} for {display(e164)}",
                      status="calling", attempts=1)
    db.add(job)
    await db.commit()
    try:
        job.provider_call_id = await _place(db, number, e164, job.id)
    except Exception as e:
        job.status, job.last_error = "failed", str(e)[:300]
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Couldn't place the call: {e}")
    await db.commit()
    return {"status": "calling", "from": number.number, "to": display(e164)}


# ─── calls ────────────────────────────────────────────────────────
@router.get("/calls")
async def list_calls(direction: Optional[str] = None, outcome: Optional[str] = None, limit: int = 200,
                     ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    q = select(CallLog).where(CallLog.user_id == ctx.owner_id)
    if direction in ("inbound", "outbound"):
        q = q.where(CallLog.direction == direction, CallLog.channel == "phone")
    if outcome:
        q = q.where(CallLog.outcome == outcome)
    calls = (await db.execute(q.order_by(CallLog.started_at.desc()).limit(min(limit, 500)))).scalars().all()
    names = await _bot_names(ctx.owner_id, db)
    return [_call_json(c, names) for c in calls]


@router.get("/calls/{call_id}")
async def get_call(call_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    call = (await db.execute(select(CallLog).where(CallLog.id == call_id, CallLog.user_id == ctx.owner_id))).scalars().first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    data = _call_json(call, await _bot_names(ctx.owner_id, db), full=True)
    data["recording_url"] = None
    if call.recording_path:
        signed = await recording.signed_url(call.recording_path)
        data["recording_url"] = signed or f"/api/voice/calls/{call.id}/recording?token={issue_scoped_token(call.id, 'recording', 900)}"
    return data


@router.get("/calls/{call_id}/recording")
async def call_recording(call_id: str, token: str = "", db: AsyncSession = Depends(get_db)):
    if decode_scoped_token(token, "recording") != call_id:
        raise HTTPException(status_code=403, detail="This link has expired")
    call = (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()
    path = recording.local_path(call.recording_path) if call and call.recording_path else None
    if path:
        return FileResponse(path, media_type="audio/wav")
    signed = await recording.signed_url(call.recording_path) if call and call.recording_path else None
    if signed:
        return RedirectResponse(signed)
    raise HTTPException(status_code=404, detail="Recording not found")


# ─── numbers ──────────────────────────────────────────────────────
def _number_json(n: PhoneNumber) -> dict:
    own = bool(n.account_id)
    replace_open = (not own and n.provider == "twilio" and bool(n.provider_sid) and n.status == "active"
                    and (n.replaced_at is None or datetime.utcnow() - n.replaced_at.replace(tzinfo=None) > timedelta(days=30)))
    return {"id": n.id, "number": n.number, "kind": n.kind, "city": n.city, "status": n.status, "bot_id": n.bot_id,
            "monthly_fee": n.monthly_fee, "provider": n.provider, "country": n.country,
            "next_charge_at": n.next_charge_at.isoformat() if n.next_charge_at else None,
            "documents": [d.get("kind") for d in (n.kyc_documents or [])],
            "source": "own" if own else "nimmi", "account_id": n.account_id, "can_replace": replace_open}


async def _ops_email(subject: str, body: str) -> None:
    ops = os.getenv("OPS_EMAIL")
    if ops:
        await send_email(ops, subject, body)


@router.get("/numbers")
async def list_numbers(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PhoneNumber).where(PhoneNumber.user_id == ctx.owner_id).order_by(PhoneNumber.created_at)
    )).scalars().all()
    return [_number_json(n) for n in rows]


class NumberRequest(BaseModel):
    city: str


@router.post("/numbers")
async def request_number(req: NumberRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "voice")
    if req.city not in catalog.CITIES:
        raise HTTPException(status_code=400, detail="Choose a city from the list")
    open_requests = (await db.execute(select(func.count()).select_from(PhoneNumber).where(
        PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status != "active"))).scalar_one()
    if open_requests >= 3:
        raise HTTPException(status_code=400, detail="You already have number requests in progress")
    number = PhoneNumber(user_id=ctx.owner_id, number=f"New {req.city} number", city=req.city, status="pending_kyc",
                         monthly_fee=catalog.NUMBER_MONTHLY_FEE)
    db.add(number)
    await db.commit()
    await _ops_email("Nimmi: phone number requested", f"Workspace {ctx.owner_id} requested a {req.city} number ({number.id}).")
    return _number_json(number)


@router.patch("/numbers/{number_id}")
async def route_number(number_id: str, data: dict, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    number = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.user_id == ctx.owner_id))).scalars().first()
    if not number:
        raise HTTPException(status_code=404, detail="Number not found")
    if number.status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="This number isn't active yet")
    bot_id = data.get("bot_id")
    if bot_id:
        await get_owned_bot(bot_id, ctx, db)
    number.bot_id = bot_id or None
    await db.commit()
    return _number_json(number)


@router.delete("/numbers/{number_id}")
async def cancel_number(number_id: str, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    number = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.user_id == ctx.owner_id))).scalars().first()
    if not number:
        raise HTTPException(status_code=404, detail="Number not found")
    if number.account_id:
        # The customer's own number: never release it, just give back the webhook it had before.
        acc = await accounts.account_of(db, number)
        if acc and number.provider == "twilio" and number.provider_sid:
            try:
                await twilio.set_voice_url(number.provider_sid, number.previous_voice_url or "", accounts.twilio_creds(acc))
            except Exception as e:
                logger.warning(f"Couldn't restore the webhook for {number.number}: {e}")
    elif number.provider == "twilio" and number.provider_sid:
        try:
            await twilio.release_number(number.provider_sid)  # stop paying Twilio for it
        except twilio.TwilioError as e:
            raise HTTPException(status_code=502, detail=f"Couldn't release the number: {e}")
    await db.delete(number)
    await db.commit()
    if number.status == "active" and number.provider != "twilio" and not number.account_id:
        await _ops_email("Nimmi: number released", f"Workspace {ctx.owner_id} released {number.number} ({number.id}).")
    return {"status": "deleted"}


KYC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "kyc")
KYC_TYPES = {"application/pdf", "image/png", "image/jpeg"}


@router.post("/numbers/{number_id}/documents")
async def upload_documents(number_id: str, kind: str = Form(...), file: UploadFile = File(...),
                           ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Certificate of Incorporation (kind=coi) and GST certificate (kind=gst), kept private."""
    if kind not in ("coi", "gst"):
        raise HTTPException(status_code=400, detail="Upload the Certificate of Incorporation or the GST certificate")
    if file.content_type not in KYC_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PDF, PNG or JPG")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Documents must be 10 MB or smaller")
    number = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.user_id == ctx.owner_id))).scalars().first()
    if not number:
        raise HTTPException(status_code=404, detail="Number not found")
    folder = os.path.join(KYC_DIR, number.id)
    os.makedirs(folder, exist_ok=True)
    ext = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}[file.content_type]
    await asyncio.to_thread(lambda: open(os.path.join(folder, kind + ext), "wb").write(content))
    docs = [d for d in (number.kyc_documents or []) if d.get("kind") != kind] + [{"kind": kind, "file": kind + ext}]
    number.kyc_documents = docs
    if {d["kind"] for d in docs} >= {"coi", "gst"} and number.status == "pending_kyc":
        number.status = "provisioning"
        await _ops_email("Nimmi: KYC documents ready", f"Number request {number.id} ({number.city}) has both documents.")
    await db.commit()
    return _number_json(number)


class ActivateNumber(BaseModel):
    e164: str
    display: Optional[str] = None
    provider: str = "exotel"  # exotel or twilio


@router.post("/admin/numbers/{number_id}/activate")
async def admin_activate_number(number_id: str, data: ActivateNumber, request: Request, db: AsyncSession = Depends(get_db)):
    """Ops: after provisioning the ExoPhone in Exotel, attach it to the request."""
    key = os.getenv("ADMIN_API_KEY")
    if key and len(key) < 24 and is_production():
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is too short. Use at least 24 random characters.")
    if not key or not hmac.compare_digest(request.headers.get("x-admin-key", ""), key):
        raise HTTPException(status_code=403, detail="Forbidden")
    number = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id))).scalars().first()
    e164 = to_e164(data.e164)
    if not number or not e164:
        raise HTTPException(status_code=400, detail="Unknown request or invalid number")
    if data.provider not in ("exotel", "twilio"):
        raise HTTPException(status_code=400, detail="Provider must be exotel or twilio")
    number.e164, number.number, number.status, number.provider = e164, data.display or display(e164), "active", data.provider
    if data.provider == "twilio" and twilio.configured():
        try:
            await twilio.point_number_here(e164)  # route the number's incoming calls to us
        except Exception as e:
            logger.warning(f"Couldn't set the Twilio webhook for {e164}: {e}")
    await db.commit()
    return _number_json(number)


# ─── callbacks ────────────────────────────────────────────────────
class CallbackUpdate(BaseModel):
    enabled: bool
    delay: str
    window_start: str
    window_end: str
    max_attempts: int = Field(2, ge=1, le=3)
    from_number_id: Optional[str] = None


_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _callback_json(c: CallbackSettings) -> dict:
    return {"enabled": bool(c.enabled), "delay": c.delay, "window_start": c.window_start, "window_end": c.window_end,
            "max_attempts": c.max_attempts, "from_number_id": c.from_number_id}


@router.get("/callbacks")
async def get_callbacks(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    data = _callback_json(await _callbacks(ctx.owner_id, db))
    active = (await db.execute(select(PhoneNumber.id).where(
        PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active"
    ).order_by(PhoneNumber.created_at))).scalars().all()
    if data["from_number_id"] not in active:
        # Nothing chosen yet (or that number is gone): suggest the first active one.
        data["from_number_id"] = active[0] if active else None
    return data


@router.put("/callbacks")
async def update_callbacks(data: CallbackUpdate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    if data.enabled:
        await plans.require(db, ctx.owner_id, "voice")
    if data.delay not in scheduler.DELAYS:
        raise HTTPException(status_code=400, detail="Unknown delay")
    if not (_TIME.match(data.window_start) and _TIME.match(data.window_end)):
        raise HTTPException(status_code=400, detail="Use 24-hour times like 09:00")
    if data.enabled:
        number = (await db.execute(select(PhoneNumber).where(
            PhoneNumber.id == data.from_number_id, PhoneNumber.user_id == ctx.owner_id, PhoneNumber.status == "active"
        ))).scalars().first() if data.from_number_id else None
        if not number:
            raise HTTPException(status_code=400, detail="Choose an active number to call from")
    settings = (await db.execute(select(CallbackSettings).where(CallbackSettings.user_id == ctx.owner_id))).scalars().first()
    if not settings:
        settings = CallbackSettings(user_id=ctx.owner_id)
        db.add(settings)
    for field, value in data.model_dump().items():
        setattr(settings, field, value)
    await db.commit()
    return _callback_json(settings)


@router.get("/callbacks/jobs")
async def callback_jobs(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    jobs = (await db.execute(select(CallbackJob).where(CallbackJob.user_id == ctx.owner_id, CallbackJob.campaign_id.is_(None))
                             .order_by(CallbackJob.created_at.desc()).limit(50))).scalars().all()
    return [{"id": j.id, "number": mask(j.e164), "name": j.name, "status": j.status, "attempts": j.attempts,
             "next_attempt_at": j.next_attempt_at.isoformat() if j.next_attempt_at else None,
             "last_error": j.last_error, "call_id": j.call_id, "created_at": j.created_at.isoformat() if j.created_at else None}
            for j in jobs]


class CallbackRequest(BaseModel):
    bot_id: str
    phone: str
    consent: bool
    name: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/callbacks/request")
async def request_callback(req: CallbackRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Public, called by the chat widget when a visitor ticks 'call me back'."""
    rate_limit(f"cbreq:{client_ip(request)}", 5, 600)
    if not req.consent:
        raise HTTPException(status_code=400, detail="We can only call if you agree to a callback")
    e164 = to_e164(req.phone)
    if not e164 or not callable_destination(e164):
        raise HTTPException(status_code=400, detail="Enter a valid phone number")
    rate_limit(f"cbreq-num:{e164}", 3, 3600)
    bot = (await db.execute(select(Bot).where(Bot.bot_id == req.bot_id))).scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Assistant not found")
    settings = await _callbacks(bot.user_id, db)
    if not settings.enabled:
        raise HTTPException(status_code=409, detail="Callbacks aren't available right now")
    blocked = (await db.execute(select(DncEntry.id).where(DncEntry.user_id == bot.user_id, DncEntry.e164 == e164))).first()
    if blocked:
        return {"status": "queued"}  # don't reveal the list; the scheduler will never dial it
    recent = (await db.execute(select(CallbackJob.id).where(
        CallbackJob.user_id == bot.user_id, CallbackJob.e164 == e164, CallbackJob.status.in_(["queued", "calling"])
    ))).first()
    if recent:
        return {"status": "queued"}
    now = datetime.utcnow()
    # Their email from the chat, so we can write if the call never gets through.
    conv = (await db.execute(select(Conversation).where(
        Conversation.bot_id == bot.bot_id, Conversation.visitor_session_id == req.session_id,
    ).order_by(Conversation.created_at.desc()))).scalars().first() if req.session_id else None
    address = extract_contact(conv.captured_data or {}).get("email") if conv else None
    db.add(CallbackJob(
        user_id=bot.user_id, bot_id=bot.bot_id, e164=e164, name=(req.name or "")[:80] or None,
        consent_source=f"Asked for a callback in the {bot.bot_name} chat on {now:%d %b %Y at %H:%M} UTC",
        next_attempt_at=now + timedelta(seconds=scheduler.DELAYS.get(settings.delay, 60)),
        variables={"email": address} if address else None,
    ))
    await db.commit()
    return {"status": "queued"}


# ─── compliance, do-not-call, erase ───────────────────────────────
class ComplianceUpdate(BaseModel):
    record_calls: bool
    retention_days: int
    opt_out_phrases: list[str]


@router.get("/compliance")
async def get_compliance(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _compliance(ctx.owner_id, db)
    return {"disclosure_enabled": True, "record_calls": bool(c.record_calls), "retention_days": c.retention_days,
            "opt_out_phrases": c.opt_out_phrases or []}


@router.put("/compliance")
async def update_compliance(data: ComplianceUpdate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    if data.retention_days not in (30, 90, 180):
        raise HTTPException(status_code=400, detail="Retention must be 30, 90 or 180 days")
    c = (await db.execute(select(ComplianceSettings).where(ComplianceSettings.user_id == ctx.owner_id))).scalars().first()
    if not c:
        c = ComplianceSettings(user_id=ctx.owner_id)
        db.add(c)
    c.record_calls = data.record_calls
    c.retention_days = data.retention_days
    c.opt_out_phrases = [p.strip().lower()[:60] for p in data.opt_out_phrases if p.strip()][:30]
    await db.commit()
    return {"disclosure_enabled": True, "record_calls": c.record_calls, "retention_days": c.retention_days,
            "opt_out_phrases": c.opt_out_phrases}


def _dnc_json(d: DncEntry) -> dict:
    return {"id": d.id, "number": display(d.e164), "reason": d.reason, "added_at": d.added_at.isoformat() if d.added_at else None}


@router.get("/dnc")
async def list_dnc(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(DncEntry).where(DncEntry.user_id == ctx.owner_id).order_by(DncEntry.added_at.desc()))).scalars().all()
    return [_dnc_json(d) for d in rows]


class DncAdd(BaseModel):
    number: Optional[str] = None
    call_id: Optional[str] = None


@router.post("/dnc")
async def add_dnc(data: DncAdd, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    e164 = to_e164(data.number) if data.number else None
    if data.call_id and not e164:
        call = (await db.execute(select(CallLog).where(CallLog.id == data.call_id, CallLog.user_id == ctx.owner_id))).scalars().first()
        e164 = call.caller_e164 if call else None
    if not e164:
        raise HTTPException(status_code=400, detail="Enter a valid phone number")
    entry = DncEntry(user_id=ctx.owner_id, e164=e164, reason="manual")
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        entry = (await db.execute(select(DncEntry).where(DncEntry.user_id == ctx.owner_id, DncEntry.e164 == e164))).scalars().first()
    await db.execute(sa_delete(CallbackJob).where(CallbackJob.user_id == ctx.owner_id, CallbackJob.e164 == e164,
                                                  CallbackJob.status == "queued"))
    await db.commit()
    return _dnc_json(entry)


@router.delete("/dnc/{entry_id}")
async def remove_dnc(entry_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    entry = (await db.execute(select(DncEntry).where(DncEntry.id == entry_id, DncEntry.user_id == ctx.owner_id))).scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail="Not on the list")
    await db.delete(entry)
    await db.commit()
    return {"status": "removed"}


class EraseRequest(BaseModel):
    number: str


@router.post("/erase")
async def erase_caller(data: EraseRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """DPDP erasure: delete a caller's calls, recordings, transcripts and callback requests."""
    e164 = to_e164(data.number)
    if not e164:
        raise HTTPException(status_code=400, detail="Enter a valid phone number")
    calls = (await db.execute(select(CallLog).where(CallLog.user_id == ctx.owner_id, CallLog.caller_e164 == e164))).scalars().all()
    for call in calls:
        try:
            await recording.delete(call.recording_path)
        except Exception as e:
            logger.warning(f"Erase: recording delete failed for {call.id}: {e}")
        await db.delete(call)
    await db.execute(sa_delete(CallbackJob).where(CallbackJob.user_id == ctx.owner_id, CallbackJob.e164 == e164))
    await db.execute(sa_delete(Meeting).where(Meeting.user_id == ctx.owner_id, Meeting.e164 == e164))
    await db.execute(sa_delete(Contact).where(Contact.user_id == ctx.owner_id, Contact.e164 == e164))

    # Chat leads that captured the same number.
    bot_ids = list((await _bot_names(ctx.owner_id, db)).keys())
    convs = (await db.execute(select(Conversation).where(Conversation.bot_id.in_(bot_ids)))).scalars().all() if bot_ids else []
    chats = [c for c in convs if extract_contact(c.captured_data).get("phone") == e164]
    for conv in chats:
        await db.delete(conv)
    # WhatsApp chats with the number, and the files kept from them.
    from backend.models import WhatsAppChat, WhatsAppMessage
    from whatsapp import storage as whatsapp_storage
    wa_chats = (await db.execute(select(WhatsAppChat).where(
        WhatsAppChat.user_id == ctx.owner_id, WhatsAppChat.wa_id == e164.lstrip("+")))).scalars().all()
    for wa_chat in wa_chats:
        for media in (await db.execute(select(WhatsAppMessage.media).where(WhatsAppMessage.chat_id == wa_chat.id))).scalars().all():
            if (media or {}).get("stored") and not (media or {}).get("file_id"):  # not the business's own Files
                await whatsapp_storage.delete(media["stored"])
        if wa_chat.conversation_id:
            conv = await db.get(Conversation, wa_chat.conversation_id)
            if conv is not None and conv not in chats:
                await db.delete(conv)
                chats.append(conv)
        await db.execute(sa_delete(WhatsAppMessage).where(WhatsAppMessage.chat_id == wa_chat.id))
        await db.delete(wa_chat)
    await db.commit()

    db.add(DncEntry(user_id=ctx.owner_id, e164=e164, reason="caller_request"))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # already on the list
    return {"status": "erased", "calls_deleted": len(calls), "chats_deleted": len(chats)}


@router.get("/packs")
async def packs():
    return catalog.PACKS


def _rate_card() -> dict:
    return {"base_credits": ai_models.BASE_CREDITS, "billing_step_sec": catalog.BILLING_STEP_SEC,
            "free_credits": catalog.FREE_CREDITS, "groups": ai_models.GROUPS, "packs": catalog.PACKS}


@router.get("/models")
async def list_ai_models(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The AI models an agent can use: what a call minute costs on each, how fast it starts answering, and how
    long the workspace's credits last on it."""
    left = metering.credits_left(await metering.get_wallet(db, ctx.owner_id))
    return {**_rate_card(), "credits_left": left, "default": ai_models.DEFAULT,
            "models": [ai_models.public(m, left) for m in ai_models.AI_MODELS]}


@router.get("/rates")
async def rates():
    """The public rate card (the website's pricing): what a call minute costs on each model that's set up."""
    return {**_rate_card(), "models": [ai_models.public(m) for m in ai_models.AI_MODELS if ai_models.available(m)]}


class FunctionTest(BaseModel):
    function: dict
    arguments: dict = Field(default_factory=dict)
    direction: Optional[str] = None


@router.post("/agents/{bot_id}/functions/test")
async def test_function(bot_id: str, req: FunctionTest, ctx: AuthContext = Depends(require_manager),
                        db: AsyncSession = Depends(get_db)):
    """Run one of the agent's functions with sample arguments, as it would run on a call (the Test button)."""
    rate_limit(f"fntest:{ctx.owner_id}", 30, 600)
    bot = await get_owned_bot(bot_id, ctx, db)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    try:
        fn = functions.clean([req.function], scripts.for_direction(agent, _direction(req.direction)).functions)[0]
    except functions.FunctionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    started = time.monotonic()
    result = await functions.run(fn, req.arguments, functions.test_variables())
    return {"result": result, "ms": int((time.monotonic() - started) * 1000)}


# From the caller stopping to the agent's first sound, apart from the model: the transcript and the first audio
# (measured on a 4-minute test call, Oct 2026).
REPLY_OVERHEAD_SEC = 0.35


@router.get("/agents/{bot_id}/details")
async def agent_details(bot_id: str, direction: Optional[str] = None, ctx: AuthContext = Depends(get_ctx),
                        db: AsyncSession = Depends(get_db)):
    """The agent page's summary line: what a call minute costs, how quickly it replies (measured on its recent calls,
    or expected from its model), and how long the instructions are that go with every answer."""
    direction = _direction(direction)
    bot = await get_owned_bot(bot_id, ctx, db)
    agent, _ = await _agent_for(bot, ctx.owner_id, db)
    script_row = (await db.execute(select(VoiceScript).where(
        VoiceScript.bot_id == bot.bot_id, VoiceScript.direction == direction))).scalars().first()
    call_agent, script = _for_call(agent, script_row, None, direction, {})
    model = ai_models.call_model(call_agent.ai_model)
    prompt = llm.system_prompt(call_agent, bot, await llm.call_knowledge(bot), direction, None,
                               script=scripts.style(script), phone_known=True)
    recent = (await db.execute(select(CallLog.reply_ms).where(
        CallLog.bot_id == bot.bot_id, CallLog.direction == direction, CallLog.reply_ms.is_not(None))
        .order_by(CallLog.started_at.desc()).limit(20))).scalars().all()
    return {"model": ai_models.public(model), "credits_per_minute": ai_models.per_minute(model),
            "base_credits": ai_models.BASE_CREDITS, "prompt_tokens": -(-len(prompt) // 4),
            "reply_sec_expected": round(model.first_words + REPLY_OVERHEAD_SEC, 2) if model.first_words else None,
            "reply_sec_measured": round(statistics.median(recent) / 1000, 2) if recent else None, "calls_measured": len(recent)}
