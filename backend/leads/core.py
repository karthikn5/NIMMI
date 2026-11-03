"""
The working record of a lead (instagram_plan.md, phase 1): who looks after them, the next thing to do, what happened, how it ended.

A person is one Contact, whatever brought them in and however many times they ask. Each submission stays in LeadIntake, each outcome in LeadDeal, so someone who
buys and comes back keeps their old sale and gets new work. Calls, chats and emails stay in their own tables: the timeline only reads them. `visible` is the one
place that says who may see which lead: an agent reaches only the leads given to them.
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext
from backend.models import (Bot, CallbackJob, CallLog, Contact, Conversation, EmailJob, EmailThread, LeadDeal, LeadEvent, LeadIntake, LeadPromise, LeadSettings, LeadTask, Meeting, Message, TeamMember,
                            ThreadMessage, User, WhatsAppChat)
from database import async_session
from mail import journeys
from phone import display
from voice.schedule import WAITING, utc

logger = logging.getLogger(__name__)

OPEN = ("new", "contacted", "interested", "meeting")
KINDS = ("call", "whatsapp", "email", "visit", "other")
LOST_REASONS = ("Not interested", "Too expensive", "Bought elsewhere", "Couldn't reach them", "Wrong number", "Not a real enquiry", "Other")
RESULTS = {"reached": "Spoke to them", "no_answer": "No answer", "later": "Asked to be called later", "wrong_number": "Wrong number", "not_interested": "Not interested"}
RETRY = timedelta(hours=2)        # no answer: when to try again
RECENT = timedelta(days=14)       # how long a lead with no next step keeps asking for attention
NEW_FOR = timedelta(days=30)      # how long an unowned new lead does
REMIND_WITHIN = timedelta(days=1)  # older tasks aren't reminded of: nobody needs a pile of them after a pause
PASS_EVERY = timedelta(seconds=60)
BATCH = 50                        # reminders a pass sends at most; the oldest first
SETTINGS = {"assign": "off", "people": [], "backup": None, "first_task": True, "respond_minutes": 15,  # assign: off, one, turns
            # WhatsApp (phase 4): the approved template a new lead who agreed to WhatsApp gets at once ({{1}} their first name, {{2}} the business), and the one
            # that tells a salesperson about a lead ({{1}} what it is, {{2}} the link). None: not sent.
            "whatsapp_first": None, "whatsapp_language": "en", "alert_template": None, "alert_language": "en"}
_last_pass: Optional[datetime] = None
_last_event: datetime = datetime.min


def now() -> datetime:
    return datetime.utcnow()


def iso(at: Optional[datetime]) -> Optional[str]:
    return utc(at).isoformat() if at else None


def visible(ctx: AuthContext) -> list:
    """Which contacts this person may reach."""
    return [Contact.user_id == ctx.owner_id] + ([Contact.assigned_to == ctx.user_id] if ctx.role == "agent" else [])


async def team(db: AsyncSession, owner_id: str) -> list[dict]:
    """The workspace's people: the owner and everyone who has joined."""
    owner = await db.get(User, owner_id)
    rows = (await db.execute(select(TeamMember.member_id, User.name, User.email).join(User, User.id == TeamMember.member_id).where(
        TeamMember.owner_id == owner_id, TeamMember.status == "active"))).all()
    return [{"id": owner.id, "name": owner.name or owner.email, "email": owner.email}, *({"id": i, "name": name or address, "email": address} for i, name, address in rows)]


async def settings_of(db: AsyncSession, bot_id: str) -> dict:
    row = await db.get(LeadSettings, bot_id)
    return {**SETTINGS, **((row.settings if row else None) or {})}


async def save_settings(db: AsyncSession, owner_id: str, bot_id: str, values: dict) -> dict:
    row = await db.get(LeadSettings, bot_id)
    if row is None:
        row = LeadSettings(bot_id=bot_id, user_id=owner_id, settings={}, turn=0)
        db.add(row)
    row.settings = {**SETTINGS, **(row.settings or {}), **{k: v for k, v in values.items() if k in SETTINGS}}
    return row.settings


def event(contact: Contact, kind: str, text: Optional[str] = None, by: Optional[str] = None) -> LeadEvent:
    """Stamped here, each later than the one before: the database's own clock gives every row of one save the same time, and a lead's story would lose its order."""
    global _last_event
    _last_event = max(now(), _last_event + timedelta(microseconds=1))
    return LeadEvent(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, kind=kind, text=(text or "")[:1000] or None, by=by, at=_last_event)


async def open_tasks(db: AsyncSession, contact_id: str) -> list[LeadTask]:
    return (await db.execute(select(LeadTask).where(LeadTask.contact_id == contact_id, LeadTask.status == "open").order_by(LeadTask.due_at))).scalars().all()


async def _next_person(db: AsyncSession, bot_id: str, prefs: dict) -> Optional[str]:
    """Who a new lead goes to. By turns, the row's own update hands out each turn once, however many processes ask at the same moment."""
    if prefs["assign"] == "off":
        return None
    active = {p["id"] for p in await team(db, (await db.get(Bot, bot_id)).user_id)}
    people = [p for p in prefs["people"] if p in active]
    if not people:
        return None
    if prefs["assign"] == "one":
        return people[0]
    await db.execute(update(LeadSettings).where(LeadSettings.bot_id == bot_id).values(turn=func.coalesce(LeadSettings.turn, 0) + 1).execution_options(synchronize_session=False))
    turn = (await db.execute(select(LeadSettings.turn).where(LeadSettings.bot_id == bot_id).execution_options(populate_existing=True))).scalar_one()
    return people[(turn - 1) % len(people)]


def _first_title(contact: Contact) -> str:
    who = contact.name or contact.email or display(contact.e164) or "them"
    return f"Call {who}" if contact.e164 else f"Email {who}"


async def _came_in(contact_id: str, source: str, wants: Optional[str], origin: Optional[dict], first_step: bool, answered: bool) -> None:
    async with async_session() as db:
        if (await db.execute(select(Contact.quality).where(Contact.id == contact_id))).scalar_one_or_none() == "junk":
            return  # whoever marked it said why: nobody is given it and nothing is planned
        at = now()
        one = update(Contact).where(Contact.id == contact_id).values(last_enquiry_at=at).execution_options(synchronize_session=False)
        # Written first: two submissions at the same moment take turns from here, so the second sees the first's task.
        again = (await db.execute(one.where(Contact.last_enquiry_at.is_(None)))).rowcount == 0
        if again:
            await db.execute(one)
        contact = await db.get(Contact, contact_id)
        if contact is None:
            return
        prefs = await settings_of(db, contact.bot_id)
        contact.origin = contact.origin or origin
        if contact.quality == "old":  # someone from an old list asking now is a lead like any other
            contact.quality = None
        if answered:
            contact.first_response_at = contact.first_response_at or at
        if contact.stage == "lost":
            from voice import schedule
            contact.stage = "new"
            if contact.quality != "ok":
                contact.quality = None
            if contact.lead_status == "not_interested":
                schedule.rate(contact, "new", "They asked again")
                contact.stage = "new"
        said = f"{source}: {wants}" if wants else source
        db.add(event(contact, "asked_again" if again else "came_in", said))
        if not contact.assigned_to:
            contact.assigned_to = await _next_person(db, contact.bot_id, prefs)
            if contact.assigned_to:
                db.add(event(contact, "assigned", "Given to them by your rules"))
        tell = None
        if first_step and prefs["first_task"] and not await open_tasks(db, contact_id):
            due = at + timedelta(minutes=int(prefs["respond_minutes"]))
            db.add(LeadTask(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, title=_first_title(contact), kind="call" if contact.e164 else "email", due_at=due,
                            assigned_to=contact.assigned_to, origin="rule"))
            if contact.assigned_to and prefs.get("alert_template"):
                tell = (contact.user_id, contact.bot_id, contact.assigned_to, f"New lead: {_first_title(contact)} ({source})")
        await db.commit()
    if tell:  # their WhatsApp alert, off the lead's own path
        from notify.events import fire_and_forget
        fire_and_forget(whatsapp_alert(*tell, contact_id))


async def came_in(owner_id: str, contact_id: str, source: str, ref: str, wants: Optional[str] = None, origin: Optional[dict] = None, first_step: bool = True, answered: bool = False) -> None:
    """A lead arrived, new or asking again: once per `ref`. It never raises: the lead's own path goes on without this."""
    from notify import events

    async def go():
        await _came_in(contact_id, source, wants, origin, first_step, answered)
    key = hashlib.sha256(f"{contact_id}:{ref}".encode()).hexdigest()[:40]
    try:
        await events._once(owner_id, "lead_in", key, go)
    except Exception as e:
        logger.warning(f"Recording a lead for {contact_id} failed: {e!r}")


async def after_call(call_id: str) -> None:
    """Someone who rang and talked to the assistant has enquired, and has been answered: no first task, and they show under No next step until there is one. A call the
    business made isn't an enquiry, so it doesn't renew what an enquiry allows. Without a contact (Remember callers off) there's nothing to work on. Never raises."""
    from mail.after_call import TALKED, _heard_them
    try:
        async with async_session() as db:
            call = await db.get(CallLog, call_id)
            if call is None or call.channel != "phone" or call.direction != "inbound" or not call.bot_id or not call.caller_e164 or call.outcome not in TALKED or not _heard_them(call):
                return
            contact_id = (await db.execute(select(Contact.id).where(Contact.bot_id == call.bot_id, Contact.e164 == call.caller_e164))).scalars().first()
            owner_id = call.user_id
        if contact_id:
            await came_in(owner_id, contact_id, "Phone call", call_id, first_step=False, answered=True)
    except Exception as e:
        logger.warning(f"Recording a lead from call {call_id} failed: {e!r}")


async def merge(db: AsyncSession, src: Contact, into: Contact, why: str) -> None:
    """Two contacts that are one person (only on evidence they gave: a number or email they typed, never a name or a photo): everything of `src` moves
    to `into`, what `into` lacks is filled from `src`, and `src` goes. The caller commits."""
    from backend.models import ChannelPermission, EmailAgentAction, InstagramChat, JourneyRun
    if src.id == into.id or src.bot_id != into.bot_id:
        return
    for field in ("name", "email", "e164", "instagram_id", "instagram_username", "origin", "assigned_to", "lead_status", "lead_reason"):
        if not getattr(into, field) and getattr(src, field):
            value = getattr(src, field)
            if field == "e164":  # the number is unique per assistant: it moves only once src lets go of it
                src.e164 = None
                await db.flush()
            setattr(into, field, value)
    into.details = {**(src.details or {}), **(into.details or {})}
    into.tags = sorted({*(into.tags or []), *(src.tags or [])}) or None
    if src.notes:
        into.notes = f"{into.notes}\n{src.notes}".strip() if into.notes else src.notes
    for field, pick in (("last_enquiry_at", max), ("first_response_at", min), ("last_chat_at", max)):
        values = [v for v in (getattr(into, field), getattr(src, field)) if v is not None]
        if values:
            setattr(into, field, pick(_naive(v) for v in values))
    if (into.stage or "new") == "new" and src.stage:
        into.stage = src.stage
    for model in (LeadTask, LeadEvent, LeadDeal, EmailAgentAction):
        await db.execute(update(model).where(model.contact_id == src.id).values(contact_id=into.id).execution_options(synchronize_session=False))
    for model in (Conversation, LeadIntake, InstagramChat):
        await db.execute(update(model).where(model.contact_id == src.id).values(contact_id=into.id).execution_options(synchronize_session=False))
    have = {(p.channel, p.purpose) for p in (await db.execute(select(ChannelPermission).where(ChannelPermission.contact_id == into.id))).scalars().all()}
    for p in (await db.execute(select(ChannelPermission).where(ChannelPermission.contact_id == src.id))).scalars().all():
        if (p.channel, p.purpose) in have:
            await db.delete(p)
        else:
            p.contact_id = into.id
    await journeys.stop_for(db, src.user_id, [src.id], "Joined with another contact")
    await db.execute(update(JourneyRun).where(JourneyRun.contact_id == src.id, JourneyRun.status != "active").values(contact_id=into.id)
                     .execution_options(synchronize_session=False))
    db.add(event(into, "merged", f"The same person as {src.name or src.instagram_username or 'another contact'}: {why}"))
    await db.flush()
    await db.delete(src)


def _naive(at: datetime) -> datetime:
    return at.replace(tzinfo=None) if at.tzinfo else at


async def find_or_make(bot: Bot, phone: Optional[str], address: Optional[str], name: Optional[str], source: str) -> Optional[str]:
    """The contact for a WhatsApp lead, which `mail/contacts.py` leaves to the chat's memory. None when the assistant keeps no contacts."""
    from backend.models import VoiceAgent
    from sqlalchemy.exc import IntegrityError
    for _ in range(2):
        async with async_session() as db:
            found = await journeys.find_contact(db, bot.bot_id, phone, address)
            if found is not None:
                return found.id
            if (await db.execute(select(VoiceAgent.remember_callers).where(VoiceAgent.bot_id == bot.bot_id))).scalar_one_or_none() is False:
                return None
            contact = Contact(user_id=bot.user_id, bot_id=bot.bot_id, e164=phone, email=address, name=name, details={}, calls=0, source=source)
            db.add(contact)
            try:
                await db.commit()
                return contact.id
            except IntegrityError:
                await db.rollback()
    return None


def lead_json(c: Contact, task: Optional[LeadTask] = None, names: Optional[dict] = None, bots: Optional[dict] = None) -> dict:
    return {"id": c.id, "name": c.name, "email": c.email, "phone": display(c.e164) if c.e164 else None, "e164": c.e164, "stage": c.stage or "new", "status": c.lead_status,
            "assigned_to": c.assigned_to, "owner": (names or {}).get(c.assigned_to), "source": c.source, "origin": c.origin, "tags": c.tags or [], "bot_id": c.bot_id,
            "bot_name": (bots or {}).get(c.bot_id), "quality": c.quality, "created_at": iso(c.created_at), "last_enquiry_at": iso(c.last_enquiry_at),
            "next": task_json(task) if task else None}


def task_json(t: LeadTask, names: Optional[dict] = None) -> dict:
    return {"id": t.id, "title": t.title, "kind": t.kind, "due_at": iso(t.due_at), "assigned_to": t.assigned_to, "owner": (names or {}).get(t.assigned_to), "status": t.status, "result": t.result,
            "origin": t.origin, "done_at": iso(t.done_at)}


async def names_of(db: AsyncSession, owner_id: str) -> tuple[dict, dict]:
    people = {p["id"]: p["name"] for p in await team(db, owner_id)}
    bots = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == owner_id))).all())
    return people, bots


async def next_tasks(db: AsyncSession, contact_ids: list[str]) -> dict:
    """Each lead's soonest open task."""
    if not contact_ids:
        return {}
    found: dict = {}
    for t in (await db.execute(select(LeadTask).where(LeadTask.contact_id.in_(contact_ids), LeadTask.status == "open").order_by(LeadTask.due_at))).scalars().all():
        found.setdefault(t.contact_id, t)
    return found


# ─── what the team does ──────────────────────────────────────────
async def assign(db: AsyncSession, contact: Contact, person: Optional[str], by: Optional[str], names: dict) -> None:
    if contact.assigned_to == person:
        return
    contact.assigned_to = person
    await db.execute(update(LeadTask).where(LeadTask.contact_id == contact.id, LeadTask.status == "open").values(assigned_to=person, reminded_at=None).execution_options(synchronize_session=False))
    db.add(event(contact, "assigned", f"Now with {names.get(person, 'nobody')}" if person else "Nobody looks after them now", by))


def mark_junk(db: AsyncSession, contact: Contact, why: str) -> bool:
    """The junk filter's mark (leads/quality.py), only on a lead nothing real has happened with. True when marked."""
    from leads import quality
    if not quality.fresh(contact):
        return False
    contact.quality = "junk"
    db.add(event(contact, "junk", why))
    return True


async def let_go(db: AsyncSession, owner_id: str, person: str) -> None:
    """Someone left the team: their leads and open tasks wait for a manager instead of for nobody."""
    await db.execute(update(Contact).where(Contact.user_id == owner_id, Contact.assigned_to == person).values(assigned_to=None).execution_options(synchronize_session=False))
    await db.execute(update(LeadTask).where(LeadTask.user_id == owner_id, LeadTask.assigned_to == person, LeadTask.status == "open").values(assigned_to=None, reminded_at=None).execution_options(synchronize_session=False))


def stage(db: AsyncSession, contact: Contact, value: str, by: Optional[str]) -> None:
    if (contact.stage or "new") != value:
        contact.stage = value
        db.add(event(contact, "stage", f"Moved to {value}", by))


def add_task(db: AsyncSession, contact: Contact, title: str, due: datetime, kind: str, by: Optional[str], person: Optional[str] = None, origin: str = "team") -> LeadTask:
    task = LeadTask(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, title=title[:200], kind=kind if kind in KINDS else "other", due_at=due,
                    assigned_to=person or contact.assigned_to, created_by=by, origin=origin)
    db.add(task)
    return task


async def finish_task(db: AsyncSession, task_id: str, by: Optional[str], result: Optional[str], status: str = "done") -> bool:
    """Once only: two people pressing Done at the same moment finish it once."""
    done = await db.execute(update(LeadTask).where(LeadTask.id == task_id, LeadTask.status == "open")
                            .values(status=status, done_by=by, done_at=now(), result=(result or "")[:300] or None).execution_options(synchronize_session=False))
    return done.rowcount == 1


async def close(db: AsyncSession, contact: Contact, outcome: str, by: Optional[str], amount: Optional[float] = None, reason: Optional[str] = None) -> LeadDeal:
    """Won or lost: the outcome is kept for good, open tasks are cancelled, and the status follows so Schedule's calls stop."""
    from voice import schedule
    deal = LeadDeal(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, outcome=outcome, amount=amount, reason=(reason or "")[:200] or None, source=(contact.source or "")[:60] or None, by=by,
                    closed_at=now())  # to the microsecond: Reopen takes the latest
    db.add(deal)
    await db.execute(update(LeadTask).where(LeadTask.contact_id == contact.id, LeadTask.status == "open").values(status="cancelled", done_at=now(), result=f"Closed: {outcome}")
                     .execution_options(synchronize_session=False))
    contact.stage = "customer" if outcome == "won" else "lost"
    schedule.rate(contact, "customer" if outcome == "won" else "not_interested", "Set by the team", by=by)
    worth = f" for {amount:,.0f}" if amount else ""
    db.add(event(contact, outcome, f"Won{worth}" if outcome == "won" else f"Lost: {reason or 'no reason given'}", by))
    from leads import contact as reach
    await reach.stop_chase(db, contact, "Won" if outcome == "won" else "Lost")
    if outcome == "lost":  # nothing promised goes to someone who said no; a customer still gets what they were promised
        from leads import promises
        await promises.cancel_open(db, contact, "The lead was closed as lost", by)
    return deal


async def reopen(db: AsyncSession, contact: Contact, by: Optional[str]) -> None:
    """Back to work. The outcome it had stays on record, marked reopened, and no longer counts in reports: reopening is mostly a correction. An earlier sale
    (someone who bought, asked again, and was then lost) still stands."""
    from voice import schedule
    latest = (await db.execute(select(LeadDeal).where(LeadDeal.contact_id == contact.id, LeadDeal.reopened_at.is_(None)).order_by(LeadDeal.closed_at.desc()).limit(1))).scalars().first()
    if latest is not None:
        latest.reopened_at = now()
    if contact.lead_status in ("customer", "not_interested"):
        schedule.rate(contact, "warm", "Set by the team", by=by)
    contact.stage = "contacted"
    if contact.quality != "ok":
        contact.quality = None
    db.add(event(contact, "reopened", "Reopened", by))


async def record_result(db: AsyncSession, contact: Contact, result: str, by: Optional[str], note: Optional[str], next_at: Optional[datetime]) -> None:
    """How a try at reaching them went. It finishes the open task, moves the lead, and sets up what comes next."""
    words = RESULTS[result] + (f": {note}" if note else "")
    tasks = await open_tasks(db, contact.id)
    if tasks:
        await finish_task(db, tasks[0].id, by, words)
    contact.first_response_at = contact.first_response_at or now()
    db.add(event(contact, "result", words, by))
    if result == "wrong_number":
        contact.quality = "wrong_number"
        await close(db, contact, "lost", by, reason="Wrong number")
    elif result == "not_interested":
        await close(db, contact, "lost", by, reason=note or "Not interested")
    else:
        if result == "reached":
            journeys.move_stage(contact, "contacted")
        again = next_at or (now() + RETRY if result == "no_answer" else None)
        if again:
            add_task(db, contact, f"{'Try' if result == 'no_answer' else 'Call'} {contact.name or display(contact.e164) or 'them'} again", again, "call", by)


# ─── what a lead's page shows ────────────────────────────────────
async def timeline(db: AsyncSession, contact: Contact, names: dict, limit: int = 100) -> list[dict]:
    """Everything that happened with them, newest first, from where each thing is kept."""
    items: list[dict] = []

    def add(kind: str, at, text: str, **more):
        if at is not None:
            items.append({"kind": kind, "at": iso(at), "text": text, **more})

    for e in (await db.execute(select(LeadEvent).where(LeadEvent.contact_id == contact.id).order_by(LeadEvent.at.desc()).limit(limit))).scalars().all():
        add(e.kind, e.at, e.text or e.kind, who=names.get(e.by) if e.by else None)
    for i in (await db.execute(select(LeadIntake).where(LeadIntake.contact_id == contact.id).order_by(LeadIntake.created_at.desc()).limit(20))).scalars().all():
        add("submission", i.created_at, f"Form from {i.source or i.channel}", found={k: v for k, v in (i.found or {}).items() if v}, origin=i.origin, consents=i.consents, test=bool(i.test))
    if contact.e164:
        for c in (await db.execute(select(CallLog).where(CallLog.bot_id == contact.bot_id, CallLog.caller_e164 == contact.e164).order_by(CallLog.started_at.desc()).limit(30))).scalars().all():
            add("call", c.started_at, c.summary or "A call", call_id=c.id, direction=c.direction, outcome=c.outcome)
        for m in (await db.execute(select(Meeting).where(Meeting.bot_id == contact.bot_id, Meeting.e164 == contact.e164).order_by(Meeting.starts_at.desc()).limit(10))).scalars().all():
            add("meeting", m.created_at, f"Meeting {m.status}", meeting_id=m.id, starts_at=iso(m.starts_at))
    for conv in (await db.execute(select(Conversation).where(Conversation.contact_id == contact.id).order_by(Conversation.created_at.desc()).limit(10))).scalars().all():
        said = (await db.execute(select(Message.content).where(Message.conversation_id == conv.conversation_id, Message.role == "user").order_by(Message.timestamp).limit(1))).scalar_one_or_none()
        whatsapp = (conv.visitor_session_id or "").startswith("wa:")
        chat_id = (await db.execute(select(WhatsAppChat.id).where(WhatsAppChat.conversation_id == conv.conversation_id))).scalar_one_or_none() if whatsapp else None
        add("chat", conv.created_at, f"{'WhatsApp' if whatsapp else 'Website chat'}{f': {said[:200]}' if said else ''}", chat_link=f"/dashboard/whatsapp/inbox?chat={chat_id}" if chat_id else None)
    if contact.email:
        address = contact.email.lower()
        for j in (await db.execute(select(EmailJob).where(EmailJob.bot_id == contact.bot_id, func.lower(EmailJob.to_email) == address, EmailJob.status == "sent").order_by(EmailJob.sent_at.desc()).limit(30))).scalars().all():
            add("email", j.sent_at, j.subject, automation=j.automation)
        for m in (await db.execute(select(ThreadMessage).join(EmailThread, EmailThread.id == ThreadMessage.thread_id).where(
                EmailThread.bot_id == contact.bot_id, EmailThread.email == address, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True)).order_by(ThreadMessage.created_at.desc()).limit(20))).scalars().all():
            add("reply", m.created_at, (m.text or "")[:300], thread_id=m.thread_id)
    for t in (await db.execute(select(LeadTask).where(LeadTask.contact_id == contact.id, LeadTask.status == "done").order_by(LeadTask.done_at.desc()).limit(30))).scalars().all():
        add("task", t.done_at, f"{t.title}{f': {t.result}' if t.result else ''}", who=names.get(t.done_by) if t.done_by else None)
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


async def queues(db: AsyncSession, ctx: AuthContext, bot_id: Optional[str] = None, limit: int = 25) -> dict:
    """Needs attention: what's new and unowned, due, overdue, without a next step, waiting for a person, waiting for approval."""
    at = now()
    mine = visible(ctx) + ([Contact.bot_id == bot_id] if bot_id else [])
    people, bots = await names_of(db, ctx.owner_id)
    tasks = select(LeadTask).join(Contact, Contact.id == LeadTask.contact_id).where(LeadTask.status == "open", *mine).order_by(LeadTask.due_at)
    day_end = at.replace(hour=18, minute=30, second=0, microsecond=0)  # midnight in India
    day_end = day_end if day_end > at else day_end + timedelta(days=1)
    overdue = (await db.execute(tasks.where(LeadTask.due_at < at).limit(limit))).scalars().all()
    today = (await db.execute(tasks.where(LeadTask.due_at >= at, LeadTask.due_at < day_end).limit(limit))).scalars().all()
    has_open = select(LeadTask.id).where(LeadTask.contact_id == Contact.id, LeadTask.status == "open").exists()
    planned = select(CallbackJob.id).where(CallbackJob.bot_id == Contact.bot_id, CallbackJob.e164 == Contact.e164, CallbackJob.status.in_(WAITING)).exists()  # Schedule's calls and meetings are next steps too
    meeting = select(Meeting.id).where(Meeting.bot_id == Contact.bot_id, Meeting.e164 == Contact.e164, Meeting.status.in_(("requested", "proposed", "confirmed")), Meeting.starts_at > at).exists()
    open_stage = or_(Contact.stage.is_(None), Contact.stage.in_(OPEN))
    real = or_(Contact.quality.is_(None), Contact.quality == "ok")  # not junk, not closed as a wrong number, not an old lead from a list
    unowned = (await db.execute(select(Contact).where(*mine, Contact.assigned_to.is_(None), or_(Contact.stage.is_(None), Contact.stage == "new"), Contact.created_at >= at - NEW_FOR, real)
                                .order_by(Contact.created_at.desc()).limit(limit))).scalars().all() if ctx.role != "agent" else []
    stuck = (await db.execute(select(Contact).where(*mine, open_stage, ~has_open, ~planned, ~meeting, Contact.created_at >= at - RECENT, real, Contact.id.notin_([c.id for c in unowned]))
                              .order_by(Contact.created_at.desc()).limit(limit))).scalars().all()

    async def contacts_of(rows: list) -> dict:
        ids = {r.contact_id for r in rows}
        return {c.id: c for c in (await db.execute(select(Contact).where(Contact.id.in_(ids)))).scalars().all()} if ids else {}
    who = await contacts_of([*overdue, *today])
    upcoming = await next_tasks(db, [c.id for c in [*unowned, *stuck]])

    def row(t: LeadTask) -> Optional[dict]:
        return lead_json(who[t.contact_id], t, people, bots) if t.contact_id in who else None
    asked, approve = [], []
    if ctx.role != "agent":
        scope = [CallbackJob.user_id == ctx.owner_id, CallbackJob.kind == "person", CallbackJob.status == "todo"] + ([CallbackJob.bot_id == bot_id] if bot_id else [])
        asked = [{"id": j.id, "name": j.name, "phone": display(j.e164), "bot_name": bots.get(j.bot_id), "about": j.purpose, "at": iso(j.created_at)}
                 for j in (await db.execute(select(CallbackJob).where(*scope).order_by(CallbackJob.created_at.desc()).limit(limit))).scalars().all()]
        scope = [Meeting.user_id == ctx.owner_id, Meeting.status == "requested"] + ([Meeting.bot_id == bot_id] if bot_id else [])
        approve = [{"id": m.id, "name": m.name, "phone": display(m.e164), "bot_id": m.bot_id, "bot_name": bots.get(m.bot_id), "about": m.topic, "starts_at": iso(m.starts_at)}
                   for m in (await db.execute(select(Meeting).where(*scope).order_by(Meeting.starts_at).limit(limit))).scalars().all()]
    from leads import promises
    owed = (await db.execute(select(LeadPromise, Contact).join(Contact, Contact.id == LeadPromise.contact_id).where(LeadPromise.status == "open", *mine,
                                                                                                                  LeadPromise.due_at < day_end)
                             .order_by(LeadPromise.due_at).limit(limit))).all()
    return {"overdue": [r for r in map(row, overdue) if r], "today": [r for r in map(row, today) if r], "new": [lead_json(c, upcoming.get(c.id), people, bots) for c in unowned],
            "no_next": [lead_json(c, None, people, bots) for c in stuck], "asked_for_person": asked, "meetings": approve,
            "promises": [{**promises.promise_json(p, people), "lead": lead_json(c, None, people, bots)} for p, c in owed]}


# ─── reminders ───────────────────────────────────────────────────
async def whatsapp_alert(owner_id: str, bot_id: Optional[str], person: Optional[str], words: str, contact_id: Optional[str] = None) -> Optional[str]:
    """The salesperson's alert on WhatsApp (the assistant's alert template, to the number on their profile; the owner when nobody has the lead), with a
    link to the lead. Why it didn't go, or None. Never raises: the email alert stands on its own."""
    import plans
    from notify import channels, email
    from whatsapp import numbers
    try:
        async with async_session() as db:
            prefs = await settings_of(db, bot_id) if bot_id else SETTINGS
            template = prefs.get("alert_template")
            if not template:
                return "No alert template"
            if not (await plans.includes(db, bot_id)).whatsapp:
                return "WhatsApp isn't on the plan"
            to = (await db.execute(select(User.whatsapp).where(User.id == (person or owner_id)))).scalar_one_or_none()
            number = await numbers.workspace_number(db, owner_id)
            if not to:
                return "No WhatsApp number on their profile"
            if number is None or not number.access_token:
                return "No WhatsApp number connected"
            pid, token, language = number.phone_number_id, number.access_token, prefs.get("alert_language") or "en"
        link = f"{email.dashboard_url()}/dashboard/leads{f'/{contact_id}' if contact_id else ''}"
        await channels.send_whatsapp_template(to, template, language, [words[:200], link], phone_number_id=pid, token=token)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"The WhatsApp alert didn't go: {e!r}")
        return "WhatsApp didn't take it"


async def _alert(owner_id: str, person: Optional[str], subject: str, text: str, bot_id: Optional[str] = None, contact_id: Optional[str] = None) -> None:
    from notify import email, events
    if bot_id:
        await whatsapp_alert(owner_id, bot_id, person, subject, contact_id)
    async with async_session() as db:
        address = (await db.execute(select(User.email).where(User.id == person))).scalar_one_or_none() if person else None
        if address is None:
            settings = await events._settings(db, owner_id)
            owner = (await db.execute(select(User.email).where(User.id == owner_id))).scalar_one_or_none()
            to = events.recipients(settings, owner)
        else:
            to = [address]
    await events._email_team(to, subject[:150], f"{text}\n\nOpen it: {email.dashboard_url()}/dashboard/leads", owner_id)


async def _remind(task_id: str, at: datetime) -> None:
    import plans
    async with async_session() as db:
        claimed = await db.execute(update(LeadTask).where(LeadTask.id == task_id, LeadTask.reminded_at.is_(None), LeadTask.status == "open").values(reminded_at=at).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        task = await db.get(LeadTask, task_id)
        contact = await db.get(Contact, task.contact_id)
        included = await plans.includes(db, task.bot_id)
        person, owner_id, title, bot_id, contact_id = task.assigned_to, task.user_id, task.title, task.bot_id, task.contact_id
        who = " ".join(x for x in (contact.name, display(contact.e164) if contact.e164 else None, contact.email) if x) if contact else ""
    if included.team_alerts:
        await _alert(owner_id, person, f"Due now: {title}", f"{title}\n{who}", bot_id, contact_id)


async def _escalate(task_id: str, at: datetime) -> None:
    """A new lead's first step wasn't done in time: it goes to the backup, once."""
    import plans
    async with async_session() as db:
        claimed = await db.execute(update(LeadTask).where(LeadTask.id == task_id, LeadTask.escalated_at.is_(None), LeadTask.status == "open").values(escalated_at=at).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        task = await db.get(LeadTask, task_id)
        contact = await db.get(Contact, task.contact_id)
        prefs = await settings_of(db, task.bot_id)
        backup = prefs["backup"]
        if contact is None or not backup or backup == task.assigned_to or backup not in {p["id"] for p in await team(db, task.user_id)}:
            return
        people = {p["id"]: p["name"] for p in await team(db, task.user_id)}
        await assign(db, contact, backup, None, people)
        included = await plans.includes(db, task.bot_id)
        await db.commit()
        owner_id, title, bot_id, contact_id = task.user_id, task.title, task.bot_id, task.contact_id
    if included.team_alerts:
        await _alert(owner_id, backup, f"Passed to you: {title}", f"{title}\nIt wasn't done in time, so it has come to you as the backup.", bot_id, contact_id)


async def _due(db: AsyncSession, at: datetime) -> list[str]:
    """Tasks owed a reminder: someone's, due, not reminded yet (else a pile of reminded ones would fill every pass and hold up the rest), and not so old that a reminder is no use."""
    return (await db.execute(select(LeadTask.id).where(LeadTask.status == "open", LeadTask.reminded_at.is_(None), LeadTask.assigned_to.isnot(None), LeadTask.due_at <= at,
                                                       LeadTask.due_at > at - REMIND_WITHIN).order_by(LeadTask.due_at).limit(BATCH))).scalars().all()


async def tick(at: Optional[datetime] = None) -> None:
    """Scheduler: a reminder for each task of someone's that has come due, and first steps nobody took. Every row is claimed, so the processes share them."""
    global _last_pass
    at = at or now()
    if _last_pass and at - _last_pass < PASS_EVERY:
        return
    _last_pass = at
    async with async_session() as db:
        due = await _due(db, at)
        rows = (await db.execute(select(LeadTask).where(LeadTask.status == "open", LeadTask.origin == "rule", LeadTask.escalated_at.is_(None), LeadTask.due_at <= at, LeadTask.due_at > at - REMIND_WITHIN).limit(200))).scalars().all()
        late = []
        for task in rows:
            prefs = await settings_of(db, task.bot_id)
            if prefs["backup"] and utc(task.due_at) + timedelta(minutes=int(prefs["respond_minutes"])) <= utc(at):
                late.append(task.id)
    for task_id in due:
        await _remind(task_id, at)
    for task_id in late[:50]:
        await _escalate(task_id, at)


# ─── reports ─────────────────────────────────────────────────────
async def report(db: AsyncSession, ctx: AuthContext, days: int, bot_id: Optional[str] = None) -> dict:
    since = now() - timedelta(days=days)
    scope = visible(ctx) + ([Contact.bot_id == bot_id] if bot_id else [])
    counted = or_(Contact.quality.is_(None), Contact.quality.notin_(("junk", "old")))  # junk is counted apart; an imported list isn't new leads
    rows = (await db.execute(select(Contact.source, Contact.stage, Contact.created_at, Contact.first_response_at, Contact.assigned_to).where(*scope, counted, Contact.created_at >= since))).all()
    junk = dict((await db.execute(select(Contact.source, func.count()).where(*scope, Contact.quality == "junk", Contact.created_at >= since).group_by(Contact.source))).all())
    people, _ = await names_of(db, ctx.owner_id)
    deals = (await db.execute(select(LeadDeal).join(Contact, Contact.id == LeadDeal.contact_id).where(*scope, LeadDeal.closed_at >= since, LeadDeal.reopened_at.is_(None)))).scalars().all()
    sources: dict = {}
    for source, stage_, *_rest in rows:
        s = sources.setdefault(source or "call", {"source": source or "call", "leads": 0, "reached": 0, "meetings": 0, "won": 0, "lost": 0, "value": 0.0, "junk": 0})
        s["leads"] += 1
        s["reached"] += (stage_ or "new") != "new"
        s["meetings"] += stage_ == "meeting"
    for source, count in junk.items():
        sources.setdefault(source or "call", {"source": source or "call", "leads": 0, "reached": 0, "meetings": 0, "won": 0, "lost": 0, "value": 0.0, "junk": 0})["junk"] = count
    for d in deals:
        s = sources.setdefault(d.source or "call", {"source": d.source or "call", "leads": 0, "reached": 0, "meetings": 0, "won": 0, "lost": 0, "value": 0.0, "junk": 0})
        s[d.outcome] += 1
        s["value"] += d.amount or 0 if d.outcome == "won" else 0
    waits = sorted((utc(first) - utc(made)).total_seconds() / 60 for _s, _st, made, first, _o in rows if first and made and first >= made)
    done = dict((await db.execute(select(LeadTask.done_by, func.count()).join(Contact, Contact.id == LeadTask.contact_id).where(*scope, LeadTask.status == "done", LeadTask.done_at >= since).group_by(LeadTask.done_by))).all())
    late = dict((await db.execute(select(LeadTask.assigned_to, func.count()).join(Contact, Contact.id == LeadTask.contact_id).where(*scope, LeadTask.status == "open", LeadTask.due_at < now()).group_by(LeadTask.assigned_to))).all())
    won = {}
    for d in deals:
        if d.outcome == "won" and d.by:
            won[d.by] = won.get(d.by, 0) + 1
    reasons: dict = {}
    lost_by: dict = {}  # why leads were lost, for each place they came from
    for d in deals:
        if d.outcome == "lost":
            reason = d.reason or "No reason given"
            reasons[reason] = reasons.get(reason, 0) + 1
            row_ = lost_by.setdefault(d.source or "call", {"source": d.source or "call", "lost": 0, "reasons": {}})
            row_["lost"] += 1
            row_["reasons"][reason] = row_["reasons"].get(reason, 0) + 1
    from leads import promises
    made = (await db.execute(select(LeadPromise).join(Contact, Contact.id == LeadPromise.contact_id).where(*scope, LeadPromise.made_at >= since))).scalars().all()
    return {"days": days, "leads": len(rows), "junk": sum(junk.values()), "sources": sorted(sources.values(), key=lambda s: -s["leads"]),
            "first_response": {"measured": len(waits), "median_minutes": round(waits[len(waits) // 2], 1) if waits else None, "within_5": sum(w <= 5 for w in waits), "within_60": sum(w <= 60 for w in waits),
                               "not_tried": len(rows) - len(waits)},
            "team": [{"id": i, "name": n, "done": done.get(i, 0), "overdue": late.get(i, 0), "won": won.get(i, 0)} for i, n in people.items()],
            "won": sum(d.outcome == "won" for d in deals), "lost": sum(d.outcome == "lost" for d in deals), "value": sum(d.amount or 0 for d in deals if d.outcome == "won"),
            "lost_reasons": sorted(({"reason": k, "count": v} for k, v in reasons.items()), key=lambda r: -r["count"]),
            "lost_by_source": [{"source": r["source"], "lost": r["lost"], "reasons": sorted(({"reason": k, "count": v} for k, v in r["reasons"].items()), key=lambda x: -x["count"])}
                               for r in sorted(lost_by.values(), key=lambda r: -r["lost"])],
            "promises": promises.report(made)}

