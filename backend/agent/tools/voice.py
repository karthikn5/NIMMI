"""Tools about the phone agent: the voice overview, an agent's settings, recent calls, Schedule, phone numbers."""
from auth import get_owned_bot
from agent.screens import AREAS
from agent.registry import tool, untrusted

DIRECTION = {"type": "string", "enum": ["inbound", "outbound"],
             "description": "inbound: people who call their number; outbound: call-backs and campaigns."}
AGENT_FIELDS = ("enabled", "language", "voice_id", "follow_caller_language", "switch_languages", "understand_code_mixed",
                "remember_callers", "speaking_rate", "assistant_name", "company_name", "greeting", "allow_interruptions",
                "silence_timeout_sec", "max_call_minutes", "transfer_enabled", "transfer_when", "end_call_phrases",
                "call_goal", "collect_fields", "ambience", "voicemail_action")


@tool("voice_overview", "The phone agent at a glance: voice credits left, calls this month and last, average call "
      "length, leads from calls, and which setup steps are done.", "Looking at voice", routes=("GET /api/voice/overview",))
async def voice_overview(tc, db):
    from voice.router import overview
    o = await overview(ctx=tc.ctx, db=db)
    return {k: o.get(k) for k in ("credits_left", "credits_included", "credits_used", "cycle_ends", "calls_this_month",
                                  "calls_last_month", "avg_duration_sec", "leads_captured", "setup", "engine_ready",
                                  "phone_ready")}


@tool("get_voice_agent", "One assistant's phone agent for incoming or outgoing calls: voice, language, AI model and "
      "its credits a minute, opening, transfer, call rules.", "Reading the voice agent",
      {"type": "object", "required": ["assistant_id"], "properties": {
          "assistant_id": {"type": "string"}, "direction": DIRECTION}},
      routes=("GET /api/voice/agents", "GET /api/voice/agents/{bot_id}", "GET /api/voice/agents/{bot_id}/details"), screens=AREAS["voice"])
async def get_voice_agent(tc, db, assistant_id, direction="inbound"):
    from voice import ai_models
    from voice.router import get_agent
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    agent = await get_agent(bot.bot_id, direction=direction, ctx=tc.ctx, db=db)
    out = {k: agent[k] for k in AGENT_FIELDS if k in agent}
    out["transfer_number"] = "set" if agent.get("transfer_number") else "not set"
    # From the catalog, not the agent page's summary route: that one writes the business summary with AI when missing.
    model = ai_models.call_model(agent.get("ai_model"))
    out["ai_model"] = {"name": model.name, "kind": ai_models.GROUPS[model.group],
                       "credits_per_minute": ai_models.per_minute(model), "first_words_sec": model.first_words}
    return {"assistant": bot.bot_name, "direction": direction, "settings": out}


@tool("recent_calls", "The latest phone calls: when, which assistant, direction, length, how it went, language, the "
      "AI model, credits used and a short summary.", "Looking at recent calls",
      {"type": "object", "properties": {"limit": {"type": "integer", "description": "How many (up to 15; default 5)."},
                                        "direction": DIRECTION}}, routes=("GET /api/voice/calls",), screens=AREAS["voice"])
async def recent_calls(tc, db, limit=5, direction=None):
    from voice.router import list_calls
    calls = await list_calls(direction=direction, outcome=None, limit=max(1, min(int(limit), 15)), ctx=tc.ctx, db=db)
    return {"calls": untrusted([{k: c.get(k) for k in ("started_at", "bot_name", "direction", "caller", "duration_sec", "outcome",
                                                         "language", "ai_model", "credits_used", "summary", "in_progress")}
                                for c in calls])}


@tool("get_schedule", "An assistant's Schedule settings (call-backs, follow-ups, meetings: on or off, hours, rules) "
      "and what is waiting for the team.", "Reading Schedule",
      {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}}},
      routes=("GET /api/voice/schedule/settings/{bot_id}", "GET /api/voice/schedule/attention"), screens=AREAS["voice"])
async def get_schedule(tc, db, assistant_id):
    from voice.schedule_api import attention, get_settings
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    settings = (await get_settings(bot.bot_id, ctx=tc.ctx, db=db))["settings"]
    meetings = {k: v for k, v in (settings.get("meetings") or {}).items() if k != "link"}
    meetings["link"] = "set" if (settings.get("meetings") or {}).get("link") else "not set"
    return {"assistant": bot.bot_name, "callbacks": settings.get("callbacks"), "follow_ups": settings.get("follow_ups"),
            "meetings": meetings, "waiting_for_the_team": await attention(ctx=tc.ctx, db=db)}


@tool("phone_numbers", "The workspace's phone numbers for calls: number, country, status, which assistant answers it, "
      "monthly fee, and whether it's Nimmi's or from their own Twilio/Exotel account.", "Looking at phone numbers",
      routes=("GET /api/voice/numbers",), screens=AREAS["voice"])
async def phone_numbers(tc, db):
    from voice.router import list_numbers
    from backend.models import Bot
    from sqlalchemy import select
    numbers = await list_numbers(ctx=tc.ctx, db=db)
    names = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == tc.ctx.owner_id))).all())
    return {"numbers": [{"id": n["id"], "number": n["number"], "country": n["country"], "status": n["status"],
                         "assistant": names.get(n["bot_id"], "none"), "monthly_fee": n["monthly_fee"], "from": n["source"],
                         "provider": n["provider"]} for n in numbers]}


@tool("voice_options", "The choices for a voice agent: its voices (id, name, gender), languages, background sounds, "
      "and AI models (id, name, quick or smarter, credits a minute, whether it can be used on this server).",
      "Looking at voice options", routes=("GET /api/voice/voices", "GET /api/voice/models", "GET /api/voice/ambience",
                                          "GET /api/voice/rates"), screens=AREAS["voice"])
async def voice_options(tc, db):
    from voice import ai_models, ambience, catalog
    return {"voices": catalog.VOICES, "languages": catalog.LANGUAGES, "background_sounds": list(ambience.KINDS),
            "ai_models": [{"id": m.id, "name": m.name, "kind": ai_models.GROUPS[m.group], "credits_per_minute": ai_models.per_minute(m),
                           "available": ai_models.available(m)} for m in ai_models.AI_MODELS],
            "default_ai_model": ai_models.DEFAULT}


@tool("get_voice_script", "What an assistant's phone agent says (Voice > Knowledge), for incoming or outgoing calls: "
      "opening line, opening for callers it knows, personality, instructions, goal of the call, details to collect.",
      "Reading the voice script",
      {"type": "object", "required": ["assistant_id", "direction"], "properties": {
          "assistant_id": {"type": "string"}, "direction": DIRECTION}},
      routes=("GET /api/voice/scripts/{bot_id}/{direction}",), screens=AREAS["voice"])
async def get_voice_script(tc, db, assistant_id, direction="inbound"):
    from voice.router import get_script
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    script = await get_script(bot.bot_id, direction, ctx=tc.ctx, db=db)
    keep = ("saved", "greeting", "greeting_known", "personality", "instructions", "call_goal", "collect_fields", "language")
    return {"assistant": bot.bot_name, "direction": direction, **{k: script.get(k) for k in keep}}
