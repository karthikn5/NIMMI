"""
Journeys (mail plan, phase 4): what each lead gets, as a list of steps. A journey starts from a trigger (a new lead, a status change, a meeting,
someone becoming a customer, a date in their details) and runs its steps: an email, a WhatsApp message, a call, a wait, a branch, a change to the
contact, a word or a to-do for the team. Its goal ends it. A reply ends every journey the person is on, and an unsubscribe, a spam report or the
do-not-call list stop everything before the next step.

One run per person per journey at a time (slot "active"), and not again for RESTART_AFTER. The scheduler claims each run that's due, so one process
advances it, and each step is saved before the next, so a restart doesn't repeat a message. No database connection is held while a model writes or
a message goes out. One cap holds across everything sent to a person. Messages keep to quiet hours (not the first answer to a new lead), and waits
of a day or more end at about the hour they last picked up. A journey's call is a Schedule follow-up: its hours, limits, switch and 7-day rule decide.
"""
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from assist import DAYS
from backend.models import Bot, CallbackJob, Contact, EmailJob, EmailLink, EmailThread, Journey, JourneyRun, Meeting, ThreadMessage, User, WhatsAppChat
from database import async_session
from mail import address, compose, consent, render, senders, setup, suppress

logger = logging.getLogger(__name__)

TRIGGERS = {"new_lead": "A new lead", "status": "Their lead status changes", "meeting_booked": "A meeting is booked", "meeting_attended": "A meeting is attended",
            "meeting_missed": "A meeting is missed", "customer": "They become a customer", "date": "A date in their details"}
SOURCES = {"chat": "Website chat", "call": "A phone call", "whatsapp": "WhatsApp", "instagram": "Instagram (messages and comments)", "form": "A website form",
           "portal": "A portal such as IndiaMART", "meta": "Facebook or Instagram lead ads", "google": "Google lead forms",
           "ads": "An ad's lead form (Google, Facebook, Instagram)", "any_ad": "Any ad: lead forms, WhatsApp and Instagram ads, website visits from ads"}
GOALS = {"replied": "They reply or talk to you", "booked": "They book a meeting", "customer": "They become a customer"}
STEPS = ("email", "wait", "whatsapp", "call", "branch", "update", "notify")
TESTS = {"replied": "They replied", "clicked": "They clicked a link", "downloaded": "They downloaded a file", "booked": "They booked a meeting"}
STAGES = ("new", "contacted", "interested", "meeting", "customer", "lost")
STAGE_OF = {"hot": "interested", "warm": "interested", "cold": "contacted", "new": "contacted", "not_interested": "lost", "customer": "customer"}  # by lead status
QUIET = ["09:00", "20:00"]              # when messages may go
MAX_STEPS = 20
BATCH = 20
SAFETY = 12                             # steps one pass runs before it comes back
STUCK = timedelta(minutes=5)            # a claim older than this was lost with its process
PERSON_WAIT = timedelta(hours=6)        # someone on the team is working them: the journey looks again this much later
START_DELAY = timedelta(seconds=30)     # lets what else is happening now (a welcome email) be queued first, so the cap sees it
RESTART_AFTER = timedelta(days=30)      # someone going round the same journey again
POLL = timedelta(hours=1)               # how often a wait for something looks again
SOON = timedelta(minutes=15)            # an email about to go counts towards the cap
AI_SECONDS = 45

AI_EMAIL = ("Rewrite this email from {business} so it fits this person, in plain warm words, at most 120 words. Use only the knowledge and what you're told about them. "
            "No prices, dates or numbers that aren't there. Reply with the email's body only, without a subject.")
AI_READY = ("These are the emails of a journey for a business's leads. Rewrite each in the business's own words from its knowledge, in plain warm words, at most 90 words "
            "each. Keep everything in double curly brackets exactly as it is, such as {{first_name|there}} and {{business}}. No prices, dates or numbers that aren't in the knowledge. Reply with JSON only: a list of "
            '{"subject": "...", "body": "..."}, one for each email, in the same order.')


def _email(subject: str, body: str) -> dict:
    return {"type": "email", "subject": subject, "body": body}


def _wait(days: int = 0, hours: int = 0) -> dict:
    return {"type": "wait", "days": days, "hours": hours}


READY = {
    "new_lead": {"name": "New website lead", "about": "Thanks them, follows up after two days, then tells your team.", "trigger": "new_lead", "goal": "replied", "steps": [
        _email("Thanks for contacting {{business}}", "Hi {{first_name|there}},\n\nThanks for your interest in {{business}}. Reply to this email with anything you'd like to know."),
        _wait(days=2),
        _email("Still looking?", "Hi {{first_name|there}},\n\nI wanted to check whether you still need help. Just reply, and we'll take it from there."),
        _wait(days=3), {"type": "notify", "text": "{{name|This lead}} hasn't replied: worth a call.", "todo": True}]},
    "after_call": {"name": "After a call with someone interested", "about": "For hot leads: an email the next day, then a call.", "trigger": "status", "trigger_value": "hot", "goal": "booked", "steps": [
        _wait(days=1), _email("Good speaking with you", "Hi {{first_name|there}},\n\nIt was good speaking with you. Let us know a good time to take this forward."),
        _wait(days=2), {"type": "call", "about": "Follow up on their interest and offer to book a meeting."}]},
    "not_reached": {"name": "Couldn't reach them", "about": "For new leads you haven't reached: a short email, then a call.", "trigger": "status", "trigger_value": "new", "goal": "replied", "steps": [
        _email("We tried to reach you", "Hi {{first_name|there}},\n\nWe tried to reach you. Reply with a good time and we'll call you then."),
        _wait(days=2), {"type": "call", "about": "Try them again about their enquiry."}]},
    "meeting_missed": {"name": "Meeting missed", "about": "A kind note, and a to-do for your team if they don't reply.", "trigger": "meeting_missed", "goal": "booked", "steps": [
        _wait(days=1), _email("Shall we find another time?", "Hi {{first_name|there}},\n\nWe're sorry we missed you. Reply with a time that suits you and we'll set it up."),
        _wait(days=3), {"type": "notify", "text": "{{name|This lead}} missed their meeting and hasn't rebooked.", "todo": True}]},
    "cold": {"name": "Cold lead", "about": "One useful note a week later. Only for people who agreed to offers and news.", "trigger": "status", "trigger_value": "cold", "options": {"marketing": True}, "goal": "replied", "steps": [
        _wait(days=7), _email("Something that may help", "Hi {{first_name|there}},\n\nIf the timing wasn't right before, we're still here. Reply whenever you'd like to talk.")]},
    "customer": {"name": "New customer", "about": "A welcome, how to get started, then a review request and a referral ask.", "trigger": "customer", "goal": None, "steps": [
        _email("Welcome to {{business}}", "Hi {{first_name|there}},\n\nWelcome, and thank you for choosing {{business}}. Reply any time you need us."),
        _wait(days=2), _email("Getting started", "Hi {{first_name|there}},\n\nHere's how to get the most from {{business}}. Tell us if anything isn't clear."),
        _wait(days=14), _email("How are we doing?", "Hi {{first_name|there}},\n\nIf you're happy with us, a short review would mean a lot.\n\n{{feedback_link}}"),
        _wait(days=14), _email("Know someone who'd like this?", "Hi {{first_name|there}},\n\nIf you know someone who could use {{business}}, please send them our way.")]},
    "feedback": {"name": "Feedback after a meeting", "about": "Asks how it went: good or bad, with a comment.", "trigger": "meeting_attended", "goal": None, "steps": [
        _wait(days=1), _email("How did it go?", "Hi {{first_name|there}},\n\nHow was your meeting with {{business}}? It takes a few seconds:\n\n{{feedback_link}}")]},
    "service_due": {"name": "Service due", "about": "A reminder a week before the date in their details.", "trigger": "date", "trigger_value": "service_due", "options": {"days_before": 7}, "goal": "booked", "steps": [
        _email("Your service is coming up", "Hi {{first_name|there}},\n\nYour service with {{business}} is due on {{service_due}}. Reply with a time that suits you and we'll book it."),
        _wait(days=3), {"type": "notify", "text": "{{name|This customer}}'s service is due soon and they haven't booked.", "todo": True}]},
}


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _known_test(test: str) -> bool:
    return test in TESTS or test.startswith(("status:", "detail:"))


def checked(steps) -> list[dict]:
    """A journey's steps as saved from the dashboard or written by a model. Raises ValueError with what to fix."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("Add at least one step")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"A journey can have up to {MAX_STEPS} steps")
    out = []
    for n, step in enumerate(steps, 1):
        kind = step.get("type") if isinstance(step, dict) else None
        if kind not in STEPS:
            raise ValueError(f"Step {n} isn't a step Nimmi knows")
        if kind == "email":
            subject, body = str(step.get("subject") or "").strip()[:200], str(step.get("body") or "").strip()[:5000]
            if not subject or not body:
                raise ValueError(f"Step {n}: add a subject and a message")
            out.append({"type": kind, "subject": subject, "body": body, "ai": bool(step.get("ai"))})
        elif kind == "wait":
            weekday = str(step.get("weekday") or "")
            if weekday:
                at = str(step.get("at") or "10:00")
                if weekday not in DAYS or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
                    raise ValueError(f"Step {n}: choose a day and an hour")
                out.append({"type": kind, "weekday": weekday, "at": at})
                continue
            days, hours, until = _int(step.get("days")), _int(step.get("hours")), str(step.get("until") or "")
            if days < 0 or hours < 0 or days * 24 + hours < 1 or days > 365:
                raise ValueError(f"Step {n}: wait at least an hour, and at most a year")
            if until and not _known_test(until):
                raise ValueError(f"Step {n}: choose what to wait for")
            out.append({"type": kind, "days": days, "hours": hours, **({"until": until[:60]} if until else {})})
        elif kind == "whatsapp":
            text = str(step.get("text") or "").strip()[:1000]
            if not text:
                raise ValueError(f"Step {n}: add the message")
            out.append({"type": kind, "text": text, "subject": str(step.get("subject") or "").strip()[:200], "template": str(step.get("template") or "").strip()[:120]})
        elif kind == "call":
            out.append({"type": kind, "about": str(step.get("about") or "").strip()[:300]})
        elif kind == "branch":
            test = str(step.get("if") or "")
            if not _known_test(test):
                raise ValueError(f"Step {n}: choose what to check")
            out.append({"type": kind, "if": test[:60], "not": bool(step.get("not")), "then": "end" if step.get("then") == "end" else "skip", "skip": max(_int(step.get("skip")), 1)})
        elif kind == "update":
            stage, status, tag, owner = (str(step.get(k) or "").strip() for k in ("stage", "status", "tag", "owner"))
            if stage and stage not in STAGES or status and status not in STAGE_OF:
                raise ValueError(f"Step {n}: that stage or status doesn't exist")
            if not (stage or status or tag or owner):
                raise ValueError(f"Step {n}: say what to change")
            out.append({"type": kind, "stage": stage, "status": status, "tag": tag[:40], "owner": owner[:36]})
        else:
            text = str(step.get("text") or "").strip()[:500]
            if not text:
                raise ValueError(f"Step {n}: say what to tell your team")
            out.append({"type": kind, "text": text, "todo": bool(step.get("todo"))})
    return out


def checked_start(trigger: str, value: Optional[str], goal: Optional[str], options: Optional[dict]) -> tuple[Optional[str], Optional[str], dict]:
    """What starts a journey and what ends it, as saved: (trigger_value, goal, options). Raises ValueError with what to fix."""
    if trigger not in TRIGGERS or (goal and goal not in GOALS):
        raise ValueError("Choose what starts it, and what ends it")
    value = (value or "").strip() or None
    if trigger == "new_lead" and value and value not in SOURCES:
        raise ValueError("Choose where the lead comes from")
    if trigger == "status" and value not in STAGE_OF:
        raise ValueError("Choose the lead status")
    if trigger == "date" and not value:
        raise ValueError("Say which date in their details starts it")
    if trigger not in ("new_lead", "status", "date"):
        value = None
    if goal == "customer" and "customer" in (trigger, value):
        goal = None  # they're one already: it would end before its first step
    options = options or {}
    marketing = {"marketing": True} if options.get("marketing") else {}
    if trigger != "date":
        return value, goal or None, marketing
    days = _int(options.get("days_before"))
    if not 0 <= days <= 365:
        raise ValueError("Say how many days before the date it starts")
    return value[:60], goal or None, {"days_before": days, "yearly": bool(options.get("yearly")), **marketing}


def move_stage(contact: Contact, stage: str) -> None:
    """Where a lead stands moves forward by itself; only the team moves someone back. A lost lead who comes back moves on; a customer stays one."""
    current = contact.stage or "new"
    if stage == "lost":
        contact.stage = current if current == "customer" else "lost"
    elif current == "lost" or STAGES.index(stage) > STAGES.index(current):
        contact.stage = stage


# ─── starting ────────────────────────────────────────────────────
async def find_contact(db, bot_id: str, e164: Optional[str], address: Optional[str]) -> Optional[Contact]:
    if e164:
        found = (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalars().first()
        if found is not None:
            return found
    if address:
        return (await db.execute(select(Contact).where(Contact.bot_id == bot_id, func.lower(Contact.email) == address.lower())
                                 .order_by(Contact.created_at))).scalars().first()
    return None


async def _start(journey_id: str, owner_id: str, bot_id: str, contact_id: str, now: datetime, at: Optional[datetime] = None) -> bool:
    async with async_session() as db:
        again = (await db.execute(select(JourneyRun.id).where(JourneyRun.journey_id == journey_id, JourneyRun.contact_id == contact_id,
                                                              JourneyRun.started_at >= now - RESTART_AFTER).limit(1))).first()
        if again:
            return False
        db.add(JourneyRun(journey_id=journey_id, user_id=owner_id, bot_id=bot_id, contact_id=contact_id, slot="active", status="active", step=0,
                          next_at=at or now + START_DELAY, history=[], started_at=now))
        try:
            await db.commit()
        except IntegrityError:  # already on it: two things at once, or another process
            await db.rollback()
            return False
    return True


async def fire(owner_id: str, bot_id: str, trigger: str, contact_id: Optional[str], value=None, now: Optional[datetime] = None) -> int:
    """Something happened to a contact: the journeys it starts. `value`: one, or several from the most specific (a new lead from a Facebook lead ad is
    "meta", "ads" and "any_ad"). A new lead gets one follow-up plan (instagram_plan.md 4.4: one chase at a time): the journey for the most specific
    source, else one for any lead, and none while they're on a new-lead journey already. Best effort; never raises. Returns how many started."""
    if not contact_id or not bot_id:
        return 0
    import plans
    values = [v for v in (value if isinstance(value, (list, tuple)) else [value]) if v]
    started = 0
    try:
        async with async_session() as db:
            if not (await plans.includes(db, bot_id)).email_alerts:
                return 0
            rows = (await db.execute(select(Journey).where(Journey.bot_id == bot_id, Journey.trigger == trigger, Journey.enabled.is_(True))
                                     .order_by(Journey.created_at))).scalars().all()
            if trigger == "new_lead" and (await db.execute(select(JourneyRun.id).join(Journey, Journey.id == JourneyRun.journey_id).where(
                    JourneyRun.contact_id == contact_id, JourneyRun.status == "active", Journey.trigger == "new_lead").limit(1))).first():
                return 0  # already on a new lead's journey: the chase they're in goes on
        rows = sorted((j for j in rows if not j.trigger_value or j.trigger_value in values),
                      key=lambda j: values.index(j.trigger_value) if j.trigger_value else len(values))
        for journey in rows:
            if await _start(journey.id, owner_id, bot_id, contact_id, now or datetime.utcnow()):
                started += 1
                if trigger == "new_lead":
                    break
    except Exception as e:
        logger.warning(f"Starting journeys ({trigger}) for {contact_id} failed: {e}")
    return started


async def fire_for(owner_id: str, bot_id: str, trigger: str, e164: Optional[str], address: Optional[str], value=None) -> int:
    """`fire`, for someone known by number or email. Best effort; never raises."""
    try:
        async with async_session() as db:
            contact = await find_contact(db, bot_id, e164, address)
    except Exception as e:
        logger.warning(f"Finding a contact for journeys ({trigger}) failed: {e}")
        return 0
    return await fire(owner_id, bot_id, trigger, contact.id if contact else None, value)


def _end(run: JourneyRun, status: str, why: str) -> None:
    run.status, run.reason, run.ended_at, run.slot, run.claimed_at, run.next_at, run.wait_ends = status, why[:200], datetime.utcnow(), run.id, None, None, None


async def stop_for(db, owner_id: str, contact_ids: list[str], why: str) -> int:
    """End every run of these people (the caller commits)."""
    if not contact_ids:
        return 0
    runs = (await db.execute(select(JourneyRun).where(JourneyRun.user_id == owner_id, JourneyRun.contact_id.in_(contact_ids), JourneyRun.status == "active"))).scalars().all()
    for run in runs:
        _end(run, "stopped", why)
    return len(runs)


async def stopped_by_reply(db, thread: EmailThread) -> None:
    """They replied, so nothing else goes out by itself (mail/inbound.py; the caller commits). Only with this assistant: one account can run several businesses."""
    people = (await db.execute(select(Contact).where(Contact.user_id == thread.user_id, Contact.bot_id == thread.bot_id, func.lower(Contact.email) == thread.email))).scalars().all()
    from leads import contact as reach
    for contact in people:
        move_stage(contact, "contacted")
        await reach.stop_chase(db, contact, "They replied")  # journeys, follow-up calls and the email agent's waiting emails, all at once


# ─── what's known about them ─────────────────────────────────────
def _key(name) -> str:
    return re.sub(r"\W+", "_", str(name)).strip("_").lower()


def _detail(contact: Contact, name: str):
    wanted = _key(name)
    return next((v for k, v in (contact.details or {}).items() if _key(k) == wanted and v not in (None, "", [])), None)


def _values(contact: Contact, sender) -> dict:
    from mail import links
    details = {_key(k): v for k, v in (contact.details or {}).items() if isinstance(v, (str, int, float))}
    return {**details, "name": contact.name or "", "first_name": compose._first_name(contact.name) or "", "business": sender.name, "email": contact.email or "",
            "phone": contact.e164 or "", "feedback_link": links.feedback_url(contact.id) if contact.id else ""}


def _after(at: Optional[datetime], since: Optional[datetime]) -> bool:
    from voice import schedule
    return bool(at and since and schedule.utc(at) >= schedule.utc(since))


async def _test(db, test: str, run: JourneyRun, contact: Contact) -> bool:
    since, address = run.started_at, (contact.email or "").lower()
    if test == "replied":
        if _after(contact.last_call_at, since) or _after(contact.last_chat_at, since):
            return True  # on the phone or WhatsApp: they talked to you
        return bool(address and (await db.execute(select(ThreadMessage.id).join(EmailThread, EmailThread.id == ThreadMessage.thread_id).where(
            EmailThread.user_id == run.user_id, EmailThread.bot_id == run.bot_id, EmailThread.email == address, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True),
            ThreadMessage.created_at >= since).limit(1))).first())
    if test == "clicked":
        return bool(address and (await db.execute(select(EmailJob.id).where(EmailJob.user_id == run.user_id, func.lower(EmailJob.to_email) == address,
                                                                            EmailJob.clicked_at >= since).limit(1))).first())
    if test == "downloaded":
        return bool(address and (await db.execute(select(EmailLink.token).join(EmailJob, EmailJob.id == EmailLink.job_id).where(
            EmailJob.user_id == run.user_id, func.lower(EmailJob.to_email) == address, EmailLink.kind == "file", EmailLink.first_at >= since).limit(1))).first())
    if test == "booked":
        who = [Meeting.e164 == contact.e164] if contact.e164 else []
        who += [func.lower(Meeting.email) == address] if address else []
        return bool(who and (await db.execute(select(Meeting.id).where(Meeting.bot_id == run.bot_id, or_(*who), Meeting.created_at >= since,
                                                                       Meeting.status.in_(("requested", "proposed", "confirmed", "done"))).limit(1))).first())
    if test.startswith("status:"):
        return contact.lead_status == test.split(":", 1)[1]
    if test.startswith("detail:"):
        return _detail(contact, test.split(":", 1)[1]) is not None
    return False


async def _why_stop(db, run: JourneyRun, journey: Optional[Journey], contact: Optional[Contact], bot: Optional[Bot]) -> Optional[tuple[str, str]]:
    """Why this run ends before its next step: (status, why), or None. ("wait", why): not now, as a person on the team is working them."""
    import plans
    from voice import schedule
    if journey is None or bot is None:
        return "stopped", "The journey is gone"
    if contact is None:
        return "stopped", "They're no longer in Contacts"
    if not journey.enabled:
        return "stopped", "The journey was turned off"
    if not (await plans.includes(db, run.bot_id)).email_alerts:
        return "stopped", "The plan no longer includes journeys"
    if contact.email and await suppress.why_blocked(db, run.user_id, contact.email, marketing=True):
        return "stopped", "They can't be emailed any more"
    if contact.e164 and await schedule.on_dnc(db, run.user_id, contact.e164):
        return "stopped", "They're on the do-not-call list"
    if (journey.options or {}).get("marketing") and not (contact.email and await consent.has(db, run.bot_id, contact.email)):
        return "stopped", "They haven't agreed to offers and news"
    if journey.goal == "replied" and await _test(db, "replied", run, contact):
        return "done", "They replied"
    if journey.goal == "booked" and await _test(db, "booked", run, contact):
        return "done", "They booked a meeting"
    if journey.goal == "customer" and "customer" in (contact.lead_status, contact.stage):
        return "done", "They became a customer"
    from leads import contact as reach
    # One chase at a time (leads/contact.py): junk, a person on the team working them, or (for a new lead's journey) a closed lead or a meeting ends it. A
    # journey made for lost leads, customers or meetings isn't ended by what started it.
    skip = ("closed", "meeting") if journey.trigger != "new_lead" else ()
    stop = await reach.blockers(db, contact, "email" if contact.email else "call", "marketing" if (journey.options or {}).get("marketing") else "service", skip=skip)
    if stop is not None and stop.code == "person":  # someone on the team is on it: the journey waits for them, it doesn't end
        return "wait", stop.reason
    if stop is not None and stop.code not in ("no_email", "no_number", "email_blocked", "dnc"):  # those are above, worded for journeys
        return "stopped", stop.reason
    return None


# ─── the steps ───────────────────────────────────────────────────
def _in_hours(at: datetime, tz) -> datetime:
    from voice import schedule
    return schedule.stored(schedule.next_allowed(schedule.utc(at), QUIET, schedule.DAYS, tz))


def _quiet_until(run: JourneyRun, journey: Journey, now: datetime, tz) -> Optional[datetime]:
    """When a message may go, if now is quiet hours. Someone who has just asked hears back at once, at any hour."""
    from voice import schedule
    if journey.trigger == "new_lead" and run.step == 0:
        return None
    soon = _in_hours(now, tz)
    return soon if schedule.utc(soon) > schedule.utc(now) else None


async def _cap_until(db, run: JourneyRun, to: str, now: datetime) -> Optional[datetime]:
    """When the next journey email to this person may go, if not now. Everything the business sent them counts, so one never lands on top of a welcome
    email or a newsletter; only journeys wait for it."""
    from voice import schedule
    prefs = (await setup.settings_for(db, run.bot_id))["journeys"]
    rows = (await db.execute(select(EmailJob.send_at).where(
        EmailJob.user_id == run.user_id, func.lower(EmailJob.to_email) == to.lower(), EmailJob.status.in_(("queued", "sent")),
        EmailJob.send_at >= now - timedelta(days=7), EmailJob.send_at <= now + SOON).order_by(EmailJob.send_at))).scalars().all()
    week, clock = [schedule.utc(at) for at in rows], schedule.utc(now)
    today = [at for at in week if at > clock - timedelta(days=1)]
    if len(today) >= int(prefs["per_day"]):
        return today[0] + timedelta(days=1)
    if len(week) >= int(prefs["per_week"]):
        return week[0] + timedelta(days=7)
    return None


async def _held(db, run: JourneyRun, to: str, tz, now: datetime) -> bool:
    later = await _cap_until(db, run, to, now)
    if later is None:
        return False
    run.next_at = _in_hours(later, tz)
    _note(run, "Waiting: the limit on emails to one person", now)
    return True


def _queue_email(db, run: JourneyRun, contact: Contact, subject: str, body: str, now: datetime) -> None:
    db.add(EmailJob(user_id=run.user_id, bot_id=run.bot_id, kind=f"journey#{run.step}", ref_id=run.id, to_email=contact.email, automation="journey", step=1,
                    subject=subject, body=body, send_at=now, merge_data={"name": contact.name}))


async def _write_email(db, bot: Bot, contact: Contact, step: dict, sender) -> tuple[str, str]:
    """An email step, filled in. With `ai`, a model fits it to the person from the knowledge; without an answer, or AI replies left, the words stand."""
    import plans
    values = _values(contact, sender)
    subject, body = render.fill(step["subject"], values)[:200], render.fill(step["body"], values)
    if not step.get("ai") or not await plans.can_reply(db, bot.bot_id):
        return subject, body
    await db.commit()  # no connection is held while the model writes
    from voice import llm
    written = ""
    try:
        knowledge = await llm.call_knowledge(bot)
        told = json.dumps({"name": contact.name, "details": contact.details or {}}, ensure_ascii=False)[:1000]
        raw = await compose.ask_model(bot, AI_EMAIL.format(business=sender.name), f"The email:\n{body}\n\nWhat we know about them:\n{told}\n\nKnowledge:\n{knowledge[:5000]}", 500, AI_SECONDS)
        written = compose.keep_known_numbers(re.sub(r"[*`]", "", raw or "").strip(), f"{body}\n{told}\n{knowledge}")
        if not all(link in written for link in re.findall(r"https?://\S+", body)):
            written = ""  # a review link or a feedback link is the point of such an email
    except Exception as e:
        logger.warning(f"Writing a journey email for {bot.bot_id} failed: {e!r}")
    if written:
        await plans.count_reply(bot.bot_id)  # an AI-written email counts as one AI reply
    return subject, written or body


async def _whatsapp(db, run: JourneyRun, contact: Contact, sender, step: dict, tz, now: datetime) -> Optional[str]:
    """Inside the 24-hour window, a WhatsApp message. Outside it, the same words by email, about 25 times cheaper than a template (mail plan 2.6), and only
    without an email the template it names. Returns what happened; None when the cap holds the run."""
    from notify import channels
    from whatsapp import chats as wa_chats, numbers, outbound
    values = _values(contact, sender)
    text, chat = render.fill(step["text"], values), None
    number = await numbers.workspace_number(db, run.user_id)
    if number is not None and number.status != "disconnected" and number.access_token and contact.e164:
        chat = (await db.execute(select(WhatsAppChat).where(WhatsAppChat.number_id == number.id, WhatsAppChat.wa_id == contact.e164.lstrip("+")))).scalars().first()
    if chat is not None and chat.conversation_id and wa_chats.window_open(chat):
        await db.commit()  # no connection is held while Meta answers
        sent = await outbound.send_text(number, chat, text, sent_by="ai")
        return f"WhatsApp didn't take it: {sent.error}" if sent.status == "failed" else "Sent on WhatsApp"
    if contact.email:
        if await _held(db, run, contact.email, tz, now):
            return None
        _queue_email(db, run, contact, step.get("subject") or f"A message from {sender.name}", text, now)
        return "Outside WhatsApp's 24-hour window: sent by email instead"
    if chat is not None and step.get("template"):
        from leads import contact as reach
        allowed = await reach.can_contact(db, contact, "whatsapp", hours=False)
        if not allowed.ok:
            return f"Skipped the WhatsApp template: {allowed.reason}"
        await db.commit()
        try:
            await channels.send_whatsapp_template(contact.e164, step["template"], "en", [values["first_name"] or "there", values["business"]],
                                                  phone_number_id=number.phone_number_id, token=number.access_token)
            return "Sent the WhatsApp template"
        except Exception as e:
            return f"The WhatsApp template didn't go: {str(e)[:120]}"
    return "Skipped: outside WhatsApp's 24-hour window, and no email for them"


async def _call(db, run: JourneyRun, journey: Journey, contact: Contact, step: dict, now: datetime) -> str:
    """A Schedule follow-up: its checks run again before it dials (schedule.dial_check), so the 7-day rule, the limits and the do-not-call list hold."""
    import plans
    from voice import schedule
    if not contact.e164:
        return "Skipped: no number for them"
    if not (await plans.includes(db, run.bot_id)).schedule:
        return "Skipped: calls come with the Pro plan"
    settings = await schedule.settings_for(run.bot_id, db)
    fu, tz = settings["follow_ups"], schedule.zone(settings)
    if not fu["enabled"]:
        return "Skipped: follow-up calls are off in Voice > Schedule"
    if contact.follow_ups_off:
        return "Skipped: follow-ups were stopped for them"
    for kind in ("callback", "person", "follow_up"):
        if await schedule.waiting_job(db, run.bot_id, contact.e164, kind):
            return "Skipped: a call to them is already waiting"
    at = schedule.next_allowed(schedule.utc(now), fu["hours"], fu["days"], tz, await schedule.holidays(run.user_id))
    db.add(CallbackJob(user_id=run.user_id, bot_id=run.bot_id, e164=contact.e164, name=contact.name, kind="follow_up", status="review" if fu["review"] else "queued",
                       next_attempt_at=schedule.stored(at), purpose=(step.get("about") or "Follow up on their enquiry.")[:600], variables={"step": 0, "journey": run.id},
                       consent_source=f"Journey \"{journey.name}\", after their enquiry on {schedule.utc(contact.created_at or now).astimezone(tz):%d %b %Y}"[:200]))
    return f"Call planned: {schedule.when_text(at, tz)}"


async def _tell_team(db, run: JourneyRun, journey: Journey, contact: Contact, sender, step: dict) -> str:
    from notify import events
    text = render.fill(step["text"], _values(contact, sender))
    if step.get("todo") and contact.e164:
        db.add(CallbackJob(user_id=run.user_id, bot_id=run.bot_id, e164=contact.e164, name=contact.name, kind="person", status="todo", next_attempt_at=datetime.utcnow(),
                           purpose=text[:600], consent_source=f"Journey \"{journey.name}\""[:200]))
        return "To-do added for the team"
    team = await events._settings(db, run.user_id)
    owner = (await db.execute(select(User.email).where(User.id == run.user_id))).scalar_one_or_none()
    await db.commit()  # no connection is held while the email goes
    who = " ".join(x for x in (contact.name, contact.email, contact.e164) if x)
    await events._email_team(events.recipients(team, owner), f"{journey.name}: {contact.name or contact.email or contact.e164}", f"{text}\n\n{who}", run.user_id)
    return "Told the team"


def _note(run: JourneyRun, what: str, now: datetime) -> None:
    run.history = [*(run.history or []), {"step": run.step, "at": now.isoformat(), "what": what[:200]}][-40:]


def _wait_ends(step: dict, now: datetime, contact: Contact, tz) -> datetime:
    from voice import schedule
    clock = schedule.utc(now)
    if step.get("weekday"):
        local = clock.astimezone(tz)
        at = datetime.combine(local.date() + timedelta(days=(DAYS.index(step["weekday"]) - local.weekday()) % 7),
                              datetime.strptime(step.get("at") or "10:00", "%H:%M").time(), tzinfo=tz)
        return at if at > local else at + timedelta(days=7)
    at = clock + timedelta(days=int(step.get("days") or 0), hours=int(step.get("hours") or 0))
    if not step.get("days"):
        return at
    return schedule._their_hour(at.astimezone(tz).date(), schedule.utc(contact.last_call_at), QUIET, tz, contact.e164 or contact.id)  # about the hour they last picked up


async def _wait_step(db, run: JourneyRun, contact: Contact, step: dict, tz, now: datetime) -> bool:
    """Until a time, or with `until`, until something happens or the time runs out. True when it's over."""
    from voice import schedule
    until = step.get("until")
    if not until:
        run.step += 1
        run.next_at = _in_hours(_wait_ends(step, now, contact, tz), tz)
        _note(run, "Waiting", now)
        return False
    if run.wait_ends is None:
        run.wait_ends = schedule.stored(_wait_ends(step, now, contact, tz))
        _note(run, f"Waiting for: {until}", now)
    happened = await _test(db, until, run, contact)
    if happened or schedule.utc(now) >= schedule.utc(run.wait_ends):
        run.wait_ends = None
        _note(run, "It happened" if happened else "It didn't happen in time", now)
        run.step += 1
        return True
    run.next_at = min(now + POLL, schedule.stored(schedule.utc(run.wait_ends)))
    return False


async def _step(db, run: JourneyRun, journey: Journey, contact: Contact, bot: Bot, sender, step: dict, tz, now: datetime) -> bool:
    """One step. True to go on to the next; False when the run stops here for now."""
    from voice import schedule
    kind = step.get("type")
    if kind == "wait":
        return await _wait_step(db, run, contact, step, tz, now)
    if kind in ("email", "whatsapp"):
        quiet = _quiet_until(run, journey, now, tz)
        if quiet:
            run.next_at = quiet
            _note(run, f"Waiting for {int(QUIET[0][:2])} am: no messages from {int(QUIET[1][:2]) - 12} pm to {int(QUIET[0][:2])} am", now)
            return False
    if kind == "email":
        if not contact.email:
            _note(run, "Skipped: no email for them", now)
        else:
            if await _held(db, run, contact.email, tz, now):
                return False
            await db.commit()  # the address check is a DNS lookup: no connection waits on it
            verdict = await address.check(contact.email)
            if not verdict.ok:
                _note(run, f"Skipped: {verdict.reason}", now)
            else:
                subject, body = await _write_email(db, bot, contact, step, sender)
                _queue_email(db, run, contact, subject, body, now)
                _note(run, f"Email: {subject}", now)
    elif kind == "whatsapp":
        what = await _whatsapp(db, run, contact, sender, step, tz, now)
        if what is None:
            return False
        _note(run, what, now)
    elif kind == "call":
        _note(run, await _call(db, run, journey, contact, step, now), now)
    elif kind == "branch":
        test = step.get("if") or ""
        if await _test(db, test, run, contact) != bool(step.get("not")):
            if step.get("then") == "end":
                _end(run, "done", f"Ended at a step: {test}")
                return False
            run.step += int(step.get("skip") or 1)
            _note(run, f"Skipped ahead: {test}", now)
    elif kind == "update":
        contact.stage = step.get("stage") or contact.stage
        if step.get("status"):
            schedule.rate(contact, step["status"], f"Journey: {journey.name}")
        if step.get("tag"):
            contact.tags = sorted({*(contact.tags or []), step["tag"]})
        contact.assigned_to = step.get("owner") or contact.assigned_to
        _note(run, "Contact updated", now)
    elif kind == "notify":
        _note(run, await _tell_team(db, run, journey, contact, sender, step), now)
    run.step += 1
    return True


async def advance(run_id: str, now: Optional[datetime] = None) -> None:
    from voice import schedule
    now = now or datetime.utcnow()
    async with async_session() as db:
        claimed = await db.execute(update(JourneyRun).where(JourneyRun.id == run_id, JourneyRun.status == "active", or_(JourneyRun.claimed_at.is_(None), JourneyRun.claimed_at < now - STUCK))
                                   .values(claimed_at=now).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        run = await db.get(JourneyRun, run_id)
        journey, contact, bot = await db.get(Journey, run.journey_id), await db.get(Contact, run.contact_id), await db.get(Bot, run.bot_id)
        ended = await _why_stop(db, run, journey, contact, bot)
        if ended and ended[0] == "wait":
            if not run.history or run.history[-1].get("what") != ended[1][:200]:  # once, not every few hours
                _note(run, ended[1], now)
            run.next_at, run.claimed_at = now + PERSON_WAIT, None
            return await db.commit()
        if ended:
            _end(run, *ended)
            return await db.commit()
        sender = await senders.sender_for(db, run.user_id, run.bot_id)
        tz = schedule.zone(await schedule.settings_for(run.bot_id, db))
        steps = journey.steps or []
        for _ in range(SAFETY):
            if run.step >= len(steps):
                _end(run, "done", "It ran to the end")
                break
            if not await _step(db, run, journey, contact, bot, sender, steps[run.step], tz, now):
                break
            await db.commit()  # each step once, whatever happens to this process
        else:
            run.next_at = now
        run.claimed_at = None
        await db.commit()


# ─── dates ───────────────────────────────────────────────────────
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d %b", "%d %B")


def date_of(value) -> Optional[date]:
    """A date as people write it in India, day first. Without a year it's 1900: good only for a yearly journey."""
    text = str(value or "").strip()
    for form in DATE_FORMATS:
        try:
            return datetime.strptime(text, form).date()
        except ValueError:
            continue
    return None


def date_due(journey: Journey, value, today: date) -> bool:
    when, options = date_of(value), journey.options or {}
    if when is None:
        return False
    target = today + timedelta(days=int(options.get("days_before") or 0))
    return (when.month, when.day) == (target.month, target.day) if options.get("yearly") else when == target


async def _dates(now: datetime) -> None:
    """Once a day per journey, India time: the people whose date has come. Their first message waits for morning."""
    import plans
    from voice import schedule
    today = schedule.utc(now).astimezone(plans.IST).date()
    stamp = today.isoformat()
    waiting = or_(Journey.scanned_on.is_(None), Journey.scanned_on != stamp)
    async with async_session() as db:
        ids = (await db.execute(select(Journey.id).where(Journey.trigger == "date", Journey.enabled.is_(True), waiting))).scalars().all()
    for journey_id in ids:
        async with async_session() as db:
            claimed = await db.execute(update(Journey).where(Journey.id == journey_id, waiting).values(scanned_on=stamp).execution_options(synchronize_session=False))
            await db.commit()
            if claimed.rowcount != 1:
                continue
            journey = await db.get(Journey, journey_id)
            if not (await plans.includes(db, journey.bot_id)).email_alerts:
                continue
            tz = schedule.zone(await schedule.settings_for(journey.bot_id, db))
            people = (await db.execute(select(Contact).where(Contact.bot_id == journey.bot_id).limit(20000))).scalars().all()
            due = [c.id for c in people if date_due(journey, _detail(c, journey.trigger_value), today)]
        for contact_id in due:
            await _start(journey.id, journey.user_id, journey.bot_id, contact_id, now, at=_in_hours(now, tz))


async def tick(now: Optional[datetime] = None) -> None:
    """Scheduler: the runs that are due, one step at a time. Each is claimed, so the processes share them."""
    now = now or datetime.utcnow()
    try:
        await _dates(now)
    except Exception as e:
        logger.exception(f"Starting journeys by date failed: {e}")
    async with async_session() as db:
        due = (await db.execute(select(JourneyRun.id).where(
            JourneyRun.status == "active", JourneyRun.next_at <= now, or_(JourneyRun.claimed_at.is_(None), JourneyRun.claimed_at < now - STUCK))
            .order_by(JourneyRun.next_at).limit(BATCH))).scalars().all()
    for run_id in due:
        try:
            await advance(run_id, now)
        except Exception as e:
            logger.exception(f"Advancing journey run {run_id} failed: {e}")


def with_tracked_links(job: EmailJob) -> tuple[str, list]:
    """The email's words with its links through Nimmi, and the links to save with it."""
    from mail import links
    tracker = links.Tracker(job.user_id, job.id)
    body = re.sub(r"https?://[^\s<>\"')\]]+", lambda m: tracker(m.group(0), "link", ""), job.body)
    return body, tracker.rows()


async def hold_back(db, job: EmailJob) -> Optional[str]:
    """Just before a journey's email goes: a reason to cancel it (notify/automations.py)."""
    import plans
    run = await db.get(JourneyRun, job.ref_id)
    if run is None or run.status == "stopped":
        return "The journey stopped"
    return None if (await plans.includes(db, job.bot_id)).email_alerts else "The plan no longer includes it"


async def from_knowledge(bot: Bot, steps: list[dict]) -> list[dict]:
    """A ready-made journey's emails in the business's own words. Without a model's answer, or knowledge to go on, the ready-made words stand."""
    from voice import llm
    emails = [step for step in steps if step["type"] == "email"]
    out = [dict(step) for step in steps]
    try:
        knowledge = (await llm.call_knowledge(bot) or "").strip()
        if not emails or not knowledge:
            return out
        raw = await compose.ask_model(bot, AI_READY, f"The business is {bot.bot_name}.\n\nThe emails:\n{json.dumps(emails, ensure_ascii=False)}\n\nKnowledge:\n{knowledge[:5000]}", 1500, 25)
        found = re.search(r"\[.*\]", raw or "", re.S)
        written = json.loads(found.group(0)) if found else []
        if len(written) != len(emails):
            return out
        words = iter(written)
        for step in out:
            if step["type"] != "email":
                continue
            new = next(words)
            body = compose.keep_known_numbers(str(new.get("body") or "").strip(), f"{step['body']}\n{knowledge}")
            if not all(part in body for part in re.findall(r"\{\{[^}]+\}\}", step["body"])):
                continue  # it lost a placeholder, such as the date in a service reminder
            step["subject"], step["body"] = str(new.get("subject") or step["subject"]).strip()[:200], body or step["body"]
    except Exception as e:
        logger.warning(f"Writing a ready-made journey for {bot.bot_id} failed: {e!r}")
        return [dict(step) for step in steps]
    return out
