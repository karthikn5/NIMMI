"""Workspace integrations: lead alert email, WhatsApp confirmations, CRM webhook and LeadSquared."""
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, require_manager
from database import get_db
from backend.models import Bot, IntegrationSettings, NotificationLog, User
from phone import to_e164
from netsafe import UnsafeUrl, assert_public_url
from notify import automations, channels, email
from notify.events import recipients

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


import os

def _json(s: IntegrationSettings, owner_email: str) -> dict:
    backend_url = (os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
    return {
        "email_alerts": bool(s.email_alerts), "alert_email": s.alert_email or "", "default_email": owner_email,
        "whatsapp_enabled": bool(s.whatsapp_enabled), "whatsapp_template": s.whatsapp_template or "",
        "whatsapp_language": s.whatsapp_language or "en",
        "webhook_url": s.webhook_url or "", "webhook_secret": s.webhook_secret or "",
        "leadsquared_enabled": bool(s.leadsquared_enabled), "leadsquared_host": s.leadsquared_host or "",
        "leadsquared_access_key": s.leadsquared_access_key or "",
        "leadsquared_has_secret": bool(s.leadsquared_secret_key),
        # Two-Way WhatsApp AI Chat
        "whatsapp_chat_enabled": bool(s.whatsapp_chat_enabled),
        "whatsapp_bot_id": s.whatsapp_bot_id or "",
        "whatsapp_phone_number_id": s.whatsapp_phone_number_id or "",
        "whatsapp_has_token": bool(s.whatsapp_access_token),
        "whatsapp_verify_token": s.whatsapp_verify_token or "",
        "whatsapp_business_account_id": s.whatsapp_business_account_id or "",
        "whatsapp_webhook_url": f"{backend_url}/api/integrations/whatsapp/webhook",
        # Email automation
        "alert_calls": s.alert_calls is not False, "alert_handoffs": bool(s.alert_handoffs),
        "sender_name": s.sender_name or "", "reply_to": s.reply_to or "",
        "automations": automations.automations(s), "placeholders": automations.PLACEHOLDERS,
        "server": {
            "email": email.is_configured(),
            "whatsapp": channels.whatsapp_configured(s.whatsapp_access_token, s.whatsapp_phone_number_id),
        },
    }


async def _load(owner_id: str, db: AsyncSession) -> tuple[IntegrationSettings, str]:
    s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    owner = (await db.execute(select(User.email).where(User.id == owner_id))).scalar_one_or_none() or ""
    return s or IntegrationSettings(user_id=owner_id, email_alerts=True, whatsapp_language="en"), owner


@router.get("")
async def get_settings(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    s, owner = await _load(ctx.owner_id, db)
    return _json(s, owner)


class AutomationIn(BaseModel):
    enabled: bool = False
    delay: str = "now"
    subject: str = Field("", max_length=200)
    body: str = Field("", max_length=5000)


class IntegrationUpdate(BaseModel):
    email_alerts: bool = True
    alert_email: str = ""
    whatsapp_enabled: bool = False
    whatsapp_template: str = Field("", max_length=120)
    whatsapp_language: str = Field("en", max_length=10)
    webhook_url: str = ""
    leadsquared_enabled: bool = False
    leadsquared_host: str = ""
    leadsquared_access_key: str = ""
    leadsquared_secret_key: Optional[str] = None  # blank keeps the saved one
    # Two-Way WhatsApp AI Chatbot
    whatsapp_chat_enabled: bool = False
    whatsapp_bot_id: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None
    whatsapp_business_account_id: Optional[str] = None
    # Email automation
    alert_calls: bool = True
    alert_handoffs: bool = False
    sender_name: str = Field("", max_length=60)
    reply_to: str = Field("", max_length=200)
    automations: dict[str, AutomationIn] = {}


@router.put("")
async def update_settings(data: IntegrationUpdate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    s, owner = await _load(ctx.owner_id, db)
    if data.webhook_url:
        try:
            await assert_public_url(data.webhook_url)
        except UnsafeUrl as e:
            raise HTTPException(status_code=400, detail=f"Webhook URL: {e}")
    alert_list = [a.strip() for a in re.split(r"[,;\s]+", data.alert_email or "") if a.strip()]
    bad = [a for a in alert_list if not automations.EMAIL_RE.fullmatch(a)]
    if bad:
        raise HTTPException(status_code=400, detail=f"Check this email address: {bad[0]}")
    if len(alert_list) > 5:
        raise HTTPException(status_code=400, detail="Send alerts to up to 5 addresses")
    if data.reply_to.strip() and not automations.EMAIL_RE.fullmatch(data.reply_to.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid reply-to email address")
    autos = {}
    for key, a in data.automations.items():
        if key not in automations.DEFAULTS or a.delay not in automations.DELAYS:
            raise HTTPException(status_code=400, detail="Unknown email automation")
        if a.enabled and not (a.subject.strip() and a.body.strip()):
            raise HTTPException(status_code=400, detail="Add a subject and message before turning an email on")
        autos[key] = {"enabled": a.enabled, "delay": a.delay, "subject": a.subject.strip(), "body": a.body.strip()}
    if any(a["enabled"] for a in autos.values()) and not (data.reply_to.strip() or s.reply_to):
        raise HTTPException(status_code=400, detail="Add a reply-to address so customers can answer you")
    if data.whatsapp_enabled and not data.whatsapp_template:
        raise HTTPException(status_code=400, detail="Enter the name of your approved WhatsApp template")
    if data.leadsquared_enabled and not (data.leadsquared_host and data.leadsquared_access_key and (data.leadsquared_secret_key or s.leadsquared_secret_key)):
        raise HTTPException(status_code=400, detail="LeadSquared needs the API host, access key and secret key")

    s.email_alerts = data.email_alerts
    s.alert_email = ", ".join(alert_list) or None
    s.alert_calls, s.alert_handoffs = data.alert_calls, data.alert_handoffs
    s.sender_name = data.sender_name.strip() or None
    s.reply_to = data.reply_to.strip() or None
    if autos:
        s.email_automations = {**(s.email_automations or {}), **autos}
    s.whatsapp_enabled, s.whatsapp_template, s.whatsapp_language = data.whatsapp_enabled, data.whatsapp_template.strip() or None, data.whatsapp_language
    if data.webhook_url.strip() != (s.webhook_url or ""):
        s.webhook_url = data.webhook_url.strip() or None
        s.webhook_secret = secrets.token_hex(24) if s.webhook_url else None
    s.leadsquared_enabled, s.leadsquared_host, s.leadsquared_access_key = data.leadsquared_enabled, data.leadsquared_host.strip() or None, data.leadsquared_access_key.strip() or None
    if data.leadsquared_secret_key:
        s.leadsquared_secret_key = data.leadsquared_secret_key.strip()

    # WhatsApp 2-Way AI Chatbot
    if data.whatsapp_bot_id and data.whatsapp_bot_id.strip():
        owned = (await db.execute(select(Bot.bot_id).where(
            Bot.bot_id == data.whatsapp_bot_id.strip(), Bot.user_id == ctx.owner_id))).first()
        if not owned:
            raise HTTPException(status_code=400, detail="Choose one of your own assistants for WhatsApp")
    pid = (data.whatsapp_phone_number_id or "").strip()
    if pid:
        taken = (await db.execute(select(IntegrationSettings.user_id).where(
            IntegrationSettings.whatsapp_phone_number_id == pid, IntegrationSettings.user_id != ctx.owner_id))).first()
        if taken:
            raise HTTPException(status_code=409, detail="That WhatsApp number is already connected to another workspace")
    if data.whatsapp_chat_enabled and not (pid and (data.whatsapp_access_token or s.whatsapp_access_token)):
        raise HTTPException(status_code=400, detail="WhatsApp chat needs the phone number ID and an access token")
    s.whatsapp_chat_enabled = bool(data.whatsapp_chat_enabled)
    s.whatsapp_bot_id = data.whatsapp_bot_id.strip() if data.whatsapp_bot_id else None
    s.whatsapp_phone_number_id = data.whatsapp_phone_number_id.strip() if data.whatsapp_phone_number_id else None
    if data.whatsapp_access_token:
        s.whatsapp_access_token = data.whatsapp_access_token.strip()
    if data.whatsapp_verify_token:
        s.whatsapp_verify_token = data.whatsapp_verify_token.strip()
    elif not s.whatsapp_verify_token and data.whatsapp_chat_enabled:
        s.whatsapp_verify_token = f"nimmi_wa_{secrets.token_hex(10)}"
    s.whatsapp_business_account_id = data.whatsapp_business_account_id.strip() if data.whatsapp_business_account_id else None

    db.add(s)
    await db.commit()
    return _json(s, owner)


class TestRequest(BaseModel):
    channel: str  # email, email_automation, webhook, leadsquared, whatsapp
    to_phone: Optional[str] = None
    message: Optional[str] = None
    automation: Optional[str] = None  # chat_lead, call_lead


@router.post("/test")
async def send_test(req: TestRequest, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    s, owner = await _load(ctx.owner_id, db)
    sample = {"name": "Test Lead", "phone": "+919876543210", "email": "test@example.com", "bot": "Test assistant",
              "summary": "This is a test from Nimmi AI.", "fields": {"Name": "Test Lead"}, "source": "test"}
    try:
        if req.channel == "email":
            to = recipients(s, owner)
            sent = [await email.send_email(a, "Test alert from Nimmi AI", "This is a test. New lead alerts will arrive at this address.")
                    for a in to]
            if not any(sent):
                raise channels.ChannelError("Email isn't configured on the server")
        elif req.channel == "email_automation":
            auto = automations.automations(s).get(req.automation or "")
            if not auto:
                raise HTTPException(status_code=400, detail="Unknown email automation")
            business = s.sender_name or "Your business"
            values = {"name": "Priya", "business": business, "assistant": "Nimmi", "email": "priya@example.com",
                      "phone": "+91 98765 43210",
                      "summary": "Priya asked about weekend site visits for a 2BHK and booked Saturday at 11am."}
            body = automations.render(auto["body"], values)
            to = recipients(s, owner)[0] if recipients(s, owner) else owner
            ok = await email.send_email(to, "[Test] " + automations.render(auto["subject"], values), body,
                                        automations.html_email(body, business, None), reply_to=s.reply_to, from_name=business)
            if not ok:
                raise channels.ChannelError("Email isn't configured on the server")
        elif req.channel == "webhook":
            if not s.webhook_url:
                raise channels.ChannelError("Save a webhook URL first")
            await channels.post_webhook(s.webhook_url, s.webhook_secret, "test", sample)
        elif req.channel == "leadsquared":
            if not (s.leadsquared_host and s.leadsquared_access_key and s.leadsquared_secret_key):
                raise channels.ChannelError("Save your LeadSquared details first")
            await channels.push_leadsquared(s.leadsquared_host, s.leadsquared_access_key, s.leadsquared_secret_key, sample)
        elif req.channel == "whatsapp":
            target = to_e164(req.to_phone or "")
            if not target:
                raise channels.ChannelError("Enter the phone number to send the test message to")
            text = (req.message or "Hello from Nimmi AI. Your WhatsApp integration is connected.")[:1000]
            await channels.send_whatsapp_text(
                to_e164=target,
                text=text,
                phone_number_id=s.whatsapp_phone_number_id,
                token=s.whatsapp_access_token,
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown channel")
    except channels.ChannelError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "sent"}


@router.get("/log")
async def delivery_log(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(NotificationLog).where(NotificationLog.user_id == ctx.owner_id)
                             .order_by(NotificationLog.created_at.desc()).limit(50))).scalars().all()
    return [{"id": r.id, "kind": r.kind, "status": r.status, "error": r.error,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/email/unsubscribe", response_class=HTMLResponse)
async def email_unsubscribe(token: str = ""):
    """Public link at the bottom of every automatic customer email."""
    from auth import decode_scoped_token
    subject = decode_scoped_token(token, "email_unsub")
    if not subject or "|" not in subject:
        return HTMLResponse(_page("This link has expired", "Reply to the email you received and ask to be removed."), status_code=400)
    owner_id, address = subject.split("|", 1)
    await automations.unsubscribe(owner_id, address)
    return HTMLResponse(_page("You're unsubscribed", f"{address} won't get any more automatic emails from this business."))


def _page(title: str, text: str) -> str:
    import html as h
    return (f'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h.escape(title)}</title>'
            f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:420px;margin:15vh auto;padding:0 16px;color:#1c1719">'
            f'<h1 style="font-size:20px;margin:0 0 8px">{h.escape(title)}</h1><p style="color:#57534e;line-height:1.6">{h.escape(text)}</p></div>')
