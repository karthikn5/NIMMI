"""Twilio: audio codec, webhooks, media-stream protocol and the dashboard test call."""
import base64
import json
import warnings
from array import array

from sqlalchemy.future import select

from database import async_session
from backend.models import CallbackJob, CallLog
from voice import router as voice_router, scheduler, twilio
from voice.transports import TwilioTransport


def test_ulaw_matches_reference_codec():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            import audioop
        except ImportError:  # removed in Python 3.13
            return
    pcm = array("h", [0, 1, -1, 100, -100, 3000, -3000, 32767, -32768, 12345, -12345]).tobytes()
    assert twilio.pcm_to_ulaw(pcm) == audioop.lin2ulaw(pcm, 2)
    ulaw = bytes(range(256))
    assert twilio.ulaw_to_pcm(ulaw) == audioop.ulaw2lin(ulaw, 2)


def _active_twilio_number(client, user, bot):
    req = client.post("/api/voice/numbers", json={"city": "Chennai"}, headers=user.h()).json()
    client.post(f"/api/voice/admin/numbers/{req['id']}/activate", json={"e164": "+15005550006", "provider": "twilio"},
                headers={"x-admin-key": "admin-key"})
    client.patch(f"/api/voice/numbers/{req['id']}", json={"bot_id": bot}, headers=user.h())
    return req["id"]


def test_incoming_webhook_routes_to_stream(client, make_user, monkeypatch):
    async def no_webhook(e164):
        return None
    monkeypatch.setattr(twilio, "point_number_here", no_webhook)
    assert client.post("/api/voice/twilio/incoming/wrong", data={"To": "+15005550006"}).status_code == 403
    unrouted = client.post("/api/voice/twilio/incoming/tw-secret", data={"To": "+15009999999", "From": "+919876543210"})
    assert "<Hangup/>" in unrouted.text and "isn't set up" in unrouted.text

    u = make_user()
    bot = u.bot()
    _active_twilio_number(client, u, bot)
    r = client.post("/api/voice/twilio/incoming/tw-secret", data={"To": "+15005550006", "From": "+919876543210"})
    assert r.headers["content-type"].startswith("application/xml")
    assert 'url="wss://example.test/api/voice/ws/twilio/tw-secret"' in r.text
    assert 'action="https://example.test/api/voice/twilio/after/tw-secret"' in r.text
    assert 'name="from" value="+919876543210"' in r.text


def test_after_stream_transfers_or_hangs_up(client):
    scheduler.pending_transfers["CA1"] = "+91 98400 12345"
    assert "<Dial>+919840012345</Dial>" in client.post("/api/voice/twilio/after/tw-secret", data={"CallSid": "CA1"}).text
    assert "<Hangup/>" in client.post("/api/voice/twilio/after/tw-secret", data={"CallSid": "CA2"}).text


class FakeWs:
    def __init__(self, incoming):
        self.incoming = [json.dumps(m) for m in incoming]
        self.sent = []

    async def receive_text(self):
        if not self.incoming:
            raise RuntimeError("closed")
        return self.incoming.pop(0)

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def close(self):
        pass


def test_media_stream_protocol(run):
    ulaw = twilio.pcm_to_ulaw(array("h", [1000, -1000] * 80).tobytes())
    ws = FakeWs([
        {"event": "connected"},
        {"event": "start", "streamSid": "MZ1", "start": {"streamSid": "MZ1", "callSid": "CA9",
                                                         "customParameters": {"job": "j1", "from": "+91987"}}},
        {"event": "media", "media": {"payload": base64.b64encode(ulaw).decode()}},
        {"event": "stop"},
    ])

    async def scenario():
        t = TwilioTransport(ws)
        assert await t.wait_for_start()
        pcm = await t.receive()
        end = await t.receive()
        t.closed = False
        await t.play(pcm)
        await t.clear()
        return t, pcm, end

    t, pcm, end = run(scenario)
    assert (t.stream_sid, t.call_sid, t.params["job"]) == ("MZ1", "CA9", "j1")
    assert len(pcm) == 320 and end is None
    assert ws.sent[0]["event"] == "media" and ws.sent[0]["streamSid"] == "MZ1"
    assert ws.sent[1] == {"event": "clear", "streamSid": "MZ1"}


def test_dashboard_test_call(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    assert client.post("/api/voice/test-call", json={"bot_id": bot, "phone": "9876543210"}, headers=u.h()).status_code == 400

    placed, warmed = {}, []

    async def fake_place(to, frm, job_id, **_):
        placed.update(to=to, frm=frm, job=job_id, opening_ready=bool(warmed))
        return "CA-test"
    monkeypatch.setattr(voice_router, "prepare_opening",
                        lambda agent, variables, recorded, rate=8000: warmed.append((agent.bot_id, variables, recorded)))

    async def no_webhook(e164):
        return None
    monkeypatch.setattr(twilio, "place_call", fake_place)
    monkeypatch.setattr(twilio, "point_number_here", no_webhook)
    _active_twilio_number(client, u, bot)

    r = client.post("/api/voice/test-call", json={"bot_id": bot, "phone": "98765 43210"}, headers=u.h())
    assert r.status_code == 200, r.text
    assert placed["to"] == "+919876543210" and placed["frm"] == "+15005550006"
    assert placed["opening_ready"] and warmed == [(bot, {}, True)]  # the opening is made while the phone rings

    # The phone wasn't answered: logged as no answer, and test calls aren't retried.
    client.post("/api/voice/twilio/status/tw-secret", data={"CallSid": "CA-test", "CallStatus": "no-answer"})

    async def check():
        async with async_session() as db:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.id == placed["job"]))).scalars().first()
            logs = (await db.execute(select(CallLog).where(CallLog.provider_call_id == "CA-test"))).scalars().all()
            return job, logs

    job, logs = run(check)
    assert job.status == "failed" and [c.outcome for c in logs] == ["no_answer"]


def test_place_call_sends_a_valid_twilio_request(run, monkeypatch):
    """Exercises the real HTTP request (against a mock Twilio), not a stubbed function."""
    import httpx
    from urllib.parse import parse_qs
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["form"] = parse_qs(request.content.decode())
        return httpx.Response(201, json={"sid": "CA123"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    sid = run(twilio.place_call, "+919876543210", "+15005550006", "job-1")
    assert sid == "CA123"
    assert seen["url"].endswith("/Accounts/ACtest/Calls.json")
    assert seen["form"]["To"] == ["+919876543210"] and seen["form"]["From"] == ["+15005550006"]
    assert "<Stream url=" in seen["form"]["Twiml"][0] and 'value="job-1"' in seen["form"]["Twiml"][0]


def test_completed_status_after_a_real_conversation_is_ignored(client, make_user, run):
    """Twilio's 'completed' can arrive before the session finishes writing; it must not add a failed call."""
    u = make_user()
    bot = u.bot()

    async def seed():
        async with async_session() as db:
            job = CallbackJob(user_id=u.id, bot_id=bot, e164="+919876543210", consent_source="Test call requested from the dashboard",
                              status="calling", attempts=1, provider_call_id="CA-live")
            db.add(job)
            db.add(CallLog(user_id=u.id, bot_id=bot, direction="outbound", channel="phone", provider_call_id="CA-live",
                           outcome="in_progress"))
            await db.commit()
    run(seed)
    client.post("/api/voice/twilio/status/tw-secret", data={"CallSid": "CA-live", "CallStatus": "completed"})

    async def logs():
        async with async_session() as db:
            return (await db.execute(select(CallLog).where(CallLog.provider_call_id == "CA-live"))).scalars().all()
    assert [c.outcome for c in run(logs)] == ["in_progress"]  # no extra "no_answer" row
