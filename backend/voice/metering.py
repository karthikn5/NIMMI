"""Voice minutes: balances, monthly plan cycles, charging calls and crediting top-ups."""
import math
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, VoiceTopup, VoiceWallet
from subscriptions import active_subscription
from voice.catalog import PLAN_MINUTES, TRIAL_MINUTES


def _naive(dt):
    return dt.replace(tzinfo=None) if dt else dt


async def _plan_allowance(db: AsyncSession, owner_id: str) -> int:
    """Sum of monthly voice minutes included in the owner's active bot plans."""
    if not PLAN_MINUTES:
        return 0
    bots = (await db.execute(select(Bot.bot_id).where(Bot.user_id == owner_id))).scalars().all()
    total = 0
    for bot_id in bots:
        sub = await active_subscription(bot_id, db)
        if sub:
            total += int(PLAN_MINUTES.get(sub.plan_name, 0))
    return total


async def get_wallet(db: AsyncSession, owner_id: str) -> VoiceWallet:
    """The workspace's wallet, created with trial minutes and rolled to the current cycle."""
    wallet = (await db.execute(select(VoiceWallet).where(VoiceWallet.user_id == owner_id))).scalars().first()
    now = datetime.utcnow()
    if not wallet:
        # In a savepoint: if another process creates it at the same moment, only this insert is undone,
        # not the caller's other work in the session (e.g. the dialler's half-done jobs).
        try:
            async with db.begin_nested():
                db.add(VoiceWallet(user_id=owner_id, plan_minutes=0, plan_minutes_used=0,
                                   topup_minutes=TRIAL_MINUTES, cycle_end=now + timedelta(days=30)))
        except IntegrityError:  # created concurrently
            pass
        await db.commit()
        wallet = (await db.execute(select(VoiceWallet).where(VoiceWallet.user_id == owner_id))).scalars().first()
    if not wallet.cycle_end or _naive(wallet.cycle_end) <= now:
        wallet.plan_minutes = await _plan_allowance(db, owner_id)
        wallet.plan_minutes_used = 0
        wallet.cycle_end = now + timedelta(days=30)
        await db.commit()
    return wallet


def minutes_left(wallet: VoiceWallet) -> int:
    return max(wallet.plan_minutes - wallet.plan_minutes_used, 0) + max(wallet.topup_minutes, 0)


def billable_minutes(seconds: float) -> int:
    """Per started minute: 1 s -> 1, 60 s -> 1, 61 s -> 2."""
    return math.ceil(seconds / 60) if seconds > 0 else 0


async def charge(db: AsyncSession, owner_id: str, seconds: float) -> int:
    """Deduct a call's minutes: plan minutes first, then top-up. Returns minutes billed."""
    minutes = billable_minutes(seconds)
    if not minutes:
        return 0
    wallet = await get_wallet(db, owner_id)
    from_plan = min(minutes, max(wallet.plan_minutes - wallet.plan_minutes_used, 0))
    wallet.plan_minutes_used += from_plan
    wallet.topup_minutes = max(wallet.topup_minutes - (minutes - from_plan), 0)
    await db.commit()
    return minutes


async def credit_topup(db: AsyncSession, order_id: str, payment_id: str) -> VoiceTopup | None:
    """Mark a top-up paid and add its minutes. Safe to call twice for the same payment."""
    topup = (await db.execute(select(VoiceTopup).where(VoiceTopup.razorpay_order_id == order_id))).scalars().first()
    if not topup:
        return None
    if topup.status == "paid":
        return topup
    wallet = await get_wallet(db, topup.user_id)
    topup.status, topup.razorpay_payment_id = "paid", payment_id
    wallet.topup_minutes += topup.minutes
    await db.commit()
    return topup
