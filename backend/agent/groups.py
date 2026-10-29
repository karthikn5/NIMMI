"""
The tools in small groups by what they're for, so an answer carries only the ones it needs: the first look at the
message (agent/intake.py) names the groups, the model can bring in more with load_tools, and CORE is always there.
Fewer tools mean fewer tokens on every round (a free tier counts tokens per minute: Groq refuses a request over
7,000-8,000 tokens on some models) and a model that picks the right tool more often. When the first look couldn't
run, an answer gets the open page's tools as before (registry.available). A test checks every tool is in CORE or a
group.
"""
CORE = ("update_plan", "load_tools", "go_to", "point_at", "list_assistants", "get_assistant")

GROUPS: dict[str, tuple[str, str]] = {  # name -> (what it's for, its tools)
    "design": ("an assistant's look: name, colours, font, launcher, welcome message, suggested questions",
               "update_assistant_design"),
    "knowledge": ("what an assistant answers from: facts, a website, removing a source",
                  "add_knowledge_text add_website_to_knowledge remove_knowledge_source"),
    "behaviour": ("an assistant's instructions and reply settings (length, language, the details it collects)",
                  "update_instructions update_reply_settings"),
    "flow": ("an assistant's flow, its guided start: reading it, changing it, a new one drafted from its knowledge",
             "get_flow write_flow draft_flow edit_flow_block"),
    "copy": ("setting one assistant up like another", "copy_assistant_settings"),
    "assistants": ("making a new assistant from a website, deleting or restoring one",
                   "start_agent_builder delete_assistant restore_assistant"),
    "results": ("leads, unanswered questions and their answers, analytics, live chat, hosted websites",
                "get_leads get_unanswered_questions answer_question dismiss_question analytics_summary live_chat_waiting websites"),
    "voice_agent": ("phone agents: their settings, voice, language, AI model and scripts; turning calls on or off",
                    "get_voice_agent update_voice_agent voice_options get_voice_script update_voice_script set_voice_calls"),
    "calls": ("phone calls, voice credits, callers, campaigns", "voice_overview recent_calls get_call voice_contacts campaigns"),
    "schedule": ("Schedule: call-backs, follow-ups and meetings", "get_schedule update_schedule schedule_planned"),
    "numbers": ("phone numbers and which assistant answers each", "phone_numbers assign_number"),
    "whatsapp": ("WhatsApp numbers and chats", "whatsapp_status whatsapp_chats update_whatsapp_number"),
    "connect": ("connecting WhatsApp, a phone number (Twilio or Exotel) or Cal.com, and what's connected now",
                "connection_guide connection_status"),
    "account": ("the plan and its limits, the team, business hours",
                "plan_and_limits team_members invite_teammate business_hours update_business_hours"),
}


def tools_of(groups) -> set[str]:
    return {name for g in groups if g in GROUPS for name in GROUPS[g][1].split()}


def described() -> str:
    """The groups for a model to choose from: "design (an assistant's look: ...); knowledge (...)"."""
    return "; ".join(f"{name} ({words})" for name, (words, _) in GROUPS.items())
