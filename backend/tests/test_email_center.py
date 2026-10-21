"""Email sequences, the new triggers, email history and bulk email."""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.future import select

from database import async_session
from backend.models import CallbackJob, CallLog, Conversation, EmailJob
from notify import automations, email, events

BASE = {
    "email_alerts": False, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "",
    "alert_calls": False, "sender_name": "Acme Realty", "reply_to": "hello@acme.in",
}


def _capture(monkeypatch):
    sent = []

    async def fake_send(to, subject, text, html_body=None, reply_to=None, from_name=None, unsubscribe_url=None, **_):
        sent.append({"to": to, "subject": subject, "text": text, "unsubscribe": unsubscribe_url})
        return True
    monkeypatch.setattr(email, "send_email", fake_send)
    monkeypatch.setattr(email, "is_configured", lambda: True)
    return sent


def _seq(*steps, enabled=True):
    return {"enabled": enabled, "steps": [{"delay": d, "subject": s, "body": b} for d, s, b in steps]}


async def _jobs(user_id):
    async with async_session() as db:
        return (await db.execute(select(EmailJob).where(EmailJob.user_id == user_id).order_by(EmailJob.step))).scalars().all()


async def _all_due(user_id):
    async with async_session() as db:
        for j in (await db.execute(select(EmailJob).where(EmailJob.user_id == user_id))).scalars().all():
            j.send_at = datetime.utcnow() - timedelta(seconds=1)
        await db.commit()


async def _drain():
    while events._background:
        await asyncio.sleep(0.01)


def test_sequence_validation(client, make_user):
    u = make_user()
    put = lambda autos: client.put("/api/integrations", json={**BASE, "automations": autos}, headers=u.h())
    assert put({"chat_lead": _seq(("1d", "A", "a"), ("1d", "B", "b"))}).status_code == 400  # not later than the one before
    assert put({"chat_lead": _seq(*[(d, "S", "b") for d in ("now", "1d", "3d", "7d")])}).status_code == 400  # four emails
    assert put({"chat_lead": _seq(("now", "A", "a"), ("2d", "", "b"))}).status_code == 400  # empty follow-up
    r = put({"chat_lead": _seq(("now", "A", "a"), ("2d", "B", "b"))})
    assert r.status_code == 200 and [s["delay"] for s in r.json()["automations"]["chat_lead"]["steps"]] == ["now", "2d"]
    # Older dashboards send one email; it's stored as a one-step sequence.
    r = put({"call_lead": {"enabled": True, "delay": "1h", "subject": "S", "body": "B"}})
    assert r.json()["automations"]["call_lead"]["steps"] == [{"delay": "1h", "subject": "S", "body": "B"}]


def test_follow_ups_go_out_and_stop_when_a_later_call_reaches_its_goal(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {"chat_lead": _seq(
        ("now", "Thanks {{name}}", "Hi"), ("1d", "Still looking?", "Follow-up"), ("3d", "Last note", "Bye"))}}, headers=u.h())
    sent = _capture(monkeypatch)

    async def scenario():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s1", captured_data={"Name": "Priya", "Email": "priya@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        await automations.process_due()
        first = [m["subject"] for m in sent]
        async with async_session() as db:  # later she books on a call
            db.add(CallLog(user_id=u.id, bot_id=bot, channel="phone", caller_e164="+919800000001", outcome="lead_captured",
                           successful=True, captured={"Email": "Priya@Example.com"}, started_at=datetime.utcnow() + timedelta(seconds=5)))
            await db.commit()
        await _all_due(u.id)
        await automations.process_due()
        return first, await _jobs(u.id)
    first, jobs = run(scenario)
    assert first == ["Thanks Priya"] and [m["subject"] for m in sent] == ["Thanks Priya"]
    assert [(j.step, j.status) for j in jobs] == [(1, "sent"), (2, "cancelled"), (3, "cancelled")]
    assert "goal" in jobs[1].error and jobs[0].sent_at is not None


def test_goal_met_replaces_call_email_and_fills_details(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {
        "call_lead": _seq(("now", "Call", "x")),
        "goal_met": _seq(("now", "Booked for {{visit_date}}", "{{details}}"))}}, headers=u.h())
    sent = _capture(monkeypatch)

    async def call(successful):
        async with async_session() as db:
            c = CallLog(user_id=u.id, bot_id=bot, channel="phone", caller_e164="+919800000002", outcome="lead_captured",
                        successful=successful, captured={"Email": f"r{int(successful)}@example.com", "Visit date": "Sunday 10 AM"})
            db.add(c)
            await db.commit()
        await events.call_completed(c.id)
        await automations.process_due()
    run(call, True)
    run(call, False)
    assert [(m["to"], m["subject"]) for m in sent] == [("r1@example.com", "Booked for Sunday 10 AM"), ("r0@example.com", "Call")]
    assert "Visit date: Sunday 10 AM" in sent[0]["text"]


def test_missed_call_email_after_last_attempt(client, make_user, monkeypatch, run):
    from voice import router as voice_router
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {"call_missed": _seq(("now", "We tried {{phone}}", "Hi {{name}}"))}},
               headers=u.h())
    sent = _capture(monkeypatch)

    async def scenario():
        async with async_session() as db:
            job = CallbackJob(user_id=u.id, bot_id=bot, e164="+919800000003", name="Kiran", consent_source="Campaign list",
                              status="calling", attempts=3, provider_call_id="CAmiss", variables={"email": "kiran@example.com"})
            db.add(job)
            await db.commit()
            await voice_router._log_unanswered(db, "CAmiss", None, "no-answer", "Twilio")
        await _drain()
        await automations.process_due()
    run(scenario)
    assert [(m["to"], m["subject"]) for m in sent] == [("kiran@example.com", "We tried +91 98000 00003")]
    assert sent[0]["text"].startswith("Hi Kiran")


def test_email_after_team_closes_live_chat(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {"handoff_done": _seq(("now", "Thanks {{name}}", "Bye"))}},
               headers=u.h())
    sent = _capture(monkeypatch)

    async def make():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s2", handoff_status="human",
                                captured_data={"Name": "Asha", "Email": "asha@example.com"})
            db.add(conv)
            await db.commit()
            return conv.conversation_id
    cid = run(make)
    assert client.post(f"/api/handoffs/{cid}/close", headers=u.h()).status_code == 200
    run(_drain)
    run(automations.process_due)
    assert [m["subject"] for m in sent] == ["Thanks Asha"]


def test_history_cancel_resend_and_stop(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {"chat_lead": _seq(("now", "One", "a"), ("1d", "Two", "b"))}},
               headers=u.h())
    sent = _capture(monkeypatch)

    async def lead(addr, session):
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=session, captured_data={"Email": addr})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
    run(lead, "a@example.com", "h1")
    run(lead, "b@example.com", "h2")

    h = client.get("/api/integrations/email/history", headers=u.h()).json()
    assert h["counts"]["queued"] == 4 and h["total"] == 4 and h["items"][0]["label"] == "After a chat"
    second_a = next(i for i in h["items"] if i["to"] == "a@example.com" and i["step"] == 2)
    assert client.post(f"/api/integrations/email/jobs/{second_a['id']}/cancel", headers=u.h()).json()["status"] == "cancelled"
    assert client.post(f"/api/integrations/email/jobs/{second_a['id']}/cancel", headers=u.h()).status_code == 409

    # Resend: delivered again even though the first attempt was logged.
    resent = client.post(f"/api/integrations/email/jobs/{second_a['id']}/resend", headers=u.h())
    assert resent.status_code == 200 and resent.json()["status"] == "queued"
    run(automations.process_due)
    assert sorted(m["subject"] for m in sent) == ["One", "One", "Two"]

    # Stop b: their queued follow-up is cancelled, and nothing new is queued for them.
    assert client.post("/api/integrations/email/stop", json={"email": "B@example.com"}, headers=u.h()).json() == {"cancelled": 1}
    run(lead, "b@example.com", "h3")
    detail = client.get(f"/api/integrations/email/jobs/{h['items'][0]['id']}", headers=u.h()).json()
    assert "body" in detail
    failed = client.get("/api/integrations/email/history?status=cancelled", headers=u.h()).json()
    assert failed["total"] == 1 and failed["items"][0]["to"] == "b@example.com"
    other = make_user()
    assert client.post(f"/api/integrations/email/jobs/{second_a['id']}/cancel", headers=other.h()).status_code == 404


def test_bulk_email_audience_and_send(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    sent = _capture(monkeypatch)

    async def seed():
        async with async_session() as db:
            db.add_all([
                Conversation(bot_id=bot, visitor_session_id="b1", captured_data={"Name": "Meera Iyer", "Email": "meera@example.com"}),
                Conversation(bot_id=bot, visitor_session_id="b2", captured_data={"Email": "MEERA@example.com"}),  # same person
                Conversation(bot_id=bot, visitor_session_id="b3", captured_data={"Name": "No email"}),
                CallLog(user_id=u.id, bot_id=bot, channel="phone", caller_e164="+919800000004", captured={"Email": "dev@example.com"}),
                CallLog(user_id=u.id, bot_id=bot, channel="browser", captured={"Email": "test@example.com"}),  # test call
            ])
            await db.commit()
    run(seed)
    client.post("/api/integrations/email/stop", json={"email": "dev@example.com"}, headers=u.h())

    aud = client.post("/api/integrations/email/audience", json={"source": "all", "days": 30}, headers=u.h()).json()
    assert aud["count"] == 1 and aud["unsubscribed"] == 1 and aud["sample"][0]["email"].lower() == "meera@example.com"
    assert client.post("/api/integrations/email/audience", json={"source": "calls"}, headers=u.h()).json()["count"] == 0

    msg = {"source": "all", "days": 30, "subject": "Open house, {{name}}", "body": "Hi {{name}}, see you Sunday.\n\n{{business}}"}
    assert client.post("/api/integrations/email/broadcasts", json=msg, headers=u.h()).status_code == 400  # no consent
    client.put("/api/integrations", json={**BASE, "reply_to": ""}, headers=u.h())
    assert client.post("/api/integrations/email/broadcasts", json={**msg, "consent": True}, headers=u.h()).status_code == 400  # no reply-to
    client.put("/api/integrations", json=BASE, headers=u.h())
    r = client.post("/api/integrations/email/broadcasts", json={**msg, "consent": True}, headers=u.h())
    assert r.status_code == 200 and r.json()["recipients"] == 1, r.text
    run(automations.process_due)
    assert [(m["subject"], m["text"].split("\n")[0]) for m in sent] == [("Open house, Meera", "Hi Meera, see you Sunday.")]

    listed = client.get("/api/integrations/email/broadcasts", headers=u.h()).json()
    assert listed[0]["counts"]["sent"] == 1 and listed[0]["recipients"] == 1
    hist = client.get("/api/integrations/email/history?automation=broadcast", headers=u.h()).json()
    assert hist["total"] == 1 and hist["items"][0]["label"] == "Bulk email"


def test_one_click_unsubscribe_header_and_post(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "automations": {"chat_lead": _seq(("now", "Hi", "Thanks"), ("2d", "Again", "x"))}},
               headers=u.h())
    sent = _capture(monkeypatch)

    async def lead():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="u1", captured_data={"Email": "neha@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        await automations.process_due()
    run(lead)
    link = sent[0]["unsubscribe"]
    assert link and "/api/integrations/email/unsubscribe?token=" in link
    # The mail app posts to the same link; the queued follow-up is cancelled.
    assert client.post(link[link.index("/api/"):]).json() == {"status": "unsubscribed"}
    assert [j.status for j in run(_jobs, u.id)] == ["sent", "cancelled"]
    assert client.post("/api/integrations/email/unsubscribe?token=bogus").status_code == 400
