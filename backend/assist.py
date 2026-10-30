"""
Shared behaviour for every channel (website chat, WhatsApp, voice):

- unanswered questions are recorded, and the business's answers are used from then on
- upset customers are noticed so a person can step in
- business hours decide what "talk to a person" means right now
- leads get a simple, explainable score
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import async_session
from backend.models import KnowledgeGap, WorkspaceSettings

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

# ─── Unanswered questions ─────────────────────────────────────────
# The chat prompt tells the assistant to say exactly this when the knowledge doesn't cover a question;
# the voice prompt says it'll have the team follow up.
_UNANSWERED = re.compile(
    r"(don'?t|do not) have (that|this|any|the) information|not (able|sure) to (find|answer)|"
    r"have (the|our) team follow up|team will (follow up|get back)|i'?m not sure about that",
    re.IGNORECASE,
)


def is_unanswered(answer: str) -> bool:
    return bool(answer) and bool(_UNANSWERED.search(answer.replace("’", "'")))


def normalize(question: str) -> str:
    q = re.sub(r"[^\w\s]", " ", (question or "").lower())
    return " ".join(q.split())[:300]


async def record_gap(bot_id: str, question: str, channel: str, conversation_id: Optional[str] = None) -> None:
    """Count a question the assistant couldn't answer, grouped with identical wording."""
    norm = normalize(question)
    if len(norm) < 3:
        return
    async with async_session() as db:
        row = (await db.execute(select(KnowledgeGap).where(KnowledgeGap.bot_id == bot_id, KnowledgeGap.normalized == norm))).scalars().first()
        if row:
            if row.status == "dismissed":
                return
            row.count = (row.count or 0) + 1
            row.last_asked_at = datetime.utcnow()
            row.last_conversation_id = conversation_id or row.last_conversation_id
            if row.status == "answered" and row.answer:
                return await db.commit()  # answered since; the next reply will use it
        else:
            db.add(KnowledgeGap(bot_id=bot_id, question=question.strip()[:1000], normalized=norm, channel=channel,
                                last_conversation_id=conversation_id))
        try:
            await db.commit()
        except IntegrityError:
            pass  # recorded by a parallel request
    _answers_cache.pop(bot_id, None)


_answers_cache: dict[str, tuple[float, str]] = {}


async def verified_answers(bot_id: str) -> str:
    """The business's own answers, given to the assistant ahead of other knowledge. Cached briefly."""
    hit = _answers_cache.get(bot_id)
    if hit and time.monotonic() - hit[0] < 30:
        return hit[1]
    async with async_session() as db:
        rows = (await db.execute(select(KnowledgeGap.question, KnowledgeGap.answer).where(
            KnowledgeGap.bot_id == bot_id, KnowledgeGap.status == "answered", KnowledgeGap.answer.isnot(None),
        ).order_by(KnowledgeGap.last_asked_at.desc()).limit(60))).all()
    text = ""
    if rows:
        pairs = "\n".join(f"Q: {q}\nA: {a}" for q, a in rows)[:6000]
        text = f"Answers confirmed by the business (use these first):\n{pairs}\n\n"
    _answers_cache[bot_id] = (time.monotonic(), text)
    return text


def forget_answers(bot_id: str) -> None:
    _answers_cache.pop(bot_id, None)


# ─── Upset customers ──────────────────────────────────────────────
_UPSET_WORDS = [
    "worst", "useless", "pathetic", "terrible", "horrible", "disgusting", "scam", "fraud", "cheat", "cheated",
    "cheating", "furious", "ridiculous", "nonsense", "rubbish", "unacceptable", "complaint", "consumer court",
    "legal action", "refund my money", "waste of time", "waste of money", "fed up", "never again", "not happy",
    "very bad", "so bad", "angry", "irritating", "frustrated", "frustrating",
    # Hinglish / Tanglish
    "bakwas", "bekar", "ghatiya", "dhokha", "chor", "mosam", "romba mosam",
    # Native script
    "बकवास", "बेकार", "घटिया", "धोखा", "मोसम", "மோசம்", "ஏமாற்று", "கேவலம்",
]
_UPSET_RE = re.compile("|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in _UPSET_WORDS), re.IGNORECASE)


def is_upset(text: str) -> bool:
    """Clear signs of an unhappy customer: strong words, lots of !!!, or SHOUTING."""
    if not text:
        return False
    if _UPSET_RE.search(text) or text.count("!") >= 3:
        return True
    letters = [c for c in text if c.isalpha() and c.isascii()]
    return len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7


# ─── Business hours ───────────────────────────────────────────────
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_HOURS = {
    "enabled": False,
    "days": {d: {"open": d not in ("sun",), "from": "09:00", "to": "18:00"} for d in DAYS},
    "holidays": [],
    "away_message": "Our team is offline right now. Leave your question and number, and we'll get back to you {next_open}.",
}


def hours_config(settings: Optional[WorkspaceSettings]) -> dict:
    saved = (settings.business_hours if settings else None) or {}
    days = {d: {**DEFAULT_HOURS["days"][d], **(saved.get("days", {}).get(d) or {})} for d in DAYS}
    return {**DEFAULT_HOURS, **{k: v for k, v in saved.items() if k != "days"}, "days": days}


def _minutes(hhmm: str) -> int:
    h, m = (hhmm or "00:00").split(":")
    return int(h) * 60 + int(m)


def is_open(hours: dict, now: Optional[datetime] = None) -> bool:
    """Always open unless business hours are switched on. Times are India time."""
    if not hours.get("enabled"):
        return True
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    if local.strftime("%Y-%m-%d") in (hours.get("holidays") or []):
        return False
    day = hours["days"][DAYS[local.weekday()]]
    minute = local.hour * 60 + local.minute
    return bool(day.get("open")) and _minutes(day["from"]) <= minute < _minutes(day["to"])


def next_open(hours: dict, now: Optional[datetime] = None) -> str:
    """'today at 9:00 AM', 'tomorrow at 9:00 AM' or 'on Monday at 9:00 AM'."""
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    for offset in range(0, 15):
        day_dt = local + timedelta(days=offset)
        if day_dt.strftime("%Y-%m-%d") in (hours.get("holidays") or []):
            continue
        day = hours["days"][DAYS[day_dt.weekday()]]
        if not day.get("open"):
            continue
        start = _minutes(day["from"])
        if offset == 0 and local.hour * 60 + local.minute >= start:
            continue
        when = datetime(2000, 1, 1, start // 60, start % 60).strftime("%I:%M %p").lstrip("0")
        label = "today" if offset == 0 else "tomorrow" if offset == 1 else f"on {day_dt.strftime('%A')}"
        return f"{label} at {when}"
    return "soon"


async def workspace(owner_id: str) -> WorkspaceSettings:
    """The workspace's settings as they apply now: business hours only on a plan with them (Pro, plans.py); without
    it the business counts as always open, and the hours stay saved for when it has one."""
    import plans
    async with async_session() as db:
        s = (await db.execute(select(WorkspaceSettings).where(WorkspaceSettings.user_id == owner_id))).scalars().first()
        hours_on = (s is not None and (s.business_hours or {}).get("enabled")
                    and (await plans.workspace_includes(db, owner_id)).business_hours)
    s = s or WorkspaceSettings(user_id=owner_id)
    if (s.business_hours or {}).get("enabled") and not hours_on:
        s.business_hours = {**s.business_hours, "enabled": False}  # this copy only: the session is closed, nothing saved
    return s


async def away_reply(owner_id: str) -> Optional[str]:
    """The message for "talk to a person" when the team is offline; None while open."""
    hours = hours_config(await workspace(owner_id))
    if is_open(hours):
        return None
    return (hours.get("away_message") or DEFAULT_HOURS["away_message"]).replace("{next_open}", next_open(hours))


async def should_escalate(owner_id: str, text: str) -> bool:
    settings = await workspace(owner_id)
    return settings.escalate_upset is not False and is_upset(text)


# ─── Lead score ───────────────────────────────────────────────────
def lead_score(captured: Optional[dict], *, successful: Optional[bool] = None, sentiment: Optional[str] = None,
               outcome: Optional[str] = None, asked_for_person: bool = False) -> dict:
    """0-100 from how reachable and how interested someone is. Returns {score, label, reasons}."""
    from phone import extract_contact
    data = captured or {}
    contact = extract_contact(data)
    score, reasons = 0, []

    def add(points: int, why: str):
        nonlocal score
        score += points
        reasons.append(why)

    if contact.get("phone"):
        add(25, "Phone number")
    if contact.get("email"):
        add(15, "Email")
    if contact.get("name"):
        add(5, "Name")
    extra = len([k for k in data if k.lower() not in ("name", "phone", "email", "channel")])
    if extra:
        add(min(15, extra * 5), f"{extra} more detail{'s' if extra > 1 else ''}")
    if successful:
        add(25, "Goal met")
    if outcome == "transferred" or asked_for_person:
        add(10, "Wanted to talk to a person")
    if sentiment == "positive":
        add(10, "Positive mood")
    elif sentiment == "negative":
        add(-15, "Unhappy")
    score = max(0, min(100, score))
    label = "hot" if score >= 60 else "warm" if score >= 30 else "cold"
    return {"score": score, "label": label, "reasons": reasons}
