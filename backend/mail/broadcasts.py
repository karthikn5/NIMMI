"""
Bulk email (mail plan, phase 5): one email to a group of people who agreed to offers and news. A draft is checked and tried, then sent now, at a time, or at each person's
usual hour. The list is read when it starts, so someone who unsubscribed in between isn't on it. Emails go out at a set pace, each with its own time, so a big send never
holds up a customer's meeting confirmation. Two subjects can be tried on a fifth of the list, and the better one, by clicks and replies, goes to the rest.

A send pauses by itself when spam reports or bounces rise; its emails wait as "held" until the team resumes or cancels it. `tick` (scheduler) claims each send, so one process
moves it on, and an email's unique (kind, ref_id) means nobody gets two. From Nimmi's address, which carries every business's mail, the daily limit is low; a business's own
domain warms up and is then free of it.
"""
import asyncio
import hashlib
import logging
import math
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.future import select

from backend.models import Contact, EmailBounce, EmailBroadcast, EmailDomain, EmailJob, EmailRsvp, EmailThread, EmailUnsubscribe, IntegrationSettings, ThreadMessage
from database import async_session
from mail import address, compose, consent, domains, journeys, links, render, senders

logger = logging.getLogger(__name__)

MAX_RECIPIENTS = 2000
PER_DAY = 5                # bulk emails a workspace can start in a day
PACES = (30, 60, 120)      # emails a minute: the queue sends up to 50 each pass, about every 20 seconds
PACE = 60
TEST_SHARE = 0.2           # of the list, half for each subject
TEST_MIN = 100             # fewer people can't show which subject is better
TEST_HOURS = 4
COMPLAINT_LIMIT = 0.003    # Gmail's ceiling for spam reports (0.3%)
COMPLAINT_SAMPLE = 200     # delivered bulk emails needed before the rate over 30 days means anything
BOUNCE_LIMIT = 0.05
BOUNCE_SAMPLE = 20
SPIKE_COMPLAINTS = 2       # in one send, with the rate over Gmail's ceiling
STUCK = timedelta(minutes=10)
DNS_SECONDS = 20           # checking where a list's addresses go
DNS_AT_ONCE = 20
AHEAD = timedelta(days=60)
SCAN = 20000               # contacts of one assistant looked at
SOURCES = {"chat": "Website chat", "call": "Calls and WhatsApp", "portal": "Portals and forms", "import": "Imported"}
OPEN = ("scheduled", "testing", "sending", "paused")
EDITABLE = ("draft",)


def shared_daily() -> int:
    return int(os.getenv("BROADCAST_SHARED_DAILY", "200"))


def bulk_address(sender) -> str:
    """Offers go from an address of their own (BULK_EMAIL_FROM, a subdomain such as news.nimmiai.in), so they never spoil confirmations. A business's own domain stays its own."""
    from notify import email
    own = os.getenv("BULK_EMAIL_FROM", "").strip()
    return sender.address if sender.domain or not own else email.address_of(own)


def clean_rules(rules: Optional[dict]) -> dict:
    """A group's rules as saved: only what can be asked."""
    rules = rules if isinstance(rules, dict) else {}
    out: dict = {}
    for key, known in (("statuses", journeys.STAGE_OF), ("stages", journeys.STAGES), ("sources", SOURCES)):
        chosen = [str(v) for v in (rules.get(key) or []) if str(v) in known]
        if chosen:
            out[key] = chosen
    tags = [str(t).strip()[:40] for t in (rules.get("tags") or []) if str(t).strip()][:20]
    if tags:
        out["tags"] = tags
    for key in ("active_days", "engaged_days"):
        try:
            days = int(rules.get(key) or 0)
        except (TypeError, ValueError):
            days = 0
        if 0 < days <= 3650:
            out[key] = days
    return out


def source_of(contact: Contact) -> str:
    if contact.source in ("chat", "import"):
        return contact.source
    return "portal" if contact.source else "call"


def last_touch(contact: Contact) -> Optional[datetime]:
    from voice import schedule
    return max([t for t in (schedule.utc(contact.last_call_at), schedule.utc(contact.last_chat_at), schedule.utc(contact.created_at)) if t], default=None)


async def _engaged(db, owner_id: str, bot_id: str, since: datetime) -> set[str]:
    clicked = (await db.execute(select(EmailJob.to_email).where(EmailJob.user_id == owner_id, EmailJob.clicked_at >= since))).scalars().all()
    replied = (await db.execute(select(EmailThread.email).join(ThreadMessage, ThreadMessage.thread_id == EmailThread.id).where(
        EmailThread.bot_id == bot_id, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True), ThreadMessage.created_at >= since))).scalars().all()
    return {a.lower() for a in (*clicked, *replied)}


async def people(db, owner_id: str, bot_id: str, rules: dict, now: Optional[datetime] = None) -> tuple[list[dict], dict]:
    """Who gets it: this assistant's contacts in the group who agreed to offers and news, one per address, newest first; and how many were left out, and why."""
    from voice import schedule
    now = now or datetime.utcnow()
    rows = (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.email.isnot(None)).order_by(Contact.created_at.desc()).limit(SCAN))).scalars().all()
    engaged = await _engaged(db, owner_id, bot_id, now - timedelta(days=rules["engaged_days"])) if rules.get("engaged_days") else None
    active = schedule.utc(now) - timedelta(days=rules["active_days"]) if rules.get("active_days") else None
    wanted = set(rules.get("tags") or [])

    def fits(c: Contact) -> bool:
        return ((not rules.get("statuses") or c.lead_status in rules["statuses"]) and (not rules.get("stages") or (c.stage or "new") in rules["stages"])
                and (not rules.get("sources") or source_of(c) in rules["sources"]) and (not wanted or bool(wanted & set(c.tags or [])))
                and (active is None or (last_touch(c) or active) > active) and (engaged is None or c.email.lower() in engaged))
    matched, seen = [], set()
    for c in rows:
        key = c.email.strip().lower()
        if key not in seen and fits(c):
            seen.add(key)
            matched.append(c)
    stopped = {e.lower() for e in (await db.execute(select(EmailUnsubscribe.email).where(EmailUnsubscribe.user_id == owner_id))).scalars().all()}
    keys = sorted(seen)
    for i in range(0, len(keys), 500):
        stopped |= set((await db.execute(select(EmailBounce.email).where(EmailBounce.email.in_(keys[i:i + 500])))).scalars().all())
    agreed = await consent.agreed(db, bot_id)
    out, left = [], {"no_consent": 0, "stopped": 0, "throwaway": 0}
    for c in matched:
        key = c.email.strip().lower()
        if key in stopped:
            left["stopped"] += 1
        elif address.throwaway(address.domain_of(key)):
            left["throwaway"] += 1
        elif key not in agreed:
            left["no_consent"] += 1
        else:
            out.append({"id": c.id, "name": c.name or "", "email": c.email.strip(), "last": last_touch(c)})
    return out, left


async def complaint_rate(db, owner_id: str, days: int = 30) -> Optional[float]:
    """Spam reports per delivered bulk email in the last `days` days; None until there are enough to tell."""
    since = datetime.utcnow() - timedelta(days=days)
    bulk = [EmailJob.user_id == owner_id, EmailJob.broadcast_id.isnot(None), EmailJob.sent_at >= since]
    delivered = (await db.execute(select(func.count()).select_from(EmailJob).where(*bulk, EmailJob.delivered_at.isnot(None)))).scalar_one()
    if delivered < COMPLAINT_SAMPLE:
        return None
    return (await db.execute(select(func.count()).select_from(EmailJob).where(*bulk, EmailJob.complained_at.isnot(None)))).scalar_one() / delivered


async def room_today(db, owner_id: str, sender) -> Optional[int]:
    """How many more bulk emails can go today; None = no limit. A new domain warms up, and Nimmi's own address has a low limit: it carries every business's mail."""
    if sender.domain:
        domain = (await db.execute(select(EmailDomain).where(EmailDomain.user_id == owner_id, EmailDomain.name == sender.domain))).scalars().first()
        allowance = domains.bulk_allowance(domain)
    else:
        allowance = shared_daily()
    if allowance is None:
        return None
    used = (await db.execute(select(func.count()).select_from(EmailJob).where(
        EmailJob.user_id == owner_id, EmailJob.broadcast_id.isnot(None), EmailJob.status.in_(("queued", "held", "sent")),
        EmailJob.send_at >= datetime.utcnow() - timedelta(days=1)))).scalar_one()
    return max(allowance - used, 0)


def over_limit(count: int, room: Optional[int], sender) -> Optional[str]:
    if room is None or count <= room:
        return None
    if sender.domain:
        return (f"{sender.domain} is new, so mail services are still learning to trust it: it can send {room} more bulk emails today, about twice as many each day this week. "
                "Narrow the group, or send the rest tomorrow.")
    return (f"From Nimmi's address you can send {room} more bulk emails today. Narrow the group, or send from your own domain (Email > Settings), which has no such limit "
            "once it has warmed up.")


async def problem(db, b: EmailBroadcast, count: int, starting: bool = False) -> Optional[str]:
    """Why this send can't go, in words; None if it can."""
    import plans
    from notify import email
    if not (b.subject or "").strip() or not (b.body or "").strip():
        return "Add a subject and a message"
    if not email.is_configured():
        return "Email sending isn't set up on the server yet"
    if not (await plans.includes(db, b.bot_id)).email_alerts:
        return "Bulk email comes with the Growth plan"
    sender = await senders.sender_for(db, b.user_id, b.bot_id)
    if not sender.reply_to:
        return "Add where replies go (Email > Settings), so people can answer you"
    if count == 0:
        return "Nobody in this group has agreed to offers and news"
    if count > MAX_RECIPIENTS:
        return f"That's {count} people. Narrow it to {MAX_RECIPIENTS} or fewer."
    if b.subject_b and count < TEST_MIN:
        return f"A subject test needs at least {TEST_MIN} people, and this group has {count}. Remove the second subject."
    started = (await db.execute(select(func.count()).select_from(EmailBroadcast).where(
        EmailBroadcast.user_id == b.user_id, EmailBroadcast.id != b.id, EmailBroadcast.started_at >= datetime.utcnow() - timedelta(days=1)))).scalar_one()
    if started >= PER_DAY:
        return f"You can send up to {PER_DAY} bulk emails a day"
    rate = await complaint_rate(db, b.user_id)
    if rate is not None and rate > COMPLAINT_LIMIT:
        return (f"Bulk email is paused: {rate:.1%} of the people who got your recent bulk emails reported them as spam, and Gmail's limit is {COMPLAINT_LIMIT:.1%}. "
                "Send to people who asked to hear from you, and it opens again as the rate falls.")
    return over_limit(count, await room_today(db, b.user_id, sender), sender)


# ─── starting ────────────────────────────────────────────────────
def _invitation(b: EmailBroadcast, tz) -> str:
    from voice import schedule
    event = b.event or {}
    if not event.get("title"):
        return ""
    at = datetime.fromisoformat(event["at"]) if event.get("at") else None
    when = schedule.when_text(schedule.utc(at), tz, now=schedule.utc(at) + timedelta(days=30)) if at else ""
    return "\n\n" + "\n".join(x for x in (event["title"], when[:1].upper() + when[1:], event.get("where")) if x)


def _at(b: EmailBroadcast, person: dict, n: int, gap: float, tz, now: datetime) -> datetime:
    from voice import schedule
    if not b.usual_hour:
        return now + timedelta(seconds=n * gap)
    start = schedule.utc(now)
    day = start.astimezone(tz).date()
    at = schedule._their_hour(day, person["last"], journeys.QUIET, tz, person["email"])
    if at < start:
        at = schedule._their_hour(day + timedelta(days=1), person["last"], journeys.QUIET, tz, person["email"])
    return schedule.stored(at)


async def _queue(db, b: EmailBroadcast, group: list[dict], subject: str, variant: Optional[str], sender, tz, now: datetime) -> None:
    from notify import automations
    gap, invitation = 60 / (b.per_minute or PACE), _invitation(b, tz)
    for n, person in enumerate(group):
        values = {"name": person["name"], "first_name": compose._first_name(person["name"]) or "", "email": person["email"], "business": sender.name}
        body = render.fill(b.body, values) + invitation
        if invitation:
            body += f"\n\nWill you come? {links.rsvp_url(b.id, person['email'])}"
        db.add(EmailJob(user_id=b.user_id, bot_id=b.bot_id, kind=f"broadcast:{b.id}", ref_id=automations.recipient_ref(person["email"]), to_email=person["email"], automation="broadcast",
                        step=1, broadcast_id=b.id, variant=variant, subject=render.fill(subject, values)[:200], body=body, send_at=_at(b, person, n, gap, tz, now), merge_data={"name": person["name"]}))


async def _deliverable(group: list[dict]) -> tuple[list[dict], int]:
    """Without the people whose domain takes no mail: each bounce costs the sender's reputation. One lookup per domain, cached; a domain that can't be checked
    in time is kept."""
    names = sorted({address.domain_of(p["email"]) for p in group})
    gate = asyncio.Semaphore(DNS_AT_ONCE)

    async def one(name: str):
        async with gate:
            return await address.receives_mail(name)
    try:
        found = await asyncio.wait_for(asyncio.gather(*(one(n) for n in names)), DNS_SECONDS)
    except asyncio.TimeoutError:
        return group, 0
    dead = {n for n, ok in zip(names, found) if ok is False}
    kept = [p for p in group if address.domain_of(p["email"]) not in dead]
    return kept, len(group) - len(kept)


def _shuffled(group: list[dict], salt: str) -> list[dict]:
    """The same order on every process, and no link to who came in first."""
    return sorted(group, key=lambda p: hashlib.sha256(f"{salt}{p['email'].lower()}".encode()).hexdigest())


async def _start(db, b: EmailBroadcast, now: datetime) -> None:
    from voice import schedule
    group, _ = await people(db, b.user_id, b.bot_id, b.rules or {}, now)
    stop = await problem(db, b, len(group), starting=True)
    if stop:
        await pause(db, b, stop)
        return
    await db.commit()  # the address checks are DNS lookups: no connection waits on them
    group, dead = await _deliverable(group)
    b.audience = {"people": len(group), "no_mail_server": dead}
    if not group:
        await pause(db, b, "None of these addresses can receive email: their domains have no mail server.")
        return
    sender = await senders.sender_for(db, b.user_id, b.bot_id)
    tz = schedule.zone(await schedule.settings_for(b.bot_id, db))
    b.recipients, b.started_at = len(group), now
    if not b.subject_b:
        await _queue(db, b, group, b.subject, None, sender, tz, now)
        b.status = "sending"
        return
    mixed = _shuffled(group, b.id)
    size = max(math.ceil(len(group) * TEST_SHARE), 2)
    half = size // 2
    await _queue(db, b, mixed[:half], b.subject, "a", sender, tz, now)
    await _queue(db, b, mixed[half:size], b.subject_b, "b", sender, tz, now)
    b.status, b.test_ends_at = "testing", now + timedelta(hours=TEST_HOURS)


async def _replied(db, b: EmailBroadcast) -> set[str]:
    if not b.started_at:
        return set()
    rows = (await db.execute(select(EmailThread.email).join(ThreadMessage, ThreadMessage.thread_id == EmailThread.id).where(
        EmailThread.user_id == b.user_id, ThreadMessage.direction == "in", ThreadMessage.automatic.isnot(True), ThreadMessage.created_at >= b.started_at))).scalars().all()
    return {a.lower() for a in rows}


async def _scores(db, b: EmailBroadcast) -> dict:
    """Clicks and replies per email of each subject. A reply says more than a click. Opens don't count: mail apps open emails by themselves."""
    rows = (await db.execute(select(EmailJob.variant, EmailJob.to_email, EmailJob.clicked_at).where(EmailJob.broadcast_id == b.id, EmailJob.variant.isnot(None)))).all()
    replied = await _replied(db, b)
    sent, points = {"a": 0, "b": 0}, {"a": 0, "b": 0}
    for variant, to, clicked in rows:
        sent[variant] += 1
        points[variant] += (1 if clicked else 0) + (2 if to.lower() in replied else 0)
    return {k: points[k] / sent[k] if sent[k] else 0 for k in sent}


async def _pick_winner(db, b: EmailBroadcast, now: datetime) -> None:
    from voice import schedule
    scores = await _scores(db, b)
    b.winner = "b" if scores["b"] > scores["a"] else "a"
    group, _ = await people(db, b.user_id, b.bot_id, b.rules or {}, now)
    done = {t.lower() for t in (await db.execute(select(EmailJob.to_email).where(EmailJob.broadcast_id == b.id))).scalars().all()}
    rest = [p for p in group if p["email"].lower() not in done]
    await db.commit()  # DNS lookups ahead
    rest, dead = await _deliverable(rest)
    b.audience = {**(b.audience or {}), "no_mail_server": (b.audience or {}).get("no_mail_server", 0) + dead}
    sender = await senders.sender_for(db, b.user_id, b.bot_id)
    tz = schedule.zone(await schedule.settings_for(b.bot_id, db))
    await _queue(db, b, rest, b.subject_b if b.winner == "b" else b.subject, b.winner, sender, tz, now)
    b.recipients, b.status = len(done) + len(rest), "sending"


# ─── while it's going ────────────────────────────────────────────
async def pause(db, b: EmailBroadcast, why: str) -> None:
    await db.execute(update(EmailJob).where(EmailJob.broadcast_id == b.id, EmailJob.status == "queued").values(status="held").execution_options(synchronize_session=False))
    b.status, b.paused_why = "paused", why[:300]


async def resume(db, b: EmailBroadcast, now: datetime) -> None:
    """The emails it held go at the same pace from now. One that hasn't started goes through its checks again."""
    from voice import schedule
    b.paused_why = None
    if not b.started_at:  # it keeps its time, if that's still ahead
        b.status, b.send_at = "scheduled", max(schedule.stored(schedule.utc(b.send_at)), now) if b.send_at else now
        return
    held = (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == b.id, EmailJob.status == "held").order_by(EmailJob.send_at))).scalars().all()
    gap = 60 / (b.per_minute or PACE)
    for n, job in enumerate(held):
        job.status, job.send_at = "queued", now + timedelta(seconds=n * gap)
    b.status = "testing" if b.test_ends_at and not b.winner else "sending"


async def cancel(db, b: EmailBroadcast) -> int:
    done = await db.execute(update(EmailJob).where(EmailJob.broadcast_id == b.id, EmailJob.status.in_(("queued", "held"))).values(status="cancelled", error="Cancelled by your team")
                            .execution_options(synchronize_session=False))
    b.status, b.finished_at = "cancelled", datetime.utcnow()
    return done.rowcount


async def _spike(db, b: EmailBroadcast) -> Optional[str]:
    """A reason to stop this send while there's still time."""
    mine = [EmailJob.broadcast_id == b.id]
    delivered = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine, EmailJob.delivered_at.isnot(None)))).scalar_one()
    complained = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine, EmailJob.complained_at.isnot(None)))).scalar_one()
    if complained >= SPIKE_COMPLAINTS and complained / max(delivered, 1) > COMPLAINT_LIMIT:
        return f"Paused: {complained} of {delivered} people reported this as spam, above Gmail's limit of {COMPLAINT_LIMIT:.1%}. Check who's on the list before going on."
    sent = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine, EmailJob.sent_at.isnot(None)))).scalar_one()
    bounced = (await db.execute(select(func.count()).select_from(EmailJob).where(*mine, EmailJob.bounced_at.isnot(None)))).scalar_one()
    if sent >= BOUNCE_SAMPLE and bounced / sent > BOUNCE_LIMIT:
        return f"Paused: {bounced} of {sent} emails bounced, so the list has old addresses. Too many bounces make mail services distrust you."
    return None


async def _watch(db, b: EmailBroadcast, now: datetime) -> None:
    spike = await _spike(db, b)
    if spike:
        return await pause(db, b, spike)
    waiting = (await db.execute(select(func.count()).select_from(EmailJob).where(EmailJob.broadcast_id == b.id, EmailJob.status.in_(("queued", "held"))))).scalar_one()
    if not waiting and b.status == "sending":
        b.status, b.finished_at = "sent", now


async def advance(broadcast_id: str, now: Optional[datetime] = None) -> None:
    from voice import schedule
    now = now or datetime.utcnow()
    async with async_session() as db:
        claimed = await db.execute(update(EmailBroadcast).where(EmailBroadcast.id == broadcast_id, EmailBroadcast.status.in_(("scheduled", "testing", "sending")),
                                                                or_(EmailBroadcast.claimed_at.is_(None), EmailBroadcast.claimed_at < now - STUCK))
                                   .values(claimed_at=now).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        b = await db.get(EmailBroadcast, broadcast_id)
        try:
            if b.status == "scheduled" and schedule.utc(b.send_at) <= schedule.utc(now):
                await _start(db, b, now)
            elif b.status == "testing" and schedule.utc(b.test_ends_at) <= schedule.utc(now):
                await _pick_winner(db, b, now)
            else:
                await _watch(db, b, now)
        finally:
            b.claimed_at = None
            await db.commit()


async def _remind(now: datetime) -> None:
    """The day before an invitation's event: to those who said yes or maybe."""
    from notify import automations
    from voice import schedule
    async with async_session() as db:
        rows = (await db.execute(select(EmailBroadcast).where(EmailBroadcast.status.in_(("sending", "sent")), EmailBroadcast.reminded_at.is_(None), EmailBroadcast.bot_id.isnot(None)))).scalars().all()
        for b in rows:
            event = b.event or {}
            at = schedule.stored(schedule.utc(datetime.fromisoformat(event["at"]))) if event.get("at") else None
            if at is None or not (now < at <= now + timedelta(days=1)):
                continue
            claimed = await db.execute(update(EmailBroadcast).where(EmailBroadcast.id == b.id, EmailBroadcast.reminded_at.is_(None)).values(reminded_at=now).execution_options(synchronize_session=False))
            if claimed.rowcount != 1:
                continue
            sender = await senders.sender_for(db, b.user_id, b.bot_id)
            tz = schedule.zone(await schedule.settings_for(b.bot_id, db))
            coming = (await db.execute(select(EmailRsvp.email).where(EmailRsvp.broadcast_id == b.id, EmailRsvp.answer.in_(("yes", "maybe"))))).scalars().all()
            for to in coming:
                db.add(EmailJob(user_id=b.user_id, bot_id=b.bot_id, kind=f"rsvp_reminder:{b.id}", ref_id=automations.recipient_ref(to), to_email=to, automation="rsvp_reminder", step=1,
                                subject=f"Tomorrow: {event['title']}"[:200], body=f"A reminder, from {sender.name}:{_invitation(b, tz)}", send_at=now))
        await db.commit()


async def tick(now: Optional[datetime] = None) -> None:
    """Scheduler: sends that are due, tests that are over, and an eye on those going out. Each is claimed, so the processes share them."""
    now = now or datetime.utcnow()
    async with async_session() as db:
        due = (await db.execute(select(EmailBroadcast.id).where(or_(
            EmailBroadcast.status.in_(("testing", "sending")), (EmailBroadcast.status == "scheduled") & (EmailBroadcast.send_at <= now))).order_by(EmailBroadcast.send_at).limit(50))).scalars().all()
    for broadcast_id in due:
        try:
            await advance(broadcast_id, now)
        except Exception as e:
            logger.exception(f"Moving bulk email {broadcast_id} on failed: {e}")
    try:
        await _remind(now)
    except Exception as e:
        logger.exception(f"Invitation reminders failed: {e}")


# ─── before it goes, and after ───────────────────────────────────
SPAMMY = ("free money", "100% free", "act now", "you have won", "you've won", "winner", "lottery", "guaranteed", "risk free", "risk-free", "no cost", "click here", "urgent", "limited time",
          "double your", "earn money", "make money", "cash bonus", "buy now", "order now")
SHORTENERS = ("bit.ly", "tinyurl.", "t.co/", "goo.gl", "ow.ly", "is.gd", "cutt.ly")


def _shouting(text: str) -> bool:
    letters = [c for c in text if c.isascii() and c.isalpha()]
    return len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.6


def check_words(subject: str, body: str, subject_b: Optional[str] = None) -> list[str]:
    """Common reasons for landing in spam. A help, not a promise: mail services don't say how they decide."""
    notes = []
    for label, text in ((("Subject", subject),) + ((("Second subject", subject_b),) if subject_b else ())):
        if _shouting(text):
            notes.append(f"{label}: mostly capital letters. Write it as you'd write to a friend.")
        if len(text) > 70:
            notes.append(f"{label}: phones cut it off after about 40 to 70 characters.")
        if text.count("!") > 1 or "$$" in text or "₹₹" in text:
            notes.append(f"{label}: more than one exclamation mark looks like an advert.")
    both = f"{subject} {subject_b or ''} {body}".lower()
    words = sorted({w for w in SPAMMY if w in both})
    if words:
        notes.append("Words that spam filters watch for: " + ", ".join(words) + ".")
    if _shouting(body):
        notes.append("Message: mostly capital letters.")
    urls = re.findall(r"https?://\S+", body)
    if len(urls) > 5:
        notes.append(f"Message: {len(urls)} links. Two or three work better.")
    if any(s in u for u in urls for s in SHORTENERS):
        notes.append("Message: link shorteners are often blocked. Use the full address.")
    if len(body.strip()) < 40:
        notes.append("Message: very short. An email with almost no words looks suspicious.")
    return notes


async def report(db, b: EmailBroadcast) -> dict:
    rows = (await db.execute(select(EmailJob.variant, EmailJob.status, EmailJob.to_email, EmailJob.delivered_at, EmailJob.bounced_at, EmailJob.complained_at, EmailJob.clicked_at)
                             .where(EmailJob.broadcast_id == b.id))).all()
    replied = await _replied(db, b)
    counts = {k: 0 for k in ("queued", "held", "sent", "failed", "cancelled", "delivered", "bounced", "complained", "clicked", "replied", "unsubscribed")}
    variants = {"a": {"sent": 0, "clicked": 0, "replied": 0}, "b": {"sent": 0, "clicked": 0, "replied": 0}}
    addresses = set()
    for variant, status, to, delivered, bounced, complained, clicked in rows:
        key = to.lower()
        addresses.add(key)
        counts[status] = counts.get(status, 0) + 1
        for name, value in (("delivered", delivered), ("bounced", bounced), ("complained", complained), ("clicked", clicked), ("replied", key in replied)):
            counts[name] += 1 if value else 0
        if variant in variants:
            variants[variant]["sent"] += 1
            variants[variant]["clicked"] += 1 if clicked else 0
            variants[variant]["replied"] += 1 if key in replied else 0
    if b.started_at and addresses:
        gone = (await db.execute(select(EmailUnsubscribe.email).where(EmailUnsubscribe.user_id == b.user_id, EmailUnsubscribe.created_at >= b.started_at))).scalars().all()
        counts["unsubscribed"] = len({e.lower() for e in gone} & addresses)
    answers = dict((await db.execute(select(EmailRsvp.answer, func.count()).where(EmailRsvp.broadcast_id == b.id).group_by(EmailRsvp.answer))).all())
    return {"counts": counts, "variants": variants if b.subject_b else None, "rsvp": {k: answers.get(k, 0) for k in ("yes", "no", "maybe")} if (b.event or {}).get("title") else None,
            "no_mail_server": (b.audience or {}).get("no_mail_server", 0)}
