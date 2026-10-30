"""
Plans per assistant (BILLING_PLAN.md): Starter, Growth and Pro, monthly or yearly at 10 months' price, as the website
sells them. A monthly plan renews itself through a Razorpay subscription; a yearly one is paid once a year (RBI lets
automatic debits through without an OTP only up to ₹15,000). The 1, 6 and 12 Month plans sold before 31 Oct 2026 keep
everything until they end. Whatever asks whether an assistant is live, or what it may use, reads `active_subscription`.

Buying: `plan_purchase` says what a choice means now (start, extend, upgrade now paying the difference for the days
left, or a change from the end of the current period); payments.py takes the money and `apply_purchase` makes the
plan rows, once per payment even when the browser's check and Razorpay's webhook arrive together.
"""
import calendar
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend.models import Bot, NotificationLog, Subscription, Transaction, User
except ImportError:
    from models import Bot, NotificationLog, Subscription, Transaction, User

logger = logging.getLogger(__name__)

TIERS = {
    "starter": {"name": "Starter", "monthly": 999},
    "growth": {"name": "Growth", "monthly": 2499},
    "pro": {"name": "Pro", "monthly": 6999},
}
RANK = {tier: i for i, tier in enumerate(TIERS)}
PERIODS = {"monthly": {"months": 1, "pays_for": 1, "days": 30}, "yearly": {"months": 12, "pays_for": 10, "days": 365}}
# Sold until 30 Oct 2026, everything included until they end. Kept so payments made for them before then still apply.
LEGACY = {"1 Month Plan": {"price": 999, "days": 30}, "6 Month Plan": {"price": 499, "days": 180},
          "12 Month Plan": {"price": 999, "days": 365}}
PLANS = LEGACY  # older imports
SUBSCRIPTION_CYCLES = 120  # Razorpay charges a subscription for up to 10 years


def price(tier: str, period: str) -> int:
    return TIERS[tier]["monthly"] * PERIODS[period]["pays_for"]


def label(tier: Optional[str], period: Optional[str], plan_name: str = "") -> str:
    """"Growth monthly"; an earlier plan keeps its own name."""
    return f"{TIERS[tier]['name']} {period}" if tier in TIERS and period in PERIODS else plan_name


def add_months(at: datetime, months: int) -> datetime:
    month = at.month - 1 + months
    year, month = at.year + month // 12, month % 12 + 1
    return at.replace(year=year, month=month, day=min(at.day, calendar.monthrange(year, month)[1]))


def naive(dt: Optional[datetime]) -> Optional[datetime]:
    """UTC without a zone (SQLite keeps it that way; Postgres gives it with one)."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def from_unix(seconds) -> Optional[datetime]:
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc).replace(tzinfo=None) if seconds else None


def day(dt: datetime) -> str:
    return f"{naive(dt):%d %b %Y}".lstrip("0")


# ─── which plan an assistant is on ────────────────────────────────
async def plans_of(bot_id: str, db: AsyncSession) -> tuple[Optional[Subscription], Optional[Subscription]]:
    """The plan the assistant is on now, and one set to start later (a change at the end of the period)."""
    now = datetime.utcnow()
    rows = (await db.execute(select(Subscription).where(
        Subscription.bot_id == bot_id, Subscription.status == "active").order_by(Subscription.start_date))).scalars().all()
    current = [s for s in rows if (s.start_date is None or naive(s.start_date) <= now) and naive(s.end_date) > now]
    later = [s for s in rows if s.start_date is not None and naive(s.start_date) > now]
    return (current[-1] if current else None), (later[0] if later else None)


async def active_subscription(bot_id: str, db: AsyncSession) -> Optional[Subscription]:
    """The bot's current plan, if it has one (it's live on websites while it does)."""
    return (await plans_of(bot_id, db))[0]


# ─── what buying means ────────────────────────────────────────────
@dataclass
class Purchase:
    """What buying `tier`/`period` for an assistant means right now."""
    action: str                     # start, extend, upgrade, schedule
    tier: str
    period: str
    pay_now: int                    # rupees taken at checkout (a renewing plan that starts later: none)
    starts_at: datetime             # when it (or, for an upgrade, its tier) starts
    ends_at: datetime               # the end of what's paid for (a renewing plan: until its next charge)
    renews: bool                    # a monthly plan renewing through a Razorpay subscription
    replaces: Optional[str] = None  # the current plan it replaces (upgrade, extend) or follows (schedule)
    drops: Optional[str] = None     # a change set earlier (not paid) that this one takes the place of
    note: str = ""                  # for the customer


def plan_purchase(current: Optional[Subscription], later: Optional[Subscription], tier: str, period: str, *,
                  subscriptions: bool = True, now: Optional[datetime] = None) -> Purchase:
    """What choosing `tier`/`period` does for an assistant on `current` (with `later` set to follow it). Raises
    ValueError, worded for the customer, when it can't be bought now. `subscriptions`: whether monthly plans can renew
    through Razorpay (else they're paid a month at a time)."""
    if tier not in TIERS or period not in PERIODS:
        raise ValueError("Choose Starter, Growth or Pro, monthly or yearly.")
    now = now or datetime.utcnow()
    name, months, full = label(tier, period), PERIODS[period]["months"], price(tier, period)
    renews = period == "monthly" and subscriptions
    each = "a month" if period == "monthly" else "a year"
    if later is not None and not later.auto_renewal:
        raise ValueError(f"{label(later.tier, later.period, later.plan_name)} is already paid and starts on "
                         f"{day(later.start_date)}. You can change it after that.")
    drops = later.id if later is not None else None
    if current is None:
        return Purchase("start", tier, period, full, now, add_months(now, months), renews, drops=drops,
                        note=f"{name} starts now: ₹{full:,} {each}" + (", renewing by itself." if renews else "."))
    end = naive(current.end_date)
    then = add_months(end, months)
    if current.tier is None:  # an earlier plan, everything included: the new one follows it
        return Purchase("schedule", tier, period, 0 if renews else full, end, then, renews, current.id, drops,
                        f"Your current plan runs until {day(end)}; {name} starts then" +
                        (f" (₹{full:,} {each}, charged on that day)." if renews else f". You pay ₹{full:,} now."))
    if current.tier == tier and current.period == period:
        if current.auto_renewal and current.razorpay_subscription_id:
            raise ValueError(f"{name} renews by itself on {day(end)}.")
        if renews:  # paid a month at a time so far, or renewal stopped: renew by itself from the end of this month
            return Purchase("schedule", tier, period, 0, end, then, True, current.id, drops,
                            f"{name} renews by itself from {day(end)}: ₹{full:,} a month.")
        return Purchase("extend", tier, period, full, now, then, False, current.id, drops,
                        f"Adds {'a month' if period == 'monthly' else 'a year'}: {name} until {day(then)}.")
    if current.period == period and RANK[tier] > RANK[current.tier]:  # an upgrade starts now
        left = max((end - now).total_seconds(), 0) / 86400
        part = min(1.0, left / PERIODS[period]["days"])
        pay = max(1, math.ceil((price(tier, period) - price(current.tier, period)) * part))
        return Purchase("upgrade", tier, period, pay, now, end, renews, current.id, drops,
                        f"{name} starts now. You pay ₹{pay:,}, the difference for the {math.ceil(left)} days left; "
                        f"from {day(end)}, ₹{full:,} {each}.")
    # A lower tier, or the other period: from the end of this one, so no paid day is lost.
    return Purchase("schedule", tier, period, 0 if renews else full, end, then, renews, current.id, drops,
                    f"You keep {label(current.tier, current.period, current.plan_name)} until {day(end)}; {name} "
                    "starts then" + (f" (₹{full:,} {each}, charged on that day)." if renews else f". You pay ₹{full:,} now."))


# ─── applying a payment ───────────────────────────────────────────
async def paid_already(db: AsyncSession, payment_id: Optional[str]) -> bool:
    return bool(payment_id) and (await db.execute(
        select(Transaction.id).where(Transaction.razorpay_payment_id == payment_id))).first() is not None


def _claim(db: AsyncSession, user_id: str, kind: str, ref: str) -> None:
    """A unique row saved with the change it guards: the second of two at once fails, so it's made once."""
    db.add(NotificationLog(user_id=user_id, kind=kind, ref_id=ref[:200], status="sent"))


@dataclass
class Applied:
    plan: Subscription
    stop: list[str] = field(default_factory=list)  # Razorpay subscriptions that must stop charging now
    new: bool = True


async def _made(db: AsyncSession, sub_id: Optional[str], order_id: Optional[str]) -> Optional[Subscription]:
    if sub_id:
        return (await db.execute(select(Subscription).where(Subscription.razorpay_subscription_id == sub_id))).scalars().first()
    if order_id:
        return (await db.execute(select(Subscription).where(Subscription.razorpay_order_id == order_id))).scalars().first()
    return None


async def apply_purchase(db: AsyncSession, notes: dict, *, payment_id: Optional[str], order_id: Optional[str] = None,
                         subscription: Optional[dict] = None) -> Applied:
    """A paid (or, for a renewing plan that starts later, authorised) purchase, made into plan rows once. `notes`: the
    order's or subscription's own (what checkout decided); `subscription`: the Razorpay subscription of a monthly plan.
    Also says which Razorpay subscriptions must stop charging (the plan it replaced, or a change it took the place of)."""
    sub_id = subscription["id"] if subscription else None
    made = await _made(db, sub_id, order_id)
    if made is not None:
        return Applied(made, new=False)
    tier, period, action = notes["tier"], notes["period"], notes.get("action") or "start"
    user_id, bot_id = notes["user_id"], notes["bot_id"]
    months, now = PERIODS[period]["months"], datetime.utcnow()
    current = await db.get(Subscription, notes["replaces"]) if notes.get("replaces") else None
    if current is not None and (current.bot_id != bot_id or current.status != "active"):
        current = None
    end = naive(current.end_date) if current is not None else None
    if action == "extend":
        start, until = now, add_months(end if end and end > now else now, months)
    elif action == "upgrade":
        start, until = now, end if end and end > now else add_months(now, months)
    elif action == "schedule":
        start = end if end and end > now else now
        until = add_months(start, months)
    else:
        start, until = now, add_months(now, months)
    if subscription and subscription.get("current_end") and start <= now:
        until = from_unix(subscription["current_end"])  # Razorpay's own cycle, once it's charging
    stop: list[str] = []
    if current is not None:
        if action in ("extend", "upgrade"):
            current.status = "renewed" if action == "extend" else "replaced"
        else:
            current.auto_renewal = False  # it ends; this one follows
        if action in ("upgrade", "schedule") and current.razorpay_subscription_id and current.rzp_status not in ("cancelled", "completed"):
            stop.append(current.razorpay_subscription_id)
            current.rzp_status = "cancel_failed"  # until Razorpay confirms it stopped (payments.stop_charging)
    if notes.get("drops"):
        dropped = await db.get(Subscription, notes["drops"])
        if dropped is not None and dropped.bot_id == bot_id and dropped.status == "active" and dropped is not current:
            dropped.status = "cancelled"
            if dropped.razorpay_subscription_id:
                stop.append(dropped.razorpay_subscription_id)
                dropped.rzp_status = "cancel_failed"  # until Razorpay confirms it stopped
    row = Subscription(user_id=user_id, bot_id=bot_id, plan_name=label(tier, period), tier=tier, period=period,
                       credits_granted=1, price_paid=price(tier, period), start_date=start, end_date=until,
                       auto_renewal=bool(sub_id), razorpay_subscription_id=sub_id, razorpay_order_id=order_id,
                       rzp_status=(subscription or {}).get("status"), status="active")
    db.add(row)
    pay_now = int(notes.get("pay_now") or 0)
    if pay_now > 0 and payment_id and not await paid_already(db, payment_id):
        what = label(tier, period) + (", the days left" if action == "upgrade" else "")
        db.add(Transaction(user_id=user_id, bot_id=bot_id, amount=pay_now, razorpay_order_id=order_id,
                           razorpay_payment_id=payment_id, status="success", plan_name=what))
    bot = await db.get(Bot, bot_id)
    if bot is not None:
        bot.export_unlocked = True
        bot.is_active = True
    user = await db.get(User, user_id)
    if user is not None:
        user.subscription_tier = label(tier, period)
    _claim(db, user_id, "plan_applied", str(sub_id or order_id or payment_id))  # last: no query may flush it early
    try:
        await db.commit()
    except IntegrityError:  # the browser's check and the webhook at once: the other one made it
        await db.rollback()
        made = await _made(db, sub_id, order_id)
        if made is None:
            raise
        return Applied(made, new=False)
    logger.info(f"Bot {bot_id}: {label(tier, period)} ({action}) from {start:%Y-%m-%d} until {until:%Y-%m-%d}")
    return Applied(row, stop)


async def renewal_charged(db: AsyncSession, subscription: dict, payment: Optional[dict]) -> Optional[Subscription]:
    """A Razorpay subscription charged a cycle: the plan runs to the end of it. Once per payment."""
    row = (await db.execute(select(Subscription).where(
        Subscription.razorpay_subscription_id == subscription.get("id")))).scalars().first()
    if row is None:
        return None
    if payment and await paid_already(db, payment.get("id")):
        return row
    if row.status != "active":
        logger.warning(f"Razorpay charged subscription {row.razorpay_subscription_id} of a plan that was {row.status}: "
                       "check it stopped, and refund the charge from the Razorpay Dashboard")
    end = from_unix(subscription.get("current_end"))
    if end and end > naive(row.end_date):
        row.end_date = end
    if row.status == "active":
        row.rzp_status, row.auto_renewal = "active", True
    if payment and payment.get("id"):
        _claim(db, row.user_id, "plan_charge", payment["id"])
        db.add(Transaction(user_id=row.user_id, bot_id=row.bot_id, amount=int(payment.get("amount") or 0) // 100,
                           razorpay_order_id=payment.get("order_id"), razorpay_payment_id=payment["id"],
                           status="success", plan_name=row.plan_name))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return row


async def sync_subscription(db: AsyncSession, subscription: dict) -> Optional[Subscription]:
    """Where Razorpay says a renewing plan's subscription is, for when its webhook didn't reach us (not set up yet, or
    lost): the plan runs to the end of the cycle Razorpay charged, so a customer who paid keeps their assistant, and a
    subscription that stopped renewing there stops here too."""
    row = (await db.execute(select(Subscription).where(
        Subscription.razorpay_subscription_id == subscription.get("id")))).scalars().first()
    if row is None or row.status != "active":
        return row
    end = from_unix(subscription.get("current_end"))
    if end and end > naive(row.end_date):
        logger.info(f"Plan {row.id} renewed at Razorpay (no webhook came): until {end:%Y-%m-%d}")
        row.end_date = end
    status = subscription.get("status")
    if status in ("halted", "cancelled", "completed", "expired"):
        row.rzp_status, row.auto_renewal = status, False
    elif status in ("active", "pending", "paused"):
        row.rzp_status = status
    await db.commit()
    return row


async def activate_plan(db: AsyncSession, *, user_id: str, bot_id: str, plan_name: str, razorpay_order_id: str,
                        razorpay_payment_id: str) -> Subscription:
    """An earlier 1/6/12 Month plan, paid for while it was still sold (an order paid around the change). Once per
    payment; buying again extends it."""
    if await paid_already(db, razorpay_payment_id):
        existing = (await db.execute(select(Subscription).where(
            Subscription.razorpay_order_id == razorpay_order_id))).scalars().first()
        if existing:
            return existing
    plan = LEGACY[plan_name]
    current = await active_subscription(bot_id, db)
    start_base = naive(current.end_date) if current else datetime.utcnow()
    if current:
        current.status = "renewed"
    sub = Subscription(user_id=user_id, bot_id=bot_id, plan_name=plan_name, credits_granted=1, price_paid=plan["price"],
                       start_date=datetime.utcnow(), end_date=start_base + timedelta(days=plan["days"]),
                       razorpay_order_id=razorpay_order_id, status="active", auto_renewal=False)
    db.add(sub)
    bot = await db.get(Bot, bot_id)
    if bot:
        bot.export_unlocked = True
        bot.is_active = True
    db.add(Transaction(user_id=user_id, bot_id=bot_id, amount=plan["price"], razorpay_order_id=razorpay_order_id,
                       razorpay_payment_id=razorpay_payment_id, status="success", plan_name=plan_name))
    await db.commit()
    logger.info(f"Bot {bot_id} on {plan_name} until {sub.end_date:%Y-%m-%d}")
    return sub
