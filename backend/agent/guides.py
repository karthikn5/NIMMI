"""
Step-by-step guides for what only the business can do: get keys from another company's console and paste them into
Nimmi's own form (phase 4). The secret never goes through the agent: the guide ends at the form, which checks the keys
with the provider and stores them encrypted. Click paths checked against each provider's current help pages (Oct 2026);
the last steps use the words Nimmi's forms use. When a console changes, change it here.
"""
GUIDES = {
    "twilio": {
        "title": "Connect your Twilio account",
        "why": "Calls through your own Twilio numbers (US, UK, Canada, Australia and more).",
        "link": "https://console.twilio.com", "link_label": "Open the Twilio Console",
        "form": "/dashboard/voice/numbers?connect=1", "form_label": "Voice > Numbers > Use your own number",
        "steps": [
            "Sign in to the Twilio Console (console.twilio.com).",
            "On the Console's home page, find the Account Info box. Copy the Account SID: it starts with AC.",
            "In the same box, click the eye icon next to Auth Token to show it, and copy it. Keep it private, like a password.",
            "In Nimmi, open Voice > Numbers and click Use your own number, then Twilio. Paste the Account SID and Auth "
            "token and save: Nimmi checks them with Twilio straight away and stores them encrypted.",
            "Pick the Twilio numbers your assistant should answer and call from, and choose the assistant under Answered by.",
        ],
        "note": "No number in Twilio yet? Buy one there (Phone Numbers > Manage > Buy a number), or get one from Nimmi "
                "on Voice > Numbers > Get a number.",
    },
    "exotel": {
        "title": "Connect your Exotel account",
        "why": "Calls through your own Indian ExoPhone numbers.",
        "link": "https://my.exotel.com", "link_label": "Open Exotel (Mumbai accounts: my.mum1.exotel.com)",
        "form": "/dashboard/voice/numbers?connect=1", "form_label": "Voice > Numbers > Use your own number",
        "steps": [
            "Sign in to Exotel: my.exotel.com, or my.mum1.exotel.com if your account is in the Mumbai region.",
            "Open Settings > API Settings. Copy the Account SID, the API key and the API token. If there's no key yet, "
            "click Create: the token is shown only once, so copy it then.",
            "Note your region: Singapore accounts use api.exotel.com, Mumbai accounts api.in.exotel.com.",
            "In Nimmi, open Voice > Numbers, click Use your own number, then Exotel. Choose the region and paste the "
            "three keys: Nimmi checks them and stores them encrypted. It then shows a voicebot address and a passthru address.",
            "In Exotel, open App Bazaar and create a new flow. Add a Voicebot applet with Nimmi's voicebot address. After "
            "it, add a Passthru applet with the passthru address; for its 200 OK branch add a Connect applet that dials "
            "the number from the transfer address, otherwise Hangup. Save the flow.",
            "Copy the flow's ID (the number at the end of the flow's address) into Nimmi's Flow ID, add your ExoPhone "
            "numbers, and save. In Exotel, set your ExoPhone to use this flow.",
        ],
        "note": "Indian numbers need your business documents (the Certificate of Incorporation and the GST certificate), "
                "as telecom rules require.",
    },
    "whatsapp": {
        "title": "Connect your WhatsApp number",
        "why": "Your assistant answers on your own WhatsApp Business number, through Meta's official platform.",
        "link": "https://developers.facebook.com/apps", "link_label": "Open your Meta apps",
        "form": "/dashboard/whatsapp/settings?connect=1", "form_label": "WhatsApp > Settings > Connect a number",
        "steps": [
            "Open developers.facebook.com > My Apps > your app > WhatsApp > API Setup. Copy the Phone number ID (under "
            "your number) and the WhatsApp Business Account ID (above it).",
            "Make a token that doesn't expire: open business.facebook.com > Settings > Users > System users. Add a system "
            "user (Admin), then Assign assets: your app and your WhatsApp account, both with Full control.",
            "Still on that system user, click Generate token: choose your app, tick whatsapp_business_messaging and "
            "whatsapp_business_management, choose no expiry, and copy the token (it starts with EAA; it's shown only once).",
            "Copy the app secret: developers.facebook.com > your app > App settings > Basic > App secret > Show.",
            "In Nimmi, open WhatsApp > Settings and click Connect a number. Paste the phone number ID, the account ID, "
            "the access token and the app secret, and choose the assistant that answers.",
            "Back in your Meta app: WhatsApp > Configuration > Webhook > Edit. Paste the Callback URL and the Verify token "
            "Nimmi shows on WhatsApp > Settings, click Verify and save, then subscribe to messages under Webhook fields.",
            "In Nimmi, click Send a test message to check it end to end.",
        ],
        "note": "Meta charges for template messages sent outside WhatsApp's 24-hour window; replies to customers inside "
                "it are free.",
    },
    "calcom": {
        "title": "Let the phone agent book on Cal.com",
        "why": "During a call, the agent checks your free times and books the meeting in your Cal.com calendar.",
        "link": "https://app.cal.com/settings/developer/api-keys", "link_label": "Open Cal.com API keys",
        "form": None, "form_label": "Voice > Agents > your assistant > Functions",
        "steps": [
            "In Cal.com, open Settings > Developer > API keys and click New. Name it Nimmi, choose Never expires, click "
            "Create, and copy the key: it starts with cal_live_ and is shown only once.",
            "Open Event Types and click the meeting the agent should book. Its ID is the number in the page's address "
            "(…/event-types/123456).",
            "In Nimmi, open Voice > Agents, pick the assistant, and under Functions add Check calendar and Book on "
            "calendar. Paste the Cal.com API key and the Event type ID, choose your Time zone, and save.",
            "Click Test it on each to check them before a real call.",
        ],
        "note": "The key acts as you in Cal.com, so keep it private. Nimmi stores it encrypted and shows it masked.",
    },
}


def guide(provider: str, assistant_id: str = "") -> dict:
    g = dict(GUIDES[provider])
    if provider == "calcom" and assistant_id:
        g["form"] = f"/dashboard/voice/agents/{assistant_id}?direction=inbound"
    return g
