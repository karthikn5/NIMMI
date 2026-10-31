"""
Who a workspace doesn't email (EmailUnsubscribe) and addresses nobody is emailed at (EmailBounce, every workspace).

Reasons, strongest first: a spam report, a hard bounce, the team stopped them, they unsubscribed. "marketing" (from the
unsubscribe page) stops only bulk email; emails about their own enquiries still go. A meeting confirmation still goes
to someone who unsubscribed (they asked for the meeting), never to an address that bounced or reported spam.
"""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import EmailBounce, EmailJob, EmailUnsubscribe

TEXT = {
    "unsubscribed": "They unsubscribed",
    "marketing": "They stopped offers and news",
    "complaint": "They reported an email as spam",
    "bounce": "The address doesn't exist (an email to it bounced)",
    "suppressed": "Resend won't send to this address: an earlier email to it bounced or was reported as spam",
    "team": "Your team stopped emails to them",
}
_RANK = {"unsubscribed": 1, "team": 2, "bounce": 3, "complaint": 4}


def _norm(address: str) -> str:
    return (address or "").strip().lower()


async def why_blocked(db, owner_id: str, address: str, *, marketing: bool = False, requested: bool = False) -> Optional[str]:
    """Why this workspace mustn't email this address, or None. `marketing`: a bulk email; `requested`: something the
    person asked for, such as their meeting's confirmation."""
    a = _norm(address)
    bounce = await db.get(EmailBounce, a)
    if bounce:
        return TEXT["bounce"] if bounce.kind == "bounce" else TEXT["suppressed"]
    row = (await db.execute(select(EmailUnsubscribe).where(
        EmailUnsubscribe.user_id == owner_id, func.lower(EmailUnsubscribe.email) == a))).scalars().first()
    if row is None:
        return None
    reason = row.reason or "unsubscribed"
    if (row.scope or "all") == "marketing" and reason == "unsubscribed":
        return TEXT["marketing"] if marketing else None
    if requested and reason == "unsubscribed":
        return None
    return TEXT.get(reason, TEXT["unsubscribed"])


async def add(db, owner_id: str, address: str, reason: str = "unsubscribed", scope: str = "all",
              bot_id: Optional[str] = None) -> None:
    """Stop emails to this address from this workspace (the caller commits). A stronger reason replaces a weaker one,
    and "all" widens "marketing"."""
    a = _norm(address)
    row = (await db.execute(select(EmailUnsubscribe).where(
        EmailUnsubscribe.user_id == owner_id, func.lower(EmailUnsubscribe.email) == a))).scalars().first()
    if row is None:
        db.add(EmailUnsubscribe(user_id=owner_id, email=a, reason=reason, scope=scope, bot_id=bot_id))
        return
    if _RANK.get(reason, 0) > _RANK.get(row.reason or "unsubscribed", 0):
        row.reason = reason
    if scope == "all" or reason != "unsubscribed":
        row.scope = "all"
    row.bot_id = row.bot_id or bot_id


async def resubscribe(db, owner_id: str, address: str) -> bool:
    """They changed their mind on the unsubscribe page. Only their own unsubscribe is undone, never a spam report, a
    bounce or the team's stop. True if they can be emailed again."""
    a = _norm(address)
    row = (await db.execute(select(EmailUnsubscribe).where(
        EmailUnsubscribe.user_id == owner_id, func.lower(EmailUnsubscribe.email) == a))).scalars().first()
    if row is None:
        return True
    if (row.reason or "unsubscribed") != "unsubscribed":
        return False
    await db.delete(row)
    return True


async def add_bounce(db, address: str, kind: str = "bounce", detail: Optional[str] = None) -> None:
    """An address that doesn't take mail, for every workspace (the caller commits)."""
    a = _norm(address)
    if a and await db.get(EmailBounce, a) is None:
        db.add(EmailBounce(email=a, kind=kind, detail=(detail or "")[:300] or None))


async def cancel_queued(db, address: str, why: str, owner_id: Optional[str] = None) -> int:
    """Cancel what's still waiting to go to this address (in one workspace, or all). Returns how many."""
    query = select(EmailJob).where(func.lower(EmailJob.to_email) == _norm(address), EmailJob.status.in_(("queued", "draft")))
    if owner_id:
        query = query.where(EmailJob.user_id == owner_id)
    jobs = (await db.execute(query)).scalars().all()
    for job in jobs:
        job.status, job.error = "cancelled", why
    return len(jobs)


async def cancel_queued_bulk(db, owner_id: str, address: str) -> int:
    """They stopped offers and news: cancel the bulk emails still waiting for them in this workspace."""
    jobs = (await db.execute(select(EmailJob).where(
        EmailJob.user_id == owner_id, func.lower(EmailJob.to_email) == _norm(address), EmailJob.status == "queued",
        EmailJob.broadcast_id.is_not(None)))).scalars().all()
    for job in jobs:
        job.status, job.error = "cancelled", TEXT["marketing"]
    return len(jobs)


async def commit_quietly(db) -> None:
    """Two processes stopping the same address at once: the second finds it done."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
