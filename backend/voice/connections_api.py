"""
Bring your own number: connect a Twilio or Exotel account the customer already has, then
use its numbers for the voice agent (incoming calls and outgoing call-backs and campaigns).

Twilio: we verify the keys, list the account's numbers and point the chosen ones at Nimmi
(remembering their old webhook so it can be put back). Exotel: we verify the keys; the
customer adds our voicebot URLs to a flow in their Exotel dashboard and tells us its ID.
"""
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import secretbox
from auth import AuthContext, get_owned_bot, rate_limit, require_owner
from database import get_db
from backend.models import PhoneNumber, TelephonyAccount
from phone import display, to_e164
from voice import accounts, exotel, twilio
import plans

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["phone accounts"])

EXOTEL_REGIONS = {"api.exotel.com": "Singapore (most accounts)", "api.in.exotel.com": "Mumbai"}
LIVE_STATUSES = ("active", "suspended", "provisioning", "pending_kyc")


def _mask(sid: str) -> str:
    return f"{sid[:6]}…{sid[-4:]}" if len(sid) > 12 else sid


async def _owned(db: AsyncSession, ctx: AuthContext, account_id: str) -> TelephonyAccount:
    acc = (await db.execute(select(TelephonyAccount).where(
        TelephonyAccount.id == account_id, TelephonyAccount.user_id == ctx.owner_id))).scalars().first()
    if not acc:
        raise HTTPException(status_code=404, detail="Phone account not found")
    return acc


async def _numbers_of(db: AsyncSession, acc: TelephonyAccount) -> list[PhoneNumber]:
    return list((await db.execute(select(PhoneNumber).where(PhoneNumber.account_id == acc.id))).scalars().all())


async def _account_json(db: AsyncSession, acc: TelephonyAccount) -> dict:
    data = {"id": acc.id, "provider": acc.provider, "label": acc.label or "", "account_sid": _mask(acc.account_sid),
            "numbers": len(await _numbers_of(db, acc)),
            "created_at": acc.created_at.isoformat() if acc.created_at else None}
    if acc.provider == "exotel":
        data.update({"subdomain": acc.subdomain, "app_id": acc.app_id or "", "setup": exotel.setup_urls(acc.webhook_token)})
    return data


async def _taken(db: AsyncSession, e164: str) -> bool:
    """A number can be connected once across Nimmi, so incoming calls always reach the right assistant."""
    return (await db.execute(select(PhoneNumber.id).where(
        PhoneNumber.e164 == e164, PhoneNumber.status.in_(LIVE_STATUSES)))).first() is not None


class ConnectRequest(BaseModel):
    provider: Literal["twilio", "exotel"]
    label: str = Field("", max_length=60)
    account_sid: str = Field(..., max_length=80)
    auth_token: str = Field("", max_length=200)  # Twilio
    api_key: str = Field("", max_length=200)  # Exotel
    api_token: str = Field("", max_length=200)
    subdomain: str = "api.exotel.com"
    app_id: str = Field("", max_length=20)


@router.get("/phone-accounts")
async def list_accounts(ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TelephonyAccount).where(TelephonyAccount.user_id == ctx.owner_id)
                             .order_by(TelephonyAccount.created_at))).scalars().all()
    return {"accounts": [await _account_json(db, a) for a in rows], "exotel_regions": EXOTEL_REGIONS,
            "ready": bool(twilio.public_base())}


@router.post("/phone-accounts")
async def connect_account(req: ConnectRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Check the keys with the provider, then save them encrypted. Connecting the same account again updates its keys."""
    await plans.require(db, ctx.owner_id, "voice")
    rate_limit(f"phoneacct:{ctx.owner_id}", 10, 600)
    if not twilio.public_base():
        raise HTTPException(status_code=503, detail="The server's public address (PUBLIC_BACKEND_URL) isn't set yet")
    sid = req.account_sid.strip()
    if req.provider == "twilio":
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", sid) or not req.auth_token.strip():
            raise HTTPException(status_code=400, detail="Enter the Account SID (starts with AC) and the auth token from your Twilio console")
        try:
            name = await twilio.verify_account((sid, req.auth_token.strip()))
        except twilio.TwilioError as e:
            raise HTTPException(status_code=400, detail=str(e))
        secrets_json, extra = {"token": req.auth_token.strip()}, {}
    else:
        if req.subdomain not in EXOTEL_REGIONS:
            raise HTTPException(status_code=400, detail="Choose your Exotel region")
        if not sid or not req.api_key.strip() or not req.api_token.strip():
            raise HTTPException(status_code=400, detail="Enter the account SID, API key and API token from Exotel's API settings")
        if req.app_id and not req.app_id.strip().isdigit():
            raise HTTPException(status_code=400, detail="The flow ID is the number in the flow's address in Exotel")
        creds = {"sid": sid, "key": req.api_key.strip(), "token": req.api_token.strip(), "subdomain": req.subdomain}
        try:
            await exotel.verify(creds)
        except exotel.ExotelError as e:
            raise HTTPException(status_code=400, detail=str(e))
        name = sid
        secrets_json, extra = {"api_key": creds["key"], "api_token": creds["token"]}, {"subdomain": req.subdomain, "app_id": req.app_id.strip()}

    try:
        sealed = accounts.seal(secrets_json)
    except secretbox.SecretError as e:
        raise HTTPException(status_code=503, detail=str(e))
    acc = (await db.execute(select(TelephonyAccount).where(
        TelephonyAccount.user_id == ctx.owner_id, TelephonyAccount.provider == req.provider,
        TelephonyAccount.account_sid == sid))).scalars().first()
    if acc:
        acc.secrets = sealed
        acc.label = req.label.strip() or acc.label
        for k, v in extra.items():
            if v or k == "subdomain":
                setattr(acc, k, v)
    else:
        acc = TelephonyAccount(user_id=ctx.owner_id, provider=req.provider, account_sid=sid, secrets=sealed,
                               label=req.label.strip() or name, webhook_token=accounts.new_token(), **extra)
        db.add(acc)
    await db.commit()
    return await _account_json(db, acc)


class AccountUpdate(BaseModel):
    label: str | None = Field(None, max_length=60)
    app_id: str | None = Field(None, max_length=20)


@router.patch("/phone-accounts/{account_id}")
async def update_account(account_id: str, req: AccountUpdate, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    acc = await _owned(db, ctx, account_id)
    if req.label is not None:
        acc.label = req.label.strip()
    if req.app_id is not None:
        if req.app_id.strip() and not req.app_id.strip().isdigit():
            raise HTTPException(status_code=400, detail="The flow ID is the number in the flow's address in Exotel")
        acc.app_id = req.app_id.strip()
    await db.commit()
    return await _account_json(db, acc)


@router.get("/phone-accounts/{account_id}/numbers")
async def account_numbers(account_id: str, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Twilio: the numbers on the account, and whether each is already connected."""
    acc = await _owned(db, ctx, account_id)
    if acc.provider != "twilio":
        return {"numbers": []}
    try:
        numbers = await twilio.list_numbers(accounts.twilio_creds(acc))
    except twilio.TwilioError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't list your Twilio numbers: {e}")
    mine = {n.e164 for n in await _numbers_of(db, acc)}
    out = []
    for n in numbers:
        e164 = n["phone_number"]
        out.append({"phone_number": e164, "display": display(e164), "name": n["friendly_name"], "country": n["country"],
                    "connected": e164 in mine, "in_use": e164 not in mine and await _taken(db, e164),
                    "has_other_webhook": bool(n["voice_url"]) and acc.webhook_token not in n["voice_url"]})
    return {"numbers": out}


class AddNumbers(BaseModel):
    phone_numbers: list[str] = Field(..., min_length=1, max_length=20)
    bot_id: str | None = None


@router.post("/phone-accounts/{account_id}/numbers")
async def add_numbers(account_id: str, req: AddNumbers, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Use these numbers in Nimmi. Twilio numbers are pointed at Nimmi automatically."""
    await plans.require(db, ctx.owner_id, "voice")
    acc = await _owned(db, ctx, account_id)
    if req.bot_id:
        await get_owned_bot(req.bot_id, ctx, db)
    wanted = []
    for raw in req.phone_numbers:
        e164 = to_e164(raw)
        if not e164:
            raise HTTPException(status_code=400, detail=f"{raw} isn't a valid phone number")
        if await _taken(db, e164):
            raise HTTPException(status_code=409, detail=f"{display(e164)} is already connected in Nimmi")
        wanted.append(e164)

    from voice.router import _number_json
    added = []
    if acc.provider == "twilio":
        creds = accounts.twilio_creds(acc)
        try:
            on_account = {n["phone_number"]: n for n in await twilio.list_numbers(creds)}
        except twilio.TwilioError as e:
            raise HTTPException(status_code=502, detail=f"Couldn't reach your Twilio account: {e}")
        for e164 in wanted:
            n = on_account.get(e164)
            if not n:
                raise HTTPException(status_code=400, detail=f"{display(e164)} isn't on this Twilio account")
            try:
                await twilio.set_voice_url(n["sid"], twilio.incoming_url(acc.webhook_token), creds)
            except twilio.TwilioError as e:
                raise HTTPException(status_code=502, detail=str(e))
            row = PhoneNumber(user_id=ctx.owner_id, number=display(e164), e164=e164, kind="local", city=n["country"],
                              country=n["country"] or None, status="active", provider="twilio", provider_sid=n["sid"],
                              monthly_fee=0, bot_id=req.bot_id, account_id=acc.id, previous_voice_url=n["voice_url"] or "")
            db.add(row)
            added.append(row)
    else:
        for e164 in wanted:
            row = PhoneNumber(user_id=ctx.owner_id, number=display(e164), e164=e164, kind="landline", city="",
                              country="IN" if e164.startswith("+91") else None, status="active", provider="exotel",
                              monthly_fee=0, bot_id=req.bot_id, account_id=acc.id)
            db.add(row)
            added.append(row)
    await db.commit()
    return {"numbers": [_number_json(r) for r in added]}


@router.delete("/phone-accounts/{account_id}")
async def disconnect_account(account_id: str, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Stop using this account: its numbers leave Nimmi (Twilio webhooks are put back) and the keys are deleted."""
    acc = await _owned(db, ctx, account_id)
    numbers = await _numbers_of(db, acc)
    if acc.provider == "twilio":
        try:
            creds = accounts.twilio_creds(acc)
        except secretbox.SecretError:
            creds = None
        for n in numbers:
            if creds and n.provider_sid:
                try:
                    await twilio.set_voice_url(n.provider_sid, n.previous_voice_url or "", creds)
                except Exception as e:
                    logger.warning(f"Couldn't restore the webhook for {n.number}: {e}")
    for n in numbers:
        await db.delete(n)
    await db.delete(acc)
    await db.commit()
    return {"status": "disconnected", "numbers_removed": len(numbers)}
