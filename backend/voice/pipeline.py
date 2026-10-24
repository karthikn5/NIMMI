"""
One live call, from greeting to post-call summary.

Transport-agnostic: the browser test panel and Exotel phone calls both plug in
a Transport. Speech services are injectable so the session can be tested
without network access.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from array import array
from collections import OrderedDict
from contextlib import aclosing
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
STT_BATCH_SEC = 0.1  # phone audio arrives in 20 ms frames; the recognizer ends turns ~0.3 s sooner fed 100 ms at a time
# The opening's audio starts within a second normally (a few over REST). Nothing for this long means
# the voice service isn't answering: the call is ended rather than left silent.
OPENING_STALL_SEC = 10.0
# Opening audio, kept so a call starts talking the moment it connects instead of ~0.75 s later: the opening
# is the same sentence on every call, and an outbound call's is made while the phone rings. In memory, and in
# files shared by the server's processes (a call can reach any of them).
OPENINGS_DIR = os.getenv("VOICE_OPENINGS_DIR") or os.path.join(tempfile.gettempdir(), "nimmi-openings")
OPENINGS_KEPT = 200
OPENING_PIECE_SEC = 0.25  # a kept opening goes out in pieces this long
_OPENINGS: "OrderedDict[str, bytes]" = OrderedDict()
# Unicode blocks of the scripts our languages are written in (Hindi and Marathi share Devanagari).
SCRIPTS = {
    "hi-IN": (0x0900, 0x097F), "mr-IN": (0x0900, 0x097F), "bn-IN": (0x0980, 0x09FF), "pa-IN": (0x0A00, 0x0A7F),
    "gu-IN": (0x0A80, 0x0AFF), "od-IN": (0x0B00, 0x0B7F), "ta-IN": (0x0B80, 0x0BFF), "te-IN": (0x0C00, 0x0C7F),
    "kn-IN": (0x0C80, 0x0CFF), "ml-IN": (0x0D00, 0x0D7F),
}


def written_language(text: str, hint: Optional[str] = None) -> Optional[str]:
    """The Indian language whose script `text` is mostly written in, or None for English. Devanagari is
    Hindi unless `hint` says Marathi. Tanglish and Hinglish keep English words in Latin letters, hence 35%."""
    letters = [c for c in text or "" if c.isalpha()]
    for code, (lo, hi) in SCRIPTS.items():
        if letters and sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= 0.35:
            return hint if lo == 0x0900 and hint in ("hi-IN", "mr-IN") else code
    return None


def spoken_language(text: str, reported: Optional[str]) -> Optional[str]:
    """The language a caller clearly switched to, or None when it's too short or unclear to act on
    ("Okay", "Hmm", one word). The script the recognizer wrote decides (its reported language can be
    off, and is always the configured one when it isn't detecting); the report only confirms English."""
    letters = [c for c in text or "" if c.isalpha()]
    words = len((text or "").split())
    if len(letters) < 4 or words < 2:
        return None
    written = written_language(text, reported)
    if written:
        return written
    if reported is None or reported.startswith("en"):
        latin = sum(c.isascii() for c in letters) / len(letters)
        return "en-IN" if latin >= 0.9 and words >= 3 else None
    return None

# What people say when they pick up (or over the greeting); not a question for the assistant.
HELLO_WORDS = {
    "hello", "helo", "halo", "hallo", "allo", "hi", "hey", "hai", "yes", "yeah", "yep", "ya", "haan", "han", "ha", "ji",
    "haan ji", "ok", "okay", "speaking", "who", "is", "this", "it", "sir", "madam", "ma'am", "mam", "vanakkam",
    "namaste", "namaskar", "namaskaram", "sollunga", "bolo", "boliye", "bolie", "hm", "hmm", "ஹலோ", "வணக்கம்",
    "சொல்லுங்க", "हेलो", "हैलो", "हाँ", "हां", "जी", "नमस्ते", "బోలో", "హలో", "ಹಲೋ", "ഹലോ",
}


_DIGIT_RUN = re.compile(r"\+?\d[\d\s-]{5,}\d")


def number_check(text: str) -> str:
    """A private note for the model when a phone number came through with the wrong number of digits
    (phone lines and recognizers drop or double a digit now and then); empty when it looks right."""
    for run in _DIGIT_RUN.findall(text or ""):
        digits = re.sub(r"\D", "", run)
        if 7 <= len(digits) <= 13 and len(digits) not in (10, 12):
            return (f" [Note for the assistant, not said by the caller: the number heard, {digits}, has {len(digits)} digits;"
                    " an Indian mobile number has 10. Say you may have missed a digit and ask them to repeat it slowly.]")
    return ""


def spoken(agent: VoiceAgent, text: str) -> str:
    """Apply the agent's pronunciation guide (spoken audio only; the transcript keeps the spelling)."""
    for rule in agent.pronunciations or []:
        word, say = (rule.get("word") or "").strip(), (rule.get("say") or "").strip()
        if word and say:
            text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", say, text, flags=re.IGNORECASE)
    return text


def opening_for(agent: VoiceAgent, variables: Optional[dict], recorded: bool, rate: int) -> tuple[str, str, str, str]:
    """A call's opening: its text, the words spoken (pronunciations applied), their language, and the key its
    audio is kept under. The same for the call and for anything preparing it ahead."""
    text = llm.disclosure(agent, variables, recorded=recorded)
    words = spoken(agent, text)
    lang = written_language(words, agent.language or "en-IN") or agent.language or "en-IN"
    raw = json.dumps([words, lang, agent.voice_id or "priya", agent.speaking_rate or 1.0, rate, sarvam.TTS_MODEL],
                     ensure_ascii=False)
    return text, words, lang, hashlib.sha256(raw.encode()).hexdigest()[:32]


def _kept_opening(key: str) -> Optional[bytes]:
    pcm = _OPENINGS.get(key)
    if pcm is None:
        path = os.path.join(OPENINGS_DIR, f"{key}.pcm")
        try:
            with open(path, "rb") as f:
                pcm = f.read()
            os.utime(path)  # recently used: pruned last
        except OSError:
            return None
        _OPENINGS[key] = pcm
    _OPENINGS.move_to_end(key)
    while len(_OPENINGS) > OPENINGS_KEPT:
        _OPENINGS.popitem(last=False)
    return pcm


def _keep_opening(key: str, pcm: bytes) -> None:
    _OPENINGS[key] = pcm
    while len(_OPENINGS) > OPENINGS_KEPT:
        _OPENINGS.popitem(last=False)
    try:
        os.makedirs(OPENINGS_DIR, exist_ok=True)
        part = os.path.join(OPENINGS_DIR, f"{key}.{os.getpid()}.part")
        with open(part, "wb") as f:
            f.write(pcm)
        os.replace(part, os.path.join(OPENINGS_DIR, f"{key}.pcm"))  # whole files only, for the other processes
        files = sorted((os.path.join(OPENINGS_DIR, n) for n in os.listdir(OPENINGS_DIR)), key=os.path.getmtime)
        for old in files[:-OPENINGS_KEPT]:  # personalised openings ("Hi Ravi, ...") are used once
            os.remove(old)
    except OSError as e:
        logger.debug(f"Couldn't keep the opening on disk: {e}")


def prepare_opening(agent: VoiceAgent, variables: Optional[dict], recorded: bool, rate: int = 8000) -> None:
    """Make a call's opening audio before the call connects (while the phone rings, or when the agent is saved
    for calls coming in), so it starts talking at once. Returns straight away; best effort."""
    if not sarvam.configured():
        return
    _, words, lang, key = opening_for(agent, variables, recorded, rate)
    if _kept_opening(key) is None:
        fire_and_forget(_make_opening(key, words, lang, agent.voice_id or "priya", agent.speaking_rate or 1.0, rate))


async def _make_opening(key: str, words: str, lang: str, voice: str, pace: float, rate: int) -> None:
    try:
        _keep_opening(key, await sarvam.synthesize(words, lang, voice, pace, rate))
    except Exception as e:
        logger.warning(f"Preparing an opening ahead of the call failed (the call will make it): {e}")


def _just_hello(text: str) -> bool:
    words = _normalize(text).split()
    return 0 < len(words) <= 4 and all(w.strip("'") in HELLO_WORDS for w in words)


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
        # The voice for a language the caller just switched to, connecting while the answer is written.
        self.next_stream: Optional[sarvam.TtsStream] = None
        self.next_stream_ready: Optional[asyncio.Task] = None
        self.spare_voices: list[tuple[sarvam.TtsStream, Optional[asyncio.Task]]] = []  # closed when the call ends
        self.replier = replier or llm.reply_sentences
        self.summarizer = summarizer or llm.summarize
        self.recorder = recording.Recorder(self.rate)

        self.call_id: Optional[str] = None
        self.started = time.monotonic()
        self.transcript: list[dict] = []
        self.history: list[dict] = []
        self.speaking_until = 0.0
        self.last_heard = time.monotonic()
        self.caller_talking_since: Optional[float] = None  # between the recognizer's speech start and end
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
        # The opening: replies wait for it, and it can't be cut off by a "hello" over it.
        self.greeted = asyncio.Event()
        self.greeting_until = 0.0
        self.speech_ended_at: Optional[float] = None  # when the caller last stopped talking (turn timings)
        self.speech_began_at = 0.0                    # when the latest sentence's first audio went out
        self.tts_cut_short = False                    # the latest sentence's audio stopped part way
        self.opening: Optional[asyncio.Queue] = None  # greeting audio, generated while the call is set up
        self.opening_task: Optional[asyncio.Task] = None
        self.opening_error: Optional[str] = None
        self.opening_kept = False  # its audio was ready before the call connected
        # The language the agent speaks: the agent's own, or the caller's once they clearly speak another.
        self.lang = setup.agent.language or "en-IN"
        self.follow_language = setup.agent.follow_caller_language is not False
        self.knowledge_task: Optional[asyncio.Task] = None
        self.stt_batch = int(self.rate * STT_BATCH_SEC) * 2 if self.rate == 8000 else 0  # phone lines only
        # One sentence at a time is turned into speech: they share one connection, and an interrupted
        # sentence must be cleared off it before the next one (a goodbye, a reminder) starts.
        self.voice = asyncio.Lock()

    # ── helpers ────────────────────────────────────────────────
    def _elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    def _log(self, speaker: str, text: str) -> None:
        self.transcript.append({"at_sec": self._elapsed(), "speaker": speaker, "text": text})

    @property
    def speaking(self) -> bool:
        return time.monotonic() < self.speaking_until

    async def _tts_chunks(self, text: str):
        """Audio for `text`, streamed when possible (first audio ~0.4 s), else in one piece over REST.
        Callers hold `self.voice`."""
        agent = self.s.agent
        lang = written_language(text, self.lang) or self.lang  # the voice must match the script it reads
        args = (text, lang, agent.voice_id or "priya", agent.speaking_rate or 1.0, self.rate)
        self.tts_cut_short = False
        if self.tts is not None:  # injected (tests)
            yield await self.tts(*args)
            return
        yielded = False
        try:
            if self.tts_stream is not None and self.tts_stream.language != lang:
                await self.tts_stream.close()  # the caller switched language
                self.tts_stream = None
            if self.tts_stream is None and self.next_stream is not None and self.next_stream.language == lang:
                self.tts_stream, self.next_stream = self.next_stream, None
                ready, self.next_stream_ready = self.next_stream_ready, None
                try:
                    if ready is not None:
                        await ready  # usually connected already, while the answer was written
                except Exception:
                    pass  # speak() connects it
            if self.tts_stream is None:
                self.tts_stream = sarvam.TtsStream(lang, args[2], args[3], self.rate)
            async with aclosing(self.tts_stream.speak(text)) as chunks:  # closed at once if cut short
                async for chunk in chunks:
                    yielded = True
                    yield chunk
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if yielded:  # part of the sentence was already heard: don't start it again
                logger.warning(f"Streaming TTS stopped part way ({e})")
                self.tts_cut_short = True
                return
            logger.warning(f"Streaming TTS failed ({e}); using REST")
            yield await sarvam.synthesize(*args)

    def _for_speech(self, text: str) -> str:
        return spoken(self.s.agent, text)

    async def speak(self, text: str) -> None:
        if not text or self.ended.is_set():
            return
        failed: Optional[Exception] = None
        async with self.voice:
            if self.ended.is_set():
                return
            self._log("agent", text)
            await self.t.event({"type": "agent", "text": text})
            try:
                first = True
                async with aclosing(self._tts_chunks(self._for_speech(text))) as chunks:
                    async for pcm in chunks:
                        if self.ended.is_set() or not pcm:
                            return
                        if first:
                            self.speech_began_at, first = time.monotonic(), False
                        await self._emit(pcm)
            except Exception as e:  # streaming and REST speech both failed
                failed = e
        if failed is not None:
            await self._voice_failed(f"speech failed ({failed})")

    async def _emit(self, pcm: bytes) -> None:
        self.recorder.add_agent(pcm)
        if self.ambience:
            self.out_buf.extend(pcm)  # the playout loop sends it, mixed with the background
        else:
            await self.t.play(pcm)
        now = time.monotonic()
        self.speaking_until = max(now, self.speaking_until) + len(pcm) / 2 / self.rate

    def _lang(self) -> str:
        return self.lang

    def _switch_language(self, language: str) -> None:
        """Speak the caller's language from now on: replies, the voice, and the fixed phrases. A sentence
        already being spoken (the opening, say) finishes as it is; the next one uses the new voice."""
        if language == self.lang or language not in llm.LANGUAGE_NAMES:
            return
        logger.info(f"Call {self.call_id}: caller switched to {language}")
        self.lang = language
        self._log("system", f"Switched to {llm.LANGUAGE_NAMES[language]}")
        if self.tts is None:  # connect the voice for it now, while the answer is being written (~0.6 s saved)
            if self.next_stream is not None:  # switched again before that voice was used
                if self.next_stream_ready is not None:
                    self.next_stream_ready.cancel()
                self.spare_voices.append((self.next_stream, self.next_stream_ready))
            agent = self.s.agent
            self.next_stream = sarvam.TtsStream(language, agent.voice_id or "priya", agent.speaking_rate or 1.0, self.rate)
            self.next_stream_ready = asyncio.create_task(self.next_stream.open())

    async def _close_voices(self) -> None:
        voices = [*self.spare_voices, (self.next_stream, self.next_stream_ready), (self.tts_stream, None)]
        for stream, ready in voices:
            if ready is not None:
                ready.cancel()  # before closing, so a connection can't open after the close
                await asyncio.gather(ready, return_exceptions=True)
            if stream is not None:
                await stream.close()

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

    async def _voice_failed(self, detail: str) -> None:
        """The speech service failed (down, unreachable, out of credits). End the call now rather than leave
        the caller in silence; it's logged as failed, and not billed unless the caller was helped."""
        logger.error(f"Call {self.call_id}: {detail}; ending the call")
        if not self.failure:
            self.failure = "The voice service was unavailable, so the call was ended."
            await self.t.event({"type": "error", "code": "speech",
                                "message": "The voice service isn't available right now. Please try again in a few minutes."})
        await self.end()

    async def _hush(self) -> None:
        """Stop talking now: drop the audio still queued for the caller."""
        self.speaking_until = time.monotonic()
        self.out_buf.clear()
        self.recorder.cut_agent()
        await self.t.clear()

    # ── events ────────────────────────────────────────────────
    async def on_speech_start(self) -> None:
        self.last_heard = time.monotonic()
        self.caller_talking_since = self.last_heard
        if time.monotonic() < self.greeting_until:
            return  # the opening (who we are, recorded line) always plays in full; it's a few seconds
        if self.speaking and self.s.agent.allow_interruptions:
            if self.reply_task and not self.reply_task.done():
                self.reply_task.cancel()
            await self._hush()

    async def on_caller_text(self, text: str, language: Optional[str] = None) -> None:
        self.caller_spoke = True
        self.last_heard = time.monotonic()
        self.silence_prompts = 0
        self._log("caller", text)
        await self.t.event({"type": "caller", "text": text})
        opening = not self.greeted.is_set() or time.monotonic() < self.greeting_until + 0.5
        if self.follow_language:
            switched = spoken_language(text, language)
            if switched:
                self._switch_language(switched)
        if opening and _just_hello(text):
            return  # "Hello?" as they pick up, or over the greeting: the greeting is the answer

        opt_out = _matches(text, self.s.opt_out_phrases)
        if opt_out or _matches(text, self.s.agent.end_call_phrases or []):
            # A pending answer to their last sentence must not play after the goodbye, nor the goodbye over the opening.
            if self.reply_task and not self.reply_task.done():
                self.reply_task.cancel()
            await self.greeted.wait()
            if opt_out:
                self.opted_out = True
                await self._add_to_dnc()
            await self.speak(self._opt_out_reply() if opt_out else self._goodbye())
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
        began, written = time.monotonic(), None
        try:
            knowledge = None
            if self.knowledge_task is not None:
                try:
                    knowledge = await asyncio.wait_for(asyncio.shield(self.knowledge_task), 3)
                except Exception:
                    knowledge = None
            extra = {"knowledge": knowledge} if knowledge is not None else {}
            # aclosing: an interrupted answer stops the model at once (it would otherwise keep writing,
            # and using up the per-minute allowance, until it finished).
            async with aclosing(self.replier(self.s.bot, self.s.agent, self.history[:-1], text + number_check(text),
                                             self.s.direction, self.s.consent_source,
                                             variables=self.s.variables, purpose=self.s.purpose,
                                             after_hours=self.s.after_hours, reply_language=self.lang, **extra)) as replies:
                async for sentence, control in replies:
                    if sentence:
                        said.append(sentence)
                        self.turn_spoken = True
                        written = written or time.monotonic()
                        await self.greeted.wait()  # never over the opening (the answer itself is already being written)
                        await self.speak(sentence)
                        if len(said) == 1:
                            self._log_timing(began, written)
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

    def _log_timing(self, began: float, written: float) -> None:
        """One line per answer: where the time between the caller stopping and the reply went."""
        stopped = self.speech_ended_at if self.speech_ended_at and self.speech_ended_at <= began else began
        if self.speech_began_at >= written:
            logger.info(f"Call {self.call_id} reply timing: transcript {began - stopped:.2f}s, answer text "
                        f"{written - began:.2f}s, first audio {self.speech_began_at - written:.2f}s "
                        f"({self.speech_began_at - stopped:.2f}s after they stopped)")

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
        pending = bytearray()
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
            if not self.stt_batch:
                await stt.send(pcm)
                continue
            pending.extend(pcm)
            if len(pending) >= self.stt_batch:
                await stt.send(bytes(pending))
                pending.clear()

    async def _consume_stt(self, stt) -> None:
        async for ev in stt.events():
            if ev.kind in self.stt_events:
                self.stt_events[ev.kind] += 1
            if ev.kind == "speech_start":
                await self.on_speech_start()
            elif ev.kind == "speech_end":
                self.caller_talking_since = None
                self.last_heard = self.speech_ended_at = time.monotonic()
            elif ev.kind == "transcript":
                await self.on_caller_text(ev.text, getattr(ev, "language", None))
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
                if self.reply_task and not self.reply_task.done():
                    self.reply_task.cancel()  # the time-limit notice replaces whatever was being said
                await self.speak(self._timeout_reply())
                await self.end()
                return
            # Not before the opening has played: it isn't silence.
            busy = (not self.greeted.is_set() or self.speaking
                    or (self.reply_task is not None and not self.reply_task.done()))
            # Someone talking for a long while (spelling an address, explaining a problem) isn't silence.
            talking = self.caller_talking_since is not None and time.monotonic() - self.caller_talking_since < 60
            if busy or talking:
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
    def _prepare_opening(self) -> None:
        """Get the greeting's audio ready to play the moment the call connects: made ahead of the call, or kept
        from an earlier one, when possible; else generated now into a queue as it arrives (~0.75 s)."""
        text, words, _, key = opening_for(self.s.agent, self.s.variables, self.s.record, self.rate)
        queue: asyncio.Queue = asyncio.Queue()
        self.opening, self.opening_text = queue, text
        kept = _kept_opening(key) if self.tts is None else None  # real speech only; tests inject their own
        if kept is not None:
            self.opening_kept = True
            piece = int(self.rate * OPENING_PIECE_SEC) * 2
            for i in range(0, len(kept), piece):
                queue.put_nowait(kept[i:i + piece])
            queue.put_nowait(None)
            return

        async def produce():
            audio: list[bytes] = []
            try:
                async with self.voice, aclosing(self._tts_chunks(words)) as chunks:
                    async for pcm in chunks:
                        audio.append(pcm)
                        await queue.put(pcm)
                    complete = not self.tts_cut_short
                if self.tts is None and audio and complete:
                    _keep_opening(key, b"".join(audio))
            except Exception as e:
                logger.warning(f"Preparing the greeting failed: {e}")
                self.opening_error = str(e)[:200]
            finally:
                await queue.put(None)
        self.opening_task = asyncio.create_task(produce())

    async def _greet(self) -> None:
        """The opening. Protected from barge-in while it plays; replies wait for it."""
        self.greeting_until = float("inf")
        spoke = False
        try:
            if self.opening is None:
                self._prepare_opening()
            self._log("agent", self.opening_text)
            await self.t.event({"type": "agent", "text": self.opening_text})
            while (pcm := await asyncio.wait_for(self.opening.get(), OPENING_STALL_SEC)) is not None:
                if self.ended.is_set():
                    break
                if pcm:
                    if not spoke:
                        logger.info(f"Call {self.s.provider_call_id or self.call_id}: opening started "
                                    f"{time.monotonic() - self.started:.2f}s after the call connected "
                                    f"({'made ahead' if self.opening_kept else 'made now'})")
                    spoke = True
                    await self._emit(pcm)
        except asyncio.TimeoutError:
            self.opening_error = self.opening_error or f"no audio for {OPENING_STALL_SEC:.0f} s"
            if self.opening_task:
                self.opening_task.cancel()  # a stalled opening must not keep the voice from the replies
        finally:
            self.greeting_until = self.speaking_until
            self.last_heard = time.monotonic()
            self.greeted.set()
        if not spoke and self.opening_error:
            await self._voice_failed(f"the opening couldn't be spoken ({self.opening_error})")

    async def _has_minutes(self) -> bool:
        async with async_session() as db:
            return metering.minutes_left(await metering.get_wallet(db, self.s.owner_id)) > 0

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

    async def _load_ambience(self) -> None:
        kind = self.s.agent.ambience or "none"
        if kind != "none" and kind in ambience.KINDS:
            try:
                await asyncio.to_thread(ambience.loop, kind, self.rate)  # cached after the first call
                self.ambience = ambience.AmbiencePlayer(kind, self.s.agent.ambience_volume or "medium", self.rate)
            except Exception as e:
                logger.warning(f"Background sound unavailable: {e}")

    async def _out_of_minutes(self, greeting: Optional[asyncio.Task], tasks: list[asyncio.Task]) -> Optional[str]:
        """The owner has no voice minutes left: stop the opening, say so, and end."""
        stopping = [t for t in (greeting, self.opening_task) if t]
        for task in stopping:
            task.cancel()
        await asyncio.gather(*stopping, return_exceptions=True)
        await self._hush()
        self.failure = "No voice minutes left"
        await self.t.event({"type": "error", "code": "no_minutes", "message": "You're out of voice minutes."})
        await self.speak(self._no_minutes_reply())
        await self.end()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._close_voices()
        await self._finish()
        return self.call_id

    async def run(self) -> Optional[str]:
        await self._load_ambience()
        tasks: list[asyncio.Task] = []
        greeting: Optional[asyncio.Task] = None
        if not self.s.voicemail:
            if self.ambience:
                tasks.append(asyncio.create_task(self._playout()))
            # Speak first, the moment the call connects, rather than leave the person who answered saying
            # "hello?" into silence (a hello over the opening is ignored). The call log, the minutes check,
            # the AI and the recognizer get ready while it plays.
            self._prepare_opening()
            greeting = asyncio.create_task(self._greet())
        try:
            _, has_minutes = await asyncio.gather(self._open_log(), self._has_minutes())
        except BaseException:
            for task in (greeting, self.opening_task, *tasks):
                if task:
                    task.cancel()
            raise
        if not has_minutes:
            return await self._out_of_minutes(greeting, tasks)
        if self.s.voicemail:
            return await self._leave_voicemail()

        if self.replier is llm.reply_sentences:
            tasks.append(asyncio.create_task(asyncio.to_thread(llm.warm_up)))
            self.knowledge_task = asyncio.create_task(llm.call_knowledge(self.s.bot))  # once, for the whole call
        # Following the caller's language: let the recognizer detect it ("unknown") instead of assuming ours.
        listen_in = "unknown" if self.follow_language else self.s.agent.language
        stt_cm = self.stt_factory(listen_in, self.rate, bool(self.s.agent.understand_code_mixed))
        stt = None
        try:
            stt = await stt_cm.__aenter__()
            essential = [asyncio.create_task(self._pump_audio(stt)), asyncio.create_task(self._consume_stt(stt)),
                         asyncio.create_task(self._watchdog())]
            tasks += essential
            await self._until_ended(essential)
        except Exception as e:
            logger.error(f"Call {self.call_id} failed: {e}")
            self.failure = str(e)[:300]
            await self.t.event({"type": "error", "code": "engine", "message": "The voice engine had a problem."})
            self.ended.set()
        finally:
            extra = [t for t in (greeting, self.reply_task, self.knowledge_task, self.opening_task) if t]
            for task in tasks + extra:
                task.cancel()
            await asyncio.gather(*tasks, *extra, return_exceptions=True)
            if stt is not None:
                try:
                    await stt_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            await self._close_voices()
            await self._finish()
        return self.call_id

    async def _until_ended(self, essential: list[asyncio.Task]) -> None:
        """Wait for the call to end. The audio pump, the recognizer and the watchdog run for the whole call;
        if one stops early (the speech service dropped its connection, say), the call is ended as failed.
        Otherwise nothing would be left to notice the caller hang up, and the call would never finish."""
        ended = asyncio.create_task(self.ended.wait())
        try:
            done, _ = await asyncio.wait([ended, *essential], return_when=asyncio.FIRST_COMPLETED)
        finally:
            ended.cancel()
        if not self.ended.is_set():
            stopped = next(t for t in done if t is not ended)
            error = None if stopped.cancelled() else stopped.exception()
            await self._voice_failed(f"{stopped.get_coro().__name__} stopped ({error or 'connection closed'})")

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
            await self._close_voices()
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
            log.language = self.lang  # where the conversation ended up
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
