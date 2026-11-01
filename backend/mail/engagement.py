"""
What someone did with a business's emails (mail plan 5.8, phase 6), as a score from 0 to 100 on their contact: a reply counts most, then opening Book a time or
Call me, a look at prices, a download, any other link. Only a person's clicks count (mail/clicks.py); opens count for nothing, as mail apps open emails by
themselves. What they did in the last week counts fully, the week before half, and after two weeks it's gone. "Hot now" is who did something worth acting on in
the last two days. The team hears about the actions worth a call, once a day for each person and action; on Pro, someone who opened the booking times and didn't
book in ten minutes can get a call (the assistant's "fast_call" setting), through Schedule's checks like any follow-up.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.future import select

from backend.models import Contact, EmailClick, EmailJob, EmailLink, EmailThread, ThreadMessage, User
from database import async_session

logger = logging.getLogger(__name__)

WEIGHTS = {"reply": 40, "book": 30, "call": 30, "pricing": 20, "file": 15, "link": 5}
WORDS = {"reply": "replied", "book": "opened Book a time", "call": "asked for a call", "pricing": "looked at prices", "file": "downloaded", "link": "opened a link"}
WINDOW = timedelta(days=14)
FULL = timedelta(days=7)
REPLIES = 2                       # replies that count: a long thread isn't worth more
HOT = 30
HOT_FOR = timedelta(hours=48)
ALERT = ("book", "call", "pricing", "file")
FAST_CALL_AFTER = timedelta(minutes=10)
PRICING = re.compile(r"\b(price|prices|pricing|plans?|costs?|rates?|fees?|quotes?|tariffs?)\b", re.I)


def _naive(at: Optional[datetime]) -> Optional[datetime]:
    from mail.clicks import _naive as naive
    return naive(at)


def kind_of(link: EmailLink) -> str:
    if link.kind in ("book", "call"):
        return link.kind
    if PRICING.search(f"{link.label or ''} {link.target or ''}"):
        return "pricing"
    return "file" if link.kind == "file" else "link"


def describe(kind: str, link: Optional[EmailLink] = None) -> str:
    what = WORDS[kind]
    label = (link.label or "").strip() if link is not None else ""
    return f"{what} {label}".strip() if kind in ("file", "pricing", "link") and label else what


def score(actions: list[tuple[str, datetime]], now: datetime) -> int:
    """actions: (kind, when), already one per link and at most REPLIES replies."""
    points = 0.0
    for kind, at in actions:
        age = now - at
        if age > WINDOW:
            continue
        points += WEIGHTS[kind] * (1 if age <= FULL else 0.5)
    return min(100, round(points))


async def _contact(db, bot_id: Optional[str], address: str) -> Optional[Contact]:
    if not bot_id or not address:
        return None
    return (await db.execute(select(Contact).where(Contact.bot_id == bot_id, func.lower(Contact.email) == address.lower())
                             .order_by(Contact.created_at))).scalars().first()


async def recompute(db, contact: Contact, now: Optional[datetime] = None) -> None:
    """Their score from what they did in the last two weeks (the caller commits)."""
    now = now or datetime.utcnow()
    since, address = now - WINDOW, (contact.email or "").lower()
    if not address:
        return
    replies = (await db.execute(select(ThreadMessage.created_at).join(EmailThread, EmailThread.id == ThreadMessage.thread_id).where(
        EmailThread.bot_id == contact.bot_id, EmailThread.email == address, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True),
        ThreadMessage.created_at >= since).order_by(ThreadMessage.created_at.desc()).limit(REPLIES))).scalars().all()
    clicks = (await db.execute(select(EmailLink, func.max(EmailClick.at)).join(EmailClick, EmailClick.token == EmailLink.token).join(
        EmailJob, EmailJob.id == EmailClick.job_id).where(EmailClick.person.is_(True), EmailClick.at >= since, EmailJob.bot_id == contact.bot_id,
                                                          func.lower(EmailJob.to_email) == address).group_by(EmailLink.token))).all()
    done = sorted([(_naive(at), "reply", None) for at in replies] + [(_naive(at), kind_of(link), link) for link, at in clicks], key=lambda x: x[0], reverse=True)
    contact.engagement = score([(kind, at) for at, kind, _ in done], now)
    if done:
        contact.engaged_at = done[0][0]
        contact.engaged_by = [{"what": describe(kind, link)[:120], "kind": kind, "at": at.isoformat()} for at, kind, link in done[:5]]
    else:
        contact.engaged_by = []


async def clicked(db, job: EmailJob, link: EmailLink, at: datetime) -> list:
    """A person's click (mail/clicks.py): their score, then what goes out once it's saved. Returns those actions."""
    contact = await _contact(db, job.bot_id, job.to_email)
    if contact is None:
        return []
    await recompute(db, contact, at)
    kind = kind_of(link)
    later = []
    if kind in ALERT:
        later.append(lambda: _alert(job.user_id, contact.id, kind, describe(kind, link), at))
    if kind == "book":
        later.append(lambda: _fast_call(job.user_id, job.bot_id, contact.id, at))
    return later


async def replied(db, thread: EmailThread) -> None:
    """They replied (mail/inbound.py; the caller commits)."""
    contact = await _contact(db, thread.bot_id, thread.email)
    if contact is not None:
        await recompute(db, contact)


async def _alert(owner_id: str, contact_id: str, kind: str, what: str, at: datetime) -> None:
    """To the team, once a day for each person and action. Best effort; never raises."""
    import plans
    from notify import email, events
    try:
        async with async_session() as db:
            settings = await events._settings(db, owner_id)
            contact = await db.get(Contact, contact_id)
            if settings.alert_engaged is False or contact is None or not (await plans.workspace_includes(db, owner_id)).team_alerts:
                return
            owner = (await db.execute(select(User.email).where(User.id == owner_id))).scalar_one_or_none()
        who = contact.name or contact.email or contact.e164 or "Someone"
        details = "\n".join(x for x in (contact.name, contact.email, contact.e164) if x)
        text = (f"{who} just {what}, from one of your emails. A good moment to get in touch.\n\n{details}\n\n"
                f"See your leads: {email.dashboard_url()}/dashboard/email/board")
        await events._once(owner_id, "engaged_alert", f"{contact_id}:{kind}:{at.date().isoformat()}",
                           lambda: events._email_team(events.recipients(settings, owner), f"{who} just {what}"[:150], text, owner_id))
    except Exception as e:
        logger.warning(f"The engagement alert for {contact_id} failed: {e}")


async def _fast_call(owner_id: str, bot_id: str, contact_id: str, at: datetime) -> None:
    """On Pro, with the assistant's fast_call on: a follow-up call ten minutes after they opened the booking times, which Schedule calls off if they book
    meanwhile (its checks before each dial). Once a week at most. Best effort; never raises."""
    import plans
    from backend.models import CallbackJob
    from mail import setup
    from notify import events
    from voice import schedule
    try:
        async with async_session() as db:
            contact = await db.get(Contact, contact_id)
            if contact is None or not contact.e164 or not (await setup.settings_for(db, bot_id))["fast_call"]["enabled"]:
                return
            if not (await plans.includes(db, bot_id)).schedule or await schedule.on_dnc(db, owner_id, contact.e164):
                return
            settings = await schedule.settings_for(bot_id, db)
            if not settings["follow_ups"]["enabled"] or contact.follow_ups_off:
                return
            for waiting in ("callback", "person", "follow_up"):
                if await schedule.waiting_job(db, bot_id, contact.e164, waiting):
                    return
            if await schedule.upcoming_meeting(db, bot_id, contact.e164):
                return
            fu, tz = settings["follow_ups"], schedule.zone(settings)
            due = schedule.next_allowed(schedule.utc(at + FAST_CALL_AFTER), fu["hours"], fu["days"], tz, await schedule.holidays(owner_id))
            week = at.isocalendar()

        async def plan() -> Optional[str]:
            async with async_session() as db:
                db.add(CallbackJob(user_id=owner_id, bot_id=bot_id, e164=contact.e164, name=contact.name, kind="follow_up", status="queued",
                                   next_attempt_at=schedule.stored(due), purpose="They opened your meeting times from an email but didn't book one. Offer to help them pick a time.",
                                   variables={"step": 0, "from_email": "book"}, consent_source=f"Opened Book a time in an email on {schedule.utc(at).astimezone(tz):%d %b %Y}"))
                await db.commit()
            return None
        await events._once(owner_id, "fast_call", f"{contact_id}:{week[0]}-{week[1]}", plan)
    except Exception as e:
        logger.warning(f"The fast call for {contact_id} failed: {e}")


async def hot(db, bot_id: Optional[str], now: Optional[datetime] = None, limit: int = 20, owner_id: Optional[str] = None) -> list[dict]:
    """Who did something worth acting on in the last two days: one assistant's, or (owner_id) the whole workspace's."""
    now = now or datetime.utcnow()
    where = [Contact.bot_id == bot_id] if bot_id else [Contact.user_id == owner_id]
    rows = (await db.execute(select(Contact).where(*where, Contact.engagement >= HOT, Contact.engaged_at >= now - HOT_FOR)
                             .order_by(Contact.engagement.desc(), Contact.engaged_at.desc()).limit(limit))).scalars().all()
    from phone import display
    return [{"id": c.id, "bot_id": c.bot_id, "name": c.name, "email": c.email, "phone": display(c.e164) if c.e164 else None, "score": c.engagement,
             "at": _naive(c.engaged_at).isoformat() if c.engaged_at else None, "did": c.engaged_by or [], "status": c.lead_status, "stage": c.stage or "new"} for c in rows]


async def decay(now: Optional[datetime] = None) -> int:
    """Scheduler: scores of people who did nothing for a week fall, and after two weeks are gone."""
    now = now or datetime.utcnow()
    done = 0
    async with async_session() as db:
        rows = (await db.execute(select(Contact).where(Contact.engagement > 0, Contact.engaged_at < now - FULL).limit(2000))).scalars().all()
        for contact in rows:
            await recompute(db, contact, now)
            done += 1
        await db.commit()
    return done
