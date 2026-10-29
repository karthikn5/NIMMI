"""
Nimmi, the dashboard's agent (backend/agent): answers streamed and saved, tools that act as the signed-in person,
replays from any point (a reload, another server process), stop, limits, privacy between people and workspaces,
and how the model clients read what Gemini and OpenAI-style services send. A scripted model stands in for the real
ones; the parsing tests feed the clients recorded-style responses.
"""
import asyncio
import json
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException

from agent import check, events, intake, loop, prompt, providers, registry
from agent.providers import Text, ToolCall, Usage
from voice.ai_models import AI_MODELS_BY_ID

GEMINI = AI_MODELS_BY_ID["gemini-3.6-flash"]
GROQ = AI_MODELS_BY_ID["gpt-oss-120b"]
OPENAI = AI_MODELS_BY_ID["gpt-5.4-mini"]


class Script:
    """A model that answers from a list of turns. A turn is a list of items to yield (an asyncio.Event in it waits
    until set; an exception in it is raised), or an exception to raise at once."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.calls = []

    async def __call__(self, system, context, history, tools, force_answer=False, **options):
        self.calls.append({"system": system, "context": context, "history": [dict(h) for h in history],
                           "tools": tools, "force": force_answer, "patience": options.get("patience")})
        turn = self.turns.pop(0) if self.turns else [Text("(the script ran out)")]
        if isinstance(turn, Exception):
            raise turn
        for item in turn:
            if isinstance(item, Exception):
                raise item
            if isinstance(item, asyncio.Event):
                await item.wait()
                continue
            yield item


@pytest.fixture
def model(monkeypatch):
    """A scripted model for the answer itself. The first look at the message (intake) and the review of the answer
    (check) are left out unless a test scripts them (the `brain` fixture): then a message is a plain question."""
    async def no_intake(message, screen, before, usage):
        return intake.Intake()

    async def no_review(request, steps, ledger, draft, usage, may_continue):
        return check.Verdict()

    def use(*turns):
        script = Script(*turns)
        monkeypatch.setattr(providers, "stream", script)
        monkeypatch.setattr(providers, "models", lambda *_: [GEMINI])
        monkeypatch.setattr(intake, "understand", no_intake)
        monkeypatch.setattr(check, "review", no_review)
        return script
    return use


def sse_events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]


def ask(user, text, thread_id=None, screen=None, workspace=None) -> list[dict]:
    body = {"text": text, "thread_id": thread_id, "screen": screen}
    with user.client.stream("POST", "/api/agent/messages", json=body, headers=user.h(workspace)) as r:
        assert r.status_code == 200, r.read()
        return sse_events(r)


def replay(user, run_id, after=0) -> list[dict]:
    with user.client.stream("GET", f"/api/agent/runs/{run_id}/events?after={after}", headers=user.h()) as r:
        assert r.status_code == 200, r.read()
        return sse_events(r)


def said(evs) -> str:
    return "".join(e["delta"] for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")


def teammate(client, owner, role):
    import auth
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    invited = client.post("/api/team/invite", json={"email": email, "role": role}, headers=owner.h()).json()
    auth._hits.clear()
    signup = client.post("/api/auth/signup", json={"email": email, "name": "Team Mate", "password": "password123"}).json()
    me = {"Authorization": f"Bearer {signup['token']}"}
    token = invited["invite_link_path"].split("token=")[1]
    assert client.post("/api/team/accept", json={"token": token}, headers=me).json()["role"] == role
    return me, signup["user_id"]


# ─── A run, end to end ──────────────────────────────────────────────

def test_an_answer_is_streamed_saved_and_replayed(client, make_user, model):
    user = make_user("Kavya")
    script = model([Text("Hello "), Text("Kavya, "), Text("how can I help?"), Usage("gemini-3.6-flash", 900, 12)])
    evs = ask(user, "  hi  ", screen={"path": "/dashboard", "id": "assistants", "title": "Assistants"})

    types = [e["type"] for e in evs]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert types[1] == "TEXT_MESSAGE_START" and "TEXT_MESSAGE_END" in types
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    assert said(evs) == "Hello Kavya, how can I help?"
    assert evs[-1]["outcome"] == "success"
    run_id, thread_id = evs[0]["runId"], evs[0]["threadId"]

    # The model got the screen and the person in its note, the message trimmed, and the tools.
    call = script.calls[0]
    assert '"id": "assistants"' in call["context"] and "Kavya (owner, their own workspace)" in call["context"]
    assert call["history"] == [{"role": "user", "content": "hi", "tool_calls": None, "tool_call_id": None, "name": None,
                                "raw": None}]
    assert sorted(t["name"] for t in call["tools"]) == sorted(t.name for t in registry.available("owner", "assistants") if not t.after)
    assert call["force"] is False

    # Saved: the thread reads back the same, and the run has its numbers.
    thread = client.get(f"/api/agent/threads/{thread_id}", headers=user.h()).json()
    assert thread["title"] == "hi" and thread["running"] is None
    assert [(i["type"], i["text"]) for i in thread["items"]] == [("user", "hi"), ("text", "Hello Kavya, how can I help?")]
    assert [t["id"] for t in client.get("/api/agent/threads", headers=user.h()).json()] == [thread_id]

    async def the_run():
        from backend.models import AgentRun
        from database import async_session
        async with async_session() as db:
            return await db.get(AgentRun, run_id)
    run = client.portal.call(the_run)
    assert (run.state, run.tokens_in, run.tokens_out, run.models, run.rounds) == ("done", 900, 12, "gemini-3.6-flash", 1)
    assert run.first_output_ms is not None and run.last_seq == len(evs)

    # A reload picks up from any point: everything after the last event it saw, and nothing before.
    assert replay(user, run_id) == evs
    assert replay(user, run_id, after=2) == evs[2:]


def test_tools_act_as_the_person_and_their_results_go_back_to_the_model(client, make_user, model):
    user, other = make_user(), make_user()
    user.bot("Clinic Desk")
    other.bot("Someone Else's Bot")
    script = model([Text("Let me look."), ToolCall("c1", "list_assistants", {})],
                   [Text("You have one assistant, Clinic Desk.")])
    evs = ask(user, "which assistants do I have?")

    start = next(e for e in evs if e["type"] == "TOOL_CALL_START")
    assert (start["toolCallName"], start["label"]) == ("list_assistants", "Looking at your assistants")
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert result["ok"] is True and "Clinic Desk" in result["content"]
    assert said(evs) == "Let me look.You have one assistant, Clinic Desk."

    # The second model call saw its own call and the tool's result, which has only this workspace's assistants.
    second = script.calls[1]["history"]
    assert second[-2]["tool_calls"] == [{"id": "c1", "name": "list_assistants", "arguments": {}}]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert "Clinic Desk" in second[-1]["content"] and "Someone Else" not in second[-1]["content"]

    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert [i["type"] for i in thread["items"]] == ["user", "text", "step", "text"]
    step = dict(thread["items"][2])
    assert step.pop("runId") == evs[0]["runId"]
    assert step == {"type": "step", "id": "c1", "name": "list_assistants", "label": "Looking at your assistants", "ok": True}

    # The next message carries the whole conversation, tool round included.
    later = model([Text("Still one.")])
    ask(user, "and now?", thread_id=evs[0]["threadId"])
    assert [h["role"] for h in later.calls[0]["history"]] == ["user", "assistant", "tool", "assistant", "user"]


def test_a_bad_tool_call_is_answered_in_words_and_the_model_carries_on(client, make_user, model):
    user = make_user()
    script = model([ToolCall("c1", "delete_everything", {}), ToolCall("c2", "list_assistants", {"junk": 1})],
                   [Text("Done looking.")])
    evs = ask(user, "go")
    results = [e for e in evs if e["type"] == "TOOL_CALL_RESULT"]
    assert results[0]["ok"] is False and "no tool named delete_everything" in results[0]["content"]
    assert results[1]["ok"] is True  # unknown inputs are dropped, not passed on
    assert said(evs) == "Done looking."
    assert len(script.calls) == 2


def test_tool_rounds_are_capped_and_the_last_round_must_answer(client, make_user, model, monkeypatch):
    monkeypatch.setattr(loop, "MAX_ROUNDS", 2)
    user = make_user()
    script = model([ToolCall("a", "list_assistants", {})], [ToolCall("b", "list_assistants", {})], [Text("Here it is.")])
    evs = ask(user, "loop forever")
    assert [c["force"] for c in script.calls] == [False, False, True]
    assert said(evs) == "Here it is." and evs[-1]["type"] == "RUN_FINISHED"


# ─── Stop, busy, failures ───────────────────────────────────────────

def test_stop_ends_a_run_and_a_busy_chat_takes_no_new_message(client, make_user, model):
    user = make_user()
    gate = asyncio.Event()  # never set: the model "thinks" until stopped
    model([Text("Thinking about "), gate, Text("never said")])
    seen = []
    with client.stream("POST", "/api/agent/messages", json={"text": "slow one"}, headers=user.h()) as r:
        for line in r.iter_lines():  # read up to the first words, then close the connection (like a reload)
            if line.startswith("data: "):
                seen.append(json.loads(line[6:]))
                if seen[-1]["type"] == "TEXT_MESSAGE_CONTENT":
                    break
    assert seen[-1]["delta"] == "Thinking about "
    run_id, thread_id = seen[0]["runId"], seen[0]["threadId"]

    busy = client.post("/api/agent/messages", json={"text": "another", "thread_id": thread_id}, headers=user.h())
    assert busy.status_code == 409
    assert client.delete(f"/api/agent/threads/{thread_id}", headers=user.h()).status_code == 409
    assert client.get(f"/api/agent/threads/{thread_id}", headers=user.h()).json()["running"] == {"id": run_id}

    assert client.post(f"/api/agent/runs/{run_id}/stop", headers=user.h()).json() == {"stopped": True}
    evs = replay(user, run_id)
    assert evs[-1]["type"] == "RUN_FINISHED" and evs[-1]["outcome"] == "stopped"
    assert said(evs) == "Thinking about "
    # What they saw is kept; the chat takes messages again.
    thread = client.get(f"/api/agent/threads/{thread_id}", headers=user.h()).json()
    assert thread["running"] is None and thread["items"][-1]["text"] == "Thinking about"
    assert client.post(f"/api/agent/runs/{run_id}/stop", headers=user.h()).json()["stopped"] is False
    gate.set()


def test_a_failed_model_is_reported_in_plain_words(client, make_user, model):
    user = make_user()
    model(providers.ModelError("No AI model could answer"))
    evs = ask(user, "hello?")
    assert evs[-1]["type"] == "RUN_ERROR"
    assert "couldn't get an answer from the AI service" in evs[-1]["message"]

    async def state():
        from backend.models import AgentRun
        from database import async_session
        async with async_session() as db:
            return await db.get(AgentRun, evs[0]["runId"])
    run = client.portal.call(state)
    assert run.state == "failed" and "No AI model" in run.error


def test_a_run_whose_server_process_died_is_closed_for_whoever_follows_it(client, make_user, model):
    user = make_user()
    model([Text("ok")])
    thread_id = ask(user, "first")[0]["threadId"]

    async def orphan():
        from backend.models import AgentRun
        from database import async_session
        async with async_session() as db:
            run = AgentRun(thread_id=thread_id, user_id=user.id, owner_id=user.id, role="owner", state="running",
                           heartbeat_at=events.now() - timedelta(minutes=5))
            db.add(run)
            await db.commit()
            return run.id
    run_id = client.portal.call(orphan)
    evs = replay(user, run_id)
    assert [e["type"] for e in evs] == ["RUN_ERROR"] and "server restarted" in evs[0]["message"]
    assert replay(user, run_id) == evs  # written once, then replayed like any other event
    # The chat is free again.
    model([Text("back")])
    assert said(ask(user, "again", thread_id=thread_id)) == "back"


def test_not_set_up_daily_limit_and_empty_messages(client, make_user, model, monkeypatch):
    from agent import router
    user = make_user()
    monkeypatch.setattr(providers, "models", lambda *_: [])
    assert client.get("/api/agent/status", headers=user.h()).json()["ready"] is False
    assert client.post("/api/agent/messages", json={"text": "hi"}, headers=user.h()).status_code == 503

    model([Text("one")])
    assert client.post("/api/agent/messages", json={"text": "   "}, headers=user.h()).status_code == 400
    assert client.post("/api/agent/messages", json={"text": "x" * 4001}, headers=user.h()).status_code == 400
    monkeypatch.setattr(router, "DAILY_PAID", 1)  # the test suite counts as paid (plan limits aren't enforced in it)
    ask(user, "one")
    over = client.post("/api/agent/messages", json={"text": "two"}, headers=user.h())
    assert over.status_code == 429 and "today's 1 messages" in over.json()["detail"]
    assert client.get("/api/agent/status", headers=user.h()).json() == {"ready": True, "daily_limit": 1, "used_today": 1}
    assert client.post("/api/agent/messages", json={"text": "hi"}).status_code == 401


# ─── Privacy ────────────────────────────────────────────────────────

def test_chats_belong_to_the_person_who_wrote_them(client, make_user, model):
    owner, stranger = make_user("Owner"), make_user("Stranger")
    model([Text("private answer")])
    evs = ask(owner, "my secret plans")
    thread_id, run_id = evs[0]["threadId"], evs[0]["runId"]

    for headers in (stranger.h(), stranger.h(workspace=owner.id)):
        assert client.get(f"/api/agent/threads/{thread_id}", headers=headers).status_code in (403, 404)
        assert client.get(f"/api/agent/runs/{run_id}/events", headers=headers).status_code in (403, 404)
        assert client.post(f"/api/agent/runs/{run_id}/stop", headers=headers).status_code in (403, 404)
        assert client.delete(f"/api/agent/threads/{thread_id}", headers=headers).status_code in (403, 404)
    assert client.post("/api/agent/messages", json={"text": "hi", "thread_id": thread_id},
                       headers=stranger.h()).status_code == 404

    # A teammate in the owner's workspace doesn't see the owner's chats either, and theirs act with their own role.
    me, member_id = teammate(client, owner, "agent")
    member = {**me, "X-Workspace": owner.id}
    assert client.get(f"/api/agent/threads/{thread_id}", headers=member).status_code == 404
    assert client.get("/api/agent/threads", headers=member).json() == []
    script = model([Text("hello teammate")])
    with client.stream("POST", "/api/agent/messages", json={"text": "hi"}, headers=member) as r:
        mine = sse_events(r)
    assert said(mine) == "hello teammate"
    assert "(agent, " in script.calls[0]["context"] and "Owner's workspace, as a team member" in script.calls[0]["context"]
    # ...and that chat is in the owner's workspace for them only: not in their own workspace, not the owner's list.
    assert len(client.get("/api/agent/threads", headers=member).json()) == 1
    assert client.get("/api/agent/threads", headers=me).json() == []
    assert [t["id"] for t in client.get("/api/agent/threads", headers=owner.h()).json()] == [thread_id]

    assert client.delete(f"/api/agent/threads/{thread_id}", headers=owner.h()).json() == {"deleted": True}
    assert client.get(f"/api/agent/threads/{thread_id}", headers=owner.h()).status_code == 404


def test_the_screen_is_kept_small_and_only_the_named_parts(client, make_user, model):
    user = make_user()
    script = model([Text("ok")])
    screen = {"path": "/dashboard/builder/abc", "id": "builder", "title": "Builder", "tab": "design",
              "entity": {"kind": "assistant", "id": "abc", "name": "Desk", "extra": "dropped"},
              "errors": ["Colour is not valid"] + [""] * 3, "details": {"colour": "#12"}, "html": "<div>dump</div>"}
    ask(user, "why is this red?", screen=screen)
    note = script.calls[0]["context"]
    shown = json.loads(note.split("<screen>\n")[1].split("\n</screen>")[0])
    assert shown == {"path": "/dashboard/builder/abc", "id": "builder", "title": "Builder", "tab": "design",
                     "entity": {"kind": "assistant", "id": "abc", "name": "Desk"}, "errors": ["Colour is not valid"],
                     "details": {"colour": "#12"}}
    big = prompt.clean_screen({"details": {"blob": "x" * 5000}})
    assert big["details"]["note"] == "too long to include"
    assert prompt.clean_screen("not a dict") == {}


# ─── The tool registry ──────────────────────────────────────────────

def test_tool_inputs_errors_secrets_and_long_results(run, monkeypatch):
    from auth import AuthContext

    async def echo(tc, db, **kw):
        if kw.get("mode") == "http":
            raise HTTPException(status_code=403, detail="Your role doesn't allow this")
        if kw.get("mode") == "boom":
            raise RuntimeError("internal detail that must not leak")
        if kw.get("mode") == "secret":
            return {"token": "enc:v1:gAAAAABlongsecretvalue", "key": "gsk_" + "a" * 30, "jwt": "eyJabcdefghij.klmnopqrst.uvwxyz12345"}
        if kw.get("mode") == "long":
            return "y" * 9000
        return kw

    schema = {"type": "object", "required": ["mode"], "properties": {
        "mode": {"type": "string", "enum": ["ok", "http", "boom", "secret", "long"]},
        "count": {"type": "integer"}, "flag": {"type": "boolean"}}}
    monkeypatch.setitem(registry.TOOLS, "echo", registry.Tool("echo", "test", schema, echo, "Testing", roles=("owner",)))
    tc = registry.ToolContext(ctx=AuthContext("u", "u", "owner"), run_id="r", thread_id="t", screen={})

    def go(inputs, as_tc=None):
        out = run(registry.run, as_tc or tc, "echo", inputs)
        return out.text, out.ok
    assert go({"mode": "ok", "count": 3.0, "extra": "x"}) == ('{"mode":"ok","count":3}', True)
    assert go({"mode": "ok", "count": "7"}) == ('{"mode":"ok","count":7}', True)
    assert "Missing: mode" in go({})[0]
    assert "must be one of" in go({"mode": "nope"})[0]
    assert "should be an integer" in go({"mode": "ok", "count": True})[0]
    assert "should be a boolean" in go({"mode": "ok", "flag": "yes"})[0]
    assert go({"mode": "http"}) == ('{"error":"Your role doesn\'t allow this","kind":"not_allowed"}', False)
    text, ok = go({"mode": "boom"})
    assert not ok and "internal detail" not in text and "Something went wrong inside Nimmi" in text and '"kind":"internal"' in text
    text, ok = go({"mode": "secret"})
    assert ok and text.count("[hidden]") == 3 and "enc:v1" not in text and "gsk_" not in text
    text, _ = go({"mode": "long"})
    assert len(text) < registry.RESULT_CHARS + 40 and text.endswith("(cut short)")

    agent_role = registry.ToolContext(ctx=AuthContext("u", "o", "agent"), run_id="r", thread_id="t", screen={})
    assert "role in this workspace doesn't allow" in go({"mode": "ok"}, agent_role)[0]
    assert "echo" not in [t.name for t in registry.available("agent", None)]
    # A tool without inputs is described without `parameters` (Gemini refuses an empty list of them).
    assert registry.specs([registry.TOOLS["list_assistants"]]) == [
        {"name": "list_assistants", "description": registry.TOOLS["list_assistants"].description}]


# ─── The model clients ──────────────────────────────────────────────

@pytest.fixture
def service(monkeypatch):
    """Answers the model clients' requests with what `reply(request)` returns; remembers the requests."""
    seen = []

    def use(reply, *available):
        def handler(request):
            seen.append({"url": str(request.url), "body": json.loads(request.content), "headers": request.headers})
            return reply(request)
        monkeypatch.setattr(providers, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        monkeypatch.setattr(providers, "models", lambda *_: list(available))
        monkeypatch.setattr(providers, "_resting", {})
        for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.setenv(name, f"test-{name}")
        return seen
    return use


def sse_body(*chunks, done=False) -> str:
    return "".join(f"data: {json.dumps(c)}\r\n\r\n" for c in chunks) + ("data: [DONE]\r\n\r\n" if done else "")


async def collect(stream):
    return [item async for item in stream]


def test_gemini_answers_calls_tools_and_keeps_its_signatures(run, service):
    parts = [{"text": "check."}, {"functionCall": {"name": "list_assistants", "args": {"limit": 2}}, "thoughtSignature": "sig-1"}]
    seen = service(lambda r: httpx.Response(200, text=sse_body(
        {"candidates": [{"content": {"parts": [{"text": "Let me "}], "role": "model"}}]},
        {"candidates": [{"content": {"parts": parts, "role": "model"}, "finishReason": "STOP"}],
         "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 15, "thoughtsTokenCount": 40}})), GEMINI)
    tools = [{"name": "list_assistants", "description": "Assistants"}]
    items = run(collect, providers.stream("SYSTEM", "NOTE", [{"role": "user", "content": "hi"}], tools))

    assert [i.text for i in items if isinstance(i, Text)] == ["Let me ", "check."]
    call = next(i for i in items if isinstance(i, ToolCall))
    assert (call.name, call.arguments) == ("list_assistants", {"limit": 2})
    assert call.raw["gemini_parts"][-1]["thoughtSignature"] == "sig-1"
    assert items[-1] == Usage("gemini-3.6-flash", 1200, 55)

    sent = seen[0]
    assert "gemini-3.6-flash:streamGenerateContent" in sent["url"] and "alt=sse" in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == "test-GEMINI_API_KEY"
    assert sent["body"]["systemInstruction"] == {"parts": [{"text": "SYSTEM"}, {"text": "NOTE"}]}
    assert sent["body"]["tools"] == [{"functionDeclarations": tools}]
    assert sent["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "toolConfig" not in sent["body"]

    # Sent back on the next turn: its own parts unchanged; a call another model made carries Gemini's marker.
    history = [{"role": "user", "content": "hi"},
               {"role": "assistant", "content": "Let me check.", "raw": call.raw,
                "tool_calls": [{"id": call.id, "name": "list_assistants", "arguments": {"limit": 2}}]},
               {"role": "tool", "tool_call_id": call.id, "name": "list_assistants", "content": '{"assistants":[]}'},
               {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "name": "list_assistants", "arguments": {}}]},
               {"role": "tool", "tool_call_id": "x", "name": "list_assistants", "content": "{}"}]
    contents = providers.gemini_contents(history)
    assert contents[1] == {"role": "model", "parts": call.raw["gemini_parts"]}
    assert contents[2]["parts"][0]["functionResponse"] == {"name": "list_assistants", "response": {"result": '{"assistants":[]}'}}
    assert contents[3]["parts"] == [{"functionCall": {"name": "list_assistants", "args": {}},
                                     "thoughtSignature": providers.FOREIGN_CALL}]

    # The last round: tools described, answering in words required.
    run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], tools, force_answer=True))
    assert seen[1]["body"]["toolConfig"] == {"functionCallingConfig": {"mode": "NONE"}}


def test_openai_style_services_send_tool_calls_in_pieces(run, service):
    seen = service(lambda r: httpx.Response(200, text=sse_body(
        {"choices": [{"delta": {"role": "assistant", "content": "One moment. "}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_9", "function": {"name": "list_assistants", "arguments": ""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"limit\":"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": " 5}"}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "x_groq": {"usage": {"prompt_tokens": 800, "completion_tokens": 20}}},
        done=True)), GROQ)
    tools = [{"name": "list_assistants", "description": "Assistants", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}]
    items = run(collect, providers.stream("SYSTEM", "NOTE", [{"role": "user", "content": "hi"}], tools))
    assert items[0] == Text("One moment. ")
    assert items[1] == ToolCall("call_9", "list_assistants", {"limit": 5})
    assert items[2] == Usage("gpt-oss-120b", 800, 20)
    body = seen[0]["body"]
    assert seen[0]["url"].endswith("api.groq.com/openai/v1/chat/completions")
    assert body["messages"][:2] == [{"role": "system", "content": "SYSTEM"}, {"role": "system", "content": "NOTE"}]
    assert body["tools"] == [{"type": "function", "function": tools[0]}] and body["tool_choice"] == "auto"
    assert body["reasoning_effort"] == "low" and "stream_options" not in body  # Groq counts tokens by itself

    # OpenAI: asked for the token counts, which come in a last piece without choices.
    seen = service(lambda r: httpx.Response(200, text=sse_body(
        {"choices": [{"delta": {"content": "Hi"}}]}, {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 2}},
        done=True)), OPENAI)
    items = run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], tools, force_answer=True))
    assert items == [Text("Hi"), Usage("gpt-5.4-mini", 50, 2)]
    assert seen[-1]["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen[-1]["body"]["stream_options"] == {"include_usage": True} and seen[-1]["body"]["tool_choice"] == "none"


def test_the_next_model_answers_when_one_is_busy_and_the_busy_one_rests(run, service):
    def reply(request):
        if "generativelanguage" in str(request.url):
            return httpx.Response(429, text='{"error": "quota"}', headers={"retry-after": "30"})
        return httpx.Response(200, text=sse_body({"choices": [{"delta": {"content": "From Groq"}}]}, done=True))
    seen = service(reply, GEMINI, GROQ)
    items = run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert [i.text for i in items if isinstance(i, Text)] == ["From Groq"]
    assert 25 < providers._resting["gemini-3.6-flash"] - time.monotonic() <= 30
    # While it rests it isn't asked at all.
    run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert ["generativelanguage" in s["url"] for s in seen] == [True, False, False]


def test_a_model_that_stops_part_way_is_not_answered_over_and_none_left_is_an_error(run, service):
    seen = service(lambda r: httpx.Response(200, text=sse_body(
        {"candidates": [{"content": {"parts": [{"text": "Half an ans"}]}}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "MALFORMED_FUNCTION_CALL"}]})), GEMINI, GROQ)

    async def go():
        got = []
        with pytest.raises(providers.ModelError, match="stopped part way"):
            async for item in providers.stream("S", "", [{"role": "user", "content": "hi"}], []):
                got.append(item)
        return got
    assert run(go) == [Text("Half an ans")]
    assert len(seen) == 1  # Groq wasn't asked to start a second answer over the first

    service(lambda r: httpx.Response(500, text="down"), GEMINI)
    with pytest.raises(providers.ModelError, match="No AI model could answer"):
        run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))


def test_history_is_trimmed_to_whole_tool_rounds_starting_with_the_person():
    history = [
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "t", "arguments": {}}, {"id": "lost", "name": "t", "arguments": {}}],
         "raw": {"gemini_parts": ["..."]}},
        {"role": "tool", "tool_call_id": "a", "name": "t", "content": "result a"},
        {"role": "tool", "tool_call_id": "stray", "name": "t", "content": "no call"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "gone", "name": "t", "arguments": {}}]},
        {"role": "user", "content": "q2"},
    ]
    out = providers.trim(history, 40)
    assert [h["role"] for h in out] == ["user", "assistant", "tool", "user"]
    assert out[1]["tool_calls"] == [{"id": "a", "name": "t", "arguments": {}}]
    assert out[1]["raw"] is None  # Gemini's parts named a call that's gone: they can't go back as they were
    assert providers.trim(history, 1) == [{"role": "user", "content": "q2"}]


# ─── Phase 1: the read tools and the screen ─────────────────────────

def test_every_read_tool_works_stays_in_the_workspace_and_never_calls_an_ai(client, make_user, run, monkeypatch):
    import ai
    from auth import AuthContext
    owner, other = make_user("Owner"), make_user("Other")
    mine, theirs = owner.bot("Mine"), other.bot("Theirs")

    def no_ai(*args, **kwargs):
        raise AssertionError("a read tool called an AI model")
    for name in ("chat", "chat_stream", "extract_json", "look"):
        monkeypatch.setattr(ai, name, no_ai)
    tc = registry.ToolContext(ctx=AuthContext(owner.id, owner.id, "owner"), run_id="r", thread_id="t", screen={})
    async def a_call():
        from backend.models import CallLog
        from database import async_session
        async with async_session() as db:
            call = CallLog(user_id=owner.id, bot_id=mine, caller_e164="+919876543210", duration_sec=60)
            db.add(call)
            await db.commit()
            return call.id
    special = {"go_to": {"page": "builder", "assistant_id": mine}, "point_at": {"element": "nav.voice"},
               "connection_guide": {"provider": "calcom", "assistant_id": mine}, "get_call": {"call_id": run(a_call)}}
    for name, t in registry.TOOLS.items():
        if t.level != "read" or t.internal:  # Nimmi's own tools act on a run: tested with the plan
            continue
        takes_assistant = "assistant_id" in t.parameters.get("properties", {})
        inputs = special.get(name) or ({"assistant_id": mine} if takes_assistant else {})
        if "direction" in t.parameters.get("required", []):
            inputs["direction"] = "inbound"
        out = run(registry.run, tc, name, inputs)
        assert out.ok, (name, out.text)
        assert "Theirs" not in out.text, name
        if takes_assistant:
            out = run(registry.run, tc, name, {**inputs, "assistant_id": theirs})
            assert not out.ok and "not found" in out.text.lower(), (name, out.text)
    # Every tool says what it does and what the panel shows while it runs.
    assert all(t.description and t.label for t in registry.TOOLS.values())


def test_the_panel_is_moved_by_go_to_and_the_model_knows_the_open_screen(client, make_user, model):
    user = make_user()
    bot = user.bot("Desk")
    script = model([ToolCall("c1", "go_to", {"page": "builder", "assistant_id": bot, "tab": "knowledge"}),
                    ToolCall("c2", "point_at", {"element": "builder.tab.knowledge"})],
                   [Text("I've opened the Knowledge tab.")])
    evs = ask(user, "where do I add my website?", screen={"path": f"/dashboard/builder/{bot}", "id": "builder", "tab": "design",
                                                          "entity": {"kind": "assistant", "id": bot, "name": "Desk"}})
    custom = [(e["name"], e["value"]) for e in evs if e["type"] == "CUSTOM"]
    assert custom == [("navigate", {"path": f"/dashboard/builder/{bot}?tab=knowledge"}),
                      ("highlight", {"element": "builder.tab.knowledge"})]
    note = script.calls[0]["context"]
    assert "About this screen (Assistant builder)" in note and "The open tab (Design): How the chat looks" in note
    # The builder's tools come with every screen in this phase; the role decides the rest.
    names = {t["name"] for t in script.calls[0]["tools"]}
    assert {"get_assistant", "go_to", "point_at", "get_unanswered_questions"} <= names


def test_the_dashboard_and_the_agent_name_the_same_screens_and_elements():
    """dashboard/src/lib/agent/screens.ts maps routes to screen ids; agent/screens.py has the notes for each. The
    elements point_at can name must be named in the pages (data-agent="...")."""
    import re
    from pathlib import Path
    from agent import screens
    dashboard = Path(__file__).resolve().parents[2] / "dashboard" / "src"
    ids = set(re.findall(r'/, "([a-z_]+)", "', (dashboard / "lib" / "agent" / "screens.ts").read_text()))
    assert ids == set(screens.SCREENS), ids ^ set(screens.SCREENS)
    pages = "\n".join(p.read_text() for p in dashboard.rglob("*.tsx"))
    named = set(re.findall(r'data-agent="([a-z_.]+)"', pages))
    # Names built from a list in the page (data-agent={`nav.${...}`}): the list's items.
    built = {"nav": ("assistants", "deployments", "live_chat", "questions", "voice", "whatsapp", "integrations", "analytics", "billing"),
             "voice.tab": ("overview", "agents", "knowledge", "contacts", "calls", "schedule", "campaigns", "data", "numbers", "compliance"),
             "whatsapp.tab": ("overview", "inbox", "assistant", "files", "settings"),
             "builder.tab": ("design", "knowledge", "behaviour", "flow", "leads")}
    for prefix, values in built.items():
        if "data-agent={`" + prefix + ".${" in pages:
            named |= {f"{prefix}.{v}" for v in values}
    assert set(screens.POINTS) <= named, set(screens.POINTS) - named


def test_rate_limits_rest_a_model_as_long_as_the_service_says_and_busy_is_said_plainly(run, service, client, make_user, model):
    gemini_quota = (b'{"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", '
                    b'"retryDelay": "46419s"}]}}')
    seen = service(lambda r: httpx.Response(429, content=gemini_quota), GEMINI)
    with pytest.raises(providers.ModelError) as failed:
        run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert failed.value.busy is True
    # A free tier's daily quota: not asked again for an hour (it said 12.9 hours), rather than every minute.
    assert 3590 < providers._resting["gemini-3.6-flash"] - time.monotonic() <= providers.MAX_REST_SEC
    assert len(seen) == 1

    # Groq's per-minute limit frees in a few seconds: the next answer waits for it instead of failing.
    seen = service(lambda r: httpx.Response(200, text=sse_body({"choices": [{"delta": {"content": "ok"}}]}, done=True)), GROQ)
    providers._resting["gpt-oss-120b"] = time.monotonic() + 0.3
    started = time.monotonic()
    items = run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert items[0] == Text("ok") and 0.25 < time.monotonic() - started < 3
    assert "groq" in seen[-1]["url"] and len(seen) == 2  # the one Gemini request above, then this one

    # In the panel: the plain "busy" message, and it's still there when the chat is opened again.
    user = make_user()
    model(providers.ModelError("Every AI model is at its rate limit or quota", busy=True))
    evs = ask(user, "hello?")
    assert evs[-1]["type"] == "RUN_ERROR" and "busy right now" in evs[-1]["message"]
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert [i["type"] for i in thread["items"]] == ["user", "error"] and "busy right now" in thread["items"][1]["text"]



# ─── Phase 2: changes with undo, and what waits for Confirm ─────────

def config(user, bot):
    return user.client.get(f"/api/bots/{bot}/config", headers=user.h()).json()


def test_a_change_is_made_recorded_and_undone_and_undo_never_overwrites_a_newer_edit(client, make_user, model):
    user = make_user()
    bot = user.bot("Clinic Desk")
    start = config(user, bot)["visual_config"]
    model([ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#16A34A", "launcher_shape": "oval"})],
          [Text("Done: green, oval.")])
    evs = ask(user, "make it green with an oval button")
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert result["ok"] and result["undoable"] and result["actionId"]
    assert ("changed", {"kind": "assistant", "id": bot}) in [(e["name"], e["value"]) for e in evs if e["type"] == "CUSTOM"]
    look = config(user, bot)["visual_config"]
    assert (look["color"], look["launcher_shape"]) == ("#16a34a", "oval")
    actions = client.get("/api/agent/actions", headers=user.h()).json()
    assert actions[0]["summary"].startswith("Clinic Desk: design: brand colour:") and actions[0]["undoable"]

    # Undo puts back exactly those two settings, and tells the chat.
    undone = client.post(f"/api/agent/actions/{result['actionId']}/undo", headers=user.h())
    assert undone.status_code == 200 and undone.json()["refresh"] == [{"kind": "assistant", "id": bot}]
    look = config(user, bot)["visual_config"]
    assert (look.get("color"), look.get("launcher_shape")) == (start.get("color"), start.get("launcher_shape"))
    assert client.post(f"/api/agent/actions/{result['actionId']}/undo", headers=user.h()).status_code == 409
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    step = next(i for i in thread["items"] if i["type"] == "step")
    assert step["undone"] is True and step["undoable"] is False
    assert thread["items"][-1]["type"] == "note" and "they undid" in thread["items"][-1]["text"]

    # Changed again by hand after Nimmi's change: undo refuses rather than overwrite it.
    model([ToolCall("c2", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#ff0000"})], [Text("Red.")])
    action_id = next(e for e in ask(user, "red") if e["type"] == "TOOL_CALL_RESULT")["actionId"]
    client.patch(f"/api/bots/{bot}", json={"visual_config": {**config(user, bot)["visual_config"], "color": "#000000"}}, headers=user.h())
    refused = client.post(f"/api/agent/actions/{action_id}/undo", headers=user.h())
    assert refused.status_code == 409 and "changed again" in refused.json()["detail"]
    assert config(user, bot)["visual_config"]["color"] == "#000000"
    # Another person's change can't be undone by someone else.
    other = make_user()
    assert client.post(f"/api/agent/actions/{action_id}/undo", headers=other.h()).status_code == 404


def test_a_change_that_changes_nothing_is_not_recorded_and_bad_values_are_refused(client, make_user, model):
    user = make_user()
    bot = user.bot()
    colour = config(user, bot)["visual_config"].get("color") or "#3b82f6"
    model([ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "brand_colour": colour}),
           ToolCall("c2", "update_assistant_design", {"assistant_id": bot, "brand_colour": "green"}),
           ToolCall("c3", "update_assistant_design", {"assistant_id": bot})], [Text("ok")])
    results = [e for e in ask(user, "go") if e["type"] == "TOOL_CALL_RESULT"]
    assert results[0]["ok"] and "already set that way" in results[0]["content"] and "actionId" not in results[0]
    assert not results[1]["ok"] and "hex colour" in results[1]["content"]
    assert not results[2]["ok"] and "Say what to change" in results[2]["content"]
    assert client.get("/api/agent/actions", headers=user.h()).json() == []


def test_changes_need_a_manager_and_a_teammate_with_the_agent_role_is_refused(client, make_user, model):
    owner = make_user("Owner")
    bot = owner.bot()
    me, _ = teammate(client, owner, "agent")
    member = {**me, "X-Workspace": owner.id}
    script = model([ToolCall("c1", "update_instructions", {"assistant_id": bot, "text": "Be rude."})], [Text("I can't.")])
    with client.stream("POST", "/api/agent/messages", json={"text": "change it"}, headers=member) as r:
        evs = sse_events(r)
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert not result["ok"] and "role" in result["content"]
    assert "update_instructions" not in {t["name"] for t in script.calls[0]["tools"]}  # not even offered
    assert "Be rude" not in (config(owner, bot).get("system_prompt") or "")


def test_confirm_tools_only_propose_and_run_when_the_person_confirms(client, make_user, model, run):
    user = make_user()
    keep, bot = user.bot("Keep"), user.bot("Old Bot")
    model([ToolCall("c1", "delete_assistant", {"assistant_id": bot})], [Text("Confirm above to delete it.")])
    evs = ask(user, "delete Old Bot")
    card = next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "confirm")
    assert card["title"] == "Delete Old Bot" and "restored for 30 days" in card["summary"]
    assert "waiting_for_confirmation" in next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")["content"]
    assert bot in [b["id"] for b in client.get("/api/bots", headers=user.h()).json()]  # nothing happened yet

    other = make_user()
    assert client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=other.h()).status_code == 404
    assert client.post(f"/api/agent/actions/{card['actionId']}/cancel", headers=user.h()).json()["state"] == "cancelled"
    assert client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h()).status_code == 409
    assert bot in [b["id"] for b in client.get("/api/bots", headers=user.h()).json()]

    model([ToolCall("c2", "delete_assistant", {"assistant_id": bot})], [Text("Confirm above.")])
    evs = ask(user, "ok really delete it", thread_id=evs[0]["threadId"])
    card = next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "confirm")
    done = client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h()).json()
    assert done["state"] == "done" and done["refresh"] == [{"kind": "assistant", "id": bot, "deleted": True}]
    assert [b["id"] for b in client.get("/api/bots", headers=user.h()).json()] == [keep]
    assert "Old Bot" in [d["name"] for d in client.get("/api/bots/deleted", headers=user.h()).json()]
    assert client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h()).status_code == 409
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert [i["state"] for i in thread["items"] if i["type"] == "confirm"] == ["cancelled", "done"]
    assert [i["text"][:30] for i in thread["items"] if i["type"] == "note"] == ["(In the panel they cancelled: ", "(In the panel they confirmed: "]

    # A proposal left too long expires instead of running.
    model([ToolCall("c3", "delete_assistant", {"assistant_id": keep})], [Text("Confirm above.")])
    card = next(e["value"] for e in ask(user, "delete Keep") if e["type"] == "CUSTOM" and e["name"] == "confirm")

    async def age():
        from backend.models import AgentAction
        from database import async_session
        async with async_session() as db:
            a = await db.get(AgentAction, card["actionId"])
            a.created_at = events.now() - timedelta(minutes=registry.CONFIRM_MINUTES + 1)
            await db.commit()
    run(age)
    late = client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h())
    assert late.status_code == 409 and "waited too long" in late.json()["detail"]
    assert [b["id"] for b in client.get("/api/bots", headers=user.h()).json()] == [keep]


def test_a_voice_agent_change_keeps_the_rest_of_its_form_and_undo_restores_only_that(client, make_user, model):
    user = make_user()
    bot = user.bot()
    agent = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=user.h()).json()
    form = {k: agent[k] for k in ("enabled", "language", "understand_code_mixed", "voice_id")}
    assert client.put(f"/api/voice/agents/{bot}?direction=inbound", json={**form, "silence_timeout_sec": 20},
                      headers=user.h()).status_code == 200
    agent = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=user.h()).json()  # as it is before Nimmi
    model([ToolCall("c1", "update_voice_agent", {"assistant_id": bot, "direction": "inbound", "speaking_rate": 1.2,
                                                 "assistant_name": "Priya"})], [Text("Done.")])
    result = next(e for e in ask(user, "faster, and call yourself Priya") if e["type"] == "TOOL_CALL_RESULT")
    after = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=user.h()).json()
    assert (after["speaking_rate"], after["assistant_name"], after["silence_timeout_sec"]) == (1.2, "Priya", 20)
    assert client.post(f"/api/agent/actions/{result['actionId']}/undo", headers=user.h()).status_code == 200
    back = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=user.h()).json()
    assert (back["speaking_rate"], back["assistant_name"], back["silence_timeout_sec"]) == (agent["speaking_rate"], agent["assistant_name"], 20)


def test_knowledge_added_and_undone_keeps_the_business_summary(client, make_user, model, run, monkeypatch):
    import knowledge_sources
    from routers import bots as bots_router
    monkeypatch.setattr(bots_router, "_after_change", lambda bot, summary=True: {})  # no background summary or index here
    user = make_user()
    bot = user.bot()
    summary = knowledge_sources.put("Our own words.", knowledge_sources.SUMMARY, "A clinic in Chennai.")
    client.patch(f"/api/bots/{bot}", json={"knowledge_base": summary}, headers=user.h())
    model([ToolCall("c1", "add_knowledge_text", {"assistant_id": bot, "text": "Open Monday to Saturday, 9 to 6."})], [Text("Added.")])
    result = next(e for e in ask(user, "add our timings") if e["type"] == "TOOL_CALL_RESULT")
    kb = config(user, bot)["knowledge_base"]
    assert "Monday to Saturday" in kb and "A clinic in Chennai." in kb

    # The summary is rewritten in the background after a change: undo still works, and keeps the new summary.
    rewritten = knowledge_sources.put(kb, knowledge_sources.SUMMARY, "A dental clinic in Chennai.")
    client.patch(f"/api/bots/{bot}", json={"knowledge_base": rewritten}, headers=user.h())
    assert client.post(f"/api/agent/actions/{result['actionId']}/undo", headers=user.h()).status_code == 200
    kb = config(user, bot)["knowledge_base"]
    assert "Monday to Saturday" not in kb and "A dental clinic in Chennai." in kb and "Our own words." in kb


def test_schedule_changes_wait_for_confirm_and_are_checked_first(client, make_user, model):
    user = make_user()
    bot = user.bot()
    model([ToolCall("c1", "update_schedule", {"assistant_id": bot, "callbacks_on": True, "meeting_link": "zoom.us/x"}),
           ToolCall("c2", "update_schedule", {"assistant_id": bot, "callbacks_on": True})], [Text("Confirm above.")])
    evs = ask(user, "turn on call-backs")
    results = [e for e in evs if e["type"] == "TOOL_CALL_RESULT"]
    assert not results[0]["ok"] and "https://" in results[0]["content"]
    card = next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "confirm")
    assert "call-backs callers ask for: on" in card["summary"]
    assert client.get(f"/api/voice/schedule/settings/{bot}", headers=user.h()).json()["settings"]["callbacks"]["enabled"] is False
    done = client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h()).json()
    assert done["state"] == "done" and done["refresh"] == [{"kind": "schedule", "id": bot}]
    assert client.get(f"/api/voice/schedule/settings/{bot}", headers=user.h()).json()["settings"]["callbacks"]["enabled"] is True



def test_every_route_is_a_tool_or_excluded_with_a_reason_or_pending_for_a_phase(client):
    """The parity check (agent/coverage.py): a new route fails this until it gets a tool or a reason."""
    import main
    from agent import coverage
    routes = sorted(f"{m.upper()} {p}" for p, methods in main.app.openapi()["paths"].items() for m in methods)
    places = {r: coverage.place(r) for r in routes}
    assert not [r for r, p in places.items() if not p], "routes nobody accounted for"
    assert not [(r, p) for r, p in places.items() if len(p) > 1 and not all(x.startswith("tool") for x in p)], \
        "a route both done by a tool and excluded or pending"
    named = ({r for t in registry.TOOLS.values() for r in t.routes} | {k for k in coverage.EXCLUDED if " " in k}
             | set(coverage.PENDING))
    assert named <= set(routes), named - set(routes)  # no misspelt or stale entries
    tools = sum(1 for p in places.values() if p[0].startswith("tool"))
    pending = sum(1 for p in places.values() if p == ["pending"])
    assert tools >= 53 and pending <= 97, (tools, pending)  # the gap only shrinks (30 Oct 2026: 53 by tools, 97 pending)



def test_each_area_brings_its_own_tools_and_go_to_brings_the_next_areas_in_the_same_answer(client, make_user, model):
    user = make_user()
    bot = user.bot()
    script = model([ToolCall("c1", "go_to", {"page": "voice_agent", "assistant_id": bot, "direction": "inbound"})],
                   [ToolCall("c2", "get_voice_agent", {"assistant_id": bot, "direction": "inbound"})], [Text("It speaks English.")])
    evs = ask(user, "what language does my phone agent speak?", screen={"path": "/dashboard", "id": "assistants", "title": "Assistants"})
    first, second = ({t["name"] for t in c["tools"]} for c in script.calls[:2])
    assert "update_assistant_design" in first and "get_voice_agent" not in first and "go_to" in first
    assert "get_voice_agent" in second and "update_voice_agent" in second and "update_assistant_design" not in second
    assert '"id": "voice_agent"' in script.calls[1]["context"] and "About this screen (Voice agent settings)" in script.calls[1]["context"]
    assert next(e for e in evs if e["type"] == "TOOL_CALL_RESULT" and e["toolCallId"] == "c2")["ok"]
    from agent import screens
    assert screens.screen_for_path(f"/dashboard/builder/{bot}?tab=flow") == {
        "path": f"/dashboard/builder/{bot}", "id": "builder", "title": "Assistant builder",
        "entity": {"kind": "assistant", "id": bot}, "tab": "flow"}
    assert screens.screen_for_path("/dashboard/somewhere-new")["id"] == "other"
    assert len(registry.available("owner", "other")) == len(registry.TOOLS)  # an unknown screen: everything


# ─── Phase 3: "create an agent for me" ──────────────────────────────

SITE = [("https://sridental.example/", "Sri Dental Care, Anna Nagar, Chennai. Root canal treatment from Rs 3,500. "
                                       "Open Monday to Saturday, 9 am to 7 pm. Call +91 98765 43210."),
        ("https://sridental.example/services", "Teeth cleaning, braces, implants and root canal treatment.")]
WORDS = {"business": "Sri Dental Care", "industry": "clinic", "language": "en", "names": ["Asha", "Sri Dental Assistant"],
         "greeting": "Hi! I can help with treatments, timings and appointments at Sri Dental Care.",
         "instructions": "You help visitors of Sri Dental Care. Root canal treatment starts at Rs 3,500. "
                         "Teeth whitening costs Rs 999.",  # the website never says 999: this sentence must go
         "topics": [{"label": "Treatments", "answer": "Cleaning, braces, implants and root canal treatment."},
                    {"label": "Timings", "answer": "Monday to Saturday, 9 am to 7 pm."},
                    {"label": "Offers", "answer": "Free check-up worth Rs 1,200 this month."}],  # not on the site
         "details": {"standard": ["name", "phone"], "own": ["Preferred date"], "when": "interest"},
         "test_questions": ["Do you do implants?", "What are your timings?", "Where are you?"],
         "voice_greeting": "Welcome to Sri Dental Care. How can I help you today?"}


@pytest.fixture
def website(monkeypatch):
    """A stand-in website and AI for the builder; `calls` counts what was asked of them."""
    import crawler
    import netsafe
    from agent import brand
    calls = {"crawl": 0, "ai": 0, "fail_ai": 0}

    async def crawl(url, pages=25):
        calls["crawl"] += 1
        return SITE

    async def look(url):
        return {"name": "Sri Dental Care", "logo": "https://sridental.example/logo.png", "colours": ["#0e7c86", "#f59e0b"],
                "primary": "#0e7c86", "text_on_primary": "#ffffff", "font": "Poppins", "found_colours": True,
                "url": url, "moved_to": None}

    async def ask_json(system, text):
        calls["ai"] += 1
        if calls["fail_ai"]:
            calls["fail_ai"] -= 1
            raise providers.ModelError("Every AI model is at its rate limit or quota", busy=True)
        assert "<data>" in text and "Root canal" in text and "INDUSTRIES" not in system
        return dict(WORDS), [Usage("gpt-oss-120b", 3000, 400)]

    async def public(url):
        return url
    monkeypatch.setattr(crawler, "crawl_site", crawl)
    monkeypatch.setattr(brand, "extract", look)
    monkeypatch.setattr(providers, "ask_json", ask_json)
    monkeypatch.setattr(netsafe, "assert_public_url", public)
    from routers import bots as bots_router
    monkeypatch.setattr(bots_router, "_after_change", lambda bot, summary=True: {})
    return calls


def step(user, job_id, name, body):
    with user.client.stream("POST", f"/api/agent/jobs/{job_id}/{name}", json=body, headers=user.h()) as r:
        assert r.status_code == 200, r.read()
        return sse_events(r)


def card(evs, kind):
    return next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "card" and e["value"]["kind"] == kind)


def test_the_builder_makes_a_whole_assistant_from_a_website_card_by_card(client, make_user, model, website):
    user = make_user()
    model([ToolCall("c1", "start_agent_builder", {})], [Text("Fill in your website above.")])
    evs = ask(user, "create an assistant for my clinic")
    job = card(evs, "source")["jobId"]
    thread_id = evs[0]["threadId"]

    evs = step(user, job, "source", {"url": "sridental.example"})
    steps = [(e["stepName"], e["ok"]) for e in evs if e["type"] == "STEP_FINISHED"]
    assert steps == [("read", True), ("create", True), ("write", True), ("save", True)]
    assert "left out 2 part(s) the website doesn't support" in next(e["detail"] for e in evs if e.get("stepName") == "write" and e["type"] == "STEP_FINISHED")
    look = card(evs, "look")
    assert look["names"][:2] == ["Asha", "Sri Dental Assistant"] and look["colours"][:2] == ["#0e7c86", "#f59e0b"]
    bot = look["botId"]
    c = config(user, bot)
    assert c["bot_name"] == "Sri Dental Care" and "Root canal treatment starts at Rs 3,500." in c["system_prompt"]
    assert "999" not in c["system_prompt"]  # the fact check left the invented price out
    assert "sridental.example/services" in c["knowledge_base"] and c["visual_config"]["color"] == "#0e7c86"
    nodes = {n["id"]: n for n in c["flow_data"]["nodes"]}
    assert nodes["n-what"]["data"]["options"] == ["Treatments", "Timings", "Ask something else"]  # "Offers" wasn't on the site
    assert {(e["source"], e["target"], e["sourceHandle"]) for e in c["flow_data"]["edges"] if e["source"] == "n-what"} == {
        ("n-what", "n-t0", "Treatments"), ("n-what", "n-t1", "Timings"), ("n-what", "n-ask", "Ask something else")}
    assert c["behaviour"]["collect"] == {"enabled": True, "fields": ["name", "phone"], "custom": ["Preferred date"], "timing": "interest"}

    evs = step(user, job, "look", {"name": "Asha", "colour": "#f59e0b", "use_logo": True})
    assert card(evs, "voice")["name"] == "Asha"
    c = config(user, bot)
    assert (c["bot_name"], c["visual_config"]["color"], c["visual_config"]["text_color"], c["visual_config"]["logo_url"]) == (
        "Asha", "#f59e0b", "#111827", "https://sridental.example/logo.png")  # dark text reads better on amber

    evs = step(user, job, "voice", {"on": True})
    result = card(evs, "result")
    assert result["botId"] == bot and result["tryUrl"] == f"/demo/{bot}" and result["numbersUrl"] == "/dashboard/voice/numbers"
    agent = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=user.h()).json()
    assert (agent["assistant_name"], agent["company_name"], agent["voice_id"], agent["enabled"]) == ("Asha", "Sri Dental Care", "priya", False)
    script = client.get(f"/api/voice/scripts/{bot}/inbound", headers=user.h()).json()
    assert script["greeting"] == WORDS["voice_greeting"] and script["call_goal"]

    # The chat keeps it all: the cards (none open now), what the builder said, in order.
    items = client.get(f"/api/agent/threads/{thread_id}", headers=user.h()).json()["items"]
    assert [(i["card"]["kind"], i["active"]) for i in items if i["type"] == "card"] == [
        ("source", False), ("look", False), ("voice", False), ("result", False)]
    assert any(i["type"] == "text" and "**Asha** is ready" in i["text"] for i in items)
    # A step can't be done twice, or by someone else.
    assert client.post(f"/api/agent/jobs/{job}/voice", json={"on": False}, headers=user.h()).status_code == 409
    assert client.post(f"/api/agent/jobs/{job}/look", json={}, headers=make_user().h()).status_code == 404


def test_a_busy_ai_in_the_builder_can_be_tried_again_without_a_second_assistant(client, make_user, model, website):
    user = make_user()
    model([ToolCall("c1", "start_agent_builder", {})], [Text("Fill it in above.")])
    job = card(ask(user, "make me a chatbot"), "source")["jobId"]
    website["fail_ai"] = 1
    evs = step(user, job, "source", {"url": "https://sridental.example"})
    assert evs[-1]["type"] == "RUN_ERROR" and "busy" in evs[-1]["message"]
    bots = client.get("/api/bots", headers=user.h()).json()
    assert len(bots) == 1  # the draft was made before the AI was asked
    evs = step(user, job, "source", {})  # the same card again: the address is remembered
    assert card(evs, "look")["botId"] == bots[0]["id"]
    assert len(client.get("/api/bots", headers=user.h()).json()) == 1 and website["crawl"] == 1 and website["ai"] == 2

    # Stopping the builder leaves the draft, and says so in the chat.
    assert client.post(f"/api/agent/jobs/{job}/cancel", json={}, headers=user.h()).json()["state"] == "cancelled"
    assert client.post(f"/api/agent/jobs/{job}/look", json={"name": "x", "colour": "#000000"}, headers=user.h()).status_code == 409


def test_the_builder_needs_a_website_or_a_description_and_room_on_the_plan(client, make_user, model, website, monkeypatch):
    user = make_user()
    model([ToolCall("c1", "start_agent_builder", {})], [Text("Above.")])
    job = card(ask(user, "build an agent"), "source")["jobId"]
    evs = step(user, job, "source", {"description": "too short"})
    assert evs[-1]["type"] == "RUN_ERROR" and "describe your business" in evs[-1]["message"]

    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    full = make_user()
    full.bot("The one free assistant")
    model([ToolCall("c1", "start_agent_builder", {})], [Text("Your plan is full.")])
    result = next(e for e in ask(full, "create another assistant") if e["type"] == "TOOL_CALL_RESULT")
    assert not result["ok"] and "Billing" in result["content"]



# ─── Phase 4: connections, guided ───────────────────────────────────

def test_guides_end_at_nimmis_own_form_and_status_and_numbers_follow(client, make_user, model, run):
    user = make_user()
    bot, other_bot = user.bot("Front Desk"), user.bot("Sales")
    model([ToolCall("c1", "connection_guide", {"provider": "twilio"})], [Text("The steps are above.")])
    evs = ask(user, "how do I connect my twilio number?")
    guide = next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "card")
    assert guide["kind"] == "guide" and guide["form"] == "/dashboard/voice/numbers?connect=1"
    assert any("Account Info" in step for step in guide["steps"]) and guide["link"] == "https://console.twilio.com"
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert '"already_connected":false' in result["content"] and "never into this chat" in result["content"]
    items = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()["items"]
    assert [i["card"]["kind"] for i in items if i["type"] == "card"] == ["guide"]  # kept in the chat

    # A number of theirs: which assistant answers it is a change they can undo.
    async def number():
        from backend.models import PhoneNumber
        from database import async_session
        async with async_session() as db:
            n = PhoneNumber(user_id=user.id, number="+1 484 555 0100", status="active", bot_id=bot, provider="twilio")
            db.add(n)
            await db.commit()
            return n.id
    number_id = run(number)
    model([ToolCall("c2", "assign_number", {"number_id": number_id, "assistant_id": other_bot})], [Text("Done.")])
    result = next(e for e in ask(user, "let Sales answer my number",
                                 screen={"path": "/dashboard/voice/numbers", "id": "voice_numbers", "title": "Voice: Numbers"})
                  if e["type"] == "TOOL_CALL_RESULT")
    assert result["ok"] and result["undoable"]
    status = client.get("/api/voice/numbers", headers=user.h()).json()
    assert [n["bot_id"] for n in status] == [other_bot]
    assert client.post(f"/api/agent/actions/{result['actionId']}/undo", headers=user.h()).status_code == 200
    assert [n["bot_id"] for n in client.get("/api/voice/numbers", headers=user.h()).json()] == [bot]

    # Connected accounts are the owner's to see.
    me, _ = teammate(client, user, "admin")
    script = model([ToolCall("c3", "connection_status", {})], [Text("ok")])
    with client.stream("POST", "/api/agent/messages", json={"text": "what's connected?"}, headers={**me, "X-Workspace": user.id}) as r:
        out = next(e for e in sse_events(r) if e["type"] == "TOOL_CALL_RESULT")
    assert out["ok"] and '"accounts"' not in out["content"] and "+1 484 555 0100" in out["content"]



# ─── Phase 5: limits by plan, cost, usage ───────────────────────────

def test_each_answer_records_its_cost_and_the_usage_adds_up_per_day_and_person(client, make_user, model, monkeypatch):
    from agent import router
    user = make_user("Owner")
    model([Text("ok"), Usage("gpt-oss-120b", 1_000_000, 100_000)])
    ask(user, "hello")
    # GPT-OSS 120B: $0.15 a million tokens in and $0.60 out: $0.21, in rupees at the catalog's rate.
    from voice.catalog import USD_INR_RATE
    usage = client.get("/api/agent/usage", headers=user.h()).json()
    assert usage["total"]["messages"] == 1 and usage["total"]["tokens_in"] == 1_000_000
    assert abs(usage["total"]["cost_inr"] - round(0.21 * USD_INR_RATE, 2)) < 0.01
    assert list(usage["by_person"]) == ["Owner"] and usage["today"]["used"] == 1
    me, _ = teammate(client, user, "agent")
    assert client.get("/api/agent/usage", headers={**me, "X-Workspace": user.id}).status_code == 403

    # The limit is the workspace's: a teammate's messages count against it too; free and paid plans differ.
    monkeypatch.setattr(router, "DAILY_PAID", 2)
    model([Text("ok")])
    with client.stream("POST", "/api/agent/messages", json={"text": "hi"}, headers={**me, "X-Workspace": user.id}) as r:
        assert r.status_code == 200
        sse_events(r)
    assert client.post("/api/agent/messages", json={"text": "again"}, headers=user.h()).status_code == 429
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")  # a free workspace
    free = make_user()
    assert client.get("/api/agent/status", headers=free.h()).json()["daily_limit"] == router.DAILY_FREE


def test_business_hours_change_and_undo_and_a_deleted_assistant_comes_back_on_confirm(client, make_user, model):
    user = make_user()
    model([ToolCall("c1", "update_business_hours", {"on": True, "open_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                                                    "opens": "09:00", "closes": "19:00"}),
           ToolCall("c2", "update_business_hours", {"opens": "9am"})], [Text("Done.")])
    results = [e for e in ask(user, "we're open Monday to Saturday, 9 to 7") if e["type"] == "TOOL_CALL_RESULT"]
    assert results[0]["ok"] and results[0]["undoable"] and not results[1]["ok"] and "24-hour" in results[1]["content"]
    hours = client.get("/api/workspace/settings", headers=user.h()).json()["business_hours"]
    assert hours["enabled"] and hours["days"]["sat"] == {"open": True, "from": "09:00", "to": "19:00"} and not hours["days"]["sun"]["open"]
    assert client.post(f"/api/agent/actions/{results[0]['actionId']}/undo", headers=user.h()).status_code == 200
    assert client.get("/api/workspace/settings", headers=user.h()).json()["business_hours"]["enabled"] is False

    bot = user.bot("Old Desk")
    client.delete(f"/api/bots/{bot}", headers=user.h())
    model([ToolCall("c3", "restore_assistant", {"name": "old desk"})], [Text("Confirm above.")])
    evs = ask(user, "bring back Old Desk", screen={"path": "/dashboard", "id": "assistants", "title": "Assistants"})
    card = next(e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "confirm")
    assert card["title"] == "Restore Old Desk" and client.get("/api/bots", headers=user.h()).json() == []
    done = client.post(f"/api/agent/actions/{card['actionId']}/confirm", headers=user.h()).json()
    assert done["state"] == "done" and [b["name"] for b in client.get("/api/bots", headers=user.h()).json()] == ["Old Desk"]



# ─── Phase 6: Nimmi over MCP ────────────────────────────────────────

def mcp(client, key, method, params=None, id_=1, version="2026-07-28"):
    meta = {"io.modelcontextprotocol/protocolVersion": version, "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"}} if version else {}
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": {**(params or {}), **({"_meta": meta} if meta else {})}}
    return client.post("/mcp", json=body, headers={"Authorization": f"Bearer {key}"} if key else {})


def test_ai_apps_use_nimmis_tools_over_mcp_with_a_key_and_the_same_rules(client, make_user):
    user, stranger = make_user("Owner"), make_user("Stranger")
    bot = user.bot("Clinic Desk")
    stranger.bot("Not Yours")
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    made = client.post("/api/agent/keys", json={"name": "Claude Code"}, headers=user.h()).json()
    key = made["key"]
    assert key.startswith("nmk_") and made["prefix"] == key[:10]
    assert [k["name"] for k in client.get("/api/agent/keys", headers=user.h()).json()] == ["Claude Code"]
    assert "key" not in client.get("/api/agent/keys", headers=user.h()).json()[0]  # shown once only

    found = mcp(client, key, "server/discover").json()["result"]
    assert found["resultType"] == "complete" and found["supportedVersions"][0] == "2026-07-28" and "tools" in found["capabilities"]
    assert found["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "nimmi"
    wrong = mcp(client, key, "tools/list", version="1900-01-01").json()["error"]
    assert wrong["code"] == -32022 and wrong["data"]["requested"] == "1900-01-01" and "2026-07-28" in wrong["data"]["supported"]
    legacy = client.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}}},
        headers={"Authorization": f"Bearer {key}"}).json()["result"]
    assert legacy["protocolVersion"] == "2025-06-18" and legacy["serverInfo"]["name"] == "nimmi"
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                       headers={"Authorization": f"Bearer {key}"}).status_code == 202

    listed = mcp(client, key, "tools/list").json()["result"]
    names = [t["name"] for t in listed["tools"]]
    assert names == sorted(names) and "list_assistants" in names and "go_to" not in names and "start_agent_builder" not in names
    design = next(t for t in listed["tools"] if t["name"] == "update_assistant_design")
    assert design["inputSchema"]["required"] == ["assistant_id"] and design["annotations"]["readOnlyHint"] is False
    assert next(t for t in listed["tools"] if t["name"] == "delete_assistant")["annotations"]["destructiveHint"] is True
    assert listed["cacheScope"] == "private" and listed["ttlMs"] > 0

    found = mcp(client, key, "tools/call", {"name": "list_assistants", "arguments": {}}).json()["result"]
    text = found["content"][0]["text"]
    assert found["isError"] is False and "Clinic Desk" in text and "Not Yours" not in text
    changed = mcp(client, key, "tools/call", {"name": "update_assistant_design", "arguments": {"assistant_id": bot, "brand_colour": "#16a34a"}}).json()["result"]
    assert not changed["isError"] and config(user, bot)["visual_config"]["color"] == "#16a34a" and "Changes > Undo" in changed["content"][0]["text"]
    asked = mcp(client, key, "tools/call", {"name": "delete_assistant", "arguments": {"assistant_id": bot}}).json()["result"]
    assert "waiting_for_confirmation" in asked["content"][0]["text"] and bot in [b["id"] for b in client.get("/api/bots", headers=user.h()).json()]
    waiting = [a for a in client.get("/api/agent/actions", headers=user.h()).json() if a["state"] == "proposed"]
    assert [a["title"] for a in waiting] == ["Delete Clinic Desk"]  # confirmed in Nimmi, not by the AI app
    assert mcp(client, key, "tools/call", {"name": "go_to", "arguments": {"page": "billing"}}).json()["result"]["isError"] is True
    assert mcp(client, key, "nope/method").json()["error"]["code"] == -32601

    # A teammate's key acts with their role; a revoked key stops working at once.
    me, _ = teammate(client, user, "agent")
    their = client.post("/api/agent/keys", json={"name": "Cursor"}, headers={**me, "X-Workspace": user.id}).json()["key"]
    their_tools = [t["name"] for t in mcp(client, their, "tools/list").json()["result"]["tools"]]
    assert "list_assistants" in their_tools and "update_assistant_design" not in their_tools
    key_id = client.get("/api/agent/keys", headers=user.h()).json()[0]["id"]
    assert client.delete(f"/api/agent/keys/{key_id}", headers=user.h()).json() == {"revoked": True}
    assert mcp(client, key, "tools/list").status_code == 401



def test_a_website_that_cant_be_read_says_why_and_offers_the_description_instead():
    from agent.builder import _unreadable
    assert "doesn't let automated readers in" in _unreadable("https://x.in", Exception("Client error '403 Forbidden'"))
    assert "built with JavaScript" in _unreadable("https://x.in", None)
    assert "doesn't open" in _unreadable("https://x.in", Exception("That address could not be found"))
    assert all("Describe your business instead" in _unreadable("https://x.in", e) for e in (None, Exception("boom")))



def test_nimmi_can_have_its_own_ai_keys_so_it_never_uses_up_the_ones_calls_and_chat_need(run, service, monkeypatch):
    seen = service(lambda r: httpx.Response(200, text=sse_body({"choices": [{"delta": {"content": "ok"}}]}, done=True)), GROQ)
    monkeypatch.setenv("AGENT_GROQ_API_KEY", "agent-own-key")
    run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert seen[-1]["headers"]["authorization"] == "Bearer agent-own-key"
    monkeypatch.delenv("AGENT_GROQ_API_KEY")
    run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], []))
    assert seen[-1]["headers"]["authorization"] == "Bearer test-GROQ_API_KEY"  # without its own: the backend's



# ─── The panel's voice and feedback ─────────────────────────────────

def test_the_mic_writes_out_speech_and_answers_can_be_read_aloud_and_rated(client, make_user, model, monkeypatch):
    from voice import sarvam
    user = make_user()
    heard = {}

    async def transcribe(audio, filename, content_type, language="unknown"):
        heard.update(audio=audio, language=language)
        return "  என் assistants எத்தனை?  "

    async def synthesize(text, language, speaker, pace, sample_rate):
        heard.update(text=text, said_in=language, speaker=speaker)
        return b"\x00\x01" * 200
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "transcribe", transcribe)
    monkeypatch.setattr(sarvam, "synthesize", synthesize)

    def mic(data, kind="audio/webm", who=user.h()):
        return client.post("/api/agent/transcribe", files={"file": ("speech.webm", data, kind)}, headers=who)
    assert mic(b"voice").json() == {"text": "என் assistants எத்தனை?"} and heard["language"] == "unknown"
    assert mic(b"x", "text/plain").status_code == 400 and mic(b"x" * 1_000_001).status_code == 400
    assert client.post("/api/agent/transcribe", files={"file": ("s.webm", b"v", "audio/webm")}).status_code == 401

    said = client.post("/api/agent/speak", json={"text": "**Done.** Open [Billing](/dashboard/billing):\n- one\n- two"}, headers=user.h())
    assert said.status_code == 200 and said.headers["content-type"] == "audio/wav" and said.content[:4] == b"RIFF"
    assert heard["text"] == "Done. Open Billing: one two" and heard["said_in"] == "en-IN" and heard["speaker"] == "priya"
    client.post("/api/agent/speak", json={"text": "உங்களிடம் மூன்று assistants இருக்கு"}, headers=user.h())
    assert heard["said_in"] == "ta-IN"
    assert client.post("/api/agent/speak", json={"text": "** **"}, headers=user.h()).status_code == 400

    model([Text("You have one assistant.")])
    evs = ask(user, "how many assistants?")
    run_id = evs[0]["runId"]
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert thread["items"][-1]["runId"] == run_id  # each answer knows its run, for the thumbs
    assert client.post(f"/api/agent/runs/{run_id}/feedback", json={"rating": "down", "note": "wrong count"}, headers=user.h()).json() == {"saved": True}
    assert client.post(f"/api/agent/runs/{run_id}/feedback", json={"rating": "meh"}, headers=user.h()).status_code == 422
    assert client.post(f"/api/agent/runs/{run_id}/feedback", json={"rating": "up"}, headers=make_user().h()).status_code == 404

    async def rated():
        from backend.models import AgentRun
        from database import async_session
        async with async_session() as db:
            run = await db.get(AgentRun, run_id)
            return run.feedback, run.feedback_note
    assert client.portal.call(rated) == ("down", "wrong count")



def test_recordings_reach_sarvam_with_a_type_it_takes(run, monkeypatch):
    """Chrome labels recordings "audio/webm;codecs=opus", which Sarvam refuses; Safari's audio/mp4 it doesn't list."""
    import httpx as real_httpx
    from voice import sarvam
    sent = []

    def answer(request):
        label = request.content.split(b"Content-Type: ")[1].split(b"\r\n")[0].decode()
        sent.append(label)
        if label in ("audio/webm", "application/octet-stream"):
            return real_httpx.Response(200, json={"transcript": " hello "})
        return real_httpx.Response(400, json={"error": {"message": f"Invalid file type: {label}. Only [...]"}})
    real = real_httpx.AsyncClient
    monkeypatch.setattr(sarvam.httpx, "AsyncClient", lambda **kw: real(transport=real_httpx.MockTransport(answer)))
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    assert run(sarvam.transcribe, b"voice", "speech.webm", "audio/webm;codecs=opus") == "hello"
    assert sent == ["audio/webm"]
    assert run(sarvam.transcribe, b"voice", "speech.mp4", "audio/mp4") == "hello"
    assert sent[1:] == ["audio/mp4", "application/octet-stream"]


# ─── Tasks done right: plan, guard, review, flows, copies (NIMMI_AGENT_PLAN.md, section 14) ───

@pytest.fixture
def brain(monkeypatch):
    """Scripts the first look at a message and the reviews of its answer (call it after `model`, which turns them off).
    Records what each review was given."""
    class Brain:
        first = intake.Intake()
        verdicts: list = []
        reviews: list = []
        looks: list = []

    b = Brain()

    async def understand(message, screen, before, usage):
        b.looks.append({"message": message, "screen": screen, "before": before})
        return b.first

    async def review(request, steps, ledger, draft, usage, may_continue):
        b.reviews.append({"request": request, "steps": [dict(s) for s in steps], "changed": list(ledger.changed),
                          "failed": [f for _, f in ledger.failed], "draft": draft, "may_continue": may_continue})
        return b.verdicts.pop(0) if b.verdicts else check.Verdict()

    def use(first=None, *verdicts):
        b.first, b.verdicts, b.reviews, b.looks = first or intake.Intake(), list(verdicts), [], []
        monkeypatch.setattr(intake, "understand", understand)
        monkeypatch.setattr(check, "review", review)
        return b
    return use


def customs(evs, name):
    return [e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == name]


def test_a_task_gets_a_plan_the_panel_shows_keeps_current_and_brings_back(client, make_user, model, brain, run):
    user = make_user()
    bot = user.bot("Clinic Desk")
    steps = ("Read Clinic Desk's setup", "Make it green", "Check the result")
    script = model([ToolCall("p1", "update_plan", {"steps": [{"title": steps[0], "status": "doing"},
                                                             {"title": steps[1], "status": "pending"},
                                                             {"title": steps[2], "status": "pending"}]}),
                    ToolCall("c1", "get_assistant", {"assistant_id": bot})],
                   [ToolCall("c2", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#16a34a"})],
                   [ToolCall("p2", "update_plan", {"steps": [{"title": s, "status": "done"} for s in steps]})],
                   [Text("Clinic Desk is green now.")])
    b = brain(intake.Intake("do", ("design",), True))
    evs = ask(user, "make clinic desk green and check it")
    plans = customs(evs, "plan")
    assert [s["status"] for s in plans[0]["steps"]] == ["doing", "pending", "pending"]  # the model's own plan
    assert [s["status"] for s in plans[-1]["steps"]] == ["done"] * 3
    # Nimmi's own tool isn't a step in the panel; the dashboard's tools are.
    assert [e["toolCallName"] for e in evs if e["type"] == "TOOL_CALL_START"] == ["get_assistant", "update_assistant_design"]
    # A task without a plan yet is told to make one; then the plan is in front of the model every round, and so is
    # what its tools really did.
    assert "<task>" in script.calls[0]["context"] and "<plan>" not in script.calls[0]["context"]
    assert "[pending] Make it green" in script.calls[1]["context"] and "<task>" not in script.calls[1]["context"]
    assert "Changed: Clinic Desk: design: brand colour" in script.calls[3]["context"]
    assert {c["patience"] for c in script.calls} == {loop.TASK_PATIENCE_SEC}  # a task waits out a rate limit
    # Only the groups it needs: the design tool, not the voice agent's or the flow's.
    offered = {t["name"] for t in script.calls[0]["tools"]}
    assert "update_assistant_design" in offered and "update_voice_agent" not in offered and "draft_flow" not in offered
    # A task's words are held until checked: one piece, after the review.
    assert said(evs) == "Clinic Desk is green now." and len(b.reviews) == 1
    assert b.reviews[0]["changed"][0].startswith("Clinic Desk: design: brand colour")
    from database import async_session
    from backend.models import AgentRun

    async def saved():
        async with async_session() as db:
            row = await db.get(AgentRun, evs[0]["runId"])
            return row.kind, row.plan
    kind, kept = run(saved)
    assert kind == "do" and [s["status"] for s in kept] == ["done"] * 3
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert [i["type"] for i in thread["items"]] == ["user", "plan", "step", "step", "text"]
    assert thread["items"][1]["steps"] == kept


def test_an_answer_while_plan_steps_are_open_sends_the_model_back_and_is_never_shown(client, make_user, model, brain):
    user = make_user()
    bot = user.bot("Desk")
    script = model([ToolCall("p0", "update_plan", {"steps": [{"title": "Change the welcome", "status": "doing"},
                                                             {"title": "Change the colour", "status": "pending"}]})],
                   [Text("All done, everything is set!")],  # nothing was done: not shown, back to work
                   [ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "welcome_message": "Hello there"}),
                    ToolCall("p1", "update_plan", {"steps": [{"title": "Change the welcome", "status": "done"},
                                                             {"title": "Change the colour", "status": "failed", "note": "no colour given"}]})],
                   [Text("I changed the welcome message. Which colour would you like?")])
    b = brain(intake.Intake("do", ("design",), True))
    evs = ask(user, "change the welcome and the colour")
    assert "All done" not in said(evs) and said(evs).startswith("I changed the welcome message")
    nudge = script.calls[2]["history"][-1]
    assert nudge["role"] == "user" and "open steps: Change the welcome; Change the colour" in nudge["content"]
    assert len(b.reviews) == 1 and b.reviews[0]["draft"].startswith("I changed the welcome")  # only the real answer
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert "All done" not in json.dumps(thread)  # the guard's exchange isn't kept with the chat

    # A task without a plan to follow isn't the guard's: the review checks it against what was done, for less.
    script = model([Text("Done!")], [Text("Sorry: I haven't changed anything yet.")])
    b = brain(intake.Intake("do", ("design",), True), check.Verdict("fix", answer="I haven't changed anything yet."))
    evs = ask(user, "change the welcome and the colour")
    assert len(script.calls) == 1 and len(b.reviews) == 1 and said(evs) == "I haven't changed anything yet."


def test_the_answer_is_checked_against_what_was_really_done_corrected_or_finished(client, make_user, model, brain):
    user = make_user()
    bot = user.bot("Desk")
    # A plain question by intake's look, but the model changed something: the answer is held and reviewed.
    model([ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#000000"})],
          [Text("Done: I changed the colour, the font and the flow.")])
    b = brain(None, check.Verdict("fix", answer="I changed the colour to black. The font and the flow weren't changed."))
    evs = ask(user, "make it black, use Poppins and redo the flow")
    assert said(evs) == "I changed the colour to black. The font and the flow weren't changed."
    assert b.reviews[0]["draft"].startswith("Done: I changed the colour, the font")
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert thread["items"][-1]["text"].startswith("I changed the colour to black")  # what's kept is what was shown

    # "continue": part of the request was never tried: Nimmi carries on with it once, then answers.
    script = model([ToolCall("c2", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#ffffff"})],
                   [Text("White it is.")],
                   [ToolCall("c3", "update_assistant_design", {"assistant_id": bot, "font": "Poppins"})],
                   [Text("It's white, with Poppins.")])
    b = brain(intake.Intake("do", ("design",), True), check.Verdict("continue", todo=["the font: Poppins"]), check.Verdict())
    evs = ask(user, "white, and the Poppins font")
    assert said(evs) == "It's white, with Poppins." and "White it is." not in said(evs)
    assert "isn't done yet: the font: Poppins" in script.calls[2]["history"][-1]["content"]
    assert [r["may_continue"] for r in b.reviews] == [True, False]  # it carries on once at most
    assert config(user, bot)["visual_config"]["font_family"] == "'Poppins', sans-serif"


def test_a_call_made_twice_in_one_answer_is_not_made_twice(client, make_user, model):
    user = make_user()
    bot = user.bot()
    model([ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#123456"})],
          [ToolCall("c2", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#123456"})],
          [ToolCall("c3", "update_assistant_design", {"assistant_id": bot, "brand_colour": "teal"})],
          [ToolCall("c4", "update_assistant_design", {"assistant_id": bot, "brand_colour": "teal"})],
          [Text("Done.")])
    results = {e["toolCallId"]: e for e in ask(user, "go") if e["type"] == "TOOL_CALL_RESULT"}
    assert results["c1"]["ok"] and results["c1"]["actionId"]
    assert results["c2"]["ok"] and "wasn't made twice" in results["c2"]["content"] and "actionId" not in results["c2"]
    assert not results["c3"]["ok"] and "hex colour" in results["c3"]["content"]
    assert not results["c4"]["ok"] and "failed a moment ago" in results["c4"]["content"]
    assert len(client.get("/api/agent/actions", headers=user.h()).json()) == 1


def test_emojis_never_reach_the_person(client, make_user, model):
    user = make_user()
    model([Text("1️⃣ Programs 2️⃣ Fees ✅ Done \U0001F680")])
    evs = ask(user, "hi")
    assert said(evs) == "1. Programs 2. Fees  Done "
    from agent import output
    assert output.clean("Design → Launcher, © Nimmi") == "Design → Launcher, © Nimmi"  # arrows and signs stay


def test_the_tools_a_message_needs_come_whatever_page_is_open(client, make_user, model, brain):
    user = make_user()
    bot = user.bot()
    on_assistants = {"path": "/dashboard", "id": "assistants", "title": "Assistants"}
    script = model([ToolCall("l1", "load_tools", {"group": "whatsapp"})], [Text("ok")])
    brain(intake.Intake("do", ("voice_agent",), True))
    ask(user, f"make {bot}'s phone agent speak Tamil", screen=on_assistants)
    first, second = ({t["name"] for t in c["tools"]} for c in script.calls[:2])
    assert {"get_voice_agent", "update_voice_agent", "list_assistants", "go_to", "update_plan"} <= first
    assert "update_assistant_design" not in first  # the page's own tools don't come along: only what it needs
    assert "update_whatsapp_number" not in first and "update_whatsapp_number" in second  # load_tools: from the next step
    from agent import groups
    every = set(registry.TOOLS)
    assert set(groups.CORE) | groups.tools_of(groups.GROUPS) == every, every - set(groups.CORE) - groups.tools_of(groups.GROUPS)
    assert all(n in every for n in groups.CORE) and all(groups.tools_of([g]) <= every for g in groups.GROUPS)
    # write_flow and edit_flow_block wait until the flow was read in that answer.
    script = model([ToolCall("g1", "get_flow", {"assistant_id": bot})], [Text("ok")])
    brain(intake.Intake("do", ("flow",), True))
    ask(user, "add a step to the flow")
    first, second = ({t["name"] for t in c["tools"]} for c in script.calls[:2])
    assert "get_flow" in first and "write_flow" not in first and "edit_flow_block" not in first
    assert {"write_flow", "edit_flow_block"} <= second


def test_when_the_first_look_fails_nimmi_answers_as_before(client, make_user, model, monkeypatch, run):
    user = make_user()
    model([Text("Hello!")])

    async def busy(*args, **kwargs):
        raise providers.ModelError("Every AI model is at its rate limit or quota", busy=True)
    monkeypatch.setattr(providers, "ask_json", busy)
    from agent import intake as first_look
    import importlib
    real = importlib.reload(first_look)  # the real function, not the fixture's stand-in
    assert run(real.understand, "hi", {}, [], []) == real.Intake()  # not looked: the open page's tools, as before
    assert real.parse({"kind": "DO", "needs": ["copy", "nowhere", "copy", 3]}) == real.Intake("do", ("copy",), True)
    assert real.parse({"kind": "maybe"}) == real.Intake("ask", (), True)
    from agent import loop as answering
    st = answering.RunState("r", real.Intake())
    assert {t.name for t in st.tools("owner", "builder")} >= {"update_assistant_design", "add_knowledge_text"}


def test_reviews_are_read_safely_and_only_carry_on_when_allowed():
    assert check.parse({"verdict": "fix"}, 0, True).kind == "ok"  # nothing to show instead: the draft goes
    assert check.parse({"verdict": "fix", "answer": "Only the colour changed ✅"}, 0, True).answer == "Only the colour changed"
    assert check.parse({"verdict": "continue", "todo": ["the font"]}, 0, False).kind == "ok"
    assert check.parse({"verdict": "continue", "todo": []}, 0, True).kind == "ok"
    assert check.parse({"verdict": "continue", "todo": ["the font"]}, 0, True).todo == ["the font"]
    assert check.parse({"plan": ["done", "failed"]}, 2, True).plan == ["done", "failed"]
    assert check.parse({"plan": ["done"]}, 2, True).plan is None and check.parse({"plan": ["done", "maybe"]}, 2, True).plan is None
    ledger = check.Ledger()
    ok = registry.Outcome("{}", True, "a1", summary="Desk: design: brand colour: x to y")
    ledger.add(registry.TOOLS["update_assistant_design"], "Changing the design", ok)
    ledger.add(registry.TOOLS["update_assistant_design"], "Changing the design", registry.Outcome("{}", True, kind="repeat"))
    ledger.add(registry.TOOLS["delete_assistant"], "Deleting", registry.Outcome("{}", True, "a2", summary="Delete Desk"))
    ledger.add(registry.TOOLS["write_flow"], "Writing the flow", registry.failed("Step x goes nowhere", "invalid_input"))
    assert ledger.acted() and ledger.lines()[:3] == ["Changed: Desk: design: brand colour: x to y",
                                                     "Waiting for their Confirm in the panel (not done until they click it): Delete Desk",
                                                     "Didn't work: Writing the flow: Step x goes nowhere"]


def test_a_flow_is_read_and_written_as_steps_checked_first_and_undone(client, make_user, model):
    from agent.builder import flow as starter
    user = make_user()
    bot = user.bot("Desk")
    old = starter("Hi! I help with courses.", [{"label": "Courses", "answer": "We teach Python."}])
    client.patch(f"/api/bots/{bot}", json={"flow_data": old}, headers=user.h())
    new_steps = [{"id": "n-hi", "type": "message", "text": "Hi! I help with courses."},
                 {"id": "email", "type": "email_question", "text": "Your email, so we can send the brochure?"},
                 {"id": "done", "type": "end", "text": "Thanks! Ask me anything."}]
    script = model([ToolCall("g1", "get_flow", {"assistant_id": bot})],
                   [ToolCall("w1", "write_flow", {"assistant_id": bot, "steps": [{"id": "a", "type": "message", "text": "x", "next": "nowhere"}]})],
                   [ToolCall("w2", "write_flow", {"assistant_id": bot, "steps": new_steps})],
                   [Text("Added an email question.")])
    evs = ask(user, "ask for their email after the welcome, then end")
    results = {e["toolCallId"]: e for e in evs if e["type"] == "TOOL_CALL_RESULT"}
    read = script.calls[1]["history"][-1]["content"]
    assert read.startswith('Steps: <data>[{"id":"n-hi","type":"message"') and '"type":"choices"' in read and "Ask something else" in read
    assert not results["w1"]["ok"] and "no step with that id" in results["w1"]["content"]
    assert results["w2"]["ok"] and results["w2"]["undoable"]
    flow = config(user, bot)["flow_data"]
    links = sorted((e["source"], e["target"]) for e in flow["edges"])
    assert links == [("email", "done"), ("n-hi", "email"), ("start-1", "n-hi")]
    hi = next(n for n in flow["nodes"] if n["id"] == "n-hi")
    assert hi["position"] == next(n for n in old["nodes"] if n["id"] == "n-hi")["position"]  # kept its place
    assert next(n for n in flow["nodes"] if n["id"] == "email")["data"]["variableName"] == "email"
    assert "the flow now has 3 steps (it had 5)" in client.get("/api/agent/actions", headers=user.h()).json()[0]["summary"]
    assert client.post(f"/api/agent/actions/{results['w2']['actionId']}/undo", headers=user.h()).status_code == 200
    assert config(user, bot)["flow_data"] == old


def test_a_drafted_flow_says_only_what_the_knowledge_says(client, make_user, model, monkeypatch, run):
    from agent.tools import flow as flow_tools
    user = make_user()
    bot = user.bot("Academy")
    client.patch(f"/api/bots/{bot}", json={"knowledge_base": "Kd Academy teaches Python and data science in Chennai. "
                                                             "The Python course is 6 weeks long. Classes run on weekends."},
                 headers=user.h())
    asked = []

    async def ask_json(system, text, role="main", patience=None):
        asked.append((role, system == flow_tools.CHECK, text))
        if system == flow_tools.CHECK:  # the fast model's fact check: what the knowledge doesn't say
            return {"unsupported": [{"id": "pick", "text": "Digital marketing"},
                                    {"id": "courses", "text": "We also run a free career fair."}]}, [Usage("gpt-oss-20b", 900, 60)]
        return {"steps": [
            {"id": "hi", "type": "message", "text": "Welcome to Kd Academy!"},
            {"id": "pick", "type": "choices", "text": "What would you like to know?", "save_as": "topic",
             "choices": [{"label": "Courses", "next": "courses"}, {"label": "Fees", "next": "fees"},
                         {"label": "Digital marketing", "next": "courses"}]},
            {"id": "courses", "type": "message", "next": "name",
             "text": "We teach Python and data science. The Python course is 6 weeks long. We also run a free career fair."},
            {"id": "fees", "type": "message", "text": "The course costs Rs 25,000.", "next": "name"},  # a price it never gave
            {"id": "name", "type": "text_question", "text": "May I have your name?", "save_as": "name"},
            {"id": "phone", "type": "phone_question", "text": "And your phone number?"},
            {"id": "bye", "type": "end", "text": "Thank you, {name}! Our team will call you."}]}, [Usage("gpt-oss-120b", 3000, 400)]
    monkeypatch.setattr(providers, "ask_json", ask_json)
    model([ToolCall("d1", "draft_flow", {"assistant_id": bot, "goal": "get course enquiries"})], [Text("A new flow is in.")])
    evs = ask(user, "make a flow from what it knows")
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert result["ok"] and result["undoable"], result["content"]
    assert [(role, checking) for role, checking, _ in asked] == [("main", False), ("fast", True)]
    assert "Kd Academy teaches Python" in asked[0][2] and "get course enquiries" in asked[0][2]
    flow = config(user, bot)["flow_data"]
    nodes = {n["id"]: n for n in flow["nodes"]}
    assert "fees" not in nodes  # its only sentence had a price the knowledge doesn't have
    assert ("pick", "name", "Fees") in [(e["source"], e["target"], e["sourceHandle"]) for e in flow["edges"]]
    assert nodes["pick"]["data"]["options"] == ["Courses", "Fees"]  # the fact check's finds are left out too
    assert nodes["courses"]["data"]["message"] == "We teach Python and data science. The Python course is 6 weeks long."
    assert nodes["bye"]["data"]["message"] == "Thank you! Our team will call you."  # the widget can't fill {name}
    summary = client.get("/api/agent/actions", headers=user.h()).json()[0]["summary"]
    assert "a new flow from its knowledge, 6 steps" in summary and "left out 3 sentence(s) or choice(s)" in summary
    from backend.models import AgentRun
    from database import async_session

    async def cost():
        async with async_session() as db:
            return (await db.get(AgentRun, evs[0]["runId"])).tokens_in
    assert run(cost) >= 3900  # the drafting and checking calls count with the run


def test_a_draft_that_doesnt_hold_together_goes_back_once_then_says_why(client, make_user, model, monkeypatch):
    user = make_user()
    bot = user.bot("Academy")
    client.patch(f"/api/bots/{bot}", json={"knowledge_base": "Kd Academy teaches Python in Chennai, on weekends, online too."},
                 headers=user.h())
    long = {"steps": [{"id": f"m{i}", "type": "message", "text": "Python on weekends."} for i in range(20)] + [{"id": "e", "type": "end"}]}
    good = {"steps": [{"id": "hi", "type": "message", "text": "Hi! We teach Python."}, {"id": "e", "type": "end", "text": "Ask me anything."}]}
    answers = [long, {"unsupported": []}, good]
    sent = []

    async def ask_json(system, text, role="main", patience=None):
        sent.append(text)
        return answers.pop(0), []
    monkeypatch.setattr(providers, "ask_json", ask_json)
    model([ToolCall("d1", "draft_flow", {"assistant_id": bot})], [Text("ok")])
    assert next(e for e in ask(user, "make a flow") if e["type"] == "TOOL_CALL_RESULT")["ok"]
    assert "It has 21 steps; keep it to 16" in sent[2]  # sent back with what to fix
    assert len(config(user, bot)["flow_data"]["nodes"]) == 3

    answers[:] = [long, {"unsupported": []}, long]
    model([ToolCall("d2", "draft_flow", {"assistant_id": bot})], [Text("ok")])
    result = next(e for e in ask(user, "make a flow") if e["type"] == "TOOL_CALL_RESULT")
    assert not result["ok"] and "nothing was changed" in result["content"] and len(config(user, bot)["flow_data"]["nodes"]) == 3


def test_a_task_cut_short_by_a_busy_ai_says_exactly_what_it_did(client, make_user, model, brain, run):
    user = make_user()
    bot = user.bot("Desk")
    model([ToolCall("p1", "update_plan", {"steps": [{"title": "Make it green", "status": "done"},
                                                    {"title": "Change the welcome", "status": "pending"}]}),
           ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#16a34a"})],
          providers.ModelError("Every AI model is at its rate limit or quota", busy=True))
    brain(intake.Intake("do", ("design",), True))
    evs = ask(user, "make it green and change the welcome")
    text = said(evs)
    assert text.startswith("I couldn't finish: the AI service is at its limit right now. What I did before that:")
    assert "- Desk: design: brand colour" in text and "Not done yet: Change the welcome." in text
    assert evs[-1]["type"] == "RUN_FINISHED" and not [e for e in evs if e["type"] == "RUN_ERROR"]
    from backend.models import AgentRun
    from database import async_session

    async def saved():
        async with async_session() as db:
            return (await db.get(AgentRun, evs[0]["runId"])).error
    assert run(saved).startswith("cut short:")
    # Nothing done yet: the usual message.
    model(providers.ModelError("Every AI model is at its rate limit or quota", busy=True))
    brain(intake.Intake("do", ("design",), True))
    evs = ask(user, "make it red")
    assert [e["message"] for e in evs if e["type"] == "RUN_ERROR"][0].startswith("The AI service is busy right now")


def test_a_task_waits_for_a_model_at_its_rate_limit_rather_than_fail(run, service, monkeypatch):
    calls = []

    def reply(request):
        calls.append(time.monotonic())
        if len(calls) == 1:
            return httpx.Response(429, text='{"error": "tokens per minute"}', headers={"retry-after": "0.2"})
        return httpx.Response(200, text=sse_body({"choices": [{"delta": {"content": "Done."}}]}, done=True))
    service(reply, GROQ)
    monkeypatch.setattr(providers, "_rest", lambda m, e: providers._resting.__setitem__(m.id, time.monotonic() + 0.2) or True)
    told = []

    async def on_wait(seconds):
        told.append(seconds)
    items = run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], [], patience=5, on_wait=on_wait))
    assert [i.text for i in items if isinstance(i, Text)] == ["Done."] and len(calls) == 2 and told and told[0] <= 0.2
    # Without the patience (a plain question), the same limit is an error at once.
    calls.clear()
    with pytest.raises(providers.ModelError) as e:
        run(collect, providers.stream("S", "", [{"role": "user", "content": "hi"}], [], patience=0))
    assert e.value.busy and len(calls) == 1


def test_one_assistant_set_up_like_another_and_all_of_it_undone_at_once(client, make_user, model):
    user = make_user()
    source, target = user.bot("GTBOT"), user.bot("GBOT")
    from agent.builder import flow as starter
    client.patch(f"/api/bots/{source}", json={
        "visual_config": {**config(user, source)["visual_config"], "color": "#166534", "font_family": "'Poppins', sans-serif",
                          "welcome_message": "Hi! I'm GTBOT.", "logo_url": "https://example.com/gt.png", "page_rule": "only"},
        "system_prompt": "You are GradTwin's assistant. Help with internships.",
        "knowledge_base": "GradTwin runs internship programs and corporate training.",
        "behaviour": {"reply_length": "short"},
        "flow_data": starter("Hi! I help with internships.", [{"label": "Programs", "answer": "Internships in IT."}]),
    }, headers=user.h())
    before = config(user, target)
    model([ToolCall("k1", "copy_assistant_settings", {"from_assistant_id": source, "to_assistant_id": target,
                                                      "parts": ["design", "instructions", "reply_settings", "knowledge", "flow"]})],
          [ToolCall("k2", "update_assistant_design", {"assistant_id": target, "name": "GBOT Two"})],
          [Text("GBOT is set up like GTBOT.")])
    evs = ask(user, "set up GBOT like GTBOT")
    src, now_ = config(user, source), config(user, target)
    for key in ("color", "font_family", "welcome_message"):
        assert now_["visual_config"][key] == src["visual_config"][key], key
    assert now_["visual_config"].get("logo_url") != "https://example.com/gt.png"  # the avatar is its own part
    assert now_["visual_config"].get("page_rule") != "only"  # where it shows is per website
    assert now_["system_prompt"] == src["system_prompt"] and now_["flow_data"] == src["flow_data"]
    assert "GradTwin runs internship programs" in now_["knowledge_base"]
    assert now_["behaviour"]["reply_length"] == "short"
    summary = client.get("/api/agent/actions", headers=user.h()).json()[1]["summary"]
    assert summary.startswith("GBOT: copied from GTBOT: design (") and "instructions" in summary and "flow (5 steps)" in summary

    # Undo all: every change of that answer, newest first; the chat is told.
    undone = client.post(f"/api/agent/runs/{evs[0]['runId']}/undo", headers=user.h()).json()
    assert len(undone["undone"]) == 2 and undone["kept"] == [] and undone["refresh"] == [{"kind": "assistant", "id": target}]
    after = config(user, target)
    assert after["bot_name"] == before["bot_name"] and after["system_prompt"] == before["system_prompt"]
    assert after["visual_config"].get("color") == before["visual_config"].get("color") and after["flow_data"] == before["flow_data"]
    thread = client.get(f"/api/agent/threads/{evs[0]['threadId']}", headers=user.h()).json()
    assert "undid everything from one answer" in thread["items"][-1]["text"]
    assert client.post(f"/api/agent/runs/{evs[0]['runId']}/undo", headers=make_user().h()).status_code == 404
    # The same assistant twice, or nothing to copy: said plainly.
    model([ToolCall("k3", "copy_assistant_settings", {"from_assistant_id": source, "to_assistant_id": source, "parts": ["flow"]})],
          [Text("ok")])
    assert "same assistant" in next(e for e in ask(user, "copy") if e["type"] == "TOOL_CALL_RESULT")["content"]


def test_instructions_can_be_edited_in_part(client, make_user, model):
    user = make_user()
    bot = user.bot()
    client.patch(f"/api/bots/{bot}", json={"system_prompt": "Be polite. Office hours are 9 to 5. Be polite."}, headers=user.h())
    model([ToolCall("e1", "update_instructions", {"assistant_id": bot, "mode": "edit", "find": "9 to 5", "text": "10 to 6"}),
           ToolCall("e2", "update_instructions", {"assistant_id": bot, "mode": "edit", "find": "Be polite.", "text": "Be kind."}),
           ToolCall("e3", "update_instructions", {"assistant_id": bot, "mode": "edit", "find": "not there", "text": "x"})],
          [Text("ok")])
    results = [e for e in ask(user, "hours are 10 to 6 now") if e["type"] == "TOOL_CALL_RESULT"]
    assert results[0]["ok"] and config(user, bot)["system_prompt"] == "Be polite. Office hours are 10 to 6. Be polite."
    assert not results[1]["ok"] and "2 times" in results[1]["content"]
    assert not results[2]["ok"] and "copy them exactly" in results[2]["content"]


def test_a_plan_step_is_done_only_once_a_tool_did_it_and_the_plan_follows_the_rounds_work(client, make_user, model, brain):
    user = make_user()
    bot = user.bot("Desk")
    script = model([ToolCall("p1", "update_plan", {"steps": [{"title": "Change the welcome", "status": "done"}]})],
                   # The plan first, the change second: Nimmi runs the change first, so the step is done.
                   [ToolCall("p2", "update_plan", {"steps": [{"title": "Change the welcome", "status": "done"}]}),
                    ToolCall("c1", "update_assistant_design", {"assistant_id": bot, "welcome_message": "Hi there"})],
                   [Text("The welcome now says Hi there.")])
    brain(intake.Intake("do", ("design",), True))
    evs = ask(user, "change the welcome to Hi there")
    plans = [p["steps"][0]["status"] for p in customs(evs, "plan")]
    assert plans == ["pending", "done"]  # ticked off with nothing done: refused; after the change: done
    refused = script.calls[1]["history"][-1]["content"]
    assert "not marked done, because none of your tools has done anything yet" in refused
    second = [m for m in script.calls[2]["history"] if m["role"] == "tool"][-2:]
    assert [m["tool_call_id"] for m in second] == ["p2", "c1"]  # results stay in the order the model asked

    # Seen on a real run: a step's work in one round, ticked off in the next on its own. That's allowed.
    script = model([ToolCall("q1", "update_plan", {"steps": [{"title": "Colour", "status": "doing"}, {"title": "Hours", "status": "pending"}]}),
                    ToolCall("d1", "update_assistant_design", {"assistant_id": bot, "brand_colour": "#0f766e"})],
                   [ToolCall("q2", "update_plan", {"steps": [{"title": "Colour", "status": "done"}, {"title": "Hours", "status": "doing"}]}),
                    ToolCall("k1", "add_knowledge_text", {"assistant_id": bot, "text": "Open 9 to 5."})],
                   [ToolCall("q3", "update_plan", {"steps": [{"title": "Colour", "status": "done"}, {"title": "Hours", "status": "done"}]})],
                   [Text("Both done.")])
    brain(intake.Intake("do", ("design", "knowledge"), True))
    evs = ask(user, "colour teal, and we're open 9 to 5")
    assert [s["status"] for s in customs(evs, "plan")[-1]["steps"]] == ["done", "done"]
    assert "not_done" not in script.calls[3]["history"][-1]["content"]


def test_a_busy_ai_inside_a_tool_is_said_as_busy(client, make_user, model, monkeypatch):
    user = make_user()
    bot = user.bot("Academy")
    client.patch(f"/api/bots/{bot}", json={"knowledge_base": "Kd Academy teaches Python in Chennai, on weekends, online too."},
                 headers=user.h())

    async def busy(system, text, role="main", patience=None):
        raise providers.ModelError("Every AI model is at its rate limit or quota", busy=True)
    monkeypatch.setattr(providers, "ask_json", busy)
    model([ToolCall("d1", "draft_flow", {"assistant_id": bot})], [Text("It's busy; try again soon.")])
    result = next(e for e in ask(user, "make a flow") if e["type"] == "TOOL_CALL_RESULT")
    assert not result["ok"] and '"kind":"busy"' in result["content"] and "The AI service is busy right now" in result["content"]


def test_a_run_that_has_just_ended_sends_its_own_last_event_before_anyone_closes_it(client, make_user, model, run):
    """The run is saved before its last event (so whoever sees the end reads it as it ended); a follower in another
    process that sees it ended doesn't write a last event of its own in that moment, only for a run long gone quiet."""
    user = make_user()
    model([Text("ok")])
    thread_id = ask(user, "first")[0]["threadId"]

    async def ended(seconds_ago):
        from backend.models import AgentRun
        from database import async_session
        async with async_session() as db:
            row = AgentRun(thread_id=thread_id, user_id=user.id, owner_id=user.id, role="owner", state="done",
                           finished_at=events.now() - timedelta(seconds=seconds_ago))
            db.add(row)
            await db.commit()
            return row.id
    assert run(events._end_dead_run, run(ended, 0.5)) is None  # its own RUN_FINISHED is on its way
    closed = run(events._end_dead_run, run(ended, 60))
    assert closed["type"] == "RUN_FINISHED" and closed["outcome"] == "success"


def test_a_used_up_allowance_is_said_as_it_is_not_as_a_minute(client, make_user, model):
    user = make_user()
    model(providers.ModelError("Every AI model is at its rate limit or quota", busy=True, wait=1800))
    evs = ask(user, "hi")
    assert [e["message"] for e in evs if e["type"] == "RUN_ERROR"] == [
        "The AI service has used up its allowance for now (the limits of its current plan). Please try again in about 30 minutes."]
    assert providers.when_free(providers.ModelError("x", busy=True, wait=20)) == "in a minute"
    assert providers.when_free(providers.ModelError("x", busy=True, wait=3600)) == "in about an hour or later"
