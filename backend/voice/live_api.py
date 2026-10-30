"""
Live calls for the dashboard (LIVE_CALLS_PLAN.md): the calls going on right now, callers waiting for a person, and
picking one up.

  GET  /api/voice/live                         live calls and open requests; also checks the person in as present
  POST /api/voice/live/presence                "Available for calls" on or off, and the phone "Call my phone" rings
  POST /api/voice/live/handoffs/{id}/accept    take the call: in the browser (Twilio) or on their phone
  POST /api/voice/live/handoffs/{id}/decline   let the assistant handle it (when everyone available has, it gives up)
  POST /api/voice/live/token                   a Voice SDK token for the browser, on the call's own Twilio account

Every role in a workspace (owner, admin, agent) sees its live calls and may pick them up. The first to accept gets the
call. The call itself (voice/pipeline.py) notices within a second and hands over (voice/handoff.py).
"""
import json
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import secretbox
from auth import AuthContext, get_ctx
from backend.models import CallHandoff, CallLog, PhoneNumber, TwilioKey
from database import get_db
from notify.events import fire_and_forget
from phone import mask, to_e164
from voice import accounts, handoff, twilio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice/live", tags=["voice-live"])

LIVE_SEC = 20  # a call that said it's alive this recently is live
LINES = 6      # the last lines of the conversation a request shows


def _lines(transcript: Optional[list], n: int) -> list[dict]:
    said = [{"speaker": t.get("speaker"), "text": t.get("text")} for t in transcript or []
            if t.get("speaker") in ("caller", "agent")]
    return said[-n:]


def _caller(call: Optional[CallLog], row: Optional[CallHandoff] = None) -> dict:
    channel = call.channel if call is not None else ("browser" if row and row.provider == "browser" else "phone")
    e164 = (call.caller_e164 if call is not None else None) or (row.caller if row else None)
    name = (row.caller_name if row else None) or ((call.captured or {}).get("Name") if call is not None else None)
    return {"caller": "Browser test" if channel == "browser" else mask(e164), "caller_name": name or None,
            "test": channel == "browser"}


async def _names(db: AsyncSession, owner_id: str) -> dict:
    from voice.router import _bot_names
    return await _bot_names(owner_id, db)


async def _item(db: AsyncSession, row: CallHandoff, call: Optional[CallLog], bots: dict, user_id: str) -> dict:
    now = handoff.now()
    return {
        "id": row.id, "call_id": row.call_id, **_caller(call, row), "bot_name": bots.get(row.bot_id, "Assistant"),
        "reason": row.reason or "", "status": row.status,
        "waited_sec": int((now - handoff.aware(row.created_at)).total_seconds()),
        "left_sec": max(0, int((handoff.aware(row.expires_at) - now).total_seconds())) if row.expires_at else 0,
        "browser": row.provider == "twilio", "phone": row.provider in ("twilio", "exotel"),
        "lines": _lines(call.transcript if call is not None else None, LINES),
        "mine": row.accepted_by == user_id,
    }


@router.get("")
async def live(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The workspace's live calls and the callers waiting for a person. Asking also says this person is here."""
    me = await handoff.check_in(db, ctx.owner_id, ctx.user_id)
    now = handoff.now()
    calls = (await db.execute(select(CallLog).where(
        CallLog.user_id == ctx.owner_id, CallLog.outcome == "in_progress",
        or_(CallLog.live_at >= now - timedelta(seconds=LIVE_SEC),
            and_(CallLog.live_at.is_(None), CallLog.started_at >= now - timedelta(seconds=LIVE_SEC))))
        .order_by(CallLog.started_at.desc()).limit(50))).scalars().all()
    rows = (await db.execute(select(CallHandoff).where(
        CallHandoff.owner_id == ctx.owner_id, CallHandoff.status.in_(("ringing", "accepted", "connecting", "connected")),
        CallHandoff.created_at >= now - timedelta(hours=4)).order_by(CallHandoff.created_at.desc()))).scalars().all()
    by_call = {}
    for row in rows:
        by_call.setdefault(row.call_id, row)  # the newest per call
    # A call handed to a person is still live after the assistant's part ended.
    handed = [r.call_id for r in by_call.values() if r.status == "connected" and r.call_id not in {c.id for c in calls}]
    if handed:
        calls = [*calls, *(await db.execute(select(CallLog).where(CallLog.id.in_(handed)))).scalars().all()]
    bots = await _names(db, ctx.owner_id)
    out = []
    for call in calls:
        row = by_call.get(call.id)
        state = "assistant"
        person = None
        if row is not None:
            state = {"ringing": "waiting", "accepted": "connecting", "connecting": "connecting", "connected": "person"}[row.status]
            person = await handoff.name_of(db, row.accepted_by) if row.accepted_by else (row.target if row.via == "transfer" else None)
        started = handoff.aware(call.started_at)
        out.append({
            "id": call.id, **_caller(call, row), "bot_name": bots.get(call.bot_id, "Assistant"), "direction": call.direction,
            "started_at": started.isoformat() if started else None,
            "seconds": int((now - started).total_seconds()) if started else 0,
            "state": state, "person": person, "handoff_id": row.id if row is not None else None,
            "lines": _lines(call.transcript, 3),
        })
    calls_by_id = {c.id: c for c in calls}
    requests = []
    for row in by_call.values():
        if row.status != "ringing" or handoff.aware(row.expires_at) <= now or ctx.user_id in (row.declined_by or []):
            continue
        call = calls_by_id.get(row.call_id) or (await db.get(CallLog, row.call_id) if row.call_id else None)
        requests.append(await _item(db, row, call, bots, ctx.user_id))
    return {"calls": out, "requests": requests, "me": {"available": me.available is not False, "phone": me.phone or ""}}


class PresenceIn(BaseModel):
    available: Optional[bool] = None
    phone: Optional[str] = Field(None, max_length=30)


@router.post("/presence")
async def presence(body: PresenceIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    phone = None
    if body.phone is not None:
        phone = to_e164(body.phone) if body.phone.strip() else ""
        if phone is None:
            raise HTTPException(status_code=400, detail="Enter a valid phone number")
    me = await handoff.check_in(db, ctx.owner_id, ctx.user_id, available_now=body.available, phone=phone)
    return {"available": me.available is not False, "phone": me.phone or ""}


async def _own(db: AsyncSession, handoff_id: str, ctx: AuthContext) -> CallHandoff:
    row = await db.get(CallHandoff, (handoff_id or "")[:36])
    if row is None or row.owner_id != ctx.owner_id or ctx.user_id not in await handoff.members(db, ctx.owner_id):
        raise HTTPException(status_code=404, detail="Not found")
    return row


class AcceptIn(BaseModel):
    via: str = "browser"  # browser, phone
    phone: Optional[str] = Field(None, max_length=30)


@router.post("/handoffs/{handoff_id}/accept")
async def accept(handoff_id: str, body: AcceptIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    row = await _own(db, handoff_id, ctx)
    if body.via == "browser":
        if row.provider not in ("twilio", "browser"):
            raise HTTPException(status_code=400, detail="This call came in on Exotel: pick it up on your phone.")
        target = handoff.identity(ctx.user_id)
    elif body.via == "phone":
        me = await handoff.check_in(db, ctx.owner_id, ctx.user_id)
        target = to_e164(body.phone) if body.phone else me.phone
        if not target:
            raise HTTPException(status_code=400, detail="Enter the phone number to ring you on")
        if body.phone:
            await handoff.check_in(db, ctx.owner_id, ctx.user_id, phone=target)
    else:
        raise HTTPException(status_code=400, detail="Pick it up in the browser or on your phone")
    if not await handoff.accept(db, row.id, ctx.user_id, body.via, target):
        await db.refresh(row)
        if row.accepted_by and row.accepted_by != ctx.user_id:
            raise HTTPException(status_code=409, detail=f"{await handoff.name_of(db, row.accepted_by)} already picked it up.")
        raise HTTPException(status_code=409, detail="The caller isn't waiting any more.")
    fire_and_forget(handoff.announce(ctx.owner_id, row.id, "accepted"))
    return {"status": "accepted", "via": body.via}


@router.post("/handoffs/{handoff_id}/decline")
async def decline(handoff_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Let the assistant handle it. When everyone available has, the call stops waiting (the assistant takes over)."""
    row = await _own(db, handoff_id, ctx)
    if row.status != "ringing":
        return {"status": row.status}
    row.declined_by = sorted({*(row.declined_by or []), ctx.user_id})
    present = {p.user_id for p in await handoff.available(db, ctx.owner_id)}
    if present <= set(row.declined_by):
        row.expires_at = handoff.now()  # nobody left to ask: the call's watcher falls back now
    await db.commit()
    fire_and_forget(handoff.announce(ctx.owner_id, row.id, "declined"))
    return {"status": "declined"}


class TokenIn(BaseModel):
    handoff_id: str = Field(..., max_length=36)


async def _twilio_creds(db: AsyncSession, call: Optional[CallLog]) -> Optional[twilio.Creds]:
    """The Twilio account a call is on: a customer's connected one, else Nimmi's own (None)."""
    number = await db.get(PhoneNumber, call.number_id) if call is not None and call.number_id else None
    acc = await accounts.account_of(db, number) if number is not None else None
    return accounts.twilio_creds(acc) if acc is not None and acc.provider == "twilio" else None


async def key_for(db: AsyncSession, creds: Optional[twilio.Creds]) -> tuple[str, str, str]:
    """(account SID, key SID, key secret) to sign browser tokens with, made on the account the first time."""
    account_sid, _ = twilio._auth(creds)
    if not account_sid:
        raise HTTPException(status_code=503, detail="Twilio isn't set up on this server")
    row = await db.get(TwilioKey, account_sid)
    if row is None:
        try:
            key_sid, secret = await twilio.create_api_key(creds)
        except twilio.TwilioError as e:
            logger.error(f"Couldn't make a Twilio API key for browser pickup: {e}")
            raise HTTPException(status_code=502, detail="Twilio didn't allow picking up in the browser. Use Call my phone.")
        row = TwilioKey(account_sid=account_sid, key_sid=key_sid, secret=secretbox.seal(json.dumps({"secret": secret})))
        db.add(row)
        await db.commit()
    return account_sid, row.key_sid, json.loads(secretbox.unseal(row.secret))["secret"]


@router.post("/token")
async def token(body: TokenIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A short-lived token for this person's browser to take a call on the call's own Twilio account."""
    row = await _own(db, body.handoff_id, ctx)
    if row.provider != "twilio":
        raise HTTPException(status_code=400, detail="Picking up in the browser works on Twilio numbers. Use Call my phone.")
    call = await db.get(CallLog, row.call_id) if row.call_id else None
    account_sid, key_sid, secret = await key_for(db, await _twilio_creds(db, call))
    identity = handoff.identity(ctx.user_id)
    return {"token": twilio.access_token(account_sid, key_sid, secret, identity, ttl=3600), "identity": identity,
            "edge": ["singapore", "roaming"]}
