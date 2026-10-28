"""A live call's rough edges, each one seen on real calls: the agent going silent mid-call (a stuck speech
connection, a stalled AI service), slow answers, being cut off by a cough, answering in the wrong language after
one misheard line, and filler sounds ("hmm", "ஓ, அப்படியா!") that mean nothing."""
import asyncio
import base64
import json
import time

import pytest
from websockets.exceptions import ConnectionClosedOK
from websockets.protocol import State

from voice import llm, pipeline, sarvam
from voice.pipeline import CallSession
from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, fake_tts, long_tts, replier_saying


def _replier(asked, *sentences):
    async def gen(bot, agent, history, text, direction, consent, **_):
        asked.append(text)
        for s in sentences:
            yield s, None
    return gen


async def _call_in_progress(u, bot, replier, tts=long_tts):
    """A call past its opening (and `long_tts` makes every sentence still be playing when the caller speaks)."""
    t = FakeTransport()
    session = CallSession(await _setup(u.id, bot), t, stt_factory=lambda *a: FakeStt([]), tts=tts, replier=replier,
                          summarizer=fake_summary)
    await session._open_log()
    session.greeted.set()
    return session, t


async def _hang_up(session):
    session.ended.set()
    await session._finish()


# ─── filler sounds ────────────────────────────────────────────────
def _answer(monkeypatch, pieces, language):
    """What a call says when the model writes `pieces`."""
    def model(bot, prompt, history, text):
        yield from pieces
    monkeypatch.setattr(llm, "stream_reply", model)
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")

    async def collect():
        return [s async for s, _ in llm.reply_sentences(llm.Bot(bot_name="Desk"), agent, [], "fees?", "outbound", None,
                                                        knowledge="", reply_language=language)]
    return asyncio.run(collect())


def test_filler_sounds_and_empty_reactions_are_never_spoken(monkeypatch):
    """Real calls opened nearly every answer with "ஓ, அப்படியா!" ("Oh, is that so!") or "ஹ்ம்ம்...", each spoken on
    its own as an odd noise. Whatever the model writes, the answer starts at the answer."""
    assert _answer(monkeypatch, ["Hmm... ", "ஓ, அப்படியா! ", "ஹ்ம்ம், சரிங்க... fees ஒரு ", "லட்சம். ",
                                 "வேற ஏதாவது வேணுமா?"], "ta-IN") == ["சரிங்க, fees ஒரு லட்சம்.", "வேற ஏதாவது வேணுமா?"]
    assert _answer(monkeypatch, ["Hmm, yes, ", "how can I help?"], "en-IN") == ["Yes, how can I help?"]
    assert _answer(monkeypatch, ["अरे वाह! ", "हम्म, फीस एक लाख है।"], "hi-IN") == ["फीस एक लाख है।"]


def test_the_prompt_gives_the_model_no_fillers_to_copy():
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")
    for language in ("en-IN", "ta-IN", "hi-IN", "te-IN"):
        prompt = llm.system_prompt(agent, llm.Bot(bot_name="Desk"), "", "inbound", None, reply_language=language)
        assert "..." not in prompt and "Hmm, yes" not in prompt and "ஹ்ம்ம்..." not in prompt
        assert "Never use filler sounds" in prompt and "introduce yourself again" in prompt


def test_hellos_in_tamil_and_hindi_count_as_hellos():
    """A "வணக்கம்" over the opening got an answer of its own: the vowel signs split the word, so it never matched."""
    from voice.pipeline import _just_hello
    assert _just_hello("வணக்கம்") and _just_hello("हैलो जी") and _just_hello("சொல்லுங்க")


# ─── following the caller's language ──────────────────────────────
def test_one_sentence_switches_language_only_when_its_clear():
    from voice.pipeline import switch_now
    assert switch_now("எனக்கு data science course பத்தி தெரிஞ்சுக்கணும்", "ta-IN", None)
    assert switch_now("ஆ தமிழ் தெரியுமா உங்களுக்கு", "ta-IN", 0.9)
    assert not switch_now("தமிழ்ல பேசுங்க", "ta-IN", None)  # two words: wait for one more...
    assert switch_now("தமிழ்ல பேசுங்க", "ta-IN", 0.95)  # ...unless the recognizer is sure
    # Sarvam's certainty for this clear Tanglish sentence on a simulated call (Oct 2026): it must still switch.
    assert switch_now("எனக்கு data science course பத்தி தெரிஞ்சுக்கணும் fees எவ்வளவு", "ta-IN", 0.577)
    assert not switch_now("I think Katha calls", "en-IN", None)  # Tamil speech garbled into English (a real call)
    assert switch_now("I want to know about the fees", "en-IN", None)
    assert not switch_now("I want to know about the fees", "en-IN", 0.3)  # the recognizer itself isn't sure


def test_one_garbled_line_doesnt_flip_the_call_into_another_language(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        session, _ = await _call_in_progress(u, bot, replier_saying("x"), tts=fake_tts)
        seen = []
        for text, reported in (("ஆ தமிழ் தெரியுமா உங்களுக்கு", "ta-IN"),  # a clear Tamil sentence: Tamil at once
                               ("I think Katha calls", "en-IN"),  # Tamil speech that came out as English words
                               ("எனக்கு fees எவ்வளவு சொல்லுங்க", "ta-IN"),
                               ("Sorry, can we talk", "en-IN"),  # they really do change to English...
                               ("in English please", "en-IN")):  # ...and the next sentence confirms it
            await session.on_caller_text(text, reported)
            seen.append(session.lang)
        if session.reply_task:
            await asyncio.gather(session.reply_task, return_exceptions=True)
        await _hang_up(session)
        return seen

    assert run(scenario) == ["ta-IN", "ta-IN", "ta-IN", "ta-IN", "en-IN"]


# ─── interruptions ────────────────────────────────────────────────
class Recognizer:
    """Speech events, sent when the test says."""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    def hears(self, *events):
        for ev in events:
            self.queue.put_nowait(ev)

    async def events(self):
        while (ev := await self.queue.get()) is not None:
            yield ev


def test_a_cough_or_a_quick_mm_doesnt_cut_the_agent_off(run, make_user, monkeypatch):
    """The recognizer flags speech after a few hundredths of a second of sound. Stopping on that alone cut the agent
    off mid-sentence on a cough or line noise, with nothing to answer after: the call went quiet."""
    monkeypatch.setattr(pipeline, "BARGE_IN_SEC", 0.1)
    u = make_user()
    bot = u.bot()

    async def scenario():
        session, t = await _call_in_progress(u, bot, replier_saying("x"))
        recognizer = Recognizer()
        listening = asyncio.create_task(session._consume_stt(recognizer))
        await session.speak("The fees are one lakh a year, and the hostel is separate.")
        recognizer.hears(Ev("speech_start"))
        await asyncio.sleep(0.03)
        recognizer.hears(Ev("speech_end"))  # over almost at once
        await asyncio.sleep(0.2)
        after_cough = (t.cleared, session.speaking)
        recognizer.hears(Ev("speech_start"))  # now they really talk over it
        await asyncio.sleep(0.2)
        after_talking = (t.cleared, session.speaking)
        recognizer.hears(None)
        await listening
        await _hang_up(session)
        return after_cough, after_talking

    after_cough, after_talking = run(scenario)
    assert after_cough == (0, True)  # it carried on
    assert after_talking == (1, False)  # it stopped to listen


def test_listening_words_and_the_agents_own_echo_dont_stop_it_but_a_question_does(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []

    async def scenario():
        session, t = await _call_in_progress(u, bot, _replier(asked, "The fees are one lakh a year.", "The hostel is extra."))
        await session.on_caller_text("What are the fees?")
        await session.reply_task  # the answer is out, and still playing
        for text in ("okay", "சரி", "हाँ जी", "the fees are one lakh a year"):  # listening, then the agent's own voice
            await session.on_caller_text(text)
        quiet = (list(asked), t.cleared)
        await session.on_caller_text("And what about the hostel fees?")
        await session.reply_task
        await _hang_up(session)
        return quiet, t.cleared, session.transcript

    quiet, cleared, transcript = run(scenario)
    assert quiet == (["What are the fees?"], 0)  # nothing new answered, nothing cut off
    assert asked[-1] == "And what about the hostel fees?" and cleared == 1  # it stopped, and answered that
    callers = [x["text"] for x in transcript if x["speaker"] == "caller"]
    assert "okay" in callers and "the fees are one lakh a year" not in callers  # its echo isn't the caller


def test_a_yes_over_a_question_is_its_answer(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []

    async def scenario():
        session, t = await _call_in_progress(u, bot, _replier(asked, "Shall I book the visit for Monday?"))
        await session.on_caller_text("I want to visit the campus")
        await session.reply_task
        await session.on_caller_text("yes")  # before the question has finished playing
        await session.reply_task
        await _hang_up(session)

    run(scenario)
    assert asked == ["I want to visit the campus", "yes"]


# ─── a stuck speech connection ────────────────────────────────────
def _audio(pcm=b"\x01\x00" * 160):
    return json.dumps({"type": "audio", "data": {"audio": base64.b64encode(pcm).decode()}})


FINAL = json.dumps({"type": "event", "data": {"event_type": "final"}})


class FakeSocket:
    """Stands in for Sarvam's speech WebSocket: sends `replies`, then nothing (or `error`) for ever."""

    def __init__(self, replies=(), error=None):
        self.replies, self.error = list(replies), error
        self.sent = []
        self.state = State.OPEN

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self.error:
            raise self.error
        if self.replies:
            return self.replies.pop(0)
        await asyncio.Event().wait()

    async def close(self):
        self.state = State.CLOSED


def _connections(monkeypatch, *sockets):
    queue = list(sockets)

    async def connect(url, attempts=3, open_timeout=8):
        return queue.pop(0)
    monkeypatch.setattr(sarvam, "_connect_ws", connect)
    return queue


def test_a_voice_connection_that_goes_quiet_is_given_up_on_quickly(monkeypatch):
    monkeypatch.setattr(sarvam, "TTS_CHUNK_GAP_SEC", 0.1)
    _connections(monkeypatch, FakeSocket(), FakeSocket([_audio()]))

    async def speak(stream):
        chunks = []
        started = time.monotonic()
        with pytest.raises(sarvam.SarvamError):
            async for chunk in stream.speak("The fees are one lakh.", first_audio_sec=0.2):
                chunks.append(chunk)
        return len(chunks), time.monotonic() - started, stream.connected

    stream = sarvam.TtsStream("en-IN", "priya", 1.0, 8000)
    silent, cut = asyncio.run(speak(stream)), asyncio.run(speak(stream))
    assert silent[0] == 0 and silent[1] < 1 and not silent[2]  # no audio at all: it used to wait for ever
    assert cut[0] == 1 and cut[1] < 1 and not cut[2]  # stopped part way


def test_a_connection_sarvam_closed_while_idle_gets_one_fresh_try(monkeypatch):
    stale = FakeSocket(error=ConnectionClosedOK(None, None))  # closed by Sarvam; the close went unnoticed
    left = _connections(monkeypatch, FakeSocket([_audio(), FINAL]))
    stream = sarvam.TtsStream("en-IN", "priya", 1.0, 8000)
    stream._ws = stale  # kept from a sentence a minute ago

    async def speak():
        return [chunk async for chunk in stream.speak("Anything else?", first_audio_sec=1)]

    assert len(asyncio.run(speak())) == 1 and not left and stale.state is State.CLOSED


def test_a_stuck_voice_falls_back_to_rest_instead_of_leaving_the_caller_in_silence(run, make_user, monkeypatch):
    monkeypatch.setattr(sarvam, "TTS_FIRST_AUDIO_SEC", 0.2)
    _connections(monkeypatch, FakeSocket())  # connects, then never sends audio
    rest = []

    async def synthesize(text, language, speaker, pace, rate):
        rest.append(text)
        return b"\x01\x00" * 800
    monkeypatch.setattr(sarvam, "synthesize", synthesize)
    u = make_user()
    bot = u.bot()

    async def scenario():
        session, t = await _call_in_progress(u, bot, replier_saying("x"), tts=None)
        started = time.monotonic()
        await session.speak("The fees are one lakh a year.")
        took = time.monotonic() - started
        await session._close_voices()
        await _hang_up(session)
        return took, t.played

    took, played = run(scenario)
    assert rest == ["The fees are one lakh a year."] and played and took < 1


def test_open_voice_connections_are_kept_alive_while_the_caller_talks(run, make_user):
    """Sarvam closes a speech connection after a minute without traffic."""
    u = make_user()
    bot = u.bot()

    async def scenario():
        session, _ = await _call_in_progress(u, bot, replier_saying("x"), tts=None)
        socket = FakeSocket()
        session.tts_stream = sarvam.TtsStream("en-IN", "priya", 1.0, 8000)
        session.tts_stream._ws = socket
        await session._keep_voices_warm()  # just used: nothing to do
        session.tts_stream.used_at -= 30  # quiet for 30 s while the caller explained something
        await session._keep_voices_warm()
        await _hang_up(session)
        return socket.sent

    assert run(scenario) == [{"type": "ping"}]


# ─── slow or missing answers ──────────────────────────────────────
def test_a_slow_answer_says_one_moment_and_that_isnt_remembered_as_the_answer(run, make_user, monkeypatch):
    monkeypatch.setattr(pipeline, "HOLD_AFTER_SEC", 0.05)
    u = make_user()
    bot = u.bot()

    async def busy_service(bot, agent, history, text, direction, consent, **_):
        await asyncio.sleep(0.3)
        yield "The fees are one lakh a year.", None

    async def scenario():
        session, t = await _call_in_progress(u, bot, busy_service, tts=fake_tts)
        await session.on_caller_text("What are the fees?")
        await session.reply_task
        await _hang_up(session)
        return t.said(), session.history

    said, history = run(scenario)
    assert said == ["One moment, please.", "The fees are one lakh a year."]
    assert history[-1] == {"role": "assistant", "content": "The fees are one lakh a year."}


def test_an_answer_that_never_comes_doesnt_leave_the_caller_in_silence(run, make_user, monkeypatch):
    monkeypatch.setattr(pipeline, "HOLD_AFTER_SEC", 0.05)
    monkeypatch.setattr(pipeline, "REPLY_GIVE_UP_SEC", 0.3)
    u = make_user()
    bot = u.bot()

    async def stalled(bot, agent, history, text, direction, consent, **_):
        await asyncio.sleep(30)
        yield "never", None

    async def scenario():
        session, t = await _call_in_progress(u, bot, stalled, tts=fake_tts)
        await session.on_caller_text("What are the fees?")
        await asyncio.wait_for(session.reply_task, 2)  # it used to wait as long as the AI service did
        await _hang_up(session)
        return t.said()

    assert run(scenario) == ["One moment, please.", llm.FALLBACK_ERRORS["en-IN"]]


def test_a_groq_model_that_doesnt_start_answering_hands_over_to_the_next(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    monkeypatch.setattr(llm, "VOICE_GROQ_MODELS", ["busy", "free"])
    monkeypatch.setattr(llm, "GROQ_FIRST_WORDS_SEC", 0.1)
    timeouts = []

    def chunk(text):
        delta = type("Delta", (), {"content": text})()
        return type("Chunk", (), {"choices": [type("Choice", (), {"delta": delta})()]})()

    class Stream:
        def __init__(self, model):
            self.model = model

        def __iter__(self):
            if self.model == "busy":
                for _ in range(50):  # a second of "thinking" before any words
                    time.sleep(0.02)
                    yield chunk(None)
            yield chunk("From the free one.")

        def close(self):
            pass

    class Completions:
        @staticmethod
        def create(model, timeout=None, **_):
            timeouts.append(timeout)
            return Stream(model)

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions})()})()
    monkeypatch.setattr(llm, "_groq", lambda: client)
    started = time.monotonic()
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Desk"), "p", [], "hi")) == "From the free one."
    assert time.monotonic() - started < 0.6  # not the second the busy one would have taken
    assert "busy" in llm._rate_limited  # it rests a while
    assert timeouts and all(t is not None for t in timeouts)  # never the SDK's 15 s


def test_when_every_model_fails_the_apology_is_in_the_callers_language(monkeypatch):
    def broken(bot, prompt, history, text):
        raise RuntimeError("every model is down")
        yield  # pragma: no cover
    monkeypatch.setattr(llm, "stream_reply", broken)
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")

    async def collect():
        return [s async for s, _ in llm.reply_sentences(llm.Bot(bot_name="Desk"), agent, [], "fees?", "inbound", None,
                                                        knowledge="", reply_language="ta-IN")]
    assert " ".join(asyncio.run(collect())) == llm.FALLBACK_ERRORS["ta-IN"]


# ─── the conversation the model sees ──────────────────────────────
def test_a_sentence_cut_off_before_it_was_heard_isnt_remembered_as_said(run, make_user):
    u = make_user()
    bot = u.bot()

    async def tts(text, language, speaker, pace, rate):
        if text.startswith("The hostel"):
            await asyncio.Event().wait()  # its audio never starts: the caller talks first
        return b"\x01\x00" * 160

    async def scenario():
        session, _ = await _call_in_progress(u, bot, replier_saying("The fees are one lakh.", "The hostel is extra."), tts=tts)
        await session.on_caller_text("What are the fees?")
        await asyncio.sleep(0.05)
        session.reply_task.cancel()  # the caller talked over it
        await asyncio.gather(session.reply_task, return_exceptions=True)
        await _hang_up(session)
        return session.history

    assert run(scenario) == [{"role": "user", "content": "What are the fees?"},
                             {"role": "assistant", "content": "The fees are one lakh."}]
