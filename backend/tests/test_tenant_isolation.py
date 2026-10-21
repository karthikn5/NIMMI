"""
Tenant isolation: every signed-in endpoint, called by workspace B with workspace A's IDs, must
neither show A's data nor change it. Routes are discovered from the app, so new endpoints are
covered automatically.
"""
import json
import re
import uuid
from datetime import datetime, timedelta

from fastapi.routing import APIRoute
from sqlalchemy.future import select

import main
from database import async_session
from backend.models import (Bot, CallbackJob, CallLog, Campaign, Conversation, DncEntry, EmailBroadcast, EmailJob,
                            KnowledgeGap, Message, PhoneNumber, SavedReply, TeamMember, TelephonyAccount)

MARK = "MARKER-A-" + uuid.uuid4().hex[:6]

OWNED = [Bot, Conversation, Message, CallLog, Campaign, CallbackJob, PhoneNumber, TelephonyAccount, EmailJob,
         EmailBroadcast, TeamMember, DncEntry, KnowledgeGap, SavedReply]


async def _seed(owner: str, bot_id: str) -> dict:
    ids = {k: str(uuid.uuid4()) for k in ("conversation_id", "call_id", "campaign_id", "number_id", "account_id",
                                          "job_id", "email_job_id", "broadcast_id", "member_id", "entry_id",
                                          "gap_id", "reply_id")}
    async with async_session() as db:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        bot.bot_name, bot.knowledge_base, bot.system_prompt = f"{MARK} bot", f"{MARK} secret knowledge", f"{MARK} prompt"
        bot.ai_api_key = f"{MARK}-api-key"
        db.add_all([
            Conversation(conversation_id=ids["conversation_id"], bot_id=bot_id, visitor_session_id=f"s-{MARK}",
                         captured_data={"Email": "a-customer@example.com", "Note": MARK}, handoff_status="pending",
                         handoff_requested=True),
            CallLog(id=ids["call_id"], user_id=owner, bot_id=bot_id, caller_e164="+919800000099", summary=MARK,
                    captured={"Name": MARK}, transcript=[{"role": "user", "text": MARK}], recording_path="local:none.wav"),
            Campaign(id=ids["campaign_id"], user_id=owner, bot_id=bot_id, name=MARK, status="paused"),
            CallbackJob(id=ids["job_id"], user_id=owner, bot_id=bot_id, e164="+919800000098", name=MARK,
                        consent_source=MARK, status="queued", next_attempt_at=datetime.utcnow() + timedelta(days=1)),
            PhoneNumber(id=ids["number_id"], user_id=owner, number=f"+1 415 555 0199 {MARK}", e164="+14155550199",
                        status="active", provider="twilio", bot_id=bot_id),
            TelephonyAccount(id=ids["account_id"], user_id=owner, provider="twilio", label=MARK, account_sid="AC" + "1" * 32,
                             secrets="sealed", webhook_token=uuid.uuid4().hex),
            EmailJob(id=ids["email_job_id"], user_id=owner, kind="chat_lead", ref_id=ids["conversation_id"],
                     to_email="a-customer@example.com", subject=MARK, body=MARK, status="queued",
                     send_at=datetime.utcnow() + timedelta(days=1), automation="chat_lead", step=1),
            EmailBroadcast(id=ids["broadcast_id"], user_id=owner, subject=MARK, body=MARK, recipients=1),
            TeamMember(id=ids["member_id"], owner_id=owner, email=f"{MARK.lower()}@example.com", role="agent",
                       status="invited", invite_token=uuid.uuid4().hex),
            DncEntry(id=ids["entry_id"], user_id=owner, e164="+919800000097", reason=MARK),
            KnowledgeGap(id=ids["gap_id"], bot_id=bot_id, question=MARK, normalized=MARK.lower(), status="open"),
            SavedReply(id=ids["reply_id"], user_id=owner, title=MARK[:40], body=MARK),
        ])
        await db.flush()
        db.add(Message(conversation_id=ids["conversation_id"], role="user", content=MARK))
        await db.commit()
    ids["bot_id"] = bot_id
    return ids


async def _snapshot(owner: str, bot_id: str) -> dict:
    """Everything workspace A owns, as comparable text."""
    out = {}
    async with async_session() as db:
        for model in OWNED:
            cols = model.__table__.columns
            q = select(model)
            if "user_id" in cols:
                q = q.where(model.user_id == owner)
            elif "owner_id" in cols:
                q = q.where(model.owner_id == owner)
            elif "bot_id" in cols:
                q = q.where(model.bot_id == bot_id)
            elif model is Message:
                q = q.join(Conversation, Conversation.conversation_id == Message.conversation_id).where(Conversation.bot_id == bot_id)
            for row in (await db.execute(q)).scalars().all():
                key = (model.__tablename__, str(getattr(row, list(model.__table__.primary_key.columns)[0].name)))
                out[key] = json.dumps({c.name: getattr(row, c.name) for c in cols}, default=str, sort_keys=True)
    return out


def _example(schema: dict, defs: dict, ids: dict, name: str = ""):
    """A minimal valid value for a JSON schema, preferring workspace A's IDs for id-like fields."""
    if "$ref" in schema:
        return _example(defs[schema["$ref"].split("/")[-1]], defs, ids, name)
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"] or schema["anyOf"]
        return _example(options[0], defs, ids, name)
    if name in ids:
        return ids[name]
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {k: _example(v, defs, ids, k) for k, v in props.items() if k in schema.get("required", [])}
    if t == "array":
        return []
    if t == "boolean":
        return True
    if t in ("integer", "number"):
        return schema.get("minimum", schema.get("exclusiveMinimum", 0) + 1 if "exclusiveMinimum" in schema else 1)
    if "email" in name:
        return "b-user@example.com"
    return "x"


def _body(route: APIRoute, ids: dict):
    field = route.body_field
    if field is None:
        return None
    try:
        from pydantic import TypeAdapter
        schema = TypeAdapter(field.field_info.annotation).json_schema()
    except Exception:
        return {}
    return _example(schema, schema.get("$defs", {}), ids)


def _protected(route: APIRoute) -> bool:
    seen = set()

    def walk(dep):
        if dep.call is not None:
            seen.add(getattr(dep.call, "__qualname__", ""))
        for d in dep.dependencies:
            walk(d)
    walk(route.dependant)
    return "get_ctx" in seen or "require_role.<locals>.dep" in seen


def _routes() -> list[tuple[str, APIRoute]]:
    """(full path, route) for every API route. Newer FastAPI nests included routers instead of flattening them."""
    found: list[tuple[str, APIRoute]] = []

    def walk(routes, prefix: str = "") -> None:
        for r in routes:
            if isinstance(r, APIRoute):
                found.append((prefix + r.path, r))
            elif hasattr(r, "original_router"):
                walk(r.original_router.routes, prefix + (getattr(getattr(r, "include_context", None), "prefix", "") or ""))
    walk(main.app.routes)
    return found


ACTIONS = {"/api/voice/campaigns/{campaign_id}/{action}": "resume", "/api/questions/{gap_id}/{action}": "dismiss"}


def test_no_endpoint_shows_or_changes_another_workspaces_data(client, make_user, run, monkeypatch):
    monkeypatch.setenv("LOCAL_DEV", "false")
    a, b = make_user("Workspace A"), make_user("Workspace B")
    ids = run(_seed, a.id, a.bot("A"))
    before = run(_snapshot, a.id, ids["bot_id"])
    params = {"bot_id": ids["bot_id"], "campaign_id": ids["campaign_id"], "name": "x", "email": "a-customer@example.com"}

    leaks, tried = [], 0
    for full_path, route in _routes():
        if not _protected(route) or "{secret}" in full_path:
            continue
        path = full_path
        if path in ACTIONS:
            path = path.replace("{action}", ACTIONS[path])
        for name in re.findall(r"\{(\w+)\}", path):
            value = ids["email_job_id"] if (name == "job_id" and "/email/" in path) else ids.get(name, "x")
            path = path.replace("{" + name + "}", value)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            tried += 1
            try:
                resp = client.request(method, path, headers=b.h(), params=params, json=_body(route, ids))
            except Exception as e:  # a crash is a bug, but not a leak; the snapshot below catches side effects
                print(f"crashed: {method} {route.path}: {e!r}"[:200])
                continue
            if MARK in resp.text or "a-customer@example.com" in resp.text:
                leaks.append(f"{method} {route.path} -> {resp.status_code}: {resp.text[:160]}")

    after = run(_snapshot, a.id, ids["bot_id"])
    changed = sorted(k for k in before if before.get(k) != after.get(k))
    assert tried > 80
    assert not leaks, "Workspace B could read A's data:\n" + "\n".join(leaks)
    assert not changed, f"Workspace B changed A's data: {changed}"
