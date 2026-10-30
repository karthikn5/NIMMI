"""
Voice > Schedule: what an assistant does after a conversation, on its own or with the team's OK.

  Call-backs   Someone on a call asks to be called later ("call me after 10 minutes", "tomorrow at 11"). The agent books
               it during the call (schedule_callback); it's dialled then, from the number they called, opening with
               "calling you back as you asked". If the agent agreed to one but didn't book it, the call's analysis does.
  Follow-ups   After each call the analysis rates the person as a lead (hot, warm, cold, new, not interested) and writes
               what the next call should do. The assistant's rules say how many follow-ups each rating gets, and how many
               days apart, at about the hour they last picked up. Each conversation starts the count again. They stop
               when the person books a meeting or a call-back, asks for a person, says no or opts out, is marked a
               customer, has had the most follow-ups allowed, or hasn't spoken with the business for `stop_after_days`
               (India, TRAI 2025: consent to be called about an enquiry lasts 7 days). With "review" on, each one waits
               for the team's OK.
  Meetings     voice/meetings.py: asked for on a call, approved by the team (or at once), confirmed with a call, and the
               link sent a few minutes before it starts.
  A person     Someone asked for a person to call them: a to-do for the team, never dialled by the system.

Everything to dial is a CallbackJob with a `kind`. voice/scheduler.py dials it when it's due and `dial_check` allows it
(calling hours and days, nothing changed since); the call opens and runs with what it's for (`plan_for`).
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import assist
from backend.models import (CallbackJob, CallbackSettings, CallLog, Contact, DncEntry, Meeting, PhoneNumber,
                            ScheduleSettings, VoiceAgent)
from database import async_session

logger = logging.getLogger(__name__)

LEAD_STATUSES = ("hot", "warm", "cold", "new", "not_interested", "customer")
FOLLOWED_UP = ("hot", "warm", "cold", "new")       # ratings that get follow-ups
LEAD_LABELS = {"hot": "Hot", "warm": "Warm", "cold": "Cold", "new": "New", "not_interested": "Not interested",
               "customer": "Customer"}
CALL_KINDS = ("callback", "follow_up", "meeting", "no_show")  # dialled by the scheduler
KINDS = CALL_KINDS + ("person",)
WAITING = ("queued", "review", "todo")            # not dialled or done yet
MEETING_KINDS = ("online", "in_person", "phone")
MEETING_LABELS = {"online": "online", "in_person": "in-person", "phone": "phone"}
DAYS = assist.DAYS
DEFAULT_TZ = "Asia/Kolkata"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RETRY_MINUTES = (5, 10, 15, 30, 60)
MEETING_MINUTES = (15, 30, 45, 60, 90)
LINK_MINUTES = (5, 10, 15, 30, 60)
CALLBACK_AHEAD = timedelta(days=30)   # a call-back further out than this isn't booked
CALLBACK_SOONEST = timedelta(minutes=2)
NAMED_DAY_AHEAD = 60                  # a follow-up on the day they named, up to this many days out
FOLLOW_UP_RETRY = timedelta(hours=2)  # an unanswered follow-up is tried again this much later (same day if it can)
TEST_CALL = "Test call requested from the dashboard"  # voice/router.py: "Call me" from the dashboard

DEFAULTS = {
    "timezone": DEFAULT_TZ,
    "from_number_id": None,  # None: the number they called, else the assistant's own, else the workspace's first
    # Everything starts off: each places calls (and uses credits) the business should choose to make.
    "callbacks": {"enabled": False, "hours": ["09:00", "21:00"], "attempts": 3, "retry_minutes": 15},
    "follow_ups": {
        "enabled": False, "review": False, "hours": ["10:00", "19:00"], "days": DAYS[:6],
        "rules": {"hot": {"count": 3, "every": 2}, "warm": {"count": 2, "every": 3},
                  "cold": {"count": 1, "every": 5}, "new": {"count": 1, "every": 1}},
        "stop_after_days": 7, "max_total": 6, "attempts": 2,
    },
    "meetings": {
        "enabled": False, "approval": True, "kinds": ["online"], "minutes": 30, "days": DAYS[:6],
        "hours": ["10:00", "18:00"], "notice_hours": 2, "ahead_days": 14, "at_once": 1, "offer_when": "",
        "link": "", "address": "", "confirm_call": True, "link_minutes": 5, "day_before": True, "no_show_call": True,
        "whatsapp_template": "", "template_language": "en",
    },
}


class ScheduleError(ValueError):
    """Settings from the dashboard that can't be saved; the message is shown as is."""


# ─── settings ─────────────────────────────────────────────────────
def zone_of(name) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def zone(settings: dict) -> ZoneInfo:
    return zone_of(settings.get("timezone"))


def _part(raw: dict, key: str) -> dict:
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


def _bool(value, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _one_of(value, default, options):
    return value if value in options else default


def _hours(value, default: list) -> list:
    if (isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, str) and TIME_RE.match(v) for v in value)
            and value[0] < value[1]):
        return [value[0], value[1]]
    return list(default)


def _days(value, default: list) -> list:
    days = [d for d in DAYS if isinstance(value, list) and d in value]
    return days or list(default)


def clean(raw) -> dict:
    """Settings as saved (or from the dashboard), with anything missing or out of range set to the default."""
    raw = raw if isinstance(raw, dict) else {}
    cb, fu, mt = _part(raw, "callbacks"), _part(raw, "follow_ups"), _part(raw, "meetings")
    d_cb, d_fu, d_mt = DEFAULTS["callbacks"], DEFAULTS["follow_ups"], DEFAULTS["meetings"]
    rules = {}
    given_rules = _part(fu, "rules")
    for status in FOLLOWED_UP:
        given, default = _part(given_rules, status), d_fu["rules"][status]
        rules[status] = {"count": _int(given.get("count"), default["count"], 0, 5),
                         "every": _int(given.get("every"), default["every"], 1, 14)}
    link = str(mt.get("link") or "").strip()
    template = str(mt.get("whatsapp_template") or "").strip().lower()
    language = str(mt.get("template_language") or "").strip()
    return {
        "timezone": str(zone_of(raw.get("timezone"))),
        "from_number_id": raw.get("from_number_id") if isinstance(raw.get("from_number_id"), str) and raw.get("from_number_id") else None,
        "callbacks": {
            "enabled": _bool(cb.get("enabled"), d_cb["enabled"]),
            "hours": _hours(cb.get("hours"), d_cb["hours"]),
            "attempts": _int(cb.get("attempts"), d_cb["attempts"], 1, 5),
            "retry_minutes": _one_of(cb.get("retry_minutes"), d_cb["retry_minutes"], RETRY_MINUTES),
        },
        "follow_ups": {
            "enabled": _bool(fu.get("enabled"), d_fu["enabled"]),
            "review": _bool(fu.get("review"), d_fu["review"]),
            "hours": _hours(fu.get("hours"), d_fu["hours"]),
            "days": _days(fu.get("days"), d_fu["days"]),
            "rules": rules,
            "stop_after_days": _int(fu.get("stop_after_days"), d_fu["stop_after_days"], 1, 30),
            "max_total": _int(fu.get("max_total"), d_fu["max_total"], 1, 10),
            "attempts": _int(fu.get("attempts"), d_fu["attempts"], 1, 3),
        },
        "meetings": {
            "enabled": _bool(mt.get("enabled"), d_mt["enabled"]),
            "approval": _bool(mt.get("approval"), d_mt["approval"]),
            "kinds": [k for k in MEETING_KINDS if k in (mt.get("kinds") or [])] or list(d_mt["kinds"]),
            "minutes": _one_of(mt.get("minutes"), d_mt["minutes"], MEETING_MINUTES),
            "days": _days(mt.get("days"), d_mt["days"]),
            "hours": _hours(mt.get("hours"), d_mt["hours"]),
            "notice_hours": _int(mt.get("notice_hours"), d_mt["notice_hours"], 0, 72),
            "ahead_days": _int(mt.get("ahead_days"), d_mt["ahead_days"], 1, 60),
            "at_once": _int(mt.get("at_once"), d_mt["at_once"], 1, 10),
            "offer_when": str(mt.get("offer_when") or "").strip()[:300],
            "link": link if re.match(r"^https?://\S+$", link) and len(link) <= 500 else "",
            "address": str(mt.get("address") or "").strip()[:300],
            "confirm_call": _bool(mt.get("confirm_call"), d_mt["confirm_call"]),
            "link_minutes": _one_of(mt.get("link_minutes"), d_mt["link_minutes"], LINK_MINUTES),
            "day_before": _bool(mt.get("day_before"), d_mt["day_before"]),
            "no_show_call": _bool(mt.get("no_show_call"), d_mt["no_show_call"]),
            "whatsapp_template": template if re.match(r"^[a-z0-9_]{1,512}$", template) else "",
            "template_language": language if re.match(r"^[a-z]{2,3}(_[A-Z]{2})?$", language) else "en",
        },
    }


def check(raw: dict) -> dict:
    """Settings the owner typed in the dashboard: say what's wrong instead of quietly using a default."""
    raw = raw if isinstance(raw, dict) else {}
    for part, label in (("callbacks", "Call-back"), ("follow_ups", "Follow-up"), ("meetings", "Meeting")):
        hours = _part(raw, part).get("hours")
        if hours is not None and _hours(hours, ["x", "y"]) == ["x", "y"]:
            raise ScheduleError(f"{label} hours need a start before the end, like 09:00 to 21:00")
    if raw.get("timezone") and str(zone_of(raw["timezone"])) != raw["timezone"]:
        raise ScheduleError("Unknown time zone")
    mt = _part(raw, "meetings")
    link = str(mt.get("link") or "").strip()
    if link and not (re.match(r"^https?://\S+$", link) and len(link) <= 500):
        raise ScheduleError("The meeting link should be a full address starting with https://")
    template = str(mt.get("whatsapp_template") or "").strip()
    if template and not re.match(r"^[a-z0-9_]{1,512}$", template.lower()):
        raise ScheduleError("A WhatsApp template name uses lowercase letters, numbers and underscores")
    settings = clean(raw)
    if settings["meetings"]["enabled"] and "in_person" in settings["meetings"]["kinds"] and not settings["meetings"]["address"]:
        raise ScheduleError("Add the address for in-person meetings")
    return settings


async def settings_for(bot_id: str, db: Optional[AsyncSession] = None) -> dict:
    if db is None:
        async with async_session() as session:
            return await settings_for(bot_id, session)
    row = await db.get(ScheduleSettings, bot_id)
    return clean(row.settings if row else None)


# ─── time ─────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc(at: Optional[datetime]) -> Optional[datetime]:
    """A stored time as aware UTC (SQLite gives them back without a zone; they're stored in UTC)."""
    if at is None:
        return None
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)


def stored(at: datetime) -> datetime:
    """How times are written: UTC without a zone, like datetime.utcnow() everywhere else."""
    return at.astimezone(timezone.utc).replace(tzinfo=None)


def _clock_of(hhmm: str) -> dtime:
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


def allowed(at: datetime, hours: list, days: list, tz: ZoneInfo, holidays=()) -> bool:
    local = at.astimezone(tz)
    if DAYS[local.weekday()] not in days or local.date().isoformat() in holidays:
        return False
    return _clock_of(hours[0]) <= local.time().replace(second=0, microsecond=0) < _clock_of(hours[1])


def next_allowed(at: datetime, hours: list, days: list, tz: ZoneInfo, holidays=()) -> datetime:
    """The first moment at or after `at` inside the hours, on an allowed day (aware UTC)."""
    local = at.astimezone(tz)
    for offset in range(0, 22):
        day = local.date() + timedelta(days=offset)
        if DAYS[day.weekday()] not in days or day.isoformat() in holidays:
            continue
        start = datetime.combine(day, _clock_of(hours[0]), tzinfo=tz)
        end = datetime.combine(day, _clock_of(hours[1]), tzinfo=tz)
        if offset == 0:
            if local >= end:
                continue
            return max(start, local).astimezone(timezone.utc)
        return start.astimezone(timezone.utc)
    return at.astimezone(timezone.utc)


def _clock(local: datetime) -> str:
    hour = local.hour % 12 or 12
    return f"{hour}{f':{local.minute:02d}' if local.minute else ''} {'am' if local.hour < 12 else 'pm'}"


def when_text(at: datetime, tz: ZoneInfo, now: Optional[datetime] = None) -> str:
    """'today at 4:40 pm', 'tomorrow at 11 am', 'Friday 31 October at 4 pm', in the business's time zone."""
    local, today = at.astimezone(tz), (now or now_utc()).astimezone(tz).date()
    if local.date() == today:
        day = "today"
    elif local.date() == today + timedelta(days=1):
        day = "tomorrow"
    else:
        day = f"{local:%A} {local.day} {local:%B}"
    return f"{day} at {_clock(local)}"


def hours_text(hours: list) -> str:
    return " to ".join(_clock(datetime.combine(date.today(), _clock_of(h))) for h in hours)


TA_DAYS = ("திங்கள்கிழமை", "செவ்வாய்க்கிழமை", "புதன்கிழமை", "வியாழக்கிழமை", "வெள்ளிக்கிழமை", "சனிக்கிழமை", "ஞாயிற்றுக்கிழமை")
TA_MONTHS = ("ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்",
             "நவம்பர்", "டிசம்பர்")
HI_DAYS = ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार")
HI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")


def spoken_when(at: datetime, tz: ZoneInfo, language: str, now: Optional[datetime] = None) -> str:
    """When something is, the way it's said in the call's language: 'நாளைக்கு காலை 11 மணிக்கு', 'कल सुबह 11 बजे',
    'on Friday 31 October at 4 pm'."""
    local, today = at.astimezone(tz), (now or now_utc()).astimezone(tz).date()
    offset = (local.date() - today).days
    hour = local.hour % 12 or 12
    clock = f"{hour}:{local.minute:02d}" if local.minute else f"{hour}"
    if language == "ta-IN":
        day = "இன்னைக்கு" if offset == 0 else "நாளைக்கு" if offset == 1 else \
            f"{TA_MONTHS[local.month - 1]} {local.day}, {TA_DAYS[local.weekday()]}"
        part = "காலை" if local.hour < 12 else "மதியம்" if local.hour < 16 else "சாயங்காலம்" if local.hour < 19 else "ராத்திரி"
        return f"{day} {part} {clock} மணிக்கு"
    if language == "hi-IN":
        day = "आज" if offset == 0 else "कल" if offset == 1 else f"{HI_DAYS[local.weekday()]}, {local.day} {HI_MONTHS[local.month - 1]} को"
        part = "सुबह" if local.hour < 12 else "दोपहर" if local.hour < 16 else "शाम" if local.hour < 20 else "रात"
        return f"{day} {part} {clock} बजे"
    text = when_text(at, tz, now)
    return text if text.startswith(("today", "tomorrow")) else f"on {text}"


def _day_of(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def local_time(day_text, time_text, tz: ZoneInfo) -> Optional[datetime]:
    """'2026-10-31' and '16:30' (or '4:30 pm') as an aware time in the business's zone; None if either doesn't read."""
    day = _day_of(day_text)
    match = re.match(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]\.?m\.?)?\s*$", str(time_text or ""), re.IGNORECASE)
    if not day or not match:
        return None
    hour, minute, half = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or "").lower()
    if half.startswith("p") and hour < 12:
        hour += 12
    elif half.startswith("a") and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return datetime.combine(day, dtime(hour, minute), tzinfo=tz)


async def holidays(owner_id: str) -> tuple:
    """The workspace's holidays (Settings > Business hours): no follow-ups or meetings on them."""
    try:
        return tuple(assist.hours_config(await assist.workspace(owner_id)).get("holidays") or ())
    except Exception:
        return ()


# ─── who and what's waiting ──────────────────────────────────────
async def contact_of(db: AsyncSession, bot_id: str, e164: str) -> Optional[Contact]:
    return (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalars().first()


async def waiting_job(db: AsyncSession, bot_id: str, e164: str, kind: str) -> Optional[CallbackJob]:
    return (await db.execute(select(CallbackJob).where(
        CallbackJob.bot_id == bot_id, CallbackJob.e164 == e164, CallbackJob.kind == kind,
        CallbackJob.status.in_(WAITING)).order_by(CallbackJob.next_attempt_at))).scalars().first()


async def upcoming_meeting(db: AsyncSession, bot_id: str, e164: str) -> Optional[Meeting]:
    return (await db.execute(select(Meeting).where(
        Meeting.bot_id == bot_id, Meeting.e164 == e164, Meeting.status.in_(("requested", "proposed", "confirmed")),
        Meeting.starts_at > stored(now_utc())).order_by(Meeting.starts_at))).scalars().first()


async def cancel_waiting(db: AsyncSession, bot_id: str, e164: str, reason: str, kinds=KINDS,
                         statuses=WAITING, keep: Optional[str] = None) -> int:
    """Calls (and to-dos) not made yet for one person, called off. `keep`: a job id to leave alone."""
    conditions = [CallbackJob.bot_id == bot_id, CallbackJob.e164 == e164, CallbackJob.kind.in_(kinds),
                  CallbackJob.status.in_(statuses)]
    if keep:
        conditions.append(CallbackJob.id != keep)
    result = await db.execute(update(CallbackJob).where(*conditions).values(status="cancelled", last_error=reason[:300])
                              .execution_options(synchronize_session=False))
    return result.rowcount or 0


async def on_dnc(db: AsyncSession, owner_id: str, e164: str) -> bool:
    return (await db.execute(select(DncEntry.id).where(DncEntry.user_id == owner_id, DncEntry.e164 == e164))).first() is not None


def rate(contact: Contact, status: str, reason: Optional[str], by: Optional[str] = None) -> None:
    """Their lead rating. The assistant never changes a customer the team marked; the team can set anything."""
    if by is None and contact.lead_status == "customer":
        return
    contact.lead_status = status
    contact.lead_reason = (reason or "").strip()[:300] or None
    contact.lead_set_by = by
    contact.lead_at = datetime.utcnow()


# ─── call-backs ───────────────────────────────────────────────────
_IN = re.compile(r"^\s*(?:in\s+|after\s+)?(\d+(?:\.\d+)?)\s*(m|min|mins|minutes?|h|hrs?|hours?)\b", re.IGNORECASE)
_AT = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})?[\sT]*(\d{1,2}(?:[:.]\d{2})?\s*(?:[ap]\.?m\.?)?)?\s*$", re.IGNORECASE)


def _when(args: dict) -> dict:
    """The agent's `when` ("in 10 minutes", "2026-10-30 09:00") as in_minutes, or date and time. A single text field:
    a model sometimes fills a number field in a way Groq's check of the arguments rejects, and the turn is lost."""
    text = str(args.get("when") or "").strip()
    if not text:
        return args
    found = _IN.match(text)
    if found:
        amount = float(found.group(1))
        return {**args, "in_minutes": amount * 60 if found.group(2).lower().startswith("h") else amount}
    found = _AT.match(text)
    if found and (found.group(1) or found.group(2)):
        return {**args, "date": found.group(1), "time": (found.group(2) or "").strip() or None}
    return {**args, "unreadable": True}


def callback_time(args: dict, settings: dict, now: Optional[datetime] = None) -> tuple[Optional[datetime], str]:
    """When to call back, from what the agent heard: (the time, "") or (None, what to tell the caller instead)."""
    tz, hours = zone(settings), settings["callbacks"]["hours"]
    now = now or now_utc()
    args = _when(args)
    if args.get("unreadable"):
        return None, "Give when as 'in N minutes' or as 'YYYY-MM-DD HH:MM', then try again."
    minutes = args.get("in_minutes")
    try:
        minutes = float(minutes) if minutes not in (None, "") else None
    except (TypeError, ValueError):
        minutes = None
    if minutes is not None and minutes > 0:
        at = now + max(timedelta(minutes=minutes), CALLBACK_SOONEST)
    elif args.get("time"):
        at = local_time(args.get("date") or now.astimezone(tz).date().isoformat(), args.get("time"), tz)
        if at is None:
            return None, "That time didn't read. Ask the caller for the day and time again."
    elif args.get("date"):
        return None, "Ask the caller what time on that day suits them, then book it."
    else:
        return None, "Ask the caller when to call them back, then book it."
    if at < now + timedelta(minutes=1):
        return None, "That time has already passed. Ask for a time later today or another day."
    if at > now + CALLBACK_AHEAD:
        return None, "That's too far ahead: call-backs can be booked up to 30 days out. Ask for a sooner time."
    if not allowed(at, hours, DAYS, tz):
        nearest = next_allowed(at, hours, DAYS, tz)
        return None, (f"That's outside calling hours ({hours_text(hours)}). The nearest time is "
                      f"{when_text(nearest, tz, now)}: ask whether that works, and book it if they agree.")
    return at, ""


async def book_callback(*, owner_id: str, bot_id: str, e164: str, at: datetime, about: str, name: Optional[str],
                        source_call_id: Optional[str], number_id: Optional[str], tz: ZoneInfo,
                        created_by: Optional[str] = None, consent: Optional[str] = None) -> CallbackJob:
    """One call-back per person: a newer one replaces the one waiting, and any follow-up planned (it's what they asked
    for instead)."""
    async with async_session() as db:
        job = await waiting_job(db, bot_id, e164, "callback")
        when = stored(at)
        about = (about or "").strip()[:300]
        consent = consent or f"Asked on a call on {now_utc().astimezone(tz):%d %b %Y at %H:%M} to be called back"
        if job is None:
            job = CallbackJob(user_id=owner_id, bot_id=bot_id, e164=e164, kind="callback", consent_source=consent)
            db.add(job)
        job.status, job.attempts, job.last_error = "queued", 0, None
        job.next_attempt_at, job.purpose, job.name = when, about or job.purpose, name or job.name
        job.source_call_id, job.from_number_id, job.created_by = source_call_id, number_id or job.from_number_id, created_by
        await db.flush()
        await cancel_waiting(db, bot_id, e164, "They asked for a call-back instead", kinds=("follow_up",))
        await db.commit()
        return job


# ─── after a call ─────────────────────────────────────────────────
async def after_call(call_id: str) -> None:
    """After a phone call: the person's lead rating and what happens next (a follow-up, a call-back the agent agreed to,
    a to-do for the team), replacing what was planned before. Best effort; never raises."""
    try:
        async with async_session() as db:
            await _after_call(db, call_id)
            await db.commit()
            requests = db.info.pop("tell_team", [])
        from voice import meetings
        for meeting_id in requests:  # once it's saved
            await meetings.notify_team(meeting_id, "requested")
    except Exception as e:
        logger.warning(f"Planning what follows call {call_id} failed: {e}")


async def _after_call(db: AsyncSession, call_id: str) -> None:
    call = await db.get(CallLog, call_id)
    if not call or call.channel != "phone" or not call.caller_e164 or not call.bot_id:
        return
    settings = await settings_for(call.bot_id, db)
    source = (await db.execute(select(CallbackJob).where(CallbackJob.call_id == call.id))).scalars().first()
    if call.outcome == "opted_out":
        await cancel_waiting(db, call.bot_id, call.caller_e164, "They asked not to be called again")
        contact = await contact_of(db, call.bot_id, call.caller_e164)
        if contact is not None:
            rate(contact, "not_interested", "Asked not to be contacted again")
        return
    if call.outcome in ("no_answer", "voicemail", "failed", "in_progress"):
        if source is not None and source.kind == "follow_up":
            await next_follow_up(db, source, settings)  # picked up but said nothing, or a machine: the next one
        return
    step = call.next_step or {}
    await _mark_handled(db, call, settings, step.get("handled") or [])
    contact = await contact_of(db, call.bot_id, call.caller_e164)
    if contact is not None and call.lead in FOLLOWED_UP + ("not_interested",):
        rate(contact, call.lead, step.get("reason"))
    await _agreed_callback(db, call, settings, step)
    await _agreed_meeting(db, call, settings, step)
    if call.outcome == "transferred":  # a person has them now: nothing more from the assistant
        await cancel_waiting(db, call.bot_id, call.caller_e164, "Handed over to a person", kinds=("follow_up",),
                             statuses=("queued", "review"))
        return
    if step.get("person"):
        await _person_todo(db, call, contact)
    await plan_follow_up(db, call, contact, settings)


async def _agreed_callback(db: AsyncSession, call: CallLog, settings: dict, step: dict) -> None:
    """They asked to be called back at a time, or on a day ("call me next Monday"), and the agent didn't book it during
    the call: book it now (it's what they asked for). A day without a time: about the hour they called."""
    if not (step.get("call_back_at") or step.get("on")) or not settings["callbacks"]["enabled"]:
        return
    booked = (await db.execute(select(CallbackJob.id).where(
        CallbackJob.source_call_id == call.id, CallbackJob.kind == "callback"))).first()
    if booked:
        return
    tz, hours, now = zone(settings), settings["callbacks"]["hours"], now_utc()
    day, _, clock = str(step.get("call_back_at") or "").strip().partition(" ")
    at = local_time(day, clock, tz) if clock else None
    named = _day_of(step.get("on"))
    if at is None and named and named > now.astimezone(tz).date():
        at = _their_hour(named, utc(call.started_at), hours, tz, call.caller_e164)
    if at is None or at < now + timedelta(minutes=1) or at > now + CALLBACK_AHEAD:
        return
    at = next_allowed(at, hours, DAYS, tz)
    contact = await contact_of(db, call.bot_id, call.caller_e164)
    job = await waiting_job(db, call.bot_id, call.caller_e164, "callback")
    if job is None:
        job = CallbackJob(user_id=call.user_id, bot_id=call.bot_id, e164=call.caller_e164, kind="callback", status="queued",
                          consent_source=f"Asked on a call on {utc(call.started_at).astimezone(tz):%d %b %Y at %H:%M} to be called back")
        db.add(job)
    job.next_attempt_at, job.attempts, job.last_error = stored(at), 0, None
    job.purpose = (step.get("brief") or call.summary or "")[:300] or None
    job.name, job.source_call_id, job.from_number_id = contact.name if contact else None, call.id, call.number_id
    await cancel_waiting(db, call.bot_id, call.caller_e164, "They asked for a call-back instead", kinds=("follow_up",))
    logger.info(f"Call {call.id}: booked the call-back the agent agreed to, for {at.isoformat()}")


async def _agreed_meeting(db: AsyncSession, call: CallLog, settings: dict, step: dict) -> None:
    """They agreed on the call to meet the team at a time, but the agent didn't book it (models sometimes say "you're
    booked" without doing it): the request is made now, for the team to approve or move."""
    if not step.get("meeting_at") or not settings["meetings"]["enabled"]:
        return
    booked = (await db.execute(select(Meeting.id).where(Meeting.source_call_id == call.id))).first()
    if booked or await upcoming_meeting(db, call.bot_id, call.caller_e164):
        return
    tz, now = zone(settings), now_utc()
    day, _, clock = str(step["meeting_at"]).strip().partition(" ")
    at = local_time(day, clock, tz) if clock else None
    if at is None or at <= now or at > now + timedelta(days=settings["meetings"]["ahead_days"] + 1):
        return
    kinds = settings["meetings"]["kinds"]
    contact = await contact_of(db, call.bot_id, call.caller_e164)
    meeting = Meeting(user_id=call.user_id, bot_id=call.bot_id, e164=call.caller_e164, starts_at=stored(at),
                      kind=step.get("meeting_kind") if step.get("meeting_kind") in kinds else kinds[0],
                      topic=(step.get("meeting_about") or "").strip()[:300] or None, minutes=settings["meetings"]["minutes"],
                      status="requested", source_call_id=call.id, name=contact.name if contact else None,
                      email=contact.email if contact else None,
                      history=[{"at": now.isoformat(), "what": f"Agreed on a call for {when_text(at, tz, now)} (taken from the "
                                "call: the agent didn't book it during the call)", "by": None}])
    db.add(meeting)
    await db.flush()
    await cancel_waiting(db, call.bot_id, call.caller_e164, "They booked a meeting", kinds=("follow_up",))
    db.info.setdefault("tell_team", []).append(meeting.id)
    logger.info(f"Call {call.id}: made the meeting request the caller agreed to, for {at.isoformat()}")


async def _person_todo(db: AsyncSession, call: CallLog, contact: Optional[Contact]) -> None:
    """They asked for a person to call them: one open to-do for the team per person."""
    todo = await waiting_job(db, call.bot_id, call.caller_e164, "person")
    if todo is None:
        todo = CallbackJob(user_id=call.user_id, bot_id=call.bot_id, e164=call.caller_e164, kind="person", status="todo",
                           consent_source="Asked for a person to call them back")
        db.add(todo)
    todo.next_attempt_at, todo.source_call_id = datetime.utcnow(), call.id
    todo.purpose = (call.summary or "They asked for a person to call them back.")[:600]
    todo.name = (contact.name if contact else None) or todo.name


def _their_hour(day: date, last: Optional[datetime], hours: list, tz: ZoneInfo, e164: str) -> datetime:
    """A follow-up's time on a day: about the hour they last picked up, inside the follow-up hours; else an hour after
    they open. A few minutes' spread per person, so follow-ups don't all start at once."""
    spread = int(hashlib.sha256(e164.encode()).hexdigest(), 16) % 15
    start, end = _clock_of(hours[0]), _clock_of(hours[1])
    picked = last.astimezone(tz).time().replace(second=0, microsecond=0) if last else None
    if picked is None or not (start <= picked < end):
        picked = (datetime.combine(day, start) + timedelta(hours=1)).time()
    at = datetime.combine(day, picked, tzinfo=tz) + timedelta(minutes=spread)
    latest = datetime.combine(day, end, tzinfo=tz) - timedelta(minutes=15)
    return min(at, max(latest, datetime.combine(day, start, tzinfo=tz))).astimezone(timezone.utc)


async def _follow_up_allowed(db: AsyncSession, bot_id: str, owner_id: str, e164: str, contact: Optional[Contact],
                             settings: dict) -> bool:
    fu = settings["follow_ups"]
    if not fu["enabled"] or contact is None or contact.follow_ups_off or contact.lead_status not in FOLLOWED_UP:
        return False
    if (contact.follow_ups or 0) >= fu["max_total"] or fu["rules"][contact.lead_status]["count"] < 1:
        return False
    agent = await db.get(VoiceAgent, bot_id)
    if agent is not None and agent.remember_callers is False:
        return False  # follow-ups build on what the assistant remembers about them
    for kind in ("callback", "person"):
        if await waiting_job(db, bot_id, e164, kind):
            return False  # a call-back they asked for, or a person to call them, comes first
    return not (await upcoming_meeting(db, bot_id, e164) or await on_dnc(db, owner_id, e164))


async def plan_follow_up(db: AsyncSession, call: CallLog, contact: Optional[Contact], settings: dict) -> None:
    """The next follow-up after a conversation, by their rating and the rules; anything planned earlier is replaced."""
    await cancel_waiting(db, call.bot_id, call.caller_e164, "Replaced after a newer conversation", kinds=("follow_up",),
                         statuses=("queued", "review"))
    await db.flush()
    if not await _follow_up_allowed(db, call.bot_id, call.user_id, call.caller_e164, contact, settings):
        return
    fu, tz = settings["follow_ups"], zone(settings)
    rule = fu["rules"][contact.lead_status]
    step = call.next_step or {}
    last = utc(call.started_at) or now_utc()
    today = now_utc().astimezone(tz).date()
    named = _day_of(step.get("on"))
    variables: dict = {"step": 0}
    if named and today < named <= today + timedelta(days=NAMED_DAY_AHEAD):
        due = _their_hour(named, last, fu["hours"], tz, call.caller_e164)  # the day they said: they agreed to that
        variables["on"] = named.isoformat()
    else:
        due = _their_hour(last.astimezone(tz).date() + timedelta(days=rule["every"]), last, fu["hours"], tz, call.caller_e164)
        if due - last > timedelta(days=fu["stop_after_days"]):
            return
    due = next_allowed(due, fu["hours"], fu["days"], tz, await holidays(call.user_id))
    test = (call.consent_source or "").startswith(TEST_CALL)
    brief = (step.get("brief") or "").strip() or (
        f"Follow up on their last call ({(call.summary or 'an enquiry').strip()}). Ask whether they have questions or want to go ahead.")
    db.add(CallbackJob(
        user_id=call.user_id, bot_id=call.bot_id, e164=call.caller_e164, name=contact.name, kind="follow_up",
        status="review" if fu["review"] or test else "queued",  # a test call's follow-up never dials by itself
        next_attempt_at=stored(due), purpose=brief[:600], variables=variables, source_call_id=call.id,
        from_number_id=call.number_id,
        consent_source=f"Follow-up after their call on {last.astimezone(tz):%d %b %Y} ({LEAD_LABELS[contact.lead_status].lower()} lead)"))


async def next_follow_up(db: AsyncSession, job: CallbackJob, settings: Optional[dict] = None) -> None:
    """A follow-up nobody answered (every attempt): the next one in the rules, if any is left."""
    settings = settings or await settings_for(job.bot_id, db)
    contact = await contact_of(db, job.bot_id, job.e164)
    if not await _follow_up_allowed(db, job.bot_id, job.user_id, job.e164, contact, settings):
        return
    others = (await db.execute(select(CallbackJob.id).where(
        CallbackJob.bot_id == job.bot_id, CallbackJob.e164 == job.e164, CallbackJob.kind == "follow_up",
        CallbackJob.status.in_(("queued", "review", "calling")), CallbackJob.id != job.id))).first()
    if others:
        return
    fu, tz = settings["follow_ups"], zone(settings)
    rule = fu["rules"][contact.lead_status]
    step = int((job.variables or {}).get("step") or 0) + 1
    if step >= rule["count"]:
        return
    last = max([t for t in (utc(contact.last_call_at), utc(contact.last_chat_at)) if t], default=None)
    due = _their_hour(now_utc().astimezone(tz).date() + timedelta(days=rule["every"]), last, fu["hours"], tz, job.e164)
    if last and due - last > timedelta(days=fu["stop_after_days"]):
        return
    due = next_allowed(due, fu["hours"], fu["days"], tz, await holidays(job.user_id))
    db.add(CallbackJob(
        user_id=job.user_id, bot_id=job.bot_id, e164=job.e164, name=job.name, kind="follow_up",
        status="review" if fu["review"] else "queued", next_attempt_at=stored(due), purpose=job.purpose,
        variables={**(job.variables or {}), "step": step}, source_call_id=job.source_call_id,
        from_number_id=job.from_number_id, consent_source=job.consent_source))


# ─── dialling ─────────────────────────────────────────────────────
@dataclass
class DialCheck:
    stop: Optional[tuple[str, str]] = None   # don't call: (status, why)
    wait_until: Optional[datetime] = None    # not yet: try again then (stored form)
    from_number_id: Optional[str] = None
    attempts: int = 1


def retry_gap(job: CallbackJob, settings: dict) -> timedelta:
    """How long after an unanswered attempt to try again."""
    if job.kind == "callback":
        return timedelta(minutes=settings["callbacks"]["retry_minutes"])
    if job.kind == "meeting":
        return timedelta(minutes=30)
    return FOLLOW_UP_RETRY


def attempts_for(job: CallbackJob, settings: dict) -> int:
    if job.kind == "callback":
        return settings["callbacks"]["attempts"]
    if job.kind == "follow_up":
        return settings["follow_ups"]["attempts"]
    return 3 if job.kind == "meeting" else 2


async def _from_number(db: AsyncSession, job: CallbackJob, settings: dict) -> Optional[str]:
    """The number they called (so they know who's calling back), else the one chosen for the assistant, else the
    assistant's own, else the website call-back number, else the workspace's first."""
    def usable(n: Optional[PhoneNumber]) -> bool:
        return bool(n and n.user_id == job.user_id and n.status == "active" and n.e164)
    for number_id in (job.from_number_id, settings.get("from_number_id")):
        if number_id and usable(await db.get(PhoneNumber, number_id)):
            return number_id
    active = select(PhoneNumber).where(PhoneNumber.user_id == job.user_id, PhoneNumber.status == "active",
                                       PhoneNumber.e164.is_not(None))
    own = (await db.execute(active.where(PhoneNumber.bot_id == job.bot_id).order_by(PhoneNumber.created_at))).scalars().first()
    if own:
        return own.id
    cb = (await db.execute(select(CallbackSettings).where(CallbackSettings.user_id == job.user_id))).scalars().first()
    if cb and cb.from_number_id and usable(await db.get(PhoneNumber, cb.from_number_id)):
        return cb.from_number_id
    first = (await db.execute(active.order_by(PhoneNumber.created_at))).scalars().first()
    return first.id if first else None


async def _called_today(db: AsyncSession, job: CallbackJob, tz: ZoneInfo, now: datetime) -> bool:
    """Spoke with them on a call we made today (unanswered tries don't count: a follow-up gets its retries)."""
    midnight = datetime.combine(now.astimezone(tz).date(), dtime(0), tzinfo=tz)
    return (await db.execute(select(CallLog.id).where(
        CallLog.bot_id == job.bot_id, CallLog.caller_e164 == job.e164, CallLog.direction == "outbound",
        CallLog.started_at >= stored(midnight),
        CallLog.outcome.notin_(("no_answer", "voicemail", "failed", "in_progress"))))).first() is not None


async def _follow_up_stale(db: AsyncSession, job: CallbackJob, settings: dict, now: datetime) -> Optional[str]:
    """Why a planned follow-up shouldn't happen any more, or None."""
    fu = settings["follow_ups"]
    contact = await contact_of(db, job.bot_id, job.e164)
    if contact is None:
        return "They're no longer in Contacts"
    if contact.follow_ups_off:
        return "Follow-ups were stopped for them"
    if contact.lead_status not in FOLLOWED_UP:
        return f"They're now marked {LEAD_LABELS.get(contact.lead_status, 'not rated').lower()}"
    last = max([t for t in (utc(contact.last_call_at), utc(contact.last_chat_at)) if t], default=None)
    created = utc(job.created_at)
    if last and created and last > created:
        return "They spoke with you after this was planned"
    if last and not (job.variables or {}).get("on") and now - last > timedelta(days=fu["stop_after_days"]):
        return f"More than {fu['stop_after_days']} days since they last spoke with you"
    if (contact.follow_ups or 0) >= fu["max_total"]:
        return "They've had the most follow-ups allowed"
    if await upcoming_meeting(db, job.bot_id, job.e164):
        return "They have a meeting booked"
    return None


def meeting_call(job: CallbackJob, meeting: Optional[Meeting], now: datetime) -> Optional[str]:
    """What a meeting call is for, if it still makes sense: confirmed, proposed (another time), declined (find
    another time). None when the meeting changed since the call was planned."""
    about = (job.variables or {}).get("about")
    if meeting is None or about not in ("confirmed", "proposed", "declined"):
        return None
    future = utc(meeting.starts_at) > now
    if about == "confirmed" and meeting.status == "confirmed" and future:
        return "meeting_confirmed"
    if about == "proposed" and meeting.status == "proposed" and future:
        return "meeting_proposed"
    if about == "declined" and meeting.status in ("cancelled", "expired"):
        return "meeting_declined"
    return None


async def dial_check(db: AsyncSession, job: CallbackJob, now: Optional[datetime] = None) -> DialCheck:
    """Whether a Schedule call should be dialled now, from which number, and how many tries it gets."""
    now = now or now_utc()
    if await on_dnc(db, job.user_id, job.e164):
        return DialCheck(stop=("cancelled", "Number is on the do-not-call list"))
    settings = await settings_for(job.bot_id, db)
    tz, off = zone(settings), ()
    hours, days = settings["callbacks"]["hours"], DAYS
    # Call-backs and meeting calls already promised are made even if the switch that lets the agent book them is turned
    # off later; follow-ups are the business's own idea, so they stop with theirs.
    if job.kind == "follow_up":
        fu = settings["follow_ups"]
        if not fu["enabled"]:
            return DialCheck(stop=("cancelled", "Follow-ups are turned off"))
        stale = await _follow_up_stale(db, job, settings, now)
        if stale:
            return DialCheck(stop=("cancelled", stale))
        hours, days, off = fu["hours"], fu["days"], await holidays(job.user_id)
        if await _called_today(db, job, tz, now):  # once a day at most
            tomorrow = datetime.combine(now.astimezone(tz).date() + timedelta(days=1), dtime(0), tzinfo=tz)
            return DialCheck(wait_until=stored(next_allowed(tomorrow, hours, days, tz, off)))
    elif job.kind in ("meeting", "no_show"):
        meeting = await db.get(Meeting, job.meeting_id) if job.meeting_id else None
        if meeting is None or meeting.user_id != job.user_id:
            return DialCheck(stop=("cancelled", "The meeting was deleted"))
        if job.kind == "meeting" and meeting_call(job, meeting, now) is None:
            return DialCheck(stop=("cancelled", "The meeting changed since this call was planned"))
        if job.kind == "no_show" and meeting.status != "no_show":
            return DialCheck(stop=("cancelled", "The meeting is no longer marked as missed"))
    if not allowed(now, hours, days, tz, off):
        return DialCheck(wait_until=stored(next_allowed(now, hours, days, tz, off)))
    from_id = await _from_number(db, job, settings)
    if not from_id:
        return DialCheck(stop=("failed", "No active number to call from"))
    return DialCheck(from_number_id=from_id, attempts=attempts_for(job, settings))


# ─── what a Schedule call says ────────────────────────────────────
# Its opening, after the "automated assistant" line: (with their name, without). Languages without one keep the
# agent's usual opening; the call's purpose still tells the agent what to do.
OPENINGS = {
    "callback": {
        "en-IN": ("Hi {name}, calling you back as you asked. Is this a good time to talk?",
                  "Hi, calling you back as you asked. Is this a good time to talk?"),
        "ta-IN": ("வணக்கம் {name}, நீங்க சொன்னபடி திரும்ப கூப்பிடுறேன். இப்போ பேசலாமா?",
                  "வணக்கம், நீங்க சொன்னபடி திரும்ப கூப்பிடுறேன். இப்போ பேசலாமா?"),
        "hi-IN": ("नमस्ते {name} जी, आपके कहने पर आपको वापस कॉल किया है। क्या अभी बात हो सकती है?",
                  "नमस्ते, आपके कहने पर आपको वापस कॉल किया है। क्या अभी बात हो सकती है?"),
    },
    "follow_up": {
        "en-IN": ("Hi {name}, I'm following up on our last conversation. Is this a good time to talk?",
                  "Hi, I'm following up on our last conversation. Is this a good time to talk?"),
        "ta-IN": ("வணக்கம் {name}, போன தடவை நாம பேசினதைப் பத்தி கேட்க கூப்பிட்டேன். இப்போ பேசலாமா?",
                  "வணக்கம், போன தடவை நாம பேசினதைப் பத்தி கேட்க கூப்பிட்டேன். இப்போ பேசலாமா?"),
        "hi-IN": ("नमस्ते {name} जी, पिछली बार की हमारी बातचीत के सिलसिले में कॉल किया है। क्या अभी बात हो सकती है?",
                  "नमस्ते, पिछली बार की हमारी बातचीत के सिलसिले में कॉल किया है। क्या अभी बात हो सकती है?"),
    },
    "meeting_confirmed": {
        "en-IN": ("Hi {name}, good news: your meeting with us {when} is confirmed. Does that time still work for you?",
                  "Hi, good news: your meeting with us {when} is confirmed. Does that time still work for you?"),
        "ta-IN": ("வணக்கம் {name}, உங்க meeting {when} confirm ஆயிடுச்சு. அந்த நேரம் உங்களுக்கு சரியா இருக்குமா?",
                  "வணக்கம், உங்க meeting {when} confirm ஆயிடுச்சு. அந்த நேரம் உங்களுக்கு சரியா இருக்குமா?"),
        "hi-IN": ("नमस्ते {name} जी, आपकी मीटिंग {when} कन्फ़र्म हो गई है। क्या वो समय आपके लिए ठीक है?",
                  "नमस्ते, आपकी मीटिंग {when} कन्फ़र्म हो गई है। क्या वो समय आपके लिए ठीक है?"),
    },
    "meeting_proposed": {
        "en-IN": ("Hi {name}, about the meeting you asked for: that time isn't free, but we can meet {when}. Would that work for you?",
                  "Hi, about the meeting you asked for: that time isn't free, but we can meet {when}. Would that work for you?"),
        "ta-IN": ("வணக்கம் {name}, நீங்க கேட்ட meeting நேரம் free இல்லை, ஆனா {when} வைக்கலாம். அது உங்களுக்கு சரியா?",
                  "வணக்கம், நீங்க கேட்ட meeting நேரம் free இல்லை, ஆனா {when} வைக்கலாம். அது உங்களுக்கு சரியா?"),
        "hi-IN": ("नमस्ते {name} जी, आपने जिस समय मीटिंग माँगी थी वो खाली नहीं है, पर {when} मिल सकते हैं। क्या वो ठीक रहेगा?",
                  "नमस्ते, आपने जिस समय मीटिंग माँगी थी वो खाली नहीं है, पर {when} मिल सकते हैं। क्या वो ठीक रहेगा?"),
    },
    "meeting_declined": {
        "en-IN": ("Hi {name}, about the meeting you asked for {when}: the team can't make that time. Can we find another time that works for you?",
                  "Hi, about the meeting you asked for {when}: the team can't make that time. Can we find another time that works for you?"),
        "ta-IN": ("வணக்கம் {name}, நீங்க {when} கேட்ட meeting-க்கு team-ஆல வர முடியல. வேற ஒரு நேரம் பாக்கலாமா?",
                  "வணக்கம், நீங்க {when} கேட்ட meeting-க்கு team-ஆல வர முடியல. வேற ஒரு நேரம் பாக்கலாமா?"),
        "hi-IN": ("नमस्ते {name} जी, आपने {when} जो मीटिंग माँगी थी, उस समय टीम नहीं मिल पाएगी। क्या कोई और समय देख लें?",
                  "नमस्ते, आपने {when} जो मीटिंग माँगी थी, उस समय टीम नहीं मिल पाएगी। क्या कोई और समय देख लें?"),
    },
    "no_show": {
        "en-IN": ("Hi {name}, we missed you at the meeting {when}. Would you like to pick another time?",
                  "Hi, we missed you at the meeting {when}. Would you like to pick another time?"),
        "ta-IN": ("வணக்கம் {name}, {when} meeting-ல உங்களை பார்க்க முடியல. வேற ஒரு நேரம் வைக்கலாமா?",
                  "வணக்கம், {when} meeting-ல உங்களை பார்க்க முடியல. வேற ஒரு நேரம் வைக்கலாமா?"),
        "hi-IN": ("नमस्ते {name} जी, {when} की मीटिंग में आप नहीं आ पाए। क्या कोई और समय रख लें?",
                  "नमस्ते, {when} की मीटिंग में आप नहीं आ पाए। क्या कोई और समय रख लें?"),
    },
}


@dataclass
class CallPlan:
    """What a Schedule call is for: the agent's instructions (`purpose`), its opening line, and the language to start
    in (the one they spoke last time, when the agent follows callers' languages)."""
    purpose: str
    greeting: Optional[str] = None
    language: Optional[str] = None


async def plan_inputs(job: CallbackJob) -> tuple[dict, Optional[Meeting]]:
    """What plan_for needs, looked up on its own connection (the call's other lookups run beside it)."""
    async with async_session() as db:
        settings = await settings_for(job.bot_id, db)
        meeting = await db.get(Meeting, job.meeting_id) if job.meeting_id else None
        channels = None
        if meeting is not None:
            from voice import meetings
            channels = await meetings.channels_for(db, meeting, settings)
    return {**settings, "_channels": channels}, meeting


def plan_for(job: CallbackJob, settings: dict, meeting: Optional[Meeting], agent: VoiceAgent, caller: Optional[dict],
             business: str) -> CallPlan:
    tz, now = zone(settings), now_utc()
    language = agent.language or "en-IN"
    last = (caller or {}).get("language")
    allowed_languages = set(agent.switch_languages or [])
    if (last and last != language and agent.follow_caller_language is not False
            and (not allowed_languages or last in allowed_languages)):
        language = last  # they spoke it last time: start there
    from voice.memory import first_name
    name = (caller or {}).get("first_name") or first_name(job.name) or ""
    kind = job.kind if job.kind != "meeting" else meeting_call(job, meeting, now)
    if job.kind in ("meeting", "no_show") and (meeting is None or kind is None):
        # The meeting changed or went away after the phone started ringing.
        return CallPlan(purpose="A call about the meeting they asked for. Ask how you can help, and offer to book a time.")
    when = utc(meeting.starts_at) if meeting is not None else None
    templates = OPENINGS.get(kind, {}).get(language)
    greeting = None
    if templates:
        greeting = (templates[0] if name else templates[1]).format(
            name=name, when=spoken_when(when, tz, language, now) if when else "")
    about = (job.purpose or "").strip()
    if kind == "callback":
        purpose = (f"They asked you to call them back{f' (about: {about})' if about else ''}. Ask whether now is a good "
                   "time; if it isn't, offer to call back later and book it.")
    elif kind == "follow_up":
        purpose = (f"A follow-up on their earlier conversation with {business}. What to do on this call: {about or 'see if they have questions or want to go ahead.'} "
                   "Keep it short and respect their time; if they aren't interested, thank them and end the call.")
    elif kind == "no_show":
        purpose = (f"They had a {MEETING_LABELS.get(meeting.kind, '')} meeting with {business} {when_text(when, tz, now)} "
                   f"but didn't join. Be kind: ask if all is well and whether they'd like another time, and book it if they do.")
    elif kind == "meeting_proposed":
        purpose = (f"They asked for a meeting, but that time wasn't free, so the team proposed {when_text(when, tz, now)} instead. "
                   "Ask if it works. If yes, book exactly that date and time with book_meeting; if not, check other free "
                   "times and book the one they choose.")
    elif kind == "meeting_declined":
        purpose = (f"They asked for a meeting {when_text(when, tz, now)}, but the team can't make that time. Help them "
                   "choose another free time (check_meeting_times) and book it (book_meeting).")
    else:
        from voice import meetings
        purpose = (f"Their {MEETING_LABELS.get(meeting.kind, '')} meeting with {business} {when_text(when, tz, now)} is "
                   f"confirmed by the team. Tell them, and that {meetings.how_they_join(meeting, settings, settings.get('_channels'))}. "
                   "If the time no longer works, help them choose another free time and book it (book_meeting); if they "
                   "want to cancel, cancel it (cancel_meeting).")
    return CallPlan(purpose=purpose, greeting=greeting, language=language if language != agent.language else None)


def apply_plan(call_agent: VoiceAgent, plan: CallPlan) -> None:
    """The call's own opening and language (the agent is a copy for this call)."""
    if plan.language:
        call_agent.language = plan.language
    if plan.greeting:
        call_agent.greeting = plan.greeting


# ─── calls not made yet ───────────────────────────────────────────
# Oct 2026, live: a meeting's confirmation call found the line busy; the person rang straight back and asked four times
# why they'd been called, and the agent, never told about the call, kept asking how it could help (then booked a call-back
# when they said "I called back"). Later the planned retry rang to say what they had heard meanwhile. So a call knows what
# was tried or is due for this person, and the after-call analysis says which of those the conversation took care of.
OPEN_FOR = timedelta(days=3)  # an unanswered call they may still be returning
OPEN_MOST = 5


@dataclass
class OpenCall:
    """A call planned or tried for this person that hasn't reached them yet."""
    id: str                               # the CallbackJob
    label: str                            # how the after-call analysis names it ("call_1")
    about: str                            # what it's for, in words the agent can say
    tried_at: Optional[datetime] = None   # its last try, unanswered
    missed: str = ""                      # why that try didn't reach them
    next_at: Optional[datetime] = None    # when it's due (again)


def _missed(last_error: Optional[str]) -> str:
    status = (last_error or "").rpartition(":")[2].strip().lower()
    return {"busy": "the line was busy", "no-answer": "no answer"}.get(status, "")


def about_call(job: CallbackJob, settings: dict, meeting: Optional[Meeting] = None, campaign=None, business: str = "us",
               channels: Optional[dict] = None, now: Optional[datetime] = None) -> Optional[str]:
    """What a planned call is for, in a few words the agent can tell the person; None when it no longer makes sense."""
    tz, now = zone(settings), now or now_utc()
    purpose = (job.purpose or "").strip()
    if job.kind == "callback":
        return f"the call back they asked for{f' (about: {purpose})' if purpose and purpose.lower() != 'unknown' else ''}"
    if job.kind == "follow_up":
        return f"a follow-up on their earlier conversation with {business}: {purpose or 'whether they have questions or want to go ahead'}"
    if job.kind in ("meeting", "no_show"):
        kind = meeting_call(job, meeting, now) if job.kind == "meeting" else (
            "no_show" if meeting is not None and meeting.status == "no_show" else None)
        if meeting is None or kind is None:
            return None
        when, label = when_text(utc(meeting.starts_at), tz, now), MEETING_LABELS.get(meeting.kind, "")
        if kind == "meeting_confirmed":
            from voice import meetings
            return (f"to tell them their {label} meeting with {business} {when} is confirmed, and that "
                    f"{meetings.how_they_join(meeting, settings, channels)}")
        if kind == "meeting_proposed":
            return (f"to offer {when} for the meeting they asked for, as their time wasn't free; if it works, book exactly "
                    "that time with book_meeting")
        if kind == "meeting_declined":
            return f"to tell them the team can't make the meeting time they asked for ({when}), and help them choose another"
        return f"they missed their {label} meeting {when}: to ask if all is well and offer another time"
    if job.campaign_id:
        from voice.llm import fill
        goal = fill((campaign.purpose or "") if campaign else "", job.variables)
        return f"the {(campaign.name if campaign else '') or 'call'} campaign{f': {goal}' if goal else ''}"
    return "the call they asked for on the website chat"


async def open_calls(db: AsyncSession, bot_id: str, e164: Optional[str], settings: dict, skip: Optional[str] = None,
                     now: Optional[datetime] = None) -> list[OpenCall]:
    """Calls tried for this person in the last few days that didn't reach them, and calls they're expecting (a call-back,
    a meeting call). Not follow-ups or campaign calls that haven't been tried (the person doesn't know of them), not test
    calls, and not `skip` (the call being made now)."""
    if not e164:
        return []
    now = now or now_utc()
    jobs = (await db.execute(select(CallbackJob).where(
        CallbackJob.bot_id == bot_id, CallbackJob.e164 == e164, CallbackJob.status.in_(("queued", "failed")),
        CallbackJob.created_at >= stored(now - timedelta(days=30))).order_by(CallbackJob.created_at.desc()))).scalars().all()
    out: list[OpenCall] = []
    business = None
    for job in jobs:
        if job.id == skip or job.kind == "person" or (job.consent_source or "").startswith(TEST_CALL):
            continue
        tried = None
        if job.attempts and job.provider_call_id:
            tried = (await db.execute(select(CallLog.started_at).where(
                CallLog.provider_call_id == job.provider_call_id, CallLog.outcome == "no_answer"))).scalars().first()
        if tried is None and (job.status == "failed" or job.kind == "follow_up" or job.campaign_id):
            continue  # never tried, or given up without a call: nothing they'd be returning
        if tried is not None and utc(tried) < now - OPEN_FOR:
            continue
        meeting = await db.get(Meeting, job.meeting_id) if job.meeting_id else None
        campaign = None
        if job.campaign_id:
            from backend.models import Campaign
            campaign = await db.get(Campaign, job.campaign_id)
        channels = None
        if meeting is not None and job.kind == "meeting":
            from voice import meetings
            channels = await meetings.channels_for(db, meeting, settings)
        if business is None:
            from voice import meetings
            business = await meetings._business(db, bot_id)
        about = about_call(job, settings, meeting, campaign, business, channels, now)
        if about is None:
            continue
        out.append(OpenCall(id=job.id, label=f"call_{len(out) + 1}", about=about, tried_at=utc(tried) if tried else None,
                            missed=_missed(job.last_error) if tried else "",
                            next_at=utc(job.next_attempt_at) if job.status == "queued" else None))
        if len(out) == OPEN_MOST:
            break
    return out


async def _mark_handled(db: AsyncSession, call: CallLog, settings: dict, ids: list) -> None:
    """Calls planned or tried earlier that this conversation took care of (the after-call analysis says which): done,
    so they aren't made."""
    if not ids:
        return
    local = (utc(call.started_at) or now_utc()).astimezone(zone(settings))
    jobs = (await db.execute(select(CallbackJob).where(
        CallbackJob.id.in_(ids), CallbackJob.bot_id == call.bot_id, CallbackJob.e164 == call.caller_e164,
        CallbackJob.status.in_(("queued", "failed"))))).scalars().all()
    for job in jobs:
        job.status, job.call_id = "done", call.id
        job.last_error = f"Taken care of on their call on {local.day} {local:%b} at {_clock(local)}"
        logger.info(f"Call {call.id} took care of {job.kind or 'call'} {job.id}: it won't be made")


# ─── during a call ────────────────────────────────────────────────
class CallTools:
    """The Schedule functions an agent has on one call: book or cancel a call-back, see free meeting times, ask for,
    move or cancel a meeting. Made when the call starts, with what's already waiting for this caller and the calls tried
    or due for them (`open_calls`); each function's description carries the current time, so "tomorrow at 11" can
    become a date."""

    def __init__(self, settings: dict, *, owner_id: str, bot_id: str, e164: Optional[str], number_id: Optional[str],
                 test: bool = False, upcoming: Optional[dict] = None, name: Optional[str] = None, call_id=None,
                 open_calls: Optional[list[OpenCall]] = None):
        self.settings, self.tz = settings, zone(settings)
        self.owner_id, self.bot_id, self.e164, self.number_id = owner_id, bot_id, e164, number_id
        self.test = test or not e164  # a browser test: nothing is booked
        self.upcoming = dict(upcoming or {})
        self.name = name
        self.call_id = call_id or (lambda: None)
        self.open = list(open_calls or [])
        self.checked_return = False  # a call-back asked for while they may be returning a missed call: checked once

    @property
    def callbacks(self) -> bool:
        return self.settings["callbacks"]["enabled"]

    @property
    def meetings(self) -> bool:
        return self.settings["meetings"]["enabled"]

    def names(self) -> set:
        return {s["name"] for s in self.specs()}

    def has(self, name: str) -> bool:
        return name in self.names()

    def specs(self) -> list[dict]:
        now = now_utc().astimezone(self.tz)
        today = f"Now it's {now:%A} {now.day} {now:%B %Y}, {_clock(now)}."
        out = []
        if self.callbacks:
            hours = self.settings["callbacks"]["hours"]
            out.append({"name": "schedule_callback", "description": (
                "Book a call back to this caller when they ask to be called later or agree to it ('call me after 10 "
                f"minutes', 'call me tomorrow at 11'). Not for someone returning a call you made: answer them. {today} "
                f"Call-backs go out between {hours_text(hours)}; for a time outside them it books nothing and tells you "
                "the nearest time to offer. Then tell them when you'll call."),
                "parameters": {"type": "object", "properties": {
                    "when": {"type": "string", "description": "'in 10 minutes' or 'in 2 hours' for a delay; 'YYYY-MM-DD HH:MM' "
                             "(24 hours) for a set time"},
                    "about": {"type": "string", "description": "What they want to talk about then, from the conversation, "
                              "in a few words (for example 'MBA fees and batch dates')"}},
                    "required": ["when"]}})
            if self.upcoming.get("callback"):
                out.append({"name": "cancel_callback", "description": "Cancel the call back you're due to make to this "
                            "caller, when they say they don't need it any more.",
                            "parameters": {"type": "object", "properties": {}}})
        if self.meetings:
            mt = self.settings["meetings"]
            kinds = ", ".join(MEETING_LABELS[k] for k in mt["kinds"])
            out.append({"name": "check_meeting_times", "description": (
                "Run this as soon as the caller wants a meeting with the team, before asking them anything else: it gives "
                f"the free times to offer ({mt['minutes']}-minute meetings; {kinds}). {today}"),
                "parameters": {"type": "object", "properties": {
                    "date": {"type": "string", "description": "The day they'd like, YYYY-MM-DD; leave out for the next free days"}}}})
            booking = {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM in 24 hours, a free time they agreed to"},
                "topic": {"type": "string", "description": "What they want to talk about, in a few words"},
                "name": {"type": "string", "description": "Their name, if they gave it"},
                "email": {"type": "string", "description": "Only if they ask for the invite by email: spelled out and confirmed"},
            }
            if len(mt["kinds"]) > 1:
                booking["kind"] = {"type": "string", "enum": list(mt["kinds"]), "description": "online, in_person or phone"}
            confirm = ("The team confirms each request, then you'll call them to confirm it." if mt["approval"]
                       else "It's confirmed at once.")
            out.append({"name": "book_meeting", "description": (
                f"Book a meeting with the team at a free time the caller chose, as soon as they choose it. {confirm} If "
                f"they already have a meeting coming up, this moves it. {today}"),
                "parameters": {"type": "object", "properties": booking, "required": ["date", "time"]}})
            if self.upcoming.get("meeting"):
                out.append({"name": "cancel_meeting", "description": "Cancel this caller's upcoming meeting, when they ask to.",
                            "parameters": {"type": "object", "properties": {
                                "reason": {"type": "string", "description": "Why, in a few words, if they said"}}}})
        return out

    def rules(self) -> str:
        """For the instructions: when to use them, and what's already waiting for this caller."""
        lines: list[str] = []
        if self.callbacks:
            lines.append("- If the caller is busy or asks you to call later, book it straight away with schedule_callback "
                         "(it checks the calling hours and tells you the nearest time when theirs is outside them), then "
                         "tell them when. Don't ask for their name or what it's about first: you have their number. Never "
                         "promise a call back you haven't booked.")
        if self.meetings:
            mt = self.settings["meetings"]
            when = mt["offer_when"] or "they're interested and want to discuss details with the team"
            lines.append(f"- Meetings: offer one when {when}. When they want a meeting, your next step is "
                         "check_meeting_times, before you ask anything else. Offer two of the free times it gives. As soon "
                         "as they pick one, book it (book_meeting); ask only for their name first, if you don't have it. "
                         "Collect anything else after it's booked. Don't ask for an email for the meeting: they're "
                         "confirmed on this number. Never offer a time you haven't checked, and never say a meeting is "
                         "booked until book_meeting says so.")
        tz, now = self.tz, now_utc()
        meeting, callback = (self.upcoming.get("meeting"), self.upcoming.get("callback")) if self.callbacks or self.meetings else (None, None)
        if meeting is not None:
            state = {"requested": "waiting for the team to confirm it", "proposed": "the team proposed this time",
                     "confirmed": "confirmed"}.get(meeting.status, meeting.status)
            lines.append(f"- This caller has a {MEETING_LABELS.get(meeting.kind, '')} meeting {when_text(utc(meeting.starts_at), tz, now)} "
                         f"({state}). If they ask, tell them; they can move it or cancel it.")
        if callback is not None and callback.id not in {o.id for o in self.open}:
            lines.append(f"- You're due to call this caller back {when_text(utc(callback.next_attempt_at), tz, now)}.")
        lines += self._open_lines()
        return "\n" + "\n".join(lines) if lines else ""

    def _open_lines(self) -> list[str]:
        """The calls tried or due for this caller, and what to do about them on this call."""
        tz, now = self.tz, now_utc()
        missed = [o for o in self.open if o.tried_at]
        due = [o for o in self.open if not o.tried_at and o.next_at]
        lines = []
        if missed:
            lines.append("- Calls you made to this caller that didn't reach them (they may be returning one):")
            for o in missed:
                again = f" Another try is planned {when_text(o.next_at, tz, now)}." if o.next_at else ""
                lines.append(f"  - {when_text(o.tried_at, tz, now)}{f' ({o.missed})' if o.missed else ''}: {o.about}.{again}")
            lines.append("  If they say they had a call from this number, or ask why you called, tell them at once what it was "
                         "about and take care of it. Returning your call is not asking to be called back. If they called "
                         "about something else, still tell them before the call ends.")
        if due:
            lines.append("- Calls you're due to make to this caller. If what one is for comes up, take care of it now:")
            lines += [f"  - {when_text(o.next_at, tz, now)}: {o.about}." for o in due]
        return lines

    async def run(self, name: str, args: dict) -> str:
        """Never raises: what comes back is for the model to read."""
        try:
            if name == "schedule_callback":
                return await self._callback(args or {})
            if name == "cancel_callback":
                return await self._cancel_callback()
            from voice import meetings
            if name == "check_meeting_times":
                return await meetings.free_times_text(self.settings, self.owner_id, self.bot_id, (args or {}).get("date"))
            if name == "book_meeting":
                return await self._book_meeting(args or {}, meetings)
            if name == "cancel_meeting":
                return await self._cancel_meeting(args or {}, meetings)
        except Exception as e:
            logger.warning(f"Schedule function {name} failed: {e}")
            return "That couldn't be done just now. Tell the caller the team will follow up."
        return f"There's no function called {name}. Answer without it."

    async def _callback(self, args: dict) -> str:
        if any(o.tried_at for o in self.open) and not self.checked_return:
            # Live, Oct 2026: someone saying "I called back" (returning a missed call) got a call-back about "unknown".
            # The first one asked for on such a call goes back to the agent; asked for again, it's booked.
            self.checked_return = True
            return ("Wait: they may be returning the call you made. Tell them what it was about first. If they still want "
                    "a call back after that, book it then.")
        at, problem = callback_time(args, self.settings)
        if at is None:
            return problem
        when = when_text(at, self.tz)
        if self.test:
            return f"This is a test call in the browser, so no call back is booked. On a phone call it would be {when}. Tell the tester that."
        job = await book_callback(owner_id=self.owner_id, bot_id=self.bot_id, e164=self.e164, at=at,
                                  about=str(args.get("about") or ""), name=self.name, source_call_id=self.call_id(),
                                  number_id=self.number_id, tz=self.tz)
        self.upcoming["callback"] = job
        return f"Booked: you'll call them back {when}. Tell them that."

    async def _cancel_callback(self) -> str:
        if self.test:
            return "This is a test call in the browser, so there's nothing to cancel."
        async with async_session() as db:
            done = await cancel_waiting(db, self.bot_id, self.e164, "They said on a call they don't need it", kinds=("callback",))
            await db.commit()
        self.upcoming.pop("callback", None)
        return "Cancelled the call back. Tell them." if done else "There was no call back waiting."

    async def _book_meeting(self, args: dict, meetings) -> str:
        result, meeting = await meetings.book(self.settings, owner_id=self.owner_id, bot_id=self.bot_id, e164=self.e164,
                                              args=args, name=self.name, source_call_id=self.call_id(), test=self.test)
        if meeting is not None:
            self.upcoming["meeting"] = meeting
        return result

    async def _cancel_meeting(self, args: dict, meetings) -> str:
        meeting = self.upcoming.get("meeting")
        if self.test or meeting is None:
            return "There's no meeting to cancel."
        result = await meetings.cancel_by_caller(meeting.id, str(args.get("reason") or ""))
        self.upcoming.pop("meeting", None)
        return result


async def tools_for(owner_id: str, bot_id: str, e164: Optional[str], number_id: Optional[str], *, test: bool = False,
                    name: Optional[str] = None, call_id=None, skip: Optional[str] = None) -> Optional[CallTools]:
    """The Schedule functions for a call starting now, and the calls tried or due for this caller (`skip`: the call
    being made now); None when the assistant has no functions switched on and nothing is waiting."""
    async with async_session() as db:
        settings = await settings_for(bot_id, db)
        waiting = await open_calls(db, bot_id, e164, settings, skip=skip) if e164 and not test else []
        if not (settings["callbacks"]["enabled"] or settings["meetings"]["enabled"] or waiting):
            return None
        upcoming = {}
        if e164:
            upcoming = {"meeting": await upcoming_meeting(db, bot_id, e164),
                        "callback": await waiting_job(db, bot_id, e164, "callback")}
    return CallTools(settings, owner_id=owner_id, bot_id=bot_id, e164=e164, number_id=number_id, test=test,
                     upcoming={k: v for k, v in upcoming.items() if v is not None}, name=name, call_id=call_id,
                     open_calls=waiting)


# ─── overview counts ──────────────────────────────────────────────
async def needs_attention(db: AsyncSession, owner_id: str) -> dict:
    """What's waiting for the team: meetings to approve, follow-ups to check, people who want a person, missed
    meetings to mark."""
    ended = stored(now_utc() - timedelta(minutes=30))
    approve = (await db.execute(select(func.count()).select_from(Meeting).where(
        Meeting.user_id == owner_id, Meeting.status == "requested", Meeting.starts_at > stored(now_utc())))).scalar() or 0
    review = (await db.execute(select(func.count()).select_from(CallbackJob).where(
        CallbackJob.user_id == owner_id, CallbackJob.status == "review"))).scalar() or 0
    people = (await db.execute(select(func.count()).select_from(CallbackJob).where(
        CallbackJob.user_id == owner_id, CallbackJob.kind == "person", CallbackJob.status == "todo"))).scalar() or 0
    mark = (await db.execute(select(func.count()).select_from(Meeting).where(
        Meeting.user_id == owner_id, Meeting.status == "confirmed", Meeting.starts_at < ended))).scalar() or 0
    return {"approve": approve, "review": review, "people": people, "mark": mark,
            "total": approve + review + people + mark}

