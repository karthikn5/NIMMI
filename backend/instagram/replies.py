"""
The assistant's Instagram replies, written and sent the way a person at the business would: the steps of WhatsApp (whatsapp/replies.py), with
Instagram's rules.

- A reply is due a few seconds after their last message (Instagram > Assistant, "wait"), so three quick messages get one answer. Any server process
  may answer: the chat is claimed in the database first, so only one does; the scheduler's sweep picks up what a restart left behind.
- Only inside Instagram's window (24 hours from their last message, or 7 days after a first message from an ad), and never with the human agent tag:
  past the window, their messages wait for the team.
- Meta expects an automated answer within 30 seconds: if writing it takes long, a short "one moment" goes first.
- Up to three short messages, each within Instagram's 1,000 bytes, with quick replies when it offers a few choices. Photos, voice messages and PDFs
  are understood first (understand.py). A person asked for, or an upset customer, goes to the team (Live chat and the Inbox), and a chat a team
  member is handling is left to them.
"""
import asyncio
import logging
import os
import re
from datetime import timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.future import select

import ai
import assist
import behaviour
import brain
import plans
from backend.models import Contact, Conversation, InstagramAccount, InstagramChat, InstagramMessage, Message
from database import async_session
from instagram import accounts, chats, graph, outbound, settings, understand
from notify.events import fire_and_forget, handoff_requested
from realtime import notify_owner
from utils import FlowEngine, generate_ai_response
from voice import memory as voice_memory
from whatsapp.replies import ASKED_FOR_PERSON, HUMAN_RE, UPSET, Reply, parse, script_of

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Sorry, this assistant isn't available on Instagram right now. Please contact the business directly."
HOLDING = "One moment, let me check that for you."
PACE = float(os.getenv("INSTAGRAM_PACE", os.getenv("WHATSAPP_PACE", "1")))  # 0 in tests: no pauses between messages
PAUSE_BASE, PAUSE_PER_CHAR, PAUSE_MAX = 0.6, 0.01, 2.5
HOLD_AT = float(os.getenv("INSTAGRAM_HOLD_SECONDS", "20"))  # seconds after their last message: nothing written by then, "one moment" goes
CLAIM_STALE = timedelta(minutes=3)
LATE = timedelta(seconds=45)
OVERDUE = timedelta(seconds=10)
EARLY = timedelta(milliseconds=250)
HISTORY = 20
SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")

_timers: set = set()


# ─── when to answer ───────────────────────────────────────────────
def schedule(chat_id: str, due) -> None:
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
        logger.exception(f"Instagram reply in chat {chat_id} failed: {e}")
    finally:
        again = await _release(chat_id)
        if again is not None:  # they wrote while it was answering
            schedule(chat_id, max(again, chats.now()))


async def sweep() -> None:
    """Chats whose answer is overdue: their timer was in a process that restarted, or a process died answering."""
    now = chats.now()
    async with async_session() as db:
        await db.execute(update(InstagramChat).where(
            InstagramChat.reply_claimed_at.isnot(None), InstagramChat.reply_claimed_at < now - CLAIM_STALE,
            InstagramChat.reply_due_at.is_(None)).values(reply_due_at=now - OVERDUE))
        await db.commit()
        ids = (await db.execute(select(InstagramChat.id).where(
            InstagramChat.reply_due_at.isnot(None), InstagramChat.reply_due_at <= now - OVERDUE).limit(50))).scalars().all()
    for chat_id in ids:
        schedule(chat_id, now)


async def _claim(chat_id: str) -> bool:
    now = chats.now()
    async with async_session() as db:
        claimed = await db.execute(update(InstagramChat).where(
            InstagramChat.id == chat_id, InstagramChat.reply_due_at.isnot(None), InstagramChat.reply_due_at <= now + EARLY,
            or_(InstagramChat.reply_claimed_at.is_(None), InstagramChat.reply_claimed_at < now - CLAIM_STALE),
        ).values(reply_claimed_at=now, reply_due_at=None))
        await db.commit()
    return claimed.rowcount == 1


async def _release(chat_id: str):
    async with async_session() as db:
        await db.execute(update(InstagramChat).where(InstagramChat.id == chat_id).values(reply_claimed_at=None))
        await db.commit()
        due = (await db.execute(select(InstagramChat.reply_due_at).where(InstagramChat.id == chat_id))).scalar_one_or_none()
    return chats.aware(due)


# ─── answering ────────────────────────────────────────────────────
async def _answer(chat_id: str) -> None:
    async with async_session() as db:
        chat = await db.get(InstagramChat, chat_id)
        account = await db.get(InstagramAccount, chat.account_id) if chat and chat.account_id else None
        if chat is None or account is None or account.status in ("disconnected", "token"):
            return
        rows = (await db.execute(
            select(InstagramMessage, Message).join(Message, Message.id == InstagramMessage.message_id)
            .where(InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "in", InstagramMessage.handled.is_(False))
            .order_by(InstagramMessage.created_at))).all()
        if not rows or not account.ai_enabled or chats.ai_paused(chat):
            return
        bot = await accounts.assistant(db, account)
        if bot is None:
            return
        conv, _ = await chats.conversation(db, chat, bot)
        await db.commit()
        if conv.handoff_status == "human":
            return  # a team member has it
        paid = (await plans.includes(db, bot.bot_id)).instagram  # Growth and Pro (plans.py)
        replies_left = await plans.can_reply(db, bot.bot_id)
    pending = [w for w, _ in rows]
    if not chats.window_open(chat):  # Instagram allows nothing automatic now: their messages wait for the team, who can reply for 7 days
        await _done(chat.id, pending, team=True)
        return
    cfg = settings.clean(account.settings)
    last_at = chats.aware(pending[-1].created_at) or chats.now()
    await graph.action(account.ig_id, account.access_token, chat.igsid, "mark_seen")
    if cfg["typing"]:
        await graph.action(account.ig_id, account.access_token, chat.igsid, "typing_on")
    if not paid:  # like WhatsApp, it answers only on a plan that includes it
        await outbound.send_text(account, chat, NOT_AVAILABLE, sent_by="ai")
        await _done(chat.id, pending)
        return

    turn = []
    for w, m in rows:
        text = m.content
        if w.kind in understand.KINDS and cfg["understand_media"] and (w.media or {}).get("url") and not (w.media or {}).get("understood"):
            text = await understand.message(account, w, m)
        turn.append(text)
    said = "\n".join(turn)

    asked = bool(HUMAN_RE.search(said))
    upset = not asked and await assist.should_escalate(bot.user_id, said)
    if asked or upset:
        await _hand_over(account, chat, conv, bot, said, UPSET if upset else ASKED_FOR_PERSON)
        await _done(chat.id, pending, team=True)
        return
    if bot.flow_data and bot.flow_data.get("nodes") and await _flow(account, chat, conv, bot, said, cfg):
        await _done(chat.id, pending)
        return
    if not replies_left:  # its AI replies for the month are used up (plans.py): the team answers from the Inbox
        await outbound.send_text(account, chat, plans.REPLIES_USED_UP, sent_by="ai")
        await _done(chat.id, pending)
        return
    reply, last_asked = await _write_in_time(account, chat, conv, bot, cfg, rows, turn, last_at)
    if await _newer(chat.id, pending) and not _late(pending):
        return  # they wrote again: the next answer covers everything they said
    await _deliver(account, chat, cfg, reply)
    fire_and_forget(plans.count_reply(bot.bot_id))
    await _done(chat.id, pending)
    if reply.handoff:
        await _flag_handoff(chat, conv, bot, said)
    if assist.is_unanswered(reply.text):
        fire_and_forget(assist.record_gap(bot.bot_id, said, "instagram", conv.conversation_id))
    fire_and_forget(brain.learn_details(conv.conversation_id, bot, said, last_asked))


async def _write_in_time(account: InstagramAccount, chat: InstagramChat, conv: Conversation, bot, cfg: dict, rows: list, turn: list[str],
                         last_at) -> tuple[Reply, str]:
    """The answer, and if it isn't written by HOLD_AT seconds after their message, a short "one moment" first: Meta expects an automated answer
    within 30 seconds."""
    task = asyncio.ensure_future(_write(chat, conv, bot, cfg, rows, turn))
    wait = HOLD_AT - (chats.now() - last_at).total_seconds()
    if wait > 0:
        await asyncio.wait({task}, timeout=wait)
    if not task.done():
        await outbound.send_text(account, chat, HOLDING, sent_by="ai")
    return await task


async def _write(chat: InstagramChat, conv: Conversation, bot, cfg: dict, rows: list, turn: list[str]) -> tuple[Reply, str]:
    turn_ids = [m.id for _, m in rows]
    async with async_session() as db:
        history_rows = (await db.execute(select(Message).where(
            Message.conversation_id == conv.conversation_id, Message.role.in_(["user", "assistant"]),
            Message.id.notin_(turn_ids)).order_by(Message.timestamp.desc()).limit(HISTORY + 1))).scalars().all()
        talk = await db.get(Conversation, conv.conversation_id)
        captured, came = talk.captured_data or {}, talk.origin or {}
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows[:HISTORY])]
    numbered = len(turn) > 1
    said = "\n".join(f"[{i}] {t}" for i, t in enumerate(turn, 1)) if numbered else turn[0]
    first = not any(h["role"] == "assistant" for h in history)
    welcome = cfg["welcome"] if first else ""
    knowledge = await brain.knowledge(bot, "\n".join(turn))
    about = await _about(bot.bot_id, chat)
    base = brain.system_prompt(bot, captured=captured, first_message=first and not welcome, channel="instagram", knowledge_text=knowledge)
    ad = came.get("headline") if came.get("channel") == "instagram_ad" else None
    extra = rules(cfg, numbered, about, ongoing=not first, match_language=behaviour.clean(bot.behaviour).get("language", "match") == "match",
                  script=next((s for s in map(script_of, reversed(turn)) if s), None), ad=ad)
    system = base.replace("\n\n# Business knowledge", extra + "\n\n# Business knowledge", 1) if "\n\n# Business knowledge" in base else base + extra
    messages = brain.turns(history, said)
    raw = await asyncio.to_thread(generate_ai_response, system, "", said, history=messages[:-1],
                                  provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key)
    reply = parse(raw, [], [], {**cfg, "send_files": False})
    reply.bubbles = [(piece, None) for text, _ in reply.bubbles for piece in pieces(text)]
    if welcome:
        reply.bubbles.insert(0, (welcome, None))
    if not reply.bubbles:
        reply.bubbles = [(ai.SORRY, None)]
    return reply, next((h["content"] for h in reversed(history) if h["role"] == "assistant"), "")


def pieces(text: str, limit: int = graph.TEXT_BYTES) -> list[str]:
    """A message as Instagram can take it: 1,000 bytes each (a Tamil letter is 3), split between sentences where it can be."""
    text = (text or "").strip()
    if len(text.encode("utf-8")) <= limit:
        return [text] if text else []
    out, current = [], ""
    for sentence in (s for s in SENTENCE.split(text) if s.strip()):
        candidate = f"{current} {sentence}".strip() if current else sentence.strip()
        if len(candidate.encode("utf-8")) <= limit:
            current = candidate
            continue
        if current:
            out.append(current)
        while len(sentence.encode("utf-8")) > limit:  # one sentence longer than Instagram allows: cut at a word
            head = graph.fit(sentence, limit)
            out.append(head)
            sentence = sentence[len(head):].strip()
        current = sentence.strip()
    if current:
        out.append(current)
    return out


async def _about(bot_id: str, chat: InstagramChat) -> list[str]:
    """What's known about them, from their contact (and their calls, once they've given a number). Never their number or email."""
    if not chat.contact_id:
        return []
    async with async_session() as db:
        contact = await db.get(Contact, chat.contact_id)
    if contact is None:
        return []
    ctx = await voice_memory.context_for(bot_id, contact.e164) if contact.e164 else None
    lines = []
    name = (ctx or {}).get("name") or contact.name
    details = (ctx or {}).get("details") or {k: v for k, v in (contact.details or {}).items() if isinstance(v, (str, int, float))}
    notes = (ctx or {}).get("notes") or contact.notes
    if name:
        lines.append(f"- Name: {name}")
    if details:
        lines.append("- What they've told us: " + "; ".join(f"{k}: {v}" for k, v in list(details.items())[:12]))
    if notes:
        lines.append(f"- Notes from the team: {notes[:500]}")
    for call in (ctx or {}).get("calls") or []:
        who = "they called" if call.get("direction") == "inbound" else "we called them"
        lines.append(f"- Phone call, {call['when']} ({who}): {call['summary']}")
    return lines


def rules(cfg: dict, numbered: bool, about: list[str], ongoing: bool = False, match_language: bool = True, script: Optional[str] = None,
          ad: Optional[str] = None) -> str:
    """What the assistant is told about writing in Instagram DMs, on top of its usual instructions (brain.py)."""
    words = 50 if cfg["length"] == "short" else 100
    lines = ["", "In Instagram direct messages:",
             "- Write like a helpful person from the business answering DMs: natural, warm and brief, without a greeting or sign-off in every message.",
             f"- Keep a reply under about {words} words unless they ask for full details. Plain text only: Instagram shows stars, hashes and markdown as typed."]
    if match_language and script == "English letters":
        lines.append("- Their latest message is in English letters: reply in English letters, in the same language they used (Tamil written in English "
                     "letters, like \"price evlo?\", stays that way; so does Hindi, and English stays English), even if earlier messages were in another script.")
    elif match_language and script:
        lines.append(f"- Their latest message is in {script} script: reply in {script} script.")
    if ongoing:
        lines.append("- You're in the middle of this chat: don't greet them again or start with their name. Just answer.")
    if cfg["split"]:
        lines.append("- You may send up to 3 short messages: put a blank line between them. Often one is enough.")
    if numbered:
        lines.append("- They sent several messages since your last reply, numbered [1], [2] and so on. Answer them together.")
    if cfg["buttons"]:
        lines.append("- To offer 2 or 3 short choices, end your last message with [BUTTONS: First | Second], each at most 20 characters. Only for a "
                     "real choice they need to make.")
    lines += ["- If they share a post, reel or story, you can't see it: ask what they'd like to know about it.",
              "- If they mentioned you in their story, thank them in a sentence. If they replied to your story, answer what they said about it.",
              "- If they need someone from the team to act (a complaint, a refund, a change to an order or booking, or a question the business "
              "information doesn't answer that they still want answered), put [HANDOFF] on its own line and tell them someone will reply here. Don't "
              "hand over just because the business doesn't offer what they asked about: say so kindly and mention what it does offer.",
              "- Only help with this business, its products and services. Politely decline anything else, such as general questions or help with "
              "writing or coding."]
    if ad:  # the business's own ad, from Meta's referral (leads/origin.py): they shouldn't be asked what they saw
        lines.append(f"- They came from your Instagram ad \"{ad}\". Answer about what it offers; don't ask which ad they mean.")
    if about:
        lines += ["", "What you know about this person (use it naturally; don't recite it):"] + about
    return "\n".join(lines)


# ─── sending ──────────────────────────────────────────────────────
async def _pause(text: str) -> None:
    """Wait as a person would before a second or third message."""
    wait = min(PAUSE_MAX, PAUSE_BASE + len(text) * PAUSE_PER_CHAR)
    if wait > 0 and PACE > 0:
        await asyncio.sleep(wait * PACE)


async def _deliver(account: InstagramAccount, chat: InstagramChat, cfg: dict, reply: Reply) -> None:
    for i, (text, _) in enumerate(reply.bubbles):
        last = i == len(reply.bubbles) - 1
        if i:
            if cfg["typing"]:
                await graph.action(account.ig_id, account.access_token, chat.igsid, "typing_on")
            await _pause(text)
            if await _team_took_over(chat.id):
                return
        quick = reply.buttons if last and reply.buttons else None
        w = await outbound.send_text(account, chat, text, sent_by="ai", quick_replies=quick)
        if w.status == "failed":
            return


async def _team_took_over(chat_id: str) -> bool:
    """A team member wrote in the chat while the assistant was mid-reply: the rest of the reply isn't sent."""
    async with async_session() as db:
        chat = await db.get(InstagramChat, chat_id)
        conv = await db.get(Conversation, chat.conversation_id) if chat and chat.conversation_id else None
    return chat is None or chats.ai_paused(chat) or (conv is not None and conv.handoff_status == "human")


async def _flow(account: InstagramAccount, chat: InstagramChat, conv: Conversation, bot, said: str, cfg: dict) -> bool:
    """The assistant's visual flow, when it has one: each of its messages as its own DM."""
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
        if i:
            if cfg["typing"]:
                await graph.action(account.ig_id, account.access_token, chat.igsid, "typing_on")
            await _pause(text)
        if (await outbound.send_text(account, chat, text, sent_by="ai")).status == "failed":
            break
    if handoff:
        await _flag_handoff(chat, conv, bot, said, already_pending=True)
    return True


async def _hand_over(account: InstagramAccount, chat: InstagramChat, conv: Conversation, bot, said: str, default: str) -> None:
    """A person was asked for, or they're upset: the team is told, and they hear that."""
    async with async_session() as db:
        row = await db.get(Conversation, conv.conversation_id)
        row.handoff_status, row.handoff_requested = "pending", True
        await db.commit()
    text = await assist.away_reply(bot.user_id) or default
    await outbound.send_text(account, chat, text, sent_by="ai")
    await _flag_handoff(chat, conv, bot, said, already_pending=True)


async def _flag_handoff(chat: InstagramChat, conv: Conversation, bot, said: str, already_pending: bool = False) -> None:
    if not already_pending:
        async with async_session() as db:
            row = await db.get(Conversation, conv.conversation_id)
            if row.handoff_status == "ai":
                row.handoff_status, row.handoff_requested = "pending", True
            await db.commit()
    fire_and_forget(handoff_requested(conv.conversation_id, said))
    await notify_owner(bot.user_id, "handoff_requested", {
        "conversation_id": conv.conversation_id, "bot_id": bot.bot_id, "bot_name": bot.bot_name, "session_id": conv.visitor_session_id,
        "message": said, "phone": None, "name": chats.label(chat)})


async def _newer(chat_id: str, pending: list[InstagramMessage]) -> bool:
    async with async_session() as db:
        return (await db.execute(select(InstagramMessage.id).where(
            InstagramMessage.chat_id == chat_id, InstagramMessage.direction == "in", InstagramMessage.handled.is_(False),
            InstagramMessage.id.notin_([w.id for w in pending])))).first() is not None


def _late(pending: list[InstagramMessage]) -> bool:
    first = chats.aware(pending[0].created_at)
    return bool(first and first < chats.now() - LATE)


async def _done(chat_id: str, pending: list[InstagramMessage], team: bool = False) -> None:
    """The messages are answered (or are the team's now). Unread, for the team, is what's still waiting."""
    async with async_session() as db:
        await db.execute(update(InstagramMessage).where(InstagramMessage.id.in_([w.id for w in pending])).values(handled=True))
        if not team:
            waiting = (await db.execute(select(InstagramMessage.id).where(
                InstagramMessage.chat_id == chat_id, InstagramMessage.direction == "in", InstagramMessage.handled.is_(False)))).all()
            await db.execute(update(InstagramChat).where(InstagramChat.id == chat_id).values(unread=len(waiting)))
        await db.commit()
