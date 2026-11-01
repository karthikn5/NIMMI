"""
Emails coming in (mail plan, phase 2). Resend's `email.received` event says an email arrived and for whom; the row is kept
before Resend gets its answer (each email once, by Resend's id), and the text is then fetched and handled by one process,
right away and, if that process goes down, by the scheduler.

A reply is matched by its address (mail/threads.py). What's new is cut from what it quotes. From the person: follow-ups stop,
the team gets a copy, and the AI reads it (mail/replies.py). From the team, answering the copy from their own mailbox: it goes
on to the person as the business, if the mail server says the sender is real. An email is data, never instructions: it's
kept and shown as text, and only ever answered to the same person.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import EmailJob, EmailThread, ThreadMessage
from database import async_session
from mail import senders, threads
from notify import email

logger = logging.getLogger(__name__)

STUCK = timedelta(minutes=3)
TRIES = 5
TEXT_CHARS = 20_000
MANY = 20   # emails from one conversation in an hour: a loop between two machines, not a person
MACHINE = re.compile(r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply|bounces?|mail-?daemon)([+._-][^@]*)?@", re.I)
AUTO_SUBJECT = re.compile(r"^\s*(auto(matic)?[ -]?(reply|response|answer)|out of (the )?office|ooo\b|on (leave|vacation|holiday)|"
                          r"away from|undeliverable|undelivered|delivery (status|failure)|mail delivery|returned mail|failure notice)", re.I)
QUOTE_START = re.compile(r"^(on\s.{5,160}\swrote:\s*$|-{2,}\s*(original|forwarded) message\s*-{2,}|_{10,}\s*$|"
                         r"from:\s.+@.+|sent from my\s|.{5,160}(எழுதியது|ने लिखा|లిఖించారు|ಬರೆದಿದ್ದಾರೆ|എഴുതി):\s*$)", re.I)


def plain(html_body: Optional[str]) -> str:
    """An HTML email as text: never kept or shown as HTML."""
    soup = BeautifulSoup(html_body or "", "html.parser")
    for tag in soup(["script", "style", "head", "title", "blockquote"]):
        tag.decompose()
    for br in soup.find_all(["br", "p", "div", "tr", "li"]):
        br.append("\n")
    return re.sub(r"\n{3,}", "\n\n", soup.get_text()).strip()


def cut_quoted(text: str) -> str:
    """What's new in an email: without the email it quotes, or a signature line from a phone."""
    kept = []
    for line in (text or "").splitlines():
        if line.lstrip().startswith(">") or QUOTE_START.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def is_automatic(sender: str, subject: str, headers: dict) -> bool:
    """An out-of-office, a delivery report or a mailing machine: never answered, so two machines can't talk for ever."""
    names = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if names.get("auto-submitted", "no").strip() not in ("no", ""):
        return True
    if names.get("precedence", "").strip() in ("bulk", "auto_reply", "list", "junk"):
        return True
    if any(k in names for k in ("x-autoreply", "x-autorespond", "x-auto-response-suppress", "list-id")):
        return True
    return bool(MACHINE.match(sender or "") or AUTO_SUBJECT.match(subject or ""))


def _address(value) -> str:
    found = re.search(r"[^\s<>\"',;]+@[^\s<>\"',;]+", str(value or ""))
    return found.group(0).lower() if found else ""


async def received(data: dict) -> None:
    """Resend's event: an email arrived. Only the address is looked at here."""
    code = threads.code_in([*(data.get("to") or []), *(data.get("cc") or []), *(data.get("received_for") or [])])
    if code is None or not data.get("email_id"):
        logger.info("An email came in that isn't a reply to one of ours; ignored")
        return
    async with async_session() as db:
        thread = (await db.execute(select(EmailThread).where(EmailThread.code == code))).scalars().first()
        if thread is None:
            logger.info("An email came in for a conversation that doesn't exist; ignored")
            return
        row = ThreadMessage(thread_id=thread.id, user_id=thread.user_id, direction="in", who="customer", status="new",
                            provider_id=str(data["email_id"]), message_id=str(data.get("message_id") or "")[:300] or None,
                            sender=_address(data.get("from")), subject=str(data.get("subject") or "")[:300])
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            return  # kept already
        message_id = row.id
    from notify.events import fire_and_forget
    fire_and_forget(_process(message_id))


async def process_due() -> None:
    """Scheduler: emails kept but not handled, because their process went down or Resend wasn't reachable."""
    now = datetime.utcnow()
    async with async_session() as db:
        due = (await db.execute(select(ThreadMessage.id).where(
            ThreadMessage.direction == "in", ThreadMessage.status.in_(("new", "working")),
            ThreadMessage.created_at < now - timedelta(seconds=30),
            or_(ThreadMessage.claimed_at.is_(None), ThreadMessage.claimed_at < now - STUCK)).limit(5))).scalars().all()
    for message_id in due:
        await _process(message_id)


async def fetch(provider_id: str) -> Optional[dict]:
    """The email itself, from Resend: its event carries only who and what about. Sending-only keys can't read it."""
    key = os.getenv("RESEND_API_KEY")
    if not key:
        return None
    try:
        async with email.resend_client() as client:
            resp = await client.get(f"{email.resend_url()}/emails/receiving/{provider_id}", headers={"Authorization": f"Bearer {key}"})
        if resp.status_code >= 300:
            logger.warning(f"Reading received email {provider_id} failed: {resp.status_code} {resp.text[:160]}")
            return None
        return resp.json()
    except Exception as e:
        logger.warning(f"Reading received email {provider_id} failed: {e}")
        return None


async def _process(message_id: str) -> None:
    now = datetime.utcnow()
    async with async_session() as db:
        claimed = await db.execute(update(ThreadMessage).where(
            ThreadMessage.id == message_id, ThreadMessage.status.in_(("new", "working")),
            or_(ThreadMessage.claimed_at.is_(None), ThreadMessage.claimed_at < now - STUCK))
            .values(status="working", claimed_at=now, attempts=ThreadMessage.attempts + 1).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        row = await db.get(ThreadMessage, message_id)
        provider_id, attempts = row.provider_id, row.attempts or 0
    fetched = await fetch(provider_id)  # no connection is held while Resend answers
    async with async_session() as db:
        row = await db.get(ThreadMessage, message_id)
        if fetched is None:
            row.status, row.claimed_at = ("failed", None) if attempts >= TRIES else ("new", None)
            row.note = "Couldn't read this email from Resend" if attempts >= TRIES else None
            await db.commit()
            return
        thread = await db.get(EmailThread, row.thread_id)
        await _keep(db, row, thread, fetched)
        team = await _from_team(db, row, thread)
        if team:
            row.who, row.direction, row.status = "team", "out", "working"
        else:
            await _their_reply(db, row, thread)
        await db.commit()
        thread_id = thread.id
    from mail import replies
    try:
        if team:
            await replies.relay(thread_id, message_id)
        else:
            await forward(thread_id, message_id)
            await replies.answer(message_id)
    except Exception as e:
        logger.exception(f"Handling reply {message_id} failed: {e}")


async def _keep(db, row: ThreadMessage, thread: EmailThread, fetched: dict) -> None:
    text = fetched.get("text") or plain(fetched.get("html"))
    headers = fetched.get("headers") if isinstance(fetched.get("headers"), dict) else {}
    row.sender = _address(fetched.get("from")) or row.sender
    row.subject = str(fetched.get("subject") or row.subject or "")[:300]
    row.message_id = str(fetched.get("message_id") or row.message_id or "")[:300] or None
    row.text = cut_quoted(text)[:TEXT_CHARS] or text[:TEXT_CHARS]
    row.authentication = fetched.get("authentication") if isinstance(fetched.get("authentication"), dict) else None
    row.attachments = [{k: a.get(k) for k in ("id", "filename", "content_type", "size")}
                       for a in fetched.get("attachments") or [] if isinstance(a, dict)] or None
    since = datetime.utcnow() - timedelta(hours=1)
    many = len((await db.execute(select(ThreadMessage.id).where(
        ThreadMessage.thread_id == thread.id, ThreadMessage.direction == "in", ThreadMessage.created_at >= since))).all())
    row.automatic = is_automatic(row.sender, row.subject, headers) or many > MANY


async def _from_team(db, row: ThreadMessage, thread: EmailThread) -> bool:
    """The team answering the copy from their own mailbox. It has to be really from them: the mail server's check, which a
    sender can't forge. Someone testing with their own address is the person in the conversation, not the team."""
    if row.sender == thread.email or row.automatic:
        return False
    if row.sender not in await threads.team_addresses(db, thread.user_id, thread.bot_id):
        return False
    results = row.authentication or {}
    return "pass" in (results.get("dkim"), results.get("spf"))


async def _their_reply(db, row: ThreadMessage, thread: EmailThread) -> None:
    row.status, row.claimed_at = "received", None
    if row.automatic:
        row.kind, row.note = "auto_reply", "An automatic message: not answered"
        return
    thread.status, thread.unread, thread.last_at = "open", (thread.unread or 0) + 1, datetime.utcnow()
    thread.subject = row.subject or thread.subject
    if row.message_id:
        thread.last_message_id = row.message_id
        thread.reference_ids = [*(thread.reference_ids or []), row.message_id][-20:]
    # They answered, so nothing else goes out by itself.
    jobs = (await db.execute(select(EmailJob).where(
        EmailJob.user_id == thread.user_id, EmailJob.status == "queued", EmailJob.broadcast_id.is_(None), EmailJob.step > 1,
        EmailJob.to_email.ilike(thread.email)))).scalars().all()
    for job in jobs:
        job.status, job.error = "cancelled", "They replied"


async def forward(thread_id: str, message_id: str) -> None:
    """A copy for the business's own mailbox, as before Nimmi received replies. Answering it goes through Nimmi."""
    async with async_session() as db:
        thread = await db.get(EmailThread, thread_id)
        row = await db.get(ThreadMessage, message_id)
        if row.automatic:
            return
        sender = await senders.sender_for(db, thread.user_id, thread.bot_id)
    mailbox = (sender.reply_to or "").lower()
    if not mailbox or mailbox == thread.email:
        return
    who = thread.name or thread.email
    link = f"{email.dashboard_url()}/dashboard/email/inbox?thread={thread_id}"
    body = f"{who} ({thread.email}) wrote:\n\n{row.text}\n\nAnswer by replying to this email, or in Nimmi: {link}"
    await email.send_email(mailbox, f"{row.subject or 'A reply'}", body, reply_to=threads.address(thread), from_name=f"{who} via Nimmi",
                           from_address=sender.address, api_key=sender.api_key, tags={"ws": thread.user_id, "kind": "alert"})
