"""
The parts of a customer email the AI writes, and designed emails made ready to send (mail plan, phase 1).

The welcome email's note (a sentence or two about what they asked) and the files that fit their chat are written
before it's due, by `prepare_due` in the background: the email loop never waits on a model, and no database connection
is held while one answers. An email is claimed by one process (compose_state pending -> working -> done); one whose
writing doesn't finish in a few minutes goes without it. A number the conversation and the knowledge don't have is
taken out with its sentence: the AI never invents a price.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.future import select

from backend.models import Bot, Conversation, EmailJob, Message, WhatsAppFile, WhatsAppNumber
from database import async_session
from mail import designs, links, render, setup

logger = logging.getLogger(__name__)

WAIT = timedelta(minutes=3)        # how long an email waits for its AI parts before going without them
STUCK = timedelta(minutes=3)       # a claim older than this was lost with its process
AI_SECONDS = 45                    # Gemini Flash-Lite can take 20 s for a one-word answer (measured Nov 2026)
CHAT_MESSAGES = 24
_running = False


def needs_writing(kind: str) -> bool:
    return kind in ("chat_lead",)


# ─── the AI's parts ──────────────────────────────────────────────
def _numbers(text: str) -> set[str]:
    return {re.sub(r"[,\s]", "", n).rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


def keep_known_numbers(note: str, sources: str) -> str:
    """Drop each sentence with a number the sources don't have (prices, dates, counts the AI might invent)."""
    known = _numbers(sources)
    sentences = re.split(r"(?<=[.!?।])\s+", note.strip())
    kept = [s for s in sentences if _numbers(s) <= known]
    return " ".join(kept).strip()


async def _chat_lines(db, conversation_id: str) -> tuple[str, str]:
    """(the chat as lines, what the visitor wrote): the newest messages, oldest first."""
    rows = (await db.execute(select(Message).where(Message.conversation_id == conversation_id, Message.role.in_(("user", "assistant")))
                             .order_by(Message.timestamp.desc()).limit(CHAT_MESSAGES))).scalars().all()
    rows = list(reversed(rows))
    lines = "\n".join(f"{'Visitor' if m.role == 'user' else 'Assistant'}: {m.content[:600]}" for m in rows)
    said = "\n".join(m.content for m in rows if m.role == "user")
    return lines, said


async def _files(db, owner_id: str, bot_id: Optional[str]) -> list[WhatsAppFile]:
    """The business's Files this assistant may send: its own and the ones for every assistant."""
    return (await db.execute(select(WhatsAppFile).where(
        WhatsAppFile.user_id == owner_id, or_(WhatsAppFile.bot_id.is_(None), WhatsAppFile.bot_id == bot_id))
        .order_by(WhatsAppFile.created_at.desc()).limit(30))).scalars().all()


async def welcome_parts(bot: Bot, chat: str, captured: dict, files: list[WhatsAppFile], language: str,
                        want_note: bool, want_files: bool, max_files: int, guidance: str = "") -> dict:
    """{"ai_note", "file_ids"} for one welcome email. One model call; nothing when the chat says nothing to go on."""
    if not chat.strip() or not (want_note or (want_files and files)):
        return {"ai_note": "", "file_ids": []}
    from voice import llm
    knowledge = await llm.call_knowledge(bot)
    listed = "\n".join(f"{i}. {f.name}" + (f" (send when: {f.when_to_send})" if f.when_to_send else "")
                       for i, f in enumerate(files, 1)) if want_files else ""
    system = (
        f"You write part of the welcome email {bot.bot_name} sends to someone who just chatted with its assistant. "
        'Reply with JSON only: {"note": "...", "files": [numbers]}.\n'
        + ("note: one or two short sentences (at most 45 words) about what they asked about and how the business can "
           "help, using only facts from the conversation and the knowledge below. No greeting, no sign-off, no promises "
           "the conversation didn't make, and no prices, dates or numbers that aren't in the conversation or the "
           f"knowledge. Write in {designs.LANGUAGES.get(language, 'English')}. If the conversation has nothing specific, "
           'the note is "".' + (f" The business asks: {guidance}" if guidance else "") + "\n" if want_note else 'note: "".\n')
        + (f"files: the numbers of at most {max_files} files from this list that fit what they asked about, else []:\n"
           f"{listed}\n" if listed else "files: [].\n"))
    user = (f"Conversation:\n{chat[:6000]}\n\nWhat they told us: "
            f"{json.dumps({k: v for k, v in captured.items() if v}, ensure_ascii=False)[:800]}\n\nKnowledge:\n{knowledge[:6000]}")
    try:
        raw = await asyncio.wait_for(llm._complete(bot, system, user, max_tokens=300), timeout=AI_SECONDS)
        found = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(found.group(0)) if found else {}
    except Exception as e:
        logger.warning(f"Writing a welcome email for {bot.bot_id} failed: {e}")
        return {"ai_note": "", "file_ids": []}
    note = str(data.get("note") or "").strip() if want_note else ""
    note = keep_known_numbers(re.sub(r"\s+", " ", note), f"{chat}\n{knowledge}\n{json.dumps(captured, ensure_ascii=False)}")
    note = note if designs.written_in(note, language) else ""  # in another language: the email goes without it
    picked = []
    for n in data.get("files") or []:
        try:
            f = files[int(n) - 1]
        except (ValueError, TypeError, IndexError):
            continue
        if f.id not in picked:
            picked.append(f.id)
    return {"ai_note": note[:400], "file_ids": picked[:max_files] if want_files else []}


async def prepare_due() -> None:
    """Scheduler (in the background, one at a time per process): write the AI's parts of emails due soon."""
    global _running
    if _running:
        return
    _running = True
    try:
        for _ in range(5):
            if not await _prepare_one():
                break
    finally:
        _running = False


async def _prepare_one() -> bool:
    now = datetime.utcnow()
    free = or_(EmailJob.compose_state == "pending", (EmailJob.compose_state == "working") & (EmailJob.compose_at < now - STUCK))
    async with async_session() as db:
        job = (await db.execute(select(EmailJob).where(
            EmailJob.status.in_(("queued", "draft")), free,
            EmailJob.send_at <= now + timedelta(minutes=1)).order_by(EmailJob.send_at).limit(1))).scalars().first()
        if job is None:
            return False
        claimed = await db.execute(update(EmailJob).where(EmailJob.id == job.id, free)
                                   .values(compose_state="working", compose_at=now).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return True  # another process has it: look for the next
        if job.automation == "after_call":
            from mail import after_call
            await after_call.write(job.id)
            return True
        conv = await db.get(Conversation, job.ref_id)
        bot = await db.get(Bot, conv.bot_id) if conv else None
        chat, said = await _chat_lines(db, conv.conversation_id) if conv else ("", "")
        files = await _files(db, job.user_id, bot.bot_id) if bot else []
        prefs = (await setup.settings_for(db, bot.bot_id))["welcome"] if bot else setup.SETTINGS["welcome"]
        import plans
        growth = (await plans.includes(db, bot.bot_id)).email_alerts and await plans.can_reply(db, bot.bot_id) if bot else False
        captured = dict(conv.captured_data or {}) if conv else {}
        design = await setup.design_for(db, job.user_id, bot.bot_id, "welcome", designs.language_of(said)) if bot else {}
    # No connection is held while the model writes.
    parts = {"ai_note": "", "file_ids": []}
    if bot is not None and growth:
        guidance = next((b.get("guidance", "") for b in design.get("blocks", []) if b.get("type") == "ai_note"), "")
        has_note = any(b.get("type") == "ai_note" for b in design.get("blocks", []))
        has_files = any(b.get("type") == "files" for b in design.get("blocks", []))
        parts = await welcome_parts(bot, chat, captured, files, design.get("language", "en"),
                                    want_note=bool(prefs.get("ai_note")) and has_note,
                                    want_files=bool(prefs.get("ai_files")) and has_files and bool(files),
                                    max_files=int(prefs.get("max_files") or 2), guidance=guidance)
        if parts["ai_note"]:
            await plans.count_reply(bot.bot_id)  # an AI-written email counts as one AI reply
    async with async_session() as db:
        job = await db.get(EmailJob, job.id)
        if job is not None:
            job.merge_data = {**(job.merge_data or {}), **parts}
            job.compose_state = "done"
            await db.commit()
    return True


LONGEST_WAIT = timedelta(minutes=10)  # a long chat still gets its welcome email within this of the address


async def chat_went_on(db, conversation_id: str) -> None:
    """They're still chatting: their welcome email waits until the chat goes quiet (the caller commits)."""
    from notify import automations
    now = datetime.utcnow()
    await db.execute(update(EmailJob).where(
        EmailJob.ref_id == conversation_id, EmailJob.automation == "chat_lead", EmailJob.step == 1,
        EmailJob.status == "queued", EmailJob.created_at > now - LONGEST_WAIT)
        .values(send_at=now + timedelta(seconds=automations.QUIET)).execution_options(synchronize_session=False))


def waiting(job: EmailJob, now: Optional[datetime] = None) -> bool:
    """Its AI parts are still being written, and there's time to wait for them."""
    if job.compose_state not in ("pending", "working"):
        return False
    created = job.created_at.replace(tzinfo=None) if job.created_at else None
    return created is not None and (now or datetime.utcnow()) - created < WAIT


# ─── designed emails ─────────────────────────────────────────────
async def whatsapp_link(db, owner_id: str, bot_id: Optional[str]) -> Optional[str]:
    rows = (await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.user_id == owner_id,
                                                          WhatsAppNumber.status == "connected"))).scalars().all()
    number = next((n for n in rows if n.bot_id == bot_id), None) or next((n for n in rows if n.bot_id is None), None)
    digits = re.sub(r"\D", "", (number.display_number or "") if number else "")
    return f"https://wa.me/{digits}" if len(digits) >= 10 else None


def _first_name(name: Optional[str]) -> Optional[str]:
    from voice.memory import first_name
    return first_name(name) if name and name != "there" else None


async def welcome(db, job: EmailJob, values: dict, sender, unsubscribe_url: str) -> tuple[render.Rendered, list]:
    """The first email after a chat, from the assistant's welcome design."""
    import plans
    conv = await db.get(Conversation, job.ref_id)
    bot = await db.get(Bot, job.bot_id or (conv.bot_id if conv else None))
    _, said = await _chat_lines(db, conv.conversation_id) if conv else ("", "")
    design = await setup.design_for(db, job.user_id, bot.bot_id if bot else None, "welcome", designs.language_of(said))
    growth = (await plans.includes(db, bot.bot_id)).email_alerts if bot else False
    data = job.merge_data or {}
    files = []
    if growth and data.get("file_ids") is not None:
        prefs = (await setup.settings_for(db, bot.bot_id))["welcome"] if bot else {}
        wanted = list(dict.fromkeys([*(prefs.get("files") or []), *(data.get("file_ids") or [])]))
        rows = {f.id: f for f in await _files(db, job.user_id, bot.bot_id if bot else None)}
        files = [{"name": rows[i].name, "url": i, "size": _size(rows[i].size)} for i in wanted if i in rows][:4]
    values = {**values, "first_name": _first_name(values.get("name")), "signature": sender.name,
              "ai_note": data.get("ai_note") if growth else "", "files": files,
              "details_map": (conv.captured_data or {}) if conv else {},
              "actions": {"whatsapp": await whatsapp_link(db, job.user_id, bot.bot_id if bot else None)}}
    if not growth:  # Starter: the text and buttons, without the AI's note or files
        design = {**design, "blocks": [b for b in design["blocks"] if b["type"] not in ("ai_note", "files")]}
    tracker = links.Tracker(job.user_id, job.id)
    brand = render.brand_of(bot.visual_config if bot else None, sender.name)
    made = render.email(design, values, brand, language=design.get("language", "en"), unsubscribe_url=unsubscribe_url,
                        link=lambda url, kind, label: tracker(url if kind != "file" else f"file:{url}", kind, label))
    return made, tracker.rows()


def _size(n: Optional[int]) -> str:
    if not n:
        return ""
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{max(1, round(n / 1024))} KB"
