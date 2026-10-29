"""
Nimmi over MCP (phase 6): the same tools the panel's agent uses, for AI apps (Claude Code, Claude Desktop, Cursor,
VS Code, and more), at POST /mcp. Same people, roles, plan rules, checks and levels: read tools run, change tools are
recorded and can be undone in Nimmi, and confirm-level tools only propose; the person confirms in Nimmi's panel
(Changes). Paying stays a person's job.

Protocol: the MCP revision 2026-07-28 (stateless: the version and the client's details come in each request's _meta;
server/discover; resultType on every result; tools/list cacheable), and the earlier, handshake revisions for apps that
open with "initialize" (2025-11-25, 2025-06-18, 2025-03-26): a dual-era server, as the spec allows. No sessions, so
any of the server's processes answers any request. Responses are JSON (no SSE stream: no tool here needs one).

Sign-in: a Nimmi key (Authorization: Bearer nmk_...), made on the Profile page; only its hash is kept. OAuth sign-in
(for claude.ai and ChatGPT connectors) is the next step.
"""
import hashlib
import json
import logging
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import agent.tools  # noqa: F401  (registers the tools)
import database
from agent import registry
from agent.events import aware, now
from auth import AuthContext, get_ctx, rate_limit
from backend.models import AgentKey, TeamMember
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])
MODERN = ["2026-07-28"]
LEGACY = ["2025-11-25", "2025-06-18", "2025-03-26"]
SERVER = {"name": "nimmi", "title": "Nimmi AI", "version": "1.0.0"}
INSTRUCTIONS = ("Nimmi AI runs AI assistants for Indian businesses on their website chat, WhatsApp and phone calls. These "
                "tools work in the person's own Nimmi workspace with their role. Read tools look things up; change tools "
                "change settings and can be undone in Nimmi; tools marked destructive only propose: the person confirms "
                "them in Nimmi (the Nimmi panel > Changes). Keys and passwords never go through these tools.")
# The panel's own tools: they move the dashboard's screen or show cards there.
PANEL_ONLY = {"go_to", "point_at", "start_agent_builder"}
CALLS_PER_MINUTE = 120


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _ctx_for_key(request: Request) -> tuple[AuthContext, AgentKey]:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token.startswith("nmk_"):
        raise HTTPException(status_code=401, detail="A Nimmi key is needed (Authorization: Bearer nmk_...)",
                            headers={"WWW-Authenticate": 'Bearer realm="nimmi"'})
    async with database.async_session() as db:
        key = (await db.execute(select(AgentKey).where(AgentKey.token_hash == _hash(token)))).scalars().first()
        if key is None or key.revoked_at is not None:
            raise HTTPException(status_code=401, detail="This Nimmi key isn't valid any more",
                                headers={"WWW-Authenticate": 'Bearer realm="nimmi", error="invalid_token"'})
        role = "owner"
        if key.owner_id != key.user_id:  # a teammate's key: the role they have today, if they're still on the team
            member = (await db.execute(select(TeamMember).where(TeamMember.owner_id == key.owner_id, TeamMember.member_id == key.user_id,
                                                                TeamMember.status == "active"))).scalars().first()
            if member is None:
                raise HTTPException(status_code=401, detail="This key's owner is no longer on that team")
            role = member.role
        key.last_used_at = now()
        await db.commit()
    return AuthContext(user_id=key.user_id, owner_id=key.owner_id, role=role), key


def _tools_for(ctx: AuthContext) -> list[dict]:
    out = []
    for t in sorted(registry.available(ctx.role, None), key=lambda t: t.name):  # a steady order (cacheable)
        if t.name in PANEL_ONLY:
            continue
        spec = {"name": t.name, "title": t.label, "description": t.description,
                "inputSchema": t.parameters if t.parameters.get("properties") else {"type": "object", "properties": {}},
                "annotations": {"title": t.label, "readOnlyHint": t.level == "read", "destructiveHint": t.level == "confirm",
                                "idempotentHint": t.level == "read", "openWorldHint": False}}
        if t.level == "confirm":
            spec["description"] += " Only proposes it: the person confirms in Nimmi (the Nimmi panel > Changes)."
        out.append(spec)
    return out


def _error(id_: Any, code: int, message: str, data: Any = None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": error}


def _result(id_: Any, result: dict, modern: bool) -> dict:
    if modern:
        result = {"resultType": "complete", **result, "_meta": {"io.modelcontextprotocol/serverInfo": SERVER}}
    return {"jsonrpc": "2.0", "id": id_, "result": result}


async def _call(ctx: AuthContext, key: AgentKey, params: dict) -> dict:
    name = params.get("name")
    t = registry.TOOLS.get(name)
    if t is None or name in PANEL_ONLY or ctx.role not in t.roles:
        return {"content": [{"type": "text", "text": f"There is no tool named {name}."}], "isError": True}
    tc = registry.ToolContext(ctx=ctx, run_id=f"mcp:{key.id}", thread_id=None, screen={"id": "mcp"})
    outcome = await registry.run(tc, name, params.get("arguments") or {})
    text = outcome.text
    if outcome.proposed:
        text = json.dumps({"waiting_for_confirmation": outcome.proposed["summary"],
                           "how": "Nothing has happened yet. The person confirms it in Nimmi: open the Nimmi panel in "
                                  "the dashboard > Changes > Waiting for you.",
                           "action_id": outcome.action_id}, ensure_ascii=False)
    elif outcome.undoable:
        text = text.replace("with the Undo link next to this step in your panel (not on the page)",
                            "in Nimmi: the Nimmi panel > Changes > Undo")
    return {"content": [{"type": "text", "text": text}], "isError": not outcome.ok}


@router.post("/mcp")
async def mcp(request: Request):
    ctx, key = await _ctx_for_key(request)
    rate_limit(f"mcp:{key.id}", CALLS_PER_MINUTE, 60)
    try:
        message = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return JSONResponse(_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid request"), status_code=400)
    method, id_ = message["method"], message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if id_ is None:  # a notification (notifications/initialized and the like): nothing to answer
        return Response(status_code=202)
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    version = meta.get("io.modelcontextprotocol/protocolVersion") or request.headers.get("mcp-protocol-version")
    if method == "initialize":  # a legacy app: the handshake revision it asks for, if we speak it
        asked = params.get("protocolVersion")
        chosen = asked if asked in LEGACY else LEGACY[0]
        return JSONResponse(_result(id_, {"protocolVersion": chosen, "capabilities": {"tools": {"listChanged": False}},
                                          "serverInfo": SERVER, "instructions": INSTRUCTIONS}, modern=False))
    modern = version in MODERN
    if version and version not in MODERN + LEGACY:
        return JSONResponse(_error(id_, -32022, "Unsupported protocol version", {"supported": MODERN + LEGACY, "requested": version}))
    if method == "server/discover":
        return JSONResponse(_result(id_, {"supportedVersions": MODERN + LEGACY, "capabilities": {"tools": {}},
                                          "instructions": INSTRUCTIONS, "ttlMs": 3_600_000, "cacheScope": "public"}, modern=True))
    if method == "ping":  # removed in 2026-07-28; legacy apps still send it
        return JSONResponse(_result(id_, {}, modern))
    if method == "tools/list":
        return JSONResponse(_result(id_, {"tools": _tools_for(ctx), "ttlMs": 300_000, "cacheScope": "private"}, modern))
    if method == "tools/call":
        if not isinstance(params.get("name"), str):
            return JSONResponse(_error(id_, -32602, "Invalid params: name is required"))
        return JSONResponse(_result(id_, await _call(ctx, key, params), modern))
    if method in ("resources/list", "prompts/list"):
        return JSONResponse(_result(id_, {method.split("/")[0]: [], "ttlMs": 3_600_000, "cacheScope": "public"}, modern))
    return JSONResponse(_error(id_, -32601, f"Method not found: {method}"))


@router.get("/mcp")
async def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})  # no server-started stream here


# ─── Nimmi keys (Profile) ───────────────────────────────────────────

class KeyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


@router.get("/api/agent/keys")
async def list_keys(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentKey).where(AgentKey.user_id == ctx.user_id, AgentKey.owner_id == ctx.owner_id,
                                                    AgentKey.revoked_at.is_(None)).order_by(AgentKey.created_at.desc()))).scalars().all()
    return [{"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": aware(k.created_at).isoformat(),
             "last_used_at": aware(k.last_used_at).isoformat() if k.last_used_at else None} for k in rows]


@router.post("/api/agent/keys")
async def create_key(body: KeyIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    count = len((await db.execute(select(AgentKey.id).where(AgentKey.user_id == ctx.user_id, AgentKey.revoked_at.is_(None)))).all())
    if count >= 10:
        raise HTTPException(status_code=400, detail="You have 10 keys already. Revoke one you don't use first.")
    token = "nmk_" + secrets.token_urlsafe(30)
    key = AgentKey(owner_id=ctx.owner_id, user_id=ctx.user_id, name=body.name.strip(), prefix=token[:10], token_hash=_hash(token))
    db.add(key)
    await db.commit()
    return {"id": key.id, "name": key.name, "prefix": key.prefix, "key": token}  # the only time the key is shown


@router.delete("/api/agent/keys/{key_id}")
async def revoke_key(key_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    key = await db.get(AgentKey, (key_id or "")[:36])
    if key is None or key.user_id != ctx.user_id or key.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    key.revoked_at = now()
    await db.commit()
    return {"revoked": True}
