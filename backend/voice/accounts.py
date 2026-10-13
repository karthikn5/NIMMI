"""
Which telephony account a number runs on: Nimmi's own (environment keys) or a customer's
own Twilio or Exotel account (bring your own number), and placing calls through it.

Every connected account gets its own webhook token, used in the URLs we give its provider.
The token tells us which account a webhook came from; Twilio requests are also signed with
that account's auth token, which we check.
"""
import json
import secrets as _secrets
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import secretbox
from backend.models import PhoneNumber, TelephonyAccount
from voice import exotel, twilio

NIMMI = "nimmi"  # scope for Nimmi's own account


def new_token() -> str:
    return _secrets.token_urlsafe(24)


def seal(data: dict) -> str:
    return secretbox.seal(json.dumps(data))


def twilio_creds(acc: TelephonyAccount) -> tuple[str, str]:
    return acc.account_sid, json.loads(secretbox.unseal(acc.secrets))["token"]


def exotel_creds(acc: TelephonyAccount) -> dict:
    s = json.loads(secretbox.unseal(acc.secrets))
    return {"sid": acc.account_sid, "key": s["api_key"], "token": s["api_token"],
            "subdomain": acc.subdomain or "api.exotel.com", "app_id": acc.app_id or ""}


async def by_hook(db: AsyncSession, provider: str, hook: str) -> Optional[TelephonyAccount | str]:
    """The account a webhook token belongs to: NIMMI for our own, the TelephonyAccount, or None if unknown."""
    own = twilio.ws_secret() if provider == "twilio" else exotel.ws_secret()
    if own and hook == own:
        return NIMMI
    if not hook or len(hook) < 20:
        return None
    return (await db.execute(select(TelephonyAccount).where(
        TelephonyAccount.webhook_token == hook, TelephonyAccount.provider == provider))).scalars().first()


async def account_of(db: AsyncSession, number: PhoneNumber) -> Optional[TelephonyAccount]:
    if not number.account_id:
        return None
    return (await db.execute(select(TelephonyAccount).where(TelephonyAccount.id == number.account_id))).scalars().first()


def usable(number: PhoneNumber, acc: Optional[TelephonyAccount]) -> bool:
    """Can we place calls from this number right now?"""
    if number.account_id:
        return acc is not None and (number.provider == "twilio" or bool(acc.app_id))
    return twilio.configured() if number.provider == "twilio" else exotel.configured()


async def dial(db: AsyncSession, number: PhoneNumber, to_e164: str, job_id: str, detect_voicemail: bool = False) -> str:
    """Place an outbound call from `number` through whichever account it belongs to. Returns the call ID."""
    acc = await account_of(db, number)
    if number.account_id and not acc:
        raise RuntimeError("This number's phone account was disconnected")
    if number.provider == "twilio":
        return await twilio.place_call(to_e164, number.e164, job_id, detect_voicemail=detect_voicemail,
                                       creds=twilio_creds(acc) if acc else None, hook=acc.webhook_token if acc else None)
    return await exotel.place_call(to_e164, number.e164, job_id,
                                   creds=exotel_creds(acc) if acc else None, hook=acc.webhook_token if acc else None)
