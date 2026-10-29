"""
More of the dashboard for the agent (phase 5): one call's transcript, callers it remembers, what's planned in Schedule,
campaigns, the team, business hours (undoable), hosted websites, WhatsApp chats, dismissing a question, and restoring
a deleted assistant (confirm). Text written by customers comes back marked as data (untrusted()).
"""
import assist
from auth import get_owned_bot
from agent.registry import MANAGERS, Change, ToolError, adapter, tool, untrusted
from agent.screens import AREAS


@tool("get_call", "One phone call in full (ids from recent_calls): who, when, how it went, the summary, what was "
      "collected, and the transcript.", "Reading the call",
      {"type": "object", "required": ["call_id"], "properties": {"call_id": {"type": "string"}}},
      screens=AREAS["voice"], routes=("GET /api/voice/calls/{call_id}",))
async def get_call(tc, db, call_id):
    from voice.router import get_call as call_route
    c = await call_route(call_id, ctx=tc.ctx, db=db)
    keep = ("started_at", "direction", "caller", "bot_name", "duration_sec", "outcome", "language", "ai_model", "credits_used",
            "sentiment", "successful")
    return {**{k: c.get(k) for k in keep}, "summary": untrusted(c.get("summary") or ""),
            "collected": untrusted(c.get("captured") or {}), "transcript": untrusted(str(c.get("transcript") or "")[:5000])}


@tool("voice_contacts", "Callers the phone agent remembers: name, number (partly hidden), calls, lead rating, follow-ups; "
      "optionally one assistant's or a search.", "Looking at contacts",
      {"type": "object", "properties": {"assistant_id": {"type": "string"}, "search": {"type": "string"}}},
      screens=AREAS["voice"], routes=("GET /api/voice/contacts",))
async def voice_contacts(tc, db, assistant_id=None, search=""):
    from voice.router import list_contacts
    if assistant_id:
        await get_owned_bot(assistant_id, tc.ctx, db)
    rows = await list_contacts(bot_id=assistant_id, q=search[:80], ctx=tc.ctx, db=db)
    keep = ("name", "number", "bot_name", "calls", "last_call_at", "lead_status", "follow_ups", "follow_ups_off")
    return {"contacts": untrusted([{k: r.get(k) for k in keep} for r in rows[:25]]), "total": len(rows)}


@tool("schedule_planned", "What's planned in Voice > Schedule: call-backs, follow-ups and to-dos still open, and upcoming "
      "meetings (with what waits for the team).", "Looking at what's planned",
      {"type": "object", "properties": {"assistant_id": {"type": "string"}}},
      screens=AREAS["voice"], routes=("GET /api/voice/schedule/items", "GET /api/voice/schedule/meetings",
                                       "GET /api/voice/schedule/overview"))
async def schedule_planned(tc, db, assistant_id=""):
    from voice.schedule_api import list_items, list_meetings
    if assistant_id:
        await get_owned_bot(assistant_id, tc.ctx, db)
    items = await list_items(kind="", status="open", bot_id=assistant_id or "", ctx=tc.ctx, db=db)
    meetings = await list_meetings(status="upcoming", bot_id=assistant_id or "", ctx=tc.ctx, db=db)
    return {"calls_and_todos": untrusted(items[:20] if isinstance(items, list) else items),
            "meetings": untrusted(meetings[:20] if isinstance(meetings, list) else meetings)}


@tool("campaigns", "Their calling campaigns: name, assistant, status, and how many on the list were called.",
      "Looking at campaigns", roles=MANAGERS, screens=AREAS["voice"], routes=("GET /api/voice/campaigns",))
async def campaigns(tc, db):
    from voice.campaigns_api import list_campaigns
    rows = await list_campaigns(ctx=tc.ctx, db=db)
    return {"campaigns": [{k: c.get(k) for k in ("id", "name", "bot_name", "status", "total", "called", "created_at") if k in c}
                          for c in rows[:30]]}


@tool("team_members", "The people in their workspace: name, email, role (admin or agent) and whether they've joined. "
      "Owners only.", "Looking at the team", roles=("owner",), routes=("GET /api/team/members",))
async def team_members(tc, db):
    from routers.team import list_members
    return {"members": await list_members(ctx=tc.ctx, db=db)}


@tool("websites", "The websites they host with Nimmi (Deployments): name, address, status, and the assistant on it.",
      "Looking at your websites", screens=AREAS["assistant"], routes=("GET /api/sites",))
async def websites(tc, db):
    from routers.sites import list_sites
    data = await list_sites(ctx=tc.ctx, db=db)
    keep = ("id", "name", "slug", "url", "status", "custom_domain", "bot_name", "updated_at")
    return {"websites": [{k: s.get(k) for k in keep if k in s} for s in data.get("sites", [])],
            "recently_deleted": len(data.get("deleted") or [])}


@tool("whatsapp_chats", "WhatsApp chats with customers: name, status, whether the assistant or the team is handling it, "
      "and the last message. view: open, person (needs the team), mine, closed.", "Looking at WhatsApp chats",
      {"type": "object", "properties": {"view": {"type": "string", "enum": ["open", "ai", "person", "mine", "closed"]}}},
      screens=AREAS["whatsapp"], routes=("GET /api/whatsapp/chats",))
async def whatsapp_chats(tc, db, view="open"):
    from whatsapp.api import list_chats
    rows = await list_chats(view=view, q="", number_id="", ctx=tc.ctx, db=db)
    keep = ("name", "status", "handoff", "unread", "last_message_at", "last")
    return {"chats": untrusted([{k: r.get(k) for k in keep} for r in rows[:20]]), "total": len(rows)}


# ─── Business hours (undoable) ──────────────────────────────────────

async def _read_hours(ctx, db, owner_id: str, keys: list) -> dict:
    from routers.workspace import get_settings
    s = await get_settings(ctx=ctx, db=db)
    return {"business_hours": s["business_hours"]}


async def _write_hours(ctx, db, owner_id: str, values: dict) -> None:
    from routers.workspace import SettingsIn, get_settings, update_settings
    current = await get_settings(ctx=ctx, db=db)
    await update_settings(SettingsIn(business_hours=values["business_hours"], escalate_upset=current["escalate_upset"]), ctx=ctx, db=db)


adapter("workspace_hours", _read_hours, _write_hours, lambda owner_id: {"kind": "workspace", "id": owner_id})


@tool("business_hours", "Their business hours (when the team is in), whether they're on, and the message visitors get "
      "when the team is away.", "Checking business hours", routes=("GET /api/workspace/settings",))
async def business_hours(tc, db):
    from routers.workspace import get_settings
    return await get_settings(ctx=tc.ctx, db=db)


@tool("update_business_hours", "Set their business hours: which days they're open, from and to (24-hour, like 09:00 and "
      "19:00), turning hours on or off, and the away message. Days not listed are closed.", "Changing business hours",
      {"type": "object", "properties": {
          "on": {"type": "boolean"}, "open_days": {"type": "array", "items": {"type": "string", "enum": list(assist.DAYS)}},
          "opens": {"type": "string"}, "closes": {"type": "string"}, "away_message": {"type": "string"}}},
      level="change", roles=MANAGERS, routes=("PUT /api/workspace/settings",))
async def update_business_hours(tc, db, on=None, open_days=None, opens=None, closes=None, away_message=None):
    import re
    before = await _read_hours(tc.ctx, db, tc.ctx.owner_id, ["business_hours"])
    hours = {**before["business_hours"], "days": {d: dict(v) for d, v in before["business_hours"]["days"].items()}}
    for t in (opens, closes):
        if t is not None and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
            raise ToolError("Times are 24-hour, like 09:00 or 19:30.")
    if open_days is not None or opens or closes:
        days = open_days if open_days is not None else [d for d, v in hours["days"].items() if v.get("open")]
        for d in assist.DAYS:
            day = hours["days"].setdefault(d, {"open": False, "from": "09:00", "to": "18:00"})
            day["open"] = d in days
            if d in days and opens:
                day["from"] = opens
            if d in days and closes:
                day["to"] = closes
    if on is not None:
        hours["enabled"] = on
    if away_message is not None:
        hours["away_message"] = away_message.strip()[:400]
    await _write_hours(tc.ctx, db, tc.ctx.owner_id, {"business_hours": hours})
    after = await _read_hours(tc.ctx, db, tc.ctx.owner_id, ["business_hours"])
    open_now = [d for d, v in after["business_hours"]["days"].items() if v.get("open")]
    first = after["business_hours"]["days"].get(open_now[0], {}) if open_now else {}
    summary = (f"Business hours {'on' if after['business_hours'].get('enabled') else 'off'}: "
               + (f"{', '.join(open_now)}, {first.get('from')} to {first.get('to')}" if open_now else "closed every day"))
    return Change(summary, "workspace_hours", tc.ctx.owner_id, before, after, {"kind": "workspace", "id": tc.ctx.owner_id})


@tool("dismiss_question", "Dismiss an unanswered question (it isn't worth answering), or reopen one (ids from "
      "get_unanswered_questions).", "Dismissing the question",
      {"type": "object", "required": ["question_id"], "properties": {"question_id": {"type": "string"}, "reopen": {"type": "boolean"}}},
      level="change", roles=MANAGERS, screens=AREAS["assistant"], routes=("POST /api/questions/{gap_id}/{action}",))
async def dismiss_question(tc, db, question_id, reopen=False):
    from agent.tools.changes import _read_question
    from routers.workspace import question_action
    before = await _read_question(tc.ctx, db, question_id, ["status"])
    await question_action(question_id, "reopen" if reopen else "dismiss", ctx=tc.ctx, db=db)
    after = await _read_question(tc.ctx, db, question_id, ["status"])
    question = (await _read_question(tc.ctx, db, question_id, ["question"]))["question"]
    return Change(f"{'Reopened' if reopen else 'Dismissed'} the question \"{question[:80]}\"", "question", question_id, before, after,
                  {"kind": "question", "id": question_id})


# ─── Restoring a deleted assistant (confirm) ────────────────────────

async def _find_deleted(tc, db, name: str) -> dict:
    from routers.bots import deleted_bots
    items = await deleted_bots(ctx=tc.ctx, db=db)
    match = [i for i in items if i["name"].strip().lower() == name.strip().lower()] or \
            [i for i in items if name.strip().lower() in i["name"].lower()]
    if not match:
        raise ToolError(f"No recently deleted assistant called {name}. Recently deleted: "
                        + (", ".join(i["name"] for i in items) or "none") + ".")
    return match[0]


async def _preview_restore(tc, db, name):
    item = await _find_deleted(tc, db, name)
    return {"title": f"Restore {item['name']}", "summary": f"Bring back the assistant {item['name']} with its chats and leads "
                                                           f"({item['conversations']} conversations)."}


@tool("restore_assistant", "Bring back an assistant they deleted in the last 30 days, by its name. The person confirms "
      "in the panel first.", "Preparing to restore",
      {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
      level="confirm", roles=MANAGERS, preview=_preview_restore, screens=AREAS["assistant"],
      routes=("GET /api/bots/deleted", "POST /api/bots/deleted/{item_id}/restore"))
async def restore_assistant(tc, db, name):
    from routers.bots import restore_deleted_bot
    item = await _find_deleted(tc, db, name)
    result = await restore_deleted_bot(item["id"], ctx=tc.ctx, db=db)
    return {"message": f"Restored {result['name']}.", "refresh": {"kind": "assistant", "id": result["bot_id"]}}
