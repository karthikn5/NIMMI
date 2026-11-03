"""
Instagram DMs (instagram_plan.md, phase 5), against a fake of Instagram's APIs shaped like Meta's documents (read 3 November 2026): connecting with
Business Login for Instagram, the webhook signed and kept once, the assistant answering inside Instagram's window only, never with the human agent tag,
echoes never answered, two processes answering once, someone who only wrote a DM kept as a lead and joined to the lead that has the number they type,
a sign-in that lapses showing its repair, "one moment" when an answer is slow, quick replies, 1,000-byte messages, files understood, reactions,
seen, edits and unsends, Live chat replies, disconnecting, Meta's removal callbacks and Erase.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import Contact, Conversation, InstagramAccount, InstagramChat, InstagramMessage, LeadEvent, LeadTask, Message
from database import async_session
from instagram import accounts, chats, graph, outbound, replies
from tests.test_lead_sources import _settled, on  # noqa: F401  (email stopped at the test's edge)
from tests.test_whatsapp import wait_for
from whatsapp import storage

SECRET = "ig-app-secret"
META_SECRET = "meta-app-secret"
NOW = datetime.now(timezone.utc)


def big() -> str:
    return str(10 ** 16 + uuid.uuid4().int % 10 ** 16)


class FakeInstagram:
    """graph.instagram.com, api.instagram.com and Meta's CDN as Meta's documents show them."""

    def __init__(self):
        self.next_account()
        self.sent: list = []        # message bodies posted to /messages
        self.actions: list = []     # sender actions
        self.profiles: dict = {}
        self.files: dict = {}
        self.fail: list = []        # (path piece, status, body): each used once
        self.fail_send: list = []   # (status, body) for the next DMs sent (not "typing" or "seen")
        self.codes: list = []
        self.subscribed: list = []
        self.refreshes = 0
        self.answers: list = []
        self.prompts: list = []
        self.ai_delay = 0.0
        self.private: list = []      # private replies to comments: {"comment_id", "text"}
        self.public: list = []       # public replies: {"comment_id", "text", "id"}
        self.commenters: dict = {}   # comment id -> the IGSID Meta answers a private reply with
        self.media_list: list = []
        self.profile_calls: list = []  # (method, body) to /me/messenger_profile

    def next_account(self):
        self.ig_id, self.login_id, self.username = big(), big(), f"sunrise.{uuid.uuid4().hex[:6]}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, host = request.url.path, request.url.host
        for i, (piece, status, body) in enumerate(self.fail):
            if piece in path:
                self.fail.pop(i)
                return httpx.Response(status, json=body)
        if host == "api.instagram.com" and path == "/oauth/access_token":
            form = parse_qs(request.content.decode())
            self.codes.append(form["code"][0])
            return httpx.Response(200, json={"data": [{"access_token": "SHORT", "user_id": self.login_id,
                                                        "permissions": "instagram_business_basic,instagram_business_manage_messages"}]})
        if path == "/access_token":
            return httpx.Response(200, json={"access_token": "LONG-1", "token_type": "bearer", "expires_in": 5183944})
        if path == "/refresh_access_token":
            self.refreshes += 1
            return httpx.Response(200, json={"access_token": f"LONG-R{self.refreshes}", "token_type": "bearer", "expires_in": 5183944})
        if host == "cdn.test":
            content, mime = self.files.get(path, (None, None))
            return httpx.Response(200, content=content, headers={"content-type": mime}) if content else httpx.Response(404)
        parts = path.strip("/").split("/")
        if parts[-1] == "me":
            return httpx.Response(200, json={"data": [{"user_id": self.ig_id, "username": self.username, "name": "Sunrise Homes"}]})
        if parts[-1] == "subscribed_apps":
            self.subscribed.append(request.url.params.get("subscribed_fields"))
            return httpx.Response(200, json={"success": True})
        if parts[-1] == "messages":
            assert request.headers.get("authorization", "").startswith("Bearer ") and "access_token" not in request.url.params
            body = json.loads(request.content)
            if "comment_id" in body.get("recipient", {}):  # a private reply (Meta answers with the commenter's IGSID)
                if self.fail_send:
                    status, error = self.fail_send.pop(0)
                    return httpx.Response(status, json=error)
                cid = body["recipient"]["comment_id"]
                self.private.append({"comment_id": cid, "text": body["message"]["text"]})
                return httpx.Response(200, json={"recipient_id": self.commenters.setdefault(cid, big()), "message_id": f"m_pr_{uuid.uuid4().hex}"})
            if "sender_action" in body:
                self.actions.append(body["sender_action"])
                return httpx.Response(200, json={"recipient_id": body["recipient"]["id"]})
            if self.fail_send:
                status, error = self.fail_send.pop(0)
                return httpx.Response(status, json=error)
            self.sent.append(body)
            return httpx.Response(200, json={"recipient_id": body["recipient"]["id"], "message_id": f"m_out_{uuid.uuid4().hex}"})
        if parts[-1] == "replies":
            body = json.loads(request.content)
            reply_id = big()
            self.public.append({"comment_id": parts[-2], "text": body["message"], "id": reply_id})
            return httpx.Response(200, json={"id": reply_id})
        if parts[-1] == "media":
            return httpx.Response(200, json={"data": self.media_list})
        if parts[-1] == "messenger_profile":
            self.profile_calls.append((request.method, json.loads(request.content or b"{}")))
            return httpx.Response(200, json={"success": True})
        if parts[-1] in self.profiles:
            return httpx.Response(200, json=self.profiles[parts[-1]])
        return httpx.Response(400, json={"error": {"message": "Unsupported get request", "type": "GraphMethodException", "code": 100, "error_subcode": 33}})

    def texts(self):
        return [b["message"].get("text") for b in self.sent]


@pytest.fixture
def ig(monkeypatch, tmp_path, run):
    fake = FakeInstagram()
    monkeypatch.setenv("INSTAGRAM_APP_ID", "777")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", SECRET)
    monkeypatch.setenv("INSTAGRAM_VERIFY_TOKEN", "verify-me")
    monkeypatch.setattr(graph, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), timeout=5))
    monkeypatch.setattr(replies, "PACE", 0)
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path / "ig"))
    monkeypatch.setattr(accounts, "_last_pass", None)

    def ai(system, context, query, **kw):
        fake.prompts.append({"system": system, "said": query})
        if fake.ai_delay:
            time.sleep(fake.ai_delay)
        return fake.answers.pop(0) if fake.answers else "We're open from 9 am to 7 pm."
    monkeypatch.setattr(replies, "generate_ai_response", ai)
    yield fake
    run(_drain)  # every answer finishes here, while the fake is still in place: none spills into the next test


async def _drain():
    for _ in range(200):
        busy = [t for t in list(replies._timers) if not t.done()]
        if not busy:
            break
        await asyncio.gather(*busy, return_exceptions=True)
    await _settled()


def until(check, timeout=6.0):
    """An async check, polled on the app's loop (wait_for takes plain functions)."""
    async def poll():
        for _ in range(int(timeout / 0.05)):
            if await check():
                return True
            await asyncio.sleep(0.05)
        return await check()
    return poll


@pytest.fixture
def shop(client, make_user, ig):
    def make(wait=0, ai_on=True):
        ig.next_account()
        u = make_user("Owner")
        u.bot_id = u.bot("Sunrise")
        url = client.post("/api/instagram/connect", headers=u.h()).json()["url"]
        u.state = parse_qs(urlparse(url).query)["state"][0]
        r = client.post("/api/instagram/connect/finish", json={"code": "CODE-1#_", "state": u.state}, headers=u.h())
        assert r.status_code == 200, r.text
        u.account = r.json()
        r = client.patch(f"/api/instagram/accounts/{u.account['id']}", json={"bot_id": u.bot_id, "ai_enabled": ai_on, "settings": {"wait_seconds": wait}},
                         headers=u.h())
        assert r.status_code == 200, r.text
        u.ig_id = ig.ig_id
        return u
    return make


def envelope(ig_id: str, events: list) -> dict:
    return {"object": "instagram", "entry": [{"id": ig_id, "time": int(time.time()), "messaging": events}]}


def dm(ig_id: str, igsid: str, text=None, mid=None, **message) -> dict:
    msg = {"mid": mid or f"m_in_{uuid.uuid4().hex}", **({"text": text} if text is not None else {}), **message}
    return envelope(ig_id, [{"sender": {"id": igsid}, "recipient": {"id": ig_id}, "timestamp": int(time.time() * 1000), "message": msg}])


def post(client, payload, secret: str = SECRET):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/instagram/webhook", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})


async def _chat(igsid: str) -> InstagramChat:
    async with async_session() as db:
        return (await db.execute(select(InstagramChat).where(InstagramChat.igsid == igsid))).scalars().first()


async def _rows(model, **where):
    async with async_session() as db:
        q = select(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return (await db.execute(q)).scalars().all()


async def _set(model, key, **values):
    async with async_session() as db:
        await db.execute(update(model).where(model.id == key).values(**values))
        await db.commit()


def person() -> str:
    return big()


# ─── connecting ──────────────────────────────────────────────────
def test_connecting_through_instagrams_sign_in(client, make_user, shop, ig, run):
    u = shop()
    assert ig.codes == ["CODE-1"]  # Meta: "The #_ appended to the end of the redirect URI is not part of the code itself"
    a = u.account
    assert (a["status"], a["subscribed"], a["username"]) == ("connected", True, ig.username) and a["ig_id"] == ig.ig_id
    assert ig.subscribed and "messages" in ig.subscribed[-1]
    expires = datetime.fromisoformat(a["token_expires_at"])
    assert timedelta(days=59) < expires - NOW < timedelta(days=61)
    row = run(_rows, InstagramAccount, id=a["id"])[0]
    assert row.access_token == "LONG-1"  # the long-lived one, sealed in the database
    # Someone else's sign-in can't be finished here, and one account belongs to one workspace.
    other = make_user("Other")
    assert client.post("/api/instagram/connect/finish", json={"code": "C", "state": u.state}, headers=other.h()).status_code == 403
    url = client.post("/api/instagram/connect", headers=other.h()).json()["url"]
    assert url.startswith("https://www.instagram.com/oauth/authorize?") and "instagram_business_manage_messages" in url
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.post("/api/instagram/connect/finish", json={"code": "CODE-2", "state": state}, headers=other.h())
    assert r.status_code == 409 and "already connected to another Nimmi account" in r.json()["detail"]
    shown = client.get("/api/instagram", headers=u.h()).json()
    assert shown["available"] and [x["id"] for x in shown["accounts"]] == [a["id"]] and client.get("/api/instagram", headers=other.h()).json()["accounts"] == []


# ─── a DM, its answer, a lead ────────────────────────────────────
def test_a_dm_gets_an_answer_and_the_person_is_a_lead_without_a_number(client, shop, ig, run):
    u = shop()
    igsid = person()
    ig.profiles[igsid] = {"name": "Priya Raman", "username": "priya.r"}
    assert post(client, dm(u.ig_id, igsid, "What are your timings?")).status_code == 200
    assert run(wait_for(lambda: len(ig.sent) == 1))
    assert ig.sent[0] == {"recipient": {"id": igsid}, "message": {"text": "We're open from 9 am to 7 pm."}}
    assert "mark_seen" in ig.actions and "typing_on" in ig.actions
    assert "in Instagram direct messages" in ig.prompts[0]["system"] and "No *stars*" in ig.prompts[0]["system"]
    run(_settled)
    chat = run(_chat, igsid)
    assert (chat.username, chat.name) == ("priya.r", "Priya Raman") and chat.contact_id
    [c] = run(_rows, Contact, bot_id=u.bot_id)
    assert (c.instagram_id, c.instagram_username, c.e164, c.email, c.source, c.name) == (igsid, "priya.r", None, None, "instagram", "Priya Raman")
    lead = client.get(f"/api/crm/leads/{c.id}", headers=u.h()).json()
    assert lead["name"] == "Priya Raman" and any(t["kind"] == "came_in" for t in lead["timeline"] if "kind" in t) or lead["id"] == c.id
    assert [e.kind for e in run(_rows, LeadEvent, contact_id=c.id)] == ["came_in"]
    assert run(_rows, LeadTask, contact_id=c.id) == []  # the assistant answered: no first task, as for a call
    conv = run(_rows, Conversation, conversation_id=chat.conversation_id)[0]
    assert conv.visitor_session_id == f"ig:{igsid}" and conv.contact_id == c.id
    msgs = sorted(run(_rows, InstagramMessage, chat_id=chat.id), key=lambda w: w.created_at)
    assert [(w.direction, w.sent_by, w.status) for w in msgs] == [("in", "customer", "received"), ("out", "ai", "sent")] and msgs[1].mid.startswith("m_out_")


def test_the_webhook_is_signed_kept_once_and_batched(client, shop, ig, run, monkeypatch):
    u = shop()
    one, two = person(), person()
    payload = dm(u.ig_id, one, "Hi", mid="m_once")
    assert post(client, payload, secret="not-ours").status_code == 403
    assert post(client, payload).status_code == 200 and post(client, payload).status_code == 200  # Meta sends it again
    assert run(wait_for(lambda: len(ig.sent) == 1))
    assert len(run(_rows, InstagramMessage, mid="m_once")) == 1
    monkeypatch.setenv("META_APP_SECRET", META_SECRET)  # Meta's pages don't say which of Nimmi's two secrets signs these: either is taken
    batch = [dm(u.ig_id, two, "Price?"), dm(big(), person(), "Nobody connected this account")]
    assert post(client, batch, secret=META_SECRET).status_code == 200
    assert run(wait_for(lambda: len(ig.sent) == 2))
    assert run(_chat, two) is not None and len(run(_rows, InstagramChat)) >= 2
    assert client.get("/api/instagram/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "verify-me"}).text == "42"
    assert client.get("/api/instagram/webhook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "wrong"}).status_code == 403


# ─── echoes ──────────────────────────────────────────────────────
def test_echoes_are_never_answered(client, shop, ig, run):
    u = shop()
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Hello"))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    chat = run(_chat, igsid)
    [ours] = [w for w in run(_rows, InstagramMessage, chat_id=chat.id) if w.direction == "out"]
    echo = lambda mid, text: envelope(u.ig_id, [{"sender": {"id": u.ig_id}, "recipient": {"id": igsid}, "timestamp": int(time.time() * 1000),
                                                "message": {"mid": mid, "text": text, "is_echo": True}}])
    # Nimmi's own send: known by its id, nothing new.
    post(client, echo(ours.mid, "We're open from 9 am to 7 pm."))
    # Nimmi's own send whose echo beats Meta's answer: kept before Meta was asked, so the echo finds it.
    async def sending():
        return await outbound._keep(await _chat(igsid), "Our address is MG Road.", kind="text", sent_by="ai", author_id=None, message_id=None, tag=None)
    early = run(sending)
    post(client, echo("m_early", "Our address is MG Road."))
    row = run(_rows, InstagramMessage, id=early.id)[0]
    assert (row.mid, row.status) == ("m_early", "sent") and not chats.ai_paused(run(_chat, igsid))
    # Written in the Instagram app: kept as the team's, and the assistant steps back.
    post(client, echo("m_app", "I'll call you in 5 minutes"))
    app = run(_rows, InstagramMessage, mid="m_app")[0]
    chat = run(_chat, igsid)
    assert (app.sent_by, app.direction) == ("app", "out") and chats.ai_paused(chat) and chat.reply_due_at is None
    [listed] = [c for c in client.get("/api/instagram/chats", headers=u.h()).json() if c["id"] == chat.id]
    assert listed["last"] == {"role": "assistant", "text": "I'll call you in 5 minutes", "by": "team"}  # the Inbox shows it as the team's, not the assistant's
    post(client, dm(u.ig_id, igsid, "Ok thanks"))
    run(_settled)
    assert len(ig.sent) == 1  # no echo was answered, and the chat is the team's for now


# ─── Instagram's windows ─────────────────────────────────────────
def test_past_24_hours_only_a_person_may_reply_and_only_for_7_days(client, shop, ig, run):
    u = shop(ai_on=False)
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Is the 2BHK available?"))
    run(_settled)
    chat = run(_chat, igsid)
    assert ig.sent == []  # the assistant is off for this account
    # The assistant never answers outside the window, whatever is waiting.
    run(_set, InstagramChat, chat.id, last_inbound_at=datetime.utcnow() - timedelta(days=2), reply_due_at=datetime.utcnow())
    run(_set, InstagramAccount, u.account["id"], ai_enabled=True)
    run(replies.run, chat.id)
    assert ig.sent == [] and all(w.handled for w in run(_rows, InstagramMessage, chat_id=chat.id))
    # A person can, with Instagram's human agent tag.
    r = client.post(f"/api/instagram/chats/{chat.id}/send", json={"text": "Sorry for the delay: yes, it is."}, headers=u.h())
    assert r.status_code == 200 and r.json()["tag"] == "human_agent"
    assert ig.sent[-1]["messaging_type"] == "MESSAGE_TAG" and ig.sent[-1]["tag"] == "HUMAN_AGENT"
    # Inside 24 hours, no tag; after 7 days, nothing.
    run(_set, InstagramChat, chat.id, last_inbound_at=datetime.utcnow() - timedelta(hours=1))
    client.post(f"/api/instagram/chats/{chat.id}/send", json={"text": "Shall I share the floor plan?"}, headers=u.h())
    assert "tag" not in ig.sent[-1]
    run(_set, InstagramChat, chat.id, last_inbound_at=datetime.utcnow() - timedelta(days=8))
    r = client.post(f"/api/instagram/chats/{chat.id}/send", json={"text": "Hello?"}, headers=u.h())
    assert r.status_code == 409 and r.json()["detail"] == chats.CLOSED and len(ig.sent) == 2


def test_the_assistant_can_never_use_the_human_agent_tag(shop, ig, run):
    u = shop()

    async def try_it(sent_by, author):
        async with async_session() as db:
            a = await db.get(InstagramAccount, u.account["id"])
        chat = InstagramChat(id=str(uuid.uuid4()), igsid="x", account_id=a.id)
        await outbound.send_text(a, chat, "Hi", sent_by=sent_by, author_id=author, human_agent=True)
    for sent_by, author in (("ai", None), ("team", None), ("app", "someone")):
        with pytest.raises(outbound.TagRefused):
            run(try_it, sent_by, author)
    assert ig.sent == []


def test_an_ads_first_message_gives_7_days(client, shop, ig, run):
    u = shop()
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Interested", referral={"ref": "diwali", "ad_id": "120330001", "source": "ADS", "type": "OPEN_THREAD",
                                                            "ads_context_data": {"ad_title": "2BHK in Anna Nagar"}}))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    chat = run(_chat, igsid)
    conv = run(_rows, Conversation, conversation_id=chat.conversation_id)[0]
    assert conv.origin == {"channel": "instagram_ad", "ad_id": "120330001", "headline": "2BHK in Anna Nagar", "ref": "diwali"}
    assert '"2BHK in Anna Nagar"' in ig.prompts[0]["system"]
    run(_set, InstagramChat, chat.id, last_inbound_at=datetime.utcnow() - timedelta(days=3))
    assert chats.window_open(run(_chat, igsid))  # Meta: up to 7 days after an ad's first message


# ─── two processes ───────────────────────────────────────────────
def test_two_processes_answer_once(client, shop, ig, run):
    u = shop(ai_on=False)
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Hi"))
    run(_settled)
    chat = run(_chat, igsid)
    run(_set, InstagramAccount, u.account["id"], ai_enabled=True)
    run(_set, InstagramChat, chat.id, reply_due_at=datetime.utcnow())

    async def both():
        await asyncio.gather(replies.run(chat.id), replies.run(chat.id))
    run(both)
    assert len(ig.sent) == 1


# ─── joined up by what they type ─────────────────────────────────
def test_a_number_typed_in_a_dm_joins_the_lead_that_has_it(client, shop, ig, run):
    from notify import events
    u = shop()
    igsid = person()
    ig.profiles[igsid] = {"name": "Arjun", "username": "arjun.k"}
    post(client, dm(u.ig_id, igsid, "Hi"))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    run(_settled)
    chat = run(_chat, igsid)
    mine = chat.contact_id

    async def known():
        async with async_session() as db:
            c = Contact(user_id=u.id, bot_id=u.bot_id, e164="+919876500801", name="Arjun Kumar", details={}, calls=1)
            db.add(c)
            await db.commit()
            return c.id
    theirs = run(known)

    async def typed():
        async with async_session() as db:
            conv = await db.get(Conversation, chat.conversation_id)
            conv.captured_data = {**(conv.captured_data or {}), "phone": "+919876500801"}
            await db.commit()
        await events.lead_captured(chat.conversation_id)
    run(typed)
    run(_settled)
    assert run(_rows, Contact, id=mine) == []  # one person, one contact
    [c] = run(_rows, Contact, id=theirs)
    assert (c.instagram_id, c.instagram_username, c.name) == (igsid, "arjun.k", "Arjun Kumar")
    assert run(_chat, igsid).contact_id == theirs and run(_rows, Conversation, conversation_id=chat.conversation_id)[0].contact_id == theirs
    kinds = [e.kind for e in run(_rows, LeadEvent, contact_id=theirs)]
    assert "merged" in kinds and "came_in" in kinds  # the Instagram lead's story came with it
    # Someone new who types their number: their own contact takes it.
    other = person()
    post(client, dm(u.ig_id, other, "Hello"))
    assert run(wait_for(lambda: len(ig.sent) == 2))
    run(_settled)
    chat2 = run(_chat, other)

    async def typed2():
        async with async_session() as db:
            conv = await db.get(Conversation, chat2.conversation_id)
            conv.captured_data = {**(conv.captured_data or {}), "email": "meena@buyers.in"}
            await db.commit()
        await events.lead_captured(chat2.conversation_id)
    run(typed2)
    run(_settled)
    [c2] = run(_rows, Contact, id=chat2.contact_id)
    assert (c2.email, c2.instagram_id) == ("meena@buyers.in", other)


# ─── a sign-in that lapses ───────────────────────────────────────
def test_a_lapsed_sign_in_shows_its_repair_and_tokens_are_renewed(client, shop, ig, run):
    u = shop()
    ig.fail_send.append((400, {"error": {"message": "Error validating access token", "type": "OAuthException", "code": 190}}))
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Hi"))
    async def lapsed():
        return (await _rows(InstagramAccount, id=u.account["id"]))[0].status == "token"
    assert run(until(lapsed))
    a = client.get("/api/instagram", headers=u.h()).json()["accounts"][0]
    assert a["status"] == "token" and "Connect it again" in a["status_detail"]
    failed = [w for w in run(_rows, InstagramMessage, chat_id=run(_chat, igsid).id) if w.direction == "out"]
    assert failed[0].status == "failed" and "Connect it again" in failed[0].error
    # Renewed weekly; a sign-in that ran out shows the repair.
    v = shop()
    run(_set, InstagramAccount, v.account["id"], token_refreshed_at=datetime.utcnow() - timedelta(days=8))
    run(accounts.tick)
    row = run(_rows, InstagramAccount, id=v.account["id"])[0]
    assert ig.refreshes == 1 and row.access_token == "LONG-R1" and chats.aware(row.token_expires_at) > NOW + timedelta(days=59)
    run(_set, InstagramAccount, v.account["id"], token_expires_at=datetime.utcnow() - timedelta(minutes=1))
    accounts._last_pass = None
    run(accounts.tick)
    assert run(_rows, InstagramAccount, id=v.account["id"])[0].status == "token"


# ─── how answers look ────────────────────────────────────────────
def test_a_slow_answer_sends_one_moment_first(client, shop, ig, run, monkeypatch):
    u = shop()
    monkeypatch.setattr(replies, "HOLD_AT", 0.2)
    ig.ai_delay = 0.8
    post(client, dm(u.ig_id, person(), "Do you have parking?"))
    assert run(wait_for(lambda: len(ig.sent) == 2))
    assert ig.texts() == [replies.HOLDING, "We're open from 9 am to 7 pm."]


def test_quick_replies_and_messages_within_1000_bytes(client, shop, ig, run):
    u = shop()
    ig.answers = ["Would you like a site visit or a call?\n[BUTTONS: Site visit | Call me]", "வணக்கம். " * 200]
    post(client, dm(u.ig_id, person(), "I'm interested"))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    assert ig.sent[0]["message"]["quick_replies"] == [{"content_type": "text", "title": "Site visit", "payload": "q1"},
                                                      {"content_type": "text", "title": "Call me", "payload": "q2"}]
    assert "[BUTTONS" not in ig.sent[0]["message"]["text"]
    post(client, dm(u.ig_id, person(), "விலை?"))
    whole = ("வணக்கம். " * 200).strip()
    assert run(wait_for(lambda: sum(len(b["message"]["text"]) for b in ig.sent[1:]) >= len(whole) - 10))  # nothing lost when it's split
    assert len(ig.sent) >= 3 and all(len(b["message"]["text"].encode("utf-8")) <= 1000 for b in ig.sent)


def test_a_photo_is_understood_before_the_answer(client, shop, ig, run, monkeypatch):
    import ai
    u = shop()
    ig.files["/p/plan.jpg"] = (b"\xff\xd8\xff fake jpeg", "image/jpeg")
    monkeypatch.setattr(ai, "look", lambda prompt, content, mime, limit: "a floor plan of a 2BHK flat")
    post(client, dm(u.ig_id, person(), None, attachments=[{"type": "image", "payload": {"url": "https://cdn.test/p/plan.jpg"}}]))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    assert "(photo: a floor plan of a 2BHK flat)" in ig.prompts[0]["said"]
    [w] = [w for w in run(_rows, InstagramMessage) if w.kind == "image" and (w.media or {}).get("url") == "https://cdn.test/p/plan.jpg"]
    assert w.media["understood"] and w.media["stored"]


def test_reactions_seen_edits_and_unsends(client, shop, ig, run):
    u = shop()
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Hi", mid="m_hi"))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    chat = run(_chat, igsid)
    [out] = [w for w in run(_rows, InstagramMessage, chat_id=chat.id) if w.direction == "out"]
    base = {"sender": {"id": igsid}, "recipient": {"id": u.ig_id}, "timestamp": int(time.time() * 1000)}
    post(client, envelope(u.ig_id, [{**base, "reaction": {"mid": out.mid, "action": "react", "reaction": "love", "emoji": "❤️"}}]))
    post(client, envelope(u.ig_id, [{**base, "read": {"mid": out.mid}}]))
    post(client, envelope(u.ig_id, [{**base, "message_edit": {"mid": "m_hi", "text": "Hi there", "num_edit": 1}}]))
    run(_settled)
    rows = run(_rows, InstagramMessage, chat_id=chat.id)
    assert any(w.kind == "reaction" and w.handled for w in rows) and run(_rows, InstagramMessage, id=out.id)[0].status == "read"
    edited = run(_rows, Message, id=run(_rows, InstagramMessage, mid="m_hi")[0].message_id)[0]
    assert edited.content == "Hi there (edited)"
    # Unsent before the answer: not answered.
    run(_set, InstagramAccount, u.account["id"], settings={"wait_seconds": 5})
    post(client, dm(u.ig_id, igsid, "my aadhaar is 1234", mid="m_oops"))
    post(client, envelope(u.ig_id, [{**base, "message": {"mid": "m_oops", "is_deleted": True}}]))
    assert run(_chat, igsid).reply_due_at is None
    gone = run(_rows, Message, id=run(_rows, InstagramMessage, mid="m_oops")[0].message_id)[0]
    assert gone.content == "(unsent a message)" and len(ig.sent) == 1


# ─── the team ────────────────────────────────────────────────────
def test_live_chat_replies_reach_instagram(client, shop, ig, run):
    u = shop()
    igsid = person()
    post(client, dm(u.ig_id, igsid, "I want to talk to a human"))
    assert run(wait_for(lambda: len(ig.sent) == 1))  # "I've let our team know"
    chat = run(_chat, igsid)
    listed = client.get("/api/handoffs/pending", headers=u.h()).json()
    assert any(h["conversation_id"] == chat.conversation_id and h["channel"] == "instagram" for h in listed)
    r = client.post(f"/api/handoffs/{chat.conversation_id}/reply", json={"text": "Hi, this is Meena from Sunrise."}, headers=u.h())
    assert r.status_code == 200
    assert run(wait_for(lambda: len(ig.sent) == 2)) and ig.texts()[-1] == "Hi, this is Meena from Sunrise."
    out = [w for w in run(_rows, InstagramMessage, chat_id=chat.id) if w.sent_by == "team"]
    assert len(out) == 1 and out[0].status == "sent" and chats.ai_paused(run(_chat, igsid))


def test_disconnecting_and_metas_removal_callbacks(client, shop, ig, run):
    u = shop()
    assert client.delete(f"/api/instagram/accounts/{u.account['id']}", headers=u.h()).status_code == 200
    stranger = person()
    post(client, dm(u.ig_id, stranger, "Hello?"))
    run(_settled)
    assert run(_chat, stranger) is None  # a disconnected account's DMs aren't even kept
    assert ig.sent == [] and client.get("/api/instagram", headers=u.h()).json()["accounts"] == []
    v = shop()

    def signed_request(data: dict) -> str:
        payload = base64.urlsafe_b64encode(json.dumps({"algorithm": "HMAC-SHA256", **data}).encode()).decode().rstrip("=")
        sig = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        return f"{sig}.{payload}"
    assert client.post("/api/instagram/deauthorize", data={"signed_request": "bad.sig"}).status_code == 400
    r = client.post("/api/instagram/deletion", data={"signed_request": signed_request({"user_id": ig.login_id})})
    assert r.status_code == 200 and r.json()["confirmation_code"]
    row = run(_rows, InstagramAccount, id=v.account["id"])[0]
    assert (row.status, row.access_token) == ("disconnected", None)


def test_erase_removes_their_instagram_chats(client, shop, ig, run):
    from notify import events
    u = shop()
    igsid = person()
    post(client, dm(u.ig_id, igsid, "Hi"))
    assert run(wait_for(lambda: len(ig.sent) == 1))
    run(_settled)
    chat = run(_chat, igsid)

    async def typed():
        async with async_session() as db:
            conv = await db.get(Conversation, chat.conversation_id)
            conv.captured_data = {**(conv.captured_data or {}), "phone": "+919876500901"}
            await db.commit()
        await events.lead_captured(chat.conversation_id)
    run(typed)
    run(_settled)
    assert client.post("/api/voice/erase", json={"number": "+91 98765 00901"}, headers=u.h()).status_code == 200
    assert run(_chat, igsid) is None and run(_rows, Conversation, conversation_id=chat.conversation_id) == []
    assert run(_rows, InstagramMessage, chat_id=chat.id) == []
