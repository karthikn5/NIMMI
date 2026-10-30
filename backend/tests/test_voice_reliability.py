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
    def model(bot, prompt, history, text, *_):
        yield from pieces
    monkeypatch.setattr(llm, "stream_reply", model)
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")

    async def collect():
        return [s async for s, _ in llm.reply_sentences(llm.Bot(bot_name="Desk"), agent, [], "fees?", "outbound", None,
                                                        knowledge="", reply_language=language)]
    return asyncio.run(collect())


def test_stage_directions_are_never_read_out(monkeypatch):
    """Live, 30 Oct 2026: the model glued "(Waiting for user response)" to its question, the brackets were dropped and the
    caller heard "...email address கொடுக்க முடியுமா? Waiting for user response"."""
    assert _answer(monkeypatch, ["மெயில் அனுப்ப உங்கள் email address கொடுக்க முடியுமா?(Waiting for user response)"],
                   "ta-IN") == ["மெயில் அனுப்ப உங்கள் email address கொடுக்க முடியுமா?"]
    assert _answer(monkeypatch, ["Sure. ", "(Waiting for user response) ", "The fee is 20,000 rupees (with GST)."],
                   "en-IN") == ["Sure.", "The fee is 20,000 rupees with GST."]
    assert _answer(monkeypatch, ["*pauses* ", "Your seat is booked."], "en-IN") == ["Your seat is booked."]


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
    # A language not heard yet on the call needs a longer sentence (or a second one): short unclear first words came
    # out as Punjabi and Malayalam on real calls, and the agent switched to them.
    assert not switch_now("ਉਹ ਵੀ ਮੈਨੂੰ", "pa-IN", 0.95, first_time=True)
    assert not switch_now("ஆ தமிழ் தெரியுமா உங்களுக்கு", "ta-IN", 0.9, first_time=True)
    assert switch_now("எனக்கு வந்து machine ஒன்னு internship பண்ணலாமா", "ta-IN", None, first_time=True)


def test_one_garbled_line_doesnt_flip_the_call_into_another_language(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        session, _ = await _call_in_progress(u, bot, replier_saying("x"), tts=fake_tts)
        seen = []
        for text, reported in (("ஆ தமிழ் தெரியுமா உங்களுக்கு, தமிழ்ல பேசலாமா", "ta-IN"),  # a clear Tamil sentence: Tamil at once
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


def test_unclear_first_words_dont_switch_the_call_into_a_random_language(run, make_user):
    """A real call's first words came out as Punjabi, another call's as Malayalam: both switched the agent."""
    u = make_user()
    bot = u.bot()

    async def scenario(lines):
        session, _ = await _call_in_progress(u, bot, replier_saying("x"), tts=fake_tts)
        seen = []
        for text, reported in lines:
            await session.on_caller_text(text, reported)
            seen.append(session.lang)
        if session.reply_task:
            await asyncio.gather(session.reply_task, return_exceptions=True)
        await _hang_up(session)
        return seen

    assert run(scenario, [("ਉਹ ਵੀ ਮੈਨੂੰ", "pa-IN"), ("I'm going to nominate", "en-IN")]) == ["en-IN", "en-IN"]
    assert run(scenario, [("Okay ഉടൻ തന്നെ", "ml-IN"), ("Do you know me?", "en-IN")]) == ["en-IN", "en-IN"]
    # A real Tamil caller who starts short: Tamil from their second sentence.
    assert run(scenario, [("தமிழ்ல பேசலாமா", "ta-IN"), ("எனக்கு fees தெரியணும்", "ta-IN")]) == ["en-IN", "ta-IN"]


def test_the_agent_only_switches_to_the_languages_the_business_picked(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        setup = await _setup(u.id, bot, switch_languages=["ta-IN"])
        session = CallSession(setup, FakeTransport(), stt_factory=lambda *a: FakeStt([]), tts=fake_tts,
                              replier=replier_saying("x"), summarizer=fake_summary)
        await session._open_log()
        session.greeted.set()
        seen = []
        for text, reported in (("നിങ്ങൾക്ക് മലയാളം അറിയാമോ എനിക്ക് ഫീസ് അറിയണം", "ml-IN"),  # long and clear, but not picked
                               ("எனக்கு இந்த internship பத்தி கொஞ்சம் சொல்லுங்க", "ta-IN")):
            await session.on_caller_text(text, reported)
            seen.append(session.lang)
        if session.reply_task:
            await asyncio.gather(session.reply_task, return_exceptions=True)
        await _hang_up(session)
        return seen

    assert run(scenario) == ["en-IN", "ta-IN"]


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
    backups_only = "gpt-5.4-mini"  # the agent's own model isn't set up here, so the backups answer
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Desk"), "p", [], "hi", backups_only)) == "From the free one."
    assert time.monotonic() - started < 0.6  # not the second the busy one would have taken
    assert "busy" in llm._rate_limited  # it rests a while
    assert timeouts and all(t is not None for t in timeouts)  # never the SDK's 15 s


def test_when_every_model_fails_the_apology_is_in_the_callers_language(monkeypatch):
    def broken(bot, prompt, history, text, *_):
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


# ─── the call hanging up on its own ───────────────────────────────
# Live calls hung up mid-conversation, a second after the agent asked something ("Karthik, what's your 10-digit
# mobile number?"). The models that answer while the main one is rate-limited (gpt-oss) add [END_CALL] to
# questions, glued on ("என்ன?[END_CALL]"), and the call hung up as soon as the question had been said.
from voice.pipeline import GOODBYES as _GOODBYES, TROUBLE_REPLIES  # noqa: E402
from tests.test_voice_quality import DroppedRecognizer, _logged  # noqa: E402


def _controls(monkeypatch, raw):
    """What a call gets when the model writes `raw` (in small pieces, as it streams)."""
    def model(bot, prompt, history, text, *_):
        for i in range(0, len(raw), 7):
            yield raw[i:i + 7]
    monkeypatch.setattr(llm, "stream_reply", model)
    agent = llm.VoiceAgent(language="ta-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="")

    async def collect():
        return [x async for x in llm.reply_sentences(llm.Bot(bot_name="Desk"), agent, [], "என் பேர் Karthik",
                                                     "outbound", None, knowledge="")]
    return asyncio.run(collect())


def test_a_question_never_hangs_up(monkeypatch):
    # The first two are what gpt-oss-20b and gpt-oss-120b wrote, replaying a cut call's last turn (Oct 2026).
    assert _controls(monkeypatch, "கார்த்திக் அவர்களின் email முகவரி என்ன?[END_CALL]") == [
        ("கார்த்திக் அவர்களின் email முகவரி என்ன?", None)]
    assert _controls(monkeypatch, "நன்றி Karthik. உங்கள் email address-ஐ சொல்ல முடியுமா?[END_CALL]") == [
        ("நன்றி Karthik.", None), ("உங்கள் email address-ஐ சொல்ல முடியுமா?", None)]
    assert _controls(monkeypatch, "[END_CALL] Could you repeat the number slowly?") == [
        ("Could you repeat the number slowly?", None)]
    assert _controls(monkeypatch, "Shall I connect you?[TRANSFER]") == [("Shall I connect you?", None)]


def test_a_goodbye_still_hangs_up(monkeypatch):
    for raw in ("Thank you, Karthik. Have a great day![END_CALL]", "Thank you, Karthik. Have a great day! [END_CALL]",
                "நன்றி, Karthik. நல்ல நாளாக அமையட்டும்.[END_CALL]"):
        said = _controls(monkeypatch, raw)
        assert said[-1][1] == llm.END_CALL and all(c is None for _, c in said[:-1]), raw
        assert all("[" not in s for s, _ in said), raw  # the marker is never spoken


def test_the_model_is_told_exactly_when_to_hang_up():
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Kdbot", greeting="",
                           transfer_enabled=True, transfer_number="+919876543210", team_handoff=False)
    prompt = llm.system_prompt(agent, llm.Bot(bot_name="Desk"), "", "inbound", None)
    assert "on its own" not in prompt  # "then write [END_CALL] on its own": read as "after every answer"
    assert f"Never write {llm.END_CALL} in any other reply, and never after a question" in prompt
    assert f"Never write {llm.TRANSFER} in any other reply" in prompt


async def _whole_call(u, bot, factory, replier, frames=30, tune=None):
    t = FakeTransport()
    session = CallSession(await _setup(u.id, bot), t, stt_factory=factory, tts=fake_tts, replier=replier,
                          summarizer=fake_summary)
    if tune:
        tune(session)

    async def feed():
        for _ in range(frames):
            await t.inbox.put(b"\x00\x00" * 160)
            await asyncio.sleep(0.05)
    feeder = asyncio.create_task(feed())
    call_id = await asyncio.wait_for(session.run(), timeout=10)
    feeder.cancel()
    return t, await _logged(call_id)


def test_the_call_stays_up_after_the_agent_asks_for_the_number(run, make_user, monkeypatch):
    """The whole way, with the model's own words: the question is asked, the line stays open, the caller answers."""
    u = make_user()
    bot = u.bot()
    written = iter(["கார்த்திக் அவர்களின் 10 இலக்க மொபைல் எண் என்ன?[END_CALL]",
                    "நன்றி, Karthik. நல்ல நாளாக அமையட்டும்.[END_CALL]"])

    def model(bot, prompt, history, text, *_):
        yield next(written)

    async def no_knowledge(bot):
        return ""
    monkeypatch.setattr(llm, "stream_reply", model)
    monkeypatch.setattr(llm, "call_knowledge", no_knowledge)
    monkeypatch.setattr(llm, "warm_up", lambda: None)
    heard = [Ev("transcript", "என் பேர் Karthik")] + [Ev("pause")] * 12 + [Ev("transcript", "98765 43210")]
    t, log = run(lambda: _whole_call(u, bot, lambda *a: FakeStt(heard), llm.reply_sentences))
    said = t.said()
    assert "கார்த்திக் அவர்களின் 10 இலக்க மொபைல் எண் என்ன?" in said
    assert said[-1] == "நல்ல நாளாக அமையட்டும்." and t.hung_up == "done"  # hung up after the goodbye, not before
    assert [x["text"] for x in log.transcript if x["speaker"] == "caller"] == ["என் பேர் Karthik", "98765 43210"]


# ─── the recognizer's connection dropping ─────────────────────────
# A dropped recognizer connection used to end the whole call, in silence.
def _system_lines(log):
    return [x["text"] for x in log.transcript if x["speaker"] == "system"]


class DroppingStt(FakeStt):
    """Hears its script, then its connection closes (as a speech service's sometimes does)."""

    async def send(self, pcm):
        if self.script:
            await self.queue.put(self.script.pop(0))
            if not self.script:
                await self.queue.put(None)


def test_a_recognizer_that_drops_mid_call_is_reconnected_and_the_call_goes_on(run, make_user):
    u = make_user()
    bot = u.bot()
    asked, made = [], []

    def factory(language, rate, mixed):
        made.append(DroppingStt([Ev("transcript", "What are the fees?")]) if not made else
                    FakeStt([Ev("transcript", "And the hostel fees?"), Ev("pause"), Ev("pause"), Ev("transcript", "ok bye")]))
        return made[-1]
    t, log = run(lambda: _whole_call(u, bot, factory, _replier(asked, "Sure.")))
    assert len(made) == 2 and asked == ["What are the fees?", "And the hostel fees?"]
    assert t.said()[-1] == _GOODBYES["en-IN"] and log.outcome != "failed"  # carried on, and ended normally
    assert _system_lines(log) == ["Speech recognition dropped for a moment and was reconnected"]


def test_an_error_handling_one_sentence_doesnt_end_the_call(run, make_user):
    u = make_user()
    bot = u.bot()
    asked, made = [], []

    def factory(language, rate, mixed):
        made.append(FakeStt([Ev("transcript", "boom"), Ev("pause"), Ev("transcript", "What are the fees?"),
                             Ev("pause"), Ev("pause"), Ev("transcript", "ok bye")]))
        return made[-1]

    def tune(session):
        original = session.on_caller_text

        async def flaky(text, language=None, probability=None):
            if text == "boom":
                raise RuntimeError("a bug while handling it")
            return await original(text, language, probability)
        session.on_caller_text = flaky

    t, log = run(lambda: _whole_call(u, bot, factory, _replier(asked, "Sure."), tune=tune))
    assert len(made) == 1 and asked == ["What are the fees?"]  # the same connection carried on
    assert t.said()[-1] == _GOODBYES["en-IN"] and log.outcome != "failed"


def test_when_the_recognizer_keeps_dropping_the_caller_is_told_before_the_call_ends(run, make_user):
    u = make_user()
    bot = u.bot()
    t, log = run(lambda: _whole_call(u, bot, lambda *a: DroppedRecognizer([]), replier_saying("x"), frames=60))
    assert TROUBLE_REPLIES["en-IN"] in t.said()  # not silence
    assert log.outcome == "failed" and log.billed_minutes == 0 and t.hung_up == "done"
    assert _system_lines(log)[-1].startswith("Call ended early because of a technical problem")


def test_a_recognizer_that_cant_be_reached_ends_the_call_at_once(run, make_user):
    u = make_user()
    bot = u.bot()
    tried = []

    class Unreachable(FakeStt):
        async def __aenter__(self):
            tried.append(1)
            raise ConnectionError("couldn't reach it")

    async def scenario():
        started = time.monotonic()
        result = await _whole_call(u, bot, lambda *a: Unreachable([]), replier_saying("x"), frames=60)
        return time.monotonic() - started, result
    took, (t, log) = run(scenario)
    assert len(tried) == 1 and took < 2  # no retrying a service that isn't there
    assert TROUBLE_REPLIES["en-IN"] in t.said() and log.outcome == "failed" and log.billed_minutes == 0


# ─── sound around the caller ──────────────────────────────────────
# The recognizer takes any speech-like sound for speech, however faint. On a real call, sound around the caller
# (20-35 dB below their voice) came through as "caller" lines ("अच्छा।", "नमस्कार", "this friend.", "ஆ") and the agent
# answered each one; with a TV on 20 dB below the caller, the recognizer never ended a turn and 4 of 7 questions
# went unanswered (simulated, Oct 2026).
import struct  # noqa: E402

from voice import levels as caller_levels  # noqa: E402
from tests.test_pipeline import RATE  # noqa: E402


def _tone(db, sec=0.02):
    """`sec` of sound at `db` dBFS (a square wave: its RMS is its height)."""
    height, n = int(32768 * 10 ** (db / 20)), int(RATE * sec)
    return struct.pack(f"<{n}h", *([height, -height] * (n // 2)))


class HearingStt(FakeStt):
    """Hears speech in whatever sound comes, like the real recognizer: the script is timed in seconds of audio
    received, and flush() finishes the turn at once (each flush says what that turn was)."""

    def __init__(self, script, flushes=()):
        super().__init__([])
        self.timed, self.flushes, self.heard, self.flushed_at = list(script), [list(f) for f in flushes], 0.0, []

    async def send(self, pcm):
        self.heard += len(pcm) / 2 / RATE
        while self.timed and self.timed[0][0] <= self.heard + 1e-6:
            await self.queue.put(self.timed.pop(0)[1])

    async def flush(self):
        self.flushed_at.append(round(self.heard, 2))
        for ev in (self.flushes.pop(0) if self.flushes else []):
            await self.queue.put(ev)


async def _room_call(u, bot, stt, timeline, replier, tts=fake_tts, **agent):
    """A call whose caller side sounds like `timeline`: (seconds, dBFS) pieces, in real time; then they hang up."""
    t = FakeTransport()
    session = CallSession(await _setup(u.id, bot, **agent), t, stt_factory=lambda *a: stt, tts=tts, replier=replier,
                          summarizer=fake_summary)

    async def feed():
        began, n = time.monotonic(), 0
        for sec, db in timeline:
            for _ in range(round(sec / 0.02)):
                await t.inbox.put(_tone(db))
                n += 1
                await asyncio.sleep(max(0.0, began + n * 0.02 - time.monotonic()))
        await t.inbox.put(None)
    feeder = asyncio.create_task(feed())
    call_id = await asyncio.wait_for(session.run(), timeout=30)
    feeder.cancel()
    return session, t, await _logged(call_id)


def test_the_callers_voice_level_is_learned_from_their_turns():
    lv = caller_levels.CallerLevels(RATE)
    assert lv.add(_tone(-20, 0.05), now=10.0) == pytest.approx([-20.0, -20.0], abs=0.1)  # whole 20 ms only
    assert lv.voice is None and not lv.background(9.0, 11.0)  # nothing to compare with yet
    assert lv.is_voice(-20) and not lv.is_voice(-30)  # meanwhile: a voice close to the phone
    lv.turns.extend([-32.0, -14.0, -16.0])  # the first was the room, taken for the caller before their level was known
    assert lv.voice == -15.0 and lv.is_voice(-29) and not lv.is_voice(-31)
    for i in range(30):  # the room: mostly quiet, a louder moment now and then
        lv.add(_tone(-28 if i % 12 == 0 else -45), now=20.0 + i * 0.02)
    for i in range(30):  # the caller
        lv.add(_tone(-18 if i % 2 else -40), now=21.0 + i * 0.02)
    assert lv.background(19.9, 20.7) and not lv.background(20.9, 21.7)
    assert not lv.background(20.0, 20.1) and not lv.background(30.0, 31.0)  # too little audio to say


def test_sounds_from_around_the_caller_arent_answered(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []
    stt = HearingStt([(0.5, Ev("speech_start")), (2.1, Ev("speech_end")), (2.15, Ev("transcript", "What are the fees?")),
                      (2.6, Ev("speech_start")), (3.9, Ev("speech_end")), (3.95, Ev("transcript", "नमस्कार")),
                      (4.9, Ev("speech_start")), (6.0, Ev("speech_end")), (6.05, Ev("transcript", "And the hostel?"))])
    timeline = [(0.5, -120), (1.0, -16), (1.0, -120), (0.8, -46), (1.5, -120), (0.6, -16), (1.5, -120)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, _replier(asked, "Sure.")))
    assert asked == ["What are the fees?", "And the hostel?"]
    assert "नमस्कार" not in [x["text"] for x in log.transcript] and session.background_ignored == 1


def test_sound_from_around_the_caller_doesnt_stop_the_agent_but_the_caller_does(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []
    # The answer (three 2 s sentences) plays from ~1.5 s. The room at 2.2-3.7 s (heard as speech for 1.5 s): it
    # carries on. The caller talking over it at 5-6.5 s: it stops for them.
    stt = HearingStt([(0.3, Ev("speech_start")), (1.4, Ev("speech_end")), (1.45, Ev("transcript", "What are the fees?")),
                      (2.3, Ev("speech_start")), (3.8, Ev("speech_end")), (3.85, Ev("transcript", "the weather tonight")),
                      (5.1, Ev("speech_start")), (6.9, Ev("speech_end")), (6.95, Ev("transcript", "Wait, and the hostel?"))])
    timeline = [(0.2, -120), (1.0, -16), (1.0, -120), (1.5, -46), (1.3, -120), (1.5, -16), (2.0, -120)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, _replier(asked, "One.", "Two.", "Three."), tts=long_tts))
    assert t.cleared == 1  # once: for the caller
    assert asked == ["What are the fees?", "Wait, and the hostel?"] and session.background_ignored == 1


def test_talk_around_the_caller_cant_keep_their_question_from_being_answered(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []
    # A TV from 2 s on, 24 dB below the caller: the recognizer hears speech from then on and never ends the turn
    # itself. The caller asks over it at 4-5.2 s.
    stt = HearingStt([(0.3, Ev("speech_start")), (1.4, Ev("speech_end")), (1.45, Ev("transcript", "Hello, who is this?")),
                      (2.2, Ev("speech_start"))],
                     flushes=[[Ev("speech_end"), Ev("transcript", "and the weather tonight"), Ev("speech_start")],
                              [Ev("speech_end"), Ev("transcript", "What are the fees?"), Ev("speech_start")]])
    timeline = [(0.2, -120), (1.0, -16), (0.8, -120), (2.0, -40), (1.2, -16), (2.5, -40)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, _replier(asked, "Sure.")))
    assert asked == ["Hello, who is this?", "What are the fees?"]
    # Cut where the caller started (so the TV's words stay out of theirs), and finished ~0.9 s after they stopped.
    assert len(stt.flushed_at) == 2 and 3.9 <= stt.flushed_at[0] <= 4.3 and 5.9 <= stt.flushed_at[1] <= 6.5
    assert "and the weather tonight" not in [x["text"] for x in log.transcript]


def test_a_lone_so_or_uh_isnt_answered(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []

    async def scenario():
        session, t = await _call_in_progress(u, bot, _replier(asked, "Sure."), tts=fake_tts)
        for text in ("So", "Uh", "ஆ", "हम्म", "So what are the fees?"):
            await session.on_caller_text(text)
            await asyncio.sleep(0.1)
        await _hang_up(session)
    run(scenario)
    assert asked == ["So what are the fees?"]


def test_the_caller_is_reminded_when_only_the_room_is_talking(run, make_user):
    u = make_user()
    bot = u.bot()
    # A TV from 2.5 s on: the recognizer hears speech from then on, but the caller has gone quiet.
    stt = HearingStt([(0.3, Ev("speech_start")), (1.4, Ev("speech_end")), (1.45, Ev("transcript", "What are the fees?")),
                      (2.6, Ev("speech_start"))])
    timeline = [(0.2, -120), (1.0, -16), (1.3, -120), (7.0, -40)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, replier_saying("They are 5000."), silence_timeout_sec=3))
    assert pipeline.REMINDERS_BY_LANG["en-IN"][0] in t.said()


def test_long_talk_around_the_caller_isnt_taken_for_them(run, make_user):
    """Seconds of a TV's talk have louder moments now and then: they mustn't add up to the caller's voice."""
    u = make_user()
    bot = u.bot()
    asked = []
    stt = HearingStt([(0.3, Ev("speech_start")), (1.4, Ev("speech_end")), (1.45, Ev("transcript", "What are the fees?")),
                      (2.0, Ev("speech_start")), (6.0, Ev("speech_end")), (6.05, Ev("transcript", "in sports the home team won"))])
    timeline = [(0.2, -120), (1.0, -16), (0.6, -120)] + [(0.24, -45), (0.02, -28)] * 16 + [(1.0, -120)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, _replier(asked, "Sure.")))
    assert asked == ["What are the fees?"] and session.background_ignored == 1


def test_a_tv_on_before_the_caller_speaks_isnt_answered_but_their_question_is(run, make_user):
    u = make_user()
    bot = u.bot()
    asked = []
    # The TV is on from the start, 24 dB below the caller: the recognizer hears speech throughout, and nothing tells
    # the caller's level yet. Their first words come at 3-4.2 s, over it.
    stt = HearingStt([(0.1, Ev("speech_start"))],
                     flushes=[[Ev("speech_end"), Ev("transcript", "breaking news this evening"), Ev("speech_start")],
                              [Ev("speech_end"), Ev("transcript", "What are the fees?"), Ev("speech_start")]])
    timeline = [(3.0, -40), (1.2, -16), (2.5, -40)]
    session, t, log = run(lambda: _room_call(u, bot, stt, timeline, _replier(asked, "Sure.")))
    assert asked == ["What are the fees?"]
    assert len(stt.flushed_at) == 2 and 2.9 <= stt.flushed_at[0] <= 3.3 and 4.9 <= stt.flushed_at[1] <= 5.5
