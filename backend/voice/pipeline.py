"""
One live call, from greeting to post-call summary.

Transport-agnostic: the browser test panel and Exotel phone calls both plug in
a Transport. Speech services are injectable so the session can be tested
without network access.
"""
import asyncio
import logging
import re
import time
from array import array
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Awaitable, Callable, Optional, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import async_session
from backend.models import Bot, CallbackJob, CallLog, DncEntry, VoiceAgent
import assist
from notify.events import call_completed, fire_and_forget
from phone import extract_contact
from voice import ambience, llm, metering, recording, sarvam, scheduler

logger = logging.getLogger(__name__)


class Transport(Protocol):
    sample_rate: int
    async def receive(self) -> Optional[bytes]: ...       # caller PCM16 mono; None when the caller hangs up
    async def play(self, pcm: bytes) -> None: ...          # queue assistant audio
    async def clear(self) -> None: ...                     # drop queued audio (barge-in)
    async def event(self, data: dict) -> None: ...         # UI updates (browser only)
    async def hangup(self, reason: str) -> None: ...       # end the call ("done" or "transfer")


@dataclass
class CallSetup:
    owner_id: str
    bot: Bot
    agent: VoiceAgent
    direction: str = "inbound"          # inbound, outbound
    channel: str = "phone"              # phone, browser
    caller_e164: Optional[str] = None
    consent_source: Optional[str] = None
    provider_call_id: Optional[str] = None
    callback_job_id: Optional[str] = None
    record: bool = True
    opt_out_phrases: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)  # {{placeholders}} for this call (campaign columns, caller name)
    purpose: Optional[str] = None                  # outbound: why we're calling
    campaign_id: Optional[str] = None
    voicemail: bool = False                        # reached an answering machine: leave the message and go
    after_hours: Optional[str] = None              # team offline: "tomorrow at 9:00 AM" (no transfers)


SttFactory = Callable[[str, int, bool], object]
Tts = Callable[[str, str, str, float, int], Awaitable[bytes]]
Replier = Callable[..., AsyncIterator[tuple[str, Optional[str]]]]
Summarizer = Callable[[Bot, list], Awaitable[dict]]

GOODBYES = {
    "ta-IN": "அழைத்ததற்கு நன்றி. வணக்கம்!",
    "hi-IN": "कॉल करने के लिए धन्यवाद। नमस्ते!",
    "te-IN": "కాల్ చేసినందుకు ధన్యవాదాలు. ఉంటానండి!",
    "kn-IN": "ಕರೆ ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ!",
    "ml-IN": "വിളിച്ചതിന് നന്ദി. നമസ്കാരം!",
    "mr-IN": "कॉल केल्याबद्दल धन्यवाद. नमस्कार!",
    "bn-IN": "কল করার জন্য ধন্যবাদ। নমস্কার!",
    "gu-IN": "કૉલ કરવા બદલ આભાર. નમસ્તે!",
    "pa-IN": "ਕਾਲ ਕਰਨ ਲਈ ਧੰਨਵਾਦ। ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ!",
    "od-IN": "କଲ୍ କରିଥିବାରୁ ଧନ୍ୟବାଦ। ନମସ୍କାର!",
    "en-IN": "Thanks for calling. Have a great day!",
}

REMINDERS_BY_LANG = {
    "ta-IN": ["ஹலோ, லைன்ல இருக்கீங்களா?", "வணக்கம், கேக்குதாங்க?", "நான் இங்கதான் இருக்கேன், சொல்லுங்க."],
    "hi-IN": ["क्या आप सुन रहे हैं?", "नमस्ते, क्या आपको मेरी आवाज़ आ रही है?", "जी, मैं यहीं हूँ, बताइए।"],
    "te-IN": ["హలో, లైన్‌లో ఉన్నారా?", "నమస్కారం, నా మాట వినిపిస్తోందా?", "నేను ఇక్కడే ఉన్నాను, చెప్పండి."],
    "kn-IN": ["ಹಲೋ, ಲೈನ್‌ನಲ್ಲಿದ್ದೀರಾ?", "ನಮಸ್ಕಾರ, ನನ್ನ ಧ್ವನಿ ಕೇಳಿಸುತ್ತಿದೆಯೇ?", "ನಾನು ಇಲ್ಲೇ ಇದ್ದೇನೆ, ಹೇಳಿ."],
    "ml-IN": ["ഹലോ, ലൈനിലുണ്ടോ?", "നമസ്കാരം, കേൾക്കുന്നുണ്ടോ?", "ഞാൻ ഇവിടെയുണ്ട്, പറയൂ."],
    "mr-IN": ["हॅलो, आपण ऐकत आहात का?", "माझा आवाज येत आहे का?", "मी इथेच आहे, बोला."],
    "bn-IN": ["হ্যালো, আপনি কি লাইনে আছেন?", "আমার কথা কি শোনা যাচ্ছে?", "আমি শুনছি, বলুন।"],
    "gu-IN": ["હેલો, શું તમે સાંભળી રહ્યા છો?", "નમસ્તે, મારો અવાજ આવે છે?", "હું અહીં જ છું, કહો."],
    "pa-IN": ["ਹੈਲੋ, ਕੀ ਤੁਸੀਂ ਲਾਈਨ ਤੇ ਹੋ?", "ਕੀ ਮੇਰੀ ਆਵਾਜ਼ ਆ ਰਹੀ ਹੈ?", "ਮੈਂ ਇੱਥੇ ਹੀ ਹਾਂ, ਦੱਸੋ ਜੀ।"],
    "od-IN": ["ହେଲୋ, ଆପଣ ଶୁଣୁଛନ୍ତି କି?", "ମୋ ସ୍ୱର ଶୁଭୁଛି କି?", "ମୁଁ ଏଇଠି ଅଛି, କୁହନ୍ତୁ |"],
    "en-IN": ["Are you still there?", "Hello, can you hear me?", "I'm still here whenever you're ready."],
}

OPT_OUT_REPLIES = {
    "ta-IN": "புரிந்தது. இனி உங்களை தொடர்பு கொள்ள மாட்டோம். நன்றி, வணக்கம்.",
    "hi-IN": "समझ गया। हम आपको दोबारा संपर्क नहीं करेंगे। धन्यवाद, नमस्ते।",
    "te-IN": "అర్థమైంది. ఇకపై మిమ్మల్ని సంప్రదించము. ధన్యవాదాలు, ఉంటానండి.",
    "kn-IN": "ತಿಳಿಯಿತು. ಇನ್ನು ಮುಂದೆ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುವುದಿಲ್ಲ. ಧನ್ಯವಾದಗಳು, ನಮಸ್ಕಾರ.",
    "ml-IN": "മനസ്സിലായി. ഇനി നിങ്ങളെ ബന്ധപ്പെടില്ല. നന്ദി, നമസ്കാരം.",
    "mr-IN": "समजले. आम्ही तुम्हाला पुन्हा संपर्क करणार नाही. धन्यवाद, नमस्कार.",
    "bn-IN": "বুঝতে পেরেছি। আমরা আর আপনার সাথে যোগাযোগ করব না। ধন্যবাদ, নমস্কার।",
    "gu-IN": "સમજી ગયું. અમે ફરી તમારો સંપર્ક નહીં કરીએ. આભાર, નમસ્તે.",
    "pa-IN": "ਸਮਝ ਗਿਆ ਜੀ। ਅਸੀਂ ਤੁਹਾਨੂੰ ਦੁਬਾਰਾ ਸੰਪਰਕ ਨਹੀਂ ਕਰਾਂਗੇ। ਧੰਨਵਾਦ, ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ।",
    "od-IN": "ବୁଝିପାରିଲି | ଆମେ ଆପଣଙ୍କୁ ପୁଣି ଯୋଗାଯୋଗ କରିବୁ ନାହିଁ | ଧନ୍ୟବାଦ, ନମସ୍କାର |",
    "en-IN": "Understood. We won't contact you again. Thank you, goodbye.",
}

NO_MINUTES_REPLIES = {
    "ta-IN": "மன்னிக்கவும், தற்போது இந்த எண்ணில் அழைப்புகளை ஏற்க இயலவில்லை. பிறகு முயற்சிக்கவும்.",
    "hi-IN": "क्षमा करें, इस समय इस लाइन पर कॉल उपलब्ध नहीं हैं। कृपया बाद में प्रयास करें।",
    "te-IN": "క్షమించండి, ప్రస్తుతం ఈ లైన్ అందుబాటులో లేదు. దయచేసి తర్వాత ప్రయత్నించండి.",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ಪ್ರಸ್ತುತ ಈ ಲೈನ್ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ನಂತರ ಪ್ರಯತ್ನಿಸಿ.",
    "ml-IN": "ക്ഷമിക്കണം, നിലവിൽ ഈ ലൈൻ ലഭ്യമല്ല. ദയവായി പിന്നീട് ശ്രമിക്കുക.",
    "en-IN": "Sorry, this line can't take calls right now. Please try again later.",
}

TIMEOUT_REPLIES = {
    "ta-IN": "அழைப்பின் நேர வரம்பை எட்டிவிட்டோம். அழைத்ததற்கு நன்றி, வணக்கம்.",
    "hi-IN": "इस कॉल की समय सीमा समाप्त हो गई है। कॉल करने के लिए धन्यवाद, नमस्ते।",
    "en-IN": "We've reached the time limit for this call. Thanks for calling, goodbye.",
}

FRAME_SEC = 0.1   # with background sound, audio goes out in real-time frames
LEAD_SEC = 0.25   # how far ahead of real time we keep the line fed


def _normalize(text: str) -> str:
    """Lowercase, straight apostrophes, punctuation to spaces: "Okay, thank you. Bye." -> " okay thank you bye "."""
    text = re.sub(r"[^\w\s']", " ", text.lower().replace("’", "'"))
    return " " + " ".join(text.split()) + " "


def _matches(text: str, phrases: list) -> bool:
    t = _normalize(text)
    for p in phrases:
        phrase = _normalize(p or "").strip()
        if phrase and (f" {phrase} " in t or (len(phrase) > 6 and phrase in t)):
            return True
    return False


class CallSession:
    def __init__(self, setup: CallSetup, transport: Transport, *, stt_factory: Optional[SttFactory] = None,
                 tts: Optional[Tts] = None, replier: Optional[Replier] = None, summarizer: Optional[Summarizer] = None):
        self.s = setup
        self.t = transport
        self.rate = transport.sample_rate
        self.stt_factory = stt_factory or (lambda lang, rate, mixed: sarvam.SttStream(lang, rate, mixed))
        self.tts = tts  # None = Sarvam streaming TTS
        self.tts_stream: Optional[sarvam.TtsStream] = None
        self.replier = replier or llm.reply_sentences
        self.summarizer = summarizer or llm.summarize
        self.recorder = recording.Recorder(self.rate)

        self.call_id: Optional[str] = None
        self.started = time.monotonic()
        self.transcript: list[dict] = []
        self.history: list[dict] = []
        self.speaking_until = 0.0
        self.last_heard = time.monotonic()
        self.silence_prompts = 0
        self.reply_task: Optional[asyncio.Task] = None
        self.turn_spoken = False  # has the current reply produced any speech yet?
        self.ended = asyncio.Event()
        self.opted_out = False
        self.transferred = False
        self.caller_spoke = False
        self.failure: Optional[str] = None
        self.ambience: Optional[ambience.AmbiencePlayer] = None
        self.out_buf = bytearray()  # assistant speech waiting for the playout clock (background sound on)
        # Diagnostics: what actually arrived from the caller's side.
        self.caller_bytes = 0
        self.caller_peak = 0
        self.stt_events = {"speech_start": 0, "transcript": 0, "error": 0}

    # ── helpers ────────────────────────────────────────────────
    def _elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    def _log(self, speaker: str, text: str) -> None:
        self.transcript.append({"at_sec": self._elapsed(), "speaker": speaker, "text": text})

    @property
    def speaking(self) -> bool:
        return time.monotonic() < self.speaking_until

    async def _tts_chunks(self, text: str):
        """Audio for `text`, streamed when possible (first audio ~0.4 s), else in one piece over REST."""
        agent = self.s.agent
        args = (text, agent.language, agent.voice_id or "priya", agent.speaking_rate or 1.0, self.rate)
        if self.tts is not None:  # injected (tests)
            yield await self.tts(*args)
            return
        yielded = False
        try:
            if self.tts_stream is None:
                self.tts_stream = sarvam.TtsStream(agent.language, args[2], args[3], self.rate)
            async for chunk in self.tts_stream.speak(text):
                yielded = True
                yield chunk
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Streaming TTS failed ({e}); using REST")
            if not yielded:
                yield await sarvam.synthesize(*args)

    def _for_speech(self, text: str) -> str:
        """Apply the agent's pronunciation guide (spoken audio only; the transcript keeps the spelling)."""
        for rule in self.s.agent.pronunciations or []:
            word, say = (rule.get("word") or "").strip(), (rule.get("say") or "").strip()
            if word and say:
                text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", say, text, flags=re.IGNORECASE)
        return text

    async def speak(self, text: str) -> None:
        if not text or self.ended.is_set():
            return
        self._log("agent", text)
        await self.t.event({"type": "agent", "text": text})
        async for pcm in self._tts_chunks(self._for_speech(text)):
            if self.ended.is_set() or not pcm:
                return
            self.recorder.add_agent(pcm)
            if self.ambience:
                self.out_buf.extend(pcm)  # the playout loop sends it, mixed with the background
            else:
                await self.t.play(pcm)
            now = time.monotonic()
            self.speaking_until = max(now, self.speaking_until) + len(pcm) / 2 / self.rate

    def _lang(self) -> str:
        return self.s.agent.language or "en-IN"

    def _goodbye(self) -> str:
        return GOODBYES.get(self._lang(), GOODBYES["en-IN"])

    def _opt_out_reply(self) -> str:
        return OPT_OUT_REPLIES.get(self._lang(), OPT_OUT_REPLIES["en-IN"])

    def _no_minutes_reply(self) -> str:
        return NO_MINUTES_REPLIES.get(self._lang(), NO_MINUTES_REPLIES["en-IN"])

    def _timeout_reply(self) -> str:
        return TIMEOUT_REPLIES.get(self._lang(), TIMEOUT_REPLIES["en-IN"])

    def _fallback_reply(self) -> str:
        return llm.FALLBACK_ERRORS.get(self._lang(), llm.FALLBACK_ERRORS["en-IN"])

    def _reminder(self, count: int) -> str:
        reminders = REMINDERS_BY_LANG.get(self._lang(), REMINDERS_BY_LANG["en-IN"])
        return reminders[(count - 1) % len(reminders)]

    async def _playout(self) -> None:
        """Background sound on: feed the line one frame at a time, speech mixed over the ambience with speech ducking."""
        nbytes = int(self.rate * FRAME_SEC) * 2
        next_at = time.monotonic()
        while not self.ended.is_set():
            now = time.monotonic()
            if next_at - now > LEAD_SEC:
                await asyncio.sleep(0.02)
                continue
            next_at = max(next_at, now - 0.05)  # if we fell behind, don't try to catch up with a burst
            speech = bytes(self.out_buf[:nbytes])
            del self.out_buf[:nbytes]
            speech += b"\x00" * (nbytes - len(speech))
            if self.ambience:
                is_speaking = any(speech)
                self.ambience.set_ducked(is_speaking)
            await self.t.play(ambience.mix(speech, self.ambience.next(nbytes)))
            next_at += FRAME_SEC

    async def _wait_for_playback(self, limit: float = 15.0) -> None:
        remaining = min(self.speaking_until - time.monotonic(), limit)
        if remaining > 0:
            await asyncio.sleep(remaining)
        if self.ambience:
            deadline = time.monotonic() + limit
            while self.out_buf and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            await asyncio.sleep(LEAD_SEC)  # let the last frames reach the caller

    async def end(self, reason: str = "done") -> None:
        if self.ended.is_set():
            return
        await self._wait_for_playback()
        self.ended.set()
        try:
            await self.t.hangup(reason)
        except Exception as e:
            logger.debug(f"hangup: {e}")

    # ── events ────────────────────────────────────────────────
    async def on_speech_start(self) -> None:
        self.last_heard = time.monotonic()
        if self.speaking and self.s.agent.allow_interruptions:
            if self.reply_task and not self.reply_task.done():
                self.reply_task.cancel()
            self.speaking_until = time.monotonic()
            self.out_buf.clear()
            self.recorder.cut_agent()
            await self.t.clear()

    async def on_caller_text(self, text: str) -> None:
        self.caller_spoke = True
        self.last_heard = time.monotonic()
        self.silence_prompts = 0
        self._log("caller", text)
        await self.t.event({"type": "caller", "text": text})

        if _matches(text, self.s.opt_out_phrases):
            self.opted_out = True
            await self._add_to_dnc()
            await self.speak(self._opt_out_reply())
            await self.end()
            return
        if _matches(text, self.s.agent.end_call_phrases or []):
            await self.speak(self._goodbye())
            await self.end()
            return

        if self.reply_task and not self.reply_task.done():
            self.reply_task.cancel()
            if not self.turn_spoken and self.history and self.history[-1]["role"] == "user":
                # The caller was still going (the recognizer split one sentence):
                # answer the whole thing, not the fragments.
                text = f"{self.history.pop()['content']} {text}"
        self.reply_task = asyncio.create_task(self._reply(text))

    async def _reply(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        self.turn_spoken = False
        said: list[str] = []
        try:
            async for sentence, control in self.replier(self.s.bot, self.s.agent, self.history[:-1], text,
                                                        self.s.direction, self.s.consent_source,
                                                        variables=self.s.variables, purpose=self.s.purpose,
                                                        after_hours=self.s.after_hours):
                if sentence:
                    said.append(sentence)
                    self.turn_spoken = True
                    await self.speak(sentence)
                if control == llm.TRANSFER:
                    await self._transfer()
                    return
                if control == llm.END_CALL:
                    await self.end()
                    return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Reply failed: {e}")
            await self.speak(self._fallback_reply())
        finally:
            if said:
                self.history.append({"role": "assistant", "content": " ".join(said)})
                if self.s.channel == "phone" and assist.is_unanswered(" ".join(said)):
                    fire_and_forget(assist.record_gap(self.s.bot.bot_id, text, "voice", None))

    async def _transfer(self) -> None:
        agent = self.s.agent
        if not (agent.transfer_enabled and agent.transfer_number) or self.s.after_hours:
            return  # nobody to transfer to (or the team is offline): the assistant takes a message instead
        if self.s.channel == "browser":
            await self.speak(f"This is a test call, so I won't transfer you. On a real call I'd connect you to {agent.transfer_number} now.")
            await self.end()
            return
        self.transferred = True
        self._log("system", f"Transferred to {agent.transfer_number}")
        if self.s.provider_call_id:
            if (agent.transfer_mode or "cold") == "warm":
                # Whisper a short brief to the person before they're connected (Twilio).
                try:
                    brief = await asyncio.wait_for(llm.transfer_brief(self.s.bot, self.transcript, self.s.caller_e164), 4)
                except Exception:
                    brief = None
                if brief:
                    scheduler.pending_whispers[self.s.provider_call_id] = brief
            # The provider asks us next (Exotel Passthru / Twilio <Connect action>) whether and where to transfer.
            scheduler.pending_transfers[self.s.provider_call_id] = agent.transfer_number
        await self.end("transfer")

    async def _add_to_dnc(self) -> None:
        if not self.s.caller_e164:
            return
        async with async_session() as db:
            db.add(DncEntry(user_id=self.s.owner_id, e164=self.s.caller_e164, reason="caller_request"))
            try:
                await db.commit()
            except IntegrityError:
                pass  # already listed

    # ── loops ────────────────────────────────────────────────
    async def _pump_audio(self, stt) -> None:
        while not self.ended.is_set():
            pcm = await self.t.receive()
            if pcm is None:
                self.ended.set()  # caller hung up
                return
            if self.s.record:
                self.recorder.add_caller(pcm)
            self.caller_bytes += len(pcm)
            samples = array("h")
            samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
            if samples:
                self.caller_peak = max(self.caller_peak, max(abs(s) for s in samples))
            await stt.send(pcm)

    async def _consume_stt(self, stt) -> None:
        async for ev in stt.events():
            if ev.kind in self.stt_events:
                self.stt_events[ev.kind] += 1
            if ev.kind == "speech_start":
                await self.on_speech_start()
            elif ev.kind == "transcript":
                await self.on_caller_text(ev.text)
            elif ev.kind == "error":
                logger.warning(f"STT error: {ev.text}")
            if self.ended.is_set():
                return

    async def _watchdog(self) -> None:
        agent = self.s.agent
        limit = max(1, agent.max_call_minutes or 10) * 60
        silence = max(3, agent.silence_timeout_sec or 8)
        while not self.ended.is_set():
            await asyncio.sleep(0.5)
            if self._elapsed() >= limit:
                await self.speak(self._timeout_reply())
                await self.end()
                return
            busy = self.speaking or (self.reply_task is not None and not self.reply_task.done())
            if busy:
                continue
            quiet_for = time.monotonic() - max(self.last_heard, self.speaking_until)
            if quiet_for >= silence:
                allowed = 1 if agent.silence_reminders is None else max(0, min(3, agent.silence_reminders))
                if self.silence_prompts < allowed:
                    self.silence_prompts += 1
                    self.last_heard = time.monotonic()
                    await self.speak(self._reminder(self.silence_prompts))
                else:
                    await self.speak(self._goodbye())
                    await self.end()
                    return

    # ── lifecycle ───────────────────────────────────────────────
    async def _open_log(self) -> None:
        async with async_session() as db:
            log = CallLog(user_id=self.s.owner_id, bot_id=self.s.bot.bot_id, direction=self.s.direction,
                          channel=self.s.channel, caller_e164=self.s.caller_e164, language=self.s.agent.language,
                          consent_source=self.s.consent_source, provider_call_id=self.s.provider_call_id,
                          campaign_id=self.s.campaign_id, outcome="in_progress")
            db.add(log)
            await db.commit()
            self.call_id = log.id
        await self.t.event({"type": "started", "call_id": self.call_id})

    async def run(self) -> Optional[str]:
        await self._open_log()
        async with async_session() as db:
            wallet = await metering.get_wallet(db, self.s.owner_id)
            has_minutes = metering.minutes_left(wallet) > 0
        if not has_minutes:
            self.failure = "No voice minutes left"
            await self.t.event({"type": "error", "code": "no_minutes", "message": "You're out of voice minutes."})
            try:
                await self.speak(self._no_minutes_reply())
            except Exception:
                pass
            await self.end()
            if self.tts_stream:
                await self.tts_stream.close()
            await self._finish()
            return self.call_id

        kind = self.s.agent.ambience or "none"
        if kind != "none" and kind in ambience.KINDS:
            try:
                await asyncio.to_thread(ambience.loop, kind, self.rate)  # cached after the first call
                self.ambience = ambience.AmbiencePlayer(kind, self.s.agent.ambience_volume or "medium", self.rate)
            except Exception as e:
                logger.warning(f"Background sound unavailable: {e}")

        if self.s.voicemail:
            return await self._leave_voicemail()

        tasks: list[asyncio.Task] = []
        if self.ambience:
            tasks.append(asyncio.create_task(self._playout()))
        try:
            async with self.stt_factory(self.s.agent.language, self.rate, bool(self.s.agent.understand_code_mixed)) as stt:
                tasks += [asyncio.create_task(self._pump_audio(stt)), asyncio.create_task(self._consume_stt(stt)),
                          asyncio.create_task(self._watchdog())]
                if self.replier is llm.reply_sentences:
                    tasks.append(asyncio.create_task(asyncio.to_thread(llm.warm_up)))
                await self.speak(llm.disclosure(self.s.agent, self.s.variables))
                self.last_heard = time.monotonic()
                await self.ended.wait()
        except Exception as e:
            logger.error(f"Call {self.call_id} failed: {e}")
            self.failure = str(e)[:300]
            await self.t.event({"type": "error", "code": "engine", "message": "The voice engine had a problem."})
            self.ended.set()
        finally:
            for task in tasks + ([self.reply_task] if self.reply_task else []):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.tts_stream:
                await self.tts_stream.close()
            await self._finish()
        return self.call_id

    async def _leave_voicemail(self) -> Optional[str]:
        """An answering machine picked up (after the beep): say the message, then hang up."""
        playout = asyncio.create_task(self._playout()) if self.ambience else None
        drain = asyncio.create_task(self._drain_caller())
        try:
            await self.speak(llm.voicemail_text(self.s.agent, self.s.variables))
            await self.end()
        finally:
            for task in (playout, drain):
                if task:
                    task.cancel()
            if self.tts_stream:
                await self.tts_stream.close()
            await self._finish()
        return self.call_id

    async def _drain_caller(self) -> None:
        while not self.ended.is_set():
            if await self.t.receive() is None:
                self.ended.set()
                return

    async def _finish(self) -> None:
        exact = time.monotonic() - self.started  # bill on exact time: any connected call is at least a minute
        duration = round(exact)
        heard_secs = self.caller_bytes / 2 / self.rate
        logger.info(f"Call {self.call_id} diagnostics: {heard_secs:.1f}s of caller audio, peak level "
                    f"{self.caller_peak}/32767, recogniser events {self.stt_events}")
        outcome, summary, fields = "answered", "", {}
        successful, sentiment = None, None
        if self.s.voicemail:
            outcome, summary = "voicemail", "Reached voicemail and left a message."
        elif self.failure and not self.caller_spoke:
            outcome, summary = "failed", self.failure
        elif self.opted_out:
            outcome, summary = "opted_out", "Caller asked not to be contacted again. Added to the do-not-call list."
        else:
            result = await self.summarizer(self.s.bot, self.transcript, self.s.agent) if self.caller_spoke else {}
            summary, fields = result.get("summary", ""), result.get("fields", {})
            successful, sentiment = result.get("successful"), result.get("sentiment")
            contact = extract_contact(fields)
            if self.transferred:
                outcome = "transferred"
            elif not self.caller_spoke:
                outcome = "no_answer" if self.s.direction == "outbound" else "answered"
                summary = ("The caller didn't say anything the assistant could hear."
                           if self.caller_peak > 300 else "No sound came through from the caller's side.")
            elif fields and (contact.get("phone") or contact.get("email") or (self.s.caller_e164 and contact.get("name"))):
                outcome = "lead_captured"

        rec_path = None
        if self.s.record and self.caller_spoke:
            try:
                rec_path = await recording.save(self.call_id, await asyncio.to_thread(self.recorder.to_wav))
            except Exception as e:
                logger.warning(f"Saving recording failed: {e}")

        async with async_session() as db:
            billed = await metering.charge(db, self.s.owner_id, exact) if not self.failure or self.caller_spoke else 0
            log = (await db.execute(select(CallLog).where(CallLog.id == self.call_id))).scalars().first()
            log.ended_at = datetime.utcnow()
            log.duration_sec = duration
            log.billed_minutes = billed
            log.outcome = outcome
            log.summary = summary
            log.captured = fields
            log.successful = successful
            log.sentiment = sentiment
            log.transcript = self.transcript
            log.recording_path = rec_path
            if self.s.callback_job_id:
                job = (await db.execute(select(CallbackJob).where(CallbackJob.id == self.s.callback_job_id))).scalars().first()
                if job:
                    job.call_id = self.call_id
                    job.status = "done"  # the call connected; nothing left to retry
                    if not self.caller_spoke:
                        job.last_error = "Answered, but the caller didn't say anything"
            if self.s.channel == "browser":
                agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == self.s.bot.bot_id))).scalars().first()
                if agent:
                    agent.tested_at = datetime.utcnow()
            await db.commit()

        await self.t.event({"type": "ended", "call_id": self.call_id, "outcome": outcome, "summary": summary})
        fire_and_forget(call_completed(self.call_id))
