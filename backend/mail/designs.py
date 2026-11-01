"""
The emails an assistant sends to customers, and how each looks (mail plan, phase 1): the ready-made design of each
kind, in English, Tamil and Hindi, until the business saves its own (EmailTemplate). A design is a subject and a list
of blocks; mail/render.py turns it into the email.

Blocks: text, heading, ai_note (a few sentences the AI writes for this person), call_summary (the after-call email's
recap, answers and next step), meeting (when and how to join), files, button, details (what they told us), transcript
(a chat), signature, divider, image. Text takes placeholders, with a fallback after a bar: {{first_name|there}}.
A button's action: book (a time with the team), call (a call-back), whatsapp, link (its url), join, change, cancel
(their meeting); one whose address isn't known for this email is left out.
"""
import unicodedata
from typing import Optional

LANGUAGES = {"en": "English", "ta": "Tamil", "hi": "Hindi", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi", "od": "Odia"}
SCRIPTS = {"en": "LATIN", "hi": "DEVANAGARI", "mr": "DEVANAGARI", "ta": "TAMIL", "te": "TELUGU", "kn": "KANNADA", "ml": "MALAYALAM",
           "bn": "BENGALI", "gu": "GUJARATI", "pa": "GURMUKHI", "od": "ORIYA"}
BLOCK_TYPES = ("text", "heading", "ai_note", "call_summary", "meeting", "files", "button", "details", "transcript",
               "signature", "divider", "image")
ACTIONS = ("book", "call", "whatsapp", "link", "join", "change", "cancel")
MAX_BLOCKS = 30


def _t(text: str) -> dict:
    return {"type": "text", "text": text}


def _button(label: str, action: str, url: str = "") -> dict:
    return {"type": "button", "label": label, "action": action, **({"url": url} if url else {})}


SIG, FILES, DIV = {"type": "signature"}, {"type": "files"}, {"type": "divider"}

KINDS: dict[str, dict] = {
    "welcome": {
        "label": "Welcome email", "about": "When someone gives their email in a chat (website or WhatsApp).",
        "placeholders": ["first_name", "name", "business", "assistant", "email", "phone", "details"],
        "designs": {
            "en": {"subject": "Thanks for contacting {{business}}", "blocks": [
                _t("Hi {{first_name|there}},\n\nThanks for your interest in {{business}}. Someone from our team will get in touch "
                   "with you shortly."),
                {"type": "ai_note", "guidance": "A sentence or two about what they asked about and how we can help."},
                FILES, _button("Book a time", "book"), _button("Chat on WhatsApp", "whatsapp"),
                _t("Any questions? Just reply to this email."), SIG]},
            "ta": {"subject": "{{business}} உடன் தொடர்பு கொண்டதற்கு நன்றி", "blocks": [
                _t("வணக்கம் {{first_name|}},\n\n{{business}} மீது நீங்கள் காட்டிய ஆர்வத்திற்கு நன்றி. எங்கள் குழுவில் ஒருவர் "
                   "விரைவில் உங்களைத் தொடர்பு கொள்வார்."),
                {"type": "ai_note", "guidance": "A sentence or two about what they asked about and how we can help."},
                FILES, _button("நேரம் பதிவு செய்ய", "book"), _button("WhatsApp-இல் பேச", "whatsapp"),
                _t("ஏதேனும் கேள்விகள் இருந்தால், இந்த மின்னஞ்சலுக்குப் பதில் அனுப்புங்கள்."), SIG]},
            "hi": {"subject": "{{business}} से संपर्क करने के लिए धन्यवाद", "blocks": [
                _t("नमस्ते {{first_name|}},\n\n{{business}} में आपकी रुचि के लिए धन्यवाद। हमारी टीम का कोई सदस्य जल्द ही आपसे "
                   "संपर्क करेगा।"),
                {"type": "ai_note", "guidance": "A sentence or two about what they asked about and how we can help."},
                FILES, _button("समय बुक करें", "book"), _button("WhatsApp पर बात करें", "whatsapp"),
                _t("कोई सवाल हो तो इस ईमेल का जवाब दें।"), SIG]},
        }},
    "after_call": {
        "label": "After a call", "about": "Written by the AI from each call: a recap, answers to their questions, the next step.",
        "placeholders": ["first_name", "name", "business", "assistant", "email", "phone"],
        "designs": {
            "en": {"subject": "Your call with {{business}}", "blocks": [
                _t("Hi {{first_name|there}},\n\nThank you for speaking with us. Here is a short note of our call."),
                {"type": "call_summary"}, FILES, _t("If anything here needs correcting, just reply to this email."), SIG]},
            "ta": {"subject": "{{business}} உடனான உங்கள் அழைப்பு", "blocks": [
                _t("வணக்கம் {{first_name|}},\n\nஎங்களுடன் பேசியதற்கு நன்றி. நம் உரையாடலின் சுருக்கம் கீழே உள்ளது."),
                {"type": "call_summary"}, FILES, _t("ஏதேனும் திருத்தம் தேவைப்பட்டால், இந்த மின்னஞ்சலுக்குப் பதில் அனுப்புங்கள்."), SIG]},
            "hi": {"subject": "{{business}} के साथ आपकी कॉल", "blocks": [
                _t("नमस्ते {{first_name|}},\n\nहमसे बात करने के लिए धन्यवाद। हमारी बातचीत का सार नीचे है।"),
                {"type": "call_summary"}, FILES, _t("कुछ ठीक करना हो तो इस ईमेल का जवाब दें।"), SIG]},
        }},
    "meeting": {
        "label": "Meeting emails", "about": "The confirmation, the day-before reminder, the joining details, and after it.",
        "placeholders": ["first_name", "name", "business", "meeting_text"],
        "designs": {
            "en": {"subject": "{{meeting_subject}}", "blocks": [
                _t("{{meeting_text}}"), {"type": "meeting"}, _button("Join the meeting", "join"),
                _button("Change the time", "change"), _button("Cancel", "cancel"), _button("Book another time", "book"), SIG]},
        }},
    "lead_email": {
        "label": "New lead from another place", "about": "When a lead comes in from a portal or a form and gave an email.",
        "placeholders": ["first_name", "name", "business", "portal", "wants"],
        "designs": {
            "en": {"subject": "Thanks for your enquiry to {{business}}", "blocks": [
                _t("Hi {{first_name|there}},\n\nThanks for your enquiry to {{business}}. We have your details, and someone from our team will get "
                   "in touch with you shortly."), FILES, _button("Book a time", "book"), _button("Chat on WhatsApp", "whatsapp"),
                _t("Any questions? Just reply to this email."), SIG]},
        }},
    "callback_booked": {
        "label": "Call-back booked", "about": "When a call-back is booked for them: on a call, in a chat or from an email.",
        "placeholders": ["first_name", "name", "business", "phone", "callback_when"],
        "designs": {
            "en": {"subject": "We'll call you {{callback_when}}", "blocks": [
                _t("Hi {{first_name|there}},\n\nAs you asked, we'll call you {{callback_when}} on {{phone}}."),
                _t("If that time doesn't suit you, just reply to this email."), SIG]},
        }},
    "voicemail": {
        "label": "Voicemail left", "about": "When we called them and reached their voicemail.",
        "placeholders": ["first_name", "name", "business", "phone"],
        "designs": {
            "en": {"subject": "We tried to call you", "blocks": [
                _t("Hi {{first_name|there}},\n\nWe tried calling you on {{phone}} and left a voicemail."),
                _button("Call me back", "call"), _t("You can also reply to this email."), SIG]},
        }},
    "missed_chat": {
        "label": "Missed live chat", "about": "When they asked for a person in the chat and nobody could reply in time.",
        "placeholders": ["first_name", "name", "business"],
        "designs": {
            "en": {"subject": "Sorry we missed you", "blocks": [
                _t("Hi {{first_name|there}},\n\nYou asked to talk to someone from our team, and we couldn't reply in time. "
                   "We'll get back to you soon."),
                _t("You can also reply to this email."), SIG]},
        }},
    "chat_copy": {
        "label": "Copy of the chat", "about": "When a visitor asks for a copy of their chat (a button in the chat).",
        "placeholders": ["business"],
        "designs": {
            "en": {"subject": "Your chat with {{business}}", "blocks": [
                _t("Here's a copy of your chat with {{business}}."), {"type": "transcript"}, SIG]},
        }},
    "question_answer": {
        "label": "The answer to their question", "about": "When your team answers a question the assistant couldn't, and sends it to the people who asked.",
        "placeholders": ["first_name", "name", "business", "question", "answer"],
        "designs": {
            "en": {"subject": "The answer to your question", "blocks": [
                _t("Hi {{first_name|there}},\n\nYou asked: {{question}}\n\n{{answer}}"), _t("You can also reply to this email."), SIG]},
        }},
    "during_call": {
        "label": "Sent during a call", "about": "When the phone agent emails a file or a note while they talk.",
        "placeholders": ["first_name", "name", "business"],
        "designs": {
            "en": {"subject": "As promised on our call", "blocks": [
                _t("Hi {{first_name|there}},\n\nAs promised on our call, here's what you asked for."),
                {"type": "ai_note", "guidance": "Only what the agent said it would send, in a sentence."}, FILES, SIG]},
        }},
}

# Words the blocks show by themselves, per language.
WORDS = {
    "en": {"talked": "What we talked about", "answers": "Your questions", "next": "Next step", "files": "Files",
           "download": "Download", "when": "When", "where": "Where", "join": "Joining link", "details": "What you told us",
           "team_replies": "Our team will reply to you about this."},
    "ta": {"talked": "நாம் பேசியவை", "answers": "உங்கள் கேள்விகள்", "next": "அடுத்த படி", "files": "கோப்புகள்",
           "download": "பதிவிறக்கு", "when": "எப்போது", "where": "எங்கே", "join": "இணைப்பு", "details": "நீங்கள் சொன்னவை",
           "team_replies": "இதற்கு எங்கள் குழு உங்களுக்குப் பதில் அளிக்கும்."},
    "hi": {"talked": "हमने क्या बात की", "answers": "आपके सवाल", "next": "अगला कदम", "files": "फ़ाइलें",
           "download": "डाउनलोड", "when": "कब", "where": "कहाँ", "join": "जुड़ने का लिंक", "details": "आपने हमें बताया",
           "team_replies": "इस बारे में हमारी टीम आपको जवाब देगी।"},
}

# The welcome and after-call frames in the other languages the phone agent speaks: (welcome subject, greeting line, thanks, book, WhatsApp, questions; call subject, thanks, corrections).
FRAMES = {
    "te": ("{{business}} ను సంప్రదించినందుకు ధన్యవాదాలు", "నమస్కారం {{first_name|}},", "{{business}} పట్ల మీ ఆసక్తికి ధన్యవాదాలు. మా బృందంలోని ఒకరు త్వరలో మిమ్మల్ని సంప్రదిస్తారు.", "సమయం బుక్ చేయండి",
           "WhatsApp లో మాట్లాడండి", "ఏవైనా ప్రశ్నలు ఉంటే, ఈ ఈమెయిల్‌కు సమాధానం ఇవ్వండి.", "{{business}} తో మీ కాల్", "మాతో మాట్లాడినందుకు ధన్యవాదాలు. మన సంభాషణ సారాంశం కింద ఉంది.",
           "ఇందులో ఏదైనా సరిదిద్దాలంటే, ఈ ఈమెయిల్‌కు సమాధానం ఇవ్వండి."),
    "kn": ("{{business}} ಅನ್ನು ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು", "ನಮಸ್ಕಾರ {{first_name|}},", "{{business}} ಬಗ್ಗೆ ನಿಮ್ಮ ಆಸಕ್ತಿಗೆ ಧನ್ಯವಾದಗಳು. ನಮ್ಮ ತಂಡದವರೊಬ್ಬರು ಶೀಘ್ರದಲ್ಲೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತಾರೆ.", "ಸಮಯವನ್ನು ಬುಕ್ ಮಾಡಿ",
           "WhatsApp ನಲ್ಲಿ ಮಾತನಾಡಿ", "ಏನಾದರೂ ಪ್ರಶ್ನೆಗಳಿದ್ದರೆ, ಈ ಇಮೇಲ್‌ಗೆ ಉತ್ತರಿಸಿ.", "{{business}} ಜೊತೆಗಿನ ನಿಮ್ಮ ಕರೆ", "ನಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನಮ್ಮ ಸಂಭಾಷಣೆಯ ಸಾರಾಂಶ ಕೆಳಗಿದೆ.",
           "ಇದರಲ್ಲಿ ಏನಾದರೂ ಸರಿಪಡಿಸಬೇಕಿದ್ದರೆ, ಈ ಇಮೇಲ್‌ಗೆ ಉತ್ತರಿಸಿ."),
    "ml": ("{{business}} മായി ബന്ധപ്പെട്ടതിന് നന്ദി", "നമസ്കാരം {{first_name|}},", "{{business}} നോടുള്ള നിങ്ങളുടെ താൽപ്പര്യത്തിന് നന്ദി. ഞങ്ങളുടെ ടീമിലെ ഒരാൾ ഉടൻ നിങ്ങളെ ബന്ധപ്പെടും.", "സമയം ബുക്ക് ചെയ്യുക",
           "WhatsApp-ൽ സംസാരിക്കുക", "എന്തെങ്കിലും ചോദ്യങ്ങളുണ്ടെങ്കിൽ, ഈ ഇമെയിലിന് മറുപടി നൽകുക.", "{{business}} യുമായുള്ള നിങ്ങളുടെ കോൾ", "ഞങ്ങളുമായി സംസാരിച്ചതിന് നന്ദി. നമ്മുടെ സംഭാഷണത്തിന്റെ ചുരുക്കം താഴെ കൊടുത്തിരിക്കുന്നു.",
           "ഇതിൽ എന്തെങ്കിലും തിരുത്തണമെങ്കിൽ, ഈ ഇമെയിലിന് മറുപടി നൽകുക."),
    "mr": ("{{business}} शी संपर्क साधल्याबद्दल धन्यवाद", "नमस्कार {{first_name|}},", "{{business}} मध्ये दाखवलेल्या रुचीबद्दल धन्यवाद. आमच्या टीममधील कोणीतरी लवकरच तुमच्याशी संपर्क साधेल.", "वेळ बुक करा",
           "WhatsApp वर बोला", "काही प्रश्न असल्यास, या ईमेलला उत्तर द्या.", "{{business}} सोबतचा तुमचा कॉल", "आमच्याशी बोलल्याबद्दल धन्यवाद. आपल्या संभाषणाचा सारांश खाली दिला आहे.",
           "यात काही दुरुस्ती हवी असल्यास, या ईमेलला उत्तर द्या."),
    "bn": ("{{business}}-এর সঙ্গে যোগাযোগ করার জন্য ধন্যবাদ", "নমস্কার {{first_name|}},", "{{business}}-এর প্রতি আপনার আগ্রহের জন্য ধন্যবাদ। আমাদের টিমের কেউ শীঘ্রই আপনার সঙ্গে যোগাযোগ করবেন।", "সময় বুক করুন",
           "WhatsApp-এ কথা বলুন", "কোনো প্রশ্ন থাকলে এই ইমেলের উত্তর দিন।", "{{business}}-এর সঙ্গে আপনার কল", "আমাদের সঙ্গে কথা বলার জন্য ধন্যবাদ। আমাদের কথোপকথনের সারসংক্ষেপ নিচে দেওয়া হলো।",
           "এতে কিছু সংশোধনের দরকার হলে এই ইমেলের উত্তর দিন।"),
    "gu": ("{{business}} નો સંપર્ક કરવા બદલ આભાર", "નમસ્તે {{first_name|}},", "{{business}} માં તમારી રુચિ બદલ આભાર. અમારી ટીમમાંથી કોઈ ટૂંક સમયમાં તમારો સંપર્ક કરશે.", "સમય બુક કરો",
           "WhatsApp પર વાત કરો", "કોઈ પ્રશ્ન હોય તો આ ઈમેલનો જવાબ આપો.", "{{business}} સાથેનો તમારો કૉલ", "અમારી સાથે વાત કરવા બદલ આભાર. અમારી વાતચીતનો સારાંશ નીચે છે.",
           "આમાં કંઈ સુધારવાનું હોય તો આ ઈમેલનો જવાબ આપો."),
    "pa": ("{{business}} ਨਾਲ ਸੰਪਰਕ ਕਰਨ ਲਈ ਧੰਨਵਾਦ", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {{first_name|}},", "{{business}} ਵਿੱਚ ਤੁਹਾਡੀ ਦਿਲਚਸਪੀ ਲਈ ਧੰਨਵਾਦ। ਸਾਡੀ ਟੀਮ ਦਾ ਕੋਈ ਮੈਂਬਰ ਜਲਦੀ ਹੀ ਤੁਹਾਡੇ ਨਾਲ ਸੰਪਰਕ ਕਰੇਗਾ।", "ਸਮਾਂ ਬੁੱਕ ਕਰੋ",
           "WhatsApp 'ਤੇ ਗੱਲ ਕਰੋ", "ਜੇ ਕੋਈ ਸਵਾਲ ਹੈ ਤਾਂ ਇਸ ਈਮੇਲ ਦਾ ਜਵਾਬ ਦਿਓ।", "{{business}} ਨਾਲ ਤੁਹਾਡੀ ਕਾਲ", "ਸਾਡੇ ਨਾਲ ਗੱਲ ਕਰਨ ਲਈ ਧੰਨਵਾਦ। ਸਾਡੀ ਗੱਲਬਾਤ ਦਾ ਸਾਰ ਹੇਠਾਂ ਹੈ।",
           "ਜੇ ਇਸ ਵਿੱਚ ਕੁਝ ਠੀਕ ਕਰਨਾ ਹੋਵੇ ਤਾਂ ਇਸ ਈਮੇਲ ਦਾ ਜਵਾਬ ਦਿਓ।"),
    "od": ("{{business}} ସହ ଯୋଗାଯୋଗ କରିଥିବାରୁ ଧନ୍ୟବାଦ", "ନମସ୍କାର {{first_name|}},", "{{business}} ପ୍ରତି ଆପଣଙ୍କ ଆଗ୍ରହ ପାଇଁ ଧନ୍ୟବାଦ। ଆମ ଟିମ୍‌ର ଜଣେ ଶୀଘ୍ର ଆପଣଙ୍କ ସହ ଯୋଗାଯୋଗ କରିବେ।", "ସମୟ ବୁକ୍ କରନ୍ତୁ",
           "WhatsApp ରେ କଥା ହୁଅନ୍ତୁ", "କୌଣସି ପ୍ରଶ୍ନ ଥିଲେ ଏହି ଇମେଲର ଉତ୍ତର ଦିଅନ୍ତୁ।", "{{business}} ସହ ଆପଣଙ୍କ କଲ୍", "ଆମ ସହ କଥା ହୋଇଥିବାରୁ ଧନ୍ୟବାଦ। ଆମ କଥାବାର୍ତ୍ତାର ସାରାଂଶ ତଳେ ଅଛି।",
           "ଏଥିରେ କିଛି ସଂଶୋଧନ ଦରକାର ହେଲେ ଏହି ଇମେଲର ଉତ୍ତର ଦିଅନ୍ତୁ।"),
}
WORDS.update({
    "te": {"talked": "మనం మాట్లాడినది", "answers": "మీ ప్రశ్నలు", "next": "తదుపరి అడుగు", "files": "ఫైళ్లు", "download": "డౌన్‌లోడ్", "when": "ఎప్పుడు", "where": "ఎక్కడ", "join": "చేరే లింక్",
           "details": "మీరు చెప్పినది", "team_replies": "దీని గురించి మా బృందం మీకు సమాధానం ఇస్తుంది."},
    "kn": {"talked": "ನಾವು ಮಾತನಾಡಿದ್ದು", "answers": "ನಿಮ್ಮ ಪ್ರಶ್ನೆಗಳು", "next": "ಮುಂದಿನ ಹಂತ", "files": "ಫೈಲ್‌ಗಳು", "download": "ಡೌನ್‌ಲೋಡ್", "when": "ಯಾವಾಗ", "where": "ಎಲ್ಲಿ", "join": "ಸೇರುವ ಲಿಂಕ್",
           "details": "ನೀವು ಹೇಳಿದ್ದು", "team_replies": "ಈ ಬಗ್ಗೆ ನಮ್ಮ ತಂಡ ನಿಮಗೆ ಉತ್ತರಿಸುತ್ತದೆ."},
    "ml": {"talked": "നമ്മൾ സംസാരിച്ചത്", "answers": "നിങ്ങളുടെ ചോദ്യങ്ങൾ", "next": "അടുത്ത ഘട്ടം", "files": "ഫയലുകൾ", "download": "ഡൗൺലോഡ്", "when": "എപ്പോൾ", "where": "എവിടെ", "join": "ചേരാനുള്ള ലിങ്ക്",
           "details": "നിങ്ങൾ പറഞ്ഞത്", "team_replies": "ഇതിനെക്കുറിച്ച് ഞങ്ങളുടെ ടീം നിങ്ങൾക്ക് മറുപടി നൽകും."},
    "mr": {"talked": "आपण काय बोललो", "answers": "तुमचे प्रश्न", "next": "पुढील पाऊल", "files": "फायली", "download": "डाउनलोड", "when": "कधी", "where": "कुठे", "join": "सामील होण्याची लिंक",
           "details": "तुम्ही सांगितलेले", "team_replies": "याबद्दल आमची टीम तुम्हाला उत्तर देईल."},
    "bn": {"talked": "আমরা যা কথা বললাম", "answers": "আপনার প্রশ্ন", "next": "পরবর্তী ধাপ", "files": "ফাইল", "download": "ডাউনলোড", "when": "কখন", "where": "কোথায়", "join": "যোগ দেওয়ার লিঙ্ক",
           "details": "আপনি যা জানিয়েছেন", "team_replies": "এ বিষয়ে আমাদের টিম আপনাকে উত্তর দেবে।"},
    "gu": {"talked": "આપણે શું વાત કરી", "answers": "તમારા પ્રશ્નો", "next": "આગળનું પગલું", "files": "ફાઇલો", "download": "ડાઉનલોડ", "when": "ક્યારે", "where": "ક્યાં", "join": "જોડાવાની લિંક",
           "details": "તમે જણાવેલું", "team_replies": "આ વિશે અમારી ટીમ તમને જવાબ આપશે."},
    "pa": {"talked": "ਅਸੀਂ ਕੀ ਗੱਲ ਕੀਤੀ", "answers": "ਤੁਹਾਡੇ ਸਵਾਲ", "next": "ਅਗਲਾ ਕਦਮ", "files": "ਫ਼ਾਈਲਾਂ", "download": "ਡਾਊਨਲੋਡ", "when": "ਕਦੋਂ", "where": "ਕਿੱਥੇ", "join": "ਜੁੜਨ ਦਾ ਲਿੰਕ",
           "details": "ਤੁਸੀਂ ਦੱਸਿਆ", "team_replies": "ਇਸ ਬਾਰੇ ਸਾਡੀ ਟੀਮ ਤੁਹਾਨੂੰ ਜਵਾਬ ਦੇਵੇਗੀ।"},
    "od": {"talked": "ଆମେ କ'ଣ କଥା ହେଲୁ", "answers": "ଆପଣଙ୍କ ପ୍ରଶ୍ନ", "next": "ପରବର୍ତ୍ତୀ ପଦକ୍ଷେପ", "files": "ଫାଇଲ୍", "download": "ଡାଉନଲୋଡ୍", "when": "କେବେ", "where": "କେଉଁଠି", "join": "ଯୋଗଦେବା ଲିଙ୍କ୍",
           "details": "ଆପଣ ଜଣାଇଥିବା କଥା", "team_replies": "ଏ ବିଷୟରେ ଆମ ଟିମ୍ ଆପଣଙ୍କୁ ଉତ୍ତର ଦେବ।"},
})
for code, (subject, hello, thanks, book, whatsapp, questions, call_subject, call_thanks, corrections) in FRAMES.items():
    KINDS["welcome"]["designs"][code] = {"subject": subject, "blocks": [
        _t(f"{hello}\n\n{thanks}"), {"type": "ai_note", "guidance": "A sentence or two about what they asked about and how we can help."},
        FILES, _button(book, "book"), _button(whatsapp, "whatsapp"), _t(questions), SIG]}
    KINDS["after_call"]["designs"][code] = {"subject": call_subject, "blocks": [_t(f"{hello}\n\n{call_thanks}"), {"type": "call_summary"}, FILES, _t(corrections), SIG]}


def default(kind: str, language: str = "en") -> dict:
    """The ready-made design: in the language when it has one, else English."""
    designs = KINDS[kind]["designs"]
    d = designs.get(language) or designs["en"]
    return {"subject": d["subject"], "blocks": [dict(b) for b in d["blocks"]], "language": language if language in designs else "en"}


def clean(blocks: list) -> list[dict]:
    """What a business saved, kept to known blocks and fields (they're shown to customers)."""
    out = []
    for b in (blocks or [])[:MAX_BLOCKS]:
        if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
            continue
        kind = b["type"]
        item: dict = {"type": kind}
        if kind in ("text", "heading"):
            item["text"] = str(b.get("text") or "")[:5000]
        elif kind == "ai_note":
            item["guidance"] = str(b.get("guidance") or "")[:500]
        elif kind == "button":
            action = b.get("action") if b.get("action") in ACTIONS else "link"
            item.update(label=str(b.get("label") or "")[:60], action=action)
            if action == "link":
                item["url"] = str(b.get("url") or "")[:500]
        elif kind == "image":
            item.update(url=str(b.get("url") or "")[:500], alt=str(b.get("alt") or "")[:200])
        out.append(item)
    return out


def written_in(text: Optional[str], language: str) -> bool:
    """Whether text is really in a language ("ta" or "ta-IN"), by its script: mostly that script, with next to nothing from another
    Indian one (English brand names are fine). Models drift: on real calls (Nov 2026) a Tamil call got an email half in Hindi and
    half in English, and the model checking it called it fine."""
    script = SCRIPTS.get((language or "en").split("-")[0])
    names = [unicodedata.name(ch, "").split(" ")[0] for ch in text or "" if ch.isalpha() or unicodedata.category(ch).startswith("M")]
    if script is None or not names:
        return True
    own = names.count(script) / len(names)
    if script == "LATIN":
        return own >= 0.8
    return own >= 0.5 and (len(names) - names.count(script) - names.count("LATIN")) / len(names) <= 0.1


def script_of(text: Optional[str]) -> str:
    """The language code of the script someone wrote in (of the languages in SCRIPTS), else "en"."""
    names = [unicodedata.name(ch, "").split(" ")[0] for ch in text or "" if ch.isalpha()]
    found = {script: names.count(script) for script in set(SCRIPTS.values()) if script != "LATIN"}
    best = max(found, key=found.get)
    return next(k for k, v in SCRIPTS.items() if v == best) if found[best] >= 3 and found[best] >= names.count("LATIN") / 2 else "en"


def language_of(text: Optional[str]) -> str:
    """The script someone wrote or spoke in, else English (Tanglish stays English). Devanagari is Hindi: Marathi looks the same, and only a call's language can tell them apart."""
    return script_of(text)
