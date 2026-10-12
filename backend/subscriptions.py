"""Bot plans: lookup and activation, shared by payments, webhooks and bot listing."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, Subscription, Transaction, User

logger = logging.getLogger(__name__)

PLANS = {
    "1 Month Plan": {"price": 1, "days": 30},
    "6 Month Plan": {"price": 499, "days": 180},
    "12 Month Plan": {"price": 999, "days": 365},
}


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt else dt


async def active_subscription(bot_id: str, db: AsyncSession) -> Optional[Subscription]:
    """The bot's current plan, if it has one that hasn't ended."""
    subs = (await db.execute(
        select(Subscription)
        .where(Subscription.bot_id == bot_id, Subscription.status == "active")
        .order_by(Subscription.end_date.desc())
    )).scalars().all()
    now = datetime.utcnow()
    return next((s for s in subs if _naive(s.end_date) > now), None)


async def activate_plan(
    db: AsyncSession, *, user_id: str, bot_id: str, plan_name: str,
    razorpay_order_id: str, razorpay_payment_id: str,
) -> Subscription:
    """
    Grant a plan for a verified payment. Idempotent per payment: calling it twice
    (browser verify and webhook) returns the existing subscription.
    """
    already = (await db.execute(
        select(Transaction).where(Transaction.razorpay_payment_id == razorpay_payment_id)
    )).scalars().first()
    if already:
        existing = (await db.execute(
            select(Subscription).where(Subscription.razorpay_order_id == razorpay_order_id)
        )).scalars().first()
        if existing:
            return existing

    plan = PLANS[plan_name]
    current = await active_subscription(bot_id, db)
    start_base = _naive(current.end_date) if current else datetime.utcnow()
    if current:
        current.status = "renewed"  # replaced by the extension below

    sub = Subscription(
        user_id=user_id,
        bot_id=bot_id,
        plan_name=plan_name,
        credits_granted=1,
        price_paid=plan["price"],
        start_date=datetime.utcnow(),
        end_date=start_base + timedelta(days=plan["days"]),
        razorpay_order_id=razorpay_order_id,
        status="active",
    )
    db.add(sub)

    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
    if bot:
        bot.export_unlocked = True
        bot.is_active = True
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if user:
        user.subscription_tier = plan_name

    db.add(Transaction(
        user_id=user_id, bot_id=bot_id, amount=plan["price"],
        razorpay_order_id=razorpay_order_id, razorpay_payment_id=razorpay_payment_id, status="success",
    ))
    await db.commit()
    logger.info(f"Bot {bot_id} on {plan_name} until {sub.end_date:%Y-%m-%d}")
    return sub
