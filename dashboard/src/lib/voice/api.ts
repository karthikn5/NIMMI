import type { AgentDirection, CallOutcome, LanguageCode, Sentiment } from "./types";

export const LANGUAGES: { code: LanguageCode; label: string }[] = [
    { code: "en-IN", label: "English (India)" },
    { code: "hi-IN", label: "Hindi" },
    { code: "ta-IN", label: "Tamil" },
    { code: "te-IN", label: "Telugu" },
    { code: "kn-IN", label: "Kannada" },
    { code: "ml-IN", label: "Malayalam" },
    { code: "mr-IN", label: "Marathi" },
    { code: "bn-IN", label: "Bengali" },
    { code: "gu-IN", label: "Gujarati" },
    { code: "pa-IN", label: "Punjabi" },
    { code: "od-IN", label: "Odia" },
];

export const languageLabel = (code: LanguageCode) => LANGUAGES.find((l) => l.code === code)?.label ?? code;

export const DEFAULT_GREETINGS: Record<LanguageCode, string> = {
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
};

export const DISCLOSURE_TEMPLATES: Record<LanguageCode, string> = {
    "en-IN": "Hi, {name} here, {company}'s AI assistant. This call is recorded.",
    "ta-IN": "வணக்கம், நான் {company}-க்கான தானியங்கி உதவியாளர் {name}. தரக்கட்டுப்பாட்டிற்காக இந்த அழைப்பு பதிவு செய்யப்படலாம்.",
    "hi-IN": "नमस्ते, मैं {company} के लिए स्वचालित सहायक {name} हूँ। गुणवत्ता के लिए यह कॉल रिकॉर्ड की जा सकती है।",
    "te-IN": "నమస్కారం, నేను {company} కోసం ఆటోమేటెడ్ అసిస్టెంట్ {name}. నాణ్యత కోసం ఈ కాల్ రికార్డ్ చేయబడవచ్చు.",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು {company} ಗಾಗಿ ಸ್ವಯಂಚಾಲಿತ ಸಹಾಯಕ {name}. ಗುಣಮಟ್ಟಕ್ಕಾಗಿ ಈ ಕರೆಯನ್ನು ರೆಕಾರ್ಡ್ ಮಾಡಬಹುದು.",
    "ml-IN": "നമസ്കാരം, ഞാൻ {company}-യുടെ ഓട്ടോമേറ്റഡ് അസിസ്റ്റന്റ് {name} ആണ്. ഗുണനിലവാരത്തിനായി ഈ കോൾ റെക്കോർഡ് ചെയ്തേക്കാം.",
    "mr-IN": "नमस्कार, मी {company} साठी स्वयंचलित सहाय्यक {name} आहे. गुणवत्तेसाठी हा कॉल रेकॉर्ड केला जाऊ शकतो.",
    "bn-IN": "নমস্কার, আমি {company}-র স্বয়ংক্রিয় সহকারী {name}। মান নিয়ন্ত্রণের জন্য এই কলটি রেকর্ড করা হতে পারে।",
    "gu-IN": "નમસ્તે, હું {company} માટે સ્વચાલિત સહાયક {name} છું. ગુણવત્તા માટે આ કૉલ રેકોર્ડ કરવામાં આવી શકે છે.",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ {company} ਲਈ ਸਵੈਚਾਲਤ ਸਹਾਇਕ {name} ਹਾਂ। ਗੁਣਵੱਤਾ ਲਈ ਇਹ ਕਾਲ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਸਕਦੀ ਹੈ।",
    "od-IN": "ନମସ୍କାର, ମୁଁ {company} ପାଇଁ ସ୍ୱୟଂଚାଳିତ ସହାୟକ {name} | ଗୁଣବତ୍ତା ପାଇଁ ଏହି କଲ୍ ରେକର୍ଡ କରାଯାଇପାରେ |",
};

export function getDisclosureText(lang: LanguageCode, assistantName: string, companyName: string): string {
    const tmpl = DISCLOSURE_TEMPLATES[lang] ?? DISCLOSURE_TEMPLATES["en-IN"];
    return tmpl.replace("{name}", assistantName || "…").replace("{company}", companyName || "…");
}

export const OUTCOMES: Record<CallOutcome, { label: string; tone: "good" | "neutral" | "warn" | "bad" }> = {
    lead_captured: { label: "Lead captured", tone: "good" },
    answered: { label: "Answered", tone: "neutral" },
    transferred: { label: "Transferred", tone: "neutral" },
    no_answer: { label: "No answer", tone: "warn" },
    voicemail: { label: "Voicemail", tone: "warn" },
    opted_out: { label: "Opted out", tone: "warn" },
    failed: { label: "Failed", tone: "bad" },
};

export const SENTIMENT: Record<Sentiment, { label: string; tone: "good" | "neutral" | "warn" }> = {
    positive: { label: "Positive", tone: "good" },
    neutral: { label: "Neutral", tone: "neutral" },
    negative: { label: "Negative", tone: "warn" },
};

/** Server timestamps are UTC; some arrive without a zone marker. */
export function parseUtc(iso: string) {
    return new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function formatDuration(sec: number) {
    if (!sec) return "–";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatINR(amount: number) {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
}

export function formatNumber(n: number) {
    return new Intl.NumberFormat("en-IN").format(n);
}

export function formatWhen(iso: string) {
    const d = parseUtc(iso);
    const diffMin = Math.round((Date.now() - d.getTime()) / 60_000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin} min ago`;
    const sameDay = new Date().toDateString() === d.toDateString();
    const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
    if (sameDay) return `Today, ${time}`;
    return `${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${time}`;
}

export function formatDate(iso: string) {
    return parseUtc(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** The two agents every assistant has (Voice > Agents). */
export const DIRECTIONS: Record<AgentDirection, { label: string; short: string; on: string; about: string }> = {
    inbound: {
        label: "Incoming calls", short: "Incoming", on: "Answering calls",
        about: "Answers people who call your number, from the assistant's knowledge and its incoming script.",
    },
    outbound: {
        label: "Outgoing calls", short: "Outgoing", on: "Making calls",
        about: "Calls people back when they ask for it in chat, and runs your campaigns, with its outgoing script.",
    },
};

export const directionOf = (value: string | null | undefined): AgentDirection => (value === "outbound" ? "outbound" : "inbound");
