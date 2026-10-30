"""
A caller who needs a person, and the team member who picks up (LIVE_CALLS_PLAN.md).

During a call the AI has one tool for it, ask_for_person. It decides from the conversation (the caller asks for a
person, or needs what only a person can do), never from a list of words. Then (voice/pipeline.py):
  - someone from the team is available (their dashboard is open and "Available for calls" is on): a CallHandoff starts
    ringing, every available team member's dashboard shows it (voice/live_api.py), and the AI tells the caller it's
    getting someone and keeps helping meanwhile;
  - one of them accepts, in their browser or on their phone: the call notices within a second, says it's connecting
    them, and closes the AI's audio stream. The provider then asks us what next, and the row here (in the database,
    so whichever server process gets that request can answer) says where;
  - nobody in time, or nobody available: the agent's transfer number if it has one; else the AI says the team is busy,
    a to-do to call them back lands in Schedule, and the call goes on with the AI.
The agent's transfer number goes through the same rows (via "transfer"), which also fixes transfers being lost when
the provider's next request reached another server process than the call.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CallbackJob, CallHandoff, CallLog, TeamMember, TeamPresence, User
from database import async_session

logger = logging.getLogger(__name__)

DEFAULT_WAIT_SEC = 45     # how long the team is rung before the fallback (the agent's own setting overrides it)
PRESENCE_SEC = 45         # a dashboard checks in every few seconds; quiet this long, its person isn't available
WATCH_SEC = 1.0           # how often a ringing call looks for an answer
LIVE_SEC = 3.0            # how often a call writes that it's alive, and its transcript so far
DEAD_SEC = 90             # a call silent this long died with its server process
OPEN = ("ringing", "accepted", "connecting")
TOOL = "ask_for_person"

CONNECTING = {
    "en-IN": "Connecting you to our team now. Please stay on the line.",
    "ta-IN": "இப்போ எங்க டீம்ல ஒருத்தர்கிட்ட இணைக்கிறேன். லைன்லயே இருங்க.",
    "hi-IN": "अभी आपको हमारी टीम से जोड़ा जा रहा है। कृपया लाइन पर बने रहिए।",
    "te-IN": "ఇప్పుడు మా టీమ్‌లో ఒకరితో కలుపుతున్నాను. దయచేసి లైన్‌లోనే ఉండండి.",
    "kn-IN": "ಈಗ ನಮ್ಮ ತಂಡದವರಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಲೈನ್‌ನಲ್ಲೇ ಇರಿ.",
    "ml-IN": "ഇപ്പോൾ ഞങ്ങളുടെ ടീമിലെ ഒരാളുമായി ബന്ധിപ്പിക്കുന്നു. ദയവായി ലൈനിൽ തുടരൂ.",
    "mr-IN": "आता तुम्हाला आमच्या टीमशी जोडत आहोत. कृपया लाईनवर राहा.",
    "bn-IN": "এখন আপনাকে আমাদের টিমের সঙ্গে যুক্ত করছি। দয়া করে লাইনে থাকুন।",
    "gu-IN": "હવે તમને અમારી ટીમ સાથે જોડી રહ્યા છીએ. કૃપા કરીને લાઇન પર રહો.",
    "pa-IN": "ਹੁਣ ਤੁਹਾਨੂੰ ਸਾਡੀ ਟੀਮ ਨਾਲ ਜੋੜ ਰਹੇ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਲਾਈਨ ਤੇ ਰਹੋ।",
    "od-IN": "ବର୍ତ୍ତମାନ ଆପଣଙ୍କୁ ଆମ ଟିମ୍ ସହ ଯୋଡୁଛି। ଦୟାକରି ଲାଇନରେ ରୁହନ୍ତୁ।",
}
BUSY = {
    "en-IN": "Sorry, no one from our team can join right now. I've asked them to call you back as soon as they can.",
    "ta-IN": "மன்னிக்கணும், இப்போ எங்க டீம்ல யாரும் வர முடியல. சீக்கிரமே உங்களைத் திரும்ப அழைக்கச் சொல்லியிருக்கேன்.",
    "hi-IN": "माफ़ कीजिए, अभी हमारी टीम से कोई जुड़ नहीं पा रहा है। हमने उनसे कहा है कि वे जल्द ही आपको वापस कॉल करें।",
    "te-IN": "క్షమించండి, ఇప్పుడు మా టీమ్ నుండి ఎవరూ రాలేకపోతున్నారు. వీలైనంత త్వరగా మీకు తిరిగి కాల్ చేయమని చెప్పాను.",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ಈಗ ನಮ್ಮ ತಂಡದಿಂದ ಯಾರೂ ಬರಲಾಗುತ್ತಿಲ್ಲ. ಆದಷ್ಟು ಬೇಗ ನಿಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡಲು ಹೇಳಿದ್ದೇನೆ.",
    "ml-IN": "ക്ഷമിക്കണം, ഇപ്പോൾ ഞങ്ങളുടെ ടീമിൽ നിന്ന് ആർക്കും ചേരാൻ കഴിയുന്നില്ല. എത്രയും വേഗം നിങ്ങളെ തിരികെ വിളിക്കാൻ പറഞ്ഞിട്ടുണ്ട്.",
    "mr-IN": "माफ करा, आत्ता आमच्या टीममधून कोणी जोडू शकत नाही. त्यांना लवकरात लवकर तुम्हाला परत कॉल करायला सांगितले आहे.",
    "bn-IN": "দুঃখিত, এই মুহূর্তে আমাদের টিম থেকে কেউ যোগ দিতে পারছেন না। ওঁদের যত তাড়াতাড়ি সম্ভব আপনাকে ফোন করতে বলেছি।",
    "gu-IN": "માફ કરશો, અત્યારે અમારી ટીમમાંથી કોઈ જોડાઈ શકતું નથી. તેમને જલ્દી તમને પાછો કૉલ કરવા કહ્યું છે.",
    "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਇਸ ਵੇਲੇ ਸਾਡੀ ਟੀਮ ਵਿੱਚੋਂ ਕੋਈ ਨਹੀਂ ਜੁੜ ਸਕਦਾ। ਉਹਨਾਂ ਨੂੰ ਜਲਦੀ ਤੁਹਾਨੂੰ ਵਾਪਸ ਕਾਲ ਕਰਨ ਲਈ ਕਿਹਾ ਹੈ।",
    "od-IN": "କ୍ଷମା କରିବେ, ଏବେ ଆମ ଟିମରୁ କେହି ଯୋଗ ଦେଇ ପାରୁନାହାନ୍ତି। ଯେତେ ଶୀଘ୍ର ସମ୍ଭବ ଆପଣଙ୍କୁ ଫୋନ୍ କରିବାକୁ କହିଛି।",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite gives times back without their zone; they're all UTC."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def identity(user_id: str) -> str:
    """A team member's browser, as Twilio knows it (letters, digits and _ only)."""
    return "u_" + "".join(ch for ch in user_id if ch.isalnum())


def wait_of(agent) -> int:
    return max(15, min(int(getattr(agent, "team_handoff_wait", None) or DEFAULT_WAIT_SEC), 120))


def team_on(agent) -> bool:
    return getattr(agent, "team_handoff", None) is not False


# ─── Who can take a call ────────────────────────────────────────────

async def members(db: AsyncSession, owner_id: str) -> set[str]:
    """Everyone who may pick up the workspace's calls: the owner and its active team (any role)."""
    rows = (await db.execute(select(TeamMember.member_id).where(
        TeamMember.owner_id == owner_id, TeamMember.status == "active", TeamMember.member_id.isnot(None)))).scalars().all()
    return {owner_id, *rows}


async def available(db: AsyncSession, owner_id: str) -> list[TeamPresence]:
    """Team members whose dashboard checked in lately with "Available for calls" on."""
    since = now() - timedelta(seconds=PRESENCE_SEC)
    rows = (await db.execute(select(TeamPresence).where(
        TeamPresence.owner_id == owner_id, TeamPresence.available.is_(True), TeamPresence.seen_at >= since))).scalars().all()
    allowed = await members(db, owner_id)
    return [p for p in rows if p.user_id in allowed]


async def check_in(db: AsyncSession, owner_id: str, user_id: str, *, available_now: Optional[bool] = None,
                   phone: Optional[str] = None) -> TeamPresence:
    """A team member's dashboard is open (and optionally: they changed their availability or phone)."""
    row = await db.get(TeamPresence, (owner_id, user_id))
    if row is None:
        row = TeamPresence(owner_id=owner_id, user_id=user_id, available=True)
        db.add(row)
    row.seen_at = now()
    if available_now is not None:
        row.available = available_now
    if phone is not None:
        row.phone = phone or None
    await db.commit()
    return row


async def name_of(db: AsyncSession, user_id: Optional[str]) -> str:
    if not user_id:
        return "Someone from the team"
    user = await db.get(User, user_id)
    return ((user.name or "").strip() or (user.email or "").split("@")[0]) if user else "Someone from the team"


# ─── The hand-off rows ─────────────────────────────────────────────

async def latest_open(db: AsyncSession, provider_call_id: Optional[str]) -> Optional[CallHandoff]:
    """The hand-off the provider's "what next" request is about: accepted, or being connected."""
    if not provider_call_id:
        return None
    return (await db.execute(select(CallHandoff).where(
        CallHandoff.provider_call_id == provider_call_id, CallHandoff.status.in_(("accepted", "connecting", "connected")))
        .order_by(CallHandoff.created_at.desc()))).scalars().first()


async def accept(db: AsyncSession, handoff_id: str, user_id: str, via: str, target: str) -> bool:
    """The first team member to accept gets the call (an atomic update: a second click finds it taken)."""
    result = await db.execute(update(CallHandoff).where(
        CallHandoff.id == handoff_id, CallHandoff.status == "ringing", CallHandoff.expires_at > now())
        .values(status="accepted", accepted_by=user_id, via=via, target=target, accepted_at=now())
        .execution_options(synchronize_session=False))
    await db.commit()
    return result.rowcount == 1


async def settle(handoff_id: str, status: str, *, only_if: tuple = OPEN, **values) -> bool:
    """Move a hand-off on (missed, cancelled, connected, ended, failed), unless it already moved past `only_if`."""
    async with async_session() as db:
        result = await db.execute(update(CallHandoff).where(
            CallHandoff.id == handoff_id, CallHandoff.status.in_(only_if)).values(status=status, **values)
            .execution_options(synchronize_session=False))
        await db.commit()
        return result.rowcount == 1


async def announce(owner_id: str, handoff_id: str, status: str) -> None:
    """Tell the workspace's open dashboards at once (those on another server process see it on their next check)."""
    from realtime import notify_owner
    await notify_owner(owner_id, "call_handoff", {"id": handoff_id, "status": status})


async def todo_for(owner_id: str, bot_id: Optional[str], e164: Optional[str], call_id: Optional[str], reason: str,
                   name: Optional[str] = None) -> None:
    """Nobody could take the call: one open to-do in Schedule for a person to call them back."""
    if not e164 or not bot_id:
        return
    from voice import schedule
    async with async_session() as db:
        todo = await schedule.waiting_job(db, bot_id, e164, "person")
        if todo is None:
            todo = CallbackJob(user_id=owner_id, bot_id=bot_id, e164=e164, kind="person", status="todo",
                               consent_source="Asked for a person during a call")
            db.add(todo)
        todo.next_attempt_at, todo.source_call_id = datetime.utcnow(), call_id
        todo.purpose = f"They asked for a person during a call: {reason}"[:600]
        todo.name = name or todo.name
        await db.commit()


async def sweep() -> None:
    """Close what died with a server process: calls no longer alive, hand-offs nobody is watching."""
    cutoff = now() - timedelta(seconds=DEAD_SEC)
    async with async_session() as db:
        dead = (await db.execute(select(CallLog).where(CallLog.outcome == "in_progress", or_(
            CallLog.live_at < cutoff,
            and_(CallLog.live_at.is_(None), CallLog.started_at < now() - timedelta(hours=3)))))).scalars().all()
        for call in dead:
            call.outcome = "failed"
            call.ended_at = call.live_at or call.started_at
            call.summary = call.summary or "The call was cut off: the server running it restarted."
        stuck = await db.execute(update(CallHandoff).where(
            CallHandoff.status == "ringing", CallHandoff.expires_at < now() - timedelta(seconds=60))
            .values(status="missed", ended_at=now()).execution_options(synchronize_session=False))
        gone = await db.execute(update(CallHandoff).where(
            CallHandoff.status.in_(("accepted", "connecting", "connected")),
            CallHandoff.created_at < now() - timedelta(hours=4)).values(status="ended", ended_at=now())
            .execution_options(synchronize_session=False))
        if dead or stuck.rowcount or gone.rowcount:
            await db.commit()
            logger.info(f"Closed {len(dead)} calls that died with their server, {stuck.rowcount} unanswered hand-offs, "
                        f"{gone.rowcount} old ones")


# ─── The AI's tool ─────────────────────────────────────────────────

class HandoffTools:
    """The call's tool for getting a person (the same shape as voice/schedule.CallTools)."""

    def __init__(self, session):
        self.session = session

    def specs(self) -> list[dict]:
        agent = self.session.s.agent
        if not (team_on(agent) or (agent.transfer_enabled and agent.transfer_number)):
            return []
        return [{"name": TOOL, "description": (
            "Get someone from the team onto this call: when the caller asks to talk to a person, or needs something only "
            "a person can do (a decision, a complaint, an exception, anything you can't do with your knowledge and "
            "tools). It tells you whether someone is coming; say what it tells you to. Never just promise that someone "
            "will call: use this."),
            "parameters": {"type": "object", "properties": {
                "reason": {"type": "string", "description": "Why they need a person, in a few words; the team sees it."}},
                "required": ["reason"]}}]

    def rules(self) -> str:
        return ("\n- After ask_for_person, keep helping the caller while they wait, and never say they're connected "
                "until you're told." if self.specs() else "")

    def has(self, name: str) -> bool:
        return name == TOOL and bool(self.specs())

    async def run(self, name: str, args: dict) -> str:
        if name != TOOL:
            return f"There's no function called {name}. Answer without it."
        return await self.session.ask_for_person(" ".join(str((args or {}).get("reason") or "").split())[:300]
                                                 or "They asked to talk to a person.")


class Toolbox:
    """Several groups of call tools as one (the Schedule's and the hand-off's)."""

    def __init__(self, *parts):
        self.parts = [p for p in parts if p is not None]

    def specs(self) -> list[dict]:
        return [spec for part in self.parts for spec in part.specs()]

    def rules(self) -> str:
        return "".join(part.rules() for part in self.parts)

    def has(self, name: str) -> bool:
        return any(part.has(name) for part in self.parts)

    async def run(self, name: str, args: dict) -> str:
        for part in self.parts:
            if part.has(name):
                return await part.run(name, args)
        return f"There's no function called {name}. Answer without it."
