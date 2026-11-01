"""
Who agreed to offers and news (mail plan 5.2). Emails about someone's own enquiry go to whoever gave their address for it; bulk email and marketing go only to people
with a record here: the purpose, the words they saw, where, when, and who noted it. Per assistant, as one account can run several businesses. Unsubscribing withdraws it,
and only the person can give it again: a team member or an import can't.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.future import select

from backend.models import Consent

WORDS = "Send me offers and news"
THEIR_OWN = ("chat", "form", "resubscribed")  # the person did it themselves


async def _row(db, bot_id: str, address: str) -> Optional[Consent]:
    return (await db.execute(select(Consent).where(Consent.bot_id == bot_id, Consent.email == address.strip().lower(), Consent.purpose == "marketing"))).scalars().first()


async def give(db, owner_id: str, bot_id: str, address: str, source: str, words: str, by: Optional[str] = None) -> bool:
    """Record it (the caller commits). False when they withdrew it and someone else is giving it back."""
    row = await _row(db, bot_id, address)
    if row is not None and row.status == "withdrawn" and row.by is None and source not in THEIR_OWN:
        return False  # they stopped it themselves
    if row is None:
        row = Consent(user_id=owner_id, bot_id=bot_id, email=address.strip().lower(), purpose="marketing")
        db.add(row)
    row.status, row.source, row.words, row.by, row.given_at, row.withdrawn_at = "given", source[:20], (words or "")[:1000], by, datetime.utcnow(), None
    return True


async def withdraw(db, owner_id: str, address: str, bot_id: Optional[str] = None, by: Optional[str] = None) -> int:
    """It ended, on one assistant or (none) on all of this workspace's. `by`: a team member noted it; without one, the person did it (the caller commits)."""
    query = select(Consent).where(Consent.user_id == owner_id, Consent.email == address.strip().lower(), Consent.status == "given")
    rows = (await db.execute(query.where(Consent.bot_id == bot_id) if bot_id else query)).scalars().all()
    for row in rows:
        row.status, row.withdrawn_at, row.by = "withdrawn", datetime.utcnow(), by
    return len(rows)


async def restore(db, owner_id: str, address: str) -> None:
    """They pressed Resubscribe: what they'd agreed to comes back, nothing more (the caller commits)."""
    rows = (await db.execute(select(Consent).where(Consent.user_id == owner_id, Consent.email == address.strip().lower(), Consent.status == "withdrawn", Consent.by.is_(None)))).scalars().all()
    for row in rows:
        row.status, row.source, row.words, row.given_at, row.withdrawn_at = "given", "resubscribed", "Pressed Resubscribe on the unsubscribe page", datetime.utcnow(), None


async def has(db, bot_id: str, address: str) -> bool:
    row = await _row(db, bot_id, address)
    return row is not None and row.status == "given"


async def agreed(db, bot_id: str) -> set[str]:
    return set((await db.execute(select(Consent.email).where(Consent.bot_id == bot_id, Consent.purpose == "marketing", Consent.status == "given"))).scalars().all())


async def of(db, bot_id: str, address: Optional[str]) -> Optional[dict]:
    """The record, for the team to read."""
    row = await _row(db, bot_id, address) if address else None
    if row is None:
        return None
    return {"status": row.status, "source": row.source, "words": row.words, "given_at": row.given_at.isoformat() if row.given_at else None,
            "withdrawn_at": row.withdrawn_at.isoformat() if row.withdrawn_at else None}
