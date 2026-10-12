"""
Background jobs, started with the app:
  - dial consented callbacks when due, inside the workspace's calling hours (IST)
  - delete recordings and transcripts past each workspace's retention period
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.future import select

from database import async_session
from backend.models import (Campaign, CallbackJob, CallbackSettings, CallLog, ComplianceSettings, DncEntry,
                            PhoneNumber, VoiceAgent)
import balance
from voice import exotel, metering, recording, twilio
from voice.catalog import NUMBER_GRACE_DAYS

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
DELAYS = {"immediate": 0, "1m": 60, "5m": 300, "15m": 900}
RETRY_GAP = timedelta(hours=1)

# Exotel call SIDs whose assistant asked to transfer -> number to dial (read by the Passthru step).
pending_transfers: dict[str, str] = {}
pending_whispers: dict[str, str] = {}  # call SID -> brief for the person taking a warm transfer
MACHINE = ("machine_end_beep", "machine_end_silence", "machine_end_other", "fax")
_task: asyncio.Task | None = None


def _naive(dt):
    return dt.replace(tzinfo=None) if dt else dt


def in_window(now_utc: datetime, start: str, end: str) -> bool:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(IST).strftime("%H:%M")
    return start <= local < end if start < end else (local >= start or local < end)


def next_window_start(now_utc: datetime, start: str) -> datetime:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(IST)
    h, m = (int(x) for x in start.split(":"))
    candidate = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


async def dispatch_due_callbacks() -> None:
    """Dial queued call-backs and campaign calls that are due, within their calling hours and limits."""
    now = datetime.utcnow()
    async with async_session() as db:
        jobs = (await db.execute(
            select(CallbackJob).outerjoin(Campaign, Campaign.id == CallbackJob.campaign_id).where(
                CallbackJob.status == "queued", CallbackJob.next_attempt_at <= now,
                or_(CallbackJob.campaign_id.is_(None), Campaign.status == "running"),
            ).order_by(CallbackJob.next_attempt_at).limit(20)
        )).scalars().all()
        campaigns: dict[str, Campaign] = {}
        in_flight: dict[str, int] = {}
        for job in jobs:
            if job.campaign_id:
                campaign = campaigns.get(job.campaign_id) or (await db.execute(
                    select(Campaign).where(Campaign.id == job.campaign_id))).scalars().first()
                if not campaign:
                    job.status, job.last_error = "cancelled", "Campaign deleted"
                    continue
                campaigns[campaign.id] = campaign
                if campaign.id not in in_flight:
                    in_flight[campaign.id] = (await db.execute(select(func.count()).select_from(CallbackJob).where(
                        CallbackJob.campaign_id == campaign.id, CallbackJob.status == "calling"))).scalar() or 0
                if in_flight[campaign.id] >= max(1, campaign.concurrency or 1):
                    continue  # wait for a line to free up
                window, from_id, max_attempts = (campaign.window_start, campaign.window_end), campaign.from_number_id, campaign.max_attempts
            else:
                settings = (await db.execute(select(CallbackSettings).where(CallbackSettings.user_id == job.user_id))).scalars().first()
                if not settings or not settings.enabled:
                    job.status, job.last_error = "cancelled", "Callbacks turned off"
                    continue
                window, from_id, max_attempts = (settings.window_start, settings.window_end), settings.from_number_id, settings.max_attempts
            blocked = (await db.execute(
                select(DncEntry.id).where(DncEntry.user_id == job.user_id, DncEntry.e164 == job.e164)
            )).scalar_one_or_none()
            if blocked:
                job.status, job.last_error = "cancelled", "Number is on the do-not-call list"
                continue
            if not in_window(now, *window):
                job.next_attempt_at = next_window_start(now, window[0])
                continue
            wallet = await metering.get_wallet(db, job.user_id)
            if metering.minutes_left(wallet) <= 0:
                job.status, job.last_error = "failed", "No voice minutes left"
                continue
            number = (await db.execute(
                select(PhoneNumber).where(PhoneNumber.id == from_id, PhoneNumber.status == "active")
            )).scalars().first() if from_id else None
            if not number or not number.e164:
                job.status, job.last_error = "failed", "No active number to call from"
                continue
            agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == job.bot_id))).scalars().first()
            detect = number.provider == "twilio" and bool(agent) and (agent.voicemail_action or "off") != "off"

            job.attempts += 1
            job.status = "calling"
            job.next_attempt_at = now  # while calling: when we dialled (see expire_stale_calls)
            if job.campaign_id:
                in_flight[job.campaign_id] += 1
            await db.commit()
            try:
                job.last_error = None
                if number.provider == "twilio":
                    job.provider_call_id = await twilio.place_call(job.e164, number.e164, job.id, **({"detect_voicemail": True} if detect else {}))
                else:
                    job.provider_call_id = await exotel.place_call(job.e164, number.e164, job.id)
            except Exception as e:
                logger.warning(f"Callback {job.id} failed to dial: {e}")
                schedule_retry(job, max_attempts, str(e)[:300])
        await db.commit()


async def finish_campaigns() -> None:
    """A running campaign with nobody left to call is complete."""
    async with async_session() as db:
        running = (await db.execute(select(Campaign).where(Campaign.status == "running"))).scalars().all()
        for campaign in running:
            left = (await db.execute(select(func.count()).select_from(CallbackJob).where(
                CallbackJob.campaign_id == campaign.id, CallbackJob.status.in_(["queued", "calling"])))).scalar()
            if not left:
                campaign.status, campaign.completed_at = "completed", datetime.utcnow()
        await db.commit()


async def max_attempts_for(db, job: CallbackJob) -> int:
    if job.campaign_id:
        campaign = (await db.execute(select(Campaign).where(Campaign.id == job.campaign_id))).scalars().first()
        return campaign.max_attempts if campaign else 1
    settings = (await db.execute(select(CallbackSettings).where(CallbackSettings.user_id == job.user_id))).scalars().first()
    return settings.max_attempts if settings else 1


STALE_CALL = timedelta(minutes=45)


async def expire_stale_calls() -> None:
    """
    A call-back stays "calling" until the call reports back. If that report never arrives
    (provider webhook lost, server restarted mid-call), close it so it can't block new requests.
    """
    cutoff = datetime.utcnow() - STALE_CALL
    async with async_session() as db:
        stuck = (await db.execute(select(CallbackJob).where(
            CallbackJob.status == "calling",
            or_(CallbackJob.next_attempt_at <= cutoff, and_(CallbackJob.next_attempt_at.is_(None), CallbackJob.created_at <= cutoff)),
        ))).scalars().all()
        for job in stuck:
            if job.call_id:
                job.status = "done"
            else:
                job.status, job.last_error = "failed", "No result from the phone provider"
        if stuck:
            await db.commit()
            logger.info(f"Closed {len(stuck)} call-backs that never reported back")


def schedule_retry(job: CallbackJob, max_attempts: int, reason: str) -> None:
    """After a missed or failed attempt: try again later, or give up."""
    job.last_error = reason
    if job.attempts < max(1, max_attempts):
        job.status = "queued"
        job.next_attempt_at = datetime.utcnow() + RETRY_GAP
    else:
        job.status = "failed"


async def purge_expired_recordings() -> None:
    async with async_session() as db:
        settings = (await db.execute(select(ComplianceSettings))).scalars().all()
        retention = {s.user_id: s.retention_days for s in settings}
        cutoff_default = datetime.utcnow() - timedelta(days=90)
        calls = (await db.execute(
            select(CallLog).where(CallLog.started_at < datetime.utcnow() - timedelta(days=30))
        )).scalars().all()
        purged = 0
        for call in calls:
            days = retention.get(call.user_id)
            cutoff = datetime.utcnow() - timedelta(days=days) if days else cutoff_default
            if _naive(call.started_at) >= cutoff or (not call.recording_path and not call.transcript):
                continue
            try:
                await recording.delete(call.recording_path)
            except Exception as e:
                logger.warning(f"Could not delete recording for {call.id}: {e}")
                continue
            call.recording_path, call.transcript = None, []
            purged += 1
        await db.commit()
        if purged:
            logger.info(f"Retention: removed recordings and transcripts for {purged} calls")


async def renew_numbers() -> None:
    """Monthly rent for self-serve numbers: charge, pause when unpaid, release after the grace period."""
    from backend.models import User
    from notify.email import dashboard_url, send_email
    now = datetime.utcnow()
    async with async_session() as db:
        due = (await db.execute(select(PhoneNumber.id).where(
            PhoneNumber.provider == "twilio", PhoneNumber.status.in_(["active", "suspended"]),
            PhoneNumber.next_charge_at <= now,
        ))).scalars().all()
    # One session per number: a failed charge rolls back, which would expire every other loaded row.
    for number_id in due:
        async with async_session() as db:
            number = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id))).scalars().first()
            owner_email = (await db.execute(select(User.email).where(User.id == number.user_id))).scalars().first()
            ref = f"rent:{number.id}:{_naive(number.next_charge_at):%Y%m%d}"
            try:
                await balance.charge(db, number.user_id, (number.monthly_fee or 0) * 100, "number_rental", ref,
                                     f"{number.number} monthly rent")
                number.next_charge_at = _naive(number.next_charge_at) + timedelta(days=30)
                if number.status == "suspended":
                    number.status, number.suspended_at = "active", None
                await db.commit()
                continue
            except balance.InsufficientBalance:
                await db.refresh(number)
            if number.status == "active":
                number.status, number.suspended_at = "suspended", now
                await db.commit()
                if owner_email:
                    await send_email(owner_email, f"Your number {number.number} is paused",
                                     f"We couldn't take this month's ₹{number.monthly_fee} for {number.number}, so it has stopped "
                                     f"answering calls. Add money to your balance within {NUMBER_GRACE_DAYS} days to keep it.\n\n"
                                     f"{dashboard_url()}/dashboard/billing")
            elif number.suspended_at and now - _naive(number.suspended_at) > timedelta(days=NUMBER_GRACE_DAYS):
                try:
                    if number.provider_sid:
                        await twilio.release_number(number.provider_sid)
                except Exception as e:
                    logger.warning(f"Couldn't release {number.number}: {e}")
                    continue
                await db.delete(number)
                await db.commit()
                if owner_email:
                    await send_email(owner_email, f"Your number {number.number} was released",
                                     f"{number.number} was unpaid for {NUMBER_GRACE_DAYS} days, so it has been released.")


async def _loop() -> None:
    last_purge = datetime.min
    while True:
        try:
            from notify import automations
            await automations.process_due()  # automatic customer emails
            if exotel.configured() or twilio.configured():
                await expire_stale_calls()
                await dispatch_due_callbacks()
                await finish_campaigns()
            if datetime.utcnow() - last_purge > timedelta(hours=6):
                await purge_expired_recordings()
                if twilio.configured():
                    await renew_numbers()
                last_purge = datetime.utcnow()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Voice scheduler error: {e}")
        await asyncio.sleep(20)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    if _task:
        _task.cancel()
