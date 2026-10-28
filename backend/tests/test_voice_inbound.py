"""Incoming and outgoing agents, their scripts (Voice > Knowledge), and callers remembered by number (Voice > Contacts)."""
import asyncio
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy.future import select

from backend.models import CallLog, Contact, PhoneNumber
from database import async_session
from voice import llm, memory
from voice import router as voice_router
from voice.pipeline import CallSession
from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, fake_tts

AGENT = {
    "enabled": True, "language": "en-IN", "understand_code_mixed": True, "follow_caller_language": True,
    "voice_id": "priya", "speaking_rate": 1.0, "assistant_name": "Nimmi", "company_name": "Desk",
    "allow_interruptions": True, "silence_timeout_sec": 8, "max_call_minutes": 10, "transfer_enabled": False,
    "transfer_number": "", "transfer_when": "", "end_call_phrases": ["bye"], "ambience": "none",
    "ambience_volume": "medium", "silence_reminders": 1, "pronunciations": [], "voicemail_action": "off",
    "voicemail_message": "", "transfer_mode": "cold",
}
CALLER = "+919876543210"


def _agent(client, u, bot, direction=None, **changes):
    url = f"/api/voice/agents/{bot}" + (f"?direction={direction}" if direction else "")
    r = client.put(url, json={**AGENT, **changes}, headers=u.h())
    assert r.status_code == 200, r.text
    return r.json()


def _get(client, u, bot, direction):
    return client.get(f"/api/voice/agents/{bot}?direction={direction}", headers=u.h()).json()


async def _add(*rows):
    async with async_session() as db:
        for row in rows:
            db.add(row)
        await db.commit()
        return [row.id for row in rows if hasattr(row, "id")]


def _call(u, bot, **kw):
    return CallLog(**{"user_id": u.id, "bot_id": bot, "direction": "inbound", "channel": "phone", "caller_e164": CALLER,
                      "outcome": "lead_captured", "summary": "Asked about the ML internship fees; we promised a callback.",
                      "captured": {"Name": "K. Karthik Raja", "Email": "karthik@example.com", "Course": "Machine Learning"},
                      **kw})


async def _contact(bot):
    async with async_session() as db:
        return (await db.execute(select(Contact).where(Contact.bot_id == bot, Contact.e164 == CALLER))).scalars().first()


# ─── incoming and outgoing agents ───────────────────────────────────
def test_the_incoming_agent_starts_as_a_copy_and_then_has_its_own_settings(client, make_user):
    u = make_user()
    bot = u.bot()
    _agent(client, u, bot)  # the dashboard before this change: no direction, the agent everyone had
    assert _get(client, u, bot, "inbound")["voice_id"] == "priya"  # same as outgoing until it's edited

    _agent(client, u, bot, "inbound", voice_id="shubh", language="ta-IN", enabled=False, assistant_name="Asha")
    assert _get(client, u, bot, "outbound")["assistant_name"] == "Asha"  # the business's own name: shared
    _agent(client, u, bot, "outbound", voice_id="kavya", assistant_name="Asha")
    inbound, outbound = _get(client, u, bot, "inbound"), _get(client, u, bot, "outbound")
    assert (inbound["voice_id"], inbound["language"], inbound["enabled"]) == ("shubh", "ta-IN", False)
    assert (outbound["voice_id"], outbound["language"], outbound["enabled"]) == ("kavya", "en-IN", True)
    listed = {d: client.get(f"/api/voice/agents?direction={d}", headers=u.h()).json()[0]["enabled"] for d in ("inbound", "outbound")}
    assert listed == {"inbound": False, "outbound": True}
    assert client.get(f"/api/voice/agents/{bot}?direction=sideways", headers=u.h()).status_code == 400

    # Which languages it may switch to: each agent its own.
    _agent(client, u, bot, "inbound", voice_id="shubh", language="ta-IN", switch_languages=["en-IN", "en-IN"])
    assert _get(client, u, bot, "inbound")["switch_languages"] == ["en-IN"]
    assert _get(client, u, bot, "outbound")["switch_languages"] == []
    r = client.put(f"/api/voice/agents/{bot}?direction=inbound", json={**AGENT, "switch_languages": ["xx-IN"]}, headers=u.h())
    assert r.status_code == 400


# ─── scripts ─────────────────────────────────────────────────────────
def test_scripts_start_from_the_agent_and_are_saved_per_kind_of_call(client, make_user):
    u = make_user()
    bot = u.bot()
    _agent(client, u, bot, greeting="Hi there!", call_goal="Book a visit",
           collect_fields=[{"label": "Budget", "type": "number", "description": "", "choices": [], "required": False}])
    inbound = client.get(f"/api/voice/scripts/{bot}/inbound", headers=u.h()).json()
    assert inbound["saved"] is False and inbound["greeting"] == "Hi there!" and inbound["call_goal"] == "Book a visit"
    assert [f["label"] for f in inbound["collect_fields"]] == ["Budget"]
    assert inbound["greeting_known"] == "Hello {{name}}, how can I help you today?"

    r = client.put(f"/api/voice/scripts/{bot}/inbound", headers=u.h(), json={
        "greeting": " Welcome to Desk! ", "greeting_known": "Welcome back, {{name}}!", "personality": "caring",
        "instructions": "1. Ask what they need.", "call_goal": "Answer their question",
        "collect_fields": [{"label": "Course", "type": "choice", "description": "", "choices": ["ML", "Data"], "required": True}],
        "answers": [{"question": "Personality", "answer": "caring"}, {"question": "Never", "answer": " "}]})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["saved"] and saved["greeting"] == "Welcome to Desk!" and saved["answers"] == [{"question": "Personality", "answer": "caring"}]
    outbound = client.get(f"/api/voice/scripts/{bot}/outbound", headers=u.h()).json()
    assert outbound["saved"] is False and outbound["greeting"] == "Hi there!"  # the other kind of call is untouched


def test_write_with_ai_drafts_a_script_from_the_answers(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    told = {}

    async def fake_complete(bot_, system, user, max_tokens=600, urgent=False):
        told["system"], told["user"] = system, user
        return "Here you go: " + json.dumps({
            "greeting": "Thanks for calling Desk!", "greeting_known": "Hi {{name}}, welcome back!", "personality": "Caring",
            "call_goal": "Book a demo", "instructions": "1. Greet. 2. Ask what they need.",
            "collect_fields": [{"label": "Course", "type": "choice", "choices": ["ML"]}, {"label": "Budget", "type": "money"},
                               {"label": ""}]})
    monkeypatch.setattr(llm, "_complete", fake_complete)
    r = client.post(f"/api/voice/scripts/{bot}/inbound/draft", headers=u.h(),
                    json={"answers": [{"question": "What should callers be able to do?", "answer": "Book a demo"}]})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["greeting"] == "Thanks for calling Desk!" and draft["personality"] == "caring"
    assert draft["collect_fields"] == [  # a choice needs two options; unknown types are text; nameless ones dropped
        {"label": "Course", "type": "text", "description": "", "choices": [], "required": False},
        {"label": "Budget", "type": "text", "description": "", "choices": [], "required": False}]
    assert "Book a demo" in told["user"] and "incoming calls" in told["user"]

    async def broken(*a, **k):
        raise RuntimeError("no model answered")
    monkeypatch.setattr(llm, "_complete", broken)
    assert client.post(f"/api/voice/scripts/{bot}/inbound/draft", headers=u.h(), json={"answers": []}).status_code == 502


# ─── remembering callers ─────────────────────────────────────────────
def test_a_caller_is_remembered_after_a_phone_call_and_only_by_that_assistant(client, make_user, run):
    u = make_user()
    bot, other = u.bot("Desk"), u.bot("Other business")
    [call_id] = run(_add, _call(u, bot))
    run(memory.remember_call, call_id)
    contact = run(_contact, bot)
    assert (contact.name, contact.email, contact.calls) == ("K. Karthik Raja", "karthik@example.com", 1)
    assert contact.details == {"Course": "Machine Learning"}

    known = run(memory.context_for, bot, CALLER)
    assert known["first_name"] == "Karthik" and known["has_email"] and known["details"] == {"Course": "Machine Learning"}
    assert known["calls"][0]["direction"] == "inbound" and "fees" in known["calls"][0]["summary"]
    assert run(memory.context_for, other, CALLER) is None  # another assistant (maybe another business) doesn't know them

    # Nothing to remember: a test in the browser, or nobody answered.
    browser = _call(u, other, channel="browser")
    unanswered = _call(u, other, direction="outbound", outcome="no_answer", summary="Call no answer. Attempt 1.")
    for call in (browser, unanswered):
        [cid] = run(_add, call)
        run(memory.remember_call, cid)
    assert run(_contact, other) is None


def test_a_shorter_name_on_a_later_call_doesnt_replace_the_full_one(client, make_user, run):
    u = make_user()
    bot = u.bot()
    for name in ("Arjun Kumar", "Arjun", "arjun kumar", "Arjun Kumar Raja"):
        [call_id] = run(_add, _call(u, bot, captured={"Name": name}))
        run(memory.remember_call, call_id)
        if name == "arjun kumar":
            assert run(_contact, bot).name == "Arjun Kumar"
    contact = run(_contact, bot)
    assert contact.name == "Arjun Kumar Raja" and contact.calls == 4  # a fuller name is taken


def test_calls_from_before_contacts_existed_are_remembered_too(client, make_user, run):
    u = make_user()
    bot = u.bot()
    run(_add, _call(u, bot, started_at=datetime.utcnow() - timedelta(days=3)))
    known = run(memory.context_for, bot, CALLER)
    assert known["name"] == "K. Karthik Raja" and len(known["calls"]) == 1


def _number(u, bot):
    """One of the assistant's numbers: unique, as other tests use the usual example number."""
    e164 = "+9144" + str(uuid.uuid4().int)[:8]
    return PhoneNumber(user_id=u.id, number=e164, e164=e164, status="active", bot_id=bot, provider="twilio")


def _capture_sessions(monkeypatch):
    started = []

    class Session:
        def __init__(self, setup, transport):
            started.append(setup)

        async def run(self):
            return None
    monkeypatch.setattr(voice_router, "CallSession", Session)
    return started


def test_a_known_caller_is_greeted_by_name_with_their_history_in_mind(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    _agent(client, u, bot)
    client.put(f"/api/voice/scripts/{bot}/inbound", headers=u.h(), json={
        "greeting": "Thanks for calling!", "greeting_known": "Hello {{name}}, how can I help you today?",
        "personality": "caring", "instructions": "Offer a campus visit.", "call_goal": "", "collect_fields": []})
    number = _number(u, bot)
    run(_add, number, _call(u, bot))
    started = _capture_sessions(monkeypatch)

    run(voice_router._route_and_run, FakeTransport(), "CA1", CALLER, number.e164)
    setup = started[0]
    assert setup.direction == "inbound" and setup.variables["name"] == "Karthik"
    assert llm.disclosure(setup.agent, setup.variables).endswith("Hello Karthik, how can I help you today?")
    prompt = llm.system_prompt(setup.agent, setup.bot, "", setup.direction, None, setup.variables,
                               script=setup.script, caller=setup.caller)
    assert "Offer a campus visit." in prompt and "Gentle, patient and reassuring" in prompt
    assert "Earlier calls, newest first:" in prompt and "Call them Karthik" in prompt
    assert "karthik@example.com" not in prompt  # never read out to whoever has the phone

    run(voice_router._route_and_run, FakeTransport(), "CA2", "+919000000001", number.e164)
    stranger = started[1]
    assert stranger.caller is None and llm.disclosure(stranger.agent, stranger.variables).endswith("Thanks for calling!")


def test_turning_off_the_incoming_agent_doesnt_stop_the_outgoing_one(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    _agent(client, u, bot)
    _agent(client, u, bot, "inbound", enabled=False)
    number = _number(u, bot)
    run(_add, number)
    started = _capture_sessions(monkeypatch)
    t = FakeTransport()
    run(voice_router._route_and_run, t, "CA3", CALLER, number.e164)
    assert not started and t.hung_up == "done"


# ─── contacts page, erasure ──────────────────────────────────────────
def test_contacts_can_be_listed_edited_and_forgotten(client, make_user, run):
    u = make_user()
    bot = u.bot()
    [call_id] = run(_add, _call(u, bot))
    run(memory.remember_call, call_id)
    listed = client.get("/api/voice/contacts", headers=u.h()).json()
    assert len(listed) == 1 and listed[0]["name"] == "K. Karthik Raja" and listed[0]["number"] == "+91 98••• ••210"
    contact_id = listed[0]["id"]
    detail = client.get(f"/api/voice/contacts/{contact_id}", headers=u.h()).json()
    assert detail["number"] == "+91 98765 43210" and detail["history"][0]["remembered"]
    edited = client.patch(f"/api/voice/contacts/{contact_id}", headers=u.h(),
                          json={"name": "Karthik", "email": "", "notes": "Prefers Tamil"}).json()
    assert edited["notes"] == "Prefers Tamil" and run(memory.context_for, bot, CALLER)["notes"] == "Prefers Tamil"
    assert client.get("/api/voice/contacts?q=9876", headers=u.h()).json()[0]["id"] == contact_id

    assert client.post(f"/api/voice/contacts/{contact_id}/forget", headers=u.h()).status_code == 200
    assert run(memory.context_for, bot, CALLER) is None  # earlier calls aren't recalled any more
    assert client.get("/api/voice/contacts", headers=u.h()).json() == []
    assert make_user().h() and client.get(f"/api/voice/contacts/{contact_id}", headers=make_user().h()).status_code == 404


def test_erasing_a_number_deletes_its_contact(client, make_user, run):
    u = make_user()
    bot = u.bot()
    [call_id] = run(_add, _call(u, bot))
    run(memory.remember_call, call_id)
    assert client.post("/api/voice/erase", headers=u.h(), json={"number": CALLER}).status_code == 200
    assert run(_contact, bot) is None


def test_the_agent_doesnt_ask_for_the_number_the_person_is_calling_from(run, make_user):
    """On a live call it said "I don't have your phone number on file. Could you share it?" to someone calling from it."""
    u = make_user()
    bot = u.bot()
    told = []

    def replier(bot_, agent, history, text, direction, consent, **kw):
        told.append(kw["phone_known"])
        prompt = llm.system_prompt(agent, bot_, "", direction, consent, phone_known=kw["phone_known"])
        told.append("don't ask for it" in prompt and "or number to reach them" not in prompt)

        async def gen():
            yield "Sure.", None
        return gen()

    async def call(e164):
        t = FakeTransport()
        setup = await _setup(u.id, bot)
        setup.caller_e164 = e164
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([Ev("transcript", "What are the fees?"), Ev("transcript", "bye")]),
                              tts=fake_tts, replier=replier, summarizer=fake_summary)

        async def feed():
            for _ in range(6):
                await t.inbox.put(b"\x00\x00" * 160)
                await asyncio.sleep(0.05)
        feeder = asyncio.create_task(feed())
        await asyncio.wait_for(session.run(), timeout=10)
        feeder.cancel()
    run(call, CALLER)
    assert told == [True, True]
    told.clear()
    run(call, None)  # a test in the browser: no number
    assert told == [False, False]


def test_remembering_callers_can_be_switched_off(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    assert _get(client, u, bot, "inbound")["remember_callers"] is True  # on unless switched off
    number = _number(u, bot)
    run(_add, number, _call(u, bot))
    _agent(client, u, bot, "inbound", remember_callers=False)
    assert _get(client, u, bot, "outbound")["remember_callers"] is False  # one switch for both agents
    started = _capture_sessions(monkeypatch)
    run(voice_router._route_and_run, FakeTransport(), "CA4", CALLER, number.e164)
    assert started[0].caller is None and "name" not in started[0].variables  # not greeted by name, no history

    async def short_call(remember):
        t = FakeTransport()
        setup = await _setup(u.id, bot, remember_callers=remember)
        setup.caller_e164 = "+919811100000" if remember else "+919811100001"
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([Ev("transcript", "Fees?"), Ev("transcript", "bye")]),
                              tts=fake_tts, replier=lambda *a, **k: _say("Sure."), summarizer=fake_summary)
        feeder = asyncio.create_task(_feed(t))
        await asyncio.wait_for(session.run(), timeout=10)
        feeder.cancel()
        await asyncio.sleep(0.3)  # the contact is written just after the call
        async with async_session() as db:
            return (await db.execute(select(Contact).where(Contact.e164 == setup.caller_e164))).scalars().first()
    assert run(short_call, True) is not None and run(short_call, False) is None  # off: nothing new is saved


async def _say(text):
    yield text, None


async def _feed(t):
    for _ in range(6):
        await t.inbox.put(b"\x00\x00" * 160)
        await asyncio.sleep(0.05)
