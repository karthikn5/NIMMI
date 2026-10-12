"""The live call engine, with fake speech, AI and audio so it runs offline."""
import asyncio

from sqlalchemy.future import select

from database import async_session
from backend.models import Bot, CallLog, DncEntry, VoiceAgent
from voice import llm
from voice.pipeline import CallSession, CallSetup

RATE = 16000


class FakeTransport:
    sample_rate = RATE

    def __init__(self):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.played: list[bytes] = []
        self.events: list[dict] = []
        self.cleared = 0
        self.hung_up = None

    async def receive(self):
        return await self.inbox.get()

    async def play(self, pcm):
        self.played.append(pcm)

    async def clear(self):
        self.cleared += 1

    async def event(self, data):
        self.events.append(data)

    async def hangup(self, reason):
        self.hung_up = reason
        await self.inbox.put(None)

    def said(self):
        return [e["text"] for e in self.events if e.get("type") == "agent"]


class FakeStt:
    """Scripted recognizer: each script item is an event emitted when audio arrives."""

    def __init__(self, script):
        self.script = list(script)
        self.queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.queue.put(None)

    async def send(self, pcm):
        if self.script:
            await self.queue.put(self.script.pop(0))

    async def events(self):
        while (ev := await self.queue.get()) is not None:
            yield ev


class Ev:
    def __init__(self, kind, text=""):
        self.kind, self.text = kind, text


async def fake_tts(text, language, speaker, pace, rate):
    return b"\x01\x00" * int(rate * 0.05)  # 50 ms per sentence


async def fake_summary(bot, transcript, agent=None):
    return {"summary": "Asked about fees.", "fields": {"Name": "Priya", "Phone": "+919876543210"}, "wants_callback": False}


def replier_saying(*sentences, control=None):
    async def gen(bot, agent, history, text, direction, consent, **_):
        for i, s in enumerate(sentences):
            yield s, (control if i == len(sentences) - 1 else None)
    return gen


async def _setup(owner_id, bot_id, **agent_overrides) -> CallSetup:
    async with async_session() as db:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        agent = VoiceAgent(bot_id=bot_id, user_id=owner_id, enabled=True, language="en-IN", voice_id="priya",
                           speaking_rate=1.0, assistant_name="Nimmi", company_name="Sri Ramana College",
                           greeting="How can I help?", allow_interruptions=True, silence_timeout_sec=30,
                           max_call_minutes=5, transfer_enabled=True, transfer_number="+919840012345",
                           transfer_when="they ask for a person", end_call_phrases=["bye"])
        for k, v in agent_overrides.items():
            setattr(agent, k, v)
    return CallSetup(owner_id=owner_id, bot=bot, agent=agent, channel="phone", caller_e164="+919876543210",
                     opt_out_phrases=["don't call me", "stop calling"])


async def _call(setup, transport, script, replier):
    session = CallSession(setup, transport, stt_factory=lambda *a: FakeStt(script), tts=fake_tts,
                          replier=replier, summarizer=fake_summary)

    async def feed():
        await asyncio.sleep(0.05)
        for _ in range(len(script) + 2):
            await transport.inbox.put(b"\x00\x00" * 160)
            await asyncio.sleep(0.05)

    feeder = asyncio.create_task(feed())
    call_id = await asyncio.wait_for(session.run(), timeout=10)
    feeder.cancel()
    async with async_session() as db:
        log = (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()
    return session, log


def test_greets_listens_replies_and_logs(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        script = [Ev("speech_start"), Ev("transcript", "What are the fees?"), Ev("transcript", "ok bye")]
        session, log = await _call(setup, t, script, replier_saying("Tuition is one lakh a year.", "Anything else?"))
        return t, log

    t, log = run(scenario)
    said = t.said()
    assert said[0].startswith("Hi, I'm Nimmi, an automated assistant for Sri Ramana College.")
    assert "This call may be recorded" in said[0]
    assert "Tuition is one lakh a year." in said
    assert said[-1] == __import__("voice.pipeline", fromlist=["GOODBYES"]).GOODBYES["en-IN"]
    assert log.outcome == "lead_captured" and log.billed_minutes == 1
    assert [x["speaker"] for x in log.transcript][:2] == ["agent", "caller"]
    assert log.captured["Name"] == "Priya"


def test_opt_out_adds_to_dnc_and_ends(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        session, log = await _call(await _setup(u.id, bot), t, [Ev("transcript", "Please don't call me again")],
                                   replier_saying("unused"))
        async with async_session() as db:
            dnc = (await db.execute(select(DncEntry).where(DncEntry.user_id == u.id))).scalars().all()
        return t, log, dnc

    t, log, dnc = run(scenario)
    assert log.outcome == "opted_out"
    assert [d.e164 for d in dnc] == ["+919876543210"]
    assert t.said()[-1].startswith("Understood. We won't contact you again.")


def test_transfer_on_a_browser_test_call_explains_instead(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        setup.channel = "browser"
        session, log = await _call(setup, t, [Ev("transcript", "Can I talk to someone?")],
                                   replier_saying("Let me connect you.", control=llm.TRANSFER))
        return t, log

    t, log = run(scenario)
    assert any("This is a test call, so I won't transfer you" in s for s in t.said())
    assert log.channel == "browser"


def test_barge_in_clears_queued_audio(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]), tts=fake_tts,
                              replier=replier_saying("x"), summarizer=fake_summary)
        await session._open_log()
        await session.speak("A long answer that the caller interrupts.")
        await session.on_speech_start()
        cleared = t.cleared
        session.ended.set()
        await session._finish()
        return cleared

    assert run(scenario) == 1


def test_no_minutes_refuses_politely(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        async with async_session() as db:
            from voice.metering import get_wallet
            wallet = await get_wallet(db, u.id)
            wallet.topup_minutes = 0
            await db.commit()
        t = FakeTransport()
        session, log = await _call(await _setup(u.id, bot), t, [], replier_saying("unused"))
        return t, log

    t, log = run(scenario)
    assert log.outcome == "failed" and log.billed_minutes == 0
    assert any(e.get("code") == "no_minutes" for e in t.events)


def test_split_sentence_is_answered_as_one(run, make_user):
    """If the recognizer splits a sentence, the assistant answers the whole thing once."""
    u = make_user()
    bot = u.bot()
    heard: list[str] = []

    async def slow_replier(bot, agent, history, text, direction, consent, **_):
        heard.append(text)
        await asyncio.sleep(0.3)  # still thinking when the next fragment arrives
        yield "Sure.", None

    async def scenario():
        t = FakeTransport()
        script = [Ev("transcript", "Hello, I want to know"), Ev("transcript", "the hostel fees"), Ev("transcript", "bye")]
        session, log = await _call(await _setup(u.id, bot), t, script, slow_replier)
        return t

    t = run(scenario)
    assert heard[-1] == "Hello, I want to know the hostel fees"
    assert t.said().count("Sure.") <= 1


def test_phrase_matching_ignores_punctuation_and_case():
    from voice.pipeline import _matches
    assert _matches("Okay, thank you. Bye.", ["bye"])
    assert _matches("Please DON’T call me again!", ["don't call me"])
    assert _matches("Call panna vendam", ["call panna vendam"])
    assert not _matches("goodbye to that idea", ["bye"])
