"""
Self-serve phone numbers: customers search Twilio's inventory and buy a number
inside Nimmi. The first month is charged from their Nimmi balance; the scheduler
renews monthly, pauses the number when the balance runs out, and releases it
after a grace period.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import balance
from auth import AuthContext, get_owned_bot, rate_limit, require_owner
from database import get_db
from backend.models import BalanceEntry, CallbackSettings, Campaign, PhoneNumber
from phone import display
from voice import catalog, twilio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["numbers"])


def _check_country(country: str, number_type: str) -> dict:
    spec = next((c for c in catalog.SELF_SERVE_COUNTRIES if c["code"] == country), None)
    if not spec or number_type not in spec["types"]:
        raise HTTPException(status_code=400, detail="That country or number type isn't available")
    if not twilio.configured():
        raise HTTPException(status_code=503, detail="Phone numbers aren't available on this server yet")
    return spec


async def _fee(country: str, number_type: str) -> int:
    try:
        usd = await twilio.monthly_price_usd(country, number_type)
    except twilio.TwilioError as e:
        logger.warning(f"Twilio pricing lookup failed: {e}")
        usd = None
    if not usd:
        raise HTTPException(status_code=502, detail="Couldn't get the price for this number. Try again.")
    return catalog.number_fee_inr(usd)


@router.get("/voice/numbers/countries")
async def countries():
    return {"countries": catalog.SELF_SERVE_COUNTRIES, "available": twilio.configured()}


@router.get("/voice/numbers/available")
async def available_numbers(country: str, type: str = "local", area_code: str = "", contains: str = "",
                            ctx: AuthContext = Depends(require_owner)):
    _check_country(country, type)
    rate_limit(f"numsearch:{ctx.owner_id}", 30, 60)
    try:
        numbers = await twilio.search_numbers(country, type, area_code.strip()[:6], contains.strip()[:10])
    except twilio.TwilioError as e:
        raise HTTPException(status_code=502, detail=f"Number search failed: {e}")
    fee = await _fee(country, type)
    return {"monthly_fee": fee, "numbers": [{**n, "display": display(n["phone_number"])} for n in numbers]}


class Address(BaseModel):
    customer_name: str = Field(..., max_length=100)
    street: str = Field(..., max_length=200)
    city: str = Field(..., max_length=100)
    region: str = Field("", max_length=100)
    postal_code: str = Field(..., max_length=20)


class BuyRequest(BaseModel):
    phone_number: str
    country: str
    type: str = "local"
    bot_id: Optional[str] = None
    address: Optional[Address] = None


@router.post("/voice/numbers/buy")
async def buy_number(req: BuyRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    _check_country(req.country, req.type)
    rate_limit(f"numbuy:{ctx.owner_id}", 5, 600)
    if req.bot_id:
        await get_owned_bot(req.bot_id, ctx, db)
    fee = await _fee(req.country, req.type)

    row = PhoneNumber(user_id=ctx.owner_id, number=display(req.phone_number), e164=req.phone_number, kind=req.type,
                      city=req.country, status="provisioning", provider="twilio", country=req.country,
                      monthly_fee=fee, bot_id=req.bot_id)
    db.add(row)
    await db.commit()

    try:
        await balance.charge(db, ctx.owner_id, fee * 100, "number_rental", f"rent:{row.id}:1",
                             f"{display(req.phone_number)} first month")
    except balance.InsufficientBalance as e:
        await db.delete(row)
        await db.commit()
        raise HTTPException(status_code=402, detail=f"{e}. Add money to your balance first.")

    try:
        address_sid = None
        if req.address:
            a = req.address
            address_sid = await twilio.create_address(a.customer_name, a.street, a.city, a.region, a.postal_code, req.country)
        row.provider_sid = await twilio.buy_number(req.phone_number, f"Nimmi {ctx.owner_id[:8]}", address_sid)
    except twilio.TwilioError as e:
        await balance.credit(db, ctx.owner_id, fee * 100, "refund", f"refund:{row.id}", "Number purchase failed")
        await db.delete(row)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Couldn't buy the number: {e}. You haven't been charged.")

    row.status = "active"
    row.next_charge_at = datetime.utcnow() + timedelta(days=30)
    await db.commit()
    from voice.router import _number_json
    return _number_json(row)


class ReplaceRequest(BaseModel):
    phone_number: str
    address: Optional[Address] = None


@router.post("/voice/numbers/{number_id}/replace")
async def replace_number(number_id: str, req: ReplaceRequest, ctx: AuthContext = Depends(require_owner),
                         db: AsyncSession = Depends(get_db)):
    """
    Swap a number bought here for a new one in the same country. The assistant, call-back and
    campaign settings move to the new number, and the month already paid carries over.
    Allowed once per billing period, since each swap costs a new number.
    """
    old = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.user_id == ctx.owner_id))).scalars().first()
    if not old:
        raise HTTPException(status_code=404, detail="Number not found")
    if old.account_id or old.provider != "twilio" or not old.provider_sid or old.status != "active":
        raise HTTPException(status_code=400, detail="Only active numbers bought in Nimmi can be swapped")
    if old.replaced_at and datetime.utcnow() - old.replaced_at.replace(tzinfo=None) < timedelta(days=30):
        raise HTTPException(status_code=400, detail="This number was swapped recently. You can swap it again next month.")
    if req.phone_number == old.e164:
        raise HTTPException(status_code=400, detail="Choose a different number")
    number_type = old.kind if old.kind in twilio.NUMBER_TYPES else "local"
    _check_country(old.country or "", number_type)
    rate_limit(f"numswap:{ctx.owner_id}", 3, 3600)
    fee = await _fee(old.country, number_type)

    try:
        address_sid = None
        if req.address:
            a = req.address
            address_sid = await twilio.create_address(a.customer_name, a.street, a.city, a.region, a.postal_code, old.country)
        new_sid = await twilio.buy_number(req.phone_number, f"Nimmi {ctx.owner_id[:8]}", address_sid)
    except twilio.TwilioError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't get the new number: {e}. Nothing has changed.")

    new = PhoneNumber(user_id=ctx.owner_id, number=display(req.phone_number), e164=req.phone_number, kind=old.kind,
                      city=old.city, status="active", provider="twilio", country=old.country, provider_sid=new_sid,
                      monthly_fee=fee, bot_id=old.bot_id, next_charge_at=old.next_charge_at, replaced_at=datetime.utcnow())
    db.add(new)
    await db.flush()
    # Everything that called from the old number now calls from the new one.
    await db.execute(update(CallbackSettings).where(CallbackSettings.from_number_id == old.id).values(from_number_id=new.id))
    await db.execute(update(Campaign).where(Campaign.from_number_id == old.id).values(from_number_id=new.id))
    old_sid, old_display = old.provider_sid, old.number
    await db.delete(old)
    await db.commit()
    try:
        await twilio.release_number(old_sid)
    except twilio.TwilioError as e:
        logger.error(f"Swapped {old_display} but couldn't release it on Twilio ({old_sid}): {e}")
    from voice.router import _number_json
    return _number_json(new)


# ─── Balance ──────────────────────────────────────────────────────
@router.get("/billing/balance")
async def get_balance(ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    row = await balance.get(db, ctx.owner_id)
    entries = (await db.execute(
        select(BalanceEntry).where(BalanceEntry.user_id == ctx.owner_id).order_by(BalanceEntry.created_at.desc()).limit(50)
    )).scalars().all()
    numbers = (await db.execute(select(PhoneNumber).where(
        PhoneNumber.user_id == ctx.owner_id, PhoneNumber.provider == "twilio", PhoneNumber.next_charge_at.isnot(None),
        PhoneNumber.status.in_(["active", "suspended"]),  # self-serve numbers billed from the balance
    ))).scalars().all()
    return {
        "balance": row.balance_paise / 100,
        "monthly_commitment": sum(n.monthly_fee or 0 for n in numbers),
        "topups": catalog.BALANCE_TOPUPS,
        "entries": [{"id": e.id, "amount": e.amount_paise / 100, "kind": e.kind, "note": e.note,
                     "created_at": e.created_at.isoformat() if e.created_at else None} for e in entries],
    }
