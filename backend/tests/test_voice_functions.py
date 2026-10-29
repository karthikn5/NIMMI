"""Functions a voice agent runs during a call: checking them, running them, and the model asking for them."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.future import select

import netsafe
import secretbox
from database import async_session
from backend.models import VoiceAgent
from tests.test_pipeline import Ev, FakeTransport, _call, _setup
from voice import functions, llm

ORDER = {"kind": "custom", "name": "check_order", "description": "When the caller asks where their order is.",
         "url": "https://shop.example.com/orders/{{caller_number}}", "method": "POST", "speak_during": "Let me check that.",
         "parameters": [{"name": "order_id", "type": "string", "description": "The order number", "required": True}],
         "headers": [{"name": "Authorization", "value": "Bearer shop-secret-1234"}]}
SLOTS = {"kind": "check_slots", "name": "check_slots", "description": "When the caller wants an appointment.",
         "cal_api_key": "cal_live_abcd9999", "event_type_id": "42", "timezone": "Asia/Kolkata"}
BOOK = {**SLOTS, "kind": "book", "name": "book_appointment", "description": "When the caller picks a time."}


def _fake_http(monkeypatch, handler):
    """Every function request goes to `handler` instead of the internet (the address check still runs on the URL)."""
    seen = []

    def wrapped(request: httpx.Request):
        seen.append(request)
        return handler(request)

    async def public(url):
        return url
    monkeypatch.setattr(netsafe, "assert_public_url", public)
    monkeypatch.setattr(netsafe, "safe_client", lambda timeout=10, **_: httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))
    return seen


def test_functions_are_checked_and_their_secrets_sealed():
    saved = functions.clean([ORDER, SLOTS])
    order, slots = saved
    assert order["id"].startswith("fn_") and order["method"] == "POST" and order["timeout_sec"] == 10
    assert order["headers"][0]["value"].startswith(secretbox.PREFIX) and "shop-secret" not in json.dumps(saved)
    assert slots["event_type_id"] == 42 and slots["cal_api_key"].startswith(secretbox.PREFIX)
    shown = functions.public(saved)
    assert shown[0]["headers"][0]["value"] == "••••1234" and shown[1]["cal_api_key"] == "••••9999"
    # The dashboard sends the masks back unchanged: the stored secrets stay.
    again = functions.clean(shown, saved)
    assert again[0]["headers"][0]["value"] == order["headers"][0]["value"] and again[1]["cal_api_key"] == slots["cal_api_key"]
    for bad, message in [({**ORDER, "name": "Check Order"}, "lowercase"), ({**ORDER, "description": ""}, "when the agent"),
                         ({**ORDER, "url": "ftp://x"}, "https://"), ({**ORDER, "name": "end_call"}, "taken"),
                         ({**SLOTS, "event_type_id": "abc"}, "event type"), ({**SLOTS, "cal_api_key": ""}, "API key"),
                         ({**ORDER, "parameters": [{"name": "size", "type": "enum"}]}, "choices")]:
        with pytest.raises(functions.FunctionError, match=message):
            functions.clean([bad])
    with pytest.raises(functions.FunctionError, match="Two functions"):
        functions.clean([ORDER, ORDER])


def test_the_model_is_told_each_functions_arguments():
    specs = functions.tool_specs(functions.clean([ORDER, SLOTS, BOOK, {**ORDER, "name": "off_one", "enabled": False}]))
    assert [s["name"] for s in specs] == ["check_order", "check_slots", "book_appointment"]
    assert specs[0]["parameters"] == {"type": "object", "properties": {
        "order_id": {"type": "string", "description": "The order number"}}, "required": ["order_id"]}
    assert "Today is" in specs[1]["description"] and specs[2]["parameters"]["required"] == ["start", "name"]
    assert specs[0]["description"].endswith("Use it only once the caller has given: order_id.")


def test_a_custom_function_calls_the_api_with_the_callers_details(run, monkeypatch):
    seen = _fake_http(monkeypatch, lambda r: httpx.Response(200, json={"status": "shipped", "eta": "Friday"}))
    fn = functions.clean([ORDER])[0]
    result = run(functions.run, fn, {"order_id": "A-77"}, {"caller_number": "+919876543210"})
    assert result == '{"status":"shipped","eta":"Friday"}'
    req = seen[0]
    assert req.method == "POST" and str(req.url) == "https://shop.example.com/orders/+919876543210"
    assert req.headers["authorization"] == "Bearer shop-secret-1234" and json.loads(req.content) == {"order_id": "A-77"}

    get = functions.clean([{**ORDER, "method": "GET", "url": "https://shop.example.com/orders?key=k1"}])[0]
    run(functions.run, get, {"order_id": "A-77"}, {})
    # The arguments join the query the address already has (they replaced it at first, losing the API's own key).
    assert seen[-1].method == "GET" and dict(seen[-1].url.params) == {"key": "k1", "order_id": "A-77"} and not seen[-1].content

    _fake_http(monkeypatch, lambda r: httpx.Response(404, text="no such order"))
    assert run(functions.run, fn, {"order_id": "X"}, {}).startswith("The request failed (HTTP 404): no such order")
    _fake_http(monkeypatch, lambda r: httpx.Response(200, text="x" * 5000))
    assert len(run(functions.run, fn, {}, {})) < functions.RESULT_CHARS + 20


def test_a_function_never_reaches_a_private_address(run, monkeypatch):
    fn = functions.clean([{**ORDER, "url": "http://127.0.0.1:8001/api/admin"}])[0]
    assert "can't be used" in run(functions.run, fn, {}, {})

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    _fake_http(monkeypatch, slow)
    assert "didn't answer in time" in run(functions.run, functions.clean([ORDER])[0], {}, {})


def test_calendar_functions_check_slots_and_book_through_cal_com(run, monkeypatch):
    def cal(request: httpx.Request):
        if request.url.path.endswith("/slots"):
            return httpx.Response(200, json={"status": "success", "data": {
                "2030-01-02": [{"start": "2030-01-02T10:00:00.000+05:30"}, {"start": "2030-01-02T10:30:00.000+05:30"}]}})
        return httpx.Response(201, json={"status": "success", "data": {"status": "accepted"}})
    seen = _fake_http(monkeypatch, cal)
    slots, book = functions.clean([SLOTS, BOOK])
    result = run(functions.run, slots, {"start_date": "2030-01-02", "end_date": "2030-01-03"}, {})
    assert result == "Free times (Asia/Kolkata):\nWednesday 02 January: 10:00, 10:30"
    req = seen[0]
    assert req.headers["cal-api-version"] == functions.CAL_SLOTS_VERSION and req.headers["authorization"] == "Bearer cal_live_abcd9999"
    assert req.url.params["eventTypeId"] == "42" and req.url.params["timeZone"] == "Asia/Kolkata"

    result = run(functions.run, book, {"start": "2030-01-02T10:30", "name": "Priya", "email": "priya@example.com"},
                 {"caller_number": "+919876543210", "call_id": "c1"})
    assert result.startswith("Booked: Wednesday 02 January at 10:30 (Asia/Kolkata) for Priya")
    body = json.loads(seen[-1].content)
    assert seen[-1].headers["cal-api-version"] == functions.CAL_BOOKINGS_VERSION
    assert body["start"] == "2030-01-02T05:00:00Z" and body["eventTypeId"] == 42  # 10:30 in India is 05:00 UTC
    assert body["attendee"] == {"name": "Priya", "timeZone": "Asia/Kolkata", "language": "en", "email": "priya@example.com",
                                "phoneNumber": "+919876543210"}
    assert "Ask the caller for the day" in run(functions.run, book, {"start": "next week", "name": "Priya"}, {})


def _agent(**overrides):
    return llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Shop", greeting="", **overrides)


def test_the_model_runs_a_function_then_answers_with_its_result(run, monkeypatch):
    rounds = []

    def model(bot, prompt, history, text, ai_model, answered, tools):
        rounds.append((list(history), text, tools))
        if len(rounds) == 1:
            yield llm.ToolCall("call_1", "check_order", {"order_id": "A-77"})
        else:
            yield "Your order ships on Friday."
    monkeypatch.setattr(llm, "stream_reply", model)
    ran = []

    async def fake_run(fn, args, values):
        ran.append((fn["name"], args, values))
        return '{"eta":"Friday"}'
    monkeypatch.setattr(functions, "run", fake_run)
    agent = _agent(functions=functions.clean([ORDER]))
    log = []

    async def reply():
        return [s async for s in llm.reply_sentences(llm.Bot(bot_name="Shop"), agent, [], "Where is my order?", "inbound", None,
                                                     knowledge="", function_values={"caller_number": "+91"}, function_log=log)]
    said = run(reply)
    assert said == [("Let me check that.", None), ("Your order ships on Friday.", None)]
    assert ran == [("check_order", {"order_id": "A-77"}, {"caller_number": "+91"})]
    assert rounds[0][1] == "Where is my order?" and rounds[0][2][0]["name"] == "check_order"
    history, text, _ = rounds[1]
    assert text is None and [h["role"] for h in history] == ["user", "assistant", "tool"]
    assert history[1]["tool_calls"] == [{"id": "call_1", "name": "check_order", "arguments": {"order_id": "A-77"}}]
    assert history[2] == {"role": "tool", "tool_call_id": "call_1", "name": "check_order", "content": '{"eta":"Friday"}'}
    assert log == history[1:]


def test_half_a_sentence_before_a_function_isnt_spoken(run, monkeypatch):
    """GPT-OSS 120B began "Your order ... is currently," then ran the function (a test call, Oct 2026)."""
    prompts = []

    def model(bot, prompt, history, text, ai_model, answered, tools):
        prompts.append(prompt)
        if tools:
            yield "Your order A one two three four is currently,"
            yield llm.ToolCall("call_1", "check_order", {"order_id": "A1234"})
        else:
            yield "It shipped on Monday."
    monkeypatch.setattr(llm, "stream_reply", model)
    monkeypatch.setattr(llm, "MAX_FUNCTION_ROUNDS", 1)

    async def fake_run(fn, args, values):
        return "shipped on Monday"
    monkeypatch.setattr(functions, "run", fake_run)
    agent = _agent(functions=functions.clean([ORDER]))

    async def reply():
        return [s async for s in llm.reply_sentences(llm.Bot(bot_name="Shop"), agent, [], "Order A1234?", "inbound", None, knowledge="")]
    assert run(reply) == [("Let me check that.", None), ("It shipped on Monday.", None)]
    assert llm.FUNCTION_RULES in prompts[0] and "A1234, not A one two three four" in llm.FUNCTION_RULES


def test_functions_stop_after_three_rounds(run, monkeypatch):
    asked = []

    def model(bot, prompt, history, text, ai_model, answered, tools):
        asked.append(tools)
        yield llm.ToolCall(f"call_{len(asked)}", "check_order", {}) if tools else "I couldn't find it, sorry."
    monkeypatch.setattr(llm, "stream_reply", model)

    async def fake_run(fn, args, values):
        return "not found"
    monkeypatch.setattr(functions, "run", fake_run)
    agent = _agent(functions=functions.clean([{**ORDER, "speak_during": ""}]))

    async def reply():
        return [s async for s in llm.reply_sentences(llm.Bot(bot_name="Shop"), agent, [], "Order?", "inbound", None, knowledge="")]
    assert run(reply) == [("I couldn't find it, sorry.", None)]
    assert len(asked) == llm.MAX_FUNCTION_ROUNDS + 1 and asked[-1] is None


TOOL_TURN = [{"role": "assistant", "content": "Hello!"}, {"role": "user", "content": "Where is my order?"},
             {"role": "assistant", "content": "Let me check.", "tool_calls": [{"id": "call_1", "name": "check_order", "arguments": {"order_id": "A"}}],
              "raw": None},
             {"role": "tool", "tool_call_id": "call_1", "name": "check_order", "content": "shipped"}]


def test_each_service_gets_the_function_turns_in_its_own_format():
    openai = llm._turns("p", TOOL_TURN, None)
    assert openai[3] == {"role": "assistant", "content": "Let me check.", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "check_order", "arguments": '{"order_id": "A"}'}}]}
    assert openai[4] == {"role": "tool", "tool_call_id": "call_1", "content": "shipped"} and len(openai) == 5
    claude = llm._claude_turns(TOOL_TURN, None)
    assert [t["role"] for t in claude] == ["user", "assistant", "user", "assistant", "user"]
    assert claude[3]["content"][1] == {"type": "tool_use", "id": "call_1", "name": "check_order", "input": {"order_id": "A"}}
    assert claude[4]["content"] == [{"type": "tool_result", "tool_use_id": "call_1", "content": "shipped"}]
    gemini = llm._gemini_contents(TOOL_TURN, None)
    assert [c["role"] for c in gemini] == ["user", "model", "user", "model", "user"]  # Gemini needs the caller first
    assert gemini[3]["parts"][1]["thoughtSignature"] == llm._FOREIGN_CALL  # another model's call
    assert gemini[4] == {"role": "user", "parts": [{"functionResponse": {"name": "check_order", "response": {"result": "shipped"}}}]}
    own = [*TOOL_TURN[:2], {**TOOL_TURN[2], "raw": {"gemini_parts": [{"functionCall": {"name": "check_order", "args": {}},
                                                                     "thoughtSignature": "abc"}]}}, TOOL_TURN[3]]
    assert llm._gemini_contents(own, None)[3]["parts"] == [{"functionCall": {"name": "check_order", "args": {}}, "thoughtSignature": "abc"}]
    # The oldest turns are dropped first; a result never comes without its request.
    assert llm._trim([TOOL_TURN[3], *TOOL_TURN[:2]]) == TOOL_TURN[:2]
    assert llm._as_text(TOOL_TURN)[-1] == {"role": "user", "content": "(Result of check_order: shipped)"}


def _delta(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=calls))])


def _call_delta(index, id_=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id_, function=SimpleNamespace(name=name, arguments=arguments))


class _Stream(list):
    def close(self):
        pass


def test_groq_function_calls_arrive_in_pieces(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    sent = []

    class Completions:
        @staticmethod
        def create(**kw):
            sent.append(kw)
            return _Stream([_delta(calls=[_call_delta(0, "call_9", "check_order", '{"order_')]),
                            _delta(calls=[_call_delta(0, arguments='id": "A-77"}')])])
    monkeypatch.setattr(llm, "_groq", lambda: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    tools = functions.tool_specs(functions.clean([ORDER]))
    out = list(llm.stream_reply(llm.Bot(bot_name="Shop"), "p", [], "Order?", None, None, tools))
    assert out == [llm.ToolCall("call_9", "check_order", {"order_id": "A-77"})]
    assert sent[0]["tools"][0] == {"type": "function", "function": tools[0]} and sent[0]["tool_choice"] == "auto"


def test_claude_function_calls_are_read_from_its_events(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    events = [SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="tool_use", id="toolu_1", name="check_order")),
              SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json='{"order_id":')),
              SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json=' "A-77"}')),
              SimpleNamespace(type="content_block_stop")]
    sent = []

    class Stream:
        def __enter__(self):
            return iter(events)

        def __exit__(self, *exc):
            return False

    class Messages:
        def stream(self, **kw):
            sent.append(kw)
            return Stream()
    monkeypatch.setattr(llm, "_anthropic_client", SimpleNamespace(messages=Messages()))
    tools = functions.tool_specs(functions.clean([ORDER]))
    out = list(llm.stream_reply(llm.Bot(bot_name="Shop"), "p", [], "Order?", "claude-haiku-5-5", None, tools))
    assert out == [llm.ToolCall("toolu_1", "check_order", {"order_id": "A-77"})]
    assert sent[0]["tools"][0]["input_schema"] == tools[0]["parameters"]


def _gemini_sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def test_gemini_keeps_its_function_call_parts_to_send_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    bodies = []
    part = {"functionCall": {"name": "check_order", "args": {"order_id": "A-77"}}, "thoughtSignature": "sig-1"}

    def google(request):
        bodies.append(json.loads(request.content))
        return _gemini_sse({"candidates": [{"content": {"parts": [part]}}]})
    monkeypatch.setattr(llm, "_http", httpx.Client(transport=httpx.MockTransport(google)))
    tools = functions.tool_specs(functions.clean([ORDER]))
    out = list(llm.stream_reply(llm.Bot(bot_name="Shop"), "p", [], "Order?", "gemini-3-flash", None, tools))
    assert [(c.name, c.arguments) for c in out] == [("check_order", {"order_id": "A-77"})]
    assert out[0].raw == {"gemini_parts": [part]}
    body = bodies[0]
    assert body["tools"] == [{"functionDeclarations": tools}] and body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Order?"}]}]


def test_a_model_that_cant_run_functions_hands_those_turns_over(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    monkeypatch.setattr(llm, "_stream_openai_style", lambda *a: iter(["From Sarvam."]))
    monkeypatch.setattr(llm, "_stream_groq", lambda model, *a: iter([f"From {model}."]))
    tools = functions.tool_specs(functions.clean([ORDER]))
    answered = []
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Shop"), "p", [], "hi", "sarvam-105b", answered, tools)) == "From qwen/qwen3.8-27b."
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Shop"), "p", [], "hi", "sarvam-105b", answered)) == "From Sarvam."


def test_a_call_keeps_what_its_functions_did(run, make_user):
    u = make_user()
    bot = u.bot()

    async def replier(bot, agent, history, text, direction, consent, function_log=None, function_values=None, **_):
        assert function_values["caller_number"] == "+919876543210"
        function_log += [{"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "check_order", "arguments": {}}]},
                         {"role": "tool", "tool_call_id": "c1", "name": "check_order", "content": "shipped on Monday"}]
        yield "It shipped on Monday.", None

    async def scenario():
        setup = await _setup(u.id, bot)
        session, log = await _call(setup, FakeTransport(), [Ev("speech_start"), Ev("transcript", "Where is my order?"),
                                                            Ev("transcript", "ok bye")], replier)
        return session, log
    session, log = run(scenario)
    roles = [h["role"] for h in session.history]
    at = roles.index("tool")
    assert roles[at - 2:at + 2] == ["user", "assistant", "tool", "assistant"]  # asked, ran, then the spoken answer
    assert session.history[at - 1]["tool_calls"][0]["name"] == "check_order"
    assert any(t["speaker"] == "system" and t["text"] == "Function check_order: shipped on Monday" for t in log.transcript)


def test_agents_save_and_test_their_functions(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    base = client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()
    assert base["functions"] == []
    saved = client.put(f"/api/voice/agents/{bot}", json={**base, "voice_id": "priya", "functions": [ORDER]}, headers=u.h())
    assert saved.status_code == 200, saved.text
    shown = saved.json()["functions"][0]
    assert shown["headers"] == [{"name": "Authorization", "value": "••••1234"}] and shown["id"].startswith("fn_")

    async def stored():
        async with async_session() as db:
            agent = (await db.execute(select(VoiceAgent).where(VoiceAgent.bot_id == bot))).scalars().first()
            return agent.functions[0]["headers"][0]["value"]
    sealed = run(stored)
    assert sealed.startswith(secretbox.PREFIX)
    # Saved again as the dashboard shows it (the secret masked): the secret stays as it was.
    again = client.put(f"/api/voice/agents/{bot}", json={**base, "voice_id": "priya", "functions": [shown]}, headers=u.h())
    assert again.status_code == 200 and run(stored) == sealed
    bad = client.put(f"/api/voice/agents/{bot}", json={**base, "voice_id": "priya", "functions": [{**ORDER, "name": "Bad Name"}]},
                     headers=u.h())
    assert bad.status_code == 400 and "lowercase" in bad.json()["detail"]
    # The incoming agent has the same functions until it's changed, then its own.
    inbound = client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=u.h()).json()
    assert [f["name"] for f in inbound["functions"]] == ["check_order"]
    client.put(f"/api/voice/agents/{bot}?direction=inbound", json={**inbound, "functions": []}, headers=u.h())
    assert client.get(f"/api/voice/agents/{bot}?direction=inbound", headers=u.h()).json()["functions"] == []
    assert len(client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()["functions"]) == 1

    seen = _fake_http(monkeypatch, lambda r: httpx.Response(200, json={"status": "shipped"}))
    tested = client.post(f"/api/voice/agents/{bot}/functions/test", json={"function": shown, "arguments": {"order_id": "A"}},
                         headers=u.h()).json()
    assert tested["result"] == '{"status":"shipped"}' and tested["ms"] >= 0
    assert seen[0].headers["authorization"] == "Bearer shop-secret-1234"  # the stored secret, not the mask
