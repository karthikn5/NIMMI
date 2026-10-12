"""How a website/WhatsApp assistant should reply, set on the builder's Behaviour tab.

Stored on Bot.behaviour; turned into a few plain prompt rules. A bot that never saved
these settings (behaviour is None) gets no extra rules, so older assistants are unchanged.
"""
from typing import Any, Optional

LENGTHS = {
    "short": "Keep replies short: one to three sentences, unless the visitor asks for more detail.",
    "balanced": "",
    "detailed": "Give complete answers with the relevant details, using short paragraphs or a brief list when it helps.",
}
LANGUAGES = {
    "match": "Reply in the language the visitor writes in, including mixes like Tanglish or Hinglish.",
    "en": "Always reply in English.",
    "hi": "Always reply in Hindi.",
    "ta": "Always reply in Tamil.",
    "te": "Always reply in Telugu.",
    "kn": "Always reply in Kannada.",
    "ml": "Always reply in Malayalam.",
    "mr": "Always reply in Marathi.",
    "bn": "Always reply in Bengali.",
    "gu": "Always reply in Gujarati.",
}
DEFAULTS: dict[str, Any] = {
    "reply_length": "balanced",
    "language": "match",
    "ask_for_contact": False,
    "offer_human": True,
    "fallback_followup": "",
}
FALLBACK = "I'm sorry, I don't have that information."  # assist.is_unanswered() looks for this wording


def clean(data: Any) -> dict:
    """Keep only known settings with valid values."""
    data = data if isinstance(data, dict) else {}
    out = dict(DEFAULTS)
    if data.get("reply_length") in LENGTHS:
        out["reply_length"] = data["reply_length"]
    if data.get("language") in LANGUAGES:
        out["language"] = data["language"]
    for flag in ("ask_for_contact", "offer_human"):
        if isinstance(data.get(flag), bool):
            out[flag] = data[flag]
    out["fallback_followup"] = str(data.get("fallback_followup") or "").strip()[:300]
    return out


def rules(behaviour: Optional[dict]) -> str:
    """Extra prompt lines for these settings; empty when the bot never set any."""
    if not behaviour:
        return ""
    b = clean(behaviour)
    lines = [LENGTHS[b["reply_length"]], LANGUAGES[b["language"]]]
    if b["ask_for_contact"]:
        lines.append("When the visitor shows interest in buying, booking or getting a quote, politely ask for their name "
                     "and phone number once. Don't ask again if they decline.")
    if b["offer_human"]:
        lines.append("If you can't help, offer to connect them with someone from the team; they only need to ask to talk to a person.")
    return "\n".join(f"- {line}" for line in lines if line)


def fallback(behaviour: Optional[dict]) -> str:
    """What to say when the information isn't available."""
    follow = clean(behaviour)["fallback_followup"] if behaviour else ""
    return f"{FALLBACK} {follow}".strip()
