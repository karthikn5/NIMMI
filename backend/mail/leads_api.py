"""
Leads > Sources (/api/email/leads) and the public links leads arrive at (/api/leads/in/<code>/...): IndiaMART's Push API, which
treats anything but a 200 as a failure and turns itself off after 48 hours of them; website forms; Google lead forms, which also send the key
only Google and the business know; and the connect link for Facebook and Instagram lead ads by Zapier, Make or Pabbly. The link's code is the
only thing that identifies an assistant, as IndiaMART has no signature.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, client_ip, rate_limit, require_manager
from backend.models import Bot, LeadIntake, LeadSource
from database import get_db
from mail import intake, setup, threads

router = APIRouter(tags=["email"])


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _base() -> str:
    return (os.getenv("PUBLIC_BACKEND_URL") or "").rstrip("/")


async def detail(db: AsyncSession, bot: Bot, ctx: AuthContext, make: bool = True) -> dict:
    """`make`: the assistant's addresses are made the first time someone opens the page; a read by Nimmi changes nothing."""
    source = await intake.source_for(db, ctx.owner_id, bot.bot_id) if make else await db.get(LeadSource, bot.bot_id)
    if make:
        await db.commit()
    rows = (await db.execute(select(LeadIntake).where(LeadIntake.bot_id == bot.bot_id).order_by(LeadIntake.created_at.desc()).limit(25))).scalars().all()
    prefs = await setup.settings_for(db, bot.bot_id)
    code = source.code if source else None
    return {"bot_id": bot.bot_id, "bot_name": bot.bot_name, "enabled": bool(source and source.enabled), "receiving": threads.enabled(),
            "address": intake.address(source) if source else None, "indiamart_url": f"{_base()}/api/leads/in/{code}/indiamart" if code else None,
            "form_url": f"{_base()}/api/leads/in/{code}/form" if code else None, "forwarding": source.forwarding if source else None,
            "google_url": f"{_base()}/api/leads/in/{code}/google" if code else None, "google_key": source.google_key if source else None,
            "connect_url": f"{_base()}/api/leads/in/{code}/connect" if code else None,
            "lead_email": prefs["lead_email"], "lead_call": prefs["lead_call"],
            "recent": [{"id": r.id, "channel": r.channel, "source": r.source, "status": r.status, "note": r.note, "subject": r.subject, "found": r.found or {},
                        "created_at": _iso(r.created_at), "test": bool(r.test)} for r in rows]}


async def _own_bot(bot_id: str, ctx: AuthContext, db: AsyncSession) -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if bot is None:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return bot


@router.get("/api/email/leads/{bot_id}")
async def get_leads(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    return await detail(db, await _own_bot(bot_id, ctx, db), ctx)


class LeadsIn(BaseModel):
    enabled: bool


@router.put("/api/email/leads/{bot_id}")
async def set_leads(bot_id: str, data: LeadsIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await _own_bot(bot_id, ctx, db)
    if data.enabled:
        await plans.require_feature(db, bot.bot_id, "email_alerts")
    source = await intake.source_for(db, ctx.owner_id, bot.bot_id)
    source.enabled = data.enabled
    await db.commit()
    return await detail(db, bot, ctx)


@router.post("/api/leads/in/{code}/indiamart")
async def indiamart_push(code: str, request: Request):
    """Always 200 once it's readable: IndiaMART retries anything else, and turns the push off after 48 hours of failures."""
    rate_limit(f"leads-in:{code}", 600, 3600)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    await intake.from_indiamart(code[:24], payload if isinstance(payload, dict) else {})
    return {"status": "received"}


@router.post("/api/leads/in/{code}/form")
async def form_post(code: str, request: Request):
    """A form's fields, as JSON or as an ordinary form post."""
    rate_limit(f"leads-form:{client_ip(request)}", 20, 3600)
    rate_limit(f"leads-in:{code}", 600, 3600)
    kind = request.headers.get("content-type", "")
    try:
        fields = await request.json() if "json" in kind else dict(await request.form())
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    if not isinstance(fields, dict) or not await intake.from_form(code[:24], fields):
        raise HTTPException(status_code=400, detail="It needs a phone number or an email")
    return {"status": "received"}


@router.post("/api/leads/in/{code}/connect")
async def connect_post(code: str, request: Request):
    """Facebook and Instagram lead ads by the business's own Zapier, Make or Pabbly: the fields as JSON or a form post. Every request comes from the same few
    servers of theirs, so there's no limit per address here, only per link."""
    rate_limit(f"leads-in:{code}", 600, 3600)
    kind = request.headers.get("content-type", "")
    try:
        fields = await request.json() if "json" in kind else dict(await request.form())
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    if not isinstance(fields, dict) or not await intake.from_form(code[:24], fields, ads=True):
        raise HTTPException(status_code=400, detail="It needs a phone number or an email, and Take leads from other places on")
    return {"status": "received"}


REFUSED = {"unknown": (404, "No such link"), "key": (403, "The key doesn't match: copy it from Nimmi > Leads > Sources into your Google lead form"),
           "off": (403, "Leads from other places are turned off for this assistant in Nimmi"), "invalid": (400, "No lead_id")}


@router.post("/api/leads/in/{code}/google")
async def google_post(code: str, request: Request):
    """Google lead forms. Google retries a 5xx and never a 4xx (developers.google.com/google-ads/webhook/docs/implementation): a lead that can never be
    taken gets a 4xx, a busy moment a 503, and the same lead twice a 200 again. Errors are {"message": ...}, as Google reads them."""
    try:
        rate_limit(f"leads-in:{code}", 600, 3600)
    except HTTPException:
        return JSONResponse({"message": "Busy: try again shortly"}, status_code=503)
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"message": "Not JSON"}, status_code=400)
    refused = await intake.from_google(code[:24], payload if isinstance(payload, dict) else {})
    if refused:
        status, message = REFUSED[refused]
        return JSONResponse({"message": message}, status_code=status)
    return {}
