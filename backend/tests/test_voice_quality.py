"""Call quality: a short protected opening, hellos, long speech, misheard numbers, and AI fallbacks."""
import asyncio
import os
import time
from collections import OrderedDict

import pytest

from voice import llm, pipeline
from voice.pipeline import CallSession, number_check
from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, fake_tts, replier_saying


@pytest.fixture(autouse=True)
def _fresh_openings(monkeypatch, tmp_path):
    """Openings are kept across calls (in memory and in files): every test starts without any."""
    monkeypatch.setattr(pipeline, "_OPENINGS", OrderedDict())
    monkeypatch.setattr(pipeline, "OPENINGS_DIR", str(tmp_path / "openings"))


def test_opening_is_short_and_mentions_recording_only_when_recorded():
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="How can I help?")
    assert llm.disclosure(agent) == "Hi, Nimmi here, Kdbot's AI assistant. This call is recorded. How can I help?"
    assert llm.disclosure(agent, recorded=False) == "Hi, Nimmi here, Kdbot's AI assistant. How can I help?"
    tamil = llm.VoiceAgent(language="ta-IN", assistant_name="நிம்மி", company_name="Kdbot", greeting="")
    assert "பதிவு" in llm.disclosure(tamil) and "பதிவு" not in llm.disclosure(tamil, recorded=False)


def test_a_number_with_a_missing_digit_is_flagged_for_the_assistant():
    assert "has 9 digits" in number_check("my number is 98765 4320")
    assert number_check("my number is 98765 43210") == ""
    assert number_check("call me on +91 98765 43210") == ""
    assert number_check("the 2BHK is 58 lakhs") == ""


def _session(setup, t, script, replier):
    return CallSession(setup, t, stt_factory=lambda *a: FakeStt(script), tts=fake_tts, replier=replier, summarizer=fake_summary)


def test_hello_over_the_opening_gets_no_extra_reply_and_cannot_cut_it_off(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []

    def replier(*sentences):
        async def gen(bot, agent, history, text, direction, consent, **_):
            asked.append(text)
            for s in sentences:
                yield s, None
        return gen

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        session = _session(setup, t, [], replier("Fees are one lakh."))
        await session._open_log()
        greeting = asyncio.create_task(session._greet())
        await asyncio.sleep(0)  # the opening has started
        await session.on_speech_start()  # "Hello?" over it
        await session.on_caller_text("Hello?")
        await greeting
        await session.on_caller_text("What are the fees?")
        await session.reply_task
        session.ended.set()
        await session._finish()
        return t

    t = run(scenario)
    assert t.cleared == 0  # the opening wasn't cut off
    assert asked == ["What are the fees?"]  # the hello didn't get its own answer
    assert t.said() == [t.said()[0], "Fees are one lakh."] and t.said()[0].startswith("Hi, Nimmi here")


def test_an_outbound_call_greets_at_once_and_a_hello_over_it_gets_no_answer(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        setup.direction = "outbound"
        session = _session(setup, t, [Ev("speech_start"), Ev("transcript", "Hello?"), Ev("transcript", "ok bye")],
                           replier_saying("unused"))

        async def feed():
            for _ in range(6):
                await t.inbox.put(b"\x00\x00" * 160)
                await asyncio.sleep(0.05)
        feeder = asyncio.create_task(feed())
        started = time.monotonic()
        await asyncio.wait_for(session.run(), timeout=10)
        feeder.cancel()
        return t, time.monotonic() - started

    t, took = run(scenario)
    said = t.said()
    assert len(said) == 2 and said[0].startswith("Hi, Nimmi here") and said[1].startswith("Thanks for calling")
    assert took < 1.5


def test_a_long_answer_from_the_caller_is_not_silence(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, silence_timeout_sec=3)
        session = _session(setup, t, [], replier_saying("x"))
        await session._open_log()
        session.greeted.set()
        await session.on_speech_start()  # starts describing a problem...
        session.last_heard = time.monotonic() - 10  # ...and has been talking for 10 s
        watchdog = asyncio.create_task(session._watchdog())
        await asyncio.sleep(1.2)
        talking_prompts = len(t.said())
        session.caller_talking_since = None  # they stopped, and stay quiet
        session.last_heard = time.monotonic() - 10
        await asyncio.sleep(1.2)
        watchdog.cancel()
        session.ended.set()
        await session._finish()
        return talking_prompts, t.said()

    talking_prompts, said = run(scenario)
    assert talking_prompts == 0
    assert said and said[0] in ("Are you still there?", "Hello, can you hear me?")


def test_a_rate_limited_groq_model_hands_over_to_the_next_then_gemini(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    monkeypatch.setattr(llm, "VOICE_GROQ_MODELS", ["model-a", "model-b"])
    tried = []

    class RateLimited(Exception):
        status_code = 429

    def fake_groq(model, prompt, history, text):
        tried.append(model)
        if model == "model-a":
            raise RateLimited("rate_limit_exceeded")
        yield "From B."
    monkeypatch.setattr(llm, "_stream_groq", fake_groq)
    monkeypatch.setattr(llm, "_stream_gemini", lambda *a: iter(["From Gemini."]))
    bot = llm.Bot(bot_name="Desk")
    assert "".join(llm.stream_reply(bot, "p", [], "hi")) == "From B."
    assert "model-a" in llm._rate_limited
    # The limited model is skipped while it refills.
    tried.clear()
    assert "".join(llm.stream_reply(bot, "p", [], "hi")) == "From B." and tried == ["model-b"]

    def all_fail(model, prompt, history, text):
        raise RateLimited("rate_limit_exceeded")
        yield  # pragma: no cover
    monkeypatch.setattr(llm, "_stream_groq", all_fail)
    assert "".join(llm.stream_reply(bot, "p", [], "hi")) == "From Gemini."


def test_groq_doesnt_wait_out_a_rate_limit_by_itself(monkeypatch):
    """The SDK's own retry sleeps for Groq's retry-after (10-20 s of silence on a call); the next model
    should answer instead."""
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_groq_client", None)
    assert llm._groq().max_retries == 0


# ─── following the caller's language ──────────────────────────────
from voice import sarvam  # noqa: E402
from voice.pipeline import GOODBYES, spoken_language, written_language  # noqa: E402


class LangEv:
    def __init__(self, kind, text="", language=None):
        self.kind, self.text, self.language = kind, text, language


def test_language_switches_only_on_clear_speech():
    assert spoken_language("எனக்கு data science course பத்தி தெரிஞ்சுக்கணும்", "ta-IN") == "ta-IN"  # Tanglish
    assert spoken_language("मुझे फीस जाननी है", "hi-IN") == "hi-IN"
    assert spoken_language("I want to know the fees please", "en-IN") == "en-IN"
    assert spoken_language("Okay", "en-IN") is None  # too short to change language over
    assert spoken_language("ok ok", "en-IN") is None
    assert spoken_language("hello there", "ta-IN") is None  # the script doesn't match what was reported
    assert spoken_language("சரி சரி", "ta-IN") == "ta-IN"
    # The script decides even when the reported language is off (a recognizer set to English still
    # writes Tamil in Tamil letters, but reports en-IN), and Devanagari is Hindi unless it says Marathi.
    assert spoken_language("எனக்கு fees எவ்வளவு சொல்லுங்க", "en-IN") == "ta-IN"
    assert spoken_language("मुझे फीस बताइए", None) == "hi-IN"
    assert spoken_language("मला फी किती आहे सांगा", "mr-IN") == "mr-IN"


def test_the_voice_follows_the_script_it_reads():
    assert written_language("சரிங்க, fees ஒரு லட்சம்.") == "ta-IN"
    assert written_language("Sure, the fees are one lakh.") is None
    assert written_language("फीस एक लाख है।", "mr-IN") == "mr-IN" and written_language("फीस एक लाख है।", "en-IN") == "hi-IN"


def test_the_prompt_says_the_caller_switched_and_asks_for_their_script():
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")
    bot = llm.Bot(bot_name="Desk")
    switched = llm.system_prompt(agent, bot, "", "outbound", None, reply_language="ta-IN")
    assert "Reply in Tamil." in switched and "answer in Tamil from now on" in switched
    assert "Write Tamil words in Tamil script" in switched
    same = llm.system_prompt(agent, bot, "", "outbound", None)
    assert "Reply in Indian English." in same and "from now on" not in same and "English letters" not in same


def _language_call(run, u, bot, follow, script):
    seen = {"stt": None, "replies": [], "tts": []}

    def replier(bot_, agent, history, text, direction, consent, reply_language=None, **_):
        async def gen():
            seen["replies"].append(reply_language)
            yield "Reply.", None
        return gen()

    async def tts(text, language, speaker, pace, rate):
        seen["tts"].append(language)
        return b"\x01\x00" * 160

    def stt_factory(language, rate, mixed):
        seen["stt"] = language
        return FakeStt(script)

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, follow_caller_language=follow)
        session = CallSession(setup, t, stt_factory=stt_factory, tts=tts, replier=replier, summarizer=fake_summary)

        async def feed():
            for _ in range(len(script) + 3):
                await t.inbox.put(b"\x00\x00" * 160)
                await asyncio.sleep(0.05)
        feeder = asyncio.create_task(feed())
        await asyncio.wait_for(session.run(), timeout=10)
        feeder.cancel()
        return t, session
    t, session = run(scenario)
    return seen, t, session


def test_an_english_agent_answers_a_tamil_caller_in_tamil(run, make_user):
    u = make_user()
    bot = u.bot()
    script = [LangEv("speech_start"), LangEv("transcript", "எனக்கு data science course பத்தி தெரிஞ்சுக்கணும்", "ta-IN"),
              LangEv("transcript", "ok bye", "en-IN")]
    seen, t, session = _language_call(run, u, bot, True, script)
    assert seen["stt"] == "unknown"  # the recognizer detects the language instead of assuming English
    assert seen["replies"] == ["ta-IN"]  # the answer is written in Tamil...
    assert seen["tts"][0] == "en-IN" and "ta-IN" in seen["tts"][1:]  # ...and spoken in Tamil after the English greeting
    assert t.said()[-1] == GOODBYES["ta-IN"] and session.lang == "ta-IN"  # "ok bye" alone doesn't switch back


def test_the_agent_keeps_its_language_when_following_is_off(run, make_user):
    u = make_user()
    bot = u.bot()
    script = [LangEv("transcript", "எனக்கு data science course பத்தி தெரிஞ்சுக்கணும்", "ta-IN"),
              LangEv("pause"), LangEv("pause"), LangEv("transcript", "ok bye")]  # time for the answer before "bye"
    seen, t, session = _language_call(run, u, bot, False, script)
    assert seen["stt"] == "en-IN" and seen["replies"] == ["en-IN"] and t.said()[-1] == GOODBYES["en-IN"]


class TimedLine(FakeTransport):
    """Notes when the first audio went down the line."""

    def __init__(self):
        super().__init__()
        self.first_audio_at = None

    async def play(self, pcm):
        self.first_audio_at = self.first_audio_at or time.monotonic()
        await super().play(pcm)


def test_the_opening_plays_the_moment_the_call_connects(run, make_user):
    """Inbound or outbound, the agent speaks first: no waiting for a hello, the call log or the recognizer."""
    u = make_user()
    bot = u.bot()

    async def scenario(direction):
        t = TimedLine()
        setup = await _setup(u.id, bot)
        setup.direction = direction
        session = _session(setup, t, [], replier_saying("x"))  # and they say nothing
        feeder = asyncio.create_task(_feed(t, 4))
        started = time.monotonic()
        runner = asyncio.create_task(session.run())
        await asyncio.wait_for(session.greeted.wait(), 5)
        session.ended.set()
        await t.inbox.put(None)
        await asyncio.wait_for(runner, 5)
        feeder.cancel()
        return t.first_audio_at - started

    assert run(scenario, "outbound") < 0.3
    assert run(scenario, "inbound") < 0.3


def test_the_opening_is_kept_and_plays_at_once_on_the_next_call(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    stream, log = _fake_streams(0.01)
    monkeypatch.setattr(sarvam, "TtsStream", stream)
    monkeypatch.setattr(sarvam, "synthesize", _no_rest)

    async def greet_once():
        t = FakeTransport()
        session = CallSession(await _setup(u.id, bot), t, stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("x"), summarizer=fake_summary)
        session._prepare_opening()
        await session._greet()
        return b"".join(t.played)

    assert run(greet_once) == run(greet_once) == b"\x01\x00" * 80 * 6  # the same opening, in full, both times
    assert len([e for e in log if e[0] == "chunk"]) == 6  # generated once; the second call reused it


def test_an_opening_cut_short_is_not_kept(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()

    class Dropping:
        def __init__(self, language, *a):
            self.language = language

        async def close(self):
            pass

        async def speak(self, text, **_):
            yield b"\x01\x00" * 80
            yield b"\x01\x00" * 80
            raise ConnectionError("connection dropped")
    monkeypatch.setattr(sarvam, "TtsStream", Dropping)
    monkeypatch.setattr(sarvam, "synthesize", _no_rest)

    async def greet_once():
        t = FakeTransport()
        session = CallSession(await _setup(u.id, bot), t, stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("x"), summarizer=fake_summary)
        session._prepare_opening()
        await session._greet()
        return len(t.played)

    assert run(greet_once) == 2 and not pipeline._OPENINGS  # what played isn't kept for the next call
    assert not os.path.isdir(pipeline.OPENINGS_DIR) or not os.listdir(pipeline.OPENINGS_DIR)


class PhoneLine(FakeTransport):
    sample_rate = 8000


def test_an_opening_made_while_the_phone_rings_is_ready_in_any_server_process(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    made = []

    async def synthesize(text, language, speaker, pace, rate):
        made.append((text, rate))
        return b"\x02\x00" * 4000  # half a second at 8 kHz
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    monkeypatch.setattr(sarvam, "synthesize", synthesize)
    monkeypatch.setattr(sarvam, "TtsStream", None)  # the call mustn't generate it again

    async def scenario():
        setup = await _setup(u.id, bot)
        pipeline.prepare_opening(setup.agent, setup.variables, setup.record)  # as the call is placed
        await asyncio.sleep(0.05)  # ...while the phone rings
        pipeline._OPENINGS.clear()  # the call reaches another server process: only the shared file is there
        t = PhoneLine()
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("x"), summarizer=fake_summary)
        session._prepare_opening()
        await session._greet()
        return session, t

    session, t = run(scenario)
    assert session.opening_kept and b"".join(t.played) == b"\x02\x00" * 4000 and len(t.played) == 2  # 0.25 s pieces
    assert len(made) == 1 and made[0][0] == session.opening_text and made[0][1] == 8000


def test_a_question_ends_the_answer_and_stops_the_model(monkeypatch):
    """The model asked for the number, then answered for the caller ("…என்ன?ஹ்ம்ம், 91 99949 20257, சரியா?ஆம்…"),
    without spaces: only the question is said, and the rest of the answer isn't read."""
    pieces = ["உங்கள் மொபைல் ", "எண் என்ன?", "ஹ்ம்ம், 91 99949 20257, சரியா?", "ஆம், சரி. "] + ["மேலும் "] * 20
    read = []

    def fake_stream(bot, prompt, history, text):
        for piece in pieces:
            read.append(piece)
            yield piece
            time.sleep(0.02)
    monkeypatch.setattr(llm, "stream_reply", fake_stream)
    agent = llm.VoiceAgent(language="ta-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")

    async def collect():
        return [s async for s in llm.reply_sentences(llm.Bot(bot_name="Desk"), agent, [], "என் பேர் கார்த்திக்",
                                                     "outbound", None, knowledge="")]
    assert asyncio.run(collect()) == [("உங்கள் மொபைல் எண் என்ன?", None)]
    time.sleep(0.1)
    assert len(read) < len(pieces)  # the model stopped being read


def test_sentences_split_without_a_space_but_not_inside_numbers_or_addresses():
    assert llm._SENTENCE_END.split("Fees are 1.5 lakh. See nimmiai.in today!Thanks") == [
        "Fees are 1.5 lakh.", "See nimmiai.in today!", "Thanks"]
    assert llm._clean_for_speech("நான் நிமி (Nimmi).") == "நான் நிமி Nimmi."


def _fake_streams(gap):
    """Stands in for sarvam.TtsStream: connects on first use, and drops the connection when a
    sentence is cut short (as the real one does, so leftover audio can't leak into the next)."""
    log = []

    class Stream:
        def __init__(self, language, speaker, pace, rate):
            self.language, self.connected = language, False

        async def open(self):
            if not self.connected:
                self.connected = True
                log.append(("open", self.language))

        async def close(self):
            if self.connected:
                self.connected = False
                log.append(("close", self.language))

        async def speak(self, text, **_):
            if not self.connected:
                self.connected = True
                log.append(("open", self.language))
            finished = False
            try:
                for _ in range(6):
                    await asyncio.sleep(gap)
                    log.append(("chunk", self.language, text))
                    yield b"\x01\x00" * 80
                finished = True
            finally:
                if not finished:
                    await self.close()
    return Stream, log


def _no_rest(*a):
    raise AssertionError("fell back to REST speech")


def test_switching_language_during_the_opening_doesnt_cut_it_off(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    stream, log = _fake_streams(0.03)  # the opening takes ~0.2 s to generate; they speak Tamil 0.03 s in
    monkeypatch.setattr(sarvam, "TtsStream", stream)
    monkeypatch.setattr(sarvam, "synthesize", _no_rest)

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)  # inbound: the opening starts at once
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("சரிங்க, fees ஒரு லட்சம்."), summarizer=fake_summary)
        await session._open_log()
        session._prepare_opening()
        greeting = asyncio.create_task(session._greet())
        await asyncio.sleep(0.03)  # the opening is still being generated when they speak Tamil
        await session.on_caller_text("எனக்கு data science course பத்தி தெரிஞ்சுக்கணும்", "ta-IN")
        await greeting
        await session.reply_task
        session.ended.set()
        await session._finish()
        return t, session

    t, session = run(scenario)
    english = [i for i, e in enumerate(log) if e[0] == "chunk" and e[1] == "en-IN"]
    tamil = [i for i, e in enumerate(log) if e[0] == "chunk" and e[1] == "ta-IN"]
    assert len(english) == 6 and len(tamil) == 6  # the whole opening played, then the answer
    assert log.index(("open", "ta-IN")) < max(english)  # the Tamil voice connected while the opening still played
    assert max(english) < log.index(("close", "en-IN")) < min(tamil)
    assert len(t.played) == 12 and session.lang == "ta-IN"


def test_every_voice_opened_for_a_language_is_closed_even_after_switching_again(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    stream, log = _fake_streams(0.01)
    monkeypatch.setattr(sarvam, "TtsStream", stream)

    async def scenario():
        session = CallSession(await _setup(u.id, bot), FakeTransport(), stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("x"), summarizer=fake_summary)
        session._switch_language("ta-IN")
        await asyncio.sleep(0.02)  # its voice connects
        session._switch_language("hi-IN")  # and they switch again before the agent has said anything
        await asyncio.sleep(0.02)
        await session._close_voices()  # the call ends

    run(scenario)
    assert sorted(e[1] for e in log if e[0] == "open") == sorted(e[1] for e in log if e[0] == "close") == ["hi-IN", "ta-IN"]


class SlowLine(FakeTransport):
    async def play(self, pcm):
        await asyncio.sleep(0.02)  # sending audio down a real line can wait
        await super().play(pcm)


def test_an_interrupted_answer_is_cleared_before_the_goodbye(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    stream, log = _fake_streams(0)
    monkeypatch.setattr(sarvam, "TtsStream", stream)
    monkeypatch.setattr(sarvam, "synthesize", _no_rest)

    async def scenario():
        t = SlowLine()
        setup = await _setup(u.id, bot)
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]), tts=None,
                              replier=replier_saying("The fees are one lakh a year."), summarizer=fake_summary)
        await session._open_log()
        session.greeted.set()
        await session.on_caller_text("What are the fees?")
        await asyncio.sleep(0.05)  # mid-answer
        await session.on_caller_text("ok bye")
        await session._finish()
        return t

    t = run(scenario)
    answer = [i for i, e in enumerate(log) if e[0] == "chunk" and e[2].startswith("The fees")]
    goodbye = [i for i, e in enumerate(log) if e[0] == "chunk" and e[2] == GOODBYES["en-IN"]]
    assert 0 < len(answer) < 6 and len(goodbye) == 6  # the answer was cut off; the goodbye played in full
    assert max(answer) < log.index(("close", "en-IN")) < min(goodbye)  # off the line before the goodbye began
    assert t.said() == ["The fees are one lakh a year.", GOODBYES["en-IN"]]


# ─── the speech service failing mid-call ──────────────────────────
from sqlalchemy.future import select  # noqa: E402
from database import async_session  # noqa: E402
from backend.models import CallLog  # noqa: E402


async def _logged(call_id):
    async with async_session() as db:
        return (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()


class DroppedRecognizer(FakeStt):
    """The speech service closed the connection (an outage, or out of credits)."""

    async def send(self, pcm):
        raise ConnectionError("recognizer connection closed")

    async def events(self):
        return
        yield  # pragma: no cover


def test_a_recognizer_that_drops_ends_the_call_instead_of_hanging(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        session = CallSession(setup, t, stt_factory=lambda *a: DroppedRecognizer([]), tts=fake_tts,
                              replier=replier_saying("x"), summarizer=fake_summary)
        feeder = asyncio.create_task(_feed(t, 10))
        call_id = await asyncio.wait_for(session.run(), timeout=5)  # it used to wait forever
        feeder.cancel()
        return await _logged(call_id), t

    log, t = run(scenario)
    assert log.outcome == "failed" and log.billed_minutes == 0 and "voice service" in log.summary
    assert t.hung_up == "done"


def test_a_voice_that_cant_speak_ends_the_call_at_once(run, make_user):
    u = make_user()
    bot = u.bot()

    async def no_credits(*a):
        raise RuntimeError("TTS 402: No credits available")

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, silence_timeout_sec=3)
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]), tts=no_credits,
                              replier=replier_saying("x"), summarizer=fake_summary)
        feeder = asyncio.create_task(_feed(t, 10))
        started = time.monotonic()
        call_id = await asyncio.wait_for(session.run(), timeout=8)
        took = time.monotonic() - started
        feeder.cancel()
        return took, await _logged(call_id), t

    took, log, t = run(scenario)
    assert took < 2  # not left in silence until the caller gives up
    assert log.outcome == "failed" and log.billed_minutes == 0 and t.hung_up == "done"
    assert any(e.get("code") == "speech" for e in t.events)  # the test panel says why


async def _feed(t, n):
    for _ in range(n):
        await t.inbox.put(b"\x00\x00" * 160)
        await asyncio.sleep(0.05)
