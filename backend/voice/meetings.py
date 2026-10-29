"""
Meetings (Voice > Schedule > Meetings), asked for on a call.

  1. The agent checks the free times (`free_times`: the assistant's meeting days and hours, less the workspace's
     holidays, at least `notice_hours` ahead and up to `ahead_days` out, with up to `at_once` meetings at the same
     time) and books the one the caller picks (`book`). It's "requested" and the team is emailed; with approval off,
     it's confirmed there and then.
  2. The team approves it (with its link, or the assistant's default link), proposes another time, or declines it.
     Approving calls the person to confirm it (`confirm_call`) and sends a written confirmation (WhatsApp, and email
     with a calendar invite); another time, or a decline, calls them to agree a time.
  3. Before it starts: a reminder the day before (when it was booked earlier than that) and the link `link_minutes`
     before (WhatsApp: a free message inside WhatsApp's 24-hour window, else the approved template; email when they
     gave one). The host gets the details at the same time.
  4. Afterwards the team marks it attended or missed; a missed one gets a call to pick another time (`no_show_call`).
     A confirmed meeting nobody marks is closed as attended after 3 days; a request nobody answered expires at its time.
Each message goes out once (NotificationLog), however many server processes run the reminders.
"""
import logging
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, CallbackJob, CallLog, Meeting, User, VoiceAgent, WhatsAppChat
from database import async_session
from voice.schedule import (DAYS, MEETING_LABELS, ScheduleError, _clock, _clock_of, _day_of, allowed, cancel_waiting,
                            contact_of, holidays, local_time, next_allowed, now_utc, settings_for, stored,
                            upcoming_meeting, utc, when_text, zone)

logger = logging.getLogger(__name__)

ACTIVE = ("requested", "proposed", "confirmed")
STATUSES = ACTIVE + ("cancelled", "expired", "done", "no_show")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
CLOSE_UNMARKED = timedelta(days=3)  # confirmed meetings nobody marked: closed as attended
IN_PERSON_LEAD = 60                 # minutes: an in-person meeting's reminder (time to travel)


def _history(meeting: Meeting, what: str, by: Optional[str] = None) -> None:
    meeting.history = [*(meeting.history or []), {"at": now_utc().isoformat(), "what": what[:300], "by": by}][-30:]


def starts(meeting: Meeting) -> datetime:
    return utc(meeting.starts_at)


def _ref(meeting: Meeting) -> str:
    """One of each message per meeting time: moving it sends them again."""
    return f"{meeting.id}@{starts(meeting):%Y%m%d%H%M}"


# ─── free times ───────────────────────────────────────────────────
async def _taken(db: AsyncSession, bot_id: str, start: datetime, end: datetime,
                 skip: Optional[str]) -> list[tuple[datetime, datetime]]:
    rows = (await db.execute(select(Meeting).where(
        Meeting.bot_id == bot_id, Meeting.status.in_(ACTIVE), Meeting.starts_at < stored(end),
        Meeting.starts_at > stored(start - timedelta(hours=4))))).scalars().all()
    return [(starts(m), starts(m) + timedelta(minutes=m.minutes or 30)) for m in rows if m.id != skip]


def _fits(at: datetime, minutes: int, taken: list, at_once: int) -> bool:
    end = at + timedelta(minutes=minutes)
    return sum(1 for s, e in taken if s < end and e > at) < at_once


async def free_times(db: AsyncSession, settings: dict, owner_id: str, bot_id: str, first: date, days: int,
                     skip: Optional[str] = None, now: Optional[datetime] = None) -> dict[date, list[datetime]]:
    """Free start times per day, from `first` for `days` days. `skip`: a meeting being moved (its own time is free)."""
    mt, tz = settings["meetings"], zone(settings)
    now = now or now_utc()
    earliest = now + timedelta(hours=mt["notice_hours"])
    last = now.astimezone(tz).date() + timedelta(days=mt["ahead_days"])
    end = min(first + timedelta(days=days), last + timedelta(days=1))
    if end <= first:
        return {}
    taken = await _taken(db, bot_id, datetime.combine(first, dtime(0), tzinfo=tz),
                         datetime.combine(end, dtime(0), tzinfo=tz), skip)
    off = await holidays(owner_id)
    step = timedelta(minutes=min(mt["minutes"], 30))
    out: dict[date, list[datetime]] = {}
    day = first
    while day < end:
        if DAYS[day.weekday()] in mt["days"] and day.isoformat() not in off:
            at = datetime.combine(day, _clock_of(mt["hours"][0]), tzinfo=tz)
            close = datetime.combine(day, _clock_of(mt["hours"][1]), tzinfo=tz)
            slots = []
            while at + timedelta(minutes=mt["minutes"]) <= close:
                if at >= earliest and _fits(at, mt["minutes"], taken, mt["at_once"]):
                    slots.append(at)
                at += step
            if slots:
                out[day] = slots
        day += timedelta(days=1)
    return out


def _spread(slots: list[datetime], count: int) -> list[datetime]:
    """A few times across the day, not just the first ones."""
    if len(slots) <= count:
        return slots
    return [slots[round(i * (len(slots) - 1) / (count - 1))] for i in range(count)]


def _day_text(day: date, today: Optional[date] = None) -> str:
    """'today (Thursday 29 October)', so the agent says "today" rather than the day's name."""
    name = f"{day:%A} {day.day} {day:%B}"
    if today is not None and day in (today, today + timedelta(days=1)):
        return f"{'today' if day == today else 'tomorrow'} ({name})"
    return name


async def free_times_text(settings: dict, owner_id: str, bot_id: str, day_text=None) -> str:
    """For the agent: free times on the day they'd like, or the next free days."""
    tz, mt = zone(settings), settings["meetings"]
    today = now_utc().astimezone(tz).date()
    asked = _day_of(day_text)
    async with async_session() as db:
        if asked:
            if asked < today:
                return "That day has passed. Ask for a day from today on."
            if asked > today + timedelta(days=mt["ahead_days"]):
                return f"Meetings can be booked up to {mt['ahead_days']} days ahead. Ask for a sooner day."
            free = await free_times(db, settings, owner_id, bot_id, asked, 1)
            if free.get(asked):
                return (f"Free on {_day_text(asked, today)}: {', '.join(_clock(t) for t in _spread(free[asked], 6))}. "
                        "Offer two of these.")
            later = await free_times(db, settings, owner_id, bot_id, asked + timedelta(days=1), 7)
            if not later:
                return f"Nothing is free on {_day_text(asked)} or in the week after. Offer to have the team call them instead."
            options = "; ".join(f"{_day_text(d, today)}: {', '.join(_clock(t) for t in _spread(s, 3))}" for d, s in list(later.items())[:2])
            return f"Nothing is free on {_day_text(asked, today)}. The next free times: {options}. Offer two of these."
        free = await free_times(db, settings, owner_id, bot_id, today, mt["ahead_days"] + 1)
    if not free:
        return "No meeting times are free right now. Offer to have the team call them instead."
    options = "; ".join(f"{_day_text(d, today)}: {', '.join(_clock(t) for t in _spread(s, 3))}" for d, s in list(free.items())[:3])
    return f"The next free times: {options}. Offer two of these."


async def _why_not(db: AsyncSession, at: datetime, settings: dict, owner_id: str, bot_id: str, skip: Optional[str],
                   now: datetime) -> Optional[str]:
    """Why a meeting can't be at that time, or None when it can (any start time inside the hours, not only the ones
    free_times lists)."""
    mt, tz = settings["meetings"], zone(settings)
    if at < now + timedelta(hours=mt["notice_hours"]):
        return f"That's too soon: meetings need {mt['notice_hours']} hours' notice."
    if at.astimezone(tz).date() > now.astimezone(tz).date() + timedelta(days=mt["ahead_days"]):
        return f"That's too far ahead: meetings can be booked up to {mt['ahead_days']} days out."
    end = at + timedelta(minutes=mt["minutes"])
    if (not allowed(at, mt["hours"], mt["days"], tz, await holidays(owner_id))
            or end.astimezone(tz).date() != at.astimezone(tz).date() or end.astimezone(tz).time() > _clock_of(mt["hours"][1])):
        days = ", ".join(d.capitalize() for d in mt["days"])
        opens, closes = (_clock(datetime.combine(date.today(), _clock_of(h))) for h in mt["hours"])
        return f"The team meets on {days}, between {opens} and {closes} (not on holidays)."
    if not _fits(at, mt["minutes"], await _taken(db, bot_id, at, end, skip), mt["at_once"]):
        return "That time is taken."
    return None


# ─── booking on a call ───────────────────────────────────────────
async def book(settings: dict, *, owner_id: str, bot_id: str, e164: Optional[str], args: dict, name: Optional[str],
               source_call_id: Optional[str], test: bool) -> tuple[str, Optional[Meeting]]:
    """The caller picked a time: ask for it (or move the meeting they have). Returns what to tell the model, and the
    meeting."""
    mt, tz, now = settings["meetings"], zone(settings), now_utc()
    at = local_time(args.get("date"), args.get("time"), tz)
    if at is None:
        return "Ask the caller for the day and time they want, then check it's free.", None
    kind = args.get("kind") if args.get("kind") in mt["kinds"] else mt["kinds"][0]
    topic = str(args.get("topic") or "").strip()[:300] or None
    person = str(args.get("name") or name or "").strip()[:80] or None
    email = str(args.get("email") or "").strip()[:120]
    email = email if EMAIL_RE.match(email) else None
    async with async_session() as db:
        existing = await upcoming_meeting(db, bot_id, e164) if e164 else None
        day = at.astimezone(tz).date()
        accepting = existing is not None and existing.status == "proposed" and starts(existing) == at
        problem = None if accepting else await _why_not(db, at, settings, owner_id, bot_id,
                                                        existing.id if existing else None, now)
        if problem:
            nearby = await free_times(db, settings, owner_id, bot_id, max(day, now.astimezone(tz).date()), 3, now=now)
            options = "; ".join(f"{_day_text(d)}: {', '.join(_clock(t) for t in _spread(s, 3))}" for d, s in list(nearby.items())[:2])
            return f"{problem} {'Free times: ' + options + '. Offer two of these.' if options else 'Offer to have the team call them instead.'}", None
        when = when_text(at, tz, now)
        if test:
            state = "requested" if mt["approval"] else "confirmed"
            return (f"This is a test call in the browser, so nothing is booked. On a phone call this {MEETING_LABELS[kind]} "
                    f"meeting would be {state} for {when}. Tell the tester that."), None
        if accepting:
            meeting = existing
            meeting.status = "confirmed"
            _history(meeting, "Agreed on a call to the time the team proposed")
        elif existing is not None:
            meeting = existing
            _history(meeting, f"Moved on a call from {when_text(starts(meeting), tz, now)} to {when}")
            meeting.starts_at, meeting.kind = stored(at), kind
            meeting.status = "requested" if mt["approval"] else "confirmed"
            meeting.topic = topic or meeting.topic
        else:
            meeting = Meeting(user_id=owner_id, bot_id=bot_id, e164=e164, kind=kind, topic=topic, starts_at=stored(at),
                              minutes=mt["minutes"], status="requested" if mt["approval"] else "confirmed",
                              source_call_id=source_call_id, history=[])
            _history(meeting, f"Asked for on a call, for {when}")
            db.add(meeting)
        meeting.name = person or meeting.name
        meeting.email = email or meeting.email
        contact = await contact_of(db, bot_id, e164)
        if contact is not None:
            meeting.name = meeting.name or contact.name
            meeting.email = meeting.email or contact.email
            if email and not contact.email:
                contact.email = email
        await db.flush()
        await _cancel_calls(db, meeting.id)
        await cancel_waiting(db, bot_id, e164, "They booked a meeting", kinds=("follow_up",))
        await db.commit()
        meeting_id, confirmed = meeting.id, meeting.status == "confirmed"
        join = how_they_join(meeting, settings, await channels_for(db, meeting, settings)) if confirmed else ""
    from notify.events import fire_and_forget
    if confirmed:
        fire_and_forget(send_confirmation(meeting_id))
        return f"Booked and confirmed: {when}, {MEETING_LABELS[kind]}. Tell them, and that {join}.", meeting
    fire_and_forget(notify_team(meeting_id, "requested"))
    return (f"Requested: {when}, {MEETING_LABELS[kind]}. Tell them the team will confirm it shortly, and they'll get a "
            "call to confirm."), meeting


async def cancel_by_caller(meeting_id: str, reason: str) -> str:
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None or meeting.status not in ACTIVE:
            return "There's no meeting to cancel."
        meeting.status = "cancelled"
        _history(meeting, f"Cancelled by them on a call{': ' + reason.strip()[:200] if reason.strip() else ''}")
        await _cancel_calls(db, meeting.id)
        await db.commit()
    from notify.events import fire_and_forget
    fire_and_forget(notify_team(meeting_id, "cancelled"))
    return "Cancelled. Tell them, and ask whether they'd like another time."


# ─── the team's decisions ─────────────────────────────────────────
async def _cancel_calls(db: AsyncSession, meeting_id: str) -> None:
    """Calls planned about a meeting, called off (it changed)."""
    await db.execute(update(CallbackJob).where(
        CallbackJob.meeting_id == meeting_id, CallbackJob.status.in_(("queued", "review")))
        .values(status="cancelled", last_error="The meeting changed").execution_options(synchronize_session=False))


CALL_PURPOSES = {"confirmed": "Confirm their meeting on {when}", "proposed": "Offer the time the team proposed: {when}",
                 "declined": "Find another time for the meeting they asked for on {when}",
                 "missed": "They missed their meeting on {when}: offer another time"}


async def _call_about(db: AsyncSession, meeting: Meeting, about: str, kind: str = "meeting",
                      at: Optional[datetime] = None) -> None:
    """A call to the person about their meeting (the scheduler waits for calling hours). Its purpose is for the lists;
    the call itself works out what to say from the meeting as it is then (schedule.plan_for)."""
    local = starts(meeting).astimezone(zone(await settings_for(meeting.bot_id, db)))
    when = f"{local:%a} {local.day} {local:%b}, {_clock(local)}"
    number_id = None
    if meeting.source_call_id:
        call = await db.get(CallLog, meeting.source_call_id)
        number_id = call.number_id if call else None
    db.add(CallbackJob(user_id=meeting.user_id, bot_id=meeting.bot_id, e164=meeting.e164, name=meeting.name, kind=kind,
                       meeting_id=meeting.id, variables={"about": about}, status="queued",
                       purpose=CALL_PURPOSES[about].format(when=when),
                       next_attempt_at=stored(at or now_utc()), from_number_id=number_id,
                       source_call_id=meeting.source_call_id,
                       consent_source=f"Asked for a meeting on a call ({meeting.created_at:%d %b %Y})" if meeting.created_at
                       else "Asked for a meeting on a call"))


async def approve(db: AsyncSession, meeting: Meeting, *, by: str, link: Optional[str] = None,
                  host_id: Optional[str] = None) -> None:
    settings = await settings_for(meeting.bot_id, db)
    if meeting.status not in ("requested", "proposed"):
        raise ScheduleError("Only a meeting waiting for an answer can be approved")
    if starts(meeting) <= now_utc():
        raise ScheduleError("That time has passed: propose another time instead")
    link = (link or "").strip()
    if link and meeting.kind == "online" and not re.match(r"^https?://\S+$", link):
        raise ScheduleError("The meeting link should be a full address starting with https://")
    meeting.link = link[:500] or meeting.link
    if meeting.kind == "online" and not (meeting.link or settings["meetings"]["link"]):
        raise ScheduleError("Add the meeting link, or a default link in Schedule settings")
    meeting.host_id = host_id or meeting.host_id
    meeting.status, meeting.decided_by, meeting.decided_at = "confirmed", by, datetime.utcnow()
    _history(meeting, "Approved", by)
    await _cancel_calls(db, meeting.id)
    if settings["meetings"]["confirm_call"]:
        await _call_about(db, meeting, "confirmed")


async def propose(db: AsyncSession, meeting: Meeting, at: datetime, *, by: str) -> None:
    """Another time for a request (or a confirmed meeting the team has to move): the agent calls to agree it."""
    tz = zone(await settings_for(meeting.bot_id, db))
    if meeting.status not in ACTIVE:
        raise ScheduleError("This meeting isn't open any more")
    if at <= now_utc() + timedelta(minutes=30):
        raise ScheduleError("Choose a time at least 30 minutes from now")
    _history(meeting, f"Proposed {when_text(at, tz)} instead of {when_text(starts(meeting), tz)}", by)
    meeting.starts_at, meeting.status = stored(at), "proposed"
    meeting.decided_by, meeting.decided_at = by, datetime.utcnow()
    await _cancel_calls(db, meeting.id)
    await _call_about(db, meeting, "proposed")


async def decline(db: AsyncSession, meeting: Meeting, *, by: str, call: bool, reason: str = "") -> None:
    """The team can't take it. With `call`, the agent calls to find another time."""
    if meeting.status not in ACTIVE:
        raise ScheduleError("This meeting isn't open any more")
    meeting.status, meeting.decided_by, meeting.decided_at = "cancelled", by, datetime.utcnow()
    _history(meeting, f"Declined by the team{': ' + reason.strip()[:200] if reason.strip() else ''}", by)
    await _cancel_calls(db, meeting.id)
    if call:
        await _call_about(db, meeting, "declined")


async def mark(db: AsyncSession, meeting: Meeting, *, by: str, attended: bool) -> None:
    if meeting.status not in ("confirmed", "done", "no_show"):
        raise ScheduleError("Only a confirmed meeting can be marked")
    if starts(meeting) > now_utc():
        raise ScheduleError("It hasn't started yet")
    before = meeting.status
    meeting.status = "done" if attended else "no_show"
    _history(meeting, "Marked as attended" if attended else "Marked as missed", by)
    settings = await settings_for(meeting.bot_id, db)
    if not attended and before != "no_show" and settings["meetings"]["no_show_call"]:
        tz, hours = zone(settings), settings["callbacks"]["hours"]
        await _call_about(db, meeting, "missed", kind="no_show",
                          at=next_allowed(now_utc() + timedelta(hours=1), hours, DAYS, tz))
    if attended:
        await db.execute(update(CallbackJob).where(
            CallbackJob.meeting_id == meeting.id, CallbackJob.kind == "no_show", CallbackJob.status == "queued")
            .values(status="cancelled", last_error="Marked as attended").execution_options(synchronize_session=False))


async def move(db: AsyncSession, meeting: Meeting, at: datetime, *, by: str) -> None:
    """The team moves a confirmed meeting: still confirmed; they're called (and written to) with the new time."""
    settings = await settings_for(meeting.bot_id, db)
    tz = zone(settings)
    if meeting.status != "confirmed":
        raise ScheduleError("Only a confirmed meeting can be moved; propose a time for a request")
    if at <= now_utc() + timedelta(minutes=30):
        raise ScheduleError("Choose a time at least 30 minutes from now")
    _history(meeting, f"Moved by the team from {when_text(starts(meeting), tz)} to {when_text(at, tz)}", by)
    meeting.starts_at = stored(at)
    await _cancel_calls(db, meeting.id)
    if settings["meetings"]["confirm_call"]:
        await _call_about(db, meeting, "confirmed")


# ─── messages ─────────────────────────────────────────────────────
async def _business(db: AsyncSession, bot_id: str) -> str:
    agent = await db.get(VoiceAgent, bot_id)
    if agent is not None and (agent.company_name or "").strip():
        return agent.company_name.strip()
    bot = await db.get(Bot, bot_id)
    return bot.bot_name if bot else "us"


async def _whatsapp_chat(db: AsyncSession, meeting: Meeting):
    from whatsapp.numbers import workspace_number
    number = await workspace_number(db, meeting.user_id)
    if number is None or number.status == "disconnected" or not number.access_token:
        return None, None
    chat = (await db.execute(select(WhatsAppChat).where(
        WhatsAppChat.number_id == number.id, WhatsAppChat.wa_id == meeting.e164.lstrip("+")))).scalars().first()
    return number, chat


async def channels_for(db: AsyncSession, meeting: Meeting, settings: dict) -> dict:
    """How they can be written to: WhatsApp (inside its 24-hour window, or with the approved template) and email."""
    from whatsapp import chats as wa_chats
    number, chat = await _whatsapp_chat(db, meeting)
    whatsapp = None
    if number is not None:
        if chat is not None and wa_chats.window_open(chat):
            whatsapp = "window"
        elif settings["meetings"]["whatsapp_template"]:
            whatsapp = "template"
    return {"whatsapp": whatsapp, "email": bool(meeting.email)}


def _where(channels: Optional[dict]) -> str:
    ways = [w for w, on in (("on WhatsApp", (channels or {}).get("whatsapp")), ("by email", (channels or {}).get("email"))) if on]
    return " and ".join(ways)


def place(meeting: Meeting, settings: dict) -> str:
    """Its link (online) or address (in person)."""
    mt = settings["meetings"]
    if meeting.kind == "online":
        return meeting.link or mt["link"]
    if meeting.kind == "in_person":
        return meeting.link or mt["address"]
    return ""


def how_they_join(meeting: Meeting, settings: dict, channels: Optional[dict]) -> str:
    mt = settings["meetings"]
    if meeting.kind == "in_person":
        return f"it's at {place(meeting, settings) or 'our office'}"
    if meeting.kind == "phone":
        return "the team will call them at that time"
    where = _where(channels)
    if not where:
        return "the team will share the joining link before it starts"
    return f"the joining link will be sent {where} {mt['link_minutes']} minutes before it starts"


def _when_for_people(meeting: Meeting, settings: dict) -> str:
    tz = zone(settings)
    text = when_text(starts(meeting), tz)
    return text if str(tz) == "Asia/Kolkata" else f"{text} ({tz})"


def _texts(meeting: Meeting, settings: dict, business: str, what: str) -> tuple[str, list[str], str]:
    """(the WhatsApp / email text; the template's four values: name, business, when, what's happening; the email
    subject). One approved template fits them all: "Hi {{1}}, about your meeting with {{2}}: {{3}}. {{4}}"."""
    name = (meeting.name or "").split(" ")[0] or "there"
    when, where = _when_for_people(meeting, settings), place(meeting, settings)
    kind = MEETING_LABELS.get(meeting.kind, "")
    minutes = settings["meetings"]["link_minutes"]
    joining = {"online": f"We'll send the joining link {minutes} minutes before it starts.",
               "in_person": f"The address: {where}." if where else "See you there.",
               "phone": "We'll call you then."}[meeting.kind]
    if what == "confirmed":
        note = f"It's confirmed. {joining}"
        text = f"Hi {name}, your {kind} meeting with {business} is confirmed for {when}. {joining}"
        subject = f"Confirmed: your meeting with {business}, {when}"
    elif what == "day_before":
        note = f"A reminder that it's coming up. {joining}"
        text = f"Hi {name}, a reminder: your {kind} meeting with {business} is {when}. {joining}"
        subject = f"Reminder: your meeting with {business}, {when}"
    elif what == "cancelled":
        note = "It has been cancelled. Reply here if you'd like another time."
        text = f"Hi {name}, your meeting with {business} {when} has been cancelled. Reply here if you'd like another time."
        subject = f"Cancelled: your meeting with {business}, {when}"
    else:  # the link, shortly before
        join = {"online": f"Join here: {where}", "in_person": f"The address: {where}." if where else "See you soon.",
                "phone": "We'll call you shortly."}[meeting.kind]
        note = f"It starts soon. {join}"
        text = f"Hi {name}, your meeting with {business} starts soon ({when}). {join}"
        subject = f"Starting soon: your meeting with {business}"
    return text, [name, business, when, note], subject


def ics(meeting: Meeting, settings: dict, business: str) -> str:
    """A calendar invite (.ics), so it lands in their calendar. Its sequence goes up each time the meeting moves."""
    def esc(text: str) -> str:
        return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    def fold(line: str) -> list[str]:  # lines longer than 75 bytes continue on the next, after a space
        out, current = [], ""
        for ch in line:
            if len((current + ch).encode()) > 74:
                out.append(current)
                current = " "
            current += ch
        return [*out, current]

    start = starts(meeting)
    end = start + timedelta(minutes=meeting.minutes or 30)
    where = place(meeting, settings)
    about = "\n".join(p for p in (meeting.topic, where if meeting.kind == "online" else "") if p)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Nimmi AI//Schedule//EN", "METHOD:PUBLISH", "BEGIN:VEVENT",
             f"UID:{meeting.id}@nimmiai.in", f"DTSTAMP:{now_utc():%Y%m%dT%H%M%SZ}", f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
             f"DTEND:{end:%Y%m%dT%H%M%SZ}", f"SEQUENCE:{len(meeting.history or [])}",
             f"SUMMARY:{esc(f'Meeting with {business}')}", f"DESCRIPTION:{esc(about)}", f"LOCATION:{esc(where)}",
             "STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(part for line in lines for part in fold(line)) + "\r\n"


async def _note_sent(meeting_id: str, what: str, via: list[str]) -> None:
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.sent = {**(meeting.sent or {}), what: {"at": now_utc().isoformat(), "via": via}}
            await db.commit()


async def _to_person(meeting_id: str, what: str) -> Optional[str]:
    """Write to the person about their meeting, on WhatsApp and by email. None when it went out at least one way, else
    why it didn't."""
    from notify import channels as notify_channels, email
    from whatsapp import chats as wa_chats, outbound
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            return "meeting deleted"
        settings = await settings_for(meeting.bot_id, db)
        business = await _business(db, meeting.bot_id)
        number, chat = await _whatsapp_chat(db, meeting)
    text, params, subject = _texts(meeting, settings, business, what)
    via, problems = [], []
    if number is not None:
        try:
            if chat is not None and chat.conversation_id and wa_chats.window_open(chat):
                sent = await outbound.send_text(number, chat, text, sent_by="ai")
                if sent.status == "failed":
                    raise RuntimeError(sent.error or "WhatsApp didn't take it")
            elif settings["meetings"]["whatsapp_template"]:
                await notify_channels.send_whatsapp_template(
                    meeting.e164, settings["meetings"]["whatsapp_template"], settings["meetings"]["template_language"],
                    params, phone_number_id=number.phone_number_id, token=number.access_token)
            else:
                raise RuntimeError("outside WhatsApp's 24-hour window, and no template is set")
            via.append("whatsapp")
        except Exception as e:
            problems.append(f"WhatsApp: {str(e)[:200]}")
    if meeting.email:
        invite = [{"filename": "meeting.ics", "content": ics(meeting, settings, business),
                   "content_type": "text/calendar; charset=utf-8; method=PUBLISH"}] if what == "confirmed" else None
        if await email.send_email(meeting.email, subject, text, from_name=business, attachments=invite):
            via.append("email")
        else:
            problems.append(f"Email: {email.last_error() or 'not sent'}")
    if via:
        await _note_sent(meeting_id, what, via)
        return None
    return "; ".join(problems) or "no WhatsApp number or email to reach them on"


async def _once(meeting: Meeting, kind: str, send) -> None:
    from notify import events
    await events._once(meeting.user_id, kind, _ref(meeting), send)


async def send_confirmation(meeting_id: str) -> None:
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
    if meeting is not None and meeting.status == "confirmed":
        await _once(meeting, "meeting_confirmed", lambda: _to_person(meeting_id, "confirmed"))
        await notify_team(meeting_id, "confirmed")


async def send_cancelled(meeting_id: str) -> None:
    """The team declined it without a call: tell them in writing."""
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
    if meeting is not None and meeting.status == "cancelled":
        await _once(meeting, "meeting_cancelled", lambda: _to_person(meeting_id, "cancelled"))


async def _team_addresses(db: AsyncSession, meeting: Meeting, host_first: bool) -> list[str]:
    from notify.events import _settings, recipients
    if host_first and meeting.host_id:
        host = await db.get(User, meeting.host_id)
        if host is not None and host.email:
            return [host.email]
    owner = await db.get(User, meeting.user_id)
    return recipients(await _settings(db, meeting.user_id), owner.email if owner else None)


async def notify_team(meeting_id: str, what: str) -> None:
    """Email the team: a new request to answer, a cancellation, a confirmed meeting (to its host, with the invite), and
    the host's reminder as it starts."""
    from notify import email
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            return
        settings = await settings_for(meeting.bot_id, db)
        business = await _business(db, meeting.bot_id)
        to = await _team_addresses(db, meeting, host_first=what in ("confirmed", "starting"))
    from phone import display
    who = f"{meeting.name or 'Someone'} ({display(meeting.e164)})"
    when = _when_for_people(meeting, settings)
    kind = MEETING_LABELS.get(meeting.kind, "")
    link = f"{email.dashboard_url()}/dashboard/voice/schedule?tab=meetings&meeting={meeting.id}"
    topic = f"About: {meeting.topic}\n" if meeting.topic else ""
    where = place(meeting, settings)
    subject, text, invite = {
        "requested": (f"Meeting request: {meeting.name or display(meeting.e164)}, {when}",
                      f"{who} asked for a {kind} meeting {when}.\n{topic}\nApprove it, or propose another time:\n{link}", None),
        "cancelled": (f"Meeting cancelled: {meeting.name or display(meeting.e164)}, {when}",
                      f"{who} cancelled their {kind} meeting {when}.\n{topic}\n{link}", None),
        "confirmed": (f"Meeting confirmed: {meeting.name or display(meeting.e164)}, {when}",
                      f"Your {kind} meeting with {who} is confirmed for {when}.\n{topic}{('Where: ' + where) if where else ''}\n\n{link}",
                      [{"filename": "meeting.ics", "content": ics(meeting, settings, business),
                        "content_type": "text/calendar; charset=utf-8; method=PUBLISH"}]),
        "starting": (f"Starting soon: meeting with {meeting.name or display(meeting.e164)}",
                     f"Your {kind} meeting with {who} starts {when}.\n{topic}{('Where: ' + where) if where else ''}\n\n{link}", None),
    }[what]

    async def send() -> Optional[str]:
        if not to:
            return "no team address"
        sent = [await email.send_email(address, subject, text, attachments=invite) for address in to]
        return None if any(sent) else "email not configured"
    await _once(meeting, f"meeting_team_{what}", send)


# ─── each minute ──────────────────────────────────────────────────
async def process_due() -> None:
    """Reminders and links that are due, requests that ran out of time, and meetings nobody marked."""
    now = now_utc()
    async with async_session() as db:
        soon = (await db.execute(select(Meeting).where(
            Meeting.status == "confirmed", Meeting.starts_at > stored(now - timedelta(minutes=5)),
            Meeting.starts_at <= stored(now + timedelta(hours=24))))).scalars().all()
        lapsed = (await db.execute(select(Meeting).where(
            Meeting.status.in_(("requested", "proposed")), Meeting.starts_at <= stored(now)))).scalars().all()
        for meeting in lapsed:
            meeting.status = "expired"
            _history(meeting, "Nobody answered the request before its time")
            await _cancel_calls(db, meeting.id)
        unmarked = (await db.execute(select(Meeting).where(
            Meeting.status == "confirmed", Meeting.starts_at <= stored(now - CLOSE_UNMARKED)))).scalars().all()
        for meeting in unmarked:
            meeting.status = "done"
            _history(meeting, "Closed as attended (nobody marked it)")
        if lapsed or unmarked:
            await db.commit()
        settings = {m.bot_id: await settings_for(m.bot_id, db) for m in soon}
    for meeting in soon:
        mt = settings[meeting.bot_id]["meetings"]
        left = starts(meeting) - now
        lead = timedelta(minutes=max(IN_PERSON_LEAD, mt["link_minutes"]) if meeting.kind == "in_person" else mt["link_minutes"])
        try:
            if left <= lead:
                meeting_id = meeting.id
                await _once(meeting, "meeting_link", lambda: _to_person(meeting_id, "link"))
                await notify_team(meeting_id, "starting")
            elif mt["day_before"] and left <= timedelta(hours=24) and left > timedelta(hours=2):
                decided = utc(meeting.decided_at) or utc(meeting.created_at)
                if decided is None or starts(meeting) - decided > timedelta(hours=24):
                    meeting_id = meeting.id
                    await _once(meeting, "meeting_day_before", lambda: _to_person(meeting_id, "day_before"))
        except Exception as e:
            logger.warning(f"Meeting {meeting.id} reminder failed: {e}")


def to_json(meeting: Meeting, settings: dict, *, names: Optional[dict] = None, full: bool = False) -> dict:
    from phone import display
    tz = zone(settings)
    data = {
        "id": meeting.id, "bot_id": meeting.bot_id, "bot_name": (names or {}).get(meeting.bot_id, ""),
        "name": meeting.name or "", "number": display(meeting.e164), "kind": meeting.kind, "topic": meeting.topic or "",
        "starts_at": starts(meeting).isoformat(), "local": starts(meeting).astimezone(tz).strftime("%Y-%m-%dT%H:%M"),
        "minutes": meeting.minutes or 30, "status": meeting.status, "link": meeting.link or "",
        "place": place(meeting, settings), "host_id": meeting.host_id, "timezone": str(tz),
        "sent": meeting.sent or {}, "created_at": utc(meeting.created_at).isoformat() if meeting.created_at else None,
    }
    if full:
        data.update({"email": meeting.email or "", "notes": meeting.notes or "", "history": meeting.history or [],
                     "source_call_id": meeting.source_call_id})
    return data
