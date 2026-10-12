"""Voice REST API: agents, numbers, callbacks, compliance, do-not-call and erasure."""


def test_agent_settings_round_trip_and_validation(client, make_user):
    u = make_user()
    bot = u.bot("Admissions")
    agents = client.get("/api/voice/agents", headers=u.h()).json()
    assert agents[0]["bot_name"] == "Admissions" and agents[0]["enabled"] is False

    cfg = client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()
    cfg.update({"enabled": True, "voice_id": None})
    assert client.put(f"/api/voice/agents/{bot}", json=cfg, headers=u.h()).status_code == 400  # needs a voice

    cfg.update({"voice_id": "priya", "language": "ta-IN", "end_call_phrases": ["  Bye ", ""]})
    saved = client.put(f"/api/voice/agents/{bot}", json=cfg, headers=u.h()).json()
    assert saved["language"] == "ta-IN" and saved["end_call_phrases"] == ["bye"]

    cfg["language"] = "fr-FR"
    assert client.put(f"/api/voice/agents/{bot}", json=cfg, headers=u.h()).status_code == 400


def test_voices_and_overview(client, make_user):
    u = make_user()
    voices = client.get("/api/voice/voices").json()
    assert {"priya", "shubh"} <= {v["id"] for v in voices}
    ov = client.get("/api/voice/overview", headers=u.h()).json()
    assert ov["minutes_topup"] == 30 and len(ov["calls_by_day"]) == 14  # trial minutes
    assert client.post("/api/voice/session", json={"bot_id": u.bot()}, headers=u.h()).status_code == 503  # no SARVAM key


def test_number_lifecycle_and_callbacks(client, make_user):
    u = make_user()
    bot = u.bot()
    req = client.post("/api/voice/numbers", json={"city": "Chennai"}, headers=u.h()).json()
    assert req["status"] == "pending_kyc"
    assert client.patch(f"/api/voice/numbers/{req['id']}", json={"bot_id": bot}, headers=u.h()).status_code == 400

    for kind in ("coi", "gst"):
        r = client.post(f"/api/voice/numbers/{req['id']}/documents", data={"kind": kind},
                        files={"file": (f"{kind}.pdf", b"%PDF-1.4", "application/pdf")}, headers=u.h())
        assert r.status_code == 200
    assert r.json()["status"] == "provisioning"

    assert client.post(f"/api/voice/admin/numbers/{req['id']}/activate", json={"e164": "04445678120"}).status_code == 403
    active = client.post(f"/api/voice/admin/numbers/{req['id']}/activate", json={"e164": "+914445678120"},
                         headers={"x-admin-key": "admin-key"}).json()
    assert active["status"] == "active"
    assert client.patch(f"/api/voice/numbers/{req['id']}", json={"bot_id": bot}, headers=u.h()).json()["bot_id"] == bot

    cb = {"enabled": True, "delay": "1m", "window_start": "09:00", "window_end": "21:00", "max_attempts": 2, "from_number_id": None}
    assert client.put("/api/voice/callbacks", json=cb, headers=u.h()).status_code == 400  # needs a number
    cb["from_number_id"] = req["id"]
    assert client.put("/api/voice/callbacks", json=cb, headers=u.h()).json()["enabled"] is True

    # Public widget request: consent required, then queued once.
    body = {"bot_id": bot, "phone": "98765 43210", "consent": False}
    assert client.post("/api/voice/callbacks/request", json=body).status_code == 400
    body["consent"] = True
    assert client.post("/api/voice/callbacks/request", json=body).json()["status"] == "queued"
    jobs = client.get("/api/voice/callbacks/jobs", headers=u.h()).json()
    assert len(jobs) == 1 and jobs[0]["number"].startswith("+91 98")


def test_compliance_dnc_and_erase(client, make_user):
    u = make_user()
    c = client.get("/api/voice/compliance", headers=u.h()).json()
    c["retention_days"] = 45
    assert client.put("/api/voice/compliance", json=c, headers=u.h()).status_code == 400
    c.update({"retention_days": 30, "opt_out_phrases": ["Call panna vendam", " "]})
    assert client.put("/api/voice/compliance", json=c, headers=u.h()).json()["opt_out_phrases"] == ["call panna vendam"]

    entry = client.post("/api/voice/dnc", json={"number": "+91 99999 11111"}, headers=u.h()).json()
    assert entry["number"] == "+91 99999 11111"
    client.post("/api/voice/dnc", json={"number": "9999911111"}, headers=u.h())  # duplicate is fine
    assert len(client.get("/api/voice/dnc", headers=u.h()).json()) == 1
    assert client.delete(f"/api/voice/dnc/{entry['id']}", headers=u.h()).status_code == 200

    erased = client.post("/api/voice/erase", json={"number": "9999911111"}, headers=u.h()).json()
    assert erased["status"] == "erased"
    assert len(client.get("/api/voice/dnc", headers=u.h()).json()) == 1  # erasure also blocks future calls


def test_exotel_endpoints_need_the_secret(client):
    assert client.get("/api/voice/exotel/after-bot?secret=wrong&CallSid=x").status_code == 403
    assert client.get("/api/voice/exotel/after-bot?secret=exo-secret&CallSid=x", follow_redirects=False).status_code == 302


def test_stuck_callbacks_are_closed_and_dont_block_new_requests(client, make_user, run):
    """A call-back whose call never reported back must not block the same person asking again."""
    from datetime import datetime, timedelta
    from sqlalchemy.future import select
    from database import async_session
    from backend.models import CallbackJob, CallbackSettings
    from voice import scheduler

    u = make_user()
    bot = u.bot()
    old = datetime.utcnow() - timedelta(hours=1)

    async def seed():
        async with async_session() as db:
            db.add(CallbackSettings(user_id=u.id, enabled=True, delay="immediate", window_start="00:00",
                                    window_end="23:59", max_attempts=1))
            db.add(CallbackJob(id="stuck-no-call", user_id=u.id, bot_id=bot, e164="+919876543210", status="calling",
                               attempts=1, next_attempt_at=old, consent_source="test"))
            db.add(CallbackJob(id="stuck-answered", user_id=u.id, bot_id=bot, e164="+919876500000", status="calling",
                               attempts=1, next_attempt_at=old, call_id="call-1", consent_source="test"))
            db.add(CallbackJob(id="in-progress", user_id=u.id, bot_id=bot, e164="+919876511111", status="calling",
                               attempts=1, next_attempt_at=datetime.utcnow(), consent_source="test"))
            await db.commit()

    async def statuses():
        async with async_session() as db:
            jobs = (await db.execute(select(CallbackJob).where(CallbackJob.user_id == u.id))).scalars().all()
            return {j.id: j.status for j in jobs}

    run(seed)
    run(scheduler.expire_stale_calls)
    s = run(statuses)
    assert s["stuck-no-call"] == "failed" and s["stuck-answered"] == "done" and s["in-progress"] == "calling"

    r = client.post("/api/voice/callbacks/request", json={"bot_id": bot, "phone": "9876543210", "consent": True})
    assert r.json()["status"] == "queued"
    assert sum(1 for k, v in run(statuses).items() if v == "queued") == 1  # a fresh request was created
