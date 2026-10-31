"""
Email, phase 0 (mail_plan.md): Resend's signed reports (bounces stop an address everywhere, spam reports stop it for
that business), the unsubscribe page that asks first, text filled in when an email is sent, idempotency keys, address
checks, the business's own sending domain, senders per assistant, chat leads as contacts, meeting emails' Reply-To,
the bulk email safeguards, and the contacts table taking a lead without a phone number.
"""
import base64
import hashlib
import hmac
import html
import json
import sqlite3
import time
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy.future import select

from database import async_session
from backend.models import (Contact, Conversation, EmailBounce, EmailDomain, EmailEvent, EmailJob, EmailSender,
                            EmailUnsubscribe, IntegrationSettings, Meeting, VoiceAgent)
from mail import address, contacts, domains, senders, suppress
from notify import automations, email, events

SECRET = "whsec_" + base64.b64encode(b"nimmi-test-signing-key-32-bytes!").decode()
BASE = {
    "email_alerts": True, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "",
}


def _signed(body: bytes, event_id: str, ts=None, secret=SECRET) -> dict:
    ts = str(int(ts if ts is not None else time.time()))
    key = base64.b64decode(secret[len("whsec_"):])
    sig = base64.b64encode(hmac.new(key, f"{event_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": event_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}


def _event(client, kind: str, data: dict, event_id=None):
    body = json.dumps({"type": kind, "created_at": "2026-11-01T10:00:00Z", "data": data}).encode()
    return client.post("/api/email/webhooks/resend", content=body, headers=_signed(body, event_id or f"msg_{time.time_ns()}"))


def _capture(monkeypatch):
    sent = []

    async def fake_deliver(to, subject, text, html_body=None, **more):
        sent.append({"to": to, "subject": subject, "text": text, **more})
        return email.Delivery(True, id=f"re_{len(sent)}")
    monkeypatch.setattr(email, "deliver", fake_deliver)
    return sent


def _job(run, owner, to, **kw):
    async def add():
        async with async_session() as db:
            job = EmailJob(user_id=owner, kind=kw.pop("kind", f"chat_lead#{time.time_ns()}"), ref_id=kw.pop("ref_id", str(time.time_ns())),
                           to_email=to, subject="Hello", body="Hi", send_at=datetime.utcnow(), **kw)
            db.add(job)
            await db.commit()
            return job.id
    return run(add)


def _get(run, model, key):
    async def get():
        async with async_session() as db:
            return await db.get(model, key)
    return run(get)


def _rows(run, model, *where):
    async def rows():
        async with async_session() as db:
            return (await db.execute(select(model).where(*where))).scalars().all()
    return run(rows)


# ─── Resend's reports ────────────────────────────────────────────

def test_the_webhook_needs_a_valid_signature_and_keeps_each_event_once(client, make_user, run, monkeypatch):
    u = make_user()
    job = _job(run, u.id, "asha@example.com", status="sent", provider_id="re_abc")
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "re_abc", "to": ["asha@example.com"]}}).encode()
    assert client.post("/api/email/webhooks/resend", content=body, headers=_signed(body, "msg_1")).status_code == 503  # no secret set

    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    forged = _signed(body, "msg_1", secret="whsec_" + base64.b64encode(b"someone-else-entirely-32-bytes!!").decode())
    assert client.post("/api/email/webhooks/resend", content=body, headers=forged).status_code == 401
    assert client.post("/api/email/webhooks/resend", content=body, headers=_signed(body, "msg_1", ts=time.time() - 3600)).status_code == 401
    changed = body.replace(b"delivered", b"complained")
    assert client.post("/api/email/webhooks/resend", content=changed, headers=_signed(body, "msg_1")).status_code == 401

    for _ in range(2):  # Resend retries with the same svix-id
        assert client.post("/api/email/webhooks/resend", content=body, headers=_signed(body, "msg_1")).status_code == 200
    assert len(_rows(run, EmailEvent, EmailEvent.event_id == "msg_1")) == 1
    j = _get(run, EmailJob, job)
    assert j.event == "delivered" and j.delivered_at is not None


def test_a_hard_bounce_stops_the_address_for_everyone_and_a_spam_report_for_that_business(client, make_user, run, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    a, b = make_user(), make_user()
    sent_a = _job(run, a.id, "Ghost@Example.com", status="sent", provider_id="re_ghost")
    waiting_a = _job(run, a.id, "ghost@example.com", status="queued")
    waiting_b = _job(run, b.id, "ghost@example.com", status="queued")

    # A temporary bounce is only shown.
    _event(client, "email.bounced", {"email_id": "re_ghost", "to": ["ghost@example.com"], "tags": {"ws": a.id, "job": sent_a, "kind": "customer"},
                                     "bounce": {"type": "Transient", "subType": "MailboxFull", "message": "Mailbox full"}})
    assert _get(run, EmailBounce, "ghost@example.com") is None and _get(run, EmailJob, waiting_b).status == "queued"

    _event(client, "email.bounced", {"email_id": "re_ghost", "to": ["ghost@example.com"], "tags": {"ws": a.id, "job": sent_a, "kind": "customer"},
                                     "bounce": {"type": "Permanent", "subType": "General", "message": "550 5.1.1 Unknown user"}})
    j = _get(run, EmailJob, sent_a)
    assert j.event == "bounced" and "Unknown user" in j.event_detail and j.bounced_at
    assert _get(run, EmailBounce, "ghost@example.com").kind == "bounce"
    for job_id in (waiting_a, waiting_b):  # dead for everyone
        w = _get(run, EmailJob, job_id)
        assert w.status == "cancelled" and "bounced" in w.error

    async def blocked(owner, addr):
        async with async_session() as db:
            return await suppress.why_blocked(db, owner, addr)
    assert "bounced" in run(blocked, b.id, "GHOST@example.com")

    # A spam report: that business never emails them again; another business still can.
    sent_b = _job(run, b.id, "priya@example.com", status="sent", provider_id="re_priya")
    _event(client, "email.complained", {"email_id": "re_priya", "to": ["priya@example.com"], "tags": {"ws": b.id, "job": sent_b, "kind": "customer"}})
    assert _get(run, EmailJob, sent_b).complained_at is not None
    assert "spam" in run(blocked, b.id, "priya@example.com") and run(blocked, a.id, "priya@example.com") is None
    # The team's own alert reported as spam doesn't stop customer emails to that address.
    _event(client, "email.complained", {"email_id": "re_alert", "to": ["owner@example.com"], "tags": {"ws": a.id, "kind": "alert"}})
    assert run(blocked, a.id, "owner@example.com") is None


def test_failed_and_suppressed_emails_say_why_in_history(client, make_user, run, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    u = make_user()
    quota = _job(run, u.id, "a@example.com", status="sent", provider_id="re_q")
    blocked = _job(run, u.id, "b@example.com", status="sent", provider_id="re_s")
    _event(client, "email.failed", {"email_id": "re_q", "to": ["a@example.com"], "failed": {"reason": "reached_daily_quota"}})
    _event(client, "email.suppressed", {"email_id": "re_s", "to": ["b@example.com"],
                                        "suppressed": {"type": "OnAccountSuppressionList", "message": "On the list"}})
    _event(client, "email.opened", {"email_id": "re_q"})
    rows = {r["id"]: r for r in client.get("/api/integrations/email/history", headers=u.h()).json()["items"]}
    assert rows[quota]["status"] == "failed" and "for the day" in rows[quota]["error"] and rows[quota]["opened_at"]
    assert rows[blocked]["status"] == "failed" and rows[blocked]["event"] == "suppressed"
    assert _get(run, EmailBounce, "b@example.com").kind == "suppressed"
    detail = client.get(f"/api/integrations/email/jobs/{blocked}", headers=u.h()).json()
    assert detail["unsubscribed"] and "Resend won't send" in detail["stopped_because"]


# ─── the unsubscribe link ────────────────────────────────────────

def test_the_unsubscribe_link_asks_first_and_offers_offers_only_and_resubscribing(client, make_user, run):
    u = make_user()
    bot = u.bot("Sunrise Homes")
    link = automations.unsubscribe_url(u.id, "Ravi@Example.com", bot)
    path = link[link.index("/api/"):]

    async def why(marketing=False):
        async with async_session() as db:
            return await suppress.why_blocked(db, u.id, "ravi@example.com", marketing=marketing)

    page = client.get(path)  # a scanner or a person opening it: nothing changes
    assert page.status_code == 200 and "Stop emails from Sunrise Homes?" in page.text and run(why) is None
    assert "form-action 'self'" in page.headers["content-security-policy"]  # the buttons may post back

    marketing = client.post(path, data={"action": "marketing"})
    assert marketing.status_code == 200 and "Offers and news stopped" in marketing.text
    assert run(why) is None and run(why, True) == suppress.TEXT["marketing"]  # enquiry emails still go, bulk doesn't

    gone = client.post(path, data={"action": "all"})
    assert "You're unsubscribed" in html.unescape(gone.text) and run(why) == suppress.TEXT["unsubscribed"]
    again = client.get(path)
    assert "You're unsubscribed" in html.unescape(again.text) and "Resubscribe" in again.text

    back = client.post(path, data={"action": "resubscribe"})
    assert "subscribed again" in html.unescape(back.text) and run(why) is None

    one_click = client.post(path, content=b"List-Unsubscribe=One-Click", headers={"content-type": "application/x-www-form-urlencoded"})
    assert one_click.json() == {"status": "unsubscribed"} and run(why) is not None
    assert client.post("/api/integrations/email/unsubscribe?token=bogus", data={"action": "all"}).status_code == 400

    # A spam report can't be undone from the page.
    async def report():
        async with async_session() as db:
            await suppress.add(db, u.id, "ravi@example.com", "complaint")
            await db.commit()
    run(report)
    assert "can't be changed here" in html.unescape(client.post(path, data={"action": "resubscribe"}).text)


# ─── sending ─────────────────────────────────────────────────────

def test_text_is_filled_in_when_sent_with_the_assistants_sender_and_an_idempotency_key(client, make_user, run, monkeypatch):
    u = make_user()
    bot = u.bot("Desk")
    client.put("/api/integrations", json={**BASE, "sender_name": "Workspace Name", "reply_to": "hello@acme.in",
                                          "automations": {"chat_lead": {"enabled": True, "delay": "now", "subject": "Thanks {{name}}",
                                                                        "body": "Hi {{name}}, about {{budget}}.\n\n{{business}}"}}}, headers=u.h())
    assert client.put(f"/api/email/senders/{bot}", json={"from_name": "Sunrise Homes", "local_part": "", "domain_id": "",
                                                         "reply_to": "sales@sunrise.in"}, headers=u.h()).status_code == 200
    sent = _capture(monkeypatch)

    async def chat():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s1", captured_data={"Email": "priya@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)  # the email first: no name yet
        async with async_session() as db:
            c = await db.get(Conversation, conv.conversation_id)
            c.captured_data = {**c.captured_data, "Name": "Priya", "Budget": "60 lakh"}  # said before it went out
            await db.commit()
        await automations.process_due()
    run(chat)
    customer = [m for m in sent if m["to"] == "priya@example.com"]
    assert len(customer) == 1
    m = customer[0]
    assert m["subject"] == "Thanks Priya" and m["text"].startswith("Hi Priya, about 60 lakh.\n\nSunrise Homes")
    assert m["from_name"] == "Sunrise Homes" and m["reply_to"] == "sales@sunrise.in"
    job = _rows(run, EmailJob, EmailJob.user_id == u.id)[0]
    assert m["idempotency_key"] == f"email-{job.id}-1" and m["tags"] == {"ws": u.id, "job": job.id, "kind": "customer"}
    assert job.provider_id == f"re_{sent.index(m) + 1}" and job.bot_id == bot and job.subject == "Thanks Priya"

    # "Send again" is a new request, not a repeat Resend ignores.
    job.status = "failed"

    async def resend():
        async with async_session() as db:
            j = await db.get(EmailJob, job.id)
            j.status = "failed"
            await automations.requeue(j, db)
            await db.commit()
        await automations.process_due()
    run(resend)
    assert sent[-1]["idempotency_key"] == f"email-{job.id}-2"


def test_an_address_that_cant_take_mail_shows_in_history_with_the_likely_fix(client, make_user, run, monkeypatch):
    u = make_user()
    u.bot()
    client.put("/api/integrations", json={**BASE, "reply_to": "hello@acme.in", "automations": {
        "call_lead": {"enabled": True, "delay": "now", "subject": "Your call", "body": "{{summary}}"}}}, headers=u.h())

    async def lookup(domain):
        return domain != "gmial.com"
    monkeypatch.setattr(address, "_lookup", lookup)
    address._cache.clear()
    assert run(automations.schedule, u.id, "call_lead", "ref-1", "karthi@gmial.com", {"summary": "x"}) is False
    job = _rows(run, EmailJob, EmailJob.user_id == u.id)[0]
    assert job.status == "cancelled" and "gmial.com doesn't receive email" in job.error and "karthi@gmail.com" in job.error


def test_address_checks():
    assert address.suggestion("karthi@gmial.com") == "karthi@gmail.com"
    assert address.suggestion("a@yaho.co.in") == "a@yahoo.co.in"
    assert address.suggestion("a@hotmial.com") == "a@hotmail.com"
    assert address.suggestion("a@mail.com") is None and address.suggestion("a@sunrisehomes.in") is None
    assert address.suggestion("a@gmail.com") is None
    assert address.throwaway("mailinator.com") and address.throwaway("x.mailinator.com") and not address.throwaway("gmail.com")


def test_address_check_needs_a_whole_address_and_a_domain_that_takes_mail(run, monkeypatch):
    async def lookup(domain):
        return {"nomail.example": False, "slow.example": None}.get(domain, True)
    monkeypatch.setattr(address, "_lookup", lookup)
    address._cache.clear()
    assert run(address.check, "not an email").ok is False
    no = run(address.check, "a@nomail.example")
    assert not no.ok and "doesn't receive email" in no.reason
    assert run(address.check, "a@slow.example").ok  # couldn't tell: sent
    assert run(address.check, "a@mailinator.com").throwaway


# ─── the business's own domain ───────────────────────────────────

class FakeResend:
    """Resend's Domains and API keys endpoints, and sending, in memory."""

    def __init__(self):
        self.domains, self.keys, self.emails, self.calls = {}, {}, [], []
        self.verified = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append(f"{method} {path}")
        body = json.loads(request.content) if request.content else {}
        if method == "POST" and path == "/domains":
            if body["name"] in {d["name"] for d in self.domains.values()}:
                return httpx.Response(422, json={"statusCode": 422, "name": "validation_error", "message": "Domain already exists"})
            did = f"dom_{len(self.domains) + 1}"
            self.domains[did] = {"id": did, "name": body["name"], "status": "not_started"}
            return httpx.Response(200, json={**self.domains[did], "region": "us-east-1", "records": self._records(body["name"], "not_started")})
        if path.startswith("/domains/"):
            did = path.split("/")[2]
            if did not in self.domains:
                return httpx.Response(404, json={"message": "Domain not found"})
            d = self.domains[did]
            if method == "PATCH":
                return httpx.Response(200, json={"object": "domain", "id": did})
            if method == "POST" and path.endswith("/verify"):
                d["status"] = "verified" if did in self.verified else "pending"
                return httpx.Response(200, json={"object": "domain", "id": did})
            if method == "GET":
                return httpx.Response(200, json={"object": "domain", **d, "records": self._records(d["name"], d["status"], full=True)})
            if method == "DELETE":
                del self.domains[did]
                return httpx.Response(200, json={"object": "domain", "id": did, "deleted": True})
        if method == "POST" and path == "/api-keys":
            kid = f"key_{len(self.keys) + 1}"
            self.keys[kid] = body
            return httpx.Response(200, json={"id": kid, "object": "api_key", "token": f"re_domain_{kid}"})
        if method == "DELETE" and path.startswith("/api-keys/"):
            self.keys.pop(path.split("/")[2], None)
            return httpx.Response(200, json={})
        if method == "POST" and path == "/emails":
            self.emails.append({"auth": request.headers.get("authorization"), "idem": request.headers.get("idempotency-key"), **body})
            return httpx.Response(200, json={"id": f"re_email_{len(self.emails)}"})
        return httpx.Response(404, json={"message": "unknown"})

    @staticmethod
    def _records(name, status, full=False):
        rec = "verified" if status == "verified" else "not_started"
        return [
            {"record": "DKIM", "name": f"resend._domainkey.{name}" if full else "resend._domainkey", "type": "TXT", "ttl": "Auto",
             "status": rec, "value": "p=MIGfMA0GCSq"},
            {"record": "SPF", "name": "send", "type": "MX", "ttl": "Auto", "status": rec, "value": "feedback-smtp.us-east-1.amazonses.com", "priority": 10},
            {"record": "SPF", "name": "send", "type": "TXT", "ttl": "Auto", "status": rec,
             "value": '"v=spf1 include:amazonses.com ~all"' if full else "v=spf1 include:amazonses.com ~all"},
            {"record": "Tracking", "name": "links", "type": "CNAME", "ttl": "Auto", "status": rec, "value": "links1.resend-dns.com"},
        ]


@pytest.fixture
def resend(monkeypatch):
    fake = FakeResend()
    monkeypatch.setenv("RESEND_API_KEY", "re_nimmi_main")
    monkeypatch.setattr(email, "resend_client", lambda timeout=15: httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler), headers={"User-Agent": "nimmi-ai"}))
    return fake


def test_a_business_sends_from_its_own_domain_once_verified(client, make_user, run, resend):
    u, other = make_user(), make_user()
    bot = u.bot("Sunrise")
    assert "Nobody can send as @gmail.com" in client.post("/api/email/domains", json={"name": "gmail.com"}, headers=u.h()).json()["detail"]
    assert client.post("/api/email/domains", json={"name": "nimmiai.in"}, headers=u.h()).status_code == 400

    added = client.post("/api/email/domains", json={"name": "https://www.Sunrise-Homes.in/"}, headers=u.h())
    assert added.status_code == 200, added.text
    d = added.json()
    assert d["name"] == "sunrise-homes.in" and not d["verified"]
    assert [(r["type"], r["host"]) for r in d["records"]] == [("TXT", "resend._domainkey"), ("MX", "send"), ("TXT", "send")]  # no tracking
    assert "PATCH /domains/dom_1" in resend.calls  # tracking turned off
    assert client.post("/api/email/domains", json={"name": "sunrise-homes.in"}, headers=other.h()).status_code == 400

    # Not verified yet: still Nimmi's address.
    client.put("/api/email/senders/default", json={"from_name": "Sunrise Homes", "local_part": "Priya", "domain_id": d["id"],
                                                   "reply_to": "priya@sunrise-homes.in"}, headers=u.h())
    s = client.get("/api/email/senders", headers=u.h()).json()
    assert s["default"]["local_part"] == "priya" and s["default"]["sends_as"]["domain"] is None
    checked = client.post(f"/api/email/domains/{d['id']}/verify", headers=u.h()).json()
    assert checked["status"] == "pending"

    resend.verified.add("dom_1")
    checked = client.post(f"/api/email/domains/{d['id']}/verify", headers=u.h()).json()
    assert checked["verified"] and checked["own_key"] and checked["records"][2]["value"] == "v=spf1 include:amazonses.com ~all"
    assert resend.keys["key_1"] == {"name": "Nimmi sunrise-homes.in", "permission": "sending_access", "domain_id": "dom_1"}
    s = client.get("/api/email/senders", headers=u.h()).json()
    assert s["assistants"][0]["sends_as"]["address"] == "priya@sunrise-homes.in"

    # An automatic email goes from the domain, with the domain's own key.
    client.put("/api/integrations", json={**BASE, "sender_name": "Sunrise Homes", "reply_to": "priya@sunrise-homes.in", "automations": {
        "chat_lead": {"enabled": True, "delay": "now", "subject": "Hi {{name}}", "body": "Thanks"}}}, headers=u.h())

    async def chat():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s9", captured_data={"Name": "Ravi", "Email": "ravi@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        await automations.process_due()
    run(chat)
    sent = [e for e in resend.emails if e["to"] == ["ravi@example.com"]]
    assert sent and sent[0]["from"] == '"Sunrise Homes" <priya@sunrise-homes.in>' and sent[0]["auth"] == "Bearer re_domain_key_1"
    assert sent[0]["idem"].startswith("email-") and {"name": "kind", "value": "customer"} in sent[0]["tags"]

    assert client.delete(f"/api/email/domains/{d['id']}", headers=u.h()).status_code == 200
    assert "DELETE /api-keys/key_1" in resend.calls and "DELETE /domains/dom_1" in resend.calls
    s = client.get("/api/email/senders", headers=u.h()).json()
    assert s["default"]["domain_id"] == "" and s["default"]["sends_as"]["address"] == email.address_of(email.customer_sender())
    assert client.post(f"/api/email/domains/{d['id']}/verify", headers=other.h()).status_code == 404


def test_new_domains_warm_up_and_bulk_email_pauses_over_gmails_spam_limit(client, make_user, run, monkeypatch):
    now = datetime(2026, 11, 1, 12)
    day0 = EmailDomain(name="x.in", status="verified", verified_at=now - timedelta(hours=2))
    assert domains.bulk_allowance(day0, now) == 100
    assert domains.bulk_allowance(EmailDomain(name="x.in", status="verified", verified_at=now - timedelta(days=3)), now) == 800
    assert domains.bulk_allowance(EmailDomain(name="x.in", status="verified", verified_at=now - timedelta(days=8)), now) is None
    assert domains.bulk_allowance(EmailDomain(name="x.in", status="pending"), now) == 0
    assert domains.bulk_allowance(None, now) is None

    u = make_user()
    u.bot()

    async def history(complaints):
        async with async_session() as db:
            for i in range(250):
                db.add(EmailJob(user_id=u.id, kind=f"broadcast:b1#{i}", ref_id=f"r{i}{complaints}", to_email=f"p{i}@example.com",
                                subject="Offer", body="x", status="sent", broadcast_id="b1", sent_at=datetime.utcnow(),
                                delivered_at=datetime.utcnow(), complained_at=datetime.utcnow() if i < complaints else None))
            await db.commit()
    run(history, 2)  # 0.8%: over Gmail's 0.3%
    monkeypatch.setattr(email, "is_configured", lambda: True)
    client.put("/api/integrations", json={**BASE, "reply_to": "hello@acme.in"}, headers=u.h())
    r = client.post("/api/integrations/email/broadcasts", json={"subject": "Hi", "body": "News", "consent": True}, headers=u.h())
    assert r.status_code == 409 and "Bulk email is paused" in r.json()["detail"]


# ─── chat leads as contacts ──────────────────────────────────────

def test_chat_leads_become_contacts_by_email_or_number(client, make_user, run):
    u = make_user()
    bot = u.bot()

    async def lead(session, captured):
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=session, captured_data=captured)
            db.add(conv)
            await db.commit()
        await contacts.remember_lead(conv.conversation_id)

    run(lead, "s1", {"Name": "Asha", "Email": "Asha@Example.com", "Budget": "60 lakh"})
    found = _rows(run, Contact, Contact.bot_id == bot)
    assert len(found) == 1 and found[0].e164 is None and found[0].email == "Asha@Example.com" and found[0].source == "chat"
    assert found[0].details == {"Budget": "60 lakh"}

    run(lead, "s2", {"Name": "Asha Kumar", "Email": "asha@example.com", "Phone": "9876543210"})  # the same person, now with a number
    found = _rows(run, Contact, Contact.bot_id == bot)
    assert len(found) == 1 and found[0].e164 == "+919876543210" and found[0].name == "Asha Kumar"

    run(lead, "wa:919800000001", {"Name": "Ravi", "Email": "ravi@example.com"})  # WhatsApp keeps its own contacts
    assert len(_rows(run, Contact, Contact.bot_id == bot)) == 1

    async def forget_callers():
        async with async_session() as db:
            db.add(VoiceAgent(bot_id=bot, user_id=u.id, remember_callers=False))
            await db.commit()
    run(forget_callers)
    run(lead, "s3", {"Name": "Meena", "Email": "meena@example.com"})
    assert len(_rows(run, Contact, Contact.bot_id == bot)) == 1


# ─── meetings ────────────────────────────────────────────────────

def test_meeting_emails_reply_to_the_business_and_skip_bounced_addresses(client, make_user, run, monkeypatch):
    from voice import meetings
    u = make_user()
    bot = u.bot("Clinic")
    client.put("/api/integrations", json={**BASE, "reply_to": "front@clinic.in"}, headers=u.h())
    sent = _capture(monkeypatch)

    async def meeting(addr):
        async with async_session() as db:
            m = Meeting(user_id=u.id, bot_id=bot, e164="+919800000002", name="Priya", email=addr, kind="online",
                        status="confirmed", history=[], starts_at=datetime(2030, 1, 2, 5, 0))
            db.add(m)
            await db.commit()
            return m.id

    async def unsubscribe(addr):
        async with async_session() as db:
            await suppress.add(db, u.id, addr, "unsubscribed")
            await suppress.add_bounce(db, "dead@example.com")
            await db.commit()
    run(unsubscribe, "priya@example.com")
    run(meetings._to_person, run(meeting, "priya@example.com"), "confirmed")  # they asked for it: it still goes
    assert sent and sent[0]["reply_to"] == "front@clinic.in" and sent[0]["tags"]["kind"] == "customer"
    problem = run(meetings._to_person, run(meeting, "dead@example.com"), "confirmed")
    assert len(sent) == 1 and "bounced" in problem


# ─── the database ────────────────────────────────────────────────

def test_an_old_sqlite_contacts_table_takes_a_lead_without_a_number(tmp_path):
    from sqlalchemy import create_engine
    import database
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE contacts (
            id VARCHAR(36) NOT NULL,
            bot_id VARCHAR(36),
            e164 VARCHAR NOT NULL,
            name VARCHAR,
            PRIMARY KEY (id),
            CONSTRAINT uq_contact_bot_number UNIQUE (bot_id, e164)
        );
        CREATE INDEX ix_contacts_e164 ON contacts (e164);
        INSERT INTO contacts (id, bot_id, e164, name) VALUES ('c1', 'b1', '+919800000001', 'Asha');
    """)
    con.close()
    engine = create_engine(f"sqlite:///{path}")
    for _ in range(2):  # the second start finds it done
        with engine.begin() as conn:
            database._relax_not_null(conn, "contacts", "e164")
    con = sqlite3.connect(path)
    assert [r[3] for r in con.execute("pragma table_info(contacts)") if r[1] == "e164"] == [0]
    assert con.execute("select name from contacts where id = 'c1'").fetchone() == ("Asha",)
    assert "ix_contacts_e164" in {r[0] for r in con.execute("select name from sqlite_master where type = 'index'")}
    con.execute("insert into contacts (id, bot_id, e164, name) values ('c2', 'b1', null, 'Ravi')")
    with pytest.raises(sqlite3.IntegrityError):  # the number is still unique per assistant
        con.execute("insert into contacts (id, bot_id, e164, name) values ('c3', 'b1', '+919800000001', 'Dup')")
