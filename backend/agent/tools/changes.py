"""
Tools that change settings the person can undo (level "change"): an assistant's look, instructions, reply settings,
knowledge and flow (tools/flow.py writes whole flows); copying any of them from another assistant; a voice agent and
its script; answers to unanswered questions.

Each goes through the same route the dashboard saves with (so the same checks), and returns a registry.Change with
exactly the settings it changed, before and after. The adapters below read and write those settings for Undo, also
through the dashboard's routes. Keys: "name", "instructions", "knowledge" (without the business summary, which is
rewritten in the background), "visual.<key>", "behaviour.<key>", "behaviour.collect.<key>", "flow" (the whole flow),
"flow_block.<id>"; for a voice agent and a script, their form's field names.
"""
import copy
import re

from pydantic import ValidationError

import behaviour as reply_rules
import knowledge_sources
from auth import get_owned_bot
from agent.screens import AREAS
from agent.registry import MANAGERS, Change, ToolError, adapter, tool

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FONTS = {"System default": "sans-serif", "Inter": "'Inter', sans-serif", "Roboto": "'Roboto', sans-serif",
         "Open Sans": "'Open Sans', sans-serif", "Lato": "'Lato', sans-serif", "Poppins": "'Poppins', sans-serif",
         "Montserrat": "'Montserrat', sans-serif", "Nunito": "'Nunito', sans-serif", "DM Sans": "'DM Sans', sans-serif",
         "Manrope": "'Manrope', sans-serif", "Work Sans": "'Work Sans', sans-serif", "Figtree": "'Figtree', sans-serif",
         "Outfit": "'Outfit', sans-serif", "Mukta (Indian scripts)": "'Mukta', sans-serif",
         "Hind (Indian scripts)": "'Hind', sans-serif", "Noto Sans (Indian scripts)": "'Noto Sans', sans-serif",
         "Lora (serif)": "'Lora', serif", "Merriweather (serif)": "'Merriweather', serif",
         "Playfair Display (serif)": "'Playfair Display', serif", "Serif": "serif", "Monospace": "monospace"}
ASSISTANT = {"assistant_id": {"type": "string"}}
DIRECTION = {"type": "string", "enum": ["inbound", "outbound"], "description": "inbound: incoming calls; outbound: outgoing calls."}


def _short(value, limit: int = 60) -> str:
    text = value if isinstance(value, str) else ("on" if value is True else "off" if value is False else str(value))
    text = " ".join(str(text).split())
    return f'"{text[:limit]}..."' if len(text) > limit else (f'"{text}"' if isinstance(value, str) else text)


def _summary(subject: str, before: dict, after: dict, names: dict) -> str:
    parts = [f"{names.get(k, k)}: {_short(before.get(k))} to {_short(after.get(k))}" for k in after if before.get(k) != after.get(k)]
    return f"{subject}: " + "; ".join(parts) if parts else f"{subject}: no change"


# ─── The assistant's own settings ───────────────────────────────────

def _without_summary(text: str) -> str:
    return knowledge_sources.remove(text or "", knowledge_sources.SUMMARY)[0]


def _get(bot, key: str):
    if key == "name":
        return bot.bot_name
    if key == "instructions":
        return bot.system_prompt or ""
    if key == "knowledge":
        return _without_summary(bot.knowledge_base or "")
    if key.startswith("visual."):
        return (bot.visual_config or {}).get(key[7:])
    if key.startswith("behaviour.collect."):
        return reply_rules.collect(bot.behaviour).get(key[18:])
    if key.startswith("behaviour."):
        return reply_rules.clean(bot.behaviour).get(key[10:])
    if key == "flow":
        return copy.deepcopy(bot.flow_data or {"nodes": [], "edges": []})
    if key.startswith("flow_block."):
        node = next((n for n in (bot.flow_data or {}).get("nodes") or [] if n.get("id") == key[11:]), None)
        return copy.deepcopy(node.get("data")) if node else None
    raise KeyError(key)


async def _read_assistant(ctx, db, bot_id: str, keys: list) -> dict:
    bot = await get_owned_bot(bot_id, ctx, db)
    return {k: _get(bot, k) for k in keys}


async def _write_assistant(ctx, db, bot_id: str, values: dict) -> None:
    """Through the builder's own save (PATCH /api/bots/{id}), whole fields merged with the new values."""
    from routers.bots import _after_change, update_bot
    bot = await get_owned_bot(bot_id, ctx, db)
    data: dict = {}
    visual = dict(bot.visual_config or {})
    rules = reply_rules.clean(bot.behaviour)
    flow = copy.deepcopy(bot.flow_data or {"nodes": [], "edges": []})
    for key, value in values.items():
        if key == "name":
            data["bot_name"] = value
        elif key == "instructions":
            data["system_prompt"] = value
        elif key == "knowledge":
            data["knowledge_base"] = value  # the route keeps the current business summary
        elif key.startswith("visual."):
            visual[key[7:]] = value
            data["visual_config"] = visual
        elif key.startswith("behaviour.collect."):
            rules["collect"] = {**rules["collect"], key[18:]: value}
            data["behaviour"] = rules
        elif key.startswith("behaviour."):
            rules[key[10:]] = value
            data["behaviour"] = rules
        elif key == "flow":
            flow = copy.deepcopy(value or {"nodes": [], "edges": []})
            data["flow_data"] = flow
        elif key.startswith("flow_block."):
            node = next((n for n in flow.get("nodes") or [] if n.get("id") == key[11:]), None)
            if node is None:
                raise ToolError("That flow block isn't there any more.")
            node["data"] = value
            data["flow_data"] = flow
    await update_bot(bot.bot_id, data, ctx=ctx, db=db)
    if "knowledge_base" in data:
        _after_change(bot)  # the business summary and the search index, in the background, as the builder's saves do


adapter("assistant", _read_assistant, _write_assistant, lambda bot_id: {"kind": "assistant", "id": bot_id})


async def _change_assistant(tc, db, bot, values: dict, subject: str, names: dict, result=None) -> Change:
    keys = list(values)
    before = await _read_assistant(tc.ctx, db, bot.bot_id, keys)
    await _write_assistant(tc.ctx, db, bot.bot_id, values)
    after = await _read_assistant(tc.ctx, db, bot.bot_id, keys)
    return Change(_summary(f"{bot.bot_name}: {subject}", before, after, names), "assistant", bot.bot_id, before, after,
                  {"kind": "assistant", "id": bot.bot_id}, result)


DESIGN = {  # input -> (setting, words)
    "brand_colour": ("color", "brand colour"), "header_text_colour": ("text_color", "header text colour"),
    "visitor_bubble_colour": ("user_bubble_bg", "visitor's bubble colour"), "visitor_text_colour": ("user_bubble_text", "visitor's text colour"),
    "assistant_bubble_colour": ("assistant_bubble_bg", "assistant's bubble colour"),
    "assistant_text_colour": ("assistant_bubble_text", "assistant's text colour"), "chat_background_colour": ("chat_bg_color", "chat background"),
    "launcher_shape": ("launcher_shape", "launcher shape"), "position": ("position", "side of the screen"),
    "welcome_message": ("welcome_message", "welcome message"), "launcher_greeting": ("launcher_greeting", "greeting beside the launcher"),
    "subtitle": ("subtitle", "header subtitle"), "input_placeholder": ("input_placeholder", "message box hint"),
    "open_by_itself_after_seconds": ("auto_open_delay", "opens by itself after (seconds)"),
    "greeting_after_seconds": ("greeting_delay", "greeting shows after (seconds)"),
    "hide_on_phones": ("hide_on_mobile", "hidden on phones"), "offer_talk_to_a_person": ("show_human_toggle", "'Talk to a person' switch"),
    "starters": ("starters", "suggested questions"), "font": ("font_family", "font"),
    "character_height": ("character_height", "character's height"), "animated_character": ("character_animation", "animated character"),
}
LIMITS = {"welcome_message": 300, "launcher_greeting": 200, "subtitle": 80, "input_placeholder": 80}


@tool("update_assistant_design", "Change how an assistant's chat looks: name, colours (hex, like #16a34a), font, "
      "launcher shape and side (character: the avatar stands at full height, character_height 80-220 px; "
      "animated_character violet: Nimmi's animated Violet stands there), welcome message, greeting beside the launcher, "
      "opening by itself after N seconds (0 off), suggested questions (up to 4). Only the inputs given change.", "Changing the design",
      {"type": "object", "required": ["assistant_id"], "properties": {
          **ASSISTANT, "name": {"type": "string", "description": "The assistant's name (up to 60 characters)."},
          **{k: {"type": "string"} for k in DESIGN if k.endswith("_colour")},
          "font": {"type": "string", "enum": list(FONTS)},
          "launcher_shape": {"type": "string", "enum": ["circle", "rounded", "square", "oval", "character"]},
          "position": {"type": "string", "enum": ["left", "right"]},
          "welcome_message": {"type": "string"}, "launcher_greeting": {"type": "string"}, "subtitle": {"type": "string"},
          "input_placeholder": {"type": "string"},
          "open_by_itself_after_seconds": {"type": "integer"}, "greeting_after_seconds": {"type": "integer"},
          "hide_on_phones": {"type": "boolean"}, "offer_talk_to_a_person": {"type": "boolean"},
          "starters": {"type": "array", "items": {"type": "string"}},
          "character_height": {"type": "integer"}, "animated_character": {"type": "string", "enum": ["none", "violet"]}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}", "POST /api/bots/{bot_id}/config"), screens=AREAS["assistant"])
async def update_assistant_design(tc, db, assistant_id, name=None, **given):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    values, names = {}, {"name": "name"}
    if name is not None:
        if not name.strip():
            raise ToolError("The name can't be empty.")
        values["name"] = name.strip()[:60]
    for key, value in given.items():
        setting, words = DESIGN[key]
        if key.endswith("_colour"):
            if not HEX.match(value.strip()):
                raise ToolError(f"{words} must be a hex colour like #16a34a.")
            value = value.strip().lower()
        elif key == "font":
            value = FONTS[value]
        elif key in LIMITS:
            value = value.strip()[:LIMITS[key]]
        elif key == "open_by_itself_after_seconds":
            value = max(0, min(int(value), 120))
        elif key == "greeting_after_seconds":
            value = max(0, min(int(value), 60))
        elif key == "starters":
            value = [s.strip()[:80] for s in value if s.strip()][:4]
        elif key == "character_height":
            value = max(80, min(int(value), 220))
        elif key == "animated_character":
            value = "" if value == "none" else value
        values[f"visual.{setting}"] = value
        names[f"visual.{setting}"] = words
    if not values:
        raise ToolError("Say what to change.")
    return await _change_assistant(tc, db, bot, values, "design", names)


@tool("update_instructions", "Change an assistant's instructions (what it should do and avoid when it chats). "
      "mode 'append' adds the text at the end; 'replace' replaces them all; 'edit' replaces only the part given in "
      "find (copied exactly from get_assistant) with text.", "Changing the instructions",
      {"type": "object", "required": ["assistant_id", "text"], "properties": {
          **ASSISTANT, "text": {"type": "string"}, "mode": {"type": "string", "enum": ["append", "replace", "edit"], "description": "Default append."},
          "find": {"type": "string", "description": "edit: the exact words to replace."}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}",), screens=AREAS["assistant"])
async def update_instructions(tc, db, assistant_id, text, mode="append", find=None):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    current = bot.system_prompt or ""
    if mode == "edit":
        times = current.count(find or "\0")
        if not find or not times:
            raise ToolError("Those words aren't in the instructions as written: copy them exactly from get_assistant.")
        if times > 1:
            raise ToolError(f"Those words are in the instructions {times} times: give more of the text around them.")
        new = current.replace(find, text.strip(), 1).strip()
    else:
        new = text.strip() if mode == "replace" else (current.rstrip() + "\n\n" + text.strip()).strip()
    if len(new) > 20000:
        raise ToolError("The instructions would be too long (over 20,000 characters).")
    return await _change_assistant(tc, db, bot, {"instructions": new}, "instructions", {"instructions": "instructions"})


@tool("update_reply_settings", "Change how an assistant replies in chats: reply length, language (match: the "
      "visitor's), asking for contact details, offering a person, what it says when it doesn't know, which visitor "
      "details it collects (standard ones, and up to 6 of their own like Budget) and when.",
      "Changing the reply settings",
      {"type": "object", "required": ["assistant_id"], "properties": {
          **ASSISTANT,
          "reply_length": {"type": "string", "enum": list(reply_rules.LENGTHS)},
          "language": {"type": "string", "enum": list(reply_rules.LANGUAGES)},
          "ask_for_contact": {"type": "boolean"}, "offer_person": {"type": "boolean"}, "when_it_doesnt_know": {"type": "string"},
          "collect_details": {"type": "boolean"},
          "standard_details": {"type": "array", "items": {"type": "string", "enum": list(reply_rules.STANDARD_FIELDS)}},
          "own_details": {"type": "array", "items": {"type": "string"}},
          "when_to_ask": {"type": "string", "enum": list(reply_rules.TIMINGS)}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}",), screens=AREAS["assistant"])
async def update_reply_settings(tc, db, assistant_id, **given):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    keys = {"reply_length": "behaviour.reply_length", "language": "behaviour.language", "ask_for_contact": "behaviour.ask_for_contact",
            "offer_person": "behaviour.offer_human", "when_it_doesnt_know": "behaviour.fallback_followup",
            "collect_details": "behaviour.collect.enabled", "standard_details": "behaviour.collect.fields",
            "own_details": "behaviour.collect.custom", "when_to_ask": "behaviour.collect.timing"}
    values = {keys[k]: v for k, v in given.items()}
    if not values:
        raise ToolError("Say what to change.")
    names = {v: k.replace("_", " ") for k, v in keys.items()}
    return await _change_assistant(tc, db, bot, values, "reply settings", names)


@tool("add_knowledge_text", "Add facts to an assistant's written knowledge (prices, timings, policies, answers): it "
      "answers from them from then on. Only facts the person gave you or a tool found: never write them yourself.",
      "Adding to the knowledge",
      {"type": "object", "required": ["assistant_id", "text"], "properties": {
          **ASSISTANT, "text": {"type": "string", "description": "The facts, in plain words (up to 5,000 characters)."}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}",), screens=AREAS["assistant"])
async def add_knowledge_text(tc, db, assistant_id, text):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    if len(text) > 5000:
        raise ToolError("That's too much to add at once (up to 5,000 characters).")
    written, blocks = knowledge_sources.split(bot.knowledge_base or "")
    new = knowledge_sources.join((written.rstrip() + "\n\n" + text.strip()).strip(), blocks)
    change = await _change_assistant(tc, db, bot, {"knowledge": _without_summary(new)}, "knowledge", {"knowledge": "knowledge"})
    change.summary = f"{bot.bot_name}: added to the knowledge: {_short(text.strip(), 80)}"
    return change


@tool("add_website_to_knowledge", "Read a website (its pages, the PDFs it links to, its contact details) into an "
      "assistant's knowledge. Takes up to two minutes for a whole site.", "Reading the website",
      {"type": "object", "required": ["assistant_id", "url"], "properties": {
          **ASSISTANT, "url": {"type": "string", "description": "The website address, e.g. https://example.com"},
          "pages": {"type": "integer", "description": "How many pages to read: 1 for just that page, up to 100. Default 25."}}},
      level="change", roles=MANAGERS, routes=("POST /api/knowledge/crawl",), screens=AREAS["assistant"])
async def add_website_to_knowledge(tc, db, assistant_id, url, pages=25):
    from routers.bots import KnowledgeCrawlRequest, crawl_website
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    before = await _read_assistant(tc.ctx, db, bot.bot_id, ["knowledge"])
    url = url.strip() if url.strip().startswith(("http://", "https://")) else "https://" + url.strip()
    result = await crawl_website(KnowledgeCrawlRequest(bot_id=bot.bot_id, url=url, pages=max(1, min(int(pages), 100))), ctx=tc.ctx, db=db)
    if result.get("error"):
        raise ToolError(result["error"])
    after = await _read_assistant(tc.ctx, db, bot.bot_id, ["knowledge"])
    return Change(f"{bot.bot_name}: read {url} into the knowledge ({result.get('message', '')})", "assistant", bot.bot_id,
                  before, after, {"kind": "assistant", "id": bot.bot_id}, {"pages_read": result.get("pages")})


@tool("remove_knowledge_source", "Remove one website, video or file from an assistant's knowledge (names from "
      "get_assistant's knowledge sources).", "Removing a knowledge source",
      {"type": "object", "required": ["assistant_id", "name"], "properties": {**ASSISTANT, "name": {"type": "string"}}},
      level="change", roles=MANAGERS, routes=("DELETE /api/bots/{bot_id}/knowledge/sources",), screens=AREAS["assistant"])
async def remove_knowledge_source(tc, db, assistant_id, name):
    from routers.bots import remove_source
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    if name == knowledge_sources.SUMMARY:
        raise ToolError("The business summary is written from the other sources; it can't be removed on its own.")
    before = await _read_assistant(tc.ctx, db, bot.bot_id, ["knowledge"])
    await remove_source(bot.bot_id, name, ctx=tc.ctx, db=db)
    after = await _read_assistant(tc.ctx, db, bot.bot_id, ["knowledge"])
    if before == after:
        raise ToolError(f'There is no source named "{name}".')
    return Change(f"{bot.bot_name}: removed {name} from the knowledge", "assistant", bot.bot_id, before, after,
                  {"kind": "assistant", "id": bot.bot_id})


@tool("edit_flow_block", "Change what one step of an assistant's flow says (step ids from get_flow). Its choices and "
      "links stay as they are; to change those, or add and remove steps, use write_flow.", "Editing the flow",
      {"type": "object", "required": ["assistant_id", "block_id", "message"], "properties": {
          **ASSISTANT, "block_id": {"type": "string"}, "message": {"type": "string", "description": "What the block says or asks."}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}",), screens=AREAS["assistant"], after=("get_flow",))
async def edit_flow_block(tc, db, assistant_id, block_id, message):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    data = _get(bot, f"flow_block.{block_id}")
    if data is None:
        raise ToolError("There's no block with that id in the flow (see get_flow).")
    if "message" not in data and data.get("label") in ("Start",):
        raise ToolError("The start block doesn't say anything.")
    new = {**data, "message": message.strip()[:1000]}
    change = await _change_assistant(tc, db, bot, {f"flow_block.{block_id}": new}, "flow", {})
    change.summary = f"{bot.bot_name}: flow block {block_id} now says {_short(message.strip(), 80)}"
    return change


# ─── One assistant set up like another ──────────────────────────────

PARTS = {"design": "design", "avatar": "avatar", "instructions": "instructions", "reply_settings": "reply settings",
         "knowledge": "knowledge", "flow": "flow"}
NOT_DESIGN = {"logo_url", "page_rule", "page_paths"}  # the picture is its own part; which pages it shows on is per website


@tool("copy_assistant_settings", "Copy settings from one assistant to another, exactly and in one step: design "
      "(colours, font, launcher, welcome message, suggested questions), avatar (its picture), instructions, "
      "reply_settings (reply rules and the details it collects), knowledge (everything it answers from, websites and "
      "files included), flow. Use it whenever they want an assistant set up like another one, rather than retyping: "
      "then copy every part unless they name some. Undo puts back what it had.", "Copying from another assistant",
      {"type": "object", "required": ["from_assistant_id", "to_assistant_id", "parts"], "properties": {
          "from_assistant_id": {"type": "string", "description": "The assistant to copy from."},
          "to_assistant_id": {"type": "string", "description": "The assistant that changes."},
          "parts": {"type": "array", "items": {"type": "string", "enum": list(PARTS)}}}},
      level="change", roles=MANAGERS, routes=("PATCH /api/bots/{bot_id}",), screens=AREAS["assistant"])
async def copy_assistant_settings(tc, db, from_assistant_id, to_assistant_id, parts):
    source = await get_owned_bot(from_assistant_id, tc.ctx, db)
    target = await get_owned_bot(to_assistant_id, tc.ctx, db)
    if source.bot_id == target.bot_id:
        raise ToolError("Those are the same assistant: say which one to copy from and which one changes.")
    parts = [p for p in dict.fromkeys(parts) if p in PARTS]
    if not parts:
        raise ToolError(f"Say which parts to copy: {', '.join(PARTS)}.")
    visual = source.visual_config or {}
    values: dict = {}
    groups: dict[str, list] = {}  # part -> its keys, to say what changed
    if "design" in parts:
        groups["design"] = [f"visual.{k}" for k in visual if k not in NOT_DESIGN]
        values.update({k: copy.deepcopy(visual[k[7:]]) for k in groups["design"]})
    if "avatar" in parts:
        groups["avatar"] = ["visual.logo_url"]
        values["visual.logo_url"] = visual.get("logo_url") or ""
    if "instructions" in parts:
        groups["instructions"] = ["instructions"]
        values["instructions"] = source.system_prompt or ""
    if "reply_settings" in parts:
        rules = reply_rules.clean(source.behaviour)
        groups["reply_settings"] = [f"behaviour.{k}" for k in rules]
        values.update({f"behaviour.{k}": copy.deepcopy(v) for k, v in rules.items()})
    if "knowledge" in parts:
        groups["knowledge"] = ["knowledge"]
        values["knowledge"] = _without_summary(source.knowledge_base or "")
    if "flow" in parts:
        groups["flow"] = ["flow"]
        values["flow"] = copy.deepcopy(source.flow_data or {"nodes": [], "edges": []})
    change = await _change_assistant(tc, db, target, values, "copied settings", {})
    differs = [p for p in parts if any(change.before.get(k) != change.after.get(k) for k in groups[p])]
    words = []
    for p in differs:
        if p == "design":
            n = sum(change.before.get(k) != change.after.get(k) for k in groups[p])
            words.append(f"design ({n} setting{'s' if n != 1 else ''})")
        elif p == "flow":
            n = len([x for x in (change.after.get("flow") or {}).get("nodes") or [] if x.get("type") != "start"])
            words.append(f"flow ({n} steps)")
        else:
            words.append(PARTS[p])
    same = [PARTS[p] for p in parts if p not in differs]
    change.summary = (f"{target.bot_name}: copied from {source.bot_name}: {', '.join(words) or 'nothing (already the same)'}"
                      + (f"; already the same: {', '.join(same)}" if same and words else ""))
    change.result = {"copied": [PARTS[p] for p in differs], "already_the_same": same}
    return change


# ─── Voice agents and their scripts ─────────────────────────────────

VOICE_FIELDS = {"language": "language", "voice_id": "voice", "follow_caller_language": "reply in the caller's language",
                "switch_languages": "languages it can switch to", "understand_code_mixed": "understand mixed language",
                "remember_callers": "remember callers", "speaking_rate": "speaking speed", "assistant_name": "introduces itself as",
                "company_name": "business name", "allow_interruptions": "let callers interrupt",
                "silence_timeout_sec": "seconds of silence before a reminder", "max_call_minutes": "longest call (minutes)",
                "end_call_phrases": "phrases that end the call", "ai_model": "AI model", "ambience": "background sound",
                "ambience_volume": "background volume", "transfer_when": "when to transfer", "voicemail_action": "if voicemail answers",
                "enabled": "calls"}


def _split(entity: str) -> tuple[str, str]:
    bot_id, _, direction = entity.partition(":")
    return bot_id, direction or "outbound"


async def _read_voice(ctx, db, entity: str, keys: list) -> dict:
    from voice.router import get_agent
    bot_id, direction = _split(entity)
    agent = await get_agent(bot_id, direction=direction, ctx=ctx, db=db)
    return {k: agent.get(k) for k in keys}


async def _write_voice(ctx, db, entity: str, values: dict) -> None:
    """Through the agent page's own save, with the whole form: today's settings and the new values."""
    from voice.router import AgentUpdate, get_agent, update_agent
    bot_id, direction = _split(entity)
    current = await get_agent(bot_id, direction=direction, ctx=ctx, db=db)
    data = {k: current[k] for k in AgentUpdate.model_fields if k in current}
    data.update(values)
    data.update(greeting=None, call_goal=None, collect_fields=None, functions=None)  # kept: edited on other pages
    try:
        form = AgentUpdate(**data)
    except ValidationError as e:
        first = e.errors()[0]
        raise ToolError(f"{'.'.join(map(str, first.get('loc', [])))}: {first.get('msg')}")
    await update_agent(bot_id, form, direction=direction, ctx=ctx, db=db)


adapter("voice_agent", _read_voice, _write_voice, lambda entity: {"kind": "voice_agent", "id": _split(entity)[0]})


@tool("update_voice_agent", "Change an assistant's phone agent for incoming or outgoing calls: language, voice, "
      "following the caller's language, remembering callers, speaking speed, how it introduces itself, interruptions, "
      "silence, longest call, phrases that end the call, AI model (ids from get_voice_agent's options), background "
      "sound. Only the inputs given change. Turning calls on or off: set_voice_calls.", "Changing the voice agent",
      {"type": "object", "required": ["assistant_id", "direction"], "properties": {
          **ASSISTANT, "direction": DIRECTION,
          "language": {"type": "string", "description": "A language code like en-IN, ta-IN, hi-IN."},
          "voice_id": {"type": "string"}, "follow_caller_language": {"type": "boolean"},
          "switch_languages": {"type": "array", "items": {"type": "string"}}, "understand_code_mixed": {"type": "boolean"},
          "remember_callers": {"type": "boolean"}, "speaking_rate": {"type": "number", "description": "0.7 to 1.3; 1 is normal."},
          "assistant_name": {"type": "string"}, "company_name": {"type": "string"}, "allow_interruptions": {"type": "boolean"},
          "silence_timeout_sec": {"type": "integer"}, "max_call_minutes": {"type": "integer"},
          "end_call_phrases": {"type": "array", "items": {"type": "string"}}, "ai_model": {"type": "string"},
          "ambience": {"type": "string"}, "ambience_volume": {"type": "string", "enum": ["low", "medium", "high"]}}},
      level="change", roles=MANAGERS, routes=("PUT /api/voice/agents/{bot_id}",), screens=AREAS["voice"])
async def update_voice_agent(tc, db, assistant_id, direction, **given):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    if not given:
        raise ToolError("Say what to change.")
    if "ai_model" in given:
        from voice import ai_models
        m = ai_models.AI_MODELS_BY_ID.get(given["ai_model"])
        if m is None:
            raise ToolError("Unknown AI model id.")
        if not ai_models.available(m):
            raise ToolError(f"{m.name} isn't available on this server yet.")
    entity = f"{bot.bot_id}:{direction}"
    before = await _read_voice(tc.ctx, db, entity, list(given))
    await _write_voice(tc.ctx, db, entity, given)
    after = await _read_voice(tc.ctx, db, entity, list(given))
    kind = "incoming" if direction == "inbound" else "outgoing"
    return Change(_summary(f"{bot.bot_name}: {kind} calls agent", before, after, VOICE_FIELDS), "voice_agent", entity,
                  before, after, {"kind": "voice_agent", "id": bot.bot_id})


SCRIPT_FIELDS = {"greeting": "opening line", "greeting_known": "opening for callers it knows", "personality": "personality",
                 "instructions": "instructions", "call_goal": "goal of the call"}


async def _read_script(ctx, db, entity: str, keys: list) -> dict:
    from voice.router import get_script
    bot_id, direction = _split(entity)
    script = await get_script(bot_id, direction, ctx=ctx, db=db)
    return {k: script.get(k) for k in keys}


async def _write_script(ctx, db, entity: str, values: dict) -> None:
    from voice.router import ScriptUpdate, get_script, update_script
    bot_id, direction = _split(entity)
    current = await get_script(bot_id, direction, ctx=ctx, db=db)
    data = {k: current[k] for k in ScriptUpdate.model_fields if k in current}
    data.update(values)
    try:
        form = ScriptUpdate(**data)
    except ValidationError as e:
        first = e.errors()[0]
        raise ToolError(f"{'.'.join(map(str, first.get('loc', [])))}: {first.get('msg')}")
    await update_script(bot_id, direction, form, ctx=ctx, db=db)


adapter("voice_script", _read_script, _write_script, lambda entity: {"kind": "voice_script", "id": _split(entity)[0]})


@tool("update_voice_script", "Change what an assistant's phone agent says (Voice > Knowledge): its opening line, the "
      "opening for callers it knows ({{name}} is their first name), personality, instructions, or the goal of the call.",
      "Changing the voice script",
      {"type": "object", "required": ["assistant_id", "direction"], "properties": {
          **ASSISTANT, "direction": DIRECTION, **{k: {"type": "string"} for k in SCRIPT_FIELDS}}},
      level="change", roles=MANAGERS, routes=("PUT /api/voice/scripts/{bot_id}/{direction}",), screens=AREAS["voice"])
async def update_voice_script(tc, db, assistant_id, direction, **given):
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    if not given:
        raise ToolError("Say what to change.")
    entity = f"{bot.bot_id}:{direction}"
    before = await _read_script(tc.ctx, db, entity, list(given))
    await _write_script(tc.ctx, db, entity, {k: v.strip() for k, v in given.items()})
    after = await _read_script(tc.ctx, db, entity, list(given))
    kind = "incoming" if direction == "inbound" else "outgoing"
    return Change(_summary(f"{bot.bot_name}: {kind} calls script", before, after, SCRIPT_FIELDS), "voice_script", entity,
                  before, after, {"kind": "voice_script", "id": bot.bot_id})


# ─── Unanswered questions ───────────────────────────────────────────

async def _read_question(ctx, db, gap_id: str, keys: list) -> dict:
    from routers.workspace import _owned_gap
    g = await _owned_gap(gap_id, ctx, db)
    return {k: getattr(g, k) or "" for k in keys}


async def _write_question(ctx, db, gap_id: str, values: dict) -> None:
    import assist
    from routers.workspace import _owned_gap
    g = await _owned_gap(gap_id, ctx, db)
    for k, v in values.items():
        setattr(g, k, v)
    await db.commit()
    assist.forget_answers(g.bot_id)


adapter("question", _read_question, _write_question, lambda gap_id: {"kind": "question", "id": gap_id})


@tool("answer_question", "Answer one of the questions an assistant couldn't answer (ids from get_unanswered_questions): "
      "it uses this answer from then on.", "Answering the question",
      {"type": "object", "required": ["question_id", "answer"], "properties": {
          "question_id": {"type": "string"}, "answer": {"type": "string", "description": "Up to 2,000 characters."}}},
      level="change", roles=MANAGERS, routes=("POST /api/questions/{gap_id}/answer",), screens=AREAS["assistant"])
async def answer_question(tc, db, question_id, answer):
    from routers.workspace import AnswerIn, answer_question as answer_route
    keys = ["status", "answer"]
    before = await _read_question(tc.ctx, db, question_id, keys)
    await answer_route(question_id, AnswerIn(answer=answer.strip()[:2000]), ctx=tc.ctx, db=db)
    after = await _read_question(tc.ctx, db, question_id, keys)
    question = (await _read_question(tc.ctx, db, question_id, ["question"]))["question"]
    return Change(f"Answered {_short(question, 80)}", "question", question_id, before, after, {"kind": "question", "id": question_id})
