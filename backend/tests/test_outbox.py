"""Email events for the business's own systems: its webhook and LeadSquared (mail plan, phase 6)."""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import EmailJob, EmailLink, EmailThread, IntegrationEvent, IntegrationSettings, NotificationLog, ThreadMessage
from database import async_session
from mail import clicks, outbox
from notify import automations, channels, email


@pytest.fixture(autouse=True)
def _quiet(run, monkeypatch):
    monkeypatch.setattr(email, "is_configured", lambda: True)
    async def clear():
        async with async_session() as db:
            await db.execute(update(IntegrationEvent).where(IntegrationEvent.status == "new").values(status="failed"))
            await db.execute(update(EmailJob).where(EmailJob.status == "queued").values(status="cancelled"))
            await db.commit()
    run(clear)
    yield
    run(clear)


@pytest.fixture
def posted(monkeypatch):
    out = []
    async def webhook(url, secret, event, data):
        out.append(("webhook", event, data))
    async def lsq(host, access_key, secret_key, address, activity, note, at=None):
        out.append(("leadsquared", activity, {"email": address, "note": note, "at": at}))
    monkeypatch.setattr(channels, "post_webhook", webhook)
    monkeypatch.setattr(channels, "post_leadsquared_activity", lsq)
    return out


def _workspace(run, user, *, webhook=True, leadsquared=False):
    async def go():
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=user.id, reply_to="team@example.com", webhook_url="https://hooks.example.com/nimmi" if webhook else None,
                                       webhook_secret="s3cret", leadsquared_enabled=leadsquared, leadsquared_host="api-in21.leadsquared.com",
                                       leadsquared_access_key="ak", leadsquared_secret_key="sk", leadsquared_activity=211 if leadsquared else None))
            await db.commit()
    run(go)


def _events(run, user):
    async def go():
        async with async_session() as db:
            return (await db.execute(select(IntegrationEvent).where(IntegrationEvent.user_id == user.id).order_by(IntegrationEvent.created_at))).scalars().all()
    return run(go)


def _drain(run):
    return run(outbox.drain, datetime.utcnow() + timedelta(seconds=1))


def _send_one(run, user, bot, monkeypatch, to="asha@example.com"):
    async def deliver(*a, **k):
        return SimpleNamespace(ok=True, id=uuid.uuid4().hex, error=None)
    monkeypatch.setattr(email, "deliver", deliver)
    async def go():
        async with async_session() as db:
            job = EmailJob(user_id=user.id, bot_id=bot, kind=f"broadcast:x#{uuid.uuid4().hex[:6]}", ref_id=uuid.uuid4().hex, to_email=to, automation="broadcast",
                           broadcast_id=None, step=1, subject="Diwali offer", body="Hi", send_at=datetime.utcnow() - timedelta(minutes=1))
            job.automation = "rsvp_reminder"  # goes without an automation switch
            db.add(job)
            await db.commit()
            return job.id
    job_id = run(go)
    run(automations.process_due)
    return job_id


def test_sending_an_email_tells_the_webhook(make_user, run, posted, monkeypatch):
    user = make_user()
    bot = user.bot()
    _workspace(run, user)
    job_id = _send_one(run, user, bot, monkeypatch)
    assert [e.event for e in _events(run, user)] == ["email.sent"]
    _drain(run)
    assert posted[0][:2] == ("webhook", "email.sent") and posted[0][2]["email_id"] == job_id and posted[0][2]["to"] == "asha@example.com"


def test_nothing_is_kept_without_somewhere_to_send_it(make_user, run, posted, monkeypatch):
    user = make_user()
    _workspace(run, user, webhook=False)
    _send_one(run, user, user.bot(), monkeypatch)
    assert _events(run, user) == []


def test_events_need_the_plan_with_integrations(make_user, run, posted, monkeypatch):
    import plans
    real = plans.workspace_includes
    async def starter(db, owner_id):
        included = await real(db, owner_id)
        return SimpleNamespace(**{**included.__dict__, "integrations": False})
    monkeypatch.setattr(plans, "workspace_includes", starter)
    user = make_user()
    _workspace(run, user)
    _send_one(run, user, user.bot(), monkeypatch)
    assert _events(run, user) == []


def test_a_reply_a_click_a_bounce_and_an_unsubscribe_are_events(make_user, client, run, posted, monkeypatch):
    from mail import inbound
    user = make_user()
    bot = user.bot()
    _workspace(run, user, leadsquared=True)
    job_id = _send_one(run, user, bot, monkeypatch)
    async def reply():
        async with async_session() as db:
            thread = EmailThread(user_id=user.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="asha@example.com")
            db.add(thread)
            await db.flush()
            row = ThreadMessage(thread_id=thread.id, user_id=user.id, direction="in", who="customer", status="working", sender="asha@example.com", subject="Re: Diwali offer",
                                text="Is parking included?")
            db.add(row)
            await db.flush()
            await inbound._their_reply(db, row, thread)
            await db.commit()
    run(reply)
    async def click():
        async with async_session() as db:
            link = EmailLink(token=uuid.uuid4().hex[:22], user_id=user.id, job_id=job_id, kind="link", target="https://x.in/offer", label="The offer", clicks=0)
            db.add(link)
            await db.flush()
            for minutes in (30, 20):  # twice: one event
                clicks.record(db, link, "2001:db8::77", "Mozilla/5.0 Chrome/124.0", True, now=datetime.utcnow() - timedelta(minutes=minutes))
            await db.commit()
        await clicks.settle_due(datetime.utcnow() + timedelta(minutes=1))
    run(click)
    run(automations.unsubscribe, user.id, "asha@example.com", "marketing", bot)
    kinds = [(e.target, e.event) for e in _events(run, user)]
    assert ("webhook", "email.replied") in kinds and ("webhook", "email.clicked") in kinds and ("webhook", "email.unsubscribed") in kinds
    assert kinds.count(("webhook", "email.clicked")) == 1, "a link's first click"
    assert ("leadsquared", "email.sent") not in kinds and ("leadsquared", "email.replied") in kinds, "LeadSquared gets everything but sent"
    _drain(run)
    lsq = [p for p in posted if p[0] == "leadsquared"]
    assert lsq and all(p[1] == 211 and p[2]["email"] == "asha@example.com" for p in lsq)
    assert any("Replied to an email" in p[2]["note"] and "Is parking included?" in p[2]["note"] for p in lsq)


def test_a_bounce_and_a_spam_report_from_resend_are_events(make_user, client, run, posted, monkeypatch):
    import hashlib, hmac, base64, time
    from mail import webhooks
    user = make_user()
    bot = user.bot()
    _workspace(run, user)
    job_id = _send_one(run, user, bot, monkeypatch, to="gone@example.com")
    secret = "whsec_" + base64.b64encode(b"x" * 24).decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    def post(kind, data):
        body = json.dumps({"type": kind, "created_at": "2026-11-01T10:00:00Z", "data": {"email_id": "r1", "to": ["gone@example.com"], **data,
                                                                                       "tags": {"ws": user.id, "job": job_id, "kind": "customer"}}})
        msg_id, ts = f"msg_{uuid.uuid4().hex[:16]}", str(int(time.time()))
        sig = base64.b64encode(hmac.new(base64.b64decode(secret.split("_", 1)[1]), f"{msg_id}.{ts}.{body}".encode(), hashlib.sha256).digest()).decode()
        return client.post("/api/email/webhooks/resend", content=body, headers={"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"})
    assert post("email.bounced", {"bounce": {"type": "Permanent", "message": "No such user"}}).status_code == 200
    assert post("email.complained", {}).status_code == 200
    kinds = [e.event for e in _events(run, user)]
    assert "email.bounced" in kinds and "email.unsubscribed" in kinds


def test_a_failed_delivery_is_tried_again_then_shown_in_activity(make_user, run, monkeypatch):
    user = make_user()
    _workspace(run, user)
    tries = []
    async def down(url, secret, event, data):
        tries.append(event)
        raise channels.ChannelError("Webhook returned 500")
    monkeypatch.setattr(channels, "post_webhook", down)
    run(outbox.emit_now, user.id, "email.sent", {"to": "a@example.com"})
    clock = datetime.utcnow()
    for n in range(outbox.TRIES):
        run(outbox.drain, clock + timedelta(days=1 + n))
    ev = _events(run, user)[0]
    assert len(tries) == outbox.TRIES and ev.status == "failed" and ev.error == "Webhook returned 500"
    async def log():
        async with async_session() as db:
            return (await db.execute(select(NotificationLog).where(NotificationLog.user_id == user.id))).scalars().all()
    assert [(r.kind, r.status) for r in run(log)] == [("email_sent_webhook", "failed")]
    run(outbox.drain, clock + timedelta(days=30))
    assert len(tries) == outbox.TRIES, "a failed event stays failed"


def test_a_retry_waits_its_turn(make_user, run, monkeypatch):
    user = make_user()
    _workspace(run, user)
    calls = []
    async def flaky(url, secret, event, data):
        calls.append(event)
        if len(calls) == 1:
            raise channels.ChannelError("timeout")
    monkeypatch.setattr(channels, "post_webhook", flaky)
    run(outbox.emit_now, user.id, "email.sent", {"to": "a@example.com"})
    now = datetime.utcnow()
    run(outbox.drain, now + timedelta(seconds=1))
    run(outbox.drain, now + timedelta(seconds=30))
    assert len(calls) == 1, "not before a minute"
    run(outbox.drain, now + timedelta(minutes=2))
    assert len(calls) == 2 and _events(run, user)[0].status == "sent"


def test_two_processes_deliver_each_event_once(make_user, run, posted):
    user = make_user()
    _workspace(run, user)
    for n in range(10):
        run(outbox.emit_now, user.id, "email.sent", {"to": f"p{n}@example.com"})
    async def both():
        await asyncio.gather(*(outbox.drain(datetime.utcnow() + timedelta(seconds=1)) for _ in range(3)))
    run(both)
    assert sorted(p[2]["to"] for p in posted) == sorted(f"p{n}@example.com" for n in range(10))


def test_leadsquared_gets_the_activity_it_documents(monkeypatch, run):
    seen = {}
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            seen.update(url=url, headers=headers, json=json)
            return SimpleNamespace(status_code=200, text='{"Status":"Success"}', json=lambda: {"Status": "Success", "Message": {"Id": "x"}})
    monkeypatch.setattr(channels, "safe_client", lambda timeout=15: Client())
    run(channels.post_leadsquared_activity, "api-in21.leadsquared.com", "ak", "sk", "asha@example.com", 211, "Replied to an email", "2026-11-03T06:30:05.123456")
    assert seen["url"] == "https://api-in21.leadsquared.com/v2/ProspectActivity.svc/Create"
    assert seen["headers"] == {"x-LSQ-AccessKey": "ak", "x-LSQ-SecretKey": "sk"}
    assert seen["json"] == {"EmailAddress": "asha@example.com", "ActivityEvent": 211, "ActivityNote": "Replied to an email", "ActivityDateTime": "2026-11-03 06:30:05"}


def test_the_integrations_page_keeps_the_activity_code(client, make_user):
    user = make_user()
    s = client.get("/api/integrations", headers=user.h()).json()
    body = {k: s[k] for k in ("email_alerts", "alert_email", "whatsapp_enabled", "whatsapp_template", "whatsapp_language", "webhook_url", "leadsquared_enabled",
                              "leadsquared_host", "leadsquared_access_key", "alert_calls", "alert_handoffs", "alert_daily", "sender_name", "reply_to") if k in s}
    r = client.put("/api/integrations", json={**body, "leadsquared_activity": 211, "alert_engaged": False}, headers=user.h())
    assert r.status_code == 200, r.text
    again = client.get("/api/integrations", headers=user.h()).json()
    assert again["leadsquared_activity"] == 211 and again["alert_engaged"] is False
