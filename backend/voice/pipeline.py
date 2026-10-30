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
import math
import os
import re
import statistics
import tempfile
import time
from array import array
from collections import OrderedDict, deque
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncIterator, Awaitable, Callable, Optional, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy import update
from sqlalchemy.future import select

from database import async_session
from backend.models import Bot, CallbackJob, CallHandoff, CallLog, DncEntry, VoiceAgent
import assist
from notify.events import call_completed, fire_and_forget
from phone import extract_contact
from voice import ai_models, ambience, handoff, llm, memory, metering, recording, sarvam, schedule
from voice.levels import CallerLevels

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
    script: Optional[dict] = None                  # personality and instructions for this kind of call (Knowledge)
    caller: Optional[dict] = None                  # what the assistant remembers about them (voice/memory.py)
    number_id: Optional[str] = None                # our number on the call (call-backs go out from it)
    tools: Optional[schedule.CallTools] = None     # call-backs and meetings it can book (Voice > Schedule)


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

NO_CREDITS_REPLIES = {
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

# Said once when an answer is slow to come (a busy AI service), so the caller doesn't think the line went dead.
HOLD_PHRASES = {
    "en-IN": "One moment, please.",
    "ta-IN": "ஒரு நிமிஷம்ங்க.",
    "hi-IN": "जी, एक मिनट।",
    "te-IN": "ఒక్క నిమిషం అండి.",
    "kn-IN": "ಒಂದು ನಿಮಿಷ.",
    "ml-IN": "ഒരു നിമിഷം.",
    "mr-IN": "एक मिनिट.",
    "bn-IN": "এক মিনিট।",
    "gu-IN": "એક મિનિટ.",
    "pa-IN": "ਇੱਕ ਮਿੰਟ ਜੀ।",
    "od-IN": "ଗୋଟିଏ ମିନିଟ୍।",
}
HOLD_AFTER_SEC = float(os.getenv("VOICE_HOLD_AFTER_SEC", "3"))
# Said when the call can't go on (the speech recognizer keeps failing), instead of hanging up in silence.
TROUBLE_REPLIES = {
    "en-IN": "Sorry, I'm having trouble hearing you on this line, so I'll end the call here. Please try again in a few minutes.",
    "ta-IN": "மன்னிக்கவும், இந்த லைனில் உங்கள் குரல் சரியாக கேட்கவில்லை. சில நிமிடங்களில் மீண்டும் முயற்சிக்கவும்.",
    "hi-IN": "माफ़ कीजिए, इस लाइन पर आपकी आवाज़ ठीक से नहीं आ रही है। कृपया कुछ मिनट बाद फिर से कोशिश करें।",
}
# The speech recognizer's connection can drop mid-call (a network blip, or the service closing it). Listening goes
# on over a fresh connection; more drops than this within the window, or no connection at all, end the call.
STT_RETRIES = 3
STT_RETRY_WINDOW_SEC = 60.0
# An answer that hasn't started by now isn't coming (every AI service failed or stalled): the caller is asked to
# say it again, rather than left in silence.
REPLY_GIVE_UP_SEC = float(os.getenv("VOICE_REPLY_GIVE_UP_SEC", "15"))
# A call the credits run out on ends this long before, so the time-limit goodbye is paid for too.
GOODBYE_SEC = 6.0
# The recognizer signals speech after a few hundredths of a second of sound, so stopping on that signal let a
# cough, a click on the line or a quick "mm" cut the agent off mid-sentence, often with nothing to answer after.
# The agent stops for the caller once they've kept talking this long (a short sound ends sooner), or as soon as
# words that need an answer come through.
BARGE_IN_SEC = float(os.getenv("VOICE_BARGE_IN_SEC", "1.0"))
# The room around the caller (a TV, people nearby, traffic) is speech to the recognizer too; their own voice is much
# louder (voice/levels.py). For the turn the recognizer is hearing:
TURN_PRE_SEC = 0.6        # it signals speech ~0.3 s after the sound starts; a turn's audio begins this much earlier
END_FLUSH_SEC = 0.9       # the caller's voice gone this long, while it still hears speech (the room): finish the turn
ONSET_FLUSH_SEC = 1.5     # a turn that has been only the room this long is cut when the caller starts talking, so
                          # the room's words aren't glued to theirs
BARGE_IN_VOICE_SEC = 0.3  # of the caller's own voice, for talking over the agent to stop it
VOICE_GONE_SEC = 2.0      # it still hears speech, but their voice stopped this long ago: they aren't talking
# What people say while listening ("mm", "okay", "சரி", "हाँ जी"): no reason to stop the agent mid-answer.
BACKCHANNEL_WORDS = {
    "ok", "okay", "k", "hmm", "hm", "mm", "mmm", "mhm", "uh", "huh", "yes", "yeah", "yep", "ya", "right", "fine",
    "sure", "alright", "haan", "han", "ha", "ji", "achha", "acha", "accha", "theek", "thik", "hai", "sari", "seri",
    "saringa", "seringa", "aama", "aamam", "ama",
    "சரி", "சரிங்க", "ம்", "ம்ம்", "ம்ம்ம்", "ஆமா", "ஆமாம்", "ஆமாங்க", "ஓகே", "ஹ்ம்", "ஹ்ம்ம்",
    "हाँ", "हां", "जी", "अच्छा", "ठीक", "है", "ओके", "हम्म",
    "సరే", "అవును", "ಸರಿ", "ಹೌದು", "ശരി", "ഉം", "അതെ", "হ্যাঁ", "আচ্ছা", "હા", "ਹਾਂ", "ହଁ",
}
# Following the caller's language. One clear sentence switches at once; a short or uncertain one waits for a
# second in the same language, so one misheard line (Tamil speech written as "I think Katha calls") can't flip
# the call into another language.
SWITCH_WORDS = 3          # words in another Indian language
# A language not heard yet on the call needs more: a caller's first few words, unclear on the line, came out in
# Punjabi and Malayalam script on real calls (Oct 2026) and the agent switched to them.
FIRST_SWITCH_WORDS = 5
SWITCH_WORDS_ENGLISH = 5  # English needs more: garbled Indian-language speech often comes out as English words
LANGUAGE_SURE = 0.85      # the recognizer's own certainty that lets two words switch
LANGUAGE_UNSURE = 0.6     # below it, one English sentence doesn't switch

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


def switch_now(text: str, language: str, probability: Optional[float], first_time: bool = False) -> bool:
    """Whether one sentence in `language` is clear enough to change the call's language on its own.
    `probability` is the recognizer's certainty of that language, when it said. `first_time`: the language hasn't
    been spoken on this call yet, so a short sentence (maybe garbled noise) isn't enough."""
    words = len((text or "").split())
    if language == "en-IN":
        return words >= SWITCH_WORDS_ENGLISH and (probability is None or probability >= LANGUAGE_UNSURE)
    if first_time:
        return words >= FIRST_SWITCH_WORDS
    # Indian-language letters are strong evidence by themselves; the recognizer's certainty isn't (it said 0.58 for
    # a clear Tanglish sentence: the English words in it count against Tamil). It only lets two words switch.
    return words >= SWITCH_WORDS or (words >= 2 and probability is not None and probability >= LANGUAGE_SURE)


def _backchannel(text: str) -> bool:
    words = llm.plain_words(text)
    return 0 < len(words) <= 3 and all(w in BACKCHANNEL_WORDS for w in words)


# Sounds people make while they think or before they start ("so", "uh", "ஆ", "वो"). Answered on their own, they got
# "Could you please tell me what you need help with?" while the caller was still about to say it.
FILLER_WORDS = {
    "so", "uh", "uhh", "um", "umm", "uhm", "hmm", "hm", "er", "erm", "ah", "aah", "aa", "eh",
    "ஆ", "அ", "ஏ", "ஆங்", "வந்து", "அது", "अ", "आ", "उम", "उम्म", "वो", "मतलब", "हम्म",
}


def _just_filler(text: str) -> bool:
    words = llm.plain_words(text)
    return 0 < len(words) <= 3 and all(w in FILLER_WORDS for w in words)


def _echoes(text: str, said: str) -> bool:
    """The caller's line carried the agent's own voice back (a speakerphone): the "caller" said what the agent is saying."""
    heard, ours = llm.plain_words(text), set(llm.plain_words(said))
    return len(heard) >= 3 and sum(w in ours for w in heard) >= 0.7 * len(heard)

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
    """Lowercase, straight apostrophes, punctuation to spaces: "Okay, thank you. Bye." -> " okay thank you bye ".
    Tamil and Hindi words stay whole ("வணக்கம்" used to come out in pieces, so it never counted as a hello)."""
    return " " + " ".join(llm.plain_words(text)) + " "


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
        self.model = ai_models.call_model(setup.agent.ai_model)  # the agent's AI model, asked first
        self.answered: list[str] = []  # which model answered each turn (a busy or slow one hands over to a backup)
        self.reply_gaps: list[float] = []  # seconds from the caller stopping to the agent's first sound, per answer
        self.paid_seconds = math.inf  # how long the credits left pay for, worked out when the call starts
        self.follow_language = setup.agent.follow_caller_language is not False
        self.lang_pending: Optional[str] = None  # heard once, not clearly enough to switch yet
        self.spoken_languages = {self.lang}      # languages used on this call so far
        allowed = set(setup.agent.switch_languages or [])
        self.allowed_languages = (allowed | {self.lang}) if allowed else None  # the agent's choice; None = any
        self.stt = None                            # the recognizer connection in use; None while reconnecting
        self.stt_problem: Optional[str] = None     # why the current one is being replaced
        self.levels = CallerLevels(self.rate)
        # The turn the recognizer is hearing now (between its speech start and end), followed on our side.
        self.turn_began: Optional[float] = None
        self.turn_voice_at: Optional[float] = None  # the caller's own voice last heard in it
        self.turn_cut_at: Optional[float] = None    # cut there: only the room had been heard when the caller started
        self.turn_flushed = False
        self.voice_run = 0
        self.turn_window: Optional[tuple] = None    # the turn just finished: since, until, when it ended, was it cut
        self.background_ignored = 0
        self.flushes = 0
        self.barge_in: Optional[asyncio.Task] = None  # the caller started talking over the agent: stop if they go on
        self.recent_speech: deque = deque(maxlen=3)  # the agent's latest sentences (to recognize its own echo)
        self.asking = False  # the sentence being spoken is a question (a "yes" over it is the answer)
        self.knowledge_task: Optional[asyncio.Task] = None
        self.stt_batch = int(self.rate * STT_BATCH_SEC) * 2 if self.rate == 8000 else 0  # phone lines only
        # One sentence at a time is turned into speech: they share one connection, and an interrupted
        # sentence must be cleared off it before the next one (a goodbye, a reminder) starts.
        self.voice = asyncio.Lock()
        if setup.tools is not None:
            setup.tools.call_id = lambda: self.call_id  # what's booked on the call points back to it
        # A person from the team (voice/handoff.py): the hand-off asked for, and its watcher.
        self.handoff: Optional[str] = None
        self.handoff_task: Optional[asyncio.Task] = None
        self.handoff_asks = 0
        self.tools = handoff.Toolbox(setup.tools, handoff.HandoffTools(self))

    # ── helpers ────────────────────────────────────────────────
    def _elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    def _function_values(self) -> dict:
        """What the agent's functions can put in their {{placeholders}}: the call, the caller, and campaign columns."""
        first = (self.s.caller or {}).get("first_name") or ""
        return {**(self.s.variables or {}), "caller_number": self.s.caller_e164 or "", "call_id": self.call_id or "",
                "direction": self.s.direction, "name": (self.s.variables or {}).get("name") or first}

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
        # Connecting and the first audio, all told: past this, REST takes over rather than the caller waiting on.
        budget_end = time.monotonic() + sarvam.TTS_FIRST_AUDIO_SEC
        try:
            if self.tts_stream is not None and self.tts_stream.language != lang:
                await self.tts_stream.close()  # the caller switched language
                self.tts_stream = None
            if self.tts_stream is None and self.next_stream is not None and self.next_stream.language == lang:
                self.tts_stream, self.next_stream = self.next_stream, None
                ready, self.next_stream_ready = self.next_stream_ready, None
                try:
                    if ready is not None:  # usually connected already, while the answer was written
                        await asyncio.wait_for(ready, max(0.1, budget_end - time.monotonic()))
                except Exception:
                    pass  # speak() connects it, in what's left of the time
            if self.tts_stream is None:
                self.tts_stream = sarvam.TtsStream(lang, args[2], args[3], self.rate)
            first_audio_sec = max(0.5, budget_end - time.monotonic())
            async with aclosing(self.tts_stream.speak(text, first_audio_sec=first_audio_sec)) as chunks:  # closed at once if cut short
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

    async def speak(self, text: str, heard: Optional[list] = None) -> None:
        """Say `text`. `heard` collects it once its audio starts reaching the caller (an answer that's cut off
        before then wasn't heard, and isn't remembered as said)."""
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
                            self.recent_speech.append(text)
                            if heard is not None:
                                heard.append(text)
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
        self.spoken_languages.add(language)
        self._log("system", f"Switched to {llm.LANGUAGE_NAMES[language]}")
        if self.tts is None:  # connect the voice for it now, while the answer is being written (~0.6 s saved)
            if self.next_stream is not None:  # switched again before that voice was used
                if self.next_stream_ready is not None:
                    self.next_stream_ready.cancel()
                self.spare_voices.append((self.next_stream, self.next_stream_ready))
            agent = self.s.agent
            self.next_stream = sarvam.TtsStream(language, agent.voice_id or "priya", agent.speaking_rate or 1.0, self.rate)
            self.next_stream_ready = asyncio.create_task(self.next_stream.open())

    async def _keep_voices_warm(self) -> None:
        """Sarvam closes a speech connection after a minute without traffic; the next sentence then waited for a
        new one (or, when the close went unnoticed, for audio that never came). Ping them while the caller talks."""
        if self.tts is not None or self.voice.locked():
            return  # injected speech (tests), or a sentence is being spoken now, which is traffic
        for stream in (self.tts_stream, self.next_stream):
            if stream is not None and stream.connected and stream.idle_for() >= sarvam.TTS_KEEPALIVE_SEC:
                await stream.ping()

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

    def _no_credits_reply(self) -> str:
        return NO_CREDITS_REPLIES.get(self._lang(), NO_CREDITS_REPLIES["en-IN"])

    def _timeout_reply(self) -> str:
        return TIMEOUT_REPLIES.get(self._lang(), TIMEOUT_REPLIES["en-IN"])

    def _fallback_reply(self) -> str:
        return llm.FALLBACK_ERRORS.get(self._lang(), llm.FALLBACK_ERRORS["en-IN"])

    def _trouble_reply(self) -> str:
        return TROUBLE_REPLIES.get(self._lang(), TROUBLE_REPLIES["en-IN"])

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

    async def _voice_failed(self, detail: str, apologize: bool = False) -> None:
        """The speech service failed (down, unreachable, out of credits). End the call now rather than leave
        the caller in silence; it's logged as failed, and not billed unless the caller was helped. The reason
        goes in the transcript (it shows on the Calls page). `apologize`: the voice still works (it's the
        listening that failed), so the caller hears why the call is ending instead of it going quiet."""
        logger.error(f"Call {self.call_id}: {detail}; ending the call")
        if not self.failure:
            self.failure = "The voice service was unavailable, so the call was ended."
            self._log("system", f"Call ended early because of a technical problem: {detail}")
            await self.t.event({"type": "error", "code": "speech",
                                "message": "The voice service isn't available right now. Please try again in a few minutes."})
            if apologize:
                await self.speak(self._trouble_reply())
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
        if self.speaking and self.s.agent.allow_interruptions and self.barge_in is None:
            self.barge_in = asyncio.create_task(self._barge_in_after(BARGE_IN_SEC))

    async def _barge_in_after(self, delay: float) -> None:
        """Stop talking if the caller is still talking `delay` from now. A cough, a click on the line or a quick
        "mm" ends sooner (speech_end cancels this), and the agent carries on with its sentence."""
        try:
            await asyncio.sleep(delay)
            if self.barge_in is asyncio.current_task():
                self.barge_in = None  # decided: a speech_end arriving now mustn't stop it half done
            if self.caller_talking_since is not None and self.speaking:
                if self._room_only(time.monotonic()):
                    logger.info(f"Call {self.call_id}: sound over the agent, far quieter than the caller's voice; carrying on")
                    return
                logger.info(f"Call {self.call_id}: the caller kept talking over the agent; stopping to listen")
                if self.reply_task and not self.reply_task.done():
                    self.reply_task.cancel()
                await self._hush()
        finally:
            if self.barge_in is asyncio.current_task():
                self.barge_in = None

    def _cancel_barge_in(self) -> None:
        if self.barge_in is not None:
            self.barge_in.cancel()
            self.barge_in = None

    def _mid_answer(self) -> bool:
        """The agent is talking, or between the sentences of an answer it's giving."""
        return self.speaking or (self.reply_task is not None and not self.reply_task.done() and self.turn_spoken)

    async def on_caller_text(self, text: str, language: Optional[str] = None, probability: Optional[float] = None) -> None:
        mid_answer = self._mid_answer()
        # Not while it asks something: a caller repeating the number it's reading back is answering.
        if mid_answer and not self.asking and _echoes(text, " ".join(self.recent_speech)):
            logger.info(f"Call {self.call_id}: ignored the agent's own voice coming back on the line: {text[:80]!r}")
            return
        if _just_filler(text):
            logger.info(f"Call {self.call_id}: {text!r} on its own isn't something to answer; waiting for the rest")
            return
        self.caller_spoke = True
        self.last_heard = time.monotonic()
        self.silence_prompts = 0
        self._log("caller", text)
        await self.t.event({"type": "caller", "text": text})
        opening = not self.greeted.is_set() or time.monotonic() < self.greeting_until + 0.5
        if self.follow_language:
            self._follow(text, language, probability)
        if opening and _just_hello(text):
            return  # "Hello?" as they pick up, or over the greeting: the greeting is the answer
        # Stopping mid-answer for the caller never cuts into the opening.
        may_stop = mid_answer and self.s.agent.allow_interruptions and time.monotonic() >= self.greeting_until

        opt_out = _matches(text, self.s.opt_out_phrases)
        if opt_out or _matches(text, self.s.agent.end_call_phrases or []):
            # A pending answer to their last sentence must not play after the goodbye, nor the goodbye over the opening.
            if self.reply_task and not self.reply_task.done():
                self.reply_task.cancel()
            if may_stop:
                await self._hush()
            await self.greeted.wait()
            if opt_out:
                self.opted_out = True
                await self._add_to_dnc()
            await self.speak(self._opt_out_reply() if opt_out else self._goodbye())
            await self.end()
            return

        if mid_answer and not self.asking and _backchannel(text):
            return  # "mm", "okay" while the agent talks: they're listening, not asking for anything
        if may_stop:
            self._cancel_barge_in()
            await self._hush()  # words that need an answer: stop talking and answer them

        if self.reply_task and not self.reply_task.done():
            self.reply_task.cancel()
            if not self.turn_spoken and self.history and self.history[-1]["role"] == "user":
                # The caller was still going (the recognizer split one sentence):
                # answer the whole thing, not the fragments.
                text = f"{self.history.pop()['content']} {text}"
        self.reply_task = asyncio.create_task(self._reply(text))

    def _follow(self, text: str, reported: Optional[str], probability: Optional[float]) -> None:
        """Change to the caller's language once it's clear they speak it (switch_now), or once a second sentence
        in it confirms a first one that wasn't clear enough on its own."""
        heard = spoken_language(text, reported)
        if heard is None:
            return  # too short or unclear to say either way
        if heard == self.lang:
            self.lang_pending = None
            return
        if self.allowed_languages is not None and heard not in self.allowed_languages:
            self.lang_pending = None
            logger.info(f"Call {self.call_id}: that sounded like {heard}, which this agent doesn't switch to")
            return
        sure = probability if reported == heard else None  # the recognizer's certainty is about what it reported
        if switch_now(text, heard, sure, heard not in self.spoken_languages) or self.lang_pending == heard:
            self.lang_pending = None
            self._switch_language(heard)
        else:
            self.lang_pending = heard
            logger.info(f"Call {self.call_id}: that sounded like {heard} ({probability}); switching if the next sentence is too")

    async def _reply(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        self.turn_spoken = False
        self.asking = False
        said: list[str] = []   # what the model wrote
        heard: list[str] = []  # what reached the caller: the conversation remembers this
        ran: list[dict] = []   # functions the model ran this turn, and their results (llm.reply_sentences)
        began, written = time.monotonic(), None
        holding: dict = {}
        hold = asyncio.create_task(self._hold_on(holding)) if HOLD_AFTER_SEC > 0 else None
        try:
            knowledge = None
            if self.knowledge_task is not None:
                try:
                    knowledge = await asyncio.wait_for(asyncio.shield(self.knowledge_task), 3)
                except Exception:
                    knowledge = None
            extra = {"knowledge": knowledge} if knowledge is not None else {}
            async with asyncio.timeout(REPLY_GIVE_UP_SEC) as limit:
                # aclosing: an interrupted answer stops the model at once (it would otherwise keep writing,
                # and using up the per-minute allowance, until it finished).
                async with aclosing(self.replier(self.s.bot, self.s.agent, self.history[:-1], text + number_check(text),
                                                 self.s.direction, self.s.consent_source,
                                                 variables=self.s.variables, purpose=self.s.purpose,
                                                 after_hours=self.s.after_hours, reply_language=self.lang,
                                                 script=self.s.script, caller=self.s.caller,
                                                 phone_known=bool(self.s.caller_e164), answered=self.answered,
                                                 function_values=self._function_values(), function_log=ran,
                                                 schedule_tools=self.tools, **extra)) as replies:
                    async for sentence, control in replies:
                        if sentence:
                            if not said:
                                limit.reschedule(None)  # it's answering: the rest takes as long as it takes
                                if hold is not None and not holding:
                                    hold.cancel()  # not needed after all
                            said.append(sentence)
                            self.turn_spoken = True
                            written = written or time.monotonic()
                            await self.greeted.wait()  # never over the opening (the answer itself is already being written)
                            self.asking = sentence.endswith("?")
                            await self.speak(sentence, heard=heard)
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
        except TimeoutError:
            logger.error(f"Call {self.call_id}: no answer {REPLY_GIVE_UP_SEC:.0f}s after the caller spoke; asking them to repeat")
            await self.speak(self._fallback_reply())
        except Exception as e:
            logger.error(f"Reply failed: {e}")
            await self.speak(self._fallback_reply())
        finally:
            if hold is not None:
                hold.cancel()
            if ran:  # before the spoken answer, which came from their results
                self.history.extend(ran)
                for entry in ran:
                    if entry["role"] == "tool":
                        self._log("system", f"Function {entry['name']}: {entry['content'][:300]}")
            if heard:
                self.history.append({"role": "assistant", "content": " ".join(heard)})
            if said and self.s.channel == "phone" and assist.is_unanswered(" ".join(said)):
                fire_and_forget(assist.record_gap(self.s.bot.bot_id, text, "voice", None))

    async def _hold_on(self, holding: dict) -> None:
        """The answer is slow (a busy AI service): say "one moment" once, instead of leaving the caller wondering
        whether the line went dead. Not part of the conversation the model sees."""
        await asyncio.sleep(HOLD_AFTER_SEC)
        await self.greeted.wait()
        holding["started"] = True
        logger.info(f"Call {self.call_id}: the answer is slow; saying one moment")
        await self.speak(HOLD_PHRASES.get(self._lang(), HOLD_PHRASES["en-IN"]))

    def _log_timing(self, began: float, written: float) -> None:
        """One line per answer: where the time between the caller stopping and the reply went."""
        stopped = self.speech_ended_at if self.speech_ended_at and self.speech_ended_at <= began else began
        if self.speech_began_at >= written:
            self.reply_gaps.append(self.speech_began_at - stopped)
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
            brief = None
            if (agent.transfer_mode or "cold") == "warm":
                # Whisper a short brief to the person before they're connected (Twilio).
                try:
                    brief = await asyncio.wait_for(llm.transfer_brief(self.s.bot, self.transcript, self.s.caller_e164), 4)
                except Exception:
                    brief = None
            # The provider asks next (Exotel Passthru / Twilio <Connect action>) whether and where to transfer, and
            # that request can reach any server process: the database says.
            async with async_session() as db:
                db.add(CallHandoff(owner_id=self.s.owner_id, bot_id=self.s.bot.bot_id, call_id=self.call_id,
                                   provider=getattr(self.t, "provider", None), provider_call_id=self.s.provider_call_id,
                                   caller=self.s.caller_e164, reason="The agent's transfer number", brief=brief,
                                   status="connecting", via="transfer", target=agent.transfer_number,
                                   accepted_at=handoff.now()))
                await db.commit()
        await self.end("transfer")

    # ── a person from the team (voice/handoff.py) ──────────────
    async def ask_for_person(self, reason: str) -> str:
        """The AI's ask_for_person: ring the team in the dashboard, else the agent's transfer number, else a call-back."""
        agent = self.s.agent
        if self.handoff:
            return "You've already asked the team; someone may join any moment. Keep helping the caller meanwhile."
        self.handoff_asks += 1
        if handoff.team_on(agent) and self.call_id and self.handoff_asks <= 2:
            async with async_session() as db:
                if await handoff.available(db, self.s.owner_id):
                    row = CallHandoff(owner_id=self.s.owner_id, bot_id=self.s.bot.bot_id, call_id=self.call_id,
                                      provider=getattr(self.t, "provider", None), provider_call_id=self.s.provider_call_id,
                                      caller=self.s.caller_e164, caller_name=(self.s.caller or {}).get("name") or None,
                                      reason=reason, brief=self._brief(), status="ringing",
                                      expires_at=handoff.now() + timedelta(seconds=handoff.wait_of(agent)))
                    db.add(row)
                    await db.commit()
                    self.handoff = row.id
        if self.handoff:
            self._log("system", f"Asked the team for a person: {reason}")
            fire_and_forget(handoff.announce(self.s.owner_id, self.handoff, "ringing"))
            self.handoff_task = asyncio.create_task(self._watch_handoff(self.handoff))
            return ("The team has been alerted and someone may join in a moment. Tell the caller, in one short sentence, "
                    "that you're getting someone from the team and ask them to stay on the line; then keep helping them. "
                    "Don't say they're connected: you'll be told.")
        if agent.transfer_enabled and agent.transfer_number and not self.s.after_hours:
            self.handoff_task = asyncio.create_task(self._transfer_after(self.reply_task))
            return ("Nobody from the team is in the dashboard, so the call goes to the team's phone now. Tell the caller, "
                    "in one short sentence, that you're connecting them, and nothing more.")
        self._log("system", f"Asked for a person ({reason}); nobody could join, so a call back is in Schedule")
        fire_and_forget(handoff.todo_for(self.s.owner_id, self.s.bot.bot_id, self.s.caller_e164, self.call_id, reason,
                                         (self.s.caller or {}).get("name")))
        opens = f" The office opens {self.s.after_hours}." if self.s.after_hours else ""
        return (f"Nobody from the team can join right now.{opens} Tell the caller that, and that someone will call them "
                "back; make sure you have their name and what it's about. (A to-do to call them back is in the team's "
                "Schedule.)")

    def _brief(self) -> str:
        """What the person picking up reads first: the caller's last words and the assistant's (the panel shows the
        whole transcript too)."""
        said = [f"{'Caller' if t['speaker'] == 'caller' else 'Assistant'}: {t['text']}"
                for t in self.transcript if t["speaker"] in ("caller", "agent")]
        return "\n".join(said[-6:])[:1500]

    async def _finish_speaking(self, stop_replying: bool) -> None:
        """Let the agent finish its sentence. `stop_replying`: an answer still being written is dropped (the call is
        being handed over); otherwise the whole answer is let finish."""
        task = self.reply_task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            if stop_replying:
                deadline = time.monotonic() + 8
                while self.speaking and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await asyncio.wait({task}, timeout=20)
        await self._wait_for_playback()

    async def _transfer_after(self, reply: Optional[asyncio.Task]) -> None:
        """Nobody in the dashboard: once the assistant has said it's connecting them, to the agent's number."""
        if reply is not None and reply is not asyncio.current_task():
            await asyncio.wait({reply}, timeout=20)
        await self._wait_for_playback()
        await self._transfer()

    async def _watch_handoff(self, handoff_id: str) -> None:
        """While the team is rung: connect the call when someone accepts; the fallback when nobody does in time."""
        while not self.ended.is_set():
            await asyncio.sleep(handoff.WATCH_SEC)
            async with async_session() as db:
                row = await db.get(CallHandoff, handoff_id)
            if row is None or row.status not in ("ringing", "accepted"):
                return
            if row.status == "accepted":
                await self._hand_over(row)
                return
            if handoff.aware(row.expires_at) <= handoff.now():
                if await handoff.settle(handoff_id, "missed", only_if=("ringing",), ended_at=handoff.now()):
                    await self._nobody_came(row)
                    return

    async def _hand_over(self, row: CallHandoff) -> None:
        """Someone accepted: finish the sentence being said, tell the caller, and hand them the call."""
        async with async_session() as db:
            name = await handoff.name_of(db, row.accepted_by)
        await self._finish_speaking(stop_replying=True)
        if self.s.channel != "phone":  # a test call in the browser has no phone line to hand over
            await handoff.settle(row.id, "ended", ended_at=handoff.now())
            fire_and_forget(handoff.announce(self.s.owner_id, row.id, "ended"))
            self._log("system", f"{name} picked up (a test call: there's no phone line to connect)")
            self.handoff = None
            await self.speak(f"This is a test call, so I can't connect you. On a phone call, {name} would be talking to you now.")
            return
        self._log("system", f"{name} picked up {'in the dashboard' if row.via == 'browser' else 'on their phone'}")
        self.transferred = True
        await handoff.settle(row.id, "connecting", only_if=("accepted",))
        fire_and_forget(handoff.announce(self.s.owner_id, row.id, "connecting"))
        await self.speak(handoff.CONNECTING.get(self._lang(), handoff.CONNECTING["en-IN"]))
        await self.end("handoff")

    async def _nobody_came(self, row: CallHandoff) -> None:
        """Nobody accepted in time: the agent's transfer number, else a call-back to-do, and the call goes on."""
        fire_and_forget(handoff.announce(self.s.owner_id, row.id, "missed"))
        agent = self.s.agent
        await self._finish_speaking(stop_replying=False)
        self.handoff = None
        if agent.transfer_enabled and agent.transfer_number and not self.s.after_hours and self.s.channel == "phone":
            await self.speak(handoff.CONNECTING.get(self._lang(), handoff.CONNECTING["en-IN"]))
            await self._transfer()
            return
        busy = handoff.BUSY.get(self._lang(), handoff.BUSY["en-IN"])
        self._log("system", "Nobody from the team picked up in time; a call back is in Schedule")
        await self.speak(busy)
        self.history.append({"role": "assistant", "content": busy})
        fire_and_forget(handoff.todo_for(self.s.owner_id, self.s.bot.bot_id, self.s.caller_e164, self.call_id,
                                         row.reason or "They asked for a person.", (self.s.caller or {}).get("name")))

    async def _live(self) -> None:
        """While the call runs: say it's alive, with the transcript so far (the Calls page shows it live; a call that
        stops saying so died with its server and is closed by voice/handoff.sweep)."""
        written = -1
        while not self.ended.is_set():
            if self.call_id:
                values = {"live_at": handoff.now(), "duration_sec": self._elapsed()}
                if len(self.transcript) != written:
                    values["transcript"] = list(self.transcript)
                try:
                    async with async_session() as db:
                        await db.execute(update(CallLog).where(CallLog.id == self.call_id, CallLog.outcome == "in_progress")
                                         .values(**values))
                        await db.commit()
                    written = len(self.transcript) if "transcript" in values else written
                except Exception as e:
                    logger.warning(f"Call {self.call_id}: couldn't write that it's alive: {e}")
            await asyncio.sleep(handoff.LIVE_SEC)

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
    async def _pump_audio(self) -> None:
        """The caller's audio, to the recording and to whichever recognizer connection is current. Runs for the
        whole call: a recognizer that drops only loses the audio sent while it reconnects."""
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
            now = time.monotonic()
            cut = self._watch_turn(self.levels.add(pcm, now), now)
            stt = self.stt
            if stt is None:
                pending.clear()  # reconnecting
                continue
            try:
                if cut is not None:
                    if cut == "before" and pending:
                        await stt.send(bytes(pending))  # the room's audio goes with the part cut off
                        pending.clear()
                    await self._finish_turn(stt, cut)
                if self.stt_batch:
                    pending.extend(pcm)
                    if len(pending) < self.stt_batch:
                        continue
                    chunk = bytes(pending)
                    pending.clear()
                else:
                    chunk = pcm
                await stt.send(chunk)
            except Exception as e:
                self._stt_lost(stt, f"sending audio to it failed ({type(e).__name__}: {e})")

    # ── the caller's voice and the room ─────────────────────────
    def _turn_started(self, now: float) -> None:
        self.turn_began, self.turn_cut_at, self.turn_flushed = now, None, False
        self.turn_voice_at, self.voice_run = None, 0
        self._follow_voice([level for t, level in self.levels.frames if t >= now - TURN_PRE_SEC], now)

    def _turn_ended(self, now: float) -> None:
        if self.turn_began is not None:
            self.turn_window = (self.turn_began - TURN_PRE_SEC, self.turn_cut_at or now, now, self.turn_cut_at is not None)
        self.turn_began = None

    def _heard_window(self, now: float) -> tuple[float, float, bool]:
        """The stretch of the caller's audio a transcript is about, and whether it was the room's part of a turn,
        cut off when the caller started talking."""
        if self.turn_began is not None:
            return self.turn_began - TURN_PRE_SEC, self.turn_cut_at or now, False
        window, self.turn_window = self.turn_window, None
        if window is not None and now - window[2] < 3.0:
            return window[0], window[1], window[3]
        return now - 8.0, now, False

    def _follow_voice(self, levels: list[float], now: float) -> bool:
        """Follow the caller's own voice through the current turn; True when it has just started in it."""
        started = False
        for level in levels:
            if self.levels.is_voice(level):
                self.voice_run += 1
                if self.voice_run >= 2:  # one loud 20 ms is a click, not a voice
                    started = started or self.turn_voice_at is None
                    self.turn_voice_at = now
            else:
                self.voice_run = 0
        return started

    def _watch_turn(self, levels: list[float], now: float) -> Optional[str]:
        """Follow the caller's voice through the turn the recognizer is hearing, and say when it should finish the
        turn now: talk or noise in the room keeps it hearing speech after the caller has stopped (under a TV it never
        ended the turn, so their question was never answered). "before": cut the turn ahead of this audio, where the
        caller starts after only the room had been heard; "after": they finished a while ago."""
        if self.turn_began is None:
            return None
        started = self._follow_voice(levels, now)
        if (started and self.speaking and self.s.agent.allow_interruptions and self.barge_in is None
                and now >= self.greeting_until):
            self.barge_in = asyncio.create_task(self._barge_in_after(BARGE_IN_SEC))  # the room had opened the turn
        if self.turn_flushed or not hasattr(self.stt, "flush"):
            return None
        if started and now - self.turn_began >= ONSET_FLUSH_SEC:
            self.turn_flushed, self.turn_cut_at, self.turn_voice_at = True, now, None
            return "before"
        if self.turn_voice_at is not None and now - self.turn_voice_at >= END_FLUSH_SEC:
            self.turn_flushed = True
            return "after"
        return None

    async def _finish_turn(self, stt, cut: str) -> None:
        self.flushes += 1
        logger.info(f"Call {self.call_id}: the recognizer still hears speech, but " + (
            "the caller just started after only the room: cutting the room's part off" if cut == "before" else
            f"the caller stopped {END_FLUSH_SEC:.1f}s ago: finishing their turn now"))
        await stt.flush()

    def _room_only(self, now: float) -> bool:
        """The recognizer hears speech, but hardly any of it is the caller's own voice (once their level is known)."""
        return self.turn_began is not None and self.levels.little_voice(now - BARGE_IN_SEC - TURN_PRE_SEC, now,
                                                                        BARGE_IN_VOICE_SEC)

    def _voice_gone(self, now: float) -> bool:
        """The recognizer still hears speech, but the caller's own voice stopped a while ago: the room is talking."""
        return self.turn_began is not None and self.levels.little_voice(now - VOICE_GONE_SEC, now, 0.1)

    def _stt_lost(self, stt, reason: str) -> None:
        """Drop this recognizer connection; _listen notices and opens another."""
        if self.stt is not stt:
            return
        self.stt, self.stt_problem = None, reason
        asyncio.ensure_future(self._close_stt(stt))

    @staticmethod
    async def _close_stt(stt) -> None:
        try:
            await stt.__aexit__(None, None, None)
        except Exception:
            pass

    async def _listen(self, language: str) -> None:
        """Hear the caller for the whole call. A recognizer connection that drops is replaced and the call goes on
        (a drop used to end the call in silence). Repeated drops, or a speech service that can't be reached, end
        the call with the caller told why."""
        drops: list[float] = []
        while not self.ended.is_set():
            try:
                stt = await self.stt_factory(language, self.rate, bool(self.s.agent.understand_code_mixed)).__aenter__()
            except Exception as e:
                await self._voice_failed(f"couldn't connect to the speech recognizer ({type(e).__name__}: {e})",
                                         apologize=True)
                return
            self.stt, self.stt_problem = stt, None
            try:
                await self._consume_stt(stt)
                reason = self.stt_problem or "it closed the connection"
            except Exception as e:
                reason = f"its connection failed ({type(e).__name__}: {e})"
            finally:
                if self.stt is stt:
                    self.stt = None
                await self._close_stt(stt)
            if self.ended.is_set():
                return
            self.caller_talking_since = self.turn_began = None  # whatever they were saying went with that connection
            self._cancel_barge_in()
            now = time.monotonic()
            drops = [t for t in drops if now - t < STT_RETRY_WINDOW_SEC] + [now]
            if len(drops) > STT_RETRIES:
                await self._voice_failed(f"the speech recognizer kept dropping ({reason})", apologize=True)
                return
            logger.warning(f"Call {self.call_id}: the speech recognizer dropped ({reason}); reconnecting")
            self._log("system", "Speech recognition dropped for a moment and was reconnected")
            await asyncio.sleep(0.2 * len(drops))

    async def _consume_stt(self, stt) -> None:
        async for ev in stt.events():
            if ev.kind in self.stt_events:
                self.stt_events[ev.kind] += 1
            try:
                await self._on_stt_event(ev)
            except Exception:  # a bug handling one sentence mustn't end the call, nor drop a working connection
                logger.exception(f"Call {self.call_id}: handling what the recognizer sent ({ev.kind}) failed")
            if self.ended.is_set():
                return

    async def _on_stt_event(self, ev) -> None:
        if ev.kind == "speech_start":
            self._turn_started(time.monotonic())
            await self.on_speech_start()
        elif ev.kind == "speech_end":
            self._turn_ended(time.monotonic())
            self.caller_talking_since = None
            self.last_heard = self.speech_ended_at = time.monotonic()
            self._cancel_barge_in()  # a short sound (a cough, "mm"): the agent carries on
        elif ev.kind == "transcript":
            since, until, cut = self._heard_window(time.monotonic())
            if cut or self.levels.background(since, until):
                self.background_ignored += 1
                why = ("the room, before the caller started talking" if cut else
                       f"far quieter than the caller ({self.levels.loud_level(since, until):.0f} dB; their voice "
                       f"{self.levels.voice:.0f} dB)")
                logger.info(f"Call {self.call_id}: ignored a sound from around the caller, {why}: {ev.text[:80]!r}")
                return
            self.levels.heard_turn(since, until)
            await self.on_caller_text(ev.text, getattr(ev, "language", None), getattr(ev, "probability", None))
        elif ev.kind == "error":
            logger.warning(f"STT error: {ev.text}")

    async def _watchdog(self) -> None:
        agent = self.s.agent
        limit = min(max(1, agent.max_call_minutes or 10) * 60, self.paid_seconds)
        silence = max(3, agent.silence_timeout_sec or 8)
        while not self.ended.is_set():
            await asyncio.sleep(0.5)
            try:
                await self._keep_voices_warm()
            except Exception as e:  # a keep-alive is a nicety; it must never take the call down
                logger.warning(f"Call {self.call_id}: keeping the voice connection open failed: {e}")
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
            talking = (self.caller_talking_since is not None and time.monotonic() - self.caller_talking_since < 60
                       and not self._voice_gone(time.monotonic()))
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
            self.recent_speech.append(self.opening_text)
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

    async def _has_credits(self) -> bool:
        """Enough credits for the call's first half-minute. It can last as long as they pay for: the watchdog
        ends it then, the goodbye included."""
        async with async_session() as db:
            left = metering.credits_left(await metering.get_wallet(db, self.s.owner_id))
        rate = ai_models.per_minute(self.model)
        self.paid_seconds = metering.seconds_for(left, rate) - GOODBYE_SEC
        return metering.enough_for_a_call(left, rate)

    def _rate(self) -> float:
        """Credits a minute: the base, plus the models that answered (when the agent's own model was busy and a backup
        answered instead, that turn costs the backup's rate)."""
        if not self.answered:
            return ai_models.per_minute(self.model)
        model_credits = sum(ai_models.ai_model(m).credits for m in self.answered) / len(self.answered)
        return round(ai_models.BASE_CREDITS + model_credits, 2)

    async def _open_log(self) -> None:
        async with async_session() as db:
            log = CallLog(user_id=self.s.owner_id, bot_id=self.s.bot.bot_id, direction=self.s.direction,
                          channel=self.s.channel, caller_e164=self.s.caller_e164, language=self.s.agent.language,
                          consent_source=self.s.consent_source, provider_call_id=self.s.provider_call_id,
                          campaign_id=self.s.campaign_id, number_id=self.s.number_id, outcome="in_progress")
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

    async def _out_of_credits(self, greeting: Optional[asyncio.Task], tasks: list[asyncio.Task]) -> Optional[str]:
        """The owner has no voice credits left: stop the opening, say so, and end."""
        stopping = [t for t in (greeting, self.opening_task) if t]
        for task in stopping:
            task.cancel()
        await asyncio.gather(*stopping, return_exceptions=True)
        await self._hush()
        self.failure = "No voice credits left"
        await self.t.event({"type": "error", "code": "no_minutes", "message": "You're out of voice credits."})
        await self.speak(self._no_credits_reply())
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
            # "hello?" into silence (a hello over the opening is ignored). The call log, the credits check,
            # the AI and the recognizer get ready while it plays.
            self._prepare_opening()
            greeting = asyncio.create_task(self._greet())
        try:
            _, has_credits = await asyncio.gather(self._open_log(), self._has_credits())
        except BaseException:
            for task in (greeting, self.opening_task, *tasks):
                if task:
                    task.cancel()
            raise
        if not has_credits:
            return await self._out_of_credits(greeting, tasks)
        if self.s.voicemail:
            return await self._leave_voicemail()

        if self.replier is llm.reply_sentences:
            tasks.append(asyncio.create_task(asyncio.to_thread(llm.warm_up)))
            self.knowledge_task = asyncio.create_task(llm.call_knowledge(self.s.bot))  # once, for the whole call
        # Following the caller's language: let the recognizer detect it ("unknown") instead of assuming ours.
        listen_in = "unknown" if self.follow_language else self.s.agent.language
        try:
            essential = [asyncio.create_task(self._pump_audio()), asyncio.create_task(self._listen(listen_in)),
                         asyncio.create_task(self._watchdog())]
            tasks += essential + [asyncio.create_task(self._live())]
            await self._until_ended(essential)
        except Exception as e:
            logger.exception(f"Call {self.call_id} failed: {e}")
            self.failure = str(e)[:300]
            await self.t.event({"type": "error", "code": "engine", "message": "The voice engine had a problem."})
            self.ended.set()
        finally:
            extra = [t for t in (greeting, self.reply_task, self.knowledge_task, self.opening_task, self.barge_in,
                                 self.handoff_task) if t and t is not asyncio.current_task()]
            for task in tasks + extra:
                task.cancel()
            await asyncio.gather(*tasks, *extra, return_exceptions=True)
            if self.stt is not None:
                await self._close_stt(self.stt)
                self.stt = None
            await self._close_voices()
            await self._finish()
        return self.call_id

    async def _until_ended(self, essential: list[asyncio.Task]) -> None:
        """Wait for the call to end. The audio pump, the listening and the watchdog run for the whole call (the
        listening survives recognizer drops by itself). If one still stops early, the call is ended as failed;
        otherwise nothing would be left to notice the caller hang up, and the call would never finish."""
        ended = asyncio.create_task(self.ended.wait())
        try:
            done, _ = await asyncio.wait([ended, *essential], return_when=asyncio.FIRST_COMPLETED)
        finally:
            ended.cancel()
        if not self.ended.is_set():
            stopped = next(t for t in done if t is not ended)
            error = None if stopped.cancelled() else stopped.exception()
            if error is not None:  # the full error in the server log, to find the cause
                logger.error(f"Call {self.call_id}: {stopped.get_coro().__name__} failed", exc_info=error)
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
        if self.handoff:  # the caller left while the team was being rung
            if await handoff.settle(self.handoff, "cancelled", only_if=("ringing",), ended_at=handoff.now()):
                fire_and_forget(handoff.announce(self.s.owner_id, self.handoff, "cancelled"))
        exact = time.monotonic() - self.started  # billed in half-minute steps: any connected call is at least one
        duration = round(exact)
        heard_secs = self.caller_bytes / 2 / self.rate
        logger.info(f"Call {self.call_id} diagnostics: {heard_secs:.1f}s of caller audio, peak level "
                    f"{self.caller_peak}/32767, recogniser events {self.stt_events}, {self.background_ignored} sounds "
                    f"from around the caller ignored, {self.flushes} turns finished early")
        outcome, summary, fields = "answered", "", {}
        successful, sentiment, lead, next_step = None, None, None, None
        if self.s.voicemail:
            outcome, summary = "voicemail", "Reached voicemail and left a message."
        elif self.failure and not self.caller_spoke:
            outcome, summary = "failed", self.failure
        elif self.opted_out:
            outcome, summary = "opted_out", "Caller asked not to be contacted again. Added to the do-not-call list."
        else:
            tools = self.s.tools
            extra = ({"zone_name": str(tools.tz), "open_calls": [{"id": o.label, "about": o.about} for o in tools.open]}
                     if tools is not None and self.summarizer is llm.summarize else {})
            result = await self.summarizer(self.s.bot, self.transcript, self.s.agent, **extra) if self.caller_spoke else {}
            summary, fields = result.get("summary", ""), result.get("fields", {})
            successful, sentiment, lead = result.get("successful"), result.get("sentiment"), result.get("lead")
            # Calls tried or planned for them that this one took care of: they aren't made (voice/schedule.py).
            handled = [o.id for o in (tools.open if tools is not None else []) if o.label in (result.get("handled") or [])]
            # What the next call should do (voice/schedule.py plans it after the call).
            next_step = {k: v for k, v in (("brief", result.get("follow_up")), ("on", result.get("follow_up_on")),
                                           ("call_back_at", result.get("call_back_at")), ("reason", result.get("lead_reason")),
                                           ("person", result.get("wants_callback")), ("meeting_at", result.get("meeting_at")),
                                           ("meeting_kind", result.get("meeting_kind")),
                                           ("meeting_about", result.get("meeting_about")), ("handled", handled)) if v} or None
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
            billed = (await metering.charge(db, self.s.owner_id, exact, self._rate())
                      if not self.failure or self.caller_spoke else 0)
            log = (await db.execute(select(CallLog).where(CallLog.id == self.call_id))).scalars().first()
            log.ended_at = datetime.utcnow()
            log.duration_sec = duration
            log.billed_minutes = math.ceil(exact / 60) if billed else 0
            log.credits_used = billed
            log.ai_model = self.model.id
            if self.reply_gaps:
                log.reply_ms = int(statistics.median(self.reply_gaps) * 1000)
            log.outcome = outcome
            log.summary = summary
            log.captured = fields
            log.successful = successful
            log.sentiment = sentiment
            log.lead, log.next_step = lead, next_step
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
        if self.s.channel == "phone":
            fire_and_forget(self._remember_and_plan())

    async def _remember_and_plan(self) -> None:
        """After a phone call: who they are, for their next call; then their lead rating and what happens next
        (a follow-up, a call-back), which build on it."""
        if self.s.agent.remember_callers is not False:
            await memory.remember_call(self.call_id)
        await schedule.after_call(self.call_id)
