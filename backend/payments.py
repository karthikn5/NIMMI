import razorpay
import os
import hmac
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
from models import Bot
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

# Activation fee: 5000 paise = ₹50
ACTIVATION_AMOUNT = 5000


def get_razorpay_client():
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


@router.post("/create-order")
async def create_order(bot_id: str, db: AsyncSession = Depends(get_db)):
    """Creates a Razorpay order for bot export activation."""
    try:
        bot_uuid = uuid.UUID(bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        bot = result.scalars().first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        if bot.export_unlocked:
            return {"already_unlocked": True, "message": "Bot is already unlocked."}

        client = get_razorpay_client()
        order_data = {
            "amount": ACTIVATION_AMOUNT,
            "currency": "INR",
            "receipt": f"nimmi_bot_{bot_id[:8]}",
            "notes": {
                "bot_id": bot_id,
                "bot_name": bot.bot_name,
            },
        }
        order = client.order.create(data=order_data)
        logger.info(f"Razorpay order created: {order['id']} for bot {bot_id}")

        return {
            "order_id": order["id"],
            "amount": ACTIVATION_AMOUNT,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
            "bot_name": bot.bot_name,
            "bot_id": bot_id,
            "callback_url": f"{BACKEND_URL}/api/payments/verify",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Razorpay order creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """Verifies Razorpay payment signature and unlocks the bot."""
    try:
        body = await request.json()
        razorpay_order_id = body.get("razorpay_order_id")
        razorpay_payment_id = body.get("razorpay_payment_id")
        razorpay_signature = body.get("razorpay_signature")
        bot_id = body.get("bot_id")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, bot_id]):
            raise HTTPException(status_code=400, detail="Missing payment details")

        # Verify signature
        generated_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode("utf-8"),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if generated_signature != razorpay_signature:
            logger.warning(f"Invalid payment signature for bot {bot_id}")
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        # Unlock the bot
        bot_uuid = uuid.UUID(bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        bot = result.scalars().first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        bot.export_unlocked = True
        db.add(bot)
        await db.commit()
        logger.info(f"Bot {bot_id} export UNLOCKED. Payment: {razorpay_payment_id}")

        return {
            "success": True,
            "message": "Payment verified. Bot export unlocked!",
            "redirect_url": f"{DASHBOARD_URL}/dashboard/payment-success?bot_id={bot_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
