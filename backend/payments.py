"""
Razorpay payments: assistant plans (BILLING_PLAN.md), voice credit packs and the Nimmi balance.

The browser never decides what was bought: after the signature check, the order's or subscription's own notes
(fetched from Razorpay, written by checkout) say what it was, for which workspace, and the amount must match. Each
payment is applied once. A monthly plan is a Razorpay subscription that renews by itself; a yearly plan, or a monthly
one when the account can't make subscriptions, is a single order. Razorpay's webhook is the backup for a browser that
closed before the check, and the only news of renewals and failed charges.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx, get_owned_bot, require_manager, require_owner
from database import async_session, get_db
from backend.models import BillingPlan, Bot, Subscription, Transaction, User
from subscriptions import (LEGACY, PERIODS, PLANS, SUBSCRIPTION_CYCLES, TIERS, activate_plan, apply_purchase, day, label,
                           naive, plan_purchase, plans_of, price, renewal_charged, sync_subscription)
import balance
from voice.catalog import BALANCE_TOPUPS, PACKS_BY_ID
from voice.metering import credit_topup
from backend.models import VoiceTopup

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])

PLAN_METADATA = PLANS  # kept for older imports


def _keys():
    return os.getenv("RAZORPAY_KEY_ID", ""), os.getenv("RAZORPAY_KEY_SECRET", "")


def get_razorpay_client():
    key_id, secret = _keys()
    if not key_id or not secret:
        raise HTTPException(status_code=503, detail="Payments aren't configured on the server")
    return razorpay.Client(auth=(key_id, secret))


def subscriptions_on() -> bool:
    """Monthly plans renew through Razorpay subscriptions (RAZORPAY_SUBSCRIPTIONS=off: paid a month at a time)."""
    return os.getenv("RAZORPAY_SUBSCRIPTIONS", "on").lower() != "off"


def _hmac(message: str) -> str:
    return hmac.new(_keys()[1].encode(), message.encode(), hashlib.sha256).hexdigest()


def _valid_signature(order_id: str, payment_id: str, signature: str) -> bool:
    return hmac.compare_digest(_hmac(f"{order_id}|{payment_id}"), signature or "")


def _valid_subscription_signature(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Razorpay signs a subscription's payment as payment id, then subscription id (the reverse of orders)."""
    return hmac.compare_digest(_hmac(f"{payment_id}|{subscription_id}"), signature or "")


async def _fetch_order(order_id: str) -> dict:
    client = get_razorpay_client()
    return await asyncio.to_thread(client.order.fetch, order_id)


async def _fetch_subscription(subscription_id: str) -> dict:
    client = get_razorpay_client()
    return await asyncio.to_thread(client.subscription.fetch, subscription_id)


def _notes(entity: dict) -> dict:
    notes = entity.get("notes") or {}
    return notes if isinstance(notes, dict) else {}  # Razorpay sends [] when there are none


class PlanChoice(BaseModel):
    bot_id: str
    tier: str
    period: str


class BotRequest(BaseModel):
    bot_id: str


class PaymentVerify(BaseModel):
    razorpay_payment_id: str
    razorpay_signature: str
    razorpay_order_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None


class MinutesOrderRequest(BaseModel):
    pack_id: str


class BalanceOrderRequest(BaseModel):
    amount: int  # INR


# ─── plans ────────────────────────────────────────────────────────
def _plan_json(s: Optional[Subscription]) -> Optional[dict]:
    if s is None:
        return None
    renews = bool(s.auto_renewal and s.razorpay_subscription_id and s.rzp_status not in ("cancelled", "completed", "halted"))
    state = ("payment_failed" if s.rzp_status == "pending" else "halted" if s.rzp_status == "halted" else
             "renews" if renews else "ends")
    return {"id": s.id, "label": label(s.tier, s.period, s.plan_name), "tier": s.tier, "period": s.period,
            "earlier": s.tier is None, "price": s.price_paid, "starts": naive(s.start_date).isoformat() if s.start_date else None,
            "ends": naive(s.end_date).isoformat(), "renews": renews, "state": state}


def catalog() -> dict:
    return {"tiers": [{"id": t, "name": v["name"], "monthly": price(t, "monthly"), "yearly": price(t, "yearly")}
                      for t, v in TIERS.items()],
            "yearly_pays_for": PERIODS["yearly"]["pays_for"], "subscriptions": subscriptions_on()}


@router.get("/plans")
async def plans_overview(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Each assistant's plan now, and the one set to follow it; and what's on sale."""
    bots = (await db.execute(select(Bot).where(Bot.user_id == ctx.owner_id).order_by(Bot.created_at))).scalars().all()
    out = []
    for bot in bots:
        if getattr(bot, "deleted_at", None) is not None:
            continue
        current, later = await plans_of(bot.bot_id, db)
        out.append({"bot_id": bot.bot_id, "name": bot.bot_name, "current": _plan_json(current), "next": _plan_json(later)})
    return {"assistants": out, "catalog": catalog()}


async def _purchase_for(req: PlanChoice, ctx: AuthContext, db: AsyncSession, subscriptions: bool):
    bot = await get_owned_bot(req.bot_id, ctx, db)
    current, later = await plans_of(bot.bot_id, db)
    try:
        return bot, plan_purchase(current, later, req.tier, req.period, subscriptions=subscriptions)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/quote")
async def quote(req: PlanChoice, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What choosing a plan would do now, before paying: shown to the person to confirm."""
    _, p = await _purchase_for(req, ctx, db, subscriptions_on())
    return {"action": p.action, "label": label(p.tier, p.period), "pay_now": p.pay_now, "starts_at": p.starts_at.isoformat(),
            "ends_at": p.ends_at.isoformat(), "renews": p.renews, "note": p.note}


async def _razorpay_plan(db: AsyncSession, tier: str, period: str) -> str:
    """The Razorpay plan for one of ours at today's price, made the first time (Razorpay plans can't change)."""
    key = f"{tier}:{period}:{price(tier, period)}"
    row = await db.get(BillingPlan, key)
    if row is not None:
        return row.razorpay_plan_id
    plan = await asyncio.to_thread(get_razorpay_client().plan.create, {
        "period": period, "interval": 1, "notes": {"tier": tier, "period": period},
        "item": {"name": f"Nimmi AI {label(tier, period)}", "amount": price(tier, period) * 100, "currency": "INR",
                 "description": "Per assistant"}})
    db.add(BillingPlan(key=key, razorpay_plan_id=plan["id"]))
    try:
        await db.commit()
    except IntegrityError:  # another process made one at the same moment: use theirs
        await db.rollback()
        return (await db.get(BillingPlan, key)).razorpay_plan_id
    return plan["id"]


async def _subscription_for(db: AsyncSession, p, notes: dict) -> dict:
    data = {"plan_id": await _razorpay_plan(db, p.tier, p.period), "total_count": SUBSCRIPTION_CYCLES,
            "customer_notify": 1, "notes": notes}
    first_charge = p.ends_at if p.action == "upgrade" else p.starts_at
    if p.action in ("upgrade", "schedule") and first_charge > datetime.utcnow() + timedelta(minutes=5):
        data["start_at"] = int(first_charge.replace(tzinfo=timezone.utc).timestamp())
    if p.action == "upgrade":  # the difference for the days left, taken now
        data["addons"] = [{"item": {"name": "Upgrade, the days left", "amount": p.pay_now * 100, "currency": "INR"}}]
    return await asyncio.to_thread(get_razorpay_client().subscription.create, data)


@router.post("/checkout")
async def checkout(req: PlanChoice, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Start paying for a plan: a Razorpay subscription (monthly, renewing) or order (yearly) for Checkout to open."""
    bot, p = await _purchase_for(req, ctx, db, subscriptions_on())
    description = f"{label(p.tier, p.period)} for {bot.bot_name}"

    def notes_of(p, mode: str) -> dict:
        return {"kind": "plan", "mode": mode, "user_id": ctx.owner_id, "bot_id": bot.bot_id, "tier": p.tier,
                "period": p.period, "action": p.action, "replaces": p.replaces or "", "drops": p.drops or "",
                "pay_now": str(p.pay_now)}
    if p.renews:
        try:
            sub = await _subscription_for(db, p, notes_of(p, "subscription"))
            return {"mode": "subscription", "subscription_id": sub["id"], "key_id": _keys()[0], "pay_now": p.pay_now,
                    "description": description, "note": p.note}
        except HTTPException:
            raise  # payments aren't configured at all
        except Exception as e:
            # Subscriptions off for the account ("The requested URL was not found on the server"), or Razorpay refused
            # the plan or subscription: the customer can still pay, a month at a time.
            logger.error(f"Razorpay couldn't make a subscription for {bot.bot_id} ({e}); taking this month as a single payment")
            _, p = await _purchase_for(req, ctx, db, subscriptions=False)
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": p.pay_now * 100, "currency": "INR", "receipt": f"nimmi_{p.tier}_{bot.bot_id[:8]}", "notes": notes_of(p, "order")})
    return {"mode": "order", "order_id": order["id"], "amount": p.pay_now * 100, "currency": "INR", "key_id": _keys()[0],
            "pay_now": p.pay_now, "description": description, "note": p.note}


@router.post("/create-subscription-order", dependencies=[Depends(require_owner)])
async def create_order():
    """The 1/6/12 Month plans' checkout (a billing page left open from before the change)."""
    raise HTTPException(status_code=410, detail="Plans have changed. Reload the page to see them.")


async def stop_charging(db: AsyncSession, subscription_ids: list[str]) -> None:
    """Cancel Razorpay subscriptions at once: a plan replaced or followed by a newer one, a change dropped, renewal
    stopped. A cancel that fails stays marked `cancel_failed` and is tried again by `maintenance`."""
    for sub_id in dict.fromkeys(s for s in subscription_ids if s):
        try:
            await asyncio.to_thread(get_razorpay_client().subscription.cancel, sub_id, {"cancel_at_cycle_end": 0})
            done = True
        except razorpay.errors.BadRequestError as e:
            done = "cancel" in str(e).lower() or "completed" in str(e).lower() or "expired" in str(e).lower()
            if not done:
                logger.warning(f"Stopping Razorpay subscription {sub_id} failed: {e}")
        except Exception as e:
            done = False
            logger.warning(f"Stopping Razorpay subscription {sub_id} failed (will try again): {e}")
        if done:
            for row in (await db.execute(select(Subscription).where(Subscription.razorpay_subscription_id == sub_id))).scalars().all():
                row.rzp_status, row.auto_renewal = "cancelled", False
            await db.commit()


@router.post("/stop-renewal")
async def stop_renewal(req: BotRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """The plan stops renewing and ends at its date (a renewing plan set to start later is dropped)."""
    bot = await get_owned_bot(req.bot_id, ctx, db)
    current, later = await plans_of(bot.bot_id, db)
    renewing = [s for s in (current, later) if s is not None and s.auto_renewal and s.razorpay_subscription_id]
    if not renewing:
        raise HTTPException(status_code=404, detail="Nothing renews for this assistant.")
    for s in renewing:
        s.auto_renewal, s.rzp_status = False, "cancel_failed"
        if s is later:
            s.status = "cancelled"
    await db.commit()
    await stop_charging(db, [s.razorpay_subscription_id for s in renewing])
    ends = current.end_date if current is not None else later.start_date
    return {"success": True, "message": f"It won't renew. {bot.bot_name}'s plan ends on {day(ends)}."}


@router.post("/update-card")
async def update_card(req: BotRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Checkout for changing the card a renewing plan is charged to (after a failed charge)."""
    bot = await get_owned_bot(req.bot_id, ctx, db)
    current, _ = await plans_of(bot.bot_id, db)
    if current is None or not current.razorpay_subscription_id or current.rzp_status in ("cancelled", "completed"):
        raise HTTPException(status_code=404, detail="This assistant's plan doesn't renew by itself.")
    return {"subscription_id": current.razorpay_subscription_id, "key_id": _keys()[0],
            "description": f"Payment method for {label(current.tier, current.period, current.plan_name)}"}


def _done(plan: Subscription) -> str:
    name, now = label(plan.tier, plan.period, plan.plan_name), datetime.utcnow()
    if plan.start_date is not None and naive(plan.start_date) > now:
        return f"{name} starts on {day(plan.start_date)}."
    if plan.auto_renewal and plan.razorpay_subscription_id:
        return f"{name} is on. It renews by itself on {day(plan.end_date)}."
    return f"{name} is on until {day(plan.end_date)}."


@router.post("/verify")
async def verify_payment(req: PaymentVerify, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    if req.razorpay_subscription_id:
        if not _valid_subscription_signature(req.razorpay_payment_id, req.razorpay_subscription_id, req.razorpay_signature):
            raise HTTPException(status_code=400, detail="Payment signature didn't match")
        sub = await _fetch_subscription(req.razorpay_subscription_id)
        notes = _notes(sub)
        if notes.get("user_id") != ctx.owner_id:
            raise HTTPException(status_code=403, detail="This payment belongs to another account")
        if notes.get("kind") != "plan" or notes.get("tier") not in TIERS:
            raise HTTPException(status_code=400, detail="This subscription isn't a plan")
        applied = await apply_purchase(db, notes, payment_id=req.razorpay_payment_id, subscription=sub)
        await stop_charging(db, applied.stop)
        message = _done(applied.plan) if applied.new else "Payment method updated. Razorpay charges it from now on."
        return {"success": True, "message": message}

    if not req.razorpay_order_id or not _valid_signature(req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment signature didn't match")
    order = await _fetch_order(req.razorpay_order_id)
    notes = _notes(order)
    if notes.get("user_id") != ctx.owner_id:
        raise HTTPException(status_code=403, detail="This payment belongs to another account")

    if notes.get("kind") == "voice_topup":
        topup = await credit_topup(db, req.razorpay_order_id, req.razorpay_payment_id)
        if not topup:
            raise HTTPException(status_code=404, detail="Top-up not found")
        return {"success": True, "message": f"Added {topup.minutes:,} voice credits"}

    if notes.get("kind") == "balance_topup":
        rupees = int(order.get("amount") or 0) // 100
        await balance.credit(db, ctx.owner_id, rupees * 100, "topup", f"topup:{req.razorpay_order_id}", "Added via Razorpay")
        return {"success": True, "message": f"Added ₹{rupees} to your balance"}

    if notes.get("tier") in TIERS and notes.get("mode") == "order":
        if order.get("amount") != int(notes.get("pay_now") or 0) * 100:
            raise HTTPException(status_code=400, detail="Order doesn't match the plan")
        applied = await apply_purchase(db, notes, payment_id=req.razorpay_payment_id, order_id=req.razorpay_order_id)
        await stop_charging(db, applied.stop)
        return {"success": True, "message": _done(applied.plan)}

    plan_name = notes.get("plan_name")  # an earlier 1/6/12 Month plan
    if plan_name not in LEGACY or order.get("amount") != LEGACY[plan_name]["price"] * 100:
        raise HTTPException(status_code=400, detail="Order doesn't match a plan")
    sub = await activate_plan(db, user_id=ctx.owner_id, bot_id=notes.get("bot_id"), plan_name=plan_name,
                              razorpay_order_id=req.razorpay_order_id, razorpay_payment_id=req.razorpay_payment_id)
    return {"success": True, "message": f"Bot activated until {sub.end_date:%b %d, %Y}"}


# ─── voice credits and the Nimmi balance ──────────────────────────
@router.post("/create-minutes-order")  # the address from when packs were minutes
async def create_minutes_order(req: MinutesOrderRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    pack = PACKS_BY_ID.get(req.pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail="Unknown credit pack")
    amount = pack["price"] * 100
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": amount, "currency": "INR", "receipt": f"nimmi_voice_{req.pack_id}",
        "notes": {"kind": "voice_topup", "user_id": ctx.owner_id, "pack_id": req.pack_id},
    })
    db.add(VoiceTopup(user_id=ctx.owner_id, pack_id=req.pack_id, minutes=pack["credits"],
                      amount=pack["price"], razorpay_order_id=order["id"]))
    await db.commit()
    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": _keys()[0],
            "credits": pack["credits"], "pack_id": req.pack_id}


@router.post("/create-balance-order")
async def create_balance_order(req: BalanceOrderRequest, ctx: AuthContext = Depends(require_owner)):
    if req.amount not in BALANCE_TOPUPS:
        raise HTTPException(status_code=400, detail="Choose one of the listed amounts")
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": req.amount * 100, "currency": "INR", "receipt": f"nimmi_balance_{req.amount}",
        "notes": {"kind": "balance_topup", "user_id": ctx.owner_id},
    })
    return {"order_id": order["id"], "amount": req.amount * 100, "currency": "INR", "key_id": _keys()[0]}


# ─── lists ────────────────────────────────────────────────────────
@router.get("/subscriptions")
async def get_bot_subscriptions(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    subs = (await db.execute(
        select(Subscription).where(Subscription.user_id == ctx.owner_id, Subscription.status != "cancelled")
        .order_by(Subscription.end_date.desc())
    )).scalars().all()
    now = datetime.utcnow()
    return [{
        "bot_id": s.bot_id, "plan_name": label(s.tier, s.period, s.plan_name),
        "status": "active" if s.status == "active" and naive(s.end_date) > now else "expired",
        "end_date": s.end_date.isoformat(), "days_remaining": (naive(s.end_date) - now).days,
        "auto_renewal": bool(s.auto_renewal and s.razorpay_subscription_id),
    } for s in subs]


@router.get("/history")
async def get_payment_history(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    txs = (await db.execute(
        select(Transaction).where(Transaction.user_id == ctx.owner_id, Transaction.status == "success")
        .order_by(Transaction.created_at.desc())
    )).scalars().all()
    topups = (await db.execute(
        select(VoiceTopup).where(VoiceTopup.user_id == ctx.owner_id, VoiceTopup.status == "paid")
    )).scalars().all()
    # Payments from before plan names were kept: the plan is on its subscription (same order).
    bought = dict((await db.execute(select(Subscription.razorpay_order_id, Subscription.plan_name).where(
        Subscription.user_id == ctx.owner_id, Subscription.razorpay_order_id.is_not(None)))).all())
    history = []
    for tx in txs:
        plan_name = (tx.plan_name or bought.get(tx.razorpay_order_id)
                     or next((n for n, m in LEGACY.items() if m["price"] == tx.amount), "Plan payment"))
        history.append({"plan_name": plan_name, "amount": tx.amount, "date": tx.created_at.strftime("%b %d, %Y, %I:%M %p"),
                        "iso": tx.created_at.isoformat(), "status": tx.status, "bot_id": tx.bot_id,
                        "transaction_id": tx.razorpay_payment_id or tx.id[:12]})
    for t in topups:
        history.append({"plan_name": f"{t.minutes:,} voice credits", "amount": t.amount,
                        "date": t.created_at.strftime("%b %d, %Y, %I:%M %p"), "iso": t.created_at.isoformat(),
                        "status": "success", "bot_id": None, "transaction_id": t.razorpay_payment_id or t.id[:12]})
    history.sort(key=lambda h: h["iso"], reverse=True)
    return history


SELLER = {"name": "Nimmi AI", "website": "nimmiai.in", "email": os.getenv("BILLING_EMAIL", "support.nimmi@gmail.com")}


@router.get("/receipt/{payment_ref}")
async def receipt(payment_ref: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A receipt for one payment in the history (a plan, or call credits), by the ID the history shows. A receipt, not
    a tax invoice: the business isn't registered for GST yet."""
    ref = payment_ref.strip()[:64]

    def mine(model):
        return select(model).where(model.user_id == ctx.owner_id, model.razorpay_payment_id == ref)
    tx = (await db.execute(mine(Transaction).where(Transaction.status == "success"))).scalars().first()
    if tx is None and len(ref) == 12:  # a payment with no Razorpay ID shows the start of its own
        tx = (await db.execute(select(Transaction).where(Transaction.user_id == ctx.owner_id, Transaction.status == "success",
                                                         Transaction.id.startswith(ref)))).scalars().first()
    topup = None if tx is not None else (await db.execute(mine(VoiceTopup).where(VoiceTopup.status == "paid"))).scalars().first()
    if tx is None and topup is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    owner = await db.get(User, ctx.owner_id)
    if tx is not None:
        bot = await db.get(Bot, tx.bot_id) if tx.bot_id else None
        item = tx.plan_name or (await db.execute(select(Subscription.plan_name).where(
            Subscription.razorpay_order_id == tx.razorpay_order_id))).scalar() or "Plan payment"
        row_id, amount, paid_at, assistant = tx.id, tx.amount, tx.created_at, bot.bot_name if bot else None
    else:
        row_id, amount, paid_at, assistant = topup.id, topup.amount, topup.created_at, None
        item = f"{topup.minutes:,} call credits"
    local = naive(paid_at).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))  # India
    return {"number": f"NIM-{local:%Y%m%d}-{row_id[:6].upper()}", "date": naive(paid_at).isoformat(), "item": item,
            "assistant": assistant, "amount": amount, "currency": "INR", "payment_id": ref,
            "billed_to": {"name": (owner.name or "") if owner else "", "email": owner.email if owner else ""},
            "seller": SELLER}


# ─── Razorpay's webhook ───────────────────────────────────────────
@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Backup for payments whose browser closed before /verify, and the news of renewals and failed charges. A failure
    answers 500, so Razorpay sends it again (each event is applied once)."""
    payload = await request.body()
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not set; ignoring webhook")
        return JSONResponse(status_code=200, content={"status": "ignored"})
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-razorpay-signature", "")):
        return JSONResponse(status_code=400, content={"message": "Invalid signature"})
    try:
        event = json.loads(payload)
        name = event.get("event") or ""
        if name.startswith("subscription."):
            entity = event["payload"]["subscription"]["entity"]
            payment = ((event["payload"].get("payment") or {}).get("entity"))
            await subscription_event(db, name, entity, payment)
            return {"status": "ok"}
        if name != "payment.captured":
            return {"status": "ok"}
        payment = event["payload"]["payment"]["entity"]
        if not payment.get("order_id") or payment.get("invoice_id"):
            return {"status": "ok"}  # a subscription's own charge: its subscription.* event carries it
        order = await _fetch_order(payment["order_id"])
        notes = _notes(order)
        if notes.get("kind") == "voice_topup":
            await credit_topup(db, payment["order_id"], payment["id"])
        elif notes.get("kind") == "balance_topup" and notes.get("user_id"):
            await balance.credit(db, notes["user_id"], int(order.get("amount") or 0), "topup",
                                 f"topup:{payment['order_id']}", "Added via Razorpay")
        elif (notes.get("tier") in TIERS and notes.get("mode") == "order"
              and order.get("amount") == int(notes.get("pay_now") or 0) * 100):
            applied = await apply_purchase(db, notes, payment_id=payment["id"], order_id=payment["order_id"])
            await stop_charging(db, applied.stop)
        elif notes.get("plan_name") in LEGACY and order.get("amount") == LEGACY[notes["plan_name"]]["price"] * 100:
            await activate_plan(db, user_id=notes["user_id"], bot_id=notes["bot_id"], plan_name=notes["plan_name"],
                                razorpay_order_id=payment["order_id"], razorpay_payment_id=payment["id"])
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return JSONResponse(status_code=500, content={"status": "error"})
    return {"status": "ok"}


async def subscription_event(db: AsyncSession, name: str, entity: dict, payment: Optional[dict]) -> None:
    """A renewing plan's news from Razorpay (BILLING_PLAN.md section 2)."""
    notes = _notes(entity)
    if notes.get("kind") != "plan" or notes.get("tier") not in TIERS:
        return
    row = (await db.execute(select(Subscription).where(Subscription.razorpay_subscription_id == entity.get("id")))).scalars().first()
    if row is None and name in ("subscription.authenticated", "subscription.activated", "subscription.charged"):
        applied = await apply_purchase(db, notes, payment_id=(payment or {}).get("id"), subscription=entity)
        await stop_charging(db, applied.stop)
        row = applied.plan
    if row is None:
        return
    if name == "subscription.charged":
        await renewal_charged(db, entity, payment)
    elif name == "subscription.pending":
        row.rzp_status = "pending"
        await db.commit()
        await _tell_owner(row, "plan_payment_failed", f"{row.razorpay_subscription_id}@{entity.get('charge_at')}")
    elif name == "subscription.halted":
        row.rzp_status, row.auto_renewal = "halted", False
        await db.commit()
        await _tell_owner(row, "plan_renewal_halted", row.razorpay_subscription_id)
    elif name in ("subscription.cancelled", "subscription.completed"):
        row.rzp_status, row.auto_renewal = name.split(".")[1], False
        await db.commit()
    elif name in ("subscription.paused", "subscription.resumed", "subscription.activated"):
        row.rzp_status = "paused" if name.endswith("paused") else "active"
        await db.commit()


# ─── emails and upkeep ────────────────────────────────────────────
async def _tell_owner(plan: Subscription, kind: str, ref: str) -> None:
    """One email to the workspace owner about a plan, once per (kind, ref)."""
    from notify import email
    from notify.events import _once
    async with async_session() as db:
        owner = await db.get(User, plan.user_id)
        bot = await db.get(Bot, plan.bot_id) if plan.bot_id else None
    if owner is None or not owner.email:
        return
    name, assistant = label(plan.tier, plan.period, plan.plan_name), bot.bot_name if bot else "Your assistant"
    link = f"{email.dashboard_url()}/dashboard/billing?bot={plan.bot_id}"
    days_left = max(0, (naive(plan.end_date) - datetime.utcnow()).days)
    subject, text = {
        "plan_payment_failed": (f"Payment failed for {assistant}'s plan",
                                f"We couldn't take the payment for {assistant}'s {name} plan. Razorpay will try again "
                                f"over the next 3 days. To avoid a break, update your payment method:\n{link}"),
        "plan_renewal_halted": (f"{assistant}'s plan stopped renewing",
                                f"Renewing {assistant}'s {name} plan stopped after the payment failed. The plan ends on "
                                f"{day(plan.end_date)}, and then {assistant} stops answering. Renew it here:\n{link}"),
        "plan_ends_soon": (f"{assistant}'s plan ends {'tomorrow' if days_left <= 1 else f'in {days_left} days'}",
                           f"{assistant}'s {name} plan ends on {day(plan.end_date)}. After that, {assistant} stops "
                           f"answering on your website and other channels. Renew it here:\n{link}"),
        "plan_ended": (f"{assistant}'s plan has ended",
                       f"{assistant}'s {name} plan ended on {day(plan.end_date)}, so {assistant} isn't answering "
                       f"customers. Choose a plan to put it live again:\n{link}"),
    }[kind]

    async def send() -> Optional[str]:
        return None if await email.send_email(owner.email, subject, text) else "email not configured"
    await _once(plan.user_id, kind, ref, send)


REMIND_DAYS = (7, 3, 1)


async def maintenance() -> None:
    """Every few minutes, from the scheduler (every server process; each email goes once): renewing plans at their end
    checked with Razorpay (in case its webhook didn't come), reminders before a plan that doesn't renew by itself ends,
    the note once it has ended, and Razorpay subscriptions still to stop."""
    now = datetime.utcnow()
    async with async_session() as db:  # renewing plans at their end: Razorpay's own word on whether they renewed
        due = (await db.execute(select(Subscription.razorpay_subscription_id).where(
            Subscription.status == "active", Subscription.auto_renewal.is_(True), Subscription.razorpay_subscription_id.is_not(None),
            Subscription.end_date > now - timedelta(days=3), Subscription.end_date <= now + timedelta(hours=1)))).scalars().all()
    for sub_id in due:
        try:
            entity = await _fetch_subscription(sub_id)
        except Exception as e:
            logger.warning(f"Checking Razorpay subscription {sub_id} failed: {e}")
            continue
        async with async_session() as db:
            await sync_subscription(db, entity)
    async with async_session() as db:
        rows = (await db.execute(select(Subscription).where(
            Subscription.status == "active", Subscription.end_date > now - timedelta(days=1),
            Subscription.end_date <= now + timedelta(days=REMIND_DAYS[0])))).scalars().all()
        stuck = (await db.execute(select(Subscription.razorpay_subscription_id).where(
            Subscription.rzp_status == "cancel_failed"))).scalars().all()
    for plan in rows:
        if plan.auto_renewal and plan.razorpay_subscription_id and plan.rzp_status not in ("cancelled", "completed", "halted"):
            continue  # renews by itself
        async with async_session() as db:
            current, later = await plans_of(plan.bot_id, db)
        if later is not None or (current is not None and current.id != plan.id):
            continue  # another plan follows it, or already took over
        end = naive(plan.end_date)
        if end <= now:
            await _tell_owner(plan, "plan_ended", plan.id)
            continue
        days_left = (end - now).total_seconds() / 86400
        due = next((d for d in sorted(REMIND_DAYS) if days_left <= d), None)
        if due is not None:
            await _tell_owner(plan, "plan_ends_soon", f"{plan.id}@{due}")
    if stuck:
        async with async_session() as db:
            await stop_charging(db, list(stuck))
