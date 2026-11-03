"""How the assistant behaves on an Instagram account (Instagram > Assistant). Kept on the account as JSON; anything missing or out of range falls
back to the defaults, so old rows and partial updates are always valid."""
from typing import Any

DEFAULTS: dict[str, Any] = {
    "wait_seconds": 4,         # after their last message, in case they're still typing (Meta expects an answer within 30 seconds)
    "typing": True,            # show "typing…" while it writes
    "split": True,             # a few short messages rather than one long one
    "length": "short",         # short, normal
    "understand_media": True,  # photos, voice messages and PDFs
    "buttons": True,           # offer 2-3 choices as quick replies
    "pause_hours": 12,         # after a team member replies, the assistant leaves the chat to them this long
    "welcome": "",             # the first reply to someone new starts with this, if set
}
WAIT_SECONDS = (0, 10)       # kept short: an automated reply must come within Meta's 30 seconds
PAUSE_HOURS = (1, 4, 12, 24, 72)
LENGTHS = ("short", "normal")
WELCOME_CHARS = 300


def clean(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    for key in ("typing", "split", "understand_media", "buttons"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    try:
        out["wait_seconds"] = max(WAIT_SECONDS[0], min(WAIT_SECONDS[1], int(raw.get("wait_seconds", out["wait_seconds"]))))
    except (TypeError, ValueError):
        pass
    try:
        hours = int(raw.get("pause_hours", out["pause_hours"]))
        out["pause_hours"] = hours if hours in PAUSE_HOURS else DEFAULTS["pause_hours"]
    except (TypeError, ValueError):
        pass
    if raw.get("length") in LENGTHS:
        out["length"] = raw["length"]
    if isinstance(raw.get("welcome"), str):
        out["welcome"] = raw["welcome"].strip()[:WELCOME_CHARS]
    return out
