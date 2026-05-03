import razorpay
import os
import hmac
import hashlib
import json
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
from models import Bot, UserUsage, Subscription, Transaction
import uuid
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

PLAN_METADATA = {
    "1 Month Plan": {"price": 1, "days": 30},
    "6 Month Plan": {"price": 499, "days": 180},
    "12 Month Plan": {"price": 999, "days": 365},
}

PLANS = PLAN_METADATA # Compatibility alias


def get_razorpay_client():
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


class PlanPurchaseRequest(BaseModel):
    plan_name: str
    user_id: str
    bot_id: str


@router.post("/create-subscription-order")
async def create_order(request: PlanPurchaseRequest = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        plan_name = request.plan_name
        user_id = request.user_id
        bot_id = request.bot_id
        
        if plan_name not in PLANS:
            raise HTTPException(status_code=400, detail="Invalid plan name")
        
        plan = PLANS[plan_name]
        amount = plan["price"] * 100 # In paise
        
        client = get_razorpay_client()
        order_data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"nimmi_bot_{bot_id[:8]}",
            "notes": {
                "user_id": user_id,
                "bot_id": bot_id,
                "plan_name": plan_name,
            },
        }
        order = client.order.create(data=order_data)
        logger.info(f"Razorpay bot order created: {order['id']} for bot {bot_id}")

        return {
            "order_id": order["id"],
            "amount": amount,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
            "plan_name": plan_name,
            "user_id": user_id,
            "bot_id": bot_id
        }
    except Exception as e:
        logger.error(f"Razorpay order creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_payment(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        body = await request.json()
        razorpay_order_id = body.get("razorpay_order_id")
        razorpay_payment_id = body.get("razorpay_payment_id")
        razorpay_signature = body.get("razorpay_signature")
        user_id = body.get("user_id")
        bot_id = body.get("bot_id")
        plan_name = body.get("plan_name")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, user_id, bot_id, plan_name]):
            raise HTTPException(status_code=400, detail="Missing payment details")

        # Verify signature
        generated_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode("utf-8"),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if generated_signature != razorpay_signature:
            logger.warning(f"Invalid signature for user {user_id}")
            raise HTTPException(status_code=400, detail="Invalid signature")

        plan = PLANS[plan_name]
        
        # 🟢 BOT-BASED SUBSCRIPTION LOGIC 🟢
        # Check for existing active subscription for this SPECIFIC BOT
        result = await db.execute(
            select(Subscription).where(
                Subscription.bot_id == bot_id,
                Subscription.status == "active",
                Subscription.end_date > datetime.utcnow()
            ).order_by(Subscription.end_date.desc())
        )
        existing_sub = result.scalars().first()

        # Calculation: Remaining Days Must Be Added (Extension Logic)
        start_base = datetime.utcnow()
        if existing_sub:
            start_base = existing_sub.end_date # Add to the end of existing plan
            existing_sub.status = "renewed" # Mark old one as replaced by extension

        new_end_date = start_base + timedelta(days=plan["days"])

        # Create/Update Subscription
        subscription = Subscription(
            user_id=user_id,
            bot_id=bot_id,
            plan_name=plan_name,
            credits_granted=1,
            price_paid=plan["price"],
            start_date=datetime.utcnow(),
            end_date=new_end_date,
            razorpay_order_id=razorpay_order_id,
            status="active"
        )
        db.add(subscription)
        
        # Update the Bot itself
        bot_result = await db.execute(select(Bot).where(Bot.bot_id == bot_id))
        bot = bot_result.scalars().first()
        if bot:
            bot.export_unlocked = True
            bot.is_active = True
        
        # Record transaction
        new_transaction = Transaction(
            user_id=user_id,
            bot_id=bot_id,
            amount=plan["price"],
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            status="success"
        )
        db.add(new_transaction)
        
        await db.commit()
        logger.info(f"Bot {bot_id} upgraded to {plan_name}. Expiry: {new_end_date}")

        return {
            "success": True,
            "message": f"Bot activated until {new_end_date.strftime('%b %d, %Y')}",
            "redirect_url": f"{DASHBOARD_URL}/dashboard/billing",
        }

    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions")
async def get_bot_subscriptions(user_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves all bot subscriptions for a user."""
    try:
        result = await db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
            .order_by(Subscription.end_date.desc())
        )
        subs = result.scalars().all()
        
        return [{
            "bot_id": s.bot_id,
            "plan_name": s.plan_name,
            "status": "active" if s.end_date > datetime.utcnow() else "expired",
            "end_date": s.end_date.isoformat(),
            "days_remaining": (s.end_date - datetime.utcnow()).days
        } for s in subs]
    except Exception as e:
        logger.error(f"Subscription fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_payment_history(user_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves the user's payment history."""
    try:
        result = await db.execute(
            select(Transaction).where(Transaction.user_id == user_id, Transaction.status == "success")
            .order_by(Transaction.created_at.desc())
        )
        transactions = result.scalars().all()
        
        history = []
        for tx in transactions:
            # Map amount to plan name
            plan_name = "Custom Payment"
            for name, meta in PLAN_METADATA.items():
                if tx.amount == meta["price"]:
                    plan_name = name
                    break
            
            history.append({
                "plan_name": plan_name,
                "amount": tx.amount,
                "date": tx.created_at.strftime("%b %d, %Y, %I:%M %p"),
                "status": tx.status,
                "bot_id": tx.bot_id,
                "transaction_id": tx.razorpay_payment_id or tx.id[:12]
            })
            
        return history
    except Exception as e:
        logger.error(f"History fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle-auto-renew")
async def toggle_auto_renew(user_id: str, enabled: bool, db: AsyncSession = Depends(get_db)):
    """Toggles auto-renewal for the active subscription."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.status == "active")
        .order_by(Subscription.start_date.desc())
    )
    subscription = result.scalars().first()
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    subscription.auto_renewal = enabled
    await db.commit()
    return {"success": True, "auto_renewal": enabled}


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handles Razorpay webhooks for additional reliability."""
    payload = await request.body()
    webhook_signature = request.headers.get("x-razorpay-signature", "")

    if RAZORPAY_WEBHOOK_SECRET:
        generated = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if generated != webhook_signature:
            logger.warning("Invalid webhook signature")
            return JSONResponse(status_code=400, content={"message": "Invalid signature"})

    try:
        event = json.loads(payload)
        event_type = event.get("event")

        if event_type == "payment.captured":
            payment = event["payload"]["payment"]["entity"]
            order_id = payment.get("order_id")

            # Get order notes to find bot_id
            client = get_razorpay_client()
            order = client.order.fetch(order_id)
            bot_id = order.get("notes", {}).get("bot_id")

            if bot_id:
                try:
                    bot_uuid = uuid.UUID(bot_id)
                    result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
                    bot = result.scalars().first()
                    if bot and not bot.export_unlocked:
                        bot.export_unlocked = True
                        db.add(bot)
                        await db.commit()
                        logger.info(f"Webhook: Bot {bot_id} export UNLOCKED.")
                except Exception as e:
                    logger.error(f"Webhook bot unlock error: {str(e)}")

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")

    return JSONResponse(status_code=200, content={"status": "ok"})
