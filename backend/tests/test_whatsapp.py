"""Two-way WhatsApp chat: webhook security, routing to the right workspace, replies, handoff and settings."""
import asyncio
import hashlib
import hmac
import json

from sqlalchemy.future import select

import realtime
from database import async_session
from backend.models import Conversation, IntegrationSettings, Message
from notify import channels
from routers import whatsapp

SECRET = "app-secret"


def _payload(phone_number_id: str, text: str, msg_id: str = "wamid.1", sender: str = "919800000001") -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": phone_number_id},
        "contacts": [{"profile": {"name": "Ravi"}}],
        "messages": [{"id": msg_id, "from": sender, "type": "text", "text": {"body": text}}],
    }}]}]}).encode()


def _post(client, body: bytes, secret: str = SECRET):
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/api/integrations/whatsapp/webhook", content=body,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})


def _connect(client, user, bot_id, pid):
    r = client.put("/api/integrations", json={"whatsapp_chat_enabled": True, "whatsapp_bot_id": bot_id,
                                              "whatsapp_phone_number_id": pid, "whatsapp_access_token": "EAAtest"},
                   headers=user.h())
    assert r.status_code == 200, r.text
    return r.json()


def _wait_for(predicate, timeout=5.0):
    async def poll():
        for _ in range(int(timeout / 0.05)):
            if predicate():
                return True
            await asyncio.sleep(0.05)
        return False
    return poll


def test_webhook_verification(client, make_user):
    u = make_user()
    token = _connect(client, u, u.bot(), "PID-VERIFY")["whatsapp_verify_token"]
    ok = client.get("/api/integrations/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": token})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/integrations/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "nope"})
    assert bad.status_code == 403


def test_unsigned_or_forged_webhooks_are_rejected(client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    body = _payload("PID-X", "hi")
    assert client.post("/api/integrations/whatsapp/webhook", content=body,
                       headers={"Content-Type": "application/json"}).status_code == 403
    assert _post(client, body, secret="wrong").status_code == 403


def test_reply_goes_to_the_owning_workspace_only(client, make_user, monkeypatch, run):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    owner, other = make_user(), make_user()
    bot = owner.bot("Clinic")
    _connect(client, owner, bot, "PID-OWNER")
    other_bot = other.bot("Other")

    sent: list[tuple] = []

    async def fake_send(to, text, phone_number_id=None, token=None):
        sent.append((to, text, phone_number_id))
        return {}

    async def fake_read(*a, **k):
        return None

    async def has_plan(bot_id, db):
        return object()
    prompts: list[str] = []

    def fake_ai(system_prompt, context, query, **kw):
        prompts.append(system_prompt)
        return "We open at 9am."
    monkeypatch.setattr(channels, "send_whatsapp_text", fake_send)
    monkeypatch.setattr(channels, "mark_whatsapp_read", fake_read)
    monkeypatch.setattr(whatsapp, "active_subscription", has_plan)
    monkeypatch.setattr(whatsapp, "generate_ai_response", fake_ai)

    # A number nobody connected: nobody answers (no falling back to some other bot).
    assert _post(client, _payload("PID-UNKNOWN", "hi", "wamid.0")).status_code == 200
    # Someone tries to steer it to another workspace's bot with ?bot_id=: ignored.
    body = _payload("PID-OWNER", "When do you open?", "wamid.1")
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    client.post(f"/api/integrations/whatsapp/webhook?bot_id={other_bot}", content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
    assert run(_wait_for(lambda: len(sent) == 1))
    assert sent == [("919800000001", "We open at 9am.", "PID-OWNER")]
    assert "Context:" not in prompts[0]  # knowledge isn't pasted twice

    async def conv():
        for _ in range(100):  # the messages are saved just after the reply goes out
            async with async_session() as db:
                c = (await db.execute(select(Conversation).where(Conversation.visitor_session_id == "wa:919800000001"))).scalars().first()
                msgs = (await db.execute(select(Message).where(Message.conversation_id == c.conversation_id))).scalars().all()
            if len(msgs) >= 2:
                break
            await asyncio.sleep(0.05)
        return c, [m.content for m in msgs]
    c, msgs = run(conv)
    assert c.bot_id == bot and msgs == ["When do you open?", "We open at 9am."]

    # Meta retries the same message id: answered once.
    _post(client, body)
    run(_wait_for(lambda: False, 0.3))
    assert len(sent) == 1

    # "travel agent" isn't a request for a person; "talk to a human" is.
    _post(client, _payload("PID-OWNER", "I am a travel agent, any group rates?", "wamid.2"))
    assert run(_wait_for(lambda: len(sent) == 2))
    assert sent[-1][1] == "We open at 9am."
    _post(client, _payload("PID-OWNER", "Can I talk to a human please", "wamid.3"))
    assert run(_wait_for(lambda: len(sent) == 3))
    assert "our team" in sent[-1][1]


def test_expired_plan_does_not_answer_with_ai(client, make_user, monkeypatch, run):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    u = make_user()
    _connect(client, u, u.bot(), "PID-EXPIRED")
    sent = []

    async def fake_send(to, text, **kw):
        sent.append(text)
        return {}

    async def fake_read(*a, **k):
        return None
    monkeypatch.setattr(channels, "send_whatsapp_text", fake_send)
    monkeypatch.setattr(channels, "mark_whatsapp_read", fake_read)
    _post(client, _payload("PID-EXPIRED", "hi", "wamid.e1", sender="919800000009"))
    assert run(_wait_for(lambda: len(sent) == 1))
    assert sent == [whatsapp.NOT_AVAILABLE]


def test_settings_guard_bot_and_number(client, make_user):
    a, b = make_user(), make_user()
    a_bot, b_bot = a.bot(), b.bot()
    _connect(client, a, a_bot, "PID-SHARED")
    r = client.put("/api/integrations", json={"whatsapp_chat_enabled": True, "whatsapp_bot_id": a_bot,
                                              "whatsapp_phone_number_id": "PID-B", "whatsapp_access_token": "t"}, headers=b.h())
    assert r.status_code == 400  # not their bot
    r = client.put("/api/integrations", json={"whatsapp_chat_enabled": True, "whatsapp_bot_id": b_bot,
                                              "whatsapp_phone_number_id": "PID-SHARED", "whatsapp_access_token": "t"}, headers=b.h())
    assert r.status_code == 409  # number belongs to another workspace
    r = client.post("/api/integrations/test", json={"channel": "whatsapp"}, headers=a.h())
    assert r.status_code == 400 and "phone number" in r.json()["detail"]
    assert "whatsapp_access_token" not in client.get("/api/integrations", headers=a.h()).json()  # token never leaves the server


def test_agent_reply_in_live_chat_reaches_whatsapp(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    _connect(client, u, bot, "PID-RELAY")
    sent = []

    async def fake_send(to, text, phone_number_id=None, token=None):
        sent.append((to, text, phone_number_id, token))
        return {}
    monkeypatch.setattr(channels, "send_whatsapp_text", fake_send)

    async def relay():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="wa:919800000002", captured_data={})
            db.add(conv)
            await db.commit()
            await realtime.relay_to_whatsapp(db, conv, "919800000002", "Hi, this is Meena from the clinic.")
    run(relay)
    assert sent == [("919800000002", "Hi, this is Meena from the clinic.", "PID-RELAY", "EAAtest")]


def test_settings_row_is_per_workspace(run, make_user, client):
    u = make_user()
    _connect(client, u, u.bot(), "PID-ROW")

    async def row():
        async with async_session() as db:
            return (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == u.id))).scalars().first()
    s = run(row)
    assert s.whatsapp_phone_number_id == "PID-ROW" and s.whatsapp_verify_token.startswith("nimmi_wa_")
