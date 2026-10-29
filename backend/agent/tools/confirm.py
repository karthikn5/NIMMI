"""
Tools that need the person's Confirm (level "confirm"): turning a phone agent's calls on or off, Schedule (calls to
customers; turning follow-ups off cancels the planned ones), deleting an assistant, inviting someone to the team (an
email goes out). The preview checks what it can and says in plain words what will happen; the handler runs only after
they click Confirm in the panel (registry.confirm_action).
"""
from auth import get_owned_bot
from agent.screens import AREAS
from agent.registry import MANAGERS, Change, ToolError, tool
from agent.tools.changes import ASSISTANT, DIRECTION, _read_voice, _write_voice

KIND = {"inbound": "incoming", "outbound": "outgoing"}


async def _preview_calls(tc, db, assistant_id, direction, on):
    import plans
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    current = await _read_voice(tc.ctx, db, f"{bot.bot_id}:{direction}", ["enabled", "voice_id"])
    if current["enabled"] == on:
        raise ToolError(f"{KIND[direction].capitalize()} calls are already {'on' if on else 'off'} for {bot.bot_name}.")
    if on:
        await plans.require(db, tc.ctx.owner_id, "voice")
        if not current["voice_id"]:
            raise ToolError("Choose a voice for this agent first (update_voice_agent, voice_id).")
    what = ("it will answer people who call your number" if direction == "inbound" else "it will make the call-backs and campaign calls")
    if on:
        return {"title": f"Turn on {KIND[direction]} calls", "summary": f"Turn on {KIND[direction]} calls for {bot.bot_name}: {what}."}
    return {"title": f"Turn off {KIND[direction]} calls",
            "summary": f"Turn off {KIND[direction]} calls for {bot.bot_name}: {what.replace('it will', 'it will no longer')}."}


@tool("set_voice_calls", "Turn an assistant's phone agent on or off, for incoming or outgoing calls. The person "
      "confirms in the panel first.", "Preparing to turn calls on or off",
      {"type": "object", "required": ["assistant_id", "direction", "on"], "properties": {
          **ASSISTANT, "direction": DIRECTION, "on": {"type": "boolean"}}},
      level="confirm", roles=MANAGERS, preview=_preview_calls, routes=("PUT /api/voice/agents/{bot_id}",), screens=AREAS["voice"])
async def set_voice_calls(tc, db, assistant_id, direction, on):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    entity = f"{bot.bot_id}:{direction}"
    before = await _read_voice(tc.ctx, db, entity, ["enabled"])
    await _write_voice(tc.ctx, db, entity, {"enabled": on})
    after = await _read_voice(tc.ctx, db, entity, ["enabled"])
    return Change(f"{bot.bot_name}: {KIND[direction]} calls turned {'on' if on else 'off'}", "voice_agent", entity,
                  before, after, {"kind": "voice_agent", "id": bot.bot_id})


SCHEDULE = {  # input -> (section, setting, words)
    "callbacks_on": ("callbacks", "enabled", "call-backs callers ask for"),
    "follow_ups_on": ("follow_ups", "enabled", "follow-up calls to leads"),
    "check_follow_ups_first": ("follow_ups", "review", "the team checks each follow-up first"),
    "meetings_on": ("meetings", "enabled", "booking meetings on calls"),
    "approve_meetings": ("meetings", "approval", "the team approves each meeting"),
    "meeting_link": ("meetings", "link", "meeting link"),
}


async def _schedule_plan(tc, db, assistant_id, given: dict):
    from voice import schedule
    from voice.schedule_api import get_settings
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    settings = (await get_settings(bot.bot_id, ctx=tc.ctx, db=db))["settings"]
    lines, new = [], {**settings}
    for key, value in given.items():
        section, setting, words = SCHEDULE[key]
        old = (settings.get(section) or {}).get(setting)
        if key == "meeting_link":
            value = value.strip()
            if value and not value.startswith(("https://", "http://")):
                raise ToolError("The meeting link must start with https://")
        if old != value:
            new[section] = {**new.get(section, {}), setting: value}
            shown = value if key == "meeting_link" else ("on" if value else "off")
            lines.append(f"{words}: {shown}")
    if not lines:
        raise ToolError("Those are already set that way.")
    try:
        schedule.check(new)
    except schedule.ScheduleError as e:
        raise ToolError(str(e))
    if given.get("follow_ups_on") is False and (settings.get("follow_ups") or {}).get("enabled"):
        lines.append("follow-ups already planned are cancelled")
    return bot, new, lines


async def _preview_schedule(tc, db, assistant_id, **given):
    bot, _, lines = await _schedule_plan(tc, db, assistant_id, given)
    return {"title": "Change Schedule", "summary": f"{bot.bot_name}'s Schedule: " + "; ".join(lines) + "."}


@tool("update_schedule", "Turn an assistant's Schedule parts on or off (call-backs, follow-up calls to leads, meetings) "
      "and whether the team checks or approves them first; set the meeting link. These call real people, so the person "
      "confirms in the panel first. Calling hours and the rules: on Voice > Schedule > Settings.", "Preparing a Schedule change",
      {"type": "object", "required": ["assistant_id"], "properties": {
          **ASSISTANT, **{k: {"type": "boolean"} for k in SCHEDULE if k != "meeting_link"},
          "meeting_link": {"type": "string", "description": "The link for online meetings (https://...)."}}},
      level="confirm", roles=MANAGERS, preview=_preview_schedule, routes=("PUT /api/voice/schedule/settings/{bot_id}",), screens=AREAS["voice"])
async def update_schedule(tc, db, assistant_id, **given):
    from voice.schedule_api import put_settings
    bot, new, lines = await _schedule_plan(tc, db, assistant_id, given)
    await put_settings(bot.bot_id, new, ctx=tc.ctx, db=db)
    return {"message": f"{bot.bot_name}'s Schedule: " + "; ".join(lines) + ".", "refresh": {"kind": "schedule", "id": bot.bot_id}}


async def _preview_delete(tc, db, assistant_id):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    return {"title": f"Delete {bot.bot_name}",
            "summary": f"Delete the assistant {bot.bot_name}, with its chats and leads. It can be restored for 30 days from "
                       "Assistants > Recently deleted."}


@tool("delete_assistant", "Delete an assistant (it can be restored for 30 days). The person confirms in the panel first.",
      "Preparing to delete", {"type": "object", "required": ["assistant_id"], "properties": ASSISTANT},
      level="confirm", roles=MANAGERS, preview=_preview_delete, routes=("DELETE /api/bots/{bot_id}",), screens=AREAS["assistant"])
async def delete_assistant(tc, db, assistant_id):
    from routers.bots import delete_bot
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    name = bot.bot_name
    await delete_bot(bot.bot_id, ctx=tc.ctx, db=db)
    return {"message": f"Deleted {name}. It can be restored for 30 days from Assistants > Recently deleted.",
            "refresh": {"kind": "assistant", "id": assistant_id, "deleted": True}}


async def _preview_invite(tc, db, email, role):
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ToolError("That doesn't look like an email address.")
    what = "manage assistants, voice and integrations" if role == "admin" else "answer live chats and calls"
    return {"title": f"Invite {email}", "summary": f"Email an invitation to {email} to join your workspace as {'an admin' if role == 'admin' else 'an agent'} ({what})."}


@tool("invite_teammate", "Invite someone to the workspace by email, as an admin or an agent (an email goes out). The "
      "person confirms in the panel first. Owners only.", "Preparing an invitation",
      {"type": "object", "required": ["email", "role"], "properties": {
          "email": {"type": "string"}, "role": {"type": "string", "enum": ["admin", "agent"]}}},
      level="confirm", roles=("owner",), preview=_preview_invite, routes=("POST /api/team/invite",), screens=AREAS["account"])
async def invite_teammate(tc, db, email, role):
    from routers.team import InviteRequest, invite
    result = await invite(InviteRequest(email=email.strip().lower(), role=role), ctx=tc.ctx, db=db)
    return {"message": f"Invited {email.strip().lower()} as {'an admin' if role == 'admin' else 'an agent'}.",
            "refresh": {"kind": "team", "id": tc.ctx.owner_id}, "status": result.get("status") if isinstance(result, dict) else None}
