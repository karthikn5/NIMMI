"""
The pages people open from an email (mail plan, phase 1): change or cancel their meeting, book a time with the team, ask for a call.
Opening a link only shows a page, because mail apps and scanners open links by themselves; the buttons post back. Each link is signed
for one meeting or one person (mail/links.py), so nobody signs in. Bookings go through Voice > Schedule, with the team's approval
where the assistant asks for it, and the times offered are the free ones.
"""
import html as h
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlalchemy.future import select

from auth import client_ip, decode_scoped_token, rate_limit
from backend.models import Contact, EmailBroadcast, EmailRsvp, Meeting, User
from database import async_session
from mail import senders
from phone import to_e164
from routers.integrations import _html, _page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email/p", tags=["email"])

GONE = "This link isn't available any more. Reply to the email and the team will help."
RSVP = {"yes": "Yes, I'll come", "maybe": "Maybe", "no": "I can't come"}
FIELD = "width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d6d3d1;border-radius:8px;font:inherit;font-size:15px;margin:0 0 12px"


def _form(options: list[tuple[str, str]], label: str, ask_phone: bool, heading: str) -> str:
    """One form, so a phone works as well as a computer: a time, their number if we need it, and the button."""
    choices = "".join(f'<option value="{h.escape(v)}">{h.escape(t)}</option>' for v, t in options)
    phone = f'<label style="display:block;font-size:14px;color:#57534e;margin:0 0 4px">Your phone number</label><input name="phone" type="tel" required style="{FIELD}">' if ask_phone else ""
    return (f'<form method="post"><input type="hidden" name="action" value="pick"><label style="display:block;font-size:14px;color:#57534e;margin:0 0 4px">{h.escape(heading)}</label>'
            f'<select name="at" required style="{FIELD}">{choices}</select>{phone}'
            f'<button type="submit" style="width:100%;padding:11px 16px;border-radius:8px;font:inherit;font-size:15px;cursor:pointer;border:1px solid #550a64;background:#550a64;color:#fff">'
            f'{h.escape(label)}</button></form>')


def _with_form(title: str, text: str, form: str, buttons: Optional[list] = None):
    page = _page(title, text, buttons)
    return _html(page.replace("</div></body>", f"{form}</div></body>"))


def _text_of(at: datetime, tz) -> str:
    from voice import schedule
    text = schedule.when_text(at, tz, now=at + timedelta(days=30))
    return text[0].upper() + text[1:]


async def _free_options(db, settings: dict, owner_id: str, bot_id: str, skip: Optional[str] = None) -> list[tuple[str, str]]:
    """The next free meeting times, a few a day."""
    from voice import meetings, schedule
    tz = schedule.zone(settings)
    today = schedule.now_utc().astimezone(tz).date()
    free = await meetings.free_times(db, settings, owner_id, bot_id, today, settings["meetings"]["ahead_days"] + 1, skip=skip)
    return [(at.isoformat(), _text_of(at, tz)) for slots in list(free.values())[:5] for at in meetings._spread(slots, 3)]


def _call_options(settings: dict) -> list[tuple[str, str]]:
    """Times inside the calling hours, for the next few days."""
    from voice import schedule
    tz, hours = schedule.zone(settings), settings["callbacks"]["hours"]
    now = schedule.now_utc().astimezone(tz)
    soon = now + timedelta(minutes=5)
    found = [(SOON, "In about 5 minutes")] if schedule.allowed(soon, hours, schedule.DAYS, tz) else []
    at = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while len(found) < 9 and at < now + timedelta(days=4):
        if schedule.allowed(at, hours, schedule.DAYS, tz):
            found.append((at.astimezone(timezone.utc).isoformat(), _text_of(at, tz)))
        at += timedelta(hours=3)
    return found


SOON = "soon"  # "In about 5 minutes": the time is taken when they press the button


def _picked(value: Optional[str], options: list[tuple[str, str]]) -> Optional[datetime]:
    """Only a time that was on offer."""
    if not value or value not in {v for v, _ in options}:
        return None
    return datetime.now(timezone.utc) + timedelta(minutes=5) if value == SOON else datetime.fromisoformat(value)


async def _meeting(token: str) -> Optional[Meeting]:
    meeting_id = decode_scoped_token(token, "email_meeting")
    if not meeting_id:
        return None
    async with async_session() as db:
        return await db.get(Meeting, meeting_id)


@router.get("/meeting")
async def meeting_page(token: str = "", view: str = ""):
    from voice import meetings, schedule
    m = await _meeting(token)
    if m is None or m.status not in meetings.ACTIVE:
        return _html(_page("This meeting isn't active", GONE))
    async with async_session() as db:
        settings = await schedule.settings_for(m.bot_id, db)
        business = await meetings._business(db, m.bot_id)
        options = await _free_options(db, settings, m.user_id, m.bot_id, skip=m.id)
    tz = schedule.zone(settings)
    when = _text_of(meetings.starts(m), tz)
    if view == "cancel":
        return _html(_page("Cancel your meeting?", f"{when}, with {business}.", [("cancel", "Yes, cancel it", True)]))
    if view == "change" and options:
        return _with_form("Change the time", f"It's {when} now. Pick another time.", _form(options, "Change the time", False, "Free times"))
    if view == "change":
        return _html(_page("No other times are free", "Reply to the email and the team will find one."))
    return _html(_page("Your meeting", f"{when}, with {business}.", [("show_change", "Change the time", True), ("show_cancel", "Cancel it", False)]))


@router.post("/meeting")
async def meeting_action(request: Request, token: str = ""):
    from voice import meetings, schedule
    rate_limit(f"email-page:{client_ip(request)}", 30, 3600)
    m = await _meeting(token)
    if m is None or m.status not in meetings.ACTIVE:
        return _html(_page("This meeting isn't active", GONE))
    form = await request.form()
    action = str(form.get("action") or "")
    if action in ("show_change", "show_cancel"):
        return await meeting_page(token, "change" if action == "show_change" else "cancel")
    if action == "cancel":
        await meetings.cancel_by_caller(m.id, "", via="the link in an email")
        return _html(_page("Your meeting is cancelled", "Reply to the email if you'd like another time."))
    async with async_session() as db:
        settings = await schedule.settings_for(m.bot_id, db)
        options = await _free_options(db, settings, m.user_id, m.bot_id, skip=m.id)
    at = _picked(str(form.get("at") or ""), options)
    if at is None:
        return await meeting_page(token, "change")
    local = at.astimezone(schedule.zone(settings))
    await meetings.book(settings, owner_id=m.user_id, bot_id=m.bot_id, e164=m.e164, args={"date": local.date().isoformat(), "time": f"{local:%H:%M}"},
                        name=m.name, source_call_id=None, test=False, via="the link in an email")
    wait = " The team will confirm it." if settings["meetings"]["approval"] else ""
    return _html(_page("Your meeting has moved", f"It's now {_text_of(at, schedule.zone(settings))}.{wait}"))


def _person(token: str, scope: str) -> Optional[tuple[str, str, str]]:
    """(workspace, assistant, address) from a booking link."""
    subject = decode_scoped_token(token, scope)
    parts = (subject or "").split("|")
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else None


async def _phone_of(db, bot_id: str, address: str) -> tuple[Optional[str], Optional[str]]:
    contact = (await db.execute(select(Contact).where(Contact.bot_id == bot_id, func.lower(Contact.email) == address.lower())
                                .order_by(Contact.created_at))).scalars().first()
    return (contact.e164, contact.name) if contact else (None, None)


@router.get("/book")
async def book_page(token: str = ""):
    from voice import schedule
    person = _person(token, "email_book")
    if person is None:
        return _html(_page("This link has expired", GONE))
    owner, bot, address = person
    async with async_session() as db:
        settings = await schedule.settings_for(bot, db)
        business = (await senders.sender_for(db, owner, bot)).name
        e164, _ = await _phone_of(db, bot, address)
        options = await _free_options(db, settings, owner, bot) if settings["meetings"]["enabled"] else []
    if not options:
        return _html(_page("No times are free just now", "Reply to the email and the team will find one."))
    return _with_form(f"Book a time with {business}", "Pick a time that suits you.", _form(options, "Book it", not e164, "Free times"))


@router.post("/book")
async def book_action(request: Request, token: str = ""):
    from voice import meetings, schedule
    rate_limit(f"email-page:{client_ip(request)}", 30, 3600)
    person = _person(token, "email_book")
    if person is None:
        return _html(_page("This link has expired", GONE))
    owner, bot, address = person
    form = await request.form()
    async with async_session() as db:
        settings = await schedule.settings_for(bot, db)
        e164, name = await _phone_of(db, bot, address)
        options = await _free_options(db, settings, owner, bot) if settings["meetings"]["enabled"] else []
    e164 = e164 or to_e164(str(form.get("phone") or ""))
    at = _picked(str(form.get("at") or ""), options)
    if at is None or not e164:
        return _html(_page("That didn't work", "Go back, check your phone number and pick a time again."))
    local = at.astimezone(schedule.zone(settings))
    await meetings.book(settings, owner_id=owner, bot_id=bot, e164=e164, name=name, source_call_id=None, test=False, via="the link in an email",
                        args={"date": local.date().isoformat(), "time": f"{local:%H:%M}", "email": address})
    wait = " The team will confirm it." if settings["meetings"]["approval"] else ""
    return _html(_page("It's booked", f"{_text_of(at, schedule.zone(settings))}.{wait}"))


@router.get("/call")
async def call_page(token: str = ""):
    from voice import schedule
    person = _person(token, "email_call")
    if person is None:
        return _html(_page("This link has expired", GONE))
    owner, bot, address = person
    async with async_session() as db:
        settings = await schedule.settings_for(bot, db)
        business = (await senders.sender_for(db, owner, bot)).name
        e164, _ = await _phone_of(db, bot, address)
    options = _call_options(settings) if settings["callbacks"]["enabled"] else []
    if not options:
        return _html(_page("We can't book a call here just now", "Reply to the email and the team will call you."))
    return _with_form(f"Ask {business} to call you", "Pick a time that suits you.", _form(options, "Call me then", not e164, "When to call"))


@router.post("/call")
async def call_action(request: Request, token: str = ""):
    from voice import schedule
    rate_limit(f"email-page:{client_ip(request)}", 30, 3600)
    person = _person(token, "email_call")
    if person is None:
        return _html(_page("This link has expired", GONE))
    owner, bot, address = person
    form = await request.form()
    async with async_session() as db:
        settings = await schedule.settings_for(bot, db)
        e164, name = await _phone_of(db, bot, address)
    e164 = e164 or to_e164(str(form.get("phone") or ""))
    options = _call_options(settings) if settings["callbacks"]["enabled"] else []
    at = _picked(str(form.get("at") or ""), options)
    if at is None or not e164:
        return _html(_page("That didn't work", "Go back, check your phone number and pick a time again."))
    await schedule.book_callback(owner_id=owner, bot_id=bot, e164=e164, at=at, about="They asked for a call from an email", name=name, source_call_id=None,
                                 number_id=None, tz=schedule.zone(settings), consent=f"Asked from an email link on {datetime.utcnow():%d %b %Y} to be called back")
    return _html(_page("We'll call you", f"{_text_of(at, schedule.zone(settings))}."))


FEEDBACK_BUTTON = "flex:1;padding:11px 16px;border-radius:8px;font:inherit;font-size:15px;cursor:pointer;border:1px solid #d6d3d1;background:#fff;color:#1c1917"


def _feedback_form() -> str:
    return (f'<form method="post"><label style="display:block;font-size:14px;color:#57534e;margin:0 0 4px" for="comment">Anything you\'d like to add? (optional)</label>'
            f'<textarea id="comment" name="comment" rows="3" maxlength="1000" style="{FIELD}"></textarea><div style="display:flex;gap:8px">'
            f'<button type="submit" name="action" value="good" style="{FEEDBACK_BUTTON}">Good</button>'
            f'<button type="submit" name="action" value="bad" style="{FEEDBACK_BUTTON}">Not good</button></div></form>')


async def _feedback_contact(token: str) -> Optional[Contact]:
    contact_id = decode_scoped_token(token, "email_feedback")
    if not contact_id:
        return None
    async with async_session() as db:
        return await db.get(Contact, contact_id)


@router.get("/feedback")
async def feedback_page(token: str = ""):
    contact = await _feedback_contact(token)
    if contact is None:
        return _html(_page("This link has expired", GONE))
    async with async_session() as db:
        business = (await senders.sender_for(db, contact.user_id, contact.bot_id)).name
    return _with_form(f"How was it with {business}?", "Your answer goes to the team.", _feedback_form())


@router.post("/feedback")
async def feedback_action(request: Request, token: str = ""):
    """Kept with their details. "Not good" tells the team at once, so someone can put it right."""
    from notify import events
    rate_limit(f"email-page:{client_ip(request)}", 30, 3600)
    contact = await _feedback_contact(token)
    if contact is None:
        return _html(_page("This link has expired", GONE))
    form = await request.form()
    action, comment = str(form.get("action") or ""), str(form.get("comment") or "").strip()[:1000]
    if action not in ("good", "bad"):
        return await feedback_page(token)
    async with async_session() as db:
        row = await db.get(Contact, contact.id)
        if row is None:
            return _html(_page("This link has expired", GONE))
        row.details = {**(row.details or {}), "Feedback": "Good" if action == "good" else "Not good", **({"Feedback comment": comment} if comment else {})}
        await db.commit()
        team = await events._settings(db, row.user_id)
        owner = (await db.execute(select(User.email).where(User.id == row.user_id))).scalar_one_or_none()
        who = row.name or row.email or row.e164 or "A customer"
    if action == "bad":
        await events._email_team(events.recipients(team, owner), f"Feedback from {who}: not good", comment or "They didn't add a comment.", row.user_id)
    return _html(_page("Thank you", "Your answer has gone to the team."))


async def _rsvp(token: str):
    """The invitation and the person a link is for."""
    subject = decode_scoped_token(token, "email_rsvp")
    if not subject or "|" not in subject:
        return None, None
    broadcast_id, to = subject.split("|", 1)
    async with async_session() as db:
        return await db.get(EmailBroadcast, broadcast_id), to


@router.get("/rsvp")
async def rsvp_page(token: str = ""):
    from voice import schedule
    b, to = await _rsvp(token)
    event = (b.event or {}) if b is not None else {}
    if not event.get("title"):
        return _html(_page("This invitation has ended", GONE))
    async with async_session() as db:
        tz = schedule.zone(await schedule.settings_for(b.bot_id, db))
        answer = (await db.execute(select(EmailRsvp.answer).where(EmailRsvp.broadcast_id == b.id, EmailRsvp.email == to))).scalar_one_or_none()
    when = _text_of(schedule.utc(datetime.fromisoformat(event["at"])), tz)
    place = f" {event['where']}." if event.get("where") else ""
    said = f" You said {RSVP[answer].lower()}." if answer else ""
    return _html(_page(f"Will you come to {event['title']}?", f"{when}.{place}{said}", [("yes", RSVP["yes"], True), ("maybe", RSVP["maybe"], False), ("no", RSVP["no"], False)]))


@router.post("/rsvp")
async def rsvp_action(request: Request, token: str = ""):
    """Their answer, on the invitation and on their details. The day before, yes and maybe get a reminder (mail/broadcasts.py)."""
    rate_limit(f"email-page:{client_ip(request)}", 30, 3600)
    b, to = await _rsvp(token)
    event = (b.event or {}) if b is not None else {}
    answer = str((await request.form()).get("action") or "")
    if not event.get("title") or answer not in RSVP:
        return await rsvp_page(token)
    async with async_session() as db:
        row = (await db.execute(select(EmailRsvp).where(EmailRsvp.broadcast_id == b.id, EmailRsvp.email == to))).scalars().first()
        if row is None:
            db.add(EmailRsvp(broadcast_id=b.id, user_id=b.user_id, email=to, answer=answer))
        else:
            row.answer, row.answered_at = answer, datetime.utcnow()
        contact = (await db.execute(select(Contact).where(Contact.bot_id == b.bot_id, func.lower(Contact.email) == to).order_by(Contact.created_at))).scalars().first()
        if contact is not None:
            contact.details = {**(contact.details or {}), f"RSVP: {event['title']}"[:60]: RSVP[answer]}
        await db.commit()
    return _html(_page("Thank you", "We'll see you there." if answer == "yes" else "Your answer has gone to the team."))

