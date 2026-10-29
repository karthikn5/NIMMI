"""
The agent's tools: what Nimmi can look at and do in the dashboard, each acting as the signed-in person, through the
same code (and so the same checks) as the dashboard's own requests. Calling a route function directly skips FastAPI's
dependencies, so each tool declares the roles its route requires.

Levels, enforced here and never left to the model:
- read: looks things up; runs freely.
- change: changes settings the person can undo; runs, and records exactly what it changed (the settings before and
  after, per setting) so Undo restores just those, and only if nobody changed them again since.
- confirm: does something that can't simply be undone, or that reaches other people (deleting, turning on calls that
  dial customers, inviting someone). The tool only proposes it: the panel shows what will happen, and it runs when the
  person clicks Confirm there (confirm_action). Proposals expire after CONFIRM_MINUTES.
Paying, buying and upgrading are never tools: the agent opens the page and the person decides there.

Inputs are checked before a tool runs, errors go back to the model as plain words with their kind (the input, a
permission, the plan, not found, busy, a passing failure), results are clipped, and anything that looks like a secret
is hidden from the model. Text written by other people is marked as data (untrusted()). A lookup that hit a passing
failure (the database or a service for a moment) is tried once more before the model hears of it.

Some tools are for Nimmi's own work, not the dashboard (`internal`: keeping the plan, loading another area's tools):
they act on the run (ToolContext.run), never show as steps in the panel and are never offered over MCP.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import database
from auth import AuthContext

logger = logging.getLogger(__name__)

LEVELS = ("read", "change", "confirm")
ALL_ROLES = ("owner", "admin", "agent")
MANAGERS = ("owner", "admin")
RESULT_CHARS = 8000
CONFIRM_MINUTES = 15
TOOLS: dict[str, "Tool"] = {}
ADAPTERS: dict[str, "Adapter"] = {}
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
# Sealed columns (secretbox), API keys and tokens of the services Nimmi uses, and signed tokens: never shown to a model.
_SECRET = re.compile(
    r"enc:v1:[\w\-=.]+|\b(?:sk|rk)-[A-Za-z0-9_\-]{16,}|\bgsk_[A-Za-z0-9]{20,}|\bAIza[0-9A-Za-z_\-]{30,}"
    r"|\bAQ\.[A-Za-z0-9_\-]{20,}|\brzp_(?:live|test)_[A-Za-z0-9]{8,}|\bEAA[A-Za-z0-9]{40,}|\bsb_secret_[A-Za-z0-9_\-]{10,}"
    r"|\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")


class ToolError(Exception):
    """A tool couldn't do what was asked; the message goes back to the model (or the panel) as it is. `kind` says
    what sort of problem it is (ERROR_KINDS), so the model knows whether to fix its inputs or do something else."""

    def __init__(self, message: str, kind: str = "invalid_input"):
        super().__init__(message)
        self.kind = kind


ERROR_KINDS = ("invalid_input", "not_allowed", "needs_paid_plan", "not_found", "conflict", "busy", "temporary", "internal")


@dataclass
class ToolContext:
    ctx: AuthContext
    run_id: str
    thread_id: str
    screen: dict
    tool_call_id: Optional[str] = None
    actions: list = field(default_factory=list)  # what the panel does after the tool: go to a page, point, refresh
    run: Any = None  # the answer's own state (loop.RunState): its plan and areas, for the internal tools
    usage: list = field(default_factory=list)  # AI models a tool used itself (draft_flow): counted with the run

    def act(self, name: str, value: dict) -> None:
        self.actions.append({"name": name, "value": value})


@dataclass
class Change:
    """What a change tool did. `before` and `after` hold only the settings it changed (keys the adapter understands),
    so Undo restores just those. `refresh` tells the open page what to reload."""
    summary: str
    adapter: str
    entity_id: str
    before: dict
    after: dict
    refresh: dict
    result: Any = None  # anything else the model should read


@dataclass(frozen=True)
class Adapter:
    """Reads and writes one kind of settings, for undo: read(ctx, db, entity_id, keys) -> {key: value};
    write(ctx, db, entity_id, values) -> None (it commits)."""
    read: Callable[..., Awaitable[dict]]
    write: Callable[..., Awaitable[None]]
    refresh: Callable[[str], dict]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[Any]]
    label: str
    level: str = "read"
    roles: tuple = ALL_ROLES
    screens: tuple = ()
    preview: Optional[Callable[..., Awaitable[dict]]] = None  # confirm: (tc, db, **inputs) -> {"title", "summary"}
    routes: tuple = ()  # the API routes it does the work of ("GET /api/bots"), for the parity check
    internal: bool = False  # Nimmi's own work (the plan, loading tools): not a step in the panel, not on MCP
    after: tuple = ()  # offered in an answer only once one of these tools ran in it (write_flow: after get_flow)


def tool(name: str, description: str, label: str, parameters: Optional[dict] = None, *, level: str = "read",
         roles: tuple = ALL_ROLES, screens: tuple = (), preview=None, routes: tuple = (), internal: bool = False,
         after: tuple = ()):
    """Register a tool. Its handler gets (ToolContext, db session, **inputs). A read tool returns what the model reads;
    a change tool returns a Change; a confirm tool needs `preview` and its handler runs only once confirmed."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}")
    if level == "confirm" and preview is None:
        raise ValueError(f"{name}: a confirm-level tool needs a preview")

    def register(fn):
        TOOLS[name] = Tool(name, description, parameters or {"type": "object", "properties": {}}, fn, label, level,
                           roles, screens, preview, routes, internal, after)
        return fn
    return register


def adapter(name: str, read, write, refresh) -> None:
    ADAPTERS[name] = Adapter(read, write, refresh)


def available(role: str, screen_id: Optional[str], areas=()) -> list[Tool]:
    """The tools for this person on this screen: everyday ones everywhere, each area's on its own screens, the areas
    a request needs (`areas`: intake's or load_tools'), and all of them on a screen nobody described."""
    from agent.screens import AREAS, SCREENS
    known = screen_id in SCREENS
    wanted = {screen_id, *(s for a in areas for s in AREAS.get(a, ()))}
    return [t for t in TOOLS.values()
            if role in t.roles and (not t.screens or not known or wanted.intersection(t.screens))]


def specs(tools: list[Tool], screen_id: Optional[str] = None) -> list[dict]:
    """The tools as the models take them. A tool without inputs has no `parameters` (Gemini refuses an empty list).
    point_at lists only what can be on this screen: the top bar's menus, and this area's tabs and buttons."""
    out = []
    for t in tools:
        spec = {"name": t.name, "description": t.description}
        if t.parameters.get("properties"):
            spec["parameters"] = t.parameters
        if t.name == "point_at" and screen_id:
            area = "builder." if screen_id == "builder" else "voice." if screen_id.startswith("voice") else \
                "whatsapp." if screen_id.startswith("whatsapp") else None
            element = t.parameters["properties"]["element"]
            names = [n for n in element["enum"] if n.startswith("nav.") or (area and n.startswith(area))]
            spec["parameters"] = {**t.parameters, "properties": {"element": {**element, "enum": names}}}
        out.append(spec)
    return out


def label(name: str) -> str:
    t = TOOLS.get(name)
    return t.label if t else name.replace("_", " ").capitalize()


def check_inputs(schema: dict, given: dict) -> tuple[dict, Optional[str]]:
    """The inputs the tool declares, of the right type; anything else is dropped. Returns (inputs, problem)."""
    clean = {}
    for key, spec in (schema.get("properties") or {}).items():
        value = given.get(key)
        if value is None or value == "":
            continue
        kind = spec.get("type")
        if kind in ("integer", "number") and isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                return {}, f"'{key}' should be a number"
        if kind == "integer" and isinstance(value, float) and value.is_integer():
            value = int(value)  # JSON from some models has 3.0 for 3
        if kind == "boolean" and isinstance(value, str) and value.lower() in ("true", "false"):
            value = value.lower() == "true"
        if kind in _TYPES and (not isinstance(value, _TYPES[kind]) or (kind in ("integer", "number") and isinstance(value, bool))):
            return {}, f"'{key}' should be a{'n' if kind[0] in 'aeiou' else ''} {kind}"
        if "enum" in spec and value not in spec["enum"]:
            return {}, f"'{key}' must be one of: {', '.join(map(str, spec['enum']))}"
        if kind == "array" and isinstance(spec.get("items"), dict) and spec["items"].get("type") == "string":
            value = [str(v) for v in value if str(v).strip()]
        clean[key] = value
    missing = [k for k in schema.get("required") or [] if k not in clean]
    if missing:
        return {}, "Missing: " + ", ".join(missing)
    return clean, None


def untrusted(value: Any) -> str:
    """Text written by other people (customers' messages, leads, call summaries, website pages): marked so the model
    reads it as information, never as instructions (the prompt says so)."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return "<data>" + text.replace("</data>", "") + "</data>"


def hide_secrets(text: str) -> str:
    return _SECRET.sub("[hidden]", text)


def dump(result: Any) -> str:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
    text = hide_secrets(text)
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + " ...(cut short)"


def _error(e: Exception, name: str, run_id: str) -> tuple[str, str]:
    """The problem in words, and its kind (ERROR_KINDS)."""
    if isinstance(e, HTTPException):
        status = e.status_code
        kind = ("not_allowed" if status in (401, 403) else "needs_paid_plan" if status == 402 else
                "not_found" if status == 404 else "conflict" if status == 409 else "busy" if status == 429 else
                "temporary" if status >= 500 else "invalid_input")
        return (e.detail if isinstance(e.detail, str) else "That didn't work."), kind
    if isinstance(e, ToolError):
        return str(e), e.kind
    from agent.providers import ModelError
    if isinstance(e, ModelError):  # a tool that uses an AI itself (draft_flow) found it busy
        return ("The AI service is busy right now, so this didn't work. Try it again in a minute." if e.busy else
                "The AI service didn't answer, so this didn't work. Try it again in a minute."), "busy" if e.busy else "temporary"
    if isinstance(e, (TimeoutError, httpx.TimeoutException, httpx.NetworkError)):
        logger.warning(f"Agent tool {name} timed out or lost its connection (run {run_id}): {e!r}")
        return "A service didn't answer in time, so this didn't work. Try again in a moment.", "temporary"
    logger.exception(f"Agent tool {name} failed (run {run_id})")
    return "Something went wrong inside Nimmi, so this didn't work. Try again in a moment.", "internal"


@dataclass
class Outcome:
    """What a tool run gives the loop: the model's text, whether it worked, and for the panel the action it recorded."""
    text: str
    ok: bool
    action_id: Optional[str] = None
    undoable: bool = False
    proposed: Optional[dict] = None  # confirm level: {"actionId", "title", "summary"}
    kind: Optional[str] = None  # a problem's kind (ERROR_KINDS); "repeat": the loop answered from an earlier call
    summary: Optional[str] = None  # what a change did, or what waits for Confirm, in words (the run's ledger)


async def _record(db: AsyncSession, tc: ToolContext, tool_name: str, **fields) -> str:
    from backend.models import AgentAction
    row = AgentAction(owner_id=tc.ctx.owner_id, user_id=tc.ctx.user_id, thread_id=tc.thread_id, run_id=tc.run_id,
                      tool_call_id=tc.tool_call_id, tool=tool_name, **fields)
    db.add(row)
    await db.commit()
    return row.id


def failed(message: str, kind: str) -> Outcome:
    return Outcome(dump({"error": message, "kind": kind}), False, kind=kind)


async def run(tc: ToolContext, name: str, inputs: dict) -> Outcome:
    """Run one tool for the model. A lookup that hit a passing failure is tried once more."""
    t = TOOLS.get(name)
    if t is None:
        return failed(f"There is no tool named {name}.", "invalid_input")
    if tc.ctx.role not in t.roles:
        return failed("The person's role in this workspace doesn't allow this.", "not_allowed")
    clean, problem = check_inputs(t.parameters, inputs if isinstance(inputs, dict) else {})
    if problem:
        return failed(problem, "invalid_input")
    outcome = await _run_once(tc, t, clean)
    if outcome.kind == "temporary" and t.level == "read":
        await asyncio.sleep(0.5)
        outcome = await _run_once(tc, t, clean)
    return outcome


async def _run_once(tc: ToolContext, t: Tool, clean: dict) -> Outcome:
    name = t.name
    try:
        async with database.async_session() as db:
            if t.level == "confirm":
                plan = await t.preview(tc, db, **clean)
                action_id = await _record(db, tc, name, inputs=clean, title=plan["title"], summary=plan["summary"], state="proposed")
                proposed = {"actionId": action_id, "title": plan["title"], "summary": plan["summary"]}
                return Outcome(dump({"waiting_for_confirmation": plan["summary"],
                                     "note": "Nothing has happened yet. The person sees Confirm and Cancel buttons in the "
                                             "panel; tell them in one line what happens if they confirm."}),
                               True, action_id, proposed=proposed, summary=plan["summary"])
            result = await t.handler(tc, db, **clean)
            if t.level == "change":
                if not isinstance(result, Change):
                    raise TypeError(f"{name} is a change tool but returned {type(result).__name__}")
                if result.before == result.after:
                    return Outcome(dump({"unchanged": "It was already set that way.", **({"details": result.result} if result.result else {})}), True)
                action_id = await _record(db, tc, name, summary=result.summary, adapter=result.adapter,
                                          entity_id=result.entity_id, before=result.before, after=result.after)
                tc.act("changed", result.refresh)
                return Outcome(dump({"done": result.summary, **({"details": result.result} if result.result else {}),
                                     "note": "They can undo it with the Undo link next to this step in your panel (not on the page)."}),
                               True, action_id, undoable=True, summary=result.summary)
    except Exception as e:  # noqa: BLE001 (each kind is turned into words in _error)
        return failed(*_error(e, name, tc.run_id))
    return Outcome(dump(result), True)


# ─── After the run: confirm, cancel, undo (the panel's buttons) ─────

async def _own_action(db: AsyncSession, ctx: AuthContext, action_id: str):
    from backend.models import AgentAction
    row = await db.get(AgentAction, (action_id or "")[:36])
    if row is None or row.owner_id != ctx.owner_id or row.user_id != ctx.user_id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


async def confirm_action(ctx: AuthContext, action_id: str) -> dict:
    """The person clicked Confirm: run what was proposed, as them, with today's role and checks."""
    from agent.events import aware, now
    async with database.async_session() as db:
        row = await _own_action(db, ctx, action_id)
        if row.state != "proposed":
            raise HTTPException(status_code=409, detail=f"This was already {row.state}.")
        if aware(row.created_at) < now() - timedelta(minutes=CONFIRM_MINUTES):
            row.state, row.decided_at = "expired", now()
            await db.commit()
            raise HTTPException(status_code=409, detail="This waited too long, so it wasn't done. Ask Nimmi again.")
        t = TOOLS.get(row.tool)
        if t is None or ctx.role not in t.roles:
            raise HTTPException(status_code=403, detail="Your role doesn't allow this")
        row.state, row.decided_at = "confirming", now()  # a second click can't run it twice
        await db.commit()
        tc = ToolContext(ctx=ctx, run_id=row.run_id or "", thread_id=row.thread_id or "", screen={}, tool_call_id=row.tool_call_id)
        try:
            result = await t.handler(tc, db, **(row.inputs or {}))
        except Exception as e:  # noqa: BLE001
            row.state, row.error = "failed", _error(e, row.tool, row.run_id or "")[0]
            await db.commit()
            return {"state": "failed", "message": row.error, "summary": row.summary}
        if isinstance(result, Change):
            row.adapter, row.entity_id, row.before, row.after = result.adapter, result.entity_id, result.before, result.after
            tc.act("changed", result.refresh)
            message = result.summary
        elif isinstance(result, dict):
            message = result.get("message")
            if result.get("refresh"):
                tc.act("changed", result["refresh"])
        else:
            message = str(result or "Done.")
        row.state = "done"
        await db.commit()
    return {"state": "done", "message": message or "Done.", "summary": row.summary, "undoable": bool(row.adapter),
            "refresh": [a["value"] for a in tc.actions if a["name"] == "changed"]}


async def cancel_action(ctx: AuthContext, action_id: str) -> dict:
    from agent.events import now
    async with database.async_session() as db:
        row = await _own_action(db, ctx, action_id)
        if row.state != "proposed":
            raise HTTPException(status_code=409, detail=f"This was already {row.state}.")
        row.state, row.decided_at = "cancelled", now()
        await db.commit()
        return {"state": "cancelled", "summary": row.summary}


async def undo_action(ctx: AuthContext, action_id: str) -> dict:
    """Put back the settings a change set, if they're still as it left them."""
    from agent.events import now
    async with database.async_session() as db:
        row = await _own_action(db, ctx, action_id)
        if row.state != "done" or not row.adapter or row.before is None:
            raise HTTPException(status_code=409, detail="This can't be undone." if row.state == "done" else f"This was already {row.state}.")
        a = ADAPTERS[row.adapter]
        t = TOOLS.get(row.tool)
        if t is not None and ctx.role not in t.roles:
            raise HTTPException(status_code=403, detail="Your role doesn't allow this")
        current = await a.read(ctx, db, row.entity_id, list(row.after))
        if json.dumps(current, sort_keys=True, default=str) != json.dumps(row.after, sort_keys=True, default=str):
            raise HTTPException(status_code=409, detail="This was changed again since, so undo would overwrite the newer "
                                                        "change. Change it back on the page instead.")
        await a.write(ctx, db, row.entity_id, row.before)
        row.state, row.decided_at = "undone", now()
        await db.commit()
        return {"state": "undone", "summary": row.summary, "refresh": [a.refresh(row.entity_id)]}


async def undo_run(ctx: AuthContext, run_id: str) -> dict:
    """Undo every change one answer made, newest first (so each finds the settings as it left them). A change that
    was changed again since is kept, with the reason."""
    from sqlalchemy import select
    from backend.models import AgentAction
    async with database.async_session() as db:
        rows = (await db.execute(select(AgentAction).where(
            AgentAction.run_id == run_id, AgentAction.owner_id == ctx.owner_id, AgentAction.user_id == ctx.user_id,
            AgentAction.state == "done", AgentAction.adapter.isnot(None)).order_by(AgentAction.created_at.desc()))).scalars().all()
    undone, kept, refresh = [], [], []
    for row in rows:
        try:
            result = await undo_action(ctx, row.id)
        except HTTPException as e:
            kept.append({"actionId": row.id, "summary": row.summary, "reason": e.detail})
            continue
        undone.append({"actionId": row.id, "summary": result["summary"]})
        refresh += [r for r in result["refresh"] if r not in refresh]
    return {"undone": undone, "kept": kept, "refresh": refresh}
