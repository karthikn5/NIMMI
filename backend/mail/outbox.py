"""
Email events for the business's own systems (mail plan 5.8, phase 6; Pro's integrations): its webhook gets email.sent, email.replied, email.clicked, email.bounced
and email.unsubscribed, signed as the lead webhooks are (X-Nimmi-Signature); LeadSquared gets the same as activities on the lead, found by email (a custom activity
whose code the business enters), except "sent": a bulk email would go past LeadSquared's limit of about 10 calls every 5 seconds. HubSpot and Zoho CRM get them as notes
(notify/crm.py). Each event is kept first, then sent by the scheduler, with retries; deliveries show in Integrations > Activity.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.future import select

from backend.models import IntegrationEvent, IntegrationSettings, NotificationLog
from database import async_session

logger = logging.getLogger(__name__)

EVENTS = ("email.sent", "email.replied", "email.clicked", "email.bounced", "email.unsubscribed")
TO_LEADSQUARED = ("email.replied", "email.clicked", "email.bounced", "email.unsubscribed")
TRIES = 6
WAITS = (1, 5, 30, 120, 360)   # minutes before trying again
BATCH = {"webhook": 100, "leadsquared": 20, "hubspot": 20, "zoho": 20}
LEADSQUARED_GAP = 0.6           # seconds between calls: LeadSquared allows about 10 every 5 seconds
STUCK = timedelta(minutes=10)
KEEP = timedelta(days=30)
NOTES = {"email.replied": "Replied to an email", "email.clicked": "Clicked a link in an email", "email.bounced": "An email bounced", "email.unsubscribed": "Unsubscribed from emails"}


async def emit(db, owner_id: str, event: str, data: dict) -> None:
    """Keep an event for the workspace's own systems, if it has any (the caller commits). Never raises."""
    import plans
    try:
        s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        if s is None:
            return
        targets = ["webhook"] if s.webhook_url else []
        if event in TO_LEADSQUARED and s.leadsquared_enabled and s.leadsquared_activity and s.leadsquared_host and s.leadsquared_access_key and s.leadsquared_secret_key:
            targets.append("leadsquared")
        if event in TO_LEADSQUARED and s.hubspot_enabled and s.hubspot_token:
            targets.append("hubspot")
        if event in TO_LEADSQUARED and s.zoho_enabled and s.zoho_refresh_token:
            targets.append("zoho")
        if not targets or not (await plans.workspace_includes(db, owner_id)).integrations:
            return
        for target in targets:
            db.add(IntegrationEvent(user_id=owner_id, target=target, event=event, data=data, status="new", attempts=0, next_at=datetime.utcnow()))
    except Exception as e:
        logger.warning(f"Keeping {event} for {owner_id} failed: {e}")


async def emit_now(owner_id: str, event: str, data: dict) -> None:
    """emit, in a session of its own."""
    async with async_session() as db:
        await emit(db, owner_id, event, data)
        await db.commit()


async def _deliver(row: IntegrationEvent, s: IntegrationSettings) -> None:
    from notify import channels, crm
    if row.target == "webhook":
        if not s.webhook_url:
            raise channels.ChannelError("The webhook was removed")
        await channels.post_webhook(s.webhook_url, s.webhook_secret, row.event, row.data)
        return
    d = row.data or {}
    note = "; ".join(x for x in (NOTES.get(row.event, row.event), d.get("subject") and f"\"{d['subject']}\"", d.get("link"), d.get("detail"), d.get("text")) if x)
    if row.target == "hubspot":
        if not (s.hubspot_enabled and s.hubspot_token):
            raise channels.ChannelError("HubSpot was turned off")
        await crm.hubspot_note(s.hubspot_token, d.get("lead") or d.get("to") or "", note[:1000], d.get("at"))
        return
    if row.target == "zoho":
        if not (s.zoho_enabled and s.zoho_refresh_token):
            raise channels.ChannelError("Zoho CRM was disconnected")
        await crm.zoho_note(row.user_id, d.get("lead") or d.get("to") or "", NOTES.get(row.event, row.event), note[:1000])
        return
    if not (s.leadsquared_enabled and s.leadsquared_activity):
        raise channels.ChannelError("LeadSquared's email activity was turned off")
    await channels.post_leadsquared_activity(s.leadsquared_host, s.leadsquared_access_key, s.leadsquared_secret_key, d.get("lead") or d.get("to") or "",
                                             int(s.leadsquared_activity), note[:1000], d.get("at"))


async def drain(now: Optional[datetime] = None) -> int:
    """Scheduler: the events due. Each is claimed, so the processes share them."""
    now = now or datetime.utcnow()
    sent = 0
    for target, limit in BATCH.items():
        async with async_session() as db:
            ids = (await db.execute(select(IntegrationEvent.id).where(
                IntegrationEvent.target == target, IntegrationEvent.status == "new", IntegrationEvent.next_at <= now,
                or_(IntegrationEvent.claimed_at.is_(None), IntegrationEvent.claimed_at < now - STUCK)).order_by(IntegrationEvent.next_at).limit(limit))).scalars().all()
        for n, event_id in enumerate(ids):
            if target == "leadsquared" and n:
                await asyncio.sleep(LEADSQUARED_GAP)
            sent += await _one(event_id, now)
    return sent


async def _one(event_id: str, now: datetime) -> int:
    async with async_session() as db:
        claimed = await db.execute(update(IntegrationEvent).where(IntegrationEvent.id == event_id, IntegrationEvent.status == "new",
                                                                  or_(IntegrationEvent.claimed_at.is_(None), IntegrationEvent.claimed_at < now - STUCK))
                                   .values(claimed_at=now).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return 0
        row = await db.get(IntegrationEvent, event_id)
        s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == row.user_id))).scalars().first()
    error = None
    try:
        if s is None:
            raise RuntimeError("The workspace's integrations are gone")
        await _deliver(row, s)
    except Exception as e:
        error = str(e)[:300] or e.__class__.__name__
    async with async_session() as db:
        row = await db.get(IntegrationEvent, event_id)
        row.attempts, row.claimed_at = (row.attempts or 0) + 1, None
        if error is None:
            row.status, row.sent_at, row.error = "sent", datetime.utcnow(), None
        elif row.attempts >= TRIES:
            row.status, row.error = "failed", error
        else:
            row.error, row.next_at = error, datetime.utcnow() + timedelta(minutes=WAITS[min(row.attempts, len(WAITS)) - 1])
        if row.status in ("sent", "failed"):  # Integrations > Activity
            db.add(NotificationLog(user_id=row.user_id, kind=f"{row.event.replace('.', '_')}_{row.target}", ref_id=row.id, status=row.status, error=row.error))
        await db.commit()
    return 1 if error is None else 0


async def purge(now: Optional[datetime] = None) -> None:
    from sqlalchemy import delete
    async with async_session() as db:
        await db.execute(delete(IntegrationEvent).where(IntegrationEvent.status.in_(("sent", "failed")), IntegrationEvent.created_at < (now or datetime.utcnow()) - KEEP))
        await db.commit()
