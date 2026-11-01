"""Someone's own Gmail or Outlook, and their calendar (mail plan, phase 8): what's asked for, who it attaches to, what goes from it, what happens when it can't, and meetings on the calendar."""
import asyncio
import base64
import email as emaillib
import json
import uuid
from datetime import datetime, timedelta, timezone
from email import policy as email_policy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.future import select

from backend.models import Contact, EmailJob, EmailThread, MailConnection, Meeting, NotificationLog, ScheduleSettings, ThreadMessage
from database import async_session
from mail import mailbox, replies, setup
from notify import automations
from notify import email
from voice import calendars, meetings, schedule
from voice.schedule import stored

GOOGLE_ALL = "openid email profile https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/calendar.events.owned"
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
IST = timezone(timedelta(hours=5, minutes=30))


class Provider:
    """Google and Microsoft, as far as Nimmi talks to them."""

    def __init__(self):
        self.sent, self.events, self.revoked, self.calls = [], {}, [], []
        self.busy, self.outlook = [], []
        self.granted = None         # what the person ticked; None: what was asked
        self.address, self.dead, self.refreshes, self.count = "priya@gmail.com", False, 0, 0
        self.send_answer = self.event_answer = None   # (status, text)
        self.meet_late, self.personal = False, False
        self.access = "access-1"

    def _token(self, r: httpx.Request, microsoft: bool) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(r.content.decode()).items()}
        if form["grant_type"] == "refresh_token":
            if self.dead:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.refreshes += 1
            self.access = f"access-{self.refreshes + 1}"
            return httpx.Response(200, json={"access_token": self.access, "expires_in": 3600, "scope": "Mail.Send", **({"refresh_token": f"rotated-{self.refreshes}"} if microsoft else {})})
        if form["code"] != "good":
            return httpx.Response(400, json={"error": "invalid_grant"})
        claims = base64.urlsafe_b64encode(json.dumps({"email": self.address, "name": "Priya Raman"}).encode()).decode().rstrip("=")
        asked = parse_qs(self.asked)["scope"][0] if getattr(self, "asked", None) else GOOGLE_ALL
        return httpx.Response(200, json={"access_token": self.access, "refresh_token": "refresh-secret", "expires_in": 3600, "scope": self.granted if self.granted is not None else asked,
                                         "id_token": f"x.{claims}.y"})

    def __call__(self, r: httpx.Request) -> httpx.Response:
        path = r.url.path
        self.calls.append(f"{r.method} {path}")
        if path.endswith("/token"):
            return self._token(r, "oauth2/v2.0" in path)
        if path.endswith("/revoke"):
            self.revoked.append(r.url.params.get("token"))
            return httpx.Response(200)
        assert r.headers["authorization"] == f"Bearer {self.access}" or r.headers["authorization"] == "Bearer stale"
        if r.headers["authorization"] == "Bearer stale":
            return httpx.Response(401, json={"error": "stale"})
        if path == "/v1.0/me":
            return httpx.Response(200, json={"displayName": "Priya Raman", "mail": None, "userPrincipalName": self.address})
        if path.endswith("/messages/send") or path.endswith("/me/sendMail"):
            if self.send_answer:
                return httpx.Response(self.send_answer[0], text=self.send_answer[1])
            raw = base64.urlsafe_b64decode(json.loads(r.content)["raw"]) if path.endswith("/messages/send") else base64.b64decode(r.content)
            self.sent.append(SimpleNamespace(message=emaillib.message_from_bytes(raw, policy=email_policy.default), content_type=r.headers.get("content-type")))
            return httpx.Response(200, json={"id": "gm1"}) if path.endswith("/messages/send") else httpx.Response(202)
        if path.endswith("/freeBusy"):
            return httpx.Response(200, json={"calendars": {self.address: {"busy": self.busy}}})
        if path.endswith("/calendarView"):
            if "skip" in str(r.url):
                return httpx.Response(200, json={"value": self.outlook[2:]})
            return httpx.Response(200, json={"value": self.outlook[:2], **({"@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?skip=2"} if len(self.outlook) > 2 else {})})
        if "/events" in path:
            return self._event(r, path)
        return httpx.Response(404, text=f"nothing at {path}")

    def _event(self, r: httpx.Request, path: str) -> httpx.Response:
        if self.event_answer:
            return httpx.Response(self.event_answer[0], text=self.event_answer[1])
        event_id = path.rsplit("/", 1)[1]
        if r.method == "POST":
            body = json.loads(r.content)
            if body.get("isOnlineMeeting") and self.personal:
                return httpx.Response(400, json={"error": {"code": "ErrorInvalidRequest"}})
            self.count += 1
            new = f"event-{self.count}"
            self.events[new] = {**body, "query": dict(r.url.params)}
            found = {"id": new, **({"onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/abc"}} if body.get("isOnlineMeeting") else {})}
            if "conferenceData" in body and not self.meet_late:
                found["hangoutLink"] = "https://meet.google.com/abc-defg-hij"
            return httpx.Response(200, json=found)
        if r.method == "GET":
            return httpx.Response(200, json={"id": event_id, "hangoutLink": "https://meet.google.com/late-link"})
        if event_id not in self.events:
            return httpx.Response(404, text="gone")
        if r.method == "DELETE":
            del self.events[event_id]
            return httpx.Response(204)
        self.events[event_id].update(json.loads(r.content))
        return httpx.Response(200, json={"id": event_id})


@pytest.fixture(autouse=True)
def _nothing_left_queued(run):
    yield
    async def clear():
        async with async_session() as db:
            await db.execute(update(EmailJob).where(EmailJob.status.in_(("queued", "draft"))).values(status="cancelled"))
            await db.commit()
    run(clear)


@pytest.fixture
def provider(monkeypatch):
    fake = Provider()
    for name in ("GOOGLE_MAIL_CLIENT_ID", "GOOGLE_MAIL_CLIENT_SECRET", "MICROSOFT_MAIL_CLIENT_ID", "MICROSOFT_MAIL_CLIENT_SECRET"):
        monkeypatch.setenv(name, "from-the-console")
    monkeypatch.delenv("MAILBOX_API_URL", raising=False)
    monkeypatch.setattr(mailbox, "client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return fake


@pytest.fixture
def usual(monkeypatch):
    """Emails that went the usual way (Resend)."""
    sent = []
    async def deliver(to, subject, text, html_body=None, **k):
        sent.append(SimpleNamespace(to=to, subject=subject, text=text, **k))
        return email.Delivery(True, id=f"re_{len(sent)}")
    monkeypatch.setattr(email, "deliver", deliver)
    return sent


def start(client, user, name="google", purpose="mail"):
    return client.post(f"/api/email/connections/{name}/start", json={"purpose": purpose}, headers=user.h())


def connect(client, user, fake, name="google", purpose="mail"):
    url = start(client, user, name, purpose).json()["url"]
    fake.asked = urlparse(url).query
    return client.post("/api/email/connections/finish", json={"code": "good", "state": parse_qs(urlparse(url).query)["state"][0]}, headers=user.h()).json()


def row_of(run, connection_id):
    async def go():
        async with async_session() as db:
            return await db.get(MailConnection, connection_id)
    return run(go)


def job_of(run, job_id):
    async def go():
        async with async_session() as db:
            return await db.get(EmailJob, job_id)
    return run(go)


def use_mailbox(run, user, bot, connection_id, level="auto"):
    async def go():
        async with async_session() as db:
            await setup.save_settings(db, user.id, bot, "mailbox", {"connection_id": connection_id})
            await setup.save_settings(db, user.id, bot, "agent", {"level": level, "per_day": 20})
            await db.commit()
    run(go)


def queue(run, user, bot, automation="agent", to="asha@example.com", **more):
    async def go():
        async with async_session() as db:
            job = EmailJob(user_id=user.id, bot_id=bot, kind=f"{automation}#{uuid.uuid4().hex[:8]}", ref_id=uuid.uuid4().hex, to_email=to, automation=automation, step=1,
                           subject="About your home", body="Hi Asha, would Saturday suit you?", status="queued", send_at=datetime.utcnow(), merge_data={"name": "Asha"}, **more)
            db.add(job)
            await db.commit()
            return job.id
    return run(go)


# ─── connecting ──────────────────────────────────────────────────
def test_it_only_ever_asks_to_send_and_never_to_read(client, make_user, provider):
    u = make_user()
    for name, purpose, wanted, never in (("google", "mail", ["gmail.send"], ["gmail.readonly", "gmail.modify", "mail.google.com", "gmail.metadata"]),
                                         ("microsoft", "mail", ["Mail.Send"], ["Mail.Read", "Mail.ReadWrite"]),
                                         ("google", "calendar", ["calendar.freebusy", "calendar.events.owned"], ["gmail", "auth/calendar "]),
                                         ("microsoft", "calendar", ["Calendars.ReadWrite"], ["Mail."])):
        url = start(client, u, name, purpose).json()["url"]
        scope = parse_qs(urlparse(url).query)["scope"][0]
        assert all(w in scope for w in wanted), scope
        assert not any(n in f"{scope} " for n in never), scope
        assert parse_qs(urlparse(url).query)["redirect_uri"][0].endswith("/dashboard/email/settings")
    google = parse_qs(urlparse(start(client, u, "google").json()["url"]).query)
    assert google["access_type"] == ["offline"] and google["prompt"] == ["consent"]  # else no refresh token


def test_nothing_is_offered_until_nimmi_has_an_app_at_the_provider(client, make_user, monkeypatch):
    for name in ("GOOGLE_MAIL_CLIENT_ID", "GOOGLE_MAIL_CLIENT_SECRET", "MICROSOFT_MAIL_CLIENT_ID", "MICROSOFT_MAIL_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    u = make_user()
    assert client.get("/api/email/connections", headers=u.h()).json()["available"] == {"google": False, "microsoft": False}
    assert start(client, u).status_code == 409


def test_a_link_someone_else_started_cant_attach_your_mailbox_to_their_workspace(client, make_user, provider):
    attacker, victim = make_user("Attacker"), make_user("Victim")
    url = start(client, attacker).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    answer = client.post("/api/email/connections/finish", json={"code": "good", "state": state}, headers=victim.h())
    assert answer.status_code == 403 and "another account" in answer.json()["detail"]
    assert client.post("/api/email/connections/finish", json={"code": "good", "state": "made-up"}, headers=attacker.h()).status_code == 403
    assert client.get("/api/email/connections", headers=attacker.h()).json()["items"] == []
    assert not any(c.endswith("/token") for c in provider.calls), "the code is never spent for the wrong person"


def test_a_connection_is_kept_sealed_and_never_shown(client, make_user, provider, run):
    u = make_user()
    made = connect(client, u, provider)
    assert made["address"] == "priya@gmail.com" and made["can_send"] and not made["has_calendar"] and made["mine"]
    async def stored_values():
        async with async_session() as db:
            return (await db.execute(text("select refresh_token, access_token from mail_connections where id = :i"), {"i": made["id"]})).one()
    refresh, access = run(stored_values)
    assert "refresh-secret" not in refresh and "access-1" not in access and refresh != "" and access != ""
    shown = client.get("/api/email/connections", headers=u.h()).text
    assert "refresh" not in shown and "access-1" not in shown


def test_sending_not_ticked_on_the_permission_page_says_so(client, make_user, provider):
    u = make_user()
    provider.granted = "openid email profile"
    url = start(client, u).json()["url"]
    answer = client.post("/api/email/connections/finish", json={"code": "good", "state": parse_qs(urlparse(url).query)["state"][0]}, headers=u.h())
    assert answer.status_code == 400 and "wasn't ticked" in answer.json()["detail"]
    assert client.get("/api/email/connections", headers=u.h()).json()["items"] == []


def test_a_calendar_adds_to_the_same_connection(client, make_user, provider):
    u = make_user()
    first = connect(client, u, provider)
    second = connect(client, u, provider, purpose="calendar")
    assert second["id"] == first["id"] and second["can_send"] and second["has_calendar"]
    assert len(client.get("/api/email/connections", headers=u.h()).json()["items"]) == 1


def test_outlook_says_who_it_is_and_its_new_refresh_tokens_are_kept(client, make_user, provider, run):
    u = make_user()
    provider.address = "priya@contoso.com"
    made = connect(client, u, provider, "microsoft")
    assert made["address"] == "priya@contoso.com" and made["provider"] == "microsoft" and made["can_send"]
    async def expire():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
            await db.commit()
    run(expire)
    run(mailbox._token, made["id"])
    assert provider.refreshes == 1 and "rotated-1" not in row_of(run, made["id"]).refresh_token
    import secretbox
    assert secretbox.unseal(row_of(run, made["id"]).refresh_token) == "rotated-1"


# ─── what goes from it ───────────────────────────────────────────
def test_an_agent_email_goes_from_the_mailbox_and_replies_still_come_to_nimmi(client, make_user, provider, usual, run, monkeypatch):
    monkeypatch.setenv("REPLY_DOMAIN", "mail.nimmiai.in")
    u = make_user()
    bot = u.bot("Sunrise")
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    job_id = queue(run, u, bot)
    run(automations.process_due)
    assert usual == [] and len(provider.sent) == 1
    m = provider.sent[0].message
    assert m["From"] == "Priya Raman <priya@gmail.com>" and m["To"] == "asha@example.com" and m["Subject"] == "About your home"
    assert m["Reply-To"].startswith("r-") and m["Reply-To"].endswith("@mail.nimmiai.in")
    assert "List-Unsubscribe" in m and m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert m.get_body(("plain",)).get_content().startswith("Hi Asha")
    job = job_of(run, job_id)
    assert job.status == "sent" and job.provider_id == "google:gm1" and job.merge_data["sent_from"] == "priya@gmail.com"


def test_outlook_gets_the_whole_email_as_mime_so_its_headers_survive(client, make_user, provider, usual, run, monkeypatch):
    monkeypatch.setenv("REPLY_DOMAIN", "mail.nimmiai.in")
    u = make_user()
    bot = u.bot()
    provider.address = "priya@contoso.com"
    use_mailbox(run, u, bot, connect(client, u, provider, "microsoft")["id"])
    queue(run, u, bot)
    run(automations.process_due)
    assert usual == [] and provider.sent[0].content_type == "text/plain"
    m = provider.sent[0].message
    assert "priya@contoso.com" in m["From"] and m["Reply-To"].startswith("r-") and "List-Unsubscribe" in m


@pytest.mark.parametrize("automation", ["after_call", "journey", "agent"])
def test_one_to_one_kinds_are_the_ones_that_use_it(automation):
    assert automation in mailbox.ONE_TO_ONE


def test_bulk_and_welcome_emails_never_go_from_a_mailbox(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    use_mailbox(run, u, bot, connect(client, u, provider)["id"])
    assert "broadcast" not in mailbox.ONE_TO_ONE and "chat_lead" not in mailbox.ONE_TO_ONE
    from backend.models import EmailBroadcast
    async def broadcast():
        async with async_session() as db:
            row = EmailBroadcast(user_id=u.id, bot_id=bot, subject="Offer", body="Hi", recipients=1, status="sending")
            db.add(row)
            await db.commit()
            return row.id
    # an agent email marked as part of a bulk send still goes the usual way
    queue(run, u, bot, broadcast_id=run(broadcast))
    async def agree():
        from mail import consent
        async with async_session() as db:
            await consent.give(db, u.id, bot, "asha@example.com", "import", "Signed up at the expo")
            await db.commit()
    run(agree)
    run(automations.process_due)
    assert provider.sent == [] and [m.to for m in usual] == ["asha@example.com"]


def test_a_mailbox_that_needs_connecting_again_never_holds_up_the_email(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    async def expire():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
            await db.commit()
    run(expire)
    provider.dead = True
    first, second = queue(run, u, bot), queue(run, u, bot, to="ravi@example.com")
    run(automations.process_due)
    run(automations.process_due)
    assert provider.sent == [] and job_of(run, first).status == "sent" and job_of(run, second).status == "sent"
    assert {"asha@example.com", "ravi@example.com"} <= {m.to for m in usual}
    assert row_of(run, made["id"]).status == "reconnect"
    told = [m for m in usual if m.subject.startswith("Connect priya@gmail.com again")]
    assert len(told) == 1 and told[0].to == u.email, "whoever connected it hears, once"
    assert "needs connecting again" in told[0].text and "/dashboard/email/settings" in told[0].text
    assert client.get("/api/email/connections", headers=u.h()).json()["items"][0]["status"] == "reconnect"
    assert row_of(run, made["id"]).sent_today == 1, "only the email that found out counts against its limit"
    async def next_day():
        async with async_session() as db:
            await db.execute(delete(NotificationLog).where(NotificationLog.kind == "mailbox_reconnect", NotificationLog.user_id == u.id))
            await db.commit()
    run(next_day)
    run(mailbox._needs_reconnect, made["id"], "Again")
    assert len([m for m in usual if m.subject.startswith("Connect priya@gmail.com again")]) == 1, "told when it broke, not every time it's found broken"


def test_a_calendar_only_connection_doesnt_send(client, make_user, provider, usual, run):
    u = make_user()
    made = connect(client, u, provider, purpose="calendar")
    assert run(mailbox.send, made["id"], "asha@example.com", "Hi", "Hi", None, reply_to=None, from_name=None) is None and provider.sent == []


def test_a_mailbox_waiting_to_be_connected_again_isnt_tried(client, make_user, provider, run):
    u = make_user()
    made = connect(client, u, provider)
    async def broken():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(status="reconnect"))
            await db.commit()
    run(broken)
    assert run(mailbox.send, made["id"], "asha@example.com", "Hi", "Hi", None, reply_to=None, from_name=None) is None
    assert not row_of(run, made["id"]).sent_today


def test_connecting_again_puts_it_right(client, make_user, provider, usual, run):
    u = make_user()
    made = connect(client, u, provider)
    async def broken():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(status="reconnect", error="Gone"))
            await db.commit()
    run(broken)
    again = connect(client, u, provider)
    assert again["id"] == made["id"] and again["status"] == "connected" and again["error"] is None


def test_a_token_the_provider_stopped_taking_is_renewed_once(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    import secretbox
    async def stale():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(access_token=secretbox.seal("stale")))
            await db.commit()
    run(stale)
    queue(run, u, bot)
    run(automations.process_due)
    assert len(provider.sent) == 1 and provider.refreshes == 1 and usual == []


def test_its_daily_limit_then_the_usual_way(client, make_user, provider, usual, run, monkeypatch):
    monkeypatch.setenv("MAILBOX_DAILY_LIMIT", "1")
    u = make_user()
    bot = u.bot()
    use_mailbox(run, u, bot, connect(client, u, provider)["id"])
    queue(run, u, bot)
    queue(run, u, bot, to="ravi@example.com")
    run(automations.process_due)
    assert len(provider.sent) == 1 and len(usual) == 1
    assert client.get("/api/email/connections", headers=u.h()).json()["items"][0]["sent_today"] == 1


def test_the_providers_own_limit_pauses_it_for_an_hour(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    provider.send_answer = (429, '{"error":{"message":"User-rate limit exceeded"}}')
    queue(run, u, bot)
    run(automations.process_due)
    assert [m.to for m in usual] == ["asha@example.com"] and row_of(run, made["id"]).paused_until is not None
    assert row_of(run, made["id"]).status == "connected", "a limit isn't a lost permission"
    provider.send_answer, before = None, len(provider.calls)
    queue(run, u, bot, to="ravi@example.com")
    run(automations.process_due)
    assert provider.sent == [] and len(usual) == 2 and len(provider.calls) == before


def test_permission_to_send_taken_away_asks_them_to_connect_again(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    provider.send_answer = (403, '{"error":{"status":"PERMISSION_DENIED","details":[{"reason":"ACCESS_TOKEN_SCOPE_INSUFFICIENT"}],"message":"insufficientPermissions"}}')
    queue(run, u, bot)
    run(automations.process_due)
    assert [m.to for m in usual if m.to == "asha@example.com"] == ["asha@example.com"] and row_of(run, made["id"]).status == "reconnect"


def test_an_answer_in_the_inbox_goes_from_the_person_answering(client, make_user, provider, usual, run, monkeypatch):
    monkeypatch.setenv("REPLY_DOMAIN", "mail.nimmiai.in")
    owner, helper = make_user("Owner"), make_user("Helper")
    bot = owner.bot()
    connect(client, owner, provider)
    async def thread():
        async with async_session() as db:
            row = EmailThread(user_id=owner.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="asha@example.com", subject="Parking", last_message_id="<m1@x>", reference_ids=["<m0@x>", "<m1@x>"])
            db.add(row)
            await db.commit()
            return row.id
    thread_id = run(thread)
    assert run(replies.send_text, thread_id, "Yes, one space.", "team", by=owner.id) is None
    m = provider.sent[0].message
    assert "priya@gmail.com" in m["From"] and m["In-Reply-To"] == "<m1@x>" and m["References"] == "<m0@x> <m1@x>" and m["Subject"].startswith("Re:")
    assert run(replies.send_text, thread_id, "Yes, one space.", "team", by=helper.id) is None
    assert len(provider.sent) == 1 and [m.to for m in usual] == ["asha@example.com"], "someone else's mailbox isn't theirs to use"


def test_the_assistants_mailbox_must_be_the_workspaces_own(client, make_user, provider):
    u, other = make_user(), make_user()
    bot = u.bot()
    theirs = connect(client, other, provider)
    assert client.put(f"/api/email/setup/{bot}", json={"settings": {"mailbox": {"connection_id": theirs["id"]}}}, headers=u.h()).status_code == 400
    calendar_only = connect(client, u, provider, purpose="calendar")
    assert client.put(f"/api/email/setup/{bot}", json={"settings": {"mailbox": {"connection_id": calendar_only["id"]}}}, headers=u.h()).status_code == 400
    mine = connect(client, u, provider)
    client.put("/api/email/senders/" + bot, json={"reply_to": "team@example.com"}, headers=u.h())
    answer = client.put(f"/api/email/setup/{bot}", json={"settings": {"mailbox": {"connection_id": mine["id"]}}}, headers=u.h())
    assert answer.status_code == 200 and answer.json()["settings"]["mailbox"]["connection_id"] == mine["id"]
    assert client.put(f"/api/email/setup/{bot}", json={"settings": {"mailbox": {"connection_id": None}}}, headers=u.h()).status_code == 200


def test_disconnecting_takes_the_permission_back_and_emails_go_the_usual_way(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider)
    use_mailbox(run, u, bot, made["id"])
    assert client.delete(f"/api/email/connections/{made['id']}", headers=u.h()).status_code == 200
    assert provider.revoked == ["refresh-secret"] and client.get("/api/email/connections", headers=u.h()).json()["items"] == []
    queue(run, u, bot)
    run(automations.process_due)
    assert [m.to for m in usual] == ["asha@example.com"]


def test_another_workspace_cant_see_or_remove_a_connection(client, make_user, provider):
    u, other = make_user(), make_user()
    made = connect(client, u, provider)
    assert client.get("/api/email/connections", headers=other.h()).json()["items"] == []
    assert client.delete(f"/api/email/connections/{made['id']}", headers=other.h()).status_code == 404
    assert provider.revoked == []


def test_someone_leaving_the_team_takes_their_mailbox_with_them(client, make_user, provider, run):
    from backend.models import TeamMember
    owner, helper = make_user("Owner"), make_user("Helper")
    async def member():
        async with async_session() as db:
            row = TeamMember(owner_id=owner.id, member_id=helper.id, email=helper.email, role="admin", status="active", invite_token=uuid.uuid4().hex)
            db.add(row)
            await db.commit()
            return row.id
    member_id = run(member)
    url = client.post("/api/email/connections/google/start", json={"purpose": "mail"}, headers=helper.h(owner.id)).json()["url"]
    provider.asked = urlparse(url).query
    made = client.post("/api/email/connections/finish", json={"code": "good", "state": parse_qs(urlparse(url).query)["state"][0]}, headers=helper.h(owner.id)).json()
    assert made["mine"] and client.get("/api/email/connections", headers=owner.h()).json()["items"][0]["person"] == "Helper"
    assert client.delete(f"/api/team/members/{member_id}", headers=owner.h()).status_code == 200
    assert client.get("/api/email/connections", headers=owner.h()).json()["items"] == [] and provider.revoked == ["refresh-secret"]


# ─── the calendar ────────────────────────────────────────────────
def _meeting_settings(run, user, bot, connection_id, **more):
    settings = schedule.clean({"meetings": {"enabled": True, "hours": ["10:00", "12:00"], "days": ALL_DAYS, "notice_hours": 0, "calendar": connection_id, **more}})
    async def go():
        async with async_session() as db:
            db.add(ScheduleSettings(bot_id=bot, user_id=user.id, settings=settings))
            await db.commit()
    run(go)
    return settings


def _at(day, clock):
    return datetime.combine(day, datetime.strptime(clock, "%H:%M").time(), tzinfo=IST)


def _day():
    return datetime.now(IST).date() + timedelta(days=3)


def _free(run, settings, user, bot, day):
    async def go():
        async with async_session() as db:
            return [t.strftime("%H:%M") for t in (await meetings.free_times(db, settings, user.id, bot, day, 1)).get(day, [])]
    return run(go)


def _add(run, row):
    async def go():
        async with async_session() as db:
            db.add(row)
            await db.commit()
            return row.id
    return run(go)


def _meeting(run, meeting_id):
    async def go():
        async with async_session() as db:
            return await db.get(Meeting, meeting_id)
    return run(go)


def _change(run, meeting_id, **values):
    async def go():
        async with async_session() as db:
            await db.execute(update(Meeting).where(Meeting.id == meeting_id).values(calendar_tried_at=None, **values))
            await db.commit()
    run(go)


def _confirmed(user, bot, day, clock="10:00", **more):
    fields = {"e164": "+919800000001", "name": "Asha Rao", "email": "asha@example.com", "kind": "online", "status": "confirmed", "minutes": 30, "history": [],
              "topic": "Parking", **more}
    return Meeting(user_id=user.id, bot_id=bot, starts_at=stored(_at(day, clock)), **fields)


def test_busy_times_come_off_what_is_offered_on_a_call(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider, purpose="calendar")
    settings = _meeting_settings(run, u, bot, made["id"])
    day = _day()
    assert _free(run, settings, u, bot, day) == ["10:00", "10:30", "11:00", "11:30"]
    provider.busy = [{"start": _at(day, "10:30").astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "end": _at(day, "11:00").astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}]
    async def reread():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(busy_at=None))
            await db.commit()
        await calendars.refresh(made["id"])
    run(reread)
    assert _free(run, settings, u, bot, day) == ["10:00", "11:00", "11:30"]
    async def why(clock):
        async with async_session() as db:
            return await meetings._why_not(db, _at(day, clock), settings, u.id, bot, None, schedule.now_utc())
    assert run(why, "10:30") == "That time is taken." and run(why, "11:00") is None
    calls = len(provider.calls)
    _free(run, settings, u, bot, day)
    assert len(provider.calls) == calls, "a live call never waits for the provider"


def test_busy_times_are_read_once_across_processes(client, make_user, provider, run):
    u = make_user()
    made = connect(client, u, provider, purpose="calendar")
    async def together():
        await asyncio.sleep(0.05)  # the read the connection started
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(busy_at=None))
            await db.commit()
        before = sum(c.endswith("/freeBusy") for c in provider.calls)
        await asyncio.gather(*(calendars.refresh(made["id"]) for _ in range(4)))
        return sum(c.endswith("/freeBusy") for c in provider.calls) - before
    assert run(together) == 1


def test_outlook_counts_busy_away_and_tentative_but_not_free_or_cancelled(client, make_user, provider, run):
    u = make_user()
    provider.address = "priya@contoso.com"
    made = connect(client, u, provider, "microsoft", "calendar")
    event = lambda start, end, show, cancelled=False: {"start": {"dateTime": f"{start}.0000000", "timeZone": "UTC"}, "end": {"dateTime": f"{end}.0000000", "timeZone": "UTC"}, "showAs": show, "isCancelled": cancelled}
    provider.outlook = [event("2026-11-10T05:00:00", "2026-11-10T05:30:00", "busy"), event("2026-11-10T06:00:00", "2026-11-10T06:30:00", "free"),
                        event("2026-11-10T07:00:00", "2026-11-10T07:30:00", "tentative"), event("2026-11-10T08:00:00", "2026-11-10T08:30:00", "busy", True),
                        event("2026-11-10T09:00:00", "2026-11-10T09:30:00", "oof")]
    found = run(calendars.read_busy, made["id"], "microsoft", "priya@contoso.com", datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=1))
    assert [b[0][11:16] for b in found] == ["05:00", "07:00", "09:00"]
    assert calendars._when(found[0][0]) == datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc)


def test_a_confirmed_meeting_goes_on_the_calendar_and_its_meet_link_into_the_confirmation(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot("Sunrise")
    made = connect(client, u, provider, purpose="calendar")
    _meeting_settings(run, u, bot, made["id"])
    day = _day()
    meeting_id = _add(run, _confirmed(u, bot, day))
    run(meetings.send_confirmation, meeting_id)
    meeting = _meeting(run, meeting_id)
    assert meeting.link == "https://meet.google.com/abc-defg-hij" and meeting.calendar_event_id == "event-1" and meeting.calendar_id == made["id"] and meeting.calendar_error is None
    event = provider.events["event-1"]
    assert event["summary"] == "Asha Rao (Sunrise)" and "Parking" in event["description"] and "+919800000001" in event["description"]
    assert event["query"]["sendUpdates"] == "none" and event["query"]["conferenceDataVersion"] == "1", "the person hears from Nimmi, once"
    assert "attendees" not in event
    assert event["start"]["dateTime"] == _at(day, "10:00").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_them = next(m for m in usual if m.to == "asha@example.com")
    assert "meet.google.com/abc-defg-hij" in to_them.text or "joining" in to_them.text.lower()


def test_a_link_someone_set_is_kept_and_no_video_call_is_made(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day(), link="https://zoom.us/j/123"))
    run(calendars.sync, meeting_id)
    assert _meeting(run, meeting_id).link == "https://zoom.us/j/123" and "conferenceData" not in provider.events["event-1"]
    assert provider.events["event-1"]["location"] == "https://zoom.us/j/123"


def test_video_links_can_be_off(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"], calendar_video=False, link="https://meet.example.com/desk")
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    run(calendars.sync, meeting_id)
    assert "conferenceData" not in provider.events["event-1"] and _meeting(run, meeting_id).link is None
    assert provider.events["event-1"]["location"] == "https://meet.example.com/desk"


def test_a_meet_link_made_a_moment_later_is_waited_for(client, make_user, provider, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    provider.meet_late = True
    real = asyncio.sleep
    monkeypatch.setattr(calendars.asyncio, "sleep", lambda s: real(0))
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    run(calendars.sync, meeting_id)
    assert _meeting(run, meeting_id).link == "https://meet.google.com/late-link"


def test_outlook_events_with_teams_and_personal_accounts_without(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    provider.address = "priya@contoso.com"
    _meeting_settings(run, u, bot, connect(client, u, provider, "microsoft", "calendar")["id"], link="https://meet.example.com/desk")
    day = _day()
    meeting_id = _add(run, _confirmed(u, bot, day))
    run(calendars.sync, meeting_id)
    assert _meeting(run, meeting_id).link == "https://teams.microsoft.com/l/abc" and provider.events["event-1"]["onlineMeetingProvider"] == "teamsForBusiness"
    assert provider.events["event-1"]["start"] == {"dateTime": _at(day, "10:00").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}
    provider.personal = True
    second = _add(run, _confirmed(u, bot, day, "11:00"))
    run(calendars.sync, second)
    assert _meeting(run, second).calendar_event_id == "event-2" and _meeting(run, second).link is None, "the event still goes on the calendar; the default link stays"


def test_approving_needs_no_link_when_the_calendar_makes_one(client, make_user, provider, usual, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider, purpose="calendar")
    _meeting_settings(run, u, bot, made["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day(), status="requested"))
    async def approve():
        async with async_session() as db:
            await meetings.approve(db, await db.get(Meeting, meeting_id), by=u.id)
            await db.commit()
    run(approve)
    assert _meeting(run, meeting_id).status == "confirmed"


def test_moved_is_changed_cancelled_is_removed_held_is_kept(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    day = _day()
    meeting_id = _add(run, _confirmed(u, bot, day))
    run(calendars.sync, meeting_id)
    _change(run, meeting_id, starts_at=stored(_at(day, "11:00")))
    run(calendars.sync, meeting_id)
    assert list(provider.events) == ["event-1"] and provider.events["event-1"]["start"]["dateTime"] == _at(day, "11:00").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _change(run, meeting_id, status="done")
    run(calendars.sync, meeting_id)
    assert list(provider.events) == ["event-1"], "a meeting that happened stays on the calendar"
    _change(run, meeting_id, status="confirmed")
    _change(run, meeting_id, status="cancelled")
    run(calendars.sync, meeting_id)
    meeting = _meeting(run, meeting_id)
    assert provider.events == {} and meeting.calendar_event_id is None and meeting.calendar_state is None


def test_an_event_someone_removed_by_hand_is_fine(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    run(calendars.sync, meeting_id)
    provider.events.clear()
    _change(run, meeting_id, status="cancelled")
    run(calendars.sync, meeting_id)
    assert _meeting(run, meeting_id).calendar_event_id is None and _meeting(run, meeting_id).calendar_error is None


def test_a_calendar_that_fails_is_tried_again_and_the_meeting_goes_on(client, make_user, provider, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    provider.event_answer = (500, "busy")
    run(calendars.sync, meeting_id)
    meeting = _meeting(run, meeting_id)
    assert meeting.status == "confirmed" and meeting.calendar_event_id is None and "500" in meeting.calendar_error
    provider.event_answer = None
    _change(run, meeting_id)  # a minute later
    monkeypatch.setattr(calendars, "_last_pass", None)
    run(calendars.tick)
    meeting = _meeting(run, meeting_id)
    assert meeting.calendar_event_id in provider.events and meeting.calendar_error is None


def test_two_processes_make_one_event(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    _meeting_settings(run, u, bot, connect(client, u, provider, purpose="calendar")["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    async def together():
        await asyncio.gather(*(calendars.sync(meeting_id) for _ in range(4)))
    run(together)
    assert len(provider.events) == 1


def test_its_own_meetings_count_as_meetings_not_as_busy(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider, purpose="calendar")
    settings = _meeting_settings(run, u, bot, made["id"], at_once=2)
    day = _day()
    meeting_id = _add(run, _confirmed(u, bot, day))
    run(calendars.sync, meeting_id)
    block = [[_at(day, "10:00").astimezone(timezone.utc).isoformat(), _at(day, "10:30").astimezone(timezone.utc).isoformat()]]
    async def busy():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(busy=block))
            await db.commit()
    run(busy)
    assert "10:00" in _free(run, settings, u, bot, day), "two at once: one seat is still free"


def test_a_disconnected_calendar_lets_go_of_its_events(client, make_user, provider, run):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider, purpose="calendar")
    _meeting_settings(run, u, bot, made["id"])
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    run(calendars.sync, meeting_id)
    client.delete(f"/api/email/connections/{made['id']}", headers=u.h())
    _change(run, meeting_id, status="cancelled")
    run(calendars.sync, meeting_id)
    assert _meeting(run, meeting_id).calendar_event_id is None
    assert _meeting(run, meeting_id).calendar_error is None


def test_a_calendar_needing_reconnecting_is_left_alone_until_it_is(client, make_user, provider, run, monkeypatch):
    u = make_user()
    bot = u.bot()
    made = connect(client, u, provider, purpose="calendar")
    _meeting_settings(run, u, bot, made["id"])
    async def broken():
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == made["id"]).values(status="reconnect"))
            await db.commit()
    run(broken)
    meeting_id = _add(run, _confirmed(u, bot, _day()))
    run(calendars.sync, meeting_id)
    assert provider.events == {}
    again = connect(client, u, provider, purpose="calendar")
    assert again["status"] == "connected"
    monkeypatch.setattr(calendars, "_last_pass", None)
    run(calendars.tick)
    assert _meeting(run, meeting_id).calendar_event_id in provider.events


def test_the_calendar_chosen_must_be_the_workspaces_own(client, make_user, provider):
    u, other = make_user(), make_user()
    bot = u.bot()
    theirs = connect(client, other, provider, purpose="calendar")
    answer = client.put(f"/api/voice/schedule/settings/{bot}", json={"meetings": {"calendar": theirs["id"]}}, headers=u.h())
    assert answer.status_code == 400 and "connected calendars" in answer.json()["detail"]
    mail_only = connect(client, u, provider)
    assert client.put(f"/api/voice/schedule/settings/{bot}", json={"meetings": {"calendar": mail_only["id"]}}, headers=u.h()).status_code == 400
    mine = connect(client, u, provider, purpose="calendar")
    answer = client.put(f"/api/voice/schedule/settings/{bot}", json={"meetings": {"calendar": mine["id"]}}, headers=u.h()).json()
    assert answer["settings"]["meetings"]["calendar"] == mine["id"] and answer["calendars"][0]["address"] == "priya@gmail.com"


def test_booking_times_and_keys_stay_private_in_the_agents_notifications(run):
    """Connections never appear in NotificationLog with a token in the reference."""
    async def go():
        async with async_session() as db:
            return (await db.execute(select(NotificationLog).where(NotificationLog.kind == "mailbox_reconnect"))).scalars().all()
    assert all("token" not in (row.ref_id or "") for row in run(go))
