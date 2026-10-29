"""
The assistant's WhatsApp replies, written and sent the way a person at the business would.

A reply isn't sent the moment a customer writes: it's due a few seconds later (WhatsApp > Assistant, "wait"), and each
new message moves that on, so someone who sends three quick messages gets one answer to all three. Any server process
may answer: the chat is claimed in the database first (reply_due_at / reply_claimed_at), so only one does. A timer in
the process that got the message answers on time, and the scheduler's sweep picks up anything left behind (a restart).

Answering: their message is marked read and "typing…" shows; voice notes are written out and photos and PDFs looked at
(understand.py); then the business's knowledge, the conversation, what's remembered about them (memory.py) and the files
it may send go to the AI. Its answer goes out as one to three short messages, each after a pause that fits its length,
then any file it chose, with buttons when it offers a few choices. If they write again before the answer goes out, it's
written again with everything they said. A person asked for, or an upset customer, goes to the team (Live chat and the
Inbox), and a chat a team member is handling is left to them.
"""
import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.future import select

import ai
import assist
import behaviour
import brain
from backend.models import Conversation, Message, WhatsAppChat, WhatsAppFile, WhatsAppMessage, WhatsAppNumber
from database import async_session
from notify.events import fire_and_forget, handoff_requested
from realtime import notify_owner
from subscriptions import active_subscription
from utils import FlowEngine, generate_ai_response
from whatsapp import chats, graph, memory, numbers, outbound, settings, understand

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Sorry, this assistant isn't available on WhatsApp right now. Please contact the business directly."
ASKED_FOR_PERSON = "I've let our team know. Someone will reply here shortly. Feel free to add any details in the meantime."
UPSET = "I'm sorry about this. I've asked someone from our team to take over, and they'll reply here shortly."
# Whole words/phrases only: "agent" inside "travel agent" or "person" inside "personal" must not hand over.
HUMAN_KEYWORDS = [
    "talk to human", "speak to human", "talk to a human", "speak to a human", "human agent", "human",
    "representative", "support team", "real person", "customer care", "talk to someone",
    "மனிதன்", "ஆள் வேண்டும்", "பேச வேண்டும்", "इंसान", "बात करनी है",
]
HUMAN_RE = re.compile("|".join(rf"(?<!\w){re.escape(k)}(?!\w)" for k in HUMAN_KEYWORDS), re.IGNORECASE)

PACE = float(os.getenv("WHATSAPP_PACE", "1"))  # 0 in tests: no pauses between messages
PAUSE_BASE, PAUSE_PER_CHAR, PAUSE_MAX = 0.8, 0.012, 3.5  # seconds before a message: longer ones take a little longer
CLAIM_STALE = timedelta(minutes=3)  # a process that claimed a chat and died: another answers after this
LATE = timedelta(seconds=45)        # a customer still writing after this long is answered anyway
OVERDUE = timedelta(seconds=10)     # the sweep's margin over a chat's own timer
# A timer sleeps on the monotonic clock but the due time is wall-clock: one woke a hair early, its claim failed, and
# the answer waited for the sweep (16 s instead of 4). Claims allow for that; a newer message moves the due time
# seconds later, far beyond this.
EARLY = timedelta(milliseconds=250)
HISTORY = 20
FILES_SHOWN, FILES_PER_REPLY, MAX_BUBBLES = 20, 2, 3
KIND_LABEL = {"image": "photo", "video": "video", "audio": "audio", "document": "document"}

FILE_RE = re.compile(r"\[\s*FILE\s*:?\s*#?(\d{1,3})\s*\]", re.I)
SENT_FILE = re.compile(r'\(sent the file "([^"\n]+)"\)', re.I)  # how a sent file reads in the conversation (outbound.py)
BUTTONS_RE = re.compile(r"\[\s*BUTTONS?\s*:([^\]\n]+)\]", re.I)
HANDOFF_RE = re.compile(r"\[\s*HANDOFF\s*\]", re.I)
QUOTE_RE = re.compile(r"^\s*\[\s*QUOTE\s*:?\s*(\d{1,2})\s*\]\s*", re.I)
QUOTE_ANY = re.compile(r"\[\s*QUOTE\s*:?\s*\d{1,2}\s*\]\s*", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")

_timers: set = set()


@dataclass
class Reply:
    bubbles: list[tuple[str, Optional[str]]]  # (text, Meta id of the customer message it quotes)
    files: list[WhatsAppFile]
    buttons: list[str]
    handoff: bool

    @property
    def text(self) -> str:
        return "\n\n".join(b for b, _ in self.bubbles)


# ─── when to answer ───────────────────────────────────────────────
def schedule(chat_id: str, due: datetime) -> None:
    """Answer the chat at `due` from this process (if no other process has by then)."""
    async def later():
        await asyncio.sleep(max(0.0, (due - chats.now()).total_seconds()) + 0.05)
        await run(chat_id)
    task = asyncio.ensure_future(later())
    _timers.add(task)
    task.add_done_callback(_timers.discard)


async def run(chat_id: str) -> None:
    if not await _claim(chat_id):
        return
    try:
        await _answer(chat_id)
    except Exception as e:
        logger.exception(f"WhatsApp reply in chat {chat_id} failed: {e}")
    finally:
        again = await _release(chat_id)
        if again is not None:  # they wrote while it was answering
            schedule(chat_id, max(again, chats.now()))


async def sweep() -> None:
    """Chats whose answer is overdue: their timer was in a process that restarted, or a process died answering."""
    now = chats.now()
    async with async_session() as db:
        await db.execute(update(WhatsAppChat).where(
            WhatsAppChat.reply_claimed_at.isnot(None), WhatsAppChat.reply_claimed_at < now - CLAIM_STALE,
            WhatsAppChat.reply_due_at.is_(None)).values(reply_due_at=now - OVERDUE))
        await db.commit()
        ids = (await db.execute(select(WhatsAppChat.id).where(
            WhatsAppChat.reply_due_at.isnot(None), WhatsAppChat.reply_due_at <= now - OVERDUE).limit(50))).scalars().all()
    for chat_id in ids:
        schedule(chat_id, now)


async def _claim(chat_id: str) -> bool:
    now = chats.now()
    async with async_session() as db:
        claimed = await db.execute(update(WhatsAppChat).where(
            WhatsAppChat.id == chat_id, WhatsAppChat.reply_due_at.isnot(None), WhatsAppChat.reply_due_at <= now + EARLY,
            or_(WhatsAppChat.reply_claimed_at.is_(None), WhatsAppChat.reply_claimed_at < now - CLAIM_STALE),
        ).values(reply_claimed_at=now, reply_due_at=None))
        await db.commit()
    return claimed.rowcount == 1


async def _release(chat_id: str) -> Optional[datetime]:
    async with async_session() as db:
        await db.execute(update(WhatsAppChat).where(WhatsAppChat.id == chat_id).values(reply_claimed_at=None))
        await db.commit()
        due = (await db.execute(select(WhatsAppChat.reply_due_at).where(WhatsAppChat.id == chat_id))).scalar_one_or_none()
    return chats.aware(due)


# ─── answering ────────────────────────────────────────────────────
async def _answer(chat_id: str) -> None:
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat_id)
        number = await db.get(WhatsAppNumber, chat.number_id) if chat and chat.number_id else None
        if chat is None or number is None or number.status == "disconnected":
            return
        rows = (await db.execute(
            select(WhatsAppMessage, Message).join(Message, Message.id == WhatsAppMessage.message_id)
            .where(WhatsAppMessage.chat_id == chat.id, WhatsAppMessage.direction == "in", WhatsAppMessage.handled.is_(False))
            .order_by(WhatsAppMessage.created_at))).all()
        if not rows or not number.ai_enabled or chats.ai_paused(chat):
            return
        bot = await numbers.assistant(db, number)
        if bot is None:
            return
        conv, _ = await chats.conversation(db, chat, bot)
        await db.commit()
        if conv.handoff_status == "human":
            return  # a team member has it
        paid = await active_subscription(bot.bot_id, db) is not None
    cfg = settings.clean(number.settings)
    pending = [w for w, _ in rows]
    last_wamid = pending[-1].wamid
    started = time.monotonic()
    await (graph.typing if cfg["typing"] else graph.mark_read)(number.phone_number_id, number.access_token, last_wamid)
    if not paid:  # same rule as the website widget: it answers only while its plan is active
        await outbound.send_text(number, chat, NOT_AVAILABLE, sent_by="ai")
        await _done(chat.id, pending)
        return

    turn = []
    for w, m in rows:
        text = m.content
        if w.kind in understand.KINDS and cfg["understand_media"] and not (w.media or {}).get("understood"):
            text = await understand.message(number, w, m)
        turn.append(text)
    said = "\n".join(turn)

    asked = bool(HUMAN_RE.search(said))
    upset = not asked and await assist.should_escalate(bot.user_id, said)
    if asked or upset:
        await _hand_over(number, chat, conv, bot, said, UPSET if upset else ASKED_FOR_PERSON)
        await _done(chat.id, pending, team=True)
        return
    if bot.flow_data and bot.flow_data.get("nodes") and await _flow(number, chat, conv, bot, said, cfg, last_wamid, started):
        await _done(chat.id, pending)
        return

    reply, last_asked = await _write(number, chat, conv, bot, cfg, rows, turn)
    if await _newer(chat.id, pending) and not _late(pending):
        return  # they wrote again: the next answer covers everything they said
    await _deliver(number, chat, cfg, reply, last_wamid, started)
    await _done(chat.id, pending)
    if reply.handoff:
        await _flag_handoff(chat, conv, bot, said)
    if assist.is_unanswered(reply.text):
        fire_and_forget(assist.record_gap(bot.bot_id, said, "whatsapp", conv.conversation_id))
    fire_and_forget(brain.learn_details(conv.conversation_id, bot, said, last_asked))
    fire_and_forget(memory.noted(chat.id))


async def _write(number: WhatsAppNumber, chat: WhatsAppChat, conv: Conversation, bot, cfg: dict,
                 rows: list, turn: list[str]) -> tuple[Reply, str]:
    turn_ids = [m.id for _, m in rows]
    async with async_session() as db:
        history_rows = (await db.execute(select(Message).where(
            Message.conversation_id == conv.conversation_id, Message.role.in_(["user", "assistant"]),
            Message.id.notin_(turn_ids)).order_by(Message.timestamp.desc()).limit(HISTORY + 1))).scalars().all()
        files = (await db.execute(select(WhatsAppFile).where(
            WhatsAppFile.user_id == number.user_id, or_(WhatsAppFile.bot_id.is_(None), WhatsAppFile.bot_id == bot.bot_id))
            .order_by(WhatsAppFile.created_at.desc()).limit(FILES_SHOWN))).scalars().all() if cfg["send_files"] else []
        recent = (await db.execute(select(WhatsAppMessage.media).where(
            WhatsAppMessage.chat_id == chat.id, WhatsAppMessage.direction == "out",
            WhatsAppMessage.created_at > chats.now() - timedelta(hours=24)))).scalars().all()
        captured = ((await db.get(Conversation, conv.conversation_id)).captured_data or {})
    history = [{"role": m.role, "content": _as_seen(m, files)} for m in reversed(history_rows[:HISTORY])]
    sent = {(m or {}).get("file_id") for m in recent}
    numbered = len(turn) > 1
    said = "\n".join(f"[{i}] {t}" for i, t in enumerate(turn, 1)) if numbered else turn[0]
    first = not any(h["role"] == "assistant" for h in history)
    welcome = cfg["welcome"] if first else ""
    knowledge = await brain.knowledge(bot, "\n".join(turn))
    about = await memory.about(bot.bot_id, chat, long_chat=len(history_rows) > HISTORY)
    base = brain.system_prompt(bot, captured=captured, first_message=first and not welcome, channel="whatsapp",
                               knowledge_text=knowledge)
    extra = rules(cfg, files, [f.name for f in files if f.id in sent], numbered, about, ongoing=not first,
                  match_language=behaviour.clean(bot.behaviour).get("language", "match") == "match",
                  script=next((s for s in map(script_of, reversed(turn)) if s), None))
    system = base.replace("\n\n# Business knowledge", extra + "\n\n# Business knowledge", 1) if "\n\n# Business knowledge" in base else base + extra
    messages = brain.turns(history, said)
    raw = await asyncio.to_thread(generate_ai_response, system, "", said, history=messages[:-1],
                                  provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key)
    reply = parse(raw, [w.wamid for w, _ in rows], files, cfg)
    if welcome:
        reply.bubbles.insert(0, (welcome, None))
    if not reply.bubbles and not reply.files:
        reply.bubbles = [(ai.SORRY, None)]
    return reply, next((h["content"] for h in reversed(history) if h["role"] == "assistant"), "")


def _as_seen(m: Message, files: list[WhatsAppFile]) -> str:
    """A message as the AI sees it in the chat so far. A file it sent reads as the [FILE n] it would write to send it
    again: shown as '(sent the file "Brochure")', the model copied those words instead of sending the file."""
    if m.role != "assistant" or not SENT_FILE.match(m.content):
        return m.content
    name = SENT_FILE.match(m.content).group(1)
    n = next((i for i, f in enumerate(files, 1) if f.name == name), None)
    return SENT_FILE.sub(f"[FILE {n}]" if n else f"(a file that's no longer available: {name})", m.content, count=1)


SCRIPTS = {"Tamil": (0x0B80, 0x0BFF), "Devanagari": (0x0900, 0x097F), "Telugu": (0x0C00, 0x0C7F),
           "Kannada": (0x0C80, 0x0CFF), "Malayalam": (0x0D00, 0x0D7F), "Bengali": (0x0980, 0x09FF),
           "Gujarati": (0x0A80, 0x0AFF), "Gurmukhi": (0x0A00, 0x0A7F), "Odia": (0x0B00, 0x0B7F)}
PLACEHOLDER = re.compile(r"^\((voice note|audio|photo|sticker|video|document|location|shared a contact)[^)]*\)\s*", re.I)


def script_of(text: str) -> Optional[str]:
    """The writing system a message is in: "Tamil", "Devanagari"… or "English letters" (None without letters).
    Any real amount of an Indian script decides it: people writing Tamil script still type English words in English
    letters ("வணக்கம், data science fees எவ்வளவு?"), while Tamil written in English letters has none ("fees evlo?")."""
    counts: dict[str, int] = {}
    latin = 0
    for ch in PLACEHOLDER.sub("", text or ""):
        if ch.isascii():
            latin += ch.isalpha()
            continue
        code = ord(ch)
        for name, (low, high) in SCRIPTS.items():
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break
    if counts and max(counts.values()) >= 3:
        return max(counts, key=counts.get)
    return "English letters" if latin else None


def rules(cfg: dict, files: list[WhatsAppFile], already_sent: list[str], numbered: bool, about: list[str],
          ongoing: bool = False, match_language: bool = True, script: Optional[str] = None) -> str:
    """What the assistant is told about writing on WhatsApp, on top of its usual instructions (brain.py)."""
    words = 60 if cfg["length"] == "short" else 120
    lines = ["", "On WhatsApp:",
             "- Write like a helpful person from the business chatting on WhatsApp: natural, warm and brief, without a "
             "greeting or sign-off in every message.",
             f"- Keep a reply under about {words} words unless they ask for full details."]
    if match_language and script == "English letters":
        # Gemini answered "fees evlo?" in Tamil script when the chat had Tamil-script messages earlier.
        lines.append("- Their latest message is in English letters: reply in English letters, in the same language they "
                     "used (Tamil written in English letters, like \"fees evlo?\", stays that way; so does Hindi, and "
                     "English stays English), even if earlier messages were in another script.")
    elif match_language and script:
        lines.append(f"- Their latest message is in {script} script: reply in {script} script.")
    if ongoing:
        lines.append("- You're in the middle of this chat: don't greet them again or start with their name. Just answer.")
    if cfg["split"]:
        lines.append("- You may send up to 3 short messages: put a blank line between them. Often one is enough.")
    if numbered:
        lines.append("- They sent several messages since your last reply, numbered [1], [2] and so on. Answer them "
                     "together. If one of your messages answers an earlier one in particular, start it with [QUOTE n].")
    if files:
        lines.append("- Files you can send (they arrive right after your text):")
        for i, f in enumerate(files, 1):
            what = "PDF" if f.mime == "application/pdf" else KIND_LABEL.get(f.kind, "file")
            lines.append(f'  [{i}] "{f.name}" ({what}): {(f.when_to_send or "when it helps").strip()}')
        lines.append(f"  To send one, put [FILE n] on its own line. Only when it helps, at most {FILES_PER_REPLY} per reply.")
        if already_sent:
            lines.append("  Already sent in this chat today, so send again only if they ask: "
                         + ", ".join(f'"{n}"' for n in already_sent) + ".")
    if cfg["buttons"]:
        lines.append("- To offer 2 or 3 short choices, end your last message with [BUTTONS: First | Second], each at "
                     "most 20 characters. Only for a real choice they need to make.")
    lines += ["- If they need someone from the team to act (a complaint, a refund, a change to an order or booking, or "
              "a question the business information doesn't answer that they still want answered), put [HANDOFF] on its "
              "own line and tell them someone will reply here. Don't hand over just because the business doesn't offer "
              "what they asked about: say so kindly and mention what it does offer.",
              "- Only help with this business, its products and services. Politely decline anything else, such as "
              "general questions or help with writing or coding."]
    if about:
        lines += ["", "What you know about this customer (use it naturally; don't recite it):"] + about
    return "\n".join(lines)


def _short(choice: str) -> str:
    choice = choice.strip().strip("\"'")
    if len(choice) <= graph.BUTTON_CHARS:
        return choice
    cut = choice[:graph.BUTTON_CHARS].rsplit(" ", 1)[0]
    return cut if len(cut) >= 3 else choice[:graph.BUTTON_CHARS]


def _lead_in(part: str) -> bool:
    """A line that leads into the next one rather than standing alone: "Hi Priya," or "Here are our timings:"."""
    return part.endswith((":", ",")) or (len(part) <= 20 and not part.endswith((".", "!", "?", "।")))


def split(text: str, on: bool) -> list[str]:
    """The answer as up to three WhatsApp messages: by paragraph, keeping a list or a greeting with what follows it."""
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if not text:
        return []
    if not on:
        return [text]
    out: list[str] = []
    for part in (p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()):
        is_list = all(LIST_LINE.match(line) for line in part.splitlines() if line.strip())
        if out and (_lead_in(out[-1]) or is_list):
            out[-1] += "\n" + part
        else:
            out.append(part)
    if len(out) > MAX_BUBBLES:
        out = out[:MAX_BUBBLES - 1] + ["\n\n".join(out[MAX_BUBBLES - 1:])]
    return out


def parse(raw: str, turn: list[str], files: list[WhatsAppFile], cfg: dict) -> Reply:
    """The AI's answer as messages, files to send, buttons and whether it asked for the team. `turn`: Meta ids of the
    customer's messages it answers, in order ([QUOTE n] refers to them)."""
    text = raw or ""
    picked: list[WhatsAppFile] = []
    for n in FILE_RE.findall(text):
        i = int(n) - 1
        if cfg["send_files"] and 0 <= i < len(files) and files[i] not in picked:
            picked.append(files[i])
    for name in SENT_FILE.findall(text):  # it wrote what a sent file looks like instead of sending it
        f = next((f for f in files if f.name.lower() == name.strip().lower()), None)
        if cfg["send_files"] and f is not None and f not in picked:
            picked.append(f)
    text = SENT_FILE.sub("", FILE_RE.sub("", text))
    buttons: list[str] = []
    found = BUTTONS_RE.findall(text)
    if found and cfg["buttons"]:
        buttons = [_short(b) for b in found[-1].split("|") if b.strip()][:graph.BUTTONS]
        buttons = buttons if len(buttons) >= 2 else []
    text = BUTTONS_RE.sub("", text)
    handoff = bool(HANDOFF_RE.search(text))
    text = HANDOFF_RE.sub("", text)
    bubbles = []
    for part in split(text, cfg["split"]):
        quote = None
        m = QUOTE_RE.match(part)
        if m and len(turn) > 1 and 0 < int(m.group(1)) <= len(turn):
            quote = turn[int(m.group(1)) - 1]
        part = QUOTE_ANY.sub("", part).strip()
        if part:
            bubbles.append((part, quote))
    return Reply(bubbles, picked[:FILES_PER_REPLY], buttons, handoff)


# ─── sending ──────────────────────────────────────────────────────
async def _pause(text: str, since: Optional[float] = None) -> None:
    """Wait as a person would before a message (less whatever time writing it already took)."""
    wait = min(PAUSE_MAX, PAUSE_BASE + len(text) * PAUSE_PER_CHAR)
    if since is not None:
        wait -= time.monotonic() - since
    if wait > 0 and PACE > 0:
        await asyncio.sleep(wait * PACE)


async def _deliver(number: WhatsAppNumber, chat: WhatsAppChat, cfg: dict, reply: Reply, last_wamid: str,
                   started: float) -> None:
    for i, (text, quote) in enumerate(reply.bubbles):
        last = i == len(reply.bubbles) - 1
        if i and cfg["typing"]:
            await graph.typing(number.phone_number_id, number.access_token, last_wamid)
        await _pause(text, started if i == 0 else None)
        if i and await _team_took_over(chat.id):
            return
        buttons = reply.buttons if last and reply.buttons and len(text) <= 1024 else None
        w = await outbound.send_text(number, chat, text, sent_by="ai", reply_to=quote, buttons=buttons)
        if w.status == "failed":
            return
    for f in reply.files:
        if cfg["typing"]:
            await graph.typing(number.phone_number_id, number.access_token, last_wamid)
        await _pause("", started if not reply.bubbles else None)
        if await _team_took_over(chat.id):
            return
        w = await outbound.send_file(number, chat, f, sent_by="ai")
        if w.status == "failed":
            return


async def _team_took_over(chat_id: str) -> bool:
    """A team member wrote in the chat while the assistant was mid-reply (seen live: its second message went out
    after the owner's): the rest of the reply isn't sent."""
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat_id)
        conv = await db.get(Conversation, chat.conversation_id) if chat and chat.conversation_id else None
    return chat is None or chats.ai_paused(chat) or (conv is not None and conv.handoff_status == "human")


async def _flow(number: WhatsAppNumber, chat: WhatsAppChat, conv: Conversation, bot, said: str, cfg: dict,
                last_wamid: str, started: float) -> bool:
    """The assistant's visual flow, when it has one: each of its messages as its own WhatsApp message."""
    flow_messages, next_node, handoff = FlowEngine.process(bot.flow_data, conv.current_node_id)
    if not flow_messages:
        return False
    async with async_session() as db:
        row = await db.get(Conversation, conv.conversation_id)
        row.current_node_id = next_node
        if handoff:
            row.handoff_status, row.handoff_requested = "pending", True
        await db.commit()
    for i, text in enumerate(flow_messages):
        if i and cfg["typing"]:
            await graph.typing(number.phone_number_id, number.access_token, last_wamid)
        await _pause(text, started if i == 0 else None)
        if (await outbound.send_text(number, chat, text, sent_by="ai")).status == "failed":
            break
    if handoff:
        await _flag_handoff(chat, conv, bot, said, already_pending=True)
    return True


async def _hand_over(number: WhatsAppNumber, chat: WhatsAppChat, conv: Conversation, bot, said: str, default: str) -> None:
    """A person was asked for, or the customer is upset: the team is told, and the customer hears that."""
    async with async_session() as db:
        row = await db.get(Conversation, conv.conversation_id)
        row.handoff_status, row.handoff_requested = "pending", True
        await db.commit()
    text = await assist.away_reply(bot.user_id) or default
    await _pause(text)
    await outbound.send_text(number, chat, text, sent_by="ai")
    await _flag_handoff(chat, conv, bot, said, already_pending=True)


async def _flag_handoff(chat: WhatsAppChat, conv: Conversation, bot, said: str, already_pending: bool = False) -> None:
    if not already_pending:
        async with async_session() as db:
            row = await db.get(Conversation, conv.conversation_id)
            if row.handoff_status == "ai":
                row.handoff_status, row.handoff_requested = "pending", True
            await db.commit()
    fire_and_forget(handoff_requested(conv.conversation_id, said))
    await notify_owner(bot.user_id, "handoff_requested", {
        "conversation_id": conv.conversation_id, "bot_id": bot.bot_id, "bot_name": bot.bot_name,
        "session_id": conv.visitor_session_id, "message": said,
        "phone": f"+{chat.wa_id}" if chat.wa_id else None, "name": chats.label(chat)})


async def _newer(chat_id: str, pending: list[WhatsAppMessage]) -> bool:
    async with async_session() as db:
        return (await db.execute(select(WhatsAppMessage.id).where(
            WhatsAppMessage.chat_id == chat_id, WhatsAppMessage.direction == "in", WhatsAppMessage.handled.is_(False),
            WhatsAppMessage.id.notin_([w.id for w in pending])))).first() is not None


def _late(pending: list[WhatsAppMessage]) -> bool:
    first = chats.aware(pending[0].created_at)
    return bool(first and first < chats.now() - LATE)


async def _done(chat_id: str, pending: list[WhatsAppMessage], team: bool = False) -> None:
    """The messages are answered (or are the team's now). Unread, for the team, is what's still waiting."""
    async with async_session() as db:
        await db.execute(update(WhatsAppMessage).where(WhatsAppMessage.id.in_([w.id for w in pending])).values(handled=True))
        if not team:
            waiting = (await db.execute(select(WhatsAppMessage.id).where(
                WhatsAppMessage.chat_id == chat_id, WhatsAppMessage.direction == "in",
                WhatsAppMessage.handled.is_(False)))).all()
            await db.execute(update(WhatsAppChat).where(WhatsAppChat.id == chat_id).values(unread=len(waiting)))
        await db.commit()
