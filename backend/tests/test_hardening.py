"""The security hardening: sessions, account changes, live chat sockets, uploads, abuse limits and encryption."""
import base64
import hashlib
import hmac
import sqlite3
import time
from collections import defaultdict

import pytest
from sqlalchemy.future import select
from starlette.requests import Request

import auth
import realtime
from database import async_session
from backend.models import Conversation, EmailJob, Message, User
from notify import automations
from phone import callable_destination
from routers import auth_routes, chat


# ─── sessions and accounts ────────────────────────────────────────
def test_password_change_signs_out_other_sessions(client, make_user):
    u = make_user()
    old = u.h()
    time.sleep(1.1)  # tokens carry whole-second issue times
    r = client.post("/api/auth/change-password", json={"current_password": "password123", "new_password": "a-new-pass-99"}, headers=old)
    assert r.status_code == 200 and r.json()["token"]
    assert client.get("/api/auth/profile", headers=old).status_code == 401
    assert client.get("/api/auth/profile", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200


def test_sign_out_everywhere(client, make_user):
    u = make_user()
    old = u.h()
    time.sleep(1.1)
    fresh = client.post("/api/auth/logout-all", headers=old).json()["token"]
    assert client.get("/api/bots", headers=old).status_code == 401
    assert client.get("/api/bots", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_reset_links_are_stored_hashed_and_work_once(client, make_user, monkeypatch, run):
    u = make_user()
    sent = {}

    async def capture(email, token):
        sent["token"] = token
        return True
    monkeypatch.setattr(auth_routes, "send_reset_email", capture)
    client.post("/api/auth/forgot-password", json={"email": u.email})

    async def stored():
        async with async_session() as db:
            return (await db.execute(select(User.reset_token).where(User.id == u.id))).scalar()
    assert run(stored) == hashlib.sha256(sent["token"].encode()).hexdigest() != sent["token"]
    assert client.post("/api/auth/reset-password", json={"token": sent["token"], "new_password": "brand-new-pass"}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": sent["token"], "new_password": "another-pass1"}).status_code == 400


def test_changing_email_needs_the_password(client, make_user):
    u = make_user()
    new = f"moved-{u.id[:6]}@example.com"
    assert client.patch("/api/auth/profile", json={"email": new}, headers=u.h()).status_code == 400
    assert client.patch("/api/auth/profile", json={"email": new, "current_password": "wrong-one"}, headers=u.h()).status_code == 400
    ok = client.patch("/api/auth/profile", json={"email": new, "current_password": "password123"}, headers=u.h())
    assert ok.status_code == 200 and ok.json()["email"] == new
    assert client.patch("/api/auth/profile", json={"name": "Just a name"}, headers=u.h()).status_code == 200  # no password needed


def test_production_refuses_to_run_without_a_real_jwt_secret(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        auth._jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        auth._jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    assert auth._jwt_secret() == "x" * 40


def test_rate_limits_use_the_address_our_proxy_saw():
    def req(xff):
        return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("10.0.0.1", 1)})
    # The caller controls the first entries; Railway appends the real address last.
    assert auth.client_ip(req("1.2.3.4, 203.0.113.9")) == "203.0.113.9"
    assert auth.client_ip(req("203.0.113.9")) == "203.0.113.9"


# ─── live chat sockets ────────────────────────────────────────────
class FakeSockets:
    def __init__(self):
        self.handlers, self.rooms, self.sent = {}, defaultdict(set), []

    def on(self, event):
        def deco(fn):
            self.handlers[event] = fn
            return fn
        return deco

    async def enter_room(self, sid, room):
        self.rooms[sid].add(room)

    async def emit(self, event, data, room=None):
        self.sent.append((event, data, room))


def test_live_chat_sockets_only_reach_your_own_conversations(client, make_user, monkeypatch, run):
    monkeypatch.setattr(realtime, "sio", realtime.sio)  # restored after the test
    fake = FakeSockets()
    realtime.register(fake)
    owner, stranger = make_user(), make_user()
    bot = owner.bot()

    async def seed():
        async with async_session() as db:
            db.add_all([Conversation(bot_id=bot, visitor_session_id="web-visitor-1"),
                        Conversation(bot_id=bot, visitor_session_id="wa:919800000077")])
            await db.commit()
    run(seed)
    join, message = fake.handlers["join"], fake.handlers["message"]

    # A stranger with a valid Nimmi account can't open another workspace's chats.
    run(join, "s-stranger", {"room": "wa:919800000077", "token": stranger.token})
    run(join, "s-stranger", {"room": "web-visitor-1", "token": stranger.token})
    run(join, "s-anon", {"room": "wa:919800000077"})  # phone-number rooms are team-only
    assert not fake.rooms["s-stranger"] and not fake.rooms["s-anon"]

    # The visitor can join their own room but can't speak as the agent.
    run(join, "s-visitor", {"room": "web-visitor-1"})
    run(message, "s-visitor", {"room": "web-visitor-1", "message": "hello", "sender": "agent"})
    assert fake.sent[-1][1]["sender"] == "visitor"
    # Nor post into rooms they never joined.
    before = len(fake.sent)
    run(message, "s-visitor", {"room": "wa:919800000077", "message": "spoof", "sender": "agent"})
    assert len(fake.sent) == before

    # The workspace's own agent can.
    run(join, "s-agent", {"room": "web-visitor-1", "token": owner.token})
    run(message, "s-agent", {"room": "web-visitor-1", "message": "Hi, how can I help?", "sender": "agent"})
    assert fake.sent[-1][1] == {"room": "web-visitor-1", "message": "Hi, how can I help?", "sender": "agent"}

    async def saved():
        async with async_session() as db:
            conv = (await db.execute(select(Conversation).where(Conversation.visitor_session_id == "web-visitor-1"))).scalars().first()
            return [(m.role, m.content) for m in (await db.execute(select(Message).where(Message.conversation_id == conv.conversation_id))).scalars()]
    assert ("assistant", "Hi, how can I help?") in run(saved) and ("user", "hello") in run(saved)  # messages are stored


# ─── public endpoints and uploads ─────────────────────────────────
def test_ai_prompt_runs_only_the_flows_own_prompts(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    client.post(f"/api/bots/{bot}/config", json={"nodes": [{"id": "1", "type": "aiPrompt", "data": {"prompt": "Summarise the order"}}], "edges": []}, headers=u.h())
    monkeypatch.setattr(chat, "generate_ai_response", lambda *a, **k: "done")
    body = {"bot_id": bot, "visitor_session_id": "v-1", "context": ""}
    assert client.post("/api/chat/ai-prompt", json={**body, "prompt": "Summarise the order"}, headers=u.h()).json() == {"answer": "done"}
    assert client.post("/api/chat/ai-prompt", json={**body, "prompt": "Write me a 5000 word essay"}, headers=u.h()).status_code == 403


def test_uploads_are_checked_by_content(client, make_user):
    u = make_user()
    bot = u.bot()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert client.post(f"/api/bots/{bot}/logo", files={"file": ("logo.svg", svg, "image/svg+xml")}, headers=u.h()).status_code == 400
    html = b"<html><script>alert(document.domain)</script></html>"
    assert client.post(f"/api/bots/{bot}/logo", files={"file": ("logo.png", html, "image/png")}, headers=u.h()).status_code == 400
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    url = client.post(f"/api/bots/{bot}/logo", files={"file": ("x.html", png, "text/html")}, headers=u.h()).json()["logo_url"]
    assert url.endswith(".png")  # the name comes from what the file is, not what it's called
    fake_pdf = {"file": ("doc.pdf", b"<html>not a pdf</html>", "application/pdf")}
    assert client.post(f"/api/bots/{bot}/knowledge/upload", files=fake_pdf, headers=u.h()).status_code == 400


def test_oversized_requests_and_security_headers(client):
    assert client.post("/api/auth/login", content=b"x" * (3 * 1024 * 1024), headers={"content-type": "application/json"}).status_code == 413
    api = client.get("/api/health")
    assert api.headers["x-frame-options"] == "DENY" and api.headers["x-content-type-options"] == "nosniff"
    static = client.get("/static/nimmi-widget.js")
    assert "sandbox" in static.headers["content-security-policy"] and static.headers["cross-origin-resource-policy"] == "cross-origin"


def test_twilio_webhooks_need_twilio_signature(client, monkeypatch):
    monkeypatch.setenv("TWILIO_VERIFY_SIGNATURES", "true")
    form = {"To": "+15009999999", "From": "+919876543210"}
    assert client.post("/api/voice/twilio/incoming/tw-secret", data=form).status_code == 403  # the URL secret alone isn't enough
    url = "https://example.test/api/voice/twilio/incoming/tw-secret"
    payload = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    sig = base64.b64encode(hmac.new(b"tw-token", payload.encode(), hashlib.sha1).digest()).decode()
    assert client.post("/api/voice/twilio/incoming/tw-secret", data=form, headers={"X-Twilio-Signature": sig}).status_code == 200


def test_we_only_call_supported_countries(client, make_user):
    assert callable_destination("+919876543210") and callable_destination("+14155550100") and callable_destination("+447700900123")
    assert not callable_destination("+88216123456")  # international premium network
    assert not callable_destination("+18765551234")  # +1 but Jamaica
    assert not callable_destination("+2348012345678")
    u = make_user()
    bot = u.bot()
    r = client.post("/api/voice/callbacks/request", json={"bot_id": bot, "phone": "+882 1612 3456", "consent": True})
    assert r.status_code == 400


# ─── abuse limits and encryption ──────────────────────────────────
def test_one_address_gets_an_automation_once_a_day(client, make_user, run):
    u = make_user()
    client.put("/api/integrations", json={
        "email_alerts": False, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
        "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "hi@acme.in",
        "automations": {"chat_lead": {"enabled": True, "steps": [{"delay": "now", "subject": "Hi", "body": "Thanks"}]}},
    }, headers=u.h())

    async def lead(ref):
        return await automations.schedule(u.id, "chat_lead", ref, "victim@example.com", {"name": "x"})
    assert run(lead, "11111111-1111-1111-1111-111111111111") is True
    assert run(lead, "22222222-2222-2222-2222-222222222222") is False  # a second fake "lead" with the same address

    async def queued():
        async with async_session() as db:
            return len((await db.execute(select(EmailJob).where(EmailJob.user_id == u.id))).scalars().all())
    assert run(queued) == 1


def test_customer_api_keys_are_encrypted_at_rest(client, make_user):
    import os
    u = make_user()
    bot = u.bot()
    client.post(f"/api/bots/{bot}/config", json={"aiApiKey": "sk-very-secret-key"}, headers=u.h())
    raw = sqlite3.connect(os.environ["SQLITE_PATH"]).execute("select ai_api_key from bots where bot_id = ?", (bot,)).fetchone()[0]
    assert raw.startswith("enc:v1:") and "sk-very-secret-key" not in raw
    assert client.get(f"/api/bots/{bot}/config", headers=u.h()).json()["has_ai_api_key"] is True


def test_two_businesses_with_the_same_whatsapp_customer_stay_separate(client, make_user, monkeypatch, run):
    monkeypatch.setattr(realtime, "sio", realtime.sio)
    fake = FakeSockets()
    realtime.register(fake)
    a, b = make_user("Clinic A"), make_user("Shop B")
    bot_a, bot_b = a.bot("A"), b.bot("B")
    room = "wa:919811122233"

    async def seed():
        async with async_session() as db:
            db.add(Conversation(bot_id=bot_a, visitor_session_id=room))
            await db.commit()
            db.add(Conversation(bot_id=bot_b, visitor_session_id=room))  # B's conversation is the newer one
            await db.commit()
    run(seed)
    join, message = fake.handlers["join"], fake.handlers["message"]
    run(join, "agent-a", {"room": room, "token": a.token})
    run(join, "agent-b", {"room": room, "token": b.token})
    assert fake.rooms["agent-a"] != fake.rooms["agent-b"]  # separate socket rooms behind the same name

    run(message, "agent-a", {"room": room, "message": "Your appointment is at 5", "sender": "agent"})
    event, data, sent_to = fake.sent[-1]
    assert sent_to in fake.rooms["agent-a"] and sent_to not in fake.rooms["agent-b"]
    assert data["room"] == room  # the dashboard still sees the name it joined

    async def where_saved():
        async with async_session() as db:
            rows = (await db.execute(select(Message.content, Conversation.bot_id)
                                     .join(Conversation, Conversation.conversation_id == Message.conversation_id)
                                     .where(Conversation.visitor_session_id == room))).all()
            return {(content, bot) for content, bot in rows}
    assert run(where_saved) == {("Your appointment is at 5", bot_a)}  # in A's conversation, not B's


def test_google_sign_in_with_a_broken_supabase_setting_fails_cleanly(client, monkeypatch):
    # A wrong SUPABASE_URL used to crash the endpoint (HTTP 500), and the page then showed nothing.
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")  # nothing listens here
    monkeypatch.setenv("SUPABASE_KEY", "sb_publishable_test")
    r = client.post("/api/auth/social", json={"access_token": "anything"})
    assert r.status_code == 503 and "temporarily unavailable" in r.json()["detail"]


def test_google_sign_in_accepts_accounts_that_linked_google_later(client, monkeypatch):
    async def linked(token):
        return {"email": "linked.user@example.com", "email_confirmed_at": "2026-10-01T10:00:00Z",
                "app_metadata": {"provider": "email", "providers": ["email", "google"]}}
    monkeypatch.setattr(auth_routes, "_supabase_user", linked)
    assert client.post("/api/auth/social", json={"access_token": "t"}).status_code == 200


def test_a_replaced_encryption_key_can_still_read_old_secrets(monkeypatch):
    import secretbox
    monkeypatch.setenv("ENCRYPTION_KEY", "the-first-key-used-on-the-server")
    sealed = secretbox.seal("twilio-token")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-new-key-that-replaced-it")
    try:
        secretbox.unseal(sealed)
        raise AssertionError("an unknown key shouldn't decrypt")
    except secretbox.SecretError:
        pass
    monkeypatch.setenv("ENCRYPTION_OLD_KEYS", "the-first-key-used-on-the-server")
    assert secretbox.unseal(sealed) == "twilio-token"
    assert secretbox.unseal(secretbox.seal("new")) == "new"  # new secrets use the new key
