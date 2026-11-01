"""
An assistant's customer emails (mail plan, phase 1): which are on, with their follow-ups (its own, else the
workspace's), the settings of the emails that have them, and the design each email uses.

The design: what the business saved for the assistant in that language, else in English, else (for the welcome
email) the workspace's own first email after a chat as it was written before designs existed, else the ready-made one.
"""
from typing import Optional

from sqlalchemy.future import select

from backend.models import EmailSetup, EmailTemplate, IntegrationSettings
from mail import designs
from notify import automations

SETTINGS: dict[str, dict] = {
    # The first email after a chat: the AI's note and files are Growth's (on Starter it's text and buttons).
    "welcome": {"ai_note": True, "files": [], "ai_files": True, "max_files": 2},
    # The AI's email after a call, per direction: off, review (the team approves each), auto.
    "after_call": {"inbound": "off", "outbound": "off", "approved": 0, "approved_unchanged": 0, "suggested": False},
    # Who answers when someone replies (mail/replies.py): ai, draft (the AI writes, the team sends), team.
    "replies": {"mode": "draft"},
    # Leads from other places (mail/intake.py): the email at once, and a call within minutes.
    "lead_email": {"enabled": True},
    "lead_call": {"enabled": False, "minutes": 5},
    "journeys": {"per_day": 1, "per_week": 3},  # the most journey emails one person gets, across all journeys
    "during_call": {"enabled": False},  # the phone agent can email a file or a note while they talk (mail/during_call.py)
    "callback_booked": {"enabled": False},
    "voicemail": {"enabled": False},
    "missed_chat": {"enabled": False, "minutes": 10},
    "chat_copy": {"enabled": False},
    "question_answer": {"enabled": True},  # goes only when the team sends it from Questions
    "consent": {"ask": False, "words": "Send me offers and news"},  # the tick box under the chat's email question
    "fast_call": {"enabled": False},  # Pro: a call when someone opens the booking times from an email and doesn't book (mail/engagement.py)
    "agent": {"level": "off", "per_day": 20},  # the email agent (mail/agent.py): off, drafts, morning, auto
    "mailbox": {"connection_id": None},  # someone's Gmail or Outlook its one-to-one emails go from (mail/mailbox.py)
    "meeting": {"thanks": True, "missed": True},
}


async def automations_for(db, owner_id: str, bot_id: Optional[str], settings: Optional[IntegrationSettings] = None) -> dict:
    """The workspace's automations, with what the assistant set for itself."""
    if settings is None:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    found = automations.automations(settings)
    row = await db.get(EmailSetup, bot_id) if bot_id else None
    if row is not None and row.user_id == owner_id and row.automations:
        for key, saved in row.automations.items():
            if key in found:
                found[key] = automations._normalize(saved, automations.DEFAULTS[key])
    return found


async def settings_for(db, bot_id: Optional[str]) -> dict:
    row = await db.get(EmailSetup, bot_id) if bot_id else None
    saved = (row.settings if row is not None else None) or {}
    return {kind: {**defaults, **(saved.get(kind) or {})} for kind, defaults in SETTINGS.items()}


async def save_settings(db, owner_id: str, bot_id: str, kind: str, values: dict) -> dict:
    row = await db.get(EmailSetup, bot_id)
    if row is None:
        row = EmailSetup(bot_id=bot_id, user_id=owner_id, settings={})
        db.add(row)
    current = dict(row.settings or {})
    current[kind] = {**SETTINGS[kind], **(current.get(kind) or {}), **values}
    row.settings = current
    return current[kind]


async def design_for(db, owner_id: str, bot_id: Optional[str], kind: str, language: str = "en") -> dict:
    """{subject, blocks, language, saved}: what this assistant's email of this kind looks like."""
    if bot_id:
        for lang in dict.fromkeys((language, "en")):
            row = (await db.execute(select(EmailTemplate).where(
                EmailTemplate.bot_id == bot_id, EmailTemplate.kind == kind, EmailTemplate.language == lang))).scalars().first()
            if row is not None and row.user_id == owner_id:
                return {"subject": row.subject, "blocks": designs.clean(row.blocks), "language": lang, "saved": True}
    if kind == "welcome":
        first = (await automations_for(db, owner_id, bot_id))["chat_lead"]["steps"][0]
        if first["subject"] != automations.DEFAULTS["chat_lead"]["steps"][0]["subject"] or \
                first["body"] != automations.DEFAULTS["chat_lead"]["steps"][0]["body"]:
            # Their own words from before designs existed, with the files and buttons around them.
            ready = designs.default("welcome", "en")
            extras = [b for b in ready["blocks"] if b["type"] in ("ai_note", "files", "button")]
            return {"subject": first["subject"], "blocks": [{"type": "text", "text": first["body"]}, *extras],
                    "language": "en", "saved": False}
    return {**designs.default(kind, language), "saved": False}
