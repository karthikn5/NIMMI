"""Retell-style call features: data to collect, background sound, reminders, pronunciation,
voicemail detection, warm transfer, campaigns and the collected-data view."""
import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy.future import select

from database import async_session
from backend.models import CallbackJob, CallLog, Campaign, DncEntry, PhoneNumber, VoiceAgent
from voice import ambience, llm, scheduler, twilio
from voice.pipeline import CallSession
from test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, replier_saying

AGENT = {
    "enabled": True, "language": "en-IN", "understand_code_mixed": True, "voice_id": "priya", "speaking_rate": 1.0,
    "assistant_name": "Nimmi", "company_name": "Acme Realty", "greeting": "Hi {{name}}, is now a good time?",
    "allow_interruptions": True, "silence_timeout_sec": 8, "max_call_minutes": 10, "transfer_enabled": False,
    "transfer_number": "", "transfer_when": "", "end_call_phrases": ["bye"],
}


def _number(run, user_id, provider="twilio"):
    async def add():
        async with async_session() as db:
            n = PhoneNumber(user_id=user_id, number="+1 484 328 5015", e164="+14843285015", kind="local", city="US",
                            status="active", provider=provider, monthly_fee=0)
            db.add(n)
            await db.commit()
            return n.id
    return run(add)


# ─── Agent settings ───────────────────────────────────────────────
def test_agent_saves_goal_fields_sound_and_options(client, make_user):
    u = make_user()
    bot = u.bot()
    body = {**AGENT, "call_goal": "Book a site visit", "ambience": "office", "ambience_volume": "low",
            "silence_reminders": 2, "voicemail_action": "leave_message", "voicemail_message": "Hi {{name}}, call us back.",
            "transfer_mode": "warm", "pronunciations": [{"word": "Acme", "say": "Ack-mee"}],
            "collect_fields": [
                {"label": "Budget", "type": "number", "description": "In lakhs", "required": True},
                {"label": "Property type", "type": "choice", "choices": ["Flat", "Villa"]},
                {"label": "Budget", "type": "text"},  # duplicate label: dropped
            ]}
    r = client.put(f"/api/voice/agents/{bot}", json=body, headers=u.h())
    assert r.status_code == 200, r.text
    saved = client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()
    assert [f["label"] for f in saved["collect_fields"]] == ["Budget", "Property type"]
    assert saved["collect_fields"][0]["key"] == "budget" and saved["collect_fields"][0]["required"] is True
    assert saved["ambience"] == "office" and saved["silence_reminders"] == 2 and saved["transfer_mode"] == "warm"

    bad = {**body, "collect_fields": [{"label": "Plan", "type": "choice", "choices": ["Only one"]}]}
    assert client.put(f"/api/voice/agents/{bot}", json=bad, headers=u.h()).status_code == 400
    assert client.put(f"/api/voice/agents/{bot}", json={**body, "ambience": "jungle"}, headers=u.h()).status_code == 400


def test_ambience_sample_and_loop():
    from fastapi.testclient import TestClient
    import main
    r = TestClient(main.app).get("/api/voice/ambience/call_center/sample?volume=low")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    pcm = ambience.loop("office", 8000)
    assert len(pcm) == 8000 * 2 * ambience.LOOP_SECONDS
    player = ambience.AmbiencePlayer("office", "medium", 8000)
    chunk = player.next(len(pcm) + 1600)  # wraps around the loop
    assert len(chunk) == len(pcm) + 1600


# ─── Placeholders, prompt and analysis ────────────────────────────
def test_placeholders_and_prompt():
    assert llm.fill("Hi {{ Name }}, about {{unit}}{{missing}}.", {"name": "Ravi", "unit": "B-204"}) == "Hi Ravi, about B-204."
    agent = VoiceAgent(assistant_name="Nimmi", company_name="Acme", greeting="Hi {{name}}!", language="en-IN",
                       call_goal="Book a visit", collect_fields=[{"label": "Budget", "type": "number", "required": True}])
    assert llm.disclosure(agent, {"name": "Ravi"}).endswith("Hi Ravi!")

    class B:
        bot_name, system_prompt = "Acme", ""
    prompt = llm.system_prompt(agent, B(), "", "outbound", None, {"name": "Ravi"}, "Follow up on {{name}}'s enquiry")
    assert "Follow up on Ravi's enquiry" in prompt and "Your goal on this call: Book a visit" in prompt
    assert "- Budget. Required." in prompt and "name: Ravi" in prompt


def test_analysis_types_the_fields(run, monkeypatch):
    agent = VoiceAgent(call_goal="Book a visit", collect_fields=[
        {"label": "Budget", "type": "number"}, {"label": "Wants visit", "type": "yes_no"},
        {"label": "Type", "type": "choice", "choices": ["Flat", "Villa"]}, {"label": "Email", "type": "email"},
    ])

    async def fake_complete(bot, system, user, max_tokens=600):
        assert "Book a visit" in system and '"Budget": a number' in system
        return json.dumps({"summary": "Wants a flat.", "fields": {"budget": "Rs 45,00,000", "Wants visit": True,
                                                                  "Type": "flat", "Email": "not given"},
                           "successful": True, "sentiment": "Positive"})
    monkeypatch.setattr(llm, "_complete", fake_complete)
    out = run(llm.summarize, object(), [{"speaker": "caller", "text": "hi"}], agent)
    assert out["fields"] == {"Budget": "4500000", "Wants visit": "Yes", "Type": "Flat"}  # bad email dropped
    assert out["successful"] is True and out["sentiment"] == "positive"


# ─── Live call behaviour ──────────────────────────────────────────
async def _run_session(session, transport, feed_seconds=0.6):
    async def feed():
        for _ in range(int(feed_seconds / 0.05)):
            await transport.inbox.put(b"\x00\x00" * 160)
            await asyncio.sleep(0.05)
    feeder = asyncio.create_task(feed())
    call_id = await asyncio.wait_for(session.run(), timeout=15)
    feeder.cancel()
    async with async_session() as db:
        return (await db.execute(select(CallLog).where(CallLog.id == call_id))).scalars().first()


def test_background_sound_fills_silence_and_pronunciation_applies(run, make_user):
    u = make_user()
    bot = u.bot()
    spoken: list[str] = []

    async def tts(text, language, speaker, pace, rate):
        spoken.append(text)
        return b"\x00\x00" * int(rate * 0.05)

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, ambience="office", ambience_volume="medium", company_name="Acme",
                             pronunciations=[{"word": "Acme", "say": "Ack-mee"}])
        script = [Ev("transcript", "ok bye")]
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt(script), tts=tts,
                              replier=replier_saying("x"), summarizer=fake_summary)
        log = await _run_session(session, t)
        return t, log

    t, log = run(scenario)
    assert any("Ack-mee" in s for s in spoken)                       # spoken with the pronunciation
    assert any("Acme" in turn["text"] for turn in log.transcript)    # transcript keeps the spelling
    frame = int(16000 * 0.1) * 2
    assert t.played and all(len(p) == frame for p in t.played)       # steady real-time frames
    assert any(any(p) for p in t.played)                             # ambience under silent speech


def test_silence_reminders_count(run, make_user, monkeypatch):
    import types
    import voice.pipeline as pl
    u = make_user()
    bot = u.bot()
    clock = {"t": 1000.0}

    def fast_clock():  # the call's clock runs fast, so silence builds up in a moment
        clock["t"] += 0.4
        return clock["t"]
    monkeypatch.setattr(pl, "time", types.SimpleNamespace(monotonic=fast_clock))

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, silence_timeout_sec=3, silence_reminders=2)
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]),
                              tts=lambda *a: asyncio.sleep(0, b"\x00\x00" * 800), replier=replier_saying("x"),
                              summarizer=fake_summary)
        await _run_session(session, t, feed_seconds=0.2)
        return t

    said = run(scenario).said()
    assert said.count("Are you still there?") == 1 and said.count("Hello, can you hear me?") == 1
    assert said[-1] == __import__("voice.pipeline", fromlist=["GOODBYES"]).GOODBYES["en-IN"]


def test_voicemail_mode_leaves_message(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        async with async_session() as db:
            job = CallbackJob(user_id=u.id, bot_id=bot, e164="+919876543210", name="Ravi", consent_source="test",
                              status="calling", attempts=1)
            db.add(job)
            await db.commit()
        t = FakeTransport()
        setup = await _setup(u.id, bot, voicemail_message="Hi {{name}}, please call us back.")
        setup.voicemail, setup.variables, setup.callback_job_id, setup.direction = True, {"name": "Ravi"}, job.id, "outbound"
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([]),
                              tts=lambda *a: asyncio.sleep(0, b"\x00\x00" * 800), replier=replier_saying("x"),
                              summarizer=fake_summary)
        log = await _run_session(session, t)
        async with async_session() as db:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.id == job.id))).scalars().first()
        return t, log, job

    t, log, job = run(scenario)
    assert t.said() == ["Hi Ravi, please call us back."]
    assert log.outcome == "voicemail" and job.status == "done"


# ─── Twilio: voicemail detection and warm transfer ────────────────
def test_twilio_answered_by_machine_or_person(client, make_user, run):
    u = make_user()
    bot = u.bot()
    client.put(f"/api/voice/agents/{bot}", json={**AGENT, "voicemail_action": "hangup"}, headers=u.h())

    async def job():
        async with async_session() as db:
            j = CallbackJob(user_id=u.id, bot_id=bot, e164="+919876543210", consent_source="test", status="calling", attempts=1)
            db.add(j)
            await db.commit()
            return j.id
    jid = run(job)
    url = f"/api/voice/twilio/outbound/tw-secret?job={jid}"
    human = client.post(url, data={"CallSid": "CA1", "AnsweredBy": "human"})
    assert "<Stream" in human.text and "voicemail" not in human.text
    machine = client.post(url, data={"CallSid": "CA2", "AnsweredBy": "machine_end_beep"})
    assert "<Hangup/>" in machine.text

    async def state():
        async with async_session() as db:
            j = (await db.execute(select(CallbackJob).where(CallbackJob.id == jid))).scalars().first()
            log = (await db.execute(select(CallLog).where(CallLog.provider_call_id == "CA2"))).scalars().first()
            return j.status, log.outcome
    assert run(state) == ("failed", "voicemail")  # one attempt allowed by default settings

    client.put(f"/api/voice/agents/{bot}", json={**AGENT, "voicemail_action": "leave_message"}, headers=u.h())
    leave = client.post(url, data={"CallSid": "CA3", "AnsweredBy": "machine_end_silence"})
    assert 'name="voicemail" value="1"' in leave.text


def test_warm_transfer_whispers_a_brief(client):
    scheduler.pending_transfers["CA9"] = "+919840012345"
    scheduler.pending_whispers["CA9"] = "Ravi wants a 2BHK under 50 lakhs."
    after = client.post("/api/voice/twilio/after/tw-secret", data={"CallSid": "CA9"})
    assert "<Number url=" in after.text and "whisper" in after.text and "+919840012345" in after.text
    whisper = client.post("/api/voice/twilio/whisper/tw-secret?call=CA9")
    assert "Ravi wants a 2BHK" in whisper.text and "CA9" not in scheduler.pending_whispers

    scheduler.pending_transfers["CA10"] = "+919840012345"  # cold transfer: plain dial
    assert "<Number" not in client.post("/api/voice/twilio/after/tw-secret", data={"CallSid": "CA10"}).text


# ─── Campaigns ────────────────────────────────────────────────────
def test_campaign_create_dispatch_and_finish(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    client.put(f"/api/voice/agents/{bot}", json={**AGENT, "voicemail_action": "hangup"}, headers=u.h())
    number_id = _number(run, u.id)

    async def dnc():
        async with async_session() as db:
            db.add(DncEntry(user_id=u.id, e164="+919800000003", reason="caller_request"))
            await db.commit()
    run(dnc)

    contacts = [{"phone": "98000 00001", "name": "Ravi", "variables": {"unit": "B-204"}},
                {"phone": "+91 98000 00001"},              # duplicate
                {"phone": "12345"},                        # invalid
                {"phone": "9800000003"},                   # on the do-not-call list
                {"phone": "9800000002", "variables": {"name": "Asha"}}]
    body = {"name": "Site visit follow-up", "bot_id": bot, "from_number_id": number_id,
            "purpose": "Follow up on {{name}}'s enquiry about {{unit}}", "contacts": contacts,
            "window_start": "00:00", "window_end": "23:59", "max_attempts": 2, "concurrency": 1, "consent": False}
    assert client.post("/api/voice/campaigns", json=body, headers=u.h()).status_code == 400  # consent required
    r = client.post("/api/voice/campaigns", json={**body, "consent": True}, headers=u.h())
    assert r.status_code == 200, r.text
    camp = r.json()
    assert camp["counts"]["total"] == 2 and camp["skipped"] == {"invalid": 1, "duplicates": 1, "do_not_call": 1}

    dialled = []

    async def fake_place(to, frm, job_id, detect_voicemail=False):
        dialled.append((to, detect_voicemail))
        return f"CA-{len(dialled)}"
    monkeypatch.setattr(twilio, "place_call", fake_place)

    run(scheduler.dispatch_due_callbacks)
    assert dialled == [("+919800000001", True)]  # concurrency 1, voicemail detection on
    run(scheduler.dispatch_due_callbacks)
    assert len(dialled) == 1                      # still one call in flight

    assert client.post(f"/api/voice/campaigns/{camp['id']}/pause", headers=u.h()).json()["status"] == "paused"

    async def finish_first():
        async with async_session() as db:
            j = (await db.execute(select(CallbackJob).where(CallbackJob.provider_call_id == "CA-1"))).scalars().first()
            j.status = "done"
            assert j.variables == {"unit": "B-204", "name": "Ravi"}
            await db.commit()
    run(finish_first)
    run(scheduler.dispatch_due_callbacks)
    assert len(dialled) == 1                      # paused: nobody else is called
    client.post(f"/api/voice/campaigns/{camp['id']}/resume", headers=u.h())
    run(scheduler.dispatch_due_callbacks)
    assert dialled[-1][0] == "+919800000002"

    async def finish_second():
        async with async_session() as db:
            j = (await db.execute(select(CallbackJob).where(CallbackJob.provider_call_id == "CA-2"))).scalars().first()
            j.status = "done"
            await db.commit()
    run(finish_second)
    run(scheduler.finish_campaigns)
    detail = client.get(f"/api/voice/campaigns/{camp['id']}", headers=u.h()).json()
    assert detail["status"] == "completed" and [c["name"] for c in detail["contacts"]] == ["Ravi", "Asha"]
    assert client.get("/api/voice/campaigns", headers=u.h()).json()[0]["counts"]["done"] == 2
    assert client.get("/api/voice/callbacks/jobs", headers=u.h()).json() == []  # campaign calls aren't call-backs


def test_collected_data_table(client, make_user, run):
    u = make_user()
    bot = u.bot()
    client.put(f"/api/voice/agents/{bot}", json={**AGENT, "collect_fields": [{"label": "Budget", "type": "number"}]},
               headers=u.h())

    async def calls():
        async with async_session() as db:
            db.add(CallLog(user_id=u.id, bot_id=bot, channel="phone", caller_e164="+919800000001", outcome="lead_captured",
                           captured={"Budget": "45", "Old field": "x"}, successful=True, sentiment="positive"))
            db.add(CallLog(user_id=u.id, bot_id=bot, channel="browser", outcome="answered", captured={"Budget": "1"}))
            await db.commit()
    run(calls)
    data = client.get(f"/api/voice/data?bot_id={bot}", headers=u.h()).json()
    assert data["columns"] == ["Budget", "Old field"] and len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["values"]["Budget"] == "45" and row["successful"] is True and row["caller"] == "+91 98000 00001"
    assert len(client.get(f"/api/voice/data?bot_id={bot}&include_tests=true", headers=u.h()).json()["rows"]) == 2
