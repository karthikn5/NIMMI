"""
Meta's webhook for WhatsApp: the one callback URL every connected number uses (WhatsApp > Settings shows it, with the
verify token). GET is Meta checking the URL; POST brings messages, delivery receipts and news about numbers.

A POST is answered only once what it brought is kept, so if something fails Meta sends it again (and repeats are
recognised by Meta's message id). Nothing slow happens before the answer: understanding files and writing replies
run afterwards (replies.py). Each number's part of a POST is trusted only if it was signed with that number's secret.
"""
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import IntegrationSettings, WhatsAppNumber
from database import async_session, get_db
from security import local_dev
from whatsapp import inbound, numbers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/whatsapp", tags=["whatsapp"])

NUMBER_FIELDS = ("phone_number_quality_update", "account_update", "phone_number_name_update", "business_capability_update")


@router.get("/webhook")
async def verify(hub_mode: Optional[str] = Query(None, alias="hub.mode"),
                 hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
                 hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
                 db: AsyncSession = Depends(get_db)):
    """Meta checks the callback URL: echo its challenge if the verify token is Nimmi's or a connected number's."""
    if hub_mode != "subscribe" or not hub_verify_token:
        return Response(content="Invalid verification request", status_code=400)
    if hub_verify_token == os.getenv("WHATSAPP_VERIFY_TOKEN", "nimmi_wa_verify"):
        return PlainTextResponse(content=str(hub_challenge), status_code=200)
    known = (await db.execute(select(WhatsAppNumber.id).where(WhatsAppNumber.verify_token == hub_verify_token))).first() or \
        (await db.execute(select(IntegrationSettings.user_id).where(
            IntegrationSettings.whatsapp_verify_token == hub_verify_token))).first()
    if known:
        return PlainTextResponse(content=str(hub_challenge), status_code=200)
    logger.warning("WhatsApp webhook verification with an unknown verify token")
    return Response(content="Verification token mismatch", status_code=403)


@router.post("/webhook")
async def receive(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw)
    except ValueError:
        return Response(content="Bad Request", status_code=400)
    if not isinstance(body, dict) or body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}
    header = request.headers.get("x-hub-signature-256", "")
    changes = [(change.get("field") or "messages", change.get("value") or {})
               for entry in body.get("entry") or [] for change in entry.get("changes") or []
               if isinstance(change, dict)]

    accepted, refused, found = [], 0, {}
    async with async_session() as db:
        for field, value in changes:
            pid = str((value.get("metadata") or {}).get("phone_number_id") or "")
            if pid not in found:
                found[pid] = await numbers.by_phone_number_id(db, pid)
            number = found[pid]
            if number is None:
                continue
            if numbers.trusted(number, raw, header):
                accepted.append((field, number, value))
            else:
                refused += 1
    if refused and not accepted:
        logger.warning("WhatsApp webhook refused: not signed with the number's app secret")
        return Response(content="Invalid signature", status_code=403)
    if not accepted:
        # Nothing for a connected number. A body Nimmi's own app didn't sign is still refused.
        if numbers.signed(raw, header, numbers.app_secret()) or (not numbers.app_secret() and local_dev()):
            return {"status": "ignored"}
        return Response(content="Invalid signature", status_code=403)

    try:
        for field, number, value in accepted:
            if field == "messages":
                for st in value.get("statuses") or []:
                    await inbound.status(number, st)
                for msg in value.get("messages") or []:
                    await inbound.message(number, msg, value.get("contacts") or [])
            elif field == "smb_message_echoes":
                for e in value.get("message_echoes") or []:
                    await inbound.echo(number, e)
            elif field in NUMBER_FIELDS:
                await inbound.number_update(number, field, value)
    except Exception as e:  # Meta sends it again; what was already kept isn't kept twice
        logger.exception(f"WhatsApp webhook couldn't be kept: {e}")
        return Response(content="Try again", status_code=500)
    return {"status": "ok"}
