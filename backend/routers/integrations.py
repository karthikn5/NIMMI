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
from backend.models import IntegrationSettings, NotificationLog, User
from phone import to_e164
from netsafe import UnsafeUrl, assert_public_url
from notify import automations, channels, email
from notify.events import recipients
from whatsapp.numbers import workspace_number

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


import plans

def _json(s: IntegrationSettings, owner_email: str, whatsapp_number: bool = False) -> dict:
    return {
        "email_alerts": bool(s.email_alerts), "alert_email": s.alert_email or "", "default_email": owner_email,
        "whatsapp_enabled": bool(s.whatsapp_enabled), "whatsapp_template": s.whatsapp_template or "",
        "whatsapp_language": s.whatsapp_language or "en",
        "webhook_url": s.webhook_url or "", "webhook_secret": s.webhook_secret or "",
        "leadsquared_enabled": bool(s.leadsquared_enabled), "leadsquared_host": s.leadsquared_host or "",
        "leadsquared_access_key": s.leadsquared_access_key or "",
        "leadsquared_has_secret": bool(s.leadsquared_secret_key),
        # Email automation
        "alert_calls": s.alert_calls is not False, "alert_handoffs": bool(s.alert_handoffs),
        "sender_name": s.sender_name or "", "reply_to": s.reply_to or "",
        "automations": automations.automations(s), "placeholders": automations.PLACEHOLDERS,
        "server": {
            "email": email.is_configured(),
            # WhatsApp itself is set up in the WhatsApp section (whatsapp/api.py).
            "whatsapp": whatsapp_number or channels.whatsapp_configured(),
        },
    }


async def _load(owner_id: str, db: AsyncSession) -> tuple[IntegrationSettings, str]:
    s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    owner = (await db.execute(select(User.email).where(User.id == owner_id))).scalar_one_or_none() or ""
    return s or IntegrationSettings(user_id=owner_id, email_alerts=True, whatsapp_language="en"), owner


@router.get("")
async def get_settings(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    s, owner = await _load(ctx.owner_id, db)
    return _json(s, owner, bool(await workspace_number(db, ctx.owner_id)))


class StepIn(BaseModel):
    delay: str = "now"
    subject: str = Field("", max_length=200)
    body: str = Field("", max_length=5000)


class AutomationIn(BaseModel):
    enabled: bool = False
    steps: Optional[list[StepIn]] = None
    # Older dashboards sent a single email.
    delay: str = "now"
    subject: str = Field("", max_length=200)
    body: str = Field("", max_length=5000)

    def step_list(self) -> list[StepIn]:
        return self.steps if self.steps is not None else [StepIn(delay=self.delay, subject=self.subject, body=self.body)]


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
    # Email automation
    alert_calls: bool = True
    alert_handoffs: bool = False
    sender_name: str = Field("", max_length=60)
    reply_to: str = Field("", max_length=200)
    automations: dict[str, AutomationIn] = {}


@router.put("")
async def update_settings(data: IntegrationUpdate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "integrations")
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
        steps = a.step_list()
        if key not in automations.DEFAULTS or not steps or any(st.delay not in automations.DELAYS for st in steps):
            raise HTTPException(status_code=400, detail="Unknown email automation")
        if len(steps) > automations.MAX_STEPS:
            raise HTTPException(status_code=400, detail=f"A sequence can have up to {automations.MAX_STEPS} emails")
        offsets = [automations.DELAYS[st.delay] for st in steps]
        if any(later <= earlier for earlier, later in zip(offsets, offsets[1:])):
            raise HTTPException(status_code=400, detail="Each follow-up has to go out after the one before it")
        if a.enabled and not all(st.subject.strip() and st.body.strip() for st in steps):
            raise HTTPException(status_code=400, detail="Add a subject and message to every email before turning it on")
        autos[key] = {"enabled": a.enabled,
                      "steps": [{"delay": st.delay, "subject": st.subject.strip(), "body": st.body.strip()} for st in steps]}
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

    db.add(s)
    await db.commit()
    return _json(s, owner, bool(await workspace_number(db, ctx.owner_id)))


class TestRequest(BaseModel):
    channel: str  # email, email_automation, webhook, leadsquared, whatsapp
    to_phone: Optional[str] = None
    message: Optional[str] = None
    automation: Optional[str] = None  # chat_lead, or chat_lead#2 for a follow-up
    subject: Optional[str] = Field(None, max_length=200)  # bulk email drafts (channel "email_draft")
    body: Optional[str] = Field(None, max_length=10000)


@router.post("/test")
async def send_test(req: TestRequest, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await plans.require(db, ctx.owner_id, "integrations")
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
        elif req.channel in ("email_automation", "email_draft"):
            if req.channel == "email_draft":
                if not ((req.subject or "").strip() and (req.body or "").strip()):
                    raise channels.ChannelError("Add a subject and message first")
                subject, template = req.subject, req.body
            else:
                key, _, n = (req.automation or "").partition("#")
                auto = automations.automations(s).get(key)
                step = int(n) if n.isdigit() else 1
                if not auto or not 1 <= step <= len(auto["steps"]):
                    raise HTTPException(status_code=400, detail="Unknown email automation")
                subject, template = auto["steps"][step - 1]["subject"], auto["steps"][step - 1]["body"]
            business = s.sender_name or "Your business"
            values = {"name": "Priya", "business": business, "assistant": "Nimmi", "email": "priya@example.com",
                      "phone": "+91 98765 43210", "details": "Visit date: Saturday, 11 AM\nBudget: 60-70 lakh",
                      "summary": "Priya asked about weekend site visits for a 2BHK and booked Saturday at 11am."}
            body = automations.render(template, values)
            to = recipients(s, owner)[0] if recipients(s, owner) else owner
            ok = await email.send_email(to, "[Test] " + automations.render(subject, values), body,
                                        automations.html_email(body, business, None), reply_to=s.reply_to, from_name=business)
            if not ok:
                raise channels.ChannelError(email.last_error() or "Email isn't configured on the server")
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
            number = await workspace_number(db, ctx.owner_id)
            await channels.send_whatsapp_text(to_e164=target, text=text,
                                              phone_number_id=number.phone_number_id if number else None,
                                              token=number.access_token if number else None)
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


@router.post("/email/unsubscribe")
async def email_unsubscribe_one_click(token: str = ""):
    """Mail apps' one-click unsubscribe (List-Unsubscribe-Post) posts to the same link."""
    from auth import decode_scoped_token
    subject = decode_scoped_token(token, "email_unsub")
    if not subject or "|" not in subject:
        raise HTTPException(status_code=400, detail="This link has expired")
    owner_id, address = subject.split("|", 1)
    await automations.unsubscribe(owner_id, address)
    return {"status": "unsubscribed"}


def _page(title: str, text: str) -> str:
    import html as h
    return (f'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h.escape(title)}</title>'
            f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:420px;margin:15vh auto;padding:0 16px;color:#1c1719">'
            f'<h1 style="font-size:20px;margin:0 0 8px">{h.escape(title)}</h1><p style="color:#57534e;line-height:1.6">{h.escape(text)}</p></div>')
