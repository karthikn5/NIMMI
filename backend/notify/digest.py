"""
The owner's daily summary (mail plan, phase 1): each morning, what came in yesterday and what's waiting for them today. Off until a
workspace turns it on. A day with nothing to say sends nothing.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.future import select

from backend.models import Bot, CallLog, Contact, Conversation, EmailJob, EmailThread, IntegrationSettings, KnowledgeGap, Meeting, User
from database import async_session
from notify import email

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
HOUR = 9  # sent from this hour, India time


async def figures(db, owner_id: str, now: Optional[datetime] = None) -> dict:
    """Yesterday and today, as the business sees days (India time; stored in UTC)."""
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
    start, end, ends = (d.astimezone(timezone.utc).replace(tzinfo=None) for d in (yesterday, today, tomorrow))
    bots = [b for (b,) in (await db.execute(select(Bot.bot_id).where(Bot.user_id == owner_id))).all()]
    leads = 0
    if bots:
        chats = (await db.execute(select(Conversation.captured_data).where(Conversation.bot_id.in_(bots), Conversation.created_at >= start, Conversation.created_at < end))).scalars().all()
        leads = sum(1 for c in chats if c)
    calls = (await db.execute(select(func.count()).select_from(CallLog).where(
        CallLog.user_id == owner_id, CallLog.channel == "phone", CallLog.started_at >= start, CallLog.started_at < end))).scalar() or 0
    hot = (await db.execute(select(func.count()).select_from(Contact).where(
        Contact.user_id == owner_id, Contact.lead_status == "hot", Contact.lead_at >= start, Contact.lead_at < end))).scalar() or 0
    meetings = (await db.execute(select(func.count()).select_from(Meeting).where(
        Meeting.user_id == owner_id, Meeting.status.in_(("confirmed", "requested")), Meeting.starts_at >= end, Meeting.starts_at < ends))).scalar() or 0
    replies = (await db.execute(select(func.count()).select_from(EmailThread).where(EmailThread.user_id == owner_id, EmailThread.status == "open"))).scalar() or 0
    drafts = (await db.execute(select(func.count()).select_from(EmailJob).where(EmailJob.user_id == owner_id, EmailJob.status == "draft"))).scalar() or 0
    from backend.models import EmailAgentAction
    agent = dict((await db.execute(select(EmailAgentAction.action, func.count()).where(EmailAgentAction.user_id == owner_id, EmailAgentAction.created_at >= start,
                                                                                     EmailAgentAction.created_at < end).group_by(EmailAgentAction.action))).all())
    questions = (await db.execute(select(func.count()).select_from(KnowledgeGap).where(KnowledgeGap.bot_id.in_(bots), KnowledgeGap.status == "open"))).scalar() or 0 if bots else 0
    return {"leads": leads, "calls": calls, "hot": hot, "meetings": meetings, "replies": replies, "drafts": drafts, "questions": questions,
            "agent_emails": agent.get("email", 0), "agent_handovers": agent.get("handover", 0)}


def lines_of(f: dict) -> list[str]:
    def n(count: int, one: str, many: str) -> str:
        return f"{count} {one if count == 1 else many}"
    came = [(f["leads"], n(f["leads"], "new lead", "new leads")), (f["calls"], n(f["calls"], "call", "calls")), (f["hot"], n(f["hot"], "hot lead", "hot leads")),
            (f.get("agent_emails", 0), "the email agent wrote " + n(f.get("agent_emails", 0), "email", "emails")),
            (f.get("agent_handovers", 0), "the email agent handed you " + n(f.get("agent_handovers", 0), "lead", "leads"))]
    waiting = [(f["meetings"], n(f["meetings"], "meeting today", "meetings today")), (f["replies"], n(f["replies"], "reply to answer", "replies to answer")),
               (f["drafts"], n(f["drafts"], "email to approve", "emails to approve")), (f["questions"], n(f["questions"], "question to answer", "questions to answer"))]
    out = []
    if any(c for c, _ in came):
        out += ["Yesterday:", *[f"- {t}" for c, t in came if c], ""]
    if any(c for c, _ in waiting):
        out += ["Waiting for you:", *[f"- {t}" for c, t in waiting if c], ""]
    return out


async def send_one(owner_id: str, to: list[str]) -> Optional[str]:
    async with async_session() as db:
        lines = lines_of(await figures(db, owner_id))
    if not lines:
        return "nothing to say"
    body = "\n".join([*lines, f"Open Nimmi: {email.dashboard_url()}/dashboard"])
    sent = [await email.send_email(a, "Your day on Nimmi", body, tags={"ws": owner_id, "kind": "alert"}) for a in to]
    return None if any(sent) else "email not configured"


async def maybe_send(now: Optional[datetime] = None) -> None:
    """Scheduler: once a day per workspace, from 9 am India time."""
    from notify import events
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    if local.hour < HOUR:
        return
    async with async_session() as db:
        rows = (await db.execute(select(IntegrationSettings, User.email).join(User, User.id == IntegrationSettings.user_id)
                                 .where(IntegrationSettings.alert_daily.is_(True)))).all()
    for settings, owner_email in rows:
        import plans
        async with async_session() as db:
            if not (await plans.workspace_includes(db, settings.user_id)).team_alerts:
                continue
        to = events.recipients(settings, owner_email)
        await events._once(settings.user_id, "daily_summary", f"{settings.user_id}:{local.date().isoformat()}", lambda to=to, owner=settings.user_id: send_one(owner, to))
