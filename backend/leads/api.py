"""
The Leads section (/api/crm): Needs attention, All leads, one lead, tasks, outcomes, each assistant's rules, reports. Owners and admins reach every lead in their
workspace; an agent reaches only those given to them, and assigning, settings and export need a manager.
"""
import csv
import io
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, get_ctx, get_owned_bot, rate_limit, require_manager
from backend.models import Contact, LeadDeal, LeadEvent, LeadPromise, LeadTask, NotificationLog
from database import get_db
from leads import contact as reach, core, promises, quality
from mail import journeys
from mail.broadcasts_api import EMAIL_HEADERS, IMPORT_BYTES, IMPORT_ROWS, NAME_HEADERS, PHONE_HEADERS, TAG_HEADERS, _pick, _rows
from notify import automations
from phone import display, to_e164
from voice.schedule import stored

router = APIRouter(prefix="/api/crm", tags=["leads"])
LIST_LIMIT = 100
EXPORT_LIMIT = 5000


def _when(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="That date doesn't look right")
    return stored(at) if at.tzinfo else at


async def _lead(contact_id: str, ctx: AuthContext, db: AsyncSession) -> Contact:
    c = (await db.execute(select(Contact).where(Contact.id == contact_id, *core.visible(ctx)))).scalars().first()
    if c is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return c


async def _task(task_id: str, ctx: AuthContext, db: AsyncSession) -> LeadTask:
    t = (await db.execute(select(LeadTask).join(Contact, Contact.id == LeadTask.contact_id).where(LeadTask.id == task_id, *core.visible(ctx)))).scalars().first()
    if t is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


def _filtered(ctx: AuthContext, q: str, stage: str, owner: str, source: str, bot_id: str, status: str, due: str, quality: str = "") -> list:
    where = core.visible(ctx) + [Contact.quality == "junk" if quality == "junk" else or_(Contact.quality.is_(None), Contact.quality != "junk")]
    if q.strip():
        like = f"%{q.strip().lower()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        where.append(or_(func.lower(Contact.name).like(like), func.lower(Contact.email).like(like), *([Contact.e164.like(f"%{digits}%")] if len(digits) >= 3 else [])))
    if stage:
        where.append(or_(Contact.stage == stage, Contact.stage.is_(None)) if stage == "new" else Contact.stage == stage)
    if owner == "me":
        where.append(Contact.assigned_to == ctx.user_id)
    elif owner == "nobody":
        where.append(Contact.assigned_to.is_(None))
    elif owner:
        where.append(Contact.assigned_to == owner)
    if source:
        where.append(Contact.source == source)
    if bot_id:
        where.append(Contact.bot_id == bot_id)
    if status:
        where.append(Contact.lead_status == status)
    has_open = select(LeadTask.id).where(LeadTask.contact_id == Contact.id, LeadTask.status == "open")
    if due == "overdue":
        where.append(has_open.where(LeadTask.due_at < core.now()).exists())
    elif due == "none":
        where.append(~has_open.exists())
    return where


@router.get("/queues")
async def queues(bot_id: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return await core.queues(db, ctx, bot_id or None)


@router.get("/leads")
async def list_leads(q: str = "", stage: str = "", owner: str = "", source: str = "", bot_id: str = "", status: str = "", due: str = "", quality: str = "", offset: int = 0, limit: int = 50,
                     ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Every lead the person may reach, newest enquiry first. Junk is left out unless asked for: quality=junk."""
    where = _filtered(ctx, q, stage, owner, source, bot_id, status, due, quality)
    total = (await db.execute(select(func.count()).select_from(Contact).where(*where))).scalar_one()
    rows = (await db.execute(select(Contact).where(*where).order_by(func.coalesce(Contact.last_enquiry_at, Contact.created_at).desc()).offset(max(offset, 0)).limit(min(max(limit, 1), LIST_LIMIT)))).scalars().all()
    people, bots = await core.names_of(db, ctx.owner_id)
    tasks = await core.next_tasks(db, [c.id for c in rows])
    sources = [s for (s,) in (await db.execute(select(Contact.source).where(Contact.user_id == ctx.owner_id, Contact.source.isnot(None)).distinct().limit(50))).all()]
    junk = (await db.execute(select(func.count()).select_from(Contact).where(*core.visible(ctx), Contact.quality == "junk"))).scalar_one()
    return {"items": [core.lead_json(c, tasks.get(c.id), people, bots) for c in rows], "total": total, "junk": junk, "stages": list(journeys.STAGES), "sources": sorted(sources),
            "team": [{"id": p["id"], "name": p["name"]} for p in await core.team(db, ctx.owner_id)], "bots": [{"id": k, "name": v} for k, v in bots.items()], "lost_reasons": list(core.LOST_REASONS)}


def _cell(value) -> str:
    """Names and tags come from strangers: a cell starting with these runs as a formula in a spreadsheet."""
    text = str(value or "")
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/leads/export")
async def export(q: str = "", stage: str = "", owner: str = "", source: str = "", bot_id: str = "", status: str = "", due: str = "", quality: str = "",
                 ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rate_limit(f"leads-export:{ctx.user_id}", 10, 3600)
    rows = (await db.execute(select(Contact).where(*_filtered(ctx, q, stage, owner, source, bot_id, status, due, quality)).order_by(Contact.created_at.desc()).limit(EXPORT_LIMIT))).scalars().all()
    people, bots = await core.names_of(db, ctx.owner_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Phone", "Email", "Stage", "Status", "Looked after by", "Source", "Assistant", "Came in", "Tags"])
    for c in rows:
        w.writerow([_cell(c.name), display(c.e164) if c.e164 else "", _cell(c.email), c.stage or "new", c.lead_status or "", _cell(people.get(c.assigned_to)), _cell(c.source), _cell(bots.get(c.bot_id)),
                    core.iso(c.created_at) or "", _cell(", ".join(c.tags or []))])
    db.add(NotificationLog(user_id=ctx.owner_id, kind="leads_export", ref_id=f"{ctx.user_id}:{core.now().isoformat()}", status="sent", error=f"{len(rows)} leads"))  # who took a copy, and when
    await db.commit()
    return Response(content=out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nimmi-leads.csv"'})


class NewLead(BaseModel):
    bot_id: str = Field(..., max_length=36)
    name: str = Field("", max_length=80)
    phone: str = Field("", max_length=30)
    email: str = Field("", max_length=120)
    note: str = Field("", max_length=1000)


@router.post("/leads")
async def add_lead(data: NewLead, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Someone who rang or walked in: the team adds them by hand. Nobody is contacted automatically."""
    bot = await get_owned_bot(data.bot_id, ctx, db)
    e164 = to_e164(data.phone) if data.phone.strip() else None
    address = data.email.strip()
    if data.phone.strip() and not e164:
        raise HTTPException(status_code=400, detail="Check the phone number")
    if address and not automations.EMAIL_RE.fullmatch(address):
        raise HTTPException(status_code=400, detail="Check the email address")
    if not (e164 or address):
        raise HTTPException(status_code=400, detail="Add a phone number or an email")
    found = await journeys.find_contact(db, bot.bot_id, e164, address or None)
    if found is not None:
        raise HTTPException(status_code=409, detail="This person is already a lead")
    contact = Contact(user_id=bot.user_id, bot_id=bot.bot_id, e164=e164, email=address or None, name=data.name.strip() or None, details={}, calls=0, source="manual", assigned_to=ctx.user_id if ctx.role == "agent" else None)
    db.add(contact)
    await db.flush()
    if data.note.strip():
        contact.notes = data.note.strip()
    await db.commit()
    await core.came_in(ctx.owner_id, contact.id, "Added by the team", contact.id, data.note.strip() or None)
    return {"id": contact.id}


@router.get("/leads/{contact_id}")
async def one_lead(contact_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    if await promises.settle_contact(db, c):  # what's been done since the last look shows at once, not a couple of minutes later
        await db.commit()
    people, bots = await core.names_of(db, ctx.owner_id)
    tasks = await core.open_tasks(db, c.id)
    deals = (await db.execute(select(LeadDeal).where(LeadDeal.contact_id == c.id).order_by(LeadDeal.closed_at.desc()))).scalars().all()
    left = None
    if c.last_enquiry_at:  # TRAI: an enquiry kept in writing lets you contact them for seven days
        left = 7 - (core.now() - c.last_enquiry_at.replace(tzinfo=None)).days
    why_junk = (await db.execute(select(LeadEvent.text).where(LeadEvent.contact_id == c.id, LeadEvent.kind == "junk").order_by(LeadEvent.at.desc()).limit(1))).scalar_one_or_none() \
        if c.quality == "junk" else None
    return {**core.lead_json(c, tasks[0] if tasks else None, people, bots), "notes": c.notes or "", "details": c.details or {}, "brief": c.brief, "lead_reason": c.lead_reason, "tasks": [core.task_json(t, people) for t in tasks],
            "deals": [{"id": d.id, "outcome": d.outcome, "amount": d.amount, "currency": d.currency, "reason": d.reason, "source": d.source, "closed_at": core.iso(d.closed_at), "by": people.get(d.by),
                       "reopened": d.reopened_at is not None} for d in deals],
            "timeline": await core.timeline(db, c, people), "enquiry_days_left": max(left, 0) if left is not None else None, "team": [{"id": p["id"], "name": p["name"]} for p in await core.team(db, ctx.owner_id)],
            "stages": list(journeys.STAGES), "lost_reasons": list(core.LOST_REASONS), "results": core.RESULTS, "kinds": list(core.KINDS), "can_assign": ctx.role != "agent",
            "junk_reason": why_junk, "reach": await reach.overview(db, c), "permissions": await reach.permissions_of(db, c.id),
            "promises": await promises.of_contact(db, c.id, people), "promise_kinds": promises.KINDS, "promise_how": promises.HOW}


class PermissionIn(BaseModel):
    channel: str = Field(..., max_length=10)
    state: str = Field(..., max_length=10)
    words: Optional[str] = Field(None, max_length=300)


@router.post("/leads/{contact_id}/permissions")
async def record_permission(contact_id: str, data: PermissionIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What the person told someone on the team: yes or no to calls, WhatsApp or email about their enquiry. Kept with who wrote it down. A no they gave
    themselves can't be turned into a yes here: only their own tick or message can."""
    c = await _lead(contact_id, ctx, db)
    if data.channel not in reach.CHANNELS or data.state not in ("granted", "refused"):
        raise HTTPException(status_code=400, detail="Choose calls, WhatsApp or email, and yes or no")
    words = (data.words or "").strip()
    if data.state == "granted" and not words:
        raise HTTPException(status_code=400, detail="Write down how they agreed, e.g. 'Said yes on the phone on 3 Nov'")
    saved = await reach.record(db, c, data.channel, data.state, "team", words or None, by=ctx.user_id)
    if saved is None:
        raise HTTPException(status_code=409, detail="They asked not to be contacted this way. Only they can change that, by their own message or tick")
    if data.state == "refused":
        await reach.stop_chase(db, c, f"They asked not to be contacted by {reach.LABEL[data.channel]}")
    await db.commit()
    return {"reach": await reach.overview(db, c), "permissions": await reach.permissions_of(db, c.id)}


class LeadChange(BaseModel):
    stage: Optional[str] = Field(None, max_length=20)
    assigned_to: Optional[str] = Field(None, max_length=36)
    tags: Optional[list[str]] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=4000)
    name: Optional[str] = Field(None, max_length=80)


@router.put("/leads/{contact_id}")
async def change_lead(contact_id: str, data: LeadChange, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    people, _ = await core.names_of(db, ctx.owner_id)
    if data.assigned_to is not None:
        if ctx.role == "agent":
            raise HTTPException(status_code=403, detail="Ask a manager to give this lead to someone else")
        if data.assigned_to and data.assigned_to not in people:
            raise HTTPException(status_code=400, detail="That person isn't on your team")
        await core.assign(db, c, data.assigned_to or None, ctx.user_id, people)
    if data.stage is not None:
        if data.stage not in journeys.STAGES or data.stage in ("customer", "lost"):
            raise HTTPException(status_code=400, detail="Use Won or Lost to close a lead")
        core.stage(db, c, data.stage, ctx.user_id)
    if data.tags is not None:
        c.tags = sorted({t.strip()[:40] for t in data.tags if t.strip()})
    if data.notes is not None:
        c.notes = data.notes.strip() or None
    if data.name is not None and data.name.strip():
        c.name = data.name.strip()
    await db.commit()
    return {"ok": True}


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


@router.post("/leads/{contact_id}/notes")
async def add_note(contact_id: str, data: NoteIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    db.add(core.event(c, "note", data.text.strip(), ctx.user_id))
    await db.commit()
    return {"ok": True}


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_at: str = Field(..., max_length=40)
    kind: str = Field("call", max_length=12)
    assigned_to: Optional[str] = Field(None, max_length=36)


@router.post("/leads/{contact_id}/tasks")
async def add_task(contact_id: str, data: TaskIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    if data.kind not in core.KINDS:
        raise HTTPException(status_code=400, detail="Call, WhatsApp, email, visit or other")
    people, _ = await core.names_of(db, ctx.owner_id)
    person = data.assigned_to if ctx.role != "agent" else ctx.user_id
    if person and person not in people:
        raise HTTPException(status_code=400, detail="That person isn't on your team")
    task = core.add_task(db, c, data.title.strip(), _when(data.due_at), data.kind, ctx.user_id, person)
    await db.commit()
    return core.task_json(task, people)


class TaskChange(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    due_at: Optional[str] = Field(None, max_length=40)
    status: Optional[str] = Field(None, max_length=10)
    result: Optional[str] = Field(None, max_length=300)


@router.put("/tasks/{task_id}")
async def change_task(task_id: str, data: TaskChange, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    t = await _task(task_id, ctx, db)
    if t.status != "open":
        raise HTTPException(status_code=409, detail="This task is already finished")
    if data.title:
        t.title = data.title.strip()
    if data.due_at:
        t.due_at, t.reminded_at, t.escalated_at = _when(data.due_at), None, None
    if data.status in ("done", "cancelled"):
        if not await core.finish_task(db, t.id, ctx.user_id, data.result, data.status):
            raise HTTPException(status_code=409, detail="This task is already finished")
        c = await db.get(Contact, t.contact_id)
        if data.status == "done":
            c.first_response_at = c.first_response_at or core.now()
    elif data.status:
        raise HTTPException(status_code=400, detail="Done or cancelled")
    await db.commit()
    return {"ok": True}


class ResultIn(BaseModel):
    result: str = Field(..., max_length=20)
    note: str = Field("", max_length=300)
    next_at: Optional[str] = Field(None, max_length=40)


@router.post("/leads/{contact_id}/result")
async def call_result(contact_id: str, data: ResultIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """How a try at reaching them went."""
    c = await _lead(contact_id, ctx, db)
    if data.result not in core.RESULTS:
        raise HTTPException(status_code=400, detail="Choose how it went")
    next_at = _when(data.next_at)
    if data.result == "later" and next_at is None:
        raise HTTPException(status_code=400, detail="When should they be called?")
    await core.record_result(db, c, data.result, ctx.user_id, data.note.strip() or None, next_at)
    await db.commit()
    return {"ok": True}


class CloseIn(BaseModel):
    outcome: str = Field(..., max_length=6)
    amount: Optional[float] = Field(None, ge=0, le=1_000_000_000)
    reason: str = Field("", max_length=200)


@router.post("/leads/{contact_id}/close")
async def close_lead(contact_id: str, data: CloseIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    if data.outcome not in ("won", "lost"):
        raise HTTPException(status_code=400, detail="Won or lost")
    if data.outcome == "lost" and not data.reason.strip():
        raise HTTPException(status_code=400, detail="Say why it was lost: it shows you where leads go")
    if c.stage in ("customer", "lost") and c.stage == ("customer" if data.outcome == "won" else "lost"):
        raise HTTPException(status_code=409, detail="This lead is already closed. Reopen it first.")
    became_customer = data.outcome == "won"
    await core.close(db, c, data.outcome, ctx.user_id, data.amount, data.reason.strip() or None)
    await db.commit()
    if became_customer:
        await journeys.fire(ctx.owner_id, c.bot_id, "customer", c.id)
    return {"ok": True}


@router.post("/leads/{contact_id}/real")
async def not_junk(contact_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A manager overrules the junk filter: the lead is worked like any other from now, and isn't marked again."""
    c = await _lead(contact_id, ctx, db)
    if c.quality != "junk":
        raise HTTPException(status_code=409, detail="This lead isn't marked as junk")
    c.quality = "ok"
    c.last_enquiry_at = c.last_enquiry_at or c.created_at  # when they asked
    db.add(core.event(c, "real", "A real lead after all", ctx.user_id))
    await db.commit()
    return {"ok": True}


@router.post("/leads/{contact_id}/reopen")
async def reopen_lead(contact_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    c = await _lead(contact_id, ctx, db)
    await core.reopen(db, c, ctx.user_id)
    await db.commit()
    return {"ok": True}


class ImportIn(BaseModel):
    bot_id: str = Field(..., max_length=36)
    csv: str = Field(..., min_length=1, max_length=IMPORT_BYTES)
    source: str = Field("", max_length=40)


SOURCE_HEADERS = ("source", "lead source", "came from", "channel")
STAGE_HEADERS = ("stage", "status", "lead status")
NOTE_HEADERS = ("notes", "note", "remarks", "comments")


@router.post("/import")
async def import_leads(data: ImportIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Leads from an old spreadsheet, kept with where they came from. Nobody is contacted because of it: no first task, email, call or journey. An old list isn't
    a new enquiry, so it gives no seven days to call them either; they show in All leads, not in Needs attention, until they ask again."""
    from voice import schedule
    bot = await get_owned_bot(data.bot_id, ctx, db)
    rate_limit(f"leads-import:{ctx.owner_id}", 10, 3600)
    try:
        rows = _rows(data.csv)
    except csv.Error:
        raise HTTPException(status_code=400, detail="That file couldn't be read as a CSV")
    if len(rows) > IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"That's {len(rows)} rows. Import up to {IMPORT_ROWS} at a time.")
    if rows and not any(n in rows[0] for n in (*EMAIL_HEADERS, *PHONE_HEADERS)):
        raise HTTPException(status_code=400, detail="The first line must name the columns, with one called phone or email")
    added, existing, skipped = 0, 0, []
    for line, row in enumerate(rows, 2):
        given = _pick(row, EMAIL_HEADERS).lower()
        mail = given if automations.EMAIL_RE.fullmatch(given) else ""
        phone = _pick(row, PHONE_HEADERS)
        e164 = to_e164(phone) or None
        junk = quality.why_junk(phone, mail)
        if e164 and quality.impossible(e164):  # with a real email: kept without the number nobody has
            e164 = None
        if junk or not (e164 or mail):
            skipped.append({"line": line, "why": junk or "No valid phone number or email"})
            continue
        contact = await journeys.find_contact(db, bot.bot_id, e164, mail or None)
        name = _pick(row, NAME_HEADERS)[:80] or None
        if contact is not None:
            existing += 1
            contact.email, contact.e164, contact.name = contact.email or mail or None, contact.e164 or e164, contact.name or name
            continue
        contact = Contact(user_id=ctx.owner_id, bot_id=bot.bot_id, e164=e164, email=mail or None, name=name, details={}, calls=0, quality="old", origin={"channel": "import"},
                          source=(_pick(row, SOURCE_HEADERS) or data.source.strip() or "Imported")[:40], notes=_pick(row, NOTE_HEADERS)[:4000] or None,
                          tags=sorted({t.strip()[:40] for t in _pick(row, TAG_HEADERS).replace(";", ",").split(",") if t.strip()}))
        stage = _pick(row, STAGE_HEADERS).lower()
        if stage in journeys.STAGES:
            contact.stage = stage
            if stage in ("customer", "lost"):  # so Schedule never calls someone the list says is done with
                schedule.rate(contact, "customer" if stage == "customer" else "not_interested", "From an imported list", by=ctx.user_id)
                contact.stage = stage
        db.add(contact)
        await db.flush()
        db.add(core.event(contact, "imported", f"From {contact.source}", ctx.user_id))
        added += 1
    await db.commit()
    return {"added": added, "existing": existing, "skipped_count": len(skipped), "skipped": skipped[:20]}


class SettingsIn(BaseModel):
    assign: str = Field("off", max_length=8)
    people: list[str] = Field(default_factory=list, max_length=50)
    backup: Optional[str] = Field(None, max_length=36)
    first_task: bool = True
    respond_minutes: int = Field(15, ge=1, le=1440)
    whatsapp_first: Optional[str] = Field(None, max_length=512)   # an approved template's name, as WhatsApp Manager shows it
    whatsapp_language: str = Field("en", max_length=12)
    alert_template: Optional[str] = Field(None, max_length=512)
    alert_language: str = Field("en", max_length=12)


TEMPLATE_NAME = re.compile(r"^[a-z0-9_]{1,512}$")
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")


@router.get("/settings/{bot_id}")
async def get_settings(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    return {"settings": await core.settings_of(db, bot.bot_id), "team": [{"id": p["id"], "name": p["name"]} for p in await core.team(db, ctx.owner_id)]}


@router.put("/settings/{bot_id}")
async def put_settings(bot_id: str, data: SettingsIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    if data.assign not in ("off", "one", "turns"):
        raise HTTPException(status_code=400, detail="Nobody, one person, or by turns")
    known = {p["id"] for p in await core.team(db, ctx.owner_id)}
    if any(p not in known for p in data.people) or (data.backup and data.backup not in known):
        raise HTTPException(status_code=400, detail="That person isn't on your team")
    if data.assign != "off" and not data.people:
        raise HTTPException(status_code=400, detail="Choose who gets new leads")
    values = data.model_dump(exclude_unset=True)  # an older page that doesn't send the WhatsApp fields keeps them
    for key in ("whatsapp_first", "alert_template"):
        if key in values:
            values[key] = (values[key] or "").strip() or None
            if values[key] and not TEMPLATE_NAME.fullmatch(values[key]):
                raise HTTPException(status_code=400, detail="A template's name is small letters, numbers and _, exactly as WhatsApp Manager shows it")
    for key in ("whatsapp_language", "alert_language"):
        if key in values and not LANGUAGE_CODE.fullmatch(values[key] or ""):
            raise HTTPException(status_code=400, detail="A language code such as en, en_US, ta or hi")
    if (values.get("whatsapp_first") or values.get("alert_template")) and not (await plans.includes(db, bot.bot_id)).whatsapp:
        raise plans.plan_needed("whatsapp", bot.bot_name)
    saved = await core.save_settings(db, ctx.owner_id, bot.bot_id, values)
    await db.commit()
    return {"settings": saved, "team": [{"id": p["id"], "name": p["name"]} for p in await core.team(db, ctx.owner_id)]}


# ─── promises (instagram_plan.md phase 7) ───────────────────────
class PromiseIn(BaseModel):
    kind: str = Field(..., max_length=10)
    what: str = Field(..., min_length=1, max_length=200)
    due_at: Optional[str] = Field(None, max_length=40)


class KeptIn(BaseModel):
    kind: Optional[str] = Field(None, max_length=20)   # one of the records since the promise (GET .../evidence)
    id: Optional[str] = Field(None, max_length=64)
    how: Optional[str] = Field(None, max_length=10)    # or what the person did, written down
    note: Optional[str] = Field(None, max_length=300)


class CancelIn(BaseModel):
    why: str = Field(..., min_length=1, max_length=200)


async def _promise(promise_id: str, ctx: AuthContext, db: AsyncSession) -> tuple[LeadPromise, Contact]:
    found = (await db.execute(select(LeadPromise, Contact).join(Contact, Contact.id == LeadPromise.contact_id)
                              .where(LeadPromise.id == promise_id, *core.visible(ctx)))).first()
    if found is None:
        raise HTTPException(status_code=404, detail="Promise not found")
    return found[0], found[1]


@router.post("/leads/{contact_id}/promises")
async def add_promise(contact_id: str, data: PromiseIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Something a person on the team promised them, to keep it in view until it's done."""
    c = await _lead(contact_id, ctx, db)
    if data.kind not in promises.KINDS:
        raise HTTPException(status_code=400, detail="Choose what was promised")
    made_at = promises.utc(core.now())
    due = _when(data.due_at)
    if due is not None and not made_at - timedelta(hours=1) <= promises.utc(due) <= made_at + promises.LATEST_DUE:
        raise HTTPException(status_code=400, detail="Choose a time within the next two months")
    item = {"kind": data.kind, "what": data.what.strip(), "due_at": promises.utc(due) if due else made_at + promises.DEFAULT_DUE, "due_said": due is not None, "words": None}
    made = await promises.add(db, c, [item], "team", None, made_at, made_by=ctx.user_id)
    if not made:
        raise HTTPException(status_code=409, detail="That promise is already open on this lead")
    await db.commit()
    people, _ = await core.names_of(db, ctx.owner_id)
    return promises.promise_json(made[0], people)


@router.get("/promises/{promise_id}/evidence")
async def promise_evidence(promise_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What was done for them since the promise: the records a person can choose as what kept it."""
    p, c = await _promise(promise_id, ctx, db)
    return [{k: a[k] for k in ("kind", "id", "at", "text")} for a in await promises.actions(db, p, c)]


@router.post("/promises/{promise_id}/done")
async def promise_kept(promise_id: str, data: KeptIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Done, with what shows it: a record from since the promise, or what the person did, in their own words. Never just "done"."""
    p, c = await _promise(promise_id, ctx, db)
    if p.status != "open":
        raise HTTPException(status_code=409, detail="This promise isn't open any more")
    if data.kind and data.id:
        found = next((a for a in await promises.actions(db, p, c) if a["kind"] == data.kind and a["id"] == data.id), None)
        if found is None:
            raise HTTPException(status_code=400, detail="Choose something done for them after the promise was made")
    elif (data.note or "").strip() and data.how in promises.HOW:  # their own words, under their name, in the lead's story
        found = {"kind": "record", "id": None, "at": promises.utc(core.now()).isoformat(), "text": f"{promises.HOW[data.how]}: {data.note.strip()}"[:300]}
    else:
        raise HTTPException(status_code=400, detail="Choose what kept it, or write down what you did")
    if not await promises.keep(db, p, c, found, ctx.user_id):
        raise HTTPException(status_code=409, detail="This promise isn't open any more")
    await db.commit()
    people, _ = await core.names_of(db, ctx.owner_id)
    return promises.promise_json(await db.get(LeadPromise, p.id, populate_existing=True), people)


@router.post("/promises/{promise_id}/cancel")
async def promise_cancel(promise_id: str, data: CancelIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """It won't be done, and why (they don't need it any more, it was promised by mistake)."""
    p, c = await _promise(promise_id, ctx, db)
    if not await promises.cancel(db, p, c, data.why.strip(), ctx.user_id):
        raise HTTPException(status_code=409, detail="This promise isn't open any more")
    await db.commit()
    people, _ = await core.names_of(db, ctx.owner_id)
    return promises.promise_json(await db.get(LeadPromise, p.id, populate_existing=True), people)


@router.get("/reports")
async def reports(days: int = 30, bot_id: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return await core.report(db, ctx, min(max(days, 1), 365), bot_id or None)

