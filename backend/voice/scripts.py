"""
Incoming and outgoing agents, and what each says (Voice > Agents, Voice > Knowledge).

An assistant has one voice_agents row. Its columns are the outgoing agent; the incoming agent's phone settings are
kept in `inbound` once someone edits them (until then it's the same as the outgoing one). What the agent says on each
kind of call (opening, personality, how to handle the call, goal, details to collect) is a VoiceScript per direction;
until one is saved, the agent's own opening line, goal and fields are used, as before scripts existed.
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import Bot, VoiceAgent, VoiceScript
from voice import llm

logger = logging.getLogger(__name__)

DIRECTIONS = ("inbound", "outbound")
# Phone settings each agent has its own of. Its name, the business name and pronunciations belong to the business and
# are shared; voicemail is for outgoing calls only.
PER_DIRECTION = (
    "enabled", "language", "understand_code_mixed", "follow_caller_language", "switch_languages", "voice_id", "speaking_rate",
    "allow_interruptions", "silence_timeout_sec", "silence_reminders", "max_call_minutes", "end_call_phrases",
    "transfer_enabled", "transfer_number", "transfer_when", "transfer_mode", "ambience", "ambience_volume", "ai_model",
    "functions",
)
# The opening for someone the assistant has spoken to before. Languages without one use the usual opening (the agent
# still knows who they are).
KNOWN_GREETINGS = {
    "en-IN": "Hello {{name}}, how can I help you today?",
    "ta-IN": "வணக்கம் {{name}}! இன்று நான் உங்களுக்கு எப்படி உதவலாம்?",
    "hi-IN": "नमस्ते {{name}} जी! बताइए, आज मैं आपकी क्या मदद करूँ?",
}
PERSONALITIES = {
    "friendly": "Warm and friendly, like a helpful person at the front desk.",
    "professional": "Polite, clear and professional; brief and to the point.",
    "caring": "Gentle, patient and reassuring, like a good clinic receptionist.",
    "cheerful": "Upbeat and cheerful, but never pushy.",
    "formal": "Calm and formal, with respectful forms of address.",
    "playful": "Light and playful, for a fun brand or children's classes, while staying clear and respectful.",
}
GREETING_CHARS, GOAL_CHARS, PERSONALITY_CHARS, INSTRUCTIONS_CHARS = 300, 500, 300, 4000


def for_direction(agent: VoiceAgent, direction: str) -> VoiceAgent:
    """The agent as it is for one kind of call: a copy, never saved."""
    copy = VoiceAgent(**{c.name: getattr(agent, c.name) for c in VoiceAgent.__table__.columns})
    if direction == "inbound":
        for key, value in (agent.inbound or {}).items():
            if key in PER_DIRECTION:
                setattr(copy, key, value)
    return copy


def default_script(agent: VoiceAgent, direction: str) -> VoiceScript:
    """Before a script is saved: what the agent (for that direction) said before scripts existed."""
    return VoiceScript(bot_id=agent.bot_id, direction=direction, user_id=agent.user_id, greeting=agent.greeting or "",
                       greeting_known=KNOWN_GREETINGS.get(agent.language or "en-IN", ""), personality="",
                       instructions="", call_goal=agent.call_goal or "", collect_fields=agent.collect_fields or [])


async def script_for(db: AsyncSession, agent: VoiceAgent, direction: str) -> tuple[VoiceScript, bool]:
    """The direction's script, and whether it's been saved."""
    row = (await db.execute(select(VoiceScript).where(
        VoiceScript.bot_id == agent.bot_id, VoiceScript.direction == direction))).scalars().first()
    return (row, True) if row else (default_script(for_direction(agent, direction), direction), False)


def apply(agent: VoiceAgent, script: VoiceScript, known_name: Optional[str]) -> None:
    """Put a script's opening, goal and fields on a call's agent (a copy from for_direction). Someone it knows gets the
    opening for known callers, with their name in it."""
    known = (script.greeting_known or "").strip() if known_name else ""
    agent.greeting = known or script.greeting or ""
    agent.call_goal = script.call_goal or ""
    agent.collect_fields = script.collect_fields or []


def personality(value: Optional[str]) -> str:
    value = (value or "").strip()
    return PERSONALITIES.get(value, value)[:PERSONALITY_CHARS]


def style(script: VoiceScript) -> dict:
    """What a call's replies are told about how to behave (llm.system_prompt)."""
    return {"personality": personality(script.personality), "instructions": (script.instructions or "").strip()}


def script_json(script: VoiceScript, saved: bool) -> dict:
    return {
        "direction": script.direction, "saved": saved, "greeting": script.greeting or "",
        "greeting_known": script.greeting_known or "", "personality": script.personality or "",
        "instructions": script.instructions or "", "call_goal": script.call_goal or "",
        "collect_fields": script.collect_fields or [], "answers": script.answers or [],
    }


# ─── Write with AI ────────────────────────────────────────────────
DRAFT_PROMPT = """You write the call script for a business's AI phone assistant. The owner answered some questions;
use their answers and the business information. Return only JSON with these keys:
"greeting": one short, friendly sentence the assistant says first, in LANGUAGE (it's said straight after the required
"I'm an automated assistant, this call may be recorded" line, so don't repeat that or introduce the assistant),
"greeting_known": the same for a caller it has spoken to before, in LANGUAGE, with the placeholder {{name}} where their
first name goes,
"personality": one of friendly, professional, caring, cheerful, formal, playful, or a short description,
"call_goal": one sentence: what a successful call achieves,
"collect_fields": at most 6 details to find out on the call, each {"label": short name, "type": one of text, number,
yes_no, choice, date, phone, email, "description": a short hint, "choices": [options, only for choice], "required":
true or false}; don't include the caller's phone number (it's known),
"instructions": the script, in English: short numbered steps for how these calls should go, then rules (what to do
when the caller is busy, not interested, angry, or asks for a person; what never to say or promise). Under 1,500
characters. Plain sentences, no markdown headings.
Only use facts from the business information and the answers. Never invent prices, offers, timings or policies."""


async def draft(bot: Bot, agent: VoiceAgent, direction: str, answers: list[dict], knowledge: str) -> dict:
    """A script written from the owner's answers and the business's knowledge (not saved; the owner reviews it)."""
    language = llm.LANGUAGE_NAMES.get(agent.language or "en-IN", "Indian English")
    kind = ("incoming calls: people calling the business" if direction == "inbound" else
            "outgoing calls: the business calling people who asked to be called or agreed to it")
    told = "\n".join(f"- {a['question']}: {a['answer']}" for a in answers if (a.get("answer") or "").strip())
    user = (f"Calls: {kind}.\nBusiness: {agent.company_name or bot.bot_name}.\nLanguage of the calls: {language}.\n\n"
            f"The owner's answers:\n{told or '- (none)'}\n\nBusiness information:\n{(knowledge or '(none)')[:6000]}")
    raw = await llm._complete(bot, DRAFT_PROMPT.replace("LANGUAGE", language), user, max_tokens=1500)
    match = re.search(r"\{.*\}", raw or "", re.S)
    data = json.loads(match.group(0)) if match else {}
    fields = []
    for f in data.get("collect_fields") or []:
        if not isinstance(f, dict) or not str(f.get("label") or "").strip():
            continue
        kind_ = f.get("type") if f.get("type") in llm.FIELD_TYPES else "text"
        choices = [str(c)[:40] for c in (f.get("choices") or []) if str(c).strip()][:12] if kind_ == "choice" else []
        if kind_ == "choice" and len(choices) < 2:
            kind_, choices = "text", []
        fields.append({"label": str(f["label"]).strip()[:100], "type": kind_,
                       "description": str(f.get("description") or "")[:200], "choices": choices,
                       "required": bool(f.get("required"))})
    preset = str(data.get("personality") or "").strip()
    return {
        "greeting": str(data.get("greeting") or "").strip()[:GREETING_CHARS],
        "greeting_known": str(data.get("greeting_known") or "").strip()[:GREETING_CHARS],
        "personality": preset.lower() if preset.lower() in PERSONALITIES else preset[:PERSONALITY_CHARS],
        "call_goal": str(data.get("call_goal") or "").strip()[:GOAL_CHARS],
        "collect_fields": fields[:6],
        "instructions": str(data.get("instructions") or "").strip()[:INSTRUCTIONS_CHARS],
    }
