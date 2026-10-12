"""
Prepaid Nimmi balance (in paise). Every change is a ledger entry with a unique
`ref`, so a top-up or charge applies exactly once even if retried. Charges use a
conditional UPDATE, so a balance can never go below zero.
"""
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Balance, BalanceEntry


class InsufficientBalance(Exception):
    def __init__(self, needed: int, available: int):
        super().__init__(f"Not enough balance: need ₹{needed / 100:.0f}, have ₹{available / 100:.0f}")
        self.needed, self.available = needed, available


async def get(db: AsyncSession, owner_id: str) -> Balance:
    row = (await db.execute(select(Balance).where(Balance.user_id == owner_id))).scalars().first()
    if row:
        return row
    row = Balance(user_id=owner_id, balance_paise=0)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        row = (await db.execute(select(Balance).where(Balance.user_id == owner_id))).scalars().first()
    return row


async def _already(db: AsyncSession, ref: str) -> bool:
    return (await db.execute(select(BalanceEntry.id).where(BalanceEntry.ref == ref))).first() is not None


async def credit(db: AsyncSession, owner_id: str, paise: int, kind: str, ref: str, note: str = "") -> bool:
    """Add money. Returns False if this ref was already applied."""
    await get(db, owner_id)
    if await _already(db, ref):
        return False
    db.add(BalanceEntry(user_id=owner_id, amount_paise=paise, kind=kind, ref=ref, note=note[:200]))
    await db.execute(update(Balance).where(Balance.user_id == owner_id).values(balance_paise=Balance.balance_paise + paise))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def charge(db: AsyncSession, owner_id: str, paise: int, kind: str, ref: str, note: str = "") -> bool:
    """Take money, or raise InsufficientBalance. Returns False if this ref was already charged."""
    current = await get(db, owner_id)
    if await _already(db, ref):
        return False
    result = await db.execute(
        update(Balance).where(Balance.user_id == owner_id, Balance.balance_paise >= paise)
        .values(balance_paise=Balance.balance_paise - paise)
    )
    if result.rowcount != 1:
        await db.rollback()
        await db.refresh(current)
        raise InsufficientBalance(paise, current.balance_paise)
    db.add(BalanceEntry(user_id=owner_id, amount_paise=-paise, kind=kind, ref=ref, note=note[:200]))
    try:
        await db.commit()
    except IntegrityError:  # charged concurrently under the same ref: undo ours
        await db.rollback()
        return False
    return True
