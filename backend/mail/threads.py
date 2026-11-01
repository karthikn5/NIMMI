"""
Conversations by email (mail plan, phase 2). Each person has one conversation per assistant, with its own reply address
(r-<code>@REPLY_DOMAIN): customer emails carry it as their Reply-To, so a reply comes back to Nimmi, wherever the email
was sent from. REPLY_DOMAIN is a domain receiving at Resend (mail.nimmiai.in); without it, replies go straight to the
business's own mailbox, as before.
"""
import os
import re
import secrets
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.future import select

from backend.models import EmailJob, EmailThread, IntegrationSettings, TeamMember, ThreadMessage, User
from mail import senders


def reply_domain() -> str:
    return os.getenv("REPLY_DOMAIN", "").strip().lower()


def enabled() -> bool:
    return bool(reply_domain())


def address(thread: EmailThread) -> str:
    return f"r-{thread.code}@{reply_domain()}"


def code_in(addresses: Iterable) -> Optional[str]:
    """The conversation's code in the addresses an email was sent to."""
    domain = re.escape(reply_domain())
    for value in addresses:
        found = re.search(rf"\br-([a-f0-9]{{8,24}})@{domain}\b", str(value or "").lower()) if domain else None
        if found:
            return found.group(1)
    return None


async def thread_for(db, owner_id: str, bot_id: Optional[str], to: str, name: Optional[str] = None,
                     subject: Optional[str] = None) -> EmailThread:
    """Their conversation with this assistant, made if it's new (the caller commits)."""
    to = to.strip().lower()
    found = (await db.execute(select(EmailThread).where(
        EmailThread.user_id == owner_id, EmailThread.bot_id == bot_id if bot_id else EmailThread.bot_id.is_(None),
        EmailThread.email == to).order_by(EmailThread.created_at))).scalars().first()
    if found is None:
        found = EmailThread(user_id=owner_id, bot_id=bot_id, code=secrets.token_hex(8), email=to, status="quiet", unread=0, reference_ids=[])
        db.add(found)
        await db.flush()
    named = str(name or "").strip()
    if named and named != "there":
        found.name = named[:120]
    found.subject = (subject or found.subject or "")[:300] or None
    return found


def note_sent(db, thread: EmailThread, job: EmailJob) -> None:
    """An automatic email went out: it's part of the conversation."""
    db.add(ThreadMessage(thread_id=thread.id, user_id=thread.user_id, direction="out", who="nimmi", status="sent", job_id=job.id,
                         subject=job.subject[:300], text=job.body))
    thread.last_at = datetime.utcnow()


async def team_addresses(db, owner_id: str, bot_id: Optional[str]) -> set[str]:
    """The addresses that answer for this business: its people, its alert addresses and where its replies went."""
    found: set[str] = set()
    owner = (await db.execute(select(User.email).where(User.id == owner_id))).scalar_one_or_none()
    found.add(owner or "")
    found |= {e for (e,) in (await db.execute(select(TeamMember.email).where(TeamMember.owner_id == owner_id, TeamMember.status == "active"))).all()}
    settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    found |= set(re.split(r"[,;\s]+", (settings.alert_email or "") if settings else ""))
    found.add((await senders.sender_for(db, owner_id, bot_id, settings)).reply_to or "")
    return {a.strip().lower() for a in found if a and a.strip()}
