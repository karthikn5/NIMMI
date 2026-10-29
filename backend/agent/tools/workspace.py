"""Tools about the workspace: plan and limits, analytics, WhatsApp, and who is waiting in Live chat."""
from datetime import datetime, timezone

from auth import get_owned_bot
from agent.registry import tool


@tool("plan_and_limits", "The workspace's plan: paid or free, how many assistants and websites it allows and uses, "
      "and whether voice, integrations and custom domains are included; voice credits left.", "Checking your plan",
      routes=("GET /api/account/limits",))
async def plan_and_limits(tc, db):
    from plans import get_limits
    from voice.router import overview
    lim = await get_limits(ctx=tc.ctx, db=db)
    credits = (await overview(ctx=tc.ctx, db=db)).get("credits_left")
    return {"paid": lim["paid"], "assistants": {"allowed": lim["assistants"] or "no limit", "used": lim["used"]["assistants"]},
            "websites": {"allowed": lim["sites"], "used": lim["used"]["sites"]}, "custom_domains": lim["custom_domains"],
            "voice": lim["voice"], "integrations": lim["integrations"], "voice_credits_left": credits}


@tool("analytics_summary", "Chats, messages, leads, hand-overs and calls over the last N days (7 to 90), compared "
      "with the period before, and per assistant.", "Reading analytics",
      {"type": "object", "properties": {"days": {"type": "integer", "description": "7 to 90; default 30."},
                                        "assistant_id": {"type": "string", "description": "Optional: one assistant."}}},
      routes=("GET /api/analytics",))
async def analytics_summary(tc, db, days=30, assistant_id=None):
    from routers.analytics import analytics
    if assistant_id:
        await get_owned_bot(assistant_id, tc.ctx, db)
    a = await analytics(days=int(days), bot_id=assistant_id, ctx=tc.ctx, db=db)
    return {"days": a["days"], "totals": a["totals"], "previous_period": a["previous"], "by_assistant": a["by_bot"]}


@tool("whatsapp_status", "WhatsApp: connected numbers (name, status, quality, which assistant answers, AI on or off), "
      "this month's chats and replies, and what's left to set up.", "Checking WhatsApp",
      routes=("GET /api/whatsapp/overview", "GET /api/whatsapp/numbers"))
async def whatsapp_status(tc, db):
    from whatsapp.api import overview
    o = await overview(ctx=tc.ctx, db=db)
    numbers = [{k: n.get(k) for k in ("id", "display_number", "verified_name", "bot_name", "status", "status_detail", "quality_rating",
                                      "ai_enabled", "connection", "last_inbound_at")} for n in o.get("numbers") or []]
    return {"numbers": numbers, "this_month": o.get("month"), "setup": o.get("setup")}


@tool("live_chat_waiting", "People waiting for the team in Live chat: how many, on which assistant and channel, and "
      "how long the longest has waited.", "Checking Live chat", routes=("GET /api/handoffs/pending",))
async def live_chat_waiting(tc, db):
    from routers.handoffs import pending_handoffs
    rows = await pending_handoffs(ctx=tc.ctx, db=db)
    waiting = [r for r in rows if r.get("status") == "pending"]
    now = datetime.now(timezone.utc)

    def minutes(r) -> int:
        at = r.get("created_at")
        at = at.replace(tzinfo=timezone.utc) if at and at.tzinfo is None else at
        return int((now - at).total_seconds() // 60) if at else 0
    by = {}
    for r in waiting:
        key = f"{r.get('bot_name')} ({r.get('channel')})"
        by[key] = by.get(key, 0) + 1
    return {"waiting": len(waiting), "being_helped": len(rows) - len(waiting), "by_assistant": by,
            "longest_wait_minutes": max((minutes(r) for r in waiting), default=0)}
