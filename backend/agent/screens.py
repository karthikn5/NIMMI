"""
The dashboard's screens as the agent knows them: what each is for and what's on it (written from the pages
themselves, Oct 2026), where `go_to` can take the person, and what `point_at` can highlight.

The panel says which screen is open by its id (dashboard/src/lib/agent/screens.ts maps routes to the same ids). The
open screen's notes go with every answer, so a question about "this page" needs no lookup. When a page changes,
change its notes here.
"""
import re
from typing import Optional

SCREENS: dict[str, dict] = {
    "assistants": {"title": "Assistants", "path": "/dashboard", "about": (
        "The list of their assistants (the home page). Each card opens the builder; Preview tries it; New assistant "
        "makes one (from an industry template or blank). The free plan includes one assistant. Recently deleted "
        "assistants can be restored here.")},
    "builder": {"title": "Assistant builder", "path": "/dashboard/builder/{assistant}", "about": (
        "One assistant, in tabs: Design, Knowledge, Behaviour, Flow, Leads. Changes save by themselves (the top bar "
        "shows Saved / Saving). Test opens the demo page; 'Add to website' gives the install code (one line, or the "
        "WordPress plugin)."), "tabs": {
        "design": ("How the chat looks: Brand (assistant name, avatar, brand colour, font), Header, Colours (bubbles, "
                   "chat background, message box), Background image, Launcher (shape: circle, rounded, square, pill or "
                   "a standing Character, including Violet, animated; icon size, distance from the side and the "
                   "bottom, a greeting beside the launcher, opening by itself after some seconds), which pages it shows "
                   "on, Hide on phones, and 'Let visitors switch to a person'."),
        "knowledge": ("What the assistant answers from: Website (an address, and how many pages to read), Document "
                      "(PDF and other files), YouTube video, and Written knowledge (text they type). 'What it knows' "
                      "lists the sources; a source can be removed. Also the AI model (provider, model, their own API key, "
                      "optional) and the questions it couldn't answer."),
        "behaviour": ("How it replies: Instructions (what it should do and avoid), reply length, language, what to say "
                      "when it doesn't know, offering a person when it can't help; Collect visitor details (name, phone, "
                      "email and up to six of their own, and when to ask); business hours and escalation; letting "
                      "visitors rate answers; learning from visitors."),
        "flow": ("Guided steps that run before the AI answers: blocks on a canvas (messages, choices, questions for "
                 "name/phone/email/dates, images, videos, ratings, hand-over to a person, webhooks, Slack, Google "
                 "Sheets). Drag blocks from the left, connect them, select one to edit it on the right."),
        "leads": "The details visitors left (name, phone, email and the custom fields), with search.",
    }},
    "deployments": {"title": "Deployments", "path": "/dashboard/deployments", "about": (
        "Websites they host with Nimmi: upload a site (New deployment), see their websites, restore recently deleted "
        "ones. Paid plans can use their own domain.")},
    "deployment": {"title": "A deployed website", "about": (
        "One hosted website: its versions, settings, the assistant shown on it, a custom domain, and deleting it.")},
    "live_chat": {"title": "Live chat", "path": "/dashboard/live-chat", "about": (
        "Chats where a visitor asked for a person ('Talk to a person' in the widget, or WhatsApp). The team picks a "
        "conversation and replies; 'Nobody is waiting' when the list is empty. The Live chat menu shows a count of "
        "people waiting.")},
    "questions": {"title": "Questions", "path": "/dashboard/questions", "about": (
        "Questions their assistants couldn't answer (from chats, WhatsApp and calls), most asked first. 'Add an "
        "answer' teaches the assistant: it uses that answer from then on. Questions can be dismissed. Owners and "
        "admins only.")},
    "voice_overview": {"title": "Voice: Overview", "path": "/dashboard/voice", "about": (
        "The phone agent at a glance: voice credits left (Buy credits), calls per day, recent calls, and the setup "
        "steps (choose a voice, test in the browser, get a number, turn on call-backs).")},
    "voice_agents": {"title": "Voice: Agents", "path": "/dashboard/voice/agents", "about": (
        "Pick an assistant to set up its phone agent, for incoming calls (people who call their number) or outgoing "
        "calls (call-backs and campaigns).")},
    "voice_agent": {"title": "Voice agent settings", "path": "/dashboard/voice/agents/{assistant}", "about": (
        "One assistant's phone agent, for incoming or outgoing calls ('Which agent'). The toolbar: Voice, Language, AI "
        "model (quick and low cost, or smarter; each shows its credits a minute). Settings: what it introduces itself "
        "as, languages (reply in the caller's language, languages it can switch to, understand mixed language), "
        "speaking speed, background sound, letting callers interrupt, if the caller goes quiet, longest call, phrases "
        "that end the call, transfer to a person (how to hand over), if voicemail answers, remember callers, "
        "pronunciation, Functions (its own web links or Cal.com, used during calls), and 'Test on a real phone' (Call "
        "me). What it says (opening, script) is on Voice > Knowledge.")},
    "voice_knowledge": {"title": "Voice: Knowledge", "path": "/dashboard/voice/knowledge", "about": (
        "Pick an assistant to edit what its phone agent says.")},
    "voice_script": {"title": "Voice script", "path": "/dashboard/voice/knowledge/{assistant}", "about": (
        "What the phone agent says, for incoming and outgoing calls: opening line (and one for callers it already "
        "knows), personality, instructions, goal of the call, information to collect. 'Write with AI' drafts it "
        "from a few questions. The facts it answers from are the assistant's own knowledge (builder > Knowledge).")},
    "voice_contacts": {"title": "Voice: Contacts", "path": "/dashboard/voice/contacts", "about": (
        "Callers the phone agent remembers (by number, per assistant): name, calls, notes, lead rating (hot, warm, "
        "cold), follow-ups. A caller can be forgotten.")},
    "voice_calls": {"title": "Voice: Calls", "path": "/dashboard/voice/calls", "about": (
        "Every call: direction, how it went, recording, transcript, summary, credits used, and the AI model that "
        "answered.")},
    "voice_schedule": {"title": "Voice: Schedule", "path": "/dashboard/voice/schedule", "about": (
        "Calls the agent plans: call-backs callers ask for, follow-ups by lead rating, and meetings the team approves. "
        "Tabs: Coming up (what needs them: meetings to approve, follow-ups to check, people who asked for a person), "
        "Meetings, Calls, Settings (all off until turned on, per assistant: calling hours and days, call-back hours "
        "and attempts, follow-up rules by rating, meeting length, days, hours, approval, link, reminders).")},
    "voice_campaigns": {"title": "Voice: Campaigns", "path": "/dashboard/voice/campaigns", "about": (
        "Calling a list: upload people who agreed to be called, and the assistant calls everyone on the list, one by "
        "one.")},
    "voice_campaign": {"title": "A campaign", "about": "One campaign: the people on its list, how each call went, and stopping it."},
    "voice_data": {"title": "Voice: Collected data", "path": "/dashboard/voice/data", "about": (
        "The details the phone agent collected on calls (the fields set in its script), per assistant.")},
    "voice_numbers": {"title": "Voice: Numbers", "path": "/dashboard/voice/numbers", "about": (
        "Phone numbers for calls: get a new one (US, UK, Canada and Australia are instant; Indian numbers come "
        "through Exotel and need business documents: Certificate of Incorporation and GST), or connect their own "
        "Twilio or Exotel account; choose which assistant answers each number; call back new leads.")},
    "voice_compliance": {"title": "Voice: Compliance", "path": "/dashboard/voice/compliance", "about": (
        "Calling rules: the do-not-call list (add numbers), how calls and recordings are kept, and erasing a caller's "
        "data.")},
    "whatsapp_overview": {"title": "WhatsApp: Overview", "path": "/dashboard/whatsapp", "about": (
        "WhatsApp at a glance: their numbers, this month's chats and replies, and the setup steps.")},
    "whatsapp_inbox": {"title": "WhatsApp: Inbox", "path": "/dashboard/whatsapp/inbox", "about": (
        "WhatsApp chats with customers. The team can reply (inside WhatsApp's 24-hour window); that pauses the "
        "assistant on that chat until 'Hand back'.")},
    "whatsapp_assistant": {"title": "WhatsApp: Assistant", "path": "/dashboard/whatsapp/assistant", "about": (
        "How the assistant replies on WhatsApp: like a person on their team (waits for the customer to finish, short "
        "messages), what it can do (voice notes, photos, PDFs, files, buttons), and when the team steps in.")},
    "whatsapp_files": {"title": "WhatsApp: Files", "path": "/dashboard/whatsapp/files", "about": (
        "Brochures, price lists, menus and photos the assistant can send on WhatsApp, each with when to send it.")},
    "whatsapp_settings": {"title": "WhatsApp: Settings", "path": "/dashboard/whatsapp/settings", "about": (
        "Connecting a WhatsApp number (from their own Meta app for now: token and app secret), replacing a token or "
        "secret, sending a test message, disconnecting, and WhatsApp messages after phone calls. Owners and admins.")},
    "integrations": {"title": "Integrations", "path": "/dashboard/integrations", "about": (
        "What happens after chats and calls (paid plans): lead alerts and emails to customers, WhatsApp messages, "
        "webhooks and LeadSquared, each on or off, with their recent activity. Owners and admins.")},
    "analytics": {"title": "Analytics", "path": "/dashboard/analytics", "about": (
        "Chats, leads, hand-overs and calls over the last 7 to 90 days, per day and per assistant.")},
    "billing": {"title": "Billing", "path": "/dashboard/billing", "about": (
        "Plans for each assistant (Choose a plan), voice credits and their packs, call rates, the Nimmi balance, and "
        "payment history. Owners only.")},
    "profile": {"title": "Profile", "path": "/dashboard/profile", "about": (
        "Their name and email, changing their password, and signing out of all other devices.")},
    "team": {"title": "Team", "path": "/dashboard/team", "about": (
        "People in their workspace: invite someone as an admin (manages assistants, voice and integrations) or an "
        "agent (live chat and calls only), or share the invite link. Owners only.")},
}

# What point_at can highlight: names the pages put on their elements (data-agent="...").
POINTS = {
    **{f"nav.{k}": f"the {v} menu in the top bar" for k, v in (
        ("assistants", "Assistants"), ("deployments", "Deployments"), ("live_chat", "Live chat"),
        ("questions", "Questions"), ("voice", "Voice"), ("whatsapp", "WhatsApp"), ("integrations", "Integrations"),
        ("analytics", "Analytics"), ("billing", "Billing"))},
    **{f"builder.tab.{k}": f"the builder's {k.capitalize()} tab" for k in ("design", "knowledge", "behaviour", "flow", "leads")},
    "builder.test": "the builder's Test button", "builder.install": "the builder's 'Add to website' button",
    "voice.use_own_number": "Voice > Numbers: Use your own number (Twilio or Exotel)", "voice.get_number": "Voice > Numbers: Get a number",
    "whatsapp.connect": "WhatsApp > Settings: Connect a number",
    **{f"voice.tab.{k}": f"the Voice {v} tab" for k, v in (
        ("overview", "Overview"), ("agents", "Agents"), ("knowledge", "Knowledge"), ("contacts", "Contacts"),
        ("calls", "Calls"), ("schedule", "Schedule"), ("campaigns", "Campaigns"), ("data", "Collected data"),
        ("numbers", "Numbers"), ("compliance", "Compliance"))},
    **{f"whatsapp.tab.{k}": f"the WhatsApp {v} tab" for k, v in (
        ("overview", "Overview"), ("inbox", "Inbox"), ("assistant", "Assistant"), ("files", "Files"), ("settings", "Settings"))},
}


def notes(screen: dict) -> Optional[str]:
    """The open screen's notes, for the model."""
    s = SCREENS.get(screen.get("id") or "")
    if s is None:
        return None
    text = f"About this screen ({s['title']}): {s['about']}"
    tab = s.get("tabs", {}).get(screen.get("tab") or "")
    if tab:
        text += f"\nThe open tab ({screen['tab'].capitalize()}): {tab}"
    return text


def pages() -> dict[str, str]:
    """Where go_to can take them: screen id -> path ({assistant} filled in by the tool)."""
    return {sid: s["path"] for sid, s in SCREENS.items() if s.get("path")}


# Each area's tools come on its own screens (a tool's `screens`), so the model reads a few hundred words of tools, not
# thousands; go_to into another area brings that area's tools in the same answer (loop.py).
AREAS = {
    "assistant": ("assistants", "builder", "questions", "deployments", "deployment", "live_chat", "analytics"),
    "voice": tuple(k for k in SCREENS if k.startswith("voice_")),
    "whatsapp": tuple(k for k in SCREENS if k.startswith("whatsapp_")),
    "account": ("integrations", "billing", "profile", "team"),
}


def screen_for_path(path: str) -> dict:
    """The screen a dashboard path opens (for go_to): {"path", "id", "title"} and the tab or direction in it."""
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(path)
    query = parse_qs(parts.query)
    best = None
    for sid, s in SCREENS.items():
        pattern = s.get("path")
        if not pattern:
            continue
        regex = "^" + re.escape(pattern).replace(re.escape("{assistant}"), "([^/]+)") + "/?$"
        m = re.match(regex, parts.path)
        if m:
            best = {"path": parts.path, "id": sid, "title": s["title"]}
            if m.groups():
                best["entity"] = {"kind": "assistant", "id": m.group(1)}
            break
    best = best or {"path": parts.path, "id": "other", "title": "Dashboard"}
    if query.get("tab"):
        best["tab"] = query["tab"][0]
    if query.get("direction"):
        best["details"] = {"direction": query["direction"][0]}
    return best
