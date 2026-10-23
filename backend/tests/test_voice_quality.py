"""Call quality: a short protected opening, hellos, long speech, misheard numbers, and AI fallbacks."""
import asyncio
import time

from voice import llm
from voice.pipeline import CallSession, number_check
from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, fake_tts, replier_saying


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


def test_outbound_call_waits_for_hello_then_greets(run, make_user):
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
    assert said[0].startswith("Hi, Nimmi here") and said[-1].startswith("Thanks for calling")
    assert took < 2.5  # greeted on the hello, not after the full wait


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
