"""
Voice credits: balances, monthly plan cycles, charging calls and crediting top-ups.

A call minute is 1 credit plus the agent's AI model's credits (voice/ai_models.py). Calls are billed in 30-second
steps. Balances are kept to two decimals. Wallets from before credits move their minutes over
1:1 the first time they're read (a minute was a standard-model minute).
"""
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, VoiceTopup, VoiceWallet
from subscriptions import active_subscription
from voice.catalog import BILLING_STEP_SEC, FREE_CREDITS, PLAN_CREDITS


def _naive(dt):
    return dt.replace(tzinfo=None) if dt else dt


async def _plan_allowance(db: AsyncSession, owner_id: str) -> float:
    """Sum of monthly voice credits included in the owner's active bot plans."""
    if not PLAN_CREDITS:
        return 0
    bots = (await db.execute(select(Bot.bot_id).where(Bot.user_id == owner_id))).scalars().all()
    total = 0.0
    for bot_id in bots:
        sub = await active_subscription(bot_id, db)
        if sub:
            total += float(PLAN_CREDITS.get(sub.plan_name, 0))
    return total


async def get_wallet(db: AsyncSession, owner_id: str) -> VoiceWallet:
    """The workspace's wallet, created with the free credits and rolled to the current cycle."""
    wallet = (await db.execute(select(VoiceWallet).where(VoiceWallet.user_id == owner_id))).scalars().first()
    now = datetime.utcnow()
    if not wallet:
        # In a savepoint: if another process creates it at the same moment, only this insert is undone,
        # not the caller's other work in the session (e.g. the dialler's half-done jobs).
        try:
            async with db.begin_nested():
                db.add(VoiceWallet(user_id=owner_id, plan_minutes=0, plan_minutes_used=0, topup_minutes=0,
                                   plan_credits=0, plan_credits_used=0, credits=FREE_CREDITS,
                                   cycle_end=now + timedelta(days=30)))
        except IntegrityError:  # created concurrently
            pass
        await db.commit()
        wallet = (await db.execute(select(VoiceWallet).where(VoiceWallet.user_id == owner_id))).scalars().first()
    if wallet.credits is None:  # from before credits: the same values, and only while they're still unset
        await db.execute(update(VoiceWallet).where(VoiceWallet.user_id == owner_id, VoiceWallet.credits.is_(None)).values(
            credits=float(wallet.topup_minutes or 0), plan_credits=float(wallet.plan_minutes or 0),
            plan_credits_used=float(wallet.plan_minutes_used or 0)))
        await db.commit()
        await db.refresh(wallet)
    if not wallet.cycle_end or _naive(wallet.cycle_end) <= now:
        wallet.plan_credits = await _plan_allowance(db, owner_id)
        wallet.plan_credits_used = 0
        wallet.cycle_end = now + timedelta(days=30)
        await db.commit()
    return wallet


def plan_left(wallet: VoiceWallet) -> float:
    return max((wallet.plan_credits or 0) - (wallet.plan_credits_used or 0), 0)


def credits_left(wallet: VoiceWallet) -> float:
    return round(plan_left(wallet) + max(wallet.credits or 0, 0), 2)


def call_credits(seconds: float, per_minute: float) -> float:
    """Half-minute steps at the call's rate, rounded up to a hundredth: 20 s at 1 a minute -> 0.5; 61 s -> 1.5;
    61 s at 1.5 -> 2.25; 20 s at 1.27 -> 0.64."""
    steps = math.ceil(seconds / BILLING_STEP_SEC) if seconds > 0 else 0
    return math.ceil(round(steps * BILLING_STEP_SEC / 60 * per_minute * 100, 6)) / 100


def enough_for_a_call(credits: float, per_minute: float) -> bool:
    """A call needs its first half-minute paid for."""
    return credits > 0 and credits >= call_credits(1, per_minute)


def seconds_for(credits: float, per_minute: float) -> float:
    """How long a call these credits pay for, at the model's rate."""
    return max(credits, 0) / per_minute * 60 if per_minute > 0 else math.inf


async def charge(db: AsyncSession, owner_id: str, seconds: float, per_minute: float) -> float:
    """Deduct a call's credits: plan credits first, then the rest. Returns the credits it cost.
    One UPDATE, so calls ending at the same moment on different server processes are all counted."""
    cost = call_credits(seconds, per_minute)
    if not cost:
        return 0
    wallet = await get_wallet(db, owner_id)
    from_plan = round(min(cost, plan_left(wallet)), 2)
    rest = round(cost - from_plan, 2)
    await db.execute(update(VoiceWallet).where(VoiceWallet.user_id == owner_id).values(
        plan_credits_used=VoiceWallet.plan_credits_used + from_plan,
        # The call was limited to what was left (CallSession), so this rarely goes below 0; when it would
        # (two calls at once, the last half-minute step), the difference isn't owed.
        credits=case((VoiceWallet.credits - rest < 0, 0), else_=VoiceWallet.credits - rest)))
    await db.commit()
    return cost


async def credit_topup(db: AsyncSession, order_id: str, payment_id: str) -> Optional[VoiceTopup]:
    """Mark a top-up paid and add its credits, once: the payment page and Razorpay's webhook may both
    report the same payment, at the same moment on different server processes."""
    topup = (await db.execute(select(VoiceTopup).where(VoiceTopup.razorpay_order_id == order_id))).scalars().first()
    if not topup:
        return None
    if topup.status == "paid":
        return topup
    await get_wallet(db, topup.user_id)
    marked = await db.execute(update(VoiceTopup).where(VoiceTopup.id == topup.id, VoiceTopup.status != "paid")
                              .values(status="paid", razorpay_payment_id=payment_id))
    if marked.rowcount:
        await db.execute(update(VoiceWallet).where(VoiceWallet.user_id == topup.user_id).values(
            credits=VoiceWallet.credits + topup.minutes))
    await db.commit()
    await db.refresh(topup)
    return topup
