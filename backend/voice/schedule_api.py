"""
Voice > Schedule in the dashboard: what's coming up and what needs the team (meetings to approve, follow-ups to check,
people who asked for a person), the calls the assistant will make, meetings, each assistant's Schedule settings, and
leads' ratings. How it all works: voice/schedule.py and voice/meetings.py.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx, get_owned_bot, require_manager
from backend.models import (Bot, CallbackJob, CallLog, Contact, Meeting, NotificationLog, PhoneNumber, ScheduleSettings,
                            TeamMember, User)
from database import get_db
from notify.events import fire_and_forget
from phone import display
from voice import meetings, schedule
from voice.schedule import ScheduleError, now_utc, stored, utc, zone

router = APIRouter(prefix="/api/voice/schedule", tags=["voice-schedule"])

TEST_CALL = schedule.TEST_CALL
OPEN_STATUSES = ("queued", "review", "calling", "todo")


def _iso(at: Optional[datetime]) -> Optional[str]:
    return utc(at).isoformat() if at else None


async def _names(db: AsyncSession, owner_id: str) -> dict:
    return {r[0]: r[1] for r in (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all()}


class _Zones:
    """Each assistant's Schedule settings, loaded once per request."""

    def __init__(self, db: AsyncSession):
        self.db, self.cache = db, {}

    async def __call__(self, bot_id: str) -> dict:
        if bot_id not in self.cache:
            self.cache[bot_id] = await schedule.settings_for(bot_id, self.db)
        return self.cache[bot_id]


def _jobs(owner_id: str):
    """Calls the Schedule lists: its own kinds, and website call-back requests (not campaign or test calls)."""
    return select(CallbackJob).where(
        CallbackJob.user_id == owner_id, CallbackJob.campaign_id.is_(None),
        or_(CallbackJob.kind.in_(schedule.KINDS),
            CallbackJob.kind.is_(None) & ~CallbackJob.consent_source.startswith(TEST_CALL)))


async def _item_json(job: CallbackJob, names: dict, zones: _Zones, results: Optional[dict] = None) -> dict:
    tz = zone(await zones(job.bot_id))
    due = utc(job.next_attempt_at)
    result = (results or {}).get(job.call_id) if job.call_id else None
    return {
        "id": job.id, "kind": job.kind or "callback", "bot_id": job.bot_id, "bot_name": names.get(job.bot_id, ""),
        "from": "website" if job.kind is None else "team" if job.created_by else "assistant",
        "name": job.name or "", "number": display(job.e164), "status": job.status, "due_at": _iso(job.next_attempt_at),
        "local": due.astimezone(tz).strftime("%Y-%m-%dT%H:%M") if due else None, "timezone": str(tz),
        "purpose": job.purpose or "", "attempts": job.attempts or 0, "last_error": job.last_error,
        "call_id": job.call_id, "source_call_id": job.source_call_id, "meeting_id": job.meeting_id,
        "step": (job.variables or {}).get("step") if job.kind == "follow_up" else None,
        "consent": job.consent_source, "created_at": _iso(job.created_at),
        "result": {"outcome": result.outcome, "summary": result.summary or ""} if result else None,
    }


async def _results(db: AsyncSession, jobs: list) -> dict:
    ids = [j.call_id for j in jobs if j.call_id]
    if not ids:
        return {}
    return {c.id: c for c in (await db.execute(select(CallLog).where(CallLog.id.in_(ids)))).scalars().all()}


# ─── what's coming and what needs you ────────────────────────────
@router.get("/attention")
async def attention(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """For the Schedule tab's badge."""
    return await schedule.needs_attention(db, ctx.owner_id)


@router.get("/overview")
async def overview(bot_id: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    names, zones = await _names(db, ctx.owner_id), _Zones(db)
    now = now_utc()
    week = stored(now + timedelta(days=7))
    jobs = _jobs(ctx.owner_id)
    meetings_q = select(Meeting).where(Meeting.user_id == ctx.owner_id)
    if bot_id:
        jobs, meetings_q = jobs.where(CallbackJob.bot_id == bot_id), meetings_q.where(Meeting.bot_id == bot_id)
    coming = (await db.execute(jobs.where(CallbackJob.status.in_(("queued", "review", "calling")),
                                          CallbackJob.next_attempt_at <= week)
                               .order_by(CallbackJob.next_attempt_at).limit(100))).scalars().all()
    people = (await db.execute(jobs.where(CallbackJob.kind == "person", CallbackJob.status == "todo")
                               .order_by(CallbackJob.next_attempt_at).limit(50))).scalars().all()
    missed = (await db.execute(jobs.where(or_(CallbackJob.kind == "callback", CallbackJob.kind.is_(None)),
                                          CallbackJob.status == "failed",
                                          CallbackJob.next_attempt_at >= stored(now - timedelta(days=3)))
                               .order_by(CallbackJob.next_attempt_at.desc()).limit(20))).scalars().all()
    booked = (await db.execute(meetings_q.where(Meeting.status.in_(meetings.ACTIVE), Meeting.starts_at > stored(now),
                                                Meeting.starts_at <= week).order_by(Meeting.starts_at).limit(100))).scalars().all()
    to_mark = (await db.execute(meetings_q.where(Meeting.status == "confirmed",
                                                 Meeting.starts_at < stored(now - timedelta(minutes=30)))
                                .order_by(Meeting.starts_at).limit(20))).scalars().all()

    async def meeting_json(m: Meeting) -> dict:
        return meetings.to_json(m, await zones(m.bot_id), names=names)

    return {
        "attention": await schedule.needs_attention(db, ctx.owner_id),
        "stats": await _stats(db, ctx.owner_id, bot_id),
        "calls": [await _item_json(j, names, zones) for j in coming if j.kind != "person"],
        "meetings": [await meeting_json(m) for m in booked],
        "people": [await _item_json(j, names, zones) for j in people],
        "missed": [await _item_json(j, names, zones) for j in missed],
        "to_mark": [await meeting_json(m) for m in to_mark],
    }


async def _stats(db: AsyncSession, owner_id: str, bot_id: str) -> dict:
    """The last 30 days."""
    since = stored(now_utc() - timedelta(days=30))

    async def count(model, *where) -> int:
        conditions = [model.user_id == owner_id, *where]
        if bot_id:
            conditions.append(model.bot_id == bot_id)
        return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar() or 0
    recent = CallbackJob.created_at >= since
    leads = {}
    rows = (await db.execute(select(Contact.lead_status, func.count()).where(
        Contact.user_id == owner_id, Contact.lead_status.isnot(None), *([Contact.bot_id == bot_id] if bot_id else []))
        .group_by(Contact.lead_status))).all()
    for status, n in rows:
        leads[status] = n
    return {
        "callbacks": {"booked": await count(CallbackJob, recent, CallbackJob.kind == "callback"),
                      "reached": await count(CallbackJob, recent, CallbackJob.kind == "callback", CallbackJob.status == "done"),
                      "missed": await count(CallbackJob, recent, CallbackJob.kind == "callback", CallbackJob.status == "failed")},
        "follow_ups": {"made": await count(CallbackJob, recent, CallbackJob.kind == "follow_up",
                                           CallbackJob.status.in_(("done", "failed"))),
                       "answered": await count(CallbackJob, recent, CallbackJob.kind == "follow_up", CallbackJob.status == "done")},
        "meetings": {"requested": await count(Meeting, Meeting.created_at >= since),
                     "confirmed": await count(Meeting, Meeting.created_at >= since,
                                              Meeting.status.in_(("confirmed", "done", "no_show"))),
                     "attended": await count(Meeting, Meeting.created_at >= since, Meeting.status == "done"),
                     "missed": await count(Meeting, Meeting.created_at >= since, Meeting.status == "no_show")},
        "leads": leads,
    }


# ─── calls the assistant will make ────────────────────────────────
@router.get("/items")
async def list_items(kind: str = "", status: str = "open", bot_id: str = "", ctx: AuthContext = Depends(get_ctx),
                     db: AsyncSession = Depends(get_db)):
    query = _jobs(ctx.owner_id)
    if kind == "callback":
        query = query.where(or_(CallbackJob.kind == "callback", CallbackJob.kind.is_(None)))
    elif kind == "meeting":
        query = query.where(CallbackJob.kind.in_(("meeting", "no_show")))
    elif kind in ("follow_up", "person"):
        query = query.where(CallbackJob.kind == kind)
    if bot_id:
        query = query.where(CallbackJob.bot_id == bot_id)
    if status == "open":
        query = query.where(CallbackJob.status.in_(OPEN_STATUSES)).order_by(CallbackJob.next_attempt_at)
    else:
        if status == "done":
            query = query.where(CallbackJob.status.notin_(OPEN_STATUSES))
        query = query.order_by(CallbackJob.next_attempt_at.desc())
    jobs = (await db.execute(query.limit(200))).scalars().all()
    names, zones, results = await _names(db, ctx.owner_id), _Zones(db), await _results(db, jobs)
    return [await _item_json(j, names, zones, results) for j in jobs]


async def _owned_job(job_id: str, ctx: AuthContext, db: AsyncSession) -> CallbackJob:
    job = (await db.execute(_jobs(ctx.owner_id).where(CallbackJob.id == job_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    return job


def _team_time(settings: dict, day: str, clock: str, hours: Optional[list] = None) -> datetime:
    at = schedule.local_time(day, clock, zone(settings))
    if at is None:
        raise HTTPException(status_code=400, detail="Choose a day and a time")
    if at <= now_utc() + timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="Choose a time in the future")
    hours = hours or settings["callbacks"]["hours"]
    if not schedule.allowed(at, hours, schedule.DAYS, zone(settings)):
        raise HTTPException(status_code=400, detail=f"Calls go out between {schedule.hours_text(hours)}")
    return at


class NewCall(BaseModel):
    contact_id: str
    date: str
    time: str
    about: str = Field("", max_length=300)


@router.post("/items")
async def schedule_call(data: NewCall, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The team asks the assistant to call someone it has spoken with, at a time, about something."""
    contact = (await db.execute(select(Contact).where(Contact.id == data.contact_id, Contact.user_id == ctx.owner_id))).scalars().first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if await schedule.on_dnc(db, ctx.owner_id, contact.e164):
        raise HTTPException(status_code=400, detail="They're on the do-not-call list")
    settings = await schedule.settings_for(contact.bot_id, db)
    at = _team_time(settings, data.date, data.time)
    last = utc(contact.last_call_at)
    job = await schedule.book_callback(
        owner_id=ctx.owner_id, bot_id=contact.bot_id, e164=contact.e164, at=at, about=data.about, name=contact.name,
        source_call_id=None, number_id=None, tz=zone(settings), created_by=ctx.user_id,
        consent=f"Arranged by the team after their call on {last.astimezone(zone(settings)):%d %b %Y}" if last
        else "Arranged by the team")
    names = await _names(db, ctx.owner_id)
    return await _item_json(job, names, _Zones(db))


class ItemUpdate(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    about: Optional[str] = Field(None, max_length=600)


@router.patch("/items/{job_id}")
async def update_item(job_id: str, data: ItemUpdate, ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    job = await _owned_job(job_id, ctx, db)
    if job.status not in ("queued", "review", "todo"):
        raise HTTPException(status_code=409, detail="This call isn't waiting any more")
    settings = await schedule.settings_for(job.bot_id, db)
    if data.date and data.time:
        hours = settings["follow_ups"]["hours"] if job.kind == "follow_up" else None
        job.next_attempt_at = stored(_team_time(settings, data.date, data.time, hours))
    if data.about is not None:
        job.purpose = data.about.strip() or job.purpose
    await db.commit()
    return await _item_json(job, await _names(db, ctx.owner_id), _Zones(db))


@router.post("/items/{job_id}/{action}")
async def item_action(job_id: str, action: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """approve (a follow-up waiting for the team's OK), now (call as soon as calling hours allow), cancel, done (a
    person called them)."""
    job = await _owned_job(job_id, ctx, db)
    if action != "done" and ctx.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Your role doesn't allow this")
    if action == "done":
        if job.kind != "person" or job.status != "todo":
            raise HTTPException(status_code=409, detail="Only a to-do for the team can be marked done")
        job.status, job.last_error = "done", None
        job.created_by = job.created_by or ctx.user_id
    elif action in ("approve", "now"):
        if job.status not in ("queued", "review") or job.kind == "person":
            raise HTTPException(status_code=409, detail="This call isn't waiting any more")
        job.status = "queued"
        if action == "now":
            job.next_attempt_at = datetime.utcnow()
    elif action == "cancel":
        if job.status not in ("queued", "review", "todo"):
            raise HTTPException(status_code=409, detail="This call isn't waiting any more")
        job.status, job.last_error = "cancelled", "Cancelled by the team"
    else:
        raise HTTPException(status_code=404, detail="Unknown action")
    await db.commit()
    return await _item_json(job, await _names(db, ctx.owner_id), _Zones(db))


# ─── meetings ─────────────────────────────────────────────────────
@router.get("/meetings")
async def list_meetings(status: str = "upcoming", bot_id: str = "", ctx: AuthContext = Depends(get_ctx),
                        db: AsyncSession = Depends(get_db)):
    query = select(Meeting).where(Meeting.user_id == ctx.owner_id)
    if bot_id:
        query = query.where(Meeting.bot_id == bot_id)
    now = stored(now_utc())
    if status == "requests":
        query = query.where(Meeting.status.in_(("requested", "proposed"))).order_by(Meeting.starts_at)
    elif status == "upcoming":
        query = query.where(Meeting.status == "confirmed", Meeting.starts_at > now - timedelta(hours=2)).order_by(Meeting.starts_at)
    elif status == "past":
        query = query.where(or_(Meeting.status.in_(("done", "no_show", "cancelled", "expired")),
                                (Meeting.status == "confirmed") & (Meeting.starts_at <= now - timedelta(hours=2)))
                            ).order_by(Meeting.starts_at.desc())
    else:
        query = query.order_by(Meeting.starts_at.desc())
    rows = (await db.execute(query.limit(200))).scalars().all()
    names, zones = await _names(db, ctx.owner_id), _Zones(db)
    return [meetings.to_json(m, await zones(m.bot_id), names=names) for m in rows]


async def _owned_meeting(meeting_id: str, ctx: AuthContext, db: AsyncSession) -> Meeting:
    meeting = (await db.execute(select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == ctx.owner_id))).scalars().first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


async def _meeting_detail(db: AsyncSession, meeting: Meeting, owner_id: str) -> dict:
    settings = await schedule.settings_for(meeting.bot_id, db)
    data = meetings.to_json(meeting, settings, names=await _names(db, owner_id), full=True)
    source = await db.get(CallLog, meeting.source_call_id) if meeting.source_call_id else None
    data["source_call"] = {"id": source.id, "summary": source.summary or "", "started_at": _iso(source.started_at)} if source else None
    sent = (await db.execute(select(NotificationLog).where(NotificationLog.ref_id.startswith(f"{meeting.id}@"))
                             .order_by(NotificationLog.created_at))).scalars().all()
    data["messages"] = [{"kind": n.kind, "status": n.status, "note": n.error, "at": _iso(n.created_at)} for n in sent]
    calls = (await db.execute(select(CallbackJob).where(CallbackJob.meeting_id == meeting.id)
                              .order_by(CallbackJob.created_at))).scalars().all()
    data["calls"] = [{"id": j.id, "kind": j.kind, "status": j.status, "due_at": _iso(j.next_attempt_at),
                      "about": (j.variables or {}).get("about"), "last_error": j.last_error, "call_id": j.call_id} for j in calls]
    data["channels"] = await meetings.channels_for(db, meeting, settings)
    mt = settings["meetings"]
    data["setup"] = {"confirm_call": mt["confirm_call"], "link_minutes": mt["link_minutes"], "default_link": mt["link"],
                     "address": mt["address"], "template": bool(mt["whatsapp_template"])}
    return data


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return await _meeting_detail(db, await _owned_meeting(meeting_id, ctx, db), ctx.owner_id)


class Approve(BaseModel):
    link: str = Field("", max_length=500)
    host_id: Optional[str] = None


async def _check_host(db: AsyncSession, ctx: AuthContext, host_id: Optional[str]) -> Optional[str]:
    if not host_id:
        return None
    if host_id == ctx.owner_id:
        return host_id
    member = (await db.execute(select(TeamMember.id).where(
        TeamMember.owner_id == ctx.owner_id, TeamMember.member_id == host_id, TeamMember.status == "active"))).first()
    if not member:
        raise HTTPException(status_code=400, detail="Choose someone on your team")
    return host_id


@router.post("/meetings/{meeting_id}/approve")
async def approve_meeting(meeting_id: str, data: Approve, ctx: AuthContext = Depends(require_manager),
                          db: AsyncSession = Depends(get_db)):
    meeting = await _owned_meeting(meeting_id, ctx, db)
    try:
        await meetings.approve(db, meeting, by=ctx.user_id, link=data.link, host_id=await _check_host(db, ctx, data.host_id))
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    fire_and_forget(meetings.send_confirmation(meeting.id))
    return await _meeting_detail(db, meeting, ctx.owner_id)


class NewTime(BaseModel):
    date: str
    time: str


def _meeting_time(settings: dict, data: NewTime) -> datetime:
    at = schedule.local_time(data.date, data.time, zone(settings))
    if at is None:
        raise HTTPException(status_code=400, detail="Choose a day and a time")
    return at


@router.post("/meetings/{meeting_id}/propose")
async def propose_time(meeting_id: str, data: NewTime, ctx: AuthContext = Depends(require_manager),
                       db: AsyncSession = Depends(get_db)):
    """Another time for a request: the assistant calls them to agree it."""
    meeting = await _owned_meeting(meeting_id, ctx, db)
    settings = await schedule.settings_for(meeting.bot_id, db)
    try:
        if meeting.status == "confirmed":
            await meetings.move(db, meeting, _meeting_time(settings, data), by=ctx.user_id)
        else:
            await meetings.propose(db, meeting, _meeting_time(settings, data), by=ctx.user_id)
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    if meeting.status == "confirmed":
        fire_and_forget(meetings.send_confirmation(meeting.id))
    return await _meeting_detail(db, meeting, ctx.owner_id)


class Decline(BaseModel):
    call: bool = True
    reason: str = Field("", max_length=300)


@router.post("/meetings/{meeting_id}/decline")
async def decline_meeting(meeting_id: str, data: Decline, ctx: AuthContext = Depends(require_manager),
                          db: AsyncSession = Depends(get_db)):
    """Can't take it: with `call`, the assistant calls them to find another time; else they're written to."""
    meeting = await _owned_meeting(meeting_id, ctx, db)
    try:
        await meetings.decline(db, meeting, by=ctx.user_id, call=data.call, reason=data.reason)
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    if not data.call:
        fire_and_forget(meetings.send_cancelled(meeting.id))
    return await _meeting_detail(db, meeting, ctx.owner_id)


class Mark(BaseModel):
    attended: bool


@router.post("/meetings/{meeting_id}/mark")
async def mark_meeting(meeting_id: str, data: Mark, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    meeting = await _owned_meeting(meeting_id, ctx, db)
    try:
        await meetings.mark(db, meeting, by=ctx.user_id, attended=data.attended)
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return await _meeting_detail(db, meeting, ctx.owner_id)


class MeetingUpdate(BaseModel):
    link: Optional[str] = Field(None, max_length=500)
    host_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    email: Optional[str] = Field(None, max_length=120)


@router.patch("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, data: MeetingUpdate, ctx: AuthContext = Depends(require_manager),
                         db: AsyncSession = Depends(get_db)):
    meeting = await _owned_meeting(meeting_id, ctx, db)
    if data.link is not None:
        link = data.link.strip()
        if link and meeting.kind == "online" and not link.startswith(("https://", "http://")):
            raise HTTPException(status_code=400, detail="The meeting link should be a full address starting with https://")
        meeting.link = link or None
    if data.host_id is not None:
        meeting.host_id = await _check_host(db, ctx, data.host_id) if data.host_id else None
    if data.notes is not None:
        meeting.notes = data.notes.strip() or None
    if data.email is not None:
        email = data.email.strip()
        if email and not meetings.EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email")
        meeting.email = email or None
    await db.commit()
    return await _meeting_detail(db, meeting, ctx.owner_id)


@router.get("/free-times")
async def free_times(bot_id: str, date: str = "", ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Free meeting times on a day (or the next week), for proposing another time."""
    bot = await get_owned_bot(bot_id, ctx, db)
    settings = await schedule.settings_for(bot.bot_id, db)
    tz = zone(settings)
    first = schedule._day_of(date) or now_utc().astimezone(tz).date()
    free = await meetings.free_times(db, settings, ctx.owner_id, bot.bot_id, first, 1 if date else 7)
    return [{"date": day.isoformat(), "times": [t.strftime("%H:%M") for t in slots]} for day, slots in free.items()]


@router.get("/hosts")
async def hosts(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Who can take a meeting: the owner and the active team."""
    owner = await db.get(User, ctx.owner_id)
    rows = (await db.execute(select(TeamMember, User).join(User, User.id == TeamMember.member_id).where(
        TeamMember.owner_id == ctx.owner_id, TeamMember.status == "active"))).all()
    people = [{"id": owner.id, "name": owner.name or owner.email, "email": owner.email}] if owner else []
    return people + [{"id": u.id, "name": u.name or u.email, "email": u.email} for _, u in rows]


# ─── settings ─────────────────────────────────────────────────────
async def _settings_json(db: AsyncSession, owner_id: str, bot_id: str) -> dict:
    settings = await schedule.settings_for(bot_id, db)
    numbers = (await db.execute(select(PhoneNumber).where(
        PhoneNumber.user_id == owner_id, PhoneNumber.status == "active", PhoneNumber.e164.is_not(None))
        .order_by(PhoneNumber.created_at))).scalars().all()
    from whatsapp.numbers import workspace_number
    whatsapp = await workspace_number(db, owner_id)
    return {"settings": settings, "numbers": [{"id": n.id, "number": n.number, "own": n.bot_id == bot_id} for n in numbers],
            "whatsapp": bool(whatsapp and whatsapp.status != "disconnected")}


@router.get("/settings/{bot_id}")
async def get_settings(bot_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    return await _settings_json(db, ctx.owner_id, bot.bot_id)


@router.put("/settings/{bot_id}")
async def put_settings(bot_id: str, data: dict, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    try:
        settings = schedule.check(data)
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if settings["from_number_id"]:
        number = await db.get(PhoneNumber, settings["from_number_id"])
        if not number or number.user_id != ctx.owner_id or number.status != "active":
            raise HTTPException(status_code=400, detail="Choose one of your active numbers to call from")
    row = await db.get(ScheduleSettings, bot.bot_id)
    if row is None:
        row = ScheduleSettings(bot_id=bot.bot_id, user_id=ctx.owner_id)
        db.add(row)
    row.settings = settings
    if not settings["follow_ups"]["enabled"]:  # off: the ones planned go too
        from sqlalchemy import update
        await db.execute(update(CallbackJob).where(
            CallbackJob.bot_id == bot.bot_id, CallbackJob.kind == "follow_up", CallbackJob.status.in_(("queued", "review")))
            .values(status="cancelled", last_error="Follow-ups were turned off").execution_options(synchronize_session=False))
    await db.commit()
    return await _settings_json(db, ctx.owner_id, bot.bot_id)


# ─── leads ────────────────────────────────────────────────────────
class LeadUpdate(BaseModel):
    lead_status: Optional[str] = None
    follow_ups_off: Optional[bool] = None


@router.patch("/contacts/{contact_id}")
async def update_lead(contact_id: str, data: LeadUpdate, ctx: AuthContext = Depends(require_manager),
                      db: AsyncSession = Depends(get_db)):
    """The team rates a lead, or stops follow-ups for them. A rating that gets follow-ups plans one from their last call
    (if it's recent enough); one that doesn't calls off what's planned."""
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == ctx.owner_id))).scalars().first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if data.follow_ups_off is not None:
        contact.follow_ups_off = data.follow_ups_off or None
        if data.follow_ups_off:
            await schedule.cancel_waiting(db, contact.bot_id, contact.e164, "Follow-ups were stopped for them",
                                          kinds=("follow_up",), statuses=("queued", "review"))
    if data.lead_status is not None:
        if data.lead_status not in schedule.LEAD_STATUSES:
            raise HTTPException(status_code=400, detail="Unknown lead status")
        schedule.rate(contact, data.lead_status, "Set by the team", by=ctx.user_id)
        if data.lead_status not in schedule.FOLLOWED_UP:
            await schedule.cancel_waiting(db, contact.bot_id, contact.e164,
                                          f"Marked {schedule.LEAD_LABELS[data.lead_status].lower()} by the team",
                                          kinds=("follow_up",), statuses=("queued", "review"))
        else:
            last = (await db.execute(select(CallLog).where(
                CallLog.bot_id == contact.bot_id, CallLog.caller_e164 == contact.e164, CallLog.channel == "phone",
                CallLog.outcome.notin_(("no_answer", "voicemail", "failed", "in_progress", "opted_out")))
                .order_by(CallLog.started_at.desc()))).scalars().first()
            if last is not None:
                await schedule.plan_follow_up(db, last, contact, await schedule.settings_for(contact.bot_id, db))
    await db.commit()
    return {"id": contact.id, "lead_status": contact.lead_status, "lead_reason": contact.lead_reason or "",
            "lead_set_by_team": bool(contact.lead_set_by), "follow_ups_off": bool(contact.follow_ups_off)}


@router.get("/contacts/{contact_id}/next")
async def contact_next(contact_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What's coming for one person: calls waiting and their next meeting (the Contacts panel)."""
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == ctx.owner_id))).scalars().first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    jobs = (await db.execute(select(CallbackJob).where(
        CallbackJob.bot_id == contact.bot_id, CallbackJob.e164 == contact.e164,
        CallbackJob.status.in_(OPEN_STATUSES)).order_by(CallbackJob.next_attempt_at))).scalars().all()
    meeting = await schedule.upcoming_meeting(db, contact.bot_id, contact.e164)
    names, zones = await _names(db, ctx.owner_id), _Zones(db)
    return {"calls": [await _item_json(j, names, zones) for j in jobs],
            "meeting": meetings.to_json(meeting, await zones(meeting.bot_id), names=names) if meeting else None}
