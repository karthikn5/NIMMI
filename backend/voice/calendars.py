"""
Meetings and the team's calendar (mail plan, phase 8). An assistant's Schedule settings can name a connected Google or Outlook calendar (mail/mailbox.py). Its busy times come off
the times on offer, on calls and on the booking page, and each confirmed meeting becomes an event there, with a Meet or Teams link when that's on.

Busy times are read every few minutes and kept on the connection, so a live call never waits for Google. Events follow the meeting: `wanted` says what the calendar should show and
`sync` makes it so; what fails is tried again on the next pass. No database connection is held while the provider answers. Nobody is invited on the provider's side: the person hears
from Nimmi (the confirmation, with its invite), which Outlook's and Google's own emails would repeat.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import or_, update
from sqlalchemy.future import select

from backend.models import Bot, MailConnection, Meeting, ScheduleSettings
from database import async_session
from mail import mailbox
from mail.mailbox import GOOGLE_CALENDAR, GRAPH, MailboxError
from voice import schedule
from voice.schedule import now_utc, stored, utc

logger = logging.getLogger(__name__)

BUSY_EVERY = timedelta(minutes=5)
AHEAD = timedelta(days=62)  # meetings can be booked up to 60 days out
RETRY = timedelta(seconds=60)
PASS_EVERY = timedelta(seconds=60)
KEPT = ("confirmed", "done", "no_show")  # a meeting that happened stays on the calendar
BUSY_KINDS = ("busy", "oof", "tentative")  # Outlook's showAs that take up the time
PAGES = 5
_last_pass: Optional[datetime] = None


def _when(value: Optional[str]) -> Optional[datetime]:
    try:
        at = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def read_busy(connection_id: str, provider: str, address: str, start: datetime, end: datetime) -> list[list[str]]:
    """Busy times from the provider: [[start, end], ...]. Outlook's calendarView, not getSchedule: that one refuses personal accounts."""
    if provider == "google":
        resp = await mailbox.call(connection_id, "POST", f"{GOOGLE_CALENDAR}/freeBusy",
                                  json={"timeMin": _iso(start), "timeMax": _iso(end), "timeZone": "UTC", "items": [{"id": address}]})
        if resp.status_code >= 300:
            raise MailboxError(f"Google answered {resp.status_code}")
        calendars = resp.json().get("calendars") or {}
        found = calendars.get(address) or next(iter(calendars.values()), {})
        if found.get("errors"):
            raise MailboxError(f"Google couldn't read the calendar: {found['errors'][0].get('reason')}")
        return [[b["start"], b["end"]] for b in found.get("busy") or []]
    blocks, url, params = [], f"{GRAPH}/me/calendarView", {"startDateTime": _iso(start), "endDateTime": _iso(end), "$select": "start,end,showAs,isCancelled", "$top": "200"}
    for _ in range(PAGES):
        resp = await mailbox.call(connection_id, "GET", url, params=params, headers={"Prefer": 'outlook.timezone="UTC"'})
        if resp.status_code >= 300:
            raise MailboxError(f"Microsoft answered {resp.status_code}")
        data = resp.json()
        blocks += [[e["start"]["dateTime"], e["end"]["dateTime"]] for e in data.get("value") or [] if e.get("showAs") in BUSY_KINDS and not e.get("isCancelled")]
        url, params = data.get("@odata.nextLink"), None
        if not url:
            break
    return blocks


async def refresh(connection_id: str, now: Optional[datetime] = None) -> None:
    """Read the calendar now (claimed: the four processes share this)."""
    now = now or now_utc()
    async with async_session() as db:
        row = await db.get(MailConnection, connection_id)
        if row is None or row.status != "connected" or not mailbox.can(row, "calendar"):
            return
        provider, address = row.provider, row.address
        claimed = await db.execute(update(MailConnection).where(
            MailConnection.id == connection_id, or_(MailConnection.busy_at.is_(None), MailConnection.busy_at < now - RETRY)).values(busy_at=now)
            .execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
    try:
        blocks = await read_busy(connection_id, provider, address, now, now + AHEAD)
    except (MailboxError, httpx.HTTPError, KeyError, ValueError) as e:
        logger.info(f"Couldn't read {address}'s calendar: {e!r}")
        return
    async with async_session() as db:
        await db.execute(update(MailConnection).where(MailConnection.id == connection_id).values(busy=blocks[:1000]))
        await db.commit()


async def busy_for(db, settings: dict, bot_id: str, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """The calendar's busy times in that window, without the meetings Nimmi put there itself: those count as meetings, seat by seat."""
    chosen = settings["meetings"].get("calendar")
    row = await db.get(MailConnection, chosen) if chosen else None
    if row is None or not row.busy:
        return []
    own = {(utc(m.starts_at), utc(m.starts_at) + timedelta(minutes=m.minutes or 30)) for m in (await db.execute(select(Meeting).where(
        Meeting.bot_id == bot_id, Meeting.calendar_event_id.isnot(None), Meeting.starts_at < stored(end),
        Meeting.starts_at > stored(start - timedelta(days=1))))).scalars().all()}
    blocks = [(_when(a), _when(b)) for a, b in row.busy]
    return [(a, b) for a, b in blocks if a and b and a < end and b > start and (a, b) not in own]


def wanted(meeting: Meeting) -> Optional[str]:
    """What the calendar should show for this meeting; None = nothing. Changing it (a new time) means the event changes."""
    return f"{utc(meeting.starts_at):%Y%m%d%H%M}:{meeting.minutes or 30}" if meeting.status in KEPT else None


def _details(meeting: Meeting, place: str) -> str:
    lines = [f"About: {meeting.topic}" if meeting.topic else "", f"Phone: {meeting.e164}" if meeting.e164 else "", f"Email: {meeting.email}" if meeting.email else "",
             f"Where: {place}" if place else "", "Booked through Nimmi"]
    return "\n".join(line for line in lines if line)


def _google_event(title: str, details: str, start: datetime, end: datetime, place: str, new: bool, video: bool) -> dict:
    body = {"summary": title, "description": details, "start": {"dateTime": _iso(start)}, "end": {"dateTime": _iso(end)}}
    if place:
        body["location"] = place
    if new and video:
        body["conferenceData"] = {"createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    return body


def _google_link(event: dict) -> Optional[str]:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    return next((e.get("uri") for e in (event.get("conferenceData") or {}).get("entryPoints") or [] if e.get("entryPointType") == "video"), None)


async def _google_put(connection_id: str, event_id: Optional[str], body: dict, video: bool) -> tuple[str, Optional[str]]:
    url = f"{GOOGLE_CALENDAR}/calendars/primary/events"
    if event_id:
        resp = await mailbox.call(connection_id, "PATCH", f"{url}/{event_id}", params={"sendUpdates": "none"}, json=body)
    else:
        resp = await mailbox.call(connection_id, "POST", url, params={"sendUpdates": "none", "conferenceDataVersion": "1"}, json=body)
    if resp.status_code >= 300:
        raise MailboxError(f"Google answered {resp.status_code}")
    event = resp.json()
    link = _google_link(event)
    for _ in range(3 if video and not event_id and not link else 0):  # Meet's link is made a moment after the event
        await asyncio.sleep(1)
        again = await mailbox.call(connection_id, "GET", f"{url}/{event['id']}")
        link = _google_link(again.json()) if again.status_code < 300 else None
        if link:
            break
    return event["id"], link


async def _microsoft_put(connection_id: str, event_id: Optional[str], title: str, details: str, start: datetime, end: datetime, place: str, video: bool) -> tuple[str, Optional[str]]:
    body = {"subject": title, "body": {"contentType": "text", "content": details}, "start": {"dateTime": _iso(start)[:-1], "timeZone": "UTC"},
            "end": {"dateTime": _iso(end)[:-1], "timeZone": "UTC"}, "location": {"displayName": place}}
    if event_id:
        resp = await mailbox.call(connection_id, "PATCH", f"{GRAPH}/me/events/{event_id}", json=body)
    else:
        resp = await mailbox.call(connection_id, "POST", f"{GRAPH}/me/events", json={**body, **({"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"} if video else {})})
        if resp.status_code == 400 and video:  # personal accounts: no Teams through this call
            resp = await mailbox.call(connection_id, "POST", f"{GRAPH}/me/events", json=body)
    if resp.status_code >= 300:
        raise MailboxError(f"Microsoft answered {resp.status_code}")
    event = resp.json()
    return event["id"], (event.get("onlineMeeting") or {}).get("joinUrl")


async def _drop(connection_id: str, provider: str, event_id: str) -> None:
    url = f"{GOOGLE_CALENDAR}/calendars/primary/events/{event_id}" if provider == "google" else f"{GRAPH}/me/events/{event_id}"
    resp = await mailbox.call(connection_id, "DELETE", url, **({"params": {"sendUpdates": "none"}} if provider == "google" else {}))
    if resp.status_code >= 300 and resp.status_code not in (404, 410):  # someone removed it by hand: gone is what we want
        raise MailboxError(f"{provider} answered {resp.status_code}")


async def _save(meeting_id: str, **values) -> None:
    async with async_session() as db:
        await db.execute(update(Meeting).where(Meeting.id == meeting_id).values(**values))
        await db.commit()


async def sync(meeting_id: str) -> None:
    """Make the calendar show what the meeting says. It never raises: a meeting goes on without its calendar, and the next pass tries again."""
    try:
        await _sync(meeting_id)
    except (MailboxError, httpx.HTTPError, KeyError, ValueError) as e:
        logger.info(f"Meeting {meeting_id} didn't reach the calendar: {e!r}")
        await _save(meeting_id, calendar_error=str(e)[:300] or "The calendar didn't answer")


async def _sync(meeting_id: str) -> None:
    now = now_utc()
    async with async_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            return
        want = wanted(meeting)
        if want == meeting.calendar_state:
            return
        settings = await schedule.settings_for(meeting.bot_id, db)
        mt = settings["meetings"]
        connection_id = meeting.calendar_id or mt.get("calendar")
        if not connection_id:
            return
        row = await db.get(MailConnection, connection_id)
        if row is None:  # disconnected: what was there is out of our reach
            meeting.calendar_id, meeting.calendar_event_id, meeting.calendar_state = None, None, None
            await db.commit()
            return
        if row.status != "connected" or not mailbox.can(row, "calendar"):
            return
        claimed = await db.execute(update(Meeting).where(Meeting.id == meeting_id, or_(Meeting.calendar_tried_at.is_(None), Meeting.calendar_tried_at < stored(now - RETRY)))
                                   .values(calendar_tried_at=stored(now)).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        provider, event_id = row.provider, meeting.calendar_event_id
        business = (await db.execute(select(Bot.bot_name).where(Bot.bot_id == meeting.bot_id))).scalar_one_or_none()
        start, minutes, kind = utc(meeting.starts_at), meeting.minutes or 30, meeting.kind
        place = meeting.link or (mt["link"] if kind == "online" else mt["address"] if kind == "in_person" else "")
        video = kind == "online" and bool(mt.get("calendar_video")) and not meeting.link
        title, details = f"{meeting.name or 'Meeting'} ({business or 'Nimmi'})"[:200], _details(meeting, "" if video else place)
    if want is None:
        if event_id:
            await _drop(connection_id, provider, event_id)
        await _save(meeting_id, calendar_id=None, calendar_event_id=None, calendar_state=None, calendar_error=None)
        return
    end = start + timedelta(minutes=minutes)
    where = "" if video else place
    if provider == "google":
        new_id, link = await _google_put(connection_id, event_id, _google_event(title, details, start, end, where, not event_id, video), video)
    else:
        new_id, link = await _microsoft_put(connection_id, event_id, title, details, start, end, where, video)
    values = {"calendar_id": connection_id, "calendar_event_id": new_id, "calendar_state": want, "calendar_error": None}
    await _save(meeting_id, **values)
    if link and kind == "online":
        async with async_session() as db:  # only if nobody set one meanwhile
            await db.execute(update(Meeting).where(Meeting.id == meeting_id, or_(Meeting.link.is_(None), Meeting.link == "")).values(link=link[:500]))
            await db.commit()


async def _due_meetings(now: datetime) -> list[str]:
    async with async_session() as db:
        rows = (await db.execute(select(ScheduleSettings.bot_id, ScheduleSettings.settings))).all()
        bots = [bot for bot, s in rows if ((s or {}).get("meetings") or {}).get("calendar")]
        found = (await db.execute(select(Meeting).where(or_(Meeting.calendar_event_id.isnot(None), Meeting.bot_id.in_(bots)),
                                                        Meeting.starts_at > stored(now - timedelta(days=1))))).scalars().all()
    return [m.id for m in found if wanted(m) != m.calendar_state]


async def tick(now: Optional[datetime] = None) -> None:
    """Scheduler: calendars due a read, and meetings the calendar hasn't caught up with."""
    global _last_pass
    now = now or now_utc()
    if _last_pass and now - _last_pass < PASS_EVERY:
        return
    _last_pass = now
    async with async_session() as db:
        rows = (await db.execute(select(MailConnection).where(MailConnection.status == "connected", or_(
            MailConnection.busy_at.is_(None), MailConnection.busy_at < now - BUSY_EVERY)).limit(50))).scalars().all()
        due = [r.id for r in rows if mailbox.can(r, "calendar")]
    for connection_id in due[:20]:
        await refresh(connection_id, now)
    for meeting_id in (await _due_meetings(now))[:20]:
        await sync(meeting_id)
