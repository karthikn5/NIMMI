"""
What the business promised a person (instagram_plan.md, phase 7): to send a brochure or photos, share a price, call back, arrange a visit, anything it said
it would do. Each promise stays open until a record shows it was done, never because the AI said so.

Where promises come from:
- A phone call: the after-call analysis (voice/llm.py summarize) lists the assistant's promises, each with the words it used, and a call-back it agreed to
  is one too. No extra model call.
- A chat (website, WhatsApp, Instagram) or an email conversation that has been quiet for half an hour: one model call reads what the business wrote since
  the last look. Each conversation is claimed first, so one server process reads it once.
- The team, on the lead's page.
A promise the AI finds must quote the business's own words, and the quote must really be in what the business said: one that isn't is dropped (models
invent). Only leads get promises: a chat that never became a lead has nobody to keep them for.

What closes one, from the records after it was made (`evidence`): a call-back by an outgoing call they talked on, or a team member's "Spoke to them"; something
to send by a file sent on WhatsApp or a file in an email; a price by a message or email with an amount in it, or a file; a visit by a confirmed meeting. Anything
else, or anything done outside Nimmi, by a team member choosing what did it on the lead's page, or writing down what they did. A lead closed as lost cancels
what's open; a customer still gets what they were promised. A call-back to someone on the do-not-call list is cancelled.
"""
import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.future import select

from backend.models import (Bot, CallLog, Contact, Conversation, EmailJob, EmailLink, EmailThread, LeadEvent, LeadPromise, Meeting, Message, ThreadMessage, WhatsAppChat,
                            WhatsAppMessage)
from database import async_session

logger = logging.getLogger(__name__)

KINDS = {"send": "Send something", "price": "Share a price", "callback": "Call them back", "visit": "Arrange a visit or meeting", "other": "Something else"}
MADE_ON = {"call": "on a phone call", "chat": "in the website chat", "whatsapp": "on WhatsApp", "instagram": "on Instagram", "email": "by email", "team": "by the team"}
HOW = {"call": "Called them", "whatsapp": "On WhatsApp", "email": "By email", "visit": "In person", "other": "Other"}
QUIET = timedelta(minutes=30)        # a conversation this quiet is read for promises
RECENT = timedelta(days=7)           # older conversations and messages aren't read
DEFAULT_DUE = timedelta(days=1)      # a promise without a time is expected within a day
LATEST_DUE = timedelta(days=60)      # a time further away than this is taken as a misreading
CHECK_EVERY = timedelta(minutes=2)   # how often an open promise's records are looked through
REMIND_WITHIN = timedelta(days=3)    # a promise this long overdue gets no reminder any more (it's on Needs attention)
PASS_EVERY = timedelta(seconds=60)
BATCH, SETTLE_BATCH, PER_SCAN, OPEN_LIMIT = 10, 50, 5, 20
AI_SECONDS = 45
FILE_KINDS = ("document", "image", "video", "audio")
SENT = ("sent", "delivered", "read")
TALKED = ("answered", "lead_captured")
SPOKE = "Spoke to them"              # leads/core.py RESULTS["reached"]: the team reached them
PRICE_FILE = re.compile(r"price|quot|rate|cost|tariff|fee|estimate|விலை|கட்டண|कीमत|दाम|शुल्क", re.I)  # a file that is a price list or a quotation, by its name
_last_pass: Optional[datetime] = None

READ = ("You read a business's conversation with a customer and list what the business promised to do for them later: send something (a brochure, photos, "
        "details), share a price or quote, call them back, arrange a visit or meeting, or anything else it said it would do. Only the business's promises (its "
        "lines start with \"Business:\"), only what is still to happen after it said so: never what the customer said they would do, never general facts such as "
        "opening hours. Reply with JSON only: {\"promises\": [{\"kind\": \"send\" | \"price\" | \"callback\" | \"visit\" | \"other\", \"what\": what was promised "
        "in a few words, \"due\": \"YYYY-MM-DD HH:MM\" or \"YYYY-MM-DD\" if a time or day was said, else null, \"words\": the business's own words that promised "
        "it, copied exactly}]}, with an empty list when nothing was promised. The last business message was sent NOW_TEXT. NEXT_DAYS")

# An amount of money, in the ways Indian businesses write one (digits in any script are read as digits first).
MONEY = re.compile(r"₹\s*\d|\b(?:rs\.?|inr)\s*\d|\d[\d,.]*\s*(?:rupees?|lakhs?|lacs?|crores?|cr\b|k\b|/-|ரூபாய்|லட்சம்|கோடி|रुपय|रुपए|लाख|करोड़)"
                   r"|\d{1,3}(?:,\d{2})*,\d{3}", re.I)


def now() -> datetime:
    return datetime.utcnow()


def utc(at: Optional[datetime]) -> Optional[datetime]:
    if at is None:
        return None
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)


def stored(at: datetime) -> datetime:
    return utc(at).replace(tzinfo=None)


def _norm(text: Optional[str]) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(str.maketrans("‘’“”", "''\"\""))
    return re.sub(r"\s+", " ", text).casefold().strip(" .,!?;:\"'")


def quoted(words: Optional[str], said: list[str]) -> Optional[int]:
    """Which of the business's messages has these words in it (the index), or None: a quote that isn't really there."""
    wanted = _norm(words)
    if len(wanted) < 8:
        return None
    return next((i for i, s in enumerate(said) if wanted in _norm(s)), None)


def _digits(text: str) -> str:
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in text or "")


def has_amount(text: Optional[str]) -> bool:
    return bool(MONEY.search(_digits(text or "")))


def _due(value, made_at: datetime, tz) -> tuple[datetime, bool]:
    """(when it's due, whether a time was said). A day alone means that day at 6 pm, the business's time, or its end when 6 pm has gone ("this evening"
    said at 9 pm); anything unreadable or far off, a day after."""
    text = str(value or "").strip().replace("T", " ")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?: (\d{1,2}):(\d{2}))?$", text)
    if m:
        try:
            at = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 18), int(m[5] or 0), tzinfo=tz).astimezone(timezone.utc)
            if m[4] is None and at < utc(made_at):
                at = datetime(int(m[1]), int(m[2]), int(m[3]), 23, 59, tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            at = None
        if at is not None and utc(made_at) - timedelta(hours=1) <= at <= utc(made_at) + LATEST_DUE:
            return at, True
    return utc(made_at) + DEFAULT_DUE, False


def clean_found(found, said: list[str], made_at: datetime, tz, kinds=tuple(KINDS)) -> list[dict]:
    """The model's promises, kept only with a real quote from what the business said: [{kind, what, due_at, due_said, words, said_in}]."""
    out = []
    for p in found if isinstance(found, list) else []:
        if not isinstance(p, dict):
            continue
        kind, what = str(p.get("kind") or "").strip().lower(), re.sub(r"\s+", " ", str(p.get("what") or "")).strip()
        where = quoted(p.get("words"), said)
        if kind not in kinds or not what or where is None:
            continue
        due_at, due_said = _due(p.get("due"), made_at, tz)
        out.append({"kind": kind, "what": what[:200], "due_at": due_at, "due_said": due_said, "words": str(p.get("words")).strip()[:600], "said_in": where})
    return out[:PER_SCAN]


async def _zone(db, bot_id: str):
    from voice import schedule
    return schedule.zone(await schedule.settings_for(bot_id, db))


def _same(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return a == b or (len(a) >= 6 and len(b) >= 6 and (a in b or b in a))


async def add(db, contact: Contact, items: list[dict], made_on: str, ref: Optional[str], made_at: datetime, made_by: Optional[str] = None,
              authors: Optional[list] = None) -> list[LeadPromise]:
    """Keep these promises on the lead (the caller commits). The same promise again isn't kept twice; a call-back said again moves the open one's time."""
    from leads import core
    if contact is None or not items:
        return []
    open_ = (await db.execute(select(LeadPromise).where(LeadPromise.contact_id == contact.id, LeadPromise.status == "open"))).scalars().all()
    made = []
    for item in items:
        twin = next((p for p in open_ if p.kind == item["kind"] and (item["kind"] == "callback" or _same(p.what, item["what"]))), None)
        if twin is not None:
            if item["kind"] == "callback" and item.get("due_said") and stored(item["due_at"]) != twin.due_at:
                twin.due_at, twin.due_said, twin.reminded_at = stored(item["due_at"]), True, None
            continue
        if len(open_) >= OPEN_LIMIT:
            break
        by = made_by or ((authors or [None])[item["said_in"]] if item.get("said_in") is not None and authors else None)
        p = LeadPromise(user_id=contact.user_id, bot_id=contact.bot_id, contact_id=contact.id, kind=item["kind"], what=item["what"][:200], words=item.get("words"),
                        made_at=stored(made_at), made_on=made_on, made_by=by, ref=(ref or "")[:64] or None, due_at=stored(item["due_at"]),
                        due_said=bool(item.get("due_said")), status="open")
        db.add(p)
        open_.append(p)
        made.append(p)
        db.add(core.event(contact, "promise", f"Promised {MADE_ON.get(made_on, made_on)}: {p.what}" if made_on != "team" else f"Promised: {p.what}", by))
    return made


# ─── where promises come from ────────────────────────────────────
async def from_call(call_id: str) -> int:
    """After a phone call: the assistant's promises (the analysis found them; each quote checked against what the assistant said) and a call-back it agreed
    to. A test call from the dashboard makes none. Best effort; never raises. How many were kept."""
    from voice import schedule
    try:
        async with async_session() as db:
            call = await db.get(CallLog, call_id)
            if call is None or call.channel != "phone" or not call.bot_id or not call.caller_e164 or (call.consent_source or "").startswith(schedule.TEST_CALL):
                return 0
            step = call.next_step or {}
            if not step.get("promises") and not step.get("call_back_at"):
                return 0
            contact = (await db.execute(select(Contact).where(Contact.bot_id == call.bot_id, Contact.e164 == call.caller_e164))).scalars().first()
            if contact is None:
                return 0
            tz = await _zone(db, call.bot_id)
            made_at = utc(call.ended_at or call.started_at) or utc(now())
            said = [str(t.get("text") or "") for t in call.transcript or [] if t.get("speaker") == "agent"]
            items = clean_found(step.get("promises"), said, made_at, tz, kinds=("send", "price", "visit", "other"))
            if step.get("call_back_at"):
                due_at, due_said = _due(step["call_back_at"], made_at, tz)
                items.append({"kind": "callback", "what": "Call them back", "due_at": due_at, "due_said": due_said, "words": None})
            made = await add(db, contact, items, "call", call.id, made_at)
            await db.commit()
            return len(made)
    except Exception as e:  # noqa: BLE001  the call's other steps go on
        logger.warning(f"Promises from call {call_id} failed: {e}")
        return 0


def next_days(local: datetime) -> str:
    """The dates of the coming week by name: models turn "Sunday" into a date wrongly (a real Tanglish chat, 3 Nov 2026, got last Sunday)."""
    days = [local + timedelta(days=i) for i in range(1, 8)]
    return "The coming days: " + ", ".join(f"{d:%A} {d.day} {d:%B} is {d:%Y-%m-%d}" for d in days) + "."


async def _ask(lines: str, made_at: datetime, tz) -> Optional[list]:
    """One model call: the promises in a conversation, or None when no model answered."""
    import ai
    local = utc(made_at).astimezone(tz)
    prompt = READ.replace("NOW_TEXT", f"on {local:%A} {local.day} {local:%B %Y} at {local:%H:%M}").replace("NEXT_DAYS", next_days(local))
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(ai.chat, prompt, [{"role": "user", "content": lines}], provider="groq", json_mode=True,
                                                       max_tokens=600, temperature=0.1), AI_SECONDS)
    except (ai.AIError, asyncio.TimeoutError) as e:
        logger.info(f"Reading promises skipped: {e}")
        return None
    match = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        return None
    found = data.get("promises") if isinstance(data, dict) else None
    return found if isinstance(found, list) else []


def _channel(session: Optional[str]) -> str:
    return "whatsapp" if (session or "").startswith("wa:") else "instagram" if (session or "").startswith("ig:") else "chat"


async def _scan_chat(conversation_id: str, at: datetime) -> int:
    import plans
    async with async_session() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or not conv.contact_id or conv.last_message_at is None:
            return 0
        before, last = conv.promises_at, conv.last_message_at
        same = Conversation.promises_at.is_(None) if before is None else Conversation.promises_at == before
        claimed = await db.execute(update(Conversation).where(Conversation.conversation_id == conversation_id, same).values(promises_at=last)
                                   .execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return 0  # another process has it
        since = max(utc(before), utc(at) - RECENT) if before is not None else utc(at) - RECENT
        rows = (await db.execute(select(Message).where(Message.conversation_id == conversation_id, Message.role.in_(("user", "assistant")),
                                                       Message.timestamp > stored(since), Message.timestamp <= last)
                                 .order_by(Message.timestamp.desc()).limit(40))).scalars().all()
        rows.reverse()
        business = [m for m in rows if m.role == "assistant"]
        bot = await db.get(Bot, conv.bot_id) if conv.bot_id else None
        if not business or bot is None or (await plans.includes(db, bot.bot_id)).tier is None:  # reading chats with AI comes with a plan
            return 0
        tz = await _zone(db, bot.bot_id)
        contact_id, session = conv.contact_id, conv.visitor_session_id
    lines = "\n".join(f"{'Business' if m.role == 'assistant' else 'Customer'}: {m.content[:600]}" for m in rows)
    made_at = utc(business[-1].timestamp) or utc(at)
    found = await _ask(lines, made_at, tz)
    items = clean_found(found, [m.content for m in business], made_at, tz)
    if not items:
        return 0
    async with async_session() as db:
        contact = await db.get(Contact, contact_id)
        made = await add(db, contact, items, _channel(session), conversation_id, made_at, authors=[m.author_id for m in business])
        await db.commit()
    return len(made)


async def _scan_thread(thread_id: str, at: datetime) -> int:
    import plans
    async with async_session() as db:
        thread = await db.get(EmailThread, thread_id)
        if thread is None or not thread.bot_id:
            return 0
        before, last = thread.promises_at, thread.last_at
        same = EmailThread.promises_at.is_(None) if before is None else EmailThread.promises_at == before
        claimed = await db.execute(update(EmailThread).where(EmailThread.id == thread_id, same).values(promises_at=last).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return 0
        seen = list(thread.promises_seen or [])
        rows = (await db.execute(select(ThreadMessage).where(ThreadMessage.thread_id == thread_id, ThreadMessage.created_at > stored(utc(at) - RECENT))
                                 .order_by(ThreadMessage.created_at.desc()).limit(20))).scalars().all()
        rows.reverse()
        business = [m for m in rows if m.direction == "out" and m.who in ("ai", "team") and m.status == "sent" and m.id not in seen and (m.text or "").strip()]
        contact = (await db.execute(select(Contact).where(Contact.bot_id == thread.bot_id, func.lower(Contact.email) == (thread.email or "").lower())
                                    .order_by(Contact.created_at))).scalars().first()
        thread.promises_seen = (seen + [m.id for m in business])[-100:]
        await db.commit()
        if not business or contact is None or (await plans.includes(db, thread.bot_id)).tier is None:
            return 0
        tz = await _zone(db, thread.bot_id)
        contact_id = contact.id
    gone = [m for m in rows if (m.text or "").strip() and (m.direction == "in" or m.status == "sent")]  # a draft hasn't gone yet
    lines = "\n".join(f"{'Business' if m.direction == 'out' else 'Customer'}: {(m.text or '')[:1500]}" for m in gone)
    made_at = utc(business[-1].created_at) or utc(at)
    found = await _ask(lines, made_at, tz)
    items = clean_found(found, [m.text or "" for m in business], made_at, tz)
    if not items:
        return 0
    async with async_session() as db:
        contact = await db.get(Contact, contact_id)
        made = await add(db, contact, items, "email", thread_id, made_at, authors=[m.by for m in business])
        await db.commit()
    return len(made)


async def scan(at: Optional[datetime] = None) -> None:
    """Conversations with a lead that have gone quiet since they were last read: chats, then email conversations."""
    at = at or now()
    async with async_session() as db:
        chats = (await db.execute(select(Conversation.conversation_id).where(
            Conversation.contact_id.isnot(None), Conversation.last_message_at.isnot(None),
            Conversation.last_message_at < stored(utc(at) - QUIET), Conversation.last_message_at > stored(utc(at) - RECENT),
            or_(Conversation.promises_at.is_(None), Conversation.promises_at < Conversation.last_message_at))
            .order_by(Conversation.last_message_at).limit(BATCH))).scalars().all()
        threads = (await db.execute(select(EmailThread.id).where(
            EmailThread.bot_id.isnot(None), EmailThread.last_at < stored(utc(at) - QUIET), EmailThread.last_at > stored(utc(at) - RECENT),
            or_(EmailThread.promises_at.is_(None), EmailThread.promises_at < EmailThread.last_at)).order_by(EmailThread.last_at).limit(BATCH))).scalars().all()
    for conversation_id in chats:
        try:
            await _scan_chat(conversation_id, at)
        except Exception as e:  # noqa: BLE001  one conversation's trouble never stops the others
            logger.warning(f"Reading promises in conversation {conversation_id} failed: {e}")
    for thread_id in threads:
        try:
            await _scan_thread(thread_id, at)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Reading promises in email conversation {thread_id} failed: {e}")


# ─── evidence ────────────────────────────────────────────────────
async def _chats_of(db, contact: Contact) -> tuple[list[str], list[str]]:
    """(the lead's conversations, its WhatsApp chats): by the lead, and on WhatsApp also by its number."""
    convs = list((await db.execute(select(Conversation.conversation_id).where(Conversation.contact_id == contact.id))).scalars().all())
    digits = re.sub(r"\D", "", contact.e164 or "")
    q = select(WhatsAppChat.id, WhatsAppChat.conversation_id).where(WhatsAppChat.bot_id == contact.bot_id)
    q = q.where(or_(WhatsAppChat.conversation_id.in_(convs), WhatsAppChat.wa_id == digits)) if digits else q.where(WhatsAppChat.conversation_id.in_(convs))
    chats = (await db.execute(q)).all() if convs or digits else []
    for _, conv in chats:
        if conv and conv not in convs:
            convs.append(conv)
    return convs, [c for c, _ in chats]


def _ev(kind: str, row_id: str, at, text: str) -> dict:
    return {"kind": kind, "id": row_id, "at": utc(at).isoformat() if at else None, "text": text[:300]}


def _when(at, tz) -> str:
    local = utc(at).astimezone(tz)
    return f"{local:%a} {local.day} {local:%b}, {local:%H:%M}"


async def actions(db, p: LeadPromise, contact: Contact) -> list[dict]:
    """Everything done for this person since the promise, newest first: what a team member can choose as the evidence, and what `evidence` looks through."""
    made, out = p.made_at, []
    tz = await _zone(db, contact.bot_id)
    convs, chats = await _chats_of(db, contact)
    if contact.e164:
        for c in (await db.execute(select(CallLog).where(CallLog.bot_id == contact.bot_id, CallLog.caller_e164 == contact.e164, CallLog.started_at > made)
                                   .order_by(CallLog.started_at.desc()).limit(10))).scalars().all():
            talked = c.outcome in TALKED and any(t.get("speaker") == "caller" and str(t.get("text") or "").strip() for t in c.transcript or [])
            words = f"{'Outgoing' if c.direction == 'outbound' else 'Incoming'} call, {_when(c.started_at, tz)}" + ("" if talked else f" ({c.outcome or 'not answered'})")
            out.append({**_ev("call", c.id, c.started_at, words), "outgoing": c.direction == "outbound", "talked": talked})
        for m in (await db.execute(select(Meeting).where(Meeting.bot_id == contact.bot_id, Meeting.e164 == contact.e164,
                                                         func.coalesce(Meeting.decided_at, Meeting.created_at) > made).limit(5))).scalars().all():
            out.append({**_ev("meeting", m.id, m.decided_at or m.created_at, f"Meeting for {_when(m.starts_at, tz)} ({m.status})"), "confirmed": m.status in ("confirmed", "attended")})
    if chats:
        for w in (await db.execute(select(WhatsAppMessage).where(WhatsAppMessage.chat_id.in_(chats), WhatsAppMessage.direction == "out",
                                                                 WhatsAppMessage.kind.in_(FILE_KINDS), WhatsAppMessage.status.in_(SENT), WhatsAppMessage.created_at > made)
                                   .order_by(WhatsAppMessage.created_at.desc()).limit(10))).scalars().all():
            name = (w.media or {}).get("filename") or (w.media or {}).get("caption") or w.kind
            out.append({**_ev("whatsapp_file", w.id, w.created_at, f"File sent on WhatsApp: {name}"), "file": True,
                        "amount": bool(PRICE_FILE.search(f"{name} {(w.media or {}).get('caption') or ''}"))})
    if convs:
        sessions = dict((await db.execute(select(Conversation.conversation_id, Conversation.visitor_session_id).where(Conversation.conversation_id.in_(convs)))).all())
        for m in (await db.execute(select(Message).where(Message.conversation_id.in_(convs), Message.role == "assistant", Message.timestamp > made)
                                   .order_by(Message.timestamp.desc()).limit(15))).scalars().all():
            where = {"chat": "in the website chat", "whatsapp": "on WhatsApp", "instagram": "on Instagram"}[_channel(sessions.get(m.conversation_id))]
            out.append({**_ev("message", m.id, m.timestamp, f"Sent {where}: {m.content[:140]}"), "amount": has_amount(m.content)})
    if contact.email:
        for j in (await db.execute(select(EmailJob).where(EmailJob.user_id == contact.user_id, func.lower(EmailJob.to_email) == contact.email.lower(),
                                                          or_(EmailJob.bot_id == contact.bot_id, EmailJob.bot_id.is_(None)), EmailJob.broadcast_id.is_(None),
                                                          EmailJob.status == "sent", EmailJob.sent_at > made).order_by(EmailJob.sent_at.desc()).limit(10))).scalars().all():
            files = (await db.execute(select(EmailLink.label).where(EmailLink.job_id == j.id, EmailLink.kind == "file").limit(5))).scalars().all()
            out.append({**_ev("email", j.id, j.sent_at, f"Email: {j.subject}" + (f" (with {', '.join(f or 'a file' for f in files)})" if files else "")), "file": bool(files),
                        "amount": has_amount(f"{j.subject} {j.body}") or any(PRICE_FILE.search(f or "") for f in files)})
        thread_ids = (await db.execute(select(EmailThread.id).where(EmailThread.bot_id == contact.bot_id, EmailThread.email == contact.email.lower()))).scalars().all()
        if thread_ids:
            for t in (await db.execute(select(ThreadMessage).where(ThreadMessage.thread_id.in_(thread_ids), ThreadMessage.direction == "out", ThreadMessage.status == "sent",
                                                                   ThreadMessage.who.in_(("ai", "team")), ThreadMessage.created_at > made)
                                       .order_by(ThreadMessage.created_at.desc()).limit(10))).scalars().all():
                out.append({**_ev("email_reply", t.id, t.created_at, f"Email reply: {(t.text or '')[:140]}"), "amount": has_amount(t.text)})
    for e in (await db.execute(select(LeadEvent).where(LeadEvent.contact_id == contact.id, LeadEvent.kind == "result", LeadEvent.by.isnot(None), LeadEvent.at > made)
                               .order_by(LeadEvent.at.desc()).limit(10))).scalars().all():
        out.append({**_ev("result", e.id, e.at, e.text or "A result the team recorded"), "reached": (e.text or "").startswith(SPOKE)})
    return sorted(out, key=lambda a: a["at"] or "", reverse=True)


def proves(p: LeadPromise, a: dict) -> bool:
    """Whether this record alone shows the promise was kept (what `settle` closes by itself)."""
    if p.kind == "callback":
        return (a["kind"] == "call" and a.get("outgoing") and a.get("talked")) or (a["kind"] == "result" and a.get("reached"))
    if p.kind == "send":
        return bool(a.get("file"))
    if p.kind == "price":  # an amount, or a price list or quotation sent: any file at all wouldn't show the price was shared
        return bool(a.get("amount"))
    if p.kind == "visit":
        return a["kind"] == "meeting" and bool(a.get("confirmed"))
    return False


async def evidence(db, p: LeadPromise, contact: Contact) -> Optional[dict]:
    """The earliest record that shows it was done, or None."""
    found = [a for a in await actions(db, p, contact) if proves(p, a)]
    return min(found, key=lambda a: a["at"] or "") if found else None


def _plain(a: dict) -> dict:
    return {k: a[k] for k in ("kind", "id", "at", "text")}


async def keep(db, p: LeadPromise, contact: Contact, found: dict, by: Optional[str]) -> bool:
    """Done, with what showed it: once, whoever gets there first (the caller commits)."""
    from leads import core
    at = datetime.fromisoformat(found["at"]) if found.get("at") else utc(now())
    done = await db.execute(update(LeadPromise).where(LeadPromise.id == p.id, LeadPromise.status == "open")
                            .values(status="done", done_at=stored(at), done_by=by, evidence=_plain(found)).execution_options(synchronize_session=False))
    if done.rowcount != 1:
        return False
    db.add(core.event(contact, "promise_kept", f"Promise kept: {p.what} ({found['text']})"[:1000], by))
    return True


async def cancel(db, p: LeadPromise, contact: Contact, why: str, by: Optional[str]) -> bool:
    from leads import core
    done = await db.execute(update(LeadPromise).where(LeadPromise.id == p.id, LeadPromise.status == "open")
                            .values(status="cancelled", done_at=now(), done_by=by, cancelled_why=why[:200]).execution_options(synchronize_session=False))
    if done.rowcount != 1:
        return False
    db.add(core.event(contact, "promise_cancel", f"Promise cancelled: {p.what} ({why})"[:1000], by))
    return True


async def cancel_open(db, contact: Contact, why: str, by: Optional[str] = None) -> int:
    """Every open promise to this person (a lead lost): the caller commits."""
    count = 0
    for p in (await db.execute(select(LeadPromise).where(LeadPromise.contact_id == contact.id, LeadPromise.status == "open"))).scalars().all():
        count += await cancel(db, p, contact, why, by)
    return count


async def settle_contact(db, contact: Contact) -> int:
    """Look through one lead's records now (their page is open): the caller commits."""
    count = 0
    for p in (await db.execute(select(LeadPromise).where(LeadPromise.contact_id == contact.id, LeadPromise.status == "open"))).scalars().all():
        found = await evidence(db, p, contact)
        if found is not None:
            count += await keep(db, p, contact, found, None)
    return count


async def _settle_one(promise_id: str, at: datetime) -> None:
    from voice import schedule
    async with async_session() as db:
        claimed = await db.execute(update(LeadPromise).where(LeadPromise.id == promise_id, LeadPromise.status == "open",
                                                             or_(LeadPromise.checked_at.is_(None), LeadPromise.checked_at < stored(utc(at) - CHECK_EVERY)))
                                   .values(checked_at=stored(at)).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        p = await db.get(LeadPromise, promise_id)
        contact = await db.get(Contact, p.contact_id)
        if contact is None:
            return
        if p.kind == "callback" and contact.e164 and await schedule.on_dnc(db, p.user_id, contact.e164):
            await cancel(db, p, contact, "They asked not to be called", None)
        else:
            found = await evidence(db, p, contact)
            if found is not None:
                await keep(db, p, contact, found, None)
        await db.commit()


async def settle(at: Optional[datetime] = None) -> None:
    at = at or now()
    async with async_session() as db:
        ids = (await db.execute(select(LeadPromise.id).where(LeadPromise.status == "open", or_(LeadPromise.checked_at.is_(None),
                                                                                               LeadPromise.checked_at < stored(utc(at) - CHECK_EVERY)))
                                .order_by(LeadPromise.checked_at.asc().nulls_first()).limit(SETTLE_BATCH))).scalars().all()
    for promise_id in ids:
        try:
            await _settle_one(promise_id, at)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Checking promise {promise_id} failed: {e}")


async def _remind_one(promise_id: str, at: datetime) -> None:
    import plans
    from leads import core
    from phone import display
    async with async_session() as db:
        claimed = await db.execute(update(LeadPromise).where(LeadPromise.id == promise_id, LeadPromise.status == "open", LeadPromise.reminded_at.is_(None))
                                   .values(reminded_at=stored(at)).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        p = await db.get(LeadPromise, promise_id)
        contact = await db.get(Contact, p.contact_id)
        if contact is None or not (await plans.includes(db, p.bot_id)).team_alerts:
            return
        tz = await _zone(db, p.bot_id)
        who = " ".join(x for x in (contact.name, display(contact.e164) if contact.e164 else None, contact.email) if x)
        person, owner_id, bot_id, contact_id = contact.assigned_to, p.user_id, p.bot_id, contact.id
        text = (f"{p.what}\n{who}\nPromised {MADE_ON.get(p.made_on, p.made_on)}, {_when(p.made_at, tz)}; due {_when(p.due_at, tz)}.\n"
                "When it's done, open the lead and choose what did it.")
    await core._alert(owner_id, person, f"Promised, not done yet: {p.what}"[:150], text, bot_id, contact_id)


async def remind(at: Optional[datetime] = None) -> None:
    """Each promise that has come due without a record of it: its lead's person is told once (Starter and up, as task reminders)."""
    at = at or now()
    async with async_session() as db:
        ids = (await db.execute(select(LeadPromise.id).where(LeadPromise.status == "open", LeadPromise.reminded_at.is_(None), LeadPromise.due_at <= stored(at),
                                                             LeadPromise.due_at > stored(utc(at) - REMIND_WITHIN)).order_by(LeadPromise.due_at).limit(SETTLE_BATCH))).scalars().all()
    for promise_id in ids:
        try:
            await _remind_one(promise_id, at)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Reminding about promise {promise_id} failed: {e}")


async def tick(at: Optional[datetime] = None) -> None:
    """Scheduler: records first (a promise kept needs no reminder), then reminders, then quiet conversations read for new promises."""
    global _last_pass
    at = at or now()
    if _last_pass and utc(at) - utc(_last_pass) < PASS_EVERY:
        return
    _last_pass = at
    await settle(at)
    await remind(at)
    await scan(at)


# ─── for the dashboard ───────────────────────────────────────────
def promise_json(p: LeadPromise, names: Optional[dict] = None) -> dict:
    late = p.status == "open" and utc(p.due_at) < utc(now())
    return {"id": p.id, "contact_id": p.contact_id, "kind": p.kind, "what": p.what, "words": p.words, "made_at": utc(p.made_at).isoformat(), "made_on": p.made_on,
            "made_by": (names or {}).get(p.made_by) if p.made_by else None, "due_at": utc(p.due_at).isoformat(), "due_said": bool(p.due_said), "status": p.status,
            "late": late, "done_at": utc(p.done_at).isoformat() if p.done_at else None, "done_by": (names or {}).get(p.done_by) if p.done_by else None,
            "evidence": p.evidence, "cancelled_why": p.cancelled_why}


async def of_contact(db, contact_id: str, names: Optional[dict] = None) -> list[dict]:
    rows = (await db.execute(select(LeadPromise).where(LeadPromise.contact_id == contact_id))).scalars().all()
    order = {"open": 0, "done": 1, "cancelled": 2}
    rows = sorted(rows, key=lambda p: (order.get(p.status, 3), utc(p.due_at) if p.status == "open" else -utc(p.done_at or p.made_at).timestamp()))
    return [promise_json(p, names) for p in rows[:50]]


def report(rows: list[LeadPromise]) -> dict:
    """What happened to the promises made in a period: kept, kept on time, cancelled, still open and late; by where they were made."""
    at = utc(now())
    by: dict = {}
    for p in rows:
        b = by.setdefault(p.made_on, {"made_on": p.made_on, "made": 0, "kept": 0, "on_time": 0})
        b["made"] += 1
        b["kept"] += p.status == "done"
        b["on_time"] += p.status == "done" and p.done_at is not None and utc(p.done_at) <= utc(p.due_at)
    return {"made": len(rows), "kept": sum(p.status == "done" for p in rows),
            "on_time": sum(p.status == "done" and p.done_at is not None and utc(p.done_at) <= utc(p.due_at) for p in rows),
            "cancelled": sum(p.status == "cancelled" for p in rows), "late": sum(p.status == "open" and utc(p.due_at) < at for p in rows),
            "by_channel": sorted(by.values(), key=lambda b: -b["made"])}
