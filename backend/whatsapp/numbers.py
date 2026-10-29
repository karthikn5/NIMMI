"""
Connected WhatsApp numbers: finding the one a webhook is for, checking Meta's signature, and the assistant that answers.

Meta signs every webhook with the secret of the app the number is connected through: the business's own app for a
manual connection (its secret is kept on the number), Nimmi's app (WHATSAPP_APP_SECRET) for Embedded Signup. Each
number's part of a webhook is only trusted when it was signed with that number's secret, so one business's app can
never post messages as another's number.
"""
import hashlib
import hmac
import logging
import os
import secrets
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, IntegrationSettings, WhatsAppNumber
from database import async_session
from security import local_dev

logger = logging.getLogger(__name__)


def app_secret() -> str:
    return os.getenv("WHATSAPP_APP_SECRET", "")


def secret_for(number: WhatsAppNumber) -> str:
    """The secret Meta signs this number's webhooks with ("" if none is known)."""
    return (number.app_secret or "") if number.connection == "manual" and number.app_secret else app_secret()


def signed(raw: bytes, header: str, secret: str) -> bool:
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


def trusted(number: WhatsAppNumber, raw: bytes, header: str) -> bool:
    """Whether this number's messages in a webhook can be believed. Without any secret to check against, only on a
    developer's machine (anyone could post fake messages and make the number reply to them)."""
    secret = secret_for(number)
    return signed(raw, header, secret) if secret else local_dev()


def new_verify_token() -> str:
    return f"nimmi_wa_{secrets.token_hex(10)}"


async def by_phone_number_id(db: AsyncSession, phone_number_id: str) -> Optional[WhatsAppNumber]:
    if not phone_number_id:
        return None
    return (await db.execute(select(WhatsAppNumber).where(
        WhatsAppNumber.phone_number_id == phone_number_id, WhatsAppNumber.status != "disconnected"))).scalars().first()


async def assistant(db: AsyncSession, number: WhatsAppNumber) -> Optional[Bot]:
    """The assistant that answers this number: the one chosen, else the workspace's first active one."""
    if number.bot_id:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == number.bot_id, Bot.user_id == number.user_id))).scalars().first()
        if bot:
            return bot
    return (await db.execute(select(Bot).where(Bot.user_id == number.user_id, Bot.is_active.is_(True))
                             .order_by(Bot.created_at))).scalars().first()


async def workspace_number(db: AsyncSession, owner_id: str) -> Optional[WhatsAppNumber]:
    """The workspace's first connected number (for messages it sends on its own, e.g. after a call)."""
    return (await db.execute(select(WhatsAppNumber).where(
        WhatsAppNumber.user_id == owner_id, WhatsAppNumber.status != "disconnected")
        .order_by(WhatsAppNumber.created_at))).scalars().first()


async def move_old_settings() -> None:
    """Numbers connected on the old Integrations page become WhatsApp numbers (once; safe on every start)."""
    try:
        async with async_session() as db:
            rows = (await db.execute(select(IntegrationSettings).where(
                IntegrationSettings.whatsapp_phone_number_id.isnot(None),
                IntegrationSettings.whatsapp_phone_number_id != ""))).scalars().all()
            moved = 0
            for s in rows:
                pid = s.whatsapp_phone_number_id.strip()
                if (await db.execute(select(WhatsAppNumber.id).where(WhatsAppNumber.phone_number_id == pid))).first():
                    continue
                db.add(WhatsAppNumber(
                    user_id=s.user_id, bot_id=s.whatsapp_bot_id, phone_number_id=pid,
                    waba_id=s.whatsapp_business_account_id, access_token=s.whatsapp_access_token,
                    verify_token=s.whatsapp_verify_token or new_verify_token(), connection="manual",
                    ai_enabled=bool(s.whatsapp_chat_enabled), settings={}, status="connected"))
                moved += 1
            if moved:
                await db.commit()
                logger.info(f"Moved {moved} WhatsApp number(s) from the old Integrations settings")
    except Exception as e:
        logger.warning(f"Moving old WhatsApp settings failed: {e}")
