"""
Connecting what only the business can connect (phase 4): step-by-step guides that end at Nimmi's own forms (keys go
there, never into the chat), what's connected now, and which assistant answers each phone or WhatsApp number.
"""
from sqlalchemy import select

from auth import get_owned_bot
from agent import guides
from agent.registry import MANAGERS, Change, ToolError, adapter, tool
from agent.screens import AREAS


async def _status(tc, db) -> dict:
    from voice.router import list_numbers
    from whatsapp.api import list_numbers as whatsapp_numbers
    from backend.models import Bot, VoiceAgent
    names = dict((await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == tc.ctx.owner_id))).all())
    out: dict = {}
    if tc.ctx.role == "owner":
        from voice.connections_api import list_accounts
        accounts = (await list_accounts(ctx=tc.ctx, db=db))["accounts"]
        out["accounts"] = [{"provider": a["provider"], "label": a.get("label") or a["provider"]} for a in accounts]
        out["twilio"] = any(a["provider"] == "twilio" for a in accounts)
        out["exotel"] = any(a["provider"] == "exotel" for a in accounts)
    numbers = await list_numbers(ctx=tc.ctx, db=db)
    out["phone_numbers"] = [{"id": n["id"], "number": n["number"], "status": n["status"], "from": n["source"],
                             "answered_by": names.get(n["bot_id"], "nobody yet")} for n in numbers]
    wa = await whatsapp_numbers(ctx=tc.ctx, db=db)
    out["whatsapp_numbers"] = [{"id": n["id"], "number": n["display_number"], "status": n["status"], "answered_by": n.get("bot_name") or "nobody yet",
                                "ai_on": n.get("ai_enabled")} for n in wa]
    out["whatsapp"] = any(n["status"] == "connected" for n in wa)
    booking = []
    for agent in (await db.execute(select(VoiceAgent).where(VoiceAgent.user_id == tc.ctx.owner_id))).scalars().all():
        kinds = {f.get("kind") for f in (agent.functions or []) if isinstance(f, dict)}
        if kinds & {"check_slots", "book"}:
            booking.append(names.get(agent.bot_id, agent.bot_id))
    out["calcom"] = bool(booking)
    out["calcom_agents"] = booking
    return out


@tool("connection_guide", "Use whenever they ask how to connect, set up or link WhatsApp, a phone number (their own "
      "Twilio or Exotel account) or Cal.com: shows a card with the exact clicks in that company's console, a link to it, "
      "and a button to Nimmi's form. They paste keys only into that form, never into the chat.", "Preparing the steps",
      {"type": "object", "required": ["provider"], "properties": {
          "provider": {"type": "string", "enum": list(guides.GUIDES)},
          "assistant_id": {"type": "string", "description": "Cal.com only: the assistant whose phone agent books."}}})
async def connection_guide(tc, db, provider, assistant_id=None):
    if assistant_id:
        await get_owned_bot(assistant_id, tc.ctx, db)
    g = guides.guide(provider, assistant_id or "")
    connected = (await _status(tc, db)).get(provider)
    tc.act("card", {"kind": "guide", "provider": provider, **{k: g[k] for k in ("title", "why", "link", "link_label", "form",
                                                                                "form_label", "steps", "note")}})
    return {"shown": g["title"], "already_connected": connected,
            "note": "The steps are in a card in the panel: say in one line what they'll need and that the card has the "
                    "clicks. They paste keys into Nimmi's form, never into this chat.",
            "steps": g["steps"], "link": g["link"], "where_in_nimmi": g["form_label"]}


@tool("connection_status", "What's connected now: their own Twilio or Exotel accounts (owners see these), their phone "
      "numbers and which assistant answers each, WhatsApp numbers, and which phone agents can book on Cal.com.",
      "Checking connections", routes=("GET /api/voice/phone-accounts",))
async def connection_status(tc, db):
    return await _status(tc, db)


# ─── Which assistant answers a number (undoable) ────────────────────

async def _read_phone(ctx, db, number_id: str, keys: list) -> dict:
    from backend.models import PhoneNumber
    n = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.user_id == ctx.owner_id))).scalars().first()
    if n is None:
        raise ToolError("Number not found.")
    return {"bot_id": n.bot_id}


async def _write_phone(ctx, db, number_id: str, values: dict) -> None:
    from voice.router import route_number
    await route_number(number_id, {"bot_id": values.get("bot_id")}, ctx=ctx, db=db)


adapter("phone_number", _read_phone, _write_phone, lambda number_id: {"kind": "phone_number", "id": number_id})


@tool("assign_number", "Choose which assistant answers (and calls from) one of their phone numbers; ids from "
      "connection_status or phone_numbers. assistant_id 'none' leaves the number unanswered.", "Choosing who answers the number",
      {"type": "object", "required": ["number_id", "assistant_id"], "properties": {
          "number_id": {"type": "string"}, "assistant_id": {"type": "string"}}},
      level="change", roles=MANAGERS, screens=AREAS["voice"], routes=("PATCH /api/voice/numbers/{number_id}",))
async def assign_number(tc, db, number_id, assistant_id):
    bot = None if assistant_id == "none" else await get_owned_bot(assistant_id, tc.ctx, db)
    before = await _read_phone(tc.ctx, db, number_id, ["bot_id"])
    await _write_phone(tc.ctx, db, number_id, {"bot_id": bot.bot_id if bot else None})
    after = await _read_phone(tc.ctx, db, number_id, ["bot_id"])
    from backend.models import PhoneNumber
    number = (await db.get(PhoneNumber, number_id)).number
    return Change(f"{number}: answered by {bot.bot_name if bot else 'nobody'}", "phone_number", number_id, before, after,
                  {"kind": "phone_number", "id": number_id})


async def _read_whatsapp(ctx, db, number_id: str, keys: list) -> dict:
    from whatsapp.api import _number
    n = await _number(db, number_id, ctx)
    return {k: getattr(n, k) for k in keys}


async def _write_whatsapp(ctx, db, number_id: str, values: dict) -> None:
    from whatsapp.api import NumberUpdate, update_number
    await update_number(number_id, NumberUpdate(**values), ctx=ctx, db=db)


adapter("whatsapp_number", _read_whatsapp, _write_whatsapp, lambda number_id: {"kind": "whatsapp_number", "id": number_id})


@tool("update_whatsapp_number", "Choose which assistant answers one of their WhatsApp numbers, or turn the AI's replies "
      "on it on or off (ids from whatsapp_status or connection_status).", "Changing the WhatsApp number",
      {"type": "object", "required": ["number_id"], "properties": {
          "number_id": {"type": "string"}, "assistant_id": {"type": "string"}, "ai_on": {"type": "boolean"}}},
      level="change", roles=MANAGERS, screens=AREAS["whatsapp"], routes=("PATCH /api/whatsapp/numbers/{number_id}",))
async def update_whatsapp_number(tc, db, number_id, assistant_id=None, ai_on=None):
    values = {}
    if assistant_id:
        values["bot_id"] = (await get_owned_bot(assistant_id, tc.ctx, db)).bot_id
    if ai_on is not None:
        values["ai_enabled"] = ai_on
    if not values:
        raise ToolError("Say what to change.")
    before = await _read_whatsapp(tc.ctx, db, number_id, list(values))
    await _write_whatsapp(tc.ctx, db, number_id, values)
    after = await _read_whatsapp(tc.ctx, db, number_id, list(values))
    words = []
    if "bot_id" in values:
        words.append(f"answered by {(await get_owned_bot(values['bot_id'], tc.ctx, db)).bot_name}")
    if "ai_enabled" in values:
        words.append(f"AI replies {'on' if ai_on else 'off'}")
    return Change(f"WhatsApp number: {', '.join(words)}", "whatsapp_number", number_id, before, after,
                  {"kind": "whatsapp_number", "id": number_id})
