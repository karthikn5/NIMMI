"""WhatsApp: webhook security per number, routing, human-like replies (one answer to quick messages, short messages,
files, buttons), voice notes, the team taking over, delivery receipts, Meta user ids, Live chat, settings and erasure."""
import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy.future import select

from backend.models import Conversation, IntegrationSettings, Message, WhatsAppChat, WhatsAppFile, WhatsAppMessage, WhatsAppNumber
from database import async_session
from whatsapp import chats, graph, numbers, replies, storage

SECRET = "app-secret"


class FakeMeta:
    """Meta's Cloud API, recording what would have been sent."""
    def __init__(self):
        self.sent, self.typing, self.read, self.uploads = [], [], [], []
        self.files: dict = {}
        self.prompts: list = []
        self.answers: list = []
        self.on_ai = None

    def _out(self, **item) -> str:
        self.sent.append(item)
        return f"wamid.out{len(self.sent)}.{uuid.uuid4().hex[:6]}"

    async def send_text(self, pid, token, to, text, reply_to=None):
        return self._out(kind="text", pid=pid, token=token, to=to, text=text, reply_to=reply_to)

    async def send_buttons(self, pid, token, to, text, buttons, reply_to=None):
        return self._out(kind="buttons", pid=pid, token=token, to=to, text=text, buttons=buttons, reply_to=reply_to)

    async def send_media(self, pid, token, to, kind, media_id, caption=None, filename=None, reply_to=None):
        return self._out(kind=kind, pid=pid, token=token, to=to, media_id=media_id, caption=caption, filename=filename)

    async def typing_(self, pid, token, wamid):
        self.typing.append(wamid)

    async def mark_read(self, pid, token, wamid):
        self.read.append(wamid)

    async def upload_media(self, pid, token, content, mime, filename):
        self.uploads.append((pid, filename, content))
        return f"MEDIA{len(self.uploads)}"

    async def download_media(self, token, media_id, max_bytes):
        return self.files.get(media_id, (b"\xff\xd8 not a real photo", "image/jpeg"))

    async def number_info(self, pid, token):
        if token.startswith("bad"):
            raise graph.GraphError(graph.ERRORS[190], 190)
        return {"display_phone_number": "+91 98765 00000", "verified_name": "Test Clinic", "quality_rating": "GREEN"}

    async def subscribe_app(self, waba, token):
        self.subscribed = getattr(self, "subscribed", []) + [(waba, token)]

    def texts(self) -> list[str]:
        return [s["text"] for s in self.sent if s["kind"] in ("text", "buttons")]


@pytest.fixture
def meta(monkeypatch, tmp_path):
    fake = FakeMeta()
    for name in ("send_text", "send_buttons", "send_media", "mark_read", "upload_media", "download_media",
                 "number_info", "subscribe_app"):
        monkeypatch.setattr(graph, name, getattr(fake, name))
    monkeypatch.setattr(graph, "typing", fake.typing_)
    monkeypatch.setattr(replies, "PACE", 0)
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path / "wa"))
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)

    async def has_plan(bot_id, db):
        return object()
    monkeypatch.setattr(replies, "active_subscription", has_plan)

    def ai(system, context, query, **kw):
        fake.prompts.append({"system": system, "said": query, "history": kw.get("history") or []})
        if fake.on_ai:
            fake.on_ai()
        return fake.answers.pop(0) if fake.answers else "We open at 9am."
    monkeypatch.setattr(replies, "generate_ai_response", ai)
    return fake


def _pid() -> str:
    return str(10 ** 14 + uuid.uuid4().int % 10 ** 13)


def _sender() -> str:
    return "9198" + str(uuid.uuid4().int % 10 ** 8).zfill(8)


def connect(client, user, bot_id, pid, secret="", wait=0, **extra):
    r = client.post("/api/whatsapp/numbers", json={"phone_number_id": pid, "access_token": "EAAtest-token-1234567890",
                                                   "app_secret": secret, "bot_id": bot_id, **extra}, headers=user.h())
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/whatsapp/numbers/{r.json()['id']}", json={"settings": {"wait_seconds": wait}}, headers=user.h())
    assert r.status_code == 200, r.text
    return r.json()


def text_msg(text, wamid=None, sender=None, user_id=None, **extra) -> dict:
    m = {"id": wamid or f"wamid.in.{uuid.uuid4().hex}", "type": "text", "text": {"body": text}, **extra}
    if sender:
        m["from"] = sender
    if user_id:
        m["from_user_id"] = user_id
    return m


def body(pid, *messages, field="messages", name="Ravi", **value) -> bytes:
    sender = next((m.get("from") for m in messages if m.get("from")), None)
    user_id = next((m.get("from_user_id") for m in messages if m.get("from_user_id")), None)
    contact = {"profile": {"name": name}, **({"wa_id": sender} if sender else {}), **({"user_id": user_id} if user_id else {})}
    v = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": pid}, **value}
    if messages:
        v.update(contacts=[contact], messages=list(messages))
    return json.dumps({"object": "whatsapp_business_account",
                       "entry": [{"id": "WABA", "changes": [{"field": field, "value": v}]}]}).encode()


def post(client, raw: bytes, secret: str = SECRET):
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/integrations/whatsapp/webhook", content=raw,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})


def wait_for(predicate, timeout=6.0):
    async def poll():
        for _ in range(int(timeout / 0.05)):
            if predicate():
                return True
            await asyncio.sleep(0.05)
        return predicate()
    return poll


async def _chat_for(pid: str) -> WhatsAppChat:
    async with async_session() as db:
        n = (await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.phone_number_id == pid))).scalars().first()
        return (await db.execute(select(WhatsAppChat).where(WhatsAppChat.number_id == n.id))).scalars().first()


async def _messages(chat_id: str) -> list[tuple]:
    async with async_session() as db:
        chat = await db.get(WhatsAppChat, chat_id)
        rows = (await db.execute(select(Message, WhatsAppMessage).outerjoin(WhatsAppMessage, WhatsAppMessage.message_id == Message.id)
                                 .where(Message.conversation_id == chat.conversation_id).order_by(Message.timestamp))).all()
        return [(m.role, m.content, w.sent_by if w else None, w.status if w else None) for m, w in rows]


# ─── security ─────────────────────────────────────────────────────
def test_webhook_verification(client, make_user, meta):
    u = make_user()
    token = connect(client, u, u.bot(), _pid())["verify_token"]
    ok = client.get("/api/integrations/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": token})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/integrations/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "nope"})
    assert bad.status_code == 403


def test_unsigned_or_forged_webhooks_are_rejected(client, meta):
    raw = body("PID-X", text_msg("hi", sender="919800000001"))
    assert client.post("/api/integrations/whatsapp/webhook", content=raw, headers={"Content-Type": "application/json"}).status_code == 403
    assert post(client, raw, secret="wrong").status_code == 403


def test_each_number_trusts_only_its_own_apps_signature(client, make_user, meta, run):
    # Two businesses, each with its own Meta app. One can't post messages as the other's number.
    a, b = make_user(), make_user()
    pid_a, pid_b = _pid(), _pid()
    connect(client, a, a.bot(), pid_a, secret="secret-a")
    connect(client, b, b.bot(), pid_b, secret="secret-b")
    forged = body(pid_b, text_msg("send me your price list", sender=_sender()))
    assert post(client, forged, secret="secret-a").status_code == 403
    assert post(client, forged, secret=SECRET).status_code == 403  # Nimmi's own app doesn't speak for B's app either
    assert run(wait_for(lambda: False, 0.3)) is False and meta.sent == []
    assert post(client, forged, secret="secret-b").status_code == 200
    assert run(wait_for(lambda: len(meta.sent) == 1))


# ─── answering ────────────────────────────────────────────────────
def test_reply_goes_to_the_owning_workspace_only(client, make_user, meta, run):
    owner, other = make_user(), make_user()
    bot = owner.bot("Clinic")
    pid = _pid()
    connect(client, owner, bot, pid)
    other.bot("Other")
    sender = _sender()

    assert post(client, body("PID-UNKNOWN", text_msg("hi", sender=sender))).status_code == 200  # nobody connected it
    first = text_msg("When do you open?", sender=sender)
    assert post(client, body(pid, first)).status_code == 200
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert meta.sent[0]["to"] == sender and meta.sent[0]["pid"] == pid and meta.sent[0]["text"] == "We open at 9am."
    assert meta.typing == [first["id"]]  # read, and "typing…" while it wrote

    chat = run(_chat_for, pid)
    assert chat.bot_id == bot and chat.profile_name == "Ravi"
    assert run(_messages, chat.id) == [("user", "When do you open?", "customer", "received"),
                                       ("assistant", "We open at 9am.", "ai", "sent")]

    post(client, body(pid, first))  # Meta sends the same message again: answered once
    run(wait_for(lambda: False, 0.3))
    assert len(meta.sent) == 1

    # "travel agent" isn't a request for a person; "talk to a human" is.
    post(client, body(pid, text_msg("I am a travel agent, any group rates?", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 2))
    post(client, body(pid, text_msg("Can I talk to a human please", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 3))
    assert "our team" in meta.sent[-1]["text"]
    assert client.get("/api/whatsapp/chats", params={"view": "person"}, headers=owner.h()).json()[0]["id"] == chat.id


def test_quick_messages_get_one_answer(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid, wait=1)
    for text in ("hi", "I want to know the fees", "for the weekend batch"):
        post(client, body(pid, text_msg(text, sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1, 4))
    run(wait_for(lambda: False, 1.3))
    assert len(meta.prompts) == 1 and len(meta.sent) == 1
    assert meta.prompts[0]["said"] == "[1] hi\n[2] I want to know the fees\n[3] for the weekend batch"


def test_a_message_while_it_writes_gets_one_answer_to_everything(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    meta.answers = ["Our fees are 5,000.", "The weekend batch is 6,000."]

    def more():  # the customer writes again while the first answer is being written
        meta.on_ai = None
        post(client, body(pid, text_msg("weekend batch?", sender=sender)))
    meta.on_ai = more
    post(client, body(pid, text_msg("fees?", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    run(wait_for(lambda: False, 0.4))
    assert meta.texts() == ["The weekend batch is 6,000."]
    assert meta.prompts[1]["said"] == "[1] fees?\n[2] weekend batch?"


def test_answer_goes_as_short_messages_with_a_file_and_buttons(client, make_user, meta, run):
    u = make_user()
    bot, pid, sender = u.bot(), _pid(), _sender()
    connect(client, u, bot, pid)
    r = client.post("/api/whatsapp/files", files={"file": ("brochure.pdf", b"%PDF-1.4 the course brochure", "application/pdf")},
                    data={"name": "Course brochure", "when_to_send": "when someone asks about courses or fees"}, headers=u.h())
    assert r.status_code == 200, r.text
    meta.answers = ["The data science course is 3 months.\n\nWant me to send the brochure?\n[FILE 1]\n[BUTTONS: Yes please | Call me back]",
                    "Here it is again.\n[FILE 1]"]
    post(client, body(pid, text_msg("tell me about data science", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 3))
    assert [s["kind"] for s in meta.sent] == ["text", "buttons", "document"]
    assert meta.sent[1]["buttons"] == ["Yes please", "Call me back"] and "[" not in meta.sent[1]["text"]
    assert meta.sent[2]["media_id"] == "MEDIA1" and meta.sent[2]["filename"] == "brochure.pdf"
    system = meta.prompts[0]["system"]
    assert '[1] "Course brochure" (PDF): when someone asks about courses or fees' in system
    # Sent again later: Meta still has the file, so it isn't uploaded twice; the AI was told it went already.
    post(client, body(pid, text_msg("send the brochure again", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 5))
    assert len(meta.uploads) == 1 and meta.sent[4]["media_id"] == "MEDIA1"
    assert 'Already sent in this chat today' in meta.prompts[1]["system"]
    # In the chat so far, the file it sent reads as the marker that sends it (it copied '(sent the file "...")' once).
    said_before = [h["content"] for h in meta.prompts[1]["history"] if h["role"] == "assistant"]
    assert "[FILE 1]" in said_before and not any("(sent the file" in h for h in said_before)
    files = client.get("/api/whatsapp/files", headers=u.h()).json()
    assert files[0]["sends"] == 2


def test_voice_note_is_written_out_and_answered(client, make_user, meta, run, monkeypatch):
    from whatsapp import understand
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    meta.files["VOICE1"] = (b"OggS fake voice", "audio/ogg; codecs=opus")

    async def hear(content, mime):
        assert content == b"OggS fake voice" and mime == "audio/ogg"
        return "fees enna?"
    monkeypatch.setattr(understand, "_hear", hear)
    voice = {"id": f"wamid.v.{uuid.uuid4().hex}", "from": sender, "type": "audio",
             "audio": {"id": "VOICE1", "mime_type": "audio/ogg; codecs=opus", "voice": True}}
    post(client, body(pid, voice))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert meta.prompts[0]["said"] == "(voice note) fees enna?"
    chat = run(_chat_for, pid)
    assert run(_messages, chat.id)[0][:3] == ("user", "(voice note) fees enna?", "customer")
    detail = client.get(f"/api/whatsapp/chats/{chat.id}", headers=u.h()).json()
    url = detail["messages"][0]["media"]["url"]
    assert detail["messages"][0]["kind"] == "voice"
    assert client.get(url).content == b"OggS fake voice"  # the team can play it
    assert client.get(url.split("?")[0]).status_code == 403  # but only through the signed link


# ─── the team ─────────────────────────────────────────────────────
def test_team_reply_pauses_the_assistant_until_handed_back(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    chat = run(_chat_for, pid)
    r = client.post(f"/api/whatsapp/chats/{chat.id}/send", json={"text": "Hi, this is Meena from the clinic."}, headers=u.h())
    assert r.status_code == 200 and r.json()["sent_by"] == "team" and r.json()["status"] == "sent"
    assert meta.sent[-1]["text"] == "Hi, this is Meena from the clinic." and meta.sent[-1]["to"] == sender

    post(client, body(pid, text_msg("ok thanks Meena", sender=sender)))  # the team has it: the assistant stays quiet
    run(wait_for(lambda: False, 0.4))
    assert len(meta.sent) == 2
    listed = client.get("/api/whatsapp/chats", params={"view": "person"}, headers=u.h()).json()
    assert listed[0]["id"] == chat.id and listed[0]["unread"] == 1

    client.post(f"/api/whatsapp/chats/{chat.id}/resume", headers=u.h())
    post(client, body(pid, text_msg("what time tomorrow?", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 3))
    assert client.get("/api/whatsapp/chats", params={"view": "ai"}, headers=u.h()).json()[0]["id"] == chat.id


def test_team_cant_write_after_the_24_hour_window(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    chat = run(_chat_for, pid)

    async def age():
        async with async_session() as db:
            row = await db.get(WhatsAppChat, chat.id)
            row.last_inbound_at = chats.now() - timedelta(hours=25)
            await db.commit()
    run(age)
    r = client.post(f"/api/whatsapp/chats/{chat.id}/send", json={"text": "hello?"}, headers=u.h())
    assert r.status_code == 409 and "24-hour" in r.json()["detail"]


def test_a_reply_from_the_phone_app_is_kept_and_pauses_the_assistant(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    echo = {"id": f"wamid.echo.{uuid.uuid4().hex}", "from": "919876500000", "to": sender, "type": "text",
            "text": {"body": "Sir, I'll call you in 5 minutes"}}
    assert post(client, body(pid, field="smb_message_echoes", message_echoes=[echo])).status_code == 200
    chat = run(_chat_for, pid)
    assert run(_messages, chat.id)[-1] == ("assistant", "Sir, I'll call you in 5 minutes", "phone", "sent")
    post(client, body(pid, text_msg("ok", sender=sender)))
    run(wait_for(lambda: False, 0.4))
    assert len(meta.sent) == 1


def test_agent_reply_in_live_chat_reaches_whatsapp(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("I want to talk to a human", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    conv_id = run(_chat_for, pid).conversation_id
    r = client.post(f"/api/handoffs/{conv_id}/reply", json={"text": "Hi, this is Meena from the clinic."}, headers=u.h())
    assert r.status_code == 200
    assert meta.sent[-1]["text"] == "Hi, this is Meena from the clinic." and meta.sent[-1]["to"] == sender
    chat = run(_chat_for, pid)
    msgs = run(_messages, chat.id)
    assert msgs.count(("assistant", "Hi, this is Meena from the clinic.", "team", "sent")) == 1  # saved once


# ─── receipts and identity ────────────────────────────────────────
def test_delivery_receipts_never_go_backwards_and_failures_say_why(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))

    async def out_wamid():
        async with async_session() as db:
            return (await db.execute(select(WhatsAppMessage).where(WhatsAppMessage.direction == "out")
                                     .order_by(WhatsAppMessage.created_at.desc()))).scalars().first()
    w = run(out_wamid)
    for state in ("delivered", "read", "delivered"):
        post(client, body(pid, statuses=[{"id": w.wamid, "status": state, "recipient_id": sender}]))
    chat = run(_chat_for, pid)
    assert run(_messages, chat.id)[-1][3] == "read"
    post(client, body(pid, statuses=[{"id": w.wamid, "status": "failed", "errors": [{"code": 131047, "title": "Re-engagement"}]}]))
    detail = client.get(f"/api/whatsapp/chats/{chat.id}", headers=u.h()).json()
    assert detail["messages"][-1]["status"] == "failed" and "24-hour" in detail["messages"][-1]["error"]


def test_customer_known_only_by_meta_user_id(client, make_user, meta, run):
    # Someone using a WhatsApp username: Meta sends their user id and no number.
    u = make_user()
    pid = _pid()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", user_id="IN.1349120865530274")))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert meta.sent[0]["to"] == "IN.1349120865530274"
    assert graph.recipient("IN.1349120865530274") == {"recipient": "IN.1349120865530274"}
    assert graph.recipient("+919800000001") == {"to": "919800000001"}


def test_a_chat_found_by_number_takes_the_user_id_from_then_on(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    post(client, body(pid, text_msg("me again", sender=sender, user_id="IN.555")))
    assert run(wait_for(lambda: len(meta.sent) == 2))
    chat = run(_chat_for, pid)
    assert chat.wa_user == "IN.555" and chat.wa_id == sender
    assert len(run(_messages, chat.id)) == 4  # one chat, not two


# ─── plans, settings, old setups ──────────────────────────────────
def test_a_number_moved_to_another_workspace_keeps_the_chats_apart(client, make_user, meta, run):
    # An agency disconnects a number and its client connects it: the client's customers' new messages must not land in
    # the agency's old chats, and the agency keeps what it had.
    agency, client_ws = make_user(), make_user()
    pid, sender = _pid(), _sender()
    first = connect(client, agency, agency.bot(), pid)
    post(client, body(pid, text_msg("hi from before", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert client.delete(f"/api/whatsapp/numbers/{first['id']}", headers=agency.h()).status_code == 200
    connect(client, client_ws, client_ws.bot(), pid)
    assert post(client, body(pid, text_msg("my new question", sender=sender))).status_code == 200
    assert run(wait_for(lambda: len(meta.sent) == 2))

    def texts(user):
        listed = client.get("/api/whatsapp/chats", headers=user.h()).json()
        assert len(listed) == 1
        return [m["text"] for m in client.get(f"/api/whatsapp/chats/{listed[0]['id']}", headers=user.h()).json()["messages"]]
    assert "hi from before" in texts(agency) and "my new question" not in texts(agency)
    assert "my new question" in texts(client_ws) and "hi from before" not in texts(client_ws)


def test_expired_plan_does_not_answer_with_ai(client, make_user, meta, run, monkeypatch):
    async def no_plan(bot_id, db):
        return None
    monkeypatch.setattr(replies, "active_subscription", no_plan)
    u = make_user()
    pid = _pid()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("hi", sender=_sender())))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert meta.texts() == [replies.NOT_AVAILABLE] and meta.prompts == []


def test_settings_guard_bot_and_number(client, make_user, meta):
    a, b = make_user(), make_user()
    a_bot, b_bot = a.bot(), b.bot()
    pid = _pid()
    connect(client, a, a_bot, pid)
    r = client.post("/api/whatsapp/numbers", json={"phone_number_id": _pid(), "access_token": "EAAtest-token-1234567890",
                                                   "bot_id": a_bot}, headers=b.h())
    assert r.status_code == 400  # not their assistant
    r = client.post("/api/whatsapp/numbers", json={"phone_number_id": pid, "access_token": "EAAtest-token-1234567890",
                                                   "bot_id": b_bot}, headers=b.h())
    assert r.status_code == 409  # the number belongs to another workspace
    r = client.post("/api/whatsapp/numbers", json={"phone_number_id": _pid(), "access_token": "bad-token-1234567890123"},
                    headers=b.h())
    assert r.status_code == 400 and "expired" in r.json()["detail"]  # Meta refused the token: nothing saved
    listed = client.get("/api/whatsapp/numbers", headers=a.h()).json()
    assert len(listed) == 1 and "access_token" not in listed[0] and "app_secret" not in listed[0]
    assert listed[0]["display_number"] == "+91 98765 00000" and listed[0]["settings"]["wait_seconds"] == 0
    # An expired token replaced: checked with Meta, and the app subscribed to the WhatsApp account again.
    meta.subscribed = []
    r = client.patch(f"/api/whatsapp/numbers/{listed[0]['id']}", json={"access_token": "bad-expired-token-123456"}, headers=a.h())
    assert r.status_code == 400 and meta.subscribed == []
    client.patch(f"/api/whatsapp/numbers/{listed[0]['id']}", json={"access_token": "EAAfresh-token-1234567890"}, headers=a.h())
    assert client.get("/api/whatsapp/numbers", headers=a.h()).json()[0]["waba_id"] == "" and meta.subscribed == []  # no account id given
    other = connect(client, b, b_bot, _pid(), waba_id="123456789")
    meta.subscribed = []
    client.patch(f"/api/whatsapp/numbers/{other['id']}", json={"access_token": "EAAfresh-token-1234567890"}, headers=b.h())
    assert meta.subscribed == [("123456789", "EAAfresh-token-1234567890")]


def test_numbers_from_the_old_integrations_page_move_over(client, make_user, run):
    u = make_user()
    bot, pid = u.bot(), _pid()

    async def old_setup():
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=u.id, whatsapp_chat_enabled=True, whatsapp_bot_id=bot,
                                       whatsapp_phone_number_id=pid, whatsapp_access_token="EAAold",
                                       whatsapp_verify_token="nimmi_wa_old"))
            await db.commit()
        await numbers.move_old_settings()
        await numbers.move_old_settings()  # safe to run on every start
        async with async_session() as db:
            return (await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.phone_number_id == pid))).scalars().all()
    rows = run(old_setup)
    assert len(rows) == 1 and rows[0].access_token == "EAAold" and rows[0].bot_id == bot
    assert rows[0].verify_token == "nimmi_wa_old" and rows[0].user_id == u.id


def test_an_old_chat_keeps_its_conversation(client, make_user, meta, run):
    u = make_user()
    bot, pid, sender = u.bot(), _pid(), _sender()

    async def old_chat():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=f"wa:{sender}", captured_data={"name": "Ravi"})
            db.add(conv)
            await db.flush()
            db.add(Message(conversation_id=conv.conversation_id, role="user", content="earlier question"))
            await db.commit()
            return conv.conversation_id
    conv_id = run(old_chat)
    connect(client, u, bot, pid)
    post(client, body(pid, text_msg("hello again", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    assert run(_chat_for, pid).conversation_id == conv_id
    assert meta.prompts[0]["history"][0]["content"] == "earlier question"


# ─── memory, sweep, erase ─────────────────────────────────────────
def test_whatsapp_chat_is_remembered_on_the_next_phone_call(client, make_user, meta, run):
    from voice import llm, memory as voice_memory
    u = make_user()
    bot, pid, sender = u.bot(), _pid(), _sender()
    connect(client, u, bot, pid)
    post(client, body(pid, text_msg("I need the fees for data science", sender=sender), name="Karthik"))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    chat = run(_chat_for, pid)

    async def summarised():
        async with async_session() as db:
            row = await db.get(WhatsAppChat, chat.id)
            row.summary = "Asked for the data science fees; was told 5,000."
            await db.commit()
        return await voice_memory.context_for(bot, f"+{sender}")
    ctx = run(summarised)
    assert ctx["first_name"] == "Karthik" and ctx["chats"][0]["summary"].startswith("Asked for the data science fees")
    assert "Their WhatsApp chat with the business" in llm._caller_lines(ctx)
    assert voice_memory.first_name("~ ✿") is None and voice_memory.first_name("K. Karthik") == "Karthik"


def test_sweep_answers_a_chat_whose_timer_was_lost(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid, wait=15)  # its own timer is 15 s away: as if lost in a restart
    post(client, body(pid, text_msg("hi", sender=sender)))
    chat = run(_chat_for, pid)

    async def overdue():
        async with async_session() as db:
            row = await db.get(WhatsAppChat, chat.id)
            row.reply_due_at = chats.now() - timedelta(seconds=30)
            await db.commit()
        await replies.sweep()
    run(overdue)
    assert run(wait_for(lambda: len(meta.sent) == 1))


def test_a_timer_waking_a_moment_early_still_answers(client, make_user, meta, run):
    # Seen in a simulated chat: the timer woke a hair before the due time on the wall clock, the claim failed and the
    # answer waited for the sweep (16 s instead of 4).
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid, wait=15)
    post(client, body(pid, text_msg("hi", sender=sender)))
    chat = run(_chat_for, pid)

    async def due_in(seconds: float) -> bool:
        async with async_session() as db:
            row = await db.get(WhatsAppChat, chat.id)
            row.reply_due_at, row.reply_claimed_at = chats.now() + timedelta(seconds=seconds), None
            await db.commit()
        return await replies._claim(chat.id)
    assert run(due_in, 2.0) is False  # a newer message moved it on: not yet
    assert run(due_in, 0.1) is True   # its own timer, a moment early: answered


def test_erase_removes_whatsapp_chats_and_their_files(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    meta.files["IMG1"] = (b"\xff\xd8 photo", "image/jpeg")
    photo = {"id": f"wamid.p.{uuid.uuid4().hex}", "from": sender, "type": "image", "image": {"id": "IMG1", "mime_type": "image/jpeg"}}
    post(client, body(pid, photo))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    chat = run(_chat_for, pid)
    url = client.get(f"/api/whatsapp/chats/{chat.id}", headers=u.h()).json()["messages"][0]["media"]["url"]
    assert client.get(url).status_code == 200
    assert client.post("/api/voice/erase", json={"number": f"+{sender}"}, headers=u.h()).status_code == 200
    assert run(_chat_for, pid) is None
    assert client.get(url).status_code == 404


# ─── reading the AI's answer ──────────────────────────────────────
def test_answer_is_split_like_whatsapp_messages():
    assert replies.split("Our timings:\n\n- Mon to Fri 9-6\n- Sat 9-1\n\nAnything else?", True) == \
        ["Our timings:\n- Mon to Fri 9-6\n- Sat 9-1", "Anything else?"]
    assert len(replies.split("A one.\n\nB two.\n\nC three.\n\nD four.\n\nE five.", True)) == 3
    assert replies.split("a\n\nb", False) == ["a\n\nb"]
    # A greeting isn't a message on its own (seen with Gemini: "Hi Priya," then the answer).
    assert replies.split("Hi Priya,\n\nThe fees are 5,000.\n\nAnything else?", True) == ["Hi Priya,\nThe fees are 5,000.", "Anything else?"]
    assert replies.split("வணக்கம் பிரியா,\n\nகட்டணம் 5,000.", True) == ["வணக்கம் பிரியா,\nகட்டணம் 5,000."]
    assert replies.split("Sure!\n\nThe fees are 5,000.", True) == ["Sure!", "The fees are 5,000."]
    cfg = {"send_files": True, "buttons": True, "split": True}
    r = replies.parse("[QUOTE 1] The fees are 5,000.\n\n[QUOTE 9] Weekends too.\n[FILE 7]\n[HANDOFF]\n"
                      "[BUTTONS: Morning batch please now | Evening]", ["wamid.a", "wamid.b"], [], cfg)
    assert r.bubbles == [("The fees are 5,000.", "wamid.a"), ("Weekends too.", None)]
    assert r.files == [] and r.handoff and r.buttons == ["Morning batch", "Evening"]
    assert replies.parse("Only one choice [BUTTONS: Yes]", [], [], cfg).buttons == []
    # The script of their latest message decides the reply's (Tamil in English letters stays in English letters).
    assert replies.script_of("weekend batch irukka?") == "English letters"
    assert replies.script_of("(voice note) வணக்கம், data science fees எவ்வளவு?") == "Tamil"
    assert replies.script_of("(photo: a payment screenshot)") is None
    from whatsapp import settings as wa_settings
    assert "reply in English letters" in replies.rules(wa_settings.DEFAULTS, [], [], False, [], script="English letters")
    assert "reply in Tamil script" in replies.rules(wa_settings.DEFAULTS, [], [], False, [], script="Tamil")
    assert "script" not in replies.rules(wa_settings.DEFAULTS, [], [], False, [], match_language=False, script="Tamil")
    brochure = WhatsAppFile(id="f1", name="Course brochure", kind="document", mime="application/pdf")
    copied = replies.parse('(sent the file "course brochure")\nHere is our brochure.', [], [brochure], cfg)
    assert copied.files == [brochure] and copied.bubbles == [("Here is our brochure.", None)]


def test_a_reply_stops_when_the_team_steps_in_mid_way(client, make_user, meta, run, monkeypatch):
    # Seen live: the owner replied from the Inbox between the assistant's two messages, and its second still went out.
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    meta.answers = ["Hello! I'm the clinic's assistant.\n\nWhich treatment would you like to know about?"]
    send = meta.send_text

    async def team_jumps_in(p, token, to, text, reply_to=None):
        wamid = await send(p, token, to, text, reply_to)
        if text.startswith("Hello!"):
            async with async_session() as db:
                chat = (await db.execute(select(WhatsAppChat).where(WhatsAppChat.wa_id == sender))).scalars().first()
                chat.ai_paused_until = chats.now() + timedelta(hours=1)
                await db.commit()
        return wamid
    monkeypatch.setattr(graph, "send_text", team_jumps_in)
    post(client, body(pid, text_msg("hi", sender=sender)))
    assert run(wait_for(lambda: len(meta.sent) == 1))
    run(wait_for(lambda: False, 0.5))
    assert meta.texts() == ["Hello! I'm the clinic's assistant."]
