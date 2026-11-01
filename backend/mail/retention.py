"""
How long the words of emails are kept (mail plan 5.2, phase 9): each business picks 6, 12, 24 or 36 months, 12 by default. After that the text goes, and the record that an email was sent stays
(who, when, what happened). Consent, unsubscribes and bounces aren't touched: they are the proof that the business kept its word. Compliance > Erase removes one person's emails at any time.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, not_, or_, update
from sqlalchemy.future import select

from backend.models import EmailAgentAction, EmailClick, EmailJob, EmailLink, EmailThread, IntegrationSettings, LeadIntake, ThreadMessage
from database import async_session

logger = logging.getLogger(__name__)

CHOICES = (6, 12, 24, 36)
DEFAULT_MONTHS = 12
GONE = "(the text is no longer kept)"
WAITING = ("queued", "draft", "held", "sending")


async def erase(db, owner_id: str, addresses: list[str]) -> None:
    """Compliance > Erase: everything written to or by these people. The caller commits. An unsubscribe or a bounce stays: it's what keeps them from being emailed again."""
    theirs = select(EmailJob.id).where(EmailJob.user_id == owner_id, func.lower(EmailJob.to_email).in_(addresses))
    await db.execute(delete(EmailClick).where(EmailClick.user_id == owner_id, EmailClick.job_id.in_(theirs)))
    await db.execute(delete(EmailLink).where(EmailLink.user_id == owner_id, EmailLink.job_id.in_(theirs)))
    await db.execute(delete(EmailJob).where(EmailJob.user_id == owner_id, func.lower(EmailJob.to_email).in_(addresses)))
    threads = (await db.execute(select(EmailThread.id).where(EmailThread.user_id == owner_id, func.lower(EmailThread.email).in_(addresses)))).scalars().all()
    if threads:
        await db.execute(delete(ThreadMessage).where(ThreadMessage.thread_id.in_(threads)))
        await db.execute(delete(EmailThread).where(EmailThread.id.in_(threads)))


async def erase_leads(db, owner_id: str, contact_ids: list[str]) -> None:
    """The emails and forms a contact's lead came in on."""
    if contact_ids:
        await db.execute(delete(LeadIntake).where(LeadIntake.user_id == owner_id, LeadIntake.contact_id.in_(contact_ids)))


async def _clear(db, cutoff: datetime, in_scope) -> int:
    """`in_scope(model)`: which workspaces, as a condition on that table's user_id."""
    done = await db.execute(update(EmailJob).where(in_scope(EmailJob), EmailJob.created_at < cutoff, EmailJob.status.notin_(WAITING), EmailJob.body != GONE)
                            .values(subject=GONE, body=GONE, subject_tpl=None, body_tpl=None, merge_data=None).execution_options(synchronize_session=False))
    said = await db.execute(update(ThreadMessage).where(in_scope(ThreadMessage), ThreadMessage.created_at < cutoff, ThreadMessage.status != "draft",
                                                        or_(ThreadMessage.text != GONE, ThreadMessage.text.is_(None)))
                            .values(text=GONE, attachments=None).execution_options(synchronize_session=False))
    await db.execute(update(LeadIntake).where(in_scope(LeadIntake), LeadIntake.created_at < cutoff, LeadIntake.raw.isnot(None)).values(raw=None).execution_options(synchronize_session=False))
    await db.execute(delete(EmailAgentAction).where(in_scope(EmailAgentAction), EmailAgentAction.created_at < cutoff).execution_options(synchronize_session=False))
    return done.rowcount + said.rowcount


async def purge(now: Optional[datetime] = None) -> int:
    """Scheduler. Safe to run in every process: what's gone is left alone."""
    now = now or datetime.utcnow()
    cleared = 0
    async with async_session() as db:
        chosen = dict((await db.execute(select(IntegrationSettings.user_id, IntegrationSettings.email_keep_months).where(IntegrationSettings.email_keep_months.isnot(None)))).all())
        for months in set(chosen.values()):
            owners = [o for o, m in chosen.items() if m == months]
            cleared += await _clear(db, now - timedelta(days=30 * months), lambda model: model.user_id.in_(owners))
        cleared += await _clear(db, now - timedelta(days=30 * DEFAULT_MONTHS), lambda model: not_(model.user_id.in_(list(chosen) or [""])))
        await db.commit()
    if cleared:
        logger.info(f"Email text past its time cleared from {cleared} rows")
    return cleared
