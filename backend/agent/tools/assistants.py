"""Tools about the workspace's assistants: the list, one assistant's setup, its flow, leads and unanswered questions."""
from auth import get_owned_bot
from agent.screens import AREAS
from agent.registry import tool, untrusted

ASSISTANT = {"assistant_id": {"type": "string"}}
LOOK = ("color", "font_family", "launcher_shape", "character_animation", "position", "welcome_message", "launcher_greeting",
        "auto_open_delay", "greeting_delay", "page_rule", "page_paths", "hide_on_mobile", "show_human_toggle", "subtitle",
        "starters", "input_placeholder")


@tool("list_assistants", "The assistants in this workspace: id, name, and whether a paid plan is active on it.",
      "Looking at your assistants", routes=("GET /api/bots",))
async def list_assistants(tc, db):
    from routers.bots import list_bots
    bots = await list_bots(ctx=tc.ctx, db=db)
    return {"assistants": [
        {"id": b["id"], "name": b["name"],
         "plan": f"{b['plan']}, until {b['expiry']}" if b["status"] == "Active" else "no active plan (free features only)"}
        for b in bots]}


def _flow_steps(flow: dict) -> list[dict]:
    steps = []
    for n in (flow or {}).get("nodes") or []:
        d = n.get("data") or {}
        step = {"id": n.get("id"), "type": n.get("type")}
        for key in ("message", "options", "variableName", "required", "url"):
            if d.get(key) not in (None, "", []):
                step[key] = d[key]
        steps.append(step)
    return steps


@tool("get_assistant", "One assistant's setup: its look, knowledge sources, instructions, reply settings and the "
      "details it collects, its flow in brief, and its AI model.", "Reading the assistant's setup",
      {"type": "object", "required": ["assistant_id"], "properties": ASSISTANT},
      routes=("GET /api/bots/{bot_id}/config", "GET /api/bots/{bot_id}/knowledge/sources", "GET /api/bots/{bot_id}/knowledge/stats"))
async def get_assistant(tc, db, assistant_id):
    from routers.bots import get_bot_config, knowledge_stats
    import knowledge_sources
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    config = await get_bot_config(bot.bot_id, ctx=tc.ctx, db=db)
    look = {k: v for k, v in (config.get("visual_config") or {}).items() if k in LOOK and v not in (None, "", [])}
    look["avatar"] = "set" if (config.get("visual_config") or {}).get("logo_url") else "none"
    knowledge = config.get("knowledge_base") or ""
    stats = await knowledge_stats(bot.bot_id, ctx=tc.ctx, db=db)
    steps = _flow_steps(config.get("flow_data") or {})
    return {
        "id": bot.bot_id, "name": config.get("bot_name"), "look": look,
        "knowledge": {"sources": knowledge_sources.listing(knowledge), "characters": len(knowledge),
                      "search_index": "ready" if stats.get("indexed") else "not built yet",
                      "beginning": untrusted(knowledge[:800])},
        "instructions": untrusted((config.get("system_prompt") or "")[:2000]),
        "behaviour": config.get("behaviour") or {},
        "flow": {"steps": len(steps), "kinds": sorted({s["type"] for s in steps if s.get("type")})},
        "ai": {"provider": config.get("ai_provider"), "model": config.get("ai_model"),
               "own_api_key": bool(config.get("has_ai_api_key"))},
        "phone_call_backs": bool(config.get("callbacks_enabled")),
    }


@tool("get_flow", "An assistant's flow: its blocks in order (type, and what each says or asks).", "Reading the flow",
      {"type": "object", "required": ["assistant_id"], "properties": ASSISTANT}, routes=("GET /api/bots/{bot_id}/config",), screens=AREAS["assistant"])
async def get_flow(tc, db, assistant_id):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    flow = bot.flow_data or {}
    links = [{"from": e.get("source"), "to": e.get("target"), **({"choice": e["sourceHandle"]} if e.get("sourceHandle") else {})}
             for e in flow.get("edges") or []]
    return {"blocks": untrusted(_flow_steps(flow)), "links": links}


@tool("get_leads", "The details visitors left with an assistant (newest first), and how many there are.",
      "Looking at the leads", {"type": "object", "required": ["assistant_id"], "properties": {
          **ASSISTANT, "limit": {"type": "integer", "description": "How many of the newest to show (up to 20; default 10)."}}},
      routes=("GET /api/bots/{bot_id}/leads",), screens=AREAS["assistant"])
async def get_leads(tc, db, assistant_id, limit=10):
    from routers.bots import get_bot_leads
    leads = await get_bot_leads(assistant_id, ctx=tc.ctx, db=db)
    recent = [{"when": str(l.get("created_at"))[:16], **(l.get("data") or {})} for l in leads[:max(1, min(int(limit), 20))]]
    return {"total": len(leads), "newest": untrusted(recent)}


@tool("get_unanswered_questions", "Questions the assistants couldn't answer (most asked first), from chats, WhatsApp "
      "and calls; optionally for one assistant.", "Looking at unanswered questions",
      {"type": "object", "properties": {"assistant_id": {**ASSISTANT["assistant_id"], "description": "Optional: one assistant."}}},
      roles=("owner", "admin"), routes=("GET /api/questions",), screens=AREAS["assistant"])
async def get_unanswered_questions(tc, db, assistant_id=None):
    from routers.workspace import list_questions
    if assistant_id:
        await get_owned_bot(assistant_id, tc.ctx, db)
    data = await list_questions(status="open", bot_id=assistant_id, ctx=tc.ctx, db=db)
    items = [{"id": q["id"], "question": q["question"], "times": q["count"], "channel": q["channel"], "assistant": q["bot_name"],
              "last_asked": (q.get("last_asked_at") or "")[:10]} for q in data["items"][:15]]
    return {"counts": data["counts"], "top": untrusted(items)}
