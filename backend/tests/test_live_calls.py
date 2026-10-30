"""
Live calls and "Pick up the call" (LIVE_CALLS_PLAN.md, voice/handoff.py, voice/live_api.py): a caller who needs a
person rings the team in the dashboard; the first to accept gets the call in their browser or on their phone; nobody
in time means the transfer number or a call-back to-do; and the provider's next request reads where the call goes
from the database, whichever server process it reaches.
"""
import asyncio
import json
from datetime import timedelta

import jwt
from sqlalchemy.future import select

import secretbox
from database import async_session
from backend.models import CallbackJob, CallHandoff, CallLog, TwilioKey
from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_summary, fake_tts
from voice import handoff, twilio
from voice.pipeline import CallSession


def asking(*after: str):
    """A model that asks for a person when the caller wants one, says what the tool tells it to, and otherwise
    answers briefly."""
    async def gen(bot, agent, history, text, direction, consent, schedule_tools=None, **_):
        if "person" in (text or "") and schedule_tools is not None and schedule_tools.has(handoff.TOOL):
            told = await schedule_tools.run(handoff.TOOL, {"reason": "Wants to discuss a refund"})
            gen.told.append(told)
            yield ("Let me get someone from our team, please stay on the line." if "alerted" in told else
                   "I'm connecting you now." if "connecting them" in told else
                   "Nobody can join right now; someone will call you back."), None
            return
        for sentence in after or ("Sure.",):
            yield sentence, None
    gen.told = []
    return gen


async def present(owner_id, user_id, *, available=True, ago=0):
    async with async_session() as db:
        row = await handoff.check_in(db, owner_id, user_id, available_now=available)
        row.seen_at = handoff.now() - timedelta(seconds=ago)
        await db.commit()


def hangs_up_after(words: str):
    """A caller who hangs up once the assistant has said `words` (the call itself goes on until then)."""
    async def caller(session):
        for _ in range(400):
            if any(words in said for said in session.t.said()):
                await asyncio.sleep(0.2)
                await session.t.inbox.put(None)
                return
            await asyncio.sleep(0.05)
    return caller


async def ringing_for(call_id, wait=5.0):
    for _ in range(int(wait / 0.05)):
        async with async_session() as db:
            row = (await db.execute(select(CallHandoff).where(CallHandoff.call_id == call_id))).scalars().first()
        if row is not None:
            return row
        await asyncio.sleep(0.05)
    raise AssertionError("no hand-off")


async def a_call(u, bot, script, replier, *, provider="twilio", sid="CA_live_1", team=None, **agent):
    """Run a call; `team(session)` plays the team member at the same time (a dashboard on another process)."""
    t = FakeTransport()
    t.provider = provider
    setup = await _setup(u.id, bot, **agent)
    setup.provider_call_id = sid
    session = CallSession(setup, t, stt_factory=lambda *a: FakeStt(script), tts=fake_tts, replier=replier,
                          summarizer=fake_summary)

    async def feed():
        await asyncio.sleep(0.05)
        for _ in range(len(script) + 2):
            await t.inbox.put(b"\x00\x00" * 160)
            await asyncio.sleep(0.05)

    feeder = asyncio.create_task(feed())
    member = asyncio.create_task(team(session)) if team else None
    try:
        call_id = await asyncio.wait_for(session.run(), timeout=20)
    finally:
        feeder.cancel()
    result = await member if member else None
    async with async_session() as db:
        log = await db.get(CallLog, call_id)
        rows = (await db.execute(select(CallHandoff).where(CallHandoff.call_id == call_id))).scalars().all()
    return t, session, log, rows, result


def test_a_caller_asking_for_a_person_rings_the_team_and_whoever_accepts_gets_the_call(run, make_user, client):
    u = make_user("Priya")
    bot = u.bot()

    async def scenario():
        await present(u.id, u.id)

        async def team(session):
            while session.call_id is None:
                await asyncio.sleep(0.05)
            row = await ringing_for(session.call_id)
            async with async_session() as db:
                live = await db.get(CallLog, session.call_id)
                alive = live.live_at is not None and live.outcome == "in_progress"
                ok = await handoff.accept(db, row.id, u.id, "browser", handoff.identity(u.id))
                again = await handoff.accept(db, row.id, u.id, "phone", "+919840000000")  # a second click
            return row, alive, ok, again

        replier = asking()
        t, session, log, rows, (row, alive, ok, again) = await a_call(
            u, bot, [Ev("transcript", "Can I talk to a person please?")], replier, team=team)
        return t, log, rows, row, alive, ok, again, replier.told

    t, log, rows, row, alive, ok, again, told = run(scenario)
    assert "alerted" in told[0] and row.status == "ringing" and row.reason == "Wants to discuss a refund"
    assert alive  # the call said it was alive while it ran
    assert ok and not again  # the first to accept gets it
    said = t.said()
    assert "Let me get someone from our team, please stay on the line." in said
    assert said[-1] == handoff.CONNECTING["en-IN"] and t.hung_up == "handoff"
    assert log.outcome == "transferred"
    assert any("Priya picked up in the dashboard" in x["text"] for x in log.transcript if x["speaker"] == "system")
    assert [r.status for r in rows] == ["connecting"]

    # Twilio's next request, from whichever process: the caller goes to Priya's browser, the hand-off riding along.
    after = client.post("/api/voice/twilio/after/tw-secret", data={"CallSid": "CA_live_1"}).text
    assert f"<Identity>{handoff.identity(u.id)}</Identity>" in after and f'value="{row.id}"' in after
    assert f"person-done/tw-secret?h={row.id}" in after
    done = client.post(f"/api/voice/twilio/person-done/tw-secret?h={row.id}",
                       data={"DialCallStatus": "completed", "DialCallDuration": "125"})
    assert "<Hangup/>" in done.text

    async def after_all():
        async with async_session() as db:
            return await db.get(CallHandoff, row.id), await db.get(CallLog, log.id)
    ended, call = run(after_all)
    assert ended.status == "ended" and ended.talk_sec == 125 and ended.connected_at is not None
    assert call.transcript[-1]["text"] == "Priya talked with the caller for 2:05"


def test_nobody_in_time_goes_to_the_transfer_number_or_a_call_back_and_the_call_goes_on(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    monkeypatch.setattr(handoff, "wait_of", lambda agent: 1)  # a second, not 45

    async def scenario(**agent):
        await present(u.id, u.id)
        return await a_call(u, bot, [Ev("transcript", "Can I talk to a person?"), Ev("transcript", "ok")],
                            asking("Anything else?"), sid=f"CA_{len(agent)}", team=hangs_up_after(handoff.BUSY["en-IN"]),
                            **agent)

    # With a transfer number: there, once nobody picked up.
    t, session, log, rows, _ = run(scenario)
    assert t.hung_up == "transfer" and log.outcome == "transferred"
    assert sorted(r.status for r in rows) == ["connecting", "missed"]
    transfer = next(r for r in rows if r.via == "transfer")
    assert transfer.target == "+919840012345" and transfer.provider_call_id == "CA_0"

    # Without one: the AI says the team is busy, a call-back to-do lands in Schedule, and the call goes on.
    t, session, log, rows, _ = run(lambda: scenario(transfer_enabled=False))
    assert handoff.BUSY["en-IN"] in t.said() and t.hung_up != "transfer" and log.outcome != "transferred"
    assert [r.status for r in rows] == ["missed"]

    async def todo():
        async with async_session() as db:
            return (await db.execute(select(CallbackJob).where(CallbackJob.user_id == u.id, CallbackJob.kind == "person"))).scalars().all()
    todos = run(todo)
    assert len(todos) == 1 and todos[0].status == "todo" and "refund" in todos[0].purpose


def test_nobody_available_means_straight_to_the_number_or_a_call_back_and_nobody_is_rung(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario(**agent):
        await present(u.id, u.id, ago=120)  # their dashboard closed two minutes ago
        replier = asking()
        t, session, log, rows, _ = await a_call(u, bot, [Ev("transcript", "Can I talk to a person?")], replier,
                                                sid=f"CA_nobody_{len(agent)}", team=hangs_up_after("Nobody can join"), **agent)
        return t, log, rows, replier.told

    t, log, rows, told = run(scenario)
    assert "goes to the team's phone" in told[0] and t.hung_up == "transfer"
    assert [(r.via, r.status) for r in rows] == [("transfer", "connecting")]  # nobody was rung
    t, log, rows, told = run(lambda: scenario(transfer_enabled=False))
    assert "Nobody from the team can join right now" in told[0] and rows == []
    # Switched off for this agent: no tool at all (the transfer marker, if any, as before).
    from voice.pipeline import CallSetup  # noqa: F401

    async def tools(**agent):
        session = CallSession(await _setup(u.id, bot, **agent), FakeTransport())
        return session.tools.specs()
    assert [s["name"] for s in run(lambda: tools(team_handoff=False, transfer_enabled=False))] == []
    assert [s["name"] for s in run(lambda: tools(transfer_enabled=False))] == [handoff.TOOL]


def test_a_caller_who_hangs_up_while_the_team_is_rung_is_no_longer_waiting(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        await present(u.id, u.id)
        t, session, log, rows, _ = await a_call(u, bot, [Ev("transcript", "Can I talk to a person?")], asking(),
                                                sid="CA_gone", transfer_enabled=False,
                                                team=lambda s: hang_up_when_rung(s))
        return rows

    async def hang_up_when_rung(session):
        while session.call_id is None:
            await asyncio.sleep(0.05)
        await ringing_for(session.call_id)
        await session.t.inbox.put(None)  # the caller hangs up

    assert [r.status for r in run(scenario)] == ["cancelled"]


def test_the_dashboard_sees_live_calls_and_requests_and_the_first_to_accept_gets_it(run, make_user, client):
    from tests.test_agent import teammate
    owner = make_user("Owner")
    bot = owner.bot("Front Desk")
    mate_headers, mate_id = teammate(client, owner, "agent")
    mate_headers = {**mate_headers, "X-Workspace": owner.id}  # working in the owner's workspace

    async def a_live_call():
        async with async_session() as db:
            call = CallLog(user_id=owner.id, bot_id=bot, direction="inbound", channel="phone", caller_e164="+919876543210",
                           outcome="in_progress", live_at=handoff.now(), provider_call_id="CA_api",
                           transcript=[{"at_sec": 1, "speaker": "agent", "text": "Hello!"},
                                       {"at_sec": 3, "speaker": "caller", "text": "I want a refund."},
                                       {"at_sec": 4, "speaker": "system", "text": "Asked the team"}])
            db.add(call)
            await db.flush()
            row = CallHandoff(owner_id=owner.id, bot_id=bot, call_id=call.id, provider="exotel", provider_call_id="CA_api",
                              caller="+919876543210", reason="Wants a refund", status="ringing",
                              expires_at=handoff.now() + timedelta(seconds=40))
            db.add(row)
            await db.commit()
            return call.id, row.id
    call_id, row_id = run(a_live_call)
    both = client.get("/api/voice/live", headers=mate_headers).json()  # the teammate's dashboard checks in
    live = client.get("/api/voice/live", headers=owner.h()).json()
    assert both["me"] == {"available": True, "phone": ""}
    call = next(c for c in live["calls"] if c["id"] == call_id)
    assert call["state"] == "waiting" and call["bot_name"] == "Front Desk" and call["caller"].endswith("210")
    assert "98765" not in call["caller"]  # the number stays masked
    assert [line["text"] for line in call["lines"]] == ["Hello!", "I want a refund."]
    request = live["requests"][0]
    assert request["id"] == row_id and request["reason"] == "Wants a refund" and request["phone"] and not request["browser"]
    assert 0 < request["left_sec"] <= 40

    # An Exotel call can't ring a browser; "Call my phone" needs a number, and remembers it.
    r = client.post(f"/api/voice/live/handoffs/{row_id}/accept", json={"via": "browser"}, headers=owner.h())
    assert r.status_code == 400 and "phone" in r.json()["detail"]
    assert client.post(f"/api/voice/live/handoffs/{row_id}/accept", json={"via": "phone"}, headers=owner.h()).status_code == 400
    ok = client.post(f"/api/voice/live/handoffs/{row_id}/accept", json={"via": "phone", "phone": "98400 12345"}, headers=owner.h())
    assert ok.status_code == 200
    taken = client.post(f"/api/voice/live/handoffs/{row_id}/accept", json={"via": "phone", "phone": "9840011111"}, headers=mate_headers)
    assert taken.status_code == 409 and "Owner already picked it up" in taken.json()["detail"]
    assert client.get("/api/voice/live", headers=owner.h()).json()["me"]["phone"] == "+919840012345"
    # Another workspace can't see or take it.
    other = make_user()
    assert client.post(f"/api/voice/live/handoffs/{row_id}/accept", json={"via": "phone", "phone": "9840011111"},
                       headers=other.h()).status_code == 404
    assert client.get("/api/voice/live", headers=other.h()).json()["calls"] == []


def test_when_everyone_available_lets_the_assistant_handle_it_the_call_stops_waiting(run, make_user, client):
    owner = make_user()
    bot = owner.bot()

    async def ringing():
        async with async_session() as db:
            row = CallHandoff(owner_id=owner.id, bot_id=bot, provider="twilio", status="ringing", reason="x",
                              expires_at=handoff.now() + timedelta(seconds=40))
            db.add(row)
            await db.commit()
            return row.id
    row_id = run(ringing)
    client.get("/api/voice/live", headers=owner.h())  # present
    assert client.post(f"/api/voice/live/handoffs/{row_id}/decline", headers=owner.h()).json() == {"status": "declined"}

    async def read():
        async with async_session() as db:
            return await db.get(CallHandoff, row_id)
    row = run(read)
    assert row.declined_by == [owner.id] and handoff.aware(row.expires_at) <= handoff.now()
    assert client.get("/api/voice/live", headers=owner.h()).json()["requests"] == []


def test_a_browser_gets_a_short_lived_token_from_a_key_made_once_and_kept_sealed(run, make_user, client, monkeypatch):
    owner = make_user()
    bot = owner.bot()
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest00000000000000000000000000")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    made = []

    async def create_api_key(creds=None, name=""):
        made.append(creds)
        return "SKtest", "the-secret"
    monkeypatch.setattr(twilio, "create_api_key", create_api_key)

    async def ringing(provider):
        async with async_session() as db:
            row = CallHandoff(owner_id=owner.id, bot_id=bot, provider=provider, status="ringing", reason="x",
                              expires_at=handoff.now() + timedelta(seconds=40))
            db.add(row)
            await db.commit()
            return row.id
    row_id = run(lambda: ringing("twilio"))
    first = client.post("/api/voice/live/token", json={"handoff_id": row_id}, headers=owner.h()).json()
    second = client.post("/api/voice/live/token", json={"handoff_id": row_id}, headers=owner.h()).json()
    assert made == [None]  # one key on Nimmi's own account, made once
    claims = jwt.decode(first["token"], "the-secret", algorithms=["HS256"])
    assert jwt.get_unverified_header(first["token"])["cty"] == "twilio-fpa;v=1"
    assert claims["iss"] == "SKtest" and claims["sub"] == "ACtest00000000000000000000000000"
    assert claims["grants"] == {"identity": handoff.identity(owner.id), "voice": {"incoming": {"allow": True}}}
    assert claims["exp"] - claims["iat"] == 3600 and second["identity"] == first["identity"]

    async def stored():
        async with async_session() as db:
            return await db.get(TwilioKey, "ACtest00000000000000000000000000")
    key = run(stored)
    assert "the-secret" not in key.secret and json.loads(secretbox.unseal(key.secret)) == {"secret": "the-secret"}
    exotel_row = run(lambda: ringing("exotel"))
    assert client.post("/api/voice/live/token", json={"handoff_id": exotel_row}, headers=owner.h()).status_code == 400


def test_exotel_reads_where_the_call_goes_from_the_database(run, client, monkeypatch):
    monkeypatch.setenv("EXOTEL_WS_SECRET", "ex-secret")

    async def handed(sid, via, target):
        async with async_session() as db:
            row = CallHandoff(provider="exotel", provider_call_id=sid, status="connecting", via=via, target=target)
            db.add(row)
            await db.commit()
            return row.id
    row_id = run(lambda: handed("EX1", "phone", "98400 12345"))
    assert client.get("/api/voice/exotel/after-bot?secret=ex-secret&CallSid=EX1").text == "transfer"
    assert client.get("/api/voice/exotel/transfer-target?secret=ex-secret&CallSid=EX1").text == "+919840012345"
    assert client.get("/api/voice/exotel/after-bot?secret=ex-secret&CallSid=EX2").status_code == 302

    async def read():
        async with async_session() as db:
            return await db.get(CallHandoff, row_id)
    assert run(read).status == "ended"


def test_calls_and_hand_offs_that_died_with_their_server_are_closed(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        async with async_session() as db:
            dead = CallLog(user_id=u.id, bot_id=bot, outcome="in_progress", live_at=handoff.now() - timedelta(minutes=5))
            alive = CallLog(user_id=u.id, bot_id=bot, outcome="in_progress", live_at=handoff.now())
            stuck = CallHandoff(owner_id=u.id, status="ringing", expires_at=handoff.now() - timedelta(minutes=3))
            db.add_all([dead, alive, stuck])
            await db.commit()
            ids = dead.id, alive.id, stuck.id
        await handoff.sweep()
        async with async_session() as db:
            return [await db.get(CallLog, ids[0]), await db.get(CallLog, ids[1]), await db.get(CallHandoff, ids[2])]
    dead, alive, stuck = run(scenario)
    assert dead.outcome == "failed" and "cut off" in dead.summary and alive.outcome == "in_progress"
    assert stuck.status == "missed"
