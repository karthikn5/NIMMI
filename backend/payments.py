"""
Razorpay payments for bot plans and voice minute packs.

The browser never decides what was bought: after the signature check, the
order's own notes (fetched from Razorpay) say which plan or pack it was, for
which workspace, and the amount must match. Each payment is applied once.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os

import razorpay
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx, get_owned_bot, require_manager, require_owner
from database import get_db
from backend.models import Subscription, Transaction
from subscriptions import PLANS, activate_plan
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


def _valid_signature(order_id: str, payment_id: str, signature: str) -> bool:
    _, secret = _keys()
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


async def _fetch_order(order_id: str) -> dict:
    client = get_razorpay_client()
    return await asyncio.to_thread(client.order.fetch, order_id)


class PlanPurchaseRequest(BaseModel):
    plan_name: str
    bot_id: str
    user_id: str | None = None  # ignored


class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class MinutesOrderRequest(BaseModel):
    pack_id: str


class BalanceOrderRequest(BaseModel):
    amount: int  # INR


@router.post("/create-subscription-order")
async def create_order(req: PlanPurchaseRequest = Body(...), ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    if req.plan_name not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan name")
    bot = await get_owned_bot(req.bot_id, ctx, db)
    amount = PLANS[req.plan_name]["price"] * 100
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": amount, "currency": "INR", "receipt": f"nimmi_bot_{bot.bot_id[:8]}",
        "notes": {"kind": "plan", "user_id": ctx.owner_id, "bot_id": bot.bot_id, "plan_name": req.plan_name},
    })
    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": _keys()[0],
            "plan_name": req.plan_name, "bot_id": bot.bot_id}


@router.post("/verify")
async def verify_payment(req: PaymentVerify, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    if not _valid_signature(req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment signature didn't match")
    order = await _fetch_order(req.razorpay_order_id)
    notes = order.get("notes") or {}
    if notes.get("user_id") != ctx.owner_id:
        raise HTTPException(status_code=403, detail="This payment belongs to another account")

    if notes.get("kind") == "voice_topup":
        topup = await credit_topup(db, req.razorpay_order_id, req.razorpay_payment_id)
        if not topup:
            raise HTTPException(status_code=404, detail="Top-up not found")
        return {"success": True, "message": f"Added {topup.minutes} voice minutes"}

    if notes.get("kind") == "balance_topup":
        rupees = int(order.get("amount") or 0) // 100
        await balance.credit(db, ctx.owner_id, rupees * 100, "topup", f"topup:{req.razorpay_order_id}", "Added via Razorpay")
        return {"success": True, "message": f"Added ₹{rupees} to your balance"}

    plan_name = notes.get("plan_name")
    if plan_name not in PLANS or order.get("amount") != PLANS[plan_name]["price"] * 100:
        raise HTTPException(status_code=400, detail="Order doesn't match a plan")
    sub = await activate_plan(db, user_id=ctx.owner_id, bot_id=notes.get("bot_id"), plan_name=plan_name,
                              razorpay_order_id=req.razorpay_order_id, razorpay_payment_id=req.razorpay_payment_id)
    dashboard = os.getenv("DASHBOARD_URL", "http://localhost:3000")
    return {"success": True, "message": f"Bot activated until {sub.end_date:%b %d, %Y}", "redirect_url": f"{dashboard}/dashboard/billing"}


@router.post("/create-minutes-order")
async def create_minutes_order(req: MinutesOrderRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    pack = PACKS_BY_ID.get(req.pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail="Unknown minute pack")
    amount = pack["price"] * 100
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": amount, "currency": "INR", "receipt": f"nimmi_voice_{req.pack_id}",
        "notes": {"kind": "voice_topup", "user_id": ctx.owner_id, "pack_id": req.pack_id},
    })
    db.add(VoiceTopup(user_id=ctx.owner_id, pack_id=req.pack_id, minutes=pack["minutes"],
                      amount=pack["price"], razorpay_order_id=order["id"]))
    await db.commit()
    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": _keys()[0],
            "minutes": pack["minutes"], "pack_id": req.pack_id}


@router.post("/create-balance-order")
async def create_balance_order(req: BalanceOrderRequest, ctx: AuthContext = Depends(require_owner)):
    if req.amount not in BALANCE_TOPUPS:
        raise HTTPException(status_code=400, detail="Choose one of the listed amounts")
    order = await asyncio.to_thread(get_razorpay_client().order.create, data={
        "amount": req.amount * 100, "currency": "INR", "receipt": f"nimmi_balance_{req.amount}",
        "notes": {"kind": "balance_topup", "user_id": ctx.owner_id},
    })
    return {"order_id": order["id"], "amount": req.amount * 100, "currency": "INR", "key_id": _keys()[0]}


@router.get("/subscriptions")
async def get_bot_subscriptions(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    from datetime import datetime
    subs = (await db.execute(
        select(Subscription).where(Subscription.user_id == ctx.owner_id).order_by(Subscription.end_date.desc())
    )).scalars().all()
    now = datetime.utcnow()
    return [{
        "bot_id": s.bot_id, "plan_name": s.plan_name,
        "status": "active" if s.status == "active" and s.end_date.replace(tzinfo=None) > now else "expired",
        "end_date": s.end_date.isoformat(), "days_remaining": (s.end_date.replace(tzinfo=None) - now).days,
        "auto_renewal": s.auto_renewal,
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
    history = []
    for tx in txs:
        plan_name = next((n for n, m in PLANS.items() if m["price"] == tx.amount), "Plan payment")
        history.append({"plan_name": plan_name, "amount": tx.amount, "date": tx.created_at.strftime("%b %d, %Y, %I:%M %p"),
                        "iso": tx.created_at.isoformat(), "status": tx.status, "bot_id": tx.bot_id,
                        "transaction_id": tx.razorpay_payment_id or tx.id[:12]})
    for t in topups:
        history.append({"plan_name": f"{t.minutes} voice minutes", "amount": t.amount,
                        "date": t.created_at.strftime("%b %d, %Y, %I:%M %p"), "iso": t.created_at.isoformat(),
                        "status": "success", "bot_id": None, "transaction_id": t.razorpay_payment_id or t.id[:12]})
    history.sort(key=lambda h: h["iso"], reverse=True)
    return history


@router.post("/toggle-auto-renew")
async def toggle_auto_renew(enabled: bool, bot_id: str | None = None, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    query = select(Subscription).where(Subscription.user_id == ctx.owner_id, Subscription.status == "active")
    if bot_id:
        query = query.where(Subscription.bot_id == bot_id)
    sub = (await db.execute(query.order_by(Subscription.start_date.desc()))).scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    sub.auto_renewal = enabled
    await db.commit()
    return {"success": True, "auto_renewal": enabled}


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Backup path: applies payments even if the browser closed before /verify."""
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
        if event.get("event") != "payment.captured":
            return {"status": "ok"}
        payment = event["payload"]["payment"]["entity"]
        order = await _fetch_order(payment["order_id"])
        notes = order.get("notes") or {}
        if notes.get("kind") == "voice_topup":
            await credit_topup(db, payment["order_id"], payment["id"])
        elif notes.get("kind") == "balance_topup" and notes.get("user_id"):
            await balance.credit(db, notes["user_id"], int(order.get("amount") or 0), "topup",
                                 f"topup:{payment['order_id']}", "Added via Razorpay")
        elif notes.get("plan_name") in PLANS and order.get("amount") == PLANS[notes["plan_name"]]["price"] * 100:
            await activate_plan(db, user_id=notes["user_id"], bot_id=notes["bot_id"], plan_name=notes["plan_name"],
                                razorpay_order_id=payment["order_id"], razorpay_payment_id=payment["id"])
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
    return {"status": "ok"}
