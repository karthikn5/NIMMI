"""
What happens when a lead is captured or a call ends: owner email, CRM webhook,
LeadSquared and (for calls) a WhatsApp confirmation to the caller.

Every send first claims a NotificationLog row (unique on kind + ref_id), so a
lead or call never notifies twice even if the trigger fires more than once.
"""
import asyncio
import logging
import re
from typing import Awaitable, Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import async_session
from backend.models import Bot, CallLog, Conversation, DncEntry, IntegrationSettings, NotificationLog, User
from notify import automations, channels, email
from phone import display, extract_contact

logger = logging.getLogger(__name__)

_background: set = set()


def fire_and_forget(coro: Awaitable) -> None:
    """Run a notification without making the caller wait (keeps a reference so it isn't GC'd)."""
    task = asyncio.ensure_future(coro)
    _background.add(task)

    def _done(t: asyncio.Task):
        _background.discard(t)
        if not t.cancelled() and t.exception():
            logger.error(f"Notification task failed: {t.exception()}")

    task.add_done_callback(_done)


async def _once(user_id: str, kind: str, ref_id: str, send: Callable[[], Awaitable[Optional[str]]]) -> None:
    """Claim (kind, ref_id), then send. `send` returns None on success or a skip reason."""
    async with async_session() as db:
        log = NotificationLog(user_id=user_id, kind=kind, ref_id=ref_id, status="sending")
        db.add(log)
        try:
            await db.commit()
        except IntegrityError:
            return  # already handled
        try:
            skipped = await send()
            log.status = "skipped" if skipped else "sent"
            log.error = skipped
        except Exception as e:
            log.status, log.error = "failed", str(e)[:1000]
            logger.warning(f"{kind} for {ref_id} failed: {e}")
        await db.commit()


async def _settings(db, owner_id: str) -> IntegrationSettings:
    s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    return s or IntegrationSettings(user_id=owner_id, email_alerts=True)


def _lines(fields: dict) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in fields.items())


def recipients(settings: IntegrationSettings, owner_email: Optional[str]) -> list[str]:
    """Team alert addresses: up to 5, comma-separated in settings, else the account email."""
    listed = [a.strip() for a in re.split(r"[,;\s]+", settings.alert_email or "") if automations.EMAIL_RE.fullmatch(a.strip())]
    return listed[:5] or ([owner_email] if owner_email else [])


async def _email_team(to: list[str], subject: str, text: str) -> Optional[str]:
    if not to:
        return "no recipient"
    sent = [await email.send_email(addr, subject, text) for addr in to]
    return None if any(sent) else "email not configured"


def _business(settings: IntegrationSettings, bot: Optional[Bot]) -> str:
    return settings.sender_name or (bot.bot_name if bot else "") or "Our team"


async def lead_captured(conversation_id: str) -> None:
    async with async_session() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
        if not conv or not conv.captured_data:
            return
        bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first()
        if not bot:
            return
        owner = (await db.execute(select(User).where(User.id == bot.user_id))).scalars().first()
        settings = await _settings(db, bot.user_id)
    contact = extract_contact(conv.captured_data)
    if not (contact.get("phone") or contact.get("email")):
        return  # not a lead until there's a way to reach them

    fields = dict(conv.captured_data)
    lead = {**contact, "bot": bot.bot_name, "fields": fields, "conversation_id": conversation_id, "source": "chat"}

    if settings.email_alerts and owner:
        channel = "WhatsApp" if (conv.visitor_session_id or "").startswith("wa:") else "chat"
        await _once(bot.user_id, "lead_email", conversation_id, lambda: _email_team(
            recipients(settings, owner.email), f"New lead from {bot.bot_name}",
            f"{bot.bot_name} captured a new lead in {channel}.\n\n{_lines(fields)}\n\n"
            f"See all leads: {email.dashboard_url()}/dashboard/builder/{bot.bot_id}"))

    # Automatic email to the customer (if they gave an email and the automation is on).
    await automations.schedule(bot.user_id, "chat_lead", conversation_id, contact.get("email"), {
        **{automations.field_key(k): v for k, v in fields.items()}, "details": automations.details_text(fields),
        "name": contact.get("name"), "email": contact.get("email"), "phone": display(contact.get("phone")) if contact.get("phone") else "",
        "business": _business(settings, bot), "assistant": bot.bot_name, "summary": "",
    })

    if settings.webhook_url:
        await _once(bot.user_id, "lead_webhook", conversation_id,
                    lambda: _none(channels.post_webhook(settings.webhook_url, settings.webhook_secret, "lead.captured", lead)))

    if settings.leadsquared_enabled and settings.leadsquared_host:
        await _once(bot.user_id, "lead_leadsquared", conversation_id,
                    lambda: _none(channels.push_leadsquared(settings.leadsquared_host, settings.leadsquared_access_key,
                                                            settings.leadsquared_secret_key, lead)))


async def call_completed(call_id: str) -> None:
    async with async_session() as db:
        call = (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()
        if not call:
            return
        bot = (await db.execute(select(Bot).where(Bot.bot_id == call.bot_id))).scalars().first() if call.bot_id else None
        owner = (await db.execute(select(User).where(User.id == call.user_id))).scalars().first()
        settings = await _settings(db, call.user_id)
        blocked = bool(call.caller_e164) and (await db.execute(
            select(DncEntry.id).where(DncEntry.user_id == call.user_id, DncEntry.e164 == call.caller_e164)
        )).scalar_one_or_none() is not None

    if call.channel == "browser":
        return  # test calls don't notify anyone
    bot_name = bot.bot_name if bot else "Your assistant"
    captured = call.captured or {}
    contact = extract_contact(captured)
    contact.setdefault("phone", call.caller_e164)
    payload = {
        **contact, "bot": bot_name, "fields": captured, "summary": call.summary, "call_id": call.id,
        "direction": call.direction, "outcome": call.outcome, "duration_sec": call.duration_sec, "source": "voice",
        "successful": call.successful, "sentiment": call.sentiment, "campaign_id": call.campaign_id,
    }

    wants_call_email = call.outcome == "lead_captured" and settings.email_alerts or \
        call.outcome in ("transferred", "answered") and settings.alert_calls is not False
    if owner and wants_call_email:
        await _once(call.user_id, "call_email", call.id, lambda: _email_team(
            recipients(settings, owner.email),
            f"{'New lead' if call.outcome == 'lead_captured' else 'Call'} from {display(call.caller_e164)} ({bot_name})",
            f"{bot_name} {'took a call from' if call.direction == 'inbound' else 'called'} {display(call.caller_e164)}.\n\n"
            f"Summary: {call.summary or '-'}\n\n{_lines(captured) if captured else ''}\n\n"
            f"Listen and read the transcript: {email.dashboard_url()}/dashboard/voice/calls?call={call.id}"))

    # Automatic email to the customer. A call that reached its goal gets the "goal met" email when that's on.
    values = {
        **{automations.field_key(k): v for k, v in captured.items()},
        "name": contact.get("name"), "email": contact.get("email"), "phone": display(call.caller_e164) if call.caller_e164 else "",
        "business": _business(settings, bot), "assistant": bot_name, "summary": call.summary or "",
        "details": automations.details_text(captured),
    }
    if not (call.successful and await automations.schedule(call.user_id, "goal_met", call.id, contact.get("email"), values)):
        await automations.schedule(call.user_id, "call_lead", call.id, contact.get("email"), values)

    if settings.webhook_url:
        await _once(call.user_id, "call_webhook", call.id,
                    lambda: _none(channels.post_webhook(settings.webhook_url, settings.webhook_secret, "call.completed", payload)))

    if settings.leadsquared_enabled and settings.leadsquared_host and call.outcome == "lead_captured":
        await _once(call.user_id, "call_leadsquared", call.id,
                    lambda: _none(channels.push_leadsquared(settings.leadsquared_host, settings.leadsquared_access_key,
                                                            settings.leadsquared_secret_key, payload)))

    if (settings.whatsapp_enabled and settings.whatsapp_template and call.caller_e164
            and call.outcome == "lead_captured" and not blocked):
        async def send_whatsapp():
            # The workspace's own WhatsApp number when connected, else the server's.
            from whatsapp.numbers import workspace_number
            async with async_session() as db:
                number = await workspace_number(db, call.user_id)
            token, pid = (number.access_token, number.phone_number_id) if number else (None, None)
            if not channels.whatsapp_configured(token, pid):
                return "whatsapp not configured"
            await channels.send_whatsapp_template(
                call.caller_e164, settings.whatsapp_template, settings.whatsapp_language,
                [contact.get("name") or "there", bot_name, call.summary or "your request"],
                phone_number_id=pid, token=token,
            )
        await _once(call.user_id, "call_whatsapp", call.id, send_whatsapp)


async def handoff_requested(conversation_id: str, message: str = "") -> None:
    """A customer asked for a person: email the team (once per conversation), if that alert is on."""
    async with async_session() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
        bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first() if conv else None
        if not bot:
            return
        owner = (await db.execute(select(User).where(User.id == bot.user_id))).scalars().first()
        settings = await _settings(db, bot.user_id)
    if not settings.alert_handoffs or not owner:
        return
    contact = extract_contact(conv.captured_data or {})
    who = contact.get("name") or (display(contact["phone"]) if contact.get("phone") else "A visitor")
    channel = "WhatsApp" if (conv.visitor_session_id or "").startswith("wa:") else "website chat"
    await _once(bot.user_id, "handoff_email", conversation_id, lambda: _email_team(
        recipients(settings, owner.email), f"{who} wants to talk to a person ({bot.bot_name})",
        f"{who} asked for a person in {channel}.\n\n" + (f"Their message: {message}\n\n" if message else "") +
        f"Reply now from Live chat: {email.dashboard_url()}/dashboard/live-chat"))


async def call_missed(owner_id: str, ref_id: str, phone: Optional[str], variables: Optional[dict], bot_id: Optional[str]) -> None:
    """We called someone (call-back or campaign) and never reached them: the "couldn't reach them" email."""
    variables = variables or {}
    contact = extract_contact(variables)
    if not contact.get("email"):
        return
    async with async_session() as db:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first() if bot_id else None
        settings = await _settings(db, owner_id)
    await automations.schedule(owner_id, "call_missed", ref_id, contact["email"], {
        **{automations.field_key(k): v for k, v in variables.items()},
        "name": contact.get("name"), "email": contact["email"], "phone": display(phone) if phone else "",
        "business": _business(settings, bot), "assistant": bot.bot_name if bot else "", "summary": "",
    })


async def handoff_closed(conversation_id: str) -> None:
    """Someone from the team finished a Live chat: the "after your team helps" email."""
    async with async_session() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
        bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first() if conv else None
        if not bot:
            return
        settings = await _settings(db, bot.user_id)
    captured = conv.captured_data or {}
    contact = extract_contact(captured)
    await automations.schedule(bot.user_id, "handoff_done", conversation_id, contact.get("email"), {
        **{automations.field_key(k): v for k, v in captured.items()},
        "name": contact.get("name"), "email": contact.get("email"),
        "phone": display(contact["phone"]) if contact.get("phone") else "",
        "business": _business(settings, bot), "assistant": bot.bot_name, "summary": "",
        "details": automations.details_text(captured),
    })


async def _none(coro: Awaitable) -> None:
    await coro
    return None
