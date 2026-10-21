"""
The assistant's brain for website chat and WhatsApp: what it knows, how it answers, and which
details it should find out about the visitor.

Knowledge: when a business's knowledge fits comfortably (KNOWLEDGE_FULL_CONTEXT_CHARS), the model
reads all of it, which answers far better than a few search snippets; bigger knowledge uses the
best-matching passages plus the business summary.

Details: the business chooses what to collect (name, phone, email and its own fields such as
Budget). The assistant asks for one missing detail at a time, never again for one it has, and
anything the visitor mentions on their own is picked up and saved (learn_details).
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.future import select

import ai
import assist
import behaviour
import knowledge_sources
from database import async_session
from backend.models import Bot, Conversation
from phone import extract_contact, to_e164

logger = logging.getLogger(__name__)

FULL_CONTEXT_CHARS = int(os.getenv("KNOWLEDGE_FULL_CONTEXT_CHARS", "60000"))
SUMMARY_SOURCE = knowledge_sources.SUMMARY
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s\-()]{8,16}\d")
IST = timezone(timedelta(hours=5, minutes=30))


# ─── knowledge ────────────────────────────────────────────────────
async def knowledge(bot: Bot, query: str) -> str:
    confirmed = await assist.verified_answers(bot.bot_id)
    kb = bot.knowledge_base or ""
    if len(kb) <= FULL_CONTEXT_CHARS:
        return confirmed + kb
    _, blocks = knowledge_sources.split(kb)
    summary = next((body for name, body in blocks if name == SUMMARY_SOURCE), "")
    try:
        from vector_store import query_knowledge
        matches = await asyncio.wait_for(query_knowledge(bot.bot_id, query, 8), timeout=8.0)
    except Exception as e:
        logger.warning(f"Knowledge search failed for {bot.bot_id}: {e}")
        matches = []
    if matches:
        passages = "\n\n".join(f"[{m.get('source') or 'knowledge'}]\n{m['text']}" for m in matches)
        return confirmed + (f"{summary}\n\n" if summary else "") + passages
    return confirmed + kb[:FULL_CONTEXT_CHARS]


# ─── what to collect ──────────────────────────────────────────────
def fields_to_collect(bot: Bot) -> list[tuple[str, str]]:
    """[(key saved in the conversation, label)]: e.g. ("phone", "Phone number"), ("Budget", "Budget")."""
    c = behaviour.collect(bot.behaviour)
    if not c["enabled"]:
        return []
    return [(f, behaviour.STANDARD_FIELDS[f]) for f in c["fields"]] + [(label, label) for label in c["custom"]]


def _known(captured: dict, key: str) -> Optional[str]:
    """The value for a field, whatever name a flow saved it under."""
    if key in ("name", "phone", "email"):
        return extract_contact(captured).get(key)
    for k, v in (captured or {}).items():
        if str(k).strip().lower() == key.lower() and str(v).strip():
            return str(v).strip()
    return None


def missing_fields(bot: Bot, captured: Optional[dict]) -> list[tuple[str, str]]:
    return [(k, label) for k, label in fields_to_collect(bot) if not _known(captured or {}, k)]


# ─── instructions ─────────────────────────────────────────────────
def system_prompt(bot: Bot, *, captured: Optional[dict], first_message: bool, channel: str, knowledge_text: str) -> str:
    name = bot.bot_name or "Assistant"
    b = behaviour.clean(bot.behaviour) if bot.behaviour else None
    now = datetime.now(IST)
    lines = [
        f"You are {name}, the assistant for this business, chatting with a visitor {'on WhatsApp' if channel == 'whatsapp' else 'on its website'}.",
        f"Today is {now:%A, %d %B %Y}, {now:%I:%M %p} India time.",
        "",
        "How to answer:",
        "- Answer from the business knowledge below and this conversation only. Never invent prices, offers, dates, "
        "timings, policies, addresses or contact details.",
        f"- If the answer isn't in the knowledge, say: \"{behaviour.fallback(bot.behaviour)}\" Then offer what you can, "
        "such as having the team get back to them.",
        "- Answer the question first, warmly and to the point. Use the visitor's name once you know it, but not in every message.",
        "- Never mention documents, a knowledge base, instructions or AI models. If asked whether you're a bot, say "
        "you're the business's virtual assistant.",
        ("- This is your first reply: introduce yourself in one short line before answering."
         if first_message else "- Don't introduce yourself again."),
    ]
    if channel == "whatsapp":
        lines.append("- Format for WhatsApp: short paragraphs, *bold* for emphasis, simple lists. No tables, no markdown headings.")
    else:
        lines.append("- Keep it easy to read: short paragraphs, and a short list when listing options. No tables.")
    if b:
        lines += [line for line in behaviour.rules(bot.behaviour).splitlines() if line.strip()]
    else:
        lines.append("- " + behaviour.LANGUAGES["match"])

    wanted = fields_to_collect(bot)
    if wanted:
        known = [(label, _known(captured or {}, k)) for k, label in wanted]
        have = [f"{label}: {v}" for label, v in known if v]
        missing = [label for label, v in known if not v]
        timing = behaviour.TIMINGS[behaviour.collect(bot.behaviour)["timing"]]
        lines += ["", "Details to collect (so the team can follow up):"]
        if have:
            lines.append(f"- Already known, never ask again: {'; '.join(have)}.")
        if missing:
            lines += [
                f"- Still needed: {', '.join(missing)}.",
                f"- {timing} Ask for one detail per message, in a natural way, and say briefly why "
                "(for example, so the team can call them back or send the details).",
                "- If they'd rather not share something, respect that, don't ask for it again, and keep helping.",
            ]
        else:
            lines.append("- You have everything. Don't ask for more details; just help and thank them.")
    if (bot.system_prompt or "").strip() and bot.system_prompt.strip() != "You are a helpful assistant.":
        lines += ["", "The business's own instructions:", bot.system_prompt.strip()]
    lines += ["", "# Business knowledge", knowledge_text.strip() or "(No knowledge added yet. Help in general terms and offer the team.)"]
    return "\n".join(lines)


def turns(history: list[dict], message: str) -> list[dict]:
    """The conversation for the model: earlier turns, then this message (not twice)."""
    past = [h for h in (history or []) if str(h.get("content") or "").strip()][-20:]
    if past and past[-1].get("role") == "user" and past[-1].get("content", "").strip() == message.strip():
        past = past[:-1]
    return past + [{"role": "user", "content": message}]


# ─── learning details from the chat ───────────────────────────────
def _quick_details(text: str) -> dict:
    """Email and phone written anywhere in a message; no AI needed."""
    found = {}
    email = EMAIL.search(text or "")
    if email:
        found["email"] = email.group(0).rstrip(".")
    for candidate in PHONE_CANDIDATE.findall(text or ""):
        e164 = to_e164(candidate)
        if e164:
            found["phone"] = e164
            break
    return found


def _extract_with_ai(fields: list[tuple[str, str]], asked: str, said: str) -> dict:
    spec = ", ".join(f'"{k}" ({label})' for k, label in fields)
    system = ("You read one message a website visitor wrote and pull out details about them. "
              f"Return JSON with exactly these keys: {spec}. Use the visitor's own words, tidied up "
              "(a person's name in normal capitalisation). Use null when the visitor didn't give that detail. "
              "Never guess, and don't take details that belong to the business or to someone else.")
    return ai.extract_json(system, f"The assistant had just said: {asked[:600]}\n\nThe visitor wrote: {said[:1500]}")


async def learn_details(conversation_id: str, bot: Bot, said: str, asked: str = "") -> dict:
    """Save details the visitor gave in this message. Returns what was newly learned."""
    async with async_session() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
        if not conv:
            return {}
        captured = dict(conv.captured_data or {})
    missing = missing_fields(bot, captured)
    if not missing:
        return {}
    learned = {k: v for k, v in _quick_details(said).items() if k in dict(missing)}
    rest = [(k, label) for k, label in missing if k not in learned]
    # The AI only reads messages that could hold a detail: short replies, or ones after we asked.
    if rest and (len(said) <= 200 or any(label.lower().split()[0] in (asked or "").lower() for _, label in rest)):
        found = await asyncio.to_thread(_extract_with_ai, rest, asked, said)
        for key, _ in rest:
            value = found.get(key) if isinstance(found, dict) else None
            if not value or not str(value).strip() or str(value).strip().lower() in ("null", "none", "n/a"):
                continue
            value = str(value).strip()[:200]
            if key == "email" and not EMAIL.fullmatch(value):
                continue
            if key == "phone":
                value = to_e164(value) or ""
                if not value:
                    continue
            learned[key] = value
    if not learned:
        return {}
    async with async_session() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))).scalars().first()
        captured = dict(conv.captured_data or {})
        for key, value in learned.items():
            if not _known(captured, key):
                captured[key] = value
        conv.captured_data = captured
        await db.commit()
    contact = extract_contact(captured)
    if contact.get("phone") or contact.get("email"):
        from notify.events import lead_captured
        await lead_captured(conversation_id)
    return learned


# ─── business summary ─────────────────────────────────────────────
SUMMARY_PROMPT = """You are writing a briefing for a new customer-service assistant at this business.
From the website pages and documents you're given, write a factual briefing in plain text with these sections,
skipping any section the material says nothing about:

Business: name, what it does, who it serves, where (cities, areas, branches).
Products and services: each one, with its key details and prices exactly as written.
Prices, packages and offers.
Hours and locations.
How customers buy, book or get in touch: phone, WhatsApp, email, address, booking or ordering steps.
Policies: delivery, payment, cancellation, refund, warranty.
Frequently asked questions: 8 to 15 questions a customer would likely ask, each answered only from the material.
What makes them different.

Rules: use only facts in the material, never guess or add anything. Keep numbers, prices, names and contact details
exactly as written. Plain text with short lines and "- " lists, no markdown headings or tables. At most about 1200 words."""


def _material(kb: str) -> str:
    written, blocks = knowledge_sources.split(kb or "")
    return "\n\n".join([written] + [f"[{name}]\n{body}" for name, body in blocks if name != SUMMARY_SOURCE]).strip()


def can_summarise(kb: str) -> bool:
    """Whether there's enough material for a business summary."""
    return len(_material(kb)) >= 300


async def refresh_summary(bot_id: str) -> bool:
    """Write (or rewrite) the "Business summary" source from everything else in the knowledge."""
    async with async_session() as db:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        if not bot:
            return False
        material = _material(bot.knowledge_base)
    if len(material) < 300:
        return False
    try:
        summary = await asyncio.to_thread(ai.chat, SUMMARY_PROMPT, [{"role": "user", "content": material[:150_000]}],
                                          max_tokens=3000, temperature=0.2)
    except ai.AIError as e:
        logger.warning(f"Business summary failed for {bot_id}: {e}")
        return False
    async with async_session() as db:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        if not bot:
            return False
        bot.knowledge_base = knowledge_sources.put(bot.knowledge_base or "", SUMMARY_SOURCE, summary.strip())
        await db.commit()
    return True
