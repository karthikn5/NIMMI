"""
Reports (mail plan 5.8, phase 6): how each kind of email, each journey and each bulk email did; the funnel from lead to customer; the team's replies; whether mail
is landing. Every number comes from what was kept: the emails (EmailJob), people's clicks (mail/clicks.py leaves scanners out), replies (ThreadMessage),
unsubscribes, meetings and contacts. A reply or an unsubscribe is put down to the last email that person got before it, within a week. Opens aren't counted: mail
apps open emails by themselves.
"""
import bisect
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.future import select

from backend.models import (Bot, Contact, EmailBroadcast, EmailClick, EmailDomain, EmailJob, EmailThread, EmailUnsubscribe, Journey, JourneyRun, Meeting, TeamMember,
                            ThreadMessage, User)
from mail import address, clicks
from notify import automations

PERIODS = (7, 30, 90)
ATTRIBUTE = timedelta(days=7)
COMPLAINTS = (0.001, 0.003)   # Gmail: keep spam reports under 0.1%, never reach 0.3%
BOUNCES = (0.02, 0.05)


def _naive(at):
    return clicks._naive(at)


def _rate(part: int, whole: int) -> Optional[float]:
    return part / whole if whole else None


def _level(rate: Optional[float], limits: tuple[float, float]) -> str:
    if rate is None:
        return "unknown"
    return "good" if rate < limits[0] else "warn" if rate < limits[1] else "bad"


def _credit(sent: dict[str, list[tuple[datetime, str]]], to: str, at: datetime) -> Optional[str]:
    """The id of the last email this address got before `at`, within a week."""
    times = sent.get(to.lower())
    if not times:
        return None
    i = bisect.bisect_right(times, (at, "\\uffff")) - 1
    if i < 0 or at - times[i][0] > ATTRIBUTE:
        return None
    return times[i][1]


async def build(db, owner_id: str, bot_id: Optional[str], days: int, now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    since = now - timedelta(days=days)
    mine = [EmailJob.user_id == owner_id, EmailJob.status == "sent", EmailJob.sent_at >= since]
    if bot_id:
        mine.append(EmailJob.bot_id == bot_id)
    jobs = (await db.execute(select(EmailJob).where(*mine))).scalars().all()
    by_address: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for j in jobs:
        by_address[j.to_email.lower()].append((_naive(j.sent_at), j.id))
    for times in by_address.values():
        times.sort()

    threads = [EmailThread.user_id == owner_id] + ([EmailThread.bot_id == bot_id] if bot_id else [])
    replies = (await db.execute(select(ThreadMessage.sender, ThreadMessage.created_at, EmailThread.email).join(EmailThread, EmailThread.id == ThreadMessage.thread_id)
                                .where(*threads, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True), ThreadMessage.created_at >= since))).all()
    gone = (await db.execute(select(EmailUnsubscribe.email, EmailUnsubscribe.created_at).where(
        EmailUnsubscribe.user_id == owner_id, EmailUnsubscribe.created_at >= since, or_(EmailUnsubscribe.reason.is_(None), EmailUnsubscribe.reason.in_(("unsubscribed", "complaint")))))).all()
    replied, unsubscribed = defaultdict(int), defaultdict(int)
    for _, at, to in replies:
        job_id = _credit(by_address, to, _naive(at))
        if job_id:
            replied[job_id] += 1
    for to, at in gone:
        job_id = _credit(by_address, to, _naive(at))
        if job_id:
            unsubscribed[job_id] += 1

    runs = {r.id: r.journey_id for r in (await db.execute(select(JourneyRun).where(JourneyRun.id.in_([j.ref_id for j in jobs if j.automation == "journey"] or [""])))).scalars().all()}
    journeys = {j.id: j.name for j in (await db.execute(select(Journey).where(Journey.id.in_(set(runs.values()) or {""})))).scalars().all()}
    sends = {b.id: b.subject for b in (await db.execute(select(EmailBroadcast).where(EmailBroadcast.id.in_({j.broadcast_id for j in jobs if j.broadcast_id} or {""})))).scalars().all()}

    groups: dict[str, dict] = {}
    for j in jobs:
        if j.broadcast_id:
            key, label, kind = f"broadcast:{j.broadcast_id}", sends.get(j.broadcast_id) or "Bulk email", "bulk"
        elif j.automation == "journey":
            journey = runs.get(j.ref_id)
            key, label, kind = f"journey:{journey}", journeys.get(journey, "A journey that was deleted"), "journey"
        else:
            name = j.automation or j.kind.split("#")[0].split(":")[0]
            key, label, kind = name, automations.LABELS.get(name, name), "automatic"
        g = groups.setdefault(key, {"key": key, "label": label, "type": kind, "sent": 0, "delivered": 0, "bounced": 0, "complained": 0, "clicked": 0, "replied": 0,
                                    "unsubscribed": 0})
        g["sent"] += 1
        g["delivered"] += 1 if j.delivered_at else 0
        g["bounced"] += 1 if j.bounced_at else 0
        g["complained"] += 1 if j.complained_at else 0
        g["clicked"] += 1 if j.clicked_at else 0
        g["replied"] += 1 if replied.get(j.id) else 0
        g["unsubscribed"] += 1 if unsubscribed.get(j.id) else 0
    rows = sorted(groups.values(), key=lambda g: (-g["sent"], g["label"]))

    return {"days": days, "since": since.isoformat(), "emails": rows, "funnel": await funnel(db, owner_id, bot_id, since), "team": await team(db, owner_id, bot_id, since),
            "deliverability": await deliverability(db, owner_id, jobs, since)}


async def funnel(db, owner_id: str, bot_id: Optional[str], since: datetime) -> dict:
    """The leads who came in during the period, and how far each got."""
    where = [Contact.user_id == owner_id, Contact.created_at >= since] + ([Contact.bot_id == bot_id] if bot_id else [])
    leads = (await db.execute(select(Contact).where(*where))).scalars().all()
    emailed = engaged = met = customers = 0
    for c in leads:
        address_ = (c.email or "").lower()
        jobs = (await db.execute(select(EmailJob.id, EmailJob.clicked_at).where(EmailJob.user_id == owner_id, EmailJob.status == "sent", EmailJob.sent_at >= since,
                                                                              EmailJob.bot_id == c.bot_id, func.lower(EmailJob.to_email) == address_))).all() if address_ else []
        if jobs:
            emailed += 1
            replied = (await db.execute(select(ThreadMessage.id).join(EmailThread, EmailThread.id == ThreadMessage.thread_id).where(
                EmailThread.bot_id == c.bot_id, EmailThread.email == address_, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True),
                ThreadMessage.created_at >= since).limit(1))).first()
            if replied or any(clicked for _, clicked in jobs):
                engaged += 1
        who = [Meeting.e164 == c.e164] if c.e164 else []
        who += [func.lower(Meeting.email) == address_] if address_ else []
        if who and (await db.execute(select(Meeting.id).where(Meeting.bot_id == c.bot_id, or_(*who), Meeting.created_at >= since).limit(1))).first():
            met += 1
        if "customer" in (c.stage, c.lead_status):
            customers += 1
    return {"leads": len(leads), "emailed": emailed, "engaged": engaged, "meetings": met, "customers": customers}


async def team(db, owner_id: str, bot_id: Optional[str], since: datetime) -> list[dict]:
    """Each team member's answers in the Inbox, and how long people waited for them."""
    where = [EmailThread.user_id == owner_id] + ([EmailThread.bot_id == bot_id] if bot_id else [])
    rows = (await db.execute(select(ThreadMessage.thread_id, ThreadMessage.by, ThreadMessage.created_at).join(EmailThread, EmailThread.id == ThreadMessage.thread_id).where(
        *where, ThreadMessage.direction == "out", ThreadMessage.who == "team", ThreadMessage.status == "sent", ThreadMessage.created_at >= since))).all()
    waits: dict[str, list[float]] = defaultdict(list)
    count: dict[str, int] = defaultdict(int)
    for thread_id, by, at in rows:
        who = by or owner_id
        count[who] += 1
        asked = (await db.execute(select(func.max(ThreadMessage.created_at)).where(ThreadMessage.thread_id == thread_id, ThreadMessage.direction == "in",
                                                                                  ThreadMessage.automatic.isnot(True), ThreadMessage.created_at <= at))).scalar_one()
        if asked is not None:
            waits[who].append((_naive(at) - _naive(asked)).total_seconds() / 60)
    names = dict((await db.execute(select(User.id, func.coalesce(User.name, User.email)).where(User.id.in_(list(count) or [""])))).all())
    return sorted(({"id": who, "name": names.get(who) or "A former team member", "answers": n, "median_minutes": round(statistics.median(waits[who])) if waits[who] else None}
                   for who, n in count.items()), key=lambda r: -r["answers"])


async def deliverability(db, owner_id: str, jobs: list, since: datetime) -> dict:
    sent = len(jobs)
    delivered = sum(1 for j in jobs if j.delivered_at)
    bounced = sum(1 for j in jobs if j.bounced_at)
    complained = sum(1 for j in jobs if j.complained_at)
    scanners = (await db.execute(select(func.count()).select_from(EmailClick).where(EmailClick.user_id == owner_id, EmailClick.person.is_(False),
                                                                                    EmailClick.at >= since))).scalar_one()
    domains = []
    for d in (await db.execute(select(EmailDomain).where(EmailDomain.user_id == owner_id).order_by(EmailDomain.created_at))).scalars().all():
        record = await address.dmarc_of(d.name)
        domains.append({"name": d.name, "status": d.status, "dmarc": None if record == "" else address.dmarc_policy(record) or ("missing" if record is None else "unreadable"),
                        "checked": record != ""})
    bounce_rate, complaint_rate = _rate(bounced, sent), _rate(complained, delivered)
    return {"sent": sent, "delivered": delivered, "bounced": bounced, "complained": complained, "bounce_rate": bounce_rate, "complaint_rate": complaint_rate,
            "bounce_level": _level(bounce_rate, BOUNCES), "complaint_level": _level(complaint_rate, COMPLAINTS), "scanner_clicks": scanners, "domains": domains}
