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
# Details the assistant collects during the chat (see brain.py). On for every assistant unless turned off.
STANDARD_FIELDS = {"name": "Name", "phone": "Phone number", "email": "Email"}
TIMINGS = {
    "early": "Ask for the first missing detail early, right after your first answer.",
    "after_answer": "Answer their question first, then ask for one missing detail when it fits naturally.",
    "interest": "Only ask once they show real interest (pricing, booking, a visit, a quote, a callback).",
}
COLLECT_DEFAULTS: dict[str, Any] = {"enabled": True, "fields": ["name", "phone", "email"], "custom": [], "timing": "after_answer"}

DEFAULTS: dict[str, Any] = {
    "reply_length": "balanced",
    "language": "match",
    "ask_for_contact": False,
    "offer_human": True,
    "fallback_followup": "",
    "collect": COLLECT_DEFAULTS,
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
    out["collect"] = clean_collect(data.get("collect"))
    return out


def clean_collect(data: Any) -> dict:
    """Which details to collect: standard ones plus up to 6 of the business's own (e.g. Budget, City)."""
    data = data if isinstance(data, dict) else {}
    out = dict(COLLECT_DEFAULTS)
    if isinstance(data.get("enabled"), bool):
        out["enabled"] = data["enabled"]
    if isinstance(data.get("fields"), list):
        out["fields"] = [f for f in STANDARD_FIELDS if f in data["fields"]]
    if isinstance(data.get("custom"), list):
        seen = set(STANDARD_FIELDS) | {label.lower() for label in STANDARD_FIELDS.values()}
        custom = []
        for label in data["custom"]:
            label = " ".join(str(label or "").split())[:40]
            if label and label.lower() not in seen:
                seen.add(label.lower())
                custom.append(label)
        out["custom"] = custom[:6]
    if data.get("timing") in TIMINGS:
        out["timing"] = data["timing"]
    return out


def collect(behaviour: Optional[dict]) -> dict:
    """Collection settings, defaults included even for assistants that never saved Behaviour."""
    return clean_collect((behaviour or {}).get("collect"))


def rules(behaviour: Optional[dict]) -> str:
    """Extra prompt lines for these settings; empty when the bot never set any."""
    if not behaviour:
        return ""
    b = clean(behaviour)
    lines = [LENGTHS[b["reply_length"]], LANGUAGES[b["language"]]]
    if b["ask_for_contact"] and not b["collect"]["enabled"]:
        lines.append("When the visitor shows interest in buying, booking or getting a quote, politely ask for their name "
                     "and phone number once. Don't ask again if they decline.")
    if b["offer_human"]:
        lines.append("If you can't help, offer to connect them with someone from the team; they only need to ask to talk to a person.")
    return "\n".join(f"- {line}" for line in lines if line)


def fallback(behaviour: Optional[dict]) -> str:
    """What to say when the information isn't available."""
    follow = clean(behaviour)["fallback_followup"] if behaviour else ""
    return f"{FALLBACK} {follow}".strip()
