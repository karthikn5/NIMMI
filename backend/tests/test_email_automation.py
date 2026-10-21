"""Email automation: team alert recipients, customer follow-ups with delay, unsubscribe, and handoff alerts."""
from datetime import datetime, timedelta

from sqlalchemy.future import select

from database import async_session
from backend.models import CallLog, Conversation, EmailJob, NotificationLog
from notify import automations, email, events

BASE = {
    "email_alerts": True, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "",
}


def _capture(monkeypatch):
    sent = []

    async def fake_send(to, subject, text, html_body=None, reply_to=None, from_name=None, unsubscribe_url=None, **_):
        sent.append({"to": to, "subject": subject, "text": text, "html": html_body, "reply_to": reply_to, "from": from_name})
        return True
    monkeypatch.setattr(email, "send_email", fake_send)
    return sent


def test_settings_validate_and_round_trip(client, make_user):
    u = make_user()
    bad = client.put("/api/integrations", json={**BASE, "alert_email": "a@x.com, not-an-email"}, headers=u.h())
    assert bad.status_code == 400 and "not-an-email" in bad.json()["detail"]
    on_without_reply = {**BASE, "automations": {"chat_lead": {"enabled": True, "delay": "now", "subject": "Hi", "body": "Thanks"}}}
    assert client.put("/api/integrations", json=on_without_reply, headers=u.h()).status_code == 400

    body = {**BASE, "alert_email": "sales@acme.in; owner@acme.in", "alert_calls": False, "alert_handoffs": True,
            "sender_name": "Acme Realty", "reply_to": "hello@acme.in",
            "automations": {"call_lead": {"enabled": True, "delay": "1h", "subject": "Thanks {{name}}", "body": "Summary: {{summary}}"}}}
    r = client.put("/api/integrations", json=body, headers=u.h())
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["alert_email"] == "sales@acme.in, owner@acme.in" and s["alert_calls"] is False and s["alert_handoffs"] is True
    assert s["automations"]["call_lead"]["steps"][0]["delay"] == "1h" and s["automations"]["chat_lead"]["enabled"] is False
    assert s["automations"]["chat_lead"]["steps"][0]["subject"]  # defaults fill in what wasn't saved
    assert "summary" in s["placeholders"]


def test_chat_lead_alerts_team_and_emails_customer(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot("Acme")
    client.put("/api/integrations", json={**BASE, "alert_email": "sales@acme.in, owner@acme.in", "sender_name": "Acme Realty",
                                          "reply_to": "hello@acme.in",
                                          "automations": {"chat_lead": {"enabled": True, "delay": "now", "subject": "Thanks {{name}}",
                                                                        "body": "Hi {{name}},\n\nWe'll call {{phone}} soon.\n\n{{business}}"}}},
               headers=u.h())
    sent = _capture(monkeypatch)

    async def scenario():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s1",
                                captured_data={"Name": "Priya", "Email": "priya@example.com", "Phone": "9876543210"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        await events.lead_captured(conv.conversation_id)  # triggers twice: still one alert, one customer email
        await automations.process_due()
        await automations.process_due()
        return conv.conversation_id
    run(scenario)

    team = [m for m in sent if m["subject"].startswith("New lead")]
    assert sorted(m["to"] for m in team) == ["owner@acme.in", "sales@acme.in"]
    customer = [m for m in sent if m["to"] == "priya@example.com"]
    assert len(customer) == 1
    c = customer[0]
    assert c["subject"] == "Thanks Priya" and "We'll call +91 98765 43210 soon." in c["text"]
    assert c["reply_to"] == "hello@acme.in" and c["from"] == "Acme Realty" and "Unsubscribe" in c["html"]


def test_call_follow_up_waits_for_its_delay_and_honours_unsubscribe(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "reply_to": "hello@acme.in", "alert_calls": False,
                                          "automations": {"call_lead": {"enabled": True, "delay": "1h", "subject": "Your call",
                                                                        "body": "{{summary}}"}}}, headers=u.h())
    sent = _capture(monkeypatch)

    async def call(email_addr):
        async with async_session() as db:
            c = CallLog(user_id=u.id, bot_id=bot, channel="phone", caller_e164="+919800000001", outcome="answered",
                        captured={"Email": email_addr}, summary="Asked about fees.")
            db.add(c)
            await db.commit()
        await events.call_completed(c.id)
        return c.id

    async def scenario():
        await call("ravi@example.com")
        await automations.process_due()
        not_yet = len(sent)
        async with async_session() as db:  # an hour passes
            for job in (await db.execute(select(EmailJob))).scalars().all():
                job.send_at = datetime.utcnow() - timedelta(seconds=1)
            await db.commit()
        await automations.process_due()
        return not_yet
    assert run(scenario) == 0  # nothing before the delay, and no team email (call alerts off)
    assert [m["subject"] for m in sent] == ["Your call"] and sent[0]["text"].startswith("Asked about fees.")

    # The unsubscribe link in that email works, and stops later emails.
    link = sent[0]["text"].split("Unsubscribe: ")[1].strip()
    page = client.get(link[link.index("/api/"):])
    assert page.status_code == 200 and "unsubscribed" in page.text
    run(call, "Ravi@Example.com")

    async def jobs():
        async with async_session() as db:
            return (await db.execute(select(EmailJob).where(EmailJob.user_id == u.id))).scalars().all()
    assert len(run(jobs)) == 1  # the second call didn't queue anything
    assert client.get("/api/integrations/email/unsubscribe?token=bogus").status_code == 400


def test_handoff_alert_only_when_on(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    sent = _capture(monkeypatch)

    async def ask(session):
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=session, captured_data={"Name": "Asha"})
            db.add(conv)
            await db.commit()
        await events.handoff_requested(conv.conversation_id, "Can I speak to someone?")
    run(ask, "wa:919800000005")
    assert sent == []  # off by default
    client.put("/api/integrations", json={**BASE, "alert_handoffs": True, "alert_email": "desk@acme.in"}, headers=u.h())
    run(ask, "wa:919800000006")
    assert len(sent) == 1 and sent[0]["to"] == "desk@acme.in"
    assert "Asha asked for a person in WhatsApp" in sent[0]["text"]


def test_test_send_uses_sample_data(client, make_user, monkeypatch):
    u = make_user()
    client.put("/api/integrations", json={**BASE, "sender_name": "Acme Realty", "reply_to": "hello@acme.in"}, headers=u.h())
    sent = _capture(monkeypatch)
    r = client.post("/api/integrations/test", json={"channel": "email_automation", "automation": "call_lead"}, headers=u.h())
    assert r.status_code == 200, r.text
    assert sent[0]["subject"] == "[Test] Following up on your call with Acme Realty" and "Priya" in sent[0]["text"]


def test_delivery_log_records_customer_emails(run, make_user, client, monkeypatch):
    u = make_user()
    bot = u.bot()
    client.put("/api/integrations", json={**BASE, "reply_to": "hello@acme.in",
                                          "automations": {"chat_lead": {"enabled": True, "delay": "now", "subject": "Hi", "body": "Thanks"}}},
               headers=u.h())
    _capture(monkeypatch)

    async def scenario():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s9", captured_data={"Email": "k@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        await automations.process_due()
        async with async_session() as db:
            return [r.kind for r in (await db.execute(select(NotificationLog).where(NotificationLog.user_id == u.id))).scalars().all()]
    assert "auto_chat_lead" in run(scenario)
