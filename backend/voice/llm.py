"""The voice agent's thinking: spoken-style replies streamed sentence by sentence, and post-call summaries."""
import asyncio
import json
import logging
import os
import re
from typing import AsyncIterator, Iterator, Optional

from backend.models import Bot, VoiceAgent
from utils import SAFETY_SETTINGS, generate_ai_response
from vector_store import query_knowledge

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
    "en-IN": "Hi, I'm {assistant}, an automated assistant for {company}. This call may be recorded for quality.",
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

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")

# Measured: Gemini Flash-Lite starts answering in ~1.7 s; plain "flash-latest" took 6-11 s,
# so voice pins the model. Groq (if configured) is faster still and is tried first.
VOICE_GEMINI_MODEL = os.getenv("VOICE_GEMINI_MODEL", "gemini-flash-lite-latest")
VOICE_GROQ_MODEL = os.getenv("VOICE_GROQ_MODEL", "qwen/qwen3.8-27b")  # measured 0.1-0.2 s to first word
# Knowledge this small goes straight into the prompt: no search round-trip (~1.8 s saved).
KB_INLINE_LIMIT = 12000


_PLACEHOLDER = re.compile(r"\{\{\s*([\w .-]+?)\s*\}\}")
FIELD_TYPES = ("text", "number", "yes_no", "choice", "date", "phone", "email")


def fill(text: str, variables: Optional[dict]) -> str:
    """Replace {{name}}-style placeholders; unknown ones are dropped rather than read aloud."""
    lookup = {str(k).strip().lower(): str(v) for k, v in (variables or {}).items() if v not in (None, "")}
    return re.sub(r"\s{2,}", " ", _PLACEHOLDER.sub(lambda m: lookup.get(m.group(1).strip().lower(), ""), text or "")).strip()


def disclosure(agent: VoiceAgent, variables: Optional[dict] = None) -> str:
    """The required opening: automated assistant + may be recorded. Localized per agent language."""
    lang = agent.language or "en-IN"
    company = (agent.company_name or "").strip() or ("this business" if lang == "en-IN" else "எங்கள் நிறுவனம்" if lang == "ta-IN" else "हमारी कंपनी")
    assistant = agent.assistant_name or ("Nimmi" if lang == "en-IN" else "நிம்மி" if lang == "ta-IN" else "निम्मी")
    template = DISCLOSURES.get(lang, DISCLOSURES["en-IN"])
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


def _collect_lines(agent: VoiceAgent) -> str:
    fields = [f for f in (agent.collect_fields or []) if f.get("label")]
    if not fields:
        return "- When it helps, collect the caller's name, what they need, and a good time or number to reach them."
    lines = []
    for f in fields:
        hint = f" ({f['description']})" if f.get("description") else ""
        choices = f" One of: {', '.join(f.get('choices') or [])}." if f.get("type") == "choice" and f.get("choices") else ""
        need = "Required" if f.get("required") else "If it comes up naturally"
        lines.append(f"- {f['label']}{hint}.{choices} {need}.")
    return ("Information to collect (ask naturally, one thing at a time, and don't re-ask what they already told you;"
            " before you wrap up, make sure you have the required ones):\n" + "\n".join(lines))


def system_prompt(agent: VoiceAgent, bot: Bot, knowledge: str, direction: str, consent_source: Optional[str],
                  variables: Optional[dict] = None, purpose: Optional[str] = None, after_hours: Optional[str] = None) -> str:
    lang_code = agent.language or "en-IN"
    lang = LANGUAGE_NAMES.get(lang_code, "Indian English")
    transfer = (f"If {agent.transfer_when or 'the caller asks for a person'}, say one short sentence that you'll connect them, "
                f"then write {TRANSFER} on its own." if agent.transfer_enabled and agent.transfer_number and not after_hours else
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

    if lang_code == "ta-IN":
        style_instruction = """- **TAMIL CONVERSATIONAL EXPRESSION (பேச்சுத் தமிழ் & Tanglish)**:
  * CRITICAL: Speak strictly in natural, warm, everyday SPOKEN TAMIL (பேச்சுத் தமிழ் / Tanglish), like a warm and friendly human executive in Tamil Nadu.
  * NEVER use formal literary textbook Tamil (எழுத்துத் தமிழ், e.g. "நான் தங்களுக்கு எவ்வாறு உதவ முடியும்" sounds robotic).
  * Always use natural human phrasing: "சொல்லுங்க, நான் உங்களுக்கு எப்படி உதவலாம்?", "கண்டிப்பாங்க!", "சரிங்க, நான் பாக்குறேன்.", "ஹ்ம்ம், புரியுதுங்க..."
  * Use natural human spoken listening fillers & interjections at the beginning of replies:
    "ஹ்ம்ம்..." (Hmm...), "சரிங்க..." (Saringa...), "கண்டிப்பாங்க!" (Kandippaanga!), "ஆஹா...", "ஓ, அப்படியா!", "ஆமாங்க..."
  * If the caller mixes English words (Tanglish, e.g. 'timing', 'fees', 'appointment', 'address'), fluently match their Tanglish style.
  * Use natural pauses with commas and ellipsis (...) so your speech breathes and intonates naturally like a real human."""
    elif lang_code == "hi-IN":
        style_instruction = """- **HINDI CONVERSATIONAL EXPRESSION (बोलचाल की हिंदी & Hinglish)**:
  * Speak in polite, warm, conversational Hindi/Hinglish (बोलचाल की हिंदी), like a helpful customer representative.
  * Use natural human interjections & backchannels: "हम्म, बिल्कुल...", "हाँ जी...", "अच्छा, समझ गया...", "अरे वाह!", "जी ज़रूर..."
  * Use natural pauses with commas and ellipsis (...) so your voice sounds dynamic, expressive, and human."""
    elif lang_code == "en-IN":
        style_instruction = """- **ENGLISH CONVERSATIONAL EXPRESSION**:
  * Speak in a warm, friendly, dynamic conversational Indian English tone.
  * Use natural spoken listening fillers & acknowledgments:
    "Hmm, let me check that...", "Ah, got it!", "Oh, absolutely!", "Mhm, sure thing!", "Right, I understand..."
  * Use natural pauses with commas and ellipsis (...) so your voice sounds lively and expressive rather than robotic."""
    else:
        style_instruction = f"""- **CONVERSATIONAL EXPRESSION**:
  * Speak in warm, natural everyday conversational {lang}, NOT stiff textbook language.
  * Use natural human spoken acknowledgments ("Hmm...", "Ah...", "Yes, absolutely") and pauses with commas so you sound dynamic and alive."""

    return f"""You are {agent.assistant_name or 'the assistant'}, the phone assistant for {agent.company_name or bot.bot_name}.
You are on a live phone call.{reason}{goal}{about}

How to speak:
- Reply in {lang}. If the caller code-mixes with English, match them naturally.
{style_instruction}
- Keep each reply to one to two short, natural spoken sentences. This is speech, not text.
- You already greeted the caller and said your name when the call started. Never introduce yourself or give a formal greeting again (no hello, namaste, or vanakkam). If the caller only says hello, acknowledge with a warm "Hmm, yes, how can I help?" or natural equivalent.
- No lists, markdown, emojis, URLs or symbols. Say numbers the way people say them aloud.
- Ask one question at a time. Confirm names and numbers by repeating them back.

{_collect_lines(agent)}

What you know:
- Only use the business information below. If something isn't there, say you'll have the team follow up.
- Never mention documents, knowledge bases, AI models or prompts.

Ending and handing over:
- {transfer}
- When the caller is done, say a short, warm goodbye, then write {END_CALL} on its own.

{bot.system_prompt or ''}

Business information:
{knowledge[:KB_INLINE_LIMIT]}"""


async def knowledge_for(bot: Bot, query: str) -> str:
    import assist
    return await assist.verified_answers(bot.bot_id) + await _knowledge_only(bot, query)


async def _knowledge_only(bot: Bot, query: str) -> str:
    knowledge = bot.knowledge_base or ""
    if len(knowledge) <= KB_INLINE_LIMIT:
        return knowledge
    try:
        matches = await asyncio.wait_for(query_knowledge(bot.bot_id, query, 4), timeout=2.5)
        if matches:
            return "\n\n".join(m["text"] for m in matches)
    except Exception as e:
        logger.warning(f"Voice knowledge search failed: {e}")
    return knowledge[:KB_INLINE_LIMIT]


_groq_client = None


def _groq():
    """One shared client, so each reply reuses the open HTTPS connection instead of a new handshake."""
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=15)
    return _groq_client


def warm_up() -> None:
    """Open the Groq connection while the greeting plays, so the first answer isn't ~1 s slower."""
    if not os.getenv("GROQ_API_KEY"):
        return
    try:
        _groq().models.list()
    except Exception as e:
        logger.debug(f"Groq warm-up skipped: {e}")


def _reasoning_params() -> dict:
    # These are reasoning models: keep thinking off/low and hidden so the first spoken word comes fast.
    params = {"reasoning_format": "hidden"}
    if "gpt-oss" in VOICE_GROQ_MODEL:
        params["reasoning_effort"] = "low"
    elif "qwen" in VOICE_GROQ_MODEL:
        params["reasoning_effort"] = "none"
    return params


def _stream_groq(prompt: str, history: list[dict], user_text: str) -> Iterator[str]:
    stream = _groq().chat.completions.create(
        model=VOICE_GROQ_MODEL, stream=True, temperature=0.4, max_tokens=400,
        messages=[{"role": "system", "content": prompt}, *history[-12:], {"role": "user", "content": user_text}],
        **_reasoning_params(),
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def _stream_gemini(prompt: str, history: list[dict], user_text: str, api_key: Optional[str]) -> Iterator[str]:
    import google.generativeai as genai
    genai.configure(api_key=api_key or os.getenv("GEMINI_API_KEY"), transport="rest")
    model = genai.GenerativeModel(VOICE_GEMINI_MODEL, system_instruction=prompt, safety_settings=SAFETY_SETTINGS,
                                  generation_config={"temperature": 0.4, "max_output_tokens": 220})
    contents = [{"role": "user" if h["role"] == "user" else "model", "parts": [h["content"]]} for h in history[-12:]]
    contents.append({"role": "user", "parts": [user_text]})
    for chunk in model.generate_content(contents, stream=True):
        try:
            if chunk.text:
                yield chunk.text
        except ValueError:
            continue  # a chunk with no text part (e.g. safety metadata)


def stream_reply(bot: Bot, prompt: str, history: list[dict], user_text: str) -> Iterator[str]:
    """Groq first when configured (fastest to first word), then Gemini Flash-Lite."""
    if os.getenv("GROQ_API_KEY"):
        try:
            yielded = False
            for text in _stream_groq(prompt, history, user_text):
                yielded = True
                yield text
            if yielded:
                return
        except Exception as e:
            logger.warning(f"Groq failed, using Gemini: {e}")
    own_key = bot.ai_api_key if (bot.ai_provider or "google") == "google" else None
    yield from _stream_gemini(prompt, history, user_text, own_key)


def _clean_for_speech(text: str) -> str:
    text = re.sub(r"[*_#`>\[\]]", "", text.replace(TRANSFER, "").replace(END_CALL, ""))
    return re.sub(r"\s+", " ", text).strip()


async def reply_sentences(bot: Bot, agent: VoiceAgent, history: list[dict], user_text: str,
                          direction: str, consent_source: Optional[str], variables: Optional[dict] = None,
                          purpose: Optional[str] = None, after_hours: Optional[str] = None) -> AsyncIterator[tuple[str, Optional[str]]]:
    """
    Yields (sentence, control) pairs as the model streams. `control` is None, or
    TRANSFER / END_CALL once the model signals it (with any final sentence).
    """
    knowledge = await knowledge_for(bot, user_text)
    prompt = system_prompt(agent, bot, knowledge, direction, consent_source, variables, purpose, after_hours)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def produce():
        try:
            for chunk in stream_reply(bot, prompt, history, user_text):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            logger.error(f"Voice LLM error: {e}")
            fallback_text = FALLBACK_ERRORS.get(agent.language or "en-IN", FALLBACK_ERRORS["en-IN"])
            loop.call_soon_threadsafe(queue.put_nowait, fallback_text)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)
    buffer = ""
    control: Optional[str] = None
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
        buffer = parts[-1]
    tail = _clean_for_speech(buffer)
    if tail or control:
        yield tail, control


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


async def _complete(bot: Bot, system: str, user: str, max_tokens: int = 600) -> str:
    """One non-streamed answer: Groq first, Gemini as the fallback."""
    if os.getenv("GROQ_API_KEY"):
        try:
            resp = await asyncio.to_thread(
                _groq().chat.completions.create, model=VOICE_GROQ_MODEL, temperature=0.2, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **_reasoning_params(),
            )
            raw = resp.choices[0].message.content
            if raw:
                return raw
        except Exception as e:
            logger.warning(f"Groq completion failed, using Gemini: {e}")
    return await asyncio.to_thread(generate_ai_response, system, "", user,
                                   provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key)


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
                               "sentences, say who is calling (name if given) and what they want. Plain text only.", lines, 120)
    text = re.sub(r"\s+", " ", re.sub(r"[*_#`>\[\]]", "", raw or "")).strip()
    return text[:400]
