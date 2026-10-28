"""The voice agent's thinking: spoken-style replies streamed sentence by sentence, and post-call summaries."""
import asyncio
import json
import logging
import os
import re
import threading
import time
import unicodedata
from typing import AsyncIterator, Iterator, Optional

import httpx

import ai
import knowledge_sources
from backend.models import Bot, VoiceAgent

logger = logging.getLogger(__name__)

TRANSFER = "[TRANSFER]"
END_CALL = "[END_CALL]"
LANGUAGE_NAMES = {
    "en-IN": "Indian English", "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada",
    "ml-IN": "Malayalam", "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "od-IN": "Odia",
}

DEFAULT_GREETINGS = {
    "en-IN": "How can I help you today?",
    "ta-IN": "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?",
    "hi-IN": "नमस्ते! मैं आपकी किस प्रकार सहायता कर सकता हूँ?",
    "te-IN": "నమస్కారం! నేను మీకు ఎలా సహాయం చేయగలను?",
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "ml-IN": "നമസ്കാരം! ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "mr-IN": "नमस्कार! मी तुम्हाला कशी मदत करू शकतो?",
    "bn-IN": "নমস্কার! আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    "gu-IN": "નમસ્તે! હું તમને કેવી રીતે મદદ કરી શકું?",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "od-IN": "ନମସ୍କାର! ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
}

DISCLOSURES = {
    "en-IN": "Hi, {assistant} here, {company}'s AI assistant. This call is recorded.",  # ~6 s with the greeting
    "ta-IN": "வணக்கம், நான் {company}-க்கான தானியங்கி உதவியாளர் {assistant}. தரக்கட்டுப்பாட்டிற்காக இந்த அழைப்பு பதிவு செய்யப்படலாம்.",
    "hi-IN": "नमस्ते, मैं {company} के लिए स्वचालित सहायक {assistant} हूँ। गुणवत्ता के लिए यह कॉल रिकॉर्ड की जा सकती है।",
    "te-IN": "నమస్కారం, నేను {company} కోసం ఆటోమేటెడ్ అసిస్టెంట్ {assistant}. నాణ్యత కోసం ఈ కాల్ రికార్డ్ చేయబడవచ్చు.",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು {company} ಗಾಗಿ ಸ್ವಯಂಚಾಲಿತ ಸಹಾಯಕ {assistant}. ಗುಣಮಟ್ಟಕ್ಕಾಗಿ ಈ ಕರೆಯನ್ನು ರೆಕಾರ್ಡ್ ಮಾಡಬಹುದು.",
    "ml-IN": "നമസ്കാരം, ഞാൻ {company}-യുടെ ഓട്ടോമേറ്റഡ് അസിസ്റ്റന്റ് {assistant} ആണ്. ഗുണനിലവാരത്തിനായി ഈ കോൾ റെക്കോർഡ് ചെയ്തേക്കാം.",
    "mr-IN": "नमस्कार, मी {company} साठी स्वयंचलित सहाय्यक {assistant} आहे. गुणवत्तेसाठी हा कॉल रेकॉर्ड केला जाऊ शकतो.",
    "bn-IN": "নমস্কার, আমি {company}-র স্বয়ংক্রিয় সহকারী {assistant}। মান নিয়ন্ত্রণের জন্য এই কলটি রেকর্ড করা হতে পারে।",
    "gu-IN": "નમસ્તે, હું {company} માટે સ્વચાલિત સહાયક {assistant} છું. ગુણવત્તા માટે આ કૉલ રેકોર્ડ કરવામાં આવી શકે છે.",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ {company} ਲਈ ਸਵੈਚਾਲਤ ਸਹਾਇਕ {assistant} ਹਾਂ। ਗੁਣਵੱਤਾ ਲਈ ਇਹ ਕਾਲ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਸਕਦੀ ਹੈ।",
    "od-IN": "ନମସ୍କାର, ମୁଁ {company} ପାଇଁ ସ୍ୱୟଂଚାଳିତ ସହାୟକ {assistant} | ଗୁଣବତ୍ତା ପାଇଁ ଏହି କଲ୍ ରେକର୍ଡ କରାଯାଇପାରେ |",
}

VOICEMAIL_TEMPLATES = {
    "en-IN": "Hi{name_part}, this is {assistant} calling from {company}. Sorry we missed you. We'll try you again soon, or you can call us back on this number. Thank you.",
    "ta-IN": "வணக்கம்{name_part}, {company}-லிருந்து {assistant} பேசுகிறேன். உங்களை தொடர்பு கொள்ள முடியவில்லை. விரைவில் மீண்டும் அழைக்கிறோம், அல்லது இந்த எண்ணில் தொடர்பு கொள்ளலாம். நன்றி.",
    "hi-IN": "नमस्ते{name_part}, मैं {company} से {assistant} बात कर रहा हूँ। आपसे संपर्क नहीं हो सका। हम जल्द ही दोबारा कॉल करेंगे, या आप इस नंबर पर वापस कॉल कर सकते हैं। धन्यवाद।",
    "te-IN": "నమస్కారం{name_part}, నేను {company} నుండి {assistant}. మిమ్మల్ని సంప్రదించలేకపోయాము. మేము త్వరలో మళ్ళీ కాల్ చేస్తాము. ధన్యవాదాలు.",
    "kn-IN": "ನಮಸ್ಕಾರ{name_part}, ನಾನು {company} ಇಂದ {assistant}. ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ನಾವು ಶೀಘ್ರದಲ್ಲೇ ಮತ್ತೆ ಕರೆ ಮಾಡುತ್ತೇವೆ. ಧನ್ಯವಾದಗಳು.",
    "ml-IN": "നമസ്കാരം{name_part}, ഞാൻ {company}-ൽ നിന്ന് {assistant}. നിങ്ങളെ വിളിച്ചിട്ട് കിട്ടിയില്ല. ഉടൻ വീണ്ടും വിളിക്കാം. നന്ദി.",
    "mr-IN": "नमस्कार{name_part}, मी {company} कडून {assistant} बोलत आहे. आम्ही लवकरच पुन्हा संपर्क करू. धन्यवाद.",
    "bn-IN": "নমস্কার{name_part}, আমি {company} থেকে {assistant} বলছি। আপনার সাথে যোগাযোগ করা সম্ভব হয়নি। আমরা শীঘ্রই আবার কল করব। ধন্যবাদ।",
    "gu-IN": "નમસ્તે{name_part}, હું {company} તરફથી {assistant} બોલું છું. અમે ટૂંક સમયમાં ફરી કૉલ કરીશું. આભાર.",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ{name_part}, ਮੈਂ {company} ਤੋਂ {assistant} ਬੋਲ ਰਿਹਾ ਹਾਂ। ਅਸੀਂ ਜਲਦੀ ਹੀ ਦੁਬਾਰਾ ਕਾਲ ਕਰਾਂਗੇ। ਧੰਨਵਾਦ।",
    "od-IN": "ନମସ୍କାର{name_part}, ମୁଁ {company} ରୁ {assistant} କହୁଛି | ଆମେ ଶୀଘ୍ର ପୁଣି କଲ୍ କରିବୁ | ଧନ୍ୟବାଦ |",
}

FALLBACK_ERRORS = {
    "ta-IN": "மன்னிக்கவும், சரியாக கேட்கவில்லை. திரும்பவும் சொல்றீங்களா?",
    "hi-IN": "माफ़ कीजिए, मैं ठीक से सुन नहीं पाया। क्या आप दोबारा कह सकते हैं?",
    "te-IN": "క్షమించండి, సరిగ్గా వినపడలేదు. మళ్ళీ చెప్పగలరా?",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ಇನ್ನೊಮ್ಮೆ ಹೇಳಬಹುದೇ?",
    "ml-IN": "ക്ഷമിക്കണം, വ്യക്തമായി കേട്ടില്ല. ഒന്നുകൂടി പറയാമോ?",
    "en-IN": "Sorry, I didn't quite catch that. Could you say that again?",
}

# A sentence ends at . ! ? or । followed by a space, or at ! ? । followed straight by a letter (models
# writing Tamil or Hindi sometimes leave out the space: "என்ன?ஹ்ம்ம்"), or straight before a [TRANSFER] or
# [END_CALL] marker ("என்ன?[END_CALL]", as gpt-oss writes it). "1.5" and "nimmiai.in" don't split, nor
# does an ellipsis ("Hmm... let me check" is one sentence, not a filler spoken on its own).
_SENTENCE_END = re.compile(r"(?<=[.!?।])(?<!\.\.)\s+|(?<=[!?।])(?=[^\W\d_])|(?<=[.!?।])(?=\[)")

# Measured (Oct 2026): Groq answers in 0.1-0.5 s; Gemini Flash-Lite over REST in ~1.8 s; the old
# google-generativeai SDK took ~30 s, so it isn't used. Each Groq model has its own per-minute
# token allowance (8,000 on the free tier), so a rate-limited model is skipped for a while and
# the next one answers; Gemini is the last resort.
VOICE_GEMINI_MODEL = os.getenv("VOICE_GEMINI_MODEL", "gemini-flash-lite-latest")
VOICE_GROQ_MODEL = os.getenv("VOICE_GROQ_MODEL", "qwen/qwen3.8-27b")
VOICE_GROQ_MODELS = list(dict.fromkeys([VOICE_GROQ_MODEL] + [m.strip() for m in os.getenv(
    "VOICE_GROQ_FALLBACKS", "openai/gpt-oss-20b,openai/gpt-oss-120b").split(",") if m.strip()]))
# The business knowledge a call carries in every reply: small enough that a turn stays well inside
# the models' token allowance and answers fast. Bigger knowledge uses the "Business summary".
KB_INLINE_LIMIT = int(os.getenv("VOICE_KNOWLEDGE_CHARS", "7000"))
_rate_limited: dict[str, float] = {}  # Groq model -> when it can be used again
# A Groq model's first words come in well under a second. One that hasn't started after this long is overloaded:
# the next model answers instead (the SDK's own limit, 15 s, left callers in silence), and it rests a while.
GROQ_FIRST_WORDS_SEC = float(os.getenv("VOICE_GROQ_FIRST_WORDS_SEC", "3"))
SLOW_MODEL_REST_SEC = 15.0
# Gemini is the last resort on a call: a few seconds at most, not the website chat's 30 s.
VOICE_GEMINI_TIMEOUT = httpx.Timeout(float(os.getenv("VOICE_GEMINI_TIMEOUT_SEC", "8")), connect=3.0)
# How much of the conversation each reply sees: enough to remember a name or number given minutes ago.
HISTORY_MESSAGES = int(os.getenv("VOICE_HISTORY_MESSAGES", "16"))


class SlowModel(TimeoutError):
    """The model accepted the request but hasn't started answering in time."""


_PLACEHOLDER = re.compile(r"\{\{\s*([\w .-]+?)\s*\}\}")
FIELD_TYPES = ("text", "number", "yes_no", "choice", "date", "phone", "email")


def fill(text: str, variables: Optional[dict]) -> str:
    """Replace {{name}}-style placeholders; unknown ones are dropped rather than read aloud."""
    lookup = {str(k).strip().lower(): str(v) for k, v in (variables or {}).items() if v not in (None, "")}
    return re.sub(r"\s{2,}", " ", _PLACEHOLDER.sub(lambda m: lookup.get(m.group(1).strip().lower(), ""), text or "")).strip()


def disclosure(agent: VoiceAgent, variables: Optional[dict] = None, recorded: bool = True) -> str:
    """The required opening: an automated assistant (and that the call may be recorded, when it is), then the
    greeting. Kept short, since the caller waits for it before speaking."""
    lang = agent.language or "en-IN"
    company = (agent.company_name or "").strip() or ("this business" if lang == "en-IN" else "எங்கள் நிறுவனம்" if lang == "ta-IN" else "हमारी कंपनी")
    assistant = agent.assistant_name or ("Nimmi" if lang == "en-IN" else "நிம்மி" if lang == "ta-IN" else "निम्मी")
    template = DISCLOSURES.get(lang, DISCLOSURES["en-IN"])
    if not recorded:  # every template is "<who I am>. <may be recorded>."; keep the first sentence
        template = re.split(r"(?<=[.।|])\s+", template, maxsplit=1)[0]
    prefix = template.format(assistant=assistant, company=company)
    greeting = (agent.greeting or "").strip()
    if lang != "en-IN" and (not greeting or greeting.lower() in ("how can i help you today?", "how can i help you?")):
        greeting = DEFAULT_GREETINGS.get(lang, "")
    greeting_filled = fill(greeting, variables)
    return f"{prefix} {greeting_filled}".strip()


def voicemail_text(agent: VoiceAgent, variables: Optional[dict] = None) -> str:
    custom = fill(agent.voicemail_message or "", variables)
    if custom:
        return custom
    lang = agent.language or "en-IN"
    name = (variables or {}).get("name")
    name_part = f" {name}" if name else ""
    company = (agent.company_name or "").strip() or ("us" if lang == "en-IN" else "எங்கள் நிறுவனம்" if lang == "ta-IN" else "हमारी कंपनी")
    assistant = agent.assistant_name or ("an assistant" if lang == "en-IN" else "உதவியாளர்" if lang == "ta-IN" else "सहायक")
    template = VOICEMAIL_TEMPLATES.get(lang, VOICEMAIL_TEMPLATES["en-IN"])
    return template.format(name_part=name_part, assistant=assistant, company=company)


def _collect_lines(agent: VoiceAgent, phone_known: bool = False) -> str:
    fields = [f for f in (agent.collect_fields or []) if f.get("label")]
    if not fields:
        return ("- When it helps, collect the caller's name, what they need, and a good time "
                + ("to reach them." if phone_known else "or number to reach them."))
    lines = []
    for f in fields:
        hint = f" ({f['description']})" if f.get("description") else ""
        choices = f" One of: {', '.join(f.get('choices') or [])}." if f.get("type") == "choice" and f.get("choices") else ""
        need = "Required" if f.get("required") else "If it comes up naturally"
        lines.append(f"- {f['label']}{hint}.{choices} {need}.")
    return ("Information to collect (ask naturally, one thing at a time, and don't re-ask what they already told you;"
            " before you wrap up, make sure you have the required ones):\n" + "\n".join(lines))


# How each language should sound. Never examples of fillers ("Hmm...", "ஓ, அப்படியா!"): models copy examples
# into nearly every reply, and the voice reads them as odd noises.
SPEAKING_STYLE = {
    "en-IN": "Use warm, simple, everyday Indian English.",
    "ta-IN": "Use everyday spoken Tamil (பேச்சுத் தமிழ்) with polite -ங்க endings, the way a friendly executive in"
             " Tamil Nadu talks, not formal written Tamil. Keep the English words callers use (fees, course,"
             " appointment, address) in English.",
    "hi-IN": "Use everyday spoken Hindi, polite with आप and जी; Hinglish is fine. Avoid formal, bookish Hindi.",
}


def system_prompt(agent: VoiceAgent, bot: Bot, knowledge: str, direction: str, consent_source: Optional[str],
                  variables: Optional[dict] = None, purpose: Optional[str] = None, after_hours: Optional[str] = None,
                  reply_language: Optional[str] = None, script: Optional[dict] = None, caller: Optional[dict] = None,
                  phone_known: bool = False) -> str:
    """`script`: the business's personality and instructions for this kind of call (voice/scripts.py style).
    `caller`: what the assistant remembers about the person (voice/memory.py context_for).
    `phone_known`: a phone call, so their number is on record (the model isn't given it, so it can't read it out)."""
    lang_code = reply_language or agent.language or "en-IN"  # the caller's language once they switch
    lang = LANGUAGE_NAMES.get(lang_code, "Indian English")
    began_in = agent.language or "en-IN"
    switched = (f" The call began in {LANGUAGE_NAMES.get(began_in, 'English')}, but the caller is speaking {lang}:"
                f" answer in {lang} from now on." if lang_code != began_in else "")
    in_script = ("" if lang_code == "en-IN" else
                 f"\n- Write {lang} words in {lang} script, never in English letters: the voice reads {lang} script."
                 " English words such as course names or 'fees' can stay in English.")
    transfer = (f"If {agent.transfer_when or 'the caller asks for a person'}, say one short sentence that you'll connect them "
                f"and end that reply with {TRANSFER}. Never write {TRANSFER} in any other reply."
                if agent.transfer_enabled and agent.transfer_number and not after_hours else
                "If the caller asks for a person, offer to take their name and number so the team can call back.")
    if after_hours:
        transfer += f" The team is offline right now and back {after_hours}; say so if they ask for a person."
    reason = ""
    if direction == "outbound":
        if purpose:
            reason = f"\nYou called them. Why you're calling: {fill(purpose, variables)}"
        elif consent_source:
            reason = f"\nYou are calling back because: {consent_source}."
    goal = f"\nYour goal on this call: {fill(agent.call_goal, variables)}" if agent.call_goal else ""
    known = [f"{k}: {v}" for k, v in (variables or {}).items() if v not in (None, "")]
    about = ("\n\nWhat you already know about this person (use it, don't ask for it again):\n" + "\n".join(known)) if known else ""

    style = SPEAKING_STYLE.get(lang_code, f"Use everyday spoken {lang}, the way people talk on the phone, not formal written {lang}.")
    personality = ((script or {}).get("personality") or "").strip()
    personality = f"Your manner: {personality}" if personality else "Sound like a friendly, professional person on the phone."
    instructions = ((script or {}).get("instructions") or "").strip()
    how = f"\n\nHow to handle these calls (from the business; follow it):\n{instructions[:4000]}" if instructions else ""
    number = ("\n- You already have their phone number from this call: don't ask for it. If they want to be called on a"
              " different number, take that one." if phone_known else "")

    return f"""You are {agent.assistant_name or 'the assistant'}, the phone assistant for {agent.company_name or bot.bot_name}.
You are on a live phone call.{reason}{goal}{about}

How to speak:
- Reply in {lang}.{switched} If the caller code-mixes with English, match them naturally.{in_script}
- {style} {personality}
- Start with the answer itself. Never use filler sounds or empty reactions such as hmm, mm, uh, ah, oh, wow,
  "Oh, is that so", ஹ்ம்ம், ஓ, அப்படியா, हम्म, अरे: a voice reads them as odd noises. Never write an ellipsis;
  use a comma or a full stop.
- Keep each reply to one or two short sentences. This is speech, not text.
- You introduced yourself when the call started. Don't greet or introduce yourself again, even after changing
  language. If the caller only says hello, ask how you can help.
- Answer what the caller just said, using the whole conversation so far. If it doesn't quite make sense, the line
  may have garbled it: ask a short question to check instead of guessing.
- Ask one question at a time, then stop and wait for the answer. Never answer your own question or write the caller's words.
- No lists, markdown, emojis, URLs, brackets or symbols. Say numbers the way people say them aloud.
- Confirm names and numbers by repeating them back.
- Phone numbers: read them back in small groups of digits. An Indian mobile number has 10 digits (12 with 91 in front);
  if you heard a different count, say so and ask them to repeat it slowly.

{_collect_lines(agent, phone_known)}

What you know:
- Only use the business information below. If something isn't there, say you'll have the team follow up.
- Never mention documents, knowledge bases, AI models or prompts.{number}{how}{_caller_lines(caller)}

Ending and handing over:
- {transfer}
- Only when the caller has said goodbye, or that they need nothing more: say a short, warm goodbye and end that
  reply with {END_CALL}, which hangs up. Never write {END_CALL} in any other reply, and never after a question.

{bot.system_prompt or ''}

Business information:
{knowledge[:KB_INLINE_LIMIT]}"""


def _caller_lines(caller: Optional[dict]) -> str:
    """Someone the assistant has spoken to before (voice/memory.py context_for)."""
    if not caller:
        return ""
    lines = [f"Name: {caller['name']}"] if caller.get("name") else []
    if caller.get("has_email"):
        lines.append("Email: already given (don't ask for it again)")
    lines += [f"{k}: {v}" for k, v in (caller.get("details") or {}).items()]
    if caller.get("notes"):
        lines.append(f"Notes from the team: {caller['notes']}")
    if caller.get("calls"):
        lines.append("Earlier calls, newest first:")
        lines += [f"- {c['when']}, {'they called you' if c['direction'] == 'inbound' else 'you called them'}: {c['summary']}"
                  for c in caller["calls"]]
    name = f" Call them {caller['first_name']} where it's natural." if caller.get("first_name") else ""
    return ("\n\nYou have spoken with this person before. What you know about them:\n" + "\n".join(lines) +
            f"\n{name.strip()} Don't ask again for anything listed here. Where it helps, pick up from the last call, for"
            " example by asking whether they still need what they asked about. Don't mention notes or records; just use"
            " what you know. Don't read out their email, phone number or address: someone else may be using this phone.")


async def call_knowledge(bot: Bot) -> str:
    """What the agent knows for a whole call, worked out once when the call starts (a search on every
    turn added up to 2.5 s and failed on a cold connection). Small knowledge is used as is; bigger
    knowledge uses the business summary written from it (brain.refresh_summary)."""
    import assist
    knowledge = bot.knowledge_base or ""
    if len(knowledge) > KB_INLINE_LIMIT:
        written, blocks = knowledge_sources.split(knowledge)
        summary = dict(blocks).get(knowledge_sources.SUMMARY, "")
        if summary:
            knowledge = "\n\n".join(p for p in (written[:1500], summary) if p)
        else:
            import brain
            from notify.events import fire_and_forget
            fire_and_forget(brain.refresh_summary(bot.bot_id))  # ready for the next call
    try:
        verified = await asyncio.wait_for(assist.verified_answers(bot.bot_id), timeout=2)
    except Exception:
        verified = ""
    return (verified + knowledge)[: KB_INLINE_LIMIT + 2000]


async def knowledge_for(bot: Bot, query: str) -> str:
    """Kept for callers outside a live call."""
    return await call_knowledge(bot)


_groq_client = None


def _groq():
    """One shared client, so each reply reuses the open HTTPS connection instead of a new handshake."""
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        # No retries inside the SDK: on a rate limit it waits out Groq's retry-after (10-20 s of silence
        # on a live call). stream_reply moves to the next model, then Gemini, straight away instead.
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=15, max_retries=0)
    return _groq_client


def warm_up() -> None:
    """Open the Groq connection while the greeting plays, so the first answer isn't ~1 s slower."""
    if not os.getenv("GROQ_API_KEY"):
        return
    try:
        _groq().models.list()
    except Exception as e:
        logger.debug(f"Groq warm-up skipped: {e}")


def _reasoning_params(model: str) -> dict:
    # These are reasoning models: keep thinking off/low and hidden so the first spoken word comes fast.
    params = {"reasoning_format": "hidden"}
    if "gpt-oss" in model:
        params["reasoning_effort"] = "low"
    elif "qwen" in model:
        params["reasoning_effort"] = "none"
    return params


def _groq_models() -> list[str]:
    now = time.monotonic()
    return [m for m in VOICE_GROQ_MODELS if _rate_limited.get(m, 0) <= now]


def _note_limit(model: str, error: Exception) -> None:
    """A model out of its per-minute allowance is skipped until it refills (Groq says when); one too slow to
    start answering rests for a while."""
    if getattr(error, "status_code", None) in (413, 429) or "rate_limit" in str(error):
        wait = 20.0
        try:
            wait = float(getattr(error, "response").headers.get("retry-after") or wait)
        except (AttributeError, TypeError, ValueError):
            pass
        _rate_limited[model] = time.monotonic() + min(max(wait, 5.0), 60.0)
    elif isinstance(error, TimeoutError) or type(error).__name__ == "APITimeoutError":
        _rate_limited[model] = time.monotonic() + SLOW_MODEL_REST_SEC


def _stream_groq(model: str, prompt: str, history: list[dict], user_text: str) -> Iterator[str]:
    started = time.monotonic()
    stream = _groq().chat.completions.create(
        model=model, stream=True, temperature=0.4, max_tokens=300,
        messages=[{"role": "system", "content": prompt}, *history[-HISTORY_MESSAGES:], {"role": "user", "content": user_text}],
        timeout=httpx.Timeout(GROQ_FIRST_WORDS_SEC, connect=2.0), **_reasoning_params(model),
    )
    try:
        answering = False
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                answering = True
                yield delta
            elif not answering and time.monotonic() - started > GROQ_FIRST_WORDS_SEC:
                raise SlowModel(f"no words after {GROQ_FIRST_WORDS_SEC:.0f}s")  # still thinking (hidden reasoning)
    finally:
        stream.close()  # stopped early (the answer was cut short): don't keep reading the rest


def _stream_gemini(prompt: str, history: list[dict], user_text: str, api_key: Optional[str]) -> Iterator[str]:
    """Gemini over REST (ai.py), the fast model first."""
    messages = [{"role": "user" if h["role"] == "user" else "assistant", "content": h["content"]}
                for h in history[-HISTORY_MESSAGES:]]
    messages.append({"role": "user", "content": user_text})
    yield from ai.chat_stream(prompt, messages, model=VOICE_GEMINI_MODEL, api_key=api_key, temperature=0.4, max_tokens=220,
                              timeout=VOICE_GEMINI_TIMEOUT)


def stream_reply(bot: Bot, prompt: str, history: list[dict], user_text: str) -> Iterator[str]:
    """Groq (fastest to the first word), moving to the next Groq model when one is rate-limited, then Gemini."""
    started = time.monotonic()
    if os.getenv("GROQ_API_KEY"):
        for model in _groq_models():
            yielded = False
            try:
                for text in _stream_groq(model, prompt, history, user_text):
                    if not yielded:
                        logger.info(f"Voice reply from {model}: first words after {time.monotonic() - started:.2f}s")
                    yielded = True
                    yield text
                if yielded:
                    return
            except Exception as e:
                _note_limit(model, e)
                logger.warning(f"Groq {model} failed{' mid-answer' if yielded else ''}: {str(e)[:160]}")
                if yielded:
                    return  # part of the answer was already spoken; don't start a second one
    own_key = bot.ai_api_key if (bot.ai_provider or "google") == "google" else None
    logger.info(f"Voice reply from Gemini (Groq unavailable) after {time.monotonic() - started:.2f}s")
    yield from _stream_gemini(prompt, history, user_text, own_key)


# An ellipsis ("சரிங்க... fees") is spoken as a comma's short pause.
_ELLIPSIS = re.compile(r"\s*(?:\.{2,}|…)\s*")
# Filler sounds and empty reactions at the start of a sentence ("Hmm,", "Oh,", "ஹ்ம்ம்,", "ஓ,", "हम्म,"). The voice
# reads them as odd noises, so they're dropped even when the model writes them anyway.
_FILLERS = (r"h+m+|m+h*m+|u+h+|u+m+|e+r+m*|a+h+|o+h+|ஹ்ம்(?:ம்)*|ம்(?:ம்)+|ஓ+|ஆ+|ஆஹா|ஓஹோ|"
            r"हम्म्|हम्म*|उम्म*|अं|ओह|अरे")
_LEADING_FILLERS = re.compile(rf"^(?:(?:{_FILLERS})(?:[\s,.!?;:-]+|$))+", re.IGNORECASE)
# Sentences that are only a reaction ("ஓ, அப்படியா!" = "Oh, is that so!") say nothing to the caller.
_EMPTY_REACTIONS = {"அப்படியா", "அப்படிங்களா", "ஆஹா", "ஓஹோ", "वाह", "अरे वाह", "wow", "i see", "oh i see"}


def plain_words(text: str) -> list[str]:
    """Lowercase words without punctuation, keeping Indian scripts whole: Python's \\w leaves out their vowel
    signs, which splits "அப்படியா" or "नमस्ते" into pieces that match nothing."""
    text = (text or "").lower().replace("’", "'")
    return "".join(c if c.isalnum() or c == "'" or unicodedata.category(c).startswith("M") else " " for c in text).split()


def _clean_for_speech(text: str) -> str:
    text = re.sub(r"[*_#`>\[\]()]", "", text.replace(TRANSFER, "").replace(END_CALL, ""))
    text = re.sub(r"\s+", " ", _ELLIPSIS.sub(", ", text)).strip()
    text = _LEADING_FILLERS.sub("", text).strip(" ,;:-")
    if " ".join(plain_words(text)) in _EMPTY_REACTIONS:
        return ""
    if text[:1].isascii() and text[:1].islower():
        text = text[0].upper() + text[1:]  # "Hmm, let me check" -> "Let me check"
    return text


async def reply_sentences(bot: Bot, agent: VoiceAgent, history: list[dict], user_text: str,
                          direction: str, consent_source: Optional[str], variables: Optional[dict] = None,
                          purpose: Optional[str] = None, after_hours: Optional[str] = None,
                          knowledge: Optional[str] = None, reply_language: Optional[str] = None,
                          script: Optional[dict] = None, caller: Optional[dict] = None, phone_known: bool = False
                          ) -> AsyncIterator[tuple[str, Optional[str]]]:
    """
    Yields (sentence, control) pairs as the model streams. `control` is None, or
    TRANSFER / END_CALL once the model signals it (with any final sentence).
    `knowledge` is the call's knowledge, worked out once per call by CallSession.
    """
    if knowledge is None:
        knowledge = await call_knowledge(bot)
    prompt = system_prompt(agent, bot, knowledge, direction, consent_source, variables, purpose, after_hours, reply_language,
                           script=script, caller=caller, phone_known=phone_known)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    stop = threading.Event()

    def produce():
        try:
            for chunk in stream_reply(bot, prompt, history, user_text):
                if stop.is_set():
                    break  # the answer ended early: stop reading the model (and spending its allowance)
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            logger.error(f"Voice LLM error: {e}")
            language = reply_language or agent.language or "en-IN"  # the caller's language once they switched
            loop.call_soon_threadsafe(queue.put_nowait, FALLBACK_ERRORS.get(language, FALLBACK_ERRORS["en-IN"]))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)
    buffer = ""
    control: Optional[str] = None
    try:
        while (chunk := await queue.get()) is not None:
            buffer += chunk
            if TRANSFER in buffer:
                control = TRANSFER
            if END_CALL in buffer:
                control = control or END_CALL
            parts = _SENTENCE_END.split(buffer)
            for sentence in parts[:-1]:
                spoken = _clean_for_speech(sentence)
                if spoken:
                    yield spoken, None
                    if spoken.endswith("?"):
                        return  # a question ends the turn: the caller answers it, not the model
            buffer = parts[-1]
        tail = _clean_for_speech(buffer)
        if control and tail.endswith("?"):
            # The models (gpt-oss most) add the marker to questions too: hanging up on "What's your number?"
            # cut live calls mid-conversation. A question is answered first, as everywhere else.
            logger.warning(f"The model wrote {control} after a question; waiting for the answer instead")
            control = None
        if tail or control:
            yield tail, control
    finally:
        stop.set()


SUMMARY_PROMPT = """Read this phone call transcript between a business's assistant and a caller.
Return only JSON with these keys:
"summary": one or two plain sentences on what the caller wanted and what was agreed,
"fields": FIELDS_SPEC,
"successful": true or false, SUCCESS_SPEC,
"sentiment": "positive", "neutral" or "negative": how the caller felt by the end of the call,
"wants_callback": true if the caller asked to be called back by a person.
Only use what was actually said. Never guess.
"""

FREEFORM_FIELDS = ('an object of details the caller gave (for example Name, Phone, Email, Course, Appointment), '
                   'using short title-case keys and only values actually said')


def _fields_spec(agent: Optional[VoiceAgent]) -> str:
    fields = [f for f in ((agent.collect_fields if agent else None) or []) if f.get("label")]
    if not fields:
        return FREEFORM_FIELDS
    kinds = {"text": "short text", "number": "a number", "yes_no": "true or false", "date": "a date like 2026-10-14 or what they said",
             "phone": "a phone number", "email": "an email address", "choice": "one of the listed choices"}
    parts = []
    for f in fields:
        extra = f" Choices: {', '.join(f.get('choices') or [])}." if f.get("type") == "choice" else ""
        desc = f" {f['description']}." if f.get("description") else ""
        parts.append(f'"{f["label"]}": {kinds.get(f.get("type"), "short text")}.{desc}{extra}')
    return ("an object with exactly these keys, each set to null if the caller didn't say: {" + "; ".join(parts) + "}")


def _clean_value(field: dict, value):
    """Coerce an extracted value to the field's type; None if it doesn't fit."""
    if value in (None, "", [], {}):
        return None
    kind = field.get("type") or "text"
    text = str(value).strip()
    if kind == "number":
        try:
            num = float(re.sub(r"[^\d.\-]", "", text))
            return str(int(num)) if num.is_integer() else str(num)
        except ValueError:
            return None
    if kind == "yes_no":
        if isinstance(value, bool):
            return "Yes" if value else "No"
        low = text.lower()
        return "Yes" if low in ("yes", "true", "y", "haan", "ha") else "No" if low in ("no", "false", "n", "nahi") else None
    if kind == "choice":
        choices = field.get("choices") or []
        return next((c for c in choices if c.lower() == text.lower()), None)
    if kind == "phone":
        from phone import display, to_e164
        e164 = to_e164(text)
        return display(e164) if e164 else None
    if kind == "email":
        return text if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", text) else None
    return text[:200]


async def _complete(bot: Bot, system: str, user: str, max_tokens: int = 600, urgent: bool = False) -> str:
    """One non-streamed answer. After a call (summaries) Gemini goes first, saving Groq's per-minute
    allowance for live conversations; during a call (`urgent`, e.g. a transfer brief) Groq goes first."""
    own_key = bot.ai_api_key if (bot.ai_provider or "google") == "google" else None

    async def gemini() -> str:
        return await asyncio.to_thread(ai.chat, system, [{"role": "user", "content": user}], model=VOICE_GEMINI_MODEL,
                                       api_key=own_key, temperature=0.2, max_tokens=max_tokens)

    async def groq() -> str:
        for model in _groq_models():
            try:
                resp = await asyncio.to_thread(
                    _groq().chat.completions.create, model=model, temperature=0.2, max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **_reasoning_params(model))
                if resp.choices[0].message.content:
                    return resp.choices[0].message.content
            except Exception as e:
                _note_limit(model, e)
                logger.warning(f"Groq {model} completion failed: {str(e)[:160]}")
        raise ai.AIError("no Groq model answered")

    order = ([groq, gemini] if urgent else [gemini, groq]) if os.getenv("GROQ_API_KEY") else [gemini]
    last: Optional[Exception] = None
    for attempt in order:
        try:
            return await attempt()
        except Exception as e:
            last = e
    raise ai.AIError(f"no model answered: {last}")


def _lines(transcript: list[dict]) -> str:
    return "\n".join(f"{'Assistant' if t['speaker'] == 'agent' else 'Caller'}: {t['text']}"
                     for t in transcript if t.get("speaker") in ("agent", "caller"))


async def summarize(bot: Bot, transcript: list[dict], agent: Optional[VoiceAgent] = None) -> dict:
    """Post-call analysis: summary, the agent's fields (typed), whether the goal was met, and sentiment."""
    empty = {"summary": "", "fields": {}, "successful": None, "sentiment": None, "wants_callback": False}
    lines = _lines(transcript)
    if not lines.strip():
        return empty
    goal = (agent.call_goal if agent else None) or ""
    success_spec = (f"whether the call achieved this goal: {goal}" if goal else
                    "whether the caller's need was handled or a clear next step was agreed")
    prompt = SUMMARY_PROMPT.replace("FIELDS_SPEC", _fields_spec(agent)).replace("SUCCESS_SPEC", success_spec)
    try:
        raw = await _complete(bot, prompt, lines)
        match = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(match.group(0)) if match else {}
        configured = [f for f in ((agent.collect_fields if agent else None) or []) if f.get("label")]
        got = data.get("fields") or {}
        if configured:
            lookup = {str(k).strip().lower(): v for k, v in got.items()}
            fields = {}
            for f in configured:
                value = _clean_value(f, lookup.get(f["label"].strip().lower()))
                if value is not None:
                    fields[f["label"][:40]] = value
        else:
            fields = {str(k)[:40]: str(v)[:200] for k, v in got.items() if v not in (None, "", [])}
        sentiment = str(data.get("sentiment") or "").lower()
        successful = data.get("successful")
        return {
            "summary": str(data.get("summary") or "")[:600], "fields": fields,
            "successful": successful if isinstance(successful, bool) else None,
            "sentiment": sentiment if sentiment in ("positive", "neutral", "negative") else None,
            "wants_callback": bool(data.get("wants_callback")),
        }
    except Exception as e:
        logger.warning(f"Call summary failed: {e}")
        return empty


async def transfer_brief(bot: Bot, transcript: list[dict], caller: Optional[str]) -> str:
    """One or two sentences for the person taking a warm transfer, spoken before they're connected."""
    lines = _lines(transcript)
    if not lines.strip():
        return ""
    raw = await _complete(bot, "You brief a staff member who is about to take over a phone call. In at most two short "
                               "sentences, say who is calling (name if given) and what they want. Plain text only.", lines, 120,
                          urgent=True)
    text = re.sub(r"\s+", " ", re.sub(r"[*_#`>\[\]]", "", raw or "")).strip()
    return text[:400]
