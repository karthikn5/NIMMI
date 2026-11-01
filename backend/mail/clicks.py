"""
Clicks on the links in customer emails (mail plan 5.8, phase 6). Email security scanners (Microsoft Defender's Safe Links, Mimecast, Proofpoint, Barracuda and the
like) open an email's links by themselves, usually within seconds of delivery and several at once, so a raw click says little. Each click is kept with what tells
them apart, and settled half a minute later, when a sweep through the email's other links has shown: only a person's click then counts (EmailJob.clicked_at,
EmailLink.clicks, engagement, alerts, the business's webhook). Scanners still get the page they asked for: a link that didn't open would look broken to them.

The signals, from public practice (Suped's guides, a public scanner detector, ESPs' filters; mail_plan.md phase 6): a scanner's or an automation library's name in
the user agent decides by itself, and so do three of the email's links within three seconds; otherwise points add up: a click within seconds of sending, three
or more links within ten seconds, one network address opening five or more people's emails within ten seconds, no user agent or no Accept-Language. No single weak signal decides: a person who clicks one link
fast still counts. HEAD requests are never clicks. A scanner that waits minutes and opens a single link can't be told from a person.
"""
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.future import select

from backend.models import EmailClick, EmailJob, EmailLink
from database import async_session

logger = logging.getLogger(__name__)

SETTLE = timedelta(seconds=30)   # by then a scanner's sweep through the email's links has shown
FAST = 20                        # seconds after sending: scanners open links as an email arrives
BURST = 10                       # seconds: the links of one email, or one network across people
TIGHT = 3                        # seconds: SWEEP links this close together are a machine's, whenever it happens
SWEEP = 3                        # links of one email within BURST: nobody reads that fast
GATEWAY = 5                      # people's emails opened from one network within BURST
SCANNER_AT = 60
BATCH = 500
KEEP = timedelta(days=90)

# Names only automation and security scanners put in a user agent (lowercase substrings).
AUTOMATION = ("python-requests", "python-urllib", "aiohttp", "curl/", "wget/", "go-http-client", "java/", "apache-httpclient", "jetty/", "lua-resty-http", "ahc/",
              "libwww-perl", "headlesschrome", "phantomjs", "node-fetch", "axios/", "postmanruntime", "scrapy")
SCANNERS = ("barracuda", "mimecast", "proofpoint", "symantec", "trendmicro", "trend micro", "forcepoint", "safelinks", "bingpreview", "fireeye", "ironport",
            "zscaler", "fortiguard", "checkpoint", "sophos")
PREVIEWS = ("slackbot-linkexpanding", "facebookexternalhit", "facebookexternalua", "snap url preview", "telegrambot", "discordbot", "twitterbot", "linkedinbot",
            "skypeuripreview", "googlebot", "applebot", "whatsapp/")
MARKERS = AUTOMATION + SCANNERS + PREVIEWS


def _naive(at: Optional[datetime]) -> Optional[datetime]:
    return at.astimezone(timezone.utc).replace(tzinfo=None) if at is not None and at.tzinfo else at


def network_of(ip: str) -> Optional[str]:
    """A keyed hash of the address: enough to see one network opening many people's emails, never the address itself."""
    return hashlib.sha256(f"{os.getenv('JWT_SECRET', '')}|{ip}".encode()).hexdigest()[:16] if ip else None


def record(db, link: EmailLink, ip: str, agent: Optional[str], language: bool, now: Optional[datetime] = None) -> None:
    """Keep the click (the caller commits). It counts for nothing until it's settled."""
    db.add(EmailClick(user_id=link.user_id, token=link.token, job_id=link.job_id, kind=link.kind, at=now or datetime.utcnow(), network=network_of(ip),
                      agent=(agent or "").strip()[:300] or None, language=language))


def judge(agent: Optional[str], language: Optional[bool], seconds_after: Optional[float], links_together: int, people_together: int,
          links_tight: int = 0) -> tuple[int, list[str]]:
    """How likely this click is a scanner's, 0-100, and why. SCANNER_AT or more is a scanner."""
    ua = (agent or "").lower()
    named = next((m for m in MARKERS if m in ua), None)
    if named:
        return 100, [f'"{named}" in its user agent']
    points, reasons = 0, []
    if not ua:
        points += 20
        reasons.append("No user agent")
    elif not language:
        points += 10
        reasons.append("No language header")
    if seconds_after is not None and 0 <= seconds_after <= FAST:
        points += 40
        reasons.append(f"{int(seconds_after)} seconds after it was sent")
    if links_tight >= SWEEP:
        points += 60
        reasons.append(f"{links_tight} of the email's links within {TIGHT} seconds")
    elif links_together >= SWEEP:
        points += 45
        reasons.append(f"{links_together} of the email's links within {BURST} seconds")
    if people_together >= GATEWAY:
        points += 60
        reasons.append(f"One network opened {people_together} people's emails within {BURST} seconds")
    return min(points, 100), reasons


async def settle_due(now: Optional[datetime] = None) -> int:
    """Scheduler: clicks old enough to judge. Each is claimed, so the processes share them."""
    now = now or datetime.utcnow()
    async with async_session() as db:
        ids = (await db.execute(select(EmailClick.id).where(EmailClick.settled_at.is_(None), EmailClick.at <= now - SETTLE)
                                .order_by(EmailClick.at).limit(BATCH))).scalars().all()
    done = 0
    for click_id in ids:
        try:
            done += await _settle(click_id, now)
        except Exception as e:
            logger.exception(f"Settling email click {click_id} failed: {e}")
    return done


async def _settle(click_id: str, now: datetime) -> int:
    from mail import engagement, outbox
    later = []
    async with async_session() as db:
        claimed = await db.execute(update(EmailClick).where(EmailClick.id == click_id, EmailClick.settled_at.is_(None)).values(settled_at=now)
                                   .execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            await db.rollback()
            return 0
        c = await db.get(EmailClick, click_id)
        at = _naive(c.at)
        lo, hi = at - timedelta(seconds=BURST), at + timedelta(seconds=BURST)
        job = await db.get(EmailJob, c.job_id) if c.job_id else None
        links_together = (await db.execute(select(func.count(func.distinct(EmailClick.token))).where(
            EmailClick.job_id == c.job_id, EmailClick.at >= lo, EmailClick.at <= hi))).scalar_one() if c.job_id else 0
        links_tight = (await db.execute(select(func.count(func.distinct(EmailClick.token))).where(
            EmailClick.job_id == c.job_id, EmailClick.at >= at - timedelta(seconds=TIGHT), EmailClick.at <= at + timedelta(seconds=TIGHT)))).scalar_one() if c.job_id else 0
        people_together = (await db.execute(select(func.count(func.distinct(EmailClick.job_id))).where(
            EmailClick.network == c.network, EmailClick.at >= lo, EmailClick.at <= hi))).scalar_one() if c.network else 0
        sent = _naive(job.sent_at) if job is not None else None
        c.score, c.reasons = judge(c.agent, c.language, (at - sent).total_seconds() if sent else None, links_together, people_together, links_tight)
        c.person = c.score < SCANNER_AT
        link = await db.get(EmailLink, c.token)
        if link is not None and not c.person:
            link.scanner_clicks = (link.scanner_clicks or 0) + 1
        elif link is not None:
            first = (await db.execute(select(func.count()).select_from(EmailClick).where(
                EmailClick.token == c.token, EmailClick.person.is_(True), EmailClick.id != c.id))).scalar_one() == 0
            link.clicks = (link.clicks or 0) + 1
            link.first_at = min(_naive(link.first_at) or at, at)
            link.last_at = max(_naive(link.last_at) or at, at)
            if job is not None:
                job.clicked_at = min(_naive(job.clicked_at) or at, at)
                later = await engagement.clicked(db, job, link, at)
                if first:
                    await outbox.emit(db, job.user_id, "email.clicked", {"email_id": job.id, "to": job.to_email, "subject": job.subject, "assistant_id": job.bot_id,
                                                                         "link": link.label or link.target, "url": link.target if link.kind != "file" else None,
                                                                         "kind": link.kind, "at": at.isoformat()})
        await db.commit()
    for action in later:  # alerts go out once it's saved, without a connection waiting on them
        await action()
    return 1


async def purge(now: Optional[datetime] = None) -> None:
    from sqlalchemy import delete
    async with async_session() as db:
        await db.execute(delete(EmailClick).where(EmailClick.at < (now or datetime.utcnow()) - KEEP))
        await db.commit()
